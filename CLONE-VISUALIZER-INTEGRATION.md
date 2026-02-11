# Clone Visualizer Integration — Wrapping Durable Functions with the Contractor Dashboard

## Executive Summary

This document analyzes how to integrate the **Clone Visualizer Contractor Model** with the existing Azure Durable Functions HITL claims processing system. The existing system already has the right bones — 3 AI agents, sequential orchestration, HITL, Service Bus triggers. What's missing is the **concurrency management layer** (Layer 1) that tracks named AI Contractors, manages job slots, implements first-fill/scale-down, and powers a real-time dashboard.

---

## 1. Current State — What Already Exists

### Existing Pipeline (Sequential, Single-Claim)

```
Service Bus / HTTP POST
        │
        ▼
┌──────────────────┐
│ claim_orchestrator│  ← Durable Functions orchestrator (function_app.py:874)
│                  │
│  1. Agent1       │  ← Classification (agent1_activity.py → agent_client.py)
│  2. Notify       │  ← Log approval request
│  3. HITL Wait    │  ← wait_for_external_event("ApprovalDecision")
│  4. Agent2       │  ← Adjudication (agent2_activity.py → agent_client.py)
│  5. Agent3       │  ← Email Composer (agent3_activity.py → agent_client.py)
│  6. Send Email   │  ← SMTP via Gmail
│  7. Complete     │
└──────────────────┘
```

### Key Existing Components

| Component | File | Relevance to Clone Visualizer |
|-----------|------|-------------------------------|
| Orchestrator | `function_app.py:874-1183` | Sequential per-claim flow — becomes the "job execution" inside a contractor slot |
| Agent1 Activity | `activities/agent1_activity.py` | Already wraps Foundry call — needs persona injection |
| Agent2 Activity | `activities/agent2_activity.py` | Already wraps Foundry call — needs persona injection |
| Agent3 Activity | `activities/agent3_activity.py` | Already has persona names (`prompts.py:14-23`) — partial alignment |
| Prompt Templates | `shared/prompts.py` | System + User prompts defined — persona injection point exists |
| Agent Client | `shared/agent_client.py` | `invoke_foundry_agent()` makes API calls — contractor identity added here |
| Dashboard HTML | `static/dashboard.html` | Claims listing UI — needs to become Contractor Card dashboard |
| Review HTML | `static/review.html` | HITL form — unchanged, but links from contractor job slots |
| Custom Status | Orchestrator `set_custom_status()` | Already tracks stages — extend to include contractor assignment |
| Service Bus | `servicebus_claim_trigger()` | Ingestion — becomes the **pending queue feeder** |
| Models | `shared/models.py` | Pydantic models — extend with contractor/slot models |

### What's Missing

| Clone Visualizer Concept | Current State |
|--------------------------|---------------|
| Named AI Contractors (Alice, Bob, Priya) | No contractor abstraction — all claims run anonymously |
| First-fill job assignment | No concurrency management — claims process independently |
| Capacity tracking (N slots per contractor) | No slot concept — one orchestrator per claim |
| Spawn/terminate lifecycle | No scaling logic |
| Persona injection into user prompt | Agent3 has random persona for signatures only — not operational identity |
| Real-time contractor dashboard | Dashboard shows claim list, not contractor workload view |
| Scale-down (LIFO termination) | No scale-down concept |
| Inter-stage pending queues | Implicit via orchestrator `yield` — no visible queue |

---

## 2. Architecture — How It Maps

### The Key Insight

The existing Durable Functions orchestrator already handles **the job execution** — one claim flowing through Agent1 → HITL → Agent2 → Agent3. This is what happens **inside a single contractor job slot**.

The Clone Visualizer adds a **layer above** that manages:
- How many claims are processed concurrently per agent stage
- Which named contractor handles which claim
- When to spawn/terminate contractors
- Dashboard visualization of the whole workforce

### Two-Layer Architecture Applied to This Project

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 1: CONTRACTOR ORCHESTRATION                         │
│                    (New module in the Durable Functions app)                 │
│                                                                              │
│  ┌─────────────────────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│  │ AGENT 1: Classifier     │  │   HITL   │  │ AGENT 2: Adjudicator     │   │
│  │ Capacity: 3/contractor  │  │  (Human  │  │ Capacity: 3/contractor   │   │
│  │ Max: 5 contractors      │  │   Queue) │  │ Max: 5 contractors       │   │
│  │                         │  │          │  │                          │   │
│  │ ┌Alice─────────────┐   │  │ Reviewer │  │ ┌Alice─────────────┐    │   │
│  │ │ CSB-001 ▓▓▓░ 60% │   │  │ waiting: │  │ │ CSB-004 ▓▓░░ 40% │    │   │
│  │ │ CSB-002 ▓▓░░ 40% │   │  │ 2 claims │  │ │ CSB-005 ▓░░░ 15% │    │   │
│  │ │ CSB-003 ▓░░░ 15% │   │  │          │  │ │ (empty)           │    │   │
│  │ └──────────────────┘   │  │          │  │ └───────────────────┘    │   │
│  │ ┌Bob────────────────┐  │  │          │  │                          │   │
│  │ │ CSB-006 ▓▓░░ 30%  │  │  │          │  │                          │   │
│  │ │ (empty)            │  │  │          │  │                          │   │
│  │ │ (empty)            │  │  │          │  │                          │   │
│  │ └──────────────────-─┘  │  │          │  │                          │   │
│  │ Pending: [CSB-007]      │  │          │  │ Pending: [CSB-008]       │   │
│  └─────────────────────────┘  └──────────┘  └──────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────┐     │
│  │ AGENT 3: Email Composer  │  │          END: Send Email             │     │
│  │ Capacity: 5/contractor   │  │          (fixed, no contractors)     │     │
│  │ Max: 3 contractors       │  │                                      │     │
│  │                          │  │                                      │     │
│  │ ┌Alice──────────────┐   │  │                                      │     │
│  │ │ CSB-009 ▓▓▓░ 55%  │   │  │                                      │     │
│  │ │ (empty)            │   │  │                                      │     │
│  │ │ (empty)            │   │  │                                      │     │
│  │ │ (empty)            │   │  │                                      │     │
│  │ │ (empty)            │   │  │                                      │     │
│  │ └───────────────────-┘   │  │                                      │     │
│  └──────────────────────────┘  └──────────────────────────────────────┘     │
└────────────────────┬─────────────────────────────────────────────────────────┘
                     │  Each job = one Durable Functions orchestration
                     │  with persona injected into agent prompts
                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│            LAYER 2: AZURE AI FOUNDRY (Already Exists)                        │
│                                                                              │
│  Agent 1: claim-assistant-agent    (Classification)                          │
│  Agent 2: claim-approval-agent     (Adjudication)                            │
│  Agent 3: EmailComposerAgent       (Email Composition)                       │
│                                                                              │
│  Same agents, same system prompts — persona injected in user prompt          │
│  "You are Alice, a claims analyst. [claim data follows]"                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Critical Design Decision — Where to Put Layer 1

There are two viable approaches. The choice depends on whether you want the PoC/demo dashboard or a production-grade system.

### Option A: Durable Entities (Pure Durable Functions)

Use **Durable Entities** to model each agent stage's contractor pool as stateful entities within the existing Durable Functions app.

```
┌─────────────────────────────────────────────────────────┐
│  Durable Entity: "contractor_pool/doc-extractor"        │
│                                                         │
│  State:                                                 │
│    contractors: [                                       │
│      { name: "Alice", slots: [...], status: "active" }, │
│      { name: "Bob",   slots: [...], status: "active" }  │
│    ]                                                    │
│    pending_queue: ["CSB-007", "CSB-008"]                │
│    config: { capacity: 3, max: 5 }                      │
│                                                         │
│  Operations:                                            │
│    assign_job(claim_id) → contractor_name               │
│    complete_job(claim_id) → void                        │
│    get_state() → full snapshot for dashboard            │
│    spawn_contractor() → new contractor                  │
│    terminate_contractor(name) → void                    │
└─────────────────────────────────────────────────────────┘
```

**Pros:**
- Pure Durable Functions — no new infrastructure
- Durable Entities persist state automatically (survives restarts)
- Entities are addressable — dashboard can query them directly
- Fits within existing deployment model

**Cons:**
- Durable Entities have serialization constraints
- Dashboard polling requires HTTP endpoints to query entity state
- No native WebSocket support (need to poll)

### Option B: In-Memory State + Tick Loop (PoC Dashboard)

Add a **contractor manager module** with in-memory state, exposed via new API endpoints. The dashboard runs a tick loop (polling `/api/contractor-state` every 500ms).

```python
# New module: shared/contractor_manager.py
contractor_pools = {
    "classifier": ContractorPool(capacity=3, max=5, names=["Alice","Bob","Priya","David","Mei"]),
    "adjudicator": ContractorPool(capacity=3, max=5, names=["Alice","Bob","Priya","David","Mei"]),
    "email_composer": ContractorPool(capacity=5, max=3, names=["Alice","Bob","Priya"]),
}
```

**Pros:**
- Fast to build (PoC/demo ready)
- Simple first-fill/scale-down logic in plain Python
- Dashboard polls a single REST endpoint
- Easy to simulate for stakeholder demos

**Cons:**
- In-memory state lost on restart (OK for PoC, not production)
- Single-instance only (no scale-out for the function app itself)
- Need to sync with actual Durable Functions orchestration state

### Recommendation

**Start with Option B for PoC/demo**, then migrate to Option A for production. The visualization value is immediate with Option B, and it lets stakeholders see the contractor model in action.

---

## 4. Implementation Plan — Option B (PoC Dashboard)

### Phase 1: Contractor State Management

#### 4.1 New Data Models (`shared/models.py` — extend)

```python
# --- Contractor Models ---

class JobSlot(BaseModel):
    """A single job slot within a contractor."""
    claim_id: str
    stage: str                    # "classifier", "adjudicator", "email_composer"
    progress_pct: int = 0         # 0-100
    started_at: datetime
    status: str = "processing"    # "processing", "completed"

class Contractor(BaseModel):
    """A named AI Contractor instance."""
    name: str                     # "Alice", "Bob", etc.
    agent_id: str                 # "classifier", "adjudicator", "email_composer"
    color: str                    # "#2dd4a8"
    capacity: int                 # Max concurrent jobs
    active_jobs: list[JobSlot] = []
    jobs_completed: int = 0
    status: str = "active"        # "active", "idle", "terminated"
    is_primary: bool = False      # True for first contractor (never terminated)
    spawn_time: datetime | None = None

class ContractorPoolConfig(BaseModel):
    """Configuration for a contractor pool."""
    agent_id: str
    display_name: str
    capacity_per_contractor: int
    max_contractors: int
    contractors: list[dict]       # [{"name": "Alice", "color": "#2dd4a8"}, ...]

class ContractorPoolState(BaseModel):
    """Runtime state of a contractor pool."""
    agent_id: str
    display_name: str
    pending_queue: list[str] = []
    active_contractors: list[Contractor] = []
    total_jobs_in_flight: int = 0
    total_completed: int = 0
```

#### 4.2 New Module: Contractor Manager (`shared/contractor_manager.py`)

Core responsibilities:
1. **Maintain contractor pools** — one per agent stage
2. **First-fill assignment** — `assign_job(agent_id, claim_id) → contractor_name`
3. **Job completion** — `complete_job(agent_id, claim_id)` → trigger scale-down check
4. **Scale-down** — terminate empty contractors in reverse spawn order
5. **State snapshot** — `get_all_state()` → JSON for dashboard

```python
import threading
from datetime import datetime, timezone
from typing import Optional

class ContractorPool:
    """Manages contractors for a single agent stage."""

    def __init__(self, agent_id: str, display_name: str,
                 capacity: int, max_contractors: int,
                 contractor_defs: list[dict]):
        self.agent_id = agent_id
        self.display_name = display_name
        self.capacity = capacity
        self.max_contractors = max_contractors
        self.contractor_defs = contractor_defs  # [{"name": "Alice", "color": "#2dd4a8"}, ...]
        self.active_contractors: list[dict] = []
        self.pending_queue: list[str] = []
        self.total_completed: int = 0
        self._lock = threading.Lock()

        # Always spawn the first (primary) contractor
        self._spawn_contractor(is_primary=True)

    def assign_job(self, claim_id: str) -> Optional[str]:
        """Assign a job using first-fill logic. Returns contractor name or None if queued."""
        with self._lock:
            # Try first-fill across existing contractors
            for contractor in self.active_contractors:
                if len(contractor["active_jobs"]) < self.capacity:
                    contractor["active_jobs"].append({
                        "claim_id": claim_id,
                        "progress_pct": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "processing"
                    })
                    return contractor["name"]

            # All full — try to spawn
            if len(self.active_contractors) < self.max_contractors:
                new_contractor = self._spawn_contractor()
                new_contractor["active_jobs"].append({
                    "claim_id": claim_id,
                    "progress_pct": 0,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "status": "processing"
                })
                return new_contractor["name"]

            # Max contractors reached — queue it
            self.pending_queue.append(claim_id)
            return None

    def update_progress(self, claim_id: str, progress_pct: int):
        """Update job progress (called from orchestrator custom status)."""
        with self._lock:
            for contractor in self.active_contractors:
                for job in contractor["active_jobs"]:
                    if job["claim_id"] == claim_id:
                        job["progress_pct"] = progress_pct
                        return

    def complete_job(self, claim_id: str):
        """Mark a job as complete and run scale-down."""
        with self._lock:
            for contractor in self.active_contractors:
                for job in contractor["active_jobs"]:
                    if job["claim_id"] == claim_id:
                        contractor["active_jobs"].remove(job)
                        contractor["jobs_completed"] = contractor.get("jobs_completed", 0) + 1
                        self.total_completed += 1
                        break

            # Assign pending jobs
            self._assign_pending()

            # Scale-down check
            self._scale_down()

    def _spawn_contractor(self, is_primary=False) -> dict:
        """Spawn the next contractor from the definition list."""
        idx = len(self.active_contractors)
        defn = self.contractor_defs[idx]
        contractor = {
            "name": defn["name"],
            "color": defn["color"],
            "active_jobs": [],
            "jobs_completed": 0,
            "status": "active",
            "is_primary": is_primary,
            "spawn_time": datetime.now(timezone.utc).isoformat()
        }
        self.active_contractors.append(contractor)
        return contractor

    def _assign_pending(self):
        """Try to assign pending jobs to available slots."""
        while self.pending_queue:
            assigned = False
            for contractor in self.active_contractors:
                if len(contractor["active_jobs"]) < self.capacity and self.pending_queue:
                    claim_id = self.pending_queue.pop(0)
                    contractor["active_jobs"].append({
                        "claim_id": claim_id,
                        "progress_pct": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "processing"
                    })
                    assigned = True
                    break

            if not assigned:
                # Try to spawn
                if len(self.active_contractors) < self.max_contractors:
                    new_contractor = self._spawn_contractor()
                    claim_id = self.pending_queue.pop(0)
                    new_contractor["active_jobs"].append({
                        "claim_id": claim_id,
                        "progress_pct": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "processing"
                    })
                else:
                    break  # Truly at capacity

    def _scale_down(self):
        """Terminate empty contractors in reverse spawn order (never terminate primary)."""
        for contractor in reversed(self.active_contractors):
            if not contractor["is_primary"] and len(contractor["active_jobs"]) == 0:
                contractor["status"] = "terminated"
                self.active_contractors.remove(contractor)

    def get_state(self) -> dict:
        """Return full state snapshot for dashboard."""
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "display_name": self.display_name,
                "capacity_per_contractor": self.capacity,
                "max_contractors": self.max_contractors,
                "pending_queue": list(self.pending_queue),
                "pending_count": len(self.pending_queue),
                "active_contractors": [
                    {
                        "name": c["name"],
                        "color": c["color"],
                        "capacity": self.capacity,
                        "active_jobs": list(c["active_jobs"]),
                        "slots_used": len(c["active_jobs"]),
                        "jobs_completed": c.get("jobs_completed", 0),
                        "status": "full" if len(c["active_jobs"]) >= self.capacity
                                 else "idle" if len(c["active_jobs"]) == 0
                                 else "available",
                        "is_primary": c["is_primary"]
                    }
                    for c in self.active_contractors
                ],
                "contractor_count": len(self.active_contractors),
                "total_jobs_in_flight": sum(len(c["active_jobs"]) for c in self.active_contractors),
                "total_completed": self.total_completed
            }


# =============================================================================
# Global Contractor Manager (singleton)
# =============================================================================

class ContractorManager:
    """Singleton that manages all contractor pools."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.pools: dict[str, ContractorPool] = {
            "classifier": ContractorPool(
                agent_id="classifier",
                display_name="Claim Classifier",
                capacity=3,
                max_contractors=5,
                contractor_defs=[
                    {"name": "Alice", "color": "#2dd4a8"},
                    {"name": "Bob",   "color": "#7c5cfc"},
                    {"name": "Priya", "color": "#f59e0b"},
                    {"name": "David", "color": "#38bdf8"},
                    {"name": "Mei",   "color": "#c084fc"},
                ]
            ),
            "adjudicator": ContractorPool(
                agent_id="adjudicator",
                display_name="Claim Adjudicator",
                capacity=3,
                max_contractors=5,
                contractor_defs=[
                    {"name": "Alice", "color": "#2dd4a8"},
                    {"name": "Bob",   "color": "#7c5cfc"},
                    {"name": "Priya", "color": "#f59e0b"},
                    {"name": "David", "color": "#38bdf8"},
                    {"name": "Mei",   "color": "#c084fc"},
                ]
            ),
            "email_composer": ContractorPool(
                agent_id="email_composer",
                display_name="Email Composer",
                capacity=5,
                max_contractors=3,
                contractor_defs=[
                    {"name": "Alice", "color": "#2dd4a8"},
                    {"name": "Bob",   "color": "#7c5cfc"},
                    {"name": "Priya", "color": "#f59e0b"},
                ]
            ),
        }

    def assign_job(self, agent_id: str, claim_id: str) -> Optional[str]:
        return self.pools[agent_id].assign_job(claim_id)

    def update_progress(self, agent_id: str, claim_id: str, progress_pct: int):
        self.pools[agent_id].update_progress(claim_id, progress_pct)

    def complete_job(self, agent_id: str, claim_id: str):
        self.pools[agent_id].complete_job(claim_id)

    def get_all_state(self) -> dict:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stages": {
                agent_id: pool.get_state()
                for agent_id, pool in self.pools.items()
            },
            "hitl": {
                "display_name": "Manual Estimate",
                "waiting_count": 0,  # Updated by orchestrator
                "reviewers_active": 0
            }
        }
```

### Phase 2: Wire Contractor Manager into Orchestrator

#### 4.3 Modified Orchestrator Flow

The orchestrator (`claim_orchestrator`) needs to call the ContractorManager at each agent stage boundary:

```
Current:                              With Contractor Manager:
────────                              ──────────────────────
                                      ┌─ manager.assign_job("classifier", claim_id)
                                      │  → returns "Alice" (or queues if full)
yield call_activity("agent1")         │  yield call_activity("agent1", {persona: "Alice", ...})
                                      │  manager.complete_job("classifier", claim_id)
                                      └─

yield wait_for_external_event(...)    (unchanged — HITL)

                                      ┌─ manager.assign_job("adjudicator", claim_id)
yield call_activity("agent2")         │  yield call_activity("agent2", {persona: "Alice", ...})
                                      │  manager.complete_job("adjudicator", claim_id)
                                      └─

                                      ┌─ manager.assign_job("email_composer", claim_id)
yield call_activity("agent3")         │  yield call_activity("agent3", {persona: "Bob", ...})
                                      │  manager.complete_job("email_composer", claim_id)
                                      └─
```

**Important caveat**: Durable Functions orchestrators must be **deterministic** — you cannot call external stateful services (like ContractorManager) directly from the orchestrator. Instead:

1. Wrap contractor assignment in an **activity function**: `assign_contractor_activity`
2. Wrap contractor completion in an **activity function**: `complete_contractor_activity`
3. These activities call the ContractorManager singleton

```python
# New activity functions in function_app.py:

@app.activity_trigger(input_name="activityInput")
def assign_contractor_activity(activityInput: dict) -> dict:
    """Assign a job to a contractor using first-fill logic."""
    from shared.contractor_manager import ContractorManager
    manager = ContractorManager()
    contractor_name = manager.assign_job(
        activityInput["agent_id"],
        activityInput["claim_id"]
    )
    return {"contractor_name": contractor_name, "queued": contractor_name is None}

@app.activity_trigger(input_name="activityInput")
def complete_contractor_activity(activityInput: dict) -> dict:
    """Mark a job as complete in the contractor pool."""
    from shared.contractor_manager import ContractorManager
    manager = ContractorManager()
    manager.complete_job(
        activityInput["agent_id"],
        activityInput["claim_id"]
    )
    return {"completed": True}

@app.activity_trigger(input_name="activityInput")
def update_contractor_progress_activity(activityInput: dict) -> dict:
    """Update job progress in the contractor pool."""
    from shared.contractor_manager import ContractorManager
    manager = ContractorManager()
    manager.update_progress(
        activityInput["agent_id"],
        activityInput["claim_id"],
        activityInput["progress_pct"]
    )
    return {"updated": True}
```

#### 4.4 Modified Orchestrator (Pseudocode)

```python
@app.orchestration_trigger(context_name="context")
def claim_orchestrator(context: df.DurableOrchestrationContext):
    input_data = context.get_input()
    claim_id = input_data.get("claim_id")

    # === AGENT 1: CLASSIFICATION ===
    # Assign contractor
    assign_result = yield context.call_activity("assign_contractor_activity", {
        "agent_id": "classifier", "claim_id": claim_id
    })
    contractor_name = assign_result["contractor_name"]

    context.set_custom_status({
        "step": "agent1_processing",
        "contractor": contractor_name,  # NEW — "Alice"
        "claim_id": claim_id,
        ...
    })

    # Call Agent1 with persona
    agent1_input = {
        ...existing fields...,
        "persona_name": contractor_name,  # NEW — injected into prompt
    }
    agent1_result = yield context.call_activity("agent1_activity", agent1_input)

    # Release contractor slot
    yield context.call_activity("complete_contractor_activity", {
        "agent_id": "classifier", "claim_id": claim_id
    })

    # === HITL: Wait for Approval (unchanged) ===
    ...

    # === AGENT 2: ADJUDICATION ===
    assign_result = yield context.call_activity("assign_contractor_activity", {
        "agent_id": "adjudicator", "claim_id": claim_id
    })
    contractor_name = assign_result["contractor_name"]

    agent2_input = {..., "persona_name": contractor_name}
    agent2_result = yield context.call_activity("agent2_activity", agent2_input)

    yield context.call_activity("complete_contractor_activity", {
        "agent_id": "adjudicator", "claim_id": claim_id
    })

    # === AGENT 3: EMAIL COMPOSER ===
    assign_result = yield context.call_activity("assign_contractor_activity", {
        "agent_id": "email_composer", "claim_id": claim_id
    })
    contractor_name = assign_result["contractor_name"]

    agent3_input = {..., "persona_name": contractor_name}
    agent3_result = yield context.call_activity("agent3_activity", agent3_input)

    yield context.call_activity("complete_contractor_activity", {
        "agent_id": "email_composer", "claim_id": claim_id
    })

    ...
```

### Phase 3: Persona Injection into Agent Prompts

#### 4.5 Modify Prompt Templates (`shared/prompts.py`)

The persona identity is **prepended to the user prompt** on each API call. The system prompt remains unchanged (describes what the agent does, not who it is).

```python
# New constant in prompts.py:

CONTRACTOR_PERSONA_PREFIX = """[CONTRACTOR IDENTITY]
You are {contractor_name}, a claims processing specialist at JM&A Group.
Always respond and sign off as {contractor_name}.
Your contractor ID for this job: {contractor_name}-{claim_id}

[JOB DATA]
"""

# Modified build_agent1_prompt:
def build_agent1_prompt(claim_id, email_content, attachment_url,
                        sender_email, received_date, persona_name=None):
    prompt = ""
    if persona_name:
        prompt += CONTRACTOR_PERSONA_PREFIX.format(
            contractor_name=persona_name,
            claim_id=claim_id
        )
    prompt += AGENT1_USER_PROMPT_TEMPLATE.format(...)
    return prompt
```

The persona prefix is added to **all three agent prompts**. This means:
- Agent1 (Classification) responds as "Alice" or "Bob"
- Agent2 (Adjudication) responds as the assigned contractor
- Agent3 (Email Composer) uses the contractor name in the email signature (replacing the current random persona)

#### 4.6 Modify Agent Client (`shared/agent_client.py`)

The `invoke_foundry_agent()` function receives the persona-injected prompt and passes it as-is to the Foundry API. No changes needed at this level — the persona is already baked into the user prompt.

The existing `invoke_email_composer()` currently picks a random persona from `AGENT3_PERSONA_NAMES` — this should be changed to use the contractor name assigned by Layer 1:

```python
# In agent3_activity.py, replace random persona with contractor persona:
def run_agent3_activity(input_data: dict) -> dict:
    persona_name = input_data.get("persona_name")  # From contractor manager
    # ... build prompt with persona_name instead of random
```

### Phase 4: Dashboard API Endpoints

#### 4.7 New API Endpoints (`function_app.py`)

```python
@app.route(route="contractors/state", methods=["GET"])
async def get_contractor_state(req: func.HttpRequest) -> func.HttpResponse:
    """Return full contractor state for dashboard polling."""
    from shared.contractor_manager import ContractorManager
    manager = ContractorManager()
    state = manager.get_all_state()
    return func.HttpResponse(
        json.dumps(state, default=str),
        mimetype="application/json"
    )

@app.route(route="contractors/config", methods=["GET"])
async def get_contractor_config(req: func.HttpRequest) -> func.HttpResponse:
    """Return contractor pool configuration."""
    from shared.contractor_manager import ContractorManager
    manager = ContractorManager()
    config = {
        agent_id: {
            "display_name": pool.display_name,
            "capacity_per_contractor": pool.capacity,
            "max_contractors": pool.max_contractors,
            "contractor_names": [d["name"] for d in pool.contractor_defs]
        }
        for agent_id, pool in manager.pools.items()
    }
    return func.HttpResponse(json.dumps(config), mimetype="application/json")

@app.route(route="clone-dashboard", methods=["GET"])
async def serve_clone_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """Serve the Clone Visualizer Dashboard."""
    static_dir = Path(__file__).parent / "static"
    html_path = static_dir / "clone_dashboard.html"
    if not html_path.exists():
        return func.HttpResponse("Clone Dashboard not found", status_code=404)
    return func.HttpResponse(
        html_path.read_text(encoding="utf-8"),
        mimetype="text/html"
    )
```

### Phase 5: Clone Dashboard HTML

#### 4.8 New Dashboard (`static/clone_dashboard.html`)

The dashboard polls `/api/contractors/state` every 500ms and renders:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLONE VISUALIZER — AI Contractor Workforce Dashboard                       │
│  Total Claims: 24  │  In Flight: 8  │  Completed: 16                       │
├──────────────────────┬──────────┬──────────────────────┬────────────────────┤
│  CLASSIFIER          │   HITL   │  ADJUDICATOR         │ EMAIL COMPOSER     │
│  3 jobs/contractor   │  Manual  │  3 jobs/contractor   │ 5 jobs/contractor  │
│  Pending: 2          │  Est.    │  Pending: 1          │ Pending: 0         │
│  Contractors: 2/5    │  Wait: 3 │  Contractors: 1/5    │ Contractors: 1/3   │
│                      │          │                      │                    │
│  ┌─ Alice (3/3) ──┐ │ ┌──────┐ │  ┌─ Alice (2/3) ──┐ │ ┌─ Alice (1/5) ──┐│
│  │ CSB-01 ▓▓▓░ 75%│ │ │ 3    │ │  │ CSB-07 ▓▓░ 40% │ │ │ CSB-10 ▓▓░ 35% ││
│  │ CSB-02 ▓▓░░ 40%│ │ │claims│ │  │ CSB-08 ▓░░ 15% │ │ │ (empty)        ││
│  │ CSB-03 ▓░░░ 15%│ │ │      │ │  │ (empty)         │ │ │ (empty)        ││
│  └────────────────┘ │ └──────┘ │  └─────────────────┘ │ │ (empty)        ││
│                      │          │                      │ │ (empty)        ││
│  ┌─ Bob (2/3) ────┐ │          │                      │ └────────────────┘│
│  │ CSB-04 ▓▓░░ 30%│ │          │                      │                    │
│  │ CSB-05 ▓░░░ 10%│ │          │                      │                    │
│  │ (empty)         │ │          │                      │                    │
│  └────────────────┘ │          │                      │                    │
│                      │          │                      │                    │
│  EVENT LOG:          │          │                      │                    │
│  10:23 Bob spawned   │          │                      │                    │
│  10:20 Alice full    │          │                      │                    │
└──────────────────────┴──────────┴──────────────────────┴────────────────────┘
```

**Tech stack for dashboard:**
- Single HTML file with embedded CSS/JS (same pattern as existing `dashboard.html`)
- Bootstrap 5 for layout
- Vanilla JS with `setInterval(fetchState, 500)` polling loop
- CSS animations for progress bars and spawn/terminate events
- Responsive grid: 4 columns (one per stage)

**Dashboard features:**
- Contractor cards with colored borders (per contractor color)
- Job slot progress bars (animated)
- Status badges: FULL (red), AVAILABLE (green), IDLE (gray)
- Spawn event toast notifications ("Bob spawned — Alice was full")
- Terminate event notifications ("Priya terminated — no active jobs")
- Pending queue counter per stage
- Global stats header (total claims, in-flight, completed)
- Click-through from job slot to existing review form

---

## 5. Persona Injection — Detailed Mapping

### How Personas Flow Through the System

```
                           Layer 1 assigns                Agent responds
Claim CSB-001 ──────────► "Alice" ─────────────────────► "I'm Alice, reviewing..."
                                    │
                                    │  Injected into user prompt:
                                    │  "You are Alice, a claims specialist..."
                                    │
                                    ▼
                           invoke_foundry_agent(
                             agent_name="claim-assistant-agent",
                             user_message="[CONTRACTOR IDENTITY]\n
                                          You are Alice, a claims analyst.\n
                                          [JOB DATA]\n
                                          Claim ID: CSB-001\n..."
                           )
```

### Existing Persona Code (Agent3 Only) → Universal Persona

Currently in `prompts.py:14-23`, Agent3 has 8 random persona names used **only for email signatures**. With the Clone Visualizer:

| Current | Clone Visualizer |
|---------|------------------|
| Random persona from list per email | Contractor name assigned by Layer 1 |
| Used only in Agent3 email signature | Used in ALL 3 agents' user prompts |
| Cosmetic — stakeholders don't see | Operational — visible on dashboard |
| No tracking per persona | Full job tracking per contractor |

The `AGENT3_PERSONA_NAMES` list can be **replaced** by the contractor registry. The same "Alice" that classifies a claim as Classifier Contractor also gets credited on the dashboard, and a different "Alice" at the Email Composer stage handles the email.

---

## 6. Progress Tracking — How Progress Gets to the Dashboard

### Option A: Simulated Progress (PoC)

For the PoC, simulate progress using estimated stage durations:

```python
STAGE_DURATION_ESTIMATES = {
    "classifier": 15,      # ~15 seconds
    "adjudicator": 10,     # ~10 seconds
    "email_composer": 8,   # ~8 seconds
}
```

A background thread in ContractorManager increments progress every 500ms:

```python
def _tick(self):
    """Increment progress for all active jobs (simulated)."""
    for pool in self.pools.values():
        for contractor in pool.active_contractors:
            for job in contractor["active_jobs"]:
                duration = STAGE_DURATION_ESTIMATES[pool.agent_id]
                elapsed = (now - job["started_at"]).total_seconds()
                job["progress_pct"] = min(95, int(elapsed / duration * 100))
                # Never reaches 100% from simulation — only set to 100 on actual completion
```

### Option B: Real Progress from Custom Status (Production)

The orchestrator already calls `context.set_custom_status()` at each stage. Extend this to publish progress events that the ContractorManager can consume.

---

## 7. File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `shared/contractor_manager.py` | ContractorManager singleton + ContractorPool + first-fill/scale-down |
| `static/clone_dashboard.html` | Clone Visualizer real-time dashboard |

### Modified Files

| File | Changes |
|------|---------|
| `function_app.py` | Add 4 new endpoints (`/contractors/state`, `/contractors/config`, `/clone-dashboard`, contractor activity wrappers). Modify `claim_orchestrator` to call assign/complete activities. |
| `shared/models.py` | Add `JobSlot`, `Contractor`, `ContractorPoolConfig`, `ContractorPoolState` models |
| `shared/prompts.py` | Add `CONTRACTOR_PERSONA_PREFIX`. Modify `build_agent1_prompt`, `build_agent2_prompt`, `build_agent3_prompt` to accept `persona_name` parameter |
| `shared/agent_client.py` | Pass persona through to prompt builders (minor) |
| `activities/agent1_activity.py` | Pass `persona_name` to prompt builder |
| `activities/agent2_activity.py` | Pass `persona_name` to prompt builder |
| `activities/agent3_activity.py` | Use contractor name instead of random persona |

### Unchanged Files

| File | Why |
|------|-----|
| `static/dashboard.html` | Existing claims dashboard — kept as-is (different view) |
| `static/review.html` | HITL review form — unchanged |
| `host.json` | No configuration changes needed |
| `local.settings.json` | No new env vars needed for PoC |
| `requirements.txt` | No new packages needed for PoC |

---

## 8. Implementation Order

```
Phase 1 — Contractor State (2-3 days)
├── 1.1 Add Pydantic models to shared/models.py
├── 1.2 Build shared/contractor_manager.py (ContractorPool + ContractorManager)
├── 1.3 Unit test first-fill and scale-down logic
└── 1.4 Add /contractors/state and /contractors/config API endpoints

Phase 2 — Dashboard (2-3 days)
├── 2.1 Build static/clone_dashboard.html
├── 2.2 Implement polling loop (500ms)
├── 2.3 Contractor cards with progress bars
├── 2.4 Spawn/terminate event animations
└── 2.5 Add /clone-dashboard serve endpoint

Phase 3 — Orchestrator Integration (1-2 days)
├── 3.1 Add assign/complete/progress activity functions
├── 3.2 Modify claim_orchestrator to use contractor activities
├── 3.3 Test with simulated progress
└── 3.4 Verify dashboard reflects real orchestration state

Phase 4 — Persona Injection (1 day)
├── 4.1 Add CONTRACTOR_PERSONA_PREFIX to prompts.py
├── 4.2 Modify prompt builders to accept persona_name
├── 4.3 Modify activity functions to pass persona through
└── 4.4 Test agent responses include contractor identity

Phase 5 — Polish (1 day)
├── 5.1 End-to-end test with 10+ concurrent claims
├── 5.2 Dashboard event log panel
├── 5.3 Click-through from job slot to claim detail
└── 5.4 Responsive layout testing
```

---

## 9. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| **In-memory state lost on restart** | Dashboard resets, contractor assignments lost | For PoC: acceptable. For production: use Durable Entities or Redis |
| **Orchestrator determinism** | ContractorManager calls from orchestrator would break replay | Wrap ALL contractor calls in activity functions (never call from orchestrator directly) |
| **Concurrent access** | Multiple orchestrations updating ContractorManager simultaneously | Threading locks in ContractorManager (already included in design) |
| **Progress simulation drift** | Simulated progress doesn't match actual agent execution time | Set progress to 95% max from simulation, only 100% on actual completion |
| **Single function app instance** | ContractorManager singleton only exists in one process | For PoC: run single instance. For production: move state to shared store |
| **Agent3 persona conflict** | Existing random persona logic conflicts with contractor name | Replace random persona with contractor name from Layer 1 |

---

## 10. Future Production Path

| PoC (This Document) | Production Evolution |
|----------------------|---------------------|
| In-memory ContractorManager | Durable Entities per agent stage |
| Polling (500ms `setInterval`) | WebSocket via SignalR |
| Simulated progress | Real progress from agent API callbacks |
| Single instance | Multi-instance with shared state (Redis/Cosmos) |
| Hardcoded contractor config | Admin UI for contractor pool management |
| No persistence | Full audit trail in Cosmos DB |
| Manual claim submission | Continuous Service Bus ingestion |

---

## Appendix A: Contractor Configuration Registry

```json
{
  "agents": [
    {
      "agent_id": "classifier",
      "display_name": "Claim Classifier",
      "foundry_agent_name": "claim-assistant-agent",
      "capacity_per_contractor": 3,
      "max_contractors": 5,
      "contractors": [
        { "name": "Alice", "color": "#2dd4a8" },
        { "name": "Bob",   "color": "#7c5cfc" },
        { "name": "Priya", "color": "#f59e0b" },
        { "name": "David", "color": "#38bdf8" },
        { "name": "Mei",   "color": "#c084fc" }
      ]
    },
    {
      "agent_id": "adjudicator",
      "display_name": "Claim Adjudicator",
      "foundry_agent_name": "claim-approval-agent",
      "capacity_per_contractor": 3,
      "max_contractors": 5,
      "contractors": [
        { "name": "Alice", "color": "#2dd4a8" },
        { "name": "Bob",   "color": "#7c5cfc" },
        { "name": "Priya", "color": "#f59e0b" },
        { "name": "David", "color": "#38bdf8" },
        { "name": "Mei",   "color": "#c084fc" }
      ]
    },
    {
      "agent_id": "email_composer",
      "display_name": "Email Composer",
      "foundry_agent_name": "EmailComposerAgent",
      "capacity_per_contractor": 5,
      "max_contractors": 3,
      "contractors": [
        { "name": "Alice", "color": "#2dd4a8" },
        { "name": "Bob",   "color": "#7c5cfc" },
        { "name": "Priya", "color": "#f59e0b" }
      ]
    }
  ],
  "hitl_stages": [
    {
      "stage_id": "manual_estimate",
      "display_name": "Manual Estimate",
      "position_after": "classifier"
    }
  ]
}
```

## Appendix B: API Endpoints (Complete)

### Existing Endpoints (Unchanged)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard` | Existing claims dashboard |
| GET | `/api/presentation` | Stakeholder presentation |
| POST | `/api/claims/start` | Start claim orchestration |
| POST | `/api/claims/approve/{id}` | Submit manual estimate (HITL) |
| GET | `/api/claims` | List all claims |
| GET | `/api/claims/status/{id}` | Get claim status |
| GET | `/api/review/{id}` | HITL review form |
| POST | `/api/compose-email` | Direct email composition |

### New Endpoints (Clone Visualizer)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/clone-dashboard` | Serve Clone Visualizer dashboard |
| GET | `/api/contractors/state` | Full contractor state (dashboard polls this) |
| GET | `/api/contractors/config` | Contractor pool configuration |
