"""
Azure Durable Functions HITL Orchestration - Main Function App

This module defines the HTTP triggers and orchestrator for the Human-in-the-Loop
orchestration between two Azure AI Foundry agents.
"""

import azure.functions as func
import azure.durable_functions as df
from datetime import datetime, timezone, timedelta
import json
import logging
import os
import re
from pathlib import Path

from activities.agent1_activity import run_agent1_activity
from activities.notify_activity import run_notify_activity
from activities.agent2_activity import run_agent2_activity
from activities.agent3_activity import run_agent3_activity
from activities.send_email_activity import run_send_email_activity
from shared.models import ClaimRequest, Agent1Output, ApprovalDecision

# Initialize the Durable Functions app
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)

# Configuration
APPROVAL_TIMEOUT_HOURS = float(os.getenv("APPROVAL_TIMEOUT_HOURS", "24"))


def transform_servicebus_message(raw_message: dict) -> dict:
    """
    Transform incoming Service Bus message format to Agent 1 expected format.

    Incoming format (from email monitoring):
        {
            "message_id": "<PN3PPFDAF398764...>",
            "from": "Sujit Sarkar <sujit_s@pursuitsoftware.com>",
            "body_text": "Hi\r\nPls review my service claim...",
            "body_html": "...",
            "attachments": [{"filename": "...", "blob_url": "..."}]
        }

    Target format (for Agent 1):
        {
            "claim_id": "CLM-SB-20260203143000",
            "sender_email": "sujit_s@pursuitsoftware.com",
            "email_content": "Hi\r\nPls review my service claim...",
            "attachment_url": "https://..."
        }
    """
    # Generate a short claim_id using timestamp (CSB = Claim Service Bus)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    claim_id = f"CSB-{timestamp}"

    # Extract email from "Name <email>" format
    from_field = raw_message.get("from", "")
    email_match = re.search(r'<([^>]+)>', from_field)
    if email_match:
        sender_email = email_match.group(1)
    else:
        # Fallback: use the whole field if no angle brackets
        sender_email = from_field.strip()

    # Get first attachment URL (if any)
    attachments = raw_message.get("attachments", [])
    attachment_url = ""
    if attachments and len(attachments) > 0:
        attachment_url = attachments[0].get("blob_url", "")

    # Build transformed message
    transformed = {
        "claim_id": claim_id,
        "sender_email": sender_email,
        "email_content": raw_message.get("body_text", ""),
        "attachment_url": attachment_url
    }

    return transformed


def is_raw_email_format(message: dict) -> bool:
    """Check if message is in raw email format (from email monitoring) vs expected format."""
    # Raw email format has 'from' and 'body_text' fields
    # Expected format has 'claim_id' and 'email_content' fields
    return "from" in message and "body_text" in message


# =============================================================================
# HTTP Triggers
# =============================================================================

@app.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint to verify the function app is running.

    Returns:
        JSON response with health status and timestamp.
    """
    logger.info("Health check endpoint called")

    response_body = {
        "status": "healthy",
        "service": "durable-functions-hitl",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }

    return func.HttpResponse(
        body=json.dumps(response_body),
        status_code=200,
        mimetype="application/json"
    )


# =============================================================================
# Contractor State API (Clone Visualizer)
# =============================================================================

@app.route(route="contractors/state", methods=["GET"])
async def get_contractor_state(req: func.HttpRequest) -> func.HttpResponse:
    """
    Return full contractor workforce state for dashboard polling.

    Response includes all 3 agent pools, HITL counter, and global stats.
    The Clone Visualizer dashboard polls this every 500ms.

    Returns:
        200: JSON with stages, hitl, and global counters
    """
    try:
        from shared.contractor_manager import ContractorManager
        manager = ContractorManager()
        state = manager.get_all_state()

        return func.HttpResponse(
            body=json.dumps(state, default=str),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error getting contractor state: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="contractors/config", methods=["GET"])
async def get_contractor_config(req: func.HttpRequest) -> func.HttpResponse:
    """
    Return contractor pool configuration (capacity, max, names per agent).

    Returns:
        200: JSON with pool configs for each agent stage
    """
    try:
        from shared.contractor_manager import ContractorManager
        manager = ContractorManager()
        config = {}

        for agent_id, pool in manager.pools.items():
            config[agent_id] = {
                "agent_id": pool.agent_id,
                "display_name": pool.display_name,
                "capacity_per_contractor": pool.capacity,
                "max_contractors": pool.max_contractors,
                "contractor_names": [d["name"] for d in pool.contractor_defs],
                "contractor_colors": [d["color"] for d in pool.contractor_defs],
            }

        return func.HttpResponse(
            body=json.dumps(config),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error getting contractor config: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


# =============================================================================
# Dashboard & Static Pages
# =============================================================================

@app.route(route="clone-dashboard", methods=["GET"])
async def serve_clone_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """
    Serve the Clone Visualizer AI Contractor Dashboard.

    Returns:
        200: HTML dashboard page
        404: Static file not found
    """
    try:
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "clone_dashboard.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Clone Dashboard not found",
                status_code=404
            )

        html_content = html_path.read_text(encoding="utf-8")

        return func.HttpResponse(
            body=html_content,
            status_code=200,
            mimetype="text/html"
        )

    except Exception as e:
        logger.error(f"Error serving clone dashboard: {str(e)}")
        return func.HttpResponse(
            f"Error loading clone dashboard: {str(e)}",
            status_code=500
        )


@app.route(route="dashboard", methods=["GET"])
async def serve_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """
    Serve the Claims Dashboard HTML page.

    Returns:
        200: HTML dashboard page
        404: Static file not found
    """
    try:
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "dashboard.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Dashboard not found",
                status_code=404
            )

        html_content = html_path.read_text(encoding="utf-8")

        return func.HttpResponse(
            body=html_content,
            status_code=200,
            mimetype="text/html"
        )

    except Exception as e:
        logger.error(f"Error serving dashboard: {str(e)}")
        return func.HttpResponse(
            f"Error loading dashboard: {str(e)}",
            status_code=500
        )


@app.route(route="presentation", methods=["GET"])
async def serve_presentation(req: func.HttpRequest) -> func.HttpResponse:
    """
    Serve the Stakeholder Presentation HTML page.

    Returns:
        200: HTML presentation page
        404: Static file not found
    """
    try:
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "presentation.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Presentation not found",
                status_code=404
            )

        html_content = html_path.read_text(encoding="utf-8")

        return func.HttpResponse(
            body=html_content,
            status_code=200,
            mimetype="text/html"
        )

    except Exception as e:
        logger.error(f"Error serving presentation: {str(e)}")
        return func.HttpResponse(
            f"Error loading presentation: {str(e)}",
            status_code=500
        )


@app.route(route="email-composer-demo", methods=["GET"])
async def serve_email_composer_demo(req: func.HttpRequest) -> func.HttpResponse:
    """
    Serve the Email Composer Agent Demo HTML page.

    Returns:
        200: HTML demo page
        404: Static file not found
    """
    try:
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "email_composer_demo.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Email Composer Demo not found",
                status_code=404
            )

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        return func.HttpResponse(
            html_content,
            mimetype="text/html",
            status_code=200
        )

    except Exception as e:
        logger.error(f"Error serving email composer demo: {str(e)}")
        return func.HttpResponse(
            f"Error loading email composer demo: {str(e)}",
            status_code=500
        )


@app.route(route="compose-email", methods=["POST"])
async def compose_email_api(req: func.HttpRequest) -> func.HttpResponse:
    """
    API endpoint to compose an email using the Email Composer Agent (Agent 3).

    Expected JSON payload:
        {
            "claim_id": "CLM-2026-00142",
            "recipient_name": "John Smith",
            "recipient_email": "john.smith@email.com",
            "email_purpose": "Claim Approval Notification",
            "outcome_summary": "Your claim has been approved...",
            "additional_context": "Domain-specific context...",
            "config": {
                "tone": "formal",
                "length": "standard",
                "empathy": "warm",
                "call_to_action": "soft"
            }
        }

    Returns:
        200: JSON with composed email
        400: Invalid request
        500: Agent error
    """
    from shared.agent_client import invoke_email_composer
    from shared.models import Agent3Input, EmailComposerConfig

    try:
        # Parse request body
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                mimetype="application/json",
                status_code=400
            )

        # Validate required fields
        required_fields = ["claim_id", "recipient_name", "recipient_email", "email_purpose", "outcome_summary"]
        missing_fields = [f for f in required_fields if not body.get(f)]
        if missing_fields:
            return func.HttpResponse(
                json.dumps({"error": f"Missing required fields: {missing_fields}"}),
                mimetype="application/json",
                status_code=400
            )

        # Build config from request
        config_data = body.get("config", {})
        config = EmailComposerConfig(
            tone=config_data.get("tone", "formal"),
            length=config_data.get("length", "standard"),
            empathy=config_data.get("empathy", "warm"),
            call_to_action=config_data.get("call_to_action", "soft"),
            template=config_data.get("template", "default")
        )

        # Build Agent3 input
        agent3_input = Agent3Input(
            claim_id=body.get("claim_id"),
            recipient_name=body.get("recipient_name"),
            recipient_email=body.get("recipient_email"),
            email_purpose=body.get("email_purpose"),
            outcome_summary=body.get("outcome_summary"),
            additional_context=body.get("additional_context", ""),
            config=config
        )

        # Invoke Email Composer Agent (Agent 3)
        logger.info(f"Composing email for {agent3_input.claim_id} via API")
        agent3_output = invoke_email_composer(agent3_input)

        # Return composed email
        response_data = {
            "claim_id": agent3_output.claim_id,
            "email_subject": agent3_output.email_subject,
            "email_body": agent3_output.email_body,
            "recipient_name": agent3_output.recipient_name,
            "recipient_email": agent3_output.recipient_email,
            "generated_at": agent3_output.generated_at.isoformat() if agent3_output.generated_at else None
        }

        return func.HttpResponse(
            json.dumps(response_data),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logger.error(f"Error composing email: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="review/{instance_id}", methods=["GET"])
async def serve_review_ui(req: func.HttpRequest) -> func.HttpResponse:
    """
    Serve the HTML review form for a specific claim instance.

    The form pre-fills with Agent1 output and allows reviewers to
    enter/edit data before approving or rejecting the claim.

    Returns:
        200: HTML review form
        404: Static file not found
    """
    try:
        # Get the path to the static HTML file
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "review.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Review form not found",
                status_code=404
            )

        # Read and return the HTML
        html_content = html_path.read_text(encoding="utf-8")

        return func.HttpResponse(
            body=html_content,
            status_code=200,
            mimetype="text/html"
        )

    except Exception as e:
        logger.error(f"Error serving review UI: {str(e)}")
        return func.HttpResponse(
            f"Error loading review form: {str(e)}",
            status_code=500
        )


@app.route(route="claims/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_claim_orchestration(req: func.HttpRequest, client) -> func.HttpResponse:
    """
    HTTP trigger to start a new claim orchestration.

    Request Body:
        {
            "claim_id": "CLM-2026-00142",
            "email_content": "Hi, I'm submitting a claim...",
            "attachment_url": "https://storage.example.com/doc.pdf",
            "sender_email": "claimant@email.com",
            "metadata": {}  // optional
        }

    Returns:
        JSON response with instance_id and status URLs.
    """
    try:
        # Parse request body
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )

        # Validate required fields
        required_fields = ["claim_id", "email_content", "attachment_url", "sender_email"]
        missing_fields = [f for f in required_fields if not body.get(f)]
        if missing_fields:
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "missing_fields": missing_fields
                }),
                status_code=400,
                mimetype="application/json"
            )

        # Validate with Pydantic model
        try:
            claim_request = ClaimRequest.model_validate(body)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Validation error: {str(e)}"}),
                status_code=400,
                mimetype="application/json"
            )

        # Use claim_id as instance_id for deterministic tracking
        instance_id = f"claim-{claim_request.claim_id}"

        # Check if orchestration already exists
        existing = await client.get_status(instance_id)
        existing_rs = (existing.runtime_status.name if hasattr(existing.runtime_status, 'name') else str(existing.runtime_status)) if existing else None
        if existing and existing_rs in ["Running", "Pending"]:
            return func.HttpResponse(
                json.dumps({
                    "error": "Orchestration already exists",
                    "instance_id": instance_id,
                    "status": existing_rs
                }),
                status_code=409,
                mimetype="application/json"
            )

        # Start the orchestration
        await client.start_new(
            orchestration_function_name="claim_orchestrator",
            instance_id=instance_id,
            client_input=claim_request.model_dump(mode="json")
        )

        # Track email received for clone dashboard
        from shared.contractor_manager import ContractorManager
        ContractorManager().increment_email_received(claim_request.claim_id)

        logger.info(f"Started orchestration {instance_id} for claim {claim_request.claim_id}")

        # Build response with status URLs
        base_url = req.url.split("/api/")[0]
        response_body = {
            "instance_id": instance_id,
            "claim_id": claim_request.claim_id,
            "status": "Started",
            "status_url": f"{base_url}/api/claims/status/{instance_id}",
            "approval_url": f"{base_url}/api/claims/approve/{instance_id}"
        }

        return func.HttpResponse(
            body=json.dumps(response_body),
            status_code=202,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error starting orchestration: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="claims/approve/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def submit_estimate(req: func.HttpRequest, client) -> func.HttpResponse:
    """
    HTTP trigger to submit manual estimate data for a claim.

    This is a data entry step - the Claim Adjudicator Agent will make
    the actual approval/rejection decision.

    Request Body:
        {
            "reviewer": "estimator@company.com",
            "comments": "Optional notes for adjudicator",
            "claim_data": {
                "claimant": { "name": "...", "email": "...", "phone": "..." },
                "contract": { "contract_number": "...", ... },
                "vehicle": { "year": 2022, "make": "Honda", ... },
                "repair": { "facility_name": "...", "total_estimate": 750.00, ... },
                "documents": { "damage_photos": true, "claim_form": true }
            }
        }

    Returns:
        200: Success
        400: Invalid request
        404: Instance not found
        409: Instance not waiting for estimate
    """
    instance_id = req.route_params.get("instance_id")

    try:
        # Parse request body
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "invalid_json"}),
                status_code=400,
                mimetype="application/json"
            )

        # Decision defaults to "approved" (proceed to Adjudicator Agent)
        # Kept for backward compatibility - rejection path still exists but not used by UI
        decision = body.get("decision", "approved").lower()

        # Validate reviewer
        reviewer = body.get("reviewer")
        if not reviewer:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "missing_reviewer",
                    "message": "Reviewer email is required"
                }),
                status_code=400,
                mimetype="application/json"
            )

        # Check orchestration status
        status = await client.get_status(instance_id)
        if not status:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "instance_not_found",
                    "message": f"No orchestration found with ID: {instance_id}"
                }),
                status_code=404,
                mimetype="application/json"
            )

        # Check if orchestration is running and waiting for approval
        rs = status.runtime_status
        rs_name = rs.name if hasattr(rs, 'name') else str(rs)
        if rs_name != "Running":
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "orchestration_not_running",
                    "message": f"Orchestration is {rs_name}, not waiting for approval",
                    "runtime_status": rs_name
                }),
                status_code=409,
                mimetype="application/json"
            )

        # Check custom status to verify it's waiting for approval
        custom_status = status.custom_status or {}
        if isinstance(custom_status, str):
            try:
                custom_status = json.loads(custom_status)
            except (json.JSONDecodeError, TypeError):
                custom_status = {}
        current_step = custom_status.get("step") if isinstance(custom_status, dict) else None
        if current_step != "awaiting_approval":
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "not_awaiting_approval",
                    "message": f"Orchestration is at step '{current_step}', not awaiting_approval",
                    "current_step": current_step
                }),
                status_code=409,
                mimetype="application/json"
            )

        # Build approval decision payload
        approval_data = {
            "decision": decision,
            "reviewer": reviewer,
            "comments": body.get("comments", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "claim_amounts": body.get("claim_amounts"),
            "claim_data": body.get("claim_data")  # Complete claim data for Agent2
        }

        # Raise the approval event
        await client.raise_event(
            instance_id=instance_id,
            event_name="ApprovalDecision",
            event_data=approval_data
        )

        logger.info(f"Estimate submitted for {instance_id} by {reviewer}")

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "instance_id": instance_id,
                "submitted_by": reviewer,
                "message": "Estimate submitted successfully"
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error submitting estimate for {instance_id}: {str(e)}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="claims", methods=["GET"])
@app.durable_client_input(client_name="client")
async def list_claims(req: func.HttpRequest, client) -> func.HttpResponse:
    """
    HTTP trigger to list all claim orchestrations.

    Query Parameters:
        status: Filter by runtime status (Running, Completed, Failed, etc.)

    Returns:
        200: JSON array of claims with status info
    """
    try:
        # Get optional status filter and limit from query params
        status_filter = req.params.get("status")
        limit = int(req.params.get("limit", "20"))

        # Use the Durable Task HTTP API directly — the Python SDK's get_status_by()
        # is unreliable on the DTS emulator (omits recently completed/running instances).
        import urllib.request
        import urllib.parse
        dt_base = "http://localhost:7071/runtime/webhooks/durabletask/instances"
        dt_params = urllib.parse.urlencode({"instanceIdPrefix": "claim-", "top": "500", "taskHub": "testhubname"})
        dt_url = f"{dt_base}?{dt_params}"
        with urllib.request.urlopen(dt_url, timeout=15) as dt_resp:
            dt_data = json.loads(dt_resp.read().decode())

        # Convert raw DT API response to instance-like dicts
        instances = []
        for item in dt_data:
            class _Inst:
                pass
            inst = _Inst()
            inst.instance_id = item.get("instanceId", "")
            inst.runtime_status = item.get("runtimeStatus", "Unknown")
            inst.custom_status = item.get("customStatus")
            inst.created_time = item.get("createdTime")
            inst.last_updated_time = item.get("lastUpdatedTime")
            inst.output = item.get("output")
            instances.append(inst)

        claims = []
        for instance in instances:
            # runtime_status may be an enum or a string depending on storage backend
            rs = instance.runtime_status
            runtime_status = rs.name if hasattr(rs, 'name') else str(rs)

            # Apply status filter if provided
            if status_filter and runtime_status.lower() != status_filter.lower():
                continue

            # Extract claim_id from instance_id (remove "claim-" prefix)
            claim_id = instance.instance_id.replace("claim-", "", 1)

            # Get custom status — may be dict, JSON string, or None
            custom_status = instance.custom_status or {}
            if isinstance(custom_status, str):
                try:
                    custom_status = json.loads(custom_status)
                except (json.JSONDecodeError, TypeError):
                    custom_status = {}

            # Map internal step names to display names
            step = (custom_status.get("step") or "unknown") if isinstance(custom_status, dict) else "unknown"
            display_status = {
                "agent1_processing": "Classifier Agent Activated",
                "sending_notification": "Classifier Agent Activated",
                "awaiting_approval": "Awaiting Manual Estimate",
                "agent2_processing": "Adjudication Agent Activated",
                "agent3_processing": "Email Composer Agent Activated",
                "agent2_completed": "Completed",
                "completed": "Completed",
                "rejected": "Rejected",
                "timeout": "Timed Out"
            }.get(step, step.replace("_", " ").title())

            # Determine final display status based on runtime status
            if runtime_status == "Completed":
                # Check output for final status
                output = instance.output or {}
                final_status = output.get("status") or "completed"
                if final_status == "rejected":
                    display_status = "Rejected"
                elif final_status == "timeout":
                    display_status = "Timed Out"
                elif final_status == "completed":
                    # Check agent2 decision (use 'or {}' since value could be None)
                    agent2_output = output.get("agent2_output") or {}
                    decision = agent2_output.get("decision") or "APPROVED"
                    if decision == "APPROVED":
                        display_status = "Approved"
                    elif decision == "DENIED":
                        display_status = "Denied"
                    else:
                        display_status = decision.replace("_", " ").title()
            elif runtime_status == "Failed":
                display_status = "Failed"
            elif runtime_status == "Terminated":
                display_status = "Terminated"

            # Safely convert datetime (may be datetime object or string depending on storage backend)
            def safe_isoformat(dt):
                if dt is None:
                    return None
                if isinstance(dt, str):
                    return dt
                try:
                    return dt.isoformat()
                except Exception:
                    return str(dt)

            claim_info = {
                "claim_id": claim_id,
                "instance_id": instance.instance_id,
                "runtime_status": runtime_status,
                "display_status": display_status,
                "step": step,
                "created_time": safe_isoformat(instance.created_time),
                "last_updated_time": safe_isoformat(instance.last_updated_time),
                "classification": custom_status.get("classification"),
                "confidence_score": custom_status.get("confidence_score"),
                "contractor": custom_status.get("contractor"),
            }

            claims.append(claim_info)

        # Sort by created_time descending (newest first)
        claims.sort(key=lambda x: x.get("created_time") or "", reverse=True)

        total_count = len(claims)
        claims = claims[:limit]

        logger.info(f"Listed {len(claims)} of {total_count} claims (limit={limit})")

        resp = func.HttpResponse(
            json.dumps({"claims": claims, "count": len(claims), "total_count": total_count}, default=str),
            status_code=200,
            mimetype="application/json"
        )
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    except Exception as e:
        logger.error(f"Error listing claims: {str(e)}")
        resp = func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


@app.route(route="claims/status/{instance_id}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_claim_status(req: func.HttpRequest, client) -> func.HttpResponse:
    """
    HTTP trigger to get the status of a claim orchestration.

    Returns:
        200: Status JSON
        404: Instance not found
    """
    instance_id = req.route_params.get("instance_id")

    try:
        status = await client.get_status(instance_id)

        if not status:
            return func.HttpResponse(
                json.dumps({
                    "error": "instance_not_found",
                    "message": f"No orchestration found with ID: {instance_id}"
                }),
                status_code=404,
                mimetype="application/json"
            )

        # Build response with relevant status information
        rs = status.runtime_status
        rs_name = rs.name if hasattr(rs, 'name') else str(rs)

        # Safely convert datetime
        def safe_iso(dt):
            if dt is None:
                return None
            return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)

        # custom_status may be JSON string or dict
        cs = status.custom_status or {}
        if isinstance(cs, str):
            try:
                cs = json.loads(cs)
            except (json.JSONDecodeError, TypeError):
                cs = {}

        response = {
            "instance_id": instance_id,
            "runtime_status": rs_name,
            "custom_status": cs,
            "created_time": safe_iso(status.created_time),
            "last_updated_time": safe_iso(status.last_updated_time),
            "output": status.output
        }

        # Add approval URL if waiting for approval
        if isinstance(cs, dict) and cs.get("step") == "awaiting_approval":
            base_url = req.url.split("/api/")[0]
            response["approval_url"] = f"{base_url}/api/claims/approve/{instance_id}"
            response["review_url"] = f"{base_url}/api/claims/review/{instance_id}"

        return func.HttpResponse(
            json.dumps(response, default=str),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error getting status for {instance_id}: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


# =============================================================================
# Service Bus Trigger
# =============================================================================

@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%SERVICE_BUS_QUEUE_NAME%",
    connection="SERVICE_BUS_CONNECTION_STRING"
)
@app.durable_client_input(client_name="client")
async def servicebus_claim_trigger(message: func.ServiceBusMessage, client) -> None:
    """
    Service Bus trigger to start a new claim orchestration from queue message.

    Supports two message formats:

    1. Raw Email Format (from email monitoring service):
        {
            "message_id": "<PN3PPFDAF398764...>",
            "from": "Sujit Sarkar <sujit_s@pursuitsoftware.com>",
            "body_text": "Hi, Pls review my service claim...",
            "body_html": "...",
            "attachments": [{"filename": "...", "blob_url": "https://..."}]
        }

    2. Direct Format (pre-formatted):
        {
            "claim_id": "CLM-2026-00199",
            "email_content": "Subject: Claim Request\n\nDear Claims Team...",
            "attachment_url": "https://storage.blob.core.windows.net/claims/form.pdf",
            "sender_email": "claimant@email.com"
        }

    Raw email format is auto-detected and transformed to direct format.
    The message will be processed and the orchestration started.
    If the orchestration already exists and is running, the message is logged and skipped.
    """
    try:
        # Get message body
        message_body = message.get_body().decode("utf-8")
        logger.info(f"Service Bus message received: {message.message_id}")

        # Parse JSON
        try:
            body = json.loads(message_body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Service Bus message: {str(e)}")
            logger.error(f"Message body: {message_body[:500]}")
            # Message will be dead-lettered after max delivery attempts
            raise

        # Transform if in raw email format (from email monitoring)
        if is_raw_email_format(body):
            logger.info("Detected raw email format, transforming to Agent 1 format...")
            body = transform_servicebus_message(body)
            logger.info(f"Transformed message: claim_id={body.get('claim_id')}, sender={body.get('sender_email')}")

        # Validate required fields
        required_fields = ["claim_id", "email_content", "attachment_url", "sender_email"]
        missing_fields = [f for f in required_fields if not body.get(f)]
        if missing_fields:
            logger.error(f"Missing required fields in Service Bus message: {missing_fields}")
            raise ValueError(f"Missing required fields: {missing_fields}")

        # Validate with Pydantic model
        try:
            claim_request = ClaimRequest.model_validate(body)
        except Exception as e:
            logger.error(f"Validation error for Service Bus message: {str(e)}")
            raise

        # Use claim_id as instance_id for deterministic tracking
        instance_id = f"claim-{claim_request.claim_id}"

        # Check if orchestration already exists
        existing = await client.get_status(instance_id)
        existing_rs = (existing.runtime_status.name if hasattr(existing.runtime_status, 'name') else str(existing.runtime_status)) if existing else None
        if existing and existing_rs in ["Running", "Pending"]:
            logger.warning(
                f"Orchestration {instance_id} already exists with status {existing_rs}. "
                f"Skipping duplicate message."
            )
            return  # Message acknowledged, not reprocessed

        # Start the orchestration
        await client.start_new(
            orchestration_function_name="claim_orchestrator",
            instance_id=instance_id,
            client_input=claim_request.model_dump(mode="json")
        )

        # Track email received for clone dashboard
        from shared.contractor_manager import ContractorManager
        ContractorManager().increment_email_received(claim_request.claim_id)

        logger.info(
            f"Started orchestration {instance_id} for claim {claim_request.claim_id} "
            f"(triggered by Service Bus message {message.message_id})"
        )

    except Exception as e:
        logger.error(f"Error processing Service Bus message: {str(e)}")
        # Re-raise to trigger retry/dead-letter
        raise


# =============================================================================
# Orchestrator Function
# =============================================================================

@app.orchestration_trigger(context_name="context")
def claim_orchestrator(context: df.DurableOrchestrationContext):
    """
    Main orchestrator for claim processing with Human-in-the-Loop approval.

    Flow (Phase 4 - HITL):
        1. Receive claim data
        2. Call Agent1 Activity for classification
        3. Send notification for human approval
        4. Wait for approval event (with timeout)
        5. Handle approval/rejection/timeout
        6. (Phase 5) Call Agent2 if approved

    Args:
        context: Durable orchestration context

    Returns:
        Orchestration result with Agent1 output and approval decision
    """
    instance_id = context.instance_id

    # Log only on first execution (not on replay)
    if not context.is_replaying:
        logger.info(f"[{instance_id}] Orchestrator started")

    # Get input data
    input_data = context.get_input()
    claim_id = input_data.get("claim_id")
    started_at = context.current_utc_datetime.isoformat()

    # Initialize stage timestamps for timeline tracking
    stage_timestamps = {
        "received": started_at
    }

    # =========================================================================
    # Step 1: Agent1 Classification
    # =========================================================================
    # Assign to classifier contractor pool
    assign1 = yield context.call_activity("assign_contractor_activity",
        {"agent_id": "classifier", "claim_id": claim_id})
    classifier_contractor = assign1["contractor_name"]

    stage_timestamps["classifier_started"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "agent1_processing",
        "claim_id": claim_id,
        "contractor": classifier_contractor,
        "message": f"Classifying claim with {classifier_contractor}...",
        "stage_timestamps": stage_timestamps
    })

    # Prepare Agent1 input
    agent1_input = {
        "claim_id": claim_id,
        "email_content": input_data.get("email_content"),
        "attachment_url": input_data.get("attachment_url"),
        "sender_email": input_data.get("sender_email"),
        "persona_name": classifier_contractor,
        "_instance_id": instance_id
    }

    # Call Agent1 Activity
    agent1_result = yield context.call_activity("agent1_activity", agent1_input)

    # Release from classifier contractor pool
    yield context.call_activity("release_contractor_activity",
        {"agent_id": "classifier", "claim_id": claim_id})

    if not context.is_replaying:
        logger.info(f"[{instance_id}] Agent1 completed by {classifier_contractor} - Type: {agent1_result.get('classification', {}).get('claim_type')}")

    # =========================================================================
    # Step 2: Send Notification for Human Approval
    # =========================================================================
    stage_timestamps["classifier_completed"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "sending_notification",
        "claim_id": claim_id,
        "classification": agent1_result.get("classification", {}).get("claim_type"),
        "message": "Sending notification for approval...",
        "stage_timestamps": stage_timestamps
    })

    # Build notification input
    notify_input = {
        "instance_id": instance_id,
        "claim_id": claim_id,
        "approval_url": f"/api/claims/approve/{instance_id}",
        "review_url": f"/api/claims/review/{instance_id}",
        "agent1_summary": {
            "claim_type": agent1_result.get("classification", {}).get("claim_type"),
            "confidence_score": agent1_result.get("confidence_score"),
            "requires_human_review": agent1_result.get("flags", {}).get("requires_human_review", True),
            "total_estimate": agent1_result.get("extracted_info", {}).get("total_estimate")
        }
    }

    # Call Notify Activity
    notify_result = yield context.call_activity("notify_activity", notify_input)

    # =========================================================================
    # Step 3: Wait for Human Approval (with timeout)
    # =========================================================================
    # Increment HITL waiting counter
    yield context.call_activity("update_counter_activity",
        {"counter": "hitl", "action": "increment", "claim_id": claim_id})

    stage_timestamps["awaiting_started"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "awaiting_approval",
        "claim_id": claim_id,
        "classification": agent1_result.get("classification", {}).get("claim_type"),
        "confidence_score": agent1_result.get("confidence_score"),
        "message": "Waiting for manual estimate...",
        "agent1_output": agent1_result,  # Full Agent1 output for reviewer
        "stage_timestamps": stage_timestamps
    })

    if not context.is_replaying:
        logger.info(f"[{instance_id}] Waiting for approval (timeout: {APPROVAL_TIMEOUT_HOURS}h)")

    # Create timeout timer
    timeout_time = context.current_utc_datetime + timedelta(hours=APPROVAL_TIMEOUT_HOURS)
    timeout_task = context.create_timer(timeout_time)

    # Wait for approval event
    approval_task = context.wait_for_external_event("ApprovalDecision")

    # Wait for either approval or timeout
    winner = yield context.task_any([approval_task, timeout_task])

    # =========================================================================
    # Step 4: Handle Approval Decision
    # =========================================================================
    approval_decision = None
    final_status = None
    agent2_input = None
    agent2_output = None
    agent3_input = None
    agent3_output = None
    send_email_result = None

    if winner == timeout_task:
        # Timeout occurred — decrement HITL counter
        yield context.call_activity("update_counter_activity",
            {"counter": "hitl", "action": "decrement", "claim_id": claim_id})

        if not context.is_replaying:
            logger.warning(f"[{instance_id}] Approval timed out after {APPROVAL_TIMEOUT_HOURS} hours")

        stage_timestamps["timeout"] = context.current_utc_datetime.isoformat()
        context.set_custom_status({
            "step": "timeout",
            "claim_id": claim_id,
            "message": f"Approval timed out after {APPROVAL_TIMEOUT_HOURS} hours",
            "stage_timestamps": stage_timestamps
        })

        final_status = "timeout"

    else:
        # Cancel the timeout timer
        timeout_task.cancel()

        # Decrement HITL counter (approval or rejection received)
        yield context.call_activity("update_counter_activity",
            {"counter": "hitl", "action": "decrement", "claim_id": claim_id})

        # Get approval decision (may come as string or dict)
        approval_decision = approval_task.result
        if isinstance(approval_decision, str):
            approval_decision = json.loads(approval_decision)

        if approval_decision.get("decision") == "rejected":
            # Claim rejected
            if not context.is_replaying:
                logger.info(f"[{instance_id}] Claim rejected by {approval_decision.get('reviewer')}")

            stage_timestamps["approval_received"] = approval_decision.get("timestamp") or context.current_utc_datetime.isoformat()
            stage_timestamps["completed"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "rejected",
                "claim_id": claim_id,
                "reviewer": approval_decision.get("reviewer"),
                "message": "Claim rejected by reviewer",
                "stage_timestamps": stage_timestamps
            })

            final_status = "rejected"

        else:
            # Claim approved - continue to Agent2
            if not context.is_replaying:
                logger.info(f"[{instance_id}] Claim approved by {approval_decision.get('reviewer')}")

            # =========================================================================
            # Step 5: Call Agent2 for Adjudication
            # =========================================================================
            # Assign to adjudicator contractor pool
            assign2 = yield context.call_activity("assign_contractor_activity",
                {"agent_id": "adjudicator", "claim_id": claim_id})
            adjudicator_contractor = assign2["contractor_name"]

            stage_timestamps["approval_received"] = approval_decision.get("timestamp") or context.current_utc_datetime.isoformat()
            stage_timestamps["adjudicator_started"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "agent2_processing",
                "claim_id": claim_id,
                "contractor": adjudicator_contractor,
                "reviewer": approval_decision.get("reviewer"),
                "message": f"Processing claim with {adjudicator_contractor}...",
                "stage_timestamps": stage_timestamps
            })

            # Prepare Agent2 input
            agent2_activity_input = {
                "claim_id": claim_id,
                "agent1_output": agent1_result,
                "approval_decision": approval_decision,
                "persona_name": adjudicator_contractor,
                "_instance_id": instance_id
            }

            # Call Agent2 Activity
            agent2_activity_result = yield context.call_activity("agent2_activity", agent2_activity_input)

            # Release from adjudicator contractor pool
            yield context.call_activity("release_contractor_activity",
                {"agent_id": "adjudicator", "claim_id": claim_id})

            agent2_input = agent2_activity_result.get("agent2_input")
            agent2_output = agent2_activity_result.get("agent2_output")

            if not context.is_replaying:
                logger.info(f"[{instance_id}] Agent2 completed by {adjudicator_contractor} - Decision: {agent2_output.get('decision')}")

            stage_timestamps["adjudicator_completed"] = context.current_utc_datetime.isoformat()

            # =========================================================================
            # Step 6: Call Agent3 for Email Composition
            # =========================================================================
            # Assign to email_composer contractor pool
            assign3 = yield context.call_activity("assign_contractor_activity",
                {"agent_id": "email_composer", "claim_id": claim_id})
            email_composer_contractor = assign3["contractor_name"]

            stage_timestamps["email_composer_started"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "agent3_processing",
                "claim_id": claim_id,
                "contractor": email_composer_contractor,
                "decision": agent2_output.get("decision"),
                "message": f"Composing email with {email_composer_contractor}...",
                "stage_timestamps": stage_timestamps
            })

            # Prepare Agent3 input
            agent3_activity_input = {
                "claim_id": claim_id,
                "agent1_output": agent1_result,
                "agent2_output": agent2_output,
                "persona_name": email_composer_contractor,
                "_instance_id": instance_id
            }

            # Call Agent3 Activity
            agent3_activity_result = yield context.call_activity("agent3_activity", agent3_activity_input)

            # Release from email_composer contractor pool
            yield context.call_activity("release_contractor_activity",
                {"agent_id": "email_composer", "claim_id": claim_id})

            agent3_input = agent3_activity_result.get("agent3_input")
            agent3_output = agent3_activity_result.get("agent3_output")

            if not context.is_replaying:
                if agent3_output:
                    logger.info(f"[{instance_id}] Agent3 completed by {email_composer_contractor} - Subject: {agent3_output.get('email_subject')}")
                else:
                    logger.warning(f"[{instance_id}] Agent3 failed - {agent3_activity_result.get('error')}")

            stage_timestamps["email_composer_completed"] = context.current_utc_datetime.isoformat()

            # =========================================================================
            # Step 7: Send Email via SMTP
            # =========================================================================
            send_email_result = None
            if agent3_output:
                # Increment email sender counter
                yield context.call_activity("update_counter_activity",
                    {"counter": "email_sender", "action": "increment", "claim_id": claim_id})

                stage_timestamps["email_sending_started"] = context.current_utc_datetime.isoformat()
                context.set_custom_status({
                    "step": "sending_email",
                    "claim_id": claim_id,
                    "decision": agent2_output.get("decision"),
                    "message": "Sending notification email...",
                    "stage_timestamps": stage_timestamps
                })

                # Prepare send email input
                send_email_input = {
                    "claim_id": claim_id,
                    "email_subject": agent3_output.get("email_subject"),
                    "email_body": agent3_output.get("email_body"),
                    "recipient_email": agent3_output.get("recipient_email"),
                    "recipient_name": agent3_output.get("recipient_name"),
                    "send_to_review": True,  # Send to review email for approval
                    "send_to_claimant": False,  # Don't send directly to claimant yet
                    "_instance_id": instance_id
                }

                # Call Send Email Activity
                send_email_result = yield context.call_activity("send_email_activity", send_email_input)

                # Decrement email sender counter (email delivered or failed)
                yield context.call_activity("update_counter_activity",
                    {"counter": "email_sender", "action": "decrement", "claim_id": claim_id})

                if not context.is_replaying:
                    if send_email_result.get("success"):
                        logger.info(f"[{instance_id}] Email sent successfully to review address")
                    else:
                        logger.warning(f"[{instance_id}] Email sending failed: {send_email_result.get('errors')}")

                stage_timestamps["email_sending_completed"] = context.current_utc_datetime.isoformat()

            stage_timestamps["completed"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "completed",
                "claim_id": claim_id,
                "decision": agent2_output.get("decision"),
                "approved_amount": agent2_output.get("approved_amount"),
                "email_composed": agent3_output is not None,
                "email_sent": send_email_result.get("review_email_sent") if send_email_result else False,
                "message": "Processing complete",
                "stage_timestamps": stage_timestamps
            })

            final_status = "completed"

    # =========================================================================
    # Build Final Result
    # =========================================================================
    result = {
        "claim_id": claim_id,
        "status": final_status,
        "agent1_output": agent1_result,
        "approval_decision": approval_decision,
        "agent2_input": agent2_input,
        "agent2_output": agent2_output,
        "agent3_input": agent3_input,
        "agent3_output": agent3_output,
        "email_send_result": send_email_result,
        "stage_timestamps": stage_timestamps,
        "error_message": None,
        "started_at": started_at,
        "completed_at": context.current_utc_datetime.isoformat()
    }

    return result


# =============================================================================
# Activity Functions
# =============================================================================

@app.activity_trigger(input_name="activityInput")
def agent1_activity(activityInput: dict) -> dict:
    """
    Activity function wrapper for Agent1.

    This wrapper is registered with Durable Functions and delegates
    to the actual implementation in activities/agent1_activity.py.

    Args:
        activityInput: Dictionary with Agent1 input data

    Returns:
        Dictionary with Agent1 output data
    """
    return run_agent1_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def notify_activity(activityInput: dict) -> dict:
    """
    Activity function wrapper for sending notifications.

    This wrapper is registered with Durable Functions and delegates
    to the actual implementation in activities/notify_activity.py.

    Args:
        activityInput: Dictionary with notification data

    Returns:
        Dictionary with notification status
    """
    return run_notify_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def agent2_activity(activityInput: dict) -> dict:
    """
    Activity function wrapper for Agent2.

    This wrapper is registered with Durable Functions and delegates
    to the actual implementation in activities/agent2_activity.py.

    Args:
        activityInput: Dictionary with Agent2 input data

    Returns:
        Dictionary with Agent2 output data (adjudication decision)
    """
    return run_agent2_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def agent3_activity(activityInput: dict) -> dict:
    """
    Activity function wrapper for Agent3 (Email Composer).

    This wrapper is registered with Durable Functions and delegates
    to the actual implementation in activities/agent3_activity.py.

    Args:
        activityInput: Dictionary with Agent3 input data

    Returns:
        Dictionary with Agent3 output data (composed email)
    """
    return run_agent3_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def send_email_activity(activityInput: dict) -> dict:
    """
    Activity function wrapper for sending emails via SMTP.

    This wrapper is registered with Durable Functions and delegates
    to the actual implementation in activities/send_email_activity.py.

    Args:
        activityInput: Dictionary with email data (subject, body, recipient)

    Returns:
        Dictionary with email send status
    """
    return run_send_email_activity(activityInput)


# =============================================================================
# Contractor Lifecycle Activities (Clone Visualizer)
# =============================================================================

@app.activity_trigger(input_name="activityInput")
def assign_contractor_activity(activityInput: dict) -> dict:
    """
    Assign a claim to a contractor slot via first-fill.

    Input:  {"agent_id": "classifier", "claim_id": "CSB-001"}
    Output: {"contractor_name": "Alice", "queued": false}
    """
    from shared.contractor_manager import ContractorManager

    agent_id = activityInput["agent_id"]
    claim_id = activityInput["claim_id"]

    manager = ContractorManager()

    # Claim leaving "received" stage and entering classifier
    if agent_id == "classifier":
        manager.decrement_email_received(claim_id)

    contractor_name = manager.assign_job(agent_id, claim_id)

    logger.info(
        f"[Contractor] {claim_id} assigned to {contractor_name or 'QUEUE'} "
        f"at {agent_id}"
    )

    return {
        "contractor_name": contractor_name,
        "queued": contractor_name is None
    }


@app.activity_trigger(input_name="activityInput")
def release_contractor_activity(activityInput: dict) -> dict:
    """
    Release a claim's contractor slot after stage completion.

    Input:  {"agent_id": "classifier", "claim_id": "CSB-001"}
    Output: {"released": true}
    """
    from shared.contractor_manager import ContractorManager

    agent_id = activityInput["agent_id"]
    claim_id = activityInput["claim_id"]

    manager = ContractorManager()
    released = manager.complete_job(agent_id, claim_id)

    logger.info(
        f"[Contractor] {claim_id} released from {agent_id} "
        f"(success={released})"
    )

    return {"released": released}


@app.activity_trigger(input_name="activityInput")
def update_counter_activity(activityInput: dict) -> dict:
    """
    Update a non-pool counter (HITL waiting or Email Sender).

    Input:  {"counter": "hitl", "action": "increment"}
            {"counter": "email_sender", "action": "decrement"}
    Output: {"success": true}
    """
    from shared.contractor_manager import ContractorManager

    counter = activityInput["counter"]
    action = activityInput["action"]
    claim_id = activityInput.get("claim_id")

    manager = ContractorManager()

    if counter == "hitl":
        if action == "increment":
            manager.increment_hitl_waiting(claim_id)
        else:
            manager.decrement_hitl_waiting(claim_id)
    elif counter == "email_sender":
        if action == "increment":
            manager.increment_email_sending(claim_id)
        else:
            manager.decrement_email_sending(claim_id)
    elif counter == "email_received":
        if action == "increment":
            manager.increment_email_received(claim_id)
        else:
            manager.decrement_email_received(claim_id)

    logger.info(f"[Contractor] Counter {counter} {action}ed")

    return {"success": True}
