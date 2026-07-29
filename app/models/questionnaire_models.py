from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SubmitQuestionRequest(BaseModel):
    """Payload for POST /api/v1/admin/questionnaire/submit-question."""

    question: str = Field(..., min_length=1, description="Question text")
    answer_type: Literal["textarea", "radiobuttons", "checkboxes", "dropdown"] = Field(
        ..., description="Question answer input style"
    )
    optional: bool = Field(default=False, description="Whether the question is optional")
    answers: list[str] = Field(default_factory=list, description="Answer options for choice-based questions")

    @model_validator(mode="after")
    def validate_answers_for_choice_types(self) -> "SubmitQuestionRequest":
        if self.answer_type in {"radiobuttons", "checkboxes", "dropdown"} and len(self.answers) < 2:
            raise ValueError("Choice-based questions require at least 2 answers.")
        return self


class InteractiveQuestionnaireResponse(BaseModel):
    """Response returned after a questionnaire question is created."""

    id: int
    question: str
    answer_type: str
    optional: bool
    answers: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeleteQuestionResponse(BaseModel):
    """Response returned after a questionnaire question is deleted."""

    message: str
