import math
import pytest
from engine.validator import validate_result
from workloads.monte_carlo_pi import run_job, TransientError


def test_estimate_close_to_pi():
    r = run_job(1, 2_000_000, 1)
    assert abs(r["estimate"] - math.pi) < 0.02


def test_seed_reproducible():
    assert run_job(1, 100_000, 7)["inside"] == run_job(2, 100_000, 7)["inside"]


def test_transient_injection_succeeds_after_attempts():
    with pytest.raises(TransientError):
        run_job(1, 1000, 1, attempt=1, fail_mode="transient", fail_attempts=1)
    assert run_job(1, 1000, 1, attempt=2, fail_mode="transient", fail_attempts=1)["n_samples"] == 1000


def test_validator_accepts_valid_and_rejects_invalid():
    good = run_job(1, 1000, 1)
    assert validate_result(good)[0]
    assert not validate_result({**good, "estimate": float("nan")})[0]
    assert not validate_result({**good, "estimate": 9.0})[0]
    assert not validate_result({**good, "n_samples": 0})[0]
    assert not validate_result({"foo": 1})[0]
    assert not validate_result(None)[0]
