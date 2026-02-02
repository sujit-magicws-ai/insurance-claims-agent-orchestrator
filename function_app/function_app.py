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
from pathlib import Path

from activities.agent1_activity import run_agent1_activity
from activities.notify_activity import run_notify_activity
from activities.agent2_activity import run_agent2_activity
from activities.agent3_activity import run_agent3_activity
from shared.models import ClaimRequest, Agent1Output, ApprovalDecision

# Initialize the Durable Functions app
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)

# Configuration
APPROVAL_TIMEOUT_HOURS = float(os.getenv("APPROVAL_TIMEOUT_HOURS", "24"))


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
        if existing and existing.runtime_status.name in ["Running", "Pending"]:
            return func.HttpResponse(
                json.dumps({
                    "error": "Orchestration already exists",
                    "instance_id": instance_id,
                    "status": existing.runtime_status.name
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
        if status.runtime_status.name != "Running":
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "orchestration_not_running",
                    "message": f"Orchestration is {status.runtime_status.name}, not waiting for approval",
                    "runtime_status": status.runtime_status.name
                }),
                status_code=409,
                mimetype="application/json"
            )

        # Check custom status to verify it's waiting for approval
        custom_status = status.custom_status or {}
        if custom_status.get("step") != "awaiting_approval":
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "not_awaiting_approval",
                    "message": f"Orchestration is at step '{custom_status.get('step')}', not awaiting_approval",
                    "current_step": custom_status.get("step")
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
        # Get optional status filter from query params
        status_filter = req.params.get("status")

        # Query all orchestration instances and filter by prefix
        # The SDK's get_status_by returns a list of DurableOrchestrationStatus
        all_instances = await client.get_status_by()

        # Filter to only claim instances (start with "claim-")
        instances = [inst for inst in all_instances if inst.instance_id.startswith("claim-")]

        claims = []
        for instance in instances:
            # Apply status filter if provided
            if status_filter and instance.runtime_status.name.lower() != status_filter.lower():
                continue

            # Extract claim_id from instance_id (remove "claim-" prefix)
            claim_id = instance.instance_id.replace("claim-", "", 1)

            # Get custom status for step info
            custom_status = instance.custom_status or {}

            # Map internal step names to display names
            step = custom_status.get("step") or "unknown"
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
            runtime_status = instance.runtime_status.name
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

            claim_info = {
                "claim_id": claim_id,
                "instance_id": instance.instance_id,
                "runtime_status": runtime_status,
                "display_status": display_status,
                "step": step,
                "created_time": instance.created_time.isoformat() if instance.created_time else None,
                "last_updated_time": instance.last_updated_time.isoformat() if instance.last_updated_time else None,
                "classification": custom_status.get("classification"),
                "confidence_score": custom_status.get("confidence_score")
            }

            claims.append(claim_info)

        # Sort by created_time descending (newest first)
        claims.sort(key=lambda x: x.get("created_time") or "", reverse=True)

        logger.info(f"Listed {len(claims)} claims")

        return func.HttpResponse(
            json.dumps({"claims": claims, "count": len(claims)}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error listing claims: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )


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
        response = {
            "instance_id": instance_id,
            "runtime_status": status.runtime_status.name,
            "custom_status": status.custom_status,
            "created_time": status.created_time.isoformat() if status.created_time else None,
            "last_updated_time": status.last_updated_time.isoformat() if status.last_updated_time else None,
            "output": status.output
        }

        # Add approval URL if waiting for approval
        if status.custom_status and status.custom_status.get("step") == "awaiting_approval":
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

    Expected Message Format (JSON):
        {
            "claim_id": "CLM-2026-00199",
            "email_content": "Subject: Claim Request\n\nDear Claims Team...",
            "attachment_url": "https://storage.blob.core.windows.net/claims/form.pdf",
            "sender_email": "claimant@email.com",
            "metadata": {}  // optional
        }

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
        if existing and existing.runtime_status.name in ["Running", "Pending"]:
            logger.warning(
                f"Orchestration {instance_id} already exists with status {existing.runtime_status.name}. "
                f"Skipping duplicate message."
            )
            return  # Message acknowledged, not reprocessed

        # Start the orchestration
        await client.start_new(
            orchestration_function_name="claim_orchestrator",
            instance_id=instance_id,
            client_input=claim_request.model_dump(mode="json")
        )

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
    stage_timestamps["classifier_started"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "agent1_processing",
        "claim_id": claim_id,
        "message": "Classifying claim with Claim Classifier Agent...",
        "stage_timestamps": stage_timestamps
    })

    # Prepare Agent1 input
    agent1_input = {
        "claim_id": claim_id,
        "email_content": input_data.get("email_content"),
        "attachment_url": input_data.get("attachment_url"),
        "sender_email": input_data.get("sender_email"),
        "_instance_id": instance_id
    }

    # Call Agent1 Activity
    agent1_result = yield context.call_activity("agent1_activity", agent1_input)

    if not context.is_replaying:
        logger.info(f"[{instance_id}] Agent1 completed - Type: {agent1_result.get('classification', {}).get('claim_type')}")

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

    if winner == timeout_task:
        # Timeout occurred
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
            stage_timestamps["approval_received"] = approval_decision.get("timestamp") or context.current_utc_datetime.isoformat()
            stage_timestamps["adjudicator_started"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "agent2_processing",
                "claim_id": claim_id,
                "reviewer": approval_decision.get("reviewer"),
                "message": "Processing claim with Claim Adjudicator Agent...",
                "stage_timestamps": stage_timestamps
            })

            # Prepare Agent2 input
            agent2_activity_input = {
                "claim_id": claim_id,
                "agent1_output": agent1_result,
                "approval_decision": approval_decision,
                "_instance_id": instance_id
            }

            # Call Agent2 Activity
            agent2_activity_result = yield context.call_activity("agent2_activity", agent2_activity_input)

            agent2_input = agent2_activity_result.get("agent2_input")
            agent2_output = agent2_activity_result.get("agent2_output")

            if not context.is_replaying:
                logger.info(f"[{instance_id}] Agent2 completed - Decision: {agent2_output.get('decision')}")

            stage_timestamps["adjudicator_completed"] = context.current_utc_datetime.isoformat()

            # =========================================================================
            # Step 6: Call Agent3 for Email Composition
            # =========================================================================
            stage_timestamps["email_composer_started"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "agent3_processing",
                "claim_id": claim_id,
                "decision": agent2_output.get("decision"),
                "message": "Composing notification email...",
                "stage_timestamps": stage_timestamps
            })

            # Prepare Agent3 input
            agent3_activity_input = {
                "claim_id": claim_id,
                "agent1_output": agent1_result,
                "agent2_output": agent2_output,
                "_instance_id": instance_id
            }

            # Call Agent3 Activity
            agent3_activity_result = yield context.call_activity("agent3_activity", agent3_activity_input)

            agent3_input = agent3_activity_result.get("agent3_input")
            agent3_output = agent3_activity_result.get("agent3_output")

            if not context.is_replaying:
                if agent3_output:
                    logger.info(f"[{instance_id}] Agent3 completed - Subject: {agent3_output.get('email_subject')}")
                else:
                    logger.warning(f"[{instance_id}] Agent3 failed - {agent3_activity_result.get('error')}")

            stage_timestamps["email_composer_completed"] = context.current_utc_datetime.isoformat()
            stage_timestamps["completed"] = context.current_utc_datetime.isoformat()
            context.set_custom_status({
                "step": "completed",
                "claim_id": claim_id,
                "decision": agent2_output.get("decision"),
                "approved_amount": agent2_output.get("approved_amount"),
                "email_sent": agent3_output is not None,
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
