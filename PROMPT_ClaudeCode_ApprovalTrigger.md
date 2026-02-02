# Claude Code Development Prompt: Approval Trigger & UI

## Project Overview

Build the Human-in-the-Loop approval components for the Durable Functions orchestration. This includes the HTTP trigger that receives approval decisions and an optional simple approval UI.

## Component 1: Approval HTTP Trigger

### Endpoint Specification

```
POST /api/claims/approve/{instance_id}

Headers:
  Content-Type: application/json
  Authorization: Bearer <token> (optional, for production)

Request Body:
{
    "decision": "approved" | "rejected",
    "reviewer": "reviewer@company.com",
    "comments": "Optional reviewer comments",
    "reviewed_data": {
        "amount_adjusted": 1500.00,  // Optional adjustments
        "conditions": []              // Optional conditions
    }
}

Response (Success - 200):
{
    "success": true,
    "instance_id": "abc-123",
    "message": "Approval decision recorded successfully",
    "orchestration_status": "Running"
}

Response (Instance Not Found - 404):
{
    "success": false,
    "error": "instance_not_found",
    "message": "No orchestration found with instance_id: abc-123"
}

Response (Already Completed - 409):
{
    "success": false,
    "error": "orchestration_completed",
    "message": "Orchestration has already completed and cannot accept approval"
}

Response (Invalid State - 400):
{
    "success": false,
    "error": "invalid_state",
    "message": "Orchestration is not waiting for approval"
}
```

### Implementation Requirements

```python
import azure.functions as func
import azure.durable_functions as df
from datetime import datetime
import json
import logging

# The approval trigger must:

# 1. Validate the instance_id exists
# 2. Check orchestration is in "Running" state
# 3. Verify orchestration is waiting for "ApprovalDecision" event
# 4. Raise the external event with approval data
# 5. Return appropriate response

async def approve_claim(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    HTTP trigger that receives human approval decisions and wakes
    the waiting orchestration.
    
    Args:
        req: HTTP request containing approval decision
        starter: Durable Functions client binding
        
    Returns:
        HTTP response with operation result
    """
    client = df.DurableOrchestrationClient(starter)
    instance_id = req.route_params.get('instance_id')
    
    # 1. Parse and validate request body
    try:
        body = req.get_json()
        decision = body.get('decision')
        reviewer = body.get('reviewer')
        
        if decision not in ['approved', 'rejected']:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "invalid_decision"}),
                status_code=400
            )
    except ValueError:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "invalid_json"}),
            status_code=400
        )
    
    # 2. Check orchestration status
    status = await client.get_status(instance_id)
    
    if status is None:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "instance_not_found"}),
            status_code=404
        )
    
    if status.runtime_status.name in ['Completed', 'Failed', 'Terminated']:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "orchestration_completed"}),
            status_code=409
        )
    
    # 3. Raise the external event
    approval_data = {
        "decision": decision,
        "reviewer": reviewer,
        "comments": body.get('comments', ''),
        "reviewed_data": body.get('reviewed_data', {}),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await client.raise_event(
        instance_id=instance_id,
        event_name="ApprovalDecision",
        event_data=approval_data
    )
    
    # 4. Return success response
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "instance_id": instance_id,
            "message": f"Claim {decision} by {reviewer}",
            "orchestration_status": status.runtime_status.name
        }),
        status_code=200,
        mimetype="application/json"
    )
```

### Function Binding (function.json style or decorators)

```python
# Using the new Python v2 programming model
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="claims/approve/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def approve_claim(req: func.HttpRequest, client) -> func.HttpResponse:
    # Implementation here
    pass
```

## Component 2: Status Query Endpoint

### Endpoint Specification

```
GET /api/claims/status/{instance_id}

Response (200):
{
    "instance_id": "abc-123",
    "status": "Running" | "Completed" | "Failed" | "Pending" | "Terminated",
    "created_at": "2024-01-15T10:30:00Z",
    "last_updated": "2024-01-15T10:35:00Z",
    "current_step": "waiting_for_approval",
    "output": { ... },  // Only if completed
    "custom_status": {
        "claim_id": "CLM-001",
        "agent1_completed": true,
        "awaiting_approval": true,
        "agent2_completed": false
    }
}
```

### Implementation

```python
@app.route(route="claims/status/{instance_id}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_claim_status(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = req.route_params.get('instance_id')
    
    status = await client.get_status(instance_id, show_history=False)
    
    if status is None:
        return func.HttpResponse(
            json.dumps({"error": "instance_not_found"}),
            status_code=404
        )
    
    response = {
        "instance_id": instance_id,
        "status": status.runtime_status.name,
        "created_at": status.created_time.isoformat() if status.created_time else None,
        "last_updated": status.last_updated_time.isoformat() if status.last_updated_time else None,
        "custom_status": status.custom_status,
        "output": status.output if status.runtime_status.name == "Completed" else None
    }
    
    return func.HttpResponse(
        json.dumps(response, default=str),
        status_code=200,
        mimetype="application/json"
    )
```

## Component 3: Simple Approval UI (Optional)

Create a minimal HTML page that can be served or linked to for human reviewers.

### Endpoint

```
GET /api/claims/review/{instance_id}

Returns: HTML page with claim details and approve/reject buttons
```

### HTML Template

```html
<!DOCTYPE html>
<html>
<head>
    <title>Claim Review - {{claim_id}}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .claim-card { border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .section { margin: 15px 0; }
        .label { font-weight: bold; color: #555; }
        .value { margin-left: 10px; }
        .buttons { margin-top: 30px; }
        .btn { padding: 12px 30px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; margin-right: 10px; }
        .btn-approve { background-color: #28a745; color: white; }
        .btn-reject { background-color: #dc3545; color: white; }
        .btn:hover { opacity: 0.9; }
        textarea { width: 100%; height: 80px; margin-top: 10px; }
        .status { padding: 10px; border-radius: 5px; margin-top: 20px; }
        .status-success { background-color: #d4edda; color: #155724; }
        .status-error { background-color: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>Claim Review</h1>
    
    <div class="claim-card">
        <div class="section">
            <span class="label">Claim ID:</span>
            <span class="value" id="claim-id">{{claim_id}}</span>
        </div>
        <div class="section">
            <span class="label">Claimant:</span>
            <span class="value" id="claimant">{{claimant_name}}</span>
        </div>
        <div class="section">
            <span class="label">Amount Requested:</span>
            <span class="value" id="amount">${{amount}}</span>
        </div>
        <div class="section">
            <span class="label">Document:</span>
            <span class="value"><a href="{{document_url}}" target="_blank">View Document</a></span>
        </div>
        <div class="section">
            <span class="label">AI Analysis Summary:</span>
            <div class="value" id="ai-summary">{{agent1_summary}}</div>
        </div>
    </div>
    
    <div class="section">
        <span class="label">Reviewer Comments:</span>
        <textarea id="comments" placeholder="Enter your comments (optional)"></textarea>
    </div>
    
    <div class="section">
        <span class="label">Reviewer Email:</span>
        <input type="email" id="reviewer" placeholder="your.email@company.com" style="width: 300px; padding: 8px;">
    </div>
    
    <div class="buttons">
        <button class="btn btn-approve" onclick="submitDecision('approved')">✓ Approve</button>
        <button class="btn btn-reject" onclick="submitDecision('rejected')">✗ Reject</button>
    </div>
    
    <div id="status-message" class="status" style="display: none;"></div>
    
    <script>
        const instanceId = '{{instance_id}}';
        const apiBase = window.location.origin;
        
        async function submitDecision(decision) {
            const reviewer = document.getElementById('reviewer').value;
            const comments = document.getElementById('comments').value;
            
            if (!reviewer) {
                alert('Please enter your email address');
                return;
            }
            
            const statusDiv = document.getElementById('status-message');
            statusDiv.style.display = 'block';
            statusDiv.className = 'status';
            statusDiv.textContent = 'Submitting decision...';
            
            try {
                const response = await fetch(`${apiBase}/api/claims/approve/${instanceId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ decision, reviewer, comments })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    statusDiv.className = 'status status-success';
                    statusDiv.textContent = `Decision recorded: Claim ${decision}. You may close this page.`;
                    document.querySelector('.buttons').style.display = 'none';
                } else {
                    statusDiv.className = 'status status-error';
                    statusDiv.textContent = `Error: ${result.message}`;
                }
            } catch (error) {
                statusDiv.className = 'status status-error';
                statusDiv.textContent = `Error: ${error.message}`;
            }
        }
    </script>
</body>
</html>
```

### Python Endpoint to Serve UI

```python
@app.route(route="claims/review/{instance_id}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_review_page(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = req.route_params.get('instance_id')
    
    # Get orchestration status to extract claim details
    status = await client.get_status(instance_id)
    
    if status is None:
        return func.HttpResponse("Claim not found", status_code=404)
    
    if status.runtime_status.name != "Running":
        return func.HttpResponse("This claim is no longer awaiting review", status_code=400)
    
    # Extract claim data from custom_status or input
    custom_status = status.custom_status or {}
    
    # Render HTML template with claim data
    html = render_review_template(
        instance_id=instance_id,
        claim_id=custom_status.get('claim_id', 'N/A'),
        claimant_name=custom_status.get('claimant_name', 'N/A'),
        amount=custom_status.get('amount', 'N/A'),
        document_url=custom_status.get('document_url', '#'),
        agent1_summary=custom_status.get('agent1_summary', 'Analysis pending...')
    )
    
    return func.HttpResponse(html, mimetype="text/html")
```

## Component 4: Notification Helper

### Send Approval Request Notification

```python
async def send_approval_notification(
    instance_id: str,
    claim_data: dict,
    base_url: str
) -> dict:
    """
    Send notification to reviewer with approval link.
    
    This is an Activity function that can be extended to send:
    - Email (via SendGrid, Azure Communication Services)
    - Teams message (via webhook)
    - Slack message
    - Custom webhook
    
    For now, logs the approval URL.
    """
    approval_url = f"{base_url}/api/claims/review/{instance_id}"
    
    notification = {
        "instance_id": instance_id,
        "claim_id": claim_data.get("claim_id"),
        "approval_url": approval_url,
        "message": f"Claim {claim_data.get('claim_id')} requires your review",
        "sent_at": datetime.utcnow().isoformat()
    }
    
    # Log for now - extend with actual notification service
    logging.info(f"APPROVAL REQUIRED: {json.dumps(notification, indent=2)}")
    
    # Example: Send to Teams webhook
    # webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    # if webhook_url:
    #     await send_teams_notification(webhook_url, notification)
    
    return notification
```

## Security Considerations

### For Production Deployment

1. **Authentication**: Add Azure AD authentication to approval endpoints
2. **Authorization**: Verify reviewer has permission to approve claims
3. **CSRF Protection**: Add anti-forgery tokens to UI form
4. **Rate Limiting**: Prevent abuse of approval endpoints
5. **Audit Logging**: Log all approval decisions with IP, timestamp, user

### Example Auth Check

```python
def verify_reviewer_access(req: func.HttpRequest, claim_id: str) -> bool:
    """
    Verify the request comes from an authorized reviewer.
    Implement based on your auth system (Azure AD, API keys, etc.)
    """
    # Example: Check for valid API key
    api_key = req.headers.get('X-API-Key')
    if api_key and api_key == os.getenv('APPROVAL_API_KEY'):
        return True
    
    # Example: Validate Azure AD token
    # auth_header = req.headers.get('Authorization')
    # if auth_header and auth_header.startswith('Bearer '):
    #     token = auth_header[7:]
    #     return validate_azure_ad_token(token)
    
    return False
```

## Testing the Approval Flow

### Test Script

```python
import requests
import time

BASE_URL = "http://localhost:7071"

# 1. Start a new claim
start_response = requests.post(
    f"{BASE_URL}/api/claims/start",
    json={
        "claim_id": "TEST-001",
        "document_url": "https://example.com/doc.pdf",
        "claimant_name": "John Doe"
    }
)
result = start_response.json()
instance_id = result["instance_id"]
print(f"Started orchestration: {instance_id}")

# 2. Check status (should be waiting for approval)
time.sleep(5)  # Wait for Agent1 to complete
status = requests.get(f"{BASE_URL}/api/claims/status/{instance_id}").json()
print(f"Status: {status['status']}, Custom: {status.get('custom_status')}")

# 3. Submit approval
approval_response = requests.post(
    f"{BASE_URL}/api/claims/approve/{instance_id}",
    json={
        "decision": "approved",
        "reviewer": "test@example.com",
        "comments": "Looks good"
    }
)
print(f"Approval result: {approval_response.json()}")

# 4. Check final status
time.sleep(5)  # Wait for Agent2 to complete
final_status = requests.get(f"{BASE_URL}/api/claims/status/{instance_id}").json()
print(f"Final status: {final_status['status']}")
print(f"Output: {final_status.get('output')}")
```

## Deliverables

1. Approval HTTP trigger function with validation
2. Status query endpoint
3. Simple HTML review page (optional)
4. Notification activity function
5. Test script for approval flow
6. Security documentation/recommendations
