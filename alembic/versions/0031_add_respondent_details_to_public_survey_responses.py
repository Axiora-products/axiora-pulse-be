"""Add respondent details to public_survey_responses

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add mandatory respondent_name and optional contact_number columns."""
    # server_default backfills pre-existing rows so the NOT NULL column can be added safely.
    op.add_column(
        "public_survey_responses",
        sa.Column("respondent_name", sa.String(length=255), nullable=False, server_default="Unknown Respondent"),
    )
    op.add_column(
        "public_survey_responses",
        sa.Column("contact_number", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Drop respondent details columns."""
    op.drop_column("public_survey_responses", "contact_number")
    op.drop_column("public_survey_responses", "respondent_name")