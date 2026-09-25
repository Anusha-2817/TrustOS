"""
TrustOS — static API-key authentication for /v1 (Phase 5a).

A caller sends ``X-API-Key: <key>``. Keys are random 256-bit values shown once at creation
(``scripts/manage_api_keys.py``); only their sha256 is stored (``api_keys``). A valid, unrevoked key just means
"authenticated caller": there are no scopes or roles, and every valid key can see and act on every order
(no tenancy yet). The key's hash is the caller's identity for rate limiting and idempotency scoping.

Behaviour to know about:
  * Missing / unknown / revoked key → 401 (one message for unknown and revoked: no oracle).
  * Verified keys are cached in-process for API_KEY_CACHE_TTL seconds (default 30; 0 disables), so a revoked key
    stays usable for up to that long, and a database blip does not take /v1/risk/evaluate (which fails open on
    its own log write) down for callers already known. A cache miss with the database down is a 503: auth fails
    CLOSED. Because the keys live in the database, /v1 needs DATABASE_URL: without it every keyed request is a 503.
  * Cache misses are rate-limited per IP (services/rate_limit.py) before they touch the database.
"""

import asyncio
import hashlib
import os
import secrets
import time
from typing import Dict, Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.exc import SQLAlchemyError

import db
from services import rate_limit

HEADER = "X-API-Key"
KEY_PREFIX = "tos_"
MAX_KEY_LENGTH = 256

api_key_header = APIKeyHeader(
    name=HEADER,
    auto_error=False,  # we answer 401 ourselves (FastAPI's default would be 403)
    description="API key issued with scripts/manage_api_keys.py",
)

_cache: Dict[str, float] = {}  # key_hash -> time.monotonic() until which it is trusted


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def clear_cache() -> None:
    _cache.clear()


def _cache_ttl() -> float:
    return float(os.environ.get("API_KEY_CACHE_TTL") or 30)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "ApiKey"})


async def require_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)) -> str:
    """Dependency for the /v1 router: returns the caller's key hash and stores it on ``request.state``."""
    if not api_key:
        raise _unauthorized(f"Missing {HEADER} header")
    if len(api_key) > MAX_KEY_LENGTH:
        raise _unauthorized("Invalid or revoked API key")
    key_hash = hash_api_key(api_key)

    if _cache.get(key_hash, 0.0) > time.monotonic():
        request.state.api_key_hash = key_hash
        return key_hash

    if not db.is_configured():
        raise HTTPException(status_code=503, detail="Persistence is not configured (DATABASE_URL is not set); API keys cannot be checked")
    if not rate_limit.auth_lookup_allowed(request):
        raise HTTPException(status_code=429, detail="Too many unrecognised API keys from this address; slow down", headers={"Retry-After": "60"})
    if db.circuit_is_open():
        raise HTTPException(status_code=503, detail="Authentication is unavailable (database unreachable)")
    try:
        async with db.transaction() as conn:
            row = await db.get_api_key(conn, key_hash)
    except (SQLAlchemyError, OSError, asyncio.TimeoutError) as exc:
        if db.is_connectivity_error(exc):
            db.trip_circuit()
        raise HTTPException(status_code=503, detail="Authentication is unavailable (database error)")
    if row is None or row["revoked_at"] is not None:
        _cache.pop(key_hash, None)
        raise _unauthorized("Invalid or revoked API key")

    ttl = _cache_ttl()
    if ttl > 0:
        _cache[key_hash] = time.monotonic() + ttl
    request.state.api_key_hash = key_hash
    return key_hash
