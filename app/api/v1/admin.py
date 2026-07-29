from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.questionnaire_models import (
    DeleteQuestionResponse,
    InteractiveQuestionnaireResponse,
    SubmitQuestionRequest,
)
from app.services.questionnaire_service import questionnaire_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post(
    "/questionnaire/submit-question",
    response_model=InteractiveQuestionnaireResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new questionnaire question",
    description="Allows administrators to create a new interactive questionnaire question item.",
)
async def submit_question(
    request: Request,
    payload: SubmitQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InteractiveQuestionnaireResponse:
    return await questionnaire_service.create_question(payload, current_user, db)


@router.delete(
    "/questionnaire/delete-question/{question_id}",
    response_model=DeleteQuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a questionnaire question",
    description="Allows administrators to delete an interactive questionnaire question item.",
)
async def delete_question(
    question_id: int = Path(..., ge=1, description="ID of the questionnaire question to delete"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteQuestionResponse:
    return await questionnaire_service.delete_question(question_id, current_user, db)
