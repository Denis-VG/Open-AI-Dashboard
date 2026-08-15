"""
Route registration — collects all route modules and registers them on the app.
"""

import os as _os

from aiohttp import web

from ..constants import SERVER_DIR as _SD


async def handle_favicon(_request: web.Request) -> web.Response:
    """Serve /favicon.ico from the dashboard package directory."""
    icon_path = _os.path.join(_SD, 'favicon.ico')
    if not _os.path.isfile(icon_path):
        return web.Response(status=404)
    with open(icon_path, 'rb') as f:
        body = f.read()
    return web.Response(
        body=body,
        content_type='image/x-icon',
        headers={'Cache-Control': 'public, max-age=86400'},
    )


def register_all(app: web.Application) -> None:
    """Register every route group on the application."""

    from . import (
        config_routes,
        chat_routes,
        system_routes,
        ollama_routes,
        model_routes,
        agent_routes,
    )

    # Static files (CSS, JS, assets)
    _static_dir = _os.path.join(_SD, 'static')
    if _os.path.isdir(_static_dir):
        app.router.add_static('/static/', _static_dir, name='static')

    # Static file / index
    app.router.add_get('/', config_routes.handle_index)

    # Favicon
    app.router.add_get('/favicon.ico', handle_favicon, name='favicon')

    # Config
    config_routes.register(app)

    # Chats CRUD
    chat_routes.register(app)

    # System info & logs
    system_routes.register(app)

    # Ollama management
    ollama_routes.register(app)

    # Model discovery
    model_routes.register(app)

    # Agent & Chat endpoints
    agent_routes.register(app)
