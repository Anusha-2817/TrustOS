"""
TrustOS — idempotency keys for the /v1 write routes that require them (Phase 5a).

Contract (``Idempotency-Key`` header, 1–255 printable ASCII characters, kept 24 h):
  * first request with a key  → runs normally; a 2xx response is stored with the work, in ONE transaction;
  * same key, same request    → the stored response is replayed (same status, same bytes) with
                                ``Idempotent-Replayed: true``, and nothing runs or is written again;
  * same key, different request → 422 (the key is bound to method + path + canonical body);
  * an error (4xx/5xx) is never stored, so a failed request can simply be retried under the same key.
Keys are scoped to the calling API key: two callers can use the same string without seeing each other's data.

How duplicates are kept out: ``begin`` takes a Postgres advisory lock on (scope, key) inside the request's
transaction, so a duplicate arriving while the first is still working waits, then finds the stored response.
The response is stored in the same transaction as the order / settlement it describes, so either both exist or
neither does (the fail-closed 503 path rolls the key back with the work, and a retry starts clean).
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
_KEY_RE = re.compile(r"^[\x21-\x7e]{1,255}$")  # printable ASCII, no spaces


def ttl_seconds() -> int:
    return int(os.environ.get("IDEMPOTENCY_TTL_SECONDS") or 24 * 3600)


@dataclass(frozen=True)
class Idempotency:
    scope: str  # the caller (api_keys.key_hash)
    key: str
    request_hash: str


def parse_key(raw: Optional[str]) -> str:
    """The header value, or a 400 explaining what is wrong with it."""
    if raw is None or not raw.strip():
        raise HTTPException(status_code=400, detail=f"{HEADER} header is required")
    if not _KEY_RE.match(raw):
        raise HTTPException(status_code=400, detail=f"{HEADER} must be 1-255 printable ASCII characters without spaces")
    return raw


def fingerprint(method: str, path: str, body: Optional[BaseModel]) -> str:
    """sha256 of method + path + the canonical (parsed, key-sorted) body, so formatting and key order don't
    matter but any change of meaning does. The path includes the order id, so a key can't be reused across orders."""
    canonical = json.dumps(body.model_dump(mode="json") if body is not None else None, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{method.upper()} {path}\n{canonical}".encode()).hexdigest()


def context(scope: str, raw_key: Optional[str], method: str, path: str, body: Optional[BaseModel]) -> Idempotency:
    return Idempotency(scope=scope, key=parse_key(raw_key), request_hash=fingerprint(method, path, body))


async def begin(conn, idem: Idempotency) -> Optional[Dict[str, Any]]:
    """Call first thing inside the request's transaction. Returns the stored ``{status, body}`` to replay, or
    None when this request should do its work (then finish with ``store``). Raises 422 on a key reused with a
    different request."""
    await db.lock_idempotency_key(conn, idem.scope, idem.key)
    row = await db.get_idempotency_key(conn, idem.scope, idem.key)
    if row is None:
        return None
    if row["request_hash"] != idem.request_hash:
        raise HTTPException(status_code=422, detail=f"{HEADER} was already used with a different request")
    return {"status": row["response_status"], "body": row["response_body"]}


async def store(conn, idem: Idempotency, *, status: int, body: Dict[str, Any], order_id=None) -> None:
    """Record the response of the work just done, in the same transaction. Also clears out expired keys."""
    await db.purge_expired_idempotency_keys(conn)
    await db.store_idempotency_key(
        conn,
        scope=idem.scope,
        key=idem.key,
        request_hash=idem.request_hash,
        response_status=status,
        response_body=body,
        order_id=order_id,
        ttl_seconds=ttl_seconds(),
    )


def response(status: int, body: Dict[str, Any], *, replayed: bool) -> JSONResponse:
    """The first response and every replay go through here, so they are byte-identical apart from the header."""
    return JSONResponse(status_code=status, content=body, headers={REPLAYED_HEADER: "true"} if replayed else None)
