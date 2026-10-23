"""Excel Master Ledger for AutoHPC.

Records experiment execution history and rejected job specifications
into a stylized multi-sheet Excel (.xlsx) workbook using openpyxl.
Includes concurrency protection and retry backoff against file locks.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

log = logging.getLogger("autohpc.excel")

DEFAULT_EXCEL_PATH = "data/autohpc_master_ledger.xlsx"

# Header styling
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
REJECTED_HEADER_FILL = PatternFill(start_color="800000", end_color="800000", fill_type="solid")

THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

# Status pill fills
STATUS_STYLES = {
    "COMPLETED": {"fill": PatternFill(start_color="D9EAD3", fill_type="solid"), "font": Font(name="Calibri", color="274E13", bold=True)},
    "FAILED": {"fill": PatternFill(start_color="FCE5CD", fill_type="solid"), "font": Font(name="Calibri", color="783F04", bold=True)},
    "ERROR": {"fill": PatternFill(start_color="F4CCCC", fill_type="solid"), "font": Font(name="Calibri", color="990000", bold=True)},
    "REJECTED": {"fill": PatternFill(start_color="F4CCCC", fill_type="solid"), "font": Font(name="Calibri", color="990000", bold=True)},
}

RUNS_COLUMNS = [
    ("Timestamp", 20),
    ("Experiment ID", 15),
    ("Submission Key", 22),
    ("Mode", 12),
    ("Workers", 10),
    ("Total Samples", 16),
    ("Jobs (Chunks)", 14),
    ("Status", 14),
    ("Wall Time (s)", 14),
    ("Retries", 10),
    ("Pi Estimate", 14),
    ("Absolute Error", 16),
    ("Outcome Summary", 40),
]

REJECTED_COLUMNS = [
    ("Timestamp", 20),
    ("File Name", 25),
    ("Rejection Reason", 40),
    ("Raw / Error Detail", 40),
]


def get_excel_path():
    """Retrieve configured excel ledger path."""
    return Path(os.environ.get("AUTOHPC_EXCEL_PATH", DEFAULT_EXCEL_PATH))


def _apply_header_styles(ws, columns, fill):
    for col_idx, (col_name, width) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[1].height = 26


def init_workbook(filepath: Path) -> openpyxl.Workbook:
    """Initialize workbook with required sheets if it doesn't exist."""
    wb = openpyxl.Workbook()
    # Sheet 1: Experiment Runs
    ws_runs = wb.active
    ws_runs.title = "Experiment_Runs"
    ws_runs.views.sheetView[0].showGridLines = True
    _apply_header_styles(ws_runs, RUNS_COLUMNS, HEADER_FILL)

    # Sheet 2: Rejected Jobs
    ws_rejected = wb.create_sheet(title="Rejected_Jobs")
    ws_rejected.views.sheetView[0].showGridLines = True
    _apply_header_styles(ws_rejected, REJECTED_COLUMNS, REJECTED_HEADER_FILL)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    wb.save(filepath)
    log.info("Initialized master Excel ledger at %s", filepath)
    return wb


def _save_with_retry(wb: openpyxl.Workbook, filepath: Path, retries: int = 4, delay: float = 0.5):
    """Save workbook with retry mechanism against temporary file locks."""
    for attempt in range(1, retries + 1):
        try:
            wb.save(filepath)
            return True
        except PermissionError as e:
            log.warning("Permission denied saving Excel file (attempt %d/%d). Is it open in Excel? %s", attempt, retries, e)
            if attempt == retries:
                # Try fallback save so data is not lost
                fallback = filepath.with_name(f"{filepath.stem}_fallback_{int(time.time())}.xlsx")
                wb.save(fallback)
                log.error("Saved to fallback Excel ledger %s due to file lock on %s", fallback, filepath)
                return False
            time.sleep(delay * attempt)
        except Exception as e:
            log.exception("Unexpected error saving Excel file: %s", e)
            raise


def record_experiment_run(summary: dict, filepath: Path | None = None) -> bool:
    """Append a completed or failed experiment run into the Excel ledger. Never raises."""
    try:
        path = filepath or get_excel_path()
        if not path.exists():
            wb = init_workbook(path)
        else:
            try:
                wb = openpyxl.load_workbook(path)
            except Exception:
                wb = init_workbook(path)

        if "Experiment_Runs" not in wb.sheetnames:
            ws = wb.create_sheet(title="Experiment_Runs", index=0)
            _apply_header_styles(ws, RUNS_COLUMNS, HEADER_FILL)
        else:
            ws = wb["Experiment_Runs"]

        cfg = summary.get("config", {})
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exp_id = summary.get("experiment_id", "N/A")
        sub_key = str(summary.get("submission_key", "N/A"))
        mode = cfg.get("mode", summary.get("mode", "N/A"))
        workers = cfg.get("workers", summary.get("workers", 1))
        samples = cfg.get("total_samples", summary.get("total_samples", "N/A"))
        n_jobs = cfg.get("n_jobs", summary.get("n_jobs", "N/A"))
        status = summary.get("status", "UNKNOWN")
        wall_time = summary.get("wall_time")
        retries = summary.get("retries", 0)
        pi_est = summary.get("pi_estimate")
        abs_err = summary.get("abs_error")

        wall_str = round(wall_time, 4) if isinstance(wall_time, (int, float)) else "N/A"
        pi_str = round(pi_est, 6) if isinstance(pi_est, (int, float)) else "N/A"
        err_str = f"{abs_err:.2e}" if isinstance(abs_err, (int, float)) else "N/A"
        outcome_desc = (
            f"ok={summary.get('completed', 0)}, failed={summary.get('failed', 0)}, "
            f"retries={retries}, wall={wall_str}s"
        )

        row_values = [
            ts, exp_id, sub_key, mode, workers, samples, n_jobs,
            status, wall_str, retries, pi_str, err_str, outcome_desc
        ]

        next_row = ws.max_row + 1
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=next_row, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center", horizontal="center" if col_idx not in (1, 13) else "left")

            # Style status cell
            if col_idx == 8 and status in STATUS_STYLES:
                cell.fill = STATUS_STYLES[status]["fill"]
                cell.font = STATUS_STYLES[status]["font"]

        ws.row_dimensions[next_row].height = 20
        _save_with_retry(wb, path)
        log.info("Recorded experiment %s to Excel ledger (%s)", exp_id, path)
        return True
    except Exception as e:
        log.exception("Failed to record experiment run to Excel ledger: %s", e)
        return False


def record_rejected_job(filename: str, reason: str, details: str = "", filepath: Path | None = None) -> bool:
    """Append a rejected job specification into the Rejected_Jobs sheet."""
    try:
        path = filepath or get_excel_path()
        if not path.exists():
            wb = init_workbook(path)
        else:
            try:
                wb = openpyxl.load_workbook(path)
            except Exception:
                wb = init_workbook(path)

        if "Rejected_Jobs" not in wb.sheetnames:
            ws = wb.create_sheet(title="Rejected_Jobs")
            _apply_header_styles(ws, REJECTED_COLUMNS, REJECTED_HEADER_FILL)
        else:
            ws = wb["Rejected_Jobs"]

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_values = [ts, filename, reason, details]

        next_row = ws.max_row + 1
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=next_row, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center", horizontal="left")
            if col_idx == 3:
                cell.fill = STATUS_STYLES["REJECTED"]["fill"]
                cell.font = STATUS_STYLES["REJECTED"]["font"]

        ws.row_dimensions[next_row].height = 20
        _save_with_retry(wb, path)
        log.info("Recorded rejected job %s to Excel ledger (%s)", filename, path)
        return True
    except Exception as e:
        log.exception("Failed to record rejection to Excel ledger: %s", e)
        return False
