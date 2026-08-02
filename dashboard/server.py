#!/usr/bin/env python3
"""
Portable AI Dashboard — entry point.

Thin entry point that wires together:
- Infrastructure singletons (ChatStore, ApprovalManager, ToolRegistry)
- CORS middleware
- All route modules

The heavy-lifting code lives in:
  ai/          AI provider abstraction
  tools/       Tool definitions & execution
  routes/      HTTP handlers (thin — they call into the services above)
  agent.py     Agent loop (pure logic, no HTTP)
  sse.py       SSE stream writer helper
"""

import sys
import os

# Ensure third-party packages are available
try:
    from aiohttp import web
except ImportError:
    print("Please install aiohttp: pip install aiohttp")
    sys.exit(1)

from .routes import register_all
from .chat_store import ChatStore
from .approval import ApprovalManager
from .tools import ToolRegistry
from .constants import PORT, ROOT_DIR, CHATS_DIR


async def create_app() -> web.Application:
    app = web.Application()

    # ── infrastructure singletons (DI via app dict) ──────────────────
    app['chat_store'] = ChatStore(CHATS_DIR)
    app['approval'] = ApprovalManager()
    app['tool_registry'] = ToolRegistry(ROOT_DIR)

    # ── CORS middleware ──────────────────────────────────────────────
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        if request.method == 'OPTIONS':
            return web.Response(
                status=204,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type',
                },
            )
        resp = await handler(request)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    app.middlewares.append(cors_middleware)

    # ── routes ──────────────────────────────────────────────────────
    register_all(app)

    return app


if __name__ == '__main__':
    print(f'\n  Dashboard running at http://localhost:{PORT}')
    print(f'  Agent working directory: {ROOT_DIR}')
    print('  Press Ctrl+C to stop.\n')
    web.run_app(create_app(), port=PORT)
