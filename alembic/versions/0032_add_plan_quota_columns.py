"""Add per-plan quota columns to plans (workspace / response / regeneration limits, export flag).

Phase-1 entitlements foundation: the platform can now read each plan's limits and
enforce them. Only the limits whose underlying feature already exists are added here
(workspace count, survey-response cap, survey-regeneration count, report export).
Storage caps, stage re-runs and analytics tiers are intentionally deferred — they are
one-line `add_column`s in a later migration once those features are scoped.

Convention for the integer caps: NULL means "unlimited / not enforced" (e.g. admin
or a future unlimited tier). Concrete tier values are back-filled below.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the quota columns. Integer caps are nullable (NULL = unlimited);
    #    export defaults ON so existing behaviour is unchanged until back-filled.
    op.add_column("plans", sa.Column("workspace_limit", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("survey_response_cap", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("regeneration_limit", sa.Integer(), nullable=True))
    op.add_column(
        "plans",
        sa.Column("export_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    # 2. Back-fill the existing catalog rows with the agreed tier limits.
    #    Mapped by current code → target tier:
    #      starter      → Starter   (1  / 100  / 2  / export off)
    #      professional → Builder   (3  / 500  / 5  / export on)
    #      enterprise   → Pro       (10 / 2000 / 10 / export on)
    #    (Codes stay as-is here; the Starter/Builder/Pro rename is a separate step.)
    op.execute("""
        UPDATE plans SET
            workspace_limit     = 1,
            survey_response_cap = 100,
            regeneration_limit  = 2,
            export_enabled      = false
        WHERE code = 'starter'
    """)
    op.execute("""
        UPDATE plans SET
            workspace_limit     = 3,
            survey_response_cap = 500,
            regeneration_limit  = 5,
            export_enabled      = true
        WHERE code = 'professional'
    """)
    op.execute("""
        UPDATE plans SET
            workspace_limit     = 10,
            survey_response_cap = 2000,
            regeneration_limit  = 10,
            export_enabled      = true
        WHERE code = 'enterprise'
    """)


def downgrade() -> None:
    op.drop_column("plans", "export_enabled")
    op.drop_column("plans", "regeneration_limit")
    op.drop_column("plans", "survey_response_cap")
    op.drop_column("plans", "workspace_limit")
