"""CLI entry point: python main.py --samples 20000000 --jobs 8 --mode parallel --workers 4"""
import argparse
import os

from engine.executor import run_experiment
from integrations.excel_logger import record_experiment_run
from reporting.report_generator import run_benchmark, system_info
from integrations.logging_setup import setup_logging
from integrations.notifier import notify
from storage.database import Database


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=int, default=20_000_000)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--mode", default="sequential", choices=["sequential", "parallel"])
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fail-mode", default="none", choices=["none", "transient", "persistent"])
    p.add_argument("--inject", type=int, default=0, help="number of jobs to inject failures into")
    p.add_argument("--fail-attempts", type=int, default=1)
    p.add_argument("--benchmark", action="store_true")
    p.add_argument("--db", default=os.environ.get("AUTOHPC_DB", "data/autohpc.db"))
    a = p.parse_args()
    setup_logging()
    db = Database(a.db)
    cfg = dict(total_samples=a.samples, n_jobs=a.jobs, mode=a.mode, workers=a.workers, max_retries=a.retries,
               base_seed=a.seed, fail_mode=a.fail_mode, inject_count=a.inject, fail_attempts=a.fail_attempts)
    print("System:", system_info())
    if a.benchmark:
        for r in run_benchmark(db, cfg, [p for p in (2, 4) if p <= (os.cpu_count() or 1)]):
            print(f"{r['mode']:<10} p={r['workers']} T={r['wall_time']:.3f}s "
                  f"speedup={r['speedup']:.2f} eff={r['efficiency']:.2f} err={r['abs_error']:.2e}")
    else:
        out = run_experiment(db, cfg)
        record_experiment_run(out)
        print(out)
        print('Notifications:', notify(out))


if __name__ == "__main__":
    main()
