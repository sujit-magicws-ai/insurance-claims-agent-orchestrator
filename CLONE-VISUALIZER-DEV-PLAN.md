# Clone Visualizer — Development Plan

**7 phases. Each phase independently testable. Each phase builds on the previous without breaking existing functionality.**

---

## Phase 1: Contractor Manager Core Logic

**Goal**: Pure Python module with first-fill assignment, job completion, scale-down, and state snapshots. Zero dependency on Durable Functions — testable with a standalone script.

### Files Created

| File | Description |
|------|-------------|
| `function_app/shared/contractor_manager.py` | `ContractorPool` class + `ContractorManager` singleton |

### Files Modified

| File | Change |
|------|--------|
| `function_app/shared/models.py` | Add `JobSlot`, `Contractor`, `ContractorPoolConfig`, `ContractorPoolState` Pydantic models |

### What Gets Built

**`ContractorPool` class** — manages one agent stage's workforce:
- `assign_job(claim_id) -> contractor_name | None` — first-fill across existing contractors, spawn if all full, queue if at max
- `complete_job(claim_id)` — remove from slot, assign pending, run scale-down
- `update_progress(claim_id, pct)` — update job progress percentage
- `get_state() -> dict` — full state snapshot (contractors, slots, pending queue, counters)
- Internal `_spawn_contractor()`, `_assign_pending()`, `_scale_down()` with threading locks

**`ContractorManager` singleton** — holds 3 pools:
- `classifier` (capacity=3, max=5, names: Alice/Bob/Priya/David/Mei)
- `adjudicator` (capacity=3, max=5, names: Alice/Bob/Priya/David/Mei)
- `email_composer` (capacity=5, max=3, names: Alice/Bob/Priya)
- `assign_job(agent_id, claim_id)`, `complete_job(agent_id, claim_id)`, `get_all_state()`

### Pydantic Models Added to `models.py`

```python
class JobSlot(BaseModel):
    claim_id: str
    progress_pct: int = 0
    started_at: str
    status: str = "processing"

class ContractorState(BaseModel):
    name: str
    color: str
    capacity: int
    active_jobs: list[JobSlot] = []
    slots_used: int = 0
    jobs_completed: int = 0
    status: str = "available"       # "full" | "available" | "idle"
    is_primary: bool = False

class ContractorPoolState(BaseModel):
    agent_id: str
    display_name: str
    capacity_per_contractor: int
    max_contractors: int
    pending_queue: list[str] = []
    pending_count: int = 0
    active_contractors: list[ContractorState] = []
    contractor_count: int = 0
    total_jobs_in_flight: int = 0
    total_completed: int = 0
```

### How to Test (Independent — No `func start` needed)

Create `function_app/tests/test_contractor_manager.py`:

```
cd function_app
python -m tests.test_contractor_manager
```

**Test scenarios:**

| # | Scenario | Expected Result |
|---|----------|-----------------|
| 1 | Assign 1 job to classifier | Alice gets it (1/3 slots) |
| 2 | Assign 3 jobs to classifier | Alice full (3/3) |
| 3 | Assign 4th job | Bob spawns, gets job (1/3) |
| 4 | Assign jobs 5-6 to fill Bob | Bob full (3/3) |
| 5 | Assign 7th job | Priya spawns, gets job (1/3) |
| 6 | Complete all Bob's jobs | Bob terminated (empty, not primary) |
| 7 | Complete all Priya's jobs | Priya terminated before Bob (reverse order) |
| 8 | Complete all Alice's jobs | Alice stays (primary, never terminated) |
| 9 | Assign job after scale-down | Alice gets it (first-fill resumes) |
| 10 | Fill all 5 contractors (15 jobs) | Max reached |
| 11 | Assign 16th job | Queued in pending_queue |
| 12 | Complete 1 job when pending | Pending job auto-assigned to freed slot |
| 13 | `get_state()` returns correct JSON | All counters, statuses, slot data correct |

**Acceptance criteria**: All 13 test scenarios pass. `get_state()` returns valid JSON matching `ContractorPoolState` schema.

---

## Phase 2: Contractor State API Endpoints

**Goal**: Expose ContractorManager state over HTTP so any client (browser, Postman, curl) can read it. No dashboard yet — just raw JSON APIs.

### Files Modified

| File | Change |
|------|--------|
| `function_app/function_app.py` | Add 2 new HTTP-triggered functions: `get_contractor_state`, `get_contractor_config` |

### New Endpoints

| Method | Route | Returns |
|--------|-------|---------|
| `GET` | `/api/contractors/state` | Full contractor state JSON (all 3 pools + HITL + global counters) |
| `GET` | `/api/contractors/config` | Pool configurations (capacity, max, names per agent) |

### `GET /api/contractors/state` Response Shape

```json
{
  "timestamp": "2026-02-10T15:30:00Z",
  "stages": {
    "classifier": {
      "agent_id": "classifier",
      "display_name": "Claim Classifier",
      "capacity_per_contractor": 3,
      "max_contractors": 5,
      "pending_queue": [],
      "pending_count": 0,
      "active_contractors": [
        {
          "name": "Alice",
          "color": "#2dd4a8",
          "capacity": 3,
          "active_jobs": [],
          "slots_used": 0,
          "jobs_completed": 0,
          "status": "idle",
          "is_primary": true
        }
      ],
      "contractor_count": 1,
      "total_jobs_in_flight": 0,
      "total_completed": 0
    },
    "adjudicator": { "..." },
    "email_composer": { "..." }
  },
  "hitl": {
    "display_name": "Manual Estimate",
    "waiting_count": 0
  },
  "global": {
    "total_claims_submitted": 0,
    "total_claims_completed": 0,
    "total_claims_in_flight": 0
  }
}
```

### How to Test (Requires `func start`)

```powershell
# Terminal 1: Start emulators + function app
docker start azurite dts-emulator
cd function_app
func start

# Terminal 2: Test endpoints
curl http://localhost:7071/api/contractors/state
curl http://localhost:7071/api/contractors/config

# Verify:
# 1. /contractors/state returns valid JSON with 3 stages
# 2. Each stage shows 1 active contractor (Alice, primary, idle)
# 3. /contractors/config shows capacity and names for each pool
# 4. Existing endpoints still work: /api/health, /api/dashboard, /api/claims
```

**Acceptance criteria**: Both endpoints return valid JSON. Existing endpoints unaffected. Response matches documented schema.

---

## Phase 3: Clone Dashboard HTML

**Goal**: Build the real-time Clone Visualizer dashboard as a single HTML file. Polls `/api/contractors/state` every 500ms and renders contractor cards with job slots. Testable immediately against the Phase 2 API.

### Files Created

| File | Description |
|------|-------------|
| `function_app/static/clone_dashboard.html` | Full dashboard — HTML + CSS + JS in single file |

### Files Modified

| File | Change |
|------|--------|
| `function_app/function_app.py` | Add `serve_clone_dashboard` endpoint at `GET /api/clone-dashboard` |

### Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  HEADER BAR                                                              │
│  Clone Visualizer — AI Contractor Workforce    [Submitted: 0] [Done: 0] │
├────────────────┬──────────┬────────────────┬─────────────────────────────┤
│  CLASSIFIER    │   HITL   │  ADJUDICATOR   │  EMAIL COMPOSER             │
│  Lane          │   Lane   │  Lane          │  Lane                       │
│                │          │                │                             │
│  Pending: 0    │ Wait: 0  │  Pending: 0    │  Pending: 0                │
│  Workers: 1/5  │          │  Workers: 1/5  │  Workers: 1/3              │
│                │          │                │                             │
│ ┌─ Alice ────┐ │          │ ┌─ Alice ────┐ │ ┌─ Alice ──────────────┐   │
│ │ (idle)     │ │          │ │ (idle)     │ │ │ (idle)               │   │
│ │ ░░░░░░░░░░ │ │          │ │ ░░░░░░░░░░ │ │ │ ░░░░░░░░░░           │   │
│ │ ░░░░░░░░░░ │ │          │ │ ░░░░░░░░░░ │ │ │ ░░░░░░░░░░           │   │
│ │ ░░░░░░░░░░ │ │          │ │ ░░░░░░░░░░ │ │ │ ░░░░░░░░░░           │   │
│ └────────────┘ │          │ └────────────┘ │ │ ░░░░░░░░░░           │   │
│                │          │                │ │ ░░░░░░░░░░           │   │
│                │          │                │ └──────────────────────┘   │
├────────────────┴──────────┴────────────────┴─────────────────────────────┤
│  EVENT LOG                                                               │
│  (empty — waiting for claims)                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### Contractor Card Component

```
┌─ Alice (0/3) ─────────────── IDLE ──┐
│                                      │
│  [Slot 1] (empty)   ░░░░░░░░░░░░░  │
│  [Slot 2] (empty)   ░░░░░░░░░░░░░  │
│  [Slot 3] (empty)   ░░░░░░░░░░░░░  │
│                                      │
│  Completed: 0                        │
└──────────────────────────────────────┘

// When active:
┌─ Alice (3/3) ─────────────── FULL ──┐  ← red border
│                                      │
│  [Slot 1] CSB-001  ▓▓▓▓▓▓░░░░ 65%  │  ← animated bar
│  [Slot 2] CSB-002  ▓▓▓░░░░░░░ 30%  │
│  [Slot 3] CSB-003  ▓░░░░░░░░░ 10%  │
│                                      │
│  Completed: 14                       │
└──────────────────────────────────────┘
```

### Tech Stack (Same Pattern as Existing Dashboards)

- Single HTML file with embedded `<style>` and `<script>` (matches `dashboard.html` pattern)
- Bootstrap 5 CDN
- Vanilla JavaScript — no build tools
- `setInterval(pollState, 500)` for real-time updates
- CSS transitions on progress bars (smooth animation)
- CSS animations for contractor card spawn/terminate (fade-in / fade-out)
- Color-coded contractor borders (from contractor `color` field)
- Status badges: `FULL` (red), `AVAILABLE` (green), `IDLE` (gray)

### Polling Loop Pseudocode

```javascript
async function pollState() {
    const res = await fetch('/api/contractors/state');
    const state = await res.json();

    // For each stage (classifier, adjudicator, email_composer):
    //   - Update lane header (pending count, contractor count)
    //   - For each contractor: render/update card
    //   - For each job slot: update progress bar width + claim ID
    //   - Detect spawn events (new contractor appeared) → add to event log
    //   - Detect terminate events (contractor disappeared) → add to event log

    // Update HITL lane (waiting count)
    // Update global stats header
}

setInterval(pollState, 500);
```

### How to Test

```powershell
# Start function app (Phase 2 must be working)
cd function_app
func start

# Open browser:
# http://localhost:7071/api/clone-dashboard
```

**Manual test checklist:**

| # | Test | Expected |
|---|------|----------|
| 1 | Page loads | 4-column layout visible: Classifier, HITL, Adjudicator, Email Composer |
| 2 | Initial state | Each agent lane shows 1 contractor card (Alice, IDLE, 0 jobs) |
| 3 | Contractor cards | Show N empty slots (3 for Classifier/Adjudicator, 5 for Email Composer) |
| 4 | Header stats | "Submitted: 0 / In Flight: 0 / Completed: 0" |
| 5 | Polling active | Network tab shows `/contractors/state` calls every 500ms |
| 6 | Responsive | Columns stack on narrow viewport |

**Acceptance criteria**: Dashboard renders correctly with idle state. Polling works. No console errors.

---

## Phase 4: Orchestrator Wiring — Contractor Assignment

**Goal**: Wire the ContractorManager into the Durable Functions orchestrator. When a claim enters an agent stage, it's assigned to a contractor. When the stage completes, the slot is released. The dashboard (Phase 3) now reflects real claim processing.

### Files Modified

| File | Change |
|------|--------|
| `function_app/function_app.py` | Add 2 new activity functions (`assign_contractor_activity`, `release_contractor_activity`). Modify `claim_orchestrator` to call them before/after each agent activity. Add contractor name to `set_custom_status()`. |

### New Activity Functions

```python
@app.activity_trigger(input_name="activityInput")
def assign_contractor_activity(activityInput: dict) -> dict:
    """
    Assign a claim to a contractor slot via first-fill.

    Input:  {"agent_id": "classifier", "claim_id": "CSB-001"}
    Output: {"contractor_name": "Alice", "queued": false}
    """

@app.activity_trigger(input_name="activityInput")
def release_contractor_activity(activityInput: dict) -> dict:
    """
    Release a claim's contractor slot after stage completion.

    Input:  {"agent_id": "classifier", "claim_id": "CSB-001"}
    Output: {"released": true}
    """
```

### Modified Orchestrator Flow (Additions Marked with >>>)

```
claim_orchestrator(context):
    claim_id = input.claim_id

    # === AGENT 1 ===
>>> assign = yield call_activity("assign_contractor_activity",
>>>     {"agent_id": "classifier", "claim_id": claim_id})
>>> contractor = assign["contractor_name"]

    set_custom_status({
        "step": "agent1_processing",
>>>     "contractor": contractor,         # NEW
        "claim_id": claim_id, ...
    })

    agent1_result = yield call_activity("agent1_activity", {
>>>     "persona_name": contractor,       # NEW — passed through, used in Phase 5
        ...existing fields...
    })

>>> yield call_activity("release_contractor_activity",
>>>     {"agent_id": "classifier", "claim_id": claim_id})

    # === HITL (unchanged) ===
    ...wait_for_external_event("ApprovalDecision")...

    # === AGENT 2 ===
>>> assign = yield call_activity("assign_contractor_activity",
>>>     {"agent_id": "adjudicator", "claim_id": claim_id})
>>> contractor = assign["contractor_name"]

    agent2_result = yield call_activity("agent2_activity", {
>>>     "persona_name": contractor,
        ...existing fields...
    })

>>> yield call_activity("release_contractor_activity",
>>>     {"agent_id": "adjudicator", "claim_id": claim_id})

    # === AGENT 3 ===
>>> assign = yield call_activity("assign_contractor_activity",
>>>     {"agent_id": "email_composer", "claim_id": claim_id})
>>> contractor = assign["contractor_name"]

    agent3_result = yield call_activity("agent3_activity", {
>>>     "persona_name": contractor,
        ...existing fields...
    })

>>> yield call_activity("release_contractor_activity",
>>>     {"agent_id": "email_composer", "claim_id": claim_id})

    # ... rest unchanged
```

### Key Design Constraints

1. **Determinism**: All ContractorManager calls go through **activity functions** (not called directly from orchestrator). Activities run outside the replay loop.
2. **Backward compatibility**: The `persona_name` field is passed through to activity functions but **ignored until Phase 5**. Activity functions don't break if it's present — they just don't use it yet.
3. **In-memory state caveat**: If the function app restarts, ContractorManager resets. This is acceptable for PoC — documented as a known limitation.

### How to Test

```powershell
# Start emulators + function app
docker start azurite dts-emulator
cd function_app
func start
```

**Test 1 — Single claim flow:**

```powershell
# Submit a claim (mock mode)
curl -X POST http://localhost:7071/api/claims/start `
  -H "Content-Type: application/json" `
  -d '{"claim_id":"CV-001","email_content":"Transmission grinding","attachment_url":"https://example.com/doc.pdf","sender_email":"test@example.com"}'

# Immediately check contractor state:
curl http://localhost:7071/api/contractors/state
# Expected: classifier.active_contractors[0].active_jobs has "CV-001"

# Check claim status:
curl http://localhost:7071/api/claims/status/claim-CV-001
# Expected: custom_status.contractor = "Alice"

# After Agent1 completes (a few seconds):
curl http://localhost:7071/api/contractors/state
# Expected: classifier slot released, claim now in HITL waiting

# Approve the claim:
curl -X POST http://localhost:7071/api/claims/approve/claim-CV-001 `
  -H "Content-Type: application/json" `
  -d '{"reviewer":"test@co.com","claim_data":{"claimant":{"name":"Test"},"contract":{"contract_number":"V-123"},"vehicle":{"year":2022,"make":"Honda","model":"Accord"},"repair":{"total_estimate":750},"documents":{"damage_photos":true,"claim_form":true}}}'

# Check state again:
curl http://localhost:7071/api/contractors/state
# Expected: adjudicator has the job, then email_composer

# Open dashboard to watch visually:
# http://localhost:7071/api/clone-dashboard
```

**Test 2 — Concurrent claims (spawn test):**

```powershell
# Submit 4 claims rapidly (classifier capacity=3, should spawn Bob)
for ($i = 1; $i -le 4; $i++) {
    curl -X POST http://localhost:7071/api/claims/start `
      -H "Content-Type: application/json" `
      -d "{`"claim_id`":`"CV-10$i`",`"email_content`":`"Claim $i`",`"attachment_url`":`"https://example.com/$i.pdf`",`"sender_email`":`"test$i@example.com`"}"
}

# Check state:
curl http://localhost:7071/api/contractors/state
# Expected: classifier has Alice (3/3 FULL) + Bob (1/3 AVAILABLE)
```

**Acceptance criteria:**
- Single claim flows through all 3 agent stages with contractor assignment visible in state
- Contractor name appears in `custom_status` of orchestration
- Dashboard shows jobs appearing/disappearing from contractor slots
- 4 concurrent claims triggers Bob spawn at classifier stage

---

## Phase 5: Persona Injection into Agent Prompts

**Goal**: The contractor name assigned in Phase 4 is now injected into the user prompt for each Foundry API call. Agents respond **as** the named contractor. Agent3's email signature uses the contractor name instead of a random persona.

### Files Modified

| File | Change |
|------|--------|
| `function_app/shared/prompts.py` | Add `CONTRACTOR_PERSONA_PREFIX` constant. Modify `build_agent1_prompt()`, `build_agent2_prompt()`, `build_agent3_prompt()` to accept optional `persona_name` parameter and prepend identity block. |
| `function_app/shared/agent_client.py` | Modify `invoke_agent1()`, `invoke_agent2()`, `invoke_email_composer()` to accept and pass through `persona_name`. Update mock responses to include persona in output. |
| `function_app/activities/agent1_activity.py` | Read `persona_name` from `input_data`, pass to `invoke_agent1()`. |
| `function_app/activities/agent2_activity.py` | Read `persona_name` from `input_data`, pass to `invoke_agent2()`. |
| `function_app/activities/agent3_activity.py` | Read `persona_name` from `input_data`, pass to `invoke_email_composer()` as explicit persona instead of random. |

### Persona Prefix (Added to `prompts.py`)

```python
CONTRACTOR_PERSONA_PREFIX = """[CONTRACTOR IDENTITY]
You are {contractor_name}, a claims processing specialist at JM&A Group, Fidelity Warranty Services.
Sign off and identify yourself as {contractor_name} in all responses.

---

"""
```

This is **prepended** to the existing user prompt when `persona_name` is provided. The system prompt is **unchanged** — it still describes what the agent does, not who it is.

### Change to Prompt Builders

Each `build_agentN_prompt()` function gains an optional `persona_name` parameter:

```python
def build_agent1_prompt(claim_id, email_content, attachment_url,
                        sender_email, received_date, persona_name=None):
    prefix = ""
    if persona_name:
        prefix = CONTRACTOR_PERSONA_PREFIX.format(contractor_name=persona_name)
    return prefix + AGENT1_USER_PROMPT_TEMPLATE.format(...)
```

Same pattern for `build_agent2_prompt()` and `build_agent3_prompt()`.

### Change to Agent Client

```python
def invoke_agent1(input_data, instance_id=None, max_retries=2, persona_name=None):
    ...
    prompt = build_agent1_prompt(
        ...,
        persona_name=persona_name  # NEW
    )
    ...
```

### Change to Activity Functions

```python
# agent1_activity.py
def run_agent1_activity(input_data: dict) -> dict:
    instance_id = input_data.pop("_instance_id", None)
    persona_name = input_data.pop("persona_name", None)  # NEW
    ...
    result = invoke_agent1(agent1_input, instance_id=instance_id,
                           persona_name=persona_name)  # NEW
    ...
```

### Agent3 Special Case

Currently `invoke_email_composer()` passes `persona_name=None` to `build_agent3_prompt()`, which triggers `get_random_persona()`. With this change:

- If `persona_name` is provided (from contractor assignment) → use it for the signature
- If `persona_name` is `None` (e.g., direct `/compose-email` API call) → fall back to random persona (existing behavior preserved)

### How to Test

**Test 1 — Mock mode (verify persona flows through):**

```powershell
# Set mock mode in local.settings.json: "AGENT_MOCK_MODE": "true"
cd function_app
func start

# Submit a claim:
curl -X POST http://localhost:7071/api/claims/start `
  -H "Content-Type: application/json" `
  -d '{"claim_id":"CV-P01","email_content":"Transmission issue","attachment_url":"https://example.com/doc.pdf","sender_email":"test@example.com"}'

# Check claim status after Agent1 completes:
curl http://localhost:7071/api/claims/status/claim-CV-P01

# In function app console logs, verify:
#   "Invoking Agent1 for claim CV-P01" includes persona
#   Mock response includes contractor identity
```

**Test 2 — Real agents (verify persona in prompt):**

```powershell
# Set mock mode false, configure real Foundry endpoints
# Submit a claim and check the agent response
# Agent3 email should sign off as the assigned contractor name, not a random persona
```

**Test 3 — Direct email API still works (backward compat):**

```powershell
# POST /api/compose-email should still work with random persona
curl -X POST http://localhost:7071/api/compose-email `
  -H "Content-Type: application/json" `
  -d '{"claim_id":"DIRECT-01","recipient_name":"Test","recipient_email":"t@t.com","email_purpose":"Test","outcome_summary":"Test approved"}'

# Response should have an email with a random persona signature (not "null")
```

**Acceptance criteria:**
- Agent prompts include contractor persona prefix when persona_name is provided
- Mock responses reflect persona (visible in logs)
- Agent3 email signature uses contractor name from Layer 1
- Direct `/compose-email` API (no orchestrator) still uses random persona

---

## Phase 6: Progress Simulation + HITL Counter

**Goal**: Jobs in the dashboard show animated progress (not stuck at 0%). HITL lane shows count of claims waiting for human review. Event log captures spawn/terminate events.

### Files Modified

| File | Change |
|------|--------|
| `function_app/shared/contractor_manager.py` | Add `_progress_simulation_thread()` that increments progress based on estimated stage durations. Add HITL counter (`hitl_waiting_count`). Add event log buffer. |
| `function_app/function_app.py` | Update `submit_estimate` endpoint to decrement HITL counter. Update `claim_orchestrator` to increment HITL counter when entering `awaiting_approval`. |
| `function_app/static/clone_dashboard.html` | Render event log panel. Animate progress bar transitions. Show HITL waiting count. |

### Progress Simulation Design

```python
ESTIMATED_STAGE_DURATION_SECONDS = {
    "classifier": 15,       # Agent1 typically takes ~15s
    "adjudicator": 10,      # Agent2 typically takes ~10s
    "email_composer": 8,    # Agent3 typically takes ~8s
}
```

A daemon thread ticks every 500ms:
- For each active job, calculate `elapsed / estimated_duration * 100`
- Cap at **95%** — only the `complete_job()` call sets it to 100%
- This ensures the progress bar never "finishes" before the agent actually returns

### Event Log

```python
class ContractorEvent:
    timestamp: str
    agent_id: str
    event_type: str   # "spawn" | "terminate" | "job_assigned" | "job_completed"
    contractor_name: str
    claim_id: str | None
    message: str

# Buffer: last 50 events (ring buffer)
```

The event log is included in the `/contractors/state` response:

```json
{
  "events": [
    {"timestamp": "10:23:15", "type": "spawn", "agent": "classifier", "contractor": "Bob",
     "message": "Bob spawned — Alice was full (3/3)"},
    {"timestamp": "10:23:14", "type": "job_assigned", "agent": "classifier", "contractor": "Alice",
     "claim_id": "CV-003", "message": "CV-003 assigned to Alice (3/3)"}
  ]
}
```

### HITL Counter

The ContractorManager gains:
- `increment_hitl_waiting()` — called by orchestrator activity when entering HITL wait
- `decrement_hitl_waiting()` — called when approval event is received
- Exposed in `get_all_state()["hitl"]["waiting_count"]`

### Dashboard Event Log Panel

Bottom of dashboard, below the 4-column grid:

```
┌── EVENT LOG ─────────────────────────────────────────────────────┐
│  10:23:15  🟢 Bob SPAWNED at Classifier — Alice was full (3/3)  │
│  10:23:14  📋 CV-003 assigned to Alice at Classifier (3/3)      │
│  10:23:12  📋 CV-002 assigned to Alice at Classifier (2/3)      │
│  10:23:10  📋 CV-001 assigned to Alice at Classifier (1/3)      │
│  10:23:00  ⚡ System started                                     │
└──────────────────────────────────────────────────────────────────┘
```

### How to Test

```powershell
cd function_app
func start

# Open dashboard: http://localhost:7071/api/clone-dashboard
```

**Test 1 — Progress animation:**

```powershell
# Submit a claim:
curl -X POST http://localhost:7071/api/claims/start `
  -H "Content-Type: application/json" `
  -d '{"claim_id":"CV-A01","email_content":"Claim","attachment_url":"https://example.com/a.pdf","sender_email":"a@test.com"}'

# Watch dashboard:
# - Alice's first slot shows "CV-A01" with progress bar growing from 0% to 95%
# - When Agent1 completes, bar jumps to 100% briefly, then slot empties
# - HITL lane shows "Waiting: 1"
```

**Test 2 — Event log:**

```powershell
# Submit 4 claims rapidly
# Watch event log show:
#   "CV-A01 assigned to Alice at Classifier"
#   "CV-A02 assigned to Alice at Classifier"
#   "CV-A03 assigned to Alice at Classifier"
#   "Alice full (3/3) at Classifier"
#   "Bob SPAWNED at Classifier"
#   "CV-A04 assigned to Bob at Classifier"
```

**Test 3 — HITL counter:**

```powershell
# Submit claim, let it reach HITL
# Dashboard shows "HITL Waiting: 1"
# Approve the claim
# Dashboard shows "HITL Waiting: 0"
```

**Acceptance criteria:**
- Progress bars animate smoothly during agent processing
- Bars never exceed 95% from simulation — only 100% on real completion
- HITL counter increments/decrements correctly
- Event log shows last 50 events with timestamps
- Spawn/terminate events are clearly distinguishable

---

## Phase 7: End-to-End Load Test + Dashboard Polish

**Goal**: Full integration test with 10+ concurrent claims. Validate first-fill, spawn, scale-down, persona injection, and dashboard visualization all working together. Polish UI details.

### Files Modified

| File | Change |
|------|--------|
| `function_app/static/clone_dashboard.html` | Add: click-through from job slot to claim detail, auto-scroll event log, responsive breakpoints, contractor spawn/terminate CSS animations, pipeline flow arrows between lanes |
| `function_app/function_app.py` | Add contractor info to `list_claims` response (which contractor handled each stage) |

### Dashboard Polish Items

| Feature | Description |
|---------|-------------|
| **Spawn animation** | New contractor card fades in with green glow border |
| **Terminate animation** | Card fades out with brief "Terminated" badge |
| **Job slot click** | Clicking a claim ID in a slot opens claim detail (existing `/api/claims/status/{id}`) |
| **Stage flow arrows** | Visual arrows between lanes: Classifier → HITL → Adjudicator → Email Composer |
| **Auto-scroll event log** | Event log auto-scrolls to latest, with manual scroll lock |
| **Contractor color consistency** | Alice always `#2dd4a8`, Bob always `#7c5cfc`, etc. across all lanes |
| **Responsive layout** | 4-col on desktop, 2-col on tablet, 1-col on mobile |
| **Full/Available/Idle badges** | Clear status badge on each contractor card with color coding |

### Load Test Script (`function_app/tests/test_clone_load.py`)

```python
"""
Submit N claims rapidly and observe dashboard behavior.
Run while function app is running and dashboard is open.
"""
import requests
import time

BASE_URL = "http://localhost:7071/api"
NUM_CLAIMS = 12  # Should trigger 4 classifier contractors (capacity=3)

for i in range(1, NUM_CLAIMS + 1):
    claim_id = f"LOAD-{i:03d}"
    resp = requests.post(f"{BASE_URL}/claims/start", json={
        "claim_id": claim_id,
        "email_content": f"Load test claim {i} - transmission issue",
        "attachment_url": f"https://example.com/load/{claim_id}.pdf",
        "sender_email": f"load{i}@test.com"
    })
    print(f"Submitted {claim_id}: {resp.status_code}")
    time.sleep(0.3)  # Slight stagger to see first-fill in action
```

### How to Test

```powershell
# Terminal 1: Start emulators + function app (mock mode recommended)
docker start azurite dts-emulator
# Ensure local.settings.json has "AGENT_MOCK_MODE": "true"
cd function_app
func start

# Terminal 2: Open dashboard
# http://localhost:7071/api/clone-dashboard

# Terminal 3: Run load test
cd function_app
python -m tests.test_clone_load
```

**What to observe on dashboard:**

| Time | Expected Dashboard State |
|------|--------------------------|
| 0-1s | Claims 1-3 fill Alice at Classifier |
| 1-2s | Claim 4 triggers Bob spawn, Bob gets claim 4 |
| 2-3s | Claims 5-6 fill Bob, Claim 7 triggers Priya spawn |
| 3-4s | Claims 7-9 fill Priya, Claim 10 triggers David spawn |
| ~5s | Alice's claims complete (progress hit 100%), slots free |
| ~6s | First-fill resumes: new claims go to Alice (not David) |
| ~8s | Claims reach HITL: HITL counter rises |
| - | No claims auto-approve (waiting for HITL) |

**Then batch-approve to watch adjudicator + email composer stages:**

```powershell
# Approve all waiting claims:
$claims = (curl http://localhost:7071/api/claims).Content | ConvertFrom-Json
foreach ($claim in $claims.claims) {
    if ($claim.step -eq "awaiting_approval") {
        $body = '{"reviewer":"load-test@co.com","claim_data":{"claimant":{"name":"Load Test"},"contract":{"contract_number":"V-999"},"vehicle":{"year":2022,"make":"Honda","model":"Accord"},"repair":{"total_estimate":750},"documents":{"damage_photos":true,"claim_form":true}}}'
        curl -X POST "http://localhost:7071/api/claims/approve/$($claim.instance_id)" `
          -H "Content-Type: application/json" -d $body
    }
}
```

**After approvals, observe:**
- Adjudicator lane: Alice fills up, Bob spawns if needed
- Email Composer lane: Alice fills up (capacity=5, so may handle all)
- Scale-down: After all claims complete, only Alice remains at each stage
- Event log: Full history of spawn/terminate/assign/complete events

### Full End-to-End Checklist

| # | Check | Pass? |
|---|-------|-------|
| 1 | 12 claims submitted without errors | |
| 2 | Classifier: Alice fills (3/3), Bob spawns at claim 4 | |
| 3 | Classifier: First-fill resumes to Alice when she has free slots | |
| 4 | HITL waiting count matches actual waiting claims | |
| 5 | Approval triggers Adjudicator stage processing | |
| 6 | Adjudicator: Contractors spawn as needed | |
| 7 | Email Composer: Claims flow through, emails sent (mock) | |
| 8 | Scale-down: After all complete, only Alice remains per stage | |
| 9 | Dashboard: All animations smooth, no flickering | |
| 10 | Dashboard: Event log captures full history | |
| 11 | Dashboard: Click on claim ID opens detail | |
| 12 | Existing `/api/dashboard` still works | |
| 13 | Existing `/api/claims` still returns all claims | |
| 14 | Function app console shows persona names in logs | |

**Acceptance criteria:** All 14 checks pass. Dashboard visually demonstrates the contractor scaling model with first-fill, spawn, and scale-down for a stakeholder demo.

---

## Summary — Phase Dependencies

```
Phase 1                    Phase 2                Phase 3
ContractorManager    ───►  API Endpoints    ───►  Dashboard HTML
(Pure Python)              (/contractors/*)        (clone_dashboard.html)
    │                          │                       │
    │                          │                       │
    ▼                          ▼                       ▼
Phase 4                                           Phase 6
Orchestrator Wiring  ─────────────────────────►  Progress Simulation
(assign/release                                   + HITL Counter
 activities)                                      + Event Log
    │
    ▼
Phase 5                                           Phase 7
Persona Injection    ─────────────────────────►  Load Test + Polish
(prompts + activities)
```

| Phase | Dependencies | Can Start After | Estimated Effort |
|-------|-------------|-----------------|-----------------|
| 1 | None | Immediately | 3-4 hours |
| 2 | Phase 1 | Phase 1 | 1-2 hours |
| 3 | Phase 2 | Phase 2 | 4-6 hours |
| 4 | Phase 1, Phase 2 | Phase 2 | 3-4 hours |
| 5 | Phase 4 | Phase 4 | 2-3 hours |
| 6 | Phase 4, Phase 3 | Phase 4 + Phase 3 | 3-4 hours |
| 7 | All previous | Phase 6 | 3-4 hours |

**Total**: ~20-27 hours of implementation work.

---

## Files Inventory — Complete

### New Files (3)

| File | Created In |
|------|-----------|
| `function_app/shared/contractor_manager.py` | Phase 1 |
| `function_app/static/clone_dashboard.html` | Phase 3 |
| `function_app/tests/test_contractor_manager.py` | Phase 1 |

### Modified Files (7)

| File | Modified In | Nature of Change |
|------|------------|------------------|
| `function_app/shared/models.py` | Phase 1 | Add 3 Pydantic models (additive) |
| `function_app/function_app.py` | Phase 2, 4, 6 | Add endpoints + activity functions + orchestrator changes |
| `function_app/shared/prompts.py` | Phase 5 | Add persona prefix + modify 3 builder functions |
| `function_app/shared/agent_client.py` | Phase 5 | Add `persona_name` parameter to 3 invoke functions |
| `function_app/activities/agent1_activity.py` | Phase 5 | Pass `persona_name` through (1-2 lines) |
| `function_app/activities/agent2_activity.py` | Phase 5 | Pass `persona_name` through (1-2 lines) |
| `function_app/activities/agent3_activity.py` | Phase 5 | Use contractor name instead of random persona (3-4 lines) |

### Untouched Files

All other files remain unchanged: `host.json`, `local.settings.json`, `requirements.txt`, `static/dashboard.html`, `static/review.html`, `static/presentation.html`, `activities/notify_activity.py`, `activities/send_email_activity.py`.
