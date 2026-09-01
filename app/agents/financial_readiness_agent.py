
# Reserved for Phase 2: Financial Readiness Agent.

"""
Financial Readiness Agent — Analysis 4 (Financial Intelligence & AI CFO Agent)
──────────────────────────────────────────────────────────────────────────────
Evaluates venture business economics, revenue and pricing models, cost structures,
unit economics (CAC, LTV, margins, payback), burn rate, runway scenarios, break-even
timelines, capital requirements, funding readiness, and delivers AI CFO strategic decisions.

Skill      : financial_readiness_skill
Score      : financial_readiness_score (0–100)
Outputs    : financial_readiness_score, ai_cfo_decision, cost_category_summary,
             revenue_model_options, pricing_consideration_notes, funding_gap_awareness,
             financial_risk_flags, unit_economics_summary, burn_and_runway_analysis,
             priority_actions, financial_scenarios, executive_summary,
             confidence, educational_disclaimer
"""
import json
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logger = logging.getLogger(__name__)

VALID_CFO_DECISIONS = {
    "proceed",
    "proceed_with_conditions",
    "pause",
    "pivot",
    "stop",
}

DEFAULT_FINANCIAL_OUTPUT: dict[str, Any] = {
    "financial_readiness_score": 45,
    "ai_cfo_decision": "proceed_with_conditions",
    "cost_category_summary": [
        "Fixed overhead: Infrastructure hosting, domain, and productivity software subscriptions",
        "Variable costs: Payment gateway transaction fees (2.9% + $0.30) and third-party API consumption",
        "Customer acquisition: Initial organic founder-led outreach and targeted digital marketing",
    ],
    "revenue_model_options": [
        "Direct product sales per unit (D2C / E-commerce) or tiered recurring subscription",
        "Volume wholesale discounts or usage/tier add-ons based on customer segment",
    ],
    "pricing_consideration_notes": [
        "Introduce an accessible entry price point to minimize initial adoption friction",
        "Target healthy gross margins (50%+ for physical products, 75%+ for digital) by closely monitoring direct COGS and unit acquisition costs",
    ],
    "funding_gap_awareness": "Early validation stage: Recommended to operate lean, preserve cash runway, and demonstrate customer willingness to pay before raising external capital.",
    "financial_risk_flags": [
        "Customer willingness to pay at target price points requires empirical validation",
        "Potential customer acquisition cost (CAC) inflation prior to achieving repeatable distribution",
    ],
    "unit_economics_summary": {
        "estimated_cac": "Requires customer acquisition channel testing",
        "estimated_ltv": "Dependent on repeat purchase rate or subscription duration",
        "ltv_to_cac_ratio": "Target 3.0x+ upon reaching product-market fit",
        "gross_margin_pct": "50% - 85%",
        "cac_payback_months": "< 12 months target",
    },
    "burn_and_runway_analysis": {
        "estimated_monthly_burn": "Lean early-stage burn ($1,000 - $5,000/mo operating overhead)",
        "runway_scenarios": "Maintain a minimum of 6–12 months cash reserve during initial validation",
        "break_even_timeline": "Estimated 6–18 months post-launch depending on customer acquisition velocity",
    },
    "priority_actions": [
        "Validate customer price sensitivity and willingness to pay during customer discovery interviews",
        "Establish a strict monthly operational budget cap prior to recurring revenue traction",
        "Model per-customer unit economics to ensure positive contribution margins from day one",
    ],
    "financial_scenarios": {
        "base_case": "Moderate customer adoption with steady organic growth and controlled operating costs",
        "upside_case": "Rapid adoption across target ICP with high annual prepayment uptake",
        "downside_case": "Extended sales cycles requiring prolonged runway and cost discipline",
        "stress_case": "High early churn requiring immediate pricing or product scope adjustments",
    },
    "executive_summary": "Financial readiness analysis indicates a viable business model opportunity provided that initial customer acquisition costs remain tightly controlled and pricing power is validated early.",
    "confidence": 0.5,
    "educational_disclaimer": "This is educational and decision-support guidance only. It is not legal, tax, accounting, banking, investment, loan, or professional financial advice.",
}


class FinancialReadinessAgent(BaseAgent):
    """
    Fourth agent in the validation pipeline (Analysis 4: Financial Readiness & AI CFO Analysis).
    Uses financial_readiness_skill to evaluate business economics, unit economics, runway,
    funding readiness, and AI CFO strategic decisions.
    """
    agent_name = "financial_readiness_agent"
    skill_name = "financial_readiness_skill"

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError("Skill not loaded for FinancialReadinessAgent")

        ctx = agent_input.additional_context or {}

        # Pull forward context from IdeaValidationAgent & MarketResearchAgent
        problem_statement = agent_input.problem_statement or "Not explicitly specified"
        industry = agent_input.industry or "General / Cross-industry"
        geography = agent_input.geography or "Global"
        business_type = agent_input.business_type or "Unclear"
        validation_goal = agent_input.founder_validation_goal or "Validate financial viability"

        target_customer = (
            agent_input.target_customer
            or ctx.get("target_customer")
            or "Target prospective buyers"
        )
        primary_icp = (
            ctx.get("primary_icp_summary")
            or ctx.get("persona_summary")
            or target_customer
        )
        market_opp = (
            ctx.get("market_opportunity_summary")
            or "Market opportunity currently under validation"
        )

        budget_range = (
            ctx.get("budget_range")
            or ctx.get("budget")
            or ctx.get("capital")
            or "Early stage / Bootstrapped"
        )
        revenue_model_assumption = (
            ctx.get("revenue_model_assumption")
            or ctx.get("revenue_model")
            or ctx.get("monetization")
            or "Subscription / Value-based pricing"
        )
        pricing_assumption = (
            ctx.get("pricing_assumption")
            or ctx.get("pricing")
            or "Tiered pricing to be validated with prospective customers"
        )

        # ── Financial baseline fields (collected via conversational intake) ──────
        business_stage = (
            ctx.get("business_stage")
            or ctx.get("stage")
            or "Idea / Pre-MVP stage"
        )
        current_monthly_revenue = (
            ctx.get("current_monthly_revenue")
            or ctx.get("monthly_revenue")
            or ctx.get("mrr")
            or "Pre-revenue (no paying customers yet)"
        )
        estimated_monthly_costs = (
            ctx.get("estimated_monthly_costs")
            or ctx.get("monthly_costs")
            or ctx.get("burn_rate")
            or ctx.get("monthly_burn")
            or "Not yet specified — cost structure under planning"
        )

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=problem_statement,
            industry=industry,
            geography=geography,
            business_type=business_type,
            founder_validation_goal=validation_goal,
            target_customer=target_customer,
            primary_icp_summary=primary_icp,
            market_opportunity_summary=market_opp,
            budget_range=budget_range,
            revenue_model_assumption=revenue_model_assumption,
            pricing_assumption=pricing_assumption,
            business_stage=business_stage,
            current_monthly_revenue=current_monthly_revenue,
            estimated_monthly_costs=estimated_monthly_costs,
        )

    # ── Output parser ──────────────────────────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Parse the LLM response into the Analysis 4 financial readiness schema.
        Applies robust normalization, aliasing, default fallbacks, and range clamping.
        """
        parsed: dict[str, Any] = {}

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
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
                raise json.JSONDecodeError("No valid JSON found in LLM response", raw_content, 0)

        # ── Normalize score ───────────────────────────────────────────────────
        score_val = (
            parsed.get("financial_readiness_score")
            or parsed.get("readiness_score")
            or parsed.get("financial_score")
            or DEFAULT_FINANCIAL_OUTPUT["financial_readiness_score"]
        )
        try:
            clamped_score = max(0, min(100, int(score_val)))
        except (ValueError, TypeError):
            clamped_score = 45
        parsed["financial_readiness_score"] = clamped_score

        # ── Normalize AI CFO decision ─────────────────────────────────────────
        raw_decision = str(
            parsed.get("ai_cfo_decision")
            or parsed.get("decision")
            or parsed.get("cfo_decision")
            or "proceed_with_conditions"
        ).lower().strip().replace(" ", "_").replace("-", "_")

        if raw_decision not in VALID_CFO_DECISIONS:
            if "condition" in raw_decision:
                raw_decision = "proceed_with_conditions"
            elif "proceed" in raw_decision:
                raw_decision = "proceed"
            elif "pause" in raw_decision or "hold" in raw_decision:
                raw_decision = "pause"
            elif "pivot" in raw_decision:
                raw_decision = "pivot"
            elif "stop" in raw_decision:
                raw_decision = "stop"
            else:
                raw_decision = "proceed_with_conditions"
        parsed["ai_cfo_decision"] = raw_decision

        # ── Normalize list fields ─────────────────────────────────────────────
        def _ensure_list(key: str, fallback_key: str | None = None) -> list[str]:
            val = parsed.get(key)
            if val is None and fallback_key:
                val = parsed.get(fallback_key)
            if val is None:
                return DEFAULT_FINANCIAL_OUTPUT.get(key, [])
            if isinstance(val, list):
                return [str(item) if not isinstance(item, dict) else json.dumps(item) for item in val]
            return [str(val)]

        parsed["cost_category_summary"] = _ensure_list("cost_category_summary", "costs")
        parsed["revenue_model_options"] = _ensure_list("revenue_model_options", "revenue_models")
        parsed["pricing_consideration_notes"] = _ensure_list("pricing_consideration_notes", "pricing_notes")
        parsed["financial_risk_flags"] = _ensure_list("financial_risk_flags", "financial_risks")
        parsed["priority_actions"] = _ensure_list("priority_actions", "financial_priorities")

        # ── Normalize string / object fields ──────────────────────────────────
        funding_gap = (
            parsed.get("funding_gap_awareness")
            or parsed.get("funding_gap")
            or parsed.get("funding_summary")
            or DEFAULT_FINANCIAL_OUTPUT["funding_gap_awareness"]
        )
        parsed["funding_gap_awareness"] = str(funding_gap)

        exec_summary = (
            parsed.get("executive_summary")
            or parsed.get("financial_summary")
            or DEFAULT_FINANCIAL_OUTPUT["executive_summary"]
        )
        parsed["executive_summary"] = str(exec_summary)

        # ── Normalize unit economics & burn analysis dicts ────────────────────
        unit_econ = parsed.get("unit_economics_summary") or parsed.get("unit_economics")
        if not isinstance(unit_econ, dict):
            unit_econ = DEFAULT_FINANCIAL_OUTPUT["unit_economics_summary"]
        parsed["unit_economics_summary"] = unit_econ

        burn_runway = parsed.get("burn_and_runway_analysis") or parsed.get("burn_rate") or parsed.get("runway")
        if not isinstance(burn_runway, dict):
            burn_runway = DEFAULT_FINANCIAL_OUTPUT["burn_and_runway_analysis"]
        parsed["burn_and_runway_analysis"] = burn_runway

        scenarios = parsed.get("financial_scenarios") or parsed.get("scenarios")
        if not isinstance(scenarios, dict):
            scenarios = DEFAULT_FINANCIAL_OUTPUT["financial_scenarios"]
        parsed["financial_scenarios"] = scenarios

        # ── Normalize confidence & disclaimer ─────────────────────────────────
        raw_conf = parsed.get("confidence", 0.5)
        try:
            conf_val = float(raw_conf)
            if conf_val > 1.0:
                conf_val = conf_val / 100.0
            parsed["confidence"] = max(0.0, min(1.0, conf_val))
        except (ValueError, TypeError):
            parsed["confidence"] = 0.5

        parsed.setdefault(
            "educational_disclaimer",
            "This is educational and decision-support guidance only. It is not legal, tax, accounting, banking, investment, loan, or professional financial advice."
        )
        parsed.setdefault(
            "disclaimer",
            parsed["educational_disclaimer"],
        )

        return parsed

    # ── Score extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        score_val = (
            parsed_output.get("financial_readiness_score")
            or parsed_output.get("readiness_score")
            or parsed_output.get("financial_score")
            or 45
        )
        try:
            return float(score_val)
        except (ValueError, TypeError):
            return 45.0


