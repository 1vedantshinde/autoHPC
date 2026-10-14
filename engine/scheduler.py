import os

FAIL_MODES = ("none", "transient", "persistent")
MODES = ("sequential", "parallel")


class ConfigError(ValueError):
    pass


DEFAULTS = dict(total_samples=20_000_000, n_jobs=8, mode="sequential", workers=1, max_retries=2,
                base_seed=42, fail_mode="none", inject_count=0, fail_attempts=1)


def validate_config(cfg):
    c = {**DEFAULTS, **cfg}
    for k in ("total_samples", "n_jobs", "workers", "max_retries", "base_seed", "inject_count", "fail_attempts"):
        if not isinstance(c[k], int) or isinstance(c[k], bool):
            raise ConfigError(f"{k} must be an integer")
    if c["n_jobs"] < 1:
        raise ConfigError("n_jobs must be at least 1")
    if c["total_samples"] < c["n_jobs"]:
        raise ConfigError("total_samples must be >= n_jobs")
    if c["mode"] not in MODES:
        raise ConfigError(f"mode must be one of {MODES}")
    if not (1 <= c["workers"] <= 2 * (os.cpu_count() or 1)):
        raise ConfigError("workers out of range for this machine")
    if not (0 <= c["max_retries"] <= 10):
        raise ConfigError("max_retries must be between 0 and 10")
    if c["base_seed"] < 0:
        raise ConfigError("base_seed must be >= 0")
    if c["fail_mode"] not in FAIL_MODES:
        raise ConfigError(f"fail_mode must be one of {FAIL_MODES}")
    if not (0 <= c["inject_count"] <= c["n_jobs"]):
        raise ConfigError("inject_count must be between 0 and n_jobs")
    if c["fail_attempts"] < 1:
        raise ConfigError("fail_attempts must be >= 1")
    return c


def split_jobs(cfg):
    base, extra = divmod(cfg["total_samples"], cfg["n_jobs"])
    jobs = []
    for i in range(cfg["n_jobs"]):
        injected = cfg["fail_mode"] != "none" and i < cfg["inject_count"]
        jobs.append(dict(index=i, n_samples=base + (1 if i < extra else 0),
                         seed=cfg["base_seed"] + i,
                         fail_mode=cfg["fail_mode"] if injected else "none"))
    return jobs
