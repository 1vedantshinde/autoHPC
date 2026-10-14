"""Monte Carlo estimation of pi. run_job is a module-level function so it can be pickled for process pools."""
import time
import numpy as np

CHUNK = 2_000_000  # keeps memory use small regardless of sample count


class TransientError(RuntimeError):
    """Retryable error (also used for injected failures)."""


def run_job(job_id, n_samples, seed, attempt=1, fail_mode="none", fail_attempts=1):
    start = time.perf_counter()
    if fail_mode == "transient" and attempt <= fail_attempts:
        raise TransientError(f"Injected transient failure (job {job_id}, attempt {attempt})")
    if fail_mode == "persistent":
        raise TransientError(f"Injected persistent failure (job {job_id}, attempt {attempt})")
    rng = np.random.default_rng(seed)  # per-job generator: no shared RNG state
    inside, remaining = 0, int(n_samples)
    while remaining > 0:
        k = min(remaining, CHUNK)
        x = rng.random(k)
        y = rng.random(k)
        inside += int(np.count_nonzero(x * x + y * y <= 1.0))
        remaining -= k
    return {
        "job_id": job_id,
        "n_samples": int(n_samples),
        "inside": inside,
        "estimate": 4.0 * inside / n_samples,
        "seed": seed,
        "duration": time.perf_counter() - start,
    }
