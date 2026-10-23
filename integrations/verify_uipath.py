"""Utility script to test and verify UiPath Orchestrator Queue integration for AutoHPC.

Run this script to verify that your UiPath settings in .env can push to Orchestrator:
    python -m integrations.verify_uipath
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from integrations.uipath_client import is_uipath_configured, push_to_uipath


def verify():
    orch_url = os.environ.get("UIPATH_ORCHESTRATOR_URL")
    webhook_url = os.environ.get("UIPATH_WEBHOOK_URL")
    token = os.environ.get("UIPATH_ACCESS_TOKEN")
    tenant = os.environ.get("UIPATH_TENANT_LOGICAL_NAME")
    queue = os.environ.get("UIPATH_QUEUE_NAME", "AutoHPC_Experiments")
    folder_id = os.environ.get("UIPATH_FOLDER_ID")

    print("=" * 60)
    print("AutoHPC UiPath Integration Verification")
    print("=" * 60)
    print(f"Orchestrator URL: {orch_url or '<NOT SET>'}")
    print(f"Webhook URL:      {webhook_url or '<NOT SET>'}")
    print(f"Tenant Name:      {tenant or '<NOT SET>'}")
    print(f"Folder ID:        {folder_id or '<NOT SET>'}")
    print(f"Queue Name:       {queue}")
    print(f"Access Token:     {('***' + token[-6:]) if token else '<NOT SET>'}")
    print("=" * 60)

    if not is_uipath_configured():
        print("\n[ERROR] UiPath is not configured in .env!")
        print("Please set UIPATH_ORCHESTRATOR_URL and UIPATH_ACCESS_TOKEN (or UIPATH_WEBHOOK_URL).")
        sys.exit(1)

    test_payload = {
        "experiment_id": "TEST-RPA-999",
        "status": "COMPLETED",
        "completed": 4,
        "failed": 0,
        "retries": 0,
        "wall_time": 0.42,
        "pi_estimate": 3.14159265,
        "abs_error": 8.4e-08,
    }

    print("\nAttempting to push test experiment to UiPath Orchestrator Queue...")
    result = push_to_uipath(test_payload, queue_name=queue)
    print("Result:", result)

    if result.get("status") == "ok":
        print("\n[SUCCESS] Successfully added queue item to UiPath Orchestrator!")
        print(f"Go to UiPath Orchestrator -> Queues -> '{queue}' to view the item.")
        print("Then in Studio Web, click 'Test' / 'Run' to process it!")
    else:
        print("\n[FAILED] Could not push to UiPath:")
        print("Reason / Error:", result.get("error") or result.get("reason"))
        print("\nTips:")
        print(" 1. Ensure the Queue name in Orchestrator exactly matches UIPATH_QUEUE_NAME.")
        print(" 2. If using Modern Folders, set UIPATH_FOLDER_ID (from fid in your browser URL).")
        print(" 3. Ensure your token has OR.Queues permissions.")


if __name__ == "__main__":
    verify()
