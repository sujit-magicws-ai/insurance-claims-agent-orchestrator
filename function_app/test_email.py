"""
Test Email Sending via Gmail SMTP

Simple script to verify SMTP configuration is working.

Usage:
    python test_email.py
"""

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


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

    smtp_host = settings.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(settings.get("SMTP_PORT", "587"))
    smtp_username = settings.get("SMTP_USERNAME")
    smtp_password = settings.get("SMTP_PASSWORD")
    from_address = settings.get("EMAIL_FROM_ADDRESS", smtp_username)
    from_name = settings.get("EMAIL_FROM_NAME", "Claims Department")
    to_address = settings.get("REVIEW_EMAIL_ADDRESS")

    print("=== Email Configuration ===")
    print(f"SMTP Host: {smtp_host}")
    print(f"SMTP Port: {smtp_port}")
    print(f"SMTP Username: {smtp_username}")
    print(f"SMTP Password: {'*' * len(smtp_password) if smtp_password else 'NOT SET'}")
    print(f"From: {from_name} <{from_address}>")
    print(f"To: {to_address}")
    print()

    if not smtp_username or not smtp_password:
        print("ERROR: SMTP_USERNAME or SMTP_PASSWORD not configured")
        return

    if not to_address:
        print("ERROR: REVIEW_EMAIL_ADDRESS not configured")
        return

    # Create test email
    subject = f"[TEST] Email Configuration Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    body = f"""This is a test email to verify SMTP configuration.

Sent at: {datetime.now().isoformat()}
From: {from_name} <{from_address}>
To: {to_address}

SMTP Settings:
- Host: {smtp_host}
- Port: {smtp_port}
- Username: {smtp_username}

If you received this email, your Gmail SMTP configuration is working correctly!
"""

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_address}>"
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    print("Sending test email...")
    print()

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.set_debuglevel(1)  # Enable debug output
            print("Connecting to SMTP server...")
            server.starttls()
            print("TLS started...")
            server.login(smtp_username, smtp_password)
            print("Login successful...")
            server.sendmail(from_address, [to_address], msg.as_string())
            print()
            print("=" * 50)
            print("SUCCESS: Email sent!")
            print(f"Check inbox at: {to_address}")
            print("=" * 50)

    except smtplib.SMTPAuthenticationError as e:
        print()
        print("=" * 50)
        print("AUTHENTICATION ERROR!")
        print(f"Error: {str(e)}")
        print()
        print("Possible causes:")
        print("1. App Password is incorrect")
        print("2. 2-Step Verification not enabled on Gmail")
        print("3. App Password has spaces (remove them)")
        print("=" * 50)

    except smtplib.SMTPException as e:
        print()
        print("=" * 50)
        print("SMTP ERROR!")
        print(f"Error: {str(e)}")
        print("=" * 50)

    except Exception as e:
        print()
        print("=" * 50)
        print("UNEXPECTED ERROR!")
        print(f"Error: {str(e)}")
        print("=" * 50)


if __name__ == "__main__":
    main()
