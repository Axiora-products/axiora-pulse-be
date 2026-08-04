
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Survey, User, Workspace
from app.models.survey_models import (
    SaveAllSurveyQuestionsRequest,
    SurveyListResponse,
    SurveyResponse,
    UpdateSurveyRequest,
)

logger = logging.getLogger(__name__)


class SurveyService:

    #save all questions
    async def save_all_questions(
        self,
        payload: SaveAllSurveyQuestionsRequest,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Create or replace the full set of survey questions for a workspace, owned by current_user."""
        if payload.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to save survey questions for this user.",
            )

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == payload.workspaceId)
        )
        workspace = workspace_result.scalar_one_or_none()
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {payload.workspaceId} not found.",
            )
        if workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this workspace.",
            )

        questions_payload = [q.model_dump() for q in payload.questions]
        now = datetime.now(timezone.utc)

        survey_result = await db.execute(
            select(Survey).where(
                Survey.user_id == payload.userId,
                Survey.workspace_id == payload.workspaceId,
            )
        )
        survey = survey_result.scalar_one_or_none()

        if survey is None:
            survey = Survey(
                user_id=payload.userId,
                workspace_id=payload.workspaceId,
                questions=questions_payload,
                created_at=now,
                updated_at=now,
            )
            db.add(survey)
        else:
            survey.questions = questions_payload
            survey.updated_at = now

        await db.flush()
        await db.refresh(survey)

        logger.info(
            "Survey questions saved: survey_id=%s workspace_id=%s user_id=%s question_count=%s",
            survey.id, survey.workspace_id, survey.user_id, len(questions_payload),
        )
        return SurveyResponse.model_validate(survey)

    # Update a survey
    async def update_survey(
        self,
        survey_id: int,
        payload: UpdateSurveyRequest,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Partially update a survey's link and/or question set — 404/403 enforced."""
        if payload.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update surveys for this user.",
            )

        result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )
        if survey.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this survey.",
            )

        if payload.surveyLink is not None:
            survey.survey_link = payload.surveyLink
        if payload.questions is not None:
            survey.questions = [q.model_dump() for q in payload.questions]
        survey.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(survey)

        logger.info(
            "Survey updated: survey_id=%s user_id=%s",
            survey.id, current_user.id,
        )
        return SurveyResponse.model_validate(survey)

    #get all surveys
    async def get_all_surveys(
        self,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyListResponse:
        """Return all surveys owned by current_user."""
        result = await db.execute(
            select(Survey)
            .where(Survey.user_id == current_user.id)
            .order_by(Survey.created_at.desc())
        )
        surveys = result.scalars().all()

        return SurveyListResponse(
            total=len(surveys),
            surveys=[SurveyResponse.model_validate(s) for s in surveys],
        )


# Singleton
survey_service = SurveyService()
