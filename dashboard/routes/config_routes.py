"""
Configuration routes — read / write / export / import ai_settings.env,
plus named profile management.
"""

import os

from aiohttp import web
from aiohttp.web import Request

from ..config import (
    read_config, write_config,
    list_profiles, save_profile, load_profile, delete_profile,
)
from ..constants import ENV_FILE, HTML_FILE, SERVER_DIR


async def handle_index(_request: Request) -> web.Response:
    """Serve the dashboard SPA."""
    possible = [
        os.path.join(SERVER_DIR, 'index.html'),
        os.path.join(SERVER_DIR, 'index.htm'),
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


# ── Profile endpoints ─────────────────────────────────────────────────

async def _profiles_list(_req: Request) -> web.Response:
    """GET /api/profiles — list all saved profiles."""
    return web.json_response({'profiles': list_profiles()})


async def _profiles_save(req: Request) -> web.Response:
    """POST /api/profiles/save — save current (or provided) config as profile."""
    data = await req.json()
    name = (data.get('name') or '').strip()
    config = data.get('config') or read_config()
    if not name:
        return web.json_response({'success': False, 'error': 'Name is required'}, status=400)
    save_profile(name, config)
    return web.json_response({'success': True})


async def _profiles_load(req: Request) -> web.Response:
    """POST /api/profiles/load — load a saved profile (apply to current config)."""
    data = await req.json()
    name = (data.get('name') or '').strip()
    if not name:
        return web.json_response({'success': False, 'error': 'Name is required'}, status=400)
    config = load_profile(name)
    if config is None:
        return web.json_response({'success': False, 'error': 'Profile not found'}, status=404)
    # Apply it immediately
    write_config(config)
    return web.json_response({'success': True, 'config': config})


async def _profiles_delete(req: Request) -> web.Response:
    """POST /api/profiles/delete — delete a saved profile."""
    data = await req.json()
    name = (data.get('name') or '').strip()
    if not name:
        return web.json_response({'success': False, 'error': 'Name is required'}, status=400)
    ok = delete_profile(name)
    if not ok:
        return web.json_response({'success': False, 'error': 'Profile not found'}, status=404)
    return web.json_response({'success': True})


async def _profiles_view(req: Request) -> web.Response:
    """POST /api/profiles/view — peek at a saved profile config without applying."""
    data = await req.json()
    name = (data.get('name') or '').strip()
    config = load_profile(name)
    if config is None:
        return web.json_response({'success': False, 'error': 'Profile not found'}, status=404)
    return web.json_response({'success': True, 'config': config})


# ── System prompt endpoint ─────────────────────────────────────────────

async def _system_prompt_get(_req: Request) -> web.Response:
    cfg = read_config()
    return web.json_response({'prompt': cfg.get('SYSTEM_PROMPT', '')})


async def _system_prompt_post(req: Request) -> web.Response:
    data = await req.json()
    cfg = read_config()
    cfg['SYSTEM_PROMPT'] = data.get('prompt', '')
    write_config(cfg)
    return web.json_response({'success': True})


# ── Project-level token usage ──────────────────────────────────────────

async def _project_usage_get(req: Request) -> web.Response:
    work_dir = req.app['work_dir']
    path = os.path.join(work_dir, '.ai', 'total_usage.json')
    if not os.path.exists(path):
        return web.json_response({'total_tokens': 0})
    try:
        import json
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception:
        return web.json_response({'total_tokens': 0})


async def _project_usage_post(req: Request) -> web.Response:
    import json as _json
    work_dir = req.app['work_dir']
    usage = await req.json()
    path = os.path.join(work_dir, '.ai', 'total_usage.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)

    existing = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                existing = _json.load(f)
        except Exception:
            pass

    for key, val in usage.items():
        if isinstance(val, (int, float)):
            existing[key] = existing.get(key, 0) + val

    with open(path, 'w', encoding='utf-8') as f:
        _json.dump(existing, f)

    return web.json_response({'success': True})


def register(app: web.Application) -> None:
    app.router.add_get('/api/config', _config_get)
    app.router.add_post('/api/config', _config_post)
    app.router.add_get('/api/config/export', _config_export)
    app.router.add_post('/api/config/import', _config_import)

    # System prompt
    app.router.add_get('/api/system-prompt', _system_prompt_get)
    app.router.add_post('/api/system-prompt', _system_prompt_post)

    # Project token usage
    app.router.add_get('/api/project-usage', _project_usage_get)
    app.router.add_post('/api/project-usage', _project_usage_post)

    # Profiles
    app.router.add_get('/api/profiles', _profiles_list)
    app.router.add_post('/api/profiles/save', _profiles_save)
    app.router.add_post('/api/profiles/load', _profiles_load)
    app.router.add_post('/api/profiles/delete', _profiles_delete)
    app.router.add_post('/api/profiles/view', _profiles_view)
