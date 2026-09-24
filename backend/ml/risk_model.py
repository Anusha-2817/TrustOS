"""
TrustOS Phase 2 — unsupervised product risk scoring (Isolation Forest).

There are no fraud/dispute labels, so this is anomaly detection: a product is
"risky" to the extent that its listing looks unlike the rest of the seed
catalogue. It is a *relative-oddness* score, not a calibrated fraud probability.

Pipeline
  1. ``backfill_category_avg_price`` — median price per category over the seed set,
     written back to ``seed_products.json`` (left None in Phase 1 on purpose).
  2. ``raw_features`` / ``to_model_space`` — 8 product-level features (see
     ``FEATURES``); heavy-tailed ones are log-transformed, ``verified_review_ratio``
     is capped. ``feature_diagnostics`` reports variance/tie problems.
  3. ``train`` — Isolation Forest, then a monotone calibration of the anomaly
     score onto the 0-100 scale and LOW/MEDIUM/HIGH cutoffs used by
     ``services/risk_engine.py`` (<=30 LOW, <=60 MEDIUM, else HIGH).
  4. ``score_risk(product)`` -> (risk_score, risk_level, top_features).

Run from ``backend/``:  ``python ml/risk_model.py``  (backfill + diagnostics + training report)
                        ``python ml/sanity_check.py`` (eyeball the top/bottom products)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Sequence, Union

import numpy as np
from sklearn.ensemble import IsolationForest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:  # same convention as main.py / scripts/build_seed_data.py
    sys.path.insert(0, str(BACKEND_DIR))

from models.trust_schema import Product  # noqa: E402
from services.risk_engine import RiskEngine  # noqa: E402

SEED_PRODUCTS_PATH = BACKEND_DIR / "data" / "seed_products.json"

# ─── Features ────────────────────────────────────────────────────────────────

# Order matters: it is the column order of the model's input matrix.
FEATURES: List[str] = [
    "price_to_category_ratio",  # price / category median; too-good-to-be-true pricing
    "rating_avg",
    "review_count",
    "verified_review_ratio",
    "negative_review_ratio",
    "listing_age_days",
    "listed_at_is_approx",  # 1 = listed_at is the first-review approximation, 0 = real date
    "image_count",
]

# Above this, a verified-purchase share is indistinguishable from ordinary sampling
# noise: among products with 51+ reviews, 90% have a ratio >= 0.88 (see CLAUDE.md).
# Capping stops trivially-different values (0.9 vs 1.0) from looking "sparse" to the
# forest while keeping the meaningful low tail (0.0-0.85) intact.
VERIFIED_RATIO_CAP = 0.85

# Skewness of the raw distribution drove these: ratio 17.0, review_count 10.1,
# listing_age_days 1.1 -> log makes them roughly symmetric (0.45 / 0.66 / -0.9).
_TRANSFORMS: Dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "price_to_category_ratio": np.log,
    "review_count": np.log1p,
    "listing_age_days": np.log1p,
    "verified_review_ratio": lambda v: np.minimum(v, VERIFIED_RATIO_CAP),  # NaN-preserving
}

# ─── Risk tiers ──────────────────────────────────────────────────────────────

# Percentiles of the *training* anomaly scores that anchor the tier boundaries.
# Unsupervised => no base rate to calibrate to; these are an explicit assumption:
# flag the top 5% for strict handling, the next 15% for moderate friction.
TIER_PERCENTILES = (80.0, 95.0)
# Scale anchors = the risk_engine cutoffs: score 30 <-> P80, 60 <-> P95.
TIER_SCORES = (RiskEngine.LOW_MAX, RiskEngine.MEDIUM_MAX)

MIN_CONTRIBUTION = 0.005  # ignore attribution noise below this (anomaly-score units, ~0.3-0.8 range)

# Tiers come from the engine itself (<=30 LOW, <=60 MEDIUM, else HIGH), not a copy of its cutoffs.
risk_level_for_score = RiskEngine.classify


# ─── Step 1: category_avg_price backfill ─────────────────────────────────────


def compute_category_avg_price(rows: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """Median ``price`` per ``category``, rounded to cents. The median (not the mean) because
    prices are heavy-tailed: one $2,143 item pulls the All_Beauty mean to $40 against a $14 median. Each row
    is included in its own category's median (~150 rows/category, negligible effect)."""
    prices: Dict[str, List[float]] = {}
    for r in rows:
        prices.setdefault(r["category"], []).append(float(r["price"]))
    return {cat: round(float(np.median(v)), 2) for cat, v in sorted(prices.items())}


def backfill_category_avg_price(path: Path = SEED_PRODUCTS_PATH, write: bool = True) -> Dict[str, float]:
    """Set ``category_avg_price`` on every seed row and re-write the file if anything changed.

    Idempotent. Only that key is touched (raw JSON, not a model round-trip), and the file is
    written exactly as ``scripts/build_seed_data.py`` writes it. Every row is re-validated
    against ``Product`` before writing. NOTE: re-running build_seed_data.py resets the field
    to None; re-run this afterwards.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    medians = compute_category_avg_price(rows)
    changed = 0
    for r in rows:
        if r.get("category_avg_price") != medians[r["category"]]:
            r["category_avg_price"] = medians[r["category"]]
            changed += 1
    for r in rows:
        Product.model_validate(r)
    if changed and write:
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"category_avg_price: {changed}/{len(rows)} rows {'updated' if write else 'would change'}; {medians}")
    return medians


def load_seed_products(path: Path = SEED_PRODUCTS_PATH) -> List[Product]:
    return [Product.model_validate(r) for r in json.loads(path.read_text(encoding="utf-8"))]


# ─── Step 2: feature extraction & diagnostics ────────────────────────────────


def raw_features(p: Product, category_medians: Mapping[str, float]) -> Dict[str, float]:
    """Untransformed feature values (NaN = unknown). Falls back to ``category_medians`` when the
    product's own ``category_avg_price`` is unset."""
    avg = p.category_avg_price if p.category_avg_price is not None else category_medians.get(p.category)
    vals = {
        "price_to_category_ratio": p.price / avg if avg else None,
        "rating_avg": p.rating_avg,
        "review_count": p.review_count,
        "verified_review_ratio": p.verified_review_ratio,
        "negative_review_ratio": p.negative_review_ratio,
        "listing_age_days": p.listing_age_days,
        "listed_at_is_approx": None if p.listed_at_source is None else float(p.listed_at_source == "first_review_approx"),
        "image_count": p.image_count,
    }
    return {k: (np.nan if v is None else float(v)) for k, v in vals.items()}


def to_model_space(raw: np.ndarray) -> np.ndarray:
    """Apply the per-feature transforms to an (n, len(FEATURES)) raw matrix."""
    out = np.array(raw, dtype=float, copy=True)
    for j, name in enumerate(FEATURES):
        if name in _TRANSFORMS:
            out[:, j] = _TRANSFORMS[name](out[:, j])
    return out


def _skew(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    sd = a.std()
    return float(np.mean(((a - a.mean()) / sd) ** 3)) if sd > 0 else 0.0


def _tie_stats(col: np.ndarray) -> Dict[str, Any]:
    v = col[~np.isnan(col)]
    vals, counts = np.unique(np.round(v, 9), return_counts=True)
    k = int(np.argmax(counts))
    return {"n_unique": int(len(vals)), "top_value": float(vals[k]), "top_share": float(counts[k] / len(v))}


def feature_diagnostics(raw: np.ndarray, X: np.ndarray, *, print_report: bool = True) -> List[Dict[str, Any]]:
    """Per-feature variance / tie report on the raw matrix and the model-input matrix.

    Flags (on the model input):
      TIES      - one value holds >50% of rows (the forest sees a spike, not a spread)
      FEW_VALUES- fewer than 10 distinct values (skipped for 0/1 indicators)
      RARE_FLAG - a 0/1 indicator whose minority class is <5% of rows
      CONSTANT  - std ~ 0 (useless)
    """
    report = []
    for j, name in enumerate(FEATURES):
        r, m = _tie_stats(raw[:, j]), _tie_stats(X[:, j])
        is_binary = m["n_unique"] <= 2
        flags = []
        if np.nanstd(X[:, j]) < 1e-9:
            flags.append("CONSTANT")
        if m["top_share"] > 0.5 and not is_binary:
            flags.append("TIES")
        if is_binary and (1 - m["top_share"]) < 0.05:
            flags.append("RARE_FLAG")
        if m["n_unique"] < 10 and not is_binary:
            flags.append("FEW_VALUES")
        report.append({
            "feature": name, "missing": int(np.isnan(raw[:, j]).sum()),
            "raw_unique": r["n_unique"], "raw_top": r["top_value"], "raw_top_share": r["top_share"], "raw_skew": _skew(raw[:, j]),
            "in_unique": m["n_unique"], "in_top": m["top_value"], "in_top_share": m["top_share"], "in_skew": _skew(X[:, j]),
            "flags": flags,
        })
    if print_report:
        print(f"{'feature':26s}{'miss':>5s}{'uniq':>6s}{'top value (share)':>24s}{'skew raw->in':>15s}{'uniq_in':>9s}{'top_in (share)':>22s}  flags")
        for d in report:
            print(f"{d['feature']:26s}{d['missing']:5d}{d['raw_unique']:6d}"
                  f"{d['raw_top']:>14.4g} ({d['raw_top_share']:5.1%})"
                  f"{d['raw_skew']:>9.2f}->{d['in_skew']:<5.2f}{d['in_unique']:>8d}"
                  f"{d['in_top']:>13.4g} ({d['in_top_share']:5.1%})  {','.join(d['flags']) or '-'}")
    return report


# ─── Step 3: model ───────────────────────────────────────────────────────────


class RiskResult(NamedTuple):
    risk_score: float          # 0-100, same scale/cutoffs as services/risk_engine
    risk_level: str            # "LOW" | "MEDIUM" | "HIGH"
    top_features: List[Dict[str, Any]]  # what pushed the score up, largest first


@dataclass
class RiskAssessment:
    """Full scoring detail; ``score_risk`` returns the first three fields as a tuple."""

    risk_score: float
    risk_level: str
    top_features: List[Dict[str, Any]]
    anomaly_score: float  # raw Isolation Forest score (higher = more anomalous)
    imputed_features: List[str] = field(default_factory=list)  # unknown inputs filled with the training median


@dataclass
class RiskModel:
    forest: IsolationForest
    medians: np.ndarray                 # model-space training medians (imputation + attribution baseline)
    raw_medians: Dict[str, float]       # same, in original units (for display)
    category_medians: Dict[str, float]
    anchors: np.ndarray                 # anomaly-score anchors [min, P80, P95, max] of the training set
    train_anomaly: np.ndarray

    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:
        """Higher = more anomalous (sklearn's ``score_samples`` is the negative of this)."""
        return -self.forest.score_samples(X)

    def calibrate(self, anomaly: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Monotone piecewise-linear map of anomaly score -> 0-100 with training P80 -> 30 and P95 -> 60.
        Clamped: anything more anomalous than the whole training set scores 100."""
        return np.interp(anomaly, self.anchors, [0.0, *TIER_SCORES, 100.0])

    def features_for(self, product: Product) -> tuple:
        """(raw values dict, model-space vector with unknowns imputed, names of imputed features)."""
        raw = raw_features(product, self.category_medians)
        x = to_model_space(np.array([[raw[n] for n in FEATURES]]))[0]
        nan = np.isnan(x)
        return raw, np.where(nan, self.medians, x), [n for n, m in zip(FEATURES, nan) if m]

    def assess(self, product: Product, top_k: int = 3) -> RiskAssessment:
        raw, x, imputed = self.features_for(product)
        # Attribution by neutralisation: re-score with one feature at a time reset to its
        # training median. contribution = how much less anomalous the product becomes if that
        # feature were typical. Faithful to this forest (no surrogate), cheap (F+1 rows).
        variants = np.tile(x, (len(FEATURES) + 1, 1))
        for j in range(len(FEATURES)):
            variants[j + 1, j] = self.medians[j]
        s = self.anomaly_scores(variants)
        contrib = s[0] - s[1:]
        pos_total = float(contrib[contrib > 0].sum())
        top = []
        for j in np.argsort(-contrib)[:top_k]:
            if contrib[j] < MIN_CONTRIBUTION:
                break
            name = FEATURES[j]
            top.append({
                "feature": name,
                "value": raw[name],
                "typical": self.raw_medians[name],
                "direction": "high" if raw[name] > self.raw_medians[name] else "low",
                "contribution": round(float(contrib[j]), 4),
                "share": round(float(contrib[j]) / pos_total, 3),
            })
        score = float(self.calibrate(s[0]))
        # Tier from the *displayed* (rounded) score, so a shown score and its level never disagree
        # (unrounded 30.0128 used to show as "30.0 MEDIUM" although 30.0 is LOW).
        return RiskAssessment(round(score, 1), risk_level_for_score(round(score, 1)), top, float(s[0]), imputed)


def train(
    products: Sequence[Product],
    *,
    n_estimators: int = 500,
    random_state: int = 42,
) -> RiskModel:
    """Fit the Isolation Forest on ``products`` and derive the score calibration from the training scores."""
    rows = [{"category": p.category, "price": p.price} for p in products]
    category_medians = compute_category_avg_price(rows)
    raw = np.array([[raw_features(p, category_medians)[n] for n in FEATURES] for p in products])
    X = to_model_space(raw)
    medians = np.nanmedian(X, axis=0)
    if np.isnan(medians).any():
        raise ValueError(f"no data at all for feature(s): {[n for n, m in zip(FEATURES, medians) if np.isnan(m)]}")
    X = np.where(np.isnan(X), medians, X)

    forest = IsolationForest(n_estimators=n_estimators, max_samples="auto", contamination="auto", random_state=random_state).fit(X)
    train_anomaly = -forest.score_samples(X)
    p_med, p_high = np.percentile(train_anomaly, TIER_PERCENTILES)
    anchors = np.array([train_anomaly.min(), p_med, p_high, train_anomaly.max()])
    return RiskModel(
        forest=forest,
        medians=medians,
        raw_medians=dict(zip(FEATURES, np.nanmedian(raw, axis=0).tolist())),
        category_medians=category_medians,
        anchors=anchors,
        train_anomaly=train_anomaly,
    )


# ─── Step 4: public scoring API ──────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_default_model() -> RiskModel:
    """Model trained on the seed products (deterministic: seed 42). Cached per process."""
    return train(load_seed_products())


def score_risk(product: Union[Product, Mapping[str, Any]], model: Optional[RiskModel] = None, top_k: int = 3) -> RiskResult:
    """Score one product. Returns ``(risk_score, risk_level, top_features)``.

    ``risk_score`` is 0-100 on the same cutoffs as ``services/risk_engine`` (<=30 LOW, <=60 MEDIUM,
    else HIGH) but *relative to the seed catalogue*: 30 = the 80th-percentile oddness, 60 = the
    95th. ``top_features`` lists up to ``top_k`` features that raised the score, each with its
    value, the training-median ``typical`` value, ``direction`` (high/low vs typical),
    ``contribution`` (anomaly-score drop if reset to typical) and ``share`` of the total.
    A typical (low-risk) product may return an empty list. Unknown inputs are imputed with the
    training median; use ``RiskModel.assess`` to see which.
    """
    if not isinstance(product, Product):
        product = Product.model_validate(product)
    a = (model or get_default_model()).assess(product, top_k=top_k)
    return RiskResult(a.risk_score, a.risk_level, a.top_features)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("== 1. category_avg_price backfill ==")
    backfill_category_avg_price()

    products = load_seed_products()
    medians = compute_category_avg_price([{"category": p.category, "price": p.price} for p in products])
    raw = np.array([[raw_features(p, medians)[n] for n in FEATURES] for p in products])
    X = to_model_space(raw)
    print(f"\n== 2. feature diagnostics ({len(products)} rows; 'in' = model input after transform) ==")
    feature_diagnostics(raw, X)

    print("\n== 3. training ==")
    model = train(products)
    a = model.anchors
    print(f"anomaly score (higher = more odd): min={a[0]:.4f}  P{TIER_PERCENTILES[0]:.0f}={a[1]:.4f}  P{TIER_PERCENTILES[1]:.0f}={a[2]:.4f}  max={a[3]:.4f}")
    scores = model.calibrate(model.train_anomaly)
    levels = np.array([risk_level_for_score(round(float(s), 1)) for s in scores])  # same rounding as assess()
    for lvl in ("LOW", "MEDIUM", "HIGH"):
        n = int((levels == lvl).sum())
        print(f"  {lvl:6s} {n:4d} ({n / len(levels):5.1%})")


if __name__ == "__main__":
    main()
