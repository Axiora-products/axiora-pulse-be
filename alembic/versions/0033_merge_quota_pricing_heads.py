"""Merge the two migration heads: 0031 (plan quota columns) and 0032 (launch pricing).

Both descend from 0030 on separate feature branches, so once both are merged to
develop there are two Alembic heads and `alembic upgrade head` is ambiguous (the app
would refuse to boot). This is a no-op merge revision that unifies them into a single
head — it applies no schema changes of its own.

MERGE THIS LAST — only after BOTH 0031 and 0032 are present on the target branch.
Until then, alembic can't resolve `down_revision` and will error.

Revision ID: 0033
Revises: 0031, 0032
Create Date: 2026-09-14
"""

revision = "0033"
down_revision = ("0031", "0032")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op — this revision only unifies the two heads."""
    pass


def downgrade() -> None:
    """No-op — splitting back into two heads requires no schema change."""
    pass
