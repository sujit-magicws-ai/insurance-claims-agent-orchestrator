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

from .models import Agent1Input, Agent1Output, Agent2Output, Agent3Input, Agent3Output
from .prompts import build_agent1_prompt, build_agent2_prompt, build_agent3_prompt

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
            "current_odometer": 45000,
            "date_of_loss": "2026-01-28",
            "issue_summary": "Transmission issues reported - grinding noise when shifting",
            "repair_facility": "ABC Auto Service",
            "diagnosis": None,
            "lienholder": None
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
                "current_odometer": 45000,
                "date_of_loss": "2026-01-28",
                "issue_summary": "Transmission repair needed",
                "repair_facility": "ABC Auto Service, 123 Main St, Tampa, FL 33601",
                "diagnosis": "Transmission solenoid failure",
                "lienholder": "N/A"
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
            "current_odometer": 45000,  # From document
            "date_of_loss": "2026-01-28",  # From document
            "issue_summary": "Transmission issues reported - grinding noise when shifting",  # From email (preferred)
            "repair_facility": "ABC Auto Service, 123 Main St, Tampa, FL 33601",  # From document
            "diagnosis": "Transmission solenoid failure",  # From document
            "lienholder": "N/A"  # From document
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


def _get_mock_agent3_response(input_data: Agent3Input) -> dict:
    """Generate a mock Agent3 (Email Composer) response for testing.

    Args:
        input_data: The Agent3 input data

    Returns:
        Mock response dictionary matching Agent3Output schema
    """
    return {
        "claim_id": input_data.claim_id,
        "email_subject": f"Your Claim {input_data.claim_id} - {input_data.email_purpose}",
        "email_body": f"""Dear {input_data.recipient_name},

[MOCK EMAIL]

{input_data.outcome_summary}

If you have any questions regarding your claim, please don't hesitate to contact our claims department.

Best regards,
{input_data.config.persona}

---
Claim Reference: {input_data.claim_id}
This is an automated notification.""",
        "recipient_name": input_data.recipient_name,
        "recipient_email": input_data.recipient_email
    }


# =============================================================================
# Agent Invocation Functions
# =============================================================================

def is_mock_mode(agent_num: int = 1) -> bool:
    """Check if we should use mock mode.

    Mock mode is enabled when AGENT_MOCK_MODE env var is set to 'true'
    or when the agent's project endpoint is not properly configured.

    Args:
        agent_num: Which agent to check (1, 2, or 3)

    Returns:
        True if mock mode should be used
    """
    mock_mode = os.getenv("AGENT_MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        return True

    # Check agent-specific endpoint
    endpoint_var = f"AGENT{agent_num}_PROJECT_ENDPOINT"
    endpoint = os.getenv(endpoint_var, "")

    # For Agent3, fall back to Agent1 endpoint if not specifically configured
    if agent_num == 3 and not endpoint:
        endpoint = os.getenv("AGENT1_PROJECT_ENDPOINT", "")
        if endpoint and "your-project" not in endpoint:
            return False  # Use Agent1's endpoint for Agent3

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


def evaluate_arithmetic_expression(match) -> str:
    """Evaluate a simple arithmetic expression found in JSON.

    Args:
        match: Regex match object containing the expression

    Returns:
        The evaluated result as a string, or original if evaluation fails
    """
    expr = match.group(0)
    try:
        # Only allow safe arithmetic: numbers, +, -, *, /, spaces, decimal points
        if re.match(r'^[\d\s\.\+\-\*\/]+$', expr):
            result = eval(expr)
            # Format as float if it has decimals, otherwise as int
            if isinstance(result, float):
                return f"{result:.2f}"
            return str(result)
    except:
        pass
    return expr


def fix_common_json_issues(json_str: str) -> str:
    """Attempt to fix common JSON formatting issues from LLM responses.

    Args:
        json_str: Potentially malformed JSON string

    Returns:
        Fixed JSON string (best effort)
    """
    import re

    fixed = json_str

    # Fix arithmetic expressions in numeric values (e.g., 285.00 + 45.00 -> 330.00)
    # Pattern: number followed by arithmetic operator and another number (outside of strings)
    # This is tricky because we need to avoid modifying strings
    # Match pattern like: ": 285.00 + 45.00," or ": 285 + 45,"
    arithmetic_pattern = r':\s*(\d+(?:\.\d+)?\s*[\+\-\*\/]\s*\d+(?:\.\d+)?(?:\s*[\+\-\*\/]\s*\d+(?:\.\d+)?)*)\s*([,\}\]])'

    def replace_arithmetic(m):
        expr = m.group(1)
        suffix = m.group(2)
        try:
            # Safely evaluate the arithmetic expression
            if re.match(r'^[\d\s\.\+\-\*\/]+$', expr):
                result = eval(expr)
                if isinstance(result, float):
                    return f": {result:.2f}{suffix}"
                return f": {result}{suffix}"
        except:
            pass
        return m.group(0)

    fixed = re.sub(arithmetic_pattern, replace_arithmetic, fixed)

    # Remove trailing commas before closing brackets/braces
    # e.g., {"a": 1,} -> {"a": 1}
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    # Fix missing commas between properties: }"field" -> },"field" or "]"field" -> ],"field"
    # Pattern: closing brace/bracket followed by whitespace and opening quote without comma
    fixed = re.sub(r'([}\]])\s*(")', r'\1,\2', fixed)

    # Fix missing commas after values: value"field" -> value,"field"
    # Pattern: null/true/false/number followed by quote without comma
    fixed = re.sub(r'(null|true|false)\s*(")', r'\1,\2', fixed)
    fixed = re.sub(r'(\d)\s*(")', r'\1,\2', fixed)

    # Fix missing commas after string values: "value""field" -> "value","field"
    # This is tricky - need to find end of string followed by start of new key
    # Pattern: quote followed by whitespace and another quote (but not escaped quotes)
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    fixed = re.sub(r'"\s+"', '","', fixed)

    # Remove any control characters that might have slipped through
    fixed = re.sub(r'[\x00-\x1f\x7f]', lambda m: ' ' if m.group(0) in '\t\n\r' else '', fixed)

    return fixed


def repair_json_iteratively(json_str: str, max_iterations: int = 5) -> str:
    """Iteratively repair JSON by finding and fixing errors one at a time.

    Args:
        json_str: Potentially malformed JSON string
        max_iterations: Maximum repair attempts

    Returns:
        Repaired JSON string (best effort)
    """
    import re

    current = json_str

    for iteration in range(max_iterations):
        try:
            json.loads(current)
            return current  # Valid JSON, return it
        except json.JSONDecodeError as e:
            error_pos = e.pos
            error_msg = e.msg

            logger.debug(f"JSON repair iteration {iteration + 1}: {error_msg} at pos {error_pos}")

            # Get context around error
            start = max(0, error_pos - 50)
            end = min(len(current), error_pos + 50)
            context = current[start:end]

            if "Expecting ',' delimiter" in error_msg:
                # Find the position and try to insert a comma
                # Look backwards for the end of the previous value
                before_error = current[:error_pos]
                after_error = current[error_pos:]

                # Check what's at the error position
                if after_error.startswith('"'):
                    # Missing comma before a new string key
                    # Insert comma before the quote
                    current = before_error.rstrip() + ',' + after_error
                    logger.debug(f"Inserted comma before string at pos {error_pos}")
                    continue

            elif "Expecting ':' delimiter" in error_msg:
                # Might be an unquoted key or missing colon
                pass

            elif "Expecting value" in error_msg:
                # Might be a dangling comma or incomplete value
                pass

            # If we couldn't fix it, try general fixes
            current = fix_common_json_issues(current)

    return current


def parse_agent_response(response_text: str, agent_name: str, max_retries: int = 3) -> dict:
    """Parse agent response with retry logic and error handling.

    Attempts to parse JSON from agent response, with fallback to fix
    common JSON formatting issues using multiple repair strategies.

    Args:
        response_text: Raw response text from agent
        agent_name: Agent name for logging
        max_retries: Maximum parsing retry attempts

    Returns:
        Parsed response dictionary

    Raises:
        json.JSONDecodeError: If JSON parsing fails after all retries
    """
    # Extract JSON from potential markdown code blocks
    json_str = extract_json_from_response(response_text)
    original_json_str = json_str

    # First attempt - try direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON parse failed for {agent_name}: {e}")
        logger.warning(f"Error at position {e.pos}, attempting repairs...")

        # Log context around the error for debugging
        start = max(0, e.pos - 100)
        end = min(len(json_str), e.pos + 100)
        logger.error(f"Context around error: ...{json_str[start:end]}...")

    # Second attempt - apply common fixes
    try:
        json_str = fix_common_json_issues(original_json_str)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Common fixes didn't help for {agent_name}: {e}")

    # Third attempt - iterative repair
    try:
        json_str = repair_json_iteratively(original_json_str)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Iterative repair didn't help for {agent_name}: {e}")

    # Fourth attempt - try json5 (more lenient parser)
    try:
        import json5
        result = json5.loads(original_json_str)
        logger.info(f"Successfully parsed {agent_name} response using json5")
        return result
    except ImportError:
        logger.warning("json5 not available for fallback parsing")
    except Exception as e:
        logger.warning(f"json5 parsing also failed for {agent_name}: {e}")

    # Final attempt - log full response and fail
    logger.error(f"JSON parsing failed after all repair attempts for {agent_name}")
    logger.error(f"Full raw response:\n{response_text}")

    # Try one more time to give useful error context
    try:
        json.loads(original_json_str)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Failed to parse {agent_name} response after all repair attempts. "
            f"Original error: {e.msg}",
            e.doc,
            e.pos
        )


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


def invoke_agent1(input_data: Agent1Input, instance_id: Optional[str] = None, max_retries: int = 2) -> Agent1Output:
    """Invoke Agent1 (claim-assistant-agent) for claim classification.

    Args:
        input_data: The input data for classification
        instance_id: Optional orchestration instance ID for logging
        max_retries: Maximum number of retries on failure

    Returns:
        Agent1Output with classification results

    Raises:
        Exception: If agent invocation or response parsing fails after all retries
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

        agent_name = os.getenv("AGENT1_NAME", "claim-assistant-agent")
        project_endpoint = os.getenv("AGENT1_PROJECT_ENDPOINT")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Invoke the agent
                response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)

                # Parse the response with retry logic
                response_dict = parse_agent_response(response_text, agent_name)
                break  # Success, exit retry loop
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"{log_prefix}Agent1 attempt {attempt + 1} failed: {e}. Retrying...")
                    import time
                    time.sleep(1)  # Brief delay before retry
                else:
                    logger.error(f"{log_prefix}Agent1 failed after {max_retries + 1} attempts")
                    raise

    # Validate and return as typed model
    output = Agent1Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Agent1 classified claim as: {output.classification.claim_type}")

    return output


def invoke_agent2(
    claim_id: str,
    claim_data: dict,
    instance_id: Optional[str] = None,
    max_retries: int = 2
) -> Agent2Output:
    """Invoke Agent2 (claim-approval-agent) for claim adjudication.

    Args:
        claim_id: The claim identifier
        claim_data: The structured claim data (agent2_input format)
        instance_id: Optional orchestration instance ID for logging
        max_retries: Maximum number of retries on failure

    Returns:
        Agent2Output with adjudication results

    Raises:
        Exception: If agent invocation or response parsing fails after all retries
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

        agent_name = os.getenv("AGENT2_NAME", "claim-approval-agent")
        project_endpoint = os.getenv("AGENT2_PROJECT_ENDPOINT")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Invoke the agent
                response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)

                # Parse the response with retry logic
                response_dict = parse_agent_response(response_text, agent_name)
                break  # Success, exit retry loop
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"{log_prefix}Agent2 attempt {attempt + 1} failed: {e}. Retrying...")
                    import time
                    time.sleep(1)  # Brief delay before retry
                else:
                    logger.error(f"{log_prefix}Agent2 failed after {max_retries + 1} attempts")
                    raise

    # Validate and return as typed model
    output = Agent2Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Agent2 decision: {output.decision} - Amount: ${output.approved_amount}")

    return output


def invoke_email_composer(
    input_data: Agent3Input,
    instance_id: Optional[str] = None,
    max_retries: int = 2
) -> Agent3Output:
    """Invoke Agent3 (email-composer-agent) for email composition.

    Args:
        input_data: The input data for email composition
        instance_id: Optional orchestration instance ID for logging
        max_retries: Maximum number of retries on failure

    Returns:
        Agent3Output with composed email

    Raises:
        Exception: If agent invocation or response parsing fails after all retries
    """
    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Invoking Email Composer for claim {input_data.claim_id}")

    if is_mock_mode(agent_num=3):
        logger.info(f"{log_prefix}Using mock mode for Agent3 (Email Composer)")
        response_dict = _get_mock_agent3_response(input_data)
    else:
        # Build the prompt
        prompt = build_agent3_prompt(
            claim_id=input_data.claim_id,
            recipient_name=input_data.recipient_name,
            recipient_email=input_data.recipient_email,
            email_purpose=input_data.email_purpose,
            outcome_summary=input_data.outcome_summary,
            persona=input_data.config.persona,
            additional_context=input_data.additional_context or "",
            tone=input_data.config.tone,
            length=input_data.config.length,
            empathy=input_data.config.empathy,
            call_to_action=input_data.config.call_to_action,
            template=input_data.config.template or "default"
        )

        agent_name = os.getenv("AGENT3_NAME", "EmailComposerAgent")
        project_endpoint = os.getenv("AGENT3_PROJECT_ENDPOINT", os.getenv("AGENT1_PROJECT_ENDPOINT"))

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Invoke the agent
                response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)

                # Parse the response with retry logic
                response_dict = parse_agent_response(response_text, agent_name)
                break  # Success, exit retry loop
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"{log_prefix}Agent3 attempt {attempt + 1} failed: {e}. Retrying...")
                    import time
                    time.sleep(1)  # Brief delay before retry
                else:
                    logger.error(f"{log_prefix}Agent3 (Email Composer) failed after {max_retries + 1} attempts")
                    raise

    # Add generated_at timestamp if not present
    if "generated_at" not in response_dict:
        response_dict["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Validate and return as typed model
    output = Agent3Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Email Composer generated email: {output.email_subject}")

    return output
