"""Phase 4: orders, payments, verifications, risk_decision_log

Hand-written and frozen: it does not import db_schema.py, so later edits to the metadata can't
silently rewrite history. tests/test_db_migration.py checks the two stay in sync.

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")
UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("order_id", pg.UUID(as_uuid=True), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("buyer_id", sa.Text(), nullable=False),
        sa.Column("seller_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="INR", nullable=False),
        sa.Column("status", sa.Text(), server_default="CREATED", nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_tier", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("order_id", name="pk_orders"),
        sa.CheckConstraint("length(buyer_id) > 0", name="ck_orders_buyer_id_nonempty"),
        sa.CheckConstraint("length(seller_id) > 0", name="ck_orders_seller_id_nonempty"),
        sa.CheckConstraint("amount > 0", name="ck_orders_amount_positive"),
        sa.CheckConstraint("status IN ('CREATED', 'ACTIVE', 'COMPLETED', 'CANCELLED')", name="ck_orders_status"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_orders_risk_score_range"),
        sa.CheckConstraint("risk_tier IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_orders_risk_tier"),
    )
    op.create_index("ix_orders_seller_id_created_at", "orders", ["seller_id", sa.text("created_at DESC")])
    op.create_index("ix_orders_buyer_id_created_at", "orders", ["buyer_id", sa.text("created_at DESC")])

    op.create_table(
        "payments",
        sa.Column("payment_id", pg.UUID(as_uuid=True), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("triggered_by", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="INR", nullable=False),
        sa.Column("provider", sa.Text(), server_default="razorpay_simulation", nullable=False),
        sa.Column("provider_ref", sa.Text(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("payment_id", name="pk_payments"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="fk_payments_order_id_orders", ondelete="RESTRICT"),
        sa.CheckConstraint("route IN ('DIRECT_CAPTURE', 'AUTHORIZE_ONLY', 'WALLET_HOLD')", name="ck_payments_route"),
        sa.CheckConstraint(
            "status IN ('AUTHORIZED', 'HELD', 'CAPTURED', 'RELEASED', 'CANCELLED', 'REFUNDED')", name="ck_payments_status"
        ),
        sa.CheckConstraint("triggered_by IN ('MANUAL', 'AUTO', 'TIMEOUT')", name="ck_payments_triggered_by"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])

    op.create_table(
        "verifications",
        sa.Column("verification_id", pg.UUID(as_uuid=True), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("details", pg.JSONB(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("verification_id", name="pk_verifications"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="fk_verifications_order_id_orders", ondelete="RESTRICT"),
        sa.CheckConstraint("type IN ('PASSIVE', 'USER_CONFIRMATION', 'MANDATORY_VIDEO')", name="ck_verifications_type"),
        sa.CheckConstraint(
            "result IN ('PENDING', 'SUCCESS', 'ISSUE', 'FRAUD', 'INCONSISTENT', 'NO_RESPONSE')", name="ck_verifications_result"
        ),
        sa.CheckConstraint("(result = 'PENDING') = (completed_at IS NULL)", name="ck_verifications_completed_iff_resolved"),
    )
    op.create_index("ix_verifications_order_id", "verifications", ["order_id"])

    op.create_table(
        "risk_decision_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("buyer_id", sa.Text(), nullable=True),
        sa.Column("seller_id", sa.Text(), nullable=True),
        sa.Column("product_id", sa.Text(), nullable=True),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=False),
        sa.Column("ml_model_version", sa.Text(), nullable=True),
        sa.Column("buyer_successful_orders", sa.Integer(), nullable=True),
        sa.Column("buyer_total_orders", sa.Integer(), nullable=True),
        sa.Column("buyer_disputes", sa.Integer(), nullable=True),
        sa.Column("buyer_fraud_flags", sa.Integer(), nullable=True),
        sa.Column("seller_successful_orders", sa.Integer(), nullable=True),
        sa.Column("seller_total_orders", sa.Integer(), nullable=True),
        sa.Column("seller_complaints", sa.Integer(), nullable=True),
        sa.Column("seller_fraud_flags", sa.Integer(), nullable=True),
        sa.Column("order_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("is_new_pair", sa.Boolean(), nullable=True),
        sa.Column("is_new_device", sa.Boolean(), nullable=True),
        sa.Column("request_payload", pg.JSONB(), nullable=False),
        sa.Column("buyer_trust", sa.Numeric(5, 2), nullable=True),
        sa.Column("seller_trust", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("final_tier", sa.Text(), nullable=False),
        sa.Column("escalated_from", sa.Text(), nullable=True),
        sa.Column("product_risk_applicable", sa.Boolean(), nullable=True),
        sa.Column("product_risk_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("product_risk_level", sa.Text(), nullable=True),
        sa.Column("product_risk_top_features", pg.JSONB(), nullable=True),
        sa.Column("product_risk_imputed", pg.ARRAY(sa.Text()), nullable=True),
        sa.Column("llm_is_fallback", sa.Boolean(), nullable=True),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("llm_signals", pg.JSONB(), nullable=True),
        sa.Column("llm_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("llm_risk_modifier", sa.Numeric(8, 2), nullable=True),
        sa.Column("behavior_risk", sa.Numeric(6, 2), nullable=True),
        sa.Column("components", pg.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_risk_decision_log"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="fk_risk_decision_log_order_id_orders", ondelete="RESTRICT"),
        sa.CheckConstraint("length(source) > 0", name="ck_risk_decision_log_source_nonempty"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_decision_log_risk_score_range"),
        sa.CheckConstraint("final_tier IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_risk_decision_log_final_tier"),
        sa.CheckConstraint("escalated_from IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_risk_decision_log_escalated_from"),
        sa.CheckConstraint(
            "escalated_from IS NULL OR escalated_from <> final_tier", name="ck_risk_decision_log_escalation_changes_tier"
        ),
        sa.CheckConstraint("product_risk_level IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_risk_decision_log_product_risk_level"),
        sa.CheckConstraint(
            "llm_is_fallback IS NOT NULL OR (llm_signals IS NULL AND llm_confidence IS NULL AND llm_risk_modifier IS NULL"
            " AND behavior_risk IS NULL AND llm_model IS NULL)",
            name="ck_risk_decision_log_llm_fields_need_fallback_flag",
        ),
    )
    op.create_index(
        "ix_risk_decision_log_order_id_decided_at",
        "risk_decision_log",
        ["order_id", sa.text("decided_at DESC")],
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index("ix_risk_decision_log_decided_at_brin", "risk_decision_log", ["decided_at"], postgresql_using="brin")

    # The log is an audit trail: rows are never edited or removed. (TRUNCATE is not row-level, so test
    # cleanup can still reset it; ordinary UPDATE / DELETE — from any role — cannot.)
    op.execute(
        """
        CREATE FUNCTION risk_decision_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'risk_decision_log is append-only (% not allowed)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_risk_decision_log_append_only
        BEFORE UPDATE OR DELETE ON risk_decision_log
        FOR EACH ROW EXECUTE FUNCTION risk_decision_log_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_risk_decision_log_append_only ON risk_decision_log")
    op.execute("DROP FUNCTION IF EXISTS risk_decision_log_append_only()")
    op.drop_table("risk_decision_log")
    op.drop_table("verifications")
    op.drop_table("payments")
    op.drop_table("orders")
