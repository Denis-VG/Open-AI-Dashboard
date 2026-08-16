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

    # Accumulate token usage (numeric fields only — some providers include
    # nested detail objects like prompt_tokens_details, which must not be summed)
    if usage:
        prev = existing.get('total_usage', {})
        for key, val in usage.items():
            if isinstance(val, (int, float)):
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
        await sse.send({'type': 'error', 'content': 'No AI provider configured. Please complete setup first.'})
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
        await sse.send({'type': 'error', 'content': _friendly_error(e)})

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
    provider = create_provider(cfg['AI_PROVIDER'], tools)

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
            result = await provider.stream(all_messages, cfg, include_tools=False, on_event=sse.send)
            full_text = result.get('content', '')
            usage = result.get('usage', {})
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
