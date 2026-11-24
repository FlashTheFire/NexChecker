"""NexChecker — API Deferred Cancellation Engine.
================================================
Handles background order cancellations for discarded virtual numbers.
Since NexNum enforces a ~60-120s cooldown before allowing cancellation
(returning EARLY_CANCEL_DENIED), non-matching numbers are placed into this
queue and retried in the background until successfully refunded or terminal.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Bootstrap path resolution
_ROOT = Path(__file__).resolve().parent.parent
_NEXBOT_ROOT = _ROOT / "NexBot"
for _p in (str(_ROOT), str(_NEXBOT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from NexBot.core.nexnum_api import NexNumStatus, nexnum_client
    from NexBot.utils.config import CANCEL_MIN_AGE, CANCEL_POLL_SECS
except ImportError:
    from core.nexnum_api import NexNumStatus, nexnum_client
    from utils.config import CANCEL_MIN_AGE, CANCEL_POLL_SECS

logger = logging.getLogger("NexChecker.CancelQueue")


@dataclass
class PendingCancelItem:
    """An order waiting for cooldown before NexNum allows cancellation."""
    api_key: str
    order_id: str
    queued_at: float = field(default_factory=time.monotonic)
    retries: int = 0
    max_retry: int = 4  # max worker cycles (~2 minutes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "queued_at": self.queued_at,
            "retries": self.retries,
            "status": "QUEUED_DEFERRED",
        }


class CancelQueueManager:
    """Async background worker for queued order cancellations."""

    def __init__(self) -> None:
        self._queue: List[PendingCancelItem] = []
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running = False

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    async def enqueue(self, api_key: str, order_id: str) -> None:
        """Enqueue an order for deferred cancellation."""
        async with self._lock:
            if any(item.order_id == order_id for item in self._queue):
                return
            item = PendingCancelItem(api_key=api_key, order_id=order_id)
            self._queue.append(item)
            logger.info("[CancelQueue] Queued order %s for background refund (queue size: %d)", order_id, len(self._queue))

    async def try_immediate_or_enqueue(self, api_key: str, order_id: str) -> bool:
        """Attempt immediate cancellation; enqueue if denied or on temporary error."""
        try:
            res = await nexnum_client.set_status(api_key, order_id, 8)
        except Exception as exc:
            logger.warning("[CancelQueue] Exception attempting immediate cancel for %s: %s — enqueuing", order_id, exc)
            await self.enqueue(api_key, order_id)
            return False

        if res.get("ok"):
            logger.info("[CancelQueue] Immediate cancel success for order: %s", order_id)
            return True

        code = res.get("code", "")
        if code in NexNumStatus.CANCEL_TERMINAL:
            logger.info("[CancelQueue] Order %s in terminal state '%s', cancellation dropped", order_id, code)
            return False

        if res.get("early_denied"):
            logger.info("[CancelQueue] EARLY_CANCEL_DENIED for %s — queued for deferred cancellation", order_id)
        else:
            logger.info("[CancelQueue] Cancel failed (%s) for %s — queued for retry", code, order_id)

        await self.enqueue(api_key, order_id)
        return False

    async def _worker_loop(self) -> None:
        """Background loop executing cancellations after CANCEL_MIN_AGE cooldown."""
        logger.info("[CancelQueue] Background worker started (poll interval: %ds, min age: %ds)", CANCEL_POLL_SECS, int(CANCEL_MIN_AGE))
        try:
            while self._is_running:
                await asyncio.sleep(CANCEL_POLL_SECS)

                async with self._lock:
                    if not self._queue:
                        continue

                    now = time.monotonic()
                    ready = [item for item in self._queue if (now - item.queued_at) >= CANCEL_MIN_AGE]
                    if not ready:
                        continue

                    logger.info("[CancelQueue] Processing %d matured order(s) for cancellation", len(ready))

                # Fire parallel requests outside the lock to prevent blocking enqueues
                results = await asyncio.gather(
                    *(nexnum_client.set_status(item.api_key, item.order_id, 8) for item in ready),
                    return_exceptions=True,
                )

                async with self._lock:
                    for item, res in zip(ready, results):
                        if item not in self._queue:
                            continue

                        if isinstance(res, Exception):
                            item.retries += 1
                            if item.retries >= item.max_retry:
                                logger.warning("[CancelQueue] Dropping %s after %d failed attempts (exception: %s)", item.order_id, item.retries, res)
                                self._queue.remove(item)
                            else:
                                item.queued_at = time.monotonic()
                            continue

                        code = res.get("code", "") if isinstance(res, dict) else ""
                        status = res.get("status", "") if isinstance(res, dict) else ""

                        if isinstance(res, dict) and res.get("ok"):
                            logger.info("[CancelQueue] Successfully refunded order %s", item.order_id)
                            self._queue.remove(item)
                        elif code in NexNumStatus.CANCEL_TERMINAL:
                            logger.info("[CancelQueue] Order %s terminal state (%s), removing from queue", item.order_id, code)
                            self._queue.remove(item)
                        elif isinstance(res, dict) and res.get("early_denied"):
                            item.queued_at = time.monotonic()
                            logger.debug("[CancelQueue] EARLY_CANCEL_DENIED for %s, waiting next cycle", item.order_id)
                        else:
                            item.retries += 1
                            if item.retries >= item.max_retry:
                                logger.warning("[CancelQueue] Giving up on %s after %d retries (status=%s, code=%s)", item.order_id, item.retries, status, code)
                                self._queue.remove(item)
                            else:
                                item.queued_at = time.monotonic()

        except asyncio.CancelledError:
            logger.info("[CancelQueue] Worker loop cancelled gracefully")
        except Exception as exc:
            logger.error("[CancelQueue] Worker loop encountered unexpected error: %s", exc)

    def start(self) -> None:
        """Start background worker task."""
        if not self._is_running:
            self._is_running = True
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop background worker task gracefully."""
        self._is_running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
        self._worker_task = None


# Global singleton instance
cancel_queue = CancelQueueManager()
