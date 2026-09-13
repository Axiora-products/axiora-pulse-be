import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent
from app.llm.llm_gateway import get_llm_gateway
from app.models.agent_models import AgentInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_live_test():
    gateway = get_llm_gateway()
    agent = SurveyIntelligenceAgent(gateway)
    
    agent_input = AgentInput(
        idea_title="PetCare AI - Smart Health Monitor for Dogs",
        idea_description="AI-powered wearable collar for dogs that monitors vital health metrics and alerts owners to early disease signs.",
        problem_statement="Pet owners notice illnesses too late, leading to high vet bills and severe health outcomes for dogs.",
        target_customer="Dog owners aged 25-50 who spend on premium pet care",
        founder_validation_goal="Validate willingness to pay $15/month subscription for health tracking collar.",
    )
    
    logger.info("Running SurveyIntelligenceAgent live execution...")
    result = await agent.run(agent_input)
    
    logger.info("Agent Status: %s", result.status)
    logger.info("Execution Error: %s", result.error)
    
    output = result.data or {}
    logger.info("Survey Quality Score: %s", result.score)
    logger.info("Survey Title: %s", output.get("survey_title"))
    
    questions = output.get("questions", [])
    logger.info("Total Questions Generated: %s", len(questions))
    seen = {}
    duplicates = []
    for i, q in enumerate(questions, 1):
        q_text = (q.get("question_text") or q.get("question") or "").strip()
        norm_text = q_text.lower().rstrip("?").strip()
        if norm_text in seen:
            duplicates.append((seen[norm_text], i, q_text))
        else:
            seen[norm_text] = i
        print(f"[{i}] ({q.get('question_type')}): {q_text}")
        if q.get("options"):
            print(f"    Options: {q.get('options')}")
    
    if duplicates:
        print(f"\n*** DUPLICATE QUESTIONS DETECTED: {len(duplicates)} ***")
        for orig_idx, dup_idx, txt in duplicates:
            print(f"Duplicate between Q{orig_idx} and Q{dup_idx}: {txt}")
    else:
        print("\nNo exact string duplicates detected.")

if __name__ == "__main__":
    asyncio.run(run_live_test())
