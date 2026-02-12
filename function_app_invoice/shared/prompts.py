"""
Prompt templates for Azure AI Foundry agents — Invoice Processing.

These templates are used to construct the plain English prompts
sent to the agents. Data is injected into the templates at runtime.
"""

import random

# =============================================================================
# Contractor Persona Prefix (injected into agent prompts when assigned)
# =============================================================================

CONTRACTOR_PERSONA_PREFIX = """[CONTRACTOR IDENTITY]
You are {contractor_name}, a claims processing specialist at JM&A Group, Fidelity Warranty Services.
Sign off and identify yourself as {contractor_name} in all responses.

---

"""

# =============================================================================
# Agent3 Persona Names and Signature
# =============================================================================

AGENT3_PERSONA_NAMES = [
    "Sarah Mitchell",
    "Michael Thompson",
    "Jennifer Rodriguez",
    "David Chen",
    "Amanda Foster",
    "Robert Williams",
    "Michelle Davis",
    "Christopher Martinez"
]

AGENT3_SIGNATURE_TEMPLATE = """{persona_name}
Claims Department, JM&A Group
Fidelity Warranty Services, Inc.
500 Jim Moran Boulevard, Deerfield Beach, FL 33442
Toll Free: 1-800-327-5172 | Fax: 954-429-2699"""


def get_random_persona() -> str:
    """Get a random persona name from the list."""
    return random.choice(AGENT3_PERSONA_NAMES)


def get_full_signature(persona_name: str = None) -> str:
    """Get the full email signature with persona name.

    Args:
        persona_name: Optional specific name. If None, picks randomly.

    Returns:
        Formatted signature block
    """
    if persona_name is None:
        persona_name = get_random_persona()
    # Strip "AIContractor " prefix for human-readable signature
    display_name = persona_name.removeprefix("AIContractor ")
    return AGENT3_SIGNATURE_TEMPLATE.format(persona_name=display_name)


# =============================================================================
# Invoice Parser Prompt
# =============================================================================

INVOICE_PARSER_SYSTEM_PROMPT = """You are an invoice parsing assistant for a vehicle service contract company.
Your job is to extract structured data from repair shop invoices."""

INVOICE_PARSER_USER_PROMPT_TEMPLATE = """Parse the following repair shop invoice and extract all structured data.

**Invoice ID:** {invoice_id}

**Shop Name:** {shop_name}

**Shop Email:** {shop_email}

**Invoice Content:**
{invoice_text}

**Attachment URL:** {attachment_url}

---

**Instructions:**
1. Extract the repair shop information (name, address, phone, email, contact person, license number)
2. Extract the vehicle information (year, make, model, VIN, mileage, license plate)
3. Extract each line item (part number, description, quantity, unit price, labor hours, labor rate, line total)
4. Calculate subtotals for parts and labor
5. Extract subtotal, tax, and total amounts
6. Extract the invoice number and invoice date
7. If the attachment URL is provided, fetch and parse the PDF content
8. If invoice_text is provided, parse it directly

---

Please provide your analysis as a JSON response with the following structure:
{{
    "invoice_id": "{invoice_id}",
    "invoice_number": "Invoice number from document or null",
    "invoice_date": "YYYY-MM-DD or null",
    "shop_info": {{
        "shop_name": "{shop_name}",
        "shop_address": "Full address or null",
        "shop_phone": "Phone or null",
        "shop_email": "{shop_email}",
        "contact_name": "Contact person or null",
        "license_number": "License/ID number or null"
    }},
    "vehicle_info": {{
        "year": 2023 or null,
        "make": "Make or null",
        "model": "Model or null",
        "vin": "VIN or null",
        "mileage": 45000 or null,
        "license_plate": "Plate or null"
    }},
    "line_items": [
        {{
            "part_number": "Part # or null",
            "description": "Description of work/part",
            "quantity": 1,
            "unit_price": 0.00,
            "labor_hours": null,
            "labor_rate": null,
            "line_total": 0.00
        }}
    ],
    "parts_subtotal": 0.00,
    "labor_subtotal": 0.00,
    "subtotal": 0.00,
    "tax": 0.00,
    "total": 0.00,
    "notes": "Any additional observations or null"
}}

Respond ONLY with the JSON, no additional text."""


# =============================================================================
# Agent3 Prompt (Email Composer)
# =============================================================================

AGENT3_SYSTEM_PROMPT = """You are an email composition assistant for a vehicle service contract (VSC) company.
Your job is to compose professional, clear, and empathetic emails to customers regarding their claims."""

AGENT3_USER_PROMPT_TEMPLATE = """Compose an email with the following details:

**RECIPIENT:**
- Name: {recipient_name}
- Email: {recipient_email}

**EMAIL PURPOSE:**
{email_purpose}

**OUTCOME SUMMARY:**
{outcome_summary}

**ADDITIONAL CONTEXT:**
{additional_context}

**STYLE SETTINGS:**
- Tone: {tone}
- Length: {length}
- Empathy: {empathy}
- Call to Action: {call_to_action}
- Template: {template}

**EMAIL SIGNATURE (use exactly as provided):**
{signature}

---

**Instructions:**
1. Compose a professional email based on the purpose and outcome summary
2. Use the specified tone (formal/casual/urgent)
3. Adjust length based on setting (brief: 2-3 paragraphs, standard: 4-5 paragraphs, detailed: 6+ paragraphs)
4. Apply the empathy level appropriately
5. Include call-to-action based on setting (none: no CTA, soft: suggest next steps, direct: clear action required)
6. IMPORTANT: End the email with the exact signature block provided above (including company details)
7. Include claim reference number if available in the context

---

Please provide your response as a JSON with the following structure:
{{
    "claim_id": "{claim_id}",
    "email_subject": "Clear, concise subject line",
    "email_body": "The complete email body with proper formatting, line breaks, and the full signature block",
    "recipient_name": "{recipient_name}",
    "recipient_email": "{recipient_email}"
}}

Respond ONLY with the JSON, no additional text."""


# =============================================================================
# Helper Functions
# =============================================================================

def build_invoice_parser_prompt(
    invoice_id: str,
    shop_name: str,
    shop_email: str,
    invoice_text: str = "",
    attachment_url: str = "",
    persona_name: str = None
) -> str:
    """Build the complete prompt for the Invoice Parser Agent.

    Args:
        invoice_id: Unique invoice identifier
        shop_name: Repair shop name
        shop_email: Repair shop email
        invoice_text: Plain text content of the invoice
        attachment_url: URL to the invoice PDF/document
        persona_name: Optional contractor persona name to prepend

    Returns:
        Formatted prompt string for the Invoice Parser Agent
    """
    prefix = ""
    if persona_name:
        display_name = persona_name.removeprefix("AIContractor ")
        prefix = CONTRACTOR_PERSONA_PREFIX.format(contractor_name=display_name)
    return prefix + INVOICE_PARSER_USER_PROMPT_TEMPLATE.format(
        invoice_id=invoice_id,
        shop_name=shop_name,
        shop_email=shop_email,
        invoice_text=invoice_text or "(No text provided — see attachment)",
        attachment_url=attachment_url or "(No attachment URL provided)"
    )


def build_agent3_prompt(
    claim_id: str,
    recipient_name: str,
    recipient_email: str,
    email_purpose: str,
    outcome_summary: str,
    persona_name: str = None,
    additional_context: str = "",
    tone: str = "formal",
    length: str = "standard",
    empathy: str = "warm",
    call_to_action: str = "soft",
    template: str = "default"
) -> str:
    """Build the complete prompt for Agent3 (Email Composer).

    Args:
        claim_id: Unique identifier (invoice_id)
        recipient_name: Recipient's name
        recipient_email: Recipient's email address
        email_purpose: Purpose of the email
        outcome_summary: Summary of the outcome to communicate
        persona_name: Name for signature (if None, picks randomly)
        additional_context: Additional context for the email
        tone: Email tone (formal/casual/urgent)
        length: Email length (brief/standard/detailed)
        empathy: Empathy level (neutral/warm/highly_supportive)
        call_to_action: CTA style (none/soft/direct)
        template: Predefined template name

    Returns:
        Formatted prompt string for Agent3
    """
    # Get full signature with persona name (random if not specified)
    signature = get_full_signature(persona_name)

    prefix = ""
    if persona_name:
        display_name = persona_name.removeprefix("AIContractor ")
        prefix = CONTRACTOR_PERSONA_PREFIX.format(contractor_name=display_name)

    return prefix + AGENT3_USER_PROMPT_TEMPLATE.format(
        claim_id=claim_id,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        email_purpose=email_purpose,
        outcome_summary=outcome_summary,
        signature=signature,
        additional_context=additional_context or "None provided",
        tone=tone,
        length=length,
        empathy=empathy,
        call_to_action=call_to_action,
        template=template or "default"
    )
