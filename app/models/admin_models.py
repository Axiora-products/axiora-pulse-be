"""Request and response schemas for the administrator API."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


QuestionType = Literal["text", "radio", "dropdown", "multi_select"]


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: Literal["user", "admin"]
    is_active: bool
    workspace_count: int = 0


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    pagination: PaginationMeta


class UpdateAdminUserRequest(BaseModel):
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def requires_change(self):
        if self.role is None and self.is_active is None:
            raise ValueError("Provide role and/or is_active.")
        return self


class AdminWorkspaceResponse(BaseModel):
    id: int
    user_id: int
    username: str
    name: str
    description: str | None = None
    state: str
    created_at: datetime
    updated_at: datetime


class AdminWorkspaceListResponse(BaseModel):
    workspaces: list[AdminWorkspaceResponse]
    pagination: PaginationMeta


class AdminWorkspaceDetailResponse(AdminWorkspaceResponse):
    idea: dict[str, Any] = Field(default_factory=dict)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    validation_result: dict[str, Any] | None = None


class DashboardMetricsResponse(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    total_workspaces: int
    workspaces_last_7_days: int
    validation_completed: int
    recent_workspaces: list[AdminWorkspaceResponse]


class InteractiveQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    question_type: QuestionType
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = True
    is_active: bool = True
    sort_order: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_options(self):
        selectable = {"radio", "dropdown", "multi_select"}
        if self.question_type in selectable and not self.options:
            raise ValueError("Selectable question types require at least one option.")
        if self.question_type == "text" and self.options:
            raise ValueError("Text questions cannot include options.")
        if any(not option.strip() for option in self.options):
            raise ValueError("Options cannot be blank.")
        if len({option.strip().lower() for option in self.options}) != len(self.options):
            raise ValueError("Options must be unique.")
        return self


class UpdateInteractiveQuestionRequest(InteractiveQuestionRequest):
    pass


class InteractiveQuestionResponse(BaseModel):
    id: int
    questionId: int
    question: str
    question_type: QuestionType
    options: list[str]
    required: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class InteractiveQuestionListResponse(BaseModel):
    questions: list[InteractiveQuestionResponse]
    pagination: PaginationMeta


class AuditEventResponse(BaseModel):
    id: int
    actor_user_id: int
    actor_username: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    events: list[AuditEventResponse]
    pagination: PaginationMeta
