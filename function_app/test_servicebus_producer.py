"""
Test Service Bus Message Producer

This script sends a test claim message to the Service Bus queue
to trigger the claim orchestration.

Usage:
    python test_servicebus_producer.py
"""

import json
import os
from datetime import datetime
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

# Load environment variables from local.settings.json
def load_settings():
    """Load settings from local.settings.json"""
    settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            settings = json.load(f)
            return settings.get("Values", {})
    return {}

def main():
    # Load settings
    settings = load_settings()

    connection_string = settings.get("SERVICE_BUS_CONNECTION_STRING")
    queue_name = settings.get("SERVICE_BUS_QUEUE_NAME")

    if not connection_string:
        print("ERROR: SERVICE_BUS_CONNECTION_STRING not found in local.settings.json")
        return

    if not queue_name:
        print("ERROR: SERVICE_BUS_QUEUE_NAME not found in local.settings.json")
        return

    print(f"Connecting to Service Bus queue: {queue_name}")

    # Generate a unique claim ID
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    claim_id = f"CLM-SB-{timestamp}"

    # Hardcoded test payload
    test_claim = {
        "claim_id": claim_id,
        "email_content": """Subject: Vehicle Service Contract Claim - Transmission Repair

Dear Claims Department,

I am writing to submit a claim under my Vehicle Service Contract for transmission repairs on my 2022 Honda Accord.

Issue Details:
- Vehicle is making grinding noises when shifting gears
- Check engine light came on last week
- Local mechanic diagnosed it as transmission synchronizer failure

The repair shop has provided an estimate of $1,850.00 for parts and labor.

Vehicle Information:
- Year: 2022
- Make: Honda
- Model: Accord
- VIN: 1HGCV1F34NA000123
- Current Mileage: 45,000

My contract number is VSC-2024-78542 and I have a $100 deductible.

Please let me know if you need any additional information.

Thank you,
John Smith
Phone: 555-123-4567
Email: john.smith@email.com
Address: 123 Main Street, Tampa, FL 33601""",
        "attachment_url": "https://pdfazuredocaitest.blob.core.windows.net/test/Claim_Baker_015.pdf",
        "sender_email": "john.smith@email.com",
        "metadata": {
            "source": "test_servicebus_producer",
            "test_run": True,
            "timestamp": datetime.now().isoformat()
        }
    }

    # Convert to JSON
    message_body = json.dumps(test_claim, indent=2)

    print(f"\nSending test claim message:")
    print(f"  Claim ID: {claim_id}")
    print(f"  Queue: {queue_name}")
    print(f"  Payload size: {len(message_body)} bytes")

    try:
        # Create Service Bus client and send message
        with ServiceBusClient.from_connection_string(connection_string) as client:
            with client.get_queue_sender(queue_name) as sender:
                message = ServiceBusMessage(
                    body=message_body,
                    content_type="application/json",
                    subject=f"Claim: {claim_id}",
                    application_properties={
                        "claim_id": claim_id,
                        "source": "test_producer"
                    }
                )
                sender.send_messages(message)

        print(f"\n SUCCESS: Message sent to queue '{queue_name}'")
        print(f"\nNext steps:")
        print(f"  1. Check the Azure Function logs for processing")
        print(f"  2. View claim status at: http://localhost:7071/api/claims/status/claim-{claim_id}")
        print(f"  3. View dashboard at: http://localhost:7071/api/dashboard")

    except Exception as e:
        print(f"\n ERROR: Failed to send message: {str(e)}")
        raise

if __name__ == "__main__":
    main()
