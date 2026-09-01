"""
Idea Validation Agent — Analysis 1 (Problem Analysis & Arya 10-Section Framework)
──────────────────────────────────────────────────────────────────────────────
Evaluates whether a founder's idea is anchored in a real, evidenced, and
sufficiently painful problem, and produces a 10-section analytical validation report
using the 15-parameter framework and Objective Review protocol.

Skill      : idea_validation_skill
Score      : validation_score / problem_clarity_score (0–100)
Outputs    : validated_idea, problem_statement, validation_score, confidence,
             verdict, sections (10 analytical blocks), and legacy flat aliases.
"""
import json
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logger = logging.getLogger(__name__)

# Valid recommendation / verdict values
VALID_RECOMMENDATIONS = {
    "proceed_to_validation",
    "needs_clarification",
    "reduce_scope",
    "pivot",
    "hold",
}

VERDICT_MAP = {
    "build": "proceed_to_validation",
    "proceed_to_validation": "proceed_to_validation",
    "go": "proceed_to_validation",
    "validate_more": "needs_clarification",
    "validate more": "needs_clarification",
    "needs_clarification": "needs_clarification",
    "reduce_scope": "reduce_scope",
    "reduce scope": "reduce_scope",
    "pivot": "pivot",
    "hold": "hold",
    "hold / wait": "hold",
}

VALID_PAIN_TYPES = {
    "painkiller": "Painkiller",
    "vitamin": "Vitamin",
    "unclear": "Unclear",
}


class IdeaValidationAgent(BaseAgent):
    """
    First agent in the Phase 1 pipeline (Analysis 1: Idea Validation & Objective Review).
    Uses the idea_validation_skill to score and analyse the founder's idea across 10 sections.
    """
    agent_name = "idea_validation_agent"
    skill_name = "idea_validation_skill"

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError("Skill not loaded for IdeaValidationAgent")

        evidence = (
            agent_input.founder_evidence
            or agent_input.additional_context.get("founder_evidence")
            or "No explicit evidence provided beyond founder assertion."
        )
        goal = (
            agent_input.founder_validation_goal
            or agent_input.additional_context.get("founder_validation_goal")
            or "validate my idea"
        )
        geography = (
            agent_input.geography
            or agent_input.additional_context.get("geography")
            or "global"
        )
        target_customer = (
            agent_input.target_customer
            or agent_input.additional_context.get("target_customer")
            or "Not specified — needs target customer definition."
        )
        business_type = (
            agent_input.business_type
            or agent_input.additional_context.get("business_type")
            or "Unclear"
        )

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=agent_input.problem_statement,
            target_customer=target_customer,
            industry=agent_input.industry,
            business_type=business_type,
            geography=geography,
            founder_validation_goal=goal,
            founder_evidence=evidence,
        )

    # ── Output parser ──────────────────────────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Parse the LLM response into the 10-section schema and preserve all legacy flat fields.
        Applies defaults for missing fields and validates value ranges.
        """
        parsed: dict[str, Any] = {}

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            # Attempt to extract JSON block from freeform text
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            if not parsed:
                logger.warning(
                    f"[{self.agent_name}] Could not parse JSON. "
                    f"Raw (first 300 chars): {raw_content[:300]}"
                )
                raise json.JSONDecodeError("No valid JSON found", raw_content, 0)

        # ── 1. Top-Level Validation Score Normalization ─────────────────────────
        score_val = (
            parsed.get("validation_score")
            if parsed.get("validation_score") is not None
            else parsed.get("problem_clarity_score")
        )
        if score_val is None:
            score_val = parsed.get("idea_clarity_score", 40)

        try:
            clamped_score = max(0, min(100, int(score_val)))
        except (ValueError, TypeError):
            clamped_score = 40

        parsed["validation_score"] = clamped_score
        parsed["problem_clarity_score"] = clamped_score
        parsed["idea_clarity_score"] = clamped_score

        # ── 2. Confidence Normalization ────────────────────────────────────────
        raw_conf = parsed.get("confidence", 0.4)
        try:
            clamped_conf = max(0.0, min(1.0, float(raw_conf)))
        except (ValueError, TypeError):
            clamped_conf = 0.4
        parsed["confidence"] = clamped_conf

        # ── 3. Verdict / Recommendation Normalization ──────────────────────────
        raw_verdict = (
            parsed.get("verdict")
            or parsed.get("initial_recommendation")
            or "needs_clarification"
        )
        norm_key = str(raw_verdict).lower().strip().replace("-", "_")
        rec_code = VERDICT_MAP.get(norm_key, "needs_clarification")
        if rec_code not in VALID_RECOMMENDATIONS:
            rec_code = "needs_clarification"

        display_verdict = {
            "proceed_to_validation": "Build",
            "needs_clarification": "Validate More",
            "reduce_scope": "Reduce Scope",
            "pivot": "Pivot",
            "hold": "Hold",
        }.get(rec_code, "Validate More")

        parsed["verdict"] = display_verdict
        parsed["initial_recommendation"] = rec_code

        # ── 4. Extract or Default the 10 Sections ───────────────────────────────
        sections = parsed.get("sections")
        if not isinstance(sections, dict):
            sections = {}

        # Section 1: Problem Identification
        prob_id = sections.get("problem_identification") or {}
        falsifiable_sentence = (
            prob_id.get("falsifiable_problem_sentence")
            or parsed.get("falsifiable_problem_sentence")
            or parsed.get("problem_statement")
            or "Problem statement requires further empirical definition."
        )
        root_cause = (
            prob_id.get("root_cause")
            or "Root inefficiency or human friction in current process."
        )
        impact_scope = (
            prob_id.get("impact_scope")
            or parsed.get("problem_statement_summary")
            or "Customer pain impact requiring structured validation."
        )
        sections["problem_identification"] = {
            "falsifiable_problem_sentence": falsifiable_sentence,
            "root_cause": root_cause,
            "impact_scope": impact_scope,
        }

        # Section 2: Idea Clarity
        idea_clarity = sections.get("idea_clarity") or {}
        clarity_score = idea_clarity.get("clarity_score", clamped_score)
        try:
            clarity_score = max(0, min(100, int(clarity_score)))
        except (ValueError, TypeError):
            clarity_score = clamped_score

        clarity_assessment = (
            idea_clarity.get("assessment")
            or "Concept precision evaluated for problem-solution clarity."
        )
        red_flags_list = (
            idea_clarity.get("red_flags")
            or parsed.get("red_flags")
            or []
        )
        if not isinstance(red_flags_list, list):
            red_flags_list = [str(red_flags_list)] if red_flags_list else []
        sections["idea_clarity"] = {
            "clarity_score": clarity_score,
            "assessment": clarity_assessment,
            "red_flags": red_flags_list,
        }

        # Section 3: Customer Problem
        cust_prob = sections.get("customer_problem") or {}
        raw_pain_type = str(
            cust_prob.get("pain_type")
            or parsed.get("pain_type_classification")
            or "Unclear"
        ).lower().strip()
        pain_type = VALID_PAIN_TYPES.get(raw_pain_type, "Unclear")
        severity = cust_prob.get("severity") or ("High" if pain_type == "Painkiller" else "Medium")
        frequency = cust_prob.get("frequency") or parsed.get("who_and_frequency") or "Regular recurring cycle"
        cost_of_inaction = cust_prob.get("cost_of_inaction") or "Accumulated time loss, operational friction, or financial leakage."
        workarounds = (
            cust_prob.get("current_workarounds")
            or parsed.get("current_workarounds")
            or "Existing manual efforts, spreadsheets, or competitor substitutes."
        )
        sections["customer_problem"] = {
            "pain_type": pain_type,
            "severity": severity,
            "frequency": frequency,
            "cost_of_inaction": cost_of_inaction,
            "current_workarounds": workarounds,
        }

        # Section 4: Target Audience Hypothesis
        target_aud = sections.get("target_audience_hypothesis") or {}
        icp = (
            target_aud.get("icp")
            or parsed.get("who_and_frequency")
            or parsed.get("customer_hypothesis")
            or "Target beachhead customer segment experiencing urgent pain."
        )
        user_persona = target_aud.get("user_persona") or "Primary daily end-user experiencing the workflow friction."
        buyer_persona = target_aud.get("buyer_persona") or "Budget holder / economic buyer with purchase authority."
        early_adopter = target_aud.get("early_adopter_profile") or "High-urgency cohort seeking immediate resolution."
        sections["target_audience_hypothesis"] = {
            "icp": icp,
            "user_persona": user_persona,
            "buyer_persona": buyer_persona,
            "early_adopter_profile": early_adopter,
        }

        # Section 5: Solution Definition
        sol_def = sections.get("solution_definition") or {}
        core_mechanism = sol_def.get("core_mechanism") or "Core workflow or product capability eliminating the identified bottleneck."
        prob_sol_fit = sol_def.get("problem_solution_fit") or "Directly addresses root cause pain with minimal adoption friction."
        mvp_scope = sol_def.get("mvp_scope") or "Smallest testable version proving value delivery with lowest capital."
        sections["solution_definition"] = {
            "core_mechanism": core_mechanism,
            "problem_solution_fit": prob_sol_fit,
            "mvp_scope": mvp_scope,
        }

        # Section 6: Value Proposition
        val_prop = sections.get("value_proposition") or {}
        uvp = val_prop.get("uvp") or f"Delivering measurable resolution for {falsifiable_sentence}"
        benefits = val_prop.get("quantifiable_benefits") or ["Measurable efficiency gain", "Reduced operational cost", "Faster time-to-value"]
        if not isinstance(benefits, list):
            benefits = [str(benefits)] if benefits else []
        why_choose = val_prop.get("why_choose_this") or "Significantly lower friction and clearer ROI than existing alternatives."
        sections["value_proposition"] = {
            "uvp": uvp,
            "quantifiable_benefits": benefits,
            "why_choose_this": why_choose,
        }

        # Section 7: Idea Feasibility
        feas = sections.get("idea_feasibility") or {}
        tech_feas = feas.get("technical_feasibility") or "High — achievable with modern proven tools and architectures."
        op_feas = feas.get("operational_feasibility") or "Manageable with lean operational workflows."
        resource_req = feas.get("resource_requirements") or "Lean initial build team and modest initial testing budget."
        sections["idea_feasibility"] = {
            "technical_feasibility": tech_feas,
            "operational_feasibility": op_feas,
            "resource_requirements": resource_req,
        }

        # Section 8: Initial Competitor Check
        comp_check = sections.get("initial_competitor_check") or {}
        direct_comp = comp_check.get("direct_competitors") or ["Incumbent domain solutions"]
        if not isinstance(direct_comp, list):
            direct_comp = [str(direct_comp)] if direct_comp else []
        indirect_comp = comp_check.get("indirect_competitors") or ["Manual spreadsheets, internal tools, or doing nothing"]
        if not isinstance(indirect_comp, list):
            indirect_comp = [str(indirect_comp)] if indirect_comp else []
        key_diff = comp_check.get("key_differentiator") or "Tailored UX and lower switching friction for the beachhead segment."
        sections["initial_competitor_check"] = {
            "direct_competitors": direct_comp,
            "indirect_competitors": indirect_comp,
            "key_differentiator": key_diff,
        }

        # Section 9: Validation Survey / Interviews
        val_surv = sections.get("validation_survey_interviews") or {}
        interview_qs = val_surv.get("interview_questions") or [
            "How do you currently handle this problem today?",
            "What was the cost or friction the last time this occurred?",
            "What workaround have you tried, and why was it insufficient?",
        ]
        if not isinstance(interview_qs, list):
            interview_qs = [str(interview_qs)] if interview_qs else []
        survey_metrics = val_surv.get("survey_metrics_to_test") or [
            "Pain occurrence frequency",
            "Satisfaction with current workarounds",
            "Willingness to pilot a new solution",
        ]
        if not isinstance(survey_metrics, list):
            survey_metrics = [str(survey_metrics)] if survey_metrics else []
        riskiest_assump = (
            val_surv.get("riskiest_assumptions")
            or parsed.get("assumption_list")
            or parsed.get("key_assumptions")
            or [
                "Target segment acknowledges the problem as urgent",
                "Customers are willing to switch from status quo",
            ]
        )
        if not isinstance(riskiest_assump, list):
            riskiest_assump = [str(riskiest_assump)] if riskiest_assump else []
        sections["validation_survey_interviews"] = {
            "interview_questions": interview_qs,
            "survey_metrics_to_test": survey_metrics,
            "riskiest_assumptions": riskiest_assump,
        }

        # Section 10: Decision & Objective Review
        decision_sec = sections.get("decision") or {}
        obj_review = (
            decision_sec.get("objective_review_summary")
            or "Promising core value proposition; priority is validating critical assumptions before capital deployment."
        )
        rationale_list = decision_sec.get("rationale") or [
            f"Validation score of {clamped_score}/100 based on clarity and problem alignment.",
            f"Pain type classified as {pain_type}.",
            "Demand and willingness-to-pay require early empirical verification.",
        ]
        if not isinstance(rationale_list, list):
            rationale_list = [str(rationale_list)] if rationale_list else []
        next_actions = decision_sec.get("next_7_day_actions") or [
            "Conduct 5-10 discovery interviews with target customer profile.",
            "Deploy a focused survey to test willingness to adopt.",
            "Synthesize customer proof points to lock MVP feature boundaries.",
        ]
        if not isinstance(next_actions, list):
            next_actions = [str(next_actions)] if next_actions else []

        sections["decision"] = {
            "verdict": display_verdict,
            "recommendation_code": rec_code,
            "confidence": clamped_conf,
            "objective_review_summary": obj_review,
            "rationale": rationale_list,
            "next_7_day_actions": next_actions,
        }

        parsed["sections"] = sections

        # ── 5. Populate Header Metrics ─────────────────────────────────────────
        validated_idea = parsed.get("validated_idea")
        if not isinstance(validated_idea, dict):
            validated_idea = {}
        validated_idea.setdefault("title", "Startup Venture")
        validated_idea.setdefault("summary", falsifiable_sentence)
        validated_idea.setdefault("category", "General Venture")
        parsed["validated_idea"] = validated_idea

        parsed["problem_statement"] = falsifiable_sentence

        # ── 6. Populate Legacy Flat Fields for 100% Backward Compatibility ──────
        summary_val = (
            parsed.get("problem_statement_summary")
            or parsed.get("problem_summary")
            or impact_scope
        )
        parsed["problem_statement_summary"] = summary_val
        parsed["problem_summary"] = summary_val
        parsed["falsifiable_problem_sentence"] = falsifiable_sentence

        parsed["pain_type_classification"] = pain_type
        parsed["who_and_frequency"] = icp
        parsed["customer_hypothesis"] = icp
        parsed["current_workarounds"] = workarounds

        parsed["assumption_list"] = riskiest_assump
        parsed["key_assumptions"] = riskiest_assump
        parsed["red_flags"] = red_flags_list

        parsed.setdefault(
            "disclaimer",
            "This is decision-support guidance only, not professional business, legal, tax, or investment advice.",
        )

        return parsed

    # ── Score extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        score_val = (
            parsed_output.get("validation_score")
            if parsed_output.get("validation_score") is not None
            else parsed_output.get("problem_clarity_score")
        )
        if score_val is None:
            score_val = parsed_output.get("idea_clarity_score", 40)
        return float(score_val)
