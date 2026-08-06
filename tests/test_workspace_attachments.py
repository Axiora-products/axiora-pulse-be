"""
backend/tests/test_workspace_attachments.py
────────────────────────────────────────────────────────────────────────────────
Unit / integration tests for workspace attachment upload, listing, get, and delete.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.models.workspace_models import AttachmentInput
from app.services.workspace_attachment_service import _detect_file_type


def test_detect_file_type():
    assert _detect_file_type("document.pdf", "application/pdf") == "pdf"
    assert _detect_file_type("image.png", "image/png") == "image"
    assert _detect_file_type("photo.jpg", "image/jpeg") == "image"
    assert _detect_file_type("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "doc"
    assert _detect_file_type("notes.txt", "text/plain") == "doc"
    assert _detect_file_type("custom_file.bin", "application/octet-stream") == "doc"
