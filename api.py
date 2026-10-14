"""REST API.  uvicorn api:app --port 8000   (interactive docs at /docs)"""
import logging
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from engine.executor import execute_experiment, submit_experiment
from engine.scheduler import ConfigError
from integrations.logging_setup import setup_logging
from integrations.notifier import notify, notify_message
from reporting.report_generator import experiment_csv
from storage.database import Database, DuplicateSubmission

setup_logging(console=False)
log = logging.getLogger("autohpc.api")
app = FastAPI(title="AutoHPC API", version="1.0")


class ExperimentRequest(BaseModel):
    total_samples: int = 20_000_000
    n_jobs: int = 8
    mode: str = "sequential"
    workers: int = 1
    max_retries: int = 2
    base_seed: int = 42
    fail_mode: str = "none"
    inject_count: int = 0
    fail_attempts: int = 1
    submission_key: str | None = None  # idempotency token: resubmitting the same key returns 409


def get_db():
    return Database(os.environ.get("AUTOHPC_DB", "data/autohpc.db"))


def _execute(db, exp_id, cfg, jobs):
    try:
        notify(execute_experiment(db, exp_id, cfg, jobs))
    except Exception as e:
        log.exception("Experiment %s crashed", exp_id)
        db.finish_experiment(exp_id, "ERROR", 0.0, None, None)
        notify_message(f"AutoHPC experiment {exp_id} crashed: {type(e).__name__}: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/experiments", status_code=202)
def create_experiment(req: ExperimentRequest, background: BackgroundTasks):
    db = get_db()
    cfg = req.model_dump(exclude={"submission_key"})
    try:
        exp_id, cfg, jobs = submit_experiment(db, cfg, req.submission_key)
    except ConfigError as e:
        raise HTTPException(422, f"Invalid configuration: {e}")
    except DuplicateSubmission as e:
        raise HTTPException(409, str(e))
    background.add_task(_execute, db, exp_id, cfg, jobs)
    return {"experiment_id": exp_id, "status": "RUNNING", "poll": f"/experiments/{exp_id}"}


@app.get("/experiments")
def list_experiments():
    return get_db().list_experiments()


@app.get("/experiments/{exp_id}")
def get_experiment(exp_id: int):
    db = get_db()
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return {"experiment": exp, "jobs": db.get_jobs(exp_id), "attempts": db.get_attempts(exp_id)}


@app.get("/experiments/{exp_id}/report", response_class=PlainTextResponse)
def get_report(exp_id: int):
    db = get_db()
    if not db.get_experiment(exp_id):
        raise HTTPException(404, "Experiment not found")
    return experiment_csv(db, exp_id)
