"""
Clone Visualizer — Load Test Script

Submit N claims rapidly and observe dashboard behavior.
Run while function app is running and dashboard is open.

Usage:
    cd function_app
    python -m tests.test_clone_load

    # Or with custom count:
    python -m tests.test_clone_load --count 20

    # Batch-approve all waiting claims:
    python -m tests.test_clone_load --approve
"""

import argparse
import json
import sys
import time

import requests

BASE_URL = "http://localhost:7071/api"


def submit_claims(count: int, stagger: float = 0.3):
    """Submit N claims rapidly with a slight stagger."""
    print(f"\n{'='*60}")
    print(f"  Submitting {count} claims (stagger: {stagger}s)")
    print(f"{'='*60}\n")

    success = 0
    for i in range(1, count + 1):
        claim_id = f"LOAD-{i:03d}"
        try:
            resp = requests.post(f"{BASE_URL}/claims/start", json={
                "claim_id": claim_id,
                "email_content": f"Load test claim {i} - transmission grinding noise, "
                                 f"vehicle won't shift properly. Please process urgently.",
                "attachment_url": f"https://example.com/load/{claim_id}.pdf",
                "sender_email": f"load{i}@test.com"
            }, timeout=10)

            status = resp.status_code
            if status == 200 or status == 202:
                success += 1
                print(f"  [{i:3d}/{count}] {claim_id}: {status} OK")
            else:
                print(f"  [{i:3d}/{count}] {claim_id}: {status} FAILED - {resp.text[:100]}")
        except requests.exceptions.ConnectionError:
            print(f"  [{i:3d}/{count}] {claim_id}: CONNECTION ERROR - is func start running?")
            if i == 1:
                print("\n  Aborting: Function app not reachable.")
                sys.exit(1)
        except Exception as e:
            print(f"  [{i:3d}/{count}] {claim_id}: ERROR - {e}")

        if i < count:
            time.sleep(stagger)

    print(f"\n  Submitted: {success}/{count}")
    return success


def check_contractor_state():
    """Print current contractor state summary."""
    try:
        resp = requests.get(f"{BASE_URL}/contractors/state", timeout=5)
        state = resp.json()

        print(f"\n{'='*60}")
        print(f"  Contractor State")
        print(f"{'='*60}")

        for stage_id in ["classifier", "adjudicator", "email_composer"]:
            stage = state["stages"].get(stage_id, {})
            contractors = stage.get("active_contractors", [])
            in_flight = stage.get("total_jobs_in_flight", 0)
            completed = stage.get("total_completed", 0)
            pending = stage.get("pending_count", 0)
            names = [f"{c['name']}({c['slots_used']}/{c['capacity']})" for c in contractors]
            print(f"\n  {stage.get('display_name', stage_id)}:")
            print(f"    Workers: {', '.join(names) or 'none'}")
            print(f"    In flight: {in_flight}  |  Completed: {completed}  |  Pending: {pending}")

        hitl = state.get("hitl", {})
        print(f"\n  HITL Waiting: {hitl.get('waiting_count', 0)}")

        g = state.get("global", {})
        print(f"\n  Global: In Flight={g.get('total_claims_in_flight', 0)}, "
              f"Completed={g.get('total_claims_completed', 0)}")

        # Show recent events
        events = state.get("events", [])[:10]
        if events:
            print(f"\n  Recent Events:")
            for e in events:
                print(f"    {e['timestamp']} [{e['type']:15s}] {e['message']}")

    except Exception as e:
        print(f"  Error fetching state: {e}")


def approve_all_waiting():
    """Batch-approve all claims waiting for manual estimate."""
    print(f"\n{'='*60}")
    print(f"  Batch-Approving Waiting Claims")
    print(f"{'='*60}\n")

    try:
        resp = requests.get(f"{BASE_URL}/claims", timeout=10)
        data = resp.json()
        claims = data.get("claims", [])

        waiting = [c for c in claims if c.get("step") == "awaiting_approval"]
        print(f"  Found {len(waiting)} claims awaiting approval\n")

        if not waiting:
            print("  No claims waiting for approval.")
            return 0

        approved = 0
        for claim in waiting:
            instance_id = claim["instance_id"]
            claim_id = claim["claim_id"]

            approval_body = {
                "reviewer": "load-test@co.com",
                "decision": "approved",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "claim_data": {
                    "claimant": {"name": "Load Test Customer"},
                    "contract": {
                        "contract_number": "VSC-2024-LOAD",
                        "product_type": "VSC",
                        "coverage_level": "Gold",
                        "status": "Active",
                        "deductible": 100,
                        "max_claim_amount": 5000,
                        "mileage_limit": 100000
                    },
                    "vehicle": {
                        "year": 2022,
                        "make": "Honda",
                        "model": "Accord"
                    },
                    "repair": {
                        "total_estimate": 750,
                        "total_parts": 500,
                        "total_labor": 250
                    },
                    "documents": {
                        "damage_photos": True,
                        "claim_form": True
                    }
                }
            }

            try:
                r = requests.post(
                    f"{BASE_URL}/claims/approve/{instance_id}",
                    json=approval_body,
                    timeout=10
                )
                if r.status_code == 200 or r.status_code == 202:
                    approved += 1
                    print(f"  Approved: {claim_id} ({instance_id})")
                else:
                    print(f"  Failed:   {claim_id} - {r.status_code}: {r.text[:80]}")
            except Exception as e:
                print(f"  Error:    {claim_id} - {e}")

            time.sleep(0.2)

        print(f"\n  Approved: {approved}/{len(waiting)}")
        return approved

    except Exception as e:
        print(f"  Error: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Clone Visualizer Load Test")
    parser.add_argument("--count", type=int, default=12,
                        help="Number of claims to submit (default: 12)")
    parser.add_argument("--stagger", type=float, default=0.3,
                        help="Seconds between submissions (default: 0.3)")
    parser.add_argument("--approve", action="store_true",
                        help="Batch-approve all waiting claims instead of submitting")
    parser.add_argument("--state", action="store_true",
                        help="Just print current contractor state")
    args = parser.parse_args()

    if args.state:
        check_contractor_state()
    elif args.approve:
        approve_all_waiting()
        time.sleep(1)
        check_contractor_state()
    else:
        submit_claims(args.count, args.stagger)
        print("\n  Waiting 2s for claims to start processing...")
        time.sleep(2)
        check_contractor_state()
        print(f"\n  Dashboard: http://localhost:7071/api/clone-dashboard")
        print(f"  To approve waiting claims: python -m tests.test_clone_load --approve")


if __name__ == "__main__":
    main()
