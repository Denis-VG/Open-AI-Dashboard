"""
Chat CRUD routes.
"""

from datetime import datetime

from aiohttp import web
from aiohttp.web import Request

from ..chat_store import ChatStore


def _store(req: Request) -> ChatStore:
    return req.app['chat_store']


async def _list(req: Request) -> web.Response:
    return web.json_response({'chats': _store(req).list()})


async def _create(req: Request) -> web.Response:
    data = await req.json()
    title = data.get('title', 'New Conversation')
    chat_mode = data.get('chat_mode', 'simple')
    store = _store(req)
    chat_id = store.new_id()
    store.save(chat_id, store.init_chat(chat_id, title, chat_mode))
    return web.json_response({'id': chat_id})


async def _single(req: Request) -> web.Response:
    store = _store(req)
    chat_id = req.match_info['chat_id']

    if req.method == 'GET':
        chat = store.load(chat_id)
        if chat is None:
            return web.json_response({'error': 'Chat not found'}, status=404)
        return web.json_response(chat)

    if req.method == 'DELETE':
        store.delete(chat_id)
        return web.json_response({'success': True})

    if req.method == 'POST':
        data = await req.json()
        store.save(chat_id, data)
        return web.json_response({'success': True})

    return web.json_response({'error': 'Method not allowed'}, status=405)


async def _rename(req: Request) -> web.Response:
    store = _store(req)
    chat_id = req.match_info['chat_id']
    data = await req.json()
    title = (data.get('title') or '').strip()
    if not title:
        return web.json_response({'error': 'Title cannot be empty'}, status=400)
    chat = store.load(chat_id)
    if chat is None:
        return web.json_response({'error': 'Chat not found'}, status=404)
    chat['title'] = title
    store.save(chat_id, chat)
    return web.json_response({'success': True, 'title': title})


def register(app: web.Application) -> None:
    app.router.add_get('/api/chats', _list)
    app.router.add_post('/api/chats', _create)
    app.router.add_get('/api/chats/{chat_id}', _single)
    app.router.add_delete('/api/chats/{chat_id}', _single)
    app.router.add_post('/api/chats/{chat_id}', _single)
    app.router.add_post('/api/chats/{chat_id}/rename', _rename)
