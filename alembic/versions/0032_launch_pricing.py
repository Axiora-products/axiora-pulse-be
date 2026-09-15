"""Launch pricing: final Starter/Builder/Pro tiers (monthly-only), rename codes.

Sets the signed-off launch catalog:
    Starter  ₹0    (free  — no Razorpay plan)
    Builder  ₹299  (was professional)
    Pro      ₹799  (was enterprise)

Also renames codes professional→builder, enterprise→pro so the DB codes match the
product names (safe: subscriptions reference plan_id, not code; the SPA sends the
plan's code dynamically).

IMPORTANT — Razorpay plan-ids are NULLed here on purpose. A Razorpay Plan is
immutable and encodes its amount, so the previous ids (₹799/₹999/₹1499 test plans)
no longer match the new prices. After this migration:
  • QA (test mode): run `scratch/seed_razorpay_plans.py` with TEST keys to create the
    ₹299 / ₹799 plans and back-fill builder/pro ids. Starter is free → stays NULL.
  • Prod (live mode): create the LIVE ₹299 / ₹799 plans in the client's account and
    back-fill builder/pro ids by hand (never via a migration — that would push live
    ids to QA too).
Until back-filled, `subscribe` returns 503 for builder/pro — the correct safe state
(a clear "not configured" beats charging the wrong amount).

NOTE (release ordering): this revision and 0031 (plan quota columns, on a separate
branch) both descend from 0030. Whichever lands second creates a second Alembic head
— resolve with `alembic merge heads` (or rebase this branch onto 0031 so the chain
is linear 0030→0031→0032).

Revision ID: 0032
Revises: 0030
Create Date: 2026-09-14
"""
from alembic import op

revision = "0032"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Starter → free.
    op.execute("""
        UPDATE plans SET
            name = 'Starter',
            price_monthly = 0,
            price_yearly = 0,
            razorpay_plan_id_monthly = NULL,
            razorpay_plan_id_yearly  = NULL
        WHERE code = 'starter'
    """)
    # professional → builder (₹299).
    op.execute("""
        UPDATE plans SET
            code = 'builder',
            name = 'Builder',
            price_monthly = 299,
            price_yearly = 0,
            razorpay_plan_id_monthly = NULL,
            razorpay_plan_id_yearly  = NULL
        WHERE code = 'professional'
    """)
    # enterprise → pro (₹799).
    op.execute("""
        UPDATE plans SET
            code = 'pro',
            name = 'Pro',
            price_monthly = 799,
            price_yearly = 0,
            razorpay_plan_id_monthly = NULL,
            razorpay_plan_id_yearly  = NULL
        WHERE code = 'enterprise'
    """)


def downgrade() -> None:
    # Restore the previous codes/names/prices. Razorpay ids were dropped and are not
    # recoverable here — reseed if you downgrade.
    op.execute("""
        UPDATE plans SET code = 'enterprise', name = 'Enterprise',
            price_monthly = 1499, price_yearly = 14990
        WHERE code = 'pro'
    """)
    op.execute("""
        UPDATE plans SET code = 'professional', name = 'Professional',
            price_monthly = 999, price_yearly = 9990
        WHERE code = 'builder'
    """)
    op.execute("""
        UPDATE plans SET name = 'Starter Plan',
            price_monthly = 799, price_yearly = 7990
        WHERE code = 'starter'
    """)
