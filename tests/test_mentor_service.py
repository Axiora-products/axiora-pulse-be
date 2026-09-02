import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.mentor_service import (
    WorkspaceMentorState,
    _build_mentor_system_prompt,
    mentor_service,
)
from app.services.report_service import report_service


# ── Mentor System Prompt Tests ───────────────────────────────────────────────────

def test_build_mentor_system_prompt_includes_optional_context():
    prompt = _build_mentor_system_prompt(
        workspace_id="ws-123",
        state="GATHERING_INFO",
        idea_json=json.dumps({"idea_title": "Test Venture"}),
        missing_fields="Problem Statement",
        optional_context_status="Geography: \"Hyderabad\" (provided) | Early Evidence: Not yet provided",
    )

    assert "Optional Context Status (Geography / Evidence / Validation Goal):" in prompt
    assert "Hyderabad" in prompt
    assert "OPTIONAL CONTEXT QUESTIONS" in prompt
    assert "Where are you planning to launch first?" in prompt


def test_build_mentor_system_prompt_custom_status():
    status = "Geography: Not yet provided (will default to global) | Early Evidence: \"20 customer interviews\" (provided) | Validation Goal: \"test repeat retention\" (provided)"
    prompt = _build_mentor_system_prompt(
        workspace_id="ws-456",
        state="GATHERING_INFO",
        idea_json="{}",
        missing_fields="None",
        optional_context_status=status,
    )
    assert status in prompt


# ── Mentor Service Context Computation Tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_mentor_reply_computes_optional_context_status():
    state = WorkspaceMentorState(
        workspace_id="ws-test",
        state="GATHERING_INFO",
        idea={
            "idea_title": "AI Validator",
            "idea_description": "AI-powered idea testing platform",
            "problem_statement": "Founders waste capital building unvalidated ideas",
            "geography": "Hyderabad, India",
            "founder_evidence": "Spoke with 25 founders; 18 expressed urgent demand.",
            "founder_validation_goal": "Test pricing and willingness-to-pay",
        },
        conversation_history=[
            {"role": "user", "content": "Here is my idea."},
        ],
    )

    mock_llm = MagicMock()
    mock_res = MagicMock()
    mock_res.success = True
    mock_res.content = "Hello! That sounds like an exciting venture."
    mock_res.prompt_tokens = 100
    mock_res.completion_tokens = 50
    mock_llm.complete = AsyncMock(return_value=mock_res)

    with patch("app.services.mentor_service.get_llm_gateway", return_value=mock_llm):
        await mentor_service._generate_mentor_reply(state)

    assert len(state.conversation_history) == 2
    assert state.conversation_history[-1]["role"] == "assistant"
    assert state.conversation_history[-1]["content"] == "Hello! That sounds like an exciting venture."

    call_arg = mock_llm.complete.call_args[0][0]
    assert "Geography: \"Hyderabad, India\" (provided)" in call_arg.system_prompt
    assert "Early Evidence: \"Spoke with 25 founders; 18 expressed urgent demand.\" (provided)" in call_arg.system_prompt
    assert "Validation Goal: \"Test pricing and willingness-to-pay\" (provided)" in call_arg.system_prompt


# ── Report Service 10-Section Idea Validation Blocks Tests ───────────────────────

def test_report_service_renders_all_10_sections():
    validation_result = {
        "validation_score": 85,
        "verdict": "build",
        "confidence_rating": 0.9,
        "strengths": ["Clear urgent problem", "High founder-domain alignment"],
        "risks": ["Incumbent competition inertia"],
        "assumptions": ["Founders are willing to pay upfront for validation"],
        "recommendations": ["Run 10 discovery calls", "Launch landing page test"],
    }
    agent_results = {
        "idea_validation_agent": {
            "data": {
                "validation_score": 85,
                "verdict": "build",
                "confidence": 0.9,
                "sections": {
                    "problem_identification": {
                        "falsifiable_problem_sentence": "Early stage founders burn seed money without demand proof.",
                        "root_cause": "Lack of structured, unbiased pre-build validation frameworks.",
                        "impact_scope": "Average founder loses $15k-$50k and 6 months building dead products.",
                    },
                    "idea_clarity": {
                        "clarity_score": 90,
                        "assessment": "Very clear, focused B2B workflow tool.",
                        "red_flags": [],
                    },
                    "customer_problem": {
                        "pain_type": "Painkiller",
                        "severity": "High",
                        "frequency": "Per-idea cycle",
                        "cost_of_inaction": "$30,000 lost runway per failed launch.",
                        "current_workarounds": "Manual surveys, asking friends, spreadsheets.",
                    },
                    "target_audience_hypothesis": {
                        "icp": "First-time and second-time software founders.",
                        "user_persona": "Solo technical founders and product leads.",
                        "buyer_persona": "Founder / Managing Director.",
                        "early_adopter_profile": "Bootstrapped founders pre-launch.",
                    },
                    "solution_definition": {
                        "core_mechanism": "Automated 15-parameter AI validation + live Mom Test survey engine.",
                        "problem_solution_fit": "Directly identifies demand risks before code is written.",
                        "mvp_scope": "Idea diagnostic report + 12-question AI survey generator.",
                    },
                    "value_proposition": {
                        "uvp": "Validate startup demand in 10 minutes instead of 6 months.",
                        "quantifiable_benefits": ["80% reduction in wasted build time", "$20k saved per venture"],
                        "why_choose_this": "Evidence-based objective review rather than generic LLM hype.",
                    },
                    "idea_feasibility": {
                        "technical_feasibility": "High",
                        "operational_feasibility": "High",
                        "resource_requirements": "Lean engineering team and API credits.",
                    },
                    "initial_competitor_check": {
                        "direct_competitors": ["ValidatorAI", "IdeaCheck"],
                        "indirect_competitors": ["Typeform", "Google Forms", "Doing nothing"],
                        "key_differentiator": "Deep multi-agent pipeline + Objective Review mentor integration.",
                    },
                    "validation_survey_interviews": {
                        "interview_questions": [
                            "How did you validate your last startup idea before writing code?",
                            "How much did you spend building features that customers never used?",
                        ],
                        "survey_metrics_to_test": ["Willingness-to-pay threshold", "Feature prioritization urgency"],
                        "riskiest_assumptions": ["Founders want objective criticism rather than validation cheerleading."],
                    },
                    "decision": {
                        "verdict": "Build",
                        "recommendation_code": "proceed_to_validation",
                        "confidence": 0.9,
                        "objective_review_summary": "Urgent painkiller with strong beachhead; prioritize proving founder WTP.",
                        "rationale": [
                            "Pain is high urgency and recurring across founder communities.",
                            "Solution MVP is technically lightweight and fast to deliver.",
                        ],
                        "next_7_day_actions": [
                            "Deploy Mom Test survey to 30 early founders.",
                            "Interview 5 accelerators and incubators.",
                        ],
                    },
                },
            }
        }
    }

    blocks = report_service._idea_validation_blocks(validation_result, agent_results)
    assert len(blocks) > 10

    # Verify key sections and titles exist in blocks
    titles = [b.get("title") or b.get("label") for b in blocks if b.get("title") or b.get("label")]
    assert "Problem & Idea Validation" in titles
    assert "Falsifiable Problem Statement" in titles
    assert "Root Cause Analysis:" in titles
    assert "Cost of Inaction:" in titles
    assert "Target Beachhead ICP:" in titles
    assert "Solution Core Mechanism:" in titles
    assert "Unique Value Proposition" in titles
    assert "Objective Review Summary:" in titles
    assert "7-Day Validation Action Plan" in titles
    assert "Direct Competitors" in titles


# ── Mentor State Machine & Financial Context Tests ───────────────────────────────

@pytest.mark.asyncio
async def test_mentor_state_transitions_to_gathering_financial_context():
    state = WorkspaceMentorState(
        workspace_id="ws-fin-test",
        state="GATHERING_INFO",
        idea={},
        conversation_history=[
            {"role": "user", "content": "I am building an automated invoicing tool called QuickBill to stop invoice delays."}
        ]
    )

    mock_extractor_res = MagicMock()
    mock_extractor_res.success = True
    mock_extractor_res.tokens_input = 100
    mock_extractor_res.tokens_output = 50
    mock_extractor_res.total_tokens = 150
    mock_extractor_res.content = json.dumps({
        "idea_title": "QuickBill",
        "idea_description": "Automated invoicing tool",
        "problem_statement": "Small businesses suffer from late client invoice payments",
        "business_stage": None,
        "current_monthly_revenue": None,
        "estimated_monthly_costs": None,
        "budget_range": None,
        "revenue_model_assumption": None,
        "pricing_assumption": None,
    })

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=mock_extractor_res)

    with patch.object(mentor_service, "_llm", mock_llm):
        await mentor_service._run_extraction(state)

    # Core fields are extracted, so state should move to GATHERING_FINANCIAL_CONTEXT
    assert state.state == "GATHERING_FINANCIAL_CONTEXT"
    assert state.idea["idea_title"] == "QuickBill"
    assert state.idea["problem_statement"] == "Small businesses suffer from late client invoice payments"

    # Now simulate user providing financial baseline numbers
    mock_extractor_res2 = MagicMock()
    mock_extractor_res2.success = True
    mock_extractor_res2.tokens_input = 120
    mock_extractor_res2.tokens_output = 60
    mock_extractor_res2.total_tokens = 180
    mock_extractor_res2.content = json.dumps({
        "business_stage": "Pre-MVP",
        "current_monthly_revenue": "$0",
        "estimated_monthly_costs": "$1,500/mo",
        "budget_range": "$10,000",
        "revenue_model_assumption": "SaaS Subscription",
        "pricing_assumption": "$49/mo",
    })

    mock_llm2 = MagicMock()
    mock_llm2.complete = AsyncMock(return_value=mock_extractor_res2)

    with patch.object(mentor_service, "_llm", mock_llm2):
        await mentor_service._run_extraction(state)

    # All financial fields satisfied -> READY_TO_VALIDATE
    assert state.state == "READY_TO_VALIDATE"
    assert state.idea["pricing_assumption"] == "$49/mo"
    assert state.idea["budget_range"] == "$10,000"


@pytest.mark.asyncio
async def test_process_message_full_lifecycle_trigger_validation():
    # 1. State starts in GATHERING_FINANCIAL_CONTEXT
    state = WorkspaceMentorState(
        workspace_id="ws-e2e-test",
        state="GATHERING_FINANCIAL_CONTEXT",
        idea={
            "idea_title": "EcoBottle",
            "idea_description": "Insulated smart water bottle",
            "problem_statement": "Plastic waste and lack of hydration tracking",
        },
        conversation_history=[
            {"role": "assistant", "content": "What is your target pricing and budget?"}
        ]
    )

    # 2. User sends financial message
    mock_extractor_res = MagicMock()
    mock_extractor_res.success = True
    mock_extractor_res.tokens_input = 100
    mock_extractor_res.tokens_output = 50
    mock_extractor_res.total_tokens = 150
    mock_extractor_res.content = json.dumps({
        "business_stage": "Pre-MVP",
        "current_monthly_revenue": "$0",
        "estimated_monthly_costs": "$500/mo",
        "budget_range": "$5,000",
        "revenue_model_assumption": "D2C Sales",
        "pricing_assumption": "$29/bottle",
    })

    mock_reply_res = MagicMock()
    mock_reply_res.success = True
    mock_reply_res.tokens_input = 150
    mock_reply_res.tokens_output = 80
    mock_reply_res.total_tokens = 230
    mock_reply_res.content = "Great! Everything is set. Click 'Run Validation' or type 'run validation' to start."

    mock_llm = MagicMock()
    # First call is extractor, second call is reply generator
    mock_llm.complete = AsyncMock(side_effect=[mock_extractor_res, mock_reply_res])

    with patch.object(mentor_service, "_llm", mock_llm):
        res_state = await mentor_service.process_message(
            state=state,
            user_message="We are Pre-MVP, selling D2C at $29/bottle with $5,000 budget.",
        )

    # State transitioned to READY_TO_VALIDATE
    assert res_state.state == "READY_TO_VALIDATE"
    assert res_state.idea["pricing_assumption"] == "$29/bottle"
    assert "Click 'Run Validation'" in res_state.conversation_history[-1]["content"]

    # 3. User says "Run validation"
    mock_orch_resp = MagicMock()
    mock_orch_resp.status = "success"
    mock_orch_resp.result = MagicMock()
    mock_orch_resp.result.json = MagicMock(return_value=json.dumps({
        "validation_score": 88.0,
        "verdict": "build",
        "agent_results": {}
    }))

    with patch("app.services.mentor_service.orchestrator.run", AsyncMock(return_value=mock_orch_resp)):
        with patch.object(mentor_service, "_llm", mock_llm):
            final_state = await mentor_service.process_message(
                state=res_state,
                user_message="run validation",
            )

    assert final_state.state == "VALIDATED"
    assert final_state.validation_result["validation_score"] == 88.0


