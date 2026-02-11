"""
Test Agent1 multiple times to check for intermittent JSON issues.
"""

import os
import json
import re

# Load from environment or local.settings.json — never hardcode secrets
os.environ.setdefault("AGENT1_PROJECT_ENDPOINT", os.getenv("AGENT1_PROJECT_ENDPOINT", ""))
os.environ.setdefault("AGENT1_NAME", os.getenv("AGENT1_NAME", "claim-assistant-agent"))
os.environ.setdefault("AZURE_TENANT_ID", os.getenv("AZURE_TENANT_ID", ""))
os.environ.setdefault("AZURE_CLIENT_ID", os.getenv("AZURE_CLIENT_ID", ""))
os.environ.setdefault("AZURE_CLIENT_SECRET", os.getenv("AZURE_CLIENT_SECRET", ""))

from azure.identity import ClientSecretCredential
from azure.ai.projects import AIProjectClient
from shared.prompts import build_agent1_prompt

def test_once(attempt_num):
    email_body = "Subject: Claim Submission - Transmission Repair - 2022 Honda Accord. Hi, I am submitting a claim    for repairs on my 2022 Honda Accord (VIN: 1HGCV1F34NA000123, Mileage: 45,000). Contract: VSC-2024-78542, Gold VSC,  $100 deductible. Issue: Transmission making grinding noise when shifting, started January 28, 2026. Diagnosed as  transmission solenoid failure at ABC Auto Service (Authorized Dealer), 123 Main St, Tampa FL. Estimate: $767.50 (Parts: Solenoid Pack $285, Fluid $45, Labor 3.5hrs @ $125/hr = $437.50). Please process this claim. Thanks, John   Smith, john.smith@email.com, 555-123-4567"
    attachment_url = "https://pdfazuredocaitest.blob.core.windows.net/test/VSC Claim Form - CLM-2026-00142.pdf"

    prompt = build_agent1_prompt(
        claim_id=f"TEST-{attempt_num:03d}",
        email_content=email_body,
        attachment_url=attachment_url,
        sender_email="john.smith@email.com",
        received_date="2026-02-01T12:00:00"
    )

    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"]
    )

    project_client = AIProjectClient(
        endpoint=os.environ["AGENT1_PROJECT_ENDPOINT"],
        credential=credential,
    )

    agent = project_client.agents.get(agent_name=os.environ["AGENT1_NAME"])
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": prompt}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    raw_response = response.output_text

    # Extract from code block
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, raw_response)
    json_str = match.group(1).strip() if match else raw_response.strip()

    # Apply fix for arithmetic expressions
    from shared.agent_client import fix_common_json_issues
    json_str_fixed = fix_common_json_issues(json_str)

    try:
        parsed = json.loads(json_str_fixed)
        return True, None, len(json_str_fixed)
    except json.JSONDecodeError as e:
        # Save the failed response
        with open(f"failed_response_{attempt_num}.txt", "w", encoding="utf-8") as f:
            f.write(f"Error: {e}\n\n")
            f.write(f"Position: {e.pos}\n\n")
            f.write("=== RAW ===\n")
            f.write(raw_response)
            f.write("\n\n=== JSON STRING (original) ===\n")
            f.write(json_str)
            f.write("\n\n=== JSON STRING (after fix) ===\n")
            f.write(json_str_fixed)
        return False, str(e), len(json_str_fixed)

if __name__ == "__main__":
    print("Testing Agent1 response 5 times...\n")

    results = []
    for i in range(5):
        print(f"Attempt {i+1}/5... ", end="", flush=True)
        try:
            success, error, length = test_once(i+1)
            if success:
                print(f"SUCCESS (len={length})")
                results.append(("SUCCESS", length))
            else:
                print(f"FAILED - {error}")
                results.append(("FAILED", error))
        except Exception as e:
            print(f"ERROR - {e}")
            results.append(("ERROR", str(e)))

    print("\n" + "="*50)
    print("Summary:")
    successes = sum(1 for r in results if r[0] == "SUCCESS")
    failures = sum(1 for r in results if r[0] == "FAILED")
    errors = sum(1 for r in results if r[0] == "ERROR")
    print(f"  Successes: {successes}")
    print(f"  JSON Failures: {failures}")
    print(f"  Other Errors: {errors}")
