"""
backend/app/scratch/test_dag.py — Verification script for DAG execution and parameter interpolation.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to python path
sys.path.append(str(Path(__file__).parents[2]))

import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from app.ai.planner.planner_schema import TaskPlan, TaskStep
from app.ai.executor.executor import execute_plan, load_active_plan, save_active_plan

# Mock the actual gmail send so we don't send emails during test runs
import app.main
original_execute_write = app.main._execute_write_step_action
app.main._execute_write_step_action = lambda action, parameters, user_id: f"[Mock Executed {action} with parameters {parameters}]"

async def run_test():
    print("Initializing test TaskPlan...")
    
    # Define a 2-step plan: Step 2 depends on Step 1 output
    step1 = TaskStep(
        step_id=1,
        tool="search",
        action="search_web",
        parameters={"query": "Super Bowl score 2026"},
        requires_confirmation=False,
        depends_on=[],
        description="Search Super Bowl score",
        status="pending"
    )
    
    step2 = TaskStep(
        step_id=2,
        tool="gmail",
        action="draft_email",
        parameters={
            "recipient": "test@example.com",
            "subject": "Super Bowl updates",
            "body": "Here is what I found: $step_1"
        },
        requires_confirmation=True,
        depends_on=[1],
        description="Draft email with search results",
        status="pending"
    )
    
    plan = TaskPlan(
        intent_summary="Search Super Bowl and email Danish",
        steps=[step1, step2]
    )
    
    print("\n--- PHASE 1: Run Initial Plan (Executes Step 1, Stages Step 2) ---")
    plan_id = None
    step_id_awaiting = None
    
    async for event in execute_plan(plan, user_text="Search super bowl and email danish"):
        print(f"Event: {event}")
        if event.get("type") == "plan":
            plan_id = event["plan"].get("plan_id")
        if event.get("type") == "approval_required":
            plan_id = event["data"].get("plan_id")
            step_id_awaiting = event["data"].get("step_id")
            
    print(f"\nStaged Plan ID: {plan_id}")
    print(f"Awaiting approval for Step ID: {step_id_awaiting}")
    
    if not plan_id or not step_id_awaiting:
        print("Test failed: No plan or approval was staged.")
        return
        
    print("\n--- PHASE 2: Load Staged Plan state from Database ---")
    staged_plan = load_active_plan(plan_id)
    if not staged_plan:
        print("Test failed: Staged plan could not be loaded from store.")
        return
        
    print(f"Loaded Plan Intent: {staged_plan.intent_summary}")
    print(f"Step 1 Status (Expected completed): {staged_plan.steps[0].status}")
    print(f"Step 1 Output: {staged_plan.steps[0].output}")
    print(f"Step 2 Status (Expected running): {staged_plan.steps[1].status}")
    print(f"Step 2 Parameters (Pre-interpolation): {staged_plan.steps[1].parameters}")

    print("\n--- PHASE 3: Simulate Approval and Resume Plan execution ---")
    
    # We call the resume flow helper directly or via mock
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Call the actual resume SSE endpoint using TestClient
    print("Calling POST /agent/resume-plan...")
    response = client.post(
        "/agent/resume-plan",
        json={"plan_id": plan_id, "step_id": step_id_awaiting}
    )
    
    print(f"Resume Response Code: {response.status_code}")
    print("Streamed SSE Events:")
    for line in response.iter_lines():
        if line.startswith("data: "):
            print(line)
            
    print("\n--- PHASE 4: Verify Final Completed Plan state ---")
    final_plan = load_active_plan(plan_id)
    print(f"Step 2 Status (Expected completed): {final_plan.steps[1].status}")
    print(f"Step 2 Parameters (Post-interpolation): {final_plan.steps[1].parameters}")
    print(f"Step 2 Output: {final_plan.steps[1].output}")

    if final_plan.steps[1].status == "completed" and "Super Bowl" in str(final_plan.steps[1].parameters["body"]):
        print("\n🎉 SUCCESS! DAG execution and parameter interpolation worked perfectly!")
    else:
        print("\n❌ FAILED: Interpolation or execution status incorrect.")

if __name__ == "__main__":
    asyncio.run(run_test())
