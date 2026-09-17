"""Add emoji answer type to feedback_questionnaires

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-17
"""
from typing import Sequence, Union

from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT_NAME = "ck_feedback_questionnaires_answer_type"
_WITH_EMOJI = "answer_type IN ('textarea', 'radiobuttons', 'checkboxes', 'dropdown', 'emoji')"
_WITHOUT_EMOJI = "answer_type IN ('textarea', 'radiobuttons', 'checkboxes', 'dropdown')"


def upgrade() -> None:
    """Allow the emoji answer type on the feedback form."""
    op.drop_constraint(_CONSTRAINT_NAME, "feedback_questionnaires", type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, "feedback_questionnaires", _WITH_EMOJI)


def downgrade() -> None:
    """Remove the emoji answer type from the feedback form."""
    op.drop_constraint(_CONSTRAINT_NAME, "feedback_questionnaires", type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, "feedback_questionnaires", _WITHOUT_EMOJI)