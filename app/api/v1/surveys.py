"""


Routes:
  POST /api/v1/surveys                → save_all_survey_questions
  GET  /api/v1/surveys                → get_all_surveys
  PUT  /api/v1/surveys/{survey_id}    → update_survey
"""
import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.survey_models import (
    SaveAllSurveyQuestionsRequest,
    SurveyListResponse,
    SurveyResponse,
    UpdateSurveyRequest,
)
from app.services.survey_service import survey_service

router = APIRouter(prefix="/surveys", tags=["Surveys"])
logger = logging.getLogger(__name__)


#save all survey questions

@router.post(
    "",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Save all survey questions for a workspace",
    description="Creates or replaces the full set of survey questions for the given user's workspace.",
)
@limiter.limit("20/minute")
async def save_all_survey_questions(
    request: Request,
    payload: SaveAllSurveyQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    logger.info(
        "Saving survey questions: user_id=%s workspace_id=%s question_count=%s",
        payload.userId, payload.workspaceId, len(payload.questions),
    )
    return await survey_service.save_all_questions(payload, current_user, db)


# Get All Surveys

@router.get(
    "",
    response_model=SurveyListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all surveys for the current user",
    description="Returns all surveys owned by the authenticated user.",
)
@limiter.limit("60/minute")
async def get_all_surveys(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyListResponse:
    return await survey_service.get_all_surveys(current_user, db)


# ── Update Survey

@router.put(
    "/{survey_id}",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a survey by ID",
    description="Updates the survey link and/or question set for an existing survey owned by the authenticated user.",
)
@limiter.limit("20/minute")
async def update_survey(
    request: Request,
    survey_id: int,
    payload: UpdateSurveyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    logger.info(
        "Updating survey: survey_id=%s user_id=%s",
        survey_id, payload.userId,
    )
    return await survey_service.update_survey(survey_id, payload, current_user, db)
