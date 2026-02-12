"""
Invoice Parser Activity.

Invokes the Invoice Parser Agent in Azure AI Foundry to extract
structured data from repair shop invoices.
"""

import logging

from shared.agent_client import invoke_invoice_parser

logger = logging.getLogger(__name__)


def run_invoice_parser_activity(input_data: dict) -> dict:
    """
    Run invoice parser activity.

    Args:
        input_data: Dictionary containing:
            - invoice_id: The invoice identifier
            - shop_name: Repair shop name
            - shop_email: Repair shop email
            - invoice_text: Plain text of the invoice (optional)
            - attachment_url: URL to the invoice PDF (optional)
            - persona_name: Contractor persona name (optional)
            - _instance_id: Orchestration instance ID (optional, for logging)

    Returns:
        Dictionary with parsed invoice output
    """
    instance_id = input_data.get("_instance_id")
    invoice_id = input_data.get("invoice_id")
    shop_name = input_data.get("shop_name", "")
    shop_email = input_data.get("shop_email", "")
    invoice_text = input_data.get("invoice_text", "")
    attachment_url = input_data.get("attachment_url", "")
    persona_name = input_data.get("persona_name")

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Starting Invoice Parser activity for {invoice_id}")

    try:
        parser_output = invoke_invoice_parser(
            invoice_id=invoice_id,
            shop_name=shop_name,
            shop_email=shop_email,
            invoice_text=invoice_text,
            attachment_url=attachment_url,
            instance_id=instance_id,
            persona_name=persona_name
        )

        logger.info(
            f"{log_prefix}Invoice Parser completed - "
            f"{len(parser_output.line_items)} items, total: ${parser_output.total}"
        )

        return {
            "parser_output": parser_output.model_dump(mode="json")
        }

    except Exception as e:
        logger.error(f"{log_prefix}Invoice Parser activity failed: {str(e)}")
        raise
