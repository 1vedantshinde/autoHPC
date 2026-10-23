import os
import uuid

import pandas as pd
import streamlit as st

from engine.executor import run_experiment
from engine.scheduler import ConfigError
from integrations.excel_logger import get_excel_path, record_experiment_run
from integrations.logging_setup import log_dir, setup_logging
from integrations.notifier import notify
from pathlib import Path
from reporting.report_generator import benchmark_csv, experiment_csv, run_benchmark, system_info
from storage.database import Database, DuplicateSubmission

st.set_page_config(page_title="AutoHPC", layout="wide")
st.title("AutoHPC - Automated Parallel Experiment Manager")
db = Database(os.environ.get("AUTOHPC_DB", "data/autohpc.db"))
setup_logging(console=False)
cpus = os.cpu_count() or 2
st.session_state.setdefault("key", uuid.uuid4().hex)
st.session_state.setdefault("last_id", None)

with st.sidebar:
    st.header("Experiment configuration")
    total = st.number_input("Total samples", min_value=1000, value=20_000_000, step=1_000_000, key="total")
    n_jobs = st.number_input("Number of jobs", min_value=1, value=8, key="n_jobs")
    mode = st.selectbox("Execution mode", ["sequential", "parallel"], key="mode")
    workers = st.number_input("Workers (parallel)", min_value=1, max_value=cpus, value=min(4, cpus), key="workers")
    retries = st.number_input("Max retries", min_value=0, max_value=10, value=2, key="retries")
    seed = st.number_input("Base seed", min_value=0, value=42, key="seed")
    st.subheader("Failure injection")
    fail_mode = st.selectbox("Failure mode", ["none", "transient", "persistent"], key="fail_mode")
    inject = st.number_input("Jobs to inject", min_value=0, value=1, key="inject")
    fail_attempts = st.number_input("Transient: failing attempts", min_value=1, value=1, key="fail_attempts")
    st.caption(f"Logical CPUs: {cpus}")


def current_cfg():
    return dict(total_samples=int(total), n_jobs=int(n_jobs), mode=mode,
                workers=int(workers) if mode == "parallel" else 1, max_retries=int(retries),
                base_seed=int(seed), fail_mode=fail_mode,
                inject_count=int(inject) if fail_mode != "none" else 0, fail_attempts=int(fail_attempts))


def show_experiment(exp_id, prefix):
    exp = db.get_experiment(exp_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", exp["status"])
    c2.metric("Wall time (s)", f"{exp['wall_time']:.3f}" if exp["wall_time"] is not None else "-")
    c3.metric("pi estimate", f"{exp['pi_estimate']:.6f}" if exp["pi_estimate"] else "-")
    c4.metric("Absolute error", f"{exp['abs_error']:.2e}" if exp["abs_error"] is not None else "-")
    jobs = pd.DataFrame(db.get_jobs(exp_id))
    st.write("**Job states:**", jobs["state"].value_counts().to_dict())
    st.subheader("Jobs")
    st.dataframe(jobs, use_container_width=True)
    st.subheader("Attempts (retry history)")
    st.dataframe(pd.DataFrame(db.get_attempts(exp_id)), use_container_width=True)
    st.subheader("State transitions")
    st.dataframe(pd.DataFrame(db.get_events(exp_id)), use_container_width=True)
    st.download_button("Download experiment report (CSV)", experiment_csv(db, exp_id),
                       file_name=f"experiment_{exp_id}.csv", mime="text/csv", key=f"dl_{prefix}_{exp_id}")


tab_run, tab_bench, tab_hist, tab_mon = st.tabs(["Run", "Benchmark", "History", "Live monitor"])

with tab_run:
    col_run, col_fail = st.columns([1, 1])
    with col_run:
        run_clicked = st.button("Run experiment", type="primary", key="run")
    with col_fail:
        fail_clicked = st.button("Run failing experiment (force fail)", type="secondary", key="run_fail",
                                 help="Forces all jobs to persistently fail so you can verify email and ledger handling for failed experiments.")

    if run_clicked or fail_clicked:
        bar = st.progress(0.0, text="Running...")
        try:
            cfg = current_cfg()
            if fail_clicked:
                cfg["fail_mode"] = "persistent"
                cfg["inject_count"] = cfg["n_jobs"]
            out = run_experiment(db, cfg, st.session_state.key,
                                 progress=lambda d, t: bar.progress(d / t, text=f"{d}/{t} jobs finished"))
            st.session_state.last_id = out["experiment_id"]
            st.session_state.key = uuid.uuid4().hex  # new submission token
            record_experiment_run(out)
            notify(out)
            if out["status"] == "FAILED":
                st.error(f"Experiment {out['experiment_id']} finished: {out['status']} (Failure email sent)")
            else:
                st.success(f"Experiment {out['experiment_id']} finished: {out['status']}")
        except ConfigError as e:
            st.error(f"Invalid configuration: {e}")
        except DuplicateSubmission as e:
            st.warning(str(e))
        except Exception as e:  # noqa
            st.error(f"Unexpected error: {type(e).__name__}: {e}")
    if st.session_state.last_id:
        show_experiment(st.session_state.last_id, "run")

with tab_bench:
    st.write("Runs the same workload sequentially and with each selected worker count.")
    options = [p for p in (2, 4, 8, 12, 16) if p <= cpus] or [1]
    chosen = st.multiselect("Parallel worker counts", options, default=options[:2], key="bench_workers")
    if st.button("Run benchmark", key="bench_btn"):
        with st.spinner("Benchmarking..."):
            try:
                rows = run_benchmark(db, current_cfg(), chosen)
                st.session_state.bench_rows = rows
                os.makedirs("data", exist_ok=True)
                with open("data/benchmark_results.csv", "w") as f:
                    f.write(benchmark_csv(rows))
            except ConfigError as e:
                st.error(f"Invalid configuration: {e}")
    if st.session_state.get("bench_rows"):
        df = pd.DataFrame(st.session_state.bench_rows)
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df.set_index("workers")["wall_time"])
        st.json(system_info())
        st.download_button("Download benchmark CSV", benchmark_csv(st.session_state.bench_rows),
                           file_name="benchmark_results.csv", mime="text/csv", key="dl_bench")

with tab_hist:
    hist = db.list_experiments()
    if hist:
        st.dataframe(pd.DataFrame(hist), use_container_width=True)
        pick = st.selectbox("Inspect experiment", [h["id"] for h in hist], key="pick")
        show_experiment(pick, "hist")
    else:
        st.info("No experiments recorded yet.")

    excel_file = get_excel_path()
    if excel_file.exists():
        st.download_button(
            "Download Excel Master Ledger (.xlsx)",
            data=excel_file.read_bytes(),
            file_name="autohpc_master_ledger.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_master_excel",
        )

with tab_mon:
    st.caption("Auto-refreshes every 5 s. Shows activity from the dashboard, the REST API and the inbox watcher.")

    @st.fragment(run_every="5s")
    def monitor():
        exps = db.list_experiments()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Experiments", len(exps))
        for col, name in zip((c2, c3, c4), ("inbox", "processed", "rejected")):
            d = Path("data") / name
            col.metric(f"Watcher: {name}", len(list(d.glob("*.json"))) if d.exists() else 0)
        st.dataframe(pd.DataFrame(exps[:10]), use_container_width=True)
        for fname in ("autohpc.log", "notifications.log"):
            p = log_dir() / fname
            st.subheader(fname)
            st.code("".join(p.read_text().splitlines(True)[-15:]) if p.exists() else "(empty)", language="text")

    monitor()
