# AutoHPC
Local HPC-inspired scientific workflow manager: Monte Carlo pi jobs, process-pool parallelism, SQLite history,
bounded retries with failure injection, result validation, benchmarking and CSV reports.

## Setup (Fedora)
    sudo dnf install -y python3.13 git graphviz
    python3.13 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Run
    streamlit run app.py                      # dashboard
    python main.py --mode parallel --workers 4  # CLI
    python main.py --benchmark                  # sequential vs parallel
    pytest -v                                   # tests

Scope: local CPU prototype. Not a Slurm replacement; no multi-node or GPU support.
