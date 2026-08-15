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

# Ensure the project root is on sys.path so that "dashboard.xxx" imports
# work regardless of whether this file is run as:
#   python dashboard/server.py   (script)
#   python -m dashboard.server   (module)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Ensure third-party packages are available
try:
    from aiohttp import web
except ImportError:
    print("Please install aiohttp: pip install aiohttp")
    sys.exit(1)

from dashboard.routes import register_all
from dashboard.chat_store import ChatStore
from dashboard.approval import ApprovalManager
from dashboard.tools import ToolRegistry
from dashboard.config import ensure_defaults
from dashboard.constants import PORT, HOST, LOG_DIR


async def create_app(work_dir: str) -> web.Application:
    app = web.Application()

    # ── infrastructure singletons (DI via app dict) ───────────────────
    chats_dir = os.path.join(work_dir, '.openAiDashboard', 'chats')
    app['chat_store'] = ChatStore(chats_dir)
    app['approval'] = ApprovalManager()
    app['tool_registry'] = ToolRegistry(work_dir)
    app['work_dir'] = work_dir

    # ── CORS middleware ────────────────────────────────────────────────
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

    # ── routes ─────────────────────────────────────────────────────────
    register_all(app)

    return app


if __name__ == '__main__':
    # Working directory follows the user's cwd at startup
    WORK_DIR = os.path.realpath(os.getcwd())

    # Create config with sensible defaults on first launch
    ensure_defaults()

    # Write a startup log entry to data/logs/server.log
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        from datetime import datetime
        log_path = os.path.join(LOG_DIR, 'server.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(
                f"[{datetime.now().isoformat()}] server started: "
                f"host={HOST} port={PORT} work_dir={WORK_DIR}\n"
            )
    except Exception:
        pass

    print(f'\n  Dashboard running at http://{HOST}:{PORT}')
    print(f'  Agent working directory: {WORK_DIR}')
    print('  Press Ctrl+C to stop.\n')
    web.run_app(create_app(WORK_DIR), host=HOST, port=PORT)
