"""
Agent1 Activity Function - Claim Classification.

This activity invokes the claim-assistant-agent to classify
incoming claim emails and extract relevant information.
"""

import logging
from shared.models import Agent1Input, Agent1Output
from shared.agent_client import invoke_agent1

logger = logging.getLogger(__name__)


def run_agent1_activity(input_data: dict) -> dict:
    """
    Activity function that invokes Agent1 for claim classification.

    This function is called by the orchestrator and should be idempotent
    (safe to retry without side effects).

    Args:
        input_data: Dictionary containing Agent1Input fields:
            - claim_id: Unique claim identifier
            - email_content: The email content from claimant
            - attachment_url: URL to the attachment
            - sender_email: Sender's email address
            - received_date: (optional) When email was received

    Returns:
        Dictionary containing Agent1Output fields:
            - claim_id: Unique claim identifier
            - classification: Claim type, sub-type, urgency
            - justification: Reasoning for classification
            - extracted_info: Key information from email
            - confidence_score: Confidence level (0-1)
            - flags: Review flags and concerns

    Raises:
        Exception: If agent invocation or response parsing fails
    """
    # Extract instance_id if provided (for logging correlation)
    instance_id = input_data.pop("_instance_id", None)

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Agent1 Activity started for claim: {input_data.get('claim_id')}")

    try:
        # Parse input into typed model
        agent1_input = Agent1Input.model_validate(input_data)

        # Invoke Agent1
        result = invoke_agent1(agent1_input, instance_id=instance_id)

        logger.info(
            f"{log_prefix}Agent1 Activity completed. "
            f"Classification: {result.classification.claim_type}, "
            f"Confidence: {result.confidence_score}"
        )

        # Return as dictionary for Durable Functions serialization
        return result.model_dump(mode="json")

    except Exception as e:
        logger.error(f"{log_prefix}Agent1 Activity failed: {str(e)}")
        raise
