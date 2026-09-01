import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.llm.llm_gateway import get_llm_gateway, LLMRequest
from app.models.orchestration_models import OrchestrationRequest, IdeaInput, WorkflowType
from app.orchestration.orchestrator import orchestrator
from app.skills.skill_registry import skill_registry
from app.services.token_tracking_service import token_tracking_service

logger = logging.getLogger(__name__)

# ── Workspace State Models ───────────────────────────────────────────────────

class WorkspaceMentorState(BaseModel):
    workspace_id: str
    state: str = "GATHERING_INFO"  # GATHERING_INFO | READY_TO_VALIDATE | VALIDATING | VALIDATED
    idea: Dict[str, Any] = Field(default_factory=lambda: {
        "idea_title": None,
        "idea_description": None,
        "problem_statement": None,
        "industry": "general",
        "founder_validation_goal": "validate my idea",
        "geography": "global"
    })
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    validation_result: Optional[Dict[str, Any]] = None


# Alias for backward compatibility
MentorSession = WorkspaceMentorState


# ── LLM Prompts ────────────────────────────────────────────────────────────────

EXTRACT_SYSTEM_PROMPT = """
You are a structured data extractor inside the Axiora Pulse AI Mentor system.
Your task is to analyze the conversation history between a founder and an AI mentor, and extract/update the founder's startup idea details.

Return ONLY a raw JSON object containing these keys:
- idea_title: A short, catchy name/title for the venture (string or null)
- idea_description: Clear description of what the venture does (string or null)
- problem_statement: The specific customer problem/pain point solved (string or null)
- target_customer: The specific customer persona or target audience (string or null)
- industry: Sector or industry (string, default "general")
- geography: Target market region or city (string, default "global")
- founder_evidence: Stated proof, customer conversations, interviews, waitlist, or pilot data (string or null)
- founder_validation_goal: What the founder wants to learn from validation (string, default "validate my idea")

- business_stage: Current development stage (e.g. "Idea / Concept", "Pre-MVP", "MVP Live", "Early Revenue", "Scaling", or null)
- current_monthly_revenue: Current monthly revenue/MRR (e.g. "Pre-Revenue ($0)", "$1,500/mo", "₹50,000/mo", or null)
- estimated_monthly_costs: Monthly operating expenses/burn (e.g. "Minimal <$500/mo", "$2,000/mo", "₹25,000/mo", or null)
- budget_range: Total available capital/budget (e.g. "Bootstrapped <$5,000", "$25,000", "₹10 Lakhs", or null)
- revenue_model_assumption: Planned monetization (e.g. "Direct Product Sales / D2C", "Recurring Subscription (SaaS)", "B2B Wholesale / Bulk Orders", "Freemium", "Commission / Marketplace Take-Rate", "Service / Retainer", or null)
- pricing_assumption: Target price point/subscription tier/unit price (e.g. "₹799 per bottle", "$25 / unit", "$9.99/mo", "$49/mo", "₹999/mo", "$1,500 per project", or null)

Guidelines:
1. SUPPORT BOTH PREDEFINED OPTIONS & CUSTOM MESSAGES:
   - The user may select an option number/label (e.g. "[1] Direct Product Sales", "Option 2", "freemium", "wholesale").
   - The user may also reply in free-form custom conversational text, custom numbers, or localized currencies (e.g. "we have around 10 lakhs in bank", "spending 30k INR on manufacturing and tools", "selling at ₹799 per bottle", "charging $25 per unit", "aiming for ₹1499 per year per user", "we are pre-revenue students").
   - Extract and normalize BOTH predefined selections and custom natural language inputs into concise, meaningful values.
2. SUPPORT ALL BUSINESS TYPES (Physical Products, D2C, E-commerce, Services, SaaS, Marketplaces):
   - For physical goods/e-commerce/D2C: Extract unit prices, wholesale tiers, and per-item direct sales accurately.
   - For software/SaaS: Extract monthly/annual subscription tiers, freemium, or usage-based pricing.
   - For services/consulting: Extract project fees, hourly rates, or monthly retainer figures.
3. If a field was extracted previously and the user hasn't modified it, keep it.
4. Only extract what the user has stated; do not invent or hallucinate metrics.
5. Return raw JSON ONLY. No markdown formatting like ```json ... ```. No extra text.

"""

# ── Dynamic workspace state block (appended to skill knowledge base) ─────────────

_WORKSPACE_STATE_TEMPLATE = """

══════════════════════════════════════════════════════
CURRENT WORKSPACE CONTEXT
══════════════════════════════════════════════════════

Workspace ID: {workspace_id}
Current Workflow State: {state}
Extracted Idea details: {idea_json}
Missing required fields to run validation: {missing_fields}

Optional Context Status (Geography / Evidence / Validation Goal): {optional_context_status}

State-Specific Instructions:
1. If state is GATHERING_INFO:
   - Ask clarifying, targeted questions to help the founder fill in the missing fields: {missing_fields}.
   - Ask only ONE or TWO clear questions at a time. Keep it conversational.
   - If they gave you a vague description, help them expand it.
   - Provide a useful insight after every two or three questions.
   - Follow the progressive disclosure rules from your knowledge base.

   - OPTIONAL CONTEXT QUESTIONS: Once the core idea fields are mostly clear, gently ask (in a single block, as optional):
     * "Where are you planning to launch first? (e.g., Hyderabad, Pan-India, Global — or skip for global default)"
     * "Have you spoken to any prospective customers, run any pilots, or gathered early evidence? (or skip — that's fine too)"
     * "What's the single biggest question or risk you want this validation to answer? (or skip for a general validation)"
     Make it clear these are optional — the founder can reply 'skip', leave them blank, or answer only some.
     If the founder already provided these (shown in Optional Context Status), do NOT ask again.

   - Acknowledge and validate the core idea gathered so far.
   - Explain politely that to run an accurate AI CFO and Financial Readiness analysis (real unit economics, runway scenarios, and break-even timelines), you need a few quick baseline financial details.
   - Ask for the missing financial fields: {missing_fields}.
   - DYNAMIC & CONTEXT-AWARE FINANCIAL OPTIONS (CRITICAL):
     Do NOT output a rigid generic list. Instead, first analyze the founder's specific idea, industry, and product/service type ({idea_json}), and DYNAMICALLY GENERATE 3 to 4 realistic, highly relevant options tailored directly to their venture:
     * For **Business Stage**: Generate 4-5 progressive stages relevant to their domain (e.g., Concept, Prototype/Sample, MVP/Beta testing, Initial sales/orders, Scaling).
     * For **Current Monthly Revenue**: Generate realistic revenue brackets with both USD and INR benchmarks ($0 / ₹0, <$1k / <₹1L, $1k-$10k / ₹1L-₹10L, $10k+ / ₹10L+).
     * For **Estimated Monthly Costs / Burn**: Generate realistic operational cost brackets for their model (e.g., minimal bootstrapping, lean operations, moderate burn, scaling).
     * For **Available Capital / Budget**: Generate relevant capital reserve brackets (e.g., savings <$5k / <₹5L, seed $5k-$25k / ₹5L-₹20L, funded $25k+ / ₹20L+).
     * For **Revenue Model** (DYNAMICALLY DETECT based on their idea):
       - If physical product / D2C / hardware / consumer goods (e.g. water bottles, fashion, electronics, food): Generate options like [1] Direct Product Sales (D2C / E-commerce per unit), [2] B2B Wholesale / Bulk Orders, [3] Retail Distribution, [4] Product Refill / Replenishment Subscription.
       - If SaaS / Software / Apps: Generate options like [1] Monthly/Annual Tiered Subscription, [2] Usage-based / Pay-as-you-go, [3] Freemium to Pro upgrade, [4] Enterprise Custom Licensing.
       - If Marketplace / Platform: Generate options like [1] Commission Take-Rate (% per transaction), [2] Listing / Subscription fees, [3] Premium placement.
       - If Services / Agency / Consulting: Generate options like [1] Fixed Project Fee, [2] Monthly Retainer, [3] Hourly Rate, [4] Performance-based cut.
       - If Hybrid or other: Generate blended options matching their exact offering.
     * For **Target Pricing** (DYNAMICALLY DETECT and suggest realistic price points for their specific product or service in both USD and local/INR currency):
       - Suggest 3-4 realistic price tiers or unit costs tailored to their specific product (e.g. for eco water bottles: [1] Standard bottle ($15 - $25 / ₹499 - ₹999), [2] Premium insulated ($30 - $50 / ₹1,299 - ₹2,499), [3] Bulk wholesale tier ($8 - $15 / ₹300 - ₹600 per unit, MOQ 50); for SaaS: $19-$49/mo, $99-$199/mo; for an agency: $1,000-$5,000/project).
   - ALWAYS SUPPORT CUSTOM RESPONSES:
     Explicitly let the founder know they can select an option number (e.g. '1', '2') OR simply describe their situation in their own custom words, numbers, or currencies.
   - Ask at most 2 financial categories at a time so the founder is not overwhelmed.
3. If state is READY_TO_VALIDATE:
   - Summarize the complete idea and financial parameters understood:
     * Idea & Problem
     * Business Stage, Revenue & Monthly Burn
     * Budget, Revenue Model & Target Pricing
   - Explain that all 4 specialist AI agents (Problem Validation, Market Research, Survey Intelligence, and Financial AI CFO) are ready to analyze the venture.
   - Tell them they can click the "Run Validation" button on the dashboard or reply "Run validation analysis".
4. If state is VALIDATING:
   - Let the user know the validation engine is processing their idea.
4. If state is VALIDATED:
   - Comment on the validation run result.
   - Summarize the final score ({validation_score}/100) and the verdict ({validation_verdict}).
   - Highlight the main strengths and the critical risks.
   - Give actionable advice on what they should address next.
   - Produce a practical 7-day action plan when appropriate.

Remember: Follow your complete knowledge base above for behaviour, response format,
questioning style, objective review protocol, and all guardrails.
"""


def _build_mentor_system_prompt(
    workspace_id: str,
    state: str,
    idea_json: str,
    missing_fields: str,
    validation_score: float = 0.0,
    validation_verdict: str = "N/A",
    optional_context_status: str = "Not yet provided",
) -> str:
    """Build the full mentor system prompt by combining the core mentor specification,
    the specific idea validation mentor subpart, and the dynamic workspace state."""
    core_skill = skill_registry.get("ai_mentor_core_skill")
    val_skill = skill_registry.get("ai_idea_validation_mentor_skill")

    parts = []

    if core_skill and core_skill.prompt_template:
        parts.append(core_skill.prompt_template)
        logger.info("[MentorService] Loaded ai_mentor_core_skill (%d chars)", len(core_skill.prompt_template))

    if val_skill and val_skill.prompt_template:
        parts.append(val_skill.prompt_template)
        logger.info("[MentorService] Loaded ai_idea_validation_mentor_skill subpart (%d chars)", len(val_skill.prompt_template))

    if not parts:
        logger.warning("[MentorService] Mentor skills not found — using minimal fallback prompt")
        knowledge_base = (
            "You are the Axiora Pulse AI Mentor & Co-Founder.\n"
            "Help the founder clarify, challenge, evaluate and validate their business idea.\n"
            "Be supportive, direct, evidence-driven and politely firm.\n"
            "Never guarantee success or give legal, tax or investment advice.\n"
        )
    else:
        knowledge_base = "\n\n".join(parts)

    # Append the dynamic workspace context
    workspace_block = _WORKSPACE_STATE_TEMPLATE.format(
        workspace_id=workspace_id,
        state=state,
        idea_json=idea_json,
        missing_fields=missing_fields,
        validation_score=validation_score,
        validation_verdict=validation_verdict,
        optional_context_status=optional_context_status,
    )

    return knowledge_base + workspace_block


# ── Service Implementation ─────────────────────────────────────────────────────

from app.models.workspace_models import AttachmentInput
from app.services.attachment_processor import attachment_processor

class MentorService:
    """Manages workspace-scoped dialogue state and LLM extraction/generation loop."""

    def __init__(self):
        self._llm = None  # Lazy-initialized on first use to avoid startup crashes

    @property
    def llm(self):
        """Lazily resolve the LLM gateway on first access."""
        if self._llm is None:
            self._llm = get_llm_gateway()
        return self._llm

    async def process_message(
        self,
        state: WorkspaceMentorState,
        user_message: str,
        attachments: Optional[List[AttachmentInput]] = None,
        user_id: Optional[int] = None,
        db: Optional[Any] = None,
    ) -> WorkspaceMentorState:
        logger.info(
            "[MentorService] Processing message for workspace '%s' user_id='%s' (state=%s, message_len=%s)",
            state.workspace_id, user_id, state.state, len(user_message or ""),
        )
        # Process incoming attachments (PDFs via pdfplumber, Docs, Links, Images)
        processed_attachments, attachment_text_context, image_data_uris = (
            await attachment_processor.process_attachments(
                attachments=attachments or [],
                workspace_id=state.workspace_id,
                user_id=user_id,
                db=db,
            )
        )

        # Build full content for user message including attachment context
        full_content = user_message
        if attachment_text_context:
            full_content = f"{user_message}\n\n[Attached Information Context]:\n{attachment_text_context}"

        # Create user message dict for conversation history
        user_msg_record: Dict[str, Any] = {"role": "user", "content": full_content}
        if processed_attachments:
            user_msg_record["attachments"] = [p.model_dump() for p in processed_attachments]

        state.conversation_history.append(user_msg_record)

        # Check for system trigger or manual validation command in text
        is_trigger_command = "[TRIGGER_VALIDATION]" in user_message or user_message.lower().strip() in (
            "run validation", "run validation analysis", "validate", "validate idea", "start validation"
        )


        if is_trigger_command and state.state == "READY_TO_VALIDATE":
            state.state = "VALIDATING"
            logger.info(f"[MentorService] State GATHERING_INFO -> VALIDATING for workspace {state.workspace_id}")
            
            try:
                # Prepare and trigger orchestration
                idea_input = IdeaInput(
                    idea_title=state.idea.get("idea_title") or "Unnamed Venture",
                    idea_description=state.idea.get("idea_description") or "No description provided.",
                    problem_statement=state.idea.get("problem_statement") or "No problem statement.",
                    target_customer=state.idea.get("target_customer"),
                    industry=state.idea.get("industry") or "general",
                    geography=state.idea.get("geography") or "global",
                    founder_evidence=state.idea.get("founder_evidence"),
                    founder_validation_goal=state.idea.get("founder_validation_goal") or "validate my idea",
                    additional_context={
                        "target_customer": state.idea.get("target_customer"),
                        "industry": state.idea.get("industry") or "general",
                        "geography": state.idea.get("geography") or "global",
                        "founder_evidence": state.idea.get("founder_evidence"),
                        "founder_validation_goal": state.idea.get("founder_validation_goal") or "validate my idea",
                        "business_stage": state.idea.get("business_stage"),
                        "current_monthly_revenue": state.idea.get("current_monthly_revenue"),
                        "estimated_monthly_costs": state.idea.get("estimated_monthly_costs"),
                        "budget_range": state.idea.get("budget_range"),
                        "revenue_model_assumption": state.idea.get("revenue_model_assumption"),
                        "pricing_assumption": state.idea.get("pricing_assumption"),
                    }

                )

                request = OrchestrationRequest(
                    user_id=user_id,
                    workspace_id=state.workspace_id,
                    idea_id=f"idea-{uuid.uuid4().hex[:8]}",
                    workflow_type=WorkflowType.IDEA_VALIDATION,
                    idea=idea_input
                )

                orchestrator_resp = await orchestrator.run(request)
                if orchestrator_resp.status == "success" and orchestrator_resp.result:
                    state.validation_result = json.loads(orchestrator_resp.result.json())
                    state.state = "VALIDATED"
                else:
                    state.state = "READY_TO_VALIDATE"
                    state.conversation_history.append({
                        "role": "assistant",
                        "content": f"I tried to run the validation analysis, but the orchestrator returned an error: {orchestrator_resp.error or 'Unknown failure'}. Let's try again when you are ready."
                    })
                    return state

            except Exception as e:
                logger.error(f"[MentorService] Orchestration run crashed: {e}", exc_info=True)
                state.state = "READY_TO_VALIDATE"
                state.conversation_history.append({
                    "role": "assistant",
                    "content": "I encountered an unexpected error running the validation engine. Let's try triggering it again."
                })
                return state

        # If we are gathering info, run the Information Extractor first
        if state.state == "GATHERING_INFO":
            await self._run_extraction(state, user_id=user_id, db=db)

        # Generate conversational response
        await self._generate_mentor_reply(state, image_data_uris=image_data_uris, user_id=user_id, db=db)
        return state

    async def _run_extraction(
        self,
        state: WorkspaceMentorState,
        user_id: Optional[int] = None,
        db: Optional[Any] = None,
    ) -> None:
        """Helper to scan conversation history and extract idea details."""
        history_str = ""
        for msg in state.conversation_history[-6:]:  # focus on recent history for context
            history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"

        prompt = f"Existing Idea Context:\n{json.dumps(state.idea, indent=2)}\n\nConversation History:\n{history_str}\n"

        try:
            req = LLMRequest(
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_format="json",
                temperature=0.1
            )
            res = await self.llm.complete(req)

            # Record token usage if db and user_id available
            if db and user_id and (res.tokens_input > 0 or res.tokens_output > 0 or res.total_tokens > 0):
                ws_id_int = int(state.workspace_id) if str(state.workspace_id).isdigit() else None
                await token_tracking_service.record_usage(
                    db=db,
                    user_id=user_id,
                    workspace_id=ws_id_int,
                    source="idea_extraction",
                    agent_name="idea_extractor",
                    provider=res.provider or "openai",
                    model=res.model or "gpt-5.4-mini",
                    prompt_tokens=res.tokens_input,
                    completion_tokens=res.tokens_output,
                    metadata={"workspace_state": state.state},
                )

            if res.success and res.content:
                # Parse JSON
                cleaned_content = self._clean_json_str(res.content)
                parsed = json.loads(cleaned_content)
                
                # Merge parsed values back into state.idea (only non-null fields)
                for k, v in parsed.items():
                    if v is not None and v != "":
                        state.idea[k] = v

                # Log which fields changed, never the founder's idea content itself.
                logger.info(
                    "[MentorService] Workspace '%s' idea fields updated: %s",
                    state.workspace_id, sorted(parsed.keys()),
                )

                # Programmatic check of required fields
                required = ["idea_title", "idea_description", "problem_statement"]
                missing = [f for f in required if not state.idea.get(f)]
                if not missing:
                    state.state = "READY_TO_VALIDATE"
                    logger.info(f"[MentorService] All required fields satisfied for workspace '{state.workspace_id}'! State -> READY_TO_VALIDATE")

        except Exception as e:
            logger.warning(f"[MentorService] Extraction step failed: {e}. Continuing conversation without it.")

    async def _generate_mentor_reply(
        self,
        state: WorkspaceMentorState,
        image_data_uris: Optional[List[str]] = None,
        user_id: Optional[int] = None,
        db: Optional[Any] = None,
    ) -> None:
        """Call LLM with current workspace state to write assistant response."""
        # Find missing required fields
        required = ["idea_title", "idea_description", "problem_statement"]
        missing = [f.replace("_", " ").title() for f in required if not state.idea.get(f)]

        # Get validation context if we just validated
        score = 0.0
        verdict = "N/A"
        if state.state == "VALIDATED" and state.validation_result:
            score = state.validation_result.get("validation_score", 0.0)
            verdict = str(state.validation_result.get("verdict", "hold")).upper()

        # Build optional context status — tells Arya which soft fields are filled vs still needed
        _geo = state.idea.get("geography")
        _evidence = state.idea.get("founder_evidence")
        _goal = state.idea.get("founder_validation_goal")
        optional_parts = []
        optional_parts.append(
            f"Geography: {'\"' + _geo + '\" (provided)' if _geo and _geo != 'global' else 'Not yet provided (will default to global)'}"
        )
        optional_parts.append(
            f"Early Evidence: {'\"' + _evidence + '\" (provided)' if _evidence else 'Not yet provided (will default to none)'}"
        )
        optional_parts.append(
            f"Validation Goal: {'\"' + _goal + '\" (provided)' if _goal and _goal != 'validate my idea' else 'Not yet provided (will default to general validation)'}"
        )
        optional_context_status = " | ".join(optional_parts)

        sys_prompt = _build_mentor_system_prompt(
            workspace_id=state.workspace_id,
            state=state.state,
            idea_json=json.dumps(state.idea, indent=2),
            missing_fields=", ".join(missing) if missing else "None",
            validation_score=score,
            validation_verdict=verdict,
            optional_context_status=optional_context_status,
        )

        # Build prompt using chat messages
        user_prompt = "Generate the next mentor message. Here is the recent chat history:\n"
        for msg in state.conversation_history[-10:]:
            user_prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
        user_prompt += "Assistant:"

        try:
            req = LLMRequest(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                images=image_data_uris,
            )
            res = await self.llm.complete(req)

            # Record token usage if db and user_id available
            if db and user_id and (res.tokens_input > 0 or res.tokens_output > 0 or res.total_tokens > 0):
                ws_id_int = int(state.workspace_id) if str(state.workspace_id).isdigit() else None
                await token_tracking_service.record_usage(
                    db=db,
                    user_id=user_id,
                    workspace_id=ws_id_int,
                    source="mentor_chat",
                    agent_name="ai_mentor",
                    provider=res.provider or "openai",
                    model=res.model or "gpt-5.4-mini",
                    prompt_tokens=res.tokens_input,
                    completion_tokens=res.tokens_output,
                    metadata={"workspace_state": state.state},
                )

            if res.success and res.content:
                reply = res.content.strip()
                # Clean prefix "Assistant:" if model output it
                if reply.startswith("Assistant:"):
                    reply = reply[len("Assistant:"):].strip()
                state.conversation_history.append({"role": "assistant", "content": reply})
            else:
                state.conversation_history.append({
                    "role": "assistant",
                    "content": "I'm here! Tell me more about your startup idea, and we can validate it together."
                })
        except Exception as e:
            logger.error(f"[MentorService] Failed to generate mentor response: {e}", exc_info=True)
            state.conversation_history.append({
                "role": "assistant",
                "content": "I'm having trouble connecting to my brain right now. Can you try again?"
            })

    def _clean_json_str(self, text: str) -> str:
        """Strip markdown wrapping (e.g. ```json ... ```) to extract raw JSON block."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group()
        return text


# Global singleton service
mentor_service = MentorService()
