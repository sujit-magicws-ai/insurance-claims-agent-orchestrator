# Insurance Claims HITL Orchestration

Multi-agent workflow for processing insurance claims using Azure Durable Functions with Human-in-the-Loop (HITL) approval. Three Azure AI Foundry agents handle classification, adjudication, and email composition, with a human review gate between classification and adjudication.

## Workflow

```
Claim arrives (HTTP or Service Bus)
        |
        v
  Agent 1: Classify claim (type, urgency, extract info from email + PDF)
        |
        v
  HITL: Human reviews classification, edits data, approves or rejects
        |
   +---------+---------+
   |                   |
   v                   v
 Rejected           Approved
 (end)                 |
                       v
              Agent 2: Adjudicate (validate coverage, calculate payout)
                       |
                       v
              Agent 3: Compose notification email
                       |
                       v
              Send email via SMTP
```

## Project Structure

```
function_app/
├── function_app.py              # Main entry point — triggers, orchestrator, all activity registrations
├── host.json                    # Azure Functions + Durable Task configuration
├── local.settings.json          # Environment variables (not in git — see setup below)
├── requirements.txt             # Python dependencies
│
├── activities/                  # Activity function implementations
│   ├── agent1_activity.py       #   Claim classification (Agent 1)
│   ├── agent2_activity.py       #   Claim adjudication (Agent 2)
│   ├── agent3_activity.py       #   Email composition (Agent 3)
│   ├── notify_activity.py       #   Approval notification logging
│   └── send_email_activity.py   #   SMTP email delivery (Gmail)
│
├── shared/                      # Shared libraries
│   ├── models.py                #   Pydantic data models (inputs/outputs for all stages)
│   ├── agent_client.py          #   Azure AI Foundry agent invocation + JSON repair
│   ├── prompts.py               #   Agent prompt templates
│   ├── contractor_manager.py    #   AI contractor workforce state (for dashboard)
│   └── agent_personas.json      #   Named contractor personas and pool config
│
├── static/                      # Web dashboards
│   ├── dashboard.html           #   Claims dashboard (list, status, timeline)
│   ├── clone_dashboard.html     #   AI contractor workforce visualizer
│   ├── review.html              #   Human review form (HITL approval/rejection)
│   └── email_composer_demo.html #   Standalone email composer test UI
│
└── tests/                       # Tests and tooling
    ├── test_models.py           #   Pydantic model validation tests
    ├── test_contractor_manager.py
    ├── test_clone_load.py
    └── HITL-Claims.postman_collection.json  # Postman collection for API testing
```

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://www.python.org/downloads/ |
| Node.js | 18+ | https://nodejs.org/ |
| Docker Desktop | Latest | https://www.docker.com/products/docker-desktop/ |
| Azure Functions Core Tools | 4.x | `npm install -g azure-functions-core-tools@4 --unsafe-perm true` |
| Azure CLI | Latest | https://learn.microsoft.com/en-us/cli/azure/install-azure-cli |

Verify installations:

```powershell
python --version          # 3.11+
node --version            # 18+
docker --version          # Docker Desktop running
func --version            # 4.x
az --version              # Azure CLI
```

## Setup

### 1. Clone the repo

```powershell
git clone <repo-url>
cd DURFUNC
```

### 2. Pull Docker images

```powershell
docker pull mcr.microsoft.com/azure-storage/azurite
docker pull mcr.microsoft.com/dts/dts-emulator:latest
```

### 3. Start emulators

Run the provided script:

```powershell
.\start-local.ps1
```

This starts two Docker containers:

| Container | Ports | Purpose |
|-----------|-------|---------|
| `azurite` | 10000 (Blob), 10001 (Queue), 10002 (Table) | Azure Storage emulator — stores orchestration state |
| `dts-emulator` | 8080 (gRPC), 8082 (Dashboard) | Durable Task Scheduler — orchestration engine |

DTS Dashboard: http://localhost:8082

### 4. Create `local.settings.json`

This file is gitignored. Create `function_app/local.settings.json` with the following template and fill in your credentials:

```json
{
  "IsEncrypted": false,
  "Host": {
    "CORS": "*"
  },
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",

    "AGENT1_PROJECT_ENDPOINT": "<your-agent1-ai-foundry-endpoint>",
    "AGENT1_NAME": "claim-assistant-agent",

    "AGENT2_PROJECT_ENDPOINT": "<your-agent2-ai-foundry-endpoint>",
    "AGENT2_NAME": "claim-approval-agent",

    "AGENT3_PROJECT_ENDPOINT": "<your-agent3-ai-foundry-endpoint>",
    "AGENT3_NAME": "EmailComposerAgent",

    "AZURE_TENANT_ID": "<your-azure-tenant-id>",
    "AZURE_CLIENT_ID": "<your-service-principal-client-id>",
    "AZURE_CLIENT_SECRET": "<your-service-principal-client-secret>",

    "APPROVAL_TIMEOUT_HOURS": "24",
    "AGENT_MOCK_MODE": "false",

    "SERVICE_BUS_CONNECTION_STRING": "<your-service-bus-connection-string>",
    "SERVICE_BUS_QUEUE_NAME": "claims-agent-inbox",

    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "<your-gmail-address>",
    "SMTP_PASSWORD": "<your-gmail-app-password>",
    "EMAIL_FROM_ADDRESS": "<your-gmail-address>",
    "EMAIL_FROM_NAME": "Claims Department",
    "REVIEW_EMAIL_ADDRESS": "<email-for-review-notifications>"
  }
}
```

**To run without Azure AI credentials**, set `"AGENT_MOCK_MODE": "true"` — all agents will return realistic mock data.

### 5. Install Python dependencies

```powershell
cd function_app
pip install -r requirements.txt
```

### 6. Start the function app

```powershell
func start
```

Function app runs at: http://localhost:7071

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/claims/start` | Start a new claim orchestration |
| `GET` | `/api/claims/{instance_id}` | Get claim status and output |
| `GET` | `/api/claims` | List all claims (optional `?status=Running`) |
| `POST` | `/api/claims/approve/{instance_id}` | Submit HITL approval/rejection |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/contractors/state` | Contractor workforce state (for dashboard) |
| `GET` | `/api/contractors/config` | Contractor pool configuration |

## Dashboards

| URL | Description |
|-----|-------------|
| http://localhost:7071/dashboard | Claims dashboard — track all claims through stages |
| http://localhost:7071/clone-dashboard | AI contractor visualizer — real-time workforce view |
| http://localhost:7071/review/{instance_id} | Human review form — approve/reject a specific claim |
| http://localhost:7071/email-composer-demo | Email composer test UI |
| http://localhost:8082 | Durable Task Scheduler dashboard |

## Quick Test

### Submit a test claim

```bash
curl -X POST http://localhost:7071/api/claims/start \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "TEST-001",
    "email_content": "I need to file a VSC claim for my 2021 Toyota Camry. The transmission failed at 45,000 miles. Repair estimate is $3,200.",
    "sender_email": "john.doe@example.com"
  }'
```

### Check claim status

```bash
curl http://localhost:7071/api/claims/claim-TEST-001
```

### Approve a claim (after it reaches HITL stage)

```bash
curl -X POST http://localhost:7071/api/claims/approve/claim-TEST-001 \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approved",
    "reviewer": "reviewer@example.com",
    "comments": "Looks good",
    "claim_data": {
      "claimant_name": "John Doe",
      "vehicle_year": "2021",
      "vehicle_make": "Toyota",
      "vehicle_model": "Camry",
      "repair_description": "Transmission replacement",
      "total_estimate": "3200.00"
    }
  }'
```

Or use the Postman collection at `function_app/tests/HITL-Claims.postman_collection.json`.

## Running Tests

```powershell
cd function_app
python -m pytest tests/ -v
```

## Managing Docker Containers

```powershell
docker ps                              # Check running containers
docker stop azurite dts-emulator       # Stop emulators
docker start azurite dts-emulator      # Restart emulators
docker rm azurite dts-emulator         # Remove containers (resets all state)
docker logs azurite                    # View Azurite logs
docker logs dts-emulator              # View DTS logs
```

Emulator data is **in-memory** — restarting containers clears all orchestration state.

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT1_PROJECT_ENDPOINT` | Yes (unless mock) | Azure AI Foundry endpoint for classifier agent |
| `AGENT1_NAME` | Yes | Classifier agent name (`claim-assistant-agent`) |
| `AGENT2_PROJECT_ENDPOINT` | Yes (unless mock) | Azure AI Foundry endpoint for adjudicator agent |
| `AGENT2_NAME` | Yes | Adjudicator agent name (`claim-approval-agent`) |
| `AGENT3_PROJECT_ENDPOINT` | Yes (unless mock) | Azure AI Foundry endpoint for email composer agent |
| `AGENT3_NAME` | Yes | Email composer agent name (`EmailComposerAgent`) |
| `AZURE_TENANT_ID` | Yes (unless mock) | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Yes (unless mock) | Service principal client ID |
| `AZURE_CLIENT_SECRET` | Yes (unless mock) | Service principal secret |
| `AGENT_MOCK_MODE` | No | Set to `true` to skip real agent calls (default: `false`) |
| `APPROVAL_TIMEOUT_HOURS` | No | HITL timeout in hours (default: `24`) |
| `SERVICE_BUS_CONNECTION_STRING` | No | Azure Service Bus connection (only for queue-triggered claims) |
| `SERVICE_BUS_QUEUE_NAME` | No | Queue name (default: `claims-agent-inbox`) |
| `SMTP_HOST` | Yes | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | Yes | SMTP port (default: `587`) |
| `SMTP_USERNAME` | Yes | SMTP login |
| `SMTP_PASSWORD` | Yes | SMTP password (use Gmail app password) |
| `EMAIL_FROM_ADDRESS` | Yes | Sender email address |
| `EMAIL_FROM_NAME` | No | Sender display name (default: `Claims Department`) |
| `REVIEW_EMAIL_ADDRESS` | Yes | Where review notification emails are sent |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `func start` fails | Check `func --version` is 4.x and Python 3.11+ |
| Storage connection error | Ensure Azurite is running: `docker ps` |
| Orchestration stuck in Pending | Check activity errors in terminal output |
| Port already in use | Stop conflicting container: `docker stop azurite` |
| Docker not found | Start Docker Desktop |
| Agent calls failing | Set `AGENT_MOCK_MODE=true` or check Azure credentials |
| PowerShell script blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## Further Reading

- `ARCHITECTURE_AND_BEST_PRACTICES.md` — detailed architecture guide, patterns, gotchas, and production checklist
- `DEVELOPMENT_PLAN.md` — phased development roadmap
- `CLAUDE.md` — AI assistant instructions and code templates
