"""
Ollama management routes — status, models, start, stop.
"""

import os
import subprocess

from aiohttp import web, ClientSession
from aiohttp.web import Request

from ..constants import DATA_DIR, IS_WIN


async def _status(_req: Request) -> web.Response:
    out = {'installed': False, 'running': False}
    out['installed'] = (
        os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama.exe'))
        or os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama'))
    )
    try:
        async with ClientSession() as session:
            async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                if resp.status == 200:
                    out['running'] = True
    except Exception:
        pass
    return web.json_response(out)


async def _models(_req: Request) -> web.Response:
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
                        'label': parts[2] if len(parts) > 2 else '',
                    })
    try:
        async with ClientSession() as session:
            async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for m in data.get('models', []):
                        if not any(x['id'] == m['name'] for x in models):
                            models.append({'id': m['name'], 'name': m['name'], 'label': 'API'})
    except Exception:
        pass
    return web.json_response({'models': models})


async def _start(_req: Request) -> web.Response:
    try:
        if IS_WIN:
            exe = os.path.join(DATA_DIR, 'ollama', 'ollama.exe')
            if os.path.exists(exe):
                env = os.environ.copy()
                env['OLLAMA_MODELS'] = os.path.join(DATA_DIR, 'ollama', 'data')
                subprocess.Popen(
                    [exe, 'serve'],
                    cwd=os.path.join(DATA_DIR, 'ollama'),
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return web.json_response({'success': True})
        else:
            bin_path = os.path.join(DATA_DIR, 'ollama', 'ollama')
            if os.path.exists(bin_path):
                env = os.environ.copy()
                env['OLLAMA_MODELS'] = os.path.join(DATA_DIR, 'ollama', 'data')
                subprocess.Popen(
                    [bin_path, 'serve'],
                    cwd=os.path.join(DATA_DIR, 'ollama'),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return web.json_response({'success': True})
        return web.json_response({'error': 'Ollama not installed'}, status=404)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def _stop(_req: Request) -> web.Response:
    try:
        if IS_WIN:
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], check=False, capture_output=True)
        else:
            subprocess.run(['pkill', '-f', 'ollama serve'], check=False)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


def register(app: web.Application) -> None:
    app.router.add_get('/api/ollama/status', _status)
    app.router.add_get('/api/ollama/models', _models)
    app.router.add_post('/api/ollama/start', _start)
    app.router.add_post('/api/ollama/stop', _stop)
