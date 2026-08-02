"""
SSE (Server-Sent Events) writer — a tiny helper that wraps
an aiohttp StreamResponse so handlers only call `send(data)`.
"""

import json
import logging
from aiohttp.web import StreamResponse

logger = logging.getLogger(__name__)


class SSEWriter:
    """Wraps a StreamResponse for the SSE protocol."""

    def __init__(self, response: StreamResponse) -> None:
        self._resp = response
        self._closed = False

    async def send(self, data: dict) -> None:
        """Send one JSON-encoded SSE event."""
        if self._closed:
            return
        try:
            payload = f'data: {json.dumps(data)}\n\n'
            await self._resp.write(payload.encode('utf-8'))
            await self._resp.drain()
        except Exception:
            self._closed = True
            logger.debug("SSE write failed; closing silently.")

    async def close(self) -> None:
        """Gracefully end the stream."""
        if not self._closed:
            try:
                await self._resp.write_eof()
            except Exception:
                pass
            self._closed = True
