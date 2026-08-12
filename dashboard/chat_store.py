"""
Chat history storage — CRUD for JSON files in data/chats/.
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

class ChatStore:
    """Manages chat history via JSON files on disk."""

    def __init__(self, chats_dir: str) -> None:
        self._dir = chats_dir
        os.makedirs(self._dir, exist_ok=True)

    # ------------------------------------------------------------------
    def list(self) -> list[dict]:
        """Return all chats sorted by updated (newest first)."""
        chats = []
        for f in os.listdir(self._dir):
            if not f.endswith('.json'):
                continue
            full = os.path.join(self._dir, f)
            try:
                with open(full, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                chats.append({
                    'id': f.replace('.json', ''),
                    'title': data.get('title', 'Untitled'),
                    'created': data.get('created'),
                    'updated': data.get('updated'),
                    'messageCount': len(data.get('messages', [])),
                    'chat_mode': data.get('chat_mode', 'simple')
                })
            except Exception:
                continue
        chats.sort(key=lambda x: x.get('updated', ''), reverse=True)
        return chats

    # ------------------------------------------------------------------
    def load(self, chat_id: str) -> Optional[dict]:
        """Load a single chat by id, or None if missing."""
        filepath = os.path.join(self._dir, f'{chat_id}.json')
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    # ------------------------------------------------------------------
    def save(self, chat_id: str, data: dict) -> None:
        """Persist a chat dict to disk."""
        filepath = os.path.join(self._dir, f'{chat_id}.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    def delete(self, chat_id: str) -> None:
        """Remove a chat file if it exists."""
        filepath = os.path.join(self._dir, f'{chat_id}.json')
        if os.path.exists(filepath):
            os.unlink(filepath)

    # ------------------------------------------------------------------
    @staticmethod
    def new_id() -> str:
        return f'chat_{int(time.time() * 1000)}'

    # ------------------------------------------------------------------
    @staticmethod
    def init_chat(chat_id: str, title: str = 'New Conversation', chat_mode: str = 'simple') -> dict:
        now = datetime.now().isoformat()
        return {
            'id': chat_id,
            'title': title,
            'chat_mode': chat_mode,
            'created': now,
            'updated': now,
            'messages': []
        }
