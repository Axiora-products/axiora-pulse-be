"""Create user_allowed_workspaces — per-user accumulating entitlements (workspaces + responses).

Implements the client's accumulating model (issues #191/#192/#194): each user has a
running allowance that only ever grows. Free baseline = 1 workspace / 100 responses;
every paid Razorpay charge adds the plan's amounts on top (Builder +3 / +500, Pro
+10 / +2000), including on each monthly renewal. There is no decrement.

Only the two limits that are actually built and enforced today live here (workspaces,
survey responses). Export stays a per-plan on/off; storage / regenerations / analytics
are not built and are out of scope.

Kept the ticket's table name `user_allowed_workspaces`; `allowed_responses` is the
response pool added for this model.

Backfill: seed one row per user who currently holds an active subscription, at
`free baseline + their plan's amount`, so existing paid members start with a sane
allowance instead of the bare free baseline. Users without an active subscription get
their row lazily (free baseline) on first use.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_allowed_workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("allowed_workspaces", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("allowed_responses", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_user_allowed_workspaces_user_id"),
    )
    op.create_index(
        "ix_user_allowed_workspaces_user_id", "user_allowed_workspaces", ["user_id"]
    )

    # Seed existing active subscribers: free baseline (1 / 100) + their current plan's amount.
    # DISTINCT ON keeps one row per user (their most recent active subscription).
    op.execute("""
        INSERT INTO user_allowed_workspaces
            (user_id, allowed_workspaces, allowed_responses, created_at, updated_at)
        SELECT DISTINCT ON (s.user_id)
               s.user_id,
               1   + COALESCE(p.workspace_limit, 0),
               100 + COALESCE(p.survey_response_cap, 0),
               now(), now()
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.status = 'active'
        ORDER BY s.user_id, s.created_at DESC
    """)


def downgrade() -> None:
    op.drop_index("ix_user_allowed_workspaces_user_id", table_name="user_allowed_workspaces")
    op.drop_table("user_allowed_workspaces")
