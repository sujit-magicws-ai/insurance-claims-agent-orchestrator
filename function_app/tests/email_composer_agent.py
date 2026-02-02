# pip install --pre azure-ai-projects azure-identity python-dotenv

import os
import json
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()


def get_credential():
    """
    Get OAuth credential for Azure AI Foundry.
    """
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant_id and client_id and client_secret:
        print("Using Service Principal authentication")
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        print("Using Default Azure Credential")
        return DefaultAzureCredential()


def get_email_input():
    """
    Collect Email Composer Agent input.
    """
    print("\n" + "=" * 60)
    print("EMAIL COMPOSER AGENT")
    print("=" * 60)

    return {
        "recipient_name": input("Recipient name: ").strip(),
        "recipient_email": input("Recipient email: ").strip(),
        "email_purpose": input("Email purpose: ").strip(),
        "outcome_summary": input("Outcome summary: ").strip(),
        "sender_name": input("Sender name (optional): ").strip(),
        "additional_context": input("Additional context (optional): ").strip(),
        "tone": input("Tone [formal/casual/urgent] (default: formal): ").strip() or "formal",
        "length": input("Length [brief/standard/detailed] (default: standard): ").strip() or "standard",
        "empathy": input("Empathy [neutral/warm/highly_supportive] (default: neutral): ").strip() or "neutral",
        "call_to_action": input("CTA [none/soft/direct] (default: none): ").strip() or "none",
    }


def process_email(email_data, credential):
    """
    Send email composition request to the Email Composer Agent.
    """

    endpoint = os.getenv(
        "AZURE_EXISTING_AIPROJECT_ENDPOINT",
        "https://langgraph-ai-foundary.services.ai.azure.com/api/projects/langgraph"
    )

    agent_name = os.getenv(
        "AZURE_AGENT_NAME",
        "EmailComposerAgent"
    )

    project_client = AIProjectClient(
        endpoint=endpoint,
        credential=credential,
    )

    agent = project_client.agents.get(agent_name=agent_name)
    print(f"\nConnected to agent: {agent.name}")

    openai_client = project_client.get_openai_client()

    user_message = f"""
Compose an email with the following details:

RECIPIENT:
- Name: {email_data['recipient_name']}
- Email: {email_data['recipient_email']}

EMAIL PURPOSE:
{email_data['email_purpose']}

OUTCOME SUMMARY:
{email_data['outcome_summary']}

SENDER:
{email_data['sender_name']}

ADDITIONAL CONTEXT:
{email_data['additional_context']}

STYLE SETTINGS:
- Tone: {email_data['tone']}
- Length: {email_data['length']}
- Empathy: {email_data['empathy']}
- Call to Action: {email_data['call_to_action']}
""".strip()

    print("\nComposing email...")
    print("-" * 60)

    response = openai_client.responses.create(
        input=[{"role": "user", "content": user_message}],
        extra_body={
            "agent": {
                "name": agent.name,
                "type": "agent_reference"
            }
        },
    )

    output_text = response.output_text

    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        raise ValueError(
            f"Agent did not return valid JSON:\n{output_text}"
        )


def main():
    try:
        credential = get_credential()

        email_data = get_email_input()

        result = process_email(email_data, credential)

        print("\n" + "=" * 60)
        print("EMAIL COMPOSITION RESULT")
        print("=" * 60)
        print(json.dumps(result, indent=2))
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()