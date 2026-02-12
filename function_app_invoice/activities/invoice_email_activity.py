"""
Invoice Email Activity for composing acknowledgment emails.

Builds the email input from parsed invoice data and invokes
the Email Composer Agent to compose the acknowledgment email.
"""

import logging

from shared.agent_client import invoke_email_composer
from shared.models import Agent3Input, EmailComposerConfig

logger = logging.getLogger(__name__)


def build_invoice_ack_email_input(invoice_id: str, parser_output: dict, shop_email: str = "") -> Agent3Input:
    """
    Build the input for Email Composer Agent from parsed invoice data.

    Args:
        invoice_id: The invoice identifier
        parser_output: Output from the Invoice Parser Agent
        shop_email: Fallback shop email (from original request)

    Returns:
        Agent3Input object for email composition
    """
    # Extract shop info
    shop_info = parser_output.get("shop_info", {})
    recipient_name = shop_info.get("contact_name") or shop_info.get("shop_name") or "Repair Shop"
    recipient_email = shop_info.get("shop_email") or shop_email

    # Extract vehicle info for context
    vehicle_info = parser_output.get("vehicle_info", {})
    vehicle_desc = ""
    if vehicle_info.get("make"):
        parts = [str(vehicle_info.get("year", "")), vehicle_info.get("make", ""), vehicle_info.get("model", "")]
        vehicle_desc = " ".join(p for p in parts if p).strip()

    # Build outcome summary
    invoice_number = parser_output.get("invoice_number") or invoice_id
    total = parser_output.get("total", 0)
    line_count = len(parser_output.get("line_items", []))

    outcome_summary = (
        f"We have received your invoice {invoice_number}"
    )
    if vehicle_desc:
        outcome_summary += f" for {vehicle_desc}"
    outcome_summary += f". Total: ${total:.2f} ({line_count} line items). "
    outcome_summary += (
        "We are processing your submission and will respond within 2-3 business days."
    )

    # Build additional context
    additional_context_parts = []
    if vehicle_desc:
        additional_context_parts.append(f"Vehicle: {vehicle_desc}")
    if vehicle_info.get("vin"):
        additional_context_parts.append(f"VIN: {vehicle_info['vin']}")
    if parser_output.get("parts_subtotal"):
        additional_context_parts.append(f"Parts: ${parser_output['parts_subtotal']:.2f}")
    if parser_output.get("labor_subtotal"):
        additional_context_parts.append(f"Labor: ${parser_output['labor_subtotal']:.2f}")

    additional_context = "\n".join(additional_context_parts) if additional_context_parts else ""

    email_config = EmailComposerConfig(
        tone="formal",
        length="brief",
        empathy="warm",
        call_to_action="none",
        persona="Invoice Processing",
        template=None
    )

    return Agent3Input(
        claim_id=invoice_id,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        email_purpose="Invoice Receipt Acknowledgment",
        outcome_summary=outcome_summary,
        additional_context=additional_context,
        config=email_config
    )


def run_invoice_email_activity(input_data: dict) -> dict:
    """
    Run invoice email composition activity.

    Args:
        input_data: Dictionary containing:
            - invoice_id: The invoice identifier
            - parser_output: Output from Invoice Parser Agent
            - shop_email: Fallback shop email
            - persona_name: Contractor persona name (optional)
            - _instance_id: Orchestration instance ID (optional, for logging)

    Returns:
        Dictionary with Agent3 output (composed email)
    """
    instance_id = input_data.get("_instance_id")
    invoice_id = input_data.get("invoice_id")
    parser_output = input_data.get("parser_output", {})
    shop_email = input_data.get("shop_email", "")
    persona_name = input_data.get("persona_name")

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Starting Invoice Email activity for {invoice_id}")

    try:
        # Build input for Email Composer
        agent3_input = build_invoice_ack_email_input(
            invoice_id=invoice_id,
            parser_output=parser_output,
            shop_email=shop_email
        )

        logger.info(f"{log_prefix}Email Composer input built - Purpose: {agent3_input.email_purpose}")
        logger.info(f"{log_prefix}Recipient: {agent3_input.recipient_name} <{agent3_input.recipient_email}>")

        # Invoke Email Composer Agent
        agent3_output = invoke_email_composer(
            input_data=agent3_input,
            instance_id=instance_id,
            persona_name=persona_name
        )

        logger.info(f"{log_prefix}Email Composer completed - Subject: {agent3_output.email_subject}")

        return {
            "agent3_input": agent3_input.model_dump(mode="json"),
            "agent3_output": agent3_output.model_dump(mode="json")
        }

    except Exception as e:
        logger.error(f"{log_prefix}Invoice Email activity failed: {str(e)}")
        return {
            "agent3_input": None,
            "agent3_output": None,
            "error": str(e),
            "status": "failed"
        }
