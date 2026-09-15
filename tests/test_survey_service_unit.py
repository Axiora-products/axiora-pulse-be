"""Unit tests for app/services/survey_service.py — the uncovered helpers.

Current coverage focuses on the API surface (tests/test_surveys.py). These tests
cover the remaining service functions directly:
  - `_mask_token` (private token masking helper)
  - `sync_survey_from_validation_result` (agent-result → surveys table auto-sync)
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password_async
from app.db.models import Role, Survey, User, Workspace
from app.services.survey_service import SurveyService, survey_service

service = SurveyService()


# ── _mask_token ──────────────────────────────────────────────────────────────

def test_mask_token_masks_all_but_last_four():
    assert service._mask_token("0123456789abcdef") == "***cdef"
    assert service._mask_token(None) is None
    assert service._mask_token("") == ""


def test_mask_token_short_token():
    assert service._mask_token("abc") == "***"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def create_user(db_session: AsyncSession, *, username: str) -> User:
    member_role = (await db_session.execute(select(Role).where(Role.name == "member"))).scalar_one_or_none()
    if member_role is None:
        member_role = Role(name="member", description="Paid subscription user")
        db_session.add(member_role)
        await db_session.flush()
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        register_mfa=True,
        role=member_role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(db_session: AsyncSession, *, user_id: int) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name="Idea Workspace",
        state="GATHERING_INFO",
        idea={},
        conversation_history=[],
        validation_result=None,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


def _validation_result_with_questions() -> dict:
    return {
        "agent_results": {
            "survey_intelligence_agent": {
                "data": {
                    "questions": [
                        {
                            "question_text": "How often do you shop online?",
                            "question_type": "radio",
                            "options": ["Daily", "Weekly", "Monthly"],
                        },
                        {
                            "question_text": "Describe your ideal product.",
                            "question_type": "textarea",
                            "options": [],
                        },
                    ]
                }
            }
        }
    }


# ── sync_survey_from_validation_result ───────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_creates_survey_from_agent_questions(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-survey@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    await service.sync_survey_from_validation_result(
        user.id, workspace.id, _validation_result_with_questions(), db_session
    )

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert len(survey.questions) == 2
    types = {q["questionType"] for q in survey.questions}
    assert "radio" in types
    assert "text" in types  # textarea maps to text


@pytest.mark.asyncio
async def test_sync_noop_if_validation_result_missing(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-noop1@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    await service.sync_survey_from_validation_result(None, workspace.id, None, db_session)
    await service.sync_survey_from_validation_result(user.id, workspace.id, {}, db_session)

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_sync_noop_if_no_questions(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-noop2@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    payload = {"agent_results": {"survey_intelligence_agent": {"data": {"questions": []}}}}
    await service.sync_survey_from_validation_result(user.id, workspace.id, payload, db_session)

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_sync_handles_missing_user_gracefully(db_session: AsyncSession):
    # No user exists with this id — sync should not raise.
    await service.sync_survey_from_validation_result(
        999999, 1, _validation_result_with_questions(), db_session
    )


@pytest.mark.asyncio
async def test_sync_defaults_question_text_and_type(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-defaults@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    payload = {
        "agent_results": {
            "survey_intelligence_agent": {
                "data": {
                    "questions": [
                        {},
                        {"question_type": "multiple_choice", "options": "not-a-list"},
                    ]
                }
            }
        }
    }
    await service.sync_survey_from_validation_result(user.id, workspace.id, payload, db_session)

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert survey.questions[0]["question"] == "Question 1"
    assert survey.questions[1]["questionType"] == "radio"
    assert survey.questions[1]["options"] == []  # non-list options coerced to empty


@pytest.mark.asyncio
async def test_sync_replaces_existing_survey(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-replace@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    # First sync
    await service.sync_survey_from_validation_result(
        user.id, workspace.id, _validation_result_with_questions(), db_session
    )
    # Second sync with a single question replaces the set
    payload = {
        "agent_results": {
            "survey_intelligence_agent": {
                "data": {
                    "questions": [{"question": "Only question?", "question_type": "checkbox", "options": ["A", "B"]}]
                }
            }
        }
    }
    await service.sync_survey_from_validation_result(user.id, workspace.id, payload, db_session)

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    surveys = result.scalars().all()
    assert len(surveys) == 1
    assert len(surveys[0].questions) == 1
    assert surveys[0].questions[0]["questionType"] == "checkbox"


@pytest.mark.asyncio
async def test_sync_filters_duplicate_questions(db_session: AsyncSession):
    user = await create_user(db_session, username="sync-dedup@example.com")
    workspace = await create_workspace(db_session, user_id=user.id)

    payload = {
        "agent_results": {
            "survey_intelligence_agent": {
                "data": {
                    "questions": [
                        {"question_text": "What is your monthly budget?", "question_type": "multiple_choice", "options": ["$10", "$50"]},
                        {"question_text": "What is your monthly budget?", "question_type": "multiple_choice", "options": ["$10", "$50"]},
                        {"question_text": "  what is your monthly budget?!  ", "question_type": "multiple_choice", "options": ["$10", "$50"]},
                        {"question_text": "Who makes the buying decision?", "question_type": "multiple_choice", "options": ["Me", "Boss"]},
                    ]
                }
            }
        }
    }

    await service.sync_survey_from_validation_result(user.id, workspace.id, payload, db_session)

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id, Survey.user_id == user.id)
    )
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert len(survey.questions) == 2
    assert survey.questions[0]["id"] == 1
    assert survey.questions[0]["question"] == "What is your monthly budget?"
    assert survey.questions[1]["id"] == 2
    assert survey.questions[1]["question"] == "Who makes the buying decision?"


# ── Instance sanity ─────────────────────────────────────────────────────────

def test_module_instance():
    assert isinstance(survey_service, SurveyService)
    assert isinstance(SurveyService(), SurveyService)
