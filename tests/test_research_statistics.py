"""Independent statistics checks; artificial test frames never enter research reports."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _rscript():
    configured = os.environ.get("RESEARCH_RSCRIPT")
    local = ROOT / ".tools" / "R" / "bin" / "Rscript.exe"
    result = configured or (str(local) if local.exists() else shutil.which("Rscript"))
    if not result:
        pytest.skip("R survey reference requires project-local R or RESEARCH_RSCRIPT/PATH")
    return result


def _run_r(script, *arguments, check=True):
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    local_library = ROOT / ".tools" / "R-library"
    if local_library.exists():
        environment["R_LIBS_USER"] = str(local_library)
    return subprocess.run(
        [_rscript(), "--vanilla", str(script), *(str(arg) for arg in arguments)],
        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, check=check,
    )


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    directory = tmp_path_factory.mktemp("survey_reference")
    result = _run_r(ROOT / "research" / "reference_validation.R", directory)
    assert "validation passed" in result.stdout
    return pd.read_csv(directory / "reference_input.csv"), json.loads(
        (directory / "reference_results.json").read_text()
    )


def _independent_taylor(frame, columns, domain=None):
    """With-replacement stratified PSU ratio linearization, independent of R code.

    Domain exclusions zero their influence; all original PSUs remain for centering.
    The shipped application uses R survey, not this test implementation.
    """
    member = np.ones(len(frame), dtype=bool) if domain is None else np.asarray(domain)
    weight = frame.weight.to_numpy(dtype=float)
    y = frame[columns].to_numpy(dtype=float)
    total_weight = weight[member].sum()
    point = (y[member] * weight[member, None]).sum(axis=0) / total_weight
    residual = (weight * member)[:, None] * (y - point) / total_weight
    units = frame[["stratum", "psu"]].copy()
    for index in range(len(columns)):
        units[f"u{index}"] = residual[:, index]
    psu_totals = units.groupby(["stratum", "psu"])[[f"u{i}" for i in range(len(columns))]].sum()
    covariance = np.zeros((len(columns), len(columns)))
    for _, group in psu_totals.groupby(level="stratum"):
        values = group.to_numpy()
        centered = values - values.mean(axis=0)
        covariance += len(values) / (len(values) - 1) * (centered.T @ centered)
    return point, covariance


def test_builtin_author_reference_and_installed_versions(reference):
    _, expected = reference
    assert expected["builtin_stratified"]["mean"] == pytest.approx(662.2873631593208)
    assert expected["builtin_stratified"]["se"] == pytest.approx(9.40894080278458)
    assert expected["survey_version"]
    assert expected["full"]["df"] == 14


def test_independent_full_and_domain_taylor_covariances_match_r(reference):
    frame, expected = reference
    for name, mask in [("full", None), ("domain_H", frame.group.eq("H"))]:
        point, covariance = _independent_taylor(frame, ["y", "exposed"], mask)
        np.testing.assert_allclose(point, expected[name]["mean"], rtol=1e-11)
        np.testing.assert_allclose(covariance, expected[name]["covariance"], rtol=1e-10, atol=1e-12)


def test_joint_domain_covariance_and_contrast_not_independence_assumption(reference):
    frame, expected = reference
    influences = []
    for group in expected["group_order"]:
        member = frame.group.eq(group).to_numpy()
        weights = frame.weight.to_numpy()
        values = frame.exposed.to_numpy()
        point = np.sum(weights[member] * values[member]) / weights[member].sum()
        influences.append(weights * member * (values - point) / weights[member].sum())
    scores = pd.DataFrame(np.asarray(influences).T)
    totals = scores.groupby(frame.psu).sum().to_numpy()
    centered = totals - totals.mean(axis=0)
    covariance = len(totals) / (len(totals) - 1) * centered.T @ centered
    np.testing.assert_allclose(covariance, expected["group_covariance"], rtol=1e-10, atol=1e-12)
    contrast = np.array([1, -1, 0])
    se = float(np.sqrt(contrast @ covariance @ contrast))
    assert se == pytest.approx(expected["contrast_E_minus_H"]["se"])
    assert not np.isclose(se, np.sqrt(covariance[0, 0] + covariance[1, 1]))
    ci = expected["proportion_logit"]["interval"]
    assert 0 < ci[0] < expected["proportion_logit"]["estimate"] < ci[1] < 1


@pytest.fixture(scope="module")
def artificial_analysis(reference, tmp_path_factory):
    # Test-only shape contract: school data deterministically mapped to artificial
    # nicotine columns. Nothing here is actual NHANES or a portfolio finding.
    schools, _ = reference
    count = len(schools)
    rows = []
    for period in ("I", "P", "L"):
        for index, school in schools.iterrows():
            missing_lab = index == 0
            cotinine = None if missing_lab else (.2 if school.exposed else .02)
            rows.append({
                "period": period, "period_label": f"ARTIFICIAL UNIT TEST {period}",
                "SEQN": index + 1, "stratum": 1, "psu": int(school.psu),
                "weight": school.weight, "mec_weight": school.weight, "age": 25 + index % 50,
                "sex": "male" if index % 2 else "female",
                "race_group": ["nh_white", "nh_black", "nh_asian", "hispanic", "other"][index % 5],
                "income_ratio": {"E": 4.5, "H": .5, "M": 1.5}[school.group],
                "poverty_group": {"E": "ge4", "H": "lt1", "M": "1to2"}[school.group],
                "education": ["lt_hs", "hs", "some_college", "college"][index % 4],
                "indoor_smoking": ["yes", "no", "unknown"][index % 3],
                "household_smoker": "yes", "noncurrent": 1,
                "no_recent_all": 0 if index == count - 1 else 1,
                "cotinine": cotinine, "below_lod": None if missing_lab else 0,
                "lod": .010 if period == "L" else .015,
            })
    frame = pd.DataFrame(rows)
    # Verify L's lower native LOD changes the naive endpoint but not common .015.
    target = frame.index[(frame.period == "L") & frame.SEQN.eq(2)][0]
    frame.loc[target, "cotinine"] = .012
    directory = tmp_path_factory.mktemp("artificial_statistics")
    source = directory / "input.csv"
    frame.to_csv(source, index=False)
    _run_r(ROOT / "research" / "analysis.R", source, directory)
    return directory, frame


def test_analysis_contract_scenarios_models_and_missingness(artificial_analysis):
    directory, _ = artificial_analysis
    expected_files = ["estimates.csv", "contrasts.csv", "models.csv", "sensitivities.csv", "missingness.csv", "analysis_metadata.json"]
    assert all((directory / name).exists() for name in expected_files)
    estimates = pd.read_csv(directory / "estimates.csv")
    assert set(estimates.period) == {"I", "P", "L"}
    assert set(estimates.group_variable) == {"overall", "poverty_group", "education", "indoor_smoking"}
    assert estimates.prevalence.dropna().between(0, 1).all()
    models = pd.read_csv(directory / "models.csv")
    assert set(models.model) == {"M1_all", "M1_common", "M2"}
    counts = models.groupby(["period", "model"]).n.first().unstack()
    assert (counts.M1_common == counts.M2).all()
    assert (counts.M1_all > counts.M1_common).all()
    metadata = json.loads((directory / "analysis_metadata.json").read_text())
    assert metadata["periods"]["L"]["weight"] == "WTPH2YR"
    assert "not normal" in metadata["model_ci"]
    assert set(metadata["package_versions"]) == {"survey", "jsonlite"}
    missing = pd.read_csv(directory / "missingness.csv")
    assert "positive_phlebotomy_adults25" in set(missing.denominator)
    assert missing.missing_rate.dropna().between(0, 1).all()


def test_harmonized_cutoffs_and_lab_missing_extremes_are_distinct(artificial_analysis):
    directory, _ = artificial_analysis
    sensitivity = pd.read_csv(directory / "sensitivities.csv").set_index(["period", "scenario"])
    for period in ("I", "P", "L"):
        primary = sensitivity.loc[(period, "primary"), "prevalence"]
        low = sensitivity.loc[(period, "lab_missing_unexposed"), "prevalence"]
        high = sensitivity.loc[(period, "lab_missing_exposed"), "prevalence"]
        assert low <= primary <= high
        for scenario in ("lab_missing_unexposed", "lab_missing_exposed"):
            bound = sensitivity.loc[(period, scenario)]
            assert pd.isna(bound.ci_low) and pd.isna(bound.ci_high)
            assert pd.isna(bound.poverty_gap_ci_low) and pd.isna(bound.poverty_gap_ci_high)
            assert "descriptive_bound_no_ci" in bound.quality_flag
    assert sensitivity.loc[("L", "naive_native_detectability"), "prevalence"] > sensitivity.loc[("L", "cutoff_0_015"), "prevalence"]
    contrasts = pd.read_csv(directory / "contrasts.csv")
    assert len(contrasts) == 6
    assert set(contrasts.contrast) == {"poverty_lt1_minus_ge4", "change_in_poverty_gap_later_minus_earlier"}


def test_ambiguous_period_ids_are_rejected(artificial_analysis, tmp_path):
    _, frame = artificial_analysis
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    source = tmp_path / "duplicate.csv"
    frame.to_csv(source, index=False)
    result = _run_r(ROOT / "research" / "analysis.R", source, tmp_path / "output", check=False)
    assert result.returncode != 0
    assert "duplicate period/SEQN" in result.stderr
    assert not (tmp_path / "output" / "estimates.csv").exists()
