
"""Outbound notifications.

Channels are enabled by environment variables:
  AUTOHPC_WEBHOOK_URL                      -> JSON POST
  AUTOHPC_SMTP_HOST/PORT/USER/PASS/FROM/TO -> Email

Every notification attempt is appended to logs/notifications.log.
notify() never raises, even if a notification channel or logging fails.
"""

import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from integrations.logging_setup import log_dir

# Load environment variables from the project's .env file.
# Existing environment variables take precedence over .env values.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

log = logging.getLogger("autohpc.notify")


def format_message(summary):
    """Format an experiment summary into a readable notification."""
    pi_value = summary.get("pi_estimate")
    error_value = summary.get("abs_error")

    pi = f"{pi_value:.6f}" if pi_value is not None else "n/a"
    error = f"{error_value:.2e}" if error_value is not None else "n/a"

    return (
        f"AutoHPC experiment {summary.get('experiment_id', 'unknown')} "
        f"{summary.get('status', 'UNKNOWN')}: "
        f"{summary.get('completed', 0)} ok, "
        f"{summary.get('failed', 0)} failed, "
        f"{summary.get('retries', 0)} retries, "
        f"wall {summary.get('wall_time', 0):.2f}s, "
        f"pi={pi}, abs error={error}"
    )


def send_webhook(url, message, summary=None, timeout=10):
    """Send a JSON payload to a configured webhook URL."""
    payload = {
        "text": message,
        "content": message,
        "summary": summary,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


def send_email(subject, message):
    """Send an email using the configured SMTP server."""
    host = os.environ.get("AUTOHPC_SMTP_HOST")
    recipient = os.environ.get("AUTOHPC_SMTP_TO")

    if not host:
        raise ValueError("AUTOHPC_SMTP_HOST is not configured.")
    if not recipient:
        raise ValueError("AUTOHPC_SMTP_TO is not configured.")

    port = int(os.environ.get("AUTOHPC_SMTP_PORT", "587"))
    username = os.environ.get("AUTOHPC_SMTP_USER")
    password = os.environ.get("AUTOHPC_SMTP_PASS")
    sender = os.environ.get("AUTOHPC_SMTP_FROM") or username

    if not sender:
        raise ValueError(
            "Set AUTOHPC_SMTP_FROM or AUTOHPC_SMTP_USER."
        )

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = sender
    email["To"] = recipient
    email.set_content(message)

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()

        if username:
            smtp.login(username, password or "")

        smtp.send_message(email)


def _write_notification_log(message, results):
    """Append a notification attempt to the notification log."""
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)

    log_path = directory / "notifications.log"
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp} | {message} | {results}\n")


def notify_message(
    message,
    subject="AutoHPC notification",
    summary=None,
):
    """Send configured notifications and return each channel's result.

    Failures are recorded where possible and never propagated to the caller.
    """
    results = {}

    try:
        webhook_url = os.environ.get("AUTOHPC_WEBHOOK_URL")

        if webhook_url:
            try:
                status_code = send_webhook(
                    webhook_url,
                    message,
                    summary,
                )
                results["webhook"] = f"ok ({status_code})"
            except Exception as error:
                results["webhook"] = (
                    f"error: {type(error).__name__}: {error}"
                )
                log.warning("Webhook notification failed: %s", error)

        smtp_host = os.environ.get("AUTOHPC_SMTP_HOST")
        smtp_recipient = os.environ.get("AUTOHPC_SMTP_TO")

        if smtp_host and smtp_recipient:
            try:
                send_email(subject, message)
                results["email"] = "ok"
            except Exception as error:
                results["email"] = (
                    f"error: {type(error).__name__}: {error}"
                )
                log.warning("Email notification failed: %s", error)

        if not results:
            results["notification"] = (
                "skipped: no notification channel configured"
            )

    except Exception as error:
        # Catch unexpected notification errors too.
        results["notification"] = (
            f"error: {type(error).__name__}: {error}"
        )
        log.exception("Unexpected notification error")

    finally:
        try:
            _write_notification_log(message, results)
        except Exception:
            # A logging failure must not crash the experiment pipeline.
            log.exception("Could not write notifications.log")

    log.info("Notification attempt completed: %s", results)
    return results


def notify(summary):
    """Notify configured channels about an experiment summary."""
    try:
        message = format_message(summary)
        experiment_id = summary.get("experiment_id", "unknown")
        status = summary.get("status", "UNKNOWN")

        subject = f"AutoHPC experiment {experiment_id} {status}"

        return notify_message(
            message=message,
            subject=subject,
            summary=summary,
        )

    except Exception as error:
        # Preserve the never-raise contract even if formatting fails.
        log.exception("Could not prepare experiment notification")
        return {
            "notification": (
                f"error: {type(error).__name__}: {error}"
            )
        }
