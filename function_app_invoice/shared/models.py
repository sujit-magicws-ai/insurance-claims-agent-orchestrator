"""
Pydantic data models for the Invoice Processing orchestration.

These models define the data structures for:
- Invoice Parser Agent: Parsing repair shop invoices
- Email Composer Agent (Agent3): Composing acknowledgment emails
- Orchestration results
"""

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Invoice Parser Models
# =============================================================================

class InvoiceRequest(BaseModel):
    """Initial request to start invoice orchestration.

    This is the input to the HTTP trigger that starts the orchestration.
    """
    invoice_id: str = Field(..., description="Unique invoice identifier")
    shop_name: str = Field(..., description="Repair shop name")
    shop_email: str = Field(..., description="Repair shop email address")
    attachment_url: str = Field("", description="URL to the invoice PDF/document")
    invoice_text: str = Field("", description="Plain text of the invoice (if not PDF)")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class InvoiceLineItem(BaseModel):
    """A single line item from a parsed invoice."""
    part_number: Optional[str] = Field(None, description="Part number")
    description: str = Field(..., description="Line item description")
    quantity: float = Field(1, description="Quantity")
    unit_price: float = Field(0, description="Unit price")
    labor_hours: Optional[float] = Field(None, description="Labor hours for this item")
    labor_rate: Optional[float] = Field(None, description="Labor rate per hour")
    line_total: float = Field(0, description="Total for this line item")


class ShopInfo(BaseModel):
    """Repair shop information extracted from invoice."""
    shop_name: str = Field(..., description="Shop business name")
    shop_address: Optional[str] = Field(None, description="Shop address")
    shop_phone: Optional[str] = Field(None, description="Shop phone number")
    shop_email: Optional[str] = Field(None, description="Shop email")
    contact_name: Optional[str] = Field(None, description="Contact person name")
    license_number: Optional[str] = Field(None, description="Shop license or ID number")


class VehicleInfo(BaseModel):
    """Vehicle information extracted from invoice."""
    year: Optional[int] = Field(None, description="Vehicle year")
    make: Optional[str] = Field(None, description="Vehicle make")
    model: Optional[str] = Field(None, description="Vehicle model")
    vin: Optional[str] = Field(None, description="Vehicle Identification Number")
    mileage: Optional[int] = Field(None, description="Current mileage/odometer reading")
    license_plate: Optional[str] = Field(None, description="License plate number")


class InvoiceParserOutput(BaseModel):
    """Output from the Invoice Parser Agent.

    Contains the full structured data extracted from a repair shop invoice.
    """
    invoice_id: str = Field(..., description="Unique invoice identifier")
    invoice_number: Optional[str] = Field(None, description="Invoice number from the document")
    invoice_date: Optional[str] = Field(None, description="Invoice date (YYYY-MM-DD)")
    shop_info: ShopInfo = Field(default_factory=lambda: ShopInfo(shop_name="Unknown Shop"),
                                description="Repair shop information")
    vehicle_info: VehicleInfo = Field(default_factory=VehicleInfo, description="Vehicle information")
    line_items: list[InvoiceLineItem] = Field(default_factory=list, description="Parsed line items")
    parts_subtotal: float = Field(0, description="Subtotal for parts")
    labor_subtotal: float = Field(0, description="Subtotal for labor")
    subtotal: float = Field(0, description="Subtotal before tax")
    tax: float = Field(0, description="Tax amount")
    total: float = Field(0, description="Total invoice amount")
    notes: Optional[str] = Field(None, description="Additional notes or observations")


# =============================================================================
# Agent3 Models (Email Composer) — copied from claims app
# =============================================================================

class EmailComposerConfig(BaseModel):
    """Configuration for Email Composer Agent style settings."""
    tone: Literal["formal", "casual", "urgent"] = Field("formal", description="Email tone")
    length: Literal["brief", "standard", "detailed"] = Field("standard", description="Email length")
    empathy: Literal["neutral", "warm", "highly_supportive"] = Field("warm", description="Empathy level")
    call_to_action: Literal["none", "soft", "direct"] = Field("soft", description="Call to action style")
    persona: str = Field("Invoice Processing", description="Name in email signature")
    template: Optional[str] = Field(None, description="Predefined template/format name")


class Agent3Input(BaseModel):
    """Input for Agent3 (email-composer-agent).

    Contains recipient details, content, and style settings for email composition.
    """
    claim_id: str = Field(..., description="Unique identifier (invoice_id)")
    recipient_name: str = Field(..., description="Recipient's name")
    recipient_email: str = Field(..., description="Recipient's email address")
    email_purpose: str = Field(..., description="Purpose of the email")
    outcome_summary: str = Field(..., description="Summary of the outcome to communicate")
    additional_context: Optional[str] = Field(None, description="Additional context for the email")
    config: EmailComposerConfig = Field(default_factory=EmailComposerConfig,
                                        description="Email style configuration")


class Agent3Output(BaseModel):
    """Output from Agent3 (email-composer-agent).

    Contains the composed email ready to be sent.
    """
    claim_id: str = Field(..., description="Unique identifier (invoice_id)")
    email_subject: str = Field(..., description="Composed email subject line")
    email_body: str = Field(..., description="Composed email body")
    recipient_name: str = Field(..., description="Recipient's name")
    recipient_email: str = Field(..., description="Recipient's email address")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When email was generated")


# =============================================================================
# AI Contractor Models (Clone Visualizer)
# =============================================================================

class JobSlot(BaseModel):
    """A single job slot within a contractor."""
    claim_id: str = Field(..., description="Invoice ID occupying this slot")
    progress_pct: int = Field(0, ge=0, le=100, description="Job progress 0-100")
    started_at: str = Field(..., description="ISO timestamp when job was assigned")
    status: Literal["processing", "completed"] = Field("processing", description="Job status")


class ContractorState(BaseModel):
    """Runtime state of a single AI Contractor for dashboard rendering."""
    name: str = Field(..., description="Contractor name")
    color: str = Field(..., description="Hex color for dashboard display")
    capacity: int = Field(..., description="Max concurrent job slots")
    active_jobs: list[JobSlot] = Field(default_factory=list, description="Currently active jobs")
    slots_used: int = Field(0, description="Number of occupied slots")
    jobs_completed: int = Field(0, description="Lifetime completed job count")
    status: Literal["full", "available", "idle"] = Field("idle", description="Current status")
    is_primary: bool = Field(False, description="True for first contractor (never terminated)")


class ContractorPoolState(BaseModel):
    """Runtime state of a contractor pool for one agent stage."""
    agent_id: str = Field(..., description="Agent stage identifier")
    display_name: str = Field(..., description="Human-readable stage name")
    capacity_per_contractor: int = Field(..., description="Max jobs per contractor")
    max_contractors: int = Field(..., description="Max contractors in this pool")
    pending_queue: list[str] = Field(default_factory=list, description="Invoice IDs waiting for a slot")
    pending_count: int = Field(0, description="Number of pending jobs")
    active_contractors: list[ContractorState] = Field(default_factory=list,
                                                       description="Active contractor states")
    contractor_count: int = Field(0, description="Number of active contractors")
    total_jobs_in_flight: int = Field(0, description="Total jobs across all contractors")
    total_completed: int = Field(0, description="Total completed across all contractors")


# =============================================================================
# Orchestration Models
# =============================================================================

class InvoiceOrchestrationResult(BaseModel):
    """Final result of the invoice orchestration.

    Contains results from all stages of the orchestration.
    """
    invoice_id: str = Field(..., description="Unique invoice identifier")
    status: Literal["completed", "error"] = Field(..., description="Final status")
    parser_output: Optional[dict] = Field(None, description="Parsed invoice data")
    email_output: Optional[dict] = Field(None, description="Composed email data")
    email_send_result: Optional[dict] = Field(None, description="Email send result")
    error_message: Optional[str] = Field(None, description="Error message if status is 'error'")
    started_at: Optional[str] = Field(None, description="When orchestration started")
    completed_at: Optional[str] = Field(None, description="When orchestration completed")
