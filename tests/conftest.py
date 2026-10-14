import pytest


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOHPC_LOG_DIR", str(tmp_path / "logs"))
    for v in ("AUTOHPC_WEBHOOK_URL", "AUTOHPC_SMTP_HOST", "AUTOHPC_SMTP_TO"):
        monkeypatch.delenv(v, raising=False)
