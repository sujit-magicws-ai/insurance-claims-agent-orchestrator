# Claude Code Development Prompt: Durable Functions HITL Orchestration

## Project Overview

Build an Azure Durable Functions application in Python that orchestrates two existing Azure AI Foundry agents with a Human-in-the-Loop (HITL) approval gate between them.

## Architecture

```
HTTP Trigger (Start) 
    → Orchestrator Function
        → Agent1 Activity (claim-assistant-agent)
        → Notify Activity (send approval request)
        → WaitForExternalEvent("ApprovalDecision")
        → Agent2 Activity (claim-approval-agent)
    → Return final result

HTTP Trigger (Approval)
    → RaiseEventAsync to wake orchestrator
```

## Existing Agent Integration

The two Azure AI Foundry agents are already deployed and tested. Use this authentication pattern:

```python
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.ai.projects import AIProjectClient

def get_credential():
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant_id and client_id and client_secret:
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        return DefaultAzureCredential()

# Agent invocation pattern
project_client = AIProjectClient(
    endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
    credential=credential,
)
agent = project_client.agents.get(agent_name="agent-name")
openai_client = project_client.get_openai_client()
response = openai_client.responses.create(
    input=[{"role": "user", "content": user_message}],
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
```

## Required Components

### 1. Function App Structure

Create the following file structure:

```
function_app/
├── function_app.py          # Main function app with all triggers
├── orchestrator.py          # Orchestrator function logic
├── activities/
│   ├── __init__.py
│   ├── agent1_activity.py   # Calls claim-assistant-agent
│   ├── agent2_activity.py   # Calls claim-approval-agent
│   └── notify_activity.py   # Sends approval notification
├── shared/
│   ├── __init__.py
│   ├── agent_client.py      # Shared agent invocation logic
│   └── models.py            # Pydantic models for data transfer
├── host.json
├── local.settings.json
└── requirements.txt
```

### 2. Orchestrator Function

The orchestrator must:

1. Receive claim data as input
2. Call Agent1 Activity with the claim document URL
3. Save Agent1 output (parsed claim data)
4. Call Notify Activity to send approval request
5. Call `context.wait_for_external_event("ApprovalDecision")` with 24-hour timeout
6. Handle timeout → return timeout response or escalate
7. Handle rejection → return rejection response
8. Handle approval → Call Agent2 Activity with Agent1 output
9. Return final adjudication result

### 3. Activity Functions

**Agent1 Activity (claim-assistant-agent)**
- Input: `{ "document_url": "https://...", "claim_id": "..." }`
- Calls the existing claim-assistant-agent in Azure AI Foundry
- Output: Parsed claim data (JSON structure)

**Agent2 Activity (claim-approval-agent)**
- Input: `{ "claim_data": {...}, "approval_info": {...} }`
- Calls the existing claim-approval-agent in Azure AI Foundry
- Output: Adjudication decision (JSON structure)

**Notify Activity**
- Input: `{ "instance_id": "...", "claim_summary": {...}, "approval_url": "..." }`
- Sends notification (log for now, can extend to email/Teams)
- Output: `{ "notification_sent": true, "timestamp": "..." }`

### 4. HTTP Triggers

**Start Trigger (POST /api/claims/start)**
- Accepts claim submission JSON
- Starts new orchestration instance
- Returns: `{ "instance_id": "...", "status_url": "...", "approval_url": "..." }`

**Approval Trigger (POST /api/claims/approve/{instance_id})**
- Accepts: `{ "decision": "approved" | "rejected", "reviewer": "...", "comments": "..." }`
- Calls `client.raise_event(instance_id, "ApprovalDecision", approval_data)`
- Returns: `{ "success": true, "message": "..." }`

**Status Trigger (GET /api/claims/status/{instance_id})**
- Returns current orchestration status and history

### 5. Data Models (Pydantic)

```python
class ClaimRequest(BaseModel):
    claim_id: str
    document_url: str
    claimant_name: str
    metadata: dict = {}

class Agent1Output(BaseModel):
    claim_id: str
    parsed_data: dict
    confidence_score: float
    requires_review: bool

class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer: str
    comments: str = ""
    timestamp: datetime

class Agent2Output(BaseModel):
    claim_id: str
    adjudication_result: Literal["approved", "denied", "partial"]
    amount_approved: float
    reasoning: str

class OrchestrationResult(BaseModel):
    claim_id: str
    status: Literal["completed", "rejected", "timeout", "error"]
    agent1_output: Agent1Output | None
    approval_decision: ApprovalDecision | None
    agent2_output: Agent2Output | None
    error_message: str | None
```

## Environment Variables Required

```
AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/api/projects/your-project
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AGENT1_NAME=claim-assistant-agent
AGENT2_NAME=claim-approval-agent
APPROVAL_TIMEOUT_HOURS=24
NOTIFICATION_WEBHOOK_URL=https://your-notification-endpoint (optional)
```

## Key Implementation Requirements

### Error Handling
- Wrap all agent calls in try/except
- Use Durable Functions retry policies for transient failures
- Log all errors with correlation IDs (instance_id)

### Timeout Handling
```python
import azure.durable_functions as df
from datetime import timedelta

approval_event = context.wait_for_external_event("ApprovalDecision")
timeout_task = context.create_timer(
    context.current_utc_datetime + timedelta(hours=24)
)
winner = yield context.task_any([approval_event, timeout_task])

if winner == timeout_task:
    # Handle timeout - escalate or auto-reject
    pass
else:
    timeout_task.cancel()
    approval_data = approval_event.result
```

### Idempotency
- Activities should be idempotent (safe to retry)
- Use deterministic instance IDs based on claim_id if needed

### Logging
- Use Python logging with structured output
- Include instance_id in all log messages
- Log state transitions for debugging

## Testing Requirements

1. Create a test script that:
   - Starts a new orchestration
   - Queries status
   - Submits approval
   - Verifies completion

2. Test scenarios:
   - Happy path (approved)
   - Rejection path
   - Timeout path
   - Agent1 failure
   - Agent2 failure

## Documentation

Include docstrings for all functions explaining:
- Purpose
- Input/output formats
- Error conditions
- Retry behavior

## Reference Documentation

- Azure Durable Functions Python: https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview?tabs=python
- External Events: https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-external-events
- Azure AI Projects SDK: https://learn.microsoft.com/en-us/python/api/azure-ai-projects/
- Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview

## Deliverables

1. Complete function app code with all components
2. local.settings.json template
3. host.json with appropriate settings
4. README.md with setup and deployment instructions
5. Test script for end-to-end testing
