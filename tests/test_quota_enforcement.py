"""Server-side per-plan quota enforcement (fix B).

Covers the two caps added on top of the get_plan_limits foundation:
  - workspace_service.create_workspace      → 402 at the plan's workspace_limit
  - survey_service.submit_public_survey      → 403 at the plan's survey_response_cap

Both resolve limits via get_plan_limits, which — with no subscription — falls back
to the lowest active tier, so a free (Starter) user is capped without a blanket
paywall. SUBSCRIPTION_ENFORCED is patched True so the limits actually apply.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Plan,
    PublicSurveyResponse,
    Role,
    Survey,
    User,
    Workspace,
)
from app.models.survey_models import SubmitPublicSurveyRequest
from app.models.workspace_models import CreateWorkspaceRequest
from app.services.survey_service import survey_service
from app.services.workspace_service import workspace_service


async def _role(db: AsyncSession, name: str) -> Role:
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=name)
        db.add(role)
        await db.flush()
    return role


async def _user(db: AsyncSession, username: str, role_name: str = "member") -> User:
    user = User(username=username, password="x", register_mfa=True, role=await _role(db, role_name))
    db.add(user)
    await db.flush()
    return user


async def _starter_plan(db: AsyncSession, *, workspace_limit=None, response_cap=None) -> Plan:
    """Lowest active tier — what get_plan_limits falls back to without a subscription."""
    plan = Plan(
        code="starter",
        name="Starter",
        tier=1,
        is_active=True,
        workspace_limit=workspace_limit,
        survey_response_cap=response_cap,
    )
    db.add(plan)
    await db.flush()
    return plan


@pytest.mark.asyncio
async def test_create_workspace_blocks_at_workspace_limit(db_session: AsyncSession):
    await _starter_plan(db_session, workspace_limit=1)
    user = await _user(db_session, "wscap@axiorapulse.com")
    await db_session.commit()

    with patch("app.services.billing_service.SUBSCRIPTION_ENFORCED", True):
        # First workspace is allowed.
        await workspace_service.create_workspace(CreateWorkspaceRequest(name="Idea A"), user, db_session)
        # Second exceeds the plan's limit of 1.
        with pytest.raises(HTTPException) as exc:
            await workspace_service.create_workspace(CreateWorkspaceRequest(name="Idea B"), user, db_session)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_create_workspace_unlimited_when_limit_null(db_session: AsyncSession):
    await _starter_plan(db_session, workspace_limit=None)  # NULL = unlimited
    user = await _user(db_session, "wsunlimited@axiorapulse.com")
    await db_session.commit()

    with patch("app.services.billing_service.SUBSCRIPTION_ENFORCED", True):
        await workspace_service.create_workspace(CreateWorkspaceRequest(name="A"), user, db_session)
        await workspace_service.create_workspace(CreateWorkspaceRequest(name="B"), user, db_session)

    count = (
        await db_session.execute(
            select(Workspace.id).where(Workspace.user_id == user.id, Workspace.is_delete.is_(False))
        )
    ).all()
    assert len(count) == 2


@pytest.mark.asyncio
async def test_submit_public_survey_blocks_at_response_cap(db_session: AsyncSession):
    await _starter_plan(db_session, response_cap=1)
    owner = await _user(db_session, "surveyowner@axiorapulse.com")
    workspace = Workspace(
        user_id=owner.id, name="W", state="GATHERING_INFO", idea={},
        conversation_history=[], validation_result=None,
    )
    db_session.add(workspace)
    await db_session.flush()
    survey = Survey(
        user_id=owner.id, workspace_id=workspace.id, public_token="tok_cap", questions=[],
    )
    db_session.add(survey)
    await db_session.flush()
    # One response already collected → at the cap of 1.
    db_session.add(
        PublicSurveyResponse(
            survey_id=survey.id,
            respondent_name="Test Respondent",   # NOT NULL since migration 0031
            respondent_email="resp@example.com",  # NOT NULL since migration 0031
            answers=[],
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    with patch("app.services.billing_service.SUBSCRIPTION_ENFORCED", True):
        with pytest.raises(HTTPException) as exc:
            await survey_service.submit_public_survey(
                "tok_cap",
                SubmitPublicSurveyRequest(
                    respondentName="R", respondentEmail="r@example.com", answers=[]
                ),
                db_session,
            )
    assert exc.value.status_code == 403
