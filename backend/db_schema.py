"""
TrustOS — database schema (SQLAlchemy Core metadata) and the canonical vocabularies.

This is the code-side mirror of the Alembic migration in ``migrations/versions/``. The migration is
hand-written and frozen; ``tests/test_db_migration.py`` upgrades a real Postgres with it and fails if it
drifts from this metadata (``alembic check``) or if a vocabulary below disagrees with a CHECK constraint.

Conventions: ``TEXT + CHECK`` instead of Postgres enums (cheaper to migrate); ``NUMERIC`` for money and
scores; ``timestamptz`` everywhere; tiers are uppercase, as ``RiskEngine.classify`` returns them.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# ─── Canonical vocabularies (Phase 4 decisions 4) ────────────────────────────────────────────────
TIERS = ("LOW", "MEDIUM", "HIGH")
ORDER_STATUSES = ("CREATED", "ACTIVE", "COMPLETED", "CANCELLED")
PAYMENT_STATUSES = ("AUTHORIZED", "HELD", "CAPTURED", "RELEASED", "CANCELLED", "REFUNDED")
# What caused the payment's latest status change. MANUAL = an explicit API call (/settle). AUTO = the
# system applied tier policy with no further action (LOW's instant capture, the initial AUTHORIZED /
# HELD at /initiate-payment). TIMEOUT = a timer expired (auto-capture / auto-release; no worker yet).
# Auto-capture and auto-release are therefore (status, triggered_by) pairs, not extra statuses.
PAYMENT_TRIGGERS = ("MANUAL", "AUTO", "TIMEOUT")
PAYMENT_ROUTES = ("DIRECT_CAPTURE", "AUTHORIZE_ONLY", "WALLET_HOLD")
VERIFICATION_TYPES = ("PASSIVE", "USER_CONFIRMATION", "MANDATORY_VIDEO")
# Union of /verify's (SUCCESS / FRAUD / INCONSISTENT) and SettlementEngine's (SUCCESS / ISSUE / NO_RESPONSE)
# vocabularies. /verify can produce SUCCESS, FRAUD and INCONSISTENT today; ISSUE and NO_RESPONSE are
# reserved for later (NO_RESPONSE is what a timeout worker would record).
VERIFICATION_RESULTS = ("PENDING", "SUCCESS", "ISSUE", "FRAUD", "INCONSISTENT", "NO_RESPONSE")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


metadata = sa.MetaData()

_now = sa.text("now()")
_uuid = sa.text("gen_random_uuid()")

orders = sa.Table(
    "orders",
    metadata,
    sa.Column("order_id", pg.UUID(as_uuid=True), primary_key=True, server_default=_uuid),
    # Opaque ids supplied by the caller (Phase 4 decision 5): no parties table, no FK.
    sa.Column("buyer_id", sa.Text, nullable=False),
    sa.Column("seller_id", sa.Text, nullable=False),
    # Catalogue id (seed_products.json). Deliberately no FK: the catalogue is a JSON file.
    sa.Column("product_id", sa.Text),
    sa.Column("amount", sa.Numeric(12, 2), nullable=False),
    sa.Column("currency", sa.CHAR(3), nullable=False, server_default="INR"),
    sa.Column("status", sa.Text, nullable=False, server_default="CREATED"),
    # Denormalised from the order's latest risk_decision_log row (which is authoritative).
    sa.Column("risk_score", sa.Numeric(5, 2)),
    sa.Column("risk_tier", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.CheckConstraint("length(buyer_id) > 0", name="ck_orders_buyer_id_nonempty"),
    sa.CheckConstraint("length(seller_id) > 0", name="ck_orders_seller_id_nonempty"),
    sa.CheckConstraint("amount > 0", name="ck_orders_amount_positive"),
    sa.CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),
    sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_orders_risk_score_range"),
    sa.CheckConstraint(_in("risk_tier", TIERS), name="ck_orders_risk_tier"),
)
# "Orders for this seller / buyer, newest first." The buyer index also serves a future server-side
# is_new_pair check (find the buyer's orders, filter on seller), so there is no (buyer_id, seller_id) index.
sa.Index("ix_orders_seller_id_created_at", orders.c.seller_id, orders.c.created_at.desc())
sa.Index("ix_orders_buyer_id_created_at", orders.c.buyer_id, orders.c.created_at.desc())

payments = sa.Table(
    "payments",
    metadata,
    sa.Column("payment_id", pg.UUID(as_uuid=True), primary_key=True, server_default=_uuid),
    sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False),
    sa.Column("route", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("triggered_by", sa.Text, nullable=False),
    sa.Column("amount", sa.Numeric(12, 2), nullable=False),
    sa.Column("currency", sa.CHAR(3), nullable=False, server_default="INR"),
    sa.Column("provider", sa.Text, nullable=False, server_default="razorpay_simulation"),
    sa.Column("provider_ref", sa.Text),
    sa.Column("authorized_at", sa.DateTime(timezone=True)),
    sa.Column("settled_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.CheckConstraint(_in("route", PAYMENT_ROUTES), name="ck_payments_route"),
    sa.CheckConstraint(_in("status", PAYMENT_STATUSES), name="ck_payments_status"),
    sa.CheckConstraint(_in("triggered_by", PAYMENT_TRIGGERS), name="ck_payments_triggered_by"),
    sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
)
sa.Index("ix_payments_order_id", payments.c.order_id)

verifications = sa.Table(
    "verifications",
    metadata,
    sa.Column("verification_id", pg.UUID(as_uuid=True), primary_key=True, server_default=_uuid),
    # Not unique: a retry (or a re-recorded video) is a second row.
    sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("result", sa.Text, nullable=False, server_default="PENDING"),
    # Type-specific evidence (OTP hand-off, seal continuity, video reference); nothing models these yet.
    sa.Column("details", pg.JSONB),
    sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.CheckConstraint(_in("type", VERIFICATION_TYPES), name="ck_verifications_type"),
    sa.CheckConstraint(_in("result", VERIFICATION_RESULTS), name="ck_verifications_result"),
    sa.CheckConstraint("(result = 'PENDING') = (completed_at IS NULL)", name="ck_verifications_completed_iff_resolved"),
)
sa.Index("ix_verifications_order_id", verifications.c.order_id)

risk_decision_log = sa.Table(
    "risk_decision_log",
    metadata,
    sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    # Which route made the decision: orders_create | decision_evaluate | evaluate_product | initiate_payment.
    sa.Column("source", sa.Text, nullable=False),
    # NULL for evaluations that aren't tied to an order (only rows with an order_id can ever get outcome labels).
    sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.order_id", ondelete="RESTRICT")),
    sa.Column("buyer_id", sa.Text),
    sa.Column("seller_id", sa.Text),
    sa.Column("product_id", sa.Text),
    # ── provenance: what produced this number ──
    # static_v1 = RiskEngine formula (/decision/evaluate, /orders, /initiate-payment);
    # product_v1 = /evaluate-product's formula. The two scores are not comparable.
    sa.Column("formula", sa.Text, nullable=False),
    sa.Column("code_version", sa.Text, nullable=False),
    # sha256 of seed_products.json when the product model ran: the model retrains from that file with a
    # fixed seed, so file hash + pinned sklearn determines it.
    sa.Column("ml_model_version", sa.Text),
    # ── inputs (flat, nullable: the two request shapes don't share every field) ──
    sa.Column("buyer_successful_orders", sa.Integer),
    sa.Column("buyer_total_orders", sa.Integer),
    sa.Column("buyer_disputes", sa.Integer),
    sa.Column("buyer_fraud_flags", sa.Integer),
    sa.Column("seller_successful_orders", sa.Integer),
    sa.Column("seller_total_orders", sa.Integer),
    sa.Column("seller_complaints", sa.Integer),
    sa.Column("seller_fraud_flags", sa.Integer),
    sa.Column("order_value", sa.Numeric(14, 2)),
    sa.Column("currency", sa.CHAR(3)),
    sa.Column("is_new_pair", sa.Boolean),
    sa.Column("is_new_device", sa.Boolean),
    sa.Column("request_payload", pg.JSONB, nullable=False),
    # ── outputs ──
    sa.Column("buyer_trust", sa.Numeric(5, 2)),
    sa.Column("seller_trust", sa.Numeric(5, 2)),
    sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
    sa.Column("final_tier", sa.Text, nullable=False),
    # Mirrors the API: the tier risk_score alone implied, set only when product risk raised it.
    sa.Column("escalated_from", sa.Text),
    # ── product risk (Phase 3). applicable IS NULL = the request had no product_id ──
    sa.Column("product_risk_applicable", sa.Boolean),
    sa.Column("product_risk_score", sa.Numeric(4, 1)),
    sa.Column("product_risk_level", sa.Text),
    sa.Column("product_risk_top_features", pg.JSONB),
    sa.Column("product_risk_imputed", pg.ARRAY(sa.Text)),
    # ── LLM behaviour signals (/evaluate-product only). llm_is_fallback IS NULL = no LLM call on this path.
    # llm_is_fallback = true means call_llm hit its error fallback (signals [], modifier 0, confidence 0.5),
    # which a genuine answer can also look like, so it has to be recorded explicitly. ──
    sa.Column("llm_is_fallback", sa.Boolean),
    sa.Column("llm_model", sa.Text),
    sa.Column("llm_signals", pg.JSONB),
    sa.Column("llm_confidence", sa.Numeric(4, 3)),
    sa.Column("llm_risk_modifier", sa.Numeric(8, 2)),
    sa.Column("behavior_risk", sa.Numeric(6, 2)),
    # ── the rest of the breakdown (risk components, trust breakdowns): dynamic per formula ──
    sa.Column("components", pg.JSONB),
    sa.CheckConstraint("length(source) > 0", name="ck_risk_decision_log_source_nonempty"),
    sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_decision_log_risk_score_range"),
    sa.CheckConstraint(_in("final_tier", TIERS), name="ck_risk_decision_log_final_tier"),
    sa.CheckConstraint(_in("escalated_from", TIERS), name="ck_risk_decision_log_escalated_from"),
    sa.CheckConstraint(
        "escalated_from IS NULL OR escalated_from <> final_tier", name="ck_risk_decision_log_escalation_changes_tier"
    ),
    sa.CheckConstraint(_in("product_risk_level", TIERS), name="ck_risk_decision_log_product_risk_level"),
    sa.CheckConstraint(
        "llm_is_fallback IS NOT NULL OR (llm_signals IS NULL AND llm_confidence IS NULL AND llm_risk_modifier IS NULL"
        " AND behavior_risk IS NULL AND llm_model IS NULL)",
        name="ck_risk_decision_log_llm_fields_need_fallback_flag",
    ),
)
# Decision history for an order, and the join that will attach outcome labels later.
sa.Index(
    "ix_risk_decision_log_order_id_decided_at",
    risk_decision_log.c.order_id,
    risk_decision_log.c.decided_at.desc(),
    postgresql_where=risk_decision_log.c.order_id.isnot(None),
)
# Audit range scans / retraining exports on an append-ordered table: BRIN costs almost nothing.
sa.Index("ix_risk_decision_log_decided_at_brin", risk_decision_log.c.decided_at, postgresql_using="brin")

ALL_TABLES = (orders, payments, verifications, risk_decision_log)
