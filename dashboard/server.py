#!/usr/bin/env python3
"""
Portable AI Server - Python implementation
Replicates the functionality of the original Node.js server.mjs
"""

import os
import sys
import json
import asyncio
import subprocess
import shutil
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs
import traceback

# Third-party libraries
try:
    import aiohttp
    from aiohttp import web, ClientSession, ClientTimeout
    from aiohttp.web import Request, Response, StreamResponse
except ImportError:
    print("Please install aiohttp: pip install aiohttp")
    sys.exit(1)

# ========== Constants ==========

__file__ = os.path.abspath(__file__)
__dirname = os.path.dirname(__file__)
ROOT_DIR = os.path.join(__dirname, '..')  # Portable_AI_USB root
DATA_DIR = os.path.join(ROOT_DIR, 'data')
ENV_FILE = os.path.join(DATA_DIR, 'ai_settings.env')
CHATS_DIR = os.path.join(DATA_DIR, 'chats')
HTML_FILE = os.path.join(__dirname, 'index.html')
PORT = 3000

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
PLATFORM = 'win' if IS_WIN else 'darwin' if IS_MAC else 'linux'
ARCH = 'x64' if sys.maxsize > 2**32 else 'arm64'
BIN_DIR = os.path.join(ROOT_DIR, 'engine', f'node-{PLATFORM}-{ARCH}', 'bin')  # not used in Python

WORK_DIR = ROOT_DIR  # Default working directory

# ========== Config Helpers ==========

def read_config() -> Dict[str, str]:
    """Read ai_settings.env file into dict."""
    if not os.path.exists(ENV_FILE):
        return {}
    config = {}
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    return config


def write_config(config: Dict[str, str]) -> None:
    """Write config dict to ai_settings.env."""
    os.makedirs(DATA_DIR, exist_ok=True)
    lines = [
        '# ========================================================',
        '# Portable AI - Master Switchboard',
        '# ========================================================'
    ]
    for key, value in config.items():
        lines.append(f'{key}={value}')
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# ========== Chat History Helpers ==========

def ensure_chats_dir():
    os.makedirs(CHATS_DIR, exist_ok=True)


def list_chats() -> List[Dict]:
    ensure_chats_dir()
    chats = []
    for f in os.listdir(CHATS_DIR):
        if not f.endswith('.json'):
            continue
        full = os.path.join(CHATS_DIR, f)
        try:
            with open(full, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            chats.append({
                'id': f.replace('.json', ''),
                'title': data.get('title', 'Untitled'),
                'created': data.get('created'),
                'updated': data.get('updated'),
                'messageCount': len(data.get('messages', []))
            })
        except:
            continue
    chats.sort(key=lambda x: x.get('updated', ''), reverse=True)
    return chats


def load_chat(chat_id: str) -> Optional[Dict]:
    filepath = os.path.join(CHATS_DIR, f'{chat_id}.json')
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_chat(chat_id: str, data: Dict) -> None:
    ensure_chats_dir()
    filepath = os.path.join(CHATS_DIR, f'{chat_id}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_chat(chat_id: str) -> None:
    filepath = os.path.join(CHATS_DIR, f'{chat_id}.json')
    if os.path.exists(filepath):
        os.unlink(filepath)


def new_chat_id() -> str:
    return f'chat_{int(time.time() * 1000)}'


# ========== System Info ==========

def get_system_info() -> Dict:
    info = {
        'nodeVersion': sys.version,  # not node, but okay
        'platform': sys.platform,
        'arch': ARCH,
        'hasGit': shutil.which('git') is not None,
        'hasPython': shutil.which('python') is not None or shutil.which('python3') is not None,
        'portableGit': IS_WIN and os.path.exists(os.path.join(BIN_DIR, 'git', 'cmd', 'git.exe')),
        'portablePython': IS_WIN and os.path.exists(os.path.join(BIN_DIR, 'python', 'python.exe')),
        'engineVersion': None,  # not applicable
        'ollamaInstalled': os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama.exe')) or
                           os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama')),
        'diskFree': 0,
        'diskTotal': 0
    }
    try:
        if IS_WIN:
            # Not implemented for simplicity
            pass
        else:
            output = subprocess.check_output(['df', '-k', ROOT_DIR], encoding='utf-8')
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 4:
                    info['diskTotal'] = int(parts[1]) * 1024
                    info['diskFree'] = int(parts[3]) * 1024
    except:
        pass
    return info


def get_session_logs() -> List[Dict]:
    logs_dir = os.path.join(ROOT_DIR, '.app_data')  # trash dir excluded of git history
    logs = []
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True) #add creation dir of logs

    def walk_dir(directory, depth=0):
        if depth > 3:
            return
        try:
            for entry in os.listdir(directory):
                full = os.path.join(directory, entry)
                try:
                    if os.path.isdir(full):
                        walk_dir(full, depth + 1)
                    elif any(entry.endswith(ext) for ext in ['.json', '.log', '.md', '.txt']):
                        stat = os.stat(full)
                        logs.append({
                            'name': entry,
                            'path': full.replace(ROOT_DIR, ''),
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                except:
                    continue
        except:
            pass

    walk_dir(logs_dir)
    logs.sort(key=lambda x: x.get('modified', ''), reverse=True)
    return logs[:50]


# ========== Tool Definitions ==========

TOOL_DEFS = [
    {
        'name': 'write_file',
        'description': 'Create or overwrite a file with the given content. Creates parent directories automatically.',
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
        'description': 'Read the contents of a file.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to the working directory'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'list_directory',
        'description': 'List all files and subdirectories in a directory.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Directory path relative to working directory. Use "." for current directory.'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'execute_command',
        'description': 'Execute a shell command and return its output. Use this for running scripts, installing packages, compiling code, git operations, etc.',
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
        'description': 'Search for a text pattern in files within a directory. Returns matching lines with file names and line numbers.',
        'parameters': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Text pattern to search for'},
                'path': {'type': 'string', 'description': 'Directory to search in, relative to working directory. Use "." for current directory.'}
            },
            'required': ['pattern', 'path']
        }
    }
]

WRITE_TOOLS = {'write_file', 'execute_command'}


def tools_for_openai():
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


def tools_for_anthropic():
    return [
        {
            'name': t['name'],
            'description': t['description'],
            'input_schema': t['parameters']
        }
        for t in TOOL_DEFS
    ]


def tools_for_gemini():
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


# ========== Tool Execution ==========

def resolve_path(rel_path: str) -> str:
    global WORK_DIR
    # Нормализуем путь (преобразуем / в \ на Windows, убираем лишние разделители)
    if os.path.isabs(rel_path):
        return os.path.realpath(os.path.normpath(rel_path))
    return os.path.realpath(os.path.normpath(os.path.join(WORK_DIR, rel_path)))


def execute_tool_sync(name: str, args: Dict) -> Dict:
    """Synchronous execution of a tool (called in thread pool)."""
    try:
        if name == 'write_file':
            full_path = resolve_path(args['path'])
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(args['content'])
            return {'success': True, 'message': f"File written: {args['path']} ({len(args['content'])} chars)"}

        elif name == 'read_file':
            full_path = resolve_path(args['path'])
            if not os.path.exists(full_path):
                return {'success': False, 'error': f"File not found: {args['path']}"}
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {'success': True, 'content': content, 'size': len(content)}

        elif name == 'list_directory':
            path = args.get('path', '.')
            full_path = resolve_path(path)
            if not os.path.exists(full_path):
                return {'success': False, 'error': f"Directory not found: {path}"}
            entries = []
            for entry in os.listdir(full_path):
                try:
                    stat = os.stat(os.path.join(full_path, entry))
                    entries.append({
                        'name': entry,
                        'type': 'directory' if os.path.isdir(os.path.join(full_path, entry)) else 'file',
                        'size': stat.st_size if os.path.isfile(os.path.join(full_path, entry)) else None
                    })
                except:
                    entries.append({'name': entry, 'type': 'unknown'})
            return {'success': True, 'path': path, 'entries': entries}

        elif name == 'execute_command':
            try:
                result = subprocess.run(
                    args['command'],
                    shell=True,
                    cwd=WORK_DIR,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8'
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

        elif name == 'search_files':
            search_path = resolve_path(args.get('path', '.'))
            pattern = args['pattern']
            try:
                if IS_WIN:
                    cmd = f'findstr /S /N /I /C:"{pattern}" "{search_path}\\*"'
                else:
                    cmd = f'grep -rnI "{pattern}" "{search_path}" --include="*" | head -30'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
                if result.returncode == 1:
                    return {'success': True, 'matches': '', 'message': 'No matches found'}
                elif result.returncode != 0:
                    return {'success': False, 'error': result.stderr}
                return {'success': True, 'matches': result.stdout[:5000]}
            except Exception as e:
                return {'success': False, 'error': str(e)}

        else:
            return {'success': False, 'error': f"Unknown tool: {name}"}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def execute_tool_async(name: str, args: Dict) -> Dict:
    """Asynchronous wrapper for tool execution using thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, execute_tool_sync, name, args)


# ========== AI Calling Functions ==========

async def call_ai_openai(messages: List[Dict], cfg: Dict, include_tools: bool = True) -> Dict:
    model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
    base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    api_key = cfg.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError('OPENAI_API_KEY missing')

    payload = {
        'model': model,
        'messages': messages,
        'stream': False
    }
    if include_tools:
        payload['tools'] = tools_for_openai()

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    if cfg.get('OPENAI_BASE_URL', '').find('openrouter') != -1:
        headers['HTTP-Referer'] = 'http://localhost:3000'
        headers['X-Title'] = 'Portable AI Agent'

    async with ClientSession() as session:
        print("Sending payload with tools:", json.dumps(payload, indent=2))
        async with session.post(f'{base_url}/chat/completions', json=payload, headers=headers, timeout=60) as resp:
            data = await resp.json()
            if resp.status != 200:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                raise Exception(f'API Error: {error_msg} (status {resp.status})')
            choice = data.get('choices', [{}])[0].get('message', {})
            if not choice:
                raise Exception('No response from AI')
            tool_calls = []
            for tc in choice.get('tool_calls', []):
                try:
                    args = json.loads(tc['function']['arguments'])
                except:
                    args = {}
                tool_calls.append({
                    'id': tc['id'],
                    'name': tc['function']['name'],
                    'args': args
                })
            return {
                'content': choice.get('content', ''),
                'tool_calls': tool_calls,
                'raw_message': choice
            }


async def call_ai_anthropic(messages: List[Dict], cfg: Dict, include_tools: bool = True) -> Dict:
    model = cfg.get('AI_DISPLAY_MODEL', 'claude-3-5-sonnet-20241022')
    api_key = cfg.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY missing')

    # Extract system message
    system = ''
    filtered = []
    for m in messages:
        if m.get('role') == 'system':
            system = m.get('content', '')
        else:
            filtered.append(m)

    payload = {
        'model': model,
        'messages': filtered,
        'max_tokens': 4096
    }
    if system:
        payload['system'] = system
    if include_tools:
        payload['tools'] = tools_for_anthropic()

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01'
    }

    async with ClientSession() as session:
        async with session.post('https://api.anthropic.com/v1/messages', json=payload, headers=headers, timeout=60) as resp:
            data = await resp.json()
            if resp.status != 200:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                raise Exception(f'Anthropic API Error: {error_msg}')
            content = data.get('content', [])
            text_parts = [c.get('text', '') for c in content if c.get('type') == 'text']
            tool_parts = [c for c in content if c.get('type') == 'tool_use']
            tool_calls = [{
                'id': tc['id'],
                'name': tc['name'],
                'args': tc.get('input', {})
            } for tc in tool_parts]
            return {
                'content': '\n'.join(text_parts),
                'tool_calls': tool_calls,
                'stop_reason': data.get('stop_reason')
            }


async def call_ai_gemini(messages: List[Dict], cfg: Dict, include_tools: bool = True) -> Dict:
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
            contents.append({
                'role': gemini_role,
                'parts': [{'text': m['content']}]
            })
        elif m.get('parts'):
            contents.append({
                'role': gemini_role,
                'parts': m['parts']
            })

    payload = {'contents': contents}
    if include_tools:
        payload['tools'] = tools_for_gemini()
    if system_instruction:
        payload['system_instruction'] = {'parts': [{'text': system_instruction}]}

    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    async with ClientSession() as session:
        async with session.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=60) as resp:
            data = await resp.json()
            if resp.status != 200:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                raise Exception(f'Gemini API Error: {error_msg}')
            candidates = data.get('candidates', [])
            if not candidates:
                raise Exception('No response from Gemini')
            parts = candidates[0].get('content', {}).get('parts', [])
            text_parts = [p['text'] for p in parts if 'text' in p]
            func_parts = [p for p in parts if 'functionCall' in p]
            tool_calls = []
            for idx, p in enumerate(func_parts):
                tool_calls.append({
                    'id': f'gemini_call_{int(time.time()*1000)}_{idx}',
                    'name': p['functionCall']['name'],
                    'args': p['functionCall'].get('args', {})
                })
            return {
                'content': '\n'.join(text_parts),
                'tool_calls': tool_calls
            }


async def call_ai(messages: List[Dict], cfg: Dict, include_tools: bool = True) -> Dict:
    provider = cfg.get('AI_PROVIDER')
    if provider in ('openai', 'ollama'):
        return await call_ai_openai(messages, cfg, include_tools)
    elif provider == 'anthropic':
        return await call_ai_anthropic(messages, cfg, include_tools)
    elif provider == 'gemini':
        return await call_ai_gemini(messages, cfg, include_tools)
    else:
        raise ValueError(f'Unsupported provider: {provider}')


# ========== Message Manipulation Helpers ==========

def append_assistant_message(messages: List[Dict], ai_response: Dict, provider: str):
    if provider in ('openai', 'ollama'):
        if 'raw_message' in ai_response:
            messages.append(ai_response['raw_message'])
        else:
            msg = {'role': 'assistant', 'content': ai_response.get('content', '')}
            if ai_response.get('tool_calls'):
                msg['tool_calls'] = [
                    {
                        'id': tc['id'],
                        'type': 'function',
                        'function': {
                            'name': tc['name'],
                            'arguments': json.dumps(tc['args'])
                        }
                    }
                    for tc in ai_response['tool_calls']
                ]
            messages.append(msg)
    elif provider == 'anthropic':
        content = []
        if ai_response.get('content'):
            content.append({'type': 'text', 'text': ai_response['content']})
        for tc in ai_response['tool_calls']:
            content.append({
                'type': 'tool_use',
                'id': tc['id'],
                'name': tc['name'],
                'input': tc['args']
            })
        messages.append({'role': 'assistant', 'content': content})
    elif provider == 'gemini':
        parts = []
        if ai_response.get('content'):
            parts.append({'text': ai_response['content']})
        for tc in ai_response['tool_calls']:
            parts.append({
                'functionCall': {
                    'name': tc['name'],
                    'args': tc['args']
                }
            })
        messages.append({'role': 'model', 'parts': parts})


def append_tool_result(messages: List[Dict], tool_call: Dict, result: Any, provider: str):
    result_str = json.dumps(result) if not isinstance(result, str) else result
    if provider in ('openai', 'ollama'):
        messages.append({
            'role': 'tool',
            'tool_call_id': tool_call['id'],
            'content': result_str
        })
    elif provider == 'anthropic':
        messages.append({
            'role': 'user',
            'content': [
                {
                    'type': 'tool_result',
                    'tool_use_id': tool_call['id'],
                    'content': result_str
                }
            ]
        })
    elif provider == 'gemini':
        messages.append({
            'role': 'user',
            'parts': [
                {
                    'functionResponse': {
                        'name': tool_call['name'],
                        'response': {'result': result}
                    }
                }
            ]
        })


# ========== Approval System ==========

class ApprovalManager:
    def __init__(self):
        self._pending = {}  # call_id -> asyncio.Future

    def create_approval(self, call_id: str) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self._pending[call_id] = fut
        return fut

    def resolve_approval(self, call_id: str, approved: bool) -> bool:
        fut = self._pending.pop(call_id, None)
        if fut and not fut.done():
            fut.set_result(approved)
            return True
        return False

    async def wait_for_approval(self, call_id: str, timeout: float = 120.0) -> bool:
        fut = self.create_approval(call_id)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(call_id, None)
            return False


approval_manager = ApprovalManager()


# ========== Agent Loop ==========

async def run_agent(all_messages, cfg, mode, send_sse):
    if not isinstance(cfg, dict):
       raise TypeError(f'run_agent: cfg must be dict, got {type(cfg)}')
    provider = cfg.get('AI_PROVIDER')
    max_iterations = 15
    final_text = ''

    # Добавляем завершающий разделитель к WORK_DIR для ясности
    work_dir_display = os.path.join(WORK_DIR, '')
    system_prompts = {
        'normal': f'You are a powerful AI coding agent running in a web dashboard. You have access to tools to create files, read files, list directories, execute shell commands, and search files. The current working directory is: {work_dir_display}. Before executing write operations, briefly explain what you are about to do. Use tools to actually perform actions - do not just describe what to do.',
        'limitless': f'You are an autonomous AI coding agent running in Limitless mode. You have access to tools to create files, read files, list directories, execute shell commands, and search files. The current working directory is: {work_dir_display}. Execute tasks directly and completely without asking for confirmation. Use tools to actually perform actions. Be decisive and thorough.'
    }

    # Удаляем все старые системные сообщения из истории
    all_messages[:] = [msg for msg in all_messages if msg.get('role') != 'system']

    # Вставляем актуальное системное сообщение в начало
    sys_content = system_prompts.get(mode, system_prompts['normal'])
    all_messages.insert(0, {'role': 'system', 'content': sys_content})

    for iteration in range(max_iterations):
        await send_sse({'type': 'agent_thinking', 'iteration': iteration + 1})

        try:
            ai_response = await call_ai(all_messages, cfg, include_tools=True)
        except Exception as e:
            if iteration == 0:
                try:
                    await send_sse({'type': 'agent_reasoning', 'content': 'Tool calling not supported by this model, falling back to chat mode...', 'iteration': 1})
                    ai_response = await call_ai(all_messages, cfg, include_tools=False)
                except Exception as e2:
                    error_text = f'⚠️ Agent Error: {str(e2)}'
                    await send_sse({'type': 'agent_error', 'error': str(e2)})
                    return error_text
            else:
                error_text = f'⚠️ Agent Error: {str(e)}'
                await send_sse({'type': 'agent_error', 'error': str(e)})
                return error_text

        # ---- Парсинг JSON-инструментов из текста (с поддержкой тегов <tools>) ----
        if not ai_response.get('tool_calls') and ai_response.get('content'):
            content = ai_response['content'].strip()
            json_str = None

            # 1. Ищем JSON внутри <tools>...</tools>
            tools_match = re.search(r'<tools>\s*([\s\S]*?)\s*</tools>', content)
            if tools_match:
                json_str = tools_match.group(1).strip()
            else:
                # 2. Ищем Markdown-блок ```json ... ```
                md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if md_match:
                    json_str = md_match.group(1).strip()
                else:
                    # 3. Пробуем весь контент как JSON
                    json_str = content

            if json_str:
                try:
                    parsed = json.loads(json_str)
                    # Если это список, берем первый элемент
                    if isinstance(parsed, list):
                        if parsed:
                            parsed = parsed[0]
                        else:
                            parsed = None
                    if parsed and 'name' in parsed and 'arguments' in parsed:
                        tool_call = {
                            'id': f'manual_{int(time.time()*1000)}',
                            'name': parsed['name'],
                            'args': parsed['arguments']
                        }
                        ai_response['tool_calls'] = [tool_call]
                        ai_response['content'] = ''  # очищаем, чтобы не дублировать
                        await send_sse({'type': 'agent_reasoning', 'content': f'⏳ Executing tool: {parsed["name"]}', 'iteration': iteration + 1})
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

        if ai_response.get('content') and ai_response.get('tool_calls'):
            await send_sse({'type': 'agent_reasoning', 'content': ai_response['content'], 'iteration': iteration + 1})

        if ai_response.get('tool_calls'):
            append_assistant_message(all_messages, ai_response, provider)

            for tc in ai_response['tool_calls']:
                is_write = tc['name'] in WRITE_TOOLS
                await send_sse({
                    'type': 'tool_call',
                    'id': tc['id'],
                    'name': tc['name'],
                    'args': tc['args'],
                    'needs_approval': is_write and mode != 'limitless'
                })

                if is_write and mode != 'limitless':
                    await send_sse({
                        'type': 'approval_needed',
                        'id': tc['id'],
                        'name': tc['name'],
                        'args': tc['args']
                    })
                    approved = await approval_manager.wait_for_approval(tc['id'])
                    if not approved:
                        reject_result = {'success': False, 'error': 'User rejected this action'}
                        append_tool_result(all_messages, tc, reject_result, provider)
                        await send_sse({'type': 'tool_rejected', 'id': tc['id']})
                        continue

                result = await execute_tool_async(tc['name'], tc['args'])
                append_tool_result(all_messages, tc, result, provider)
                await send_sse({
                    'type': 'tool_result',
                    'id': tc['id'],
                    'name': tc['name'],
                    'result': result
                })
            continue

        final_text = ai_response.get('content', '')
        if final_text:
            await send_sse({'type': 'agent_text', 'content': final_text})
        break

    await send_sse({'type': 'done', 'fullText': final_text})
    return final_text


# ========== Simple Chat (Streaming) ==========

async def stream_chat_response(messages: List[Dict], cfg: Dict, send_sse: callable):
    provider = cfg.get('AI_PROVIDER')
    model = cfg.get('OPENAI_MODEL') or cfg.get('AI_DISPLAY_MODEL')
    base_url = cfg.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    api_key = cfg.get('OPENAI_API_KEY') or cfg.get('GEMINI_API_KEY') or cfg.get('ANTHROPIC_API_KEY')

    # OpenAI-compatible
    if provider in ('openai', 'ollama'):
        payload = {
            'model': model,
            'messages': messages,
            'stream': True
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        if cfg.get('OPENAI_BASE_URL', '').find('openrouter') != -1:
            headers['HTTP-Referer'] = 'http://localhost:3000'
            headers['X-Title'] = 'Portable AI Dashboard'

        full_text = ''
        async with ClientSession() as session:
            async with session.post(f'{base_url}/chat/completions', json=payload, headers=headers, timeout=60) as resp:
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
                            await send_sse({'type': 'delta', 'content': delta})
                    except:
                        pass
        await send_sse({'type': 'done', 'fullText': full_text})
        return full_text

    # Anthropic
    elif provider == 'anthropic':
        payload = {
            'model': model or 'claude-3-5-sonnet-20241022',
            'messages': messages,
            'max_tokens': 4096,
            'stream': True
        }
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        }
        full_text = ''
        async with ClientSession() as session:
            async with session.post('https://api.anthropic.com/v1/messages', json=payload, headers=headers, timeout=60) as resp:
                async for line in resp.content:
                    line = line.decode('utf-8').strip()
                    if not line.startswith('data: '):
                        continue
                    try:
                        parsed = json.loads(line[6:])
                        delta = parsed.get('delta', {}).get('text', '')
                        if delta:
                            full_text += delta
                            await send_sse({'type': 'delta', 'content': delta})
                    except:
                        pass
        await send_sse({'type': 'done', 'fullText': full_text})
        return full_text

    # Gemini
    elif provider == 'gemini':
        gem_model = model or 'gemini-2.0-pro-exp-02-05'
        gem_messages = []
        for m in messages:
            role = 'model' if m.get('role') == 'assistant' else 'user'
            gem_messages.append({'role': role, 'parts': [{'text': m.get('content', '')}]})
        payload = {'contents': gem_messages}
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:streamGenerateContent?key={api_key}'
        full_text = ''
        async with ClientSession() as session:
            async with session.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=60) as resp:
                async for chunk in resp.content:
                    chunk = chunk.decode('utf-8')
                    matches = re.findall(r'"text":\s*"((?:[^"\\]|\\.)*)"', chunk)
                    for m in matches:
                        text = json.loads('{' + m + '}').get('text', '')
                        if text:
                            full_text += text
                            await send_sse({'type': 'delta', 'content': text})
        await send_sse({'type': 'done', 'fullText': full_text})
        return full_text

    else:
        await send_sse({'type': 'error', 'content': 'Provider not configured or unsupported.'})
        return ''


# ========== HTTP Server Handlers (aiohttp) ==========

async def handle_index(request: Request):
    # Пытаемся найти index.html или index.htm
    possible_paths = [
        os.path.join(__dirname, 'index.html'),
        os.path.join(__dirname, 'index.htm')
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return web.Response(text=content, content_type='text/html')
            except Exception as e:
                print(f"Error reading {path}: {e}")
                continue
    # Если ни один файл не найден – отдаём сообщение
    return web.Response(
        text="<h1>404 Not Found</h1><p>index.html not found in server directory.</p>",
        status=404,
        content_type='text/html'
    )


async def handle_config_get(request: Request):
    return web.json_response(read_config())


async def handle_config_post(request: Request):
    data = await request.json()
    write_config(data)
    return web.json_response({'success': True})


async def handle_config_export(request: Request):
    if not os.path.exists(ENV_FILE):
        return web.json_response({'error': 'No config'}, status=404)
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    return web.Response(
        body=content,
        headers={
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': 'attachment; filename="ai_settings.env"'
        }
    )


async def handle_config_import(request: Request):
    data = await request.text()
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write(data)
    return web.json_response({'success': True})


async def handle_models(request: Request):
    type_filter = request.query.get('type', 'free')
    async with ClientSession() as session:
        async with session.get('https://openrouter.ai/api/v1/models') as resp:
            if resp.status != 200:
                return web.json_response({'models': []})
            data = await resp.json()
            all_models = [m['id'] for m in data.get('data', [])]
            if type_filter == 'free':
                models = [m for m in all_models if m.endswith(':free')]
            else:
                models = [m for m in all_models if not m.endswith(':free')]
            return web.json_response({'models': models[:30]})


async def handle_nvidia_models(request: Request):
    models = [
        'meta/llama-3.1-70b-instruct',
        'meta/llama-3.1-8b-instruct',
        'mistralai/mixtral-8x22b-instruct-v0.1',
        'mistralai/mixtral-8x7b-instruct-v0.1',
        'google/gemma-2-27b-it',
        'google/gemma-2-9b-it',
        'nvidia/nemotron-4-340b-instruct',
        'microsoft/phi-3-mini-128k-instruct'
    ]
    return web.json_response({'models': models})


async def handle_deepseek_models(request: Request):
    data = await request.json()
    key = data.get('key')
    fallback = ['deepseek-v4-flash', 'deepseek-v4-pro']
    if not key:
        return web.json_response({'models': fallback})
    try:
        async with ClientSession() as session:
            async with session.get('https://api.deepseek.com/models', headers={'Authorization': f'Bearer {key}'}) as resp:
                if resp.status != 200:
                    return web.json_response({'models': fallback})
                data = await resp.json()
                models = [m['id'] for m in data.get('data', []) if m.get('id')]
                return web.json_response({'models': models if models else fallback})
    except:
        return web.json_response({'models': fallback})


async def handle_openai_compatible_models(request: Request):
    data = await request.json()
    base_url = data.get('baseUrl')
    key = data.get('key', 'not-needed')
    if not base_url:
        return web.json_response({'models': [], 'error': 'Missing baseUrl'}, status=400)
    base_url = base_url.rstrip('/')
    try:
        async with ClientSession() as session:
            async with session.get(f'{base_url}/models', headers={'Authorization': f'Bearer {key}'}) as resp:
                if resp.status != 200:
                    return web.json_response({'models': [], 'error': f'Status {resp.status}'})
                data = await resp.json()
                models = [m['id'] for m in data.get('data', []) if m.get('id')]
                return web.json_response({'models': models})
    except Exception as e:
        return web.json_response({'models': [], 'error': str(e)})


async def handle_verify_key(request: Request):
    data = await request.json()
    provider = data.get('provider')
    key = data.get('key')
    base_url = data.get('baseUrl')
    valid = False

    try:
        if provider == 'openrouter':
            async with ClientSession() as session:
                async with session.get('https://openrouter.ai/api/v1/auth/key', headers={'Authorization': f'Bearer {key}'}) as resp:
                    valid = resp.status == 200
        elif provider == 'nvidia':
            async with ClientSession() as session:
                async with session.get('https://integrate.api.nvidia.com/v1/models', headers={'Authorization': f'Bearer {key}'}) as resp:
                    valid = resp.status == 200
        elif provider == 'deepseek':
            async with ClientSession() as session:
                async with session.get('https://api.deepseek.com/models', headers={'Authorization': f'Bearer {key}'}) as resp:
                    valid = resp.status == 200
        elif provider == 'gemini':
            async with ClientSession() as session:
                async with session.get(f'https://generativelanguage.googleapis.com/v1beta/models?key={key}') as resp:
                    valid = resp.status == 200
        elif provider == 'anthropic':
            async with ClientSession() as session:
                async with session.get('https://api.anthropic.com/v1/models', headers={'x-api-key': key, 'anthropic-version': '2023-06-01'}) as resp:
                    valid = resp.status == 200
        elif provider == 'openai':
            async with ClientSession() as session:
                async with session.get('https://api.openai.com/v1/models', headers={'Authorization': f'Bearer {key}'}) as resp:
                    valid = resp.status == 200
        elif provider == 'lmstudio':
            clean_base = base_url.rstrip('/') if base_url else 'http://localhost:1234/v1'
            try:
                async with ClientSession() as session:
                    async with session.get(f'{clean_base}/models', headers={'Authorization': 'Bearer lm-studio'}) as resp:
                        valid = resp.status == 200
            except:
                valid = False
        elif provider == 'custom-openai':
            if base_url:
                clean_base = base_url.rstrip('/')
                try:
                    async with ClientSession() as session:
                        async with session.get(f'{clean_base}/models', headers={'Authorization': f'Bearer {key or "not-needed"}'}) as resp:
                            valid = resp.status == 200
                except:
                    valid = False
        elif provider == 'ollama':
            try:
                async with ClientSession() as session:
                    async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                        valid = resp.status == 200
            except:
                valid = False
    except:
        pass

    return web.json_response({'valid': valid})


async def handle_ollama_status(request: Request):
    out = {'installed': False, 'running': False}
    out['installed'] = os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama.exe')) or os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama'))
    try:
        async with ClientSession() as session:
            async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                if resp.status == 200:
                    out['running'] = True
    except:
        pass
    return web.json_response(out)


async def handle_ollama_models(request: Request):
    models = []
    txt_path = os.path.join(DATA_DIR, 'models', 'installed-models.txt')
    if os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if parts:
                    models.append({
                        'id': parts[0],
                        'name': parts[1] if len(parts) > 1 else parts[0],
                        'label': parts[2] if len(parts) > 2 else ''
                    })
    try:
        async with ClientSession() as session:
            async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for m in data.get('models', []):
                        if not any(x['id'] == m['name'] for x in models):
                            models.append({'id': m['name'], 'name': m['name'], 'label': 'API'})
    except:
        pass
    return web.json_response({'models': models})


async def handle_ollama_start(request: Request):
    try:
        if IS_WIN:
            exe = os.path.join(DATA_DIR, 'ollama', 'ollama.exe')
            if os.path.exists(exe):
                env = os.environ.copy()
                env['OLLAMA_MODELS'] = os.path.join(DATA_DIR, 'ollama', 'data')
                subprocess.Popen([exe, 'serve'], cwd=os.path.join(DATA_DIR, 'ollama'), env=env, creationflags=subprocess.CREATE_NO_WINDOW)
                return web.json_response({'success': True})
        else:
            bin_path = os.path.join(DATA_DIR, 'ollama', 'ollama')
            if os.path.exists(bin_path):
                env = os.environ.copy()
                env['OLLAMA_MODELS'] = os.path.join(DATA_DIR, 'ollama', 'data')
                subprocess.Popen([bin_path, 'serve'], cwd=os.path.join(DATA_DIR, 'ollama'), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return web.json_response({'success': True})
        return web.json_response({'error': 'Ollama not installed'}, status=404)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_ollama_stop(request: Request):
    try:
        if IS_WIN:
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], check=False, capture_output=True)
        else:
            subprocess.run(['pkill', '-f', 'ollama serve'], check=False)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_system(request: Request):
    return web.json_response(get_system_info())


async def handle_logs(request: Request):
    logs = get_session_logs()
    return web.json_response({'logs': logs})


async def handle_logs_read(request: Request):
    path = request.query.get('path', '')
    full_path = os.path.join(ROOT_DIR, path)
    if not os.path.exists(full_path):
        return web.json_response({'error': 'Not found'}, status=404)
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read(10000)
    return web.json_response({'content': content})


async def handle_updates(request: Request):
    # Not implemented in Python
    return web.json_response({
        'current': 'unknown',
        'latest': 'unknown',
        'updateAvailable': False
    })


async def handle_updates_install(request: Request):
    return web.json_response({'error': 'Not implemented in Python'}, status=501)


async def handle_launch(request: Request):
    data = await request.json()
    mode = data.get('mode', 'normal')
    quick_flag = ' --quick' if mode == 'limitless' else ''
    try:
        if IS_WIN:
            bat_file = os.path.join(ROOT_DIR, 'Windows', 'Start_AI.bat')
            subprocess.Popen(['start', 'cmd', '/k', f'"{bat_file}"{quick_flag}'], cwd=os.path.join(ROOT_DIR, 'Windows'), shell=True)
        else:
            platform_dir = 'darwin' if IS_MAC else 'linux'
            script = os.path.join(ROOT_DIR, platform_dir, 'Start_AI.command' if IS_MAC else 'start_ai.sh')
            subprocess.Popen(['bash', f'{script}{quick_flag}'], cwd=os.path.join(ROOT_DIR, platform_dir))
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_workdir_get(request: Request):
    return web.json_response({'workDir': WORK_DIR})


async def handle_workdir_post(request: Request):
    global WORK_DIR
    data = await request.json()
    new_path = data.get('path')
    abs_path = os.path.realpath(new_path)
    if not os.path.exists(abs_path):
        return web.json_response({'error': 'Directory does not exist'}, status=400)
    WORK_DIR = abs_path
    return web.json_response({'success': True, 'workDir': WORK_DIR})


async def handle_agent_approve(request: Request):
    data = await request.json()
    call_id = data.get('callId')
    approved = data.get('approved', False)
    found = approval_manager.resolve_approval(call_id, approved)
    return web.json_response({'success': found})


async def handle_chats_list(request: Request):
    return web.json_response({'chats': list_chats()})


async def handle_chats_create(request: Request):
    data = await request.json()
    title = data.get('title', 'New Conversation')
    chat_id = new_chat_id()
    now = datetime.now().isoformat()
    save_chat(chat_id, {
        'id': chat_id,
        'title': title,
        'created': now,
        'updated': now,
        'messages': []
    })
    return web.json_response({'id': chat_id})


async def handle_chat_single(request: Request):
    chat_id = request.match_info.get('chat_id')
    if request.method == 'GET':
        chat = load_chat(chat_id)
        if not chat:
            return web.json_response({'error': 'Chat not found'}, status=404)
        return web.json_response(chat)
    elif request.method == 'DELETE':
        delete_chat(chat_id)
        return web.json_response({'success': True})
    elif request.method == 'POST':
        data = await request.json()
        save_chat(chat_id, data)
        return web.json_response({'success': True})
    else:
        return web.json_response({'error': 'Method not allowed'}, status=405)


async def handle_agent(request: Request):
    data = await request.json()
    chat_id = data.get('chatId')
    messages = data.get('messages', [])
    user_message = data.get('userMessage')
    mode = data.get('mode', 'normal')
    cfg = read_config()

    response = StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)

    async def send_sse(data):
        try:
            await response.write(f'data: {json.dumps(data)}\n\n'.encode('utf-8'))
            await response.drain()
        except Exception as e:
            print(f"SSE write error in agent: {e}")

    if not cfg.get('AI_PROVIDER'):
        await send_sse({'type': 'agent_error', 'error': 'No AI provider configured. Please complete setup first.'})
        await response.write_eof()
        return response

    history = messages.copy()
    all_messages = history + [{'role': 'user', 'content': user_message}]
    full_text = ''

    try:
        full_text = await run_agent(all_messages, cfg, mode, send_sse)
        # Save to chat history
        if chat_id and full_text:
            existing = load_chat(chat_id) or {
                'id': chat_id,
                'title': user_message[:50],
                'created': datetime.now().isoformat(),
                'messages': []
            }
            existing['messages'].append({'role': 'user', 'content': user_message})
            existing['messages'].append({'role': 'assistant', 'content': full_text})
            existing['updated'] = datetime.now().isoformat()
            if not existing.get('title') or existing['title'] == 'New Conversation':
                existing['title'] = user_message[:50]
            save_chat(chat_id, existing)
    except Exception as e:
        error_text = f' Agent Error: {str(e)}'
        await send_sse({'type': 'agent_error', 'error': str(e)})
        if chat_id:
            existing = load_chat(chat_id) or {
                'id': chat_id,
                'title': user_message[:50],
                'created': datetime.now().isoformat(),
                'messages': []
            }
            existing['messages'].append({'role': 'user', 'content': user_message})
            existing['messages'].append({'role': 'assistant', 'content': error_text})
            existing['updated'] = datetime.now().isoformat()
            if not existing.get('title') or existing['title'] == 'New Conversation':
                existing['title'] = user_message[:50]
            save_chat(chat_id, existing)

    await response.write_eof()
    return response


async def handle_chat(request: Request):
    data = await request.json()
    chat_id = data.get('chatId')
    messages = data.get('messages', [])
    user_message = data.get('userMessage')
    mode = data.get('mode', 'normal')
    cfg = read_config()

    response = StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)

    async def send_sse(event_data):
        try:
            await response.write(f'data: {json.dumps(event_data)}\n\n'.encode('utf-8'))
            await response.drain()
        except Exception as e:
            print(f"SSE write error in chat: {e}")

    if not cfg.get('AI_PROVIDER'):
        await send_sse({'type': 'error', 'content': 'No AI provider configured. Please complete setup first.'})
        await response.write_eof()
        return response

    # Используем завершающий слеш для ясности
    work_dir_display = os.path.join(WORK_DIR, '')
    system_prompts = {
        'normal': f'You are a helpful, precise AI assistant. The current working directory is: {work_dir_display}. Before executing any significant action, briefly explain what you are about to do.',
        'limitless': f'You are an autonomous AI assistant in Limitless mode. The current working directory is: {work_dir_display}. Execute tasks directly and completely without asking for confirmation. Be decisive and thorough. Do not ask clarifying questions — make reasonable assumptions and proceed immediately with full results.'
    }
    sys_content = system_prompts.get(mode, system_prompts['normal'])
    history = messages.copy()
    # Удаляем все старые системные сообщения из истории
    history = [msg for msg in history if msg.get('role') != 'system']
    # Формируем сообщения: новое системное + история + текущее сообщение пользователя
    all_messages = [{'role': 'system', 'content': sys_content}] + history + [{'role': 'user', 'content': user_message}]

    full_text = ''
    try:
        full_text = await stream_chat_response(all_messages, cfg, send_sse)
    except Exception as e:
        await send_sse({'type': 'error', 'content': str(e)})
    finally:
        # Отправляем финальное событие done, если его не отправила stream_chat_response
        if full_text:
            await send_sse({'type': 'done', 'fullText': full_text})
        await response.write_eof()

    # Сохраняем историю, если есть full_text
    if chat_id and full_text:
        existing = load_chat(chat_id) or {
            'id': chat_id,
            'title': user_message[:50],
            'created': datetime.now().isoformat(),
            'messages': []
        }
        existing['messages'].append({'role': 'user', 'content': user_message})
        existing['messages'].append({'role': 'assistant', 'content': full_text})
        existing['updated'] = datetime.now().isoformat()
        if not existing.get('title') or existing['title'] == 'New Conversation':
            existing['title'] = user_message[:50]
        save_chat(chat_id, existing)

    return response


# ========== Main App Setup ==========

async def create_app():
    app = web.Application()

    # CORS middleware
    @web.middleware
    async def cors_middleware(request: Request, handler):
        if request.method == 'OPTIONS':
            return web.Response(status=204, headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            })
        resp = await handler(request)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    app.middlewares.append(cors_middleware)

    # Routes
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/config', handle_config_get)
    app.router.add_post('/api/config', handle_config_post)
    app.router.add_get('/api/config/export', handle_config_export)
    app.router.add_post('/api/config/import', handle_config_import)
    app.router.add_get('/api/models', handle_models)
    app.router.add_get('/api/nvidia/models', handle_nvidia_models)
    app.router.add_post('/api/deepseek/models', handle_deepseek_models)
    app.router.add_post('/api/openai-compatible/models', handle_openai_compatible_models)
    app.router.add_post('/api/verify-key', handle_verify_key)
    app.router.add_get('/api/ollama/status', handle_ollama_status)
    app.router.add_get('/api/ollama/models', handle_ollama_models)
    app.router.add_post('/api/ollama/start', handle_ollama_start)
    app.router.add_post('/api/ollama/stop', handle_ollama_stop)
    app.router.add_get('/api/system', handle_system)
    app.router.add_get('/api/logs', handle_logs)
    app.router.add_get('/api/logs/read', handle_logs_read)
    app.router.add_get('/api/updates', handle_updates)
    app.router.add_post('/api/updates/install', handle_updates_install)
    app.router.add_post('/api/launch', handle_launch)
    app.router.add_get('/api/workdir', handle_workdir_get)
    app.router.add_post('/api/workdir', handle_workdir_post)
    app.router.add_post('/api/agent/approve', handle_agent_approve)
    app.router.add_get('/api/chats', handle_chats_list)
    app.router.add_post('/api/chats', handle_chats_create)
    app.router.add_get('/api/chats/{chat_id}', handle_chat_single)
    app.router.add_delete('/api/chats/{chat_id}', handle_chat_single)
    app.router.add_post('/api/chats/{chat_id}', handle_chat_single)
    app.router.add_post('/api/agent', handle_agent)
    app.router.add_post('/api/chat', handle_chat)

    return app


if __name__ == '__main__':
    print(f'\n  Dashboard running at http://localhost:{PORT}')
    print(f'  Agent working directory: {WORK_DIR}')
    print('  Press Ctrl+C to stop.\n')
    web.run_app(create_app(), port=PORT)