import pytest
from engine.scheduler import ConfigError, split_jobs, validate_config


def test_split_conserves_samples_and_unique_seeds():
    cfg = validate_config(dict(total_samples=1003, n_jobs=4))
    jobs = split_jobs(cfg)
    assert sum(j["n_samples"] for j in jobs) == 1003
    assert len({j["seed"] for j in jobs}) == 4


@pytest.mark.parametrize("bad", [dict(n_jobs=0), dict(total_samples=1, n_jobs=5), dict(mode="gpu"),
                                 dict(workers=0), dict(max_retries=-1), dict(fail_mode="boom"),
                                 dict(n_jobs=2, inject_count=3), dict(total_samples="x")])
def test_invalid_config_rejected(bad):
    with pytest.raises(ConfigError):
        validate_config(bad)


def test_failure_injection_targets_first_jobs():
    cfg = validate_config(dict(total_samples=1000, n_jobs=4, fail_mode="transient", inject_count=2))
    assert [j["fail_mode"] for j in split_jobs(cfg)] == ["transient", "transient", "none", "none"]
