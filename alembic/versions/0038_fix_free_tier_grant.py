"""Fix 0037 backfill: the free (Starter) tier must not grant on top of the baseline.

0037's backfill seeded every active subscriber at `free baseline + their plan's
amount`. But the free tier IS the baseline, so users holding a legacy active Starter
subscription (from when Starter was a paid ₹799 plan) were seeded at
`1 + 1 = 2 workspaces` and `100 + 100 = 200 responses` instead of the free 1 / 100.

This resets only rows still at that exact free-double signature (2 / 200) whose owner
has an active free-tier subscription and NO paid active subscription. The tight guard
means it can't clobber an allowance that has legitimately accumulated since deploy
(those are no longer 2 / 200) and can't touch genuine paid members.

Going forward this cannot recur: Starter has no Razorpay plan (never fires
subscription.charged), and `grant_for_plan` now skips free plans.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-18
"""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE user_allowed_workspaces uaw
        SET allowed_workspaces = 1,
            allowed_responses = 100,
            updated_at = now()
        WHERE uaw.allowed_workspaces = 2
          AND uaw.allowed_responses = 200
          AND EXISTS (
              SELECT 1 FROM subscriptions s JOIN plans p ON p.id = s.plan_id
              WHERE s.user_id = uaw.user_id AND s.status = 'active' AND p.price_monthly = 0
          )
          AND NOT EXISTS (
              SELECT 1 FROM subscriptions s JOIN plans p ON p.id = s.plan_id
              WHERE s.user_id = uaw.user_id AND s.status = 'active' AND p.price_monthly > 0
          )
    """)


def downgrade() -> None:
    # Data correction — nothing to reverse.
    pass
