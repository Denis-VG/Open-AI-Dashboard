"""
Model discovery & API-key verification routes.
"""

from aiohttp import web, ClientSession
from aiohttp.web import Request


# ── models ──────────────────────────────────────────────────────────

async def _models(req: Request) -> web.Response:
    type_filter = req.query.get('type', 'free')
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


async def _nvidia_models(_req: Request) -> web.Response:
    models = [
        'meta/llama-3.1-70b-instruct',
        'meta/llama-3.1-8b-instruct',
        'mistralai/mixtral-8x22b-instruct-v0.1',
        'mistralai/mixtral-8x7b-instruct-v0.1',
        'google/gemma-2-27b-it',
        'google/gemma-2-9b-it',
        'nvidia/nemotron-4-340b-instruct',
        'microsoft/phi-3-mini-128k-instruct',
    ]
    return web.json_response({'models': models})


async def _deepseek_models(req: Request) -> web.Response:
    data = await req.json()
    key = data.get('key')
    fallback = ['deepseek-v4-flash', 'deepseek-v4-pro']
    if not key:
        return web.json_response({'models': fallback})
    try:
        async with ClientSession() as session:
            async with session.get(
                'https://api.deepseek.com/models',
                headers={'Authorization': f'Bearer {key}'}
            ) as resp:
                if resp.status != 200:
                    return web.json_response({'models': fallback})
                data = await resp.json()
                models = [m['id'] for m in data.get('data', []) if m.get('id')]
                return web.json_response({'models': models if models else fallback})
    except Exception:
        return web.json_response({'models': fallback})


async def _openai_compatible_models(req: Request) -> web.Response:
    data = await req.json()
    base_url = data.get('baseUrl')
    key = data.get('key', 'not-needed')
    if not base_url:
        return web.json_response({'models': [], 'error': 'Missing baseUrl'}, status=400)
    base_url = base_url.rstrip('/')
    try:
        async with ClientSession() as session:
            async with session.get(
                f'{base_url}/models',
                headers={'Authorization': f'Bearer {key}'}
            ) as resp:
                if resp.status != 200:
                    return web.json_response({'models': [], 'error': f'Status {resp.status}'})
                data = await resp.json()
                models = [m['id'] for m in data.get('data', []) if m.get('id')]
                return web.json_response({'models': models})
    except Exception as e:
        return web.json_response({'models': [], 'error': str(e)})


# ── verify-key ──────────────────────────────────────────────────────

async def _verify_key(req: Request) -> web.Response:
    data = await req.json()
    provider = data.get('provider')
    key = data.get('key')
    base_url = data.get('baseUrl')
    valid = False

    try:
        if provider == 'openrouter':
            async with ClientSession() as session:
                async with session.get(
                    'https://openrouter.ai/api/v1/auth/key',
                    headers={'Authorization': f'Bearer {key}'}
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'nvidia':
            async with ClientSession() as session:
                async with session.get(
                    'https://integrate.api.nvidia.com/v1/models',
                    headers={'Authorization': f'Bearer {key}'}
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'deepseek':
            async with ClientSession() as session:
                async with session.get(
                    'https://api.deepseek.com/models',
                    headers={'Authorization': f'Bearer {key}'}
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'gemini':
            async with ClientSession() as session:
                async with session.get(
                    f'https://generativelanguage.googleapis.com/v1beta/models?key={key}'
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'anthropic':
            async with ClientSession() as session:
                async with session.get(
                    'https://api.anthropic.com/v1/models',
                    headers={'x-api-key': key, 'anthropic-version': '2023-06-01'}
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'openai':
            async with ClientSession() as session:
                async with session.get(
                    'https://api.openai.com/v1/models',
                    headers={'Authorization': f'Bearer {key}'}
                ) as resp:
                    valid = resp.status == 200
        elif provider == 'lmstudio':
            clean = base_url.rstrip('/') if base_url else 'http://localhost:1234/v1'
            try:
                async with ClientSession() as session:
                    async with session.get(
                        f'{clean}/models',
                        headers={'Authorization': 'Bearer lm-studio'}
                    ) as resp:
                        valid = resp.status == 200
            except Exception:
                valid = False
        elif provider == 'custom-openai':
            if base_url:
                clean = base_url.rstrip('/')
                try:
                    async with ClientSession() as session:
                        async with session.get(
                            f'{clean}/models',
                            headers={'Authorization': f'Bearer {key or "not-needed"}'}
                        ) as resp:
                            valid = resp.status == 200
                except Exception:
                    valid = False
        elif provider == 'ollama':
            try:
                async with ClientSession() as session:
                    async with session.get('http://127.0.0.1:11434/api/tags') as resp:
                        valid = resp.status == 200
            except Exception:
                valid = False
    except Exception:
        pass

    return web.json_response({'valid': valid})


# ── register ────────────────────────────────────────────────────────

def register(app: web.Application) -> None:
    app.router.add_get('/api/models', _models)
    app.router.add_get('/api/nvidia/models', _nvidia_models)
    app.router.add_post('/api/deepseek/models', _deepseek_models)
    app.router.add_post('/api/openai-compatible/models', _openai_compatible_models)
    app.router.add_post('/api/verify-key', _verify_key)
