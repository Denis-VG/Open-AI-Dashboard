"""
SSE (Server-Sent Events) writer — a tiny helper that wraps
an aiohttp StreamResponse so handlers only call `send(data)`.
"""

import asyncio
import json
import logging
from aiohttp.web import StreamResponse

logger = logging.getLogger(__name__)


class SSEWriter:
    """Wraps a StreamResponse for the SSE protocol.

    All writes are serialised through a lock so handler events and the
    keep-alive pings never interleave.
    """

    def __init__(self, response: StreamResponse) -> None:
        self._resp = response
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        return self._closed

    async def send(self, data: dict) -> None:
        """Send one JSON-encoded SSE event."""
        if self._closed:
            return
        async with self._lock:
            try:
                payload = f'data: {json.dumps(data)}\n\n'
                await self._resp.write(payload.encode('utf-8'))
                await self._resp.drain()
            except Exception:
                self._closed = True
                logger.debug("SSE write failed; closing silently.")

    async def ping(self) -> None:
        """Write an SSE comment to detect a disconnected client.

        Comment lines are ignored by browsers; a failed write marks the
        stream as closed so a supervisor can cancel the underlying work.
        """
        if self._closed:
            return
        async with self._lock:
            try:
                await self._resp.write(b': ping\n\n')
                await self._resp.drain()
            except Exception:
                self._closed = True

    async def close(self) -> None:
        """Gracefully end the stream."""
        if not self._closed:
            try:
                await self._resp.write_eof()
            except Exception:
                pass
            self._closed = True
