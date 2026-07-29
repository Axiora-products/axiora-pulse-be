"""Administrator-only API routes."""
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.admin_models import (
    AdminUserListResponse, AdminUserResponse, AdminWorkspaceDetailResponse,
    AdminWorkspaceListResponse, AuditEventListResponse, DashboardMetricsResponse,
    InteractiveQuestionListResponse, InteractiveQuestionRequest, InteractiveQuestionResponse,
    UpdateAdminUserRequest,
)
from app.services.admin_service import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/dashboard", response_model=DashboardMetricsResponse)
@limiter.limit("60/minute")
async def dashboard(request: Request, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.dashboard(db)


@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("60/minute")
async def list_users(request: Request, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                     search: str | None = Query(None, max_length=255), _: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    return await admin_service.list_users(db, limit, offset, search)


@router.get("/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit("60/minute")
async def get_user(request: Request, user_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.get_user(user_id, db)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit("20/minute")
async def update_user(request: Request, user_id: int, payload: UpdateAdminUserRequest,
                      current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.update_user(user_id, payload, current_user, db, _client_ip(request))


@router.get("/workspaces", response_model=AdminWorkspaceListResponse)
@limiter.limit("60/minute")
async def list_workspaces(request: Request, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                          user_id: int | None = None, search: str | None = Query(None, max_length=255),
                          _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.list_workspaces(db, limit, offset, user_id, search)


@router.get("/workspaces/{workspace_id}", response_model=AdminWorkspaceDetailResponse)
@limiter.limit("60/minute")
async def get_workspace(request: Request, workspace_id: int, current_user: User = Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    return await admin_service.get_workspace(workspace_id, current_user, db, _client_ip(request))


@router.get("/interactive-questions", response_model=InteractiveQuestionListResponse)
@limiter.limit("60/minute")
async def list_questions(request: Request, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                         _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.list_questions(db, limit, offset)


@router.post("/interactive-questions", response_model=InteractiveQuestionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_question(request: Request, payload: InteractiveQuestionRequest, current_user: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    return await admin_service.create_question(payload, current_user, db, _client_ip(request))


@router.put("/interactive-questions/{question_id}", response_model=InteractiveQuestionResponse)
@limiter.limit("20/minute")
async def update_question(request: Request, question_id: int, payload: InteractiveQuestionRequest,
                          current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.update_question(question_id, payload, current_user, db, _client_ip(request))


@router.delete("/interactive-questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_question(request: Request, question_id: int, current_user: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)) -> Response:
    await admin_service.delete_question(question_id, current_user, db, _client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-events", response_model=AuditEventListResponse)
@limiter.limit("60/minute")
async def list_audit_events(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                            action: str | None = Query(None, max_length=100), _: User = Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    return await admin_service.list_audit_events(db, limit, offset, action)
