"""
TrustOS — Product & Seller schema for the risk-scoring ML model (Phase 1: seed data).

Conventions (keep these stable; the model and the seed-data collectors rely on them):
  * ``None`` means "unknown / not collectable from the source", never "zero".
    Tree-based models handle NaN natively, and "0 disputes" vs "dispute data
    unavailable" are very different signals.
  * Every ratio is a 0–1 fraction (not a percentage).
  * Every row is a point-in-time snapshot stamped with ``collected_at``. Derived
    ages are computed relative to ``collected_at``, never ``now()``, so a row
    produces the same features whenever it is loaded — this prevents train/serve
    skew and label leakage when transaction outcomes are later joined by time.
  * Currency amounts are in ``currency`` (default INR, matching the existing API).

Field groups below are labelled  [id/meta] (not model features),  [raw] (model
inputs), or [derived] (computed properties, also model inputs).

Import as ``from models.trust_schema import Product, Seller`` (the backend is run
from ``backend/``). ``models/__init__.py`` holds the original API request/response
models that used to live in ``backend/models.py``.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

# Prior used to shrink small-sample ratings toward a typical marketplace mean.
_RATING_PRIOR_MEAN = 4.0
_RATING_PRIOR_WEIGHT = 20  # "pseudo-reviews" of prior strength


class DataSource(str, Enum):
    """Provenance of a row. Keep synthetic and real data separable for evaluation."""

    REAL = "real"  # real records from a public dataset (not scraped by us, not synthetic)
    SCRAPED = "scraped"
    API = "api"
    MANUAL = "manual"
    SYNTHETIC = "synthetic"


class ProductCondition(str, Enum):
    NEW = "new"
    REFURBISHED = "refurbished"
    USED = "used"


class _Snapshot(BaseModel):
    """Shared provenance fields for every collected row."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # [id/meta]
    platform: str = Field(..., min_length=1, max_length=100, description="Marketplace the row came from, e.g. 'amazon.in'.")
    source: DataSource = Field(DataSource.SCRAPED, description="How the row was obtained; lets us hold out or exclude synthetic rows.")
    collected_at: AwareDatetime = Field(..., description="When this snapshot was taken (tz-aware). Anchor for all derived ages.")


# ─── Seller ──────────────────────────────────────────────────────────────────


class Seller(_Snapshot):
    """A marketplace seller at a point in time."""

    # [id/meta]
    seller_id: str = Field(..., min_length=1, max_length=200)

    # Reputation — the seller-side analogue of "what do other buyers say?"
    rating_avg: Optional[float] = Field(
        None, ge=0, le=5,
        description="Mean star rating. Meaningless without review_count (5.0 from 3 reviews ≠ 4.6 from 3,000), so see bayesian_rating.",
    )
    review_count: Optional[int] = Field(None, ge=0, description="Number of ratings/reviews. Volume = confidence in rating_avg and hard to fake at scale.")
    positive_feedback_ratio: Optional[float] = Field(
        None, ge=0, le=1,
        description="Share of positive feedback (many marketplaces expose this instead of stars). Complements rating_avg.",
    )
    rating_change_90d: Optional[float] = Field(
        None, ge=-5, le=5,
        description="Change in rating_avg over the last 90 days. A falling rating flags recent deterioration or a hijacked account that lifetime averages hide.",
    )

    # History — tenure and volume
    account_created_at: Optional[AwareDatetime] = Field(
        None, description="Account creation time. Scam sellers are disproportionately young or dormant-then-reactivated accounts.",
    )
    total_orders: Optional[int] = Field(None, ge=0, description="Lifetime orders fulfilled or attempted. Track record and the denominator for every rate.")
    successful_orders: Optional[int] = Field(None, ge=0, description="Orders completed without complaint/dispute (matches SellerProfile.successful_orders).")

    # Adverse history — the most direct proxy for outcome risk
    complaint_count: Optional[int] = Field(None, ge=0, description="Informal buyer complaints (matches SellerProfile.complaints).")
    dispute_count: Optional[int] = Field(None, ge=0, description="Formal disputes/claims/chargebacks. Stronger and rarer than complaints.")
    fraud_flags: Optional[int] = Field(None, ge=0, description="Confirmed fraud incidents (matches SellerProfile.fraud_flags). Near-deterministic risk signal.")

    # Operations — reliability of fulfilment
    on_time_delivery_ratio: Optional[float] = Field(None, ge=0, le=1, description="Share of orders delivered on time. Late/never-shipped is the classic seller-side failure mode.")
    avg_response_time_hours: Optional[float] = Field(None, ge=0, description="Median time to reply to buyers. Unresponsive sellers correlate with abandoned or fake storefronts.")
    active_listing_count: Optional[int] = Field(None, ge=0, description="Live listings. Huge catalogue with a tiny order history suggests a scraped/dropship or fake shop.")

    # Identity
    is_verified: Optional[bool] = Field(None, description="Platform-verified identity/business. Raises the cost of abandoning the account.")
    country: Optional[str] = Field(None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2. Cross-border sellers have weaker recourse.")

    @model_validator(mode="after")
    def _check_consistency(self) -> "Seller":
        if (
            self.total_orders is not None
            and self.successful_orders is not None
            and self.successful_orders > self.total_orders
        ):
            raise ValueError("successful_orders must be <= total_orders")
        if self.account_created_at is not None and self.account_created_at > self.collected_at:
            raise ValueError("account_created_at must not be after collected_at")
        return self

    # [derived]
    @computed_field  # type: ignore[prop-decorator]
    @property
    def account_age_days(self) -> Optional[int]:
        """Account tenure at collection time."""
        if self.account_created_at is None:
            return None
        return (self.collected_at - self.account_created_at).days

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dispute_rate(self) -> Optional[float]:
        """disputes / total_orders. None if either input is unknown or there are no orders."""
        if not self.total_orders or self.dispute_count is None:
            return None
        return self.dispute_count / self.total_orders

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complaint_rate(self) -> Optional[float]:
        """complaints / total_orders. None if either input is unknown or there are no orders."""
        if not self.total_orders or self.complaint_count is None:
            return None
        return self.complaint_count / self.total_orders

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bayesian_rating(self) -> Optional[float]:
        """rating_avg shrunk toward a prior by review volume, so tiny-sample 5-star sellers don't look elite."""
        if self.rating_avg is None or self.review_count is None:
            return None
        n = self.review_count
        return (self.rating_avg * n + _RATING_PRIOR_MEAN * _RATING_PRIOR_WEIGHT) / (n + _RATING_PRIOR_WEIGHT)


# ─── Product ─────────────────────────────────────────────────────────────────


class Product(_Snapshot):
    """A single product listing at a point in time."""

    # [id/meta]
    product_id: str = Field(..., min_length=1, max_length=200)
    seller_id: str = Field(..., min_length=1, max_length=200, description="Join key to Seller (match on seller_id + nearest earlier collected_at).")
    title: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=200, description="Leaf category. Also the grouping key for category_avg_price; fraud base rates differ sharply by category.")
    brand: Optional[str] = Field(None, max_length=200)
    review_summary: Optional[str] = Field(None, max_length=20_000, description="Free-text review digest; consumed by the existing LLM signal extractor, not a numeric feature.")

    # Price — the strongest listing-level scam signal is being "too good to be true"
    price: float = Field(..., gt=0, le=10_000_000, description="Current selling price.")
    currency: str = Field("INR", min_length=3, max_length=3)
    list_price: Optional[float] = Field(None, gt=0, le=10_000_000, description="Original/MRP price. Basis for discount_ratio; implausible discounts are a bait-price marker.")
    category_avg_price: Optional[float] = Field(
        None, gt=0,
        description="Mean price of the category (same currency), computed over the seed dataset at collection time. Denominator for price_to_category_ratio.",
    )

    # Reputation
    rating_avg: Optional[float] = Field(None, ge=0, le=5, description="Mean product star rating.")
    review_count: Optional[int] = Field(None, ge=0, description="Number of product reviews. Zero/low volume means the rating is unproven.")
    verified_review_ratio: Optional[float] = Field(None, ge=0, le=1, description="Share of reviews from verified purchasers. Low values suggest seeded/fake reviews.")
    negative_review_ratio: Optional[float] = Field(None, ge=0, le=1, description="Share of ≤2-star reviews. Surfaces polarised products that a mean rating hides (e.g. counterfeit complaints).")
    reviews_last_30d: Optional[int] = Field(None, ge=0, description="Recent review volume. A burst on a young listing is a review-farming signature.")

    # Listing quality & context
    listed_at: Optional[AwareDatetime] = Field(None, description="When the listing went live. New listings have no track record.")
    listed_at_source: Optional[Literal["date_first_available", "first_review_approx"]] = Field(
        None,
        description=(
            "Origin of listed_at: 'date_first_available' = the platform's real listing date; "
            "'first_review_approx' = earliest review date used as a stand-in (an upper bound on listing age, "
            "biased for products that were slow to get a first review). None iff listed_at is None. "
            "Lets downstream code tell a real date from a guess."
        ),
    )
    condition: Optional[ProductCondition] = Field(None, description="Used/refurbished goods carry more not-as-described disputes.")
    image_count: Optional[int] = Field(None, ge=0, description="Listing photos. Thin listings correlate with low-effort or fake shops.")
    description_length: Optional[int] = Field(None, ge=0, description="Characters in the description. Same rationale as image_count; cheap to collect.")

    # Outcomes at the product level
    units_sold: Optional[int] = Field(None, ge=0, description="Cumulative units sold. Denominator for product-level rates.")
    return_rate: Optional[float] = Field(None, ge=0, le=1, description="Share of units returned. High returns indicate misdescription or poor quality.")
    dispute_count: Optional[int] = Field(None, ge=0, description="Disputes filed against this product. Product-specific, unlike seller-level disputes.")

    @model_validator(mode="after")
    def _check_consistency(self) -> "Product":
        if self.listed_at is not None and self.listed_at > self.collected_at:
            raise ValueError("listed_at must not be after collected_at")
        if (self.listed_at is None) != (self.listed_at_source is None):
            raise ValueError("listed_at_source must be set exactly when listed_at is set")
        if (
            self.units_sold is not None
            and self.dispute_count is not None
            and self.dispute_count > self.units_sold
        ):
            raise ValueError("dispute_count must be <= units_sold")
        return self

    # [derived]
    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_to_category_ratio(self) -> Optional[float]:
        """price / category_avg_price. ≪1 is suspiciously cheap (bait/counterfeit); ≫1 is unusual but rarely fraud."""
        if self.category_avg_price is None:
            return None
        return self.price / self.category_avg_price

    @computed_field  # type: ignore[prop-decorator]
    @property
    def discount_ratio(self) -> Optional[float]:
        """(list_price - price) / list_price, floored at 0. None if list_price is unknown."""
        if self.list_price is None:
            return None
        return max(0.0, (self.list_price - self.price) / self.list_price)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def listing_age_days(self) -> Optional[int]:
        """Listing age at collection time."""
        if self.listed_at is None:
            return None
        return (self.collected_at - self.listed_at).days

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dispute_rate(self) -> Optional[float]:
        """dispute_count / units_sold. None if either input is unknown or nothing has sold."""
        if not self.units_sold or self.dispute_count is None:
            return None
        return self.dispute_count / self.units_sold
