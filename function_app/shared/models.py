"""
Pydantic data models for the HITL orchestration.

These models define the data structures for:
- Agent1 (claim-assistant-agent): Classification
- Agent2 (claim-approval-agent): Adjudication
- HITL approval process
- Orchestration results
"""

from datetime import datetime
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# =============================================================================
# Agent1 Models (Claim Classification)
# =============================================================================

class Agent1Input(BaseModel):
    """Input for Agent1 (claim-assistant-agent).

    Contains the email content and attachment URL for claim classification.
    """
    claim_id: str = Field(..., description="Unique claim identifier")
    email_content: str = Field(..., description="Free-form email content from claimant")
    attachment_url: str = Field(..., description="URL to the claim attachment/document")
    sender_email: str = Field(..., description="Email address of the sender")
    received_date: datetime = Field(default_factory=datetime.utcnow, description="When the email was received")


class ClaimClassification(BaseModel):
    """Classification details from Agent1."""
    claim_type: str = Field(..., description="Primary claim type (VSC, GAP, Tire & Wheel, etc.)")
    sub_type: Optional[str] = Field(None, description="Sub-type (Mechanical, Electrical, etc.)")
    component_category: Optional[str] = Field(None, description="Component category (Transmission, Engine, etc.)")
    urgency: Literal["Standard", "Urgent", "Emergency"] = Field("Standard", description="Urgency level")


class EmailBodyExtraction(BaseModel):
    """Information extracted from the email body by Agent1."""
    claimant_name: Optional[str] = Field(None, description="Name mentioned in email")
    claimant_phone: Optional[str] = Field(None, description="Phone mentioned in email")
    claimant_address: Optional[str] = Field(None, description="Address mentioned in email")
    contract_number: Optional[str] = Field(None, description="Contract number mentioned in email")
    vehicle_year: Optional[int] = Field(None, description="Vehicle year")
    vehicle_make: Optional[str] = Field(None, description="Vehicle make")
    vehicle_model: Optional[str] = Field(None, description="Vehicle model")
    vehicle_vin: Optional[str] = Field(None, description="VIN mentioned in email")
    issue_summary: Optional[str] = Field(None, description="Customer's description of the problem")
    repair_facility: Optional[str] = Field(None, description="Repair facility name mentioned")
    diagnosis: Optional[str] = Field(None, description="Any diagnosis mentioned")
    total_parts: Optional[float] = Field(None, description="Parts cost mentioned")
    total_labor: Optional[float] = Field(None, description="Labor cost mentioned")
    total_estimate: Optional[float] = Field(None, description="Total estimate mentioned")


class ExtractedInfo(BaseModel):
    """Merged extraction info from email body and document (superset).

    Merge rules:
    - claimant_email: Always from sender_email input
    - issue_summary: Prefer email body (customer's own words)
    - All other fields: Prefer document values over email values
    """
    claimant_name: Optional[str] = Field(None, description="Merged: Document > Email")
    claimant_email: Optional[str] = Field(None, description="Always from sender_email")
    claimant_phone: Optional[str] = Field(None, description="Merged: Document > Email")
    claimant_address: Optional[str] = Field(None, description="Merged: Document > Email")
    contract_number: Optional[str] = Field(None, description="Merged: Document > Email")
    vehicle_year: Optional[int] = Field(None, description="Merged: Document > Email")
    vehicle_make: Optional[str] = Field(None, description="Merged: Document > Email")
    vehicle_model: Optional[str] = Field(None, description="Merged: Document > Email")
    vehicle_vin: Optional[str] = Field(None, description="Merged: Document > Email")
    issue_summary: Optional[str] = Field(None, description="Merged: Email > Document (customer's words)")
    repair_facility: Optional[str] = Field(None, description="Merged: Document > Email")
    diagnosis: Optional[str] = Field(None, description="Merged: Document > Email")
    total_parts: Optional[float] = Field(None, description="Merged: Document > Email")
    total_labor: Optional[float] = Field(None, description="Merged: Document > Email")
    total_estimate: Optional[float] = Field(None, description="Merged: Document > Email")


class Agent1Flags(BaseModel):
    """Flags indicating concerns or missing information."""
    requires_human_review: bool = Field(False, description="Whether human review is recommended")
    missing_information: list[str] = Field(default_factory=list, description="List of missing information")
    potential_concerns: list[str] = Field(default_factory=list, description="List of potential concerns")


class DocumentExtraction(BaseModel):
    """Details of document extraction from attachment URL."""
    status: Literal["success", "failed", "not_accessible"] = Field(
        ..., description="Whether document extraction succeeded"
    )
    document_type: Optional[str] = Field(
        None, description="Type of document (claim_form, invoice, diagnostic_report, etc.)"
    )
    summary: Optional[str] = Field(
        None, description="2-3 sentence summary of document content"
    )
    extracted_fields: dict = Field(
        default_factory=dict, description="Key fields extracted from the document"
    )
    notes: Optional[str] = Field(
        None, description="Any issues or observations about the extraction"
    )


class Agent1Output(BaseModel):
    """Output from Agent1 (claim-assistant-agent).

    Contains the classification result, extractions from email and document,
    and merged extracted_info.
    """
    claim_id: str = Field(..., description="Unique claim identifier")
    classification: ClaimClassification = Field(..., description="Claim classification details")
    justification: str = Field(..., description="Justification for the classification")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    flags: Agent1Flags = Field(default_factory=Agent1Flags, description="Flags and concerns")
    email_body_extraction: Optional[EmailBodyExtraction] = Field(
        None, description="Information extracted from email body"
    )
    document_extraction: Optional[DocumentExtraction] = Field(
        None, description="Details of document extraction from attachment"
    )
    extracted_info: ExtractedInfo = Field(
        default_factory=ExtractedInfo, description="Merged extraction (superset of email + document)"
    )


# =============================================================================
# HITL Approval Models
# =============================================================================

class ClaimAmounts(BaseModel):
    """Claim amounts entered by human reviewer in HITL UI."""
    total_parts_cost: float = Field(..., ge=0, description="Total cost of parts")
    total_labor_cost: float = Field(..., ge=0, description="Total cost of labor")
    total_estimate: float = Field(..., ge=0, description="Total repair estimate")
    deductible: float = Field(0, ge=0, description="Deductible amount")


class ApprovalDecision(BaseModel):
    """Manual estimate submission from HITL UI.

    Contains the estimate data entered by the reviewer. The actual approval/rejection
    decision is made by the Claim Adjudicator Agent, not the human reviewer.
    """
    decision: Literal["approved", "rejected"] = Field("approved", description="Defaults to approved (proceed to adjudicator)")
    reviewer: str = Field(..., description="Submitted by (email or identifier)")
    comments: str = Field("", description="Reviewer's comments")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When decision was made")
    claim_amounts: Optional[ClaimAmounts] = Field(None, description="Claim amounts entered by reviewer")
    reviewed_data: dict = Field(default_factory=dict, description="Additional data reviewed/modified")
    claim_data: Optional[dict] = Field(None, description="Complete claim data entered by reviewer for Agent2 input")


# =============================================================================
# Agent2 Models (Claim Adjudication)
# =============================================================================

# Agent2Input is a generic dict - created by external process
# We just pass it through to Agent2

class EvaluationSummary(BaseModel):
    """Summary of the evaluation performed by Agent2."""
    contract_status: str = Field(..., description="Contract status (Active, Expired, etc.)")
    coverage_valid: bool = Field(..., description="Whether coverage is valid")
    mileage_valid: bool = Field(..., description="Whether mileage is within limits")
    estimate_amount: float = Field(..., description="Total estimate amount")
    auto_approve_threshold: float = Field(..., description="Auto-approval threshold")
    within_threshold: bool = Field(..., description="Whether estimate is within threshold")
    facility_authorized: bool = Field(..., description="Whether facility is authorized")
    documents_complete: bool = Field(..., description="Whether all documents are present")


class Agent2Output(BaseModel):
    """Output from Agent2 (claim-approval-agent).

    Contains the adjudication decision and reasoning.
    """
    claim_id: str = Field(..., description="Unique claim identifier")
    decision: str = Field(..., description="Adjudication decision (APPROVED, DENIED, MANUAL_REVIEW, REQUEST_DOCUMENTS, etc.)")
    decision_type: str = Field("AUTO", description="How decision was made (AUTO, MANUAL)")
    approved_amount: Optional[float] = Field(None, description="Approved amount after deductible")
    deductible_applied: Optional[float] = Field(None, description="Deductible amount applied")
    missing_documents: list[Any] = Field(default_factory=list, description="List of missing documents")
    rules_evaluated: list[Any] = Field(default_factory=list, description="Rules that were evaluated (str or dict)")
    rules_passed: list[Any] = Field(default_factory=list, description="Rules that passed (str or dict)")
    rules_failed: list[Any] = Field(default_factory=list, description="Rules that failed (str or dict with rule_id and reason)")
    rules_triggered: list[Any] = Field(default_factory=list, description="Rules that triggered manual review (str or dict)")
    priority: Optional[str] = Field(None, description="Priority if manual review")
    assigned_queue: Optional[str] = Field(None, description="Queue assignment if manual review")
    reason: str = Field(..., description="Detailed reasoning for the decision")
    evaluation_summary: Optional[EvaluationSummary] = Field(None, description="Evaluation summary")


# =============================================================================
# Orchestration Models
# =============================================================================

class ClaimRequest(BaseModel):
    """Initial request to start claim orchestration.

    This is the input to the HTTP trigger that starts the orchestration.
    """
    claim_id: str = Field(..., description="Unique claim identifier")
    email_content: str = Field(..., description="Free-form email content from claimant")
    attachment_url: str = Field(..., description="URL to the claim attachment/document")
    sender_email: str = Field(..., description="Email address of the sender")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class OrchestrationResult(BaseModel):
    """Final result of the orchestration.

    Contains results from all stages of the orchestration.
    """
    claim_id: str = Field(..., description="Unique claim identifier")
    status: Literal["completed", "rejected", "timeout", "error"] = Field(..., description="Final status")
    agent1_output: Optional[Agent1Output] = Field(None, description="Classification result from Agent1")
    approval_decision: Optional[ApprovalDecision] = Field(None, description="Human reviewer decision")
    agent2_input: Optional[dict] = Field(None, description="Structured data sent to Agent2")
    agent2_output: Optional[Agent2Output] = Field(None, description="Adjudication result from Agent2")
    error_message: Optional[str] = Field(None, description="Error message if status is 'error'")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="When orchestration started")
    completed_at: Optional[datetime] = Field(None, description="When orchestration completed")
