"""
Test suite for ContractorPool and ContractorManager.

Covers all 13 scenarios from the Clone Visualizer Dev Plan Phase 1.
Run from function_app directory:
    python -m tests.test_contractor_manager
"""

import json
import sys

# Track test results
passed = 0
failed = 0


def assert_eq(actual, expected, msg=""):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {msg}")
        print(f"    Expected: {expected}")
        print(f"    Actual:   {actual}")


def assert_true(value, msg=""):
    global passed, failed
    if value:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {msg}")
        print(f"    Expected truthy, got: {value}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# =========================================================================
# Import (must be done after sys.path setup if needed)
# =========================================================================
from shared.contractor_manager import ContractorPool, ContractorManager


# =========================================================================
# Test ContractorPool directly (classifier config: capacity=3, max=5)
# =========================================================================

def new_pool() -> ContractorPool:
    """Create a fresh classifier pool for testing."""
    return ContractorPool(
        agent_id="test-classifier",
        display_name="Test Classifier",
        capacity=3,
        max_contractors=5,
        contractor_defs=[
            {"name": "Alice", "color": "#2dd4a8"},
            {"name": "Bob", "color": "#7c5cfc"},
            {"name": "Priya", "color": "#f59e0b"},
            {"name": "David", "color": "#38bdf8"},
            {"name": "Mei", "color": "#c084fc"},
        ],
    )


# ---- Test 1: Assign 1 job — Alice gets it (1/3) ----
section("Test 1: Assign 1 job to classifier")
pool = new_pool()
result = pool.assign_job("CLM-001")
assert_eq(result, "Alice", "First job should go to Alice")
state = pool.get_state()
assert_eq(state["active_contractors"][0]["slots_used"], 1, "Alice should have 1 slot used")
assert_eq(state["active_contractors"][0]["status"], "available", "Alice should be available")
print(f"  Alice has {state['active_contractors'][0]['slots_used']}/3 slots -> PASS")


# ---- Test 2: Assign 3 jobs — Alice full (3/3) ----
section("Test 2: Assign 3 jobs — Alice full")
pool = new_pool()
r1 = pool.assign_job("CLM-001")
r2 = pool.assign_job("CLM-002")
r3 = pool.assign_job("CLM-003")
assert_eq(r1, "Alice", "Job 1 -> Alice")
assert_eq(r2, "Alice", "Job 2 -> Alice")
assert_eq(r3, "Alice", "Job 3 -> Alice")
state = pool.get_state()
assert_eq(state["active_contractors"][0]["slots_used"], 3, "Alice should have 3 slots used")
assert_eq(state["active_contractors"][0]["status"], "full", "Alice should be full")
assert_eq(state["contractor_count"], 1, "Still only 1 contractor")
print(f"  Alice is {state['active_contractors'][0]['status']} ({state['active_contractors'][0]['slots_used']}/3) -> PASS")


# ---- Test 3: Assign 4th job — Bob spawns ----
section("Test 3: Assign 4th job — Bob spawns")
pool = new_pool()
for i in range(1, 4):
    pool.assign_job(f"CLM-{i:03d}")
r4 = pool.assign_job("CLM-004")
assert_eq(r4, "Bob", "Job 4 should go to Bob")
state = pool.get_state()
assert_eq(state["contractor_count"], 2, "Should be 2 contractors now")
assert_eq(state["active_contractors"][1]["name"], "Bob", "Second contractor should be Bob")
assert_eq(state["active_contractors"][1]["slots_used"], 1, "Bob should have 1 slot")
print(f"  Bob spawned with {state['active_contractors'][1]['slots_used']}/3 slots -> PASS")


# ---- Test 4: Fill Bob (jobs 5-6) ----
section("Test 4: Fill Bob — jobs 5-6")
pool = new_pool()
for i in range(1, 4):
    pool.assign_job(f"CLM-{i:03d}")
pool.assign_job("CLM-004")
r5 = pool.assign_job("CLM-005")
r6 = pool.assign_job("CLM-006")
assert_eq(r5, "Bob", "Job 5 -> Bob")
assert_eq(r6, "Bob", "Job 6 -> Bob")
state = pool.get_state()
assert_eq(state["active_contractors"][1]["slots_used"], 3, "Bob should have 3 slots")
assert_eq(state["active_contractors"][1]["status"], "full", "Bob should be full")
print(f"  Bob is {state['active_contractors'][1]['status']} ({state['active_contractors'][1]['slots_used']}/3) -> PASS")


# ---- Test 5: Assign 7th job — Priya spawns ----
section("Test 5: Assign 7th job — Priya spawns")
pool = new_pool()
for i in range(1, 7):
    pool.assign_job(f"CLM-{i:03d}")
r7 = pool.assign_job("CLM-007")
assert_eq(r7, "Priya", "Job 7 should go to Priya")
state = pool.get_state()
assert_eq(state["contractor_count"], 3, "Should be 3 contractors now")
assert_eq(state["active_contractors"][2]["name"], "Priya", "Third contractor is Priya")
print(f"  Priya spawned -> PASS")


# ---- Test 6: Complete all Bob's jobs — Bob terminated ----
section("Test 6: Complete all Bob's jobs — Bob terminated")
pool = new_pool()
for i in range(1, 8):
    pool.assign_job(f"CLM-{i:03d}")
# State: Alice [1,2,3] Bob [4,5,6] Priya [7]

# Complete Bob's jobs
pool.complete_job("CLM-004")
pool.complete_job("CLM-005")
pool.complete_job("CLM-006")

state = pool.get_state()
contractor_names = [c["name"] for c in state["active_contractors"]]
assert_true("Bob" not in contractor_names, "Bob should be terminated (empty, not primary)")
assert_true("Alice" in contractor_names, "Alice should still be active")
assert_true("Priya" in contractor_names, "Priya should still be active (has CLM-007)")
print(f"  Active contractors: {contractor_names} -> PASS")


# ---- Test 7: Complete Priya's jobs — Priya terminated (reverse order) ----
section("Test 7: Complete Priya's jobs — Priya terminated")
# Continue from test 6 state: Alice [1,2,3], Priya [7]
pool.complete_job("CLM-007")

state = pool.get_state()
contractor_names = [c["name"] for c in state["active_contractors"]]
assert_true("Priya" not in contractor_names, "Priya should be terminated (empty, not primary)")
assert_eq(len(contractor_names), 1, "Only Alice should remain")
assert_eq(contractor_names[0], "Alice", "Alice is the sole remaining contractor")
print(f"  Active contractors: {contractor_names} -> PASS")


# ---- Test 8: Complete all Alice's jobs — Alice stays (primary) ----
section("Test 8: Complete all Alice's jobs — Alice stays (primary)")
pool.complete_job("CLM-001")
pool.complete_job("CLM-002")
pool.complete_job("CLM-003")

state = pool.get_state()
assert_eq(state["contractor_count"], 1, "Still 1 contractor (Alice stays)")
assert_eq(state["active_contractors"][0]["name"], "Alice", "Alice is the primary")
assert_eq(state["active_contractors"][0]["status"], "idle", "Alice should be idle (0 jobs)")
assert_eq(state["active_contractors"][0]["is_primary"], True, "Alice is primary")
assert_eq(state["active_contractors"][0]["slots_used"], 0, "Alice has 0 jobs")
print(f"  Alice status: {state['active_contractors'][0]['status']}, primary={state['active_contractors'][0]['is_primary']} -> PASS")


# ---- Test 9: Assign job after scale-down — Alice gets it ----
section("Test 9: Assign job after scale-down — first-fill resumes")
result = pool.assign_job("CLM-100")
assert_eq(result, "Alice", "After scale-down, new job goes to Alice")
state = pool.get_state()
assert_eq(state["contractor_count"], 1, "Still just Alice")
assert_eq(state["active_contractors"][0]["slots_used"], 1, "Alice has 1 job")
print(f"  Alice picked up job after scale-down -> PASS")


# ---- Test 10: Fill all 5 contractors (15 jobs) ----
section("Test 10: Fill all 5 contractors (15 jobs)")
pool = new_pool()
expected_assignments = {
    "Alice": [],
    "Bob": [],
    "Priya": [],
    "David": [],
    "Mei": [],
}

for i in range(1, 16):
    claim_id = f"CLM-{i:03d}"
    contractor = pool.assign_job(claim_id)
    assert_true(contractor is not None, f"Job {claim_id} should be assigned (not queued)")
    expected_assignments[contractor].append(claim_id)

state = pool.get_state()
assert_eq(state["contractor_count"], 5, "All 5 contractors should be active")
assert_eq(state["total_jobs_in_flight"], 15, "15 jobs in flight")
for c in state["active_contractors"]:
    assert_eq(c["slots_used"], 3, f"{c['name']} should have 3/3 slots")
    assert_eq(c["status"], "full", f"{c['name']} should be full")
print(f"  All 5 contractors full (15 jobs) -> PASS")


# ---- Test 11: Assign 16th job — queued ----
section("Test 11: Assign 16th job — queued in pending")
result = pool.assign_job("CLM-016")
assert_eq(result, None, "Job 16 should return None (queued)")
state = pool.get_state()
assert_eq(state["pending_count"], 1, "Pending queue should have 1 job")
assert_eq(state["pending_queue"], ["CLM-016"], "CLM-016 should be in pending")
print(f"  CLM-016 queued (pending={state['pending_count']}) -> PASS")


# ---- Test 12: Complete 1 job when pending — auto-assigned ----
section("Test 12: Complete 1 job when pending — pending auto-assigned")
pool.complete_job("CLM-001")  # Free Alice slot 1
state = pool.get_state()
assert_eq(state["pending_count"], 0, "Pending queue should be empty (auto-assigned)")

# CLM-016 should now be assigned to Alice (first-fill)
alice_jobs = [j["claim_id"] for j in state["active_contractors"][0]["active_jobs"]]
assert_true("CLM-016" in alice_jobs, "CLM-016 should be assigned to Alice (first-fill)")
print(f"  CLM-016 auto-assigned to Alice from pending -> PASS")


# ---- Test 13: get_state() returns correct JSON ----
section("Test 13: get_state() returns valid JSON matching schema")
pool = new_pool()
pool.assign_job("CLM-X01")
pool.assign_job("CLM-X02")
state = pool.get_state()

# Verify all expected keys exist
required_pool_keys = [
    "agent_id", "display_name", "capacity_per_contractor", "max_contractors",
    "pending_queue", "pending_count", "active_contractors", "contractor_count",
    "total_jobs_in_flight", "total_completed"
]
for key in required_pool_keys:
    assert_true(key in state, f"Pool state should have key '{key}'")

# Verify contractor state keys
c = state["active_contractors"][0]
required_contractor_keys = [
    "name", "color", "capacity", "active_jobs", "slots_used",
    "jobs_completed", "status", "is_primary"
]
for key in required_contractor_keys:
    assert_true(key in c, f"Contractor state should have key '{key}'")

# Verify job slot keys
j = c["active_jobs"][0]
required_job_keys = ["claim_id", "progress_pct", "started_at", "status"]
for key in required_job_keys:
    assert_true(key in j, f"Job slot should have key '{key}'")

# Verify JSON serializable
json_str = json.dumps(state)
assert_true(len(json_str) > 0, "State should be JSON serializable")

# Validate with Pydantic model
from shared.models import ContractorPoolState
validated = ContractorPoolState.model_validate(state)
assert_eq(validated.agent_id, "test-classifier", "Pydantic model should validate")

print(f"  State has all required keys and is JSON serializable -> PASS")


# =========================================================================
# Test ContractorManager singleton
# =========================================================================

section("Test 14 (Bonus): ContractorManager singleton + all pools")
ContractorManager.reset()
mgr = ContractorManager()

# Verify 3 pools exist
assert_eq(set(mgr.pools.keys()), {"classifier", "adjudicator", "email_composer"}, "3 pools exist")

# Assign across pools
c1 = mgr.assign_job("classifier", "CLM-M01")
c2 = mgr.assign_job("adjudicator", "CLM-M02")
c3 = mgr.assign_job("email_composer", "CLM-M03")
assert_eq(c1, "Alice", "Classifier -> Alice")
assert_eq(c2, "Alice", "Adjudicator -> Alice")
assert_eq(c3, "Alice", "Email Composer -> Alice")

# Verify full state
full_state = mgr.get_all_state()
assert_true("timestamp" in full_state, "Full state has timestamp")
assert_true("stages" in full_state, "Full state has stages")
assert_true("hitl" in full_state, "Full state has hitl")
assert_true("global" in full_state, "Full state has global")
assert_eq(full_state["global"]["total_claims_in_flight"], 3, "3 total in-flight")

# HITL counter
mgr.increment_hitl_waiting()
mgr.increment_hitl_waiting()
assert_eq(mgr.get_hitl_waiting_count(), 2, "HITL waiting = 2")
mgr.decrement_hitl_waiting()
assert_eq(mgr.get_hitl_waiting_count(), 1, "HITL waiting = 1")

# Singleton behavior
mgr2 = ContractorManager()
assert_true(mgr is mgr2, "ContractorManager is a singleton")

# Complete and verify
mgr.complete_job("classifier", "CLM-M01")
full_state = mgr.get_all_state()
assert_eq(full_state["stages"]["classifier"]["total_completed"], 1, "Classifier completed 1")

# Email composer capacity (should be 5, not 3)
ec_state = full_state["stages"]["email_composer"]
assert_eq(ec_state["capacity_per_contractor"], 5, "Email composer capacity = 5")
assert_eq(ec_state["max_contractors"], 3, "Email composer max = 3")

print(f"  ContractorManager singleton with all pools -> PASS")

# Cleanup
ContractorManager.reset()


# =========================================================================
# Test: update_progress
# =========================================================================

section("Test 15 (Bonus): update_progress")
pool = new_pool()
pool.assign_job("CLM-P01")
pool.update_progress("CLM-P01", 55)
state = pool.get_state()
assert_eq(state["active_contractors"][0]["active_jobs"][0]["progress_pct"], 55, "Progress should be 55%")

pool.update_progress("CLM-P01", 150)  # Should cap at 100
state = pool.get_state()
assert_eq(state["active_contractors"][0]["active_jobs"][0]["progress_pct"], 100, "Progress capped at 100%")

pool.update_progress("CLM-P01", -10)  # Should cap at 0
state = pool.get_state()
assert_eq(state["active_contractors"][0]["active_jobs"][0]["progress_pct"], 0, "Progress capped at 0%")
print(f"  Progress update + clamping -> PASS")


# =========================================================================
# Test: First-fill resumes after partial scale-down
# =========================================================================

section("Test 16 (Bonus): First-fill resumes correctly mid-scale")
pool = new_pool()
# Fill Alice + Bob
for i in range(1, 7):
    pool.assign_job(f"CLM-F{i:02d}")
# Alice [1,2,3] Bob [4,5,6]

# Free 2 slots on Alice
pool.complete_job("CLM-F01")
pool.complete_job("CLM-F02")
# Alice [3] Bob [4,5,6]

# New job should go to Alice (first-fill), not Bob
r = pool.assign_job("CLM-F07")
assert_eq(r, "Alice", "First-fill should route to Alice (has free slots)")
state = pool.get_state()
alice_jobs = [j["claim_id"] for j in state["active_contractors"][0]["active_jobs"]]
assert_true("CLM-F07" in alice_jobs, "CLM-F07 should be on Alice")
assert_eq(state["active_contractors"][0]["slots_used"], 2, "Alice should have 2 jobs")
print(f"  First-fill correctly resumes to Alice -> PASS")


# =========================================================================
# Summary
# =========================================================================

print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")

if failed > 0:
    print("\n  SOME TESTS FAILED!")
    sys.exit(1)
else:
    print("\n  ALL TESTS PASSED!")
    sys.exit(0)
