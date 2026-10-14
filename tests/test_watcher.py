import json
from pathlib import Path

from storage.database import Database
from watcher import process_inbox

GOOD = {"name": "t", "total_samples": 20000, "n_jobs": 2}


def run(tmp_path, files):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, content in files.items():
        (inbox / name).write_text(content if isinstance(content, str) else json.dumps(content))
    db = Database(tmp_path / "w.db")
    out = process_inbox(db, inbox, tmp_path / "processed", tmp_path / "rejected")
    return db, out


def test_good_spec_processed_and_archived(tmp_path):
    db, out = run(tmp_path, {"a.json": GOOD})
    assert out[0]["outcome"] == "processed" and out[0]["status"] == "COMPLETED"
    assert (tmp_path / "processed" / "a.json").exists()
    assert (tmp_path / "processed" / "a.json.result.json").exists()
    assert not (tmp_path / "inbox" / "a.json").exists()
    assert len(db.list_experiments()) == 1


def test_malformed_and_invalid_specs_rejected_with_reason(tmp_path):
    db, out = run(tmp_path, {"bad.json": "{ nope", "inv.json": {"total_samples": 10, "n_jobs": 0}})
    assert {o["outcome"] for o in out} == {"rejected"}
    assert (tmp_path / "rejected" / "bad.json.error.txt").exists()
    assert "n_jobs" in (tmp_path / "rejected" / "inv.json.error.txt").read_text()
    assert db.list_experiments() == []


def test_duplicate_file_content_rejected(tmp_path):
    db, out = run(tmp_path, {"a.json": GOOD, "b.json": GOOD})
    assert sorted(o["outcome"] for o in out) == ["processed", "rejected"]
    assert len(db.list_experiments()) == 1


def test_failure_injection_via_inbox(tmp_path):
    spec = {**GOOD, "fail_mode": "transient", "inject_count": 1, "fail_attempts": 1}
    _, out = run(tmp_path, {"f.json": spec})
    assert out[0]["status"] == "COMPLETED" and out[0]["retries"] == 1
