"""
Redis-backed storage for the field-rep app.

Replaces three modal.Dict instances from the hub:
- `hub_sessions`     -> `sess:{sid}`   JSON dict,  TTL 7 days
- `hub_oauth_states` -> `oauth:{state}` marker,    TTL 5 min
- `hub_cache`        -> `tbl:{tid}`    JSON rows,  TTL 2 min

Connection URL from env `REDIS_URL` (Coolify injects from its attached Redis
service). Falls back to `redis://localhost:6379` for local docker-compose dev.

Uses redis-py 5.x async client. GETDEL (Redis 6.2+) for atomic oauth-state
consumption.
"""
import json
import os
from typing import Awaitable, Callable, Optional

import redis.asyncio as redis

_SESSION_TTL = 7 * 24 * 3600
_OAUTH_TTL   = 300
_TABLE_TTL   = 120
_KIOSK_TTL   = 12 * 3600  # kiosk sessions auto-expire after 12 hours

_client: Optional[redis.Redis] = None


def _r() -> redis.Redis:
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _client = redis.from_url(url, decode_responses=True)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Sessions ─────────────────────────────────────────────────────────────────
async def get_session(sid: str) -> Optional[dict]:
    if not sid:
        return None
    raw = await _r().get(f"sess:{sid}")
    return json.loads(raw) if raw else None


async def put_session(sid: str, data: dict) -> None:
    await _r().set(f"sess:{sid}", json.dumps(data), ex=_SESSION_TTL)


async def del_session(sid: str) -> None:
    await _r().delete(f"sess:{sid}")


# ── OAuth state (5-min nonce) ────────────────────────────────────────────────
async def put_oauth_state(state: str) -> None:
    await _r().set(f"oauth:{state}", "1", ex=_OAUTH_TTL)


async def check_and_del_oauth_state(state: str) -> bool:
    """Atomic: returns True if state existed (and deletes it). Blocks replay."""
    existed = await _r().getdel(f"oauth:{state}")
    return existed is not None


# ── Table cache (2-min hot cache, writable by warm loop) ─────────────────────
async def cached_table(
    tid: int,
    fetcher: Callable[[], Awaitable[list]],
) -> list:
    """
    GET + fallback-fetch + SET. `fetcher` is called only on cache miss and
    should return a list of Baserow row dicts.
    """
    key = f"tbl:{tid}"
    raw = await _r().get(key)
    if raw:
        return json.loads(raw)
    rows = await fetcher()
    await _r().set(key, json.dumps(rows), ex=_TABLE_TTL)
    return rows


async def set_cached_table(tid: int, rows: list) -> None:
    """Write-through entry point for `warm.py` to populate the cache."""
    await _r().set(f"tbl:{tid}", json.dumps(rows), ex=_TABLE_TTL)


async def invalidate_table(tid: int) -> None:
    """Drop a single cached table — called by write endpoints after they mutate."""
    await _r().delete(f"tbl:{tid}")


# ── Kiosk sessions (12h TTL) ─────────────────────────────────────────────────
# Created by an authenticated rep at /kiosk/setup; the token is then handed out
# in the public /kiosk/run/{kiosk_id} URL. Session payload includes a 4-digit
# PIN required to exit kiosk mode and the list of consent form slugs the rep
# selected.
async def put_kiosk_session(kiosk_id: str, data: dict) -> None:
    await _r().set(f"kiosk:{kiosk_id}", json.dumps(data), ex=_KIOSK_TTL)


async def get_kiosk_session(kiosk_id: str) -> Optional[dict]:
    if not kiosk_id:
        return None
    raw = await _r().get(f"kiosk:{kiosk_id}")
    return json.loads(raw) if raw else None


async def del_kiosk_session(kiosk_id: str) -> None:
    await _r().delete(f"kiosk:{kiosk_id}")
