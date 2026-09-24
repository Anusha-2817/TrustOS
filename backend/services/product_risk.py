"""
TrustOS — Product risk adapter (Phase 3).

Connects the Phase 2 anomaly model (``ml/risk_model.py``) to the decision engine:
``product_id`` → catalogue lookup in ``data/seed_products.json`` → all 8 model features →
``ProductRiskModel``.

Product signals come ONLY from the catalogue, never from request fields, so the model always sees
the same USD, fully-populated rows it was trained on (no INR/USD mixing, no mostly-imputed inputs).

  product_id is None          → None (the caller adds nothing to its response)
  product_id not in catalogue → applicable=False, contributes nothing
  product_id in catalogue     → applicable=True with score / level / top_features / imputed_features

numpy + scikit-learn (and the ~1 s model fit) are imported lazily, on the first request that names a
catalogue product; requests without one never pay that cost.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from models import ProductRiskModel

# Same file as ml.risk_model.SEED_PRODUCTS_PATH — not imported from there, since that pulls in sklearn.
CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_products.json"


@lru_cache(maxsize=1)
def _catalogue() -> Dict[str, Dict[str, Any]]:
    rows = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return {r["product_id"]: r for r in rows}


def assess_product(product_id: Optional[str]) -> Optional[ProductRiskModel]:
    if product_id is None:
        return None
    row = _catalogue().get(product_id)
    if row is None:
        return ProductRiskModel(product_id=product_id, applicable=False, reason="product_id not in catalogue")

    from ml.risk_model import get_default_model  # lazy: numpy / sklearn
    from models.trust_schema import Product

    a = get_default_model().assess(Product.model_validate(row))
    return ProductRiskModel(
        product_id=product_id,
        applicable=True,
        score=a.risk_score,
        level=a.risk_level,
        top_features=a.top_features,
        imputed_features=a.imputed_features,
    )
