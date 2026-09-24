# TrustOS — project context for Claude

> Keep this file current. Update it whenever a decision is finalized, a phase changes, or the architecture shifts, so future sessions don't need the project re-explained.

## What TrustOS is

A **dynamic transaction control system** (hackathon prototype, not a payments product). Every transaction is risk-scored from buyer trust, seller trust and transaction signals; the score decides how payment, delivery, verification and settlement behave. High trust → money moves instantly, zero friction. Low trust → funds held until proven safe. See [README.md](README.md) for the full flow tables.

Current (static) formula, from the README:
`Risk = 100 - 0.4×BuyerTrust - 0.4×SellerTrust + TransactionRisk` → LOW 0–30, MEDIUM 31–60, HIGH 61+ (cutoffs: `RiskEngine.LOW_MAX` / `MEDIUM_MAX`, the single source of truth).
`/evaluate-product` (inline in `main.py`) is the newer variant: trust_risk + value_risk + context_risk + LLM behavior_risk, clamped 0–100 (the LLM `risk_modifier` is echoed but not added). `services/product_risk_pipeline.py` (`ProductRiskPipeline`) is a *different*, **unused** variant of it (adds `risk_modifier`, different trust_risk); no route calls it.
Since Phase 3, both paths can additionally be **escalated (never lowered)** by the Phase 2 product anomaly model when the request carries a catalogue `product_id`; see "Phase 3".

## Architecture (as of now)

- **Backend** — FastAPI + Pydantic 2.9 (`backend/`). Run **from `backend/`**: `main.py` does `sys.path.insert` and imports `from models import ...`, `from services... import ...`.
  - `main.py` — the app and **all** routes (`/trust/buyer`, `/trust/seller`, `/risk/score`, `/decision/evaluate`, `/simulator/evaluate`, `/simulate/{scenario}`, `/evaluate-product`, `/evaluate-risk`, `/demo/payment-lifecycle`, `/initiate-payment`, `/verify`, `/settle`, `/health`). No `include_router` anywhere. This is the one true flow: evaluate → `/initiate-payment` → `/verify` → `/settle` (the last two are demo toggles).
  - `routes/` — only empty stubs remain (`payment.py`, `verification.py`, `settlement.py`, all 0 bytes, unmounted). Phase 3 **deleted** `routes/demo.py` (the old fixed-amount `create-order → pay → verify → settle` flow: `amount > 10000` HIGH, `> 3000` MEDIUM; never mounted, superseded by `main.py`) and `routes/order.py` (never mounted, and called methods that don't exist: `RiskEngine.transaction_risk/final_risk`, `DecisionEngine.classify`, `TrustEngine.calculate_*`).
  - `services/` — `trust_engine`, `risk_engine`, `decision_engine` (+ `escalate_tier`), `pipeline` (`run_pipeline`, shared Trust → Risk → Decision), `product_risk` (Phase 3 adapter), `payment_engine` (`call_llm`, used by `/evaluate-product`), `llm_risk_signals` + `product_risk_pipeline` (unused), and now-orphaned since `routes/order.py` went: `PaymentEngine` class, `verification_engine`, `settlement_engine`, `schemas` (`OrderInput`), `order`, `user`.
  - `models/__init__.py` — API request/response models (`BuyerProfile`, `SellerProfile`, `EvaluateProductRequest`, …). Formerly `backend/models.py`; moved into a package (via `git mv`) so `models/trust_schema.py` is importable. `from models import X` still works unchanged.
  - `models/trust_schema.py` — the ML-facing `Product` / `Seller` schema (see below).
  - `ml/` — Phase 2 unsupervised risk model: `risk_model.py` (backfill, features, Isolation Forest, `score_risk`) and `sanity_check.py`. Uses `scikit-learn` + `numpy`. Wired in by Phase 3 via `services/product_risk.py`. See "Phase 2" and "Phase 3" below.
  - `tests/` — pytest suite (see "Tests" below).
  - `db.py` — in-memory dicts only (orders, payments, verifications); currently unused. **No persistent DB**.
- **Python environment** — the project venv is `.venv/` at the repo root (made with uv, Python 3.13.7). Phase 3 fixed it: it had fastapi/pydantic/openai but **not numpy, scikit-learn or pytest**, so the ML code only ran on the system Python 3.14. Now `.venv/Scripts/python -m pip install -r backend/requirements-dev.txt` (= `requirements.txt` + pytest) installs everything; verified: numpy 2.5.3, scikit-learn 1.9.1 reproduced the Phase 2 numbers exactly (then 360/67/23; 361/66/23 since the rounding fix, see "Score & tiers") Use the venv, not system Python.
- **Frontend** — React + Vite + Tailwind + Radix UI (`frontend/`). Not yet changed for Phase 3: it never sends `product_id`, so it sees the pre-Phase-3 behaviour.
- ~~Known gap: AI risk engine and flow engine are separate~~ — resolved in Phase 3. (Correction: the "fixed amount threshold flow engine" was `routes/demo.py`, which was never mounted; the live UI flow always went through `main.py`'s formula pipeline.)
- Simulated, not real: escrow/wallet holds, delayed capture, settlement. Auth is API-key level only; JWT/OAuth/RBAC planned.
- `.env` holds `OPENAI_API_KEY` (gitignored; never print or commit it).

## Roadmap status

**Phase 1 (seed data collection) is done; Phase 2 (unsupervised risk scoring on product features) has a working v1 in `backend/ml/`; Phase 3 (wire it into the decision flow, escalate-only, via catalogue `product_id`) is done** — see the "Phase 2" and "Phase 3" sections below. Overall roadmap: the end goal is replacing the static risk formula with an ML model that learns weights from transaction outcomes; Phase 2 is the label-free stepping stone since we have no outcomes yet. Later roadmap items from the README: persistent database, JWT/OAuth + RBAC, service-to-service auth. (Wiring the AI risk score into the flow engine: done in Phase 3.)

**SCOPE DECISION (v1): seller-side risk features are OUT OF SCOPE.** The seed dataset has 0% coverage on every seller metric and we are **not** pulling a second dataset for it right now. **Phase 2 modelling proceeds on product-level features only** (price, ratings, review volume/quality ratios, listing age, images, brand, category). Do not build seller features, seller-dependent joins, or synthesize seller values. The `Seller` model stays in the schema for the future; the seed sellers file is identity-only.

Phase 1 goal: collect **real** Product (and, structurally, Seller) snapshots to train/evaluate the risk model. **Decision: no synthetic data for now — real fields only; anything a source can't supply stays `None` (never backfilled or defaulted).** (One deliberate exception in Phase 2: `category_avg_price` is not source data but a statistic derived from the seed rows themselves, backfilled by `ml/risk_model.py`.) Phase 1 deliberately has **no outcome labels** on Product/Seller — labels (fraud/dispute/refund) belong to a future Transaction entity that references them.

## Seed data (Phase 1) — `backend/scripts/build_seed_data.py`

Run: `python backend/scripts/build_seed_data.py` (needs network; streams ~850 MB, stores none of it; ~8 min). Writes `backend/data/seed_products.json` (450 rows) and `backend/data/seed_sellers.json` (379 rows); both re-validate against the schema. Deterministic (seed 42, pinned revision).

**Source: `McAuley-Lab/Amazon-Reviews-2023`** (UCSD / McAuley Lab, Hugging Face), pinned revision `2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`, raw item-metadata + raw review JSONL. Categories: `All_Beauty`, `Health_and_Personal_Care`, `Handmade_Products` (150 products each). Rows are tagged `source="real"`, `platform="amazon"` (dataset states no domain), `currency="USD"` (dataset prices are USD, **not INR** — the schema's INR default is only a default).

Sampling: random over items in the first 60 MB of each category's meta file that have **both a price and a store name**. So price/`seller_id` coverage is 100% *by construction*. Real availability in the source before sampling: price 17.7% (All_Beauty) / 19.0% (Health) / 64.3% (Handmade); store 90–99%. The sample is therefore skewed toward priced items and is not a uniform sample of the category.

Field mapping: `price`←meta.price; `rating_avg`←average_rating; `review_count`←rating_number; `seller_id`←`store` (free-text name, not a true seller ID); `brand`←details.Brand; `image_count`←len(images) (None if empty); `verified_review_ratio` / `negative_review_ratio` (≤2★) computed from the reviews of that product present in the review file (median only 2–3 per product, so noisy; measured on the final 450 rows, 76.2% of `verified_review_ratio` are exactly 1.0 and 58.0% of `negative_review_ratio` are exactly 0.0 (an earlier note said 81%)); `listed_at`←details["Date First Available"] when present, else earliest review timestamp (approximation), with `listed_at_source` recording which.

`collected_at` is a **fixed bound, 2023-10-01T00:00Z**, for every row — the dataset records no per-row crawl time (its interactions end Sep 2023). Derived ages are relative to it.

**Coverage report** (% rows with a real value):
- Product, 100%: platform, source, collected_at, product_id, seller_id, title, category, price, currency, rating_avg, review_count, verified_review_ratio, negative_review_ratio, listed_at, image_count (and derived `listing_age_days`).
- Product, partial: `brand` 49.3% (All_Beauty ~69%, Health ~53%, Handmade 0% — no Brand key exists there).
- Product, 0%: `list_price`, `review_summary`, `reviews_last_30d`, `condition`, `description_length`, `units_sold`, `return_rate`, `dispute_count` (so derived `discount_ratio` and `dispute_rate` are also 0%).
- `category_avg_price` was 0% out of `build_seed_data.py` (deliberately deferred) and is **100% after the Phase 2 backfill** (`ml/risk_model.py`), which also makes derived `price_to_category_ratio` 100%. Re-running `build_seed_data.py` resets it to None — re-run `python ml/risk_model.py` afterwards.
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

**`Product.listed_at_source`** — `Optional[Literal["date_first_available", "first_review_approx"]]`. Exists because `listed_at` mixes two very different things: `date_first_available` is the platform's real listing date; `first_review_approx` is the earliest review date standing in for it (the first review can only come on or after the listing date, so the derived `listing_age_days` is a **lower** bound on true age, and biased toward products slow to get a first review; the schema's field description used to say "upper bound", fixed to "lower bound"). Without the flag, downstream code — notably `listing_age_days` — cannot tell a real date from a guess. Set per row by the seed script; `None` exactly when `listed_at` is `None` (enforced by a validator in both directions). When modelling, treat `listing_age_days` as trustworthy only where the source is `date_first_available`, or include the source as a feature/stratum.

Validation: `successful_orders <= total_orders`; `dispute_count <= units_sold`; account/listing dates not after `collected_at`; `listed_at_source` set iff `listed_at` set; ratings 0–5; ratios 0–1; unknown extra fields rejected.

Open items / not yet decided:
- ~~`category_avg_price`~~ — resolved in Phase 2 (backfilled; see below).
- Seller-side data: **out of scope for v1** (see scope decision above); no second dataset planned.
- ~~`listing_age_days` approximate rows~~ — resolved in Phase 2: kept as rows, with `listed_at_is_approx` as a feature (see below).
- ~~`verified_review_ratio` noise~~ — resolved in Phase 2: kept, capped at 0.85 (see below). It remains the single most influential feature.
- `Product.seller_id` is a store name, not a unique seller ID; the same store name across categories collapses into one Seller row.
- No Buyer or Transaction schema yet; `Buyer` signals still live in `models/__init__.py` (`BuyerProfile`).
- Mapping from `Seller`/`Product` → existing `SellerProfile` / `EvaluateProductRequest` not written.
- No `to_features()` / feature-vector export; no persistence layer for collected rows.
- The schema and seed script were checked manually (seed files round-trip through the Pydantic models on write); API behaviour is covered by `backend/tests/` since Phase 3.

## Phase 2 — unsupervised risk model (`backend/ml/`)

No fraud/dispute labels exist, so this is **anomaly detection, not classification**: a product scores high when its listing looks unlike the rest of the seed catalogue. It is a relative-oddness score, **not a fraud probability**, and is only as useful as the assumption "unusual ≈ worth extra friction". Product-level features only (seller side is out of scope for v1).

Run (from `backend/`): `python ml/risk_model.py` (backfill + tie/variance diagnostics + training report) and `python ml/sanity_check.py` (top/bottom 5, tier × category, seed stability). API: `from ml.risk_model import score_risk` → `score_risk(product) -> (risk_score, risk_level, top_features)`; `product` is a `Product` or a dict. `RiskModel.assess()` additionally returns the raw anomaly score and which inputs were imputed. Deterministic (random_state 42); the model retrains from the seed file in <1s and is cached per process, so no model artifact is committed. Served through `services/product_risk.py` since Phase 3. Tier cutoffs and the 30/60 calibration anchors are imported from `RiskEngine` (`risk_level_for_score` is now an alias of `RiskEngine.classify`), not duplicated.

**`category_avg_price`** = **median** `price` per `category` over `seed_products.json` itself, rounded to cents, written back to every row (All_Beauty 14.38, Handmade_Products 22.95, Health_and_Personal_Care 17.99; USD). Idempotent; only that key is edited. It was first computed as the arithmetic mean (40.07 / 32.43 / 27.29) but switched to the median because one $2,143 All_Beauty item dragged that category's mean to 40.07, making Beauty look systematically cheap (median price ratio 0.36 vs 0.66–0.71 elsewhere). **That caveat is resolved:** with the median baseline the median `price_to_category_ratio` is exactly 1.00 in all three categories, so there is no per-category price offset any more (the log-ratio is centred at 0 everywhere). Switching changed scores very little (Spearman ρ 0.996 vs the mean version; same top-23 set, tiers still 360/67/23). Remaining minor caveat: each product is included in its own category's median (~150 rows/category, negligible). The field keeps the name `category_avg_price` (and the schema description now says median) even though it is a median.

**Features (8), model input after transform** — all have 100% coverage in the seed set:
| feature | transform | why included |
|---|---|---|
| `price_to_category_ratio` | `log` (skew 18.9 → 0.81) | too-cheap bait pricing / abnormal premium; log makes 0.5× and 2× symmetric |
| `rating_avg` | none | reputation; extreme lows (and suspicious perfect scores) are unusual |
| `review_count` | `log1p` (skew 10.1 → 0.66) | evidence volume; 1-review vs 1,000-review listings are different regimes |
| `verified_review_ratio` | **capped at 0.85** | only review-authenticity signal we have; see below |
| `negative_review_ratio` | none | polarised/complained-about products a mean rating hides |
| `listing_age_days` | `log1p` (skew 1.1 → −0.9) | brand-new listings have no track record; recency matters multiplicatively |
| `listed_at_is_approx` | 0/1 | 1 = `first_review_approx`. Kept as a feature, not a row filter, per decision. A two-level one-hot is a single indicator (a second column would be its exact complement) |
| `image_count` | none | thin listings ↔ low-effort shops |

Excluded: `brand` (49% coverage, 0% Handmade); `list_price`, `review_summary`, `reviews_last_30d`, `condition`, `description_length`, `units_sold`, `return_rate`, `dispute_count` (all 0%, so their derived rates too); identifiers `product_id/seller_id/title`; `category` is deliberately not a feature (it only sets the price baseline). No feature has missing values in the seed set; at scoring time unknowns are imputed with the training median (which contributes 0 to the explanation).

**Variance/ties diagnostics** (`feature_diagnostics`, printed by `python ml/risk_model.py`): no constant or few-valued features; two are flagged **TIES**: `verified_review_ratio` (76.2% exactly 1.0 raw) and `negative_review_ratio` (58.0% exactly 0.0). Decisions:
- `negative_review_ratio` — kept as is: 73 distinct values, the ties are the genuine "no complaints" mode, and it carries real signal.
- `verified_review_ratio` — **kept but capped at 0.85** (not dropped, not left raw). Among products with 51+ reviews, 90% have a ratio ≥ 0.88, so 0.85–1.0 is ordinary sampling noise, while the tail below 0.85 (12% of rows; 14 rows exactly 0.0, e.g. a 499-review product with 0% verified) is a plausible review-seeding/non-standard-listing signal. Capping trades more tie-mass (88% at the cap) for removing meaningless variation in the 0.85–1.0 band. **Honest note:** the cap changed the ranking little (top-23 overlap 21/23 vs raw). The feature itself matters a lot: with it removed, half the HIGH tier changes (13/23 overlap); 61% of HIGH products have ratio < 0.85 vs a 12% base rate; it is the top driver for 13 of 23 HIGH products. Some of that is small-sample noise (the ratio is computed from the ~2–3 reviews per product present in the dataset's review file).

**Model**: `sklearn.ensemble.IsolationForest`, 500 trees, `max_samples="auto"` (=256), `contamination="auto"`, no scaling (isolation splits are per-feature). Rank stability across seeds: Spearman ρ ≈ 0.995, top-23 overlap 21–23/23.

**Score & tiers**: raw anomaly score (higher = odder) → piecewise-linear map to 0–100 anchored on the training scores: min→0, **P80→30**, **P95→60**, max→100 (clamped). Levels use the *same cutoffs as the existing engine* (`services/risk_engine`: ≤30 LOW, ≤60 MEDIUM, else HIGH), so the score can drop into the current decision engine. **Thresholds chosen: LOW = bottom 80%, MEDIUM = next 15% (P80–P95), HIGH = top 5%** (seed set: **361 / 66 / 23** of 450). **Invariant: the displayed score and the displayed level never disagree.** `assess()` rounds the score to 1 decimal and assigns the tier from that rounded value, and the CLI reports in `risk_model.py` and `sanity_check.py` do the same. Before this fix the tier came from the unrounded score, so `B00MN8X5RM` (unrounded 30.0128) was returned as "30.0, MEDIUM" although `RiskEngine.classify(30.0)` is LOW (`<=` was always correct; the mismatch was purely display rounding). It is now "30.0, LOW", which moved it MEDIUM → LOW and changed the counts from 360 / 67 / 23 (Health_and_Personal_Care LOW/MEDIUM 112/28 → 113/27). Enforced by `test_boundary_product_level_matches_displayed_score` and `test_displayed_score_and_level_never_disagree` (all 450 rows). Rationale: an anomaly detector should reserve strict handling for a small tail; the README's bands are for a formula score, and applying "31–60 / 61+" as percentiles would call 70% of products elevated-risk. 5% HIGH / 15% MEDIUM is an explicit assumption — with no labels there is no base rate to calibrate to. **The score is relative to the seed catalogue and not comparable to the README formula's score; the anchors must be recomputed (retrain) whenever the data changes.**

**Explanations** (`top_features`, up to 3): attribution by neutralisation — re-score the product with one feature at a time reset to its training median; `contribution` = drop in anomaly score, `share` = fraction of the total positive drop, plus the feature's `value`, training-median `typical`, and `direction` (high/low). Faithful to the actual forest but blind to interactions (it can under-credit two features that are odd only together) and lists only features that raise the score; a typical product returns `[]`.

**Sanity-check results** (seed set): the 5 highest are 1–1.4★ items with all-negative reviews from 1–2 reviews (hair ties, Capezio bobby pins, a scalpel-blade set, a mug; two also at 0–50% verified), plus a $250 foundation powder at 17× its category median; the 5 lowest are ordinary items (4 Handmade, 1 Health; 4.4–4.8★, 5–28 reviews, all verified, real dates). Re-checked after the mean→median switch: same top-5 set, 4/5 same bottom-5. Flagged rows look like genuine outliers.

**Known limitations (v1)**:
- **Small-sample sensitivity.** 43% of HIGH products have ≤3 reviews vs 20% of LOW: a single 1★ review gives rating 1.0 / negative 1.0 and can reach HIGH. That is "thin, bad evidence", not necessarily "scam". Consider shrinking rating-derived features by `review_count` (like `Seller.bayesian_rating`) in v2.
- **Category skew.** Handmade is 91% LOW vs 75% for the other two categories (mean risk score 14 vs 22–26). Not caused by `listed_at_is_approx` (dropping it leaves Handmade at 91%) nor by the price baseline (the mean→median switch moved it only 92%→91%). It looks like a real distribution difference: Handmade is a tighter cluster (median 6 images vs 3, narrower price spread, real dates, few negatives), so the score partly reflects category rather than only individual oddness. Also `listed_at_is_approx` is ~perfectly confounded with category (All_Beauty 100% approx, Handmade 0%), so it is effectively a category indicator here.
- Anomalous ≠ fraudulent: a premium-priced or genuinely unloved product scores high. No outcome data exists to validate the score; the sanity check is an eyeball test only.
- Amazon listings, USD prices, one 2023 snapshot; no seller signal; `store` names are not seller IDs.
- Transform choices, the cap and tier percentiles are constants at the top of `ml/risk_model.py`.

## Phase 3 — product risk wired into the decision flow

**Input: catalogue `product_id` only.** `TransactionRequest` and `EvaluateProductRequest` have an optional `product_id`. It is looked up in `data/seed_products.json` (`services/product_risk.py::assess_product`) and the catalogue row feeds all 8 model features. **No raw product features are accepted on the request, by design.** Two reasons. (1) Currency: the API is INR, while the model's category medians are USD. A request-price feature would read ₹4,999 as roughly 350× the median, and this way no conversion is ever needed. (2) Coverage: from request fields alone, 7 of 8 features would be imputed, and scores then top out at ~25 (always LOW); an unknown category scores 0.0 at any price. So `product_id` absent → no `product_risk` in the response. `product_id` unknown → `product_risk.applicable=false` (with `reason`), contributing nothing. `product_id` found → `applicable=true` with `score` / `level` / `top_features` / `imputed_features` (always `[]` for catalogue rows). The adapter uses `RiskModel.assess()` rather than `score_risk()` because only `assess` reports `imputed_features`.

**Rule: ESCALATE-ONLY** (`services/decision_engine.py::escalate_tier`, table `PRODUCT_RISK_FLOOR`): final tier = max(formula tier, floor), where ML LOW → no floor, ML MEDIUM → MEDIUM and **ML HIGH → MEDIUM**. So:
- LOW + ML MEDIUM/HIGH → MEDIUM
- MEDIUM stays MEDIUM
- HIGH stays HIGH
- not applicable / absent → unchanged

The ML score never lowers a tier and never triggers the HIGH wallet hold on its own. **Why not additive blending:** there is no validated weight. The anomaly score is relative oddness within one 450-row Amazon snapshot, with no outcome labels, so any `w·ml_score` coefficient would be invented. Escalate-only uses the score only as "worth extra friction", which is the one claim it can support. The `risk_score` / `final_risk` number is **never changed**. When escalation happens, `decision.escalated_from` (in `/decision/evaluate` etc.) or top-level `escalated_from` (in `/evaluate-product`) records the formula tier. The returned decision is then the standard MEDIUM decision, so its static `risk_range` "31–60" can sit next to a `risk_score` of e.g. 25. `escalated_from` is how the UI should explain that. Practical effect: ~20% of catalogue products (ML MEDIUM + HIGH: 89/450) will lift a LOW transaction to MEDIUM (delayed capture).

**Where it runs.** `services/pipeline.py::run_pipeline` (moved out of `main.py`) is the single Trust → Risk → Decision path for `/decision/evaluate`, `/simulator/evaluate`, `/simulate/{scenario}`, `/evaluate-risk`, `/demo/payment-lifecycle` and `/initiate-payment`. `/evaluate-product` calls `escalate_tier` itself. `/risk/score` reports `components.product_risk` but makes no tier decision. Only `/decision/evaluate`, `/risk/score` and `/evaluate-product` accept a `product_id`. The simulator and the scenario routes never send one, so they are unchanged. `DecisionEngine.decide(..., product_risk=None)` keeps its old signature compatible, so `ProductRiskPipeline` still works.

**Response compatibility.** The new optional fields (`product_id` echo, `product_risk`, `escalated_from`) are **omitted from the JSON while None** (`models._OmitWhenNone`, a wrap `model_serializer`). A request without `product_id` therefore returns a byte-identical pre-Phase-3 response. That is enforced by the golden tests.

**Laziness.** numpy/sklearn are imported, and the model fitted (~1 s, cached per process), only on the first request whose `product_id` is in the catalogue. The catalogue lookup itself is plain `json`. A test asserts that sklearn is not imported for requests without a catalogue id.

**Category bias: still open, still deferred.** The Phase 2 Handmade skew still applies: ML MEDIUM+HIGH is 9% of Handmade vs 25% of All_Beauty and Health, so Handmade products escalate a LOW transaction about 1/3 as often. Escalate-only **dampens but does not remove** this. It can only move LOW → MEDIUM, never to HIGH, and never affects transactions already MEDIUM/HIGH, but the category-level rate gap passes straight through to how often LOW transactions get escalated. Per-category normalization was analysed and rejected for now. With 150 rows/category the per-category P95 cutoff's bootstrap SD is ~2× the pooled one, and 1–2 of each category's ~8 HIGH products flip tier across resamples. It would also assert equal risk rates per category without evidence, since the data suggests Handmade is genuinely more homogeneous (negative-ratio IQR 0.07 vs 0.25), and categories outside the three seed ones would need a fallback anyway. Revisit when outcome labels exist, or with ≳500 rows/category across more categories.

## Tests — `backend/tests/`

Run from `backend/`: `../.venv/Scripts/python -m pytest tests` (~35–65 s; 86 pass + 1 skipped recorder). `conftest.py` forces a dummy `OPENAI_API_KEY` and replaces `main.call_llm` with a deterministic fake, so no test touches the network.
- `test_characterization.py` — 29 golden responses in `golden/pre_phase3_responses.json`, **recorded from the pre-Phase-3 code** (commit 76d4711, before any source change). They cover `/decision/evaluate`, `/risk/score`, `/evaluate-product`, `/simulator/evaluate`, `/simulate`, `/evaluate-risk`, `/demo/payment-lifecycle` and `/initiate-payment`. The file also asserts that `product_id: null` is byte-identical and that an unknown id is identical apart from `product_risk` (and the `/evaluate-product` id echo). Don't regenerate the golden file to make a test pass. `TRUSTOS_UPDATE_GOLDEN=1` exists only for deliberate, reviewed behaviour changes.
- `test_product_risk.py` — the full 3×3 `escalate_tier` matrix, the adapter, the score/level display invariant, lazy import (subprocess), and end-to-end escalation through the routes. It uses catalogue fixtures `B0BYYPTLHX` (ML HIGH), `B0014LE00U` (MEDIUM) and `B07FSDFF75` (LOW), whose levels are re-asserted.
- Characterization finding: main.py's built-in **`low_risk` scenario actually scores 44.02 = MEDIUM**, and none of the frontend's `/evaluate-product` demo payloads is LOW. The tests add LOW cases (`TRANSACTIONS["trusted"]` 25.0, `PRODUCT_EVALUATIONS["trusted_cheap"]` 27.0). The scenario itself was left as is (behaviour change, not in scope).
