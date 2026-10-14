import pytest
from engine.state_manager import InvalidTransition, RUNNING, COMPLETED, FAILED
from storage.database import Database, DuplicateSubmission

CFG = dict(mode="sequential", workers=1)


def test_illegal_transitions_blocked(tmp_path):
    db = Database(tmp_path / "t.db")
    e = db.create_experiment(CFG)
    j = db.add_job(e, 0, 10, 1)
    with pytest.raises(InvalidTransition):
        db.set_state(j, COMPLETED)  # QUEUED -> COMPLETED not allowed
    db.set_state(j, RUNNING)
    db.set_state(j, FAILED)
    with pytest.raises(InvalidTransition):
        db.set_state(j, RUNNING)  # terminal


def test_persistence_across_reopen(tmp_path):
    p = tmp_path / "t.db"
    db = Database(p)
    e = db.create_experiment(CFG)
    db.add_job(e, 0, 10, 1)
    db2 = Database(p)  # simulates application restart
    assert len(db2.list_experiments()) == 1 and len(db2.get_jobs(e)) == 1


def test_duplicate_submission_rejected(tmp_path):
    db = Database(tmp_path / "t.db")
    db.create_experiment(CFG, "abc")
    with pytest.raises(DuplicateSubmission):
        db.create_experiment(CFG, "abc")
