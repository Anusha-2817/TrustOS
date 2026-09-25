"""Phase 5a: the CORS fix, the legacy 'deprecated for external use' note, and the /v1 OpenAPI surface."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
LEGACY = ["/trust/buyer", "/trust/seller", "/evaluate-product", "/risk/score", "/simulator/evaluate", "/decision/evaluate",
          "/orders", "/simulate/{scenario}", "/evaluate-risk", "/demo/payment-lifecycle", "/initiate-payment", "/verify", "/settle"]
ORDER_MODE = {"/orders", "/initiate-payment", "/verify", "/settle"}
KEYED_WITH_ORDER_ID = {"/initiate-payment", "/verify", "/settle"}
NOTE = "Deprecated for external use"


def preflight(client, origin, headers="content-type"):
    return client.options(
        "/decision/evaluate",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": headers},
    )


def test_the_frontend_dev_origin_is_allowed_without_credentials(client):
    r = preflight(client, "http://localhost:5173", "content-type,x-api-key,idempotency-key")
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in r.headers  # the old wildcard + credentials combination is gone


def test_other_origins_get_no_cors_headers(client):
    r = preflight(client, "https://evil.example")
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    simple = client.get("/health", headers={"Origin": "https://evil.example"})
    assert simple.status_code == 200 and "access-control-allow-origin" not in simple.headers


def test_unlisted_request_headers_are_refused(client):
    assert preflight(client, "http://localhost:5173", "authorization").status_code == 400


def test_cors_headers_needed_by_browser_callers_are_exposed(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    exposed = r.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed and "idempotent-replayed" in exposed


def test_origins_are_configurable_by_env():
    code = (
        "from fastapi.testclient import TestClient; import main; c = TestClient(main.app);"
        "r = c.get('/health', headers={'Origin': 'https://shop.example'});"
        "print(r.headers.get('access-control-allow-origin'), main.CORS_ORIGINS)"
    )
    env = {**os.environ, "CORS_ALLOW_ORIGINS": "https://shop.example, https://admin.example", "OPENAI_API_KEY": "sk-test"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.stdout.strip().startswith("https://shop.example ['https://shop.example', 'https://admin.example']"), out.stderr


# ─── OpenAPI ─────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def paths(client):
    return client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("path", LEGACY)
def test_every_legacy_route_carries_the_deprecation_note(paths, path):
    for op in paths[path].values():
        assert NOTE in op["description"] and "/v1" in op["description"]
        assert ("does NOT enforce" in op["description"]) == (path in ORDER_MODE)
        assert ("requires the `X-API-Key`" in op["description"]) == (path in KEYED_WITH_ORDER_ID)
        assert ("is unauthenticated" in op["description"]) == (path == "/orders")


def test_v1_health_and_docs_are_not_marked_legacy(paths):
    for path, ops in paths.items():
        if path.startswith("/v1") or path == "/health":
            assert all(NOTE not in op.get("description", "") for op in ops.values()), path


def test_the_v1_surface(paths):
    v1 = {(m.upper(), p) for p, ops in paths.items() if p.startswith("/v1") for m in ops}
    assert v1 == {
        ("POST", "/v1/risk/evaluate"), ("POST", "/v1/orders"), ("GET", "/v1/orders/{order_id}"),
        ("POST", "/v1/orders/{order_id}/payment"), ("POST", "/v1/orders/{order_id}/verification"),
        ("POST", "/v1/orders/{order_id}/settlement"),
    }


def test_v1_declares_the_api_key_scheme_and_legacy_does_not(client):
    spec = client.get("/openapi.json").json()
    scheme = spec["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme["in"] == "header" and scheme["name"] == "X-API-Key"
    for path, ops in spec["paths"].items():
        for op in ops.values():
            assert bool(op.get("security")) == path.startswith("/v1"), path


def test_idempotency_key_is_documented_on_exactly_the_routes_that_take_it(paths):
    def takes(path):
        return any(p["name"] == "Idempotency-Key" for p in paths[path]["post"].get("parameters", []))

    assert takes("/v1/orders") and takes("/v1/orders/{order_id}/settlement")
    assert not takes("/v1/orders/{order_id}/payment") and not takes("/v1/risk/evaluate")
