# Architecture, Learnings & Best Practices
# Azure Durable Functions HITL Orchestration with AI Agents

> **Source Project:** Insurance Claims Processing — Multi-Agent HITL Orchestration
> **Tech Stack:** Azure Durable Functions (Python v2) + Azure AI Foundry Agents + Pydantic + Azure Service Bus
> **Built with:** Claude Code (AI-assisted development)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Core Patterns](#3-core-patterns)
4. [Activity Types — Agent, Non-Agentic, Long-Running & Batch](#4-activity-types--agent-non-agentic-long-running--batch)
5. [Fan-Out / Fan-In (Parallel Processing)](#5-fan-out--fan-in-parallel-processing)
6. [Setup Requirements](#6-setup-requirements)
7. [Durable Functions Essentials](#7-durable-functions-essentials)
8. [Human-in-the-Loop (HITL) Pattern](#8-human-in-the-loop-hitl-pattern)
9. [Azure AI Foundry Agent Integration](#9-azure-ai-foundry-agent-integration)
10. [Data Modeling with Pydantic](#10-data-modeling-with-pydantic)
11. [LLM JSON Repair Pipeline](#11-llm-json-repair-pipeline)
12. [Service Bus Integration](#12-service-bus-integration)
13. [Dashboard & Real-Time Visualization](#13-dashboard--real-time-visualization)
14. [Testing Strategy](#14-testing-strategy)
15. [Common Pitfalls & Solutions](#15-common-pitfalls--solutions)
16. [Development Workflow with Claude Code](#16-development-workflow-with-claude-code)
17. [CLAUDE.md — Your AI Assistant's Playbook](#17-claudemd--your-ai-assistants-playbook)

---

## 1. Architecture Overview

### End-to-End Flow

```
                          ┌─────────────────────────────┐
                          │  Ingestion (HTTP or Service  │
                          │  Bus Queue Trigger)          │
                          └─────────────┬───────────────┘
                                        │
                                        ▼
                          ┌─────────────────────────────┐
                          │  Agent 1: Classifier         │
                          │  (Azure AI Foundry Agent)    │
                          │  • Classifies claim type     │
                          │  • Extracts info from email  │
                          │  • Parses PDF attachment     │
                          └─────────────┬───────────────┘
                                        │
                                        ▼
                          ┌─────────────────────────────┐
                          │  HITL: Human Review          │
                          │  • wait_for_external_event() │
                          │  • Configurable timeout      │
                          │  • Web form for data entry   │
                          └─────────────┬───────────────┘
                                        │
                          ┌─────────┬───┴──────────┐
                          │         │              │
                       Timeout   Rejected      Approved
                          │         │              │
                          ▼         ▼              ▼
                        [END]     [END]   ┌────────────────┐
                                          │  Agent 2:       │
                                          │  Adjudicator    │
                                          │  • Applies rules│
                                          │  • AUTO/DENY/   │
                                          │    MANUAL_REVIEW │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │  Agent 3:       │
                                          │  Email Composer │
                                          │  • Composes     │
                                          │    notification │
                                          └────────┬───────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │  Send Email     │
                                          │  (SMTP/Review)  │
                                          └────────────────┘
```

### Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Python v2 programming model** | Decorator-based, cleaner than v1's function.json approach |
| **Activities per agent** | Each AI agent lives in its own activity file for isolation |
| **Dicts (not classes) between orchestrator ↔ activities** | Durable Functions serializes all inputs/outputs as JSON; Pydantic validation happens inside activities |
| **Deterministic instance IDs** | `claim-{claim_id}` prevents duplicate orchestrations |
| **In-process singleton for dashboard state** | ContractorManager holds live state in memory; works for single-instance local/dev |
| **Mock mode** | Every agent has a mock fallback so the full flow works without Azure credentials |

---

## 2. Project Structure

```
your_project/
├── CLAUDE.md                          # AI assistant instructions (see Section 17)
├── DEVELOPMENT_PLAN.md                # Phased development plan
├── start-local.ps1                    # Docker emulator startup script
│
├── function_app/
│   ├── function_app.py                # Main entry: triggers + orchestrator + activities
│   ├── host.json                      # Azure Functions host config
│   ├── local.settings.json            # Environment variables (gitignored)
│   ├── requirements.txt               # Python dependencies
│   │
│   ├── activities/                    # Activity function implementations
│   │   ├── __init__.py
│   │   ├── agent1_activity.py         # Classifier agent invocation
│   │   ├── agent2_activity.py         # Adjudicator agent invocation
│   │   ├── agent3_activity.py         # Email composer agent invocation
│   │   ├── notify_activity.py         # Notification (logs approval URL)
│   │   └── send_email_activity.py     # SMTP email sending
│   │
│   ├── shared/                        # Shared utilities and models
│   │   ├── __init__.py                # Package exports
│   │   ├── models.py                  # All Pydantic data models
│   │   ├── prompts.py                 # Agent prompt templates
│   │   ├── agent_client.py            # Azure AI Foundry invocation + JSON repair
│   │   ├── contractor_manager.py      # Dashboard state manager (optional)
│   │   └── agent_personas.json        # Named contractor personas (optional)
│   │
│   ├── static/                        # HTML dashboards
│   │   ├── dashboard.html             # Claims dashboard
│   │   ├── review.html                # Human review form
│   │   └── clone_dashboard.html       # AI contractor visualizer
│   │
│   └── tests/
│       ├── test_models.py             # Pydantic model unit tests
│       └── test_contractor_manager.py # Dashboard state tests
│
├── test_data/                         # Sample inputs for testing
└── postman/                           # Postman collection
```

### Why This Structure?

- **`function_app.py` is the single entry point** — all triggers, orchestrators, and activity wrappers are registered here. Activity wrappers are thin — they delegate to implementations in `activities/`.
- **`shared/` is the reusable library** — models, prompts, and the agent client can be imported by any activity.
- **`activities/` holds the business logic** — each agent gets its own file. This keeps `function_app.py` focused on orchestration flow.
- **`static/` serves HTML** — Azure Functions can serve static files via HTTP triggers that read and return file contents.

---

## 3. Core Patterns

### 3.1 The Orchestrator Pattern

The orchestrator is a **generator function** that `yield`s calls to activities and external events. Azure Durable Functions replays the orchestrator from the beginning on each step, so the function must be **deterministic** (no random, no datetime.now, no I/O — use `context.current_utc_datetime` instead).

```python
@app.orchestration_trigger(context_name="context")
def claim_orchestrator(context: df.DurableOrchestrationContext):
    input_data = context.get_input()
    claim_id = input_data.get("claim_id")
    instance_id = context.instance_id

    # Step 1: Call Agent 1
    agent1_result = yield context.call_activity("agent1_activity", {
        "claim_id": claim_id,
        "email_content": input_data.get("email_content"),
        "attachment_url": input_data.get("attachment_url"),
        "sender_email": input_data.get("sender_email"),
    })

    # Step 2: Wait for human approval (HITL)
    context.set_custom_status({"step": "awaiting_approval", "agent1_output": agent1_result})

    approval_task = context.wait_for_external_event("ApprovalDecision")
    timeout_task = context.create_timer(
        context.current_utc_datetime + timedelta(hours=24)
    )
    winner = yield context.task_any([approval_task, timeout_task])

    if winner == timeout_task:
        return {"status": "timeout"}

    timeout_task.cancel()
    approval = approval_task.result

    if approval.get("decision") == "rejected":
        return {"status": "rejected"}

    # Step 3: Call Agent 2
    agent2_result = yield context.call_activity("agent2_activity", {
        "claim_id": claim_id,
        "agent1_output": agent1_result,
        "approval_decision": approval,
    })

    return {"status": "completed", "agent2_output": agent2_result}
```

### 3.2 Activity Function Pattern

Activities are where real work happens (API calls, I/O, AI invocations). They are **not replayed** — they run once and their result is stored.

```python
# In function_app.py — thin wrapper registered with Durable Functions
@app.activity_trigger(input_name="activityInput")
def agent1_activity(activityInput: dict) -> dict:
    return run_agent1_activity(activityInput)

# In activities/agent1_activity.py — the actual implementation
def run_agent1_activity(input_data: dict) -> dict:
    claim_id = input_data["claim_id"]
    instance_id = input_data.get("_instance_id")

    agent1_input = Agent1Input(
        claim_id=claim_id,
        email_content=input_data["email_content"],
        attachment_url=input_data.get("attachment_url", ""),
        sender_email=input_data["sender_email"],
    )

    result = invoke_agent1(agent1_input, instance_id=instance_id)
    return result.model_dump()
```

**Key pattern:** The activity converts raw dicts → Pydantic models (for validation) → calls the agent → returns dicts (for serialization).

### 3.3 External Event (HITL Wait)

```python
# Orchestrator waits
approval_task = context.wait_for_external_event("ApprovalDecision")
timeout_task = context.create_timer(context.current_utc_datetime + timedelta(hours=24))
winner = yield context.task_any([approval_task, timeout_task])

# HTTP endpoint raises the event
@app.route(route="claims/approve/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def approve_claim(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = req.route_params.get("instance_id")
    body = req.get_json()

    await client.raise_event(
        instance_id=instance_id,
        event_name="ApprovalDecision",  # Must match exactly (case-sensitive)
        event_data=body
    )
    return func.HttpResponse("Event raised", status_code=200)
```

### 3.4 Custom Status for Progress Tracking

```python
context.set_custom_status({
    "step": "agent1_processing",
    "claim_id": claim_id,
    "message": "Classifying claim...",
    "stage_timestamps": stage_timestamps
})
```

Custom status is visible via `GET /api/claims/status/{instance_id}` and powers the dashboard. The object must be JSON-serializable.

---

## 4. Activity Types — Agent, Non-Agentic, Long-Running & Batch

Not every activity in your orchestration calls an AI agent. Durable Functions activities are general-purpose units of work. Here are the four main categories you'll encounter, with patterns for each.

### 4.1 AI Agent Activities

Activities that invoke an external AI service (Azure AI Foundry, OpenAI, etc.) and return structured results. These are inherently non-deterministic — the same input may produce different output on each call.

```python
# activities/classification_activity.py
def run_classification_activity(input_data: dict) -> dict:
    """AI Agent activity — calls an external LLM/agent service."""
    prompt = build_prompt(input_data)

    # Call AI service (non-deterministic, may return malformed JSON)
    response_text = invoke_foundry_agent(agent_name, prompt, endpoint)

    # Parse with repair pipeline (see Section 11)
    response_dict = parse_agent_response(response_text, agent_name)

    # Validate with Pydantic model
    output = ClassificationOutput.model_validate(response_dict)
    return output.model_dump()
```

**Key considerations for agent activities:**
- Always add **retry logic** — LLMs can timeout or return malformed responses
- Always add **JSON repair** — LLM output is not guaranteed to be valid JSON
- Always add **mock mode** — enable local development without real credentials
- Use **Pydantic models** for input/output validation at the boundary

### 4.2 Non-Agentic Activities (Plain Business Logic)

Standard activities that perform deterministic operations: database writes, API calls, file processing, calculations, sending notifications.

```python
# activities/send_notification_activity.py
def run_send_notification_activity(input_data: dict) -> dict:
    """Non-agentic activity — sends an email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(input_data["body"])
    msg["Subject"] = input_data["subject"]
    msg["To"] = input_data["recipient"]

    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT"))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)

    return {"success": True, "sent_to": input_data["recipient"]}
```

```python
# activities/validate_input_activity.py
def run_validate_input_activity(input_data: dict) -> dict:
    """Non-agentic activity — validates and enriches input data."""
    # Look up customer in database
    customer = db.get_customer(input_data["customer_id"])
    if not customer:
        return {"valid": False, "error": "Customer not found"}

    # Enrich with account data
    return {
        "valid": True,
        "customer_name": customer.name,
        "account_status": customer.status,
        "original_input": input_data
    }
```

```python
# activities/generate_report_activity.py
def run_generate_report_activity(input_data: dict) -> dict:
    """Non-agentic activity — generates a PDF or CSV report."""
    records = input_data["records"]
    report_type = input_data.get("format", "csv")

    if report_type == "csv":
        content = generate_csv(records)
    else:
        content = generate_pdf(records)

    # Upload to blob storage
    blob_url = upload_to_storage(content, f"reports/{input_data['report_id']}.{report_type}")
    return {"report_url": blob_url, "record_count": len(records)}
```

### 4.3 Long-Running / HITL Wait Activities

These aren't activities in the traditional sense — they use the orchestrator's `wait_for_external_event()` pattern. The orchestration **pauses** and waits for an external signal (human approval, webhook callback, another system's response). There is **no charge** for time spent waiting in the Consumption plan.

```python
@app.orchestration_trigger(context_name="context")
def multi_approval_orchestrator(context: df.DurableOrchestrationContext):
    input_data = context.get_input()

    # Step 1: Normal activity
    result = yield context.call_activity("process_initial", input_data)

    # Step 2: HITL Wait — Manager approval with 72-hour timeout
    context.set_custom_status({"step": "awaiting_manager_approval"})
    manager_task = context.wait_for_external_event("ManagerApproval")
    timeout_task = context.create_timer(context.current_utc_datetime + timedelta(hours=72))
    winner = yield context.task_any([manager_task, timeout_task])

    if winner == timeout_task:
        # Escalate to VP if manager didn't respond
        yield context.call_activity("escalate_to_vp", {"reason": "manager_timeout"})

        # Step 3: HITL Wait — VP approval with another timeout
        context.set_custom_status({"step": "awaiting_vp_approval"})
        vp_task = context.wait_for_external_event("VPApproval")
        vp_timeout = context.create_timer(context.current_utc_datetime + timedelta(hours=24))
        vp_winner = yield context.task_any([vp_task, vp_timeout])

        if vp_winner == vp_timeout:
            return {"status": "auto_rejected", "reason": "No approvals within SLA"}
        vp_timeout.cancel()
        approval = vp_task.result
    else:
        timeout_task.cancel()
        approval = manager_task.result

    # Step 4: Continue processing
    final_result = yield context.call_activity("finalize_request", {
        "input": input_data,
        "approval": approval
    })
    return final_result
```

**You can chain multiple HITL waits in a single orchestration** — each one pauses independently and can have its own timeout and escalation logic.

### 4.4 Batch / Long-Running Job Activities

Activities that process large datasets, run ETL jobs, or perform long-running computations. These benefit from **retry policies** and **timeouts** since they may fail partway through.

```python
# activities/batch_import_activity.py
def run_batch_import_activity(input_data: dict) -> dict:
    """Long-running batch activity — imports records from a CSV file."""
    blob_url = input_data["source_url"]
    target_table = input_data["target_table"]

    # Download and parse CSV
    records = download_and_parse_csv(blob_url)

    # Process in chunks (allows partial progress tracking)
    imported = 0
    errors = []
    for chunk in chunked(records, 100):
        try:
            db.bulk_insert(target_table, chunk)
            imported += len(chunk)
        except Exception as e:
            errors.append({"chunk_start": imported, "error": str(e)})

    return {
        "total_records": len(records),
        "imported": imported,
        "errors": errors,
        "success": len(errors) == 0
    }
```

**Using retry policies for unreliable activities:**

```python
@app.orchestration_trigger(context_name="context")
def batch_orchestrator(context: df.DurableOrchestrationContext):
    input_data = context.get_input()

    # Retry policy: 3 attempts, 5s initial backoff, 2x exponential, 5min max
    retry_options = df.RetryOptions(
        first_retry_interval_in_milliseconds=5000,
        max_number_of_attempts=3,
        backoff_coefficient=2.0,
        max_retry_interval_in_milliseconds=60000,
        retry_timeout_in_milliseconds=300000
    )

    # Call unreliable activity with retry
    result = yield context.call_activity_with_retry(
        "batch_import_activity",
        retry_options,
        input_data
    )
    return result
```

### 4.5 Mixing Activity Types in One Orchestration

A real-world orchestration typically combines all activity types:

```python
@app.orchestration_trigger(context_name="context")
def mixed_workflow(context: df.DurableOrchestrationContext):
    input_data = context.get_input()

    # 1. Non-agentic: Validate and enrich input
    validated = yield context.call_activity("validate_input", input_data)
    if not validated["valid"]:
        return {"status": "rejected", "reason": validated["error"]}

    # 2. AI Agent: Classify the request
    classification = yield context.call_activity("ai_classify", validated)

    # 3. HITL Wait: Human reviews the classification
    context.set_custom_status({"step": "awaiting_review", "classification": classification})
    review_task = context.wait_for_external_event("HumanReview")
    timeout = context.create_timer(context.current_utc_datetime + timedelta(hours=24))
    winner = yield context.task_any([review_task, timeout])

    if winner == timeout:
        return {"status": "timeout"}
    timeout.cancel()
    review = review_task.result

    # 4. AI Agent: Generate recommendations based on review
    recommendations = yield context.call_activity("ai_recommend", {
        "classification": classification,
        "review": review
    })

    # 5. Batch: Process the recommendations (may take minutes)
    retry = df.RetryOptions(5000, 3)
    batch_result = yield context.call_activity_with_retry(
        "batch_process", retry, recommendations
    )

    # 6. Non-agentic: Send notification email
    yield context.call_activity("send_notification", {
        "recipient": input_data["requester_email"],
        "subject": "Processing Complete",
        "body": f"Your request has been processed. Result: {batch_result['summary']}"
    })

    return {"status": "completed", "result": batch_result}
```

---

## 5. Fan-Out / Fan-In (Parallel Processing)

Fan-out/fan-in is one of the most powerful patterns in Durable Functions. It lets you execute multiple activities **in parallel** and then aggregate the results. This is essential for batch processing, multi-agent workflows, and any scenario where independent tasks can run concurrently.

> **Source:** [Official Microsoft Documentation — Fan-out/fan-in scenarios in Durable Functions](https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-cloud-backup?tabs=python)

### 5.1 The Pattern

```
                        ┌──────────────┐
                        │  Get work    │
                        │  items (F1)  │
                        └──────┬───────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Process  │    │ Process  │    │ Process  │
        │ item (F2)│    │ item (F2)│    │ item (F2)│
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │               │               │
             └───────────────┼───────────────┘
                             │
                      ┌──────▼───────┐
                      │  Aggregate   │
                      │  results (F3)│
                      └──────────────┘
```

### 5.2 Basic Fan-Out/Fan-In (from official docs)

From the [official Microsoft documentation](https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-cloud-backup?tabs=python), here is the cloud backup example that fans out file uploads in parallel:

```python
# Official example: Fan-out/fan-in for parallel file backup
import azure.functions as func
import azure.durable_functions as df

def orchestrator_function(context: df.DurableOrchestrationContext):
    # Step 1: Get list of work items (single activity)
    root_directory: str = context.get_input()
    if not root_directory:
        raise Exception("A directory path is required as input")

    files = yield context.call_activity("E2_GetFileList", root_directory)

    # Step 2: Fan-out — start all tasks WITHOUT yielding
    tasks = []
    for file in files:
        tasks.append(context.call_activity("E2_CopyFileToBlob", file))

    # Step 3: Fan-in — wait for ALL tasks to complete
    results = yield context.task_all(tasks)

    # Step 4: Aggregate results
    total_bytes = sum(results)
    return total_bytes

main = df.Orchestrator.create(orchestrator_function)
```

**The key insight:** When you call `context.call_activity()` **without `yield`**, it starts the task but doesn't wait. Collecting all tasks into a list and then calling `yield context.task_all(tasks)` runs them all **in parallel** across multiple VMs, and waits for all to complete. Automatic checkpointing ensures that if a crash happens, already-completed tasks are not re-run.

### 5.3 Fan-Out/Fan-In with Python v2 Decorator Model

The same pattern using the modern decorator-based model:

```python
import azure.functions as func
import azure.durable_functions as df

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.orchestration_trigger(context_name="context")
def parallel_orchestrator(context: df.DurableOrchestrationContext):
    work_batch = yield context.call_activity("get_work_items", context.get_input())

    # Fan-out: create parallel tasks (do NOT yield individual calls)
    parallel_tasks = [context.call_activity("process_item", item) for item in work_batch]

    # Fan-in: wait for all to complete
    results = yield context.task_all(parallel_tasks)

    # Aggregate and return
    summary = yield context.call_activity("aggregate_results", results)
    return summary

@app.activity_trigger(input_name="input")
def get_work_items(input: dict) -> list:
    """Activity: returns a list of items to process in parallel."""
    return [{"id": i, "data": f"item-{i}"} for i in range(10)]

@app.activity_trigger(input_name="item")
def process_item(item: dict) -> dict:
    """Activity: processes a single item (runs on potentially different VM)."""
    import time
    time.sleep(2)  # Simulate work
    return {"id": item["id"], "result": f"processed-{item['id']}", "success": True}

@app.activity_trigger(input_name="results")
def aggregate_results(results: list) -> dict:
    """Activity: aggregates all parallel results."""
    successful = sum(1 for r in results if r["success"])
    return {"total": len(results), "successful": successful}
```

### 5.4 Fan-Out with Multiple Agent Types (Practical Example)

Run multiple AI agents in parallel when they don't depend on each other:

```python
@app.orchestration_trigger(context_name="context")
def multi_agent_parallel(context: df.DurableOrchestrationContext):
    document = context.get_input()

    # Fan-out: Run 3 different AI agents in parallel on the same document
    tasks = [
        context.call_activity("sentiment_analysis_agent", document),
        context.call_activity("entity_extraction_agent", document),
        context.call_activity("summarization_agent", document),
    ]

    # Fan-in: Wait for all agents to complete
    results = yield context.task_all(tasks)

    # results[0] = sentiment, results[1] = entities, results[2] = summary
    return {
        "sentiment": results[0],
        "entities": results[1],
        "summary": results[2]
    }
```

### 5.5 Fan-Out with Dynamic Work Items and Retry

Process a batch of records with per-item retry and error handling:

```python
@app.orchestration_trigger(context_name="context")
def batch_processing_orchestrator(context: df.DurableOrchestrationContext):
    input_data = context.get_input()

    # Step 1: Get batch of items to process
    items = yield context.call_activity("fetch_pending_records", input_data)

    context.set_custom_status({
        "step": "processing",
        "total_items": len(items),
        "message": f"Processing {len(items)} items in parallel..."
    })

    # Step 2: Fan-out with retry policy
    retry_options = df.RetryOptions(
        first_retry_interval_in_milliseconds=2000,
        max_number_of_attempts=3,
        backoff_coefficient=2.0
    )

    tasks = []
    for item in items:
        tasks.append(
            context.call_activity_with_retry("process_single_record", retry_options, item)
        )

    # Step 3: Fan-in — wait for all
    results = yield context.task_all(tasks)

    # Step 4: Aggregate
    succeeded = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    context.set_custom_status({
        "step": "completed",
        "succeeded": len(succeeded),
        "failed": len(failed)
    })

    return {
        "total": len(items),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failures": failed
    }
```

### 5.6 task_any — Race Pattern (First to Complete Wins)

Use `task_any` when you want the first result, not all results. This is the pattern used for HITL timeouts, but it also works for parallel racing:

```python
@app.orchestration_trigger(context_name="context")
def race_orchestrator(context: df.DurableOrchestrationContext):
    """Try multiple services in parallel, take the first response."""
    input_data = context.get_input()

    tasks = [
        context.call_activity("service_a_lookup", input_data),
        context.call_activity("service_b_lookup", input_data),
        context.call_activity("service_c_lookup", input_data),
    ]

    # Returns as soon as ANY one completes
    winner = yield context.task_any(tasks)
    return winner.result
```

### 5.7 Key Rules for Fan-Out/Fan-In

| Rule | Why |
|------|-----|
| **Don't `yield` individual tasks** | `yield` blocks execution. Collect tasks in a list first. |
| **Use `task_all()` to wait for all** | This is the fan-in point. Checkpointed automatically. |
| **Use `task_any()` for first-wins** | Useful for timeouts, racing, fallback patterns. |
| **Cancel losing tasks after `task_any`** | Especially timers — always `.cancel()` the loser. |
| **Activities may run on different VMs** | Don't rely on shared memory between parallel activities. |
| **Checkpointing is automatic** | If a crash happens, completed tasks are NOT re-run. |
| **`maxConcurrentActivityFunctions` in host.json** | Controls how many activities run simultaneously on one instance. |

---

## 6. Setup Requirements

### 6.1 Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Python** | 3.9+ (recommended 3.11) | Runtime |
| **Node.js** | 18+ | Required for Azure Functions Core Tools |
| **Azure Functions Core Tools** | v4 | Local function runtime |
| **Docker Desktop** | Latest | Runs Azurite and DTS emulators |
| **Azure CLI** | Latest | Authentication (`az login`) |

### 6.2 Install Azure Functions Core Tools

```powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
func --version   # Verify installation
```

### 6.3 Python Dependencies (`requirements.txt`)

```
# Azure Functions Core
azure-functions>=1.21.0
azure-functions-durable>=1.4.0

# Azure Service Bus (if using queue triggers)
azure-servicebus>=7.12.0

# Azure Identity & AI Foundry
azure-identity>=1.19.0
azure-ai-projects>=1.0.0b7
azure-ai-agents>=1.0.0
openai

# Data Validation
pydantic>=2.10.0

# Utilities
python-dateutil>=2.9.0
python-dotenv
tzdata>=2024.1

# JSON repair for LLM responses
json5>=0.9.0
```

**Important:** Always add packages to `requirements.txt` first, then install via `pip install -r requirements.txt`. Never install packages directly with `pip install <package>`.

### 6.4 Docker Setup — Local Emulators

You need two Docker containers for local development:

**Azurite (Azure Storage Emulator):**
```powershell
docker run -d `
  --name azurite `
  -p 10000:10000 `
  -p 10001:10001 `
  -p 10002:10002 `
  mcr.microsoft.com/azure-storage/azurite
```

| Port | Service |
|------|---------|
| 10000 | Blob Storage |
| 10001 | Queue Storage |
| 10002 | Table Storage |

**Durable Task Scheduler Emulator:**
```powershell
docker run -d `
  --name dts-emulator `
  -p 8080:8080 `
  -p 8082:8082 `
  mcr.microsoft.com/dts/dts-emulator:latest
```

| Port | Service |
|------|---------|
| 8080 | gRPC endpoint (function app connects here) |
| 8082 | Dashboard UI (view orchestration state) |

**Startup Script (`start-local.ps1`):**
```powershell
Write-Host "Starting Azurite..."
$azuriteRunning = docker ps --filter "name=azurite" --format "{{.Names}}"
if ($azuriteRunning -ne "azurite") {
    docker start azurite 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker run -d --name azurite -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
    }
}

Write-Host "Starting DTS Emulator..."
$dtsRunning = docker ps --filter "name=dts-emulator" --format "{{.Names}}"
if ($dtsRunning -ne "dts-emulator") {
    docker start dts-emulator 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
    }
}

Start-Sleep -Seconds 3
Write-Host "Ready! Run 'cd function_app && func start'"
```

### 6.5 Configuration Files

**`host.json`** — Azure Functions host configuration:
```json
{
  "version": "2.0",
  "logging": {
    "logLevel": {
      "default": "Information",
      "DurableTask.AzureStorage": "Warning"
    }
  },
  "extensions": {
    "durableTask": {
      "storageProvider": { "type": "AzureStorage" },
      "tracing": {
        "traceInputsAndOutputs": true,
        "traceReplayEvents": false
      },
      "maxConcurrentActivityFunctions": 10,
      "maxConcurrentOrchestratorFunctions": 5
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

**`local.settings.json`** — Environment variables (gitignored):
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",

    "AGENT1_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
    "AGENT1_NAME": "your-classifier-agent",
    "AGENT2_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
    "AGENT2_NAME": "your-adjudicator-agent",
    "AGENT3_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
    "AGENT3_NAME": "your-email-composer-agent",

    "AZURE_TENANT_ID": "your-tenant-id",
    "AZURE_CLIENT_ID": "your-client-id",
    "AZURE_CLIENT_SECRET": "your-client-secret",

    "APPROVAL_TIMEOUT_HOURS": "24",
    "AGENT_MOCK_MODE": "false",

    "SERVICE_BUS_CONNECTION_STRING": "your-connection-string",
    "SERVICE_BUS_QUEUE_NAME": "your-queue-name",

    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "your-email@gmail.com",
    "SMTP_PASSWORD": "your-app-password",
    "EMAIL_FROM_ADDRESS": "your-email@gmail.com",
    "EMAIL_FROM_NAME": "Claims Department",
    "REVIEW_EMAIL_ADDRESS": "review-team@company.com"
  }
}
```

### 6.6 API Keys & Credentials

| Credential | Where to Get It | Purpose |
|------------|-----------------|---------|
| `AZURE_TENANT_ID` | Azure Portal → Entra ID | Service principal auth |
| `AZURE_CLIENT_ID` | Azure Portal → App Registrations | Service principal auth |
| `AZURE_CLIENT_SECRET` | Azure Portal → App Registrations → Certificates & Secrets | Service principal auth |
| `AGENT*_PROJECT_ENDPOINT` | Azure AI Foundry → Project → Overview | AI agent API endpoint |
| `AGENT*_NAME` | Azure AI Foundry → Agents → Agent Name | Name of each deployed agent |
| `SERVICE_BUS_CONNECTION_STRING` | Azure Portal → Service Bus → Shared access policies | Queue trigger auth |
| `SMTP_PASSWORD` | Gmail → App Passwords (or your SMTP provider) | Email sending |

**Tip:** Set `AGENT_MOCK_MODE=true` in `local.settings.json` to run the full flow without any Azure credentials. Each agent returns realistic mock data.

### 6.7 Running the Function App

```powershell
# 1. Start Docker emulators
.\start-local.ps1

# 2. Install dependencies
cd function_app
pip install -r requirements.txt

# 3. Start the function app
func start
```

**Endpoints available at:**
- Function App: `http://localhost:7071`
- Dashboard: `http://localhost:7071/api/dashboard`
- DTS Dashboard: `http://localhost:8082`
- Health Check: `http://localhost:7071/api/health`

---

## 7. Durable Functions Essentials

### 7.1 How Replay Works

The orchestrator is a generator that gets **replayed from the beginning** every time it needs to advance. Previously completed `yield` calls return their stored results instantly. New `yield` calls trigger actual execution.

**This means:**
- No `datetime.now()` — use `context.current_utc_datetime`
- No `random()` — use `context.new_guid()`
- No `logging` without guard — use `if not context.is_replaying: logger.info(...)`
- No direct I/O — all I/O must happen inside activity functions

### 7.2 Deterministic Instance IDs

```python
instance_id = f"claim-{claim_id}"
await client.start_new("claim_orchestrator", instance_id, input_data)
```

Benefits:
- Prevents duplicate orchestrations (same claim_id = same instance_id)
- Enables idempotent Service Bus processing
- Makes status lookups predictable

### 7.3 Custom Status for External Visibility

```python
context.set_custom_status({
    "step": "awaiting_approval",
    "claim_id": claim_id,
    "agent1_output": agent1_result,     # Full output available for review UI
    "stage_timestamps": stage_timestamps # Timeline data
})
```

This powers the dashboard polling. Clients call `GET /api/claims/status/{instance_id}` and read `custom_status` to show real-time progress.

### 7.4 Timer + Event Race (The HITL Pattern)

```python
approval_task = context.wait_for_external_event("ApprovalDecision")
timeout_task = context.create_timer(context.current_utc_datetime + timedelta(hours=24))
winner = yield context.task_any([approval_task, timeout_task])

if winner == timeout_task:
    return {"status": "timeout"}

timeout_task.cancel()  # Always cancel the loser
approval = approval_task.result
```

**Critical:** Always `cancel()` the timer if the event wins. Otherwise the timer fires later and may cause unexpected behavior.

### 7.5 Activity Registration Pattern

All activities must be registered in `function_app.py`. We use thin wrappers that delegate to implementations:

```python
# function_app.py — registration
@app.activity_trigger(input_name="activityInput")
def agent1_activity(activityInput: dict) -> dict:
    return run_agent1_activity(activityInput)

# activities/agent1_activity.py — implementation
def run_agent1_activity(input_data: dict) -> dict:
    # Validate input, call agent, return result
    ...
```

This keeps `function_app.py` lean while allowing full logic in separate files.

---

## 8. Human-in-the-Loop (HITL) Pattern

### 8.1 The Three Parties

1. **Orchestrator** — waits for `wait_for_external_event("ApprovalDecision")`
2. **HTTP Endpoint** — validates and calls `client.raise_event()`
3. **Human** — views a web form, fills in data, submits

### 8.2 Approval Endpoint with Validation

Before raising an event, validate that the orchestration exists and is actually waiting:

```python
@app.route(route="claims/approve/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def approve_claim(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = req.route_params.get("instance_id")
    body = req.get_json()

    # 1. Check orchestration exists
    status = await client.get_status(instance_id)
    if not status:
        return func.HttpResponse(json.dumps({"error": "not_found"}), status_code=404)

    # 2. Check it's running
    if status.runtime_status.name != "Running":
        return func.HttpResponse(json.dumps({"error": "not_running"}), status_code=409)

    # 3. Check it's at the right step
    custom_status = status.custom_status or {}
    if custom_status.get("step") != "awaiting_approval":
        return func.HttpResponse(json.dumps({"error": "wrong_step"}), status_code=409)

    # 4. Raise the event
    await client.raise_event(instance_id, "ApprovalDecision", body)

    return func.HttpResponse(json.dumps({"success": True}), status_code=200)
```

### 8.3 Stage Timestamps

Track timestamps throughout the orchestration for timeline visualization:

```python
stage_timestamps = {"received": context.current_utc_datetime.isoformat()}

# After each stage:
stage_timestamps["classifier_started"] = context.current_utc_datetime.isoformat()
stage_timestamps["classifier_completed"] = context.current_utc_datetime.isoformat()
stage_timestamps["awaiting_started"] = context.current_utc_datetime.isoformat()
stage_timestamps["approval_received"] = context.current_utc_datetime.isoformat()
# ... and so on
```

Include `stage_timestamps` in every `set_custom_status()` call so the dashboard always has the latest timeline.

### 8.4 Event Data Gotcha

External event data may arrive as a **string** (JSON-encoded) or a **dict** depending on the storage backend:

```python
approval_decision = approval_task.result
if isinstance(approval_decision, str):
    approval_decision = json.loads(approval_decision)
```

Always handle both cases.

---

## 9. Azure AI Foundry Agent Integration

### 9.1 Authentication

```python
from azure.identity import DefaultAzureCredential, ClientSecretCredential

def get_credential():
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if all([tenant_id, client_id, client_secret]):
        return ClientSecretCredential(tenant_id, client_id, client_secret)
    return DefaultAzureCredential()
```

### 9.2 Invoking an Agent

```python
from azure.ai.projects import AIProjectClient

def invoke_foundry_agent(agent_name: str, prompt: str, project_endpoint: str) -> str:
    credential = get_credential()

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    agent = project_client.agents.get(agent_name=agent_name)
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": prompt}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    return response.output_text
```

### 9.3 Mock Mode for Local Development

```python
def is_mock_mode(agent_num: int = 1) -> bool:
    if os.getenv("AGENT_MOCK_MODE", "false").lower() == "true":
        return True
    endpoint = os.getenv(f"AGENT{agent_num}_PROJECT_ENDPOINT", "")
    return not endpoint or "your-project" in endpoint
```

Each agent has a `_get_mock_agentN_response()` function that returns realistic test data.

### 9.4 Retry Logic

LLM responses are not deterministic. Always wrap agent calls with retries:

```python
for attempt in range(max_retries + 1):
    try:
        response_text = invoke_foundry_agent(agent_name, prompt, endpoint)
        response_dict = parse_agent_response(response_text, agent_name)
        break  # Success
    except (json.JSONDecodeError, Exception) as e:
        if attempt < max_retries:
            time.sleep(1)
        else:
            raise
```

---

## 10. Data Modeling with Pydantic

### 10.1 Why Pydantic?

- **Validation at boundaries** — validate LLM responses and HTTP inputs
- **Type safety** — catch errors early
- **Serialization** — `model_dump()` and `model_validate()` for dict conversion
- **Documentation** — field descriptions become self-documenting

### 10.2 LLM-Friendly Numeric Types

LLMs often return numbers with formatting characters (`$1,500.00`, `85%`). Handle this with custom validators:

```python
from pydantic import BaseModel, BeforeValidator
from typing import Annotated, Optional

def clean_numeric(v):
    """Strip $, commas, %, whitespace from numeric values."""
    if isinstance(v, str):
        return v.replace(",", "").replace("$", "").replace("%", "").strip()
    return v

def clean_confidence(v):
    """Normalize percentages (85 -> 0.85) and strip formatting."""
    if isinstance(v, str):
        v = v.replace(",", "").replace("$", "").replace("%", "").strip()
    v = float(v) if isinstance(v, str) else v
    if isinstance(v, (int, float)) and v > 1.0:
        v = v / 100.0
    return v

CleanInt = Annotated[Optional[int], BeforeValidator(clean_numeric)]
CleanFloat = Annotated[Optional[float], BeforeValidator(clean_numeric)]

class ExtractedInfo(BaseModel):
    total_estimate: CleanFloat = None     # Handles "$1,234.56" -> 1234.56
    vehicle_year: CleanInt = None         # Handles "2,022" -> 2022
    confidence: Annotated[float, BeforeValidator(clean_confidence)] = 0.0  # 85 -> 0.85
```

### 10.3 Flexible Models for Unpredictable LLM Output

LLMs don't always follow your schema. Use `Optional` fields and flexible types:

```python
class Agent2Output(BaseModel):
    claim_id: str
    decision: str                              # Not Literal — LLMs may return unexpected values
    decision_type: Optional[str] = None        # Might not always be present
    approved_amount: Optional[float] = None    # None when denied
    rules_evaluated: list[Any] = []            # Sometimes returns dicts, sometimes strings
    rules_failed: list[Any] = []
    reason: Optional[str] = None
```

### 10.4 The Validation Pattern

Validate at the boundary between raw LLM output and your business logic:

```python
# In the activity function:
response_dict = parse_agent_response(raw_text, "Agent1")  # Raw text -> dict
output = Agent1Output.model_validate(response_dict)        # Dict -> typed model
return output.model_dump()                                  # Model -> dict for serialization
```

---

## 11. LLM JSON Repair Pipeline

LLMs sometimes return malformed JSON. This was one of the biggest lessons from the project.

### 11.1 Common LLM JSON Issues

| Issue | Example | Fix |
|-------|---------|-----|
| Markdown wrapping | ` ```json {...} ``` ` | Strip code blocks |
| Trailing commas | `{"a": 1,}` | Remove with regex |
| Missing commas | `"field1": "val1" "field2": "val2"` | Insert with regex |
| Arithmetic in values | `"total": 285.00 + 45.00` | Evaluate expression |
| Extra text after JSON | `{...} Note: this is valid` | Truncate at error pos |
| String numbers | `"year": "2022"` | Pydantic handles this |

### 11.2 Multi-Strategy Parser

```python
def parse_agent_response(response_text: str, agent_name: str) -> dict:
    json_str = extract_json_from_response(response_text)  # Strip markdown blocks

    # Strategy 1: Direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Strategy 1b: Truncate at "Extra data" position
        if "Extra data" in e.msg and e.pos > 0:
            try:
                return json.loads(json_str[:e.pos])
            except json.JSONDecodeError:
                pass

    # Strategy 2: Fix common issues (trailing commas, arithmetic, missing commas)
    try:
        return json.loads(fix_common_json_issues(json_str))
    except json.JSONDecodeError:
        pass

    # Strategy 3: Iterative targeted repair
    try:
        return json.loads(repair_json_iteratively(json_str))
    except json.JSONDecodeError:
        pass

    # Strategy 4: json5 lenient parser (tolerates trailing commas, comments, etc.)
    try:
        import json5
        return json5.loads(json_str)
    except:
        pass

    raise json.JSONDecodeError(f"Failed after all strategies", json_str, 0)
```

### 11.3 Arithmetic Expression Evaluator

```python
import re

def fix_arithmetic_in_json(json_str: str) -> str:
    """Replace '285.00 + 45.00' with '330.00' in JSON values."""
    pattern = r':\s*(\d+(?:\.\d+)?\s*[\+\-\*\/]\s*\d+(?:\.\d+)?)\s*([,\}\]])'

    def evaluate(m):
        expr, suffix = m.group(1), m.group(2)
        if re.match(r'^[\d\s\.\+\-\*\/]+$', expr):
            result = eval(expr)
            return f": {result:.2f}{suffix}"
        return m.group(0)

    return re.sub(pattern, evaluate, json_str)
```

---

## 12. Service Bus Integration

### 12.1 Dual-Format Auto-Detection

Support both raw email format (from monitoring) and pre-structured format:

```python
def is_raw_email_format(message: dict) -> bool:
    return "from" in message and "body_text" in message

def transform_servicebus_message(raw_message: dict) -> dict:
    # Extract email from "Name <email>" format
    from_field = raw_message.get("from", "")
    email_match = re.search(r'<([^>]+)>', from_field)
    sender_email = email_match.group(1) if email_match else from_field.strip()

    # Get first attachment URL
    attachments = raw_message.get("attachments", [])
    attachment_url = attachments[0].get("blob_url", "") if attachments else ""

    return {
        "claim_id": f"CSB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "sender_email": sender_email,
        "email_content": raw_message.get("body_text", ""),
        "attachment_url": attachment_url
    }
```

### 12.2 Idempotent Processing

```python
# Before starting orchestration, check if already running
status = await client.get_status(instance_id)
if status and status.runtime_status.name in ["Running", "Pending"]:
    logger.info(f"Orchestration {instance_id} already running, skipping")
    return
```

---

## 13. Dashboard & Real-Time Visualization

### 13.1 Serving Static HTML from Azure Functions

```python
@app.route(route="dashboard", methods=["GET"])
async def serve_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    html_path = Path(__file__).parent / "static" / "dashboard.html"
    return func.HttpResponse(
        html_path.read_text(encoding="utf-8"),
        mimetype="text/html"
    )
```

### 13.2 Dashboard Polling Pattern

The dashboard polls a state endpoint every N seconds:

```javascript
// dashboard.html
setInterval(async () => {
    const response = await fetch('/api/claims');
    const data = await response.json();
    updateClaimsTable(data.claims);
}, 10000); // Every 10 seconds
```

### 13.3 Status Display Mapping

Map internal step names to user-friendly display names:

```python
display_status = {
    "agent1_processing": "Classifier Agent Activated",
    "awaiting_approval": "Awaiting Manual Estimate",
    "agent2_processing": "Adjudication Agent Activated",
    "agent3_processing": "Email Composer Agent Activated",
    "completed": "Completed",
    "rejected": "Rejected",
    "timeout": "Timed Out"
}.get(step, step.replace("_", " ").title())
```

---

## 14. Testing Strategy

### 14.1 Unit Tests (Pydantic Models)

```python
# tests/test_models.py
def test_agent1_output_validates():
    data = {"classification": {"claim_type": "VSC"}, "confidence_score": 0.92, ...}
    output = Agent1Output.model_validate(data)
    assert output.classification.claim_type == "VSC"

def test_clean_numeric_strips_formatting():
    """LLM returns '$1,234.56' — should parse to 1234.56"""
    info = ExtractedInfo(total_estimate="$1,234.56")
    assert info.total_estimate == 1234.56
```

### 14.2 Mock Mode Testing

Set `AGENT_MOCK_MODE=true` and run the full flow. Mock responses exercise the complete orchestration path without Azure credentials.

### 14.3 Load Testing

```python
# tests/test_clone_load.py
# Submit N claims via HTTP, then batch-approve all waiting claims
for i in range(10):
    requests.post("http://localhost:7071/api/claims/start", json={
        "claim_id": f"LOAD-{i:03d}",
        "email_content": "Test claim",
        "attachment_url": "",
        "sender_email": "test@test.com"
    })
```

### 14.4 Manual Testing with curl

```bash
# Start a claim
curl -X POST "http://localhost:7071/api/claims/start" \
  -H "Content-Type: application/json" \
  -d '{"claim_id":"TEST-001","email_content":"Claim for repair","attachment_url":"","sender_email":"test@test.com"}'

# Check status
curl "http://localhost:7071/api/claims/status/claim-TEST-001"

# Submit approval (raise external event)
curl -X POST "http://localhost:7071/api/claims/approve/claim-TEST-001" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approved","reviewer":"reviewer@test.com","claim_data":{"claimant":{"name":"Test"}}}'

# Raise event directly via Durable Task HTTP API
curl -X POST "http://localhost:7071/runtime/webhooks/durabletask/instances/claim-TEST-001/raiseEvent/ApprovalDecision" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approved","reviewer":"test@test.com"}'
```

---

## 15. Common Pitfalls & Solutions

### 15.1 Durable Functions Pitfalls

| Pitfall | Solution |
|---------|----------|
| Using `datetime.now()` in orchestrator | Use `context.current_utc_datetime` |
| Logging on every replay | Guard with `if not context.is_replaying:` |
| Direct I/O in orchestrator | Move all I/O to activity functions |
| Event name mismatch | `"ApprovalDecision"` is **case-sensitive** |
| Forgetting to cancel timer | Always `timeout_task.cancel()` when event wins |
| Non-deterministic instance IDs | Use deterministic format: `f"claim-{claim_id}"` |
| Activity returns non-serializable | Always return plain dicts from activities |

### 15.2 Azure AI Foundry Pitfalls

| Pitfall | Solution |
|---------|----------|
| SDK API changes | Pin `azure-ai-projects>=1.0.0b7` — APIs changed between betas |
| Agent returns markdown-wrapped JSON | Strip ```json blocks before parsing |
| Agent returns arithmetic expressions | Evaluate `285.00 + 45.00` → `330.00` |
| Agent returns inconsistent schema | Use `Optional` fields and `list[Any]` |
| Agent times out | Add retry logic with 1-second delays |
| Mock vs Real response mismatch | Keep mock responses updated when schema changes |

### 15.3 General Pitfalls

| Pitfall | Solution |
|---------|----------|
| `get_status_by()` missing instances | Use DT HTTP API directly with `instanceIdPrefix` |
| `custom_status` may be string or dict | Always check: `if isinstance(cs, str): cs = json.loads(cs)` |
| URL spaces in attachment paths | Use `urllib.parse.quote(path, safe='/')` |
| `runtime_status` may be enum or string | Always: `rs.name if hasattr(rs, 'name') else str(rs)` |

---

## 16. Development Workflow with Claude Code

### 16.1 Phased Development

We built this project in 8 phases, each building on the previous:

| Phase | What | Key Deliverable |
|-------|------|-----------------|
| 1 | Scaffolding | Directory structure, `host.json`, health check |
| 2 | Data Models | Pydantic models, prompts, agent client |
| 3 | Agent 1 | Real AI Foundry integration, orchestrator |
| 4 | HITL | External event wait, approval endpoint |
| 5 | Agent 2 | Adjudicator integration, full flow |
| 6 | Review UI | HTML form, pre-filled from Agent 1 |
| 7 | Dashboard | Claims dashboard, timeline, status tracking |
| 8 | Email Agent | Email composer, SMTP sending |

**Each phase was testable independently.** Phase 1-2 work without Azure credentials (mock mode). Phase 3+ progressively adds real integrations.

### 16.2 Tips for Working with Claude Code

1. **Create a `DEVELOPMENT_PLAN.md`** with checkboxes for each deliverable. Claude Code can track progress and check items off.

2. **Create a comprehensive `CLAUDE.md`** (see Section 17) with project context, code templates, and rules. This is loaded into Claude Code's context every session.

3. **Test after each phase** — don't wait until the end. Give Claude Code the test commands and expected outputs.

4. **Use mock mode early** — get the full orchestration flow working with mocks before integrating real agents.

5. **Pin SDK versions** — Azure AI SDKs are in preview and change frequently. Record working versions in `requirements.txt`.

6. **Track issues** — maintain an "Issues & Blockers Log" in your development plan. This helps Claude Code avoid repeating past mistakes.

### 16.3 Effective Prompting for Claude Code

- **Be specific about file structure:** "Create `activities/agent1_activity.py` with a function `run_agent1_activity(input_data: dict) -> dict`"
- **Provide expected I/O:** "Agent1 input looks like `{claim_id, email_content, ...}`, output should match the Agent1Output Pydantic model"
- **Reference existing patterns:** "Follow the same pattern as agent1_activity.py for the new agent2_activity.py"
- **Share test data:** Provide sample JSON inputs and expected outputs

---

## 17. CLAUDE.md — Your AI Assistant's Playbook

The `CLAUDE.md` file is automatically loaded into Claude Code's context. It should contain:

### 17.1 Essential Sections

```markdown
# CLAUDE.md - Project Reference

## Project Context
Brief description of what the project does and the business domain.

## Development Rules
- Git commit conventions
- Package management rules (always use requirements.txt)
- Code style preferences

## Quick Links
Links to relevant documentation (Azure Durable Functions, AI Foundry, etc.)

## Code Templates
Working code snippets for common patterns:
- HTTP trigger template
- Orchestrator template
- Activity template
- External event (HITL) template
- Agent invocation template

## Configuration Files
Template versions of host.json and local.settings.json.

## Debugging Tips
How to test locally, view orchestration status, raise events via curl.

## Troubleshooting
Common issues and their solutions.

## Version Compatibility
Minimum and recommended versions for all dependencies.
```

### 17.2 Why CLAUDE.md Matters

- It gives Claude Code **project-specific context** that persists across sessions
- It prevents Claude Code from guessing SDK versions or API patterns
- It serves as **living documentation** that gets updated as the project evolves
- It includes **working code templates** so Claude Code writes code that actually compiles

### 17.3 Template for Your Team

Create your own `CLAUDE.md` starting with:
1. Your project's business domain
2. Your specific Azure resource names and endpoints
3. Your preferred code style and conventions
4. Working code templates from your codebase
5. Known issues and workarounds

---

## Quick Reference Card

### Start Development
```powershell
.\start-local.ps1                    # Start Docker emulators
cd function_app
pip install -r requirements.txt      # Install dependencies
func start                           # Start function app
```

### Key URLs (Local)
| URL | Purpose |
|-----|---------|
| `http://localhost:7071/api/health` | Health check |
| `http://localhost:7071/api/dashboard` | Claims dashboard |
| `http://localhost:7071/api/claims/start` | Start orchestration (POST) |
| `http://localhost:7071/api/claims` | List all claims (GET) |
| `http://localhost:7071/api/claims/status/{id}` | Get claim status (GET) |
| `http://localhost:7071/api/claims/approve/{id}` | Submit approval (POST) |
| `http://localhost:7071/api/review/{id}` | Human review form (GET) |
| `http://localhost:8082` | DTS emulator dashboard |

### Key Files
| File | What It Does |
|------|-------------|
| `function_app.py` | All triggers + orchestrator + activity wrappers |
| `shared/models.py` | Pydantic models for all agents |
| `shared/agent_client.py` | AI Foundry invocation + JSON repair |
| `shared/prompts.py` | Agent prompt templates |
| `activities/*.py` | Activity implementations |
| `host.json` | Durable Functions configuration |
| `local.settings.json` | Environment variables |
| `CLAUDE.md` | AI assistant project context |

---

> **Note:** This document was generated from a production insurance claims processing system. Adapt the patterns, models, and agent configurations to fit your specific domain and workflow requirements.
