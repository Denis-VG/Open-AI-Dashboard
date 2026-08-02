"""
Approval manager — coordinates tool-call approvals between the
agent loop (producer) and the HTTP layer (consumer via SSE).
"""

import asyncio


class ApprovalManager:
    """Lightweight pub/sub for per-call-id approval futures."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}

    # ── internal ─────────────────────────────────────────────────

    def _create(self, call_id: str) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self._pending[call_id] = fut
        return fut

    # ── public ───────────────────────────────────────────────────

    def resolve(self, call_id: str, approved: bool) -> bool:
        """Called by the HTTP handler when the user approves/rejects."""
        fut = self._pending.pop(call_id, None)
        if fut and not fut.done():
            fut.set_result(approved)
            return True
        return False

    async def wait_for_approval(self, call_id: str, timeout: float = 120.0) -> bool:
        """Called by the agent loop; blocks until user responds or timeout."""
        fut = self._create(call_id)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(call_id, None)
            return False
