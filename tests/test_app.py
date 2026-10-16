"""UI workflows and safe, date-aware report output against isolated local databases."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from study_workbench.followup import followup_metrics
from study_workbench.quality import check_bundle
from study_workbench.reporting import build_summary, render_report
from study_workbench.storage import Storage
from study_workbench.synthetic import generate_clean
from study_workbench.ui import _zip_bundle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORKBENCH_DB_PATH", str(tmp_path / "workbench.sqlite"))
    monkeypatch.setenv("WORKBENCH_REPORTS_DIR", str(tmp_path / "reports"))
    return AppTest.from_file(str(ROOT / "legacy_app.py"), default_timeout=45).run()


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def _input(app, label):
    return next(widget for widget in app.text_input if widget.label == label)


def _select(app, label):
    return next(widget for widget in app.selectbox if widget.label == label)


def _navigate(app, page):
    app.sidebar.radio(key="workspace_page").set_value(page).run()
    assert not app.exception


def test_empty_workspace_requires_explicit_demo_and_public_case_is_separate(app, tmp_path):
    assert not app.exception
    assert any("Good research starts" in title.value for title in app.title)
    assert Storage(tmp_path / "workbench.sqlite").load_bundle()["participants"].empty
    _navigate(app, "Public data")
    assert any("not been generated" in message.value for message in app.info)
    assert not (tmp_path / "reports").exists()
    assert Storage(tmp_path / "workbench.sqlite").load_bundle()["participants"].empty
    _navigate(app, "Data dictionary")
    assert app.dataframe


def test_demo_overview_followup_quality_and_report_workflow(app, tmp_path):
    _button(app, "Load synthetic demo").click().run()
    assert not app.exception
    assert len(Storage(tmp_path / "workbench.sqlite").load_bundle()["participants"]) == 240
    assert _button(app, "Load synthetic demo").disabled
    assert any("study progress" in title.value for title in app.title)
    _navigate(app, "Follow-up")
    _select(app, "Visit status").set_value("overdue").run()
    assert not app.exception
    queue = app.dataframe[0].value
    assert not queue.empty
    assert queue["computed_status"].eq("overdue").all()
    _navigate(app, "Quality review")
    assert any("No automated findings" in message.value for message in app.success)
    _button(app, "Run injected-error benchmark").click().run()
    assert not app.exception
    assert app.json
    assert app.session_state["quality_benchmark"]["clean_count"] == 0
    assert app.session_state["quality_benchmark"]["truth_count"] > 0
    _navigate(app, "Reports")
    assert not app.exception
    assert any("reproduce" in title.value for title in app.title)


def test_reasoned_correction_requires_actor_reason_and_persists_restart(app, tmp_path):
    _button(app, "Load synthetic demo").click().run()
    _navigate(app, "Corrections & audit")
    _select(app, "Table to correct").set_value("baseline").run()
    _select(app, "Field to correct").set_value("readiness").run()
    row_id = _select(app, "Record row ID").value
    current = Storage(tmp_path / "workbench.sqlite").load_bundle()["baseline"].iloc[0]["readiness"]
    replacement = "9" if current != 9 else "8"
    _input(app, "New value").input(replacement)
    _button(app, "Save reasoned correction").click().run()
    assert any("required" in message.value for message in app.error)
    assert Storage(tmp_path / "workbench.sqlite").audit_log().empty
    _input(app, "Reviewer name").input("Portfolio reviewer")
    _input(app, "Correction reason").input("Verified against synthetic source form")
    _button(app, "Save reasoned correction").click().run()
    assert not app.exception
    assert any("Correction saved" in message.value for message in app.success)
    restarted = Storage(tmp_path / "workbench.sqlite")
    audit = restarted.audit_log()
    assert len(audit) == 1
    assert audit.iloc[0]["actor"] == "Portfolio reviewer"
    assert audit.iloc[0]["row_id"] == row_id
    raw = restarted.load_bundle(raw=True)["baseline"]
    working = restarted.load_bundle()["baseline"]
    assert raw.loc[raw["row_id"].eq(row_id), "readiness"].iloc[0] == current
    assert working.loc[working["row_id"].eq(row_id), "readiness"].iloc[0] == int(replacement)
    fresh_app = AppTest.from_file(str(ROOT / "legacy_app.py"), default_timeout=45).run()
    _navigate(fresh_app, "Corrections & audit")
    assert len(fresh_app.dataframe[-1].value) == 1


def test_report_has_actual_denominator_and_escapes_findings():
    bundle = generate_clean(seed=42, n=40)
    summary = build_summary(bundle)
    assert summary["followup"] == followup_metrics(bundle, "2026-10-16")
    malicious = '<script>alert("unsafe")</script>'
    issues = pd.DataFrame([{
        "issue_id": "x", "rule_id": malicious, "severity": "review", "table": malicious,
        "row_id": "x", "participant_id": "x", "field": "x", "message": malicious,
    }])
    html = render_report(bundle, issues)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "SYNTHETIC DATA" in html
    assert "cross-sectional case" in html
    expected = summary["followup"]
    assert f"{expected['completed_due_visits']} / {expected['due_visits']}" in html
    assert '<html lang="en">' in html


def test_report_missingness_excludes_unanswered_ema_and_future_measurements():
    bundle = generate_clean(seed=42, n=40)
    bundle["ema"] = pd.DataFrame([
        {"row_id": "E1", "participant_id": "SYN-1", "prompted_at": "2026-10-15T09:00:00+00:00", "responded_at": "2026-10-15T09:01:00+00:00", "uploaded_at": "2026-10-15T09:01:00+00:00", "response_state": "answered", "urge": None, "stress": 3},
        {"row_id": "E2", "participant_id": "SYN-1", "prompted_at": "2026-10-15T10:00:00+00:00", "responded_at": None, "uploaded_at": None, "response_state": "declined", "urge": None, "stress": None},
        {"row_id": "E3", "participant_id": "SYN-1", "prompted_at": "2026-10-17T10:00:00+00:00", "responded_at": "2026-10-17T10:01:00+00:00", "uploaded_at": "2026-10-17T10:01:00+00:00", "response_state": "answered", "urge": None, "stress": None},
    ])
    summary = build_summary(bundle)
    assert summary["ema_prompts"] == 2
    assert summary["ema_answered"] == 1
    urge = next(item for item in summary["missingness"] if item["table"] == "ema" and item["field"] == "urge")
    assert urge["expected"] == 1
    assert urge["missing"] == 1


def test_mixed_fractional_iso_timestamps_do_not_change_ema_denominator():
    bundle = generate_clean(seed=42, n=40)
    before = build_summary(bundle)
    index = bundle["ema"].index[bundle["ema"]["response_state"].eq("answered")][0]
    value = pd.Timestamp(bundle["ema"].at[index, "responded_at"])
    bundle["ema"].at[index, "responded_at"] = value.isoformat(timespec="microseconds")
    after = build_summary(bundle)
    assert after["ema_answered"] == before["ema_answered"]
    assert after["missingness"] == before["missingness"]


def test_report_handles_identity_conflicts_without_inventing_denominators():
    bundle = generate_clean(seed=42, n=40)
    bundle["participants"].loc[1, "participant_id"] = bundle["participants"].loc[0, "participant_id"]
    summary = build_summary(bundle)
    assert summary["followup_error"]
    assert summary["followup"]["due_visits"] is None
    assert "Follow-up metrics unavailable" in render_report(bundle, check_bundle(bundle))


def test_table_zip_roundtrip_is_complete_and_not_a_database():
    bundle = generate_clean(seed=42, n=40)
    with ZipFile(BytesIO(_zip_bundle(bundle))) as archive:
        assert set(archive.namelist()) == {f"{table}.csv" for table in bundle}
        for table, frame in bundle.items():
            exported = pd.read_csv(BytesIO(archive.read(f"{table}.csv")))
            assert list(exported.columns) == list(frame.columns)
            assert len(exported) == len(frame)
