# CLAUDE.md - Azure Durable Functions HITL Project Reference

## Project Context

This project implements Human-in-the-Loop (HITL) orchestration between two Azure AI Foundry agents using Azure Durable Functions in Python.

## Development Rules

### **IMPORTANT: Git Commit Rules**
- **NEVER** include "Claude" or "Co-Authored-By: Claude" in commit messages
- **ALWAYS** confirm commit message with user before committing
- Keep commit messages concise and descriptive

### Package Management
- **ALWAYS** add new packages to `function_app/requirements.txt` first
- **ALWAYS** install via `pip install -r requirements.txt`, never install packages directly with `pip install <package>`
- This ensures reproducible builds and proper dependency tracking

### Installing Dependencies
```powershell
cd function_app
pip install -r requirements.txt
```

### Adding New Packages
1. Add to `function_app/requirements.txt`
2. Run `pip install -r requirements.txt`
3. Restart the function app (`func start`)

## Quick Links - Official Documentation

### Azure Durable Functions

| Topic | URL |
|-------|-----|
| **Durable Functions Overview** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview?tabs=python |
| **Python Programming Model v2** | https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python?tabs=get-started%2Casgi%2Capplication-level&pivots=python-mode-decorators |
| **External Events (HITL)** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-external-events?tabs=python |
| **Orchestration Patterns** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview?tabs=python#application-patterns |
| **Error Handling & Retries** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-error-handling?tabs=python |
| **Timers & Timeouts** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-timers?tabs=python |
| **HTTP API Reference** | https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-http-api |

### Microsoft Agent Framework

| Topic | URL |
|-------|-----|
| **Agent Framework Overview** | https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview |
| **Durable Agents** | https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/durable-agent/create-durable-agent |
| **Durable Agent Features** | https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/durable-agent/features?pivots=programming-language-python |
| **Azure AI Foundry Agents** | https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/azure-ai-foundry-agent |
| **Workflows & Checkpointing** | https://learn.microsoft.com/en-us/agent-framework/user-guide/workflows/checkpoints?pivots=programming-language-python |
| **Multi-Turn Conversations** | https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/multi-turn-conversation |
| **GitHub Repository** | https://github.com/microsoft/agent-framework |

### Azure AI Foundry

| Topic | URL |
|-------|-----|
| **AI Foundry Overview** | https://learn.microsoft.com/en-us/azure/ai-foundry/ |
| **Agent Service Quickstart** | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/quickstart |
| **Python SDK Reference** | https://learn.microsoft.com/en-us/python/api/azure-ai-projects/ |
| **Workflows in Foundry** | https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/workflow |

## Code Templates

### Template 1: Basic Durable Functions App Structure (Python v2)

```python
# function_app.py
import azure.functions as func
import azure.durable_functions as df
import logging

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

# HTTP Trigger - Start Orchestration
@app.route(route="orchestrators/{functionName}")
@app.durable_client_input(client_name="client")
async def http_start(req: func.HttpRequest, client) -> func.HttpResponse:
    function_name = req.route_params.get('functionName')
    instance_id = await client.start_new(function_name, None, req.get_json())
    
    logging.info(f"Started orchestration with ID = '{instance_id}'.")
    return client.create_check_status_response(req, instance_id)

# Orchestrator Function
@app.orchestration_trigger(context_name="context")
def my_orchestrator(context: df.DurableOrchestrationContext):
    result1 = yield context.call_activity("Activity1", context.get_input())
    result2 = yield context.call_activity("Activity2", result1)
    return result2

# Activity Function
@app.activity_trigger(input_name="input")
def Activity1(input: dict) -> dict:
    # Do work here
    return {"result": "processed"}
```

### Template 2: External Event Pattern (HITL)

```python
@app.orchestration_trigger(context_name="context")
def approval_workflow(context: df.DurableOrchestrationContext):
    # Step 1: Do initial work
    initial_result = yield context.call_activity("ProcessInitial", context.get_input())
    
    # Step 2: Request approval
    yield context.call_activity("SendApprovalRequest", {
        "instance_id": context.instance_id,
        "data": initial_result
    })
    
    # Step 3: Wait for external event with timeout
    from datetime import timedelta
    
    approval_event = context.wait_for_external_event("ApprovalDecision")
    timeout_event = context.create_timer(context.current_utc_datetime + timedelta(hours=24))
    
    winner = yield context.task_any([approval_event, timeout_event])
    
    if winner == timeout_event:
        return {"status": "timeout", "message": "Approval timed out after 24 hours"}
    
    timeout_event.cancel()
    approval_data = approval_event.result
    
    # Step 4: Check decision
    if approval_data.get("decision") == "rejected":
        return {"status": "rejected", "reviewer": approval_data.get("reviewer")}
    
    # Step 5: Continue with approved workflow
    final_result = yield context.call_activity("ProcessApproved", {
        "initial_result": initial_result,
        "approval_data": approval_data
    })
    
    return {"status": "completed", "result": final_result}
```

### Template 3: Raise External Event

```python
@app.route(route="approve/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def approve_instance(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = req.route_params.get('instance_id')
    
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)
    
    # Check if instance exists and is running
    status = await client.get_status(instance_id)
    if not status:
        return func.HttpResponse("Instance not found", status_code=404)
    
    if status.runtime_status.name != "Running":
        return func.HttpResponse(
            f"Instance is {status.runtime_status.name}, not waiting for approval",
            status_code=400
        )
    
    # Raise the event
    await client.raise_event(
        instance_id=instance_id,
        event_name="ApprovalDecision",
        event_data=body
    )
    
    return func.HttpResponse(f"Approval event sent to {instance_id}")
```

### Template 4: Azure AI Foundry Agent Invocation

```python
import os
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.ai.projects import AIProjectClient

def get_credential():
    """Get OAuth credential - Service Principal or Default."""
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if all([tenant_id, client_id, client_secret]):
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    return DefaultAzureCredential()

def invoke_foundry_agent(agent_name: str, user_message: str) -> str:
    """Invoke an Azure AI Foundry agent and return the response."""
    credential = get_credential()
    
    project_client = AIProjectClient(
        endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        credential=credential,
    )
    
    agent = project_client.agents.get(agent_name=agent_name)
    openai_client = project_client.get_openai_client()
    
    response = openai_client.responses.create(
        input=[{"role": "user", "content": user_message}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    
    return response.output_text
```

### Template 5: Activity with Retry Policy

```python
import azure.durable_functions as df

# In orchestrator
@app.orchestration_trigger(context_name="context")
def orchestrator_with_retry(context: df.DurableOrchestrationContext):
    retry_options = df.RetryOptions(
        first_retry_interval_in_milliseconds=5000,  # 5 seconds
        max_number_of_attempts=3,
        backoff_coefficient=2.0,
        max_retry_interval_in_milliseconds=60000,  # 1 minute
        retry_timeout_in_milliseconds=300000  # 5 minutes total
    )
    
    result = yield context.call_activity_with_retry(
        "UnreliableActivity",
        retry_options,
        context.get_input()
    )
    return result
```

### Template 6: Custom Status Updates

```python
@app.orchestration_trigger(context_name="context")
def orchestrator_with_status(context: df.DurableOrchestrationContext):
    # Update custom status for external visibility
    context.set_custom_status({
        "step": "agent1_processing",
        "progress": 25,
        "message": "Processing with Agent 1..."
    })
    
    result1 = yield context.call_activity("Agent1Activity", context.get_input())
    
    context.set_custom_status({
        "step": "awaiting_approval",
        "progress": 50,
        "message": "Waiting for human approval",
        "agent1_result_summary": result1.get("summary")
    })
    
    # Wait for approval...
    approval = yield context.wait_for_external_event("ApprovalDecision")
    
    context.set_custom_status({
        "step": "agent2_processing",
        "progress": 75,
        "message": "Processing with Agent 2..."
    })
    
    result2 = yield context.call_activity("Agent2Activity", {
        "agent1_result": result1,
        "approval": approval
    })
    
    return result2
```

## Configuration Files

### host.json

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensions": {
    "durableTask": {
      "storageProvider": {
        "type": "AzureStorage"
      },
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

### local.settings.json

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_AI_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
    "AZURE_TENANT_ID": "your-tenant-id",
    "AZURE_CLIENT_ID": "your-client-id",
    "AZURE_CLIENT_SECRET": "your-client-secret",
    "AGENT1_NAME": "claim-assistant-agent",
    "AGENT2_NAME": "claim-approval-agent",
    "APPROVAL_TIMEOUT_HOURS": "24"
  }
}
```

## Common Patterns

### Pattern: Fan-out/Fan-in with Multiple Agents

```python
@app.orchestration_trigger(context_name="context")
def parallel_agents(context: df.DurableOrchestrationContext):
    input_data = context.get_input()
    
    # Start multiple agent tasks in parallel
    tasks = [
        context.call_activity("AgentA", input_data),
        context.call_activity("AgentB", input_data),
        context.call_activity("AgentC", input_data),
    ]
    
    # Wait for all to complete
    results = yield context.task_all(tasks)
    
    # Aggregate results
    return {"agent_a": results[0], "agent_b": results[1], "agent_c": results[2]}
```

### Pattern: Sequential Agents with Conditional Logic

```python
@app.orchestration_trigger(context_name="context")
def conditional_workflow(context: df.DurableOrchestrationContext):
    result1 = yield context.call_activity("Agent1", context.get_input())
    
    if result1.get("requires_agent2"):
        result2 = yield context.call_activity("Agent2", result1)
        return result2
    else:
        return result1
```

## Debugging Tips

1. **View orchestration status**: Use the built-in HTTP APIs
   - `GET /runtime/webhooks/durabletask/instances/{instanceId}`

2. **Local debugging with Azurite**: Run Azurite for local storage emulation
   ```bash
   azurite --silent --location ./azurite --debug ./azurite/debug.log
   ```

3. **Enable verbose logging**: In host.json
   ```json
   "logging": { "logLevel": { "DurableTask.AzureStorage": "Debug" } }
   ```

4. **Test external events locally**: Use curl to raise events
   ```bash
   curl -X POST "http://localhost:7071/runtime/webhooks/durabletask/instances/{instanceId}/raiseEvent/ApprovalDecision" \
     -H "Content-Type: application/json" \
     -d '{"decision": "approved"}'
   ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Orchestration stuck in "Pending" | Check Activity function errors; verify storage connection |
| External event not received | Verify event name matches exactly (case-sensitive) |
| Timeout not firing | Ensure timer is yielded: `yield context.task_any([...])` |
| State not persisting | Check AzureWebJobsStorage connection string |
| Agent call timeout | Increase activity timeout; add retry policy |

## Version Compatibility

| Component | Minimum Version | Recommended |
|-----------|-----------------|-------------|
| Python | 3.9 | 3.11 |
| azure-functions | 1.17.0 | Latest |
| azure-durable-functions | 1.2.9 | Latest |
| azure-ai-projects | 1.0.0b1 | Latest preview |
| agent-framework | 0.1.0b1 | Latest preview |

## Local Development Setup (Windows PowerShell)

### Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **Docker Desktop** | Runs Azurite and Durable Task Scheduler emulators |
| **Node.js** (v18+) | Required for Azure Functions Core Tools |
| **Python** (3.9+) | Runtime for your functions |
| **Azure CLI** | Authentication (`az login`) |

### Installation

**Azure Functions Core Tools:**
```powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
func --version
```

**Pull Docker Images:**
```powershell
docker pull mcr.microsoft.com/azure-storage/azurite
docker pull mcr.microsoft.com/dts/dts-emulator:latest
```

### Running Emulators

**Azurite (Storage Emulator):**
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
| 10000 | Blob |
| 10001 | Queue |
| 10002 | Table |

**Durable Task Scheduler:**
```powershell
docker run -d `
  --name dts-emulator `
  -p 8080:8080 `
  -p 8082:8082 `
  mcr.microsoft.com/dts/dts-emulator:latest
```

| Port | Service |
|------|---------|
| 8080 | gRPC endpoint (app connection) |
| 8082 | Dashboard UI |

### Quick Start Script (start-local.ps1)

```powershell
Write-Host "Starting Azurite..."
docker start azurite 2>$null
if ($LASTEXITCODE -ne 0) {
    docker run -d --name azurite -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
}

Write-Host "Starting Durable Task Scheduler..."
docker start dts-emulator 2>$null
if ($LASTEXITCODE -ne 0) {
    docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
}

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Emulators running:"
Write-Host "  - Azurite: localhost:10000-10002"
Write-Host "  - DTS Dashboard: http://localhost:8082"
Write-Host ""
Write-Host "Run 'func start' to start your function app"
```

### Running the Function App

```powershell
cd function_app
func start
```

Functions available at: `http://localhost:7071`

**Dashboard:** http://localhost:8082

### Managing Containers

```powershell
docker ps                              # Check running containers
docker stop azurite dts-emulator       # Stop emulators
docker start azurite dts-emulator      # Start emulators
docker rm azurite dts-emulator         # Remove containers (reset state)
docker logs azurite                    # View logs
docker logs dts-emulator
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Port already in use | `docker stop <container_name>` |
| Docker not running | Start Docker Desktop |
| Storage connection error | Verify Azurite: `docker ps` |
| Orchestration not persisting | Check logs: `docker logs dts-emulator` |
| Functions not starting | Verify `func --version` and Python version |
| PowerShell script blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

**Note:** Emulator data is in-memory - restarting containers clears all state.

---

## Related Microsoft Tech Community Articles

- [Multi-agent Workflow with Human Approval](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/multi-agent-workflow-with-human-approval-using-agent-framework/4465927)
- [Bulletproof Agents with Durable Task Extension](https://techcommunity.microsoft.com/blog/appsonazureblog/bulletproof-agents-with-the-durable-task-extension-for-microsoft-agent-framework/4467122)
- [Building Human-in-the-loop AI Workflows](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/building-human-in-the-loop-ai-workflows-with-microsoft-agent-framework/4460342)
