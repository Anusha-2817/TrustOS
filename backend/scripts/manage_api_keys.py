"""
Issue, list and revoke /v1 API keys (Phase 5a). Run from backend/ with DATABASE_URL set:

    python scripts/manage_api_keys.py create --label acme-gateway     # prints the key ONCE
    python scripts/manage_api_keys.py list
    python scripts/manage_api_keys.py revoke 3fa9c1d2                 # unique prefix of the key hash (see `list`)

Only the sha256 of a key is stored, so a lost key cannot be recovered: revoke it and issue a new one (a label
need not be unique, which makes rotation a create followed by a revoke). A revoked key stops working within
API_KEY_CACHE_TTL seconds (default 30) on a running server.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from services.auth import generate_api_key, hash_api_key  # noqa: E402

MIN_PREFIX = 8


async def create(label: str) -> int:
    key = generate_api_key()
    async with db.transaction() as conn:
        await db.create_api_key(conn, key_hash=hash_api_key(key), label=label)
    print(f"API key for {label!r} (shown once; it cannot be recovered):\n\n    {key}\n")
    print("Send it as the X-API-Key header.")
    return 0


async def list_keys() -> int:
    async with db.transaction() as conn:
        rows = await db.list_api_keys(conn)
    if not rows:
        print("no API keys")
    for r in rows:
        state = f"REVOKED {r['revoked_at']:%Y-%m-%d %H:%M}" if r["revoked_at"] else "active"
        print(f"{r['key_hash'][:16]}  {r['created_at']:%Y-%m-%d %H:%M}  {state:<26}  {r['label']}")
    return 0


async def revoke(prefix: str) -> int:
    if len(prefix) < MIN_PREFIX:
        print(f"give at least {MIN_PREFIX} characters of the key hash (see `list`)", file=sys.stderr)
        return 2
    async with db.transaction() as conn:
        matches = [r for r in await db.list_api_keys(conn) if r["key_hash"].startswith(prefix.lower())]
        if len(matches) != 1:
            print(f"{len(matches)} keys match {prefix!r}; need exactly one", file=sys.stderr)
            return 1
        if not await db.revoke_api_key(conn, matches[0]["key_hash"]):
            print("that key was already revoked", file=sys.stderr)
            return 1
    print(f"revoked {matches[0]['label']!r} ({matches[0]['key_hash'][:16]})")
    return 0


async def run(args) -> int:
    if not db.is_configured():
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        if args.command == "create":
            return await create(args.label)
        if args.command == "list":
            return await list_keys()
        return await revoke(args.prefix)
    finally:
        await db.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="issue a new key").add_argument("--label", required=True, help="who it is for")
    sub.add_parser("list", help="show all keys (hash prefix, state, label)")
    sub.add_parser("revoke", help="revoke a key").add_argument("prefix", help="unique prefix of the key hash")
    args = parser.parse_args(argv)
    if args.command == "create" and not args.label.strip():
        parser.error("--label must not be empty")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
