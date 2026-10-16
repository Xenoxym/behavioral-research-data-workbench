"""Explicit hand-built corner cases for the real-data pipeline; never research findings."""

from dataclasses import replace
import hashlib
import io
import json

import numpy as np
import pandas as pd
import pytest

from study_workbench import research_data as rd


def example_frames(period):
    offset = {"I": 1000, "P": 2000, "L": 3000}[period]
    ids = np.arange(offset + 1, offset + 9)
    details = rd.PERIODS[period]
    demo = pd.DataFrame({
        "SEQN": ids, "SDDSRVYR": details["cycle"], "RIDSTATR": [2, 2, 2, 2, 2, 2, 1, 2],
        "RIDAGEYR": [30, 40, 50, 18, 17, 80, 25, 60], "RIAGENDR": [1, 2] * 4,
        "RIDRETH3": [1, 2, 3, 4, 6, 7, 3, 4],
        "INDFMPIR": [0, 1, 2, 4, 5, np.nan, 1.99, 3.99],
        "DMDEDUC2": [1, 3, 4, np.nan, np.nan, 5, 2, 9],
        "SDMVSTRA": [1, 1, 2, 2, 3, 3, 4, 4], "SDMVPSU": [1, 2] * 4,
        details["mec_weight"]: [1., 2., 3., 1., 1., 2., 0., 2.],
    })
    smq = pd.DataFrame({
        "SEQN": ids, "SMQ020": [2, 1, 1, 2, np.nan, 7, 2, 1],
        "SMQ040": [np.nan, 3, 1, np.nan, np.nan, np.nan, np.nan, 3],
        "SMD641": [np.nan, np.nan, 30, np.nan, np.nan, np.nan, np.nan, np.nan],
    })
    recent = pd.DataFrame({
        "SEQN": ids, "SMQ681": [2, 2, 1, 2, np.nan, 2, np.nan, 2],
        "SMQ851": [2, 2, 2, 7, np.nan, 2, np.nan, 2],
        "SMQ863": [2, 2, 2, 2, np.nan, 1, np.nan, 2],
        "SMQ690A": [np.nan, np.nan, 1, np.nan, np.nan, np.nan, np.nan, np.nan],
        "SMQ690F": [np.nan, np.nan, np.nan, np.nan, np.nan, 6, np.nan, np.nan],
        "SMDANY": [2, 1, 1, np.nan, np.nan, 1, np.nan, 2],
    })
    if period == "L":
        recent["SMQ846"] = [1, 2, 2, 2, np.nan, 2, np.nan, 2]
    else:
        recent["SMQ690H"] = [np.nan, 8, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]
    family = pd.DataFrame({
        "SEQN": ids, "SMD460": [0, 1, 2, 777, np.nan, 1, 0, 1],
        "SMD470": [np.nan, 0, 1, 999, np.nan, np.nan, 0, 2],
    })
    cot_ids = ids[[0, 1, 2, 3, 4, 5, 7]]
    cot = pd.DataFrame({
        "SEQN": cot_ids, "LBXCOT": [.007 if period == "L" else .011, .05, 5., 12., .015, np.nan, .1],
        "LBDCOTLC": [1., 0., 0., 0., 0., np.nan, 0.],
    })
    components = {"DEMO": demo, "SMQ": smq, "SMQRTU": recent, "SMQFAM": family, "COT": cot}
    if period == "L":
        weights = pd.DataFrame({"SEQN": cot_ids, "WTPH2YR": [1., 2., 3., 1., 1., 0., 2.]})
        components["WEIGHT"] = weights
        components["WEIGHT_CHECK"] = weights.copy()
    return {source.name: components[source.component].copy()
            for source in rd.SOURCES if source.period == period}


@pytest.mark.parametrize("period", ["I", "P", "L"])
def test_full_demographic_rows_survive_missing_sources_and_zero_weights(period):
    output, quality = rd.harmonize_period(period, example_frames(period))
    assert len(output) == 8
    assert output.SEQN.is_unique
    assert quality["all_demographic_rows_retained"] is True
    zero = output.loc[output.mec_weight.eq(0)].iloc[0]
    assert zero.has_cot_row == 0
    assert pd.isna(zero.cotinine)
    if period == "L":
        assert pd.isna(zero.weight)  # No blood-file row is never replaced with MEC weight.
    else:
        assert zero.weight == 0
    assert "exposed" not in output.columns


def test_poverty_boundaries_education_and_race_are_explicit():
    output, _ = rd.harmonize_period("I", example_frames("I"))
    assert output.poverty_group.tolist() == ["lt1", "1to2", "2to4", "ge4", "ge4", "unknown", "1to2", "2to4"]
    assert output.education.tolist() == ["lt_hs", "hs", "some_college", "unknown", "unknown", "college", "lt_hs", "unknown"]
    assert output.race_group.tolist() == ["hispanic", "hispanic", "nh_white", "nh_black", "nh_asian", "other", "nh_white", "nh_black"]


def test_noncurrent_unknowns_and_contradictory_skip_are_not_inferred_as_no_use():
    frame = pd.DataFrame({"SMQ020": [2, 1, 1, 7, 9, np.nan, 2],
                          "SMQ040": [np.nan, 3, 1, np.nan, np.nan, np.nan, 3]})
    result, conflict = rd._noncurrent(frame)
    assert result.iloc[:3].tolist() == [1, 1, 0]
    assert result.iloc[3:].isna().all()
    assert conflict.tolist() == [False, False, False, False, False, False, True]


@pytest.mark.parametrize("period", ["I", "P"])
def test_explicit_electronic_detail_overrides_broad_no_without_treating_blank_as_no(period):
    output, quality = rd.harmonize_period(period, example_frames(period))
    assert output.loc[0, "no_recent_all"] == 1  # Three observed no screens; H is a skip.
    assert output.loc[1, "no_recent_all"] == 0  # H=8 positive overrides broad no.
    assert pd.isna(output.loc[3, "no_recent_all"])  # Refused smokeless question.
    assert pd.isna(output.loc[4, "no_recent_all"])  # All absent, not inferred no.
    assert output.loc[5, "no_recent_all"] == 0  # NRT use.
    assert quality["age25_positive_detail_override_broad_no"] == 1


def test_l_requires_separate_explicit_electronic_no():
    frames = example_frames("L")
    frames["SMQRTU_L"].loc[1, "SMQ846"] = 9
    output, _ = rd.harmonize_period("L", frames)
    assert output.loc[0, "no_recent_all"] == 0
    assert pd.isna(output.loc[1, "no_recent_all"])
    assert output.loc[7, "no_recent_all"] == 1


def test_known_positive_use_excludes_even_if_another_screen_is_unknown():
    frames = example_frames("I")
    frames["SMQRTU_I"].loc[2, "SMQ863"] = np.nan
    output, _ = rd.harmonize_period("I", frames)
    assert output.loc[2, "no_recent_all"] == 0


def test_positive_cigarette_or_nrt_detail_conflicts_are_flagged_and_exclude():
    frames = example_frames("I")
    frames["SMQRTU_I"].loc[0, "SMQ690A"] = 1
    frames["SMQRTU_I"].loc[7, "SMQ690F"] = 6
    output, quality = rd.harmonize_period("I", frames)
    assert output.loc[0, "no_recent_all"] == 0
    assert output.loc[7, "no_recent_all"] == 0
    assert quality["recent_detail_conflicts"] == 3  # Includes H=8 example.


def test_household_structural_skip_is_distinct_from_refused_and_unknown():
    output, quality = rd.harmonize_period("I", example_frames("I"))
    assert output.loc[0, "indoor_smoking"] == "no"
    assert output.loc[0, "household_indoor_structural_skip"] == 1
    assert output.loc[1, "household_smoker"] == "yes"
    assert output.loc[1, "indoor_smoking"] == "no"
    assert output.loc[3, "indoor_smoking"] == "unknown"
    assert output.loc[5, "indoor_smoking"] == "unknown"
    assert output.loc[7, "household_conflict"] == 1
    assert output.loc[7, "indoor_smoking"] == "unknown"
    assert quality["household_count_conflicts"] == 1


def test_household_zero_gate_with_positive_followup_is_not_silently_forced_no():
    frames = example_frames("P")
    frames["P_SMQFAM"].loc[0, "SMD470"] = 1
    output, _ = rd.harmonize_period("P", frames)
    assert output.loc[0, "household_smoker"] == "unknown"
    assert output.loc[0, "indoor_smoking"] == "unknown"


@pytest.mark.parametrize("damage", ["duplicate", "missing", "foreign", "wrong_period", "wrong_cycle"])
def test_invalid_join_or_period_rejected(damage):
    frames = example_frames("I")
    if damage == "duplicate":
        frames["COT_I"] = pd.concat([frames["COT_I"], frames["COT_I"].iloc[[0]]])
    elif damage == "missing":
        frames["COT_I"].loc[0, "SEQN"] = np.nan
    elif damage == "foreign":
        frames["COT_I"].loc[0, "SEQN"] = 99999
    elif damage == "wrong_period":
        frames["P_COT"] = frames.pop("COT_I")
    else:
        frames["DEMO_I"].loc[0, "SDDSRVYR"] = 66
    with pytest.raises(rd.ResearchDataError):
        rd.harmonize_period("I", frames)


def test_p_three_psus_are_valid_but_not_assumed_in_i():
    frames = example_frames("P")
    frames["P_DEMO"].loc[0, "SDMVPSU"] = 3
    output, _ = rd.harmonize_period("P", frames)
    assert output.loc[0, "psu"] == 3
    frames = example_frames("I")
    frames["DEMO_I"].loc[0, "SDMVPSU"] = 3
    with pytest.raises(rd.ResearchDataError, match="SDMVPSU"):
        rd.harmonize_period("I", frames)


@pytest.mark.parametrize("damage", ["weight_disagreement", "missing_key", "zero_for_measured"])
def test_l_weight_linkage_must_cover_all_cotinine_keys_and_match_independent_file(damage):
    frames = example_frames("L")
    if damage == "weight_disagreement":
        frames["HEPB_S_L"].loc[0, "WTPH2YR"] = 5
    elif damage == "missing_key":
        for name in ("HEPA_L", "HEPB_S_L"):
            frames[name] = frames[name].iloc[1:].copy()
    else:
        for name in ("HEPA_L", "HEPB_S_L"):
            frames[name].loc[0, "WTPH2YR"] = 0
    with pytest.raises(rd.ResearchDataError, match="L:"):
        rd.harmonize_period("L", frames)


def test_l_uses_phlebotomy_weight_not_generic_mec_weight():
    frames = example_frames("L")
    for name in ("HEPA_L", "HEPB_S_L"):
        frames[name].loc[0, "WTPH2YR"] = 99.
    output, quality = rd.harmonize_period("L", frames)
    assert output.loc[0, "weight"] == 99
    assert output.loc[0, "mec_weight"] == 1
    assert quality["weight_linkage"]["all_weights_identical"] is True


def test_l_unexplained_missing_blood_weight_is_rejected_but_ineligible_infant_is_retained():
    frames = example_frames("L")
    frames["DEMO_L"].loc[6, "WTMEC2YR"] = 1
    frames["DEMO_L"].loc[6, "RIDSTATR"] = 2
    with pytest.raises(rd.ResearchDataError, match="aged2"):
        rd.harmonize_period("L", frames)
    frames["DEMO_L"].loc[6, "RIDAGEYR"] = 1
    output, quality = rd.harmonize_period("L", frames)
    assert pd.isna(output.loc[6, "weight"])
    assert quality["analysis_weight_missing_examined_age_under2"] == 1
    assert quality["analysis_weight_missing_unexplained"] == 0


@pytest.mark.parametrize("period,fill", [("I", .011), ("P", .011), ("L", .007)])
def test_period_lod_and_cdc_fill_are_preserved(period, fill):
    output, _ = rd.harmonize_period(period, example_frames(period))
    assert output.loc[0, "cotinine"] == fill
    assert output.loc[0, "below_lod"] == 1
    assert output.loc[0, "lod"] == (.010 if period == "L" else .015)
    assert pd.isna(output.loc[5, "cotinine"])
    assert pd.isna(output.loc[5, "below_lod"])


def test_documented_record_count_is_enforced():
    source = rd.SOURCE_BY_NAME["DEMO_I"]
    with pytest.raises(rd.ResearchDataError, match="record count"):
        rd.validate_source(source, example_frames("I")["DEMO_I"])


@pytest.mark.parametrize("column,value", [("LBXCOT", -.1), ("LBDCOTLC", 9), ("LBDCOTLC", np.nan), ("LBXCOT", .02)])
def test_invalid_laboratory_pair_or_fill_fails(column, value):
    frames = example_frames("P")
    frames["P_COT"].loc[0, column] = value
    with pytest.raises(rd.ResearchDataError):
        rd.harmonize_period("P", frames)


def _payload():
    return rd.XPT_SIGNATURE.ljust(240, b" ")


def _mock_source(monkeypatch):
    source = replace(rd.SOURCE_BY_NAME["DEMO_I"], expected_rows=8)
    monkeypatch.setitem(rd.SOURCE_BY_NAME, source.name, source)
    frame = example_frames("I")["DEMO_I"]
    monkeypatch.setattr(pd, "read_sas", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(rd, "urlopen", lambda *args, **kwargs: io.BytesIO(_payload()))
    return source


def test_exact_decoder_artifact_is_normalized_not_general_low_measurements(monkeypatch):
    source = replace(rd.SOURCE_BY_NAME["COT_L"], expected_rows=7)
    frame = example_frames("L")["COT_L"]
    frame.loc[1, "LBDCOTLC"] = rd.XPORT_ZERO_ARTIFACT
    monkeypatch.setattr(pd, "read_sas", lambda *args, **kwargs: frame)
    result = rd.parse_source(source, _payload())
    assert result.loc[1, "LBDCOTLC"] == 0
    assert result.loc[0, "LBXCOT"] == .007
    assert result.attrs["zero_artifacts_normalized"] == {"LBDCOTLC": 1}


def test_download_then_offline_reuses_original_retrieval_time_and_hash(tmp_path, monkeypatch):
    source = _mock_source(monkeypatch)
    _, first = rd.load_source(source, tmp_path)

    def no_network(*args, **kwargs):
        raise AssertionError("offline must never access network")

    monkeypatch.setattr(rd, "urlopen", no_network)
    _, second = rd.load_source(source, tmp_path, offline=True)
    assert second["cached"] is True
    assert second["sha256"] == hashlib.sha256(_payload()).hexdigest()
    assert first["retrieved_at_utc"] == second["retrieved_at_utc"]
    assert second["records"] == second["documented_records"] == 8


def test_missing_offline_cache_never_attempts_download(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("offline must never access network")

    monkeypatch.setattr(rd, "urlopen", no_network)
    with pytest.raises(rd.ResearchDataError, match="missing cached source in offline"):
        rd.load_source(rd.SOURCE_BY_NAME["DEMO_I"], tmp_path, offline=True)


@pytest.mark.parametrize("damage", ["hash", "metadata", "period", "time", "html"])
def test_invalid_cache_fails_without_replacement(tmp_path, monkeypatch, damage):
    source = _mock_source(monkeypatch)
    rd.load_source(source, tmp_path)
    metadata_path = tmp_path / "DEMO_I.xpt.json"
    metadata = json.loads(metadata_path.read_text())
    if damage in ("hash", "html"):
        data = b"<!doctype html>not data"
        (tmp_path / "DEMO_I.xpt").write_bytes(data)
        if damage == "html":
            metadata["sha256"] = hashlib.sha256(data).hexdigest()
            metadata["bytes"] = len(data)
    elif damage == "metadata":
        metadata = []
    elif damage == "period":
        metadata["period"] = "P"
    else:
        metadata["retrieved_at_utc"] = "2026-10-16"
    metadata_path.write_text(json.dumps(metadata))
    monkeypatch.setattr(rd, "urlopen", lambda *args, **kwargs: pytest.fail("must not replace corrupt cache"))
    with pytest.raises(rd.ResearchDataError):
        rd.load_source(source, tmp_path, offline=True)


def test_error_html_cannot_be_saved_as_public_data(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "urlopen", lambda *args, **kwargs: io.BytesIO(b"<html>error</html>"))
    with pytest.raises(rd.ResearchDataError, match="XPORT"):
        rd.load_source(rd.SOURCE_BY_NAME["DEMO_I"], tmp_path)
    assert not (tmp_path / "DEMO_I.xpt").exists()


def test_prepare_exports_complete_population_and_consistent_flow(tmp_path, monkeypatch):
    period_frames = {period: example_frames(period) for period in rd.PERIODS}

    def fixture_load(source, cache_dir, *, offline=False):
        frame = period_frames[source.period][source.name]
        return frame, {"name": source.name, "period": source.period, "records": len(frame),
                       "sha256": "0" * 64, "cached": offline}

    monkeypatch.setattr(rd, "load_source", fixture_load)
    result = rd.prepare_research(tmp_path / "raw", tmp_path / "work", tmp_path / "report", offline=True)
    assert result["row_count"] == 24
    assert result["source_count"] == 17
    analytic = pd.read_csv(result["analytic_path"])
    assert analytic.groupby("period").size().to_dict() == {"I": 8, "L": 8, "P": 8}
    assert len(analytic) == 24
    assert "exposed" not in analytic
    manifest = json.loads((tmp_path / "report/source_manifest.json").read_text())
    assert len(manifest["sources"]) == 17
    assert manifest["analytic_csv_sha256"] == hashlib.sha256((tmp_path / "work/analytic.csv").read_bytes()).hexdigest()
    flow = pd.read_csv(result["flow_path"])
    for _, period_flow in flow.groupby("period"):
        assert period_flow.iloc[0].n == 8
        assert period_flow.n.diff().dropna().le(0).all()
        assert period_flow.excluded_from_previous.sum() == 8 - period_flow.iloc[-1].n


def test_cross_period_duplicate_keys_fail_before_any_output(tmp_path, monkeypatch):
    period_frames = {period: example_frames(period) for period in rd.PERIODS}
    # Reassign all P keys to the I range while preserving valid within-period joins.
    for frame in period_frames["P"].values():
        frame["SEQN"] -= 1000

    def fixture_load(source, cache_dir, *, offline=False):
        return period_frames[source.period][source.name], {"name": source.name}

    monkeypatch.setattr(rd, "load_source", fixture_load)
    with pytest.raises(rd.ResearchDataError, match="Overlapping"):
        rd.prepare_research(tmp_path / "raw", tmp_path / "work", tmp_path / "report")
    assert not (tmp_path / "work/analytic.csv").exists()
