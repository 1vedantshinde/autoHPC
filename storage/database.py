import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from engine.state_manager import QUEUED, check_transition

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_key TEXT UNIQUE, created_at TEXT,
  config_json TEXT, mode TEXT, workers INTEGER, status TEXT,
  wall_time REAL, pi_estimate REAL, abs_error REAL);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id INTEGER, job_index INTEGER,
  n_samples INTEGER, seed INTEGER, state TEXT, retries INTEGER DEFAULT 0,
  inside INTEGER, estimate REAL, duration REAL, error TEXT);
CREATE TABLE IF NOT EXISTS attempts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, attempt_no INTEGER,
  ts TEXT, duration REAL, outcome TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, ts TEXT, from_state TEXT, to_state TEXT);
"""
JOB_FIELDS = {"retries", "inside", "estimate", "duration", "error"}


class DuplicateSubmission(Exception):
    pass


def _now():
    return datetime.now().isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")  # safer with several processes sharing the file
        conn.executescript(SCHEMA)
        conn.close()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _q(self, sql, params=()):
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ---- writes
    def create_experiment(self, cfg, key=None):
        key = key or uuid.uuid4().hex
        try:
            with self._conn() as c:
                cur = c.execute(
                    "INSERT INTO experiments(submission_key,created_at,config_json,mode,workers,status) VALUES(?,?,?,?,?,?)",
                    (key, _now(), json.dumps(cfg), cfg["mode"], cfg["workers"], "RUNNING"))
                return cur.lastrowid
        except sqlite3.IntegrityError:
            raise DuplicateSubmission("This submission was already executed")

    def add_job(self, exp_id, index, n_samples, seed):
        with self._conn() as c:
            return c.execute(
                "INSERT INTO jobs(experiment_id,job_index,n_samples,seed,state) VALUES(?,?,?,?,?)",
                (exp_id, index, n_samples, seed, QUEUED)).lastrowid

    def set_state(self, job_id, new_state, **fields):
        bad = set(fields) - JOB_FIELDS
        if bad:
            raise ValueError(f"Unknown job fields {bad}")
        with self._conn() as c:
            old = c.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()["state"]
            check_transition(old, new_state)
            cols = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE jobs SET state=?{', ' + cols if cols else ''} WHERE id=?",
                      (new_state, *fields.values(), job_id))
            c.execute("INSERT INTO events(job_id,ts,from_state,to_state) VALUES(?,?,?,?)",
                      (job_id, _now(), old, new_state))

    def add_attempt(self, job_id, attempt_no, duration, outcome, error=None):
        with self._conn() as c:
            c.execute("INSERT INTO attempts(job_id,attempt_no,ts,duration,outcome,error) VALUES(?,?,?,?,?,?)",
                      (job_id, attempt_no, _now(), duration, outcome, error))

    def finish_experiment(self, exp_id, status, wall_time, pi_estimate, abs_error):
        with self._conn() as c:
            c.execute("UPDATE experiments SET status=?,wall_time=?,pi_estimate=?,abs_error=? WHERE id=?",
                      (status, wall_time, pi_estimate, abs_error, exp_id))

    # ---- reads
    def list_experiments(self):
        return self._q("SELECT id,created_at,mode,workers,status,wall_time,pi_estimate,abs_error "
                       "FROM experiments ORDER BY id DESC")

    def get_experiment(self, exp_id):
        rows = self._q("SELECT * FROM experiments WHERE id=?", (exp_id,))
        return rows[0] if rows else None

    def get_jobs(self, exp_id):
        return self._q("SELECT * FROM jobs WHERE experiment_id=? ORDER BY job_index", (exp_id,))

    def get_attempts(self, exp_id):
        return self._q("SELECT a.* FROM attempts a JOIN jobs j ON a.job_id=j.id "
                       "WHERE j.experiment_id=? ORDER BY a.id", (exp_id,))

    def get_events(self, exp_id):
        return self._q("SELECT e.* FROM events e JOIN jobs j ON e.job_id=j.id "
                       "WHERE j.experiment_id=? ORDER BY e.id", (exp_id,))
