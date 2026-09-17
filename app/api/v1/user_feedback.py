import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin
from app.db.database import get_db
from app.db.models import User
from app.models.feedback_questionnaire_models import (
    AdminUserFeedbackListResponse,
    UserFeedbackSubmitRequest,
)
from app.services.feedback_questionnaire_service import feedback_questionnaire_service

router = APIRouter(prefix="/user-feedback", tags=["User Feedback"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    summary="Submit user feedback",
    description="Saves the feedback answers (one-time submission) and automatically triggers the workspace certificate export, returning the generated PDF.",
    status_code=status.HTTP_200_OK,
)
async def submit_user_feedback(
    payload: UserFeedbackSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(
        "Submitting feedback for user_id=%s workspace_id=%s with %s item(s)",
        current_user.id,
        payload.workspace_id,
        len(payload.answers),
    )
    return await feedback_questionnaire_service.submit_feedback(payload, current_user, db)


@router.get(
    "",
    response_model=AdminUserFeedbackListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all user feedback submissions",
    description="Returns all submitted feedback questions and answers for the administrator directory. Supports filtering by user, text search, submission date range, and pagination.",
)
async def list_user_feedback(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=255, description="Search by question text or submitted answers"),
    user_id: int | None = Query(None, ge=1, description="Restrict results to feedback submitted by this user"),
    date_from: datetime | None = Query(None, description="Only include submissions on or after this date"),
    date_to: datetime | None = Query(None, description="Only include submissions on or before this date"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserFeedbackListResponse:
    logger.info(
        "Listing user feedback: user_id=%s search=%r limit=%s offset=%s",
        user_id,
        search,
        limit,
        offset,
    )
    return await feedback_questionnaire_service.list_user_feedback(
        db, limit, offset, search, user_id, date_from, date_to
    )