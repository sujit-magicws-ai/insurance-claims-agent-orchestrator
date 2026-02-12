"""
Azure AI Foundry Agent Client — Invoice Processing.

Provides functions for:
- Getting Azure credentials
- Invoking Azure AI Foundry agents (Invoice Parser + Email Composer)
- Mock mode for local testing without real agents
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, quote, urlunparse

from .models import Agent3Input, Agent3Output, InvoiceParserOutput
from .prompts import build_invoice_parser_prompt, build_agent3_prompt, get_full_signature

logger = logging.getLogger(__name__)

# =============================================================================
# URL Encoding Helper
# =============================================================================

def encode_url_if_needed(url: str) -> str:
    """Encode URL path if it contains unencoded special characters."""
    if not url:
        return url

    try:
        parsed = urlparse(url)
        encoded_path = quote(parsed.path, safe='/')
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
    """Get Azure credential for authentication."""
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

def _get_mock_invoice_parser_response(invoice_id: str, shop_name: str, shop_email: str) -> dict:
    """Generate a mock Invoice Parser response for testing.

    Args:
        invoice_id: The invoice identifier
        shop_name: Repair shop name
        shop_email: Repair shop email

    Returns:
        Mock response dictionary matching InvoiceParserOutput schema
    """
    return {
        "invoice_id": invoice_id,
        "invoice_number": "INV-2026-04521",
        "invoice_date": "2026-02-10",
        "shop_info": {
            "shop_name": shop_name,
            "shop_address": "456 Auto Repair Blvd, Tampa, FL 33602",
            "shop_phone": "813-555-0199",
            "shop_email": shop_email,
            "contact_name": "Mike Johnson",
            "license_number": "FL-AR-2024-7891"
        },
        "vehicle_info": {
            "year": 2023,
            "make": "Toyota",
            "model": "Camry",
            "vin": "4T1BF1FK5NU123456",
            "mileage": 32000,
            "license_plate": "ABC-1234"
        },
        "line_items": [
            {
                "part_number": "90919-01253",
                "description": "Spark Plug Replacement (4x)",
                "quantity": 4,
                "unit_price": 12.50,
                "labor_hours": None,
                "labor_rate": None,
                "line_total": 50.00
            },
            {
                "part_number": None,
                "description": "Transmission Fluid Flush",
                "quantity": 1,
                "unit_price": 85.00,
                "labor_hours": 1.5,
                "labor_rate": 95.00,
                "line_total": 227.50
            },
            {
                "part_number": "15400-RTA-003",
                "description": "Oil Filter",
                "quantity": 1,
                "unit_price": 8.99,
                "labor_hours": None,
                "labor_rate": None,
                "line_total": 8.99
            },
            {
                "part_number": None,
                "description": "Synthetic Oil Change (5W-30, 5 quarts)",
                "quantity": 1,
                "unit_price": 45.00,
                "labor_hours": 0.5,
                "labor_rate": 95.00,
                "line_total": 92.50
            }
        ],
        "parts_subtotal": 156.49,
        "labor_subtotal": 190.00,
        "subtotal": 378.99,
        "tax": 26.53,
        "total": 405.52,
        "notes": "[MOCK] Invoice parsed successfully. All line items extracted with parts and labor breakdown."
    }


def _get_mock_agent3_response(input_data: Agent3Input, persona_name: Optional[str] = None) -> dict:
    """Generate a mock Agent3 (Email Composer) response for testing.

    Args:
        input_data: The Agent3 input data
        persona_name: Optional contractor persona name

    Returns:
        Mock response dictionary matching Agent3Output schema
    """
    signature = get_full_signature(persona_name)

    return {
        "claim_id": input_data.claim_id,
        "email_subject": f"Invoice {input_data.claim_id} - {input_data.email_purpose}",
        "email_body": f"""Dear {input_data.recipient_name},

[MOCK EMAIL]

{input_data.outcome_summary}

If you have any questions regarding your invoice, please don't hesitate to contact our department.

Best regards,

{signature}

---
Invoice Reference: {input_data.claim_id}
This is an automated notification.""",
        "recipient_name": input_data.recipient_name,
        "recipient_email": input_data.recipient_email
    }


# =============================================================================
# Agent Invocation Functions
# =============================================================================

def is_mock_mode(agent_name: str = "invoice_parser") -> bool:
    """Check if we should use mock mode.

    Mock mode is enabled when AGENT_MOCK_MODE env var is set to 'true'
    or when the agent's project endpoint is not properly configured.

    Args:
        agent_name: Which agent to check ("invoice_parser" or "email_composer")

    Returns:
        True if mock mode should be used
    """
    mock_mode = os.getenv("AGENT_MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        return True

    # Check agent-specific endpoint
    if agent_name == "invoice_parser":
        endpoint = os.getenv("INVOICE_PARSER_PROJECT_ENDPOINT", "")
    else:
        endpoint = os.getenv("AGENT3_PROJECT_ENDPOINT", "")

    if not endpoint or "your-project" in endpoint:
        logger.warning(f"{agent_name} endpoint not configured, using mock mode")
        return True

    return False


def extract_json_from_response(response_text: str) -> str:
    """Extract JSON from agent response, handling markdown code blocks."""
    text = response_text.strip()

    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        return match.group(1).strip()

    return text


def fix_common_json_issues(json_str: str) -> str:
    """Attempt to fix common JSON formatting issues from LLM responses."""
    fixed = json_str

    # Fix arithmetic expressions in numeric values
    arithmetic_pattern = r':\s*(\d+(?:\.\d+)?\s*[\+\-\*\/]\s*\d+(?:\.\d+)?(?:\s*[\+\-\*\/]\s*\d+(?:\.\d+)?)*)\s*([,\}\]])'

    def replace_arithmetic(m):
        expr = m.group(1)
        suffix = m.group(2)
        try:
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
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    # Fix missing commas between properties
    fixed = re.sub(r'([}\]])\s*(")', r'\1,\2', fixed)
    fixed = re.sub(r'(null|true|false)\s*(")', r'\1,\2', fixed)
    fixed = re.sub(r'(\d)\s*(")', r'\1,\2', fixed)
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    fixed = re.sub(r'"\s+"', '","', fixed)

    # Remove control characters
    fixed = re.sub(r'[\x00-\x1f\x7f]', lambda m: ' ' if m.group(0) in '\t\n\r' else '', fixed)

    return fixed


def repair_json_iteratively(json_str: str, max_iterations: int = 5) -> str:
    """Iteratively repair JSON by finding and fixing errors one at a time."""
    current = json_str

    for iteration in range(max_iterations):
        try:
            json.loads(current)
            return current
        except json.JSONDecodeError as e:
            error_pos = e.pos
            error_msg = e.msg

            logger.debug(f"JSON repair iteration {iteration + 1}: {error_msg} at pos {error_pos}")

            if "Expecting ',' delimiter" in error_msg:
                before_error = current[:error_pos]
                after_error = current[error_pos:]
                if after_error.startswith('"'):
                    current = before_error.rstrip() + ',' + after_error
                    continue

            current = fix_common_json_issues(current)

    return current


def parse_agent_response(response_text: str, agent_name: str, max_retries: int = 3) -> dict:
    """Parse agent response with retry logic and error handling."""
    json_str = extract_json_from_response(response_text)
    original_json_str = json_str

    # First attempt - try direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON parse failed for {agent_name}: {e}")

        if "Extra data" in e.msg and e.pos > 0:
            try:
                truncated = json_str[:e.pos].strip()
                result = json.loads(truncated)
                logger.info(f"Parsed {agent_name} response by truncating extra data at pos {e.pos}")
                return result
            except json.JSONDecodeError:
                pass

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

    # Fourth attempt - try json5
    try:
        import json5
        result = json5.loads(original_json_str)
        logger.info(f"Successfully parsed {agent_name} response using json5")
        return result
    except ImportError:
        logger.warning("json5 not available for fallback parsing")
    except Exception as e:
        logger.warning(f"json5 parsing also failed for {agent_name}: {e}")

    # Final attempt
    logger.error(f"JSON parsing failed after all repair attempts for {agent_name}")
    logger.error(f"Full raw response:\n{response_text}")

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
    """Invoke an Azure AI Foundry agent and return the response."""
    from azure.ai.projects import AIProjectClient

    logger.info(f"Invoking agent: {agent_name} at {project_endpoint}")

    credential = get_credential()

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    agent = project_client.agents.get(agent_name=agent_name)
    logger.info(f"Connected to agent: {agent.name}")

    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": user_message}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    logger.info(f"Agent {agent_name} responded successfully")

    return extract_json_from_response(response.output_text)


# =============================================================================
# Invoice Parser Agent
# =============================================================================

def invoke_invoice_parser(
    invoice_id: str,
    shop_name: str,
    shop_email: str,
    invoice_text: str = "",
    attachment_url: str = "",
    instance_id: Optional[str] = None,
    max_retries: int = 2,
    persona_name: Optional[str] = None
) -> InvoiceParserOutput:
    """Invoke the Invoice Parser Agent to extract structured data from an invoice.

    Args:
        invoice_id: Unique invoice identifier
        shop_name: Repair shop name
        shop_email: Repair shop email address
        invoice_text: Plain text of the invoice
        attachment_url: URL to invoice PDF/document
        instance_id: Optional orchestration instance ID for logging
        max_retries: Maximum number of retries on failure
        persona_name: Optional contractor persona name for prompt injection

    Returns:
        InvoiceParserOutput with parsed invoice data

    Raises:
        Exception: If agent invocation or response parsing fails after all retries
    """
    log_prefix = f"[{instance_id}] " if instance_id else ""
    persona_log = f" as {persona_name}" if persona_name else ""
    logger.info(f"{log_prefix}Invoking Invoice Parser for {invoice_id}{persona_log}")

    encoded_attachment_url = encode_url_if_needed(attachment_url)

    if is_mock_mode("invoice_parser"):
        logger.info(f"{log_prefix}Using mock mode for Invoice Parser")
        response_dict = _get_mock_invoice_parser_response(invoice_id, shop_name, shop_email)
    else:
        prompt = build_invoice_parser_prompt(
            invoice_id=invoice_id,
            shop_name=shop_name,
            shop_email=shop_email,
            invoice_text=invoice_text,
            attachment_url=encoded_attachment_url,
            persona_name=persona_name
        )

        agent_name = os.getenv("INVOICE_PARSER_NAME", "invoice-parser-agent")
        project_endpoint = os.getenv("INVOICE_PARSER_PROJECT_ENDPOINT")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)
                response_dict = parse_agent_response(response_text, agent_name)
                break
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"{log_prefix}Invoice Parser attempt {attempt + 1} failed: {e}. Retrying...")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"{log_prefix}Invoice Parser failed after {max_retries + 1} attempts")
                    raise

    output = InvoiceParserOutput.model_validate(response_dict)
    logger.info(f"{log_prefix}Invoice Parser extracted {len(output.line_items)} line items, total: ${output.total}")

    return output


# =============================================================================
# Email Composer Agent (Agent3)
# =============================================================================

def invoke_email_composer(
    input_data: Agent3Input,
    instance_id: Optional[str] = None,
    max_retries: int = 2,
    persona_name: Optional[str] = None
) -> Agent3Output:
    """Invoke Agent3 (email-composer-agent) for email composition.

    Args:
        input_data: The input data for email composition
        instance_id: Optional orchestration instance ID for logging
        max_retries: Maximum number of retries on failure
        persona_name: Optional contractor persona name

    Returns:
        Agent3Output with composed email

    Raises:
        Exception: If agent invocation or response parsing fails after all retries
    """
    log_prefix = f"[{instance_id}] " if instance_id else ""
    persona_log = f" as {persona_name}" if persona_name else ""
    logger.info(f"{log_prefix}Invoking Email Composer for {input_data.claim_id}{persona_log}")

    if is_mock_mode("email_composer"):
        logger.info(f"{log_prefix}Using mock mode for Agent3 (Email Composer)")
        response_dict = _get_mock_agent3_response(input_data, persona_name=persona_name)
    else:
        prompt = build_agent3_prompt(
            claim_id=input_data.claim_id,
            recipient_name=input_data.recipient_name,
            recipient_email=input_data.recipient_email,
            email_purpose=input_data.email_purpose,
            outcome_summary=input_data.outcome_summary,
            persona_name=persona_name,
            additional_context=input_data.additional_context or "",
            tone=input_data.config.tone,
            length=input_data.config.length,
            empathy=input_data.config.empathy,
            call_to_action=input_data.config.call_to_action,
            template=input_data.config.template or "default"
        )

        agent_name = os.getenv("AGENT3_NAME", "EmailComposerAgent")
        project_endpoint = os.getenv("AGENT3_PROJECT_ENDPOINT")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response_text = invoke_foundry_agent(agent_name, prompt, project_endpoint)
                response_dict = parse_agent_response(response_text, agent_name)
                break
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"{log_prefix}Agent3 attempt {attempt + 1} failed: {e}. Retrying...")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"{log_prefix}Agent3 (Email Composer) failed after {max_retries + 1} attempts")
                    raise

    if "generated_at" not in response_dict:
        response_dict["generated_at"] = datetime.now(timezone.utc).isoformat()

    output = Agent3Output.model_validate(response_dict)
    logger.info(f"{log_prefix}Email Composer generated email: {output.email_subject}")

    return output
