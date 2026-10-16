"""Offline NHANES tests use explicit tiny frames, never production survey results."""

from copy import deepcopy
import hashlib
import io
import json
from urllib.error import URLError

import numpy as np
import pandas as pd
import pytest

from study_workbench import nhanes


@pytest.fixture
def frames():
    # Nine adults and one adolescent. IDs are test keys, not NHANES participants.
    demo = pd.DataFrame({
        "SEQN": range(1, 11), "SDDSRVYR": [66] * 10,
        "RIDAGEYR": [35, 45, 25, 50, 18, 70, 80, 40, 30, 17],
        "RIDSTATR": [2] * 10, "WTMECPRP": [1.] * 10,
        "SDMVSTRA": [1] * 10, "SDMVPSU": [1, 2] * 5,
    })
    smq = pd.DataFrame({
        "SEQN": [1, 2, 3, 4, 5, 6, 7, 8, 10],
        "SMQ020": [2, 1, 1, 1, 7, 9, 1, 1, np.nan],
        "SMQ040": [np.nan, 3, 1, 2, np.nan, np.nan, 7, np.nan, np.nan],
    })
    cot = pd.DataFrame({
        "SEQN": [1, 2, 3, 4, 5, 6, 7, 9, 10],
        "LBXCOT": [.011, .5, 200., 10., .02, np.nan, 20., .03, .011],
        "LBDCOTLC": [1, 0, 0, 0, 0, np.nan, 0, 0, 1],
    })
    return {"P_DEMO": demo, "P_SMQ": smq, "P_COT": cot}


def test_adult_flow_missingness_and_denominators(frames):
    summary, table = nhanes.analyze_frames(frames)
    assert summary["counts"] == {
        "demographic_records": 10, "adult_demographic_records": 9,
        "adult_smoking_questionnaire_records": 8, "adult_cotinine_file_records": 8,
        "adult_with_cotinine": 7, "adult_cotinine_missing": 2,
        "adult_with_classifiable_smoking": 4, "adult_unknown_smoking": 5,
        "analyzed_sample": 4, "excluded_from_paired_sample": 5, "adult_below_lod": 1,
    }
    assert table.n_adults.sum() == 9
    assert table.n_with_cotinine.sum() == 7
    assert table.n_missing_cotinine.sum() == 2
    assert table.loc[table.included_in_classifiable_paired_sample, "n_with_cotinine"].sum() == 4
    assert summary["sample_flow"][-1]["n"] == 4
    assert summary["nationally_representative_estimates"] is False


def test_expected_skips_and_refused_dont_know_remain_distinct(frames):
    summary, table = nhanes.analyze_frames(frames)
    assert summary["smoking_questionnaire"]["smq040_observation_counts"] == {
        "observed": 4, "expected_skip": 3, "missing_prerequisite": 1,
        "missing_required_followup": 1,
    }
    groups = table.set_index("smoking_status")
    assert groups.loc["refused", "n_adults"] == 2
    assert groups.loc["dont_know", "n_adults"] == 1
    assert groups.loc["missing", "n_adults"] == 2
    assert groups.loc["below_100_lifetime", "n_adults"] == 1
    assert "never" not in groups.loc["below_100_lifetime", "label"].lower()
    assert groups.loc["dont_know", "pct_missing_cotinine_within_group"] == 100.


def test_below_lod_is_retained_and_not_a_smoking_classifier(frames):
    summary, table = nhanes.analyze_frames(frames)
    groups = table.set_index("smoking_status")
    assert groups.loc["below_100_lifetime", "median_cotinine_ng_ml"] == .011
    assert groups.loc["below_100_lifetime", "n_below_lod"] == 1
    assert summary["cotinine"]["biomarker_cutoff_applied"] is False
    assert summary["cotinine"]["lower_limit_of_detection"] == .015
    # A large biomarker value does not override an otherwise valid questionnaire category.
    frames["P_COT"].loc[0, ["LBXCOT", "LBDCOTLC"]] = [300., 0]
    _, changed = nhanes.analyze_frames(frames)
    row = changed.set_index("smoking_status").loc["below_100_lifetime"]
    assert row.n_adults == 1
    assert row.median_cotinine_ng_ml == 300.


def test_logically_inconsistent_skip_is_visible_not_forced_to_current(frames):
    frames["P_SMQ"].loc[0, "SMQ040"] = 1
    summary, table = nhanes.analyze_frames(frames)
    assert table.set_index("smoking_status").loc["inconsistent", "n_adults"] == 1
    assert summary["counts"]["analyzed_sample"] == 3


@pytest.mark.parametrize("name", ["P_DEMO", "P_SMQ", "P_COT"])
def test_duplicate_keys_rejected_before_join(frames, name):
    frames[name] = pd.concat([frames[name], frames[name].iloc[[0]]], ignore_index=True)
    with pytest.raises(nhanes.NhanesDataError, match="unique"):
        nhanes.analyze_frames(frames)


@pytest.mark.parametrize("key", [np.nan, -1., 1.5])
def test_invalid_join_key_rejected(frames, key):
    frames["P_COT"]["SEQN"] = frames["P_COT"]["SEQN"].astype(float)
    frames["P_COT"].loc[0, "SEQN"] = key
    with pytest.raises(nhanes.NhanesDataError, match="SEQN"):
        nhanes.analyze_frames(frames)


def test_foreign_cycle_and_orphan_keys_rejected(frames):
    frames["P_DEMO"].loc[0, "SDDSRVYR"] = 10
    with pytest.raises(nhanes.NhanesDataError, match="66"):
        nhanes.analyze_frames(frames)
    frames["P_DEMO"].loc[0, "SDDSRVYR"] = 66
    frames["P_COT"].loc[0, "SEQN"] = 999
    with pytest.raises(nhanes.NhanesDataError, match="same-cycle"):
        nhanes.analyze_frames(frames)


@pytest.mark.parametrize("column,value", [
    ("LBXCOT", -1.), ("LBDCOTLC", 2), ("LBDCOTLC", np.nan), ("LBXCOT", .02)
])
def test_invalid_lab_codes_pairs_and_lod_fill_rejected(frames, column, value):
    frames["P_COT"].loc[0, column] = value
    with pytest.raises(nhanes.NhanesDataError, match="P_COT"):
        nhanes.analyze_frames(frames)


def test_at_or_above_lod_flag_requires_at_least_llod(frames):
    frames["P_COT"].loc[0, "LBDCOTLC"] = 0
    with pytest.raises(nhanes.NhanesDataError, match="conflicts"):
        nhanes.analyze_frames(frames)


def test_unexpected_questionnaire_code_rejected(frames):
    frames["P_SMQ"].loc[0, "SMQ020"] = 77
    with pytest.raises(nhanes.NhanesDataError, match="questionnaire code"):
        nhanes.analyze_frames(frames)


def test_missing_column_and_wrong_release_name_rejected(frames):
    damaged = deepcopy(frames)
    damaged["P_DEMO"] = damaged["P_DEMO"].drop(columns="WTMECPRP")
    with pytest.raises(nhanes.NhanesDataError, match="required columns"):
        nhanes.analyze_frames(damaged)
    frames["DEMO_J"] = frames.pop("P_DEMO")
    with pytest.raises(nhanes.NhanesDataError, match="Exactly P_DEMO"):
        nhanes.analyze_frames(frames)


def test_empty_adult_sample_has_no_invented_statistics(frames):
    frames["P_DEMO"]["RIDAGEYR"] = 17
    summary, table = nhanes.analyze_frames(frames)
    assert summary["counts"]["adult_demographic_records"] == 0
    assert table.n_adults.sum() == 0
    assert table.median_cotinine_ng_ml.isna().all()
    # JSON must contain null, never NaN/Infinity.
    json.dumps(summary, allow_nan=False)


def _xpt_payload():
    # Header-only test payload. Actual decoding is mocked in cache unit tests;
    # the real CDC decode is exercised separately by the reproducible case run.
    return nhanes.XPT_SIGNATURE.ljust(240, b" ")


@pytest.mark.parametrize("payload", [b"<!doctype html>CDC error", b"", nhanes.XPT_SIGNATURE])
def test_download_rejects_html_or_truncated_xpt(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(nhanes, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    with pytest.raises(nhanes.NhanesDataError, match="XPORT"):
        nhanes.load_source("P_DEMO", tmp_path)
    assert not (tmp_path / "P_DEMO.xpt").exists()


def test_signature_without_valid_xpt_structure_cannot_be_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(nhanes, "urlopen", lambda *args, **kwargs: io.BytesIO(_xpt_payload()))
    with pytest.raises(nhanes.NhanesDataError, match="parsing failed"):
        nhanes.load_source("P_DEMO", tmp_path)
    assert not (tmp_path / "P_DEMO.xpt").exists()


def test_download_and_verified_cache_keep_original_retrieval_time(tmp_path, monkeypatch, frames):
    payload = _xpt_payload()
    monkeypatch.setattr(nhanes, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    monkeypatch.setattr(pd, "read_sas", lambda *args, **kwargs: frames["P_DEMO"].copy())
    _, first = nhanes.load_source("P_DEMO", tmp_path)
    assert first["cached"] is False
    assert first["sha256"] == hashlib.sha256(payload).hexdigest()
    assert first["bytes"] == len(payload)
    assert first["records"] == 10

    def no_network(*args, **kwargs):
        raise AssertionError("A valid cache must not access the network")

    monkeypatch.setattr(nhanes, "urlopen", no_network)
    _, second = nhanes.load_source("P_DEMO", tmp_path)
    assert second["cached"] is True
    assert second["retrieved_at_utc"] == first["retrieved_at_utc"]
    assert second["sha256"] == first["sha256"]


@pytest.mark.parametrize("damage", ["payload", "metadata", "url", "cycle", "time", "list"])
def test_corrupt_cache_fails_closed_without_network(tmp_path, monkeypatch, frames, damage):
    monkeypatch.setattr(nhanes, "urlopen", lambda *args, **kwargs: io.BytesIO(_xpt_payload()))
    monkeypatch.setattr(pd, "read_sas", lambda *args, **kwargs: frames["P_DEMO"].copy())
    nhanes.load_source("P_DEMO", tmp_path)
    metadata_path = tmp_path / "P_DEMO.xpt.json"
    metadata = json.loads(metadata_path.read_text())
    if damage == "payload":
        (tmp_path / "P_DEMO.xpt").write_bytes(b"tampered")
    elif damage == "metadata":
        metadata_path.unlink()
    else:
        if damage == "url":
            metadata["source_url"] = "https://example.com/untrusted.xpt"
        elif damage == "cycle":
            metadata["cycle"] = "2017-2018"
        elif damage == "time":
            metadata["retrieved_at_utc"] = "2026-10-16"  # timezone is required
        else:
            metadata = []
        metadata_path.write_text(json.dumps(metadata))

    def no_network(*args, **kwargs):
        raise AssertionError("An invalid cache must fail visibly, not replace itself")

    monkeypatch.setattr(nhanes, "urlopen", no_network)
    with pytest.raises(nhanes.NhanesDataError, match="cache"):
        nhanes.load_source("P_DEMO", tmp_path)


def test_cache_with_valid_hash_but_html_payload_is_still_rejected(tmp_path, monkeypatch):
    payload = b"<!doctype html>Not actual data"
    (tmp_path / "P_COT.xpt").write_bytes(payload)
    metadata = {
        "name": "P_COT", "cycle": nhanes.CYCLE,
        "source_url": f"{nhanes.BASE_URL}/P_COT.xpt",
        "retrieved_at_utc": "2026-10-16T00:00:00+00:00",
        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
    }
    (tmp_path / "P_COT.xpt.json").write_text(json.dumps(metadata))
    with pytest.raises(nhanes.NhanesDataError, match="signature"):
        nhanes.load_source("P_COT", tmp_path)


def test_download_failure_and_size_limit_are_actionable(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise URLError("offline test")

    monkeypatch.setattr(nhanes, "urlopen", unavailable)
    with pytest.raises(nhanes.NhanesDataError, match="CDC download failed"):
        nhanes.load_source("P_COT", tmp_path)
    monkeypatch.setattr(nhanes, "MAX_DOWNLOAD_BYTES", 100)
    monkeypatch.setattr(nhanes, "urlopen", lambda *args, **kwargs: io.BytesIO(_xpt_payload()))
    with pytest.raises(nhanes.NhanesDataError, match="size limit"):
        nhanes.load_source("P_COT", tmp_path)


def test_xport_zero_artifact_normalized_exactly_without_rounding_measurements(frames, monkeypatch):
    frame = frames["P_COT"].copy()
    frame.loc[1, "LBDCOTLC"] = nhanes.XPORT_ZERO_ARTIFACT
    monkeypatch.setattr(pd, "read_sas", lambda *args, **kwargs: frame)
    parsed = nhanes._parse_xpt(_xpt_payload(), "P_COT")
    assert parsed.loc[1, "LBDCOTLC"] == 0
    assert parsed.loc[0, "LBXCOT"] == .011
    assert parsed.loc[1, "LBXCOT"] == .5
    assert parsed.attrs["xport_zero_artifacts_normalized"] == {"LBDCOTLC": 1}


def test_outputs_are_aggregate_labeled_and_escape_source_text(tmp_path, frames, monkeypatch):
    def fixture_source(name, cache):
        return frames[name], {
            "name": name, "source_url": f"{nhanes.BASE_URL}/{name}.xpt",
            "codebook_url": f"{nhanes.BASE_URL}/{name}.htm",
            "retrieved_at_utc": "2026-10-16T00:00:00+00:00", "records": len(frames[name]),
            "sha256": "0" * 64,
        }

    monkeypatch.setattr(nhanes, "load_source", fixture_source)
    result = nhanes.run_analysis(tmp_path / "report", tmp_path / "cache")
    assert set(result["paths"]) == {"summary", "report", "sample_summary", "provenance_manifest"}
    summary = json.loads((tmp_path / "report/summary.json").read_text())
    assert summary["counts"]["analyzed_sample"] == 4
    csv = pd.read_csv(result["paths"]["sample_summary"])
    assert "SEQN" not in csv.columns  # Only aggregate public outputs are delivered.
    assert len(csv) == len(nhanes.STATUS_LABELS)
    summary["analysis_name"] = "<script>bad</script>"
    summary["limitations"][0] = "<script>bad</script>"
    report = nhanes.render_public_report(summary, result["provenance"])
    assert "<script>bad</script>" not in report
    assert "&lt;script&gt;bad&lt;/script&gt;" in report
    assert "not national prevalence" in report
    assert "PUBLIC CROSS-SECTIONAL DATA" in report
