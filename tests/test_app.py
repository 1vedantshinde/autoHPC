from pathlib import Path
from streamlit.testing.v1 import AppTest
from storage.database import Database


def test_app_loads_and_runs_experiment(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("AUTOHPC_DB", str(db_path))
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=60).run()
    assert not at.exception
    at.number_input(key="total").set_value(20000)
    at.number_input(key="n_jobs").set_value(4)
    at.button(key="run").click().run()
    assert not at.exception
    exps = Database(db_path).list_experiments()
    assert len(exps) == 1 and exps[0]["status"] == "COMPLETED"
