import json
import urllib.request
from integrations.uipath_client import is_uipath_configured, push_to_uipath

SAMPLE_SUMMARY = {
    "experiment_id": 99,
    "status": "COMPLETED",
    "completed": 4,
    "failed": 0,
    "retries": 1,
    "wall_time": 2.15,
    "pi_estimate": 3.14159,
    "abs_error": 2.3e-05,
}


def test_uipath_not_configured_returns_skipped(monkeypatch):
    monkeypatch.delenv("UIPATH_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("UIPATH_ORCHESTRATOR_URL", raising=False)
    monkeypatch.delenv("UIPATH_ACCESS_TOKEN", raising=False)
    
    assert not is_uipath_configured()
    res = push_to_uipath(SAMPLE_SUMMARY)
    assert res["status"] == "skipped"


def test_uipath_webhook_dispatch(monkeypatch):
    sent_requests = []

    class MockResponse:
        def __init__(self, status=200):
            self.status = status
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, timeout=10):
        sent_requests.append(req)
        return MockResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("UIPATH_WEBHOOK_URL", "https://cloud.uipath.com/mock/webhook")

    assert is_uipath_configured()
    res = push_to_uipath(SAMPLE_SUMMARY)
    assert res["status"] == "ok"
    assert res["channel"] == "uipath_webhook"
    assert len(sent_requests) == 1
    
    payload = json.loads(sent_requests[0].data.decode("utf-8"))
    assert payload["source"] == "AutoHPC"
    assert payload["data"]["experiment_id"] == 99


def test_uipath_orchestrator_queue_dispatch(monkeypatch):
    sent_requests = []

    class MockResponse:
        def __init__(self, status=201):
            self.status = status
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, timeout=10):
        sent_requests.append(req)
        return MockResponse(201)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.delenv("UIPATH_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("UIPATH_ORCHESTRATOR_URL", "https://cloud.uipath.com/myorg/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "mock_token_123")
    monkeypatch.setenv("UIPATH_TENANT_LOGICAL_NAME", "DefaultTenant")
    monkeypatch.setenv("UIPATH_QUEUE_NAME", "TestQueue")

    assert is_uipath_configured()
    res = push_to_uipath(SAMPLE_SUMMARY)
    assert res["status"] == "ok"
    assert res["channel"] == "uipath_orchestrator"
    assert len(sent_requests) == 1

    req = sent_requests[0]
    assert "Bearer mock_token_123" in req.headers["Authorization"]
    assert req.headers["X-uipath-tenantname"] == "DefaultTenant"

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["itemData"]["Name"] == "TestQueue"
    assert payload["itemData"]["SpecificContent"]["ExperimentID"] == 99
