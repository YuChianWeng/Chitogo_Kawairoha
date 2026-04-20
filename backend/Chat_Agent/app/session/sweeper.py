from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

from app.session.store import InMemorySessionStore
from app.session.models import utc_now

_SWEEP_INTERVAL_SECONDS = 60.0


async def sweep_expired_sessions(
    store: InMemorySessionStore,
    ttl_minutes: int,
) -> list[str]:
    """Delete sessions idle longer than the configured TTL."""
    cutoff = utc_now() - timedelta(minutes=ttl_minutes)
    return await store.delete_expired(cutoff)


async def ttl_sweeper_loop(
    store: InMemorySessionStore,
    ttl_minutes: int,
    interval_seconds: float = _SWEEP_INTERVAL_SECONDS,
) -> None:
    """Continuously sweep expired sessions without surfacing cleanup failures."""
    try:
        while True:
            try:
                await sweep_expired_sessions(store, ttl_minutes)
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        raise


async def stop_ttl_sweeper(task: asyncio.Task[None] | None) -> None:
    """Cancel and await the sweeper task."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
