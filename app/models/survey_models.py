"""
app/models/survey_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for Survey endpoints.

Endpoints covered:
  POST /api/v1/surveys                → SaveAllSurveyQuestionsRequest → SurveyResponse
  GET  /api/v1/surveys                → SurveyListResponse
  PUT  /api/v1/surveys/{survey_id}    → UpdateSurveyRequest → SurveyResponse
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ── Request Models ─────────────────────────────────────────────────────────────

class SurveyQuestionItem(BaseModel):
    """A single survey question."""
    id: int = Field(..., description="Question identifier, unique within the survey")
    question: str = Field(..., min_length=1, description="Question text")
    questionType: Literal["text", "radio", "checkbox", "dropdown"] = Field(
        ..., description="Question input style"
    )
    options: List[str] = Field(default_factory=list, description="Answer options (for radio/checkbox/dropdown)")


class SaveAllSurveyQuestionsRequest(BaseModel):
    """Payload for POST /api/v1/surveys/saveAllSurveyQuestions."""
    userId: int = Field(..., ge=1, description="Owner user ID")
    workspaceId: int = Field(..., ge=1, description="Workspace ID the survey belongs to")
    questions: List[SurveyQuestionItem] = Field(
        ..., description="Full list of survey questions — replaces any existing set for this workspace"
    )


class UpdateSurveyRequest(BaseModel):
    """Payload for PUT /api/v1/surveys/{survey_id}."""
    userId: int = Field(..., ge=1, description="Owner user ID")
    surveyLink: Optional[str] = Field(None, max_length=2048, description="Updated survey link")
    questions: Optional[List[SurveyQuestionItem]] = Field(
        None, description="If provided, replaces the full question set for this survey"
    )

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UpdateSurveyRequest":
        if self.surveyLink is None and self.questions is None:
            raise ValueError("At least one of surveyLink or questions must be provided.")
        return self


# ── Response Models ────────────────────────────────────────────────────────────

class SurveyResponse(BaseModel):
    """Returned for a single survey."""
    id: int
    user_id: int
    workspace_id: int
    survey_link: Optional[str] = None
    questions: List[SurveyQuestionItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SurveyListResponse(BaseModel):
    """Returned for a list of surveys."""
    total: int
    surveys: List[SurveyResponse]
