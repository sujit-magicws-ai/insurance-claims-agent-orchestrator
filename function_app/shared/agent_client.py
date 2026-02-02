"""
Azure AI Foundry Agent Client.

Provides functions for:
- Getting Azure credentials
- Invoking Azure AI Foundry agents
- Mock mode for local testing without real agents
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, quote, urlunparse

from .models import Agent1Input, Agent1Output, Agent2Output
from .prompts import build_agent1_prompt, build_agent2_prompt

logger = logging.getLogger(__name__)

# =============================================================================
# URL Encoding Helper
# =============================================================================

def encode_url_if_needed(url: str) -> str:
    """Encode URL path if it contains unencoded special characters.

    Handles spaces and other special characters in the URL path while
    preserving the URL structure (scheme, domain, query params).

    Args:
        url: The URL to encode

    Returns:
        URL with encoded path component
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)

        # Encode the path component (preserves /)
        encoded_path = quote(parsed.path, safe='/')

        # Reconstruct the URL with encoded path
        encoded_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            encoded_path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))

        if encoded_url != url:
            logger.info(f"URL encoded: {url} -> {encoded_url}")

        return encoded_url
    except Exception as e:
        logger.warning(f"Failed to encode URL, using original: {e}")
        return url


# =============================================================================
# Credential Management
# =============================================================================

def get_credential():
    """Get Azure credential for authentication.

    Returns ClientSecretCredential if service principal env vars are set,
    otherwise returns DefaultAzureCredential for local development.

    Returns:
        Azure credential object
    """
    from azure.identity import DefaultAzureCredential, ClientSecretCredential

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if all([tenant_id, client_id, client_secret]):
        logger.info("Using ClientSecretCredential for authentication")
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        logger.info("Using DefaultAzureCredential for authentication")
        return DefaultAzureCredential()


# =============================================================================
# Mock Responses for Testing
# =============================================================================

def _get_mock_agent1_response(input_data: Agent1Input) -> dict:
    """Generate a mock Agent1 response for testing.

    Args:
        input_data: The Agent1 input data

    Returns:
        Mock response dictionary matching Agent1Output schema
    """
    return {
        "claim_id": input_data.claim_id,
        "classification": {
            "claim_type": "VSC",
            "sub_type": "Mechanical",
            "component_category": "Transmission",
            "urgency": "Standard"
        },
        "justification": "[MOCK] Based on the email content and attached claim form, this appears to be a VSC mechanical claim. "
                        "The claimant describes transmission-related problems with diagnosis of solenoid failure. "
                        "Document extraction confirmed the repair estimate and vehicle details.",
        "confidence_score": 0.92,
        "flags": {
            "requires_human_review": False,
            "missing_information": [],
            "potential_concerns": []
        },
        "email_body_extraction": {
            "claimant_name": None,
            "claimant_phone": "555-123-4567",
            "claimant_address": None,
            "contract_number": None,
            "vehicle_year": 2022,
            "vehicle_make": "Honda",
            "vehicle_model": "Accord",
            "vehicle_vin": None,
            "issue_summary": "Transmission issues reported - grinding noise when shifting",
            "repair_facility": "ABC Auto Service",
            "diagnosis": None,
            "total_parts": None,
            "total_labor": None,
            "total_estimate": 767.50
        },
        "document_extraction": {
            "status": "success",
            "document_type": "claim_form",
            "summary": "[MOCK] VSC Claim Form for claim. The document contains claimant information "
                      "(John Smith), vehicle details (2022 Honda Accord, VIN: 1HGCV1F34NA000123), and repair estimate "
                      "of $767.50 for transmission solenoid replacement at ABC Auto Service.",
            "extracted_fields": {
                "claimant_name": "John Smith",
                "claimant_phone": "555-987-6543",
                "claimant_address": "123 Main St, Tampa, FL 33601",
                "contract_number": "VSC-2024-78542",
                "vehicle_year": 2022,
                "vehicle_make": "Honda",
                "vehicle_model": "Accord",
                "vehicle_vin": "1HGCV1F34NA000123",
                "issue_summary": "Transmission repair needed",
                "repair_facility": "ABC Auto Service, 123 Main St, Tampa, FL 33601",
                "diagnosis": "Transmission solenoid failure",
                "total_parts": 330.00,
                "total_labor": 437.50,
                "total_estimate": 767.50
            },
            "notes": None
        },
        # Merged extracted_info (Document > Email, except issue_summary and claimant_email)
        "extracted_info": {
            "claimant_name": "John Smith",  # From document
            "claimant_email": input_data.sender_email,  # Always from sender_email
            "claimant_phone": "555-987-6543",  # From document
            "claimant_address": "123 Main St, Tampa, FL 33601",  # From document
            "contract_number": "VSC-2024-78542",  # From document
            "vehicle_year": 2022,
            "vehicle_make": "Honda",
            "vehicle_model": "Accord",
            "vehicle_vin": "1HGCV1F34NA000123",  # From document
            "issue_summary": "Transmission issues reported - grinding noise when shifting",  # From email (preferred)
            "repair_facility": "ABC Auto Service, 123 Main St, Tampa, FL 33601",  # From document
            "diagnosis": "Transmission solenoid failure",  # From document
            "total_parts": 330.00,
            "total_labor": 437.50,
            "total_estimate": 767.50
        }
    }


def _get_mock_agent2_response(claim_id: str, claim_data: dict) -> dict:
    """Generate a mock Agent2 response for testing.

    Args:
        claim_id: The claim identifier
        claim_data: The structured claim data

    Returns:
        Mock response dictionary matching Agent2Output schema
    """
    # Extract values from claim data if available
    estimate = claim_data.get("repair", {}).get("total_estimate", 767.50)
    deductible = claim_data.get("contract", {}).get("deductible", 100)
    approved_amount = max(0, estimate - deductible)

    return {
        "claim_id": claim_id,
        "decision": "APPROVED",
        "decision_type": "AUTO",
        "approved_amount": approved_amount,
        "deductible_applied": deductible,
        "missing_documents": [],
        "rules_evaluated": ["AA-01", "AA-02", "AA-03", "AA-04", "AA-05", "AA-06", "AA-07", "AA-08"],
        "rules_passed": ["AA-01", "AA-02", "AA-03", "AA-04", "AA-05", "AA-06", "AA-07", "AA-08"],
        "rules_failed": [],
        "rules_triggered": [],
        "priority": None,
        "assigned_queue": None,
        "reason": f"[MOCK] All required documents are present, the contract is active, "
                 f"the claim is within the coverage period and mileage limit, "
                 f"the repair estimate (${estimate}) is below the auto-approve threshold ($1,500). "
                 f"Claim AUTO-APPROVED for ${approved_amount} after ${deductible} deductible.",
        "evaluation_summary": {
            "contract_status": "Active",
            "coverage_valid": True,
            "mileage_valid": True,
            "estimate_amount": estimate,
            "auto_approve_threshold": 1500,
            "within_threshold": estimate <= 1500,
            "facility_authorized": True,
            "documents_complete": True
        }
    }


# =============================================================================
# Agent Invocation Functions
# =============================================================================

def is_mock_mode(agent_num: int = 1) -> bool:
    """Check if we should use mock mode.

    Mock mode is enabled when AGENT_MOCK_MODE env var is set to 'true'
    or when the agent's project endpoint is not properly configured.

    Args:
        agent_num: Which agent to check (1 or 2)

    Returns:
        True if mock mode should be used
    """
    mock_mode = os.getenv("AGENT_MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        return True

    # Check agent-specific endpoint
    endpoint_var = f"AGENT{agent_num}_PROJECT_ENDPOINT"
    endpoint = os.getenv(endpoint_var, "")

    # Use mock mode if endpoint is not configured or is placeholder
    if not endpoint or "your-project" in endpoint or f"agent{agent_num}-project" in endpoint:
        logger.warning(f"{endpoint_var} not configured, using mock mode")
        return True

    return False


def extract_json_from_response(response_text: str) -> str:
    """Extract JSON from agent response, handling markdown code blocks.

    Args:
        response_text: Raw response text from agent

    Returns:
        Clean JSON string
    """
    import re

    text = response_text.strip()

    # Try to extract JSON from markdown code block
    # Handles ```json ... ``` or ``` ... ```
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        return match.group(1).strip()

    # If no code block, assume the entire response is JSON
    return text


def invoke_foundry_agent(agent_name: str, user_message: str, project_endpoint: str) -> str:
    """Invoke an Azure AI Foundry agent and return the response.

    Args:
        agent_name: Name of the agent to invoke
        user_message: The message/prompt to send to the agent
        project_endpoint: The Azure AI Foundry project endpoint URL

    Returns:
        The agent's response as a string (JSON extracted if in code block)

    Raises:
        Exception: If agent invocation fails
    """
    from azure.ai.projects import AIProjectClient

    logger.info(f"Invoking agent: {agent_name} at {project_endpoint}")

    credential = get_credential()

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    # Get the agent by name
    agent = project_client.agents.get(agent_name=agent_name)
    logger.info(f"Connected to agent: {agent.name}")

    # Get OpenAI client (uses same OAuth token internally)
    openai_client = project_client.get_openai_client()

    # Send message to agent
    response = openai_client.responses.create(
        input=[{"role": "user", "content": user_message}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    logger.info(f"Agent {agent_name} responded successfully")

    # Extract JSON from response (handles markdown code blocks)
    return extract_json_from_response(response.output_text)


def invoke_agent1(input_data: Agent1Input, instance_id: Optional[str] = None) -> Agent1Output:
    """Invoke Agent1 (claim-assistant-agent) for claim classification.

    Args:
        input_data: The input data for classification
        instance_id: Optional orchestration instance ID for logging

    Returns:
        Agent1Output with classification results

    Raises:
        Exception: If agent invocation or response parsing fails
    """
    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Invoking Agent1 for claim {input_data.claim_id}")

    # Encode attachment URL if needed (handles spaces and special characters)
    encoded_attachment_url = encode_url_if_needed(input_data.attachment_url)

    if is_mock_mode(agent_num=1):
        logger.info(f"{log_prefix}Using mock mode for Agent1")
        response_dict = _get_mock_agent1_response(input_data)
    else:
        # Build the prompt
        prompt = build_agent1_prompt(
            claim_id=input_data.claim_id,
            email_content=input_data.email_content,
            attachment_url=encoded_attachment_url,
            sender_email=input_data.sender_email,
            received_date=input_data.received_date.isoformat()
        )

        # Invoke the agent
        agent_name = os.getenv("AGENT1_NAME", "claim-assistant-agent")
        project_endpoint = os.getenv("AGENT1_PROJECT_ENDPOINT")
        response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)

        # Parse the response
        response_dict = json.loads(response_text)

    # Validate and return as typed model
    output = Agent1Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Agent1 classified claim as: {output.classification.claim_type}")

    return output


def invoke_agent2(
    claim_id: str,
    claim_data: dict,
    instance_id: Optional[str] = None
) -> Agent2Output:
    """Invoke Agent2 (claim-approval-agent) for claim adjudication.

    Args:
        claim_id: The claim identifier
        claim_data: The structured claim data (agent2_input format)
        instance_id: Optional orchestration instance ID for logging

    Returns:
        Agent2Output with adjudication results

    Raises:
        Exception: If agent invocation or response parsing fails
    """
    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Invoking Agent2 for claim {claim_id}")

    if is_mock_mode(agent_num=2):
        logger.info(f"{log_prefix}Using mock mode for Agent2")
        response_dict = _get_mock_agent2_response(claim_id, claim_data)
    else:
        # Build the prompt with embedded JSON
        claim_data_json = json.dumps(claim_data, indent=2, default=str)
        prompt = build_agent2_prompt(claim_id, claim_data_json)

        # Invoke the agent
        agent_name = os.getenv("AGENT2_NAME", "claim-approval-agent")
        project_endpoint = os.getenv("AGENT2_PROJECT_ENDPOINT")
        response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)

        # Parse the response
        response_dict = json.loads(response_text)

    # Validate and return as typed model
    output = Agent2Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Agent2 decision: {output.decision} - Amount: ${output.approved_amount}")

    return output
