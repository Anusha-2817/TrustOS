"""Phase 5a: scripts/manage_api_keys.py (run as a subprocess, the way an operator would)."""

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from cases import TRANSACTIONS
from pg_fixtures import fetch
from services import auth

BACKEND = Path(__file__).resolve().parents[1]


def run(url, *args):
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    if url:
        env["DATABASE_URL"] = url
    return subprocess.run([sys.executable, "scripts/manage_api_keys.py", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180)


async def test_create_list_revoke_roundtrip(api, pg_url):
    made = run(pg_url, "create", "--label", "acme gateway")
    assert made.returncode == 0, made.stderr
    key = re.search(r"tos_[A-Za-z0-9_-]+", made.stdout).group(0)

    [row] = await fetch("select key_hash, label, revoked_at from api_keys")
    assert row["key_hash"] == hashlib.sha256(key.encode()).hexdigest() == auth.hash_api_key(key)  # only the hash is stored
    assert row["label"] == "acme gateway" and row["revoked_at"] is None
    assert key not in made.stderr and key not in (await fetch("select label from api_keys"))[0]["label"]

    headers = {"X-API-Key": key}
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 200

    listed = run(pg_url, "list")
    assert "acme gateway" in listed.stdout and "active" in listed.stdout and key not in listed.stdout

    revoked = run(pg_url, "revoke", row["key_hash"][:10])
    assert revoked.returncode == 0 and "acme gateway" in revoked.stdout
    assert "REVOKED" in run(pg_url, "list").stdout
    auth.clear_cache()
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 401

    again = run(pg_url, "revoke", row["key_hash"][:10])
    assert again.returncode == 1 and "already revoked" in again.stderr


async def test_two_keys_can_share_a_label_for_rotation(pg, pg_url):
    for _ in range(2):
        assert run(pg_url, "create", "--label", "rotating").returncode == 0
    assert (await fetch("select count(*) as n from api_keys where label = 'rotating'"))[0]["n"] == 2


async def test_revoke_needs_a_unique_long_enough_prefix(pg, pg_url):
    run(pg_url, "create", "--label", "a")
    assert run(pg_url, "revoke", "abc").returncode == 2  # too short
    assert run(pg_url, "revoke", "0" * 12).returncode == 1  # matches nothing


def test_the_script_needs_a_database_and_a_label():
    assert run(None, "list").returncode == 2
    assert run("postgresql://x@127.0.0.1:9/none", "create", "--label", " ").returncode == 2
