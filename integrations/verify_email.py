"""Utility script to verify and test SMTP email configuration for AutoHPC.

Run this script to ensure your SMTP credentials in .env work:
    python -m integrations.verify_email
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from integrations.notifier import format_html_message, send_email


def verify():
    host = os.environ.get("AUTOHPC_SMTP_HOST")
    port = os.environ.get("AUTOHPC_SMTP_PORT", "587")
    user = os.environ.get("AUTOHPC_SMTP_USER")
    sender = os.environ.get("AUTOHPC_SMTP_FROM") or user
    recipient = os.environ.get("AUTOHPC_SMTP_TO")

    print("=" * 60)
    print("AutoHPC SMTP Configuration Verification")
    print("=" * 60)
    print(f"SMTP Host:      {host or '<NOT SET>'}")
    print(f"SMTP Port:      {port}")
    print(f"SMTP User:      {user or '<NOT SET>'}")
    print(f"Sender (From):  {sender or '<NOT SET>'}")
    print(f"Recipient (To): {recipient or '<NOT SET>'}")
    print("=" * 60)

    if not host or not recipient:
        print("\n[ERROR] Missing required SMTP configuration.")
        print("Please configure AUTOHPC_SMTP_HOST and AUTOHPC_SMTP_TO in your .env file.")
        print("See .env.example for details.")
        sys.exit(1)

    subject = "AutoHPC RPA - Verification Email"
    message = (
        "This is an automated test message from the AutoHPC RPA Node.\n"
        "If you are reading this, your SMTP configuration is functional!"
    )
    mock_summary = {
        "experiment_id": "TEST-001",
        "status": "COMPLETED",
        "completed": 4,
        "failed": 0,
        "retries": 0,
        "wall_time": 0.42,
        "pi_estimate": 3.141592,
        "abs_error": 1.23e-06,
    }

    html_body = format_html_message(message, summary=mock_summary, subject=subject)

    print("\nAttempting to send test email...")
    try:
        send_email(subject, message, html_body=html_body)
        print("\n[SUCCESS] Test email sent successfully to", recipient)
    except Exception as e:
        print(f"\n[FAILED] Could not send email: {type(e).__name__}: {e}")
        print("\nTips:")
        print(" - For Gmail: ensure you are using an App Password (not your normal password).")
        print(" - Ensure port is 587 (TLS) or 465 (SSL).")
        print(" - Check that your firewall permits outbound connections on that port.")
        sys.exit(1)


if __name__ == "__main__":
    verify()
