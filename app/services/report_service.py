"""
Template-first report generator for Axiora Pulse.

The service always renders into the branded PDF template. It does not build or
append legacy report layouts.
"""
from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import fitz

logger = logging.getLogger(__name__)


REPORT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "report_template.pdf"
WATERMARK_RECT = fitz.Rect(228.0, 375.2, 383.9, 416.8)
SYSTEM_FONT_DIR = Path(os.getenv("WINDIR", "C:\\Windows")) / "Fonts"
BANNER_FONT_REGULAR = Path(os.getenv("AXIORA_REPORT_BANNER_FONT_REGULAR", SYSTEM_FONT_DIR / "GOTHIC.TTF"))
BANNER_FONT_BOLD = Path(os.getenv("AXIORA_REPORT_BANNER_FONT_BOLD", SYSTEM_FONT_DIR / "GOTHICB.TTF"))
BANNER_VENTURE_FONT_REGULAR = Path(
    os.getenv("AXIORA_REPORT_BANNER_VENTURE_FONT_REGULAR", SYSTEM_FONT_DIR / "calibri.ttf")
)
BANNER_VENTURE_FONT_BOLD = Path(
    os.getenv("AXIORA_REPORT_BANNER_VENTURE_FONT_BOLD", SYSTEM_FONT_DIR / "calibrib.ttf")
)


class ReportService:
    """Transforms agent validation results into the single branded PDF format."""

    def generate_report(
        self,
        agent_name: str,
        validation_result: Dict[str, Any],
        idea_info: Optional[Dict[str, Any]] = None,
        export_format: str = "pdf",
    ) -> Tuple[bytes, str, str]:
        """
        Generate a report from the PDF template.

        `export_format` is accepted for API compatibility, but PDF is the only
        supported output format.
        """
        agent_key = agent_name.lower().strip()
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        idea_title = (idea_info or {}).get("idea_title") or (idea_info or {}).get("name") or "Startup Idea"
        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "", str(idea_title)) or "Startup"

        # Log only which agent/format was requested — never the validation
        # content itself (that's the customer's proprietary report output).
        logger.info("Generating %s report for agent=%s", export_format, agent_key)
        try:
            pdf_bytes = self._build_template_pdf(agent_key, validation_result, idea_info or {})
        except Exception:
            logger.exception("Report generation failed for agent=%s", agent_key)
            raise
        filename = f"{safe_title}_{agent_key}_report_{date_str}.pdf"
        logger.info("Report generated for agent=%s: %s bytes", agent_key, len(pdf_bytes))
        return pdf_bytes, "application/pdf", filename

    def _build_template_pdf(
        self,
        agent_key: str,
        validation_result: Dict[str, Any],
        idea_info: Dict[str, Any],
    ) -> bytes:
        template_path = self._resolve_template_path()
        template = fitz.open(template_path)
        output = fitz.open()

        report_title = self._report_title(agent_key)
        venture = str(idea_info.get("idea_title") or idea_info.get("name") or "Startup Venture")
        blocks = self._content_blocks(agent_key, validation_result)

        current_page_number = 0
        page = self._append_template_page(output, template, current_page_number)
        self._draw_cover_header(page, report_title, venture)
        cursor_y = 150

        for block in blocks:
            html_block = self._block_html(block)
            min_height = block.get("min_height", 34)
            if cursor_y + min_height > 742:
                current_page_number += 1
                page = self._append_template_page(output, template, current_page_number)
                cursor_y = 44

            cursor_y = self._insert_flowing_html(
                output=output,
                template=template,
                page=page,
                html_block=html_block,
                cursor_y=cursor_y,
                current_page_number_ref=[current_page_number],
            )
            current_page_number = output.page_count - 1
            page = output[current_page_number]

        pdf_bytes = output.tobytes(deflate=True, garbage=4)
        output.close()
        template.close()
        return pdf_bytes

    def _resolve_template_path(self) -> Path:
        configured_path = os.getenv("AXIORA_REPORT_TEMPLATE_PATH")
        template_path = Path(configured_path) if configured_path else REPORT_TEMPLATE_PATH
        if not template_path.exists():
            logger.error("Report template not found at %s", template_path)
            raise FileNotFoundError(
                f"Report template not found at {template_path}. "
                "Set AXIORA_REPORT_TEMPLATE_PATH or include app/templates/report_template.pdf."
            )
        return template_path

    def _append_template_page(self, output: fitz.Document, template: fitz.Document, page_number: int) -> fitz.Page:
        source_index = min(page_number, template.page_count - 1)
        output.insert_pdf(template, from_page=source_index, to_page=source_index)
        page = output[-1]
        top = 132 if page_number == 0 else 32
        content_rect = fitz.Rect(36, top, 576, 742)
        page.draw_rect(content_rect, color=None, fill=(1, 1, 1), fill_opacity=0.62, overlay=True)

        # Extra fade layer over the watermark logo so it sits further into the
        # background instead of competing with body text.
        watermark_hole = WATERMARK_RECT & content_rect
        if not watermark_hole.is_empty:
            page.draw_rect(watermark_hole, color=None, fill=(1, 1, 1), fill_opacity=0.4, overlay=True)
        return page

    def _draw_cover_header(self, page: fitz.Page, report_title: str, venture: str) -> None:
        title_bold_font = self._font_file(BANNER_FONT_BOLD)
        title_bold_name = "BannerTitleFontBold" if title_bold_font else "Helvetica-Bold"
        venture_regular_font = self._font_file(BANNER_VENTURE_FONT_REGULAR)
        venture_bold_font = self._font_file(BANNER_VENTURE_FONT_BOLD)
        venture_regular_name = "BannerVentureFontRegular" if venture_regular_font else "Helvetica"
        venture_bold_name = "BannerVentureFontBold" if venture_bold_font else "Helvetica-Bold"

        page.insert_text(
            fitz.Point(48, 78),
            report_title,
            fontname=title_bold_name,
            fontfile=title_bold_font,
            fontsize=31,
            color=(1, 1, 1),
        )
        venture_label = "Idea Title : "
        venture_label_point = fitz.Point(48, 111)
        page.insert_text(
            venture_label_point,
            venture_label,
            fontname=venture_regular_name,
            fontfile=venture_regular_font,
            fontsize=12,
            color=(1, 1, 1),
        )
        label_width = self._text_length(venture_label, fontfile=venture_regular_font, fontsize=12)
        page.insert_text(
            fitz.Point(venture_label_point.x + label_width + 2, venture_label_point.y),
            venture,
            fontname=venture_bold_name,
            fontfile=venture_bold_font,
            fontsize=12,
            color=(1, 1, 1),
        )

    def _insert_flowing_html(
        self,
        output: fitz.Document,
        template: fitz.Document,
        page: fitz.Page,
        html_block: str,
        cursor_y: float,
        current_page_number_ref: list[int],
    ) -> float:
        while True:
            rect = fitz.Rect(36, cursor_y, 576, 742)
            spare_height, scale = page.insert_htmlbox(
                rect,
                html_block,
                css=self._css(),
                scale_low=1,
            )
            if spare_height >= 0:
                used_height = max(10, rect.height - spare_height)
                return cursor_y + used_height + 8

            current_page_number_ref[0] += 1
            page = self._append_template_page(output, template, current_page_number_ref[0])
            cursor_y = 44

    def _content_blocks(self, agent_key: str, validation_result: Dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        agent_results = validation_result.get("agent_results") or {}

        if agent_key in ("idea_validation_agent", "full", "all"):
            blocks.extend(self._idea_validation_blocks(validation_result, agent_results))

        if agent_key in ("market_research_agent", "full", "all"):
            blocks.extend(self._market_research_blocks(agent_results))

        if agent_key in ("survey_intelligence_agent", "full", "all"):
            blocks.extend(self._survey_blocks(agent_results))

        if not blocks:
            blocks.append(
                {
                    "type": "section",
                    "title": "Validation Report",
                    "body": "No report content was returned by the selected agent.",
                    "min_height": 90,
                }
            )
        return blocks

    def _idea_validation_blocks(
        self, validation_result: Dict[str, Any], agent_results: Dict[str, Any]
    ) -> list[dict[str, Any]]:
        iv = (agent_results.get("idea_validation_agent") or {}).get("data") or {}
        score = validation_result.get("validation_score", iv.get("validation_score", iv.get("problem_clarity_score", "N/A")))
        verdict = str(iv.get("verdict") or validation_result.get("verdict", "N/A")).replace("_", " ").upper()
        confidence = self._percent(iv.get("confidence") or validation_result.get("confidence_rating", 0.5))

        sections = iv.get("sections") if isinstance(iv.get("sections"), dict) else {}
        prob_id = sections.get("problem_identification") or {}
        idea_clarity = sections.get("idea_clarity") or {}
        cust_prob = sections.get("customer_problem") or {}
        target_aud = sections.get("target_audience_hypothesis") or {}
        sol_def = sections.get("solution_definition") or {}
        val_prop = sections.get("value_proposition") or {}
        feas = sections.get("idea_feasibility") or {}
        comp = sections.get("initial_competitor_check") or {}
        val_surv = sections.get("validation_survey_interviews") or {}
        decision = sections.get("decision") or {}

        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "title": "Problem & Idea Validation",
                "metrics": [
                    ("Validation Score", f"{score}/100"),
                    ("Verdict", verdict),
                    ("Confidence", f"{confidence}%"),
                ],
                "min_height": 96,
            }
        ]

        # ── 1. Problem Identification ──────────────────────────────────────────
        falsifiable_stmt = (
            prob_id.get("falsifiable_problem_sentence")
            or iv.get("falsifiable_problem_sentence")
            or iv.get("problem_statement")
        )
        if falsifiable_stmt:
            blocks.append(
                {
                    "type": "inline",
                    "label": "Falsifiable Problem Statement",
                    "body": falsifiable_stmt,
                    "accent": True,
                    "min_height": 52,
                }
            )

        problem_summary = (
            prob_id.get("impact_scope")
            or iv.get("problem_statement_summary")
        )
        if problem_summary and problem_summary != falsifiable_stmt:
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Problem Scope & Impact:",
                    "body": problem_summary,
                    "min_height": 80,
                }
            )

        if prob_id.get("root_cause"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Root Cause Analysis:",
                    "body": prob_id["root_cause"],
                    "min_height": 72,
                }
            )

        # ── 2. Idea Clarity ───────────────────────────────────────────────────
        if idea_clarity.get("assessment"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Concept Clarity Assessment:",
                    "body": idea_clarity["assessment"],
                    "min_height": 72,
                }
            )

        # ── 3. Customer Problem Profile ───────────────────────────────────────
        pain_profile_parts = []
        if cust_prob.get("pain_type"):
            pain_profile_parts.append(f"Pain Type: {cust_prob['pain_type']}")
        if cust_prob.get("severity"):
            pain_profile_parts.append(f"Severity: {cust_prob['severity']}")
        if cust_prob.get("frequency"):
            pain_profile_parts.append(f"Frequency: {cust_prob['frequency']}")

        if pain_profile_parts:
            blocks.append(
                {
                    "type": "inline",
                    "label": "Pain Characteristics",
                    "body": " | ".join(pain_profile_parts),
                    "accent": False,
                    "min_height": 46,
                }
            )

        if cust_prob.get("cost_of_inaction"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Cost of Inaction:",
                    "body": cust_prob["cost_of_inaction"],
                    "min_height": 72,
                }
            )

        workarounds = (
            cust_prob.get("current_workarounds")
            or iv.get("current_workarounds")
        )
        if workarounds:
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Current Workarounds & Substitutes:",
                    "body": workarounds,
                    "min_height": 72,
                }
            )

        # ── 4. Target Audience Hypothesis ──────────────────────────────────────
        icp = (
            target_aud.get("icp")
            or iv.get("who_and_frequency")
        )
        if icp:
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Target Beachhead ICP:",
                    "body": icp,
                    "min_height": 72,
                }
            )

        if target_aud.get("user_persona"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Primary User Persona:",
                    "body": target_aud["user_persona"],
                    "min_height": 64,
                }
            )

        if target_aud.get("buyer_persona"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Economic Buyer Persona:",
                    "body": target_aud["buyer_persona"],
                    "min_height": 64,
                }
            )

        if target_aud.get("early_adopter_profile"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Early Adopter Profile:",
                    "body": target_aud["early_adopter_profile"],
                    "min_height": 64,
                }
            )

        # ── 5. Solution Definition ────────────────────────────────────────────
        if sol_def.get("core_mechanism"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Solution Core Mechanism:",
                    "body": sol_def["core_mechanism"],
                    "min_height": 72,
                }
            )

        if sol_def.get("problem_solution_fit"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Problem-Solution Fit:",
                    "body": sol_def["problem_solution_fit"],
                    "min_height": 64,
                }
            )

        if sol_def.get("mvp_scope"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Lean MVP Test Scope:",
                    "body": sol_def["mvp_scope"],
                    "min_height": 72,
                }
            )

        # ── 6. Value Proposition ──────────────────────────────────────────────
        if val_prop.get("uvp"):
            blocks.append(
                {
                    "type": "inline",
                    "label": "Unique Value Proposition",
                    "body": val_prop["uvp"],
                    "accent": False,
                    "min_height": 48,
                }
            )

        if val_prop.get("why_choose_this"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Why Choose This Solution:",
                    "body": val_prop["why_choose_this"],
                    "min_height": 68,
                }
            )

        # ── 7. Feasibility ────────────────────────────────────────────────────
        feas_parts = []
        if feas.get("technical_feasibility"):
            feas_parts.append(f"Technical: {feas['technical_feasibility']}")
        if feas.get("operational_feasibility"):
            feas_parts.append(f"Operational: {feas['operational_feasibility']}")

        if feas_parts:
            blocks.append(
                {
                    "type": "inline",
                    "label": "Feasibility Profile",
                    "body": " | ".join(feas_parts),
                    "accent": False,
                    "min_height": 46,
                }
            )

        if feas.get("resource_requirements"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Initial Resource & Capital Requirements:",
                    "body": feas["resource_requirements"],
                    "min_height": 72,
                }
            )

        # ── 8. Initial Competitor Check ───────────────────────────────────────
        if comp.get("key_differentiator"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Key Differentiator & Strategic Wedge:",
                    "body": comp["key_differentiator"],
                    "min_height": 68,
                }
            )

        # ── 9. Decision & Objective Review ────────────────────────────────────
        if decision.get("objective_review_summary"):
            blocks.append(
                {
                    "type": "paragraph",
                    "title": "Objective Review Summary:",
                    "body": decision["objective_review_summary"],
                    "min_height": 80,
                }
            )

        # ── 10. Lists & Actionable Next Steps ──────────────────────────────────
        blocks.extend(
            [
                *self._list_blocks("Quantifiable Benefits", val_prop.get("quantifiable_benefits")),
                *self._list_blocks("Direct Competitors", comp.get("direct_competitors")),
                *self._list_blocks("Indirect & Substitute Competitors", comp.get("indirect_competitors")),
                *self._list_blocks("Discovery Interview Questions", val_surv.get("interview_questions")),
                *self._list_blocks("Key Survey Metrics to Test", val_surv.get("survey_metrics_to_test")),
                *self._list_blocks(
                    "Key Falsifiable Assumptions",
                    val_surv.get("riskiest_assumptions")
                    or iv.get("assumption_list")
                    or validation_result.get("assumptions"),
                ),
                *self._list_blocks("Verdict Rationale", decision.get("rationale")),
                *self._list_blocks(
                    "7-Day Validation Action Plan",
                    decision.get("next_7_day_actions") or validation_result.get("recommendations"),
                ),
                *self._list_blocks("Strengths", validation_result.get("strengths")),
                *self._list_blocks("Risks & Concerns", validation_result.get("risks")),
                *self._list_blocks("Red Flags", iv.get("red_flags") or idea_clarity.get("red_flags")),
            ]
        )
        return [block for block in blocks if block]

    def _market_research_blocks(self, agent_results: Dict[str, Any]) -> list[dict[str, Any]]:
        mr = (agent_results.get("market_research_agent") or {}).get("data") or {}
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "title": "Target Customer & Market Research",
                "metrics": [
                    ("Market Score", f"{mr.get('market_opportunity_score', 'N/A')}/100"),
                    ("Audience Narrowness", f"{mr.get('audience_narrowness_score', 'N/A')}/100"),
                    ("Confidence", f"{self._percent(mr.get('confidence', 0.5))}%"),
                ],
                "min_height": 96,
            },
            self._paragraph_block("Market Opportunity Summary:", mr.get("market_opportunity_summary")),
            self._paragraph_block("Primary Ideal Customer Profile (ICP):", mr.get("primary_icp_summary")),
            self._paragraph_block("Buyer Persona:", mr.get("persona_summary")),
            *self._list_blocks("Target Customer Segments", mr.get("target_customer_segments")),
            *self._list_blocks("Secondary Segments", mr.get("secondary_segments")),
            *self._list_blocks("Competitor Overview", mr.get("competitor_overview")),
            *self._list_blocks("Opportunity Signals", mr.get("opportunity_signals")),
            *self._list_blocks("Market Risks", mr.get("risk_signals")),
            *self._list_blocks("Audience Red Flags", mr.get("red_flags")),
        ]
        return [block for block in blocks if block]

    def _survey_blocks(self, agent_results: Dict[str, Any]) -> list[dict[str, Any]]:
        survey = (agent_results.get("survey_intelligence_agent") or {}).get("data") or {}
        questions = survey.get("questions") or []
        question_lines = []
        for index, question in enumerate(questions, start=1):
            if isinstance(question, dict):
                text = question.get("question_text") or question.get("question") or ""
            else:
                text = str(question)
            if text:
                question_lines.append(f"{index}. {text}")

        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "title": "Survey Intelligence",
                "body": survey.get("survey_objective") or survey.get("summary") or "",
                "min_height": 80,
            },
            *self._list_blocks("Hypothesis Questionnaire", question_lines),
        ]
        return [block for block in blocks if block]

    def _paragraph_block(self, title: str, body: Any) -> Optional[dict[str, Any]]:
        if not body:
            return None
        return {"type": "paragraph", "title": title, "body": body, "min_height": 72}

    def _list_blocks(self, title: str, items: Any) -> list[dict[str, Any]]:
        normalized = [str(item) for item in self._as_list(items) if str(item).strip()]
        if not normalized:
            return []
        blocks = [{"type": "list_heading", "title": title, "min_height": 32}]
        blocks.extend({"type": "list_item", "body": item, "min_height": 28} for item in normalized)
        return blocks

    def _block_html(self, block: dict[str, Any]) -> str:
        block_type = block.get("type")
        if block_type == "section":
            metrics_html = ""
            if block.get("metrics"):
                metrics_html = "<table class='metrics'><tr>" + "".join(
                    f"<td class='metric metric-{index}'><b>{self._e(label)}:</b> {self._e(value)}</td>"
                    for index, (label, value) in enumerate(block["metrics"])
                ) + "</tr></table>"
            body_html = f"<p class='body-text'>{self._e(block.get('body'))}</p>" if block.get("body") else ""
            return f"<h1>{self._e(block.get('title'))}</h1>{metrics_html}{body_html}"

        if block_type == "paragraph":
            return f"<p class='label'>{self._e(block.get('title'))}</p><p class='body-text'>{self._e(block.get('body'))}</p>"

        if block_type == "inline":
            body_class = "accent" if block.get("accent") else ""
            return (
                f"<p class='callout'><b>{self._e(block.get('label'))}:</b> "
                f"<span class='{body_class}'>{self._e(block.get('body'))}</span></p>"
            )

        if block_type == "list":
            items = "".join(f"<li>{self._bold_label(item)}</li>" for item in block.get("items", []))
            return f"<h2>{self._e(block.get('title'))}</h2><ul>{items}</ul>"

        if block_type == "list_heading":
            return f"<h2>{self._e(block.get('title'))}</h2>"

        if block_type == "list_item":
            return f"<ul class='single'><li>{self._bold_label(block.get('body', ''))}</li></ul>"

        return f"<p>{self._e(block.get('body'))}</p>"

    def _css(self) -> str:
        return """
            body {
                font-family: Arial, Helvetica, sans-serif;
                color: #222222;
                font-size: 11.5px;
                line-height: 1.5;
            }
            h1 {
                font-family: Arial, Helvetica, sans-serif;
                font-size: 15.5px;
                margin: 0 0 18px 0;
                font-weight: 700;
                color: #111111;
            }
            h2 {
                font-family: Arial, Helvetica, sans-serif;
                font-size: 14.5px;
                margin: 10px 0 8px 0;
                font-weight: 700;
                color: #111111;
            }
            p {
                font-size: 11.5px;
                line-height: 1.5;
                margin: 0 0 8px 0;
                text-align: left;
            }
            .body-text {
                font-size: 11.5px;
                line-height: 1.5;
                text-align: left;
            }
            .label {
                font-size: 11.5px;
                line-height: 1.5;
                font-weight: 700;
                margin-bottom: 6px;
                text-align: left;
            }
            .callout {
                font-size: 11.5px;
                line-height: 1.5;
                text-align: left;
            }
            table.metrics {
                border-collapse: collapse;
                table-layout: fixed;
                font-family: Arial, Helvetica, sans-serif;
                font-size: 11.5px;
                line-height: 1.5;
                margin: 0 0 18px 0;
                width: 100%;
                text-align: left;
            }
            table.metrics td {
                padding: 0 12px 0 0;
                text-align: left;
                vertical-align: baseline;
                white-space: nowrap;
                overflow: hidden;
            }
            table.metrics td.metric-0 {
                width: 34%;
            }
            table.metrics td.metric-1 {
                width: 34%;
            }
            table.metrics td.metric-2 {
                width: 32%;
            }
            ul {
                font-size: 11.5px;
                line-height: 1.5;
                margin: 0 0 10px 16px;
                padding: 0;
            }
            li {
                font-size: 11.5px;
                line-height: 1.5;
                margin: 0 0 5px 0;
                padding-left: 2px;
                text-align: left;
            }
            ul.single {
                margin: 0 0 1px 16px;
                padding: 0;
            }
            ul.single li {
                font-size: 11.5px;
                line-height: 1.3;
                margin: 0 0 1px 0;
                padding-left: 2px;
                text-align: left;
            }
            .accent {
                color: #FF4500;
                font-weight: 700;
            }
            b {
                font-weight: 700;
            }
        """

    def _font_file(self, path: Path) -> Optional[str]:
        return str(path) if path.exists() else None

    def _text_length(self, text: str, fontfile: Optional[str], fontsize: float) -> float:
        if fontfile:
            return fitz.Font(fontfile=fontfile).text_length(text, fontsize=fontsize)
        return fitz.get_text_length(text, fontname="Helvetica", fontsize=fontsize)

    def _report_title(self, agent_key: str) -> str:
        return {
            "idea_validation_agent": "Idea Validation Report",
            "market_research_agent": "Market Research Report",
            "survey_intelligence_agent": "Survey Intelligence Report",
            "full": "Startup Validation Report",
            "all": "Startup Validation Report",
        }.get(agent_key, "Startup Validation Report")

    def _as_list(self, value: Any) -> Iterable[Any]:
        if not value:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _bold_label(self, value: str) -> str:
        escaped = self._e(value)
        if ":" not in escaped:
            return escaped
        label, rest = escaped.split(":", 1)
        if len(label) > 80:
            return escaped
        return f"<b>{label}:</b>{rest}"

    def _e(self, value: Any) -> str:
        return html.escape("" if value is None else str(value))

    def _percent(self, val: Any) -> int:
        try:
            f = float(val)
            return round(f * 100) if f <= 1.0 else round(f)
        except (ValueError, TypeError):
            return 50


report_service = ReportService()
