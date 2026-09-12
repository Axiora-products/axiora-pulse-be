"""
Survey Intelligence Agent
──────────────────────────────────────────────────────────────────────────────
Generates customer validation surveys and hypothesis-testing questionnaires.
Uses survey_intelligence_skill (v2.0) to structure unbiased questions across
the 10-phase Survey Intelligence framework.
Applies 5-tier output validation via OutputValidator guardrail engine.

Skill      : survey_intelligence_skill
Score      : survey_quality_score (0–100)
Outputs    : survey_title, survey_objective, survey_context, validation_objectives,
             survey_strategy, audience_definition, sampling_strategy,
             survey_structure, question_optimization_report, multilingual_support,
             testing_report, questions, target_audience_summary,
             survey_quality_score, confidence, disclaimer
"""
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.guardrails.output_guardrails import OutputValidator
from app.llm.llm_gateway import LLMGateway, LLMRequest
from app.models.agent_models import AgentInput
from app.skills.skill_registry import skill_registry

logger = logging.getLogger(__name__)

REQUIRED_SURVEY_FIELDS = [
    "survey_title",
    "survey_objective",
    "questions",
    "confidence",
]

DEFAULT_SURVEY_OUTPUT = {
    "survey_title": "Customer Validation Survey",
    "survey_objective": "Understand target customer pain points and current workarounds.",
    "survey_context": {
        "startup_summary": "Customer validation survey for startup hypothesis testing.",
        "validation_scope": "Problem validation, pain severity, and willingness to switch.",
    },
    "validation_objectives": {
        "research_objectives": [
            "Verify existence of current workarounds and pain severity",
            "Quantify urgency and problem intensity",
        ],
        "learning_goals": ["Identify core workflow bottlenecks"],
        "research_hypotheses": [
            "Target customers experience significant daily friction using manual workarounds"
        ],
    },
    "survey_strategy": {
        "survey_type": "Customer Discovery",
        "target_completion_time_minutes": 6,
        "recommended_question_count": 10,
        "data_collection_method": "Online self-administered questionnaire",
        "required_confidence_level": "95%",
    },
    "audience_definition": {
        "icp_summary": "Prospective early adopters facing the core problem statement.",
        "demographics_or_firmographics": "Target role or prospective customer segment",
        "eligibility_rules": ["Must currently experience the targeted workflow challenge"],
        "exclusion_rules": ["Non-decision makers or non-users of relevant tools"],
    },
    "sampling_strategy": {
        "recommended_sample_size": 100,
        "sampling_method": "Purposive Sampling",
        "confidence_level": "95%",
        "margin_of_error": "5%",
        "sampling_bias_risks": ["Over-representation of highly vocal early adopters"],
    },
    "survey_structure": {
        "sections": [
            {
                "section_number": 1,
                "section_title": "Team Context & Scale",
                "questions": [
                    {
                        "question_id": "Q1",
                        "question_text": "How many people in your team or organization are affected by this workflow challenge?",
                        "question_type": "multiple_choice",
                        "options": ["Just me", "2-5 people", "6-20 people", "More than 20"],
                        "is_mandatory": True,
                        "target_hypothesis": "Identify scale and organizational impact of the problem.",
                        "skip_logic": None,
                    }
                ],
            },
            {
                "section_number": 2,
                "section_title": "Problem Frequency",
                "questions": [
                    {
                        "question_id": "Q2",
                        "question_text": "How often does this challenge occur during a typical work week?",
                        "question_type": "rating_scale",
                        "options": ["1 - Never", "2 - Rarely", "3 - Sometimes", "4 - Frequently", "5 - Daily"],
                        "is_mandatory": True,
                        "target_hypothesis": "Quantify how frequently this problem occurs.",
                        "skip_logic": None,
                    }
                ],
            },
        ]
    },
    "question_optimization_report": {
        "anti_bias_checks_passed": True,
        "improvements_made": ["Ensured questions ask about past behavior instead of future promises"],
    },
    "multilingual_support": {
        "default_language": "English",
        "supported_languages": ["English"],
        "localization_notes": "Use standard neutral wording",
    },
    "testing_report": {
        "question_logic_check": "Passed",
        "flow_check": "Logical flow confirmed",
        "estimated_completion_time_minutes": 6,
        "mobile_friendliness": "Optimized for mobile",
        "publishing_readiness": "Ready",
    },
    "target_audience_summary": "Prospective early adopters facing the core problem statement.",
    "questions": [
        {
            "question_text": "How many people in your team or organization are affected by this workflow challenge?",
            "question_type": "multiple_choice",
            "options": ["Just me", "2-5 people", "6-20 people", "More than 20"],
            "target_hypothesis": "Identify scale and organizational impact of the problem.",
        },
        {
            "question_text": "How often does this challenge occur during a typical work week?",
            "question_type": "rating_scale",
            "options": ["1 - Never", "2 - Rarely", "3 - Sometimes", "4 - Frequently", "5 - Daily"],
            "target_hypothesis": "Quantify how frequently this problem occurs.",
        },
        {
            "question_text": "How do you currently address this challenge in your daily workflow?",
            "question_type": "open_ended",
            "options": [],
            "target_hypothesis": "Verify existence of current workarounds and friction points.",
        },
        {
            "question_text": "How many hours per week does your team spend dealing with this issue?",
            "question_type": "multiple_choice",
            "options": ["Less than 1 hour", "1-3 hours", "4-7 hours", "More than 7 hours"],
            "target_hypothesis": "Quantify time cost and productivity loss of the problem.",
        },
        {
            "question_text": "Which capabilities would be most critical in a dedicated solution?",
            "question_type": "ranking",
            "options": ["Process automation", "Real-time collaboration", "Integration with current tools", "Custom reporting", "Mobile access"],
            "target_hypothesis": "Identify the highest priority features for an MVP.",
        },
        {
            "question_text": "What budget range per user/month would you consider for a dedicated solution?",
            "question_type": "multiple_choice",
            "options": ["Free only", "$1-$10", "$11-$25", "$26-$50", "$50+"],
            "target_hypothesis": "Validate pricing model and willingness to pay.",
        },
        {
            "question_text": "How likely are you to adopt a solution that fully addresses this within 3 months?",
            "question_type": "rating_scale",
            "options": ["1 - Very unlikely", "2", "3", "4", "5 - Definitely would adopt"],
            "target_hypothesis": "Measure near-term adoption intent and purchase urgency.",
        },
        {
            "question_text": "Who makes the final decision on adopting new tools in your organization?",
            "question_type": "multiple_choice",
            "options": ["Myself", "My manager", "IT/Ops team", "C-suite", "Procurement committee"],
            "target_hypothesis": "Map the buying process and identify key decision-makers.",
        },
        {
            "question_text": "What is the biggest barrier that would prevent your team from adopting a new tool?",
            "question_type": "checkbox",
            "options": ["Integration with current tools", "Budget constraints", "Data security concerns", "Team learning curve", "Vendor lock-in"],
            "target_hypothesis": "Identify key adoption hurdles and friction points.",
        },
        {
            "question_text": "What single improvement would make you switch from your current workaround to a new solution?",
            "question_type": "open_ended",
            "options": [],
            "target_hypothesis": "Identify switching triggers and primary decision criteria.",
        },
    ],
    "survey_quality_score": 75.0,
    "confidence": 0.7,
    "disclaimer": "This output provides decision-support guidance only. It does not constitute formal legal, financial, or tax advice.",
}


class SurveyIntelligenceAgent(BaseAgent):
    """
    Survey Intelligence Agent.
    Creates targeted, unbiased 10-phase customer validation surveys to test key business assumptions.
    """

    agent_name = "survey_intelligence_agent"
    skill_name = "survey_intelligence_skill"
    max_tokens = 8192

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)
        self.validator = OutputValidator()

    # ── Prompt Builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError(f"[{self.agent_name}] Skill not loaded.")

        ctx = agent_input.additional_context or {}

        target_cust = (
            agent_input.target_customer
            or ctx.get("target_customer")
            or "Prospective target customer base"
        )
        val_goal = (
            agent_input.founder_validation_goal
            or ctx.get("validation_goal")
            or "Validate core problem statement and willingness to switch"
        )
        problem_stmt = (
            agent_input.problem_statement
            or ctx.get("problem_statement")
            or "Unclear problem statement"
        )

        problem_val = ctx.get("problem_validation") or ctx.get("idea_validation_output") or "Not provided"
        founder_inf = ctx.get("founder_info") or ctx.get("founder_evidence") or "Not provided"
        market_res = ctx.get("market_research") or ctx.get("market_research_output") or "Not provided"
        customer_intel = ctx.get("customer_intelligence") or ctx.get("customer_personas") or "Not provided"
        biz_assumptions = ctx.get("business_assumptions") or ctx.get("key_assumptions") or "Not provided"

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=problem_stmt,
            target_customer=target_cust,
            validation_goal=val_goal,
            problem_validation=str(problem_val),
            founder_info=str(founder_inf),
            market_research=str(market_res),
            customer_intelligence=str(customer_intel),
            business_assumptions=str(biz_assumptions),
        )

    # ── Output Parser & Validation Pipeline ─────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Runs full 5-tier output validation:
        1. JSON syntax check
        2. Required fields presence check
        3. Score & range bounds check
        4. Disclaimer enforcement
        5. Forbidden advice detection
        """
        # Log raw response size to help diagnose truncation
        logger.info(f"[{self.agent_name}] Raw LLM response length: {len(raw_content)} chars")

        val_result = self.validator.validate_all(
            raw_content=raw_content,
            required_fields=REQUIRED_SURVEY_FIELDS,
            range_specs={
                "survey_quality_score": (0.0, 100.0),
                "confidence": (0.0, 1.0),
            },
            default_values=DEFAULT_SURVEY_OUTPUT,
        )

        if not val_result.is_valid:
            logger.warning(
                f"[{self.agent_name}] Validation failed with errors: {val_result.errors}. "
                f"Raw content tail (last 300 chars): ...{raw_content[-300:]}"
            )

        data = val_result.data

        # Normalize score alias
        if "survey_quality_score" not in data or data["survey_quality_score"] is None:
            data["survey_quality_score"] = float(data.get("score", 70.0))

        # Ensure survey_structure is a valid dict or populate default
        if "survey_structure" not in data or not isinstance(data.get("survey_structure"), dict):
            data["survey_structure"] = DEFAULT_SURVEY_OUTPUT["survey_structure"]

        # Robust questions field extraction (primary: top-level, fallback: survey_structure.sections)
        raw_qs = data.get("questions")
        if not isinstance(raw_qs, list) or not raw_qs:
            extracted_qs = []
            survey_struct = data.get("survey_structure")
            if (
                isinstance(survey_struct, dict)
                and survey_struct != DEFAULT_SURVEY_OUTPUT["survey_structure"]
                and "sections" in survey_struct
            ):
                for sec in survey_struct.get("sections", []):
                    if isinstance(sec, dict) and "questions" in sec:
                        for q in sec.get("questions", []):
                            if isinstance(q, dict) and "question_text" in q:
                                extracted_qs.append(q)
            if extracted_qs:
                logger.info(f"[{self.agent_name}] Recovered {len(extracted_qs)} questions from survey_structure.sections.")
                raw_qs = extracted_qs
            else:
                logger.warning(f"[{self.agent_name}] ⚠ No AI questions found — applying static DEFAULT fallback. Check token limits or LLM errors.")
                raw_qs = list(DEFAULT_SURVEY_OUTPUT["questions"])
        else:
            logger.info(f"[{self.agent_name}] Extracted {len(raw_qs)} candidate questions from LLM output.")

        # Deduplicate questions (exact string match + token overlap + hypothesis redundancy)
        deduped_qs = self._deduplicate_questions(raw_qs)
        if not deduped_qs:
            logger.warning(f"[{self.agent_name}] Deduplication left 0 questions — applying DEFAULT_SURVEY_OUTPUT questions.")
            deduped_qs = list(DEFAULT_SURVEY_OUTPUT["questions"])

        data["questions"] = deduped_qs
        logger.info(f"[{self.agent_name}] ✓ Final clean question count: {len(deduped_qs)}.")

        if val_result.warnings:
            logger.info(f"[{self.agent_name}] Validation warnings: {val_result.warnings}")

        return data

    # ── Question Deduplication Engine ──────────────────────────────────────────

    @staticmethod
    def _normalize_question_text(text: str) -> str:
        """Normalize question string for comparison."""
        if not text:
            return ""
        cleaned = re.sub(r"[^\w\s]", " ", str(text).lower())
        return " ".join(cleaned.split())

    @classmethod
    def _question_tokens(cls, text: str) -> set[str]:
        """Extract significant word stems/tokens excluding common grammatical words."""
        stopwords = {
            "the", "and", "for", "that", "this", "with", "you", "your", "are", "have",
            "has", "what", "how", "which", "when", "where", "who", "why", "does", "did",
            "would", "could", "will", "from", "been", "being", "most", "more", "like",
            "any", "all", "our", "their", "into", "onto", "about", "such", "than", "select",
            "apply", "currently", "past", "month", "months", "year", "years", "today"
        }
        words = cls._normalize_question_text(text).split()
        tokens = set()
        for w in words:
            if len(w) > 2 and w not in stopwords:
                for suffix in ("ing", "ed", "ers", "er", "es", "s"):
                    if len(w) > len(suffix) + 3 and w.endswith(suffix):
                        w = w[:-len(suffix)]
                        break
                tokens.add(w)
        return tokens

    @classmethod
    def _is_duplicate_question(
        cls,
        candidate_q: dict[str, Any],
        accepted_questions: list[dict[str, Any]],
    ) -> bool:
        """
        Evaluates whether candidate_q is an exact duplicate or near-duplicate
        of any question already accepted.
        """
        c_text = candidate_q.get("question_text") or candidate_q.get("question") or ""
        norm_c = cls._normalize_question_text(c_text)
        if not norm_c:
            return True

        c_tokens = cls._question_tokens(c_text)
        c_hyp = cls._normalize_question_text(candidate_q.get("target_hypothesis", ""))
        c_hyp_tokens = cls._question_tokens(c_hyp)

        for accepted in accepted_questions:
            a_text = accepted.get("question_text") or accepted.get("question") or ""
            norm_a = cls._normalize_question_text(a_text)

            # 1. Exact normalized match
            if norm_c == norm_a:
                return True

            # 2. Token Jaccard similarity >= 0.70
            a_tokens = cls._question_tokens(a_text)
            if c_tokens and a_tokens:
                intersection = len(c_tokens & a_tokens)
                union = len(c_tokens | a_tokens)
                jaccard = intersection / union if union > 0 else 0.0
                if jaccard >= 0.70:
                    return True

                # 3. Moderate token overlap (>= 0.45) with high target hypothesis overlap (>= 0.50)
                if jaccard >= 0.45 and c_hyp_tokens:
                    a_hyp = cls._normalize_question_text(accepted.get("target_hypothesis", ""))
                    a_hyp_tokens = cls._question_tokens(a_hyp)
                    hyp_intersect = len(c_hyp_tokens & a_hyp_tokens)
                    hyp_union = len(c_hyp_tokens | a_hyp_tokens)
                    hyp_jaccard = hyp_intersect / hyp_union if hyp_union > 0 else 0.0
                    if hyp_jaccard >= 0.50:
                        return True

        return False

    def _deduplicate_questions(self, raw_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Deduplicates a list of question dicts, preserving the order of distinct items.
        """
        if not isinstance(raw_questions, list):
            return []

        accepted: list[dict[str, Any]] = []
        dropped_count = 0

        for q in raw_questions:
            if not isinstance(q, dict):
                continue
            if self._is_duplicate_question(q, accepted):
                dropped_count += 1
                q_text = q.get("question_text") or q.get("question") or ""
                logger.info(f"[{self.agent_name}] Deduplication dropped redundant question: '{q_text}'")
            else:
                accepted.append(dict(q))

        if dropped_count > 0:
            logger.info(
                f"[{self.agent_name}] Deduplication removed {dropped_count} redundant question(s). "
                f"Clean questions remaining: {len(accepted)}"
            )

        return accepted

    # ── Score Extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        """Extract survey_quality_score (0–100)."""
        score_val = parsed_output.get("survey_quality_score")
        if score_val is None:
            score_val = parsed_output.get("score", 70.0)
        try:
            return float(score_val)
        except (ValueError, TypeError):
            return 70.0

    # ── Post-Link Intelligence (SI.11–SI.44) ──────────────────────────────────

    async def run_post_link_analysis(
        self,
        survey_id: str,
        survey_title: str,
        survey_objective: str,
        questions: list[dict[str, Any]],
        responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Executes post-survey-link response intelligence analysis (SI.11–SI.44)
        using collected survey responses. Evaluates fraud risk, response quality,
        bias, customer intelligence, customer validation, and GTM handoff.
        """
        import json
        logger.info(
            f"[{self.agent_name}] ▶ Running post-link response intelligence analysis "
            f"for survey_id={survey_id} ({len(responses)} responses)"
        )

        post_skill = skill_registry.get("survey_intelligence_post_surveylink_skill")
        if not post_skill:
            raise ValueError(f"[{self.agent_name}] Post-link skill 'survey_intelligence_post_surveylink_skill' not found.")

        def _json_converter(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        prompt = post_skill.build_prompt(
            survey_id=str(survey_id),
            survey_title=survey_title or "Customer Validation Survey",
            survey_objective=survey_objective or "Validate problem statement and customer demand",
            response_count=len(responses),
            questions_json=json.dumps(questions, indent=2, default=_json_converter),
            responses_json=json.dumps(responses, indent=2, default=_json_converter),
        )

        llm_request = LLMRequest(
            system_prompt=(
                f"You are the {self.agent_name}, executing post-survey-link response intelligence "
                f"and customer validation framework (SI.11-SI.44)."
            ),
            user_prompt=prompt,
            response_format="json",
            temperature=0.2,
            max_tokens=self.max_tokens,
        )

        llm_response = await self.llm.complete(llm_request)
        if not llm_response.success:
            logger.error(f"[{self.agent_name}] LLM call failed for post-link analysis: {llm_response.error}")
            return {"error": llm_response.error or "LLM call failed for post-link analysis."}

        try:
            raw_parsed = json.loads(llm_response.content)
            if isinstance(raw_parsed, dict):
                return raw_parsed
            return {"error": "Parsed output is not a JSON object", "raw": llm_response.content}
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to parse post-link LLM json output: {e}")
            return {"error": f"JSON parse error: {e}", "raw": llm_response.content}


