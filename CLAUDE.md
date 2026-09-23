# TrustOS — project context for Claude

> Keep this file current. Update it whenever a decision is finalized, a phase changes, or the architecture shifts, so future sessions don't need the project re-explained.

## What TrustOS is

A **dynamic transaction control system** (hackathon prototype, not a payments product). Every transaction is risk-scored from buyer trust, seller trust and transaction signals; the score decides how payment, delivery, verification and settlement behave. High trust → money moves instantly, zero friction. Low trust → funds held until proven safe. See [README.md](README.md) for the full flow tables.

Current (static) formula, from the README:
`Risk = 100 - 0.4×BuyerTrust - 0.4×SellerTrust + TransactionRisk` → LOW 0–30, MEDIUM 31–60, HIGH 61+.
`services/product_risk_pipeline.py` (`/evaluate-product`) is the newer variant: trust_risk + value_risk + context_risk + LLM behavior_risk + LLM risk_modifier, clamped 0–100.

## Architecture (as of now)

- **Backend** — FastAPI + Pydantic 2.9 (`backend/`). Run **from `backend/`**: `main.py` does `sys.path.insert` and imports `from models import ...`, `from services... import ...`.
  - `main.py` — app + most routes (`/trust/buyer`, `/trust/seller`, `/risk/score`, `/decision/evaluate`, `/simulator/evaluate`, `/evaluate-product`, `/evaluate-risk`, demo payment-lifecycle routes, `/health`).
  - `routes/` — `order`, `payment`, `verification`, `settlement`, `demo`.
  - `services/` — `trust_engine`, `risk_engine`, `decision_engine`, `product_risk_pipeline`, `llm_risk_signals` (OpenAI), `payment_engine`, `verification_engine`, `settlement_engine`, `order`, `user`, `schemas`.
  - `models/__init__.py` — API request/response models (`BuyerProfile`, `SellerProfile`, `EvaluateProductRequest`, …). Formerly `backend/models.py`; moved into a package (via `git mv`) so `models/trust_schema.py` is importable. `from models import X` still works unchanged.
  - `models/trust_schema.py` — the ML-facing `Product` / `Seller` schema (see below).
  - `db.py` — in-memory dicts only (orders, payments, verifications). **No persistent DB**; data resets on restart.
- **Frontend** — React + Vite + Tailwind + Radix UI (`frontend/`).
- **Known gap** — two separate systems: the AI risk engine (`/evaluate-product`) and the flow engine (`create-order → pay → verify → settle`). The flow engine uses a fixed amount threshold, not the AI score. Connecting them is the immediate next step.
- Simulated, not real: escrow/wallet holds, delayed capture, settlement. Auth is API-key level only; JWT/OAuth/RBAC planned.
- `.env` holds `OPENAI_API_KEY` (gitignored; never print or commit it).

## Roadmap status

**We are in Phase 1: seed data collection** (of a larger roadmap whose end goal is replacing the static risk formula with an ML model that learns weights from transaction outcomes). Later roadmap items from the README: persistent database, JWT/OAuth + RBAC, service-to-service auth, wiring the AI risk score into the flow engine.

**SCOPE DECISION (v1): seller-side risk features are OUT OF SCOPE.** The seed dataset has 0% coverage on every seller metric and we are **not** pulling a second dataset for it right now. **Phase 2 modelling proceeds on product-level features only** (price, ratings, review volume/quality ratios, listing age, images, brand, category). Do not build seller features, seller-dependent joins, or synthesize seller values. The `Seller` model stays in the schema for the future; the seed sellers file is identity-only.

Phase 1 goal: collect **real** Product (and, structurally, Seller) snapshots to train/evaluate the risk model. **Decision: no synthetic data for now — real fields only; anything a source can't supply stays `None` (never backfilled or defaulted).** Phase 1 deliberately has **no outcome labels** on Product/Seller — labels (fraud/dispute/refund) belong to a future Transaction entity that references them.

## Seed data (Phase 1) — `backend/scripts/build_seed_data.py`

Run: `python backend/scripts/build_seed_data.py` (needs network; streams ~850 MB, stores none of it; ~8 min). Writes `backend/data/seed_products.json` (450 rows) and `backend/data/seed_sellers.json` (379 rows); both re-validate against the schema. Deterministic (seed 42, pinned revision).

**Source: `McAuley-Lab/Amazon-Reviews-2023`** (UCSD / McAuley Lab, Hugging Face), pinned revision `2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`, raw item-metadata + raw review JSONL. Categories: `All_Beauty`, `Health_and_Personal_Care`, `Handmade_Products` (150 products each). Rows are tagged `source="real"`, `platform="amazon"` (dataset states no domain), `currency="USD"` (dataset prices are USD, **not INR** — the schema's INR default is only a default).

Sampling: random over items in the first 60 MB of each category's meta file that have **both a price and a store name**. So price/`seller_id` coverage is 100% *by construction*. Real availability in the source before sampling: price 17.7% (All_Beauty) / 19.0% (Health) / 64.3% (Handmade); store 90–99%. The sample is therefore skewed toward priced items and is not a uniform sample of the category.

Field mapping: `price`←meta.price; `rating_avg`←average_rating; `review_count`←rating_number; `seller_id`←`store` (free-text name, not a true seller ID); `brand`←details.Brand; `image_count`←len(images) (None if empty); `verified_review_ratio` / `negative_review_ratio` (≤2★) computed from the reviews of that product present in the review file (median only 2–3 per product, so noisy; 81% of ratios are exactly 1.0); `listed_at`←details["Date First Available"] when present, else earliest review timestamp (approximation), with `listed_at_source` recording which.

`collected_at` is a **fixed bound, 2023-10-01T00:00Z**, for every row — the dataset records no per-row crawl time (its interactions end Sep 2023). Derived ages are relative to it.

**Coverage report** (% rows with a real value):
- Product, 100%: platform, source, collected_at, product_id, seller_id, title, category, price, currency, rating_avg, review_count, verified_review_ratio, negative_review_ratio, listed_at, image_count (and derived `listing_age_days`).
- Product, partial: `brand` 49.3% (All_Beauty ~69%, Health ~53%, Handmade 0% — no Brand key exists there).
- Product, 0%: `list_price`, `category_avg_price` (deliberately deferred — compute later over the seed set), `review_summary`, `reviews_last_30d`, `condition`, `description_length`, `units_sold`, `return_rate`, `dispute_count` (so derived `price_to_category_ratio`, `discount_ratio`, `dispute_rate` are also 0%).
- `listed_at_source` (every row has a `listed_at`; none are None): `date_first_available` 299/450 (66%) vs `first_review_approx` 151/450 (34%). By category — All_Beauty 0 / 150 (**100% approximate**), Health_and_Personal_Care 149 / 1, Handmade_Products 150 / 0. Filter on `listed_at_source` before trusting `listing_age_days`.
- **Seller, 0% except identity**: only `platform`, `source`, `collected_at`, `seller_id` are populated. Every seller metric is None (rating_avg, review_count, positive_feedback_ratio, rating_change_90d, account_created_at, total_orders, successful_orders, complaint_count, dispute_count, fraud_flags, on_time_delivery_ratio, avg_response_time_hours, active_listing_count, is_verified, country) and so are all derived seller fields.

**Seller side is empty by nature of this dataset, and OUT OF SCOPE for v1**: it has no seller entity — no seller ratings, order counts, disputes, account age or verification. We are not sourcing a second dataset for it now (revisit only if the scope decision changes). Do not fill seller fields by aggregating product ratings per store; that is not seller-level data.

## Schema decisions — `backend/models/trust_schema.py` (finalized in draft, pending user review)

Two Pydantic v2 models, `Seller` and `Product`, sharing a `_Snapshot` base (`platform`, `source`, `collected_at`; `extra="forbid"`).

Conventions — keep stable:
- **`None` = unknown, never zero.** Only `source` (scraped) and `currency` (INR) have non-None defaults; collectors must set both explicitly. (`review_count`, `Seller.is_verified`, `Product.condition` were changed from 0/False/NEW defaults to `None` during seed collection.) Rates are `None` when inputs are unknown or the denominator is 0.
- **All ratios are 0–1 fractions**, not percentages (note: the older simulator/trust code uses percents).
- **Point-in-time snapshots**: `collected_at` is tz-aware and required; derived ages (`account_age_days`, `listing_age_days`) are computed vs `collected_at`, never `now()`, to prevent leakage/skew. Product→Seller join = `seller_id` + latest Seller snapshot ≤ Product's `collected_at`.
- `source` (`real|scraped|api|manual|synthetic`; `real` = records from a public dataset) keeps synthetic rows separable from real ones for evaluation.
- Currency default INR.

**Seller** raw: `rating_avg`, `review_count`, `positive_feedback_ratio`, `rating_change_90d`, `account_created_at`, `total_orders`, `successful_orders`, `complaint_count`, `dispute_count`, `fraud_flags`, `on_time_delivery_ratio`, `avg_response_time_hours`, `active_listing_count`, `is_verified`, `country`. Derived: `account_age_days`, `dispute_rate`, `complaint_rate`, `bayesian_rating` (rating shrunk toward 4.0 with prior weight 20, so tiny-sample 5★ sellers don't look elite). `successful_orders`/`complaint_count`/`fraud_flags`/`total_orders` deliberately mirror `SellerProfile` for easy mapping to the existing trust engine.

**Product** raw: identity (`product_id`, `seller_id`, `title`, `category`, `brand`, `review_summary`), price (`price`, `currency`, `list_price`, `category_avg_price`), reputation (`rating_avg`, `review_count`, `verified_review_ratio`, `negative_review_ratio`, `reviews_last_30d`), listing (`listed_at`, `listed_at_source`, `condition`, `image_count`, `description_length`), outcomes (`units_sold`, `return_rate`, `dispute_count`). Derived: `price_to_category_ratio`, `discount_ratio`, `listing_age_days`, `dispute_rate`. `review_summary` is text for the existing LLM signal extractor, not a numeric feature.

**`Product.listed_at_source`** — `Optional[Literal["date_first_available", "first_review_approx"]]`. Exists because `listed_at` mixes two very different things: `date_first_available` is the platform's real listing date; `first_review_approx` is the earliest review date standing in for it (only an upper bound on age, and biased toward products slow to get a first review). Without the flag, downstream code — notably `listing_age_days` — cannot tell a real date from a guess. Set per row by the seed script; `None` exactly when `listed_at` is `None` (enforced by a validator in both directions). When modelling, treat `listing_age_days` as trustworthy only where the source is `date_first_available`, or include the source as a feature/stratum.

Validation: `successful_orders <= total_orders`; `dispute_count <= units_sold`; account/listing dates not after `collected_at`; `listed_at_source` set iff `listed_at` set; ratings 0–5; ratios 0–1; unknown extra fields rejected.

Open items / not yet decided:
- `category_avg_price` is stored per row and still `None` in the seed files; compute it per category over the seed set in a later step (samples are ~150 priced items/category, USD).
- Seller-side data: **out of scope for v1** (see scope decision above); no second dataset planned.
- `listing_age_days` is only real where `listed_at_source == "date_first_available"` (All_Beauty has essentially none); decide how Phase 2 handles the approximate rows (exclude, stratify, or add the source as a feature).
- `verified_review_ratio` is computed from few reviews per product (median 2–3); treat as noisy or gate on review count when modelling.
- `Product.seller_id` is a store name, not a unique seller ID; the same store name across categories collapses into one Seller row.
- No Buyer or Transaction schema yet; `Buyer` signals still live in `models/__init__.py` (`BuyerProfile`).
- Mapping from `Seller`/`Product` → existing `SellerProfile` / `EvaluateProductRequest` not written.
- No `to_features()` / feature-vector export; no persistence layer for collected rows.
- No automated tests exist in the repo; the schema and seed script were checked manually (seed files round-trip through the Pydantic models on write).
