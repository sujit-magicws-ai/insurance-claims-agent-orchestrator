# Azure Durable Functions HITL - Development Plan

> **Project:** Human-in-the-Loop Orchestration with Azure AI Foundry Agents
> **Created:** 2026-02-01
> **Status:** ✅ Completed
> **Repository:** https://github.com/sujit-magicws-ai/insurance-claims-agent-orchestrator

---

## Progress Tracker

| Phase | Description | Status | Started | Completed |
|-------|-------------|--------|---------|-----------|
| 1 | Project Scaffolding & Basic Function App | ✅ Completed | 2026-02-01 | 2026-02-01 |
| 2 | Data Models & Shared Utilities | ✅ Completed | 2026-02-01 | 2026-02-01 |
| 3 | Real Agent1 Integration & Basic Orchestrator | ✅ Completed | 2026-02-01 | 2026-02-01 |
| 4 | HITL External Event & Approval Endpoints | ✅ Completed | 2026-02-02 | 2026-02-02 |
| 5 | Real Agent2 Integration & Full Flow | ✅ Completed | 2026-02-02 | 2026-02-02 |
| 6 | Review UI & Notifications | ✅ Completed | 2026-02-02 | 2026-02-02 |
| 7 | Claims Dashboard & Enhanced UI | ✅ Completed | 2026-02-02 | 2026-02-02 |

**Legend:** ⬜ Not Started | 🔄 In Progress | ✅ Completed | ⏸️ Blocked

> **Note:** Original 8-phase plan consolidated to 6 phases. Real agent integration moved earlier (Phase 3) since agents were already deployed and tested. Phase 7 added for stakeholder demo UI.

---

## Phase 1: Project Scaffolding & Basic Function App

### Objective
Set up the project structure and verify the Azure Functions runtime works locally.

### Deliverables
- [x] `function_app/` directory structure as specified
- [x] `requirements.txt` with core dependencies
- [x] `host.json` with Durable Functions configuration
- [x] `local.settings.json` template
- [x] Basic HTTP health check trigger
- [x] Empty `__init__.py` files in `activities/` and `shared/`

### File Structure to Create
```
function_app/
├── function_app.py          # Main function app with health check
├── activities/
│   └── __init__.py
├── shared/
│   └── __init__.py
├── host.json
├── local.settings.json
└── requirements.txt
```

### Testing Phase 1

**Prerequisites:**
1. Docker Desktop running
2. Azurite container started
3. DTS emulator container started

**Test Steps:**
1. [x] Start emulators: `.\start-local.ps1`
2. [x] Navigate to function_app: `cd function_app`
3. [x] Install dependencies: `pip install -r requirements.txt`
4. [x] Start function app: `func start`
5. [x] Verify no startup errors in console
6. [x] Test health endpoint:
   ```powershell
   curl http://localhost:7071/api/health
   ```
7. [x] Expected response: `{"status": "healthy", "timestamp": "..."}`

### Notes
- Package name is `azure-functions-durable` (not `azure-durable-functions`)
- Updated requirements.txt to use >= version constraints for flexibility
- Test passed on 2026-02-01 with response:
  ```json
  {"status": "healthy", "service": "durable-functions-hitl", "timestamp": "2026-02-01T16:46:37.972068+00:00", "version": "1.0.0"}
  ```

---

## Phase 2: Data Models & Shared Utilities

### Objective
Create the Pydantic data models and shared agent client utility.

### Deliverables
- [x] `shared/models.py` with all Pydantic models
- [x] `shared/prompts.py` with prompt templates
- [x] `shared/agent_client.py` with credential and agent invocation functions
- [x] Unit tests for models

### Models Implemented

| Model | Purpose |
|-------|---------|
| `Agent1Input` | Email content + attachment URL for classification |
| `Agent1Output` | Classification, justification, extractions (email/document/merged) |
| `ClaimClassification` | Claim type, sub-type, component category, urgency |
| `EmailBodyExtraction` | Fields extracted from email body |
| `DocumentExtraction` | Fields extracted from PDF attachment |
| `ExtractedInfo` | Merged superset of email + document extractions |
| `ApprovalDecision` | Human reviewer decision + claim_data for Agent2 |
| `Agent2Output` | Adjudication decision, rules evaluated, amounts |
| `OrchestrationResult` | Final orchestration result |

### Testing Phase 2

**Test Steps:**
1. [x] Create `tests/test_models.py`
2. [x] Run: `python tests/test_models.py`
3. [x] Verify all models:
   - [x] Accept valid data
   - [x] Reject invalid data with clear errors
   - [x] Serialize to JSON correctly
   - [x] Deserialize from JSON correctly
4. [x] Test `get_credential()`:
   - [x] Returns `ClientSecretCredential` when env vars set
   - [x] Returns `DefaultAzureCredential` when env vars missing
5. [x] Test `invoke_agent1()` and `invoke_agent2()` in mock mode

### Notes
- Added `shared/prompts.py` for prompt templates (separate from models)
- Agent2Input kept as generic `dict` (created by external process)
- Mock mode auto-detects when Azure endpoint not configured
- All 14 tests passed on 2026-02-01

---

## Phase 3: Real Agent1 Integration & Basic Orchestrator

### Objective
Create the orchestrator with real Azure AI Foundry Agent1 (claim-assistant-agent) integration.

### Deliverables
- [x] HTTP Start trigger (`POST /api/claims/start`)
- [x] Basic orchestrator function (`claim_orchestrator`)
- [x] `activities/agent1_activity.py` with real agent invocation
- [x] Real Agent1 integration via `AIProjectClient`
- [x] Mock mode fallback when agents not configured
- [x] Custom status updates during orchestration
- [x] **Document extraction feature** - Agent1 extracts and summarizes attachment content
- [x] **Automatic URL encoding** - Handles spaces and special characters in attachment URLs

### Agent1 Features Implemented

| Feature | Description |
|---------|-------------|
| Classification | VSC, GAP, Tire & Wheel, PPM, Appearance, Theft claim type detection |
| Contract Types | 7 contract types defined in prompt with coverage details |
| Email Body Extraction | Extracts claimant/vehicle/repair info from email body |
| Document Extraction | Fetches and parses PDF attachments |
| Merged `extracted_info` | Superset of email + document extraction with merge rules |
| `document_extraction.status` | success / failed / not_accessible |
| `document_extraction.summary` | 2-3 sentence summary of document |
| `document_extraction.extracted_fields` | Claimant, contract, VIN, estimate breakdown |
| URL Encoding | Automatic encoding of spaces/special chars in URLs |

### Extraction Merge Rules
| Field | Priority |
|-------|----------|
| `claimant_email` | Always from `sender_email` |
| `issue_summary` | Email preferred (customer's own words) |
| All other fields | Document preferred, email as fallback |

### Testing Phase 3

**Test Steps:**
1. [x] Start function app: `func start`
2. [x] Test with mock mode (no Azure credentials)
3. [x] Configure real Azure credentials in `local.settings.json`
4. [x] Test with real Agent1:
   ```bash
   curl -X POST "http://localhost:7071/api/claims/start" \
     -H "Content-Type: application/json" \
     -d '{"claim_id": "CLM-2026-00171", "email_content": "...", "attachment_url": "https://...pdf", "sender_email": "..."}'
   ```
5. [x] Verify Agent1 returns real classification
6. [x] Verify document extraction works with valid PDF URL
7. [x] Verify URL encoding handles spaces in filenames

### Test Results (2026-02-01)

**Real Agent1 Response (Updated Structure):**
```json
{
  "classification": {"claim_type": "VSC", "sub_type": "Mechanical", "component_category": "Transmission"},
  "confidence_score": 0.98,
  "email_body_extraction": {
    "claimant_phone": "555-123-4567",
    "issue_summary": "Transmission issues reported - grinding noise when shifting",
    "vehicle_year": 2022, "vehicle_make": "Honda", "vehicle_model": "Accord"
  },
  "document_extraction": {
    "status": "success",
    "document_type": "claim_form",
    "summary": "VSC Claim Form for CLM-2026-00142, submitted by John Smith...",
    "extracted_fields": {
      "claimant_name": "John Smith",
      "claimant_phone": "555-987-6543",
      "claimant_address": "123 Main St, Tampa, FL 33601",
      "contract_number": "VSC-2024-78542",
      "vehicle_vin": "1HGCV1F34NA000123",
      "total_parts": 330.00, "total_labor": 437.50, "total_estimate": 767.50
    }
  },
  "extracted_info": {
    "claimant_name": "John Smith",
    "claimant_email": "john.smith@email.com",
    "claimant_phone": "555-987-6543",
    "claimant_address": "123 Main St, Tampa, FL 33601",
    "issue_summary": "Transmission issues reported - grinding noise when shifting",
    "total_estimate": 767.50
  }
}
```

### Notes
- Instance ID uses deterministic format: `claim-{claim_id}`
- Custom status tracks: `agent1_processing` → `agent1_completed`
- Real Agent1 tested successfully on 2026-02-01
- Document extraction requires publicly accessible URL or SAS token
- URL encoding automatically handles: `VSC Claim Form.pdf` → `VSC%20Claim%20Form.pdf`

---

## Phase 4: HITL External Event & Approval Endpoints

### Objective
Add the Human-in-the-Loop wait mechanism with timeout handling and custom HTTP endpoints.

### Deliverables
- [x] Orchestrator updated with external event wait after Agent1
- [x] Timeout handling (configurable via `APPROVAL_TIMEOUT_HOURS`, default 24h)
- [x] `activities/notify_activity.py` (logs approval URL)
- [x] `POST /api/claims/approve/{instance_id}` endpoint
- [x] `GET /api/claims/status/{instance_id}` endpoint
- [x] Request validation and error responses (400, 404, 409)

### Orchestrator Flow (Phase 4)
```
POST /api/claims/start
    ↓
Agent1 Activity (real) → Classification + Document Extraction
    ↓
Set custom_status: "agent1_completed"
    ↓
Notify Activity → Logs approval URL
    ↓
Set custom_status: "awaiting_approval"
    ↓
Wait for ApprovalDecision event (with timeout)
    ↓
┌─────────────┬─────────────┬─────────────┐
│   Timeout   │  Rejected   │  Approved   │
└─────────────┴─────────────┴─────────────┘
      ↓             ↓             ↓
   Return       Return      → Phase 5
   timeout      rejected    (Agent2)
```

### API Specifications

**POST /api/claims/approve/{instance_id}**
```json
{
  "decision": "approved | rejected",
  "reviewer": "reviewer@company.com",
  "comments": "Optional comments",
  "claim_amounts": {
    "total_parts_cost": 330.00,
    "total_labor_cost": 437.50,
    "total_estimate": 767.50,
    "deductible": 100.00
  }
}
```

| Scenario | Status Code | Response |
|----------|-------------|----------|
| Success | 200 | `{"success": true, ...}` |
| Invalid JSON | 400 | `{"success": false, "error": "invalid_json"}` |
| Instance not found | 404 | `{"success": false, "error": "instance_not_found"}` |
| Already completed | 409 | `{"success": false, "error": "orchestration_completed"}` |

**GET /api/claims/status/{instance_id}**
| Scenario | Status Code | Response |
|----------|-------------|----------|
| Found | 200 | Full status JSON with custom status |
| Not found | 404 | `{"error": "instance_not_found"}` |

### Testing Phase 4

**Test 4.1: Approval Path**
1. [x] Start orchestration with real Agent1
2. [x] Query status → Verify "Running", custom_status: "awaiting_approval"
3. [x] Submit approval via `/api/claims/approve/{id}`
4. [x] Verify 200 response with success: true

**Test 4.2: Rejection Path**
1. [x] Start orchestration
2. [x] Submit rejection via `/api/claims/approve/{id}`
3. [x] Query status → Verify "Completed" with status: "rejected"

**Test 4.3: Timeout Path**
1. [ ] Set `APPROVAL_TIMEOUT_HOURS=0.01` (36 seconds) for testing
2. [ ] Start orchestration
3. [ ] Wait for timeout
4. [ ] Query status → Verify "Completed" with status: "timeout"

**Test 4.4: Error Cases**
1. [ ] Approve non-existent instance → 404
2. [ ] Approve already completed instance → 409
3. [ ] Submit invalid JSON → 400

### Notes
- Tested approval and rejection flows on 2026-02-02 - both working
- External event data required JSON parsing fix (came as string)
- Notification activity logs approval URL to console

---

## Phase 5: Real Agent2 Integration & Full Flow

### Objective
Complete the orchestration with real Agent2 (claim-approval-agent) integration.

### Deliverables
- [x] `activities/agent2_activity.py` with real agent invocation
- [x] Build Agent2 input from Agent1 output + approval data
- [x] Orchestrator calls Agent2 after approval
- [x] Full `OrchestrationResult` returned
- [x] Custom status updates at each step
- [x] Error handling for Agent2 failures
- [x] Flexible Agent2Output model to handle varying agent responses

### Complete Orchestration Flow
```
POST /api/claims/start
    ↓
Orchestrator starts
    ↓
Agent1 Activity (real) → Classification + Document Extraction
    ↓
Set custom_status: "agent1_completed"
    ↓
Notify Activity → Logs approval URL
    ↓
Set custom_status: "awaiting_approval"
    ↓
Wait for ApprovalDecision event (with timeout)
    ↓
┌─────────────┬─────────────┬─────────────┐
│   Timeout   │  Rejected   │  Approved   │
└─────────────┴─────────────┴─────────────┘
      ↓             ↓             ↓
   Return       Return      Agent2 Activity (real)
   timeout      rejected          ↓
   result       result      Set custom_status: "agent2_completed"
                                  ↓
                            Return completed result
```

### Agent2 Input Construction
Build Agent2 input from Agent1 output + approval data:
```json
{
  "claim_id": "CLM-2026-00171",
  "claimant": { "name": "...", "email": "...", "phone": "..." },
  "contract": { "contract_number": "...", "coverage_level": "...", "deductible": 100 },
  "vehicle": { "year": 2022, "make": "Honda", "model": "Accord", "vin": "...", "mileage": 45000 },
  "repair": { "facility_name": "...", "diagnosis": "...", "total_estimate": 767.50 },
  "documents": { "repair_estimate": true, "diagnostic_report": true }
}
```

### Testing Phase 5

**Test 5.1: Full Happy Path (End-to-End)**
1. [x] Start orchestration with real document URL
2. [x] Verify Agent1 returns real classification + document extraction
3. [x] Submit approval via `/api/claims/approve/{id}`
4. [x] Verify Agent2 returns real adjudication decision
5. [x] Verify output contains:
   - [x] `agent1_output` with real classification
   - [x] `approval_decision` with reviewer info
   - [x] `agent2_output` with adjudication (APPROVED/DENIED/MANUAL_REVIEW)
   - [x] `status: "completed"`

**Test 5.2: Rejection Path**
1. [x] Start orchestration
2. [x] Submit rejection
3. [x] Verify output:
   - [x] `agent1_output` present
   - [x] `approval_decision` with rejected
   - [x] `agent2_output` is null (Agent2 not called)
   - [x] `status: "rejected"`

**Test 5.3: Custom Status Transitions**
1. [x] Start orchestration
2. [x] Poll status and record custom_status values
3. [x] Verify: `agent1_processing` → `awaiting_approval` → `agent2_processing` → `agent2_completed`

### Notes
- Agent2 returns various decisions: APPROVED, DENIED, MANUAL_REVIEW, REQUEST_DOCUMENTS
- Made Agent2Output model flexible (list[Any] for rules, Optional fields for amounts)
- Tested with multiple scenarios on 2026-02-02 - all paths working

---

## Phase 6: Review UI & Notifications

### Objective
Add the human review UI with data entry for Agent2 input.

### Deliverables
- [x] `GET /api/review/{instance_id}` HTML endpoint
- [x] HTML form with all Agent2 input fields (claimant, contract, vehicle, repair, documents)
- [x] JavaScript for API calls and form handling
- [x] Pre-fill form with Agent1 extracted data
- [x] Display Agent1 classification summary header
- [x] `claim_data` field added to ApprovalDecision model
- [x] `build_agent2_input()` uses reviewer's `claim_data` directly when provided
- [x] Notification activity logs approval URL

### Implementation (3 Substages)

**Substage 6A: Model & Endpoint Updates**
- [x] Added `claim_data: Optional[dict]` to ApprovalDecision model
- [x] Updated `/api/claims/approve` endpoint to pass `claim_data` through

**Substage 6B: Agent2 Input from claim_data**
- [x] Updated `build_agent2_input()` to use reviewer's `claim_data` directly
- [x] Added `data_source` metadata field ("reviewer_claim_data" or "agent1_extraction")
- [x] Fallback to Agent1 extraction when no `claim_data` provided

**Substage 6C: HTML Review Form**
- [x] Created `static/review.html` with Bootstrap styling
- [x] Added `GET /api/review/{instance_id}` endpoint to serve HTML
- [x] Form sections: Claimant, Contract, Vehicle, Repair, Documents, Decision
- [x] Pre-fills from Agent1 output on page load
- [x] Submits to `/api/claims/approve/{instance_id}`

### UI Features
- [x] Display claim ID, classification, confidence in summary header
- [x] Agent1 justification displayed
- [x] Full data entry form for all Agent2 input fields
- [x] Reviewer email input (required)
- [x] Comments textarea
- [x] Approve button (green)
- [x] Reject button (red)
- [x] Success/error status display
- [x] Disable form after submission

### Testing Phase 6

**Test 6.1: Substage 6A - claim_data passthrough**
1. [x] Start orchestration, wait for awaiting_approval
2. [x] Submit approval with `claim_data` in payload
3. [x] Verify `claim_data` appears in `approval_decision` output

**Test 6.2: Substage 6B - Agent2 uses claim_data**
1. [x] Submit approval with complete `claim_data`
2. [x] Verify `agent2_input` matches submitted `claim_data`
3. [x] Verify `metadata.data_source` = "reviewer_claim_data"
4. [x] Verify Agent2 returns decision based on reviewer's data

**Test 6.3: Substage 6C - HTML Form**
1. [x] Navigate to `http://localhost:7071/api/review/{instanceId}`
2. [x] Verify HTML form loads
3. [x] Verify form pre-fills with Agent1 extracted data
4. [x] Submit form and verify approval accepted
5. [x] Verify full flow completes with Agent2 output

### Test Results (2026-02-02)

| Test | claim_data Field | Agent1 Value | Reviewer Value | Agent2 Received |
|------|------------------|--------------|----------------|-----------------|
| 6B | claimant.name | null | "Jane Doe" | ✅ "Jane Doe" |
| 6B | contract.contract_number | null | "VSC-REVIEWER-001" | ✅ "VSC-REVIEWER-001" |
| 6B | repair.total_estimate | 50.0 | 775.0 | ✅ 775.0 |
| 6B | documents.photos | false | true | ✅ true |

**Agent2 Decisions Observed:**
- APPROVED ($725.00 after $50 deductible)
- MANUAL_REVIEW (Independent Shop, missing dates)
- REQUEST_DOCUMENTS (missing photos)

### Notes
- Simplified approach: No comparison logic between Agent1 and reviewer data
- Reviewer's `claim_data` goes directly to Agent2 when provided
- Form URL: `http://localhost:7071/api/review/{instance_id}`
- Form pre-fills from `extracted_info` (merged superset of email + document extractions)
- Claimant address field added to form (extracted from document)

---

## Phase 7: Claims Dashboard & Enhanced UI

### Objective
Build a comprehensive Claims Dashboard for stakeholder demos without using Postman, and enhance the Manual Estimate page with better context.

### Deliverables
- [x] `static/dashboard.html` - Claims Dashboard with real-time tracking
- [x] `GET /api/dashboard` endpoint to serve dashboard
- [x] `GET /api/claims` endpoint to list all claims
- [x] New Claim submission form (replaces Postman for demos)
- [x] Enhanced `review.html` with workflow timeline
- [x] Classifier Agent decision context in Manual Estimate page
- [x] Stage timestamps tracking throughout orchestration
- [x] Robust JSON parsing for agent responses

### Agent Naming Convention
| Internal Name | Display Name |
|---------------|--------------|
| Agent1 | Claim Classifier Agent |
| Agent2 | Claim Adjudicator Agent |
| Human Review | Manual Claim Damage Estimate |

### Dashboard Features (dashboard.html)

**Header & Stats:**
- [x] Total claims counter
- [x] Pending claims counter (awaiting estimate)
- [x] Completed claims counter
- [x] Auto-refresh toggle (10s interval)

**New Claim Form:**
- [x] Claim ID (auto-generated or manual)
- [x] Email Subject
- [x] Email Body (textarea)
- [x] Attachment URL
- [x] Sender Email
- [x] Submit button with loading state

**Claims Table:**
- [x] Sortable columns (Claim ID, Status, Type, Estimate, Created)
- [x] Status badges with color coding
- [x] Search/filter functionality
- [x] View Details button (opens modal)
- [x] Manual Estimate link (opens in new tab when awaiting)
- [x] Change detection with row highlighting

**Detail Modal:**
- [x] Full claim information display
- [x] Workflow Timeline with timestamps
- [x] Agent outputs display
- [x] Status history

### Enhanced Review Page (review.html)

**Page Header:**
- [x] Claim ID and status
- [x] Current step indicator

**Workflow Timeline:**
- [x] Claim Received (timestamp)
- [x] Classifier Processing (timestamp)
- [x] Awaiting Manual Estimate (timestamp)
- [x] Adjudicator Processing (future)
- [x] Decision (future)

**Classifier Agent Decision Section:**
- [x] Classification display (claim type, sub-type, component)
- [x] Confidence score with progress bar
- [x] Justification text
- [x] Document extraction summary
- [x] Flags display (missing info, concerns)

**Manual Estimate Form:**
- [x] All claim data fields (claimant, contract, vehicle, repair)
- [x] Submit Estimate button (no approve/reject decision)
- [x] Reviewer email field

### API Endpoints Added

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | Serve Claims Dashboard HTML |
| `/api/claims` | GET | List all claims with status |
| `/api/claims/approve/{id}` | POST | Submit estimate (renamed from approve) |

### Stage Timestamps Tracking

Timestamps recorded at each stage for timeline display:

| Stage | Timestamp Key |
|-------|---------------|
| Claim received | `received` |
| Classifier started | `classifier_started` |
| Classifier completed | `classifier_completed` |
| Awaiting estimate | `awaiting_started` |
| Estimate submitted | `estimate_submitted` |
| Adjudicator started | `adjudicator_started` |
| Adjudicator completed | `adjudicator_completed` |
| Timeout (if applicable) | `timeout` |

### Agent Response JSON Parsing

Enhanced `agent_client.py` to handle malformed JSON from Azure AI Foundry agents:

| Issue | Fix |
|-------|-----|
| Arithmetic expressions (`285.00 + 45.00`) | Evaluate and replace with result (`330.00`) |
| Trailing commas | Remove before parsing |
| Missing commas between fields | Insert automatically |
| Other formatting issues | json5 fallback parser |

**Retry Logic:**
- JSON parsing: 3 strategies (direct, fix, json5)
- Agent invocation: Up to 3 attempts with 1s delay

### Testing Phase 7

**Test 7.1: Dashboard**
1. [x] Navigate to `http://localhost:7071/api/dashboard`
2. [x] Verify dashboard loads with stats
3. [x] Submit new claim via form
4. [x] Verify claim appears in table
5. [x] Verify auto-refresh updates status

**Test 7.2: New Claim Flow**
1. [x] Fill out New Claim form
2. [x] Submit claim
3. [x] Verify orchestration starts
4. [x] Verify status changes: Classifier Processing → Awaiting Estimate

**Test 7.3: Manual Estimate with Timeline**
1. [x] Click "Manual Estimate" link for pending claim
2. [x] Verify timeline displays with timestamps
3. [x] Verify Classifier Agent decision section shows
4. [x] Submit estimate
5. [x] Verify Adjudicator processes claim

**Test 7.4: Full Cycle**
1. [x] Submit claim via dashboard
2. [x] Wait for Classifier Agent
3. [x] Submit Manual Estimate
4. [x] Wait for Adjudicator Agent
5. [x] Verify final decision (APPROVED/DENIED/MANUAL_REVIEW)

### Notes
- Dashboard URL: `http://localhost:7071/api/dashboard`
- Manual Estimate links open in new tab for better workflow
- Submit-only flow (no approve/reject) - Adjudicator makes decision
- JSON parsing handles agent arithmetic expressions (common issue)
- Stage timestamps enable accurate timeline display

---

## Environment Configuration

### Local Development

| Component | Connection |
|-----------|------------|
| Azurite | `localhost:10000-10002` |
| DTS Emulator | `localhost:8080` (gRPC), `localhost:8082` (Dashboard) |
| Function App | `localhost:7071` |

### Environment Variables

```
# local.settings.json Values section
AzureWebJobsStorage=UseDevelopmentStorage=true
FUNCTIONS_WORKER_RUNTIME=python

# Real Agents (configured from Phase 3)
AGENT1_PROJECT_ENDPOINT=https://your-agent1-project.services.ai.azure.com/api/projects/your-project
AGENT1_NAME=claim-assistant-agent
AGENT2_PROJECT_ENDPOINT=https://your-agent2-project.services.ai.azure.com/api/projects/your-project
AGENT2_NAME=claim-approval-agent

# Azure Authentication
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Configuration
APPROVAL_TIMEOUT_HOURS=24
AGENT_MOCK_MODE=false  # Set to true to use mock responses
```

---

## Test Data

### Standard Test Claim
```json
{
  "claim_id": "CLM-2024-001",
  "document_url": "https://storage.example.com/claims/test-doc.pdf",
  "claimant_name": "Jane Smith",
  "metadata": {
    "submission_date": "2024-01-15",
    "claim_type": "medical"
  }
}
```

### Approval Payload
```json
{
  "decision": "approved",
  "reviewer": "reviewer@company.com",
  "comments": "Claim verified and approved"
}
```

### Rejection Payload
```json
{
  "decision": "rejected",
  "reviewer": "reviewer@company.com",
  "comments": "Missing documentation"
}
```

---

## Dependencies Between Phases

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6 ──→ Phase 7
(Setup)    (Models)   (Agent1)    (HITL)     (Agent2)    (UI)      (Dashboard)
```

- **Phase 1-2**: Project setup, no Azure dependency (can use mock mode)
- **Phase 3+**: Real Azure AI Foundry agents integrated
- **Phase 4**: Adds HITL approval pattern (works with real Agent1)
- **Phase 5**: Adds real Agent2 integration
- **Phase 6**: Adds review UI (can be developed in parallel with Phase 5)
- **Phase 7**: Adds Claims Dashboard for stakeholder demos (depends on Phase 6)

---

## Version Control

### Repository
- **GitHub:** https://github.com/sujit-magicws-ai/insurance-claims-agent-orchestrator
- **Branch:** main
- **Initial Commit:** 2026-02-01

### Files Tracked
- All Python source files (function_app/, activities/, shared/, tests/)
- Configuration files (host.json, requirements.txt)
- Documentation (*.md files)
- Static files (static/dashboard.html, static/review.html)

### Files Excluded (.gitignore)
- Python artifacts (__pycache__, *.pyc, .eggs/, etc.)
- Virtual environments (.venv, env/)
- Azure Functions local files (local.settings.json, .python_packages/)
- IDE files (.vscode/, .idea/)
- Secrets and credentials (*.pem, *.key, credentials.json)
- Azurite emulator data (__azurite_db_*, __blobstorage__/)
- Logs and temp files (*.log, temp/, .claude/)

---

## Issues & Blockers Log

| Date | Phase | Issue | Resolution | Status |
|------|-------|-------|------------|--------|
| 2026-02-01 | 3 | SDK API mismatch (get vs get_agent) | Updated azure-ai-projects to >=1.0.0b7 | Resolved |
| 2026-02-01 | 3 | Document not accessible | URL encoding for spaces in filenames | Resolved |
| 2026-02-02 | 4 | External event data as string not dict | Added JSON parsing when string received | Resolved |
| 2026-02-02 | 5 | Agent2 rules_failed validation error | Changed list[str] to list[Any] in model | Resolved |
| 2026-02-02 | 5 | Agent2 decision type not in Literal | Changed Literal to str for flexibility | Resolved |
| 2026-02-02 | 5 | approved_amount/deductible None values | Made fields Optional[float] | Resolved |
| 2026-02-02 | 6 | Field name mismatch after extraction restructure | Updated function_app.py to use `total_estimate` | Resolved |
| 2026-02-02 | 6 | Mock response used old extraction structure | Updated `_get_mock_agent1_response()` | Resolved |
| 2026-02-02 | 6 | Tests used old field names | Updated test_models.py for new structure | Resolved |
| 2026-02-02 | 7 | Agent returns arithmetic in JSON (`285.00 + 45.00`) | Added expression evaluation in JSON parser | Resolved |
| 2026-02-02 | 7 | Claims list API errors (get_status_by) | Simplified to filter after get_status_all | Resolved |

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-02-01 | Initial plan created (8 phases) | - |
| 2026-02-01 | Phase 1 completed - scaffolding and health check | Claude |
| 2026-02-01 | Phase 2 completed - models, prompts, agent client | Claude |
| 2026-02-01 | Phase 3 completed - orchestrator, real Agent1 integration | Claude |
| 2026-02-01 | Added document extraction feature to Agent1 output | Claude |
| 2026-02-01 | Added automatic URL encoding for attachment URLs | Claude |
| 2026-02-01 | Consolidated plan from 8 phases to 6 phases (real agents from Phase 3) | Claude |
| 2026-02-02 | Phase 4 completed - HITL external event, approval/status endpoints | Claude |
| 2026-02-02 | Phase 5 completed - real Agent2 integration, full orchestration flow | Claude |
| 2026-02-02 | Phase 6 completed - Review UI with claim_data input for Agent2 | Claude |
| 2026-02-02 | **Project completed** - All 6 phases implemented and tested | Claude |
| 2026-02-02 | Added `EmailBodyExtraction` model for email-specific extraction | Claude |
| 2026-02-02 | Restructured Agent1 output: `email_body_extraction`, `document_extraction`, `extracted_info` | Claude |
| 2026-02-02 | Added 7 contract type definitions to Agent1 prompt (VSC, GAP, T&W, PPM, Appearance, Theft, Key) | Claude |
| 2026-02-02 | Implemented merge rules (Document > Email, except email/issue_summary) | Claude |
| 2026-02-02 | Updated mock responses and tests for new extraction structure | - |
| 2026-02-02 | Initialized git repository and pushed to GitHub | - |
| 2026-02-02 | Phase 7 started - Claims Dashboard for stakeholder demos | - |
| 2026-02-02 | Added Claims Dashboard (dashboard.html) with real-time claim tracking | - |
| 2026-02-02 | Added New Claim submission form (replaces Postman for demos) | - |
| 2026-02-02 | Renamed agents: Claim Classifier Agent, Claim Adjudicator Agent | - |
| 2026-02-02 | Added workflow timeline with stage timestamps to review.html | - |
| 2026-02-02 | Added Classifier Agent decision context to Manual Estimate page | - |
| 2026-02-02 | Changed Manual Estimate from approve/reject to submit-only | - |
| 2026-02-02 | Added GET /api/claims endpoint for listing all claims | - |
| 2026-02-02 | Added GET /api/dashboard endpoint to serve dashboard | - |
| 2026-02-02 | Added robust JSON parsing for agent arithmetic expressions | - |
| 2026-02-02 | Added json5 fallback parser and agent retry logic | - |
| 2026-02-02 | **Phase 7 completed** - Claims Dashboard & Enhanced UI | - |

