"""
Send Email Activity for Gmail SMTP.

Sends composed emails via Gmail SMTP to the review email address
or directly to the claimant.
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_smtp_config() -> dict:
    """
    Get SMTP configuration from environment variables.

    Returns:
        Dictionary with SMTP settings
    """
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD"),
        "from_address": os.getenv("EMAIL_FROM_ADDRESS"),
        "from_name": os.getenv("EMAIL_FROM_NAME", "Claims Department"),
        "review_email": os.getenv("REVIEW_EMAIL_ADDRESS"),
    }


def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    from_name: str = None,
    from_email: str = None,
    reply_to: str = None,
    is_html: bool = False
) -> dict:
    """
    Send an email via SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        from_name: Sender display name
        from_email: Sender email address
        reply_to: Reply-to email address
        is_html: Whether body is HTML

    Returns:
        Dictionary with send status
    """
    config = get_smtp_config()

    if not config["username"] or not config["password"]:
        raise ValueError("SMTP credentials not configured")

    from_name = from_name or config["from_name"]
    from_email = from_email or config["from_address"] or config["username"]

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    if reply_to:
        msg["Reply-To"] = reply_to

    # Attach body
    content_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, content_type, "utf-8"))

    # Send via SMTP
    try:
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.starttls()
            server.login(config["username"], config["password"])
            server.sendmail(from_email, [to_email], msg.as_string())

        logger.info(f"Email sent successfully to {to_email}")
        return {
            "success": True,
            "to_email": to_email,
            "subject": subject,
            "sent_at": datetime.now(timezone.utc).isoformat()
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {str(e)}")
        raise ValueError(f"SMTP authentication failed: {str(e)}")

    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {str(e)}")
        raise


def run_send_email_activity(input_data: dict) -> dict:
    """
    Run send email activity.

    Args:
        input_data: Dictionary containing:
            - claim_id: The claim identifier
            - email_subject: Email subject from Agent3
            - email_body: Email body from Agent3
            - recipient_email: Claimant's email address
            - recipient_name: Claimant's name
            - send_to_review: Whether to send to review address (default: True)
            - send_to_claimant: Whether to send directly to claimant (default: False)
            - _instance_id: Orchestration instance ID (optional, for logging)

    Returns:
        Dictionary with send status
    """
    instance_id = input_data.get("_instance_id")
    claim_id = input_data.get("claim_id")
    email_subject = input_data.get("email_subject")
    email_body = input_data.get("email_body")
    recipient_email = input_data.get("recipient_email")
    recipient_name = input_data.get("recipient_name", "Customer")
    send_to_review = input_data.get("send_to_review", True)
    send_to_claimant = input_data.get("send_to_claimant", False)

    log_prefix = f"[{instance_id}] " if instance_id else ""
    logger.info(f"{log_prefix}Starting send email activity for claim {claim_id}")

    config = get_smtp_config()
    results = {
        "claim_id": claim_id,
        "review_email_sent": False,
        "claimant_email_sent": False,
        "errors": []
    }

    # Validate required fields
    if not email_subject or not email_body:
        error_msg = "Email subject and body are required"
        logger.error(f"{log_prefix}{error_msg}")
        results["errors"].append(error_msg)
        return results

    # Send to review email address
    if send_to_review:
        review_email = config.get("review_email")
        if not review_email:
            error_msg = "REVIEW_EMAIL_ADDRESS not configured"
            logger.warning(f"{log_prefix}{error_msg}")
            results["errors"].append(error_msg)
        else:
            try:
                # Add claim context to subject for review emails
                review_subject = f"[REVIEW] {email_subject} - Claim {claim_id}"

                result = send_email_smtp(
                    to_email=review_email,
                    subject=review_subject,
                    body=email_body,
                    reply_to=recipient_email
                )
                results["review_email_sent"] = True
                results["review_email_result"] = result
                logger.info(f"{log_prefix}Review email sent to {review_email}")

            except Exception as e:
                error_msg = f"Failed to send review email: {str(e)}"
                logger.error(f"{log_prefix}{error_msg}")
                results["errors"].append(error_msg)

    # Send directly to claimant (if enabled)
    if send_to_claimant:
        if not recipient_email:
            error_msg = "Claimant email address not available"
            logger.warning(f"{log_prefix}{error_msg}")
            results["errors"].append(error_msg)
        else:
            try:
                result = send_email_smtp(
                    to_email=recipient_email,
                    subject=email_subject,
                    body=email_body
                )
                results["claimant_email_sent"] = True
                results["claimant_email_result"] = result
                logger.info(f"{log_prefix}Claimant email sent to {recipient_email}")

            except Exception as e:
                error_msg = f"Failed to send claimant email: {str(e)}"
                logger.error(f"{log_prefix}{error_msg}")
                results["errors"].append(error_msg)

    # Set overall success flag
    results["success"] = (
        (send_to_review and results["review_email_sent"]) or
        (send_to_claimant and results["claimant_email_sent"]) or
        (not send_to_review and not send_to_claimant)
    )
    results["sent_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"{log_prefix}Send email activity completed - Success: {results['success']}")
    return results
