import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from integrations.notifier import notify, notify_message

SUMMARY = dict(experiment_id=7, status="COMPLETED", completed=4, failed=0, retries=1,
               wall_time=1.5, pi_estimate=3.14, abs_error=0.001)


def _server():
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def test_webhook_delivery(monkeypatch):
    srv, got = _server()
    monkeypatch.setenv("AUTOHPC_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")
    res = notify(SUMMARY)
    srv.shutdown()
    assert res["webhook"].startswith("ok")
    assert "experiment 7 COMPLETED" in got[0]["text"] and got[0]["summary"]["retries"] == 1


def test_unreachable_webhook_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOHPC_WEBHOOK_URL", "http://127.0.0.1:1/hook")
    res = notify_message("hello")
    assert res["webhook"].startswith("error")
    assert "hello" in (tmp_path / "logs" / "notifications.log").read_text()


def test_email_html_formatting_and_dispatch(monkeypatch):
    sent_emails = []

    class MockSMTP:
        def __init__(self, host, port, timeout=15):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent_emails.append(msg)

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)
    monkeypatch.setenv("AUTOHPC_SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("AUTOHPC_SMTP_TO", "researcher@example.com")
    monkeypatch.setenv("AUTOHPC_SMTP_USER", "bot@example.com")

    res = notify(SUMMARY)
    assert res["email"] == "ok"
    assert len(sent_emails) == 1
    msg = sent_emails[0]
    assert msg["To"] == "researcher@example.com"
    assert "AutoHPC experiment 7 COMPLETED" in msg["Subject"]
    # Check that HTML alternative was added
    payloads = msg.get_payload()
    assert isinstance(payloads, list)
    assert any("text/html" in str(p.get_content_type()) for p in payloads)
