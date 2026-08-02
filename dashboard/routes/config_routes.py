"""
Configuration routes — read / write / export / import ai_settings.env.
"""

import os

from aiohttp import web
from aiohttp.web import Request

from ..config import read_config, write_config
from ..constants import ENV_FILE, HTML_FILE, __dirname


async def handle_index(_request: Request) -> web.Response:
    """Serve the dashboard SPA."""
    possible = [
        os.path.join(__dirname, 'index.html'),
        os.path.join(__dirname, 'index.htm'),
    ]
    for path in possible:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return web.Response(text=content, content_type='text/html')
            except Exception:
                continue
    return web.Response(
        text='<h1>404 Not Found</h1><p>index.html not found in server directory.</p>',
        status=404,
        content_type='text/html',
    )


async def _config_get(_req: Request) -> web.Response:
    return web.json_response(read_config())


async def _config_post(req: Request) -> web.Response:
    data = await req.json()
    write_config(data)
    return web.json_response({'success': True})


async def _config_export(_req: Request) -> web.Response:
    if not os.path.exists(ENV_FILE):
        return web.json_response({'error': 'No config'}, status=404)
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    return web.Response(
        body=content,
        headers={
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': 'attachment; filename="ai_settings.env"',
        },
    )


async def _config_import(req: Request) -> web.Response:
    data = await req.text()
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write(data)
    return web.json_response({'success': True})


def register(app: web.Application) -> None:
    app.router.add_get('/api/config', _config_get)
    app.router.add_post('/api/config', _config_post)
    app.router.add_get('/api/config/export', _config_export)
    app.router.add_post('/api/config/import', _config_import)
