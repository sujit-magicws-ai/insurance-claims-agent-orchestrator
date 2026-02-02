"""
Tests for Pydantic models and shared utilities.

Run with: python -m pytest tests/test_models.py -v
Or: python tests/test_models.py (for direct execution)
"""

import json
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.models import (
    Agent1Input,
    Agent1Output,
    ClaimClassification,
    ExtractedInfo,
    Agent1Flags,
    ApprovalDecision,
    ClaimAmounts,
    Agent2Output,
    EvaluationSummary,
    ClaimRequest,
    OrchestrationResult,
)
from shared.prompts import build_agent1_prompt, build_agent2_prompt
from shared.agent_client import is_mock_mode, invoke_agent1, invoke_agent2


def test_agent1_input_valid():
    """Test Agent1Input with valid data."""
    input_data = Agent1Input(
        claim_id="CLM-2026-00142",
        email_content="Hi, I'm submitting a claim for my 2022 Honda Accord...",
        attachment_url="https://storage.example.com/claims/doc.pdf",
        sender_email="john.smith@email.com"
    )
    assert input_data.claim_id == "CLM-2026-00142"
    assert "Honda Accord" in input_data.email_content
    print("  [PASS] Agent1Input validation")


def test_agent1_input_missing_required():
    """Test Agent1Input fails with missing required fields."""
    try:
        Agent1Input(
            claim_id="CLM-001",
            # Missing email_content, attachment_url, sender_email
        )
        print("  [FAIL] Should have raised validation error")
        return False
    except Exception as e:
        assert "email_content" in str(e) or "Field required" in str(e)
        print("  [PASS] Agent1Input rejects missing fields")
        return True


def test_agent1_output_valid():
    """Test Agent1Output with valid data."""
    output_data = Agent1Output(
        claim_id="CLM-2026-00142",
        classification=ClaimClassification(
            claim_type="VSC",
            sub_type="Mechanical",
            component_category="Transmission",
            urgency="Standard"
        ),
        justification="This is a VSC mechanical claim for transmission issues.",
        extracted_info=ExtractedInfo(
            claimant_name="John Smith",
            claimant_email="john.smith@email.com",
            claimant_phone="555-123-4567",
            vehicle_year=2022,
            vehicle_make="Honda",
            vehicle_model="Accord",
            issue_summary="Transmission grinding noise",
            repair_facility="ABC Auto Service",
            total_estimate=767.50
        ),
        confidence_score=0.92,
        flags=Agent1Flags(
            requires_human_review=False,
            missing_information=[],
            potential_concerns=[]
        )
    )
    assert output_data.classification.claim_type == "VSC"
    assert output_data.confidence_score == 0.92
    assert output_data.extracted_info.claimant_email == "john.smith@email.com"
    print("  [PASS] Agent1Output validation")


def test_agent1_output_confidence_bounds():
    """Test Agent1Output confidence_score must be 0-1."""
    try:
        Agent1Output(
            claim_id="CLM-001",
            classification=ClaimClassification(claim_type="VSC"),
            justification="Test",
            confidence_score=1.5  # Invalid: > 1.0
        )
        print("  [FAIL] Should have raised validation error for confidence > 1.0")
        return False
    except Exception:
        print("  [PASS] Agent1Output rejects confidence > 1.0")
        return True


def test_approval_decision_valid():
    """Test ApprovalDecision with valid data."""
    decision = ApprovalDecision(
        decision="approved",
        reviewer="reviewer@company.com",
        comments="Claim looks good",
        claim_amounts=ClaimAmounts(
            total_parts_cost=330.00,
            total_labor_cost=437.50,
            total_estimate=767.50,
            deductible=100.00
        )
    )
    assert decision.decision == "approved"
    assert decision.claim_amounts.total_estimate == 767.50
    print("  [PASS] ApprovalDecision validation")


def test_approval_decision_invalid_choice():
    """Test ApprovalDecision rejects invalid decision values."""
    try:
        ApprovalDecision(
            decision="maybe",  # Invalid: must be "approved" or "rejected"
            reviewer="test@test.com"
        )
        print("  [FAIL] Should have raised validation error")
        return False
    except Exception:
        print("  [PASS] ApprovalDecision rejects invalid decision")
        return True


def test_agent2_output_valid():
    """Test Agent2Output with valid data."""
    output = Agent2Output(
        claim_id="CLM-2026-00142",
        decision="APPROVED",
        decision_type="AUTO",
        approved_amount=667.50,
        deductible_applied=100.00,
        rules_evaluated=["AA-01", "AA-02", "AA-03"],
        rules_passed=["AA-01", "AA-02", "AA-03"],
        rules_failed=[],
        reason="All rules passed, claim auto-approved."
    )
    assert output.decision == "APPROVED"
    assert output.approved_amount == 667.50
    print("  [PASS] Agent2Output validation")


def test_orchestration_result_valid():
    """Test OrchestrationResult with valid data."""
    result = OrchestrationResult(
        claim_id="CLM-2026-00142",
        status="completed",
        agent1_output=Agent1Output(
            claim_id="CLM-2026-00142",
            classification=ClaimClassification(claim_type="VSC"),
            justification="VSC claim",
            confidence_score=0.9
        ),
        approval_decision=ApprovalDecision(
            decision="approved",
            reviewer="test@test.com"
        ),
        agent2_output=Agent2Output(
            claim_id="CLM-2026-00142",
            decision="APPROVED",
            decision_type="AUTO",
            approved_amount=667.50,
            reason="Approved"
        )
    )
    assert result.status == "completed"
    assert result.agent1_output is not None
    assert result.agent2_output.decision == "APPROVED"
    print("  [PASS] OrchestrationResult validation")


def test_json_serialization():
    """Test models can serialize to JSON and back."""
    original = Agent1Output(
        claim_id="CLM-001",
        classification=ClaimClassification(claim_type="VSC", urgency="Urgent"),
        justification="Test justification",
        confidence_score=0.88
    )

    # Serialize to JSON
    json_str = original.model_dump_json()

    # Deserialize back
    restored = Agent1Output.model_validate_json(json_str)

    assert restored.claim_id == original.claim_id
    assert restored.classification.claim_type == original.classification.claim_type
    assert restored.confidence_score == original.confidence_score
    print("  [PASS] JSON serialization round-trip")


def test_build_agent1_prompt():
    """Test Agent1 prompt building."""
    prompt = build_agent1_prompt(
        claim_id="CLM-001",
        email_content="Test email content",
        attachment_url="https://example.com/doc.pdf",
        sender_email="test@test.com",
        received_date="2026-02-01T10:00:00Z"
    )
    assert "CLM-001" in prompt
    assert "Test email content" in prompt
    assert "https://example.com/doc.pdf" in prompt
    print("  [PASS] build_agent1_prompt")


def test_build_agent2_prompt():
    """Test Agent2 prompt building."""
    claim_data = {"claim_id": "CLM-001", "repair": {"total_estimate": 500}}
    prompt = build_agent2_prompt(
        claim_id="CLM-001",
        claim_data_json=json.dumps(claim_data)
    )
    assert "CLM-001" in prompt
    assert "total_estimate" in prompt
    print("  [PASS] build_agent2_prompt")


def test_mock_mode_detection():
    """Test mock mode detection."""
    # Should be in mock mode since endpoint is not configured
    assert is_mock_mode() == True
    print("  [PASS] Mock mode detection (endpoint not configured)")


def test_invoke_agent1_mock():
    """Test Agent1 invocation in mock mode."""
    input_data = Agent1Input(
        claim_id="CLM-TEST-001",
        email_content="Test claim for Honda Accord transmission issue",
        attachment_url="https://example.com/doc.pdf",
        sender_email="test@test.com"
    )

    output = invoke_agent1(input_data, instance_id="test-instance")

    assert output.claim_id == "CLM-TEST-001"
    assert output.classification.claim_type == "VSC"
    assert "[MOCK]" in output.justification
    print("  [PASS] invoke_agent1 mock mode")


def test_invoke_agent2_mock():
    """Test Agent2 invocation in mock mode."""
    claim_data = {
        "claim_id": "CLM-TEST-001",
        "repair": {
            "total_estimate": 767.50
        },
        "contract": {
            "deductible": 100
        }
    }

    output = invoke_agent2("CLM-TEST-001", claim_data, instance_id="test-instance")

    assert output.claim_id == "CLM-TEST-001"
    assert output.decision == "APPROVED"
    assert output.approved_amount == 667.50  # 767.50 - 100
    assert "[MOCK]" in output.reason
    print("  [PASS] invoke_agent2 mock mode")


def run_all_tests():
    """Run all tests and print summary."""
    print("\n" + "=" * 60)
    print("Phase 2 Tests: Data Models & Shared Utilities")
    print("=" * 60)

    tests = [
        ("Agent1Input validation", test_agent1_input_valid),
        ("Agent1Input missing fields", test_agent1_input_missing_required),
        ("Agent1Output validation", test_agent1_output_valid),
        ("Agent1Output confidence bounds", test_agent1_output_confidence_bounds),
        ("ApprovalDecision validation", test_approval_decision_valid),
        ("ApprovalDecision invalid choice", test_approval_decision_invalid_choice),
        ("Agent2Output validation", test_agent2_output_valid),
        ("OrchestrationResult validation", test_orchestration_result_valid),
        ("JSON serialization", test_json_serialization),
        ("build_agent1_prompt", test_build_agent1_prompt),
        ("build_agent2_prompt", test_build_agent2_prompt),
        ("Mock mode detection", test_mock_mode_detection),
        ("invoke_agent1 mock", test_invoke_agent1_mock),
        ("invoke_agent2 mock", test_invoke_agent2_mock),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\nTest: {name}")
        try:
            result = test_func()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
