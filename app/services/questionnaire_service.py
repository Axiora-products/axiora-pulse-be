import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InteractiveQuestionnaire, User
from app.models.questionnaire_models import (
    DeleteQuestionResponse,
    InteractiveQuestionnaireResponse,
    SubmitQuestionRequest,
)

logger = logging.getLogger(__name__)


class QuestionnaireService:
    async def create_question(
        self,
        payload: SubmitQuestionRequest,
        current_user: User,
        db: AsyncSession,
    ) -> InteractiveQuestionnaireResponse:
        """Persist a new interactive questionnaire question for admins."""
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required.",
            )

        now = datetime.now(timezone.utc)
        questionnaire = InteractiveQuestionnaire(
            question=payload.question.strip(),
            answer_type=payload.answer_type,
            optional=payload.optional,
            answers=list(payload.answers),
            created_at=now,
            updated_at=now,
        )

        db.add(questionnaire)
        await db.flush()
        await db.refresh(questionnaire)

        logger.info(
            "Questionnaire question created: id=%s by admin_user_id=%s",
            questionnaire.id,
            current_user.id,
        )
        return InteractiveQuestionnaireResponse.model_validate(questionnaire)

    async def delete_question(
        self,
        question_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> DeleteQuestionResponse:
        """Delete an interactive questionnaire question for admins."""
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required.",
            )

        questionnaire = await db.get(InteractiveQuestionnaire, question_id)
        if questionnaire is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Questionnaire question not found.",
            )

        await db.delete(questionnaire)
        await db.commit()

        logger.info(
            "Questionnaire question deleted: id=%s by admin_user_id=%s",
            question_id,
            current_user.id,
        )
        return DeleteQuestionResponse(message="Questionnaire question deleted successfully.")


questionnaire_service = QuestionnaireService()
