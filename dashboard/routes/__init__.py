"""
Route registration — collects all route modules and registers them on the app.
"""

from aiohttp import web


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

    import os as _os
    from ..constants import SERVER_DIR as _SD

    # Static files (CSS, JS, assets)
    _static_dir = _os.path.join(_SD, 'static')
    if _os.path.isdir(_static_dir):
        app.router.add_static('/static/', _static_dir, name='static')

    # Static file / index
    app.router.add_get('/', config_routes.handle_index)

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
