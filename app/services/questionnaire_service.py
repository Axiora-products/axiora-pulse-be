import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InteractiveQuestionnaire, User, UserInteractiveQuestionnaire
from app.models.questionnaire_models import (
    DeleteQuestionResponse,
    InteractiveQuestionnaireResponse,
    SubmitAnswersRequestItem,
    SubmitAnswersResponse,
    SubmitQuestionRequest,
)

logger = logging.getLogger(__name__)


class QuestionnaireService:
    async def list_questions(self, db: AsyncSession) -> list[InteractiveQuestionnaireResponse]:
        """Retrieve all questionnaire questions ordered by id ascending."""
        result = await db.execute(
            select(InteractiveQuestionnaire).order_by(InteractiveQuestionnaire.id.asc())
        )
        questions = result.scalars().all()
        return [InteractiveQuestionnaireResponse.model_validate(question) for question in questions]

    async def submit_answers(
        self,
        payload: list[SubmitAnswersRequestItem],
        current_user: User,
        db: AsyncSession,
    ) -> SubmitAnswersResponse:
        """Persist user questionnaire answers inside a transactional block."""
        if not payload:
            logger.warning("Questionnaire submission rejected for user_id=%s: empty payload", current_user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one questionnaire answer item is required.",
            )

        questionnaire_ids = [item.questionnaire_id for item in payload]
        result = await db.execute(
            select(InteractiveQuestionnaire).where(InteractiveQuestionnaire.id.in_(questionnaire_ids))
        )
        existing_questions = {question.id: question for question in result.scalars().all()}

        if len(existing_questions) != len(questionnaire_ids):
            missing_ids = sorted(set(questionnaire_ids) - set(existing_questions))
            logger.warning(
                "Questionnaire submission failed for user_id=%s: missing questionnaire ids %s",
                current_user.id,
                missing_ids,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Questionnaire(s) not found: {missing_ids}",
            )

        for item in payload:
            question = existing_questions[item.questionnaire_id]
            if not question.optional and not any(
                isinstance(answer, str) and answer.strip() for answer in item.user_answers
            ):
                logger.warning(
                    "Questionnaire submission failed for user_id=%s: mandatory question %s missing answer",
                    current_user.id,
                    item.questionnaire_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Questionnaire {item.questionnaire_id} requires at least one non-empty answer.",
                )

        try:
            async with db.begin():
                for item in payload:
                    response = UserInteractiveQuestionnaire(
                        user_id=current_user.id,
                        questionnaire_id=item.questionnaire_id,
                        user_answers=list(item.user_answers),
                        submission_date=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(response)
        except Exception:
            logger.exception(
                "Database transaction failed while saving questionnaire answers for user_id=%s",
                current_user.id,
            )
            await db.rollback()
            raise

        logger.info(
            "Questionnaire answers submitted: user_id=%s count=%s",
            current_user.id,
            len(payload),
        )
        return SubmitAnswersResponse(message="Questionnaire answers submitted successfully.")

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
