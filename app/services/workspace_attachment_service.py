"""
app/services/workspace_attachment_service.py
────────────────────────────────────────────────────────────────────────────────
Workspace Attachment Service — handles file uploads, listing, retrieval, and
deletion of user-uploaded files scoped to a workspace.

Files are stored in the axiora-assets S3 bucket under:
  Assets/users/{user_id}/workspaces/{workspace_id}/{type_folder}/{uuid}_{filename}

Supported file types:
  - image   → images/  (JPEG, JPG, PNG, WEBP, GIF)
  - pdf     → pdfs/    (application/pdf)
  - doc     → docs/    (DOCX, TXT, MD, and other documents)
"""
import logging
from typing import List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workspace, WorkspaceAttachment
from app.models.workspace_models import (
    DeleteAttachmentResponse,
    WorkspaceAttachmentListResponse,
    WorkspaceAttachmentResponse,
)
from app.services.s3_storage_service import s3_storage_service

logger = logging.getLogger(__name__)

# ── MIME type → file_type mapping ────────────────────────────────────────────
MIME_TO_FILE_TYPE: dict[str, str] = {
    # Images
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    "image/bmp": "image",
    "image/svg+xml": "image",
    # PDFs
    "application/pdf": "pdf",
    # Documents
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "doc",  # .docx
    "application/msword": "doc",                   # .doc
    "text/plain": "doc",                           # .txt
    "text/markdown": "doc",                        # .md
    "application/rtf": "doc",                      # .rtf
    "text/csv": "doc",                             # .csv
}

EXTENSION_TO_FILE_TYPE: dict[str, str] = {
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".webp": "image", ".gif": "image", ".bmp": "image",
    ".pdf": "pdf",
    ".docx": "doc", ".doc": "doc", ".txt": "doc",
    ".md": "doc", ".rtf": "doc", ".csv": "doc",
}


def _detect_file_type(filename: str, content_type: str) -> str:
    """Determine file_type ('image' | 'pdf' | 'doc') from MIME or extension."""
    if content_type and content_type.lower() in MIME_TO_FILE_TYPE:
        return MIME_TO_FILE_TYPE[content_type.lower()]
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in EXTENSION_TO_FILE_TYPE:
        return EXTENSION_TO_FILE_TYPE[ext]
    return "doc"  # safe default


class WorkspaceAttachmentService:
    """Stateless service — all state lives in the DB session."""

    # ── Upload ────────────────────────────────────────────────────────────────

    async def upload_file(
        self,
        workspace_id: int,
        current_user: User,
        file: UploadFile,
        db: AsyncSession,
    ) -> WorkspaceAttachmentResponse:
        """
        Read a multipart uploaded file, push it to S3 (axiora-assets bucket),
        and persist a WorkspaceAttachment record in the database.
        """
        # Verify workspace ownership
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        file_bytes = await file.read()
        filename = file.filename or "upload"
        content_type = file.content_type or "application/octet-stream"
        file_type = _detect_file_type(filename, content_type)
        file_size = len(file_bytes)

        # Upload to axiora-assets bucket
        file_url, s3_key = s3_storage_service.upload_workspace_asset(
            file_bytes=file_bytes,
            filename=filename,
            user_id=current_user.id,
            workspace_id=workspace.id,
            file_type=file_type,
            content_type=content_type,
        )

        # Persist record
        attachment = WorkspaceAttachment(
            user_id=current_user.id,
            workspace_id=workspace.id,
            file_name=filename,
            file_type=file_type,
            mime_type=content_type,
            s3_key=s3_key,
            file_url=file_url,
            file_size_bytes=file_size,
        )
        db.add(attachment)
        await db.flush()
        await db.refresh(attachment)

        logger.info(
            "[WorkspaceAttachmentService] Uploaded %s (%s) to workspace %s for user %s → %s",
            filename, file_type, workspace_id, current_user.id, file_url
        )
        return WorkspaceAttachmentResponse.model_validate(attachment)

    # ── Save from base64 (used by chat sync) ─────────────────────────────────

    async def save_from_base64(
        self,
        workspace_id: int,
        user_id: int,
        filename: str,
        base64_data: str,
        mime_type: str,
        db: AsyncSession,
    ) -> Optional[WorkspaceAttachmentResponse]:
        """
        Decode a base64 attachment (sent inline in chat) and save it to the
        workspace_attachments table. Used for chat attachment sync.

        Returns None silently on any error so chat is not blocked.
        """
        try:
            import base64 as b64lib

            raw = base64_data.split(",", 1)[-1] if "," in base64_data else base64_data
            file_bytes = b64lib.b64decode(raw)
            file_type = _detect_file_type(filename, mime_type)

            file_url, s3_key = s3_storage_service.upload_workspace_asset(
                file_bytes=file_bytes,
                filename=filename,
                user_id=user_id,
                workspace_id=workspace_id,
                file_type=file_type,
                content_type=mime_type or "application/octet-stream",
            )

            attachment = WorkspaceAttachment(
                user_id=user_id,
                workspace_id=workspace_id,
                file_name=filename,
                file_type=file_type,
                mime_type=mime_type or "application/octet-stream",
                s3_key=s3_key,
                file_url=file_url,
                file_size_bytes=len(file_bytes),
            )
            db.add(attachment)
            await db.flush()
            await db.refresh(attachment)

            logger.info(
                "[WorkspaceAttachmentService] Synced chat attachment %s to workspace %s for user %s",
                filename, workspace_id, user_id
            )
            return WorkspaceAttachmentResponse.model_validate(attachment)

        except Exception as e:
            logger.warning(
                "[WorkspaceAttachmentService] Failed to sync chat attachment %s: %s",
                filename, e
            )
            return None

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_attachments(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
        file_type: Optional[str] = None,
    ) -> WorkspaceAttachmentListResponse:
        """List all attachments for a workspace (optionally filter by file_type)."""
        await self._fetch_owned_workspace(workspace_id, current_user, db)

        query = (
            select(WorkspaceAttachment)
            .where(
                WorkspaceAttachment.workspace_id == workspace_id,
                WorkspaceAttachment.user_id == current_user.id,
            )
            .order_by(WorkspaceAttachment.created_at.desc())
        )
        if file_type:
            query = query.where(WorkspaceAttachment.file_type == file_type)

        result = await db.execute(query)
        attachments = result.scalars().all()

        return WorkspaceAttachmentListResponse(
            total=len(attachments),
            attachments=[WorkspaceAttachmentResponse.model_validate(a) for a in attachments],
        )

    # ── Get Single ────────────────────────────────────────────────────────────

    async def get_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceAttachmentResponse:
        """Fetch a single attachment record."""
        attachment = await self._fetch_owned_attachment(
            workspace_id, attachment_id, current_user, db
        )
        return WorkspaceAttachmentResponse.model_validate(attachment)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> DeleteAttachmentResponse:
        """Delete a workspace attachment from S3 and the database."""
        attachment = await self._fetch_owned_attachment(
            workspace_id, attachment_id, current_user, db
        )

        # Remove from S3 (best-effort — don't block if S3 delete fails)
        s3_storage_service.delete_workspace_asset(attachment.s3_key)

        # Remove DB record
        await db.delete(attachment)
        await db.flush()

        logger.info(
            "[WorkspaceAttachmentService] Deleted attachment %s (workspace %s, user %s)",
            attachment_id, workspace_id, current_user.id
        )
        return DeleteAttachmentResponse(
            attachment_id=attachment_id,
            workspace_id=workspace_id,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _fetch_owned_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> Workspace:
        """Fetch and ownership-check a workspace; raises 404/403 as appropriate."""
        result = await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.is_delete == False,  # noqa: E712
            )
        )
        workspace = result.scalar_one_or_none()

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found.",
            )
        if workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this workspace.",
            )
        return workspace

    async def _fetch_owned_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceAttachment:
        """Fetch and ownership-check a single attachment; raises 404/403 as appropriate."""
        result = await db.execute(
            select(WorkspaceAttachment).where(
                WorkspaceAttachment.id == attachment_id,
                WorkspaceAttachment.workspace_id == workspace_id,
            )
        )
        attachment = result.scalar_one_or_none()

        if attachment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attachment {attachment_id} not found in workspace {workspace_id}.",
            )
        if attachment.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this attachment.",
            )
        return attachment


# ── Singleton ─────────────────────────────────────────────────────────────────
workspace_attachment_service = WorkspaceAttachmentService()
