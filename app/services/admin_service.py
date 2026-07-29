"""Database-backed operations for the administrator API."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, InteractiveQuestionnaire, User, Workspace
from app.models.admin_models import (
    AdminUserListResponse, AdminUserResponse, AdminWorkspaceDetailResponse,
    AdminWorkspaceListResponse, AdminWorkspaceResponse, AuditEventListResponse,
    AuditEventResponse, DashboardMetricsResponse, InteractiveQuestionListResponse,
    InteractiveQuestionRequest, InteractiveQuestionResponse, PaginationMeta,
    UpdateAdminUserRequest,
)


class AdminService:
    async def _audit(self, db: AsyncSession, actor: User, action: str, target_type: str,
                     target_id: str | None, metadata: dict, ip_address: str | None) -> None:
        db.add(AuditEvent(actor_user_id=actor.id, action=action, target_type=target_type,
                          target_id=target_id, metadata_=metadata, ip_address=ip_address))
        await db.flush()

    @staticmethod
    def _page(total: int, limit: int, offset: int) -> PaginationMeta:
        return PaginationMeta(total=total, limit=limit, offset=offset)

    @staticmethod
    def _workspace_response(workspace: Workspace, username: str) -> AdminWorkspaceResponse:
        return AdminWorkspaceResponse(id=workspace.id, user_id=workspace.user_id, username=username,
            name=workspace.name, description=workspace.description, state=workspace.state,
            created_at=workspace.created_at, updated_at=workspace.updated_at)

    @staticmethod
    def _question_response(question: InteractiveQuestionnaire) -> InteractiveQuestionResponse:
        question_types = {"textarea": "text", "radiobuttons": "radio", "dropdown": "dropdown", "checkboxes": "multi_select"}
        return InteractiveQuestionResponse(id=question.id, questionId=question.id,
            question=question.question, question_type=question_types[question.answer_type],
            options=question.answers or [], required=not question.optional, is_active=question.is_active,
            sort_order=question.sort_order, created_at=question.created_at, updated_at=question.updated_at)

    async def dashboard(self, db: AsyncSession) -> DashboardMetricsResponse:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
        active_users = (await db.execute(select(func.count(User.id)).where(User.is_active.is_(True)))).scalar_one()
        admin_users = (await db.execute(select(func.count(User.id)).where(User.role == "admin"))).scalar_one()
        total_workspaces = (await db.execute(select(func.count(Workspace.id)))).scalar_one()
        recent_count = (await db.execute(select(func.count(Workspace.id)).where(Workspace.created_at >= since))).scalar_one()
        completed = (await db.execute(select(func.count(Workspace.id)).where(Workspace.validation_result.is_not(None)))).scalar_one()
        rows = await db.execute(select(Workspace, User.username).join(User, Workspace.user_id == User.id)
                                .order_by(Workspace.updated_at.desc()).limit(10))
        return DashboardMetricsResponse(total_users=total_users, active_users=active_users,
            admin_users=admin_users, total_workspaces=total_workspaces,
            workspaces_last_7_days=recent_count, validation_completed=completed,
            recent_workspaces=[self._workspace_response(w, name) for w, name in rows.all()])

    async def list_users(self, db: AsyncSession, limit: int, offset: int, search: str | None) -> AdminUserListResponse:
        statement = select(User)
        count_statement = select(func.count(User.id))
        if search:
            criterion = User.username.ilike(f"%{search.strip()}%")
            statement, count_statement = statement.where(criterion), count_statement.where(criterion)
        total = (await db.execute(count_statement)).scalar_one()
        users = (await db.execute(statement.order_by(User.id.desc()).offset(offset).limit(limit))).scalars().all()
        counts = dict((await db.execute(select(Workspace.user_id, func.count(Workspace.id)).group_by(Workspace.user_id))).all())
        return AdminUserListResponse(users=[AdminUserResponse(id=user.id, username=user.username,
            role=user.role, is_active=user.is_active, workspace_count=counts.get(user.id, 0)) for user in users],
            pagination=self._page(total, limit, offset))

    async def get_user(self, user_id: int, db: AsyncSession) -> AdminUserResponse:
        user = await self._user_or_404(user_id, db)
        workspace_count = (await db.execute(select(func.count(Workspace.id)).where(Workspace.user_id == user.id))).scalar_one()
        return AdminUserResponse(id=user.id, username=user.username, role=user.role,
            is_active=user.is_active, workspace_count=workspace_count)

    async def update_user(self, user_id: int, payload: UpdateAdminUserRequest, actor: User,
                          db: AsyncSession, ip_address: str | None) -> AdminUserResponse:
        user = await self._user_or_404(user_id, db)
        changes: dict[str, object] = {}
        if payload.role is not None and payload.role != user.role:
            if user.id == actor.id and payload.role != "admin":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role.")
            if user.role == "admin" and payload.role != "admin":
                await self._ensure_another_active_admin(user.id, db)
            changes["role"] = {"from": user.role, "to": payload.role}
            user.role = payload.role
        if payload.is_active is not None and payload.is_active != user.is_active:
            if user.id == actor.id and not payload.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend your own account.")
            if user.role == "admin" and not payload.is_active:
                await self._ensure_another_active_admin(user.id, db)
            changes["is_active"] = {"from": user.is_active, "to": payload.is_active}
            user.is_active = payload.is_active
        if not changes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The requested state is already applied.")
        await self._audit(db, actor, "user.updated", "user", str(user.id), changes, ip_address)
        return await self.get_user(user.id, db)

    async def list_workspaces(self, db: AsyncSession, limit: int, offset: int, user_id: int | None,
                              search: str | None) -> AdminWorkspaceListResponse:
        statement = select(Workspace, User.username).join(User, Workspace.user_id == User.id)
        count_statement = select(func.count(Workspace.id))
        filters = []
        if user_id is not None:
            filters.append(Workspace.user_id == user_id)
        if search:
            filters.append(or_(Workspace.name.ilike(f"%{search.strip()}%"), User.username.ilike(f"%{search.strip()}%")))
        if filters:
            statement, count_statement = statement.where(*filters), count_statement.join(User, Workspace.user_id == User.id).where(*filters)
        total = (await db.execute(count_statement)).scalar_one()
        rows = await db.execute(statement.order_by(Workspace.updated_at.desc()).offset(offset).limit(limit))
        return AdminWorkspaceListResponse(workspaces=[self._workspace_response(w, name) for w, name in rows.all()],
            pagination=self._page(total, limit, offset))

    async def get_workspace(self, workspace_id: int, actor: User, db: AsyncSession,
                            ip_address: str | None) -> AdminWorkspaceDetailResponse:
        row = (await db.execute(select(Workspace, User.username).join(User, Workspace.user_id == User.id)
                                .where(Workspace.id == workspace_id))).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        workspace, username = row
        await self._audit(db, actor, "workspace.viewed", "workspace", str(workspace.id), {}, ip_address)
        base = self._workspace_response(workspace, username)
        return AdminWorkspaceDetailResponse(**base.model_dump(), idea=workspace.idea or {},
            conversation_history=workspace.conversation_history or [], validation_result=workspace.validation_result)

    async def list_questions(self, db: AsyncSession, limit: int, offset: int) -> InteractiveQuestionListResponse:
        total = (await db.execute(select(func.count(InteractiveQuestionnaire.id)))).scalar_one()
        questions = (await db.execute(select(InteractiveQuestionnaire).order_by(InteractiveQuestionnaire.sort_order, InteractiveQuestionnaire.id)
                                      .offset(offset).limit(limit))).scalars().all()
        return InteractiveQuestionListResponse(questions=[self._question_response(q) for q in questions],
            pagination=self._page(total, limit, offset))

    async def create_question(self, payload: InteractiveQuestionRequest, actor: User, db: AsyncSession,
                              ip_address: str | None) -> InteractiveQuestionResponse:
        values = payload.model_dump(exclude_none=True)
        values["question"] = payload.question.strip()
        values["options"] = [item.strip() for item in payload.options]
        values["answer_type"] = {"text": "textarea", "radio": "radiobuttons", "dropdown": "dropdown", "multi_select": "checkboxes"}.get(values.pop("question_type"))
        values["answers"] = values.pop("options")
        values["optional"] = not values.pop("required")
        question = InteractiveQuestionnaire(**values)
        db.add(question)
        await db.flush()
        await db.refresh(question)
        await self._audit(db, actor, "interactive_question.created", "interactive_question", str(question.id),
                          {"question_type": payload.question_type}, ip_address)
        return self._question_response(question)

    async def update_question(self, question_id: int, payload: InteractiveQuestionRequest, actor: User,
                              db: AsyncSession, ip_address: str | None) -> InteractiveQuestionResponse:
        question = await self._question_or_404(question_id, db)
        before = {"answer_type": question.answer_type, "is_active": question.is_active, "sort_order": question.sort_order}
        values = payload.model_dump()
        question.question = values["question"].strip()
        question.answer_type = {"text": "textarea", "radio": "radiobuttons", "dropdown": "dropdown", "multi_select": "checkboxes"}[values["question_type"]]
        question.answers = [item.strip() for item in values["options"]]
        question.optional = not values["required"]
        question.is_active = values["is_active"]
        question.sort_order = values["sort_order"]
        question.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(question)
        await self._audit(db, actor, "interactive_question.updated", "interactive_question", str(question.id),
                          {"before": before}, ip_address)
        return self._question_response(question)

    async def delete_question(self, question_id: int, actor: User, db: AsyncSession, ip_address: str | None) -> None:
        question = await self._question_or_404(question_id, db)
        await self._audit(db, actor, "interactive_question.deleted", "interactive_question", str(question.id),
                          {"question": question.question}, ip_address)
        await db.delete(question)

    async def list_audit_events(self, db: AsyncSession, limit: int, offset: int, action: str | None) -> AuditEventListResponse:
        statement = select(AuditEvent, User.username).outerjoin(User, AuditEvent.actor_user_id == User.id)
        count_statement = select(func.count(AuditEvent.id))
        if action:
            statement, count_statement = statement.where(AuditEvent.action == action), count_statement.where(AuditEvent.action == action)
        total = (await db.execute(count_statement)).scalar_one()
        rows = await db.execute(statement.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit))
        return AuditEventListResponse(events=[AuditEventResponse(id=event.id, actor_user_id=event.actor_user_id,
            actor_username=username, action=event.action, target_type=event.target_type, target_id=event.target_id,
            metadata=event.metadata_ or {}, ip_address=event.ip_address, created_at=event.created_at) for event, username in rows.all()],
            pagination=self._page(total, limit, offset))

    async def _user_or_404(self, user_id: int, db: AsyncSession) -> User:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return user

    async def _question_or_404(self, question_id: int, db: AsyncSession) -> InteractiveQuestionnaire:
        question = (await db.execute(select(InteractiveQuestionnaire).where(InteractiveQuestionnaire.id == question_id))).scalar_one_or_none()
        if question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interactive question not found.")
        return question

    async def _ensure_another_active_admin(self, excluded_user_id: int, db: AsyncSession) -> None:
        count = (await db.execute(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True), User.id != excluded_user_id))).scalar_one()
        if count == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin must remain.")


admin_service = AdminService()
