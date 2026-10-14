"""Outbound notifications. Channels are enabled by environment variables:
  AUTOHPC_WEBHOOK_URL                      -> JSON POST (n8n, Slack incoming webhook, any HTTP endpoint)
  AUTOHPC_SMTP_HOST/PORT/USER/PASS/FROM/TO -> e-mail
Every notification is always appended to logs/notifications.log. notify() never raises."""
import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage

from integrations.logging_setup import log_dir

log = logging.getLogger("autohpc.notify")


def format_message(s):
    pi = f"{s['pi_estimate']:.6f}" if s.get("pi_estimate") is not None else "n/a"
    err = f"{s['abs_error']:.2e}" if s.get("abs_error") is not None else "n/a"
    return (f"AutoHPC experiment {s['experiment_id']} {s['status']}: {s['completed']} ok, "
            f"{s['failed']} failed, {s['retries']} retries, wall {s['wall_time']:.2f}s, "
            f"pi={pi}, abs error={err}")


def send_webhook(url, message, summary=None, timeout=10):
    payload = {"text": message, "content": message, "summary": summary}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def send_email(subject, message):
    host = os.environ["AUTOHPC_SMTP_HOST"]
    port = int(os.environ.get("AUTOHPC_SMTP_PORT", "587"))
    user, pw = os.environ.get("AUTOHPC_SMTP_USER"), os.environ.get("AUTOHPC_SMTP_PASS")
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, os.environ["AUTOHPC_SMTP_TO"]
    msg["From"] = os.environ.get("AUTOHPC_SMTP_FROM", user or "autohpc@localhost")
    msg.set_content(message)
    with smtplib.SMTP(host, port, timeout=10) as s:
        if user:
            s.starttls()
            s.login(user, pw or "")
        s.send_message(msg)


def notify_message(message, subject="AutoHPC notification", summary=None):
    results = {}
    url = os.environ.get("AUTOHPC_WEBHOOK_URL")
    if url:
        try:
            results["webhook"] = f"ok ({send_webhook(url, message, summary)})"
        except Exception as e:  # a failed notification must never break the pipeline
            results["webhook"] = f"error: {type(e).__name__}: {e}"
            log.warning("Webhook notification failed: %s", e)
    if os.environ.get("AUTOHPC_SMTP_HOST") and os.environ.get("AUTOHPC_SMTP_TO"):
        try:
            send_email(subject, message)
            results["email"] = "ok"
        except Exception as e:
            results["email"] = f"error: {type(e).__name__}: {e}"
            log.warning("Email notification failed: %s", e)
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "notifications.log", "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | {message} | {results}\n")
    log.info("Notification sent: %s", message)
    return results


def notify(summary):
    return notify_message(format_message(summary), f"AutoHPC experiment {summary['experiment_id']} {summary['status']}", summary)
