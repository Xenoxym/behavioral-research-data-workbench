"""Isolated UI schema fixtures only; never used as research observations or evidence."""

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from study_workbench.research_ui import _archive, _periods, load_artifacts

ROOT = Path(__file__).resolve().parents[1]


def _fixture_artifacts(directory: Path) -> None:
    """Write tiny test-only aggregate tables; none enter real analysis directories."""
    directory.mkdir()
    estimates = []
    for period in ["I", "P", "L"]:
        for variable, groups in {
            "overall": ["all"], "poverty_group": ["lt1", "ge4", "unknown"],
            "education": ["lt_hs", "college"], "indoor_smoking": ["yes", "no"],
        }.items():
            for group in groups:
                estimates.append({"period": period, "group_variable": variable, "group": group,
                                  "n": 100, "events": 20, "prevalence": .2, "se": .02,
                                  "ci_low": .15, "ci_high": .25, "df": 15,
                                  "quality_flag": "OK" if group != "unknown" else "small_cell"})
    pd.DataFrame(estimates).to_csv(directory / "estimates.csv", index=False)
    pd.DataFrame([{"period": period, "contrast": "poverty_lt1_minus_ge4", "estimate": .1,
                   "se": .02, "ci_low": .06, "ci_high": .14, "df": 15, "quality_flag": "OK"}
                  for period in ["I", "P", "L"]]).to_csv(directory / "contrasts.csv", index=False)
    pd.DataFrame([{"period": period, "model": model, "term": "poverty_grouplt1", "coefficient": .5,
                   "se": .2, "odds_ratio": 1.65, "ci_low": 1.1, "ci_high": 2.5,
                   "p_value": .04, "n": 80, "events": 20, "converged": True,
                   "df": 12, "quality_flag": "OK"}
                  for period in ["I", "P", "L"] for model in ["M1_all", "M1_common", "M2"]
                  ]).to_csv(directory / "models.csv", index=False)
    pd.DataFrame([{"period": period, "scenario": scenario, "n": 100, "events": 20,
                   "prevalence": .2, "se": .02, "ci_low": .15, "ci_high": .25,
                   "df": 15, "quality_flag": "OK", "description": "Test-only scenario"}
                  for period in ["I", "P", "L"] for scenario in ["age18", "threshold_010"]
                  ]).to_csv(directory / "sensitivities.csv", index=False)
    pd.DataFrame([{"period": period, "denominator": "full_mec", "group_variable": "poverty_group",
                   "group": "lt1", "n": 100, "missing_n": 10, "missing_rate": .1,
                   "se": .01, "ci_low": .08, "ci_high": .12, "df": 15, "quality_flag": "OK"}
                  for period in ["I", "P", "L"]]).to_csv(directory / "missingness.csv", index=False)
    pd.DataFrame([{"period": "I", "stage": "primary", "n": 100}]).to_csv(directory / "sample_flow.csv", index=False)
    pd.DataFrame([{"variable": "cotinine", "source": "LBXCOT", "unit": "ng/mL"}]).to_csv(directory / "harmonization.csv", index=False)
    for filename, content in {
        "analysis_metadata": {"engine": "test fixture only", "formulas": {"M1": "outcome ~ poverty"}},
        "source_manifest": {"sources": [{"file": "TEST_ONLY", "sha256": "test-fixture"}]},
        "data_quality": {"status": "test fixture only"},
    }.items():
        (directory / f"{filename}.json").write_text(json.dumps(content), encoding="utf-8")


@pytest.fixture
def research_app(monkeypatch, tmp_path):
    directory = tmp_path / "test_aggregate_fixtures"
    _fixture_artifacts(directory)
    report = tmp_path / "test_report.html"
    report.write_text("<!doctype html><html><body><h1>Test fixture report only</h1></body></html>", encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_RESEARCH_DIR", str(directory))
    monkeypatch.setenv("WORKBENCH_RESEARCH_REPORT", str(report))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def _navigate(app, name):
    app.sidebar.radio(key="research_page").set_value(name).run()
    assert not app.exception


def _select(app, label):
    return next(widget for widget in app.selectbox if widget.label == label)


def _multi(app, label):
    return next(widget for widget in app.multiselect if widget.label == label)


def test_default_app_is_research_and_all_sections_render(research_app):
    app = research_app
    assert not app.exception
    assert any("income gradient" in title.value for title in app.title)
    assert not any(button.label == "Load synthetic demo" for button in app.button)
    assert any("real public" in item.value.lower() for item in app.markdown)
    for name in ["Questions & methods", "Weighted results", "Sensitivity & selection", "Sources & provenance", "Research report"]:
        _navigate(app, name)
    assert any("limitations" in title.value for title in app.title)


def test_period_subgroup_filter_and_model_selection_keep_actual_rows(research_app):
    app = research_app
    _navigate(app, "Weighted results")
    _multi(app, "Survey periods").set_value(["L"]).run()
    _multi(app, "Subgroups").set_value(["lt1"]).run()
    selected = app.dataframe[0].value
    assert len(selected) == 1
    assert selected.iloc[0]["period"] == "L"
    assert selected.iloc[0]["group"] == "lt1"
    assert all(column in selected for column in ["ci_low", "ci_high", "n", "events", "df", "quality_flag"])
    _select(app, "Model sample and adjustment").set_value("M1_common").run()
    assert app.dataframe[-1].value["model"].eq("M1_common").all()
    _multi(app, "Survey periods").set_value([]).run()
    assert not app.exception
    assert app.dataframe[0].value.empty


def test_sensitivity_and_missingness_have_explicit_denominator(research_app):
    app = research_app
    _navigate(app, "Sensitivity & selection")
    _multi(app, "Sensitivity periods").set_value(["P"]).run()
    _select(app, "Prespecified scenario").set_value("threshold_010").run()
    assert app.dataframe[0].value["scenario"].eq("threshold_010").all()
    assert app.dataframe[0].value["period"].eq("P").all()
    audit = next(frame.value for frame in app.dataframe if "denominator" in frame.value.columns)
    assert audit["denominator"].eq("full_mec").all()
    assert "missing_n" in audit
    assert any("never set to zero" in item.value for item in app.warning)


def test_missing_outputs_do_not_generate_data_or_access_network(monkeypatch, tmp_path):
    directory = tmp_path / "absent"
    monkeypatch.setenv("WORKBENCH_RESEARCH_DIR", str(directory))
    monkeypatch.setenv("WORKBENCH_RESEARCH_REPORT", str(tmp_path / "absent.html"))

    def no_network(*args, **kwargs):
        raise AssertionError("Research interface must not download at startup")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert any("never substitutes" in item.value for item in app.info)
    assert not directory.exists()
    assert not list(tmp_path.rglob("*.sqlite"))
    _navigate(app, "Questions & methods")
    assert any("before interpreting" in title.value for title in app.title)


def test_malformed_estimates_are_reported_not_silently_displayed(tmp_path):
    directory = tmp_path / "fixtures"
    _fixture_artifacts(directory)
    estimates = pd.read_csv(directory / "estimates.csv").drop(columns="ci_low")
    estimates.to_csv(directory / "estimates.csv", index=False)
    state = load_artifacts(directory)
    assert "estimates" not in state["tables"]
    assert any("ci_low" in error for error in state["errors"])


def test_evidence_archive_excludes_individual_data(tmp_path):
    directory = tmp_path / "fixtures"
    _fixture_artifacts(directory)
    (directory / "analytic.csv").write_text("test-only individual data", encoding="utf-8")
    with ZipFile(BytesIO(_archive(directory))) as archive:
        assert "estimates.csv" in archive.namelist()
        assert "source_manifest.json" in archive.namelist()
        assert "analytic.csv" not in archive.namelist()


def test_secondary_period_contrasts_remain_visible_when_both_periods_selected():
    frame = pd.DataFrame({"period": ["I", "P", "L", "I_to_P", "P_to_L", "I_to_L"]})
    assert len(_periods(frame, ["I", "P", "L"])) == 6
    assert _periods(frame, ["I", "L"])["period"].tolist() == ["I", "L", "I_to_L"]
    assert _periods(frame, ["L"])["period"].tolist() == ["L"]
