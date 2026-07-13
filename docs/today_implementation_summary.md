# Axiora Pulse — Today's Technical Implementation Summary & API Specification

**Date:** July 4, 2026  
**Project:** Core AI Orchestration Engine (Phase 1 Backend Architecture)  


---

## 1. User Story

### Title: Founder Idea Validation Run
**As a** Startup Founder using the Axiora Pulse platform,  
**I want to** submit my business idea details to a structured validation engine,  
**So that** I can get an objective, weighted validation score, clear risk flags, customer hypotheses, and action-oriented next steps instead of a generic chat response.

### Acceptance Criteria:
1. **Endpoint Access**: The engine must expose a single API endpoint `POST /api/v1/orchestration/run` that accepts structured details about my idea (title, description, problem, target customer).
2. **Model Agnostic Gateway**: The engine must process my request using a local or cloud LLM provider (defaulting to Llama-3.1-8B via Hugging Face Router for Phase 1) without coupling agent logic directly to the provider SDK.
3. **Structured Review**: An **Idea Validation Agent** must parse the input, run a specific "Idea Validation Skill" template, validate JSON formatting safely, and supply structured analytics.
4. **Deterministic Scoring**: A **Validation Engine** must compute a weighted final validation score, map it to a clear verdict (e.g. `validate_more`, `build`), list critical assumptions, strengths, red flags, and generate a founder-friendly mentor summary.
5. **Fail-safe Execution**: The API must return a structured response containing validation details, execution metadata (tokens used, latency), and standard liability disclaimers, even if downstream tools or models time out.

---

## 2. API Specification

Today we implemented three main API routers under FastAPI. The endpoints are as follows:

### 2.1 Global Engine Health Check
* **Endpoint**: `GET /health`
* **Purpose**: Verifies that the server is active, scans the filesystem, lists loaded skills, checks default LLM provider configurations, and verifies overall subsystem readiness.

#### Example Response:
```json
{
  "status": "healthy",
  "app": "Axiora Pulse AI Engine",
  "version": "1.0.0",
  "llm_provider": "huggingface",
  "llm_model": "meta-llama/Llama-3.1-8B-Instruct",
  "skills_loaded": [
    "financial_readiness_skill",
    "gtm_strategy_skill",
    "idea_validation_skill",
    "market_research_skill",
    "survey_intelligence_skill"
  ],
  "skills_count": 5,
  "provider_configured": true
}
```

---

### 2.2 Run Orchestrated Idea Validation
* **Endpoint**: `POST /api/v1/orchestration/run`
* **Headers**: `Content-Type: application/json`
* **Payload Structure (`OrchestrationRequest`)**:
  * `workspace_id` (string, optional, UUID auto-generated): Workspace reference.
  * `idea_id` (string, optional, UUID auto-generated): Target idea reference.
  * `workflow_type` (enum: `"idea_validation"`, `"survey_generation"`, `"survey_analytics"`, `"report_generation"`): Target pipeline to run.
  * `idea` (object, required):
    * `idea_title` (string, required): Short name of the venture.
    * `idea_description` (string, required): Comprehensive explanation.
    * `problem_statement` (string, required): The pain point being addressed.
    * `target_customer` (string, required): Who suffers from this pain.
    * `industry` (string, optional, default: `"general"`): Market sector.
    * `founder_validation_goal` (string, optional): What the founder wishes to prove.
    * `geography` (string, optional, default: `"global"`): Target geographic range.

#### Example Request Payload:
```json
{
  "workflow_type": "idea_validation",
  "idea": {
    "idea_title": "Healthy Office Lunch Delivery Subscription",
    "idea_description": "A weekly meal subscription service delivering freshly cooked organic healthy lunches to corporate offices.",
    "problem_statement": "Office workers aged 25-40 struggle to find healthy, fast, and affordable lunch options during high-stress working hours.",
    "target_customer": "Corporate employees and busy professionals working in major commercial hubs.",
    "industry": "Food & Wellness",
    "founder_validation_goal": "Validate price elasticity and willingness-to-pay a monthly premium subscription.",
    "geography": "North America"
  }
}
```

#### Example Success Response (`OrchestrationResponse` containing `ValidationResult`):
```json
{
  "run_id": "97e68cf0-2cf8-4d56-a05f-0d85a1a196e8",
  "workspace_id": "038fb50b-8d07-4228-b997-6a2c6d48c8b6",
  "idea_id": "76495db3-6f87-47b2-8406-38d77d70c406",
  "workflow_type": "idea_validation",
  "status": "success",
  "result": {
    "idea_id": "76495db3-6f87-47b2-8406-38d77d70c406",
    "orchestration_run_id": "97e68cf0-2cf8-4d56-a05f-0d85a1a196e8",
    "validation_score": 75.0,
    "confidence_rating": 0.85,
    "verdict": "validate_more",
    "strengths": [
      "Clear problem identified: Office workers aged 25-40 struggle to find healthy, fast, and affordable lunch options during high-stress working hours.",
      "Customer hypothesis defined: Corporate employees and busy professionals working in major commercial hubs."
    ],
    "risks": [
      "Operational overhead of meal preparation and delivery logistics.",
      "Pricing pressure from existing local fast-food chains."
    ],
    "assumptions": [
      "Busy professionals will pay a premium for organic, pre-ordered meals.",
      "Employers will allow daily access to delivery staff in office high-rises."
    ],
    "recommendations": [
      "Idea validation analysis suggests: Proceed To Validation",
      "Create a short validation survey and target 20–30 potential customers.",
      "Validate the top 2–3 assumptions before investing in development."
    ],
    "agent_results": {
      "idea_validation_agent": {
        "score": 75.0,
        "confidence": 0.85,
        "data": {
          "idea_clarity_score": 75,
          "problem_summary": "Office professionals lack easy access to healthy meal options during work hours.",
          "customer_hypothesis": "Corporate employees will pay premium rates for nutritional compliance and convenience.",
          "key_assumptions": [
            "Busy professionals will pay a premium for organic, pre-ordered meals.",
            "Employers will allow daily access to delivery staff in office high-rises."
          ],
          "red_flags": [
            "Operational overhead of meal preparation and delivery logistics.",
            "Pricing pressure from existing local fast-food chains."
          ],
          "initial_recommendation": "proceed_to_validation",
          "confidence": 0.85,
          "disclaimer": "This is decision-support guidance only, not professional business advice."
        },
        "model_used": "meta-llama/Llama-3.1-8B-Instruct",
        "tokens_input": 650,
        "tokens_output": 280,
        "executed_at": "2026-07-04T13:46:12.345678"
      }
    },
    "mentor_summary": "[Validation Score: 75/100 — VALIDATE MORE]\n\nYour idea has real potential, but some critical assumptions still need testing. I recommend running a short validation survey with your target customers before committing to building. Key risk to address: Operational overhead of meal preparation and delivery logistics. Suggested next step: Idea validation analysis suggests: Proceed To Validation\n\n\n⚠ This is decision-support guidance only — not professional business, legal, financial, or investment advice.",
    "disclaimer": "This is educational and decision-support guidance only. It is not legal, tax, accounting, banking, investment, loan, or professional financial advice.",
    "created_at": "2026-07-04T13:46:12.987654"
  },
  "error": null,
  "started_at": "2026-07-04T13:46:11.123456",
  "completed_at": "2026-07-04T13:46:12.987654"
}
```

---

### 2.3 AI Mentor Chat (Phase 1 Placeholder)
* **Endpoint**: `POST /api/v1/mentor/chat`
* **Purpose**: Accepts free-text chat inputs and returns a structured response prompting the user to run the formal validation endpoint instead.

---

## 3. What Was Implemented Today

1. **Clean Directory Structuring**: Created standard directories representing modules (`api/v1/`, `core/`, `orchestration/`, `agents/`, `skills/`, `mcp/`, `llm/`, `guardrails/`, `models/`, `workers/`) along with standard package entry files (`__init__.py`).
2. **Unified Configuration**: Implemented Pydantic-based `Settings` reading from `.env` dynamically, with strict model schema validation.
3. **Model-Agnostic LLM Gateway**: Built an abstract factory architecture allowing the backend to swap between HuggingFace Router endpoints (Llama-3.1-8B) and OpenAI (gpt-4o-mini) on the fly via configuration variables.
4. **HuggingFace Llama Router Integration**: Configured connections to `https://router.huggingface.co/v1` to utilize stable, partner-hosted model instances. Added robust regex-based JSON extraction filters to strip markdown blocks (```json ... ```) and extract raw dictionaries, working around Llama's lack of a native JSON output API parameter.
5. **Runtime Skill Loading**: Built a YAML-based `SkillRegistry` reading declarative prompts and validations at startup. This decouples logic from hardcoded templates.
6. **Unified Agent Runtime**: Implemented the base agent abstract class dictating a standard 5-step loop (load skill -> build prompt -> run gateway -> parse -> return output) along with robust fallback error metrics (preventing LLM failures from breaking the overall request).
7. **FastAPI Engine Setup**: Wired the app lifecycle events to verify credentials, setup structured logs, compile CORS guidelines, and run standard validation routers.

---

## 4. Metrics & Scoring Calculation Logic

The engine uses a combination of **semantic model evaluation** and **deterministic weighted scoring logic** to formulate validation results.

### 4.1 Agent Semantic Evaluation (LLM-Side)
When an agent runs, it delegates scoring criteria to the model using the rules configured in the skill's YAML file:
* **`idea_clarity_score` (0 - 100)**: Evaluated based on the specificity of the problem statement, primary customer segment clarity, and solution feasibility.
* **`confidence` (0.0 - 1.0)**: Sized dynamically based on the information density and presence of optional contextual parameters.

#### Code-Level Sanitization:
Once parsed, the agent enforces schema integrity:
```python
# Score and confidence clamping
score = max(0.0, min(100.0, float(raw_score)))
confidence = max(0.0, min(1.0, float(raw_confidence)))
```

### 4.2 Overall Validation Score (Orchestrator-Side)
The final validation score is computed by the `ValidationEngine` using a weighted average across all active agents:

$$\text{Validation Score} = \frac{\sum (\text{Agent Score} \times \text{Agent Weight})}{\sum \text{Agent Weight}}$$

#### Weighted Matrix:
* **Idea Validation Agent**: `20%` (set to `100%` in Phase 1 as the single active agent)
* **Market Research Agent**: `20%`
* **Survey Intelligence Agent**: `25%`
* **GTM Strategy Agent**: `15%`
* **Financial Readiness Agent**: `20%`

### 4.3 Verdict Mapping
The validation score is mapped to one of the following decisions:
* **80 – 100**: `BUILD` (Strong validation signals; build an MVP)
* **60 – 79**: `VALIDATE_MORE` (Moderate signals; test assumptions with a survey)
* **40 – 59**: `REDUCE_SCOPE` (Weak signals; narrow down segment or problem focus)
* **0 – 39**: `HOLD` (Very weak signals; clarify details first)

