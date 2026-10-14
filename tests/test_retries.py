import pytest
from engine.executor import run_experiment
from engine.scheduler import ConfigError
from storage.database import Database

BASE = dict(total_samples=40_000, n_jobs=4, max_retries=2)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


@pytest.mark.parametrize("mode,workers", [("sequential", 1), ("parallel", 2)])
def test_normal_run(db, mode, workers):
    out = run_experiment(db, {**BASE, "mode": mode, "workers": workers})
    assert out["status"] == "COMPLETED" and out["completed"] == 4 and out["retries"] == 0
    assert all(j["state"] == "COMPLETED" for j in db.get_jobs(out["experiment_id"]))


@pytest.mark.parametrize("mode,workers", [("sequential", 1), ("parallel", 2)])
def test_transient_failure_recovers(db, mode, workers):
    out = run_experiment(db, {**BASE, "mode": mode, "workers": workers,
                              "fail_mode": "transient", "inject_count": 2, "fail_attempts": 1})
    assert out["status"] == "COMPLETED" and out["retries"] == 2
    attempts = db.get_attempts(out["experiment_id"])
    assert sum(a["outcome"] == "ERROR" for a in attempts) == 2


@pytest.mark.parametrize("mode,workers", [("sequential", 1), ("parallel", 2)])
def test_persistent_failure_hits_retry_limit(db, mode, workers):
    out = run_experiment(db, {**BASE, "mode": mode, "workers": workers,
                              "fail_mode": "persistent", "inject_count": 1})
    assert out["status"] == "PARTIAL" and out["failed"] == 1 and out["completed"] == 3
    failed = [j for j in db.get_jobs(out["experiment_id"]) if j["state"] == "FAILED"][0]
    assert failed["retries"] == 2
    n_attempts = [a for a in db.get_attempts(out["experiment_id"]) if a["job_id"] == failed["id"]]
    assert len(n_attempts) == 3  # 1 original + 2 retries


def test_invalid_config_launches_nothing(db):
    with pytest.raises(ConfigError):
        run_experiment(db, {**BASE, "n_jobs": 0})
    assert db.list_experiments() == []


def test_zero_retries_means_immediate_failure(db):
    out = run_experiment(db, {**BASE, "max_retries": 0, "fail_mode": "persistent", "inject_count": 4})
    assert out["status"] == "FAILED" and out["retries"] == 0
