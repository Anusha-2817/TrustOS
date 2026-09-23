"""
TrustOS Phase 1 — build real seed data from the Amazon Reviews 2023 dataset.

Source: McAuley-Lab/Amazon-Reviews-2023 on Hugging Face (pinned revision below),
raw item-metadata + raw review JSONL files. Real records only: no synthetic data,
no guessed values. Any schema field the dataset cannot supply is left as None.

Run from the repo root or from backend/:
    python backend/scripts/build_seed_data.py
Outputs backend/data/seed_products.json and backend/data/seed_sellers.json (both
validate against models.trust_schema) and prints a per-field coverage report.

What this dataset does NOT have (so these stay None):
  * Any seller-level data. There is no seller entity, rating or review count.
    The only seller-like field is `store`, a free-text name; it is used solely as
    Product.seller_id / Seller.seller_id. Every other Seller field stays None.
  * list_price, units_sold, return_rate, dispute_count, condition,
    reviews_last_30d, description_length, review_summary.
  * category_avg_price is intentionally left None here; compute it later over the
    whole seed set.

Notes on the fields that ARE populated:
  * price is US dollars at crawl time (currency="USD").
  * review_count = meta.rating_number; rating_avg = meta.average_rating.
  * verified_review_ratio / negative_review_ratio are computed over the reviews
    of that product present in the review file (may be fewer than rating_number).
    None when the product has no reviews in the file.
  * listed_at is the real meta.details["Date First Available"] when present (~99%
    of Health/Handmade items, ~0.5% of All_Beauty); otherwise APPROXIMATED as the
    earliest review timestamp for the product; None if neither exists. Each row's
    Product.listed_at_source records which ("date_first_available" or
    "first_review_approx"); the report tallies them by category.
  * collected_at is a fixed dataset-level snapshot bound (see SNAPSHOT_AT), not a
    per-row crawl time, which the dataset does not record.
  * image_count = number of entries in meta.images; None when the list is empty
    (cannot tell "no images" from "not captured").

Sampling: random.Random(seed) over items in the first META_PREFIX_BYTES of each
category's meta file that have BOTH a price and a store name (needed for
category_avg_price and the seller join key). Price/seller_id coverage is therefore
100% by construction; the report also prints the raw availability in the source.
"""

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402

from models.trust_schema import DataSource, Product, Seller  # noqa: E402

DATASET = "McAuley-Lab/Amazon-Reviews-2023"
REVISION = "2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e"  # pinned for reproducibility
RAW_BASE = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/raw"

CATEGORIES = ["All_Beauty", "Health_and_Personal_Care", "Handmade_Products"]
PER_CATEGORY = 150
META_PREFIX_BYTES = 60_000_000
SEED = 42
PLATFORM = "amazon"  # the dataset does not state a domain; only that prices are USD
# Dataset interactions end Sep 2023 per the dataset card; use the first instant
# after that as the snapshot bound so every review timestamp precedes it.
SNAPSHOT_AT = datetime(2023, 10, 1, tzinfo=timezone.utc)

DEFAULT_OUT_DIR = BACKEND_DIR / "data"


# ─── Download helpers ────────────────────────────────────────────────────────


def _stream_lines(
    client: httpx.Client, url: str, max_bytes: Optional[int] = None
) -> Iterator[Tuple[str, int]]:
    """Yield (line, bytes_read_so_far). With max_bytes, request only that prefix."""
    headers = {"Range": f"bytes=0-{max_bytes - 1}"} if max_bytes else {}
    read = 0
    with client.stream("GET", url, headers=headers) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            read += len(line.encode("utf-8")) + 1
            yield line, read
            if max_bytes and read >= max_bytes:
                return


def _parse(line: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None  # a byte-range prefix ends mid-line; that last line is dropped


def _with_retries(fn, attempts: int = 3):
    for i in range(1, attempts + 1):
        try:
            return fn()
        except (httpx.HTTPError, OSError) as exc:
            print(f"    attempt {i}/{attempts} failed: {exc!r}", flush=True)
            if i == attempts:
                raise


# ─── Field extraction ────────────────────────────────────────────────────────


def _price(raw: Any) -> Optional[float]:
    """Real numeric price or None. The dataset uses null / 'None' for missing."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    if isinstance(raw, str):
        try:
            v = float(raw)
        except ValueError:
            return None
        return v if v > 0 else None
    return None


def _store(raw: Any) -> Optional[str]:
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _brand(details: Any) -> Optional[str]:
    if isinstance(details, dict):
        b = details.get("Brand")
        if isinstance(b, str) and b.strip():
            return b.strip()
    return None


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}


def _date_first_available(details: Any) -> Optional[datetime]:
    """Real listing date from details['Date First Available'] ('June 6, 2017'), else None."""
    if not isinstance(details, dict):
        return None
    raw = details.get("Date First Available")
    if not isinstance(raw, str):
        return None
    parts = raw.replace(",", " ").split()
    if len(parts) != 3 or parts[0] not in _MONTHS or not (parts[1].isdigit() and parts[2].isdigit()):
        return None
    try:
        return datetime(int(parts[2]), _MONTHS[parts[0]], int(parts[1]), tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_eligible(item: Dict[str, Any]) -> bool:
    return (
        _price(item.get("price")) is not None
        and _store(item.get("store")) is not None
        and isinstance(item.get("title"), str)
        and bool(item["title"].strip())
        and isinstance(item.get("parent_asin"), str)
        and isinstance(item.get("average_rating"), (int, float))
        and isinstance(item.get("rating_number"), int)
    )


# ─── Per-category pipeline ───────────────────────────────────────────────────


def load_meta_prefix(client: httpx.Client, category: str) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Return (all parsed items in the prefix, raw-availability stats for them)."""
    url = f"{RAW_BASE}/meta_categories/meta_{category}.jsonl"

    def go() -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for line, _ in _stream_lines(client, url, META_PREFIX_BYTES):
            item = _parse(line)
            if item is not None:
                items.append(item)
        return items

    items = _with_retries(go)
    n = len(items)
    avail = {
        "items_in_prefix": n,
        "pct_price": 100 * sum(_price(i.get("price")) is not None for i in items) / n,
        "pct_store": 100 * sum(_store(i.get("store")) is not None for i in items) / n,
        "pct_brand": 100 * sum(_brand(i.get("details")) is not None for i in items) / n,
        "pct_images": 100 * sum(bool(i.get("images")) for i in items) / n,
        "pct_price_and_store": 100 * sum(_is_eligible(i) for i in items) / n,
    }
    return items, avail


def scan_reviews(client: httpx.Client, category: str, wanted: set) -> Dict[str, Dict[str, Any]]:
    """Stream the whole review file once, aggregating only for wanted parent_asins."""
    url = f"{RAW_BASE}/review_categories/{category}.jsonl"

    def go() -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"n": 0, "verified": 0, "known_verified": 0, "neg": 0, "rated": 0, "min_ts": None}
        )
        next_mark = 50_000_000
        for line, read in _stream_lines(client, url):
            if read >= next_mark:
                print(f"    {category}: scanned {read / 1e6:.0f} MB", flush=True)
                next_mark += 50_000_000
            rev = _parse(line)
            if rev is None or rev.get("parent_asin") not in wanted:
                continue
            s = stats[rev["parent_asin"]]
            s["n"] += 1
            if isinstance(rev.get("verified_purchase"), bool):
                s["known_verified"] += 1
                s["verified"] += rev["verified_purchase"]
            if isinstance(rev.get("rating"), (int, float)):
                s["rated"] += 1
                s["neg"] += rev["rating"] <= 2
            ts = rev.get("timestamp")
            if isinstance(ts, (int, float)) and ts > 0 and (s["min_ts"] is None or ts < s["min_ts"]):
                s["min_ts"] = ts
        return dict(stats)

    return _with_retries(go)


def build_product(item: Dict[str, Any], category: str, rs: Optional[Dict[str, Any]]) -> Product:
    rs = rs or {}
    verified_ratio = (
        rs["verified"] / rs["known_verified"] if rs.get("known_verified") else None
    )
    negative_ratio = rs["neg"] / rs["rated"] if rs.get("rated") else None
    # Prefer the real listing date; otherwise approximate with the earliest review.
    listed_at = _date_first_available(item.get("details"))
    listed_at_source = "date_first_available" if listed_at is not None else None
    if listed_at is None and rs.get("min_ts") is not None:
        listed_at = datetime.fromtimestamp(rs["min_ts"] / 1000, tz=timezone.utc)
        listed_at_source = "first_review_approx"
    images = item.get("images")
    return Product(
        platform=PLATFORM,
        source=DataSource.REAL,
        collected_at=SNAPSHOT_AT,
        product_id=item["parent_asin"],
        seller_id=_store(item["store"]),
        title=item["title"].strip()[:500],
        category=category,
        brand=_brand(item.get("details")),
        price=_price(item["price"]),
        currency="USD",
        rating_avg=float(item["average_rating"]),
        review_count=item["rating_number"],
        verified_review_ratio=verified_ratio,
        negative_review_ratio=negative_ratio,
        listed_at=listed_at,
        listed_at_source=listed_at_source,
        image_count=len(images) if isinstance(images, list) and images else None,
    )


# ─── Coverage report ─────────────────────────────────────────────────────────


def coverage(model, rows: List[Any]) -> List[Tuple[str, str, float]]:
    """(field, kind, % non-None) for every raw and derived field of `model`."""
    out = []
    n = len(rows)
    dumps = [r.model_dump() for r in rows]
    for name in model.model_fields:
        out.append((name, "raw", 100 * sum(d[name] is not None for d in dumps) / n))
    for name in model.model_computed_fields:
        out.append((name, "derived", 100 * sum(d[name] is not None for d in dumps) / n))
    return out


def print_coverage(title: str, model, rows: List[Any]) -> None:
    print(f"\n{title} (n={len(rows)})")
    print(f"  {'field':<26}{'kind':<9}{'% real value':>12}")
    for name, kind, pct in coverage(model, rows):
        print(f"  {name:<26}{kind:<9}{pct:>11.1f}%")


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--categories", nargs="+", default=CATEGORIES)
    ap.add_argument("--per-category", type=int, default=PER_CATEGORY)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    products: List[Product] = []
    availability: Dict[str, Dict[str, float]] = {}
    review_support: Dict[str, List[int]] = {}
    skipped: List[str] = []

    timeout = httpx.Timeout(30.0, read=120.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for cat in args.categories:
            print(f"[{cat}] reading meta prefix ({META_PREFIX_BYTES / 1e6:.0f} MB)...", flush=True)
            items, availability[cat] = load_meta_prefix(client, cat)
            eligible = sorted((i for i in items if _is_eligible(i)), key=lambda i: i["parent_asin"])
            if len(eligible) < args.per_category:
                print(f"  only {len(eligible)} eligible items; taking all")
            sample = rng.sample(eligible, min(args.per_category, len(eligible)))
            print(f"[{cat}] sampled {len(sample)} of {len(eligible)} eligible; scanning reviews...", flush=True)
            stats = scan_reviews(client, cat, {i["parent_asin"] for i in sample})
            review_support[cat] = [stats.get(i["parent_asin"], {}).get("n", 0) for i in sample]
            for item in sample:
                try:
                    products.append(build_product(item, cat, stats.get(item["parent_asin"])))
                except ValidationError as exc:
                    skipped.append(f"{item['parent_asin']}: {exc.errors()[0]['msg']}")

    # One Seller row per distinct store name. The dataset has nothing seller-level
    # beyond the name, so every other Seller field stays None.
    store_names = sorted({p.seller_id for p in products})
    sellers = [
        Seller(platform=PLATFORM, source=DataSource.REAL, collected_at=SNAPSHOT_AT, seller_id=s)
        for s in store_names
    ]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path, rows, model in (
        (args.out_dir / "seed_products.json", products, Product),
        (args.out_dir / "seed_sellers.json", sellers, Seller),
    ):
        # Computed fields are excluded so files re-validate under extra="forbid".
        payload = [r.model_dump(mode="json", exclude=set(model.model_computed_fields)) for r in rows]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        assert [model.model_validate(p) for p in payload], f"{path} failed round-trip"
        print(f"wrote {path} ({len(rows)} rows)")

    # ── Reports ──
    print("\n=== Dataset ===")
    print(f"{DATASET} @ {REVISION[:8]}  (raw meta + raw review JSONL; prices in USD)")
    print(f"snapshot bound collected_at={SNAPSHOT_AT.isoformat()}  seed={args.seed}")
    if skipped:
        print(f"\nSKIPPED {len(skipped)} rows failing schema validation:")
        for s in skipped:
            print("  ", s)

    print("\n=== Source availability (all items in the meta prefix, BEFORE sampling) ===")
    print(f"  {'category':<26}{'items':>7}{'price':>8}{'store':>8}{'brand':>8}{'images':>8}{'price+store':>13}")
    for cat, a in availability.items():
        print(
            f"  {cat:<26}{a['items_in_prefix']:>7}{a['pct_price']:>7.1f}%{a['pct_store']:>7.1f}%"
            f"{a['pct_brand']:>7.1f}%{a['pct_images']:>7.1f}%{a['pct_price_and_store']:>12.1f}%"
        )

    print("\n=== Sample (price/seller_id are 100% by construction: sampled only where present) ===")
    by_cat: Dict[str, List[float]] = defaultdict(list)
    for p in products:
        by_cat[p.category].append(p.price)
    for cat, prices in by_cat.items():
        n_rev = review_support[cat]
        print(
            f"  {cat}: {len(prices)} products, price median ${statistics.median(prices):.2f} "
            f"(mean ${statistics.mean(prices):.2f}); reviews found per product: "
            f"median {statistics.median(n_rev)}, {100 * sum(n > 0 for n in n_rev) / len(n_rev):.0f}% have >=1, "
            f"{100 * sum(n >= 5 for n in n_rev) / len(n_rev):.0f}% have >=5"
        )
    print(f"  distinct stores (Seller rows): {len(sellers)}")
    print("\n=== listed_at_source by category (date_first_available = real; first_review_approx = guess) ===")
    print(f"  {'category':<26}{'date_first_available':>22}{'first_review_approx':>21}{'None':>10}{'total':>7}")
    tally: Dict[Tuple[str, Optional[str]], int] = defaultdict(int)
    for p in products:
        tally[(p.category, p.listed_at_source)] += 1
    for cat in list(args.categories) + ["ALL"]:
        c = {
            k: sum(v for (pc, src), v in tally.items() if src == k and (cat == "ALL" or pc == cat))
            for k in ("date_first_available", "first_review_approx", None)
        }
        total = sum(c.values())
        cells = [f"{c[k]} ({100 * c[k] / total:.0f}%)" for k in ("date_first_available", "first_review_approx", None)]
        print(f"  {cat:<26}{cells[0]:>22}{cells[1]:>21}{cells[2]:>10}{total:>7}")

    print("\n=== Coverage report: % of rows with a real (non-None) value ===")
    print_coverage("Product", Product, products)
    print_coverage("Seller", Seller, sellers)


if __name__ == "__main__":
    main()
