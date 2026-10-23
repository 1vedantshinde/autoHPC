import openpyxl
from pathlib import Path
from integrations.excel_logger import init_workbook, record_experiment_run, record_rejected_job


def test_init_workbook(tmp_path):
    excel_path = tmp_path / "test_ledger.xlsx"
    wb = init_workbook(excel_path)
    assert excel_path.exists()
    assert "Experiment_Runs" in wb.sheetnames
    assert "Rejected_Jobs" in wb.sheetnames


def test_record_experiment_run(tmp_path):
    excel_path = tmp_path / "test_ledger.xlsx"
    mock_summary = {
        "experiment_id": 101,
        "submission_key": "sub-key-abc",
        "status": "COMPLETED",
        "completed": 4,
        "failed": 0,
        "retries": 1,
        "wall_time": 1.254,
        "pi_estimate": 3.14159,
        "abs_error": 0.0001,
        "config": {
            "mode": "parallel",
            "workers": 4,
            "total_samples": 1000000,
            "n_jobs": 4,
        },
    }

    ok = record_experiment_run(mock_summary, filepath=excel_path)
    assert ok is True
    assert excel_path.exists()

    wb = openpyxl.load_workbook(excel_path)
    ws = wb["Experiment_Runs"]
    assert ws.max_row == 2  # header + 1 record
    assert ws.cell(row=2, column=2).value == 101
    assert ws.cell(row=2, column=4).value == "parallel"
    assert ws.cell(row=2, column=8).value == "COMPLETED"


def test_record_rejected_job(tmp_path):
    excel_path = tmp_path / "test_ledger.xlsx"
    ok = record_rejected_job("bad_spec.json", "Invalid JSON format", details="Missing closing brace", filepath=excel_path)
    assert ok is True

    wb = openpyxl.load_workbook(excel_path)
    ws = wb["Rejected_Jobs"]
    assert ws.max_row == 2
    assert ws.cell(row=2, column=2).value == "bad_spec.json"
    assert ws.cell(row=2, column=3).value == "Invalid JSON format"
