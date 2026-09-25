"""
TrustOS — rate limiting (Phase 5a): slowapi, in-memory by default.

Buckets (per client, moving window; every limit is overridable by env and read on each request):
  /v1/risk/evaluate                        RL_RISK_EVALUATE      60/minute   scope v1_risk_evaluate
  POST /v1/orders                          RL_ORDERS_CREATE      30/minute   scope v1_orders_create
  every other /v1 route (ONE shared pool)  RL_V1_OTHER         120/minute   scope v1_other
  POST /evaluate-product (legacy, LLM cost) RL_EVALUATE_PRODUCT  10/minute   scope evaluate_product, by IP
  API-key lookups that miss the cache      AUTH_LOOKUP_LIMIT     60/minute   by IP  (see services/auth.py)
"Client" = the validated API key on /v1 (``request.state.api_key_hash``, set by services/auth.py), else the
peer IP. Behind a reverse proxy run uvicorn with ``--proxy-headers --forwarded-allow-ips=<proxy>`` so the peer
IP is the real one; this module never reads X-Forwarded-For itself (it is client-controlled).

The in-memory storage is PER PROCESS: with N worker processes the effective limit is N times higher, and a
restart clears the counters. That is fine for one process. To share counters across workers, set
RATE_LIMIT_STORAGE_URI=redis://... (no code change; ``pip install redis``). RATE_LIMIT_ENABLED=false switches
everything off (the test suite does this).
"""

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

STORAGE_URI = os.environ.get("RATE_LIMIT_STORAGE_URI") or "memory://"


def _enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


def ip_key(request: Request) -> str:
    return f"ip:{get_remote_address(request)}"


def client_key(request: Request) -> str:
    """The authenticated API key if there is one, else the IP."""
    key_hash = getattr(request.state, "api_key_hash", None)
    return f"key:{key_hash}" if key_hash else ip_key(request)


limiter = Limiter(
    key_func=client_key,
    headers_enabled=True,  # X-RateLimit-Limit / -Remaining / -Reset (handlers take a ``response: Response``)
    storage_uri=STORAGE_URI,
    strategy="moving-window",
    key_style="endpoint",
    enabled=_enabled(),
)


def _limit(env: str, default: str):
    return lambda: os.environ.get(env) or default


risk_evaluate = _limit("RL_RISK_EVALUATE", "60/minute")
orders_create = _limit("RL_ORDERS_CREATE", "30/minute")
v1_other = _limit("RL_V1_OTHER", "120/minute")
evaluate_product = _limit("RL_EVALUATE_PRODUCT", "10/minute")

SCOPE_RISK_EVALUATE = "v1_risk_evaluate"
SCOPE_ORDERS_CREATE = "v1_orders_create"
SCOPE_V1_OTHER = "v1_other"
SCOPE_EVALUATE_PRODUCT = "evaluate_product"


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 in the API's usual {"detail": ...} shape, with Retry-After and the X-RateLimit-* headers."""
    response = JSONResponse({"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429)
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)


# ─── the pre-authentication lookup limit ─────────────────────────────────────────────────────────
# A request with an API key we have not verified recently costs a database lookup. Limiting those per IP keeps
# a flood of made-up keys from turning into a flood of queries. Keys already in the auth cache don't count.

_auth_storage = storage_from_string(STORAGE_URI)
_auth_limiter = MovingWindowRateLimiter(_auth_storage)


def auth_lookup_allowed(request: Request) -> bool:
    if not _enabled():
        return True
    return _auth_limiter.hit(parse(os.environ.get("AUTH_LOOKUP_LIMIT") or "60/minute"), "auth_lookup", get_remote_address(request))


def reset() -> None:
    """Forget every counter (tests)."""
    limiter.reset()
    _auth_storage.reset()
