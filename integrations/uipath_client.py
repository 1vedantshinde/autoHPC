"""UiPath Orchestrator Integration Module for AutoHPC.

Provides functions to push experiment summaries, failure alerts, or RPA queue items
to UiPath Orchestrator via its OData REST API or generic UiPath webhook triggers.
If Orchestrator is not configured, operations are safely recorded or mocked without raising errors.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

log = logging.getLogger("autohpc.uipath")


def is_uipath_configured():
    """Check if UiPath Orchestrator or webhook credentials are provided."""
    return bool(
        os.environ.get("UIPATH_WEBHOOK_URL")
        or (
            os.environ.get("UIPATH_ORCHESTRATOR_URL")
            and os.environ.get("UIPATH_ACCESS_TOKEN")
        )
    )


def push_to_uipath(summary_or_event, queue_name=None, timeout=10):
    """Push an experiment result or event to UiPath.
    
    Supports:
    1. Direct UiPath Webhook / Orchestrator integration via UIPATH_WEBHOOK_URL
    2. UiPath Orchestrator Queues API via UIPATH_ORCHESTRATOR_URL + UIPATH_ACCESS_TOKEN
    
    Never raises an exception so AutoHPC execution is never blocked.
    """
    queue = queue_name or os.environ.get("UIPATH_QUEUE_NAME", "AutoHPC_Experiments")
    webhook_url = os.environ.get("UIPATH_WEBHOOK_URL")
    orch_url = os.environ.get("UIPATH_ORCHESTRATOR_URL")
    token = os.environ.get("UIPATH_ACCESS_TOKEN")

    if not is_uipath_configured():
        log.debug("UiPath is not configured; skipping dispatch.")
        return {"status": "skipped", "reason": "no credentials"}

    # Approach 1: Generic UiPath Integration Service / Webhook endpoint
    if webhook_url:
        payload = {
            "source": "AutoHPC",
            "queue_name": queue,
            "data": summary_or_event,
        }
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload, default=str).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log.info("Dispatched event to UiPath webhook: HTTP %s", resp.status)
                return {"status": "ok", "channel": "uipath_webhook", "code": resp.status}
        except Exception as e:
            log.warning("Failed to dispatch to UiPath webhook: %s", e)
            return {"status": "error", "error": str(e)}

    # Approach 2: UiPath Orchestrator OData Queue Item API
    if orch_url and token:
        # Standard Cloud endpoint: {orch_url}/odata/Queues/UiPathODataSvc.AddQueueItem
        clean_url = orch_url.rstrip("/")
        endpoint = f"{clean_url}/odata/Queues/UiPathODataSvc.AddQueueItem"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        tenant_name = os.environ.get("UIPATH_TENANT_LOGICAL_NAME")
        if tenant_name:
            headers["X-UIPATH-TenantName"] = tenant_name

        folder_id = os.environ.get("UIPATH_FOLDER_ID")
        if folder_id:
            headers["X-UIPATH-OrganizationUnitId"] = str(folder_id)

        odata_payload = {
            "itemData": {
                "Name": queue,
                "Priority": "High" if summary_or_event.get("status") in ("FAILED", "ERROR") else "Normal",
                "SpecificContent": {
                    "ExperimentID": summary_or_event.get("experiment_id"),
                    "Status": summary_or_event.get("status"),
                    "WallTime": summary_or_event.get("wall_time"),
                    "PiEstimate": summary_or_event.get("pi_estimate"),
                    "AbsError": summary_or_event.get("abs_error"),
                    "Completed": summary_or_event.get("completed"),
                    "Failed": summary_or_event.get("failed"),
                    "Retries": summary_or_event.get("retries"),
                },
            }
        }
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(odata_payload, default=str).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                log.info("Added queue item to UiPath Orchestrator Queue '%s': HTTP %s", queue, resp.status)
                return {"status": "ok", "channel": "uipath_orchestrator", "code": resp.status}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            log.warning("Failed to post to UiPath Orchestrator Queue: %s - Body: %s", e, err_body)
            return {"status": "error", "error": f"{e}: {err_body}"}
        except Exception as e:
            log.warning("Failed to post to UiPath Orchestrator Queue: %s", e)
            return {"status": "error", "error": str(e)}

    return {"status": "skipped"}
