import csv
import io
import os
import platform
import sys

import numpy as np

from engine.executor import run_experiment


def system_info():
    return {"os": platform.platform(), "python": sys.version.split()[0],
            "logical_cpus": os.cpu_count(), "numpy": np.__version__}


def run_benchmark(db, cfg, worker_counts, progress=None):
    base = {**cfg, "fail_mode": "none", "inject_count": 0}
    rows = []
    seq = run_experiment(db, {**base, "mode": "sequential", "workers": 1})
    rows.append(dict(experiment_id=seq["experiment_id"], mode="sequential", workers=1,
                     wall_time=seq["wall_time"], speedup=1.0, efficiency=1.0, abs_error=seq["abs_error"]))
    for p in worker_counts:
        if progress:
            progress(f"parallel, {p} workers")
        r = run_experiment(db, {**base, "mode": "parallel", "workers": p})
        s = seq["wall_time"] / r["wall_time"]
        rows.append(dict(experiment_id=r["experiment_id"], mode="parallel", workers=p,
                         wall_time=r["wall_time"], speedup=s, efficiency=s / p, abs_error=r["abs_error"]))
    return rows


def _section(w, title, rows):
    w.writerow([f"# {title}"])
    if rows:
        w.writerow(list(rows[0].keys()))
        for r in rows:
            w.writerow(list(r.values()))
    w.writerow([])


def experiment_csv(db, exp_id):
    buf = io.StringIO()
    w = csv.writer(buf)
    _section(w, "Experiment", [db.get_experiment(exp_id)])
    _section(w, "System", [system_info()])
    _section(w, "Jobs", db.get_jobs(exp_id))
    _section(w, "Attempts", db.get_attempts(exp_id))
    return buf.getvalue()


def benchmark_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    _section(w, "System", [system_info()])
    _section(w, "Benchmark", rows)
    return buf.getvalue()
