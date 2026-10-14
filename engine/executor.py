import logging
import math
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from multiprocessing import get_context

from engine.retry_policy import should_retry
from engine.scheduler import split_jobs, validate_config
from engine.state_manager import RUNNING, RETRYING, COMPLETED, FAILED
from engine.validator import validate_result
from workloads.monte_carlo_pi import run_job

log = logging.getLogger("autohpc.engine")


def _args(job, attempt, cfg):
    return (job["id"], job["n_samples"], job["seed"], attempt, job["fail_mode"], cfg["fail_attempts"])


def _success(db, job, attempt, res, results):
    ok, reason = validate_result(res)
    db.add_attempt(job["id"], attempt, res.get("duration", 0.0) if isinstance(res, dict) else 0.0,
                   "OK" if ok else "INVALID", None if ok else reason)
    if ok:
        db.set_state(job["id"], COMPLETED, inside=res["inside"], estimate=res["estimate"], duration=res["duration"])
        results[job["id"]] = res
    else:
        db.set_state(job["id"], FAILED, error=f"Validation failed: {reason}")  # deterministic: no retry


def _failure(db, job, attempt, exc, max_retries):
    """Record a failed attempt. Returns True if the job should be retried."""
    msg = f"{type(exc).__name__}: {exc}"
    db.add_attempt(job["id"], attempt, 0.0, "ERROR", msg)
    log.warning("Job %s attempt %s failed: %s", job["id"], attempt, msg)
    if should_retry(exc, attempt, max_retries):
        db.set_state(job["id"], RETRYING, retries=attempt, error=msg)
        return True
    db.set_state(job["id"], FAILED, error=msg)
    log.error("Job %s FAILED after %s attempt(s): %s", job["id"], attempt, msg)
    return False


def submit_experiment(db, cfg, submission_key=None):
    """Validate, persist experiment + QUEUED jobs. Raises ConfigError / DuplicateSubmission."""
    cfg = validate_config(cfg)
    exp_id = db.create_experiment(cfg, submission_key)
    jobs = split_jobs(cfg)
    for j in jobs:
        j["id"] = db.add_job(exp_id, j["index"], j["n_samples"], j["seed"])
    log.info("Experiment %s created: %d jobs, mode=%s, workers=%s", exp_id, len(jobs), cfg["mode"], cfg["workers"])
    return exp_id, cfg, jobs


def execute_experiment(db, exp_id, cfg, jobs, progress=None):
    results, done_count, total = {}, 0, len(jobs)
    t0 = time.perf_counter()

    if cfg["mode"] == "sequential":
        for job in jobs:
            attempt = 1
            while True:
                db.set_state(job["id"], RUNNING)
                try:
                    res = run_job(*_args(job, attempt, cfg))
                except Exception as exc:
                    if _failure(db, job, attempt, exc, cfg["max_retries"]):
                        attempt += 1
                        continue
                else:
                    _success(db, job, attempt, res, results)
                break
            done_count += 1
            if progress:
                progress(done_count, total)
    else:
        ctx = get_context("spawn")  # safe under Streamlit/pytest and on every OS
        with ProcessPoolExecutor(max_workers=cfg["workers"], mp_context=ctx) as pool:
            pending = {}

            def submit(job, attempt):
                db.set_state(job["id"], RUNNING)
                pending[pool.submit(run_job, *_args(job, attempt, cfg))] = (job, attempt)

            for job in jobs:
                submit(job, 1)
            while pending:
                finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
                for fut in finished:
                    job, attempt = pending.pop(fut)
                    try:
                        res = fut.result()
                    except Exception as exc:
                        if _failure(db, job, attempt, exc, cfg["max_retries"]):
                            submit(job, attempt + 1)
                            continue
                    else:
                        _success(db, job, attempt, res, results)
                    done_count += 1
                    if progress:
                        progress(done_count, total)

    wall = time.perf_counter() - t0
    n_ok = len(results)
    total_n = sum(r["n_samples"] for r in results.values())
    pi_est = 4.0 * sum(r["inside"] for r in results.values()) / total_n if total_n else None
    err = abs(pi_est - math.pi) if pi_est is not None else None
    status = "COMPLETED" if n_ok == total else ("FAILED" if n_ok == 0 else "PARTIAL")
    db.finish_experiment(exp_id, status, wall, pi_est, err)
    log.info("Experiment %s finished: %s (%d/%d jobs ok, %.3fs)", exp_id, status, n_ok, total, wall)
    retries = sum(j["retries"] for j in db.get_jobs(exp_id))
    return dict(experiment_id=exp_id, status=status, wall_time=wall, completed=n_ok,
                failed=total - n_ok, retries=retries, pi_estimate=pi_est, abs_error=err)


def run_experiment(db, cfg, submission_key=None, progress=None):
    exp_id, cfg, jobs = submit_experiment(db, cfg, submission_key)
    return execute_experiment(db, exp_id, cfg, jobs, progress)
