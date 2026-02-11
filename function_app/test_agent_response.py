"""
Test script to call Agent1 directly and inspect the raw response.
Run from function_app directory: python test_agent_response.py
"""

import os
import sys

# Set environment variables
# Load from environment or local.settings.json — never hardcode secrets
os.environ.setdefault("AGENT1_PROJECT_ENDPOINT", os.getenv("AGENT1_PROJECT_ENDPOINT", ""))
os.environ.setdefault("AGENT1_NAME", os.getenv("AGENT1_NAME", "claim-assistant-agent"))
os.environ.setdefault("AZURE_TENANT_ID", os.getenv("AZURE_TENANT_ID", ""))
os.environ.setdefault("AZURE_CLIENT_ID", os.getenv("AZURE_CLIENT_ID", ""))
os.environ.setdefault("AZURE_CLIENT_SECRET", os.getenv("AZURE_CLIENT_SECRET", ""))

from azure.identity import ClientSecretCredential
from azure.ai.projects import AIProjectClient
from shared.prompts import build_agent1_prompt

def test_agent1():
    print("=" * 80)
    print("Testing Agent1 (claim-assistant-agent) Raw Response")
    print("=" * 80)

    # Build test prompt - using the exact input that causes issues
    email_body = "Subject: Claim Submission - Transmission Repair - 2022 Honda Accord. Hi, I am submitting a claim    for repairs on my 2022 Honda Accord (VIN: 1HGCV1F34NA000123, Mileage: 45,000). Contract: VSC-2024-78542, Gold VSC,  $100 deductible. Issue: Transmission making grinding noise when shifting, started January 28, 2026. Diagnosed as  transmission solenoid failure at ABC Auto Service (Authorized Dealer), 123 Main St, Tampa FL. Estimate: $767.50 (Parts: Solenoid Pack $285, Fluid $45, Labor 3.5hrs @ $125/hr = $437.50). Please process this claim. Thanks, John   Smith, john.smith@email.com, 555-123-4567"
    attachment_url = "https://pdfazuredocaitest.blob.core.windows.net/test/VSC Claim Form - CLM-2026-00142.pdf"

    prompt = build_agent1_prompt(
        claim_id="TEST-001",
        email_content=email_body,
        attachment_url=attachment_url,
        sender_email="john.smith@email.com",
        received_date="2026-02-01T12:00:00"
    )

    print("\n--- PROMPT SENT TO AGENT ---")
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("\n")

    # Get credential
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"]
    )

    # Create project client
    project_client = AIProjectClient(
        endpoint=os.environ["AGENT1_PROJECT_ENDPOINT"],
        credential=credential,
    )

    # Get the agent
    agent_name = os.environ["AGENT1_NAME"]
    agent = project_client.agents.get(agent_name=agent_name)
    print(f"Connected to agent: {agent.name}")

    # Get OpenAI client
    openai_client = project_client.get_openai_client()

    # Send message
    print("\nSending message to agent...")
    response = openai_client.responses.create(
        input=[{"role": "user", "content": prompt}],
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    # Get raw response
    raw_response = response.output_text

    print("\n--- RAW RESPONSE FROM AGENT ---")
    print(raw_response)
    print("\n--- END RAW RESPONSE ---")
    print(f"\nResponse length: {len(raw_response)} characters")

    # Try to parse as JSON
    import json
    import re

    # Extract from code block if present
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, raw_response)
    if match:
        json_str = match.group(1).strip()
        print("\n--- EXTRACTED FROM CODE BLOCK ---")
        print(json_str[:500] + "..." if len(json_str) > 500 else json_str)
    else:
        json_str = raw_response.strip()
        print("\nNo code block found, using raw response as JSON")

    print(f"\nJSON string length: {len(json_str)} characters")

    # Try to parse
    print("\n--- ATTEMPTING JSON PARSE ---")
    try:
        parsed = json.loads(json_str)
        print("SUCCESS! JSON parsed correctly.")
        print(f"Keys: {list(parsed.keys())}")
    except json.JSONDecodeError as e:
        print(f"FAILED: {e}")
        print(f"\nError position: character {e.pos}")

        # Show context around error
        start = max(0, e.pos - 100)
        end = min(len(json_str), e.pos + 100)
        print(f"\nContext around error (chars {start}-{end}):")
        print("-" * 40)
        context = json_str[start:end]
        # Mark the error position
        error_marker_pos = e.pos - start
        print(context[:error_marker_pos] + " <<< ERROR HERE >>> " + context[error_marker_pos:])
        print("-" * 40)

        # Save full response to file for analysis
        with open("agent_response_debug.txt", "w", encoding="utf-8") as f:
            f.write("=== RAW RESPONSE ===\n")
            f.write(raw_response)
            f.write("\n\n=== EXTRACTED JSON ===\n")
            f.write(json_str)
        print("\nFull response saved to agent_response_debug.txt")

if __name__ == "__main__":
    test_agent1()
