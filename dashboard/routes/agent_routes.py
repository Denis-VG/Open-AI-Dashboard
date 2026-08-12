"""
Agent & chat endpoints — the core SSE streaming routes plus
workdir, launch, and approval callbacks.
"""

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


def _save_assistant_reply(
    store: ChatStore,
    chat_id: str,
    user_message: str,
    full_text: str,
    messages: list[dict] | None = None,
) -> None:
    """Persist user + assistant messages into the chat.

    If *messages* is provided, it replaces the chat history entirely
    (so edits/truncations from the frontend are preserved). Otherwise
    the existing chat is loaded from disk and appended to.
    """
    existing = store.load(chat_id) or store.init_chat(chat_id, user_message[:50])
    if messages is not None:
        existing['messages'] = list(messages)
    existing['messages'].append({'role': 'user', 'content': user_message})
    existing['messages'].append({'role': 'assistant', 'content': full_text})
    existing['updated'] = datetime.now().isoformat()
    if not existing.get('title') or existing['title'] == 'New Conversation':
        existing['title'] = user_message[:50]
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

    try:
        full_text = await loop.run(all_messages, mode, sse.send)
        if chat_id and full_text:
            _save_assistant_reply(store, chat_id, user_message, full_text, messages)
    except Exception as e:
        # ❌ Do NOT save the error as an assistant reply — that creates a
        #    feedback loop where the model sees "⚠️ Agent Error: ..." as
        #    its own reply, and on next request the user message is repeated,
        #    creating an ever-growing error chain.
        await sse.send({'type': 'agent_error', 'error': str(e)})

    await sse.close()
    return resp


# ── chat (simple streaming, no tools) ────────────────────────────────────────

async def _chat(req: Request) -> StreamResponse:
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
        await sse.send({'type': 'error', 'content': 'No AI provider configured. Please complete setup first.'})
        await sse.close()
        return resp

    tools: ToolRegistry = req.app['tool_registry']

    from ..agent import get_system_prompt
    sys_content = get_system_prompt(mode, tools._work_dir)
    history = [m for m in messages if m.get('role') != 'system']
    all_messages = [{'role': 'system', 'content': sys_content}] + history + [{'role': 'user', 'content': user_message}]

    full_text = ''
    try:
        full_text = await _stream_chat(all_messages, cfg, sse)
    except Exception as e:
        await sse.send({'type': 'error', 'content': str(e)})
    finally:
        if full_text:
            await sse.send({'type': 'done', 'fullText': full_text})
        await sse.close()

    if chat_id and full_text:
        store: ChatStore = req.app['chat_store']
        _save_assistant_reply(store, chat_id, user_message, full_text, messages)

    return resp


# ── streaming helpers (chat route internals) ─────────────────────────────────

async def _stream_chat(messages: list, cfg: dict, sse: SSEWriter) -> str:
    """Stream a chat completion through SSE, returning the full text."""
    import re as _re
    from aiohttp import ClientSession

    provider = cfg.get('AI_PROVIDER')
    model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
    base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    api_key = cfg.get('OPENAI_API_KEY') or cfg.get('GEMINI_API_KEY') or cfg.get('ANTHROPIC_API_KEY')

    # ── OpenAI / Ollama ──
    if provider in ('openai', 'ollama'):
        payload = {'model': model, 'messages': messages, 'stream': True}
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        if 'openrouter' in cfg.get('OPENAI_BASE_URL', ''):
            headers['HTTP-Referer'] = 'http://localhost:3000'
            headers['X-Title'] = 'Portable AI Dashboard'

        try:
            full_text = ''
            async with ClientSession() as session:
                async with session.post(
                    f'{base_url}/chat/completions', json=payload, headers=headers, timeout=60
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
                            delta = parsed.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if delta:
                                full_text += delta
                                await sse.send({'type': 'delta', 'content': delta})
                        except Exception:
                            pass
            return full_text
        except Exception as exc:
            log_api_error(provider, str(exc), payload, None)
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
            async with ClientSession() as session:
                async with session.post(
                    'https://api.anthropic.com/v1/messages', json=payload, headers=headers, timeout=60
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
                            delta = parsed.get('delta', {}).get('text', '')
                            if delta:
                                full_text += delta
                                await sse.send({'type': 'delta', 'content': delta})
                        except Exception:
                            pass
            return full_text
        except Exception as exc:
            log_api_error('anthropic', str(exc), payload, None)
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
            async with ClientSession() as session:
                async with session.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=60) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise Exception(f'Gemini API Error: status {resp.status}, body: {error_body[:1000]}')
                    async for chunk in resp.content:
                        chunk = chunk.decode('utf-8')
                        matches = _re.findall(r'"text":\s*"((?:[^"\\]|\\.)*)"', chunk)
                        for m in matches:
                            text = json.loads('{' + m + '}').get('text', '')
                            if text:
                                full_text += text
                                await sse.send({'type': 'delta', 'content': text})
            return full_text
        except Exception as exc:
            log_api_error('gemini', str(exc),
                          {'url': safe_url, 'payload': payload}, None)
            raise

    await sse.send({'type': 'error', 'content': 'Provider not configured or unsupported.'})
    return ''


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
    app.router.add_post('/api/launch', _launch)
