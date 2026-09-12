import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.mentor_service import (
    WorkspaceMentorState,
    EXTRACT_SYSTEM_PROMPT,
    _WORKSPACE_STATE_TEMPLATE,
    _build_mentor_system_prompt,
    mentor_service,
)
from app.services.workspace_service import workspace_service
from app.skills.skill_registry import skill_registry
from app.db.models import User, Workspace
from app.models.workspace_models import WorkspaceChatRequest


# ── Prompt / Skill Addon Tests (ADDON-1 to ADDON-8) ──────────────────────────

def test_addon_1_founder_personality_profiling():
    skill = skill_registry.get("ai_mentor_core_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "### Founder Personality Profiling (Active Observation)" in prompt
    assert "#### 11 Dimensions to Observe and Adapt To" in prompt
    assert "Introverted / Under-Confident Founder:" in prompt
    assert "Extroverted / Highly Confident Founder:" in prompt
    assert "Analytical / Data-Driven Founder:" in prompt
    assert "Emotionally Stressed / Overwhelmed Founder:" in prompt
    assert "Aggressive / Fast-Moving Founder:" in prompt
    assert "Confused / Unclear Founder:" in prompt


def test_addon_2_archetype_tone_rules():
    skill = skill_registry.get("ai_mentor_core_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "### Same Advice, Different Delivery" in prompt
    assert "To Analytical Founder" in prompt
    assert "To Emotional/Stressed Founder" in prompt
    assert "To Overconfident Founder" in prompt


def test_addon_3_closure_protocol():
    skill = skill_registry.get("ai_idea_validation_mentor_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "### Conversation Closure Protocol (After Any Problem Discussion)" in prompt
    assert "1. **What happened**" in prompt
    assert "2. **Why it happened**" in prompt
    assert "3. **What can be controlled**" in prompt
    assert "4. **What to do next**" in prompt
    assert "5. **Immediate action**" in prompt
    assert "6. **Accountability checkpoint**" in prompt


def test_addon_4_confidence_language_rules():
    skill = skill_registry.get("ai_idea_validation_mentor_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "### Confidence Language Rules (Mandatory)" in prompt
    assert "❌ NEVER Say" in prompt
    assert "✅ Always Use Instead" in prompt
    assert '"You will definitely succeed."' in prompt
    assert "Realistic confidence = Clarity + Evidence + Action Plan + Honest Risk Visibility." in prompt


def test_addon_5_accountability_loop():
    skill = skill_registry.get("ai_idea_validation_mentor_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "8. **Accountability**" in prompt
    assert "9. **Return invitation**" in prompt


def test_addon_6_mentor_pace_calibration():
    skill = skill_registry.get("ai_mentor_core_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "## 7A. MENTOR PACE CALIBRATION" in prompt
    assert "### Slow Down Triggers" in prompt
    assert "### Push Forward Triggers" in prompt


def test_addon_7_independent_judgement_reinforcement():
    skill = skill_registry.get("ai_idea_validation_mentor_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "- **Independent judgement.**" in prompt
    assert "You know your market and context better than any AI" in prompt
    assert "- **Encourage human experts.**" in prompt


def test_addon_8_session_success_standard():
    skill = skill_registry.get("ai_mentor_core_skill")
    assert skill is not None
    prompt = skill.prompt_template
    assert "## 11. SESSION SUCCESS STANDARD" in prompt
    assert "Will the founder leave this response feeling more CLEAR, more CONFIDENT, more COURAGEOUS" in prompt
    assert "### The Three Forbidden Outcomes" in prompt
    assert "### The Three Required Outcomes (Every Single Response)" in prompt


# ── CODE-A Tests ──────────────────────────────────────────────────────────────

def test_code_a_workspace_mentor_state_default_business_stage():
    state = WorkspaceMentorState(workspace_id="ws-stage-test")
    assert "business_stage" in state.idea
    assert state.idea["business_stage"] == "idea"


def test_code_a_extract_system_prompt_includes_business_stage():
    assert "- business_stage: Current stage of the business." in EXTRACT_SYSTEM_PROMPT
    assert '"pre_idea" | "idea" | "mvp" | "revenue" | "scaling" | "existing_business"' in EXTRACT_SYSTEM_PROMPT


# ── CODE-B Tests ──────────────────────────────────────────────────────────────

def test_code_b_workspace_state_template_placeholders():
    assert "Founder Name: {founder_name}" in _WORKSPACE_STATE_TEMPLATE
    assert "Business Stage: {business_stage}" in _WORKSPACE_STATE_TEMPLATE
    assert "Emotional Signal (Last Message): {emotional_signal}" in _WORKSPACE_STATE_TEMPLATE


def test_code_b_build_mentor_system_prompt_formatting():
    prompt = _build_mentor_system_prompt(
        workspace_id="ws-code-b",
        state="GATHERING_INFO",
        idea_json="{}",
        missing_fields="None",
        founder_name="Vikram",
        business_stage="mvp",
        emotional_signal="uncertain_or_under_confident",
    )
    assert "Founder Name: Vikram" in prompt
    assert "Business Stage: mvp" in prompt
    assert "Emotional Signal (Last Message): uncertain_or_under_confident" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_text,expected_signal",
    [
        ("I'm really stressed and overwhelmed about this launch, what if I fail?", "stressed_or_fearful"),
        ("This is amazing and definitely guaranteed to be huge!", "excited_or_overconfident"),
        ("I'm not sure if this is the right direction, perhaps we could try something else", "uncertain_or_under_confident"),
        ("Let's go, ready to move fast right now!", "aggressive_or_fast_moving"),
        ("We are targeting enterprise logistics providers.", "neutral"),
    ],
)
async def test_code_b_emotional_signal_detection(user_text, expected_signal):
    state = WorkspaceMentorState(
        workspace_id="ws-emo-test",
        state="GATHERING_INFO",
        idea={
            "idea_title": "LogiRoute",
            "idea_description": "Route optimization",
            "problem_statement": "High fuel costs",
            "founder_name": "Priya",
            "business_stage": "revenue",
        },
        conversation_history=[
            {"role": "user", "content": user_text},
        ],
    )

    mock_llm = MagicMock()
    mock_res = MagicMock()
    mock_res.success = True
    mock_res.content = "I hear you."
    mock_res.tokens_input = 100
    mock_res.tokens_output = 50
    mock_res.total_tokens = 150
    mock_llm.complete = AsyncMock(return_value=mock_res)

    with patch.object(mentor_service, "_llm", mock_llm):
        await mentor_service._generate_mentor_reply(state)

    call_arg = mock_llm.complete.call_args[0][0]
    assert f"Emotional Signal (Last Message): {expected_signal}" in call_arg.system_prompt
    assert "Founder Name: Priya" in call_arg.system_prompt
    assert "Business Stage: revenue" in call_arg.system_prompt


# ── CODE-C Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_code_c_reset_workspace_mentor_with_display_name():
    fake_user = MagicMock(spec=User)
    fake_user.id = 1
    fake_user.display_name = "Aarav Sharma"
    fake_user.username = "aarav@example.com"

    fake_workspace = MagicMock(spec=Workspace)
    fake_workspace.id = 101
    fake_workspace.state = "GATHERING_INFO"
    fake_workspace.idea = {}
    fake_workspace.conversation_history = []
    fake_workspace.validation_result = None

    fake_db = MagicMock()
    fake_db.flush = AsyncMock()
    fake_db.refresh = AsyncMock()

    with patch.object(workspace_service, "_fetch_owned_workspace", AsyncMock(return_value=fake_workspace)), \
         patch("app.models.workspace_models.WorkspaceStateResponse.model_validate", side_effect=lambda x: x):
        res = await workspace_service.reset_workspace_mentor(
            workspace_id=101,
            current_user=fake_user,
            db=fake_db,
        )

    assert "Hello Aarav! I'm Arya" in fake_workspace.conversation_history[0]["content"]
    assert fake_workspace.idea.get("business_stage") == "idea"


@pytest.mark.asyncio
async def test_code_c_reset_workspace_mentor_with_username_fallback():
    fake_user = MagicMock(spec=User)
    fake_user.id = 2
    fake_user.display_name = None
    fake_user.username = "priya.patel@startup.io"

    fake_workspace = MagicMock(spec=Workspace)
    fake_workspace.id = 102
    fake_workspace.state = "GATHERING_INFO"
    fake_workspace.idea = {}
    fake_workspace.conversation_history = []
    fake_workspace.validation_result = None

    fake_db = MagicMock()
    fake_db.flush = AsyncMock()
    fake_db.refresh = AsyncMock()

    with patch.object(workspace_service, "_fetch_owned_workspace", AsyncMock(return_value=fake_workspace)), \
         patch("app.models.workspace_models.WorkspaceStateResponse.model_validate", side_effect=lambda x: x):
        res = await workspace_service.reset_workspace_mentor(
            workspace_id=102,
            current_user=fake_user,
            db=fake_db,
        )

    assert "Hello Priya.Patel! I'm Arya" in fake_workspace.conversation_history[0]["content"]


@pytest.mark.asyncio
async def test_code_c_process_mentor_chat_injects_founder_name():
    fake_user = MagicMock(spec=User)
    fake_user.id = 3
    fake_user.display_name = "Kavita Rao"
    fake_user.username = "kavita@example.com"

    fake_workspace = MagicMock(spec=Workspace)
    fake_workspace.id = 103
    fake_workspace.state = "GATHERING_INFO"
    fake_workspace.idea = {}
    fake_workspace.conversation_history = []
    fake_workspace.validation_result = None

    fake_db = MagicMock()
    fake_db.flush = AsyncMock()
    fake_db.refresh = AsyncMock()

    mock_updated_state = WorkspaceMentorState(
        workspace_id="103",
        state="GATHERING_INFO",
        idea={"founder_name": "Kavita"},
        conversation_history=[{"role": "assistant", "content": "Hello Kavita!"}],
    )

    captured_ws_state = None

    async def mock_process_message(state, user_message, attachments, user_id, db):
        nonlocal captured_ws_state
        captured_ws_state = state
        return mock_updated_state

    with patch.object(workspace_service, "_fetch_owned_workspace", AsyncMock(return_value=fake_workspace)), \
         patch.object(mentor_service, "process_message", side_effect=mock_process_message):
        payload = WorkspaceChatRequest(message="Hello mentor")
        await workspace_service.process_mentor_chat(
            workspace_id=103,
            payload=payload,
            current_user=fake_user,
            db=fake_db,
        )

    assert captured_ws_state is not None
    assert captured_ws_state.idea.get("founder_name") == "Kavita"
