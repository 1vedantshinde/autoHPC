"""Unattended 'bot': picks up JSON job specs from data/inbox, runs them, archives the outcome and notifies.
  python watcher.py --interval 3      (runs forever)      python watcher.py --once"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from engine.executor import run_experiment
from engine.scheduler import ConfigError
from integrations.logging_setup import setup_logging
from integrations.notifier import notify, notify_message
from storage.database import Database, DuplicateSubmission

log = logging.getLogger("autohpc.watcher")


def _unique(dest):
    return dest if not dest.exists() else dest.with_name(f"{dest.stem}_{datetime.now():%H%M%S%f}{dest.suffix}")


def _reject(f, rejected, reason):
    dest = _unique(Path(rejected) / f.name)
    shutil.move(str(f), dest)
    Path(str(dest) + ".error.txt").write_text(reason + "\n")
    log.warning("Rejected %s: %s", f.name, reason)
    notify_message(f"AutoHPC rejected job spec {f.name}: {reason}", "AutoHPC job spec rejected")
    return dict(file=f.name, outcome="rejected", reason=reason)


def process_inbox(db, inbox="data/inbox", processed="data/processed", rejected="data/rejected"):
    for d in (inbox, processed, rejected):
        Path(d).mkdir(parents=True, exist_ok=True)
    outcomes = []
    for f in sorted(Path(inbox).glob("*.json")):
        raw = f.read_bytes()
        key = hashlib.sha256(raw).hexdigest()  # identical file content == duplicate submission
        log.info("Picked up %s", f.name)
        try:
            spec = json.loads(raw)
            if not isinstance(spec, dict):
                raise ConfigError("job spec must be a JSON object")
            spec = {k: v for k, v in spec.items() if k != "name"}
            summary = run_experiment(db, spec, submission_key=key)
        except (json.JSONDecodeError, ConfigError) as e:  # "business exception": bad input, never retried
            outcomes.append(_reject(f, rejected, f"Invalid job spec: {e}"))
        except DuplicateSubmission as e:
            outcomes.append(_reject(f, rejected, f"Duplicate submission: {e}"))
        except Exception as e:  # "system exception": unexpected, logged with traceback
            log.exception("System error processing %s", f.name)
            outcomes.append(_reject(f, rejected, f"System error: {type(e).__name__}: {e}"))
        else:
            dest = _unique(Path(processed) / f.name)
            shutil.move(str(f), dest)
            Path(str(dest) + ".result.json").write_text(json.dumps(summary, indent=2))
            notify(summary)
            outcomes.append(dict(file=f.name, outcome="processed", **summary))
    return outcomes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--db", default=os.environ.get("AUTOHPC_DB", "data/autohpc.db"))
    a = p.parse_args()
    setup_logging()
    db = Database(a.db)
    log.info("Watching data/inbox (interval %.1fs)", a.interval)
    while True:
        process_inbox(db)
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
