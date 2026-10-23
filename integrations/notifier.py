"""Outbound notifications.

Channels are enabled by environment variables:
  AUTOHPC_WEBHOOK_URL                      -> JSON POST
  AUTOHPC_SMTP_HOST/PORT/USER/PASS/FROM/TO -> Email (HTML + Plain text)
  UIPATH_WEBHOOK_URL or UIPATH_ORCHESTRATOR_URL -> UiPath RPA Orchestrator Queue / Webhook

Every notification attempt is appended to logs/notifications.log.
notify() never raises, even if a notification channel or logging fails.
"""

import html
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


def format_html_message(message, summary=None, subject="AutoHPC Notification"):
    """Format an attractive HTML notification card for email clients."""
    status = summary.get("status", "NOTICE") if summary else "ALERT"
    status_color = "#107c41" if status == "COMPLETED" else "#d83b01" if status in ("FAILED", "ERROR", "REJECTED") else "#0078d4"

    exp_id = summary.get("experiment_id", "N/A") if summary else "N/A"
    wall = f"{summary.get('wall_time', 0):.3f}s" if summary and summary.get("wall_time") is not None else "N/A"
    pi = f"{summary.get('pi_estimate', 0):.6f}" if summary and summary.get("pi_estimate") is not None else "N/A"
    abs_err = f"{summary.get('abs_error', 0):.2e}" if summary and summary.get("abs_error") is not None else "N/A"
    completed = summary.get("completed", 0) if summary else "N/A"
    failed = summary.get("failed", 0) if summary else "N/A"
    retries = summary.get("retries", 0) if summary else "N/A"

    escaped_msg = html.escape(message).replace("\n", "<br>")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #24292e; }}
    .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #e1e4e8; }}
    .header {{ background-color: {status_color}; color: #ffffff; padding: 20px; font-size: 20px; font-weight: 600; text-align: center; }}
    .content {{ padding: 24px; }}
    .badge {{ display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: bold; border-radius: 12px; background: {status_color}; color: #ffffff; }}
    .metrics-table {{ width: 100%; border-collapse: collapse; margin-top: 18px; margin-bottom: 18px; }}
    .metrics-table td {{ padding: 8px 12px; border-bottom: 1px solid #eaecef; font-size: 14px; }}
    .metrics-table td.label {{ color: #586069; font-weight: 500; width: 40%; }}
    .metrics-table td.value {{ font-family: 'SFMono-Regular', Consolas, monospace; font-weight: 600; }}
    .footer {{ background: #fafbfc; border-top: 1px solid #eaecef; padding: 12px 24px; font-size: 12px; color: #6a737d; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      AutoHPC Scientific Workflow Update
    </div>
    <div class="content">
      <p style="font-size: 15px; line-height: 1.5; margin-bottom: 18px;">
        {escaped_msg}
      </p>
      <table class="metrics-table">
        <tr><td class="label">Experiment ID</td><td class="value">{exp_id}</td></tr>
        <tr><td class="label">Status</td><td class="value"><span class="badge">{status}</span></td></tr>
        <tr><td class="label">Execution Wall Time</td><td class="value">{wall}</td></tr>
        <tr><td class="label">Monte Carlo &pi; Estimate</td><td class="value">{pi}</td></tr>
        <tr><td class="label">Absolute Error</td><td class="value">{abs_err}</td></tr>
        <tr><td class="label">Jobs Summary</td><td class="value">{completed} OK, {failed} Failed ({retries} Retries)</td></tr>
      </table>
    </div>
    <div class="footer">
      AutoHPC Process Automation Bot &bull; System Notification
    </div>
  </div>
</body>
</html>"""
    return html_content


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


def send_email(subject, message, html_body=None):
    """Send an email using the configured SMTP server with both plain text and optional HTML."""
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
        raise ValueError("Set AUTOHPC_SMTP_FROM or AUTOHPC_SMTP_USER.")

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = sender
    email["To"] = recipient
    email.set_content(message)

    if html_body:
        email.add_alternative(html_body, subtype="html")

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
                html_body = format_html_message(message, summary=summary, subject=subject)
                send_email(subject, message, html_body=html_body)
                results["email"] = "ok"
            except Exception as error:
                results["email"] = (
                    f"error: {type(error).__name__}: {error}"
                )
                log.warning("Email notification failed: %s", error)

        # UiPath RPA Orchestrator Queue / Webhook channel
        try:
            from integrations.uipath_client import is_uipath_configured, push_to_uipath
            if is_uipath_configured():
                res = push_to_uipath(summary or {"message": message, "subject": subject})
                results["uipath"] = f"{res.get('status')} ({res.get('channel', 'uipath')})"
        except Exception as error:
            results["uipath"] = f"error: {type(error).__name__}: {error}"
            log.warning("UiPath dispatch failed: %s", error)

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
