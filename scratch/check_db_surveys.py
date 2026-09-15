import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import AsyncSessionLocal
from app.db.models import Survey, Workspace
from sqlalchemy import select

async def check_surveys():
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Survey).order_by(Survey.id.desc()).limit(10))
            surveys = res.scalars().all()
            print(f"Total surveys found: {len(surveys)}")
            for s in surveys:
                print(f"\n=== Survey ID: {s.id}, Workspace ID: {s.workspace_id}, Questions Count: {len(s.questions or [])} ===")
                texts = [q.get("question") or q.get("question_text") for q in (s.questions or [])]
                for i, t in enumerate(texts, 1):
                    print(f"  {i}. {t}")
                seen = {}
                for i, t in enumerate(texts, 1):
                    norm = str(t).lower().strip().rstrip("?")
                    if norm in seen:
                        print(f"  *** DUPLICATE FOUND: Q{i} duplicates Q{seen[norm]}: '{t}' ***")
                    else:
                        seen[norm] = i

            # Also check workspaces validation_result
            ws_res = await db.execute(select(Workspace).order_by(Workspace.id.desc()).limit(10))
            workspaces = ws_res.scalars().all()
            print(f"\nTotal workspaces found: {len(workspaces)}")
            for w in workspaces:
                val = w.validation_result or {}
                agent_res = val.get("agent_results") or {}
                survey_agent = agent_res.get("survey_intelligence_agent") or {}
                survey_data = survey_agent.get("data") or {}
                qs = survey_data.get("questions") or []
                if qs:
                    print(f"\n=== Workspace {w.id} ({w.name}): {len(qs)} questions in validation_result ===")
                    ws_texts = [q.get("question_text") or q.get("question") for q in qs]
                    seen_ws = {}
                    for i, t in enumerate(ws_texts, 1):
                        print(f"  {i}. {t}")
                        norm = str(t).lower().strip().rstrip("?")
                        if norm in seen_ws:
                            print(f"  *** DUPLICATE FOUND IN WORKSPACE: Q{i} duplicates Q{seen_ws[norm]}: '{t}' ***")
                        else:
                            seen_ws[norm] = i
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_surveys())
