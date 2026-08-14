"""
Tool Registry — definitions and execution dispatch.

Owns the canonical TOOL_DEFS list, knows which tools are "write"
tools (require approval in normal mode), and provides provider-
specific formatting helpers.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Any

from ..constants import IS_WIN

logger = logging.getLogger(__name__)

# ── raw tool definitions (provider-agnostic) ─────────────────────

TOOL_DEFS: list[dict] = [
    {
        'name': 'write_file',
        'description': (
            'Create or overwrite a file with the given content. '
            'Creates parent directories automatically. Max size: 10 MB. '
            'For larger files, use append_file or write_file_chunk.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to the working directory'},
                'content': {'type': 'string', 'description': 'The full content to write to the file'}
            },
            'required': ['path', 'content']
        }
    },
    {
        'name': 'read_file',
        'description': (
            'Read the contents of a file. Max size: 512 KB. For larger files, '
            'use execute_command with head/tail/grep or request chunked reading.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to the working directory'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'append_file',
        'description': (
            'Append text content to the end of a file. Creates the file if it '
            'does not exist. Useful for building large files incrementally.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to the working directory'},
                'content': {'type': 'string', 'description': 'Text content to append to the file'}
            },
            'required': ['path', 'content']
        }
    },
    {
        'name': 'write_file_chunk',
        'description': (
            'Write content to a file at a specific byte offset (overwrites from '
            'that position). Useful for writing large files in parts. If offset '
            'is beyond the current file size, the file is extended with null bytes.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to the working directory'},
                'content': {'type': 'string', 'description': 'Text content to write'},
                'offset': {
                    'type': 'integer',
                    'description': 'Byte offset to start writing at (0 = beginning of file). '
                                   'If file is shorter, it will be extended.'
                }
            },
            'required': ['path', 'content', 'offset']
        }
    },
    {
        'name': 'list_directory',
        'description': 'List all files and subdirectories in a directory.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {
                    'type': 'string',
                    'description': 'Directory path relative to working directory. Use "." for current directory.'
                }
            },
            'required': ['path']
        }
    },
    {
        'name': 'execute_command',
        'description': (
            'Execute a shell command and return its output. Use this for running '
            'scripts, installing packages, compiling code, git operations, etc.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'The shell command to execute'}
            },
            'required': ['command']
        }
    },
    {
        'name': 'search_files',
        'description': (
            'Search for a text pattern in files within a directory. '
            'Returns matching lines with file names and line numbers.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Text pattern to search for'},
                'path': {
                    'type': 'string',
                    'description': 'Directory to search in, relative to working directory. Use "." for current directory.'
                }
            },
            'required': ['pattern', 'path']
        }
    }
]

WRITE_TOOLS = {'write_file', 'append_file', 'write_file_chunk'}
EXEC_TOOLS = {'execute_command'}
DANGEROUS_TOOLS = WRITE_TOOLS | EXEC_TOOLS


# ── ToolRegistry ──────────────────────────────────────────────────

class PathOutsideWorkDirError(ValueError):
    """Raised when a tool-supplied path escapes the working directory."""


class ToolRegistry:
    """Holds tool definitions and executes tool calls with path safety."""

    def __init__(self, work_dir: str) -> None:
        self._work_dir = work_dir
        self._write_tools = WRITE_TOOLS
        self._dangerous_tools = DANGEROUS_TOOLS

    # ── path resolution ───────────────────────────────────────────

    @staticmethod
    def _is_within(root: str, candidate: str) -> bool:
        """Return True if *candidate* is *root* or a path inside it.

        Comparison is case-insensitive on Windows (via ``normcase``) and
        follows symlinks (via ``realpath``), so a symlink pointing outside
        the working directory is rejected just like a literal ``..`` step.
        """
        root_n = os.path.normcase(os.path.realpath(root))
        cand_n = os.path.normcase(os.path.realpath(candidate))
        if cand_n == root_n:
            return True
        prefix = root_n + os.sep if not root_n.endswith(os.sep) else root_n
        return cand_n.startswith(prefix)

    def resolve_path(self, rel_path: str) -> str:
        """Convert a tool-supplied path to a safe absolute path inside the
        working directory.

        Rejects absolute paths outside the working directory, ``..``
        traversal, and symlinks that resolve outside it. Raises
        :class:`PathOutsideWorkDirError` on any escape attempt.
        """
        if not isinstance(rel_path, str) or not rel_path.strip():
            raise PathOutsideWorkDirError('Path must be a non-empty string')

        root = os.path.realpath(self._work_dir)
        if os.path.isabs(rel_path):
            candidate = os.path.realpath(os.path.normpath(rel_path))
        else:
            candidate = os.path.realpath(
                os.path.normpath(os.path.join(self._work_dir, rel_path))
            )

        if not self._is_within(root, candidate):
            raise PathOutsideWorkDirError(
                f'Path escapes working directory: {rel_path!r} '
                f'(resolved to {candidate!r})'
            )
        return candidate

    def list_files(self, rel_path: str = '.') -> dict:
        """List files/dirs inside the working directory (confined).

        Returns ``{'ok': True, 'entries': [...]}`` or ``{'ok': False, 'error': ...}``.
        Each entry is ``{'name', 'type' ('file'|'dir'), 'path'}`` where *path* is
        relative to the working directory and uses forward slashes.
        """
        try:
            full = self.resolve_path(rel_path or '.')
        except PathOutsideWorkDirError as exc:
            return {'ok': False, 'error': str(exc)}

        if not os.path.isdir(full):
            return {'ok': False, 'error': f'Not a directory: {rel_path}'}

        try:
            names = sorted(os.listdir(full))
        except OSError as exc:
            return {'ok': False, 'error': str(exc)}

        entries: list[dict] = []
        for name in names:
            p = os.path.join(full, name)
            try:
                isdir = os.path.isdir(p)
                isfile = os.path.isfile(p)
            except OSError:
                continue
            if not (isdir or isfile):
                continue
            # Always hide .git; keep dot-files (e.g. .env, .gitignore) hidden,
            # but show dot-directories (e.g. .github, .vscode) in @-autocomplete.
            if name.startswith('.') and (name == '.git' or not isdir):
                continue
            rel = os.path.relpath(p, self._work_dir).replace(os.sep, '/')
            entries.append({
                'name': name,
                'type': 'dir' if isdir else 'file',
                'path': rel,
            })

        entries.sort(key=lambda e: (0 if e['type'] == 'dir' else 1, e['name'].lower()))
        return {'ok': True, 'entries': entries[:500]}

    # ── definitions ────────────────────────────────────────────────

    @property
    def definitions(self) -> list[dict]:
        return TOOL_DEFS

    def for_openai(self) -> list[dict]:
        return [
            {
                'type': 'function',
                'function': {
                    'name': t['name'],
                    'description': t['description'],
                    'parameters': t['parameters']
                }
            }
            for t in TOOL_DEFS
        ]

    def for_anthropic(self) -> list[dict]:
        return [
            {
                'name': t['name'],
                'description': t['description'],
                'input_schema': t['parameters']
            }
            for t in TOOL_DEFS
        ]

    def for_gemini(self) -> list[dict]:
        return [
            {
                'function_declarations': [
                    {
                        'name': t['name'],
                        'description': t['description'],
                        'parameters': t['parameters']
                    }
                    for t in TOOL_DEFS
                ]
            }
        ]

    # ── helpers ────────────────────────────────────────────────────

    def is_write_tool(self, name: str) -> bool:
        return name in self._write_tools

    def needs_approval(self, name: str) -> bool:
        """True for tools that should require user approval (write + exec)."""
        return name in self._dangerous_tools

    # ── execution ──────────────────────────────────────────────────

    async def execute(self, name: str, args: dict) -> dict:
        """Run a tool in a thread-pool and return its result dict."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._execute_sync, name, args)

    # ── sync core ──────────────────────────────────────────────────

    def _execute_sync(self, name: str, args: dict) -> dict:
        try:
            if name == 'write_file':
                return self._tool_write_file(args)
            if name == 'read_file':
                return self._tool_read_file(args)
            if name == 'append_file':
                return self._tool_append_file(args)
            if name == 'write_file_chunk':
                return self._tool_write_file_chunk(args)
            if name == 'list_directory':
                return self._tool_list_directory(args)
            if name == 'execute_command':
                return self._tool_execute_command(args)
            if name == 'search_files':
                return self._tool_search_files(args)
            return {'success': False, 'error': f'Unknown tool: {name}'}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    # ── individual tools ───────────────────────────────────────────

    def _tool_write_file(self, args: dict) -> dict:
        full = self.resolve_path(args['path'])
        content = args['content']
        MAX_WRITE = 10 * 1024 * 1024  # 10 MB
        if len(content) > MAX_WRITE:
            return {
                'success': False,
                'error': (
                    f'Content too large ({len(content)} bytes). '
                    'Use append_file or write_file_chunk for large data.'
                )
            }
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)
        return {'success': True, 'message': f"File written: {args['path']} ({len(content)} chars)"}

    def _tool_read_file(self, args: dict) -> dict:
        full = self.resolve_path(args['path'])
        if not os.path.exists(full):
            return {'success': False, 'error': f"File not found: {args['path']}"}
        size = os.path.getsize(full)
        MAX_READ = 512 * 1024  # 512 KB
        if size > MAX_READ:
            return {
                'success': False,
                'error': (
                    f'File too large ({size} bytes). '
                    'Use execute_command with head/tail/grep or request chunked reading.'
                ),
                'size': size,
                'max_allowed': MAX_READ
            }
        with open(full, 'r', encoding='utf-8') as f:
            content = f.read()
        return {'success': True, 'content': content, 'size': len(content)}

    def _tool_append_file(self, args: dict) -> dict:
        full = self.resolve_path(args['path'])
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'a', encoding='utf-8') as f:
            f.write(args['content'])
        return {'success': True, 'message': f"Appended {len(args['content'])} chars to: {args['path']}"}

    def _tool_write_file_chunk(self, args: dict) -> dict:
        full = self.resolve_path(args['path'])
        os.makedirs(os.path.dirname(full), exist_ok=True)
        offset = args.get('offset', 0)
        content = args['content']
        if os.path.exists(full):
            current = os.path.getsize(full)
            if offset > current:
                with open(full, 'ab') as f:
                    f.write(b'\x00' * (offset - current))
        else:
            with open(full, 'wb') as f:
                f.write(b'\x00' * offset)
        with open(full, 'r+b') as f:
            f.seek(offset)
            f.write(content.encode('utf-8'))
        return {'success': True, 'message': f"Written {len(content)} chars at offset {offset} to: {args['path']}"}

    def _tool_list_directory(self, args: dict) -> dict:
        path = args.get('path', '.')
        full = self.resolve_path(path)
        if not os.path.exists(full):
            return {'success': False, 'error': f"Directory not found: {path}"}
        entries = []
        for entry in os.listdir(full):
            try:
                epath = os.path.join(full, entry)
                st = os.stat(epath)
                entries.append({
                    'name': entry,
                    'type': 'directory' if os.path.isdir(epath) else 'file',
                    'size': st.st_size if os.path.isfile(epath) else None
                })
            except OSError:
                entries.append({'name': entry, 'type': 'unknown'})
        return {'success': True, 'path': path, 'entries': entries}

    def _tool_execute_command(self, args: dict) -> dict:
        try:
            # Use errors='replace' to avoid UnicodeDecodeError when
            # command output contains non-UTF-8 bytes (e.g. cp1251 on
            # Russian Windows, or binary data in stdout).
            result = subprocess.run(
                args['command'],
                shell=True,
                cwd=self._work_dir,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace',
            )
            output = result.stdout or result.stderr
            if len(output) > 5000:
                output = output[:5000]
            return {
                'success': result.returncode == 0,
                'output': output,
                'exitCode': result.returncode,
                'error': result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out', 'exitCode': -1}
        except Exception as e:
            return {'success': False, 'error': str(e), 'exitCode': 1}

    def _tool_search_files(self, args: dict) -> dict:
        search_path = self.resolve_path(args.get('path', '.'))
        pattern = args['pattern']
        try:
            if IS_WIN:
                cmd = f'findstr /S /N /I /C:"{pattern}" "{search_path}\\*"'
            else:
                cmd = f'grep -rnI "{pattern}" "{search_path}" --include="*" | head -30'
            # Use errors='replace' to tolerate non-UTF-8 bytes in file
            # contents / paths returned by findstr / grep.
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
                encoding='utf-8',
                errors='replace',
            )
            if result.returncode == 1:
                return {'success': True, 'matches': '', 'message': 'No matches found'}
            if result.returncode != 0:
                return {'success': False, 'error': result.stderr}
            return {'success': True, 'matches': result.stdout[:5000]}
        except Exception as e:
            return {'success': False, 'error': str(e)}
