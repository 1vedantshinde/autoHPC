import pytest
from fastapi.testclient import TestClient

import api

BODY = {"total_samples": 20000, "n_jobs": 4}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOHPC_DB", str(tmp_path / "api.db"))
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_submit_then_poll_result(client):
    r = client.post("/experiments", json=BODY)
    assert r.status_code == 202
    exp_id = r.json()["experiment_id"]
    data = client.get(f"/experiments/{exp_id}").json()  # TestClient has already run the background task
    assert data["experiment"]["status"] == "COMPLETED" and len(data["jobs"]) == 4
    assert "# Jobs" in client.get(f"/experiments/{exp_id}/report").text


def test_invalid_config_422_and_nothing_created(client):
    assert client.post("/experiments", json={**BODY, "n_jobs": 0}).status_code == 422
    assert client.post("/experiments", json={**BODY, "total_samples": "abc"}).status_code == 422
    assert client.get("/experiments").json() == []


def test_duplicate_submission_key_409(client):
    assert client.post("/experiments", json={**BODY, "submission_key": "k1"}).status_code == 202
    assert client.post("/experiments", json={**BODY, "submission_key": "k1"}).status_code == 409


def test_unknown_experiment_404(client):
    assert client.get("/experiments/999").status_code == 404


def test_retry_visible_through_api(client):
    r = client.post("/experiments", json={**BODY, "fail_mode": "transient", "inject_count": 1})
    data = client.get(f"/experiments/{r.json()['experiment_id']}").json()
    assert data["experiment"]["status"] == "COMPLETED"
    assert any(a["outcome"] == "ERROR" for a in data["attempts"])
