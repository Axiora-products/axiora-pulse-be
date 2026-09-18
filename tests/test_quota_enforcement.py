"""Per-user accumulating entitlements (user_allowed_workspaces) enforcement.

Covers the model built for issues #191/#192/#194:
  - free baseline (1 workspace / 100 responses), created lazily
  - grant_for_plan accumulates (Builder +3/+500) and never decrements
  - workspace check counts ACTIVE + ARCHIVED
  - survey-response check is an account-wide pool across all the owner's surveys
  - admin / disabled enforcement = unlimited
  - webhook `subscription.charged` grants the plan's amount
SUBSCRIPTION_ENFORCED is patched True so the caps actually apply.
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
    Subscription,
    Survey,
    User,
    UserAllowedWorkspaces,
    Workspace,
)
from app.models.survey_models import SubmitPublicSurveyRequest
from app.models.workspace_models import CreateWorkspaceRequest
from app.services.billing_service import billing_service
from app.services.entitlements_service import (
    FREE_RESPONSES,
    FREE_WORKSPACES,
    entitlements_service,
)
from app.services.survey_service import survey_service
from app.services.workspace_service import workspace_service

ENFORCED = "app.services.billing_service.SUBSCRIPTION_ENFORCED"


async def _role(db: AsyncSession, name: str) -> Role:
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=name)
        db.add(role)
        await db.flush()
    return role


async def _user(db: AsyncSession, username: str, role_name: str = "viewer") -> User:
    user = User(username=username, password="x", register_mfa=True, role=await _role(db, role_name))
    db.add(user)
    await db.flush()
    return user


async def _plan(db: AsyncSession, code: str, tier: int, ws: int, resp: int) -> Plan:
    plan = Plan(code=code, name=code.title(), tier=tier, is_active=True, workspace_limit=ws, survey_response_cap=resp)
    db.add(plan)
    await db.flush()
    return plan


async def _workspace(db: AsyncSession, user: User, *, name: str, is_delete: bool = False) -> Workspace:
    w = Workspace(
        user_id=user.id, name=name, state="GATHERING_INFO", idea={},
        conversation_history=[], validation_result=None, is_delete=is_delete,
    )
    db.add(w)
    await db.flush()
    return w


# ── Baseline + workspace enforcement ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_user_baseline_blocks_second_workspace(db_session: AsyncSession):
    user = await _user(db_session, "free@axiorapulse.com")
    await db_session.commit()

    with patch(ENFORCED, True):
        ws_cap, resp_cap = await entitlements_service.get_caps(user, db_session)
        assert (ws_cap, resp_cap) == (FREE_WORKSPACES, FREE_RESPONSES)  # 1 / 100

        # First workspace allowed; second exceeds the baseline of 1.
        await workspace_service.create_workspace(CreateWorkspaceRequest(name="A"), user, db_session)
        with pytest.raises(HTTPException) as exc:
            await workspace_service.create_workspace(CreateWorkspaceRequest(name="B"), user, db_session)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_workspace_count_includes_archived(db_session: AsyncSession):
    user = await _user(db_session, "arch@axiorapulse.com")
    # One ARCHIVED workspace already consumes the single free slot.
    await _workspace(db_session, user, name="old", is_delete=True)
    await db_session.commit()

    with patch(ENFORCED, True):
        with pytest.raises(HTTPException) as exc:
            await workspace_service.create_workspace(CreateWorkspaceRequest(name="new"), user, db_session)
    assert exc.value.status_code == 402


# ── Accumulation (grant) ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grant_for_plan_accumulates_and_never_decrements(db_session: AsyncSession):
    user = await _user(db_session, "grant@axiorapulse.com")
    builder = await _plan(db_session, "builder", 2, ws=3, resp=500)
    await db_session.commit()

    await entitlements_service.grant_for_plan(user.id, builder, db_session)
    row = await entitlements_service.get_or_create(user.id, db_session)
    assert row.allowed_workspaces == FREE_WORKSPACES + 3   # 4
    assert row.allowed_responses == FREE_RESPONSES + 500   # 600

    # Buying / renewing again adds on top — no decrement.
    await entitlements_service.grant_for_plan(user.id, builder, db_session)
    row = await entitlements_service.get_or_create(user.id, db_session)
    assert row.allowed_workspaces == FREE_WORKSPACES + 6   # 7
    assert row.allowed_responses == FREE_RESPONSES + 1000  # 1100


# ── Response pool (account-wide) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_response_allowance_is_account_wide_pool(db_session: AsyncSession):
    owner = await _user(db_session, "owner@axiorapulse.com")
    # Give a small allowance so the pool is easy to fill.
    db_session.add(UserAllowedWorkspaces(user_id=owner.id, allowed_workspaces=5, allowed_responses=2))
    ws = await _workspace(db_session, owner, name="W")
    s1 = Survey(user_id=owner.id, workspace_id=ws.id, public_token="pool_t1", questions=[])
    s2 = Survey(user_id=owner.id, workspace_id=ws.id, public_token="pool_t2", questions=[])
    db_session.add_all([s1, s2])
    await db_session.flush()
    # 2 responses total, split across the two surveys → pool of 2 is full.
    now = datetime.now(timezone.utc)
    db_session.add(PublicSurveyResponse(survey_id=s1.id, respondent_name="A", respondent_email="a@x.com", answers=[], submitted_at=now))
    db_session.add(PublicSurveyResponse(survey_id=s2.id, respondent_name="B", respondent_email="b@x.com", answers=[], submitted_at=now))
    await db_session.commit()

    with patch(ENFORCED, True):
        with pytest.raises(HTTPException) as exc:
            await survey_service.submit_public_survey(
                "pool_t1",
                SubmitPublicSurveyRequest(respondentName="C", respondentEmail="c@x.com", answers=[]),
                db_session,
            )
    assert exc.value.status_code == 403


# ── Bypass ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_is_unlimited(db_session: AsyncSession):
    admin = await _user(db_session, "admin@axiorapulse.com", role_name="admin")
    await db_session.commit()
    with patch(ENFORCED, True):
        assert await entitlements_service.get_caps(admin, db_session) == (None, None)


@pytest.mark.asyncio
async def test_enforcement_off_is_unlimited(db_session: AsyncSession):
    user = await _user(db_session, "dev@axiorapulse.com")
    await db_session.commit()
    with patch(ENFORCED, False):
        assert await entitlements_service.get_caps(user, db_session) == (None, None)


# ── Webhook grant on charge ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_charged_grants_plan_amount(db_session: AsyncSession):
    user = await _user(db_session, "charge@axiorapulse.com")
    plan = await _plan(db_session, "builder", 2, ws=3, resp=500)
    sub = Subscription(
        user_id=user.id, plan_id=plan.id, razorpay_subscription_id="sub_grant",
        razorpay_plan_id="rp", billing_period="monthly", status="active",
    )
    db_session.add(sub)
    await db_session.commit()

    payload = {"payload": {"subscription": {"entity": {"id": "sub_grant", "status": "active"}}}}
    await billing_service.handle_webhook("evt_charge_1", "subscription.charged", payload, db_session)

    row = await entitlements_service.get_or_create(user.id, db_session)
    assert row.allowed_workspaces == FREE_WORKSPACES + 3
    assert row.allowed_responses == FREE_RESPONSES + 500
