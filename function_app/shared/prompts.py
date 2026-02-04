"""
Prompt templates for Azure AI Foundry agents.

These templates are used to construct the plain English prompts
sent to the agents. Data is injected into the templates at runtime.
"""

import random

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
    return AGENT3_SIGNATURE_TEMPLATE.format(persona_name=persona_name)

# =============================================================================
# Agent1 Prompt (Claim Classification)
# =============================================================================

AGENT1_SYSTEM_PROMPT = """You are a claims classification assistant for a vehicle service contract (VSC) company.
Your job is to analyze incoming claim emails and classify them appropriately."""

AGENT1_USER_PROMPT_TEMPLATE = """Analyze the following claim email and attachment to classify the claim type.

**Email Content:**
{email_content}

**Attachment URL:** {attachment_url}

**Sender Email:** {sender_email}

**Received Date:** {received_date}

---

**Contract Types and Coverage:**

1. **VSC (Vehicle Service Contract):**
   - Covers: Mechanical/electrical component failures and breakdowns
   - Components: Engine, transmission, AC, alternator, starter, electrical systems
   - Sub-types: Mechanical, Electrical
   - Benefits: Roadside assistance, travel protection, alternate transportation
   - NOT covered: Maintenance, wear & tear, accidents, cosmetic damage
   - Indicators: Component failure, breakdown, won't start, overheating, grinding noise, check engine light

2. **GAP (Total Loss Protection):**
   - Covers: Difference between loan balance and vehicle value on total loss
   - Triggered by: Unrecovered theft, vehicle totaled in accident
   - NOT covered: Mechanical failures, maintenance, partial damage
   - Indicators: Total loss, vehicle totaled, theft, insurance payout, loan balance

3. **Tire & Wheel / Road Hazard:**
   - Covers: Tire and wheel damage from road hazards
   - Examples: Flat tire, puncture, bent rim, pothole damage, debris damage
   - NOT covered: Normal wear, improper inflation, cosmetic
   - Indicators: Flat tire, bent wheel, pothole, road debris, tire damage, blowout

4. **PPM (Pre-Paid Maintenance):**
   - Covers: Scheduled maintenance per manufacturer guidelines
   - Services: Oil change, tire rotation, filters, inspections, brake adjustment
   - NOT covered: Repairs, component failures
   - Indicators: Oil change, routine service, scheduled maintenance, tire rotation

5. **Appearance Protection:**
   - Covers: Interior/exterior cosmetic damage
   - Examples: Dents, dings, scratches, paint damage, windshield chips, interior stains
   - NOT covered: Mechanical failures, major collision damage
   - Indicators: Dent, scratch, windshield chip, paint damage, interior damage, rust

6. **Theft Protection:**
   - Covers: Financial protection if vehicle stolen and not recovered
   - Benefit: Up to $5,000 if unrecovered after 30 days
   - NOT covered: Mechanical issues, partial theft
   - Indicators: Vehicle stolen, theft, car missing, unrecovered

7. **Other:**
   - Use when claim doesn't clearly fit above categories
   - Always flag for human review

---

**Instructions:**
1. Extract information from the email body (email_body_extraction)
2. Fetch and extract content from the attachment URL (document_extraction)
3. Merge both extractions into extracted_info using the merge rules below
4. Classify the claim based on the contract types above
5. If the document cannot be accessed, set document_extraction.status to "not_accessible"

**Merge Rules for extracted_info:**
- claimant_email: ALWAYS use the Sender Email ({sender_email})
- issue_summary: Prefer email body (customer's own words)
- All other fields: Prefer document values over email values
- If document extraction failed, use email body values as fallback

---

Please provide your analysis as a JSON response with the following structure:
{{
    "claim_id": "{claim_id}",
    "classification": {{
        "claim_type": "VSC | GAP | Tire & Wheel | PPM | Appearance | Theft | Other",
        "sub_type": "Mechanical | Electrical | Road Hazard | Maintenance | Cosmetic | Other | null",
        "component_category": "Transmission | Engine | Brakes | Tire | Wheel | Windshield | Interior | Exterior | etc. | null",
        "urgency": "Standard | Urgent | Emergency"
    }},
    "justification": "Your detailed justification referencing the contract type criteria above",
    "confidence_score": 0.0 to 1.0,
    "flags": {{
        "requires_human_review": true/false,
        "missing_information": ["list of missing items"],
        "potential_concerns": ["list of concerns"]
    }},
    "email_body_extraction": {{
        "claimant_name": "Name mentioned in email or null",
        "claimant_phone": "Phone mentioned in email or null",
        "claimant_address": "Address mentioned in email or null",
        "contract_number": "Contract number mentioned in email or null",
        "vehicle_year": 2023 or null,
        "vehicle_make": "Make or null",
        "vehicle_model": "Model or null",
        "vehicle_vin": "VIN mentioned in email or null",
        "current_odometer": 45000 or null,
        "date_of_loss": "YYYY-MM-DD or null",
        "issue_summary": "Customer's description of the problem in their own words",
        "repair_facility": "Facility name mentioned in email or null",
        "diagnosis": "Any diagnosis mentioned or null",
        "lienholder": "Lienholder/financing company or null"
    }},
    "document_extraction": {{
        "status": "success | failed | not_accessible",
        "document_type": "claim_form | damage_photos | invoice | unknown | null",
        "summary": "2-3 sentence summary of the document content",
        "extracted_fields": {{
            "claimant_name": "Name from document or null",
            "claimant_phone": "Phone from document or null",
            "claimant_address": "Full address from document or null",
            "contract_number": "Contract number from document or null",
            "vehicle_year": 2023 or null,
            "vehicle_make": "Make or null",
            "vehicle_model": "Model or null",
            "vehicle_vin": "VIN from document or null",
            "current_odometer": 45000 or null,
            "date_of_loss": "YYYY-MM-DD or null",
            "issue_summary": "Issue description from document or null",
            "repair_facility": "Facility name and address from document or null",
            "diagnosis": "Diagnosis from document or null",
            "lienholder": "Lienholder/financing company or null"
        }},
        "notes": "Any issues accessing or parsing the document, or additional observations"
    }},
    "extracted_info": {{
        "claimant_name": "Merged: Document > Email",
        "claimant_email": "{sender_email}",
        "claimant_phone": "Merged: Document > Email",
        "claimant_address": "Merged: Document > Email",
        "contract_number": "Merged: Document > Email",
        "vehicle_year": "Merged: Document > Email",
        "vehicle_make": "Merged: Document > Email",
        "vehicle_model": "Merged: Document > Email",
        "vehicle_vin": "Merged: Document > Email",
        "current_odometer": "Merged: Document > Email",
        "date_of_loss": "Merged: Document > Email",
        "issue_summary": "Merged: Email > Document (customer's own words preferred)",
        "repair_facility": "Merged: Document > Email",
        "diagnosis": "Merged: Document > Email",
        "lienholder": "Merged: Document > Email"
    }}
}}

Respond ONLY with the JSON, no additional text."""


# =============================================================================
# Agent2 Prompt (Claim Adjudication)
# =============================================================================

AGENT2_SYSTEM_PROMPT = """You are a claims adjudication assistant for a vehicle service contract (VSC) company.
Your job is to evaluate claims against coverage rules and provide approval decisions."""

AGENT2_USER_PROMPT_TEMPLATE = """Evaluate the following claim data and provide an adjudication decision.

**Claim Data:**
```json
{claim_data_json}
```

---

**Evaluation Rules:**
1. AA-01: Contract must be in Active status
2. AA-02: Claim date must be within coverage period
3. AA-03: Vehicle mileage must be within coverage limits
4. AA-04: All required documents must be present (damage photos, claim form)
5. AA-05: Repair must be performed at an authorized facility for full coverage
6. AA-06: Claim amount must be within coverage limits
7. AA-07: No pre-existing conditions
8. AA-08: Component must be covered under the contract type

**Auto-Approval Thresholds:**
- VSC claims under $1,500 with all documents: AUTO-APPROVE
- Claims over $5,000: Require MANUAL_REVIEW
- Claims with missing documents: Require MANUAL_REVIEW

---

Provide your decision as a JSON response with the following structure:
{{
    "claim_id": "{claim_id}",
    "decision": "APPROVED | DENIED | MANUAL_REVIEW",
    "decision_type": "AUTO | MANUAL",
    "approved_amount": 0.00,
    "deductible_applied": 0.00,
    "missing_documents": ["list of missing documents"],
    "rules_evaluated": ["AA-01", "AA-02", ...],
    "rules_passed": ["AA-01", ...],
    "rules_failed": ["AA-03", ...],
    "rules_triggered": ["rules that triggered manual review"],
    "priority": "High | Medium | Low | null",
    "assigned_queue": "queue name or null",
    "reason": "Detailed explanation of your decision",
    "evaluation_summary": {{
        "contract_status": "Active | Expired | etc.",
        "coverage_valid": true/false,
        "mileage_valid": true/false,
        "estimate_amount": 0.00,
        "auto_approve_threshold": 1500,
        "within_threshold": true/false,
        "facility_authorized": true/false,
        "documents_complete": true/false
    }}
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

def build_agent1_prompt(
    claim_id: str,
    email_content: str,
    attachment_url: str,
    sender_email: str,
    received_date: str
) -> str:
    """Build the complete prompt for Agent1.

    Args:
        claim_id: Unique claim identifier
        email_content: The email content from the claimant
        attachment_url: URL to the attachment
        sender_email: Sender's email address
        received_date: When the email was received

    Returns:
        Formatted prompt string for Agent1
    """
    return AGENT1_USER_PROMPT_TEMPLATE.format(
        claim_id=claim_id,
        email_content=email_content,
        attachment_url=attachment_url,
        sender_email=sender_email,
        received_date=received_date
    )


def build_agent2_prompt(claim_id: str, claim_data_json: str) -> str:
    """Build the complete prompt for Agent2.

    Args:
        claim_id: Unique claim identifier
        claim_data_json: The structured claim data as a JSON string

    Returns:
        Formatted prompt string for Agent2
    """
    return AGENT2_USER_PROMPT_TEMPLATE.format(
        claim_id=claim_id,
        claim_data_json=claim_data_json
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
        claim_id: Unique claim identifier
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

    return AGENT3_USER_PROMPT_TEMPLATE.format(
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
