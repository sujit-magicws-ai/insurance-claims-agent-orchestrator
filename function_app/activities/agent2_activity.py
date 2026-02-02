"""
Agent2 Activity for Claim Adjudication.

Invokes the claim-approval-agent in Azure AI Foundry to adjudicate
claims based on the structured claim data.
"""

import logging
from datetime import datetime, timezone

from shared.agent_client import invoke_agent2
from shared.models import Agent2Output

logger = logging.getLogger(__name__)


def build_agent2_input(
    claim_id: str,
    agent1_output: dict,
    approval_decision: dict
) -> dict:
    """
    Build the structured input for Agent2 from reviewer's claim_data or Agent1 output.

    If the reviewer provided claim_data in their approval, use it directly.
    Otherwise, fall back to extracting from Agent1 output.

    Args:
        claim_id: The claim identifier
        agent1_output: Output from Agent1 (classification, extracted_info, document_extraction)
        approval_decision: The human reviewer's approval decision with claim_data

    Returns:
        Structured dictionary for Agent2 input
    """
    classification = agent1_output.get("classification", {})

    # Check if reviewer provided complete claim_data
    claim_data = approval_decision.get("claim_data")
    if claim_data:
        # Use reviewer's claim_data directly, just add metadata
        logger.info("Using reviewer's claim_data for Agent2 input")
        agent2_input = {
            "claim_id": claim_id,
            "claimant": claim_data.get("claimant", {}),
            "contract": claim_data.get("contract", {}),
            "vehicle": claim_data.get("vehicle", {}),
            "repair": claim_data.get("repair", {}),
            "documents": claim_data.get("documents", {}),
            "metadata": {
                "submission_date": datetime.now(timezone.utc).isoformat(),
                "reviewer": approval_decision.get("reviewer"),
                "reviewer_comments": approval_decision.get("comments"),
                "agent1_confidence": agent1_output.get("confidence_score"),
                "agent1_classification": classification,
                "data_source": "reviewer_claim_data"
            }
        }
        return agent2_input

    # Fallback: Extract from Agent1 output (uses merged extracted_info)
    logger.info("No claim_data provided, using Agent1 extracted_info")

    # Get merged extracted_info (already contains merged data from email + document)
    extracted_info = agent1_output.get("extracted_info", {})
    document_extraction = agent1_output.get("document_extraction", {})

    # Get claim amounts from approval decision (reviewer may have entered amounts)
    claim_amounts = approval_decision.get("claim_amounts", {}) or {}

    # Build the structured input from Agent1's merged extracted_info
    agent2_input = {
        "claim_id": claim_id,
        "claimant": {
            "name": extracted_info.get("claimant_name"),
            "email": extracted_info.get("claimant_email"),
            "phone": extracted_info.get("claimant_phone"),
            "address": extracted_info.get("claimant_address"),
            "lienholder": extracted_info.get("lienholder")
        },
        "contract": {
            "contract_number": extracted_info.get("contract_number"),
            "product_type": classification.get("claim_type", "VSC"),
            "coverage_level": "Gold",
            "status": "Active",
            "effective_date": None,
            "expiration_date": None,
            "deductible": claim_amounts.get("deductible", 100),
            "max_claim_amount": 5000,
            "mileage_limit": 100000
        },
        "vehicle": {
            "year": extracted_info.get("vehicle_year"),
            "make": extracted_info.get("vehicle_make"),
            "model": extracted_info.get("vehicle_model"),
            "vin": extracted_info.get("vehicle_vin"),
            "current_mileage": extracted_info.get("current_odometer"),
            "purchase_mileage": None
        },
        "claim": {
            "date_of_loss": extracted_info.get("date_of_loss"),
            "date_reported": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        },
        "repair": {
            "facility_name": extracted_info.get("repair_facility"),
            "facility_type": "Authorized Dealer",
            "diagnosis": extracted_info.get("diagnosis"),
            "issue_summary": extracted_info.get("issue_summary"),
            "repair_type": f"{classification.get('sub_type', 'Mechanical')} - {classification.get('component_category', 'General')}",
            "total_parts": claim_amounts.get("total_parts_cost", 0),
            "total_labor": claim_amounts.get("total_labor_cost", 0),
            "total_estimate": claim_amounts.get("total_estimate", 0)
        },
        "documents": {
            "damage_photos": False,
            "claim_form": document_extraction.get("status") == "success"
        },
        "metadata": {
            "submission_date": datetime.now(timezone.utc).isoformat(),
            "reviewer": approval_decision.get("reviewer"),
            "reviewer_comments": approval_decision.get("comments"),
            "agent1_confidence": agent1_output.get("confidence_score"),
            "agent1_classification": classification,
            "data_source": "agent1_extraction"
        }
    }

    return agent2_input


def run_agent2_activity(input_data: dict) -> dict:
    """
    Run Agent2 activity for claim adjudication.

    Args:
        input_data: Dictionary containing:
            - claim_id: The claim identifier
            - agent1_output: Output from Agent1
            - approval_decision: Human reviewer's decision
            - _instance_id: Orchestration instance ID (optional, for logging)

    Returns:
        Dictionary with Agent2 output (adjudication decision)
    """
    instance_id = input_data.get("_instance_id")
    claim_id = input_data.get("claim_id")
    agent1_output = input_data.get("agent1_output", {})
    approval_decision = input_data.get("approval_decision", {})

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Starting Agent2 activity for claim {claim_id}")

    try:
        # Build structured input for Agent2
        agent2_input = build_agent2_input(claim_id, agent1_output, approval_decision)

        logger.info(f"{log_prefix}Agent2 input built - Estimate: ${agent2_input['repair']['total_estimate']}")

        # Invoke Agent2
        agent2_output = invoke_agent2(
            claim_id=claim_id,
            claim_data=agent2_input,
            instance_id=instance_id
        )

        logger.info(f"{log_prefix}Agent2 completed - Decision: {agent2_output.decision}")

        # Return as dictionary
        return {
            "agent2_input": agent2_input,
            "agent2_output": agent2_output.model_dump(mode="json")
        }

    except Exception as e:
        logger.error(f"{log_prefix}Agent2 activity failed: {str(e)}")
        raise
