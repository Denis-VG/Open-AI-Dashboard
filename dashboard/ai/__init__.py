"""
AI Provider abstraction layer.

Each provider knows how to:
 - format tool definitions for its API
 - call its API (non-streaming, with tool support)
 - append assistant messages to the conversation
 - append tool results to the conversation
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from aiohttp import ClientSession, ClientTimeout

from ..tools import ToolRegistry
from ..error_logger import log_api_error

logger = logging.getLogger(__name__)

# Default timeout for AI API calls (seconds)
# Reasoning models (e.g. DeepSeek) can think for a couple of minutes before
# producing the first token, so a short total timeout truncates valid runs.
_API_TIMEOUT = 300


# ── helpers ──────────────────────────────────────────────────────────────────

async def _safe_read_json(resp) -> dict:
    """Read response body as text first, then try JSON.
    
    Some providers (e.g. DeepSeek) return non-JSON content-types
    (application/octet-stream) even for error responses.  Calling
    resp.json() directly crashes before we can inspect the real error.
    """
    raw = await resp.text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Return a synthetic dict so error-handling code still works
        return {'_raw_body': raw, '_parse_error': True}


async def _parse_openai_sse(line_iter, on_event, emit_delta: bool = True) -> dict:
    """Parse an OpenAI-compatible SSE stream.

    Emits ``reasoning`` and ``delta`` events (when ``on_event`` is given) and
    returns a normalised ``{content, reasoning, tool_calls, usage}`` dict.
    """
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    usage: dict = {}

    async for raw_line in line_iter:
        line = raw_line.decode('utf-8').strip()
        if not line.startswith('data: '):
            continue
        data_str = line[6:].strip()
        if data_str == '[DONE]':
            continue
        try:
            parsed = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if parsed.get('usage'):
            usage = parsed['usage']
        choices = parsed.get('choices') or []
        if not choices:
            continue
        delta = choices[0].get('delta') or {}

        reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
        if reasoning:
            reasoning_parts.append(reasoning)
            if on_event is not None:
                await on_event({'type': 'reasoning', 'content': reasoning})

        content = delta.get('content')
        if content:
            content_parts.append(content)
            if on_event is not None and emit_delta:
                await on_event({'type': 'delta', 'content': content})

        for tcd in delta.get('tool_calls') or []:
            idx = tcd.get('index', 0)
            acc = tool_acc.setdefault(idx, {'id': '', 'name': '', 'args': []})
            if tcd.get('id'):
                acc['id'] = tcd['id']
            fn = tcd.get('function') or {}
            if fn.get('name'):
                acc['name'] += fn['name']
            if fn.get('arguments'):
                acc['args'].append(fn['arguments'])

    tool_calls = []
    for idx in sorted(tool_acc):
        acc = tool_acc[idx]
        args_str = ''.join(acc['args'])
        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({'id': acc['id'], 'name': acc['name'], 'args': args})

    return {
        'content': ''.join(content_parts),
        'reasoning': ''.join(reasoning_parts),
        'tool_calls': tool_calls,
        'usage': usage,
    }


# ── abstract base ────────────────────────────────────────────────────────────

class AIProvider(ABC):
    """Abstract AI provider."""

    def __init__(self, tools: ToolRegistry) -> None:
        self._tools = tools

    @abstractmethod
    async def call(self, messages: list[dict], cfg: dict, include_tools: bool = True) -> dict:
        """Call the AI model and return a normalised response dict with keys:
           - content  : str
           - tool_calls : list[dict] with keys id, name, args
        """
        ...

    async def stream(
        self,
        messages: list[dict],
        cfg: dict,
        include_tools: bool = True,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
        emit_delta: bool = True,
    ) -> dict:
        """Stream a completion, emitting ``reasoning``/``delta`` events and
        returning the normalised response dict (with ``tool_calls``).

        Default implementation falls back to non-streaming :meth:`call` and
        emits the full reasoning/text as a single event each.
        """
        result = await self.call(messages, cfg, include_tools=include_tools)
        if on_event is not None:
            if result.get('reasoning'):
                await on_event({'type': 'reasoning', 'content': result['reasoning']})
            if result.get('content') and emit_delta:
                await on_event({'type': 'delta', 'content': result['content']})
        return result

    @abstractmethod
    def append_assistant(self, messages: list[dict], ai_response: dict) -> None:
        """Append the model's response (with possible tool_calls) to `messages` in-place."""
        ...

    @abstractmethod
    def append_tool_result(self, messages: list[dict], tool_call: dict, result: Any) -> None:
        """Append a tool-execution result to `messages` in-place."""
        ...


# ── OpenAI / Ollama (shared OpenAI-compatible protocol) ──────────────────────

class OpenAIProvider(AIProvider):
    """OpenAI, Ollama, OpenRouter, and any OpenAI-compatible endpoint."""

    async def call(self, messages: list[dict], cfg: dict, include_tools: bool = True) -> dict:
        model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
        base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        api_key = cfg.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError('OPENAI_API_KEY missing')

        payload: dict[str, Any] = {
            'model': model,
            'messages': messages,
            'stream': False,
        }
        if include_tools:
            payload['tools'] = self._tools.for_openai()

        headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        if 'openrouter' in cfg.get('OPENAI_BASE_URL', ''):
            headers['HTTP-Referer'] = 'http://localhost:3000'
            headers['X-Title'] = 'Portable AI Agent'

        try:
            async with ClientSession() as session:
                async with session.post(
                    f'{base_url}/chat/completions',
                    json=payload, headers=headers,
                    timeout=ClientTimeout(total=_API_TIMEOUT)
                ) as resp:
                    data = await _safe_read_json(resp)

                    if resp.status != 200:
                        err = data.get('error', {})
                        if isinstance(err, dict):
                            err = err.get('message', 'Unknown error')
                        raw_body = data.get('_raw_body', '')
                        if raw_body and not isinstance(err, str):
                            err = raw_body[:500]
                        raise Exception(f'API Error: {err} (status {resp.status})')

                    choice = data.get('choices', [{}])[0]
                    if not choice:
                        raise Exception('No choices in response')
                    message = choice.get('message', {})
                    if not message:
                        raise Exception('No message in choice')

                    tool_calls = []
                    for tc in message.get('tool_calls', []):
                        try:
                            args = json.loads(tc.get('function', {}).get('arguments', '{}'))
                        except (json.JSONDecodeError, KeyError):
                            args = {}
                        tool_calls.append({
                            'id': tc.get('id', ''),
                            'name': tc.get('function', {}).get('name', ''),
                            'args': args,
                        })

                    return {
                        'content': message.get('content', ''),
                        'reasoning': message.get('reasoning_content') or message.get('reasoning') or '',
                        'tool_calls': tool_calls,
                        'raw_message': message,
                        'usage': data.get('usage', {}),
                    }
        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            log_api_error('openai', err_msg, payload,
                          _try_get_response(exc, None))
            raise

    async def stream(
        self,
        messages: list[dict],
        cfg: dict,
        include_tools: bool = True,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
        emit_delta: bool = True,
    ) -> dict:
        model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
        base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        api_key = cfg.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError('OPENAI_API_KEY missing')

        payload: dict[str, Any] = {
            'model': model,
            'messages': messages,
            'stream': True,
            'stream_options': {'include_usage': True},
        }
        if include_tools:
            payload['tools'] = self._tools.for_openai()

        headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        if 'openrouter' in cfg.get('OPENAI_BASE_URL', ''):
            headers['HTTP-Referer'] = 'http://localhost:3000'
            headers['X-Title'] = 'Portable AI Agent'

        try:
            async with ClientSession() as session:
                async with session.post(
                    f'{base_url}/chat/completions',
                    json=payload, headers=headers,
                    timeout=ClientTimeout(total=_API_TIMEOUT, connect=15, sock_read=120),
                ) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise Exception(f'API Error: status {resp.status}, body: {error_body[:1000]}')
                    return await _parse_openai_sse(resp.content, on_event, emit_delta)
        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            log_api_error('openai', err_msg, payload, _try_get_response(exc, None))
            raise

    def append_assistant(self, messages: list[dict], ai_response: dict) -> None:
        if 'raw_message' in ai_response:
            messages.append(ai_response['raw_message'])
            return
        msg: dict[str, Any] = {'role': 'assistant', 'content': ai_response.get('content', '')}
        if ai_response.get('tool_calls'):
            msg['tool_calls'] = [
                {
                    'id': tc['id'],
                    'type': 'function',
                    'function': {
                        'name': tc['name'],
                        'arguments': json.dumps(tc['args']),
                    }
                }
                for tc in ai_response['tool_calls']
            ]
        messages.append(msg)

    def append_tool_result(self, messages: list[dict], tool_call: dict, result: Any) -> None:
        result_str = result if isinstance(result, str) else json.dumps(result)
        messages.append({
            'role': 'tool',
            'tool_call_id': tool_call['id'],
            'content': result_str,
        })


# ── Anthropic ────────────────────────────────────────────────────────────────

class AnthropicProvider(AIProvider):
    """Anthropic Claude API with prompt caching."""

    async def call(self, messages: list[dict], cfg: dict, include_tools: bool = True) -> dict:
        model = cfg.get('AI_DISPLAY_MODEL', 'claude-3-5-sonnet-20241022')
        api_key = cfg.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError('ANTHROPIC_API_KEY missing')

        system = ''
        filtered = []
        for m in messages:
            if m.get('role') == 'system':
                system = m.get('content', '')
            else:
                filtered.append(m)

        # Add cache_control to last user message
        cached_filtered = [dict(m) for m in filtered]
        if cached_filtered and cached_filtered[-1]['role'] == 'user':
            last = cached_filtered[-1]
            if isinstance(last.get('content'), str):
                last['content'] = [{'type': 'text', 'text': last['content'], 'cache_control': {'type': 'ephemeral'}}]

        payload: dict[str, Any] = {
            'model': model,
            'messages': cached_filtered,
            'max_tokens': 4096,
        }
        if system:
            payload['system'] = [{
                'type': 'text',
                'text': system,
                'cache_control': {'type': 'ephemeral'},
            }]
        if include_tools:
            payload['tools'] = self._tools.for_anthropic()

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'anthropic-beta': 'prompt-caching-2024-07-31',
        }

        base_url = cfg.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com/v1')
        try:
            async with ClientSession() as session:
                async with session.post(
                    f'{base_url.rstrip("/")}/messages',
                    json=payload, headers=headers,
                    timeout=ClientTimeout(total=_API_TIMEOUT)
                ) as resp:
                    data = await _safe_read_json(resp)

                    if resp.status != 200:
                        err = data.get('error', {})
                        if isinstance(err, dict):
                            err = err.get('message', 'Unknown error')
                        raw_body = data.get('_raw_body', '')
                        if raw_body and not isinstance(err, str):
                            err = raw_body[:500]
                        raise Exception(f'Anthropic API Error: {err}')

                    content = data.get('content', [])
                    text_parts = [c.get('text', '') for c in content if c.get('type') == 'text']
                    tool_parts = [c for c in content if c.get('type') == 'tool_use']

                    return {
                        'content': '\n'.join(text_parts),
                        'tool_calls': [
                            {'id': tc['id'], 'name': tc['name'], 'args': tc.get('input', {})}
                            for tc in tool_parts
                        ],
                        'stop_reason': data.get('stop_reason'),
                        'usage': data.get('usage', {}),
                    }
        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            log_api_error('anthropic', err_msg, payload,
                          _try_get_response(exc, None))
            raise

    def append_assistant(self, messages: list[dict], ai_response: dict) -> None:
        content = []
        if ai_response.get('content'):
            content.append({'type': 'text', 'text': ai_response['content']})
        for tc in ai_response.get('tool_calls', []):
            content.append({
                'type': 'tool_use',
                'id': tc['id'],
                'name': tc['name'],
                'input': tc['args'],
            })
        messages.append({'role': 'assistant', 'content': content})

    def append_tool_result(self, messages: list[dict], tool_call: dict, result: Any) -> None:
        result_str = result if isinstance(result, str) else json.dumps(result)
        messages.append({
            'role': 'user',
            'content': [
                {
                    'type': 'tool_result',
                    'tool_use_id': tool_call['id'],
                    'content': result_str,
                }
            ]
        })


# ── Gemini ───────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    """Google Gemini API."""

    async def call(self, messages: list[dict], cfg: dict, include_tools: bool = True) -> dict:
        model = cfg.get('AI_DISPLAY_MODEL', 'gemini-2.0-pro-exp-02-05')
        api_key = cfg.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError('GEMINI_API_KEY missing')

        contents = []
        system_instruction = None
        for m in messages:
            role = m.get('role')
            if role == 'system':
                system_instruction = m.get('content')
                continue
            gemini_role = 'model' if role == 'assistant' else 'user'
            if isinstance(m.get('content'), str):
                contents.append({'role': gemini_role, 'parts': [{'text': m['content']}]})
            elif m.get('parts'):
                contents.append({'role': gemini_role, 'parts': m['parts']})

        payload: dict[str, Any] = {'contents': contents}
        if include_tools:
            payload['tools'] = self._tools.for_gemini()
        if system_instruction:
            payload['system_instruction'] = {'parts': [{'text': system_instruction}]}

        url = (
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            f'?key={api_key}'
        )
        # Mask the key in the logged URL
        safe_url = (
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            f'?key=***'
        )

        try:
            async with ClientSession() as session:
                async with session.post(
                    url, json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=ClientTimeout(total=_API_TIMEOUT)
                ) as resp:
                    data = await _safe_read_json(resp)

                    if resp.status != 200:
                        err = data.get('error', {})
                        if isinstance(err, dict):
                            err = err.get('message', 'Unknown error')
                        raw_body = data.get('_raw_body', '')
                        if raw_body and not isinstance(err, str):
                            err = raw_body[:500]
                        raise Exception(f'Gemini API Error: {err}')

                    candidates = data.get('candidates', [])
                    if not candidates:
                        raise Exception('No response from Gemini')
                    parts = candidates[0].get('content', {}).get('parts', [])

                    text_parts = [p['text'] for p in parts if 'text' in p]
                    func_parts = [p for p in parts if 'functionCall' in p]

                    tool_calls = []
                    for idx, p in enumerate(func_parts):
                        tool_calls.append({
                            'id': f'gemini_call_{int(time.time() * 1000)}_{idx}',
                            'name': p['functionCall']['name'],
                            'args': p['functionCall'].get('args', {}),
                        })

                    return {
                        'content': '\n'.join(text_parts),
                        'tool_calls': tool_calls,
                        'usage': data.get('usageMetadata', {}),
                    }
        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            # Log the payload + masked URL as request body
            log_api_error('gemini', err_msg,
                          {'url': safe_url, 'payload': payload},
                          _try_get_response(exc, None))
            raise

    def append_assistant(self, messages: list[dict], ai_response: dict) -> None:
        parts = []
        if ai_response.get('content'):
            parts.append({'text': ai_response['content']})
        for tc in ai_response.get('tool_calls', []):
            parts.append({
                'functionCall': {
                    'name': tc['name'],
                    'args': tc['args'],
                }
            })
        messages.append({'role': 'model', 'parts': parts})

    def append_tool_result(self, messages: list[dict], tool_call: dict, result: Any) -> None:
        messages.append({
            'role': 'user',
            'parts': [
                {
                    'functionResponse': {
                        'name': tool_call['name'],
                        'response': {'result': result},
                    }
                }
            ]
        })


# ── helpers ──────────────────────────────────────────────────────────────────

def _try_get_response(exc: Exception, default: Any = None) -> Any:
    """Attempt to extract response data from an exception if available."""
    # Some aiohttp exceptions may carry the response; try common patterns
    for attr in ('response', 'resp', 'body'):
        val = getattr(exc, attr, None)
        if val is not None:
            try:
                if hasattr(val, 'json'):
                    return val.json()
            except Exception:
                pass
            try:
                return str(val)[:5000]
            except Exception:
                pass
    return default


# ── factory ──────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[AIProvider]] = {
    'openai': OpenAIProvider,
    'ollama': OpenAIProvider,  # OpenAI-compatible
    'anthropic': AnthropicProvider,
    'gemini': GeminiProvider,
}


def create_provider(name: str, tools: ToolRegistry) -> AIProvider:
    """Create the appropriate AIProvider for the given provider name."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f'Unsupported provider: {name}')
    return cls(tools)
