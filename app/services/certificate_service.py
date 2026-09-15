"""Certificate generator for Axiora Pulse idea validation."""
from __future__ import annotations

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_CERTIFICATE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "idea_validation_certificate_template.pdf"
)
_ALEX_BRUSH_FONT_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "fonts" / "AlexBrush-Regular.ttf"
)

_INK = (0.075, 0.025, 0.16)
_BLACK = (0, 0, 0)
_NAME_FONT_SIZE = 48
_NAME_MIN_FONT_SIZE = 30
_NAME_MAX_WIDTH_RATIO = 0.52
_TEXT_FONT_SIZE = 8


class CertificateService:
    """Generates personalised idea validation certificates."""

    def generate_certificate(
        self,
        display_name: str,
        *,
        certificate_id: str | None = None,
        issue_date: str | None = None,
    ) -> bytes:
        """
        Open the certificate template, draw dynamic fields as vector text, and
        return the full-page landscape PDF bytes.
        """
        fontfile = str(_ALEX_BRUSH_FONT_PATH) if _ALEX_BRUSH_FONT_PATH.exists() else None
        if fontfile is None:
            logger.error("Alex Brush font not found at %s", _ALEX_BRUSH_FONT_PATH)
            raise FileNotFoundError(f"Certificate font missing: {_ALEX_BRUSH_FONT_PATH}")

        doc = fitz.open(str(_CERTIFICATE_TEMPLATE_PATH))
        try:
            page = doc[0]
            rect = page.rect

            font_obj = fitz.Font(fontfile=fontfile)
            font_size = self._fit_font_size(
                font_obj,
                display_name,
                _NAME_FONT_SIZE,
                rect.width * _NAME_MAX_WIDTH_RATIO,
            )
            text_width = font_obj.text_length(display_name, fontsize=font_size)
            if page.rotation:
                x = rect.width * 0.354
                y = (rect.width + text_width) / 2 + 3
                text_rotation = page.rotation
            else:
                x = (rect.width - text_width) / 2
                y = rect.height * 0.485
                text_rotation = 0

            page.insert_text(
                fitz.Point(x, y),
                display_name,
                fontname="AlexBrush",
                fontfile=fontfile,
                fontsize=font_size,
                color=_INK,
                rotate=text_rotation,
            )

            if certificate_id:
                page.insert_text(
                    fitz.Point(
                        rect.width * 0.622,
                        rect.width * 0.867,
                    ),
                    certificate_id,
                    fontsize=_TEXT_FONT_SIZE,
                    color=_BLACK,
                    rotate=page.rotation,
                )

            if issue_date:
                page.insert_text(
                    fitz.Point(
                        rect.width * 0.638,
                        rect.width * 0.867,
                    ),
                    issue_date,
                    fontsize=_TEXT_FONT_SIZE,
                    color=_BLACK,
                    rotate=page.rotation,
                )

            output_bytes = doc.tobytes(deflate=True, garbage=4)
        finally:
            doc.close()

        logger.info(
            "Certificate generated for '%s' as %s: %d bytes",
            display_name,
            "pdf",
            len(output_bytes),
        )
        return output_bytes

    def _fit_font_size(
        self,
        font_obj: fitz.Font,
        text: str,
        preferred_size: int,
        max_width: float,
    ) -> int:
        font_size = preferred_size
        while font_size > _NAME_MIN_FONT_SIZE:
            if font_obj.text_length(text, fontsize=font_size) <= max_width:
                return font_size
            font_size -= 1
        return _NAME_MIN_FONT_SIZE


certificate_service = CertificateService()
