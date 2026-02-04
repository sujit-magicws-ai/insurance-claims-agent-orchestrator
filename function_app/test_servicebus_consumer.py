"""
Test Service Bus Message Consumer

This script pulls and displays messages from the Service Bus queue.
Use this to clear the queue or inspect pending messages.

Usage:
    python test_servicebus_consumer.py           # Peek messages (don't remove)
    python test_servicebus_consumer.py --clear   # Receive and remove messages
"""

import json
import os
import sys
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode

# Fix Unicode encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def load_settings():
    """Load settings from local.settings.json"""
    settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            settings = json.load(f)
            return settings.get("Values", {})
    return {}


def get_message_body(msg):
    """Extract message body as string."""
    try:
        # For ServiceBusReceivedMessage, body can be bytes or generator
        body = msg.body
        if hasattr(body, '__iter__') and not isinstance(body, (str, bytes)):
            # It's a generator, collect all parts
            body = b''.join(body)
        if isinstance(body, bytes):
            return body.decode('utf-8')
        return str(body)
    except Exception as e:
        return f"[Error reading body: {e}]"


def peek_messages(receiver, max_messages=10, interactive=False):
    """Peek at messages without removing them."""
    print(f"\nPeeking at up to {max_messages} messages (not removing)...\n")

    messages = receiver.peek_messages(max_message_count=max_messages)

    if not messages:
        print("No messages in queue.")
        return 0

    for i, msg in enumerate(messages, 1):
        print(f"{'='*60}")
        print(f"Message {i} of {len(messages)}:")
        print(f"{'='*60}")
        print(f"  Message ID: {msg.message_id}")
        print(f"  Subject: {msg.subject}")
        print(f"  Enqueued Time: {msg.enqueued_time_utc}")

        try:
            body_str = get_message_body(msg)
            body = json.loads(body_str)
            print(f"\n  Body (JSON):")
            print(f"    claim_id: {body.get('claim_id')}")
            print(f"    sender_email: {body.get('sender_email')}")
            attachment_url = body.get('attachment_url', '')
            if attachment_url:
                print(f"    attachment_url: {attachment_url[:80]}...")
            if body.get('email_content'):
                content = body.get('email_content', '')[:500]
                print(f"\n  Email Content Preview:")
                print(f"    {content}...")
        except json.JSONDecodeError:
            # Not JSON - print raw body
            body_str = get_message_body(msg)
            print(f"\n  Body (Raw):")
            print(f"    {body_str[:1000]}")
        except Exception as e:
            print(f"\n  Error parsing body: {e}")

        print(f"\n{'='*60}")

        if interactive and i < len(messages):
            input(f"Press ENTER for next message ({i}/{len(messages)})...")
            print()

    print(f"\nTotal messages peeked: {len(messages)}")
    return len(messages)


def receive_and_clear(receiver, max_messages=100):
    """Receive and remove messages from the queue."""
    print(f"\nReceiving and removing up to {max_messages} messages...\n")

    count = 0
    while count < max_messages:
        messages = receiver.receive_messages(max_message_count=10, max_wait_time=5)

        if not messages:
            break

        for msg in messages:
            print(f"Removing: {msg.message_id} - ", end="")
            try:
                body_str = get_message_body(msg)
                body = json.loads(body_str)
                print(f"claim_id: {body.get('claim_id')}")
            except:
                print(f"(non-JSON message)")

            receiver.complete_message(msg)
            count += 1

    print(f"\n{'='*60}")
    print(f"Total messages removed: {count}")
    return count


def main():
    # Check for flags
    clear_mode = "--clear" in sys.argv
    interactive_mode = "--interactive" in sys.argv or "-i" in sys.argv

    # Default to interactive mode for peek
    if not clear_mode:
        interactive_mode = True

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
    print(f"Mode: {'CLEAR (receive & remove)' if clear_mode else 'PEEK (view only)'}")
    if not clear_mode:
        print(f"Interactive: {'YES' if interactive_mode else 'NO'}")

    try:
        with ServiceBusClient.from_connection_string(connection_string) as client:
            if clear_mode:
                # Receive mode - will remove messages
                with client.get_queue_receiver(
                    queue_name,
                    receive_mode=ServiceBusReceiveMode.PEEK_LOCK
                ) as receiver:
                    receive_and_clear(receiver)
            else:
                # Peek mode - just view messages
                with client.get_queue_receiver(
                    queue_name,
                    receive_mode=ServiceBusReceiveMode.PEEK_LOCK
                ) as receiver:
                    peek_messages(receiver, interactive=interactive_mode)

        print("\nDone.")

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        raise


if __name__ == "__main__":
    main()
