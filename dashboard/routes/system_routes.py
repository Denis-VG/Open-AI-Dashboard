"""
System info & session-logs routes.
"""

import os

from aiohttp import web
from aiohttp.web import Request

from ..constants import ROOT_DIR
from ..system_info import get_system_info, get_session_logs


async def _system(_req: Request) -> web.Response:
    return web.json_response(get_system_info())


async def _logs(_req: Request) -> web.Response:
    return web.json_response({'logs': get_session_logs()})


async def _logs_read(req: Request) -> web.Response:
    path = req.query.get('path', '')
    full = os.path.join(ROOT_DIR, path)
    if not os.path.exists(full):
        return web.json_response({'error': 'Not found'}, status=404)
    with open(full, 'r', encoding='utf-8') as f:
        content = f.read(10000)
    return web.json_response({'content': content})


async def _updates(_req: Request) -> web.Response:
    return web.json_response({
        'current': 'unknown',
        'latest': 'unknown',
        'updateAvailable': False,
    })


async def _updates_install(_req: Request) -> web.Response:
    return web.json_response({'error': 'Not implemented in Python'}, status=501)


async def _shutdown(_req: Request) -> web.Response:
    """Gracefully shut down the server."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.call_later(0.3, lambda: __import__('os')._exit(0))
    return web.json_response({'success': True})


def register(app: web.Application) -> None:
    app.router.add_get('/api/system', _system)
    app.router.add_get('/api/logs', _logs)
    app.router.add_get('/api/logs/read', _logs_read)
    app.router.add_get('/api/updates', _updates)
    app.router.add_post('/api/updates/install', _updates_install)
    app.router.add_post('/api/shutdown', _shutdown)
