# A.L.T.A.I.R. — Engineering Roadmap

> **A**utonomous **L**anguage-driven **T**ask **A**gent with **I**ntelligent **R**easoning
>
> *A comprehensive development plan from our current Phase 1 baseline toward a fully autonomous, context-aware, multi-step planning assistant.*

---

## Where We Are Today (Phase 1 Baseline)

The current system has the following working components:

| Layer | What Exists |
|---|---|
| **Flutter Frontend** | Voice input (STT), chat UI, human-in-the-loop approval drawer, auth flow, connectors page, left-side drawer |
| **Backend** | FastAPI + SSE streaming, Gemini 2.5 Flash tool-calling loop, conversation history (in-memory, 10 turns) |
| **Auth** | Google OAuth (Gmail + Calendar), token storage (Supabase or local cache) |
| **Tools** | `stage_email`, `read_emails`, `send_email_via_gmail`, `get_calendar_events`, `create_calendar_event`, `search_web` |
| **HITL** | `stage_email` → approval drawer → `/agent/execute-action` |

**Current data flow:**
```
Voice → STT (device) → text → POST /agent/text → Gemini tool loop → SSE events → Flutter UI
```

---

## Phase 2 — Intent & Structured Planning

> *Goal: Replace free-form Gemini function dispatch with a deterministic planner that emits structured task graphs before execution begins.*

### Why This Matters

Currently, Gemini decides *what to do* and *how to do it* in a single, unconstrained pass. Adding a dedicated Planner:
- Makes intent extraction testable independently of tool execution.
- Lets us intercept and show the plan to the user before **anything** runs.
- Creates a stable interface so that tools, memory, and safety layers can be added without touching each other.

---

### Task 2.1 — Define the Task Plan Schema (Backend)

**File:** `backend/app/agents/planner_schema.py` *(NEW)*

Define a Pydantic model for the structured plan that the Planner Agent will produce:

```python
from pydantic import BaseModel
from typing import Literal

class TaskStep(BaseModel):
    step_id: int
    tool: Literal["gmail", "calendar", "search", "memory", "none"]
    action: str                        # e.g. "draft_email", "create_event"
    parameters: dict                   # raw arguments for the executor
    requires_confirmation: bool = True # must user approve before execution?
    depends_on: list[int] = []        # step_ids this step must wait for

class TaskPlan(BaseModel):
    intent_summary: str               # one-sentence description for the UI
    steps: list[TaskStep]
    ambiguity_question: str | None = None  # if the plan cannot be formed yet
```

---

### Task 2.2 — Build the Planner Agent (Backend)

**File:** `backend/app/agents/planner.py` *(NEW)*

The Planner is a **separate Gemini call** with a different system prompt and a JSON-only output mode (`response_mime_type="application/json"`, `response_schema=TaskPlan`). It does **not** call any tools — its sole job is structured reasoning.

```python
from google.genai import types
from app.agents.planner_schema import TaskPlan

PLANNER_SYSTEM_PROMPT = """
You are the Planner for A.L.T.A.I.R., an AI productivity assistant.

Your job is to read the user's voice command (possibly with conversation history
for context) and produce a structured JSON task plan.

Rules:
- Only include steps that are genuinely needed.
- If you need information from the user to complete the plan, set
  ambiguity_question and return zero steps.
- Mark requires_confirmation=true for all write/send/delete actions.
- Mark requires_confirmation=false only for read-only lookups.
- Infer dates relative to today's date (provided in the prompt).
"""

def plan(user_text: str, history: list[dict], today_str: str) -> TaskPlan:
    """Return a structured TaskPlan for the user's command."""
    client = _build_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_build_contents(user_text, history, today_str),
        config=types.GenerateContentConfig(
            system_instruction=PLANNER_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=TaskPlan,
            temperature=0.0,
        ),
    )
    return TaskPlan.model_validate_json(response.text)
```

---

### Task 2.3 — Build the Executor (Backend)

**File:** `backend/app/agents/executor.py` *(NEW)*

The Executor processes a `TaskPlan`, step by step. It:
1. Checks `requires_confirmation` — if `true`, yields an `approval_required` event and pauses.
2. Executes tool calls for read-only steps immediately.
3. Handles `depends_on` to ensure step ordering.
4. Returns results to feed back into the Planner for multi-step plans.

```python
def execute_plan(plan: TaskPlan, user_id: str) -> Generator[dict, None, None]:
    results = {}
    for step in plan.steps:
        # Wait for dependencies
        for dep_id in step.depends_on:
            if dep_id not in results:
                yield {"type": "error", "message": f"Dependency step {dep_id} not yet complete."}
                return

        if step.requires_confirmation:
            yield {"type": "approval_required", "action": step.action, "data": step.parameters, "step_id": step.step_id}
            return  # pause — Flutter will resume via /agent/execute-action

        result = _dispatch(step, user_id)
        results[step.step_id] = result
        yield {"type": "log", "message": f"✅ Step {step.step_id} complete: {step.action}"}

    yield {"type": "result", "text": _summarise(results)}
```

---

### Task 2.4 — Wire Planner + Executor into main.py (Backend)

**File:** `backend/app/main.py` *(MODIFY)*

The `/agent/text` endpoint becomes a two-step SSE stream:

```
1. Call planner.plan()         → emit {"type": "plan", "plan": {...}}
2. Call executor.execute_plan()→ emit logs, approvals, results
```

Flutter sees the plan before any action runs. This also enables us to show a preview of *what the agent is about to do* in the UI (Phase 3).

---

### Task 2.5 — Plan Preview UI (Flutter)

**File:** `mobile_agent/lib/widgets/plan_preview_card.dart` *(NEW)*

When the backend emits a `plan` SSE event, display a compact card above the chat showing each step as a labelled badge (e.g. "📧 Draft email → Sarah", "📅 Create event → Thursday 4PM"). Each badge shows its `requires_confirmation` state.

Update `api_service.dart` to parse the new `"plan"` SSE event type.

---

## Phase 3 — Confirmation & Safety

> *Goal: Make every destructive or externally visible action require explicit user approval, with a clear explanation of scope.*

### Task 3.1 — Safety Classifier (Backend)

**File:** `backend/app/agents/safety.py` *(NEW)*

A lightweight classifier that runs before the Executor. It:
- Tags each step as `safe` | `caution` | `dangerous`.
- For `dangerous` steps (delete, bulk send, financial), generates a human-readable scope warning.

```python
DANGER_ACTIONS = {"delete_emails", "bulk_send", "cancel_recurring_event"}

def classify(step: TaskStep, context: dict) -> SafetyRating:
    """Return a safety rating and optional scope_warning string."""
    if step.action in DANGER_ACTIONS:
        return SafetyRating(level="dangerous", scope_warning=_compute_scope(step, context))
    if step.requires_confirmation:
        return SafetyRating(level="caution", scope_warning=None)
    return SafetyRating(level="safe")
```

Example scope warning emitted to Flutter:
```json
{"type": "safety_warning", "message": "You are about to delete 214 emails from Amazon.", "requires_double_confirm": true}
```

---

### Task 3.2 — Enhanced Approval Drawer (Flutter)

**File:** `mobile_agent/lib/widgets/approval_drawer.dart` *(MODIFY)*

Add a `danger` state to the drawer that:
- Shows a red warning banner with the scope description.
- Requires the user to type "CONFIRM" or slide a special confirmation slider for `dangerous` actions.
- Adds an "Edit" mode for email and calendar drafts before approval.

---

### Task 3.3 — Bulk Action Guard (Backend)

**File:** `backend/app/tools/email_tools.py`, `calendar_tools.py` *(MODIFY)*

Before any bulk read/delete, run a count query first and include it in the `approval_required` data. The Executor never acts on more than `N` items without confirmation.

---

## Phase 4 — Memory

> *Goal: Give A.L.T.A.I.R. persistent knowledge about people, preferences, and recurring patterns, so users never have to repeat themselves.*

### Task 4.1 — Design the Memory Schema (Database)

**Supabase table:** `user_memory`

```sql
CREATE TABLE user_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    key TEXT NOT NULL,                    -- e.g. "accountant", "weekly_review"
    value JSONB NOT NULL,                 -- e.g. {"email": "bob@firm.com", "name": "Bob"}
    memory_type TEXT NOT NULL,            -- "contact", "preference", "routine"
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(user_id, key)
);
```

---

### Task 4.2 — Memory Manager (Backend)

**File:** `backend/app/agents/memory_manager.py` *(NEW)*

Provides:
- `lookup(user_id, query)` — fuzzy/semantic search over memory keys.
- `store(user_id, key, value, type)` — write or update a memory fact.
- `delete(user_id, key)` — remove a memory entry.

Uses **pgvector** (a Supabase/Postgres extension) to enable semantic similarity search on memory keys and values. This allows matching "my accountant" to stored entry `{"key": "accountant", "value": {"email": "bob@firm.com"}}`.

---

### Task 4.3 — Memory Tool (Backend)

**File:** `backend/app/tools/memory_tools.py` *(NEW)*

Expose two Gemini tools:
- `lookup_memory(query: str)` — look up a contact, preference, or routine.
- `save_memory(key: str, value: dict, memory_type: str)` — proactively store something the user told the assistant.

These tools are always available to both the Planner and the Executor.

---

### Task 4.4 — Memory Resolver in Planner (Backend)

**File:** `backend/app/agents/planner.py` *(MODIFY)*

Before the Planner generates a plan, run a **pre-pass** memory lookup:

```python
# Before calling Gemini planner, resolve obvious references
resolved_context = await memory_manager.resolve_references(user_text, user_id)
# e.g. "my accountant" → {"email": "bob@cpa.com", "name": "Bob Smith"}
# Inject resolved_context into the planner prompt
```

This means the Planner always receives enriched context — it never generates an `ambiguity_question` for something the user has already taught the assistant.

---

### Task 4.5 — Memory UI (Flutter)

**File:** `mobile_agent/lib/views/memory_view.dart` *(NEW)*

A dedicated page (accessible from the left sidebar) showing:
- Stored contacts with their resolved information.
- Saved preferences and routines.
- A way to delete individual memory entries.

When the agent stores a new memory fact mid-conversation, a subtle "Remembered: your accountant is Bob" toast appears.

---

## Phase 5 — Multi-Step Workflows

> *Goal: A single user command can trigger a sequence of coordinated actions across multiple tools.*

### Task 5.1 — Task Graph Engine (Backend)

**File:** `backend/app/agents/task_graph.py` *(NEW)*

Currently, `TaskPlan.steps` is a linear list. Upgrade it to a **directed acyclic graph (DAG)**:

```python
class TaskGraph(BaseModel):
    nodes: dict[int, TaskStep]
    edges: list[tuple[int, int]]  # (from_step_id, to_step_id)
```

The Executor walks the graph topologically:
1. Execute all nodes with no unresolved dependencies in parallel (using `asyncio.gather`).
2. Pass results downstream to dependent nodes.
3. Pause the graph at any `requires_confirmation` node.
4. Resume the graph via `/agent/resume-plan/{plan_id}`.

---

### Task 5.2 — Plan Persistence (Backend)

**File:** `backend/app/database/plan_store.py` *(NEW)*

**Supabase table:** `active_plans`

```sql
CREATE TABLE active_plans (
    plan_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    status TEXT NOT NULL,             -- "pending", "awaiting_approval", "complete", "failed"
    plan_json JSONB NOT NULL,         -- full TaskGraph serialised
    current_step_id INT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

When the user approves an action, Flutter sends `plan_id` + `step_id` to `/agent/resume-plan`, and the Executor picks up where it left off.

---

### Task 5.3 — Multi-Step UI Progress (Flutter)

**File:** `mobile_agent/lib/widgets/workflow_progress_card.dart` *(NEW)*

A horizontal stepper widget that appears in the chat when a multi-step plan is active:
- Each step shows its icon, label, and status (pending / running / ✅ done / ❌ failed).
- The active step pulses with a subtle glow animation.
- Approval steps show a "Review & Approve" button inline.

---

### Task 5.4 — Parallel Step Execution (Backend)

**File:** `backend/app/agents/executor.py` *(MODIFY)*

Convert the executor to `async` and use `asyncio.gather` to run independent steps concurrently. For example, "block my calendar AND draft an out-of-office email" can be executed in parallel since neither step depends on the other.

---

## Phase 6 — Context Awareness

> *Goal: Enable pronoun and reference resolution so the user can say "tell her I'll be late" and the assistant knows who "her" is.*

### Task 6.1 — Context Window (Backend)

**File:** `backend/app/agents/context_resolver.py` *(NEW)*

Maintain a **session context object** alongside conversation history:

```python
class SessionContext(BaseModel):
    last_mentioned_people: list[dict]   # [{"name": "Sarah", "email": "sarah@..."}]
    upcoming_events: list[dict]          # next 3 calendar events, refreshed each turn
    last_action: dict | None             # what was just done
    active_plan_id: str | None           # if a multi-step workflow is in progress
```

This object is:
1. Built at the start of every `/agent/text` request.
2. Injected into the Planner's system prompt as structured context.
3. Updated after each turn and serialised back to the conversation history.

---

### Task 6.2 — Pronoun Resolution in Planner (Backend)

**File:** `backend/app/agents/planner.py` *(MODIFY)*

Inject `SessionContext` into the planner prompt:

```
CONTEXT:
- Your last mentioned person: Sarah (sarah@acme.com)
- Your next meeting: "Acme Review" with Sarah at 3:00 PM today
- Last action taken: drafted an email to John
```

Gemini's Planner now has enough grounding to resolve "her" → Sarah, "it" → Acme Review, etc.

---

### Task 6.3 — Upcoming Event Prefetch (Backend)

**File:** `backend/app/tools/calendar_tools.py` *(MODIFY)*

Add a lightweight `prefetch_upcoming_events(user_id, limit=3)` function that fetches the next 3 calendar events silently at the start of each session. This populates `SessionContext.upcoming_events` without being a visible tool call.

---

## Phase 7 — Background Jobs

> *Goal: A.L.T.A.I.R. can monitor conditions and proactively alert the user, without requiring a voice command.*

### Task 7.1 — Background Job Schema (Database)

**Supabase table:** `background_jobs`

```sql
CREATE TABLE background_jobs (
    job_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    description TEXT NOT NULL,            -- human-readable, shown in UI
    trigger_type TEXT NOT NULL,           -- "email_keyword", "calendar_change", "schedule"
    trigger_config JSONB NOT NULL,        -- e.g. {"keywords": ["pricing"], "sender": "Acme"}
    action_on_trigger JSONB NOT NULL,     -- what to do when triggered
    status TEXT DEFAULT 'active',         -- "active", "paused", "triggered", "expired"
    last_checked TIMESTAMP,
    expires_at TIMESTAMP
);
```

---

### Task 7.2 — Background Job Runner (Backend)

**File:** `backend/app/jobs/job_runner.py` *(NEW)*

A long-running `asyncio` task started with FastAPI's `lifespan` hook:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(job_runner.run_all())
    yield
    task.cancel()
```

The runner:
1. Polls active jobs on a configurable interval (default: every 5 minutes).
2. For each `email_keyword` job: calls Gmail API, scans recent messages for keyword matches.
3. When triggered: sends a push notification to the user's device.
4. Updates `last_checked` and optionally `status = "triggered"`.

---

### Task 7.3 — Push Notifications (Flutter + Backend)

**Technology:** Firebase Cloud Messaging (FCM)

**Backend:**
- Add `firebase-admin` to `requirements.txt`.
- Store FCM device token per user in `user_memory` (or a dedicated `device_tokens` table).
- `job_runner.py` calls `firebase_admin.messaging.send()` when a job triggers.

**Flutter:**
- Add `firebase_messaging` package to `pubspec.yaml`.
- Register device token on login and send it to the backend.
- Show a notification tray card when a background job fires.

---

### Task 7.4 — Background Jobs UI (Flutter)

**File:** `mobile_agent/lib/views/background_jobs_view.dart` *(NEW)*

Accessible from the left sidebar. Displays:
- Active monitoring jobs with their conditions.
- A toggle to pause/resume each job.
- History of past triggers.

Creating a job is as simple as saying:
> "Monitor emails from Acme Corp and alert me if they mention pricing."

The Planner interprets this as a `create_background_job` intent and calls the appropriate tool.

---

## Technical Stack Additions

| What | Technology | Why |
|---|---|---|
| Structured Planner output | Gemini `response_schema` + Pydantic | Deterministic JSON output, no regex parsing |
| Semantic memory search | Supabase `pgvector` extension | Fuzzy match "my accountant" without exact key lookup |
| Plan persistence | Supabase `active_plans` table | Resume multi-step workflows after approval or restart |
| Background jobs | FastAPI `lifespan` + `asyncio` | Non-blocking, scales with the existing backend |
| Push notifications | Firebase Cloud Messaging (FCM) | Cross-platform, no polling from device |
| Parallel step execution | `asyncio.gather` in Executor | Independent steps in a workflow run concurrently |

---

## Implementation Order

The phases are designed to be built in strict order — each one is a foundation for the next.

```
Phase 2: Planner/Executor architecture
   │
   ├── 2.1  TaskStep / TaskPlan schema
   ├── 2.2  Planner agent (Gemini JSON mode)
   ├── 2.3  Executor (step dispatcher)
   ├── 2.4  Wire into /agent/text endpoint
   └── 2.5  Plan preview UI in Flutter

Phase 3: Safety layer
   │
   ├── 3.1  Safety classifier
   ├── 3.2  Enhanced approval drawer
   └── 3.3  Bulk action guard

Phase 4: Memory
   │
   ├── 4.1  Supabase user_memory table
   ├── 4.2  Memory manager (pgvector lookups)
   ├── 4.3  lookup_memory / save_memory tools
   ├── 4.4  Memory pre-pass in Planner
   └── 4.5  Memory UI in Flutter

Phase 5: Multi-step workflows
   │
   ├── 5.1  Task graph (DAG) engine
   ├── 5.2  Plan persistence (Supabase)
   ├── 5.3  Workflow progress UI
   └── 5.4  Parallel step execution

Phase 6: Context awareness
   │
   ├── 6.1  SessionContext object
   ├── 6.2  Pronoun resolution in Planner
   └── 6.3  Upcoming event prefetch

Phase 7: Background jobs
   │
   ├── 7.1  background_jobs table
   ├── 7.2  Job runner (asyncio + lifespan)
   ├── 7.3  FCM push notifications
   └── 7.4  Background jobs UI
```

---

## What We Deliberately Will Not Build (Yet)

The following integrations are explicitly deferred until the core architecture (Phases 2–6) is solid:

- Slack, WhatsApp, Discord, LinkedIn
- Trello, Notion, Dropbox
- Salesforce
- Microsoft Graph (Outlook / Exchange)

Adding integrations before the planning layer exists means each new tool makes the system fragile. After Phase 5, adding a tool is a matter of:
1. Writing one Python tool file.
2. Adding one `ConnectorConfig` entry to the Flutter registry.
3. Adding one action key to the Executor dispatch table.

That is the architectural payoff we are building toward.

---

## Suggested Two-Week Sprint

**Week 1: Phase 2 (Planner + Executor)**

| Day | Task |
|---|---|
| 1 | Define `TaskStep` / `TaskPlan` Pydantic schema + unit tests |
| 2 | Build `planner.py` — Gemini JSON mode, prompt engineering |
| 3 | Build `executor.py` — linear step dispatch, approval intercept |
| 4 | Wire into `main.py` — new SSE event `"plan"`, refactor `/agent/text` |
| 5 | Flutter: parse `"plan"` event, build `PlanPreviewCard` widget |

**Week 2: Phase 3 (Safety) + Phase 4 start (Memory schema)**

| Day | Task |
|---|---|
| 6 | `safety.py` — classifier + scope warning |
| 7 | Flutter: danger-state approval drawer + double-confirm slider |
| 8 | Supabase: create `user_memory` table, enable pgvector |
| 9 | `memory_manager.py` + `memory_tools.py` + register with Planner |
| 10 | Flutter: memory UI (list + delete), memory toast notification |
