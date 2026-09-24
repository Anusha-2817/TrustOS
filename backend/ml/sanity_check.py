"""
Eyeball test for the risk model: do the highest-scored products actually look like outliers?

Run from ``backend/``:  ``python ml/sanity_check.py``

Prints the 5 highest- and 5 lowest-scored seed products (title / category / price / rating,
plus the top "why" features), the tier x category crosstab (to expose category confounding),
and score stability across random seeds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.risk_model import (  # noqa: E402
    RiskModel,
    get_default_model,
    load_seed_products,
    risk_level_for_score,
    train,
)


def _fmt(name: str, v: float) -> str:
    if name == "listed_at_is_approx":
        return "approx date" if v else "real date"
    if name in ("review_count", "image_count", "listing_age_days"):
        return f"{v:,.0f}"
    return f"{v:.2f}"


def _why(top: list) -> str:
    if not top:
        return "nothing stands out"
    return "; ".join(f"{t['feature']}={_fmt(t['feature'], t['value'])} (typical {_fmt(t['feature'], t['typical'])}, {t['share']:.0%})" for t in top)


def _ranks(a: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(a)).astype(float)


def _show(label: str, idx, products, model: RiskModel, scores: np.ndarray) -> None:
    print(f"\n--- {label} ---")
    for i in idx:
        p = products[i]
        a = model.assess(p)
        print(f"[{a.risk_score:5.1f} {a.risk_level:6s}] {p.title[:70]}")
        print(f"      {p.category} | ${p.price:,.2f} (category median ${p.category_avg_price or model.category_medians[p.category]:,.2f}) | "
              f"rating {p.rating_avg} from {p.review_count} reviews | verified {p.verified_review_ratio:.2f} | "
              f"negative {p.negative_review_ratio:.2f} | {p.image_count} images | age {p.listing_age_days}d ({p.listed_at_source})")
        print(f"      why: {_why(a.top_features)}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    products = load_seed_products()
    model = get_default_model()
    scores = model.calibrate(model.train_anomaly)
    order = np.argsort(-scores)

    _show("5 HIGHEST risk", order[:5], products, model, scores)
    _show("5 LOWEST risk", order[::-1][:5], products, model, scores)

    print("\n--- tier x category ---")
    cats = sorted({p.category for p in products})
    levels = np.array([risk_level_for_score(round(float(s), 1)) for s in scores])  # same rounding as assess()
    print(f"{'':28s}" + "".join(f"{lvl:>9s}" for lvl in ("LOW", "MEDIUM", "HIGH")))
    for c in cats:
        m = np.array([p.category == c for p in products])
        print(f"{c:28s}" + "".join(f"{int((levels[m] == lvl).sum()):9d}" for lvl in ("LOW", "MEDIUM", "HIGH")))

    print("\n--- what drives the HIGH tier (top feature per HIGH product) ---")
    counts: dict = {}
    for i in order[: int((levels == "HIGH").sum())]:
        top = model.assess(products[i], top_k=1).top_features
        key = top[0]["feature"] if top else "(none)"
        counts[key] = counts.get(key, 0) + 1
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:26s}{n:3d}")

    print("\n--- stability: Spearman rank correlation vs. the seed-42 model, other seeds ---")
    base = _ranks(model.train_anomaly)
    for seed in (1, 2, 3):
        other = train(products, random_state=seed)
        rho = np.corrcoef(base, _ranks(other.train_anomaly))[0, 1]
        overlap = len(set(np.argsort(-model.train_anomaly)[:23]) & set(np.argsort(-other.train_anomaly)[:23]))
        print(f"  seed {seed}: rho={rho:.3f}  top-23 overlap={overlap}/23")


if __name__ == "__main__":
    main()
