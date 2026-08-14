"""
Agent & chat endpoints — the core SSE streaming routes plus
workdir, launch, and approval callbacks.
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime

from aiohttp import web
from aiohttp.web import Request, StreamResponse

from ..agent import AgentLoop
from ..ai import create_provider
from ..approval import ApprovalManager
from ..chat_store import ChatStore
from ..config import read_config
from ..constants import IS_WIN, IS_MAC, ROOT_DIR
from ..tools import ToolRegistry
from ..sse import SSEWriter
from ..error_logger import log_api_error


# ── helpers ──────────────────────────────────────────────────────────────────

def _sse_response() -> StreamResponse:
    return StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        },
    )


def _friendly_error(exc: Exception) -> str:
    """Return a user-facing error message.

    Some exceptions (e.g. timeouts) have an empty ``str(exc)`` — without
    this the UI would show a bare "Error:" with no explanation.
    """
    if isinstance(exc, TimeoutError):
        return (
            'Request timed out — the AI provider did not respond in time. '
            'Please try again.'
        )
    return str(exc) or type(exc).__name__ or 'Unknown error'


def _inline_attachments(message: dict) -> str:
    """Inline a message's attachments into its content (for the model)."""
    content = message.get('content', '') or ''
    atts = message.get('attachments') or []
    if not atts:
        return content
    parts = [content]
    for a in atts:
        if isinstance(a, dict):
            name = a.get('name', 'file')
            body = a.get('content', '') or ''
        else:
            name = str(a)
            body = ''
        parts.append(f'Attached file: {name}\n```\n{body}\n```')
    return '\n\n'.join(p for p in parts if p and p.strip())


async def _run_guarded(sse: SSEWriter, coro) -> object:
    """Run *coro* as a task, cancelling it if the client disconnects.

    Returns the task's result on normal completion, ``None`` if it was
    cancelled (client stopped the request). Exceptions from *coro* are
    propagated to the caller.
    """
    task = asyncio.create_task(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=3)
            if done:
                break
            await sse.ping()
            if sse.closed:
                task.cancel()
                break
    except asyncio.CancelledError:
        task.cancel()
        raise
    try:
        return await task
    except asyncio.CancelledError:
        return None


def _save_assistant_reply(
    store: ChatStore,
    chat_id: str,
    user_message: str,
    full_text: str,
    messages: list[dict] | None = None,
    usage: dict | None = None,
    attachments: list[dict] | None = None,
) -> None:
    """Persist user + assistant messages into the chat.

    If *messages* is provided, it replaces the chat history entirely
    (so edits/truncations from the frontend are preserved). Otherwise
    the existing chat is loaded from disk and appended to.
    """
    existing = store.load(chat_id) or store.init_chat(chat_id, user_message[:50])
    if messages is not None:
        existing['messages'] = list(messages)
    user_msg = {'role': 'user', 'content': user_message}
    if attachments:
        user_msg['attachments'] = attachments
    existing['messages'].append(user_msg)
    if full_text:
        existing['messages'].append({'role': 'assistant', 'content': full_text})
    existing['updated'] = datetime.now().isoformat()
    if not existing.get('title') or existing['title'] == 'New Conversation':
        existing['title'] = user_message[:50]

    # Accumulate token usage
    if usage:
        prev = existing.get('total_usage', {})
        for key, val in usage.items():
            prev[key] = prev.get(key, 0) + val
        existing['total_usage'] = prev

    store.save(chat_id, existing)


# ── agent (tool‑calling loop) ────────────────────────────────────────────────

async def _agent(req: Request) -> StreamResponse:
    data = await req.json()
    chat_id = data.get('chatId')
    messages = data.get('messages', [])
    user_message = data.get('userMessage')
    mode = data.get('mode', 'normal')
    cfg = read_config()

    resp = _sse_response()
    await resp.prepare(req)
    sse = SSEWriter(resp)

    if not cfg.get('AI_PROVIDER'):
        await sse.send({'type': 'agent_error', 'error': 'No AI provider configured. Please complete setup first.'})
        await sse.close()
        return resp

    store: ChatStore = req.app['chat_store']
    tools: ToolRegistry = req.app['tool_registry']
    approval: ApprovalManager = req.app['approval']
    provider = create_provider(cfg['AI_PROVIDER'], tools)

    history = messages.copy()
    all_messages = history + [{'role': 'user', 'content': user_message}]

    loop = AgentLoop(provider, tools, approval, tools._work_dir)
    full_text = ''
    total_usage = {}

    async def work():
        nonlocal full_text, total_usage
        full_text, total_usage = await loop.run(all_messages, mode, sse.send)

    try:
        await _run_guarded(sse, work())
    except Exception as e:
        # ❌ Do NOT save the error as an assistant reply — that creates a
        #    feedback loop where the model sees "⚠️ Agent Error: ..." as
        #    its own reply, and on next request the user message is repeated,
        #    creating an ever-growing error chain.
        await sse.send({'type': 'agent_error', 'error': _friendly_error(e)})

    if chat_id:
        _save_assistant_reply(store, chat_id, user_message, full_text, messages, total_usage)

    await sse.close()
    return resp


# ── chat (simple streaming, no tools) ────────────────────────────────────────

async def _chat(req: Request) -> StreamResponse:
    data = await req.json()
    chat_id = data.get('chatId')
    messages = data.get('messages', [])
    user_message = data.get('userMessage')
    attachments = data.get('attachments', [])
    mode = data.get('mode', 'normal')
    cfg = read_config()

    resp = _sse_response()
    await resp.prepare(req)
    sse = SSEWriter(resp)

    if not cfg.get('AI_PROVIDER'):
        await sse.send({'type': 'error', 'content': 'No AI provider configured. Please complete setup first.'})
        await sse.close()
        return resp

    tools: ToolRegistry = req.app['tool_registry']

    from ..agent import get_system_prompt
    sys_content = get_system_prompt(mode, tools._work_dir)
    history = [m for m in messages if m.get('role') != 'system']
    model_history = []
    for m in history:
        mm = dict(m)
        mm['content'] = _inline_attachments(mm)
        mm.pop('attachments', None)
        model_history.append(mm)
    current_user = {'role': 'user', 'content': _inline_attachments({'content': user_message, 'attachments': attachments})}
    all_messages = [{'role': 'system', 'content': sys_content}] + model_history + [current_user]

    full_text = ''
    usage = {}
    error_occurred = False

    async def work():
        nonlocal full_text, usage, error_occurred
        try:
            full_text, usage = await _stream_chat(all_messages, cfg, sse)
        except Exception as e:
            error_occurred = True
            await sse.send({'type': 'error', 'content': _friendly_error(e)})

    await _run_guarded(sse, work())

    if full_text and not error_occurred:
        await sse.send({'type': 'done', 'fullText': full_text, 'usage': usage})
    await sse.close()

    if chat_id:
        store: ChatStore = req.app['chat_store']
        _save_assistant_reply(store, chat_id, user_message, full_text if not error_occurred else '', messages, usage=usage, attachments=attachments)

    return resp


# ── streaming helpers (chat route internals) ─────────────────────────────────

async def _stream_chat(messages: list, cfg: dict, sse: SSEWriter) -> tuple[str, dict]:
    """Stream a chat completion through SSE, returning (full_text, usage)."""
    import re as _re
    from aiohttp import ClientSession, ClientTimeout

    provider = cfg.get('AI_PROVIDER')
    model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
    base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    api_key = cfg.get('OPENAI_API_KEY') or cfg.get('GEMINI_API_KEY') or cfg.get('ANTHROPIC_API_KEY')

    # ── OpenAI / Ollama ──
    if provider in ('openai', 'ollama'):
        payload = {'model': model, 'messages': messages, 'stream': True,
                   'stream_options': {'include_usage': True}}
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        if 'openrouter' in cfg.get('OPENAI_BASE_URL', ''):
            headers['HTTP-Referer'] = 'http://localhost:3000'
            headers['X-Title'] = 'Portable AI Dashboard'

        try:
            full_text = ''
            usage = {}
            async with ClientSession() as session:
                async with session.post(
                    f'{base_url}/chat/completions', json=payload, headers=headers,
                    timeout=ClientTimeout(total=None, connect=15, sock_read=60)
                ) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise Exception(f'API Error: status {resp.status}, body: {error_body[:1000]}')
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if not line.startswith('data: '):
                            continue
                        raw = line[6:].strip()
                        if raw == '[DONE]':
                            continue
                        try:
                            parsed = json.loads(raw)
                            if parsed.get('usage'):
                                usage = parsed['usage']
                            delta_obj = parsed.get('choices', [{}])[0].get('delta', {})
                            reasoning = delta_obj.get('reasoning_content') or delta_obj.get('reasoning') or ''
                            if reasoning:
                                await sse.send({'type': 'reasoning', 'content': reasoning})
                            delta = delta_obj.get('content', '')
                            if delta:
                                full_text += delta
                                await sse.send({'type': 'delta', 'content': delta})
                        except Exception:
                            pass
            return full_text, usage
        except Exception as exc:
            log_api_error(provider, str(exc) or type(exc).__name__ or 'Unknown error', payload, None)
            raise

    # ── Anthropic ──
    if provider == 'anthropic':
        payload = {
            'model': model or 'claude-3-5-sonnet-20241022',
            'messages': messages,
            'max_tokens': 4096,
            'stream': True,
        }
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }

        try:
            full_text = ''
            usage = {}
            async with ClientSession() as session:
                async with session.post(
                    'https://api.anthropic.com/v1/messages', json=payload, headers=headers,
                    timeout=ClientTimeout(total=None, connect=15, sock_read=60)
                ) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise Exception(f'Anthropic API Error: status {resp.status}, body: {error_body[:1000]}')
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if not line.startswith('data: '):
                            continue
                        try:
                            parsed = json.loads(line[6:])
                            ev_type = parsed.get('type')
                            if ev_type == 'message_start':
                                u = (parsed.get('message') or {}).get('usage') or {}
                                usage['prompt_tokens'] = u.get('input_tokens', 0)
                                usage['cache_read_input_tokens'] = u.get('cache_read_input_tokens', 0)
                                usage['cache_creation_input_tokens'] = u.get('cache_creation_input_tokens', 0)
                            elif ev_type == 'message_delta':
                                u = parsed.get('usage') or {}
                                if 'output_tokens' in u:
                                    usage['completion_tokens'] = u['output_tokens']
                            delta = parsed.get('delta', {}).get('text', '')
                            if delta:
                                full_text += delta
                                await sse.send({'type': 'delta', 'content': delta})
                        except Exception:
                            pass
            usage['total_tokens'] = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
            return full_text, usage
        except Exception as exc:
            log_api_error('anthropic', str(exc) or type(exc).__name__ or 'Unknown error', payload, None)
            raise

    # ── Gemini ──
    if provider == 'gemini':
        gem_model = model or 'gemini-2.0-pro-exp-02-05'
        gem_messages = []
        for m in messages:
            role = 'model' if m.get('role') == 'assistant' else 'user'
            gem_messages.append({'role': role, 'parts': [{'text': m.get('content', '')}]})
        payload = {'contents': gem_messages}
        safe_url = (
            f'https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:streamGenerateContent'
            f'?key=***'
        )
        url = (
            f'https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:streamGenerateContent'
            f'?key={api_key}'
        )

        try:
            full_text = ''
            raw_buffer = ''
            usage = {}
            async with ClientSession() as session:
                async with session.post(url, json=payload, headers={'Content-Type': 'application/json'},
                                        timeout=ClientTimeout(total=None, connect=15, sock_read=60)) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise Exception(f'Gemini API Error: status {resp.status}, body: {error_body[:1000]}')
                    async for chunk in resp.content:
                        chunk = chunk.decode('utf-8')
                        raw_buffer += chunk
                        matches = _re.findall(r'"text":\s*"((?:[^"\\]|\\.)*)"', chunk)
                        for m in matches:
                            text = json.loads('{' + m + '}').get('text', '')
                            if text:
                                full_text += text
                                await sse.send({'type': 'delta', 'content': text})

            def _gem_num(name):
                m = _re.search(r'"' + name + r'"\s*:\s*(\d+)', raw_buffer)
                return int(m.group(1)) if m else 0

            usage = {
                'prompt_tokens': _gem_num('promptTokenCount'),
                'completion_tokens': _gem_num('candidatesTokenCount'),
                'total_tokens': _gem_num('totalTokenCount'),
            }
            return full_text, usage
        except Exception as exc:
            log_api_error('gemini', str(exc) or type(exc).__name__ or 'Unknown error',
                          {'url': safe_url, 'payload': payload}, None)
            raise

    await sse.send({'type': 'error', 'content': 'Provider not configured or unsupported.'})
    return '', {}


# ── approval ─────────────────────────────────────────────────────────────────

async def _agent_approve(req: Request) -> web.Response:
    data = await req.json()
    call_id = data.get('callId')
    approved = data.get('approved', False)
    approval: ApprovalManager = req.app['approval']
    found = approval.resolve(call_id, approved)
    return web.json_response({'success': found})


# ── workdir ──────────────────────────────────────────────────────────────────

async def _workdir_get(req: Request) -> web.Response:
    tools: ToolRegistry = req.app['tool_registry']
    return web.json_response({'workDir': tools._work_dir})


async def _workdir_post(req: Request) -> web.Response:
    data = await req.json()
    new_path = data.get('path')
    abs_path = os.path.realpath(new_path)
    if not os.path.exists(abs_path):
        return web.json_response({'error': 'Directory does not exist'}, status=400)
    # Update the tool registry's work dir
    tools: ToolRegistry = req.app['tool_registry']
    tools._work_dir = abs_path
    return web.json_response({'success': True, 'workDir': abs_path})


# ── files (listing inside work_dir, for @-mention autocomplete) ──────────────

async def _files_get(req: Request) -> web.Response:
    tools: ToolRegistry = req.app['tool_registry']
    path = (req.query.get('path') or '.').strip() or '.'
    result = tools.list_files(path)
    if not result.get('ok'):
        return web.json_response({'success': False, 'error': result.get('error')}, status=400)
    return web.json_response({'success': True, 'entries': result['entries']})


# ── launch ───────────────────────────────────────────────────────────────────

async def _launch(req: Request) -> web.Response:
    data = await req.json()
    mode = data.get('mode', 'normal')
    quick_flag = ' --quick' if mode == 'limitless' else ''
    try:
        if IS_WIN:
            bat = os.path.join(ROOT_DIR, 'Windows', 'Start_AI.bat')
            subprocess.Popen(
                ['start', 'cmd', '/k', f'"{bat}{quick_flag}"'],
                cwd=os.path.join(ROOT_DIR, 'Windows'),
                shell=True,
            )
        else:
            platform_dir = 'darwin' if IS_MAC else 'linux'
            script = os.path.join(
                ROOT_DIR, platform_dir,
                'Start_AI.command' if IS_MAC else 'start_ai.sh',
            )
            subprocess.Popen(
                ['bash', f'{script}{quick_flag}'],
                cwd=os.path.join(ROOT_DIR, platform_dir),
            )
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


# ── register ─────────────────────────────────────────────────────────────────

def register(app: web.Application) -> None:
    app.router.add_post('/api/agent', _agent)
    app.router.add_post('/api/chat', _chat)
    app.router.add_post('/api/agent/approve', _agent_approve)
    app.router.add_get('/api/workdir', _workdir_get)
    app.router.add_post('/api/workdir', _workdir_post)
    app.router.add_get('/api/files', _files_get)
    app.router.add_post('/api/launch', _launch)
