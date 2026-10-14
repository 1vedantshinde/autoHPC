import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_dir():
    return Path(os.environ.get("AUTOHPC_LOG_DIR", "logs"))


def setup_logging(console=True):
    """Idempotent: rotating file log (logs/autohpc.log) plus optional console output."""
    root = logging.getLogger("autohpc")
    if getattr(root, "_configured", False):
        return root
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    fh = RotatingFileHandler(d / "autohpc.log", maxBytes=1_000_000, backupCount=3)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)
    root.setLevel(logging.INFO)
    root._configured = True
    return root
