import json
from unittest.mock import MagicMock

import pytest

from app.agents.idea_validation_agent import IdeaValidationAgent
from app.models.agent_models import AgentInput


def make_agent(mock_skill=None) -> IdeaValidationAgent:
    agent = IdeaValidationAgent.__new__(IdeaValidationAgent)  # bypass __init__/skill loading
    agent.skill = mock_skill or MagicMock()
    agent.llm = MagicMock()
    return agent


def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="Invoice Tracker",
        idea_description="Helps freelancers track unpaid invoices automatically.",
        problem_statement="Freelancers lose track of unpaid invoices.",
        industry="fintech",
        geography="global",
        founder_validation_goal="validate my idea",
    )
    base.update(overrides)
    return AgentInput(**base)


# _build_prompt

def test_build_prompt_raises_when_skill_missing():
    agent = make_agent(mock_skill=None)
    agent.skill = None
    with pytest.raises(ValueError, match="Skill not loaded"):
        agent._build_prompt(make_agent_input())


def test_build_prompt_passes_founder_evidence_when_provided():
    mock_skill = MagicMock()
    mock_skill.build_prompt.return_value = "rendered prompt"
    agent = make_agent(mock_skill)

    result = agent._build_prompt(make_agent_input(founder_evidence="Ran 20 customer interviews"))

    assert result == "rendered prompt"
    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["founder_evidence"] == "Ran 20 customer interviews"


def test_build_prompt_falls_back_to_additional_context_evidence():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(
        make_agent_input(additional_context={"founder_evidence": "From context dict"})
    )
    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["founder_evidence"] == "From context dict"


def test_build_prompt_default_evidence_when_none_provided():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input())
    _, kwargs = mock_skill.build_prompt.call_args
    assert "No explicit evidence" in kwargs["founder_evidence"]


# _parse_output — json extraction

def test_parse_output_direct_valid_json():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": 80, "confidence": 0.7}))
    assert parsed["problem_clarity_score"] == 80
    assert parsed["validation_score"] == 80


def test_parse_output_extracts_json_from_surrounding_text():
    agent = make_agent()
    raw = 'Here is my analysis:\n```json\n{"problem_clarity_score": 75}\n```'
    parsed = agent._parse_output(raw)
    assert parsed["problem_clarity_score"] == 75
    assert parsed["validation_score"] == 75


def test_parse_output_raises_json_decode_error_when_unparseable():
    agent = make_agent()
    with pytest.raises(json.JSONDecodeError):
        agent._parse_output("completely unparseable text")


# _parse_output — field normalization & aliasing

def test_parse_output_uses_idea_clarity_score_alias_when_primary_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"idea_clarity_score": 65}))
    assert parsed["problem_clarity_score"] == 65
    assert parsed["idea_clarity_score"] == 65
    assert parsed["validation_score"] == 65


def test_parse_output_defaults_score_to_40_when_absent():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert parsed["problem_clarity_score"] == 40
    assert parsed["validation_score"] == 40


def test_parse_output_normalizes_summary_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_summary": "Alt summary"}))
    assert parsed["problem_statement_summary"] == "Alt summary"
    assert parsed["problem_summary"] == "Alt summary"


def test_parse_output_default_summary_when_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert "Customer pain impact" in parsed["problem_statement_summary"] or "Problem statement" in parsed["problem_statement_summary"]


def test_parse_output_normalizes_who_and_frequency_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"customer_hypothesis": "Freelance designers"}))
    assert parsed["who_and_frequency"] == "Freelance designers"
    assert parsed["customer_hypothesis"] == "Freelance designers"


def test_parse_output_normalizes_assumptions_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"key_assumptions": ["A1", "A2"]}))
    assert parsed["assumption_list"] == ["A1", "A2"]
    assert parsed["key_assumptions"] == ["A1", "A2"]


def test_parse_output_default_assumptions_when_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert len(parsed["assumption_list"]) == 2


def test_parse_output_wraps_non_list_assumptions_as_single_item_list():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"assumption_list": "single string assumption"}))
    assert parsed["assumption_list"] == ["single string assumption"]


# _parse_output — defaults for analysis 1 fields

def test_parse_output_applies_defaults_for_missing_fields():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))

    assert parsed["falsifiable_problem_sentence"] == "Problem statement requires further empirical definition."
    assert parsed["pain_type_classification"] == "Unclear"
    assert "Existing manual efforts" in parsed["current_workarounds"]
    assert parsed["red_flags"] == []
    assert parsed["initial_recommendation"] == "needs_clarification"
    assert parsed["verdict"] == "Validate More"
    assert parsed["confidence"] == 0.4
    assert "decision-support guidance only" in parsed["disclaimer"]


# _parse_output — numeric clamping

def test_parse_output_clamps_score_above_100():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": 250}))
    assert parsed["problem_clarity_score"] == 100
    assert parsed["validation_score"] == 100


def test_parse_output_clamps_score_below_0():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": -20}))
    assert parsed["problem_clarity_score"] == 0
    assert parsed["validation_score"] == 0


def test_parse_output_non_numeric_score_falls_back_to_40():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": "not-a-number"}))
    assert parsed["problem_clarity_score"] == 40
    assert parsed["validation_score"] == 40


def test_parse_output_non_numeric_confidence_falls_back_to_default():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": "invalid"}))
    assert parsed["confidence"] == 0.4


def test_parse_output_clamps_confidence_above_1():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": 5.0}))
    assert parsed["confidence"] == 1.0


# _parse_output — enum validation

@pytest.mark.parametrize("raw_pain_type,expected", [
    ("painkiller", "Painkiller"),
    ("VITAMIN", "Vitamin"),
    ("unclear", "Unclear"),
    ("garbage-value", "Unclear"),
])
def test_parse_output_validates_pain_type_enum(raw_pain_type, expected):
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"pain_type_classification": raw_pain_type}))
    assert parsed["pain_type_classification"] == expected


@pytest.mark.parametrize("raw_rec,expected_code,expected_verdict", [
    ("proceed_to_validation", "proceed_to_validation", "Build"),
    ("Build", "proceed_to_validation", "Build"),
    ("Reduce Scope", "reduce_scope", "Reduce Scope"),
    ("pivot", "pivot", "Pivot"),
    ("Hold", "hold", "Hold"),
    ("nonsense_value", "needs_clarification", "Validate More"),
])
def test_parse_output_validates_recommendation_enum(raw_rec, expected_code, expected_verdict):
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"initial_recommendation": raw_rec}))
    assert parsed["initial_recommendation"] == expected_code
    assert parsed["verdict"] == expected_verdict


def test_parse_output_wraps_non_list_red_flags():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"red_flags": "single flag"}))
    assert parsed["red_flags"] == ["single flag"]


# ── 10 Sections Verification Tests ──────────────────────────────────────────

def test_parse_output_full_10_sections_structure():
    agent = make_agent()
    sample_payload = {
        "validated_idea": {
            "title": "QuickTiffin",
            "summary": "Daily home-cooked meal subscription for tech employees.",
            "category": "FoodTech"
        },
        "problem_statement": "Tech workers eat repetitive, unhealthy food daily.",
        "validation_score": 85,
        "confidence": 0.8,
        "verdict": "Build",
        "sections": {
            "problem_identification": {
                "falsifiable_problem_sentence": "Tech workers lose 45 mins daily and face health fatigue from canteen meals.",
                "root_cause": "Lack of affordable home-style fresh lunch alternatives near tech hubs.",
                "impact_scope": "50,000+ engineers in HITEC City."
            },
            "idea_clarity": {
                "clarity_score": 88,
                "assessment": "High clarity, concise subscription model.",
                "red_flags": []
            },
            "customer_problem": {
                "pain_type": "Painkiller",
                "severity": "High",
                "frequency": "Daily",
                "cost_of_inaction": "Chronic digestive fatigue and high monthly dining costs.",
                "current_workarounds": "Zomato daily orders or office canteen."
            },
            "target_audience_hypothesis": {
                "icp": "IT employees aged 22-35 in Cyber Towers area.",
                "user_persona": "Software Engineer living away from home.",
                "buyer_persona": "Self-paying employee.",
                "early_adopter_profile": "Health-conscious techies tired of junk food."
            },
            "solution_definition": {
                "core_mechanism": "Aggregated daily lunch delivery from certified local home kitchens.",
                "problem_solution_fit": "Guaranteed hygienic, rotating menu at monthly subscription rates.",
                "mvp_scope": "WhatsApp bot + 2 pilot tech park delivery drop points."
            },
            "value_proposition": {
                "uvp": "Fresh, mom-style lunch on your desk by 1 PM for under ₹120/meal.",
                "quantifiable_benefits": ["Save ₹2,000/mo vs Zomato", "Zero decision fatigue daily", "Healthy home-cooked quality"],
                "why_choose_this": "Predictable lunch routine without restaurant oil or surge fees."
            },
            "idea_feasibility": {
                "technical_feasibility": "High",
                "operational_feasibility": "Medium — requires tight kitchen dispatch timing.",
                "resource_requirements": "1 operations coordinator + 5 home cooks; ₹50,000 pilot capital."
            },
            "initial_competitor_check": {
                "direct_competitors": ["Local lunch dabbas", "Canteen providers"],
                "indirect_competitors": ["Swiggy / Zomato"],
                "key_differentiator": "Hygiene transparency & lower daily subscription cost."
            },
            "validation_survey_interviews": {
                "interview_questions": [
                    "What did you have for lunch yesterday, and how satisfied were you?",
                    "How much do you spend monthly on weekday lunches?",
                    "Have you ever subscribed to a meal plan before?"
                ],
                "survey_metrics_to_test": ["Daily reorder intent", "Willingness to prepay ₹2,500/mo"],
                "riskiest_assumptions": ["Workers will commit to weekly/monthly prepaid plans."]
            },
            "decision": {
                "verdict": "Build",
                "recommendation_code": "proceed_to_validation",
                "confidence": 0.8,
                "objective_review_summary": "Strong problem and reachable audience; validate repeat prepay habit first.",
                "rationale": ["Urgent daily pain", "Reachable beachhead", "Low capital MVP possible"],
                "next_7_day_actions": [
                    "Interview 15 tech workers in Cyber Towers.",
                    "Sign up 3 home kitchens for sample tastings.",
                    "Pre-sell 10 trial meal passes for next week."
                ]
            }
        }
    }

    parsed = agent._parse_output(json.dumps(sample_payload))

    # Top-level checks
    assert parsed["validation_score"] == 85
    assert parsed["problem_clarity_score"] == 85
    assert parsed["confidence"] == 0.8
    assert parsed["verdict"] == "Build"
    assert parsed["initial_recommendation"] == "proceed_to_validation"
    assert parsed["validated_idea"]["title"] == "QuickTiffin"
    assert parsed["problem_statement"] == "Tech workers lose 45 mins daily and face health fatigue from canteen meals."

    # 10 Sections checks
    sections = parsed["sections"]
    assert "problem_identification" in sections
    assert "idea_clarity" in sections
    assert "customer_problem" in sections
    assert "target_audience_hypothesis" in sections
    assert "solution_definition" in sections
    assert "value_proposition" in sections
    assert "idea_feasibility" in sections
    assert "initial_competitor_check" in sections
    assert "validation_survey_interviews" in sections
    assert "decision" in sections

    assert sections["customer_problem"]["pain_type"] == "Painkiller"
    assert len(sections["value_proposition"]["quantifiable_benefits"]) == 3
    assert len(sections["decision"]["next_7_day_actions"]) == 3

    # Legacy backward-compatibility checks
    assert parsed["falsifiable_problem_sentence"] == "Tech workers lose 45 mins daily and face health fatigue from canteen meals."
    assert parsed["who_and_frequency"] == "IT employees aged 22-35 in Cyber Towers area."
    assert parsed["current_workarounds"] == "Zomato daily orders or office canteen."
    assert parsed["assumption_list"] == ["Workers will commit to weekly/monthly prepaid plans."]


# _extract_score

def test_extract_score_uses_validation_score():
    agent = make_agent()
    assert agent._extract_score({"validation_score": 88}) == 88.0


def test_extract_score_uses_problem_clarity_score():
    agent = make_agent()
    assert agent._extract_score({"problem_clarity_score": 77}) == 77.0


def test_extract_score_falls_back_to_idea_clarity_score():
    agent = make_agent()
    assert agent._extract_score({"idea_clarity_score": 33}) == 33.0


def test_extract_score_defaults_to_40_when_both_missing():
    agent = make_agent()
    assert agent._extract_score({}) == 40.0
