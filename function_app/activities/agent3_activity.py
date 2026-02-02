"""
Agent3 Activity for Email Composition.

Invokes the Email Composer Agent in Azure AI Foundry to compose
notification emails to customers based on claim decisions.
"""

import logging
from datetime import datetime, timezone

from shared.agent_client import invoke_email_composer
from shared.models import Agent3Input, Agent3Output, EmailComposerConfig

logger = logging.getLogger(__name__)


def build_email_composer_input(
    claim_id: str,
    agent1_output: dict,
    agent2_output: dict,
    config: dict = None
) -> Agent3Input:
    """
    Build the input for Email Composer Agent from Agent1 and Agent2 outputs.

    Args:
        claim_id: The claim identifier
        agent1_output: Output from Agent1 (contains extracted_info with claimant details)
        agent2_output: Output from Agent2 (contains decision and amounts)
        config: Optional email configuration overrides

    Returns:
        Agent3Input object for email composition
    """
    # Extract claimant info from Agent1's extracted_info
    extracted_info = agent1_output.get("extracted_info", {})
    recipient_name = extracted_info.get("claimant_name") or "Valued Customer"
    recipient_email = extracted_info.get("claimant_email") or ""

    # Extract decision info from Agent2
    decision = agent2_output.get("decision", "UNKNOWN")
    approved_amount = agent2_output.get("approved_amount")
    deductible = agent2_output.get("deductible_applied")
    reason = agent2_output.get("reason", "")

    # Build email purpose and outcome summary based on decision
    if decision == "APPROVED":
        email_purpose = "Claim Approval Notification"
        outcome_summary = f"Your claim {claim_id} has been approved! "
        if approved_amount:
            outcome_summary += f"The approved amount is ${approved_amount:.2f}"
            if deductible:
                outcome_summary += f" (after ${deductible:.2f} deductible)"
            outcome_summary += ". "
        outcome_summary += "You should receive reimbursement within 5-7 business days."
        empathy = "warm"
        call_to_action = "soft"

    elif decision == "DENIED":
        email_purpose = "Claim Decision Notification"
        outcome_summary = f"We have completed the review of your claim {claim_id}. "
        outcome_summary += f"Unfortunately, we are unable to approve this claim. {reason} "
        outcome_summary += "If you believe this decision was made in error, you may submit an appeal within 30 days."
        empathy = "highly_supportive"
        call_to_action = "soft"

    elif decision == "MANUAL_REVIEW":
        email_purpose = "Claim Status Update"
        outcome_summary = f"Your claim {claim_id} requires additional review by our claims team. "
        outcome_summary += "A specialist will review your claim and contact you within 2-3 business days. "
        outcome_summary += "No action is required from you at this time."
        empathy = "warm"
        call_to_action = "none"

    else:  # REQUEST_DOCUMENTS or other
        email_purpose = "Additional Information Required"
        missing_docs = agent2_output.get("missing_documents", [])
        outcome_summary = f"We need additional information to process your claim {claim_id}. "
        if missing_docs:
            outcome_summary += f"Please provide the following: {', '.join(missing_docs)}. "
        outcome_summary += "Once received, we will continue processing your claim."
        empathy = "neutral"
        call_to_action = "direct"

    # Build additional context
    vehicle_info = extracted_info.get("vehicle_make", "")
    if vehicle_info:
        vehicle_year = extracted_info.get("vehicle_year", "")
        vehicle_model = extracted_info.get("vehicle_model", "")
        vehicle_info = f"{vehicle_year} {vehicle_info} {vehicle_model}".strip()

    additional_context = f"Vehicle: {vehicle_info}" if vehicle_info else ""
    if extracted_info.get("issue_summary"):
        if additional_context:
            additional_context += f"\nIssue: {extracted_info.get('issue_summary')}"
        else:
            additional_context = f"Issue: {extracted_info.get('issue_summary')}"

    # Build config with defaults and overrides
    email_config = EmailComposerConfig(
        tone=config.get("tone", "formal") if config else "formal",
        length=config.get("length", "standard") if config else "standard",
        empathy=config.get("empathy", empathy) if config else empathy,
        call_to_action=config.get("call_to_action", call_to_action) if config else call_to_action,
        persona=config.get("persona", "Claims Department") if config else "Claims Department",
        template=config.get("template") if config else None
    )

    return Agent3Input(
        claim_id=claim_id,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        email_purpose=email_purpose,
        outcome_summary=outcome_summary,
        additional_context=additional_context,
        config=email_config
    )


def run_agent3_activity(input_data: dict) -> dict:
    """
    Run Agent3 activity for email composition.

    Args:
        input_data: Dictionary containing:
            - claim_id: The claim identifier
            - agent1_output: Output from Agent1
            - agent2_output: Output from Agent2
            - email_config: Optional email configuration
            - _instance_id: Orchestration instance ID (optional, for logging)

    Returns:
        Dictionary with Agent3 output (composed email)
    """
    instance_id = input_data.get("_instance_id")
    claim_id = input_data.get("claim_id")
    agent1_output = input_data.get("agent1_output", {})
    agent2_output = input_data.get("agent2_output", {})
    email_config = input_data.get("email_config")

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Starting Agent3 (Email Composer) activity for claim {claim_id}")

    try:
        # Build input for Email Composer
        agent3_input = build_email_composer_input(
            claim_id=claim_id,
            agent1_output=agent1_output,
            agent2_output=agent2_output,
            config=email_config
        )

        logger.info(f"{log_prefix}Email Composer input built - Purpose: {agent3_input.email_purpose}")
        logger.info(f"{log_prefix}Recipient: {agent3_input.recipient_name} <{agent3_input.recipient_email}>")

        # Invoke Email Composer Agent
        agent3_output = invoke_email_composer(
            input_data=agent3_input,
            instance_id=instance_id
        )

        logger.info(f"{log_prefix}Email Composer completed - Subject: {agent3_output.email_subject}")

        # Return as dictionary
        return {
            "agent3_input": agent3_input.model_dump(mode="json"),
            "agent3_output": agent3_output.model_dump(mode="json")
        }

    except Exception as e:
        logger.error(f"{log_prefix}Agent3 (Email Composer) activity failed: {str(e)}")
        # Return error info instead of raising - email failure shouldn't fail the claim
        return {
            "agent3_input": None,
            "agent3_output": None,
            "error": str(e),
            "status": "failed"
        }
