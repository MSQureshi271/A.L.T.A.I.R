"""
backend/app/scratch/test_context.py — Verification script for SessionContext and reference resolution.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to python path
sys.path.append(str(Path(__file__).parents[2]))

from dotenv import load_dotenv
load_dotenv()

from app.ai.reasoning.context_resolver import resolve_session_context
from app.ai.planner.planner import plan as planner_plan


async def run_test():
    print("Testing SessionContext resolution from history...")

    # Mock history where Sarah is mentioned with her email
    history = [
        {"role": "user", "text": "Check email from Sarah Ahmed (sarah@acme.com) please"},
        {"role": "model", "text": "Sure, I found 3 emails from Sarah Ahmed."},
    ]

    # Resolve context
    user_id = "DEV_USER_ID"
    context = resolve_session_context(history, user_id)

    print("\n--- Resolved Context Attributes ---")
    print(f"Last Mentioned People: {context.last_mentioned_people}")
    print(f"Upcoming Events: {context.upcoming_events}")
    print(f"Last Action: {context.last_action}")
    print(f"Active Plan ID: {context.active_plan_id}")

    # Check if context resolver successfully parsed Sarah
    assert len(context.last_mentioned_people) > 0, "Failed: Mentioned people list empty"
    assert context.last_mentioned_people[0]["email"] == "sarah@acme.com", "Failed: Email mismatch"
    print("OK: Context Resolver successfully extracted Sarah Ahmed from history logs!")

    print("\n--- Calling Planner to verify Pronoun Resolution ('her' -> sarah@acme.com) ---")
    # Follow up query using pronoun 'her'
    user_query = "Draft a reply to her saying I'll review it"

    try:
        task_plan = planner_plan(user_query, history=history)
        print(f"Planner intent: {task_plan.intent_summary}")
        print(f"Steps: {task_plan.steps}")

        # Check if the generated email step points to sarah@acme.com
        email_step = next((s for s in task_plan.steps if s.action == "draft_email"), None)
        assert email_step is not None, "Failed: Planner did not generate a draft_email step"
        
        recipient = email_step.parameters.get("recipient", "")
        print(f"Resolved recipient: {recipient}")
        assert "sarah@acme.com" in recipient, f"Failed: Recipient was resolved to '{recipient}' instead of 'sarah@acme.com'"
        
        print("\nSUCCESS! Gemini successfully resolved 'her' -> 'sarah@acme.com' using the SessionContext!")
    except Exception as exc:
        print(f"\nTest Failed: {exc}")


if __name__ == "__main__":
    asyncio.run(run_test())
