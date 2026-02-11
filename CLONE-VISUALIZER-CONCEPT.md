# Clone Visualizer — Architecture & Portability Guide

## Purpose

This document explains the **Agent → AI Contractor (Persona) → Concurrent Jobs** scaling model and how to build a multi-agent Clone Dashboard for any workflow. The core idea: each AI Contractor is a **named persona that simulates a real human contractor** who can handle N jobs concurrently. When a contractor is full, a new one is spawned. First-fill logic — just like how a real workforce scales.

---

## 1. Core Concept — The Contractor Model

**An AI Contractor is a named persona that handles N concurrent jobs — like a real person.**

A human claims adjuster named Alice can juggle 3 cases at once. When her plate is full, the office hires Bob. When Bob is also full, they bring in Priya. When the workload drops, Priya is let go first, then Bob. Alice is always there.

This is exactly how AI Contractors work:

```
AGENT: Document Extractor                 Capacity per contractor: N = 3
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌─ Alice (AI Contractor #1) ──────────────────┐   ALWAYS ACTIVE   │
│  │  Slot 1: CLM-1001 ▓▓▓▓▓▓░░ 75%             │                   │
│  │  Slot 2: CLM-1002 ▓▓▓░░░░░ 35%             │                   │
│  │  Slot 3: CLM-1003 ▓▓░░░░░░ 20%             │   ← FULL (3/3)   │
│  └──────────────────────────────────────────────┘                   │
│                                                                     │
│  ┌─ Bob (AI Contractor #2) ────────────────────┐   SPAWNED         │
│  │  Slot 1: CLM-1004 ▓▓▓▓░░░░ 50%             │   (Alice was full)│
│  │  Slot 2: CLM-1005 ▓░░░░░░░ 10%             │                   │
│  │  Slot 3: (empty)                             │   ← 2/3 slots    │
│  └──────────────────────────────────────────────┘                   │
│                                                                     │
│  Pending queue: CLM-1006, CLM-1007                                  │
│  → Bob has 1 empty slot, CLM-1006 goes to Bob                      │
│  → Bob full after that, if CLM-1007 arrives → spawn Priya           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### First-Fill Logic

1. **Fill the first contractor** (Alice) up to N slots
2. Only when Alice is **completely full**, spawn the next contractor (Bob)
3. Fill Bob up to N slots
4. Only when Bob is also full, spawn the next contractor (Priya)
5. Continue until max contractors reached

### Scale-Down Logic

1. When a contractor's **all slots become empty**, terminate that contractor
2. Terminate in **reverse spawn order** — last hired, first fired (Priya before Bob)
3. **Never terminate the first contractor** (Alice) — she's always active, even with 0 jobs

### Why named Personas?

Because this simulates a **real workforce**. Each contractor has a **name and identity injected into the user prompt** — so the agent actually responds as Alice or Bob. Stakeholders can see: "Alice is handling 3 cases, Bob just picked up 2 more." The names are not cosmetic — they are:

1. **Injected into every API call** — the agent responds as that persona (signs off as Alice, uses Alice's name in correspondence)
2. **Operational identities** — each has its own job slots, utilization metrics, and lifecycle
3. **Human-relatable** — makes AI scaling tangible for stakeholders and end-users who receive responses "from Alice"

---

## 2. The Workflow — Auto Insurance Claims Processing

```
┌─────────┐    ┌───────────┐    ┌──────┐    ┌──────────────┐    ┌────────────┐    ┌──────────┐
│ START   │    │  AGENT 1  │    │ HITL │    │   AGENT 2    │    │  AGENT 3   │    │   END    │
│ Process │───▶│  Document │───▶│Human │───▶│ Adjudication │───▶│   Email    │───▶│ Process  │
│         │    │ Extractor │    │      │    │              │    │  Composer  │    │          │
│Poll     │    │           │    │Enters│    │Business rules│    │Drafts      │    │Sends     │
│email    │    │Extract key│    │damage│    │→ Auto-Approve│    │response    │    │email     │
│inbox    │    │claim info │    │costs │    │→ Auto-Deny   │    │email       │    │          │
│→ blob   │    │from docs  │    │      │    │→ Escalate    │    │            │    │          │
│→ store  │    │           │    │      │    │              │    │            │    │          │
└─────────┘    └───────────┘    └──────┘    └──────────────┘    └────────────┘    └──────────┘
   fixed        CONTRACTORS      fixed         CONTRACTORS        CONTRACTORS       fixed
                scale here                     scale here         scale here
```

| Stage | Type | What It Does | Scaleable? |
|-------|------|-------------|------------|
| **Start Process** | Automated | Polls email inbox, pushes attachment to Blob (public URL), writes to datastore | No |
| **Agent 1: Document Extractor** | AI Agent | OCR on attachment + parse email → structured claim data | **Yes — spawns contractors** |
| **HITL: Damage Assessment** | Human | Reviews extracted data, enters damage costs | No (human queue) |
| **Agent 2: Adjudication** | AI Agent | Applies business rules → Auto-Approve / Auto-Deny / Escalate | **Yes — spawns contractors** |
| **Agent 3: Email Composer** | AI Agent | Drafts response email for approve/deny verdicts | **Yes — spawns contractors** |
| **End Process** | Automated | Sends the drafted email | No |

---

## 3. Terminology

| Term | Definition |
|------|-----------|
| **Workflow** | End-to-end pipeline of stages. A claim flows through all stages sequentially. |
| **Stage** | One step: Process (automated), Agent (AI, scaleable), or HITL (human). |
| **Agent** | A single AI definition (model + instructions + tools). Defined once. Never duplicated. |
| **AI Contractor (Persona)** | A named instance of an agent that handles **N concurrent jobs**. Simulates a real person. Alice, Bob, Priya are contractors — not styles, not personality variations — they run the exact same agent. The name is an operational identity for tracking. |
| **Job Slot** | One concurrent work item a contractor is processing. Each contractor has N slots. |
| **Capacity (N)** | Max concurrent jobs per contractor. Configurable per agent. |
| **Skill/Tool** | A capability attached to an agent (OpenAPI, MCP, Code Interpreter). |
| **Work Item** | A claim flowing through the pipeline. Occupies one job slot when being processed. |

---

## 4. Scaling Mechanics — Detailed

### Configuration per Agent

```json
{
  "agent_id": "doc-extractor",
  "capacity_per_contractor": 3,
  "max_contractors": 5,
  "contractors": ["Alice", "Bob", "Priya", "David", "Mei"]
}
```

### First-Fill Algorithm

```
function assignJob(agent, job):
    // Try to fit into existing contractors (first-fill)
    for contractor in agent.active_contractors (in spawn order):
        if contractor.active_jobs < agent.capacity_per_contractor:
            contractor.add_job(job)
            return

    // All existing contractors are full — spawn next one
    if agent.active_contractors.count < agent.max_contractors:
        next = agent.contractor_names[agent.active_contractors.count]
        spawn(next)
        next.add_job(job)
    else:
        // Max contractors reached — job stays in pending queue
        queue.add(job)
```

### Walkthrough — N = 3, incoming jobs over time

```
Time 1:  Job 1 arrives
         Alice: [Job1, _, _]        ← Alice has capacity

Time 2:  Jobs 2-3 arrive
         Alice: [Job1, Job2, Job3]  ← Alice full

Time 3:  Job 4 arrives
         Alice: [Job1, Job2, Job3]  ← full
         Bob:   [Job4, _, _]        ← Bob spawned!

Time 4:  Jobs 5-7 arrive
         Alice: [Job1, Job2, Job3]  ← full
         Bob:   [Job4, Job5, Job6]  ← Bob full
         Priya: [Job7, _, _]        ← Priya spawned!

Time 5:  Job1, Job2 complete
         Alice: [Job3, _, _]        ← Alice has 2 free slots
         Bob:   [Job4, Job5, Job6]  ← still working
         Priya: [Job7, _, _]        ← still working

Time 6:  Job 8 arrives
         Alice: [Job3, Job8, _]     ← FIRST-FILL: Alice gets it (not Bob/Priya)
         Bob:   [Job4, Job5, Job6]
         Priya: [Job7, _, _]

Time 7:  Job4, Job5, Job6, Job7 all complete
         Alice: [Job3, Job8, _]
         Bob:   [_, _, _]           ← empty
         Priya: [_, _, _]           ← empty → TERMINATE Priya, then Bob

Time 8:  After scale-down
         Alice: [Job3, Job8, _]     ← only Alice remains
```

### Scale-Down Rules

1. After any job completion, check contractors in **reverse order**
2. If a contractor has **0 active jobs** AND is not the first contractor → terminate
3. First contractor (Alice) is **never terminated** — even at 0 jobs she stays idle
4. A contractor with any active jobs is **never terminated** — wait for jobs to finish

---

## 5. Architecture — Two Layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      LAYER 1: ORCHESTRATION BACKEND                      │
│                      (FastAPI / your backend)                            │
│                                                                          │
│  For EACH agent stage:                                                   │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │  AGENT: Document Extractor          capacity = 3, max = 5     │      │
│  │                                                                │      │
│  │  Pending Queue: [CLM-1008, CLM-1009]                          │      │
│  │                                                                │      │
│  │  ┌─ Alice ────────┐  ┌─ Bob ──────────┐  ┌─ Priya ────────┐  │      │
│  │  │ CLM-1001 (80%) │  │ CLM-1004 (45%) │  │ CLM-1007 (15%) │  │      │
│  │  │ CLM-1002 (60%) │  │ CLM-1005 (30%) │  │ (empty)        │  │      │
│  │  │ CLM-1003 (25%) │  │ CLM-1006 (10%) │  │ (empty)        │  │      │
│  │  └────────────────┘  └────────────────┘  └────────────────┘  │      │
│  └────────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  Responsibilities:                                                       │
│  - Pending queue per agent stage                                         │
│  - First-fill job assignment                                             │
│  - Contractor spawn/terminate lifecycle                                  │
│  - Persona injection into user prompt                                    │
│  - Job progress tracking                                                 │
│  - Inter-stage handoff (Agent 1 done → HITL queue → Agent 2 queue)       │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │  Each job = one API call with persona
                               │  injected in the user prompt
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│          LAYER 2: AZURE AI FOUNDRY (Managed Agent Service)               │
│                                                                          │
│  Agent 1: Doc Extractor (1 definition, tools: OCR + Code Interpreter)    │
│  Agent 2: Adjudication  (1 definition, tools: Code Interpreter)          │
│  Agent 3: Email Composer (1 definition, tools: Code Interpreter)         │
│                                                                          │
│  Each API call receives:                                                 │
│    system prompt (fixed) + user prompt (PERSONA + job data)              │
│                                                                          │
│  Layer 1 injects the contractor persona into the USER PROMPT:            │
│    "You are Alice, a claims document analyst. [job data follows]"        │
│  The agent responds AS that persona for this call.                       │
│                                                                          │
│  Foundry is a MANAGED SERVICE:                                           │
│  - Compute, scaling, and infrastructure are handled by Azure             │
│  - No containers, KEDA, or Kubernetes needed                             │
│  - You just make API calls; Foundry handles the rest                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key point**: The agent definition (system prompt + tools) is created **once** in Foundry. The persona is **not** part of the agent definition — it is injected into the **user prompt** on every API call by Layer 1. When Alice processes CLM-1001, Layer 1 sends: `"You are Alice, a claims analyst. [CLM-1001 data]"`. When Bob processes CLM-1004, Layer 1 sends: `"You are Bob, a claims analyst. [CLM-1004 data]"`. Same agent, same system prompt, different user prompt per contractor per job.

This means:
- **Adding a new contractor** (e.g., "David") = adding a name to Layer 1's config. No Foundry redeployment.
- **Concurrency management** (who has capacity, who's full) = Layer 1's job.
- **Persona identity** (responding as Alice vs Bob) = injected in the user prompt per call.

### Persona Injection — User Prompt

The agent's **system prompt** is fixed and generic — it describes what the agent does, not who it is. The persona is prepended to the **user prompt** on each API call:

```python
# Layer 1 builds the user prompt per job:
user_prompt = f"""
[CONTRACTOR IDENTITY]
You are {contractor.name}, a claims document analyst.
Respond and sign off as {contractor.name}.

[JOB DATA]
Claim ID: {job.claim_id}
Email body: {job.email_body}
Attachment URL: {job.attachment_url}
"""

# API call to Foundry — same agent definition, persona in user prompt:
response = openai_client.responses.create(
    model=agent_model,
    input=user_prompt
)
```

Why user prompt and not system prompt?
- **System prompt is the agent definition** — fixed at deploy time, shared by all contractors
- **User prompt changes per call** — different persona, different job data
- One agent definition serves all contractors. No duplication.

---

## 6. AI Contractor Registry

Contractors are defined per agent. Each agent has its own pool of named contractors.

```json
{
  "agents": [
    {
      "agent_id": "doc-extractor",
      "name": "Document Extractor",
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
      "agent_id": "adjudication",
      "name": "Adjudication",
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
      "agent_id": "email-composer",
      "name": "Email Composer",
      "capacity_per_contractor": 5,
      "max_contractors": 3,
      "contractors": [
        { "name": "Alice", "color": "#2dd4a8" },
        { "name": "Bob",   "color": "#7c5cfc" },
        { "name": "Priya", "color": "#f59e0b" }
      ]
    }
  ]
}
```

Notes:
- Different agents can share the same contractor names (Alice at Agent 1 and Alice at Agent 2 are independent)
- Different agents can have different capacities (Extractor: 3 jobs/contractor, Email Composer: 5 jobs/contractor)
- Contractor names can be anything — human names, team names, region names ("East-1", "West-1"), or identifiers ("Worker-A")

---

## 7. Data Model

### 7.1 Contractor (Runtime State)

```json
{
  "contractor_name": "Alice",
  "agent_id": "doc-extractor",
  "status": "active",
  "capacity": 3,
  "active_jobs": [
    { "claim_id": "CLM-1001", "progress_pct": 80, "started_at": "10:20:00" },
    { "claim_id": "CLM-1002", "progress_pct": 60, "started_at": "10:21:00" },
    { "claim_id": "CLM-1003", "progress_pct": 25, "started_at": "10:23:00" }
  ],
  "jobs_completed": 14,
  "spawn_time": null,
  "is_primary": true
}
```

- `is_primary: true` → this contractor is never terminated (Alice)
- `active_jobs` array length = current utilization (3/3 = full)
- `status`: `active` (has been spawned) or `terminated`

### 7.2 Work Item (Queue Entry)

```json
{
  "id": "CLM-1042",
  "current_stage": "agent_1_extractor",
  "status": "processing",
  "assigned_contractor": "Bob",
  "data": {
    "email_body": "I was rear-ended at Main St on Jan 10...",
    "attachment_url": "https://blob.core.windows.net/claims/CLM-1042-report.pdf"
  }
}
```

Status flow per stage: `pending` → `processing` → `done` → moves to next stage as `pending`

### 7.3 Agent Stage (Runtime State)

```json
{
  "agent_id": "doc-extractor",
  "pending_queue": ["CLM-1008", "CLM-1009"],
  "active_contractors": ["Alice", "Bob", "Priya"],
  "total_jobs_in_flight": 8,
  "total_completed": 42,
  "utilization": {
    "Alice": { "slots_used": 3, "slots_total": 3 },
    "Bob":   { "slots_used": 3, "slots_total": 3 },
    "Priya": { "slots_used": 2, "slots_total": 3 }
  }
}
```

---

## 8. Dashboard Layout — 3-Agent Contractor View

Each agent stage is a lane. Each contractor within a lane is a card showing N job slots.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  HEADER: Auto Insurance Claims Processing    Total: 24  │  Processed: 18       │
├─────────────────────────┬──────────┬───────────────────────┬────────────────────┤
│  AGENT 1: Doc Extractor │   HITL   │  AGENT 2: Adjudicat.  │ AGENT 3: Email     │
│  Capacity: 3 jobs/person│  Damage  │  Capacity: 3 jobs/per │ Capacity: 5 j/per  │
│  Pending: 2             │  Entry   │  Pending: 1           │ Pending: 0         │
│  Contractors: 3/5       │  Wait: 3 │  Contractors: 2/5     │ Contractors: 1/3   │
│                         │          │                       │                    │
│  ┌─ Alice (3/3) ─────┐ │ ┌──────┐ │  ┌─ Alice (3/3) ────┐ │ ┌─ Alice (2/5) ──┐│
│  │ CLM-01 ▓▓▓▓▓░ 80% │ │ │ John │ │  │ CLM-10 ▓▓▓░░ 55%│ │ │ CLM-18 ▓▓░░ 40%││
│  │ CLM-02 ▓▓▓░░░ 50% │ │ │ 3 ▼  │ │  │ CLM-11 ▓▓░░░ 35%│ │ │ CLM-19 ▓░░░ 20%││
│  │ CLM-03 ▓▓░░░░ 30% │ │ └──────┘ │  │ CLM-12 ▓░░░░ 15%│ │ │ (empty)        ││
│  └────────────────────┘ │          │  └──────────────────┘ │ │ (empty)        ││
│                         │          │                       │ │ (empty)        ││
│  ┌─ Bob (3/3) ───────┐ │          │  ┌─ Bob (2/3) ──────┐ │ └────────────────┘│
│  │ CLM-04 ▓▓▓▓░░ 65% │ │          │  │ CLM-13 ▓▓▓░░ 50%│ │                    │
│  │ CLM-05 ▓▓░░░░ 30% │ │          │  │ CLM-14 ▓░░░░ 15%│ │                    │
│  │ CLM-06 ▓░░░░░ 10% │ │          │  │ (empty)          │ │                    │
│  └────────────────────┘ │          │  └──────────────────┘ │                    │
│                         │          │                       │                    │
│  ┌─ Priya (2/3) ─────┐ │          │                       │                    │
│  │ CLM-07 ▓▓░░░░ 30% │ │          │                       │                    │
│  │ CLM-08 ▓░░░░░  5% │ │          │                       │                    │
│  │ (empty)            │ │          │                       │                    │
│  └────────────────────┘ │          │                       │                    │
│                         │          │                       │                    │
│  ↑ "Priya spawned —    │          │                       │                    │
│   Alice & Bob full"     │          │                       │                    │
└─────────────────────────┴──────────┴───────────────────────┴────────────────────┘
```

### Contractor Card Anatomy

```
┌─ Alice (3/3) ─────────────────────┐
│                                   │
│  [Slot 1] CLM-1001  ▓▓▓▓▓▓░░ 80% │   ← progress bar per job
│  [Slot 2] CLM-1002  ▓▓▓░░░░░ 50% │
│  [Slot 3] CLM-1003  ▓▓░░░░░░ 30% │
│                                   │
│  Jobs completed: 14               │   ← lifetime counter
│  Status: FULL                     │   ← FULL / AVAILABLE / IDLE
└───────────────────────────────────┘
```

Statuses:
- **FULL** — all N slots occupied (highlighted border)
- **AVAILABLE** — has empty slots, accepting new jobs
- **IDLE** — 0 active jobs (only the primary contractor can be idle; others get terminated)

---

## 9. Agent Definitions (Azure AI Foundry)

### Agent 1: Document Extractor

```python
PromptAgentDefinition(
    model="gpt-4o",
    instructions="""You are a claims document extractor.
You will receive an email body describing an insurance claim and a URL to an attached document.

Steps:
1. Use the Document OCR tool to extract text from the attachment URL
2. Parse the email body for additional context
3. Extract and return structured claim data as JSON:
   - claimant_name, policy_number, incident_date, incident_location
   - vehicle_year, vehicle_make, vehicle_model
   - damage_description, other_parties_involved
   - police_report_number (if available)

Always return valid JSON. If a field cannot be determined, set it to null.""",
    tools=[
        OpenApiAgentTool(openapi=OpenApiFunctionDefinition(
            name="document-ocr",
            spec=ocr_spec,
            auth={"type": "anonymous"}
        )),
        CodeInterpreterTool()
    ]
)
```

### Agent 2: Adjudication

```python
PromptAgentDefinition(
    model="gpt-4o",
    instructions="""You are a claims adjudication engine.
You will receive structured claim data and damage cost assessment.

Apply these business rules using Code Interpreter:
1. AUTO-APPROVE if: total_damage < $5,000 AND policy is active AND no prior claims in 12 months
2. AUTO-DENY if: policy is expired OR claim filed > 30 days after incident
3. MANUAL ESCALATION if: total_damage > $15,000 OR fraud indicators present OR liability disputed

Return JSON:
{ "verdict": "auto_approve"|"auto_deny"|"manual_escalation", "reason": "...", "confidence": 0.0-1.0 }""",
    tools=[CodeInterpreterTool()]
)
```

### Agent 3: Email Composer

```python
PromptAgentDefinition(
    model="gpt-4o",
    instructions="""You are a claims correspondence drafter.
You will receive claim data and an adjudication verdict.

Draft a professional email to the claimant:
- For AUTO-APPROVE: include settlement amount, next steps for payment
- For AUTO-DENY: cite specific policy clause, include appeal instructions

Return JSON: { "subject": "...", "body": "..." }""",
    tools=[CodeInterpreterTool()]
)
```

All 3 agents are defined **once** in Foundry. The system prompt is generic (describes the task, not the persona). On every API call, Layer 1 injects the contractor's persona into the **user prompt** — so the agent knows "I am Alice" or "I am Bob" for this specific job. Concurrency management (who has capacity, slot tracking, spawn/terminate) is Layer 1's responsibility.

---

## 10. Tick Loop — Multi-Agent Engine

```
Every 500ms (configurable):

  FOR EACH agent stage:
    1. PROGRESS each active job across all contractors
       - Increment progress % (simulated or tracked from real API)

    2. COMPLETE any jobs where progress >= 100%:
       - Remove job from contractor's slot
       - Move work item to NEXT stage's queue as "pending"
       - Increment contractor's jobs_completed counter

    3. SCALE DOWN check (after completions):
       - Walk contractors in REVERSE order
       - If contractor has 0 active jobs AND is not primary → terminate

    4. ASSIGN pending jobs using first-fill:
       - Walk contractors in SPAWN order
       - For each contractor with empty slots, assign pending jobs
       - If all contractors full AND pending jobs remain AND under max → spawn next contractor

  FOR HITL stage:
    - Simulate human delay OR wait for UI button click
    - On completion, move to next stage's queue

  RENDER all lanes
```

### Inter-Stage Handoff

When a job completes at one stage:
1. The work item's data is enriched with the agent's output
2. The enriched work item enters the **next stage's pending queue**
3. The next stage's first-fill logic picks it up on the next tick

This creates **pipeline backpressure**: if Agent 1 completes fast but Agent 2 is slow, Agent 2's queue grows, spawning more Agent 2 contractors. Each agent scales independently.

---

## 11. How to Adapt for a New Project

### Step 1: Draw your workflow pipeline

```
[Your Process] → [Your Agent 1] → [HITL?] → [Your Agent 2] → [Your Agent 3?] → [End Process]
```

Every project has a different pipeline. Examples:

| Domain | Pipeline |
|--------|----------|
| **Loan Origination** | Receive app → Agent: Doc Verify → HITL: Underwriter → Agent: Risk Score → Agent: Offer Letter → Send offer |
| **IT Support** | Ticket received → Agent: Triage & Classify → HITL: Approval → Agent: Resolution Drafter → Send response |
| **Invoice Processing** | Email received → Agent: Invoice Extractor → HITL: Finance Review → Agent: Payment Scheduler → Execute payment |

### Step 2: Define each agent

For each AI stage:
- **System instructions** — what it does (fixed across all contractors)
- **Tools** — OpenAPI, MCP, Code Interpreter, etc.
- **Prompt parameters** — data fields passed per job (in user prompt)

### Step 3: Set capacity and contractor names

Per agent, decide:
- **N (capacity)** — how many concurrent jobs per contractor? Consider agent processing time. Slow agents → lower N. Fast agents → higher N.
- **Max contractors** — upper bound (budget/API rate limits)
- **Contractor names** — Alice/Bob/Priya or Worker-1/Worker-2 or any naming scheme

### Step 4: Build the dashboard

For each agent lane:
- Show contractor cards with N job slots each
- Progress bar per active job
- Contractor status (FULL / AVAILABLE / IDLE)
- Spawn/terminate event log
- Pending queue count

---

## 12. Production Considerations

| Dashboard (PoC) | Production |
|------------------|------------|
| `setInterval(tick, 500)` | Background workers / Celery / Azure Functions |
| In-memory arrays | Redis / database per-stage queues |
| Simulated progress | Real API call duration tracking |
| Browser-only | FastAPI + WebSocket for live dashboard |
| Contractor = JS object | Contractor = pool of concurrent async tasks |
| First-fill in JS | First-fill in backend queue consumer |
| N/A | Foundry handles agent compute (managed service) |

### Azure AI Foundry Specifics

- Agent defined once: `AIProjectClient.agents.create_version()` with `PromptAgentDefinition`
- Each job = one API call with persona injected in user prompt:
  ```python
  response = openai_client.responses.create(
      model=agent_model,
      input=f"You are {contractor.name}, a claims analyst.\n\n{job_data}"
  )
  ```
- Alice processing 3 jobs = 3 concurrent API calls, each with `"You are Alice..."` in the input
- Bob processing 2 jobs = 2 concurrent API calls, each with `"You are Bob..."` in the input
- Same agent endpoint, same system prompt — persona varies per call via user prompt
- Foundry is a **managed service** — compute and scaling handled by Azure, no infra to manage
- Contractor/persona/slot logic is entirely Layer 1's responsibility

### HITL Integration

| Approach | How |
|----------|-----|
| **Dashboard form** | Human clicks on pending item, enters data, submits |
| **External system** | Push to ServiceNow/Jira/Teams, webhook on completion |
| **Simulated** | Auto-complete after configurable delay (for demos) |

---

## 13. Checklist — Porting to a New Project

### Workflow
- [ ] Draw pipeline: Process → Agent stages → HITL stages → End
- [ ] Define each agent: instructions, tools, prompt parameters
- [ ] Define HITL stages: what does the human enter?

### Contractor Config (per agent)
- [ ] Set **N** (concurrent jobs per contractor)
- [ ] Set **max contractors**
- [ ] Name your contractors (or use generic labels)

### Dashboard
- [ ] One lane per stage (agents + HITL)
- [ ] Contractor cards showing N job slots with progress bars
- [ ] First-fill assignment visualization
- [ ] Spawn/terminate events in each lane
- [ ] Pending queue counter per stage

### Sample Data
- [ ] 15+ sample work items that flow through entire pipeline
- [ ] Realistic HITL input values

### Production Path
- [ ] Layer 1: FastAPI with per-stage queues + first-fill consumer
- [ ] Layer 2: Deploy agent definitions to Foundry (one per stage, managed service)
- [ ] WebSocket for live dashboard updates
