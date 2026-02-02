"""
Notify Activity for HITL Orchestration.

Logs the approval URL and notification details when a claim
requires human review.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def run_notify_activity(input_data: dict) -> dict:
    """
    Log notification for human approval request.

    In a production system, this would send an email, Teams message,
    or other notification. For now, it logs the approval URL.

    Args:
        input_data: Dictionary containing:
            - instance_id: The orchestration instance ID
            - claim_id: The claim identifier
            - approval_url: URL for the approval endpoint
            - review_url: URL for the review UI (optional)
            - agent1_summary: Summary from Agent1 classification

    Returns:
        Dictionary with notification status and timestamp
    """
    instance_id = input_data.get("instance_id")
    claim_id = input_data.get("claim_id")
    approval_url = input_data.get("approval_url")
    review_url = input_data.get("review_url")
    agent1_summary = input_data.get("agent1_summary", {})

    # Log the notification details
    logger.info("=" * 60)
    logger.info("HUMAN APPROVAL REQUIRED")
    logger.info("=" * 60)
    logger.info(f"Instance ID: {instance_id}")
    logger.info(f"Claim ID: {claim_id}")
    logger.info(f"Classification: {agent1_summary.get('claim_type', 'Unknown')}")
    logger.info(f"Confidence: {agent1_summary.get('confidence_score', 'N/A')}")
    logger.info(f"Requires Review: {agent1_summary.get('requires_human_review', True)}")
    logger.info(f"Total Estimate: ${agent1_summary.get('total_estimate', 'N/A')}")
    logger.info("-" * 60)
    logger.info(f"Approval URL: {approval_url}")
    if review_url:
        logger.info(f"Review UI: {review_url}")
    logger.info("=" * 60)

    # In production, you would send notifications here:
    # - Send email to claims reviewers
    # - Post to Teams/Slack channel
    # - Create task in ticketing system
    # - etc.

    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "notification_sent": True,
        "notification_type": "log",  # Would be "email", "teams", etc. in production
        "timestamp": timestamp,
        "instance_id": instance_id,
        "claim_id": claim_id,
        "approval_url": approval_url,
        "review_url": review_url
    }
