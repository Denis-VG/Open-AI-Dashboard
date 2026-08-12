"""
Agent Loop — pure async logic with no HTTP dependencies.

Orchestrates the conversation: sends messages to the AI provider,
handles tool calls, manages approvals, and emits events via a
callback (which may push SSE events, log, or be mocked in tests).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable, Awaitable

from .ai import AIProvider, create_provider
from .approval import ApprovalManager
from .tools import ToolRegistry

logger = logging.getLogger(__name__)

# Event callback signature: async def on_event(event: dict) -> None
EventSink = Callable[[dict], Awaitable[None]]

MAX_ITERATIONS = 15

# Error substrings that indicate the model doesn't support tools.
# Only these trigger a fallback to no-tool mode on iteration 0.
_TOOL_UNSUPPORTED_MARKERS = (
    'tool', 'function', 'not support', 'unrecognized', 'unknown parameter',
    'does not support', 'invalid parameter', 'not allowed',
)

_DEFAULT_SYSTEM_PROMPTS = {
    'normal': (
        'You are a powerful AI coding agent running in a web dashboard. '
        'You have access to tools: write_file (max 10MB), append_file (append), '
        'write_file_chunk (write at offset), read_file (max 512KB), list_directory, '
        'execute_command, search_files. '
        'The current working directory is: {work_dir}. '
        'Before executing write operations, briefly explain what you are about to do. '
        'Use tools to actually perform actions - do not just describe what to do.'
    ),
    'limitless': (
        'You are an autonomous AI coding agent running in Limitless mode. '
        'You have access to tools: write_file (max 10MB), append_file, '
        'write_file_chunk, read_file (max 512KB), list_directory, '
        'execute_command, search_files. '
        'The current working directory is: {work_dir}. '
        'Execute tasks directly and completely without asking for confirmation. '
        'Use tools to actually perform actions. Be decisive and thorough.'
    ),
}


def get_system_prompt(mode: str, work_dir: str) -> str:
    """Return the system prompt for the given mode.

    Loads custom SYSTEM_PROMPT from config if set; falls back to built-in defaults.
    """
    from .config import read_config as _rc
    cfg = _rc()
    custom = cfg.get('SYSTEM_PROMPT', '').strip()

    if custom:
        return custom.format(work_dir=work_dir)

    work_dir_display = os.path.join(work_dir, '')
    return _DEFAULT_SYSTEM_PROMPTS.get(mode, _DEFAULT_SYSTEM_PROMPTS['normal']).format(
        work_dir=work_dir_display
    )


class AgentLoop:
    """Encapsulates a single agent run (one user message → final answer)."""

    def __init__(
        self,
        provider: AIProvider,
        tools: ToolRegistry,
        approval: ApprovalManager,
        work_dir: str,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._approval = approval
        self._work_dir = work_dir

    # ── public API ───────────────────────────────────────────────────────────

    async def run(
        self,
        messages: list[dict],
        mode: str,
        on_event: EventSink,
    ) -> tuple[str, dict[str, int]]:
        """Execute the agent loop.

        Parameters
        ----------
        messages : list[dict]
            The *full* conversation so far (including the latest user message).
            Will be mutated in-place.
        mode : str
            'normal' or 'limitless'.
        on_event : callable
            Async callback receiving typed events (see code for event shapes).

        Returns
        -------
        tuple[str, dict] – (final_text, total_usage)
        """
        # Inject system prompt
        self._inject_system(messages, mode)

        final_text = ''
        total_usage: dict[str, int] = {}

        for iteration in range(MAX_ITERATIONS):
            await on_event({'type': 'agent_thinking', 'iteration': iteration + 1})

            ai_response = await self._call_ai_safely(messages, on_event, iteration)
            if ai_response is None:
                return final_text, total_usage  # error already reported by _call_ai_safely

            # ── accumulate usage ────────────────────────────────────────────
            if ai_response.get('usage'):
                for key, val in ai_response['usage'].items():
                    if isinstance(val, (int, float)):
                        total_usage[key] = total_usage.get(key, 0) + val

            # ── try to parse JSON tool-calls from text ───────────────────────
            self._extract_inline_tools(ai_response, on_event, iteration)

            # Emit reasoning if both text and tools are present
            if ai_response.get('content') and ai_response.get('tool_calls'):
                await on_event({
                    'type': 'agent_reasoning',
                    'content': ai_response['content'],
                    'iteration': iteration + 1,
                })

            # ── execute tool calls ───────────────────────────────────────────
            if ai_response.get('tool_calls'):
                self._provider.append_assistant(messages, ai_response)
                await self._execute_tools(ai_response['tool_calls'], messages, mode, on_event)
                continue  # next iteration

            # ── no tool calls → final text ───────────────────────────────────
            final_text = ai_response.get('content', '')
            if final_text:
                await on_event({'type': 'agent_text', 'content': final_text})
            break

        await on_event({
            'type': 'done',
            'fullText': final_text,
            'usage': total_usage,
        })
        return final_text, total_usage

    # ── helpers ──────────────────────────────────────────────────────────────

    def _inject_system(self, messages: list[dict], mode: str) -> None:
        """Remove existing system messages and prepend the appropriate one."""
        messages[:] = [m for m in messages if m.get('role') != 'system']
        sys_content = get_system_prompt(mode, self._work_dir)
        messages.insert(0, {'role': 'system', 'content': sys_content})

    def _looks_like_tool_error(self, err: str) -> bool:
        """Return True if the error message indicates the model doesn't
        support tools/function-calling (i.e. a fallback is worth trying)."""
        err_lower = err.lower()
        return any(marker in err_lower for marker in _TOOL_UNSUPPORTED_MARKERS)

    async def _call_ai_safely(
        self, messages: list[dict], on_event: EventSink, iteration: int
    ) -> dict | None:
        """Call AI; on first-iteration tool-related errors, fall back to
        no-tools mode.  Non-tool errors (auth, connectivity, bad model, …)
        are reported immediately without a pointless retry."""
        try:
            return await self._provider.call(messages, read_config(), include_tools=True)
        except Exception as exc:
            err = str(exc) or 'Unknown error'

            # Only attempt fallback on errors that smell like tool-related issues
            if iteration == 0 and self._looks_like_tool_error(err):
                try:
                    await on_event({
                        'type': 'agent_reasoning',
                        'content': 'Tool calling not supported by this model, falling back to chat mode...',
                        'iteration': 1,
                    })
                    return await self._provider.call(messages, read_config(), include_tools=False)
                except Exception as exc2:
                    err2 = str(exc2) or 'Unknown error on fallback'
                    logger.error(f'Agent fallback error: {exc2}')
                    await on_event({'type': 'agent_error', 'error': err2})
                    return None

            # Either not first iteration, or error doesn't look tool-related
            logger.error(f'Agent error: {exc}')
            await on_event({'type': 'agent_error', 'error': err})
            return None

    def _extract_inline_tools(
        self, ai_response: dict, on_event: EventSink, iteration: int
    ) -> None:
        """Try to parse JSON tool calls from the text response."""
        if ai_response.get('tool_calls'):
            return  # already have structured tool calls
        content = ai_response.get('content', '').strip()
        if not content:
            return

        json_str: str | None = None
        # <tools>...</tools>
        m = re.search(r'<tools>\s*([\s\S]*?)\s*</tools>', content)
        if m:
            json_str = m.group(1).strip()
        else:
            # ```json ... ```
            m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if m:
                json_str = m.group(1).strip()
            else:
                json_str = content

        if not json_str:
            return

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            if parsed and isinstance(parsed, dict) and 'name' in parsed and 'arguments' in parsed:
                ai_response['tool_calls'] = [{
                    'id': f'manual_{int(time.time() * 1000)}',
                    'name': parsed['name'],
                    'args': parsed['arguments'],
                }]
                ai_response['content'] = ''
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            logger.debug(f'JSON parse error in agent for: {json_str[:200]}')

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        messages: list[dict],
        mode: str,
        on_event: EventSink,
    ) -> None:
        """Execute each tool call, handling approvals."""
        for tc in tool_calls:
            is_write = self._tools.is_write_tool(tc['name'])
            needs_approval = is_write and mode != 'limitless'

            await on_event({
                'type': 'tool_call',
                'id': tc['id'],
                'name': tc['name'],
                'args': tc['args'],
                'needs_approval': needs_approval,
            })

            if needs_approval:
                await on_event({
                    'type': 'approval_needed',
                    'id': tc['id'],
                    'name': tc['name'],
                    'args': tc['args'],
                })
                approved = await self._approval.wait_for_approval(tc['id'])
                if not approved:
                    reject = {'success': False, 'error': 'User rejected this action'}
                    self._provider.append_tool_result(messages, tc, reject)
                    await on_event({'type': 'tool_rejected', 'id': tc['id']})
                    continue

            result = await self._tools.execute(tc['name'], tc['args'])
            self._provider.append_tool_result(messages, tc, result)
            await on_event({
                'type': 'tool_result',
                'id': tc['id'],
                'name': tc['name'],
                'result': result,
            })


# ── tiny import helper (avoids circular imports) ─────────────────────────────

def read_config() -> dict[str, str]:
    from .config import read_config as _rc
    return _rc()
