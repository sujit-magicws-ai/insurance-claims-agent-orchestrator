"""
Azure Durable Functions Invoice Processing — Main Function App

This module defines the HTTP triggers and orchestrator for the
Repair Shop Invoice Parsing workflow:
    1. Receive invoice (HTTP)
    2. Parse invoice (Invoice Parser Agent)
    3. Compose acknowledgment email (Email Composer Agent)
    4. Send email (SMTP)
"""

import azure.functions as func
import azure.durable_functions as df
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from activities.invoice_parser_activity import run_invoice_parser_activity
from activities.invoice_email_activity import run_invoice_email_activity
from activities.send_email_activity import run_send_email_activity
from shared.models import InvoiceRequest

# Initialize the Durable Functions app
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)


# =============================================================================
# HTTP Triggers
# =============================================================================

@app.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint to verify the function app is running."""
    logger.info("Health check endpoint called")

    response_body = {
        "status": "healthy",
        "service": "invoice-processing",
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
    """Return full contractor workforce state for dashboard polling."""
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
    """Return contractor pool configuration."""
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
# Dashboard
# =============================================================================

@app.route(route="invoice-dashboard", methods=["GET"])
async def serve_invoice_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """Serve the Invoice Processing AI Contractor Dashboard."""
    try:
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "clone_dashboard.html"

        if not html_path.exists():
            return func.HttpResponse(
                "Invoice Dashboard not found",
                status_code=404
            )

        html_content = html_path.read_text(encoding="utf-8")

        return func.HttpResponse(
            body=html_content,
            status_code=200,
            mimetype="text/html"
        )

    except Exception as e:
        logger.error(f"Error serving invoice dashboard: {str(e)}")
        return func.HttpResponse(
            f"Error loading invoice dashboard: {str(e)}",
            status_code=500
        )


# =============================================================================
# Invoice Orchestration Triggers
# =============================================================================

@app.route(route="invoices/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_invoice_orchestration(req: func.HttpRequest, client) -> func.HttpResponse:
    """
    HTTP trigger to start a new invoice orchestration.

    Request Body:
        {
            "invoice_id": "INV-2026-001",
            "shop_name": "ABC Auto Service",
            "shop_email": "shop@example.com",
            "attachment_url": "https://storage.example.com/invoice.pdf",
            "invoice_text": "Optional plain text of invoice"
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
        required_fields = ["invoice_id", "shop_name", "shop_email"]
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
            invoice_request = InvoiceRequest.model_validate(body)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Validation error: {str(e)}"}),
                status_code=400,
                mimetype="application/json"
            )

        # Use invoice_id as instance_id for deterministic tracking
        instance_id = f"invoice-{invoice_request.invoice_id}"

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
            orchestration_function_name="invoice_orchestrator",
            instance_id=instance_id,
            client_input=invoice_request.model_dump(mode="json")
        )

        # Track email received for clone dashboard
        from shared.contractor_manager import ContractorManager
        ContractorManager().increment_email_received(invoice_request.invoice_id)

        logger.info(f"Started orchestration {instance_id} for invoice {invoice_request.invoice_id}")

        # Build response with status URLs
        base_url = req.url.split("/api/")[0]
        response_body = {
            "instance_id": instance_id,
            "invoice_id": invoice_request.invoice_id,
            "status": "Started",
            "status_url": f"{base_url}/api/invoices/status/{instance_id}"
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


@app.route(route="invoices/status/{instance_id}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_invoice_status(req: func.HttpRequest, client) -> func.HttpResponse:
    """HTTP trigger to get the status of an invoice orchestration."""
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

        rs = status.runtime_status
        rs_name = rs.name if hasattr(rs, 'name') else str(rs)

        def safe_iso(dt):
            if dt is None:
                return None
            return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)

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
# Orchestrator Function
# =============================================================================

@app.orchestration_trigger(context_name="context")
def invoice_orchestrator(context: df.DurableOrchestrationContext):
    """
    Main orchestrator for invoice processing.

    Flow:
        1. Assign to invoice_parser pool → Parse invoice → Release
        2. Assign to email_composer pool → Compose acknowledgment → Release
        3. Increment email_sender → Send email → Decrement email_sender
        4. Return result

    No HITL. No timeout. Simple linear yield chain.
    """
    instance_id = context.instance_id

    if not context.is_replaying:
        logger.info(f"[{instance_id}] Invoice orchestrator started")

    # Get input data
    input_data = context.get_input()
    invoice_id = input_data.get("invoice_id")
    shop_name = input_data.get("shop_name", "")
    shop_email = input_data.get("shop_email", "")
    started_at = context.current_utc_datetime.isoformat()

    stage_timestamps = {
        "received": started_at
    }

    # =========================================================================
    # Step 1: Invoice Parser
    # =========================================================================
    # Assign to invoice_parser contractor pool
    assign1 = yield context.call_activity("assign_contractor_activity",
        {"agent_id": "invoice_parser", "claim_id": invoice_id})
    parser_contractor = assign1["contractor_name"]

    stage_timestamps["parser_started"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "invoice_parser_processing",
        "invoice_id": invoice_id,
        "contractor": parser_contractor,
        "message": f"Parsing invoice with {parser_contractor}...",
        "stage_timestamps": stage_timestamps
    })

    # Prepare Invoice Parser input
    parser_input = {
        "invoice_id": invoice_id,
        "shop_name": shop_name,
        "shop_email": shop_email,
        "invoice_text": input_data.get("invoice_text", ""),
        "attachment_url": input_data.get("attachment_url", ""),
        "persona_name": parser_contractor,
        "_instance_id": instance_id
    }

    # Call Invoice Parser Activity
    parser_result = yield context.call_activity("invoice_parser_activity", parser_input)

    # Release from invoice_parser contractor pool
    yield context.call_activity("release_contractor_activity",
        {"agent_id": "invoice_parser", "claim_id": invoice_id})

    parser_output = parser_result.get("parser_output")

    if not context.is_replaying:
        total = parser_output.get("total", 0) if parser_output else 0
        logger.info(f"[{instance_id}] Invoice Parser completed by {parser_contractor} - Total: ${total}")

    stage_timestamps["parser_completed"] = context.current_utc_datetime.isoformat()

    # =========================================================================
    # Step 2: Email Composer (Acknowledgment)
    # =========================================================================
    assign2 = yield context.call_activity("assign_contractor_activity",
        {"agent_id": "email_composer", "claim_id": invoice_id})
    email_composer_contractor = assign2["contractor_name"]

    stage_timestamps["email_composer_started"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "email_composer_processing",
        "invoice_id": invoice_id,
        "contractor": email_composer_contractor,
        "message": f"Composing acknowledgment email with {email_composer_contractor}...",
        "stage_timestamps": stage_timestamps
    })

    # Prepare Email Composer input
    email_input = {
        "invoice_id": invoice_id,
        "parser_output": parser_output,
        "shop_email": shop_email,
        "persona_name": email_composer_contractor,
        "_instance_id": instance_id
    }

    # Call Email Composer Activity
    email_result = yield context.call_activity("invoice_email_activity", email_input)

    # Release from email_composer contractor pool
    yield context.call_activity("release_contractor_activity",
        {"agent_id": "email_composer", "claim_id": invoice_id})

    email_output = email_result.get("agent3_output")

    if not context.is_replaying:
        if email_output:
            logger.info(f"[{instance_id}] Email Composer completed by {email_composer_contractor} - Subject: {email_output.get('email_subject')}")
        else:
            logger.warning(f"[{instance_id}] Email Composer failed - {email_result.get('error')}")

    stage_timestamps["email_composer_completed"] = context.current_utc_datetime.isoformat()

    # =========================================================================
    # Step 3: Send Email via SMTP
    # =========================================================================
    send_email_result = None
    if email_output:
        # Increment email sender counter
        yield context.call_activity("update_counter_activity",
            {"counter": "email_sender", "action": "increment", "claim_id": invoice_id})

        stage_timestamps["email_sending_started"] = context.current_utc_datetime.isoformat()
        context.set_custom_status({
            "step": "sending_email",
            "invoice_id": invoice_id,
            "message": "Sending acknowledgment email...",
            "stage_timestamps": stage_timestamps
        })

        # Prepare send email input
        send_email_input = {
            "claim_id": invoice_id,
            "email_subject": email_output.get("email_subject"),
            "email_body": email_output.get("email_body"),
            "recipient_email": email_output.get("recipient_email"),
            "recipient_name": email_output.get("recipient_name"),
            "send_to_review": True,
            "send_to_claimant": False,
            "_instance_id": instance_id
        }

        # Call Send Email Activity
        send_email_result = yield context.call_activity("send_email_activity", send_email_input)

        # Decrement email sender counter
        yield context.call_activity("update_counter_activity",
            {"counter": "email_sender", "action": "decrement", "claim_id": invoice_id})

        if not context.is_replaying:
            if send_email_result.get("success"):
                logger.info(f"[{instance_id}] Email sent successfully")
            else:
                logger.warning(f"[{instance_id}] Email sending failed: {send_email_result.get('errors')}")

        stage_timestamps["email_sending_completed"] = context.current_utc_datetime.isoformat()

    # =========================================================================
    # Complete
    # =========================================================================
    stage_timestamps["completed"] = context.current_utc_datetime.isoformat()
    context.set_custom_status({
        "step": "completed",
        "invoice_id": invoice_id,
        "total": parser_output.get("total") if parser_output else None,
        "email_composed": email_output is not None,
        "email_sent": send_email_result.get("review_email_sent") if send_email_result else False,
        "message": "Processing complete",
        "stage_timestamps": stage_timestamps
    })

    # Build final result
    result = {
        "invoice_id": invoice_id,
        "status": "completed",
        "parser_output": parser_output,
        "email_output": email_output,
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
def invoice_parser_activity(activityInput: dict) -> dict:
    """Activity function wrapper for Invoice Parser."""
    return run_invoice_parser_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def invoice_email_activity(activityInput: dict) -> dict:
    """Activity function wrapper for Invoice Email Composer."""
    return run_invoice_email_activity(activityInput)


@app.activity_trigger(input_name="activityInput")
def send_email_activity(activityInput: dict) -> dict:
    """Activity function wrapper for sending emails via SMTP."""
    return run_send_email_activity(activityInput)


# =============================================================================
# Contractor Lifecycle Activities (Clone Visualizer)
# =============================================================================

@app.activity_trigger(input_name="activityInput")
def assign_contractor_activity(activityInput: dict) -> dict:
    """
    Assign an invoice to a contractor slot via first-fill.

    Input:  {"agent_id": "invoice_parser", "claim_id": "INV-001"}
    Output: {"contractor_name": "Hana", "queued": false}
    """
    from shared.contractor_manager import ContractorManager

    agent_id = activityInput["agent_id"]
    claim_id = activityInput["claim_id"]

    manager = ContractorManager()

    # Invoice leaving "received" stage and entering invoice_parser
    if agent_id == "invoice_parser":
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
    Release an invoice's contractor slot after stage completion.

    Input:  {"agent_id": "invoice_parser", "claim_id": "INV-001"}
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
    Update a non-pool counter (Email Sender or Email Received).

    Input:  {"counter": "email_sender", "action": "increment"}
    Output: {"success": true}
    """
    from shared.contractor_manager import ContractorManager

    counter = activityInput["counter"]
    action = activityInput["action"]
    claim_id = activityInput.get("claim_id")

    manager = ContractorManager()

    if counter == "email_sender":
        if action == "increment":
            manager.increment_email_sending(claim_id)
        else:
            manager.decrement_email_sending(claim_id)
    elif counter == "email_received":
        if action == "increment":
            manager.increment_email_received(claim_id)
        else:
            manager.decrement_email_received(claim_id)
    elif counter == "hitl":
        if action == "increment":
            manager.increment_hitl_waiting(claim_id)
        else:
            manager.decrement_hitl_waiting(claim_id)

    logger.info(f"[Contractor] Counter {counter} {action}ed")

    return {"success": True}
