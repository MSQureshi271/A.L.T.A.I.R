# Phase 4 Memory Implementation Plan — Persistent Human-Like Assistant Memory

This document outlines the detailed architecture, database schemas, and implementation roadmap for **Phase 4 (Memory)** of A.L.T.A.I.R.

Rather than lazily vectorizing every sentence the user says, A.L.T.A.I.R. models memory like a human assistant. Memory is segmented by structure and utility, ensuring 100% deterministic accuracy for settings, profiles, and relationships, while using semantic embeddings only for free-form knowledge retrieval.

---

## 1. The 5-Layer Memory Model

```
                                    A.L.T.A.I.R. Memory
                                             │
      ┌────────────────────────┬─────────────┼─────────────┬────────────────────────┐
      ▼                        ▼             ▼             ▼                        ▼
Layer 1: Session        Layer 2: Facts   Layer 3: Prefs   Layer 4: Routines   Layer 5: Semantic
(Current Chat Only)     (Contacts/Roles) (Settings/Tone)  (Workflows)         (pgvector Notes)
```

### Layer 1: Session Memory
* **Lifetime:** Current active conversation.
* **Scope:** Pronoun resolution, active referents (e.g., *"her"* = Sarah, *"it"* = the event we just checked).
* **Storage:** In-memory state inside Flutter's `AgentNotifier` / backend `history` block. No DB queries required.

### Layer 2: User Facts (Persistent Contacts & Profiles)
* **Scope:** Explicit relations, roles, and contacts (e.g., Accountant, Lawyer, Partner).
* **Storage:** Relational database table (`contacts`).

### Layer 3: Preferences (Persistent Settings)
* **Scope:** Structured rules applying across multiple actions (e.g., communication signature, default meeting duration, timezone).
* **Storage:** Relational database table (`preferences`).

### Layer 4: Routines (Persistent Workflows)
* **Scope:** Reusable workflow templates triggered by key phrases (e.g., *"run my weekly review"* -> sequence: read calendar → fetch emails → draft status update).
* **Storage:** Relational database table (`routines`).

### Layer 5: Semantic Memory (Knowledge Base)
* **Scope:** Free-form unstructured facts (e.g., *"The contractor's email is construction@abc.com"*).
* **Storage:** Relational table with vector embeddings (`knowledge`).

---

## 2. Database Schema Design (Task 4.1)

### Supabase Table SQL Schemas

#### 1. Contacts
```sql
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    company TEXT,
    notes TEXT,                         -- e.g. "my accountant", "works evenings"
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
```

#### 2. Preferences
```sql
CREATE TABLE IF NOT EXISTS preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    category TEXT NOT NULL,             -- e.g., "calendar", "email"
    key TEXT NOT NULL,                  -- e.g., "default_duration", "signature"
    value JSONB NOT NULL,               -- e.g., 30, "Regards,\nSubhan"
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, category, key)
);
```

#### 3. Routines
```sql
CREATE TABLE IF NOT EXISTS routines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,                 -- e.g., "weekly_review"
    steps TEXT[] NOT NULL,              -- e.g., ["calendar", "gmail", "search"]
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);
```

#### 4. Knowledge (pgvector)
```sql
-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,                 -- The raw remembered fact
    embedding vector(1536),             -- Text embeddings (using OpenAI or Gemini Embeddings)
    importance INT NOT NULL DEFAULT 1,  -- Importance score: 1 (low) to 5 (high)
    times_used INT NOT NULL DEFAULT 0,
    last_used TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

### Local Cache Fallback Schema (`.memory_cache.json`)
If Supabase is not configured, the local file is structured to reflect these distinct namespaces:
```json
{
  "DEV_USER_ID": {
    "contacts": [
      {
        "name": "Sarah",
        "email": "sarah@acme.com",
        "notes": "my partner at Acme"
      }
    ],
    "preferences": {
      "email": {
        "signature": "Regards,\nSubhan"
      },
      "calendar": {
        "default_duration": 30
      }
    ],
    "routines": {
      "weekly_review": ["calendar", "gmail", "search"]
    },
    "knowledge": [
      {
        "text": "The contractor's email is construction@abc.com",
        "importance": 4,
        "times_used": 0
      }
    ]
  }
}
```

---

## 3. The Memory Manager (Task 4.2 & 4.3)

**File:** `backend/app/agents/memory_manager.py` (NEW)

The Memory Manager acts as a gatekeeper between the user inputs and the database, preventing conversational noise from polluting persistent storage.

```
User Voice Input  ──►  Planner  ──►  Memory Manager  ──►  Confirm Gate (HITL)  ──►  Supabase
                                 (Should I remember?)
```

### Memory Classification Prompt
When a command is executed, the Memory Manager uses a lightweight Gemini call to evaluate if a user statement contains a fact worth remembering:

```
[System Instruction]
Analyze the user statement. Decide if it contains a fact, contact, preference, or routine that should be stored for long-term memory.
Output a JSON object with:
{
  "should_remember": true/false,
  "category": "contacts" | "preferences" | "routines" | "knowledge",
  "key": "short descriptive slug",
  "value": { ...structured representation... },
  "importance": 1-5 (5 being critical email/finance information, 1 being casual preference),
  "reason": "why we are remembering it"
}
```

### Writing Memory Facts (Human-in-the-Loop)
* Gemini tools: `save_contact`, `save_preference`, `save_routine`, `save_knowledge`.
* When Gemini triggers `save_preference(key="signature", value="Regards,\nSubhan")`, the tool yields an `approval_required` event.
* The user reviews the fact in a Flutter confirmation card before it is committed.

---

## 4. The Memory Resolver in Planner (Task 4.4)

**File:** `backend/app/agents/planner.py` (MODIFY)

The Planner does not query the database directly. Instead, a **Memory Resolver pre-pass** fetches facts and injects them into the system instruction before planning begins.

```
Raw User Text  ──►  Memory Resolver  ──►  Combined Context  ──►  Planner  ──►  TaskPlan
                         │ (SQL + Vectors)
                    Supabase Tables
```

### Resolver Strategy
1. **Contacts / Profile Lookup:** Fetches the full list of contacts and key preferences.
2. **Knowledge Similarity Match:** If the text has references, calls similarity search on `knowledge`.
3. **Context Injection:** Formats the facts as text:
   ```
   CONTEXT (USER FACTS & PREFERENCES):
   - User Signature: "Regards, Subhan"
   - Contact "Sarah": Email is sarah@acme.com (CEO, Acme)
   - Stored Fact: The contractor's email is construction@abc.com
   ```
4. **Task Plan Synthesis:** The Planner uses this context to automatically populate parameters in the steps (e.g. `recipient="sarah@acme.com"`), eliminating ambiguity questions.

---

## 5. Flutter Front-end UI (Task 4.5)

### Drawer Sidebar Navigation
* Add a **"Memory"** tile in the left-side navigation drawer.

### Tabbed Dashboard Screen (`mobile_agent/lib/views/memory_view.dart`)
A dashboard displaying memory elements grouped into four tabs:
1. **Contacts:** Interactive card list showing details (email, phone, company, notes).
2. **Preferences:** Lists settings by category (e.g., Email Signature, Default Meeting duration).
3. **Routines:** Shows workflow workflows and step sequences.
4. **Knowledge:** Lists free-form facts with their importance levels (1-5 stars) and usage metrics.

### Remember Toasts
* When `save_contact` or `save_preference` is confirmed and executed, the Flutter UI shows a custom animated card toast: *"Remembered: Bob is your accountant (Importance 5)"*.

---

## 6. Implementation Action Plan

### Milestone 4.1: Database Tables & Local Cache Fallback
* Create Supabase SQL schemas for `contacts`, `preferences`, `routines`, and `knowledge` tables.
* Implement `.memory_cache.json` helper functions in `backend/app/database/db_client.py`.

### Milestone 4.2: Memory Manager & Resolver
* Write `backend/app/agents/memory_manager.py` to handle writes, deletes, and the pre-pass memory resolver.
* Integrate the pre-pass resolver into the `/agent/voice` and `/agent/text` routes inside `main.py`.

### Milestone 4.3: Memory Tools & Planner Alignment
* Expose `save_contact`, `save_preference`, and `save_routine` tools to the Planner.
* Update `_PLANNER_SYSTEM_PROMPT` in `planner.py` to utilize injected `CONTEXT` facts for generating step parameters.

### Milestone 4.4: Execution Wiring
* Hook up execution routes in `executor.py` and `main.py` to handle the database write operations after user approval.

### Milestone 4.5: Flutter Memory View
* Implement tabbed UI screen `memory_view.dart` in Flutter.
* Link the Memory View into the navigation sidebar.
