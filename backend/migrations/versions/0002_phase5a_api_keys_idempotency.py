"""Phase 5a: api_keys, idempotency_keys

Hand-written and frozen (like 0001): it does not import db_schema.py. tests/test_db_migration.py checks
the two stay in sync.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key_hash", name="pk_api_keys"),
        sa.CheckConstraint("key_hash ~ '^[0-9a-f]{64}$'", name="ck_api_keys_key_hash_sha256_hex"),
        sa.CheckConstraint("length(label) > 0", name="ck_api_keys_label_nonempty"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", pg.JSON(), nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope", "key", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.order_id"], name="fk_idempotency_keys_order_id_orders", ondelete="RESTRICT"),
        sa.CheckConstraint("length(key) BETWEEN 1 AND 255", name="ck_idempotency_keys_key_length"),
        sa.CheckConstraint("response_status BETWEEN 200 AND 299", name="ck_idempotency_keys_response_status_2xx"),
        sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_keys_expires_after_created"),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("api_keys")
