"""Independent, unweighted NHANES smoking/serum-cotinine sample description.

No network access occurs on import. Raw public-use files are cached separately from
the synthetic study, with checksums and original retrieval timestamps. This module
does not estimate population prevalence or classify people from a biomarker cutoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


CYCLE = "2017-March 2020 pre-pandemic"
BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
SOURCE_COLUMNS = {
    "P_DEMO": [
        "SEQN", "SDDSRVYR", "RIDAGEYR", "RIDSTATR", "WTMECPRP", "SDMVSTRA", "SDMVPSU"
    ],
    "P_SMQ": ["SEQN", "SMQ020", "SMQ040"],
    "P_COT": ["SEQN", "LBXCOT", "LBDCOTLC"],
}
LLOD_NG_ML = 0.015
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
XPT_SIGNATURE = b"HEADER RECORD*******LIBRARY HEADER RECORD!!!!!!!"
# pandas <3 can decode all-zero IBM numeric bytes as 2**-260 (GH#30051).
# Normalize only this exact artifact; never round general scientific measurements.
XPORT_ZERO_ARTIFACT = 2.0 ** -260
CLASSIFIABLE_STATUSES = (
    "below_100_lifetime", "former", "current_every_day", "current_some_days"
)
STATUS_LABELS = {
    "below_100_lifetime": "Fewer than 100 lifetime cigarettes",
    "former": "At least 100 lifetime; now not at all",
    "current_every_day": "At least 100 lifetime; now every day",
    "current_some_days": "At least 100 lifetime; now some days",
    "refused": "Smoking response refused",
    "dont_know": "Smoking response: do not know",
    "missing": "Smoking classification unavailable",
    "inconsistent": "Questionnaire skip inconsistency",
}
CODE_MAPPINGS = {
    "SMQ020": {
        "1": "at least 100 lifetime cigarettes", "2": "fewer than 100 lifetime cigarettes",
        "7": "refused", "9": "do not know", "missing": "not observed"
    },
    "SMQ040": {
        "1": "every day", "2": "some days", "3": "not at all", "7": "refused",
        "9": "do not know",
        "missing": "expected skip for SMQ020=2/7/9; otherwise unavailable"
    },
    "LBDCOTLC": {"0": "at or above LLOD", "1": "below LLOD", "missing": "not observed"},
    "SDDSRVYR": {"66": CYCLE},
}
LIMITATIONS = [
    "All counts, percentages and quantiles describe the analyzed public-use sample only. "
    "Survey weights, strata and PSUs are not applied; these are not US national estimates.",
    "The case is cross-sectional, not a longitudinal study or randomized trial; it cannot "
    "estimate intervention effectiveness, causation, quit rates or follow-up completion.",
    "The paired sample excludes adults without a classifiable cigarette response or an "
    "available serum cotinine result; missing biospecimens may introduce selection bias.",
    "Fewer than 100 lifetime cigarettes is a questionnaire category, not proof of no "
    "current cigarette use or no nicotine exposure.",
    "Cotinine reflects nicotine exposure from multiple sources, including cigarettes, "
    "secondhand exposure, nicotine replacement therapy and electronic nicotine products. "
    "Those sources and timing are not resolved by these three files.",
    "No cotinine cutoff, clinical diagnosis, abstinence verification or honesty label is "
    "assigned. Differences between self-report and a biomarker require contextual research.",
    "Below-detection results retain the CDC-supplied LLOD/sqrt(2) fill values (published "
    "rounded values) and detection flags. Quantiles near the detection limit are censored "
    "descriptions, not precise concentrations.",
    "Age is age at screening and is top-coded at 80 years. The files combine 2017-2018 "
    "and the incomplete 2019-March 2020 cycle; they must not be split using these weights.",
]


class NhanesDataError(ValueError):
    """The source payload, cache metadata or analysis assumptions are invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_xpt(payload: bytes, source: str) -> None:
    if not payload.startswith(XPT_SIGNATURE):
        raise NhanesDataError(f"{source}: expected SAS XPORT signature, not HTML or another file.")
    if len(payload) < 240 or len(payload) % 80:
        raise NhanesDataError(f"{source}: truncated or malformed SAS XPORT record length.")


def _parse_xpt(payload: bytes, source: str) -> pd.DataFrame:
    _validate_xpt(payload, source)
    try:
        frame = pd.read_sas(io.BytesIO(payload), format="xport", encoding="utf-8")
    except (ValueError, OSError, IndexError, UnicodeError, struct.error) as exc:
        raise NhanesDataError(f"{source}: SAS XPORT parsing failed: {exc}") from exc
    normalized = {}
    for column in frame.select_dtypes(include="number").columns.intersection(
        SOURCE_COLUMNS.get(source, [])
    ):
        artifact = frame[column].abs().eq(XPORT_ZERO_ARTIFACT)
        if artifact.any():
            normalized[column] = int(artifact.sum())
            frame.loc[artifact, column] = 0.0
    frame.attrs["xport_zero_artifacts_normalized"] = normalized
    _validate_frame(source, frame)
    return frame


def _validate_frame(name: str, frame: pd.DataFrame) -> None:
    if name not in SOURCE_COLUMNS:
        raise NhanesDataError(f"Unexpected source {name}; only same-cycle P_ files are accepted.")
    missing = set(SOURCE_COLUMNS[name]) - set(frame.columns)
    if missing:
        raise NhanesDataError(f"{name}: missing required columns {sorted(missing)}.")
    if frame.empty:
        raise NhanesDataError(f"{name}: source contains no records.")
    for column in SOURCE_COLUMNS[name]:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            raise NhanesDataError(f"{name}.{column}: expected numeric public-use values.")
        if not np.isfinite(frame[column].dropna().to_numpy()).all():
            raise NhanesDataError(f"{name}.{column}: non-finite value.")
    ids = frame["SEQN"]
    if ids.isna().any() or (ids <= 0).any() or (ids % 1 != 0).any() or ids.duplicated().any():
        raise NhanesDataError(f"{name}: SEQN must be nonmissing, positive, integer and unique.")
    if name == "P_DEMO":
        if frame["SDDSRVYR"].isna().any() or not frame["SDDSRVYR"].eq(66).all():
            raise NhanesDataError("P_DEMO: SDDSRVYR must be 66 for the combined pre-pandemic cycle.")
        ages = frame["RIDAGEYR"]
        if ages.isna().any() or not ages.between(0, 80).all() or (ages % 1 != 0).any():
            raise NhanesDataError("P_DEMO: invalid screening age (expected integer 0-80).")
        if not frame["RIDSTATR"].isin([1, 2]).all():
            raise NhanesDataError("P_DEMO: invalid interview/examination status.")
        if (frame["WTMECPRP"].dropna() < 0).any():
            raise NhanesDataError("P_DEMO: negative examination weight.")
    elif name == "P_SMQ":
        for column, values in {"SMQ020": [1, 2, 7, 9], "SMQ040": [1, 2, 3, 7, 9]}.items():
            if not frame[column].dropna().isin(values).all():
                raise NhanesDataError(f"P_SMQ.{column}: unexpected questionnaire code.")
    elif name == "P_COT":
        cot, flag = frame["LBXCOT"], frame["LBDCOTLC"]
        if not flag.dropna().isin([0, 1]).all() or (cot.dropna() < 0).any():
            raise NhanesDataError("P_COT: invalid concentration or detection-limit flag.")
        if cot.isna().ne(flag.isna()).any():
            raise NhanesDataError("P_COT: cotinine result and LOD flag must be jointly available.")
        if (cot[flag.eq(0)] < LLOD_NG_ML).any():
            raise NhanesDataError("P_COT: at/above-LOD flag conflicts with concentration.")
        below = cot[flag.eq(1)]
        if not np.isclose(below, LLOD_NG_ML / math.sqrt(2), atol=0.0005, rtol=0).all():
            raise NhanesDataError("P_COT: unexpected below-LOD fill value (rounding allowed).")


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def _atomic_bytes(path: Path, payload: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name, suffix=".part",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_source(name: str, cache_dir: Path | str) -> tuple[pd.DataFrame, dict]:
    """Retrieve one allowlisted CDC file, or verify its existing cache without networking.

    Invalid caches fail closed; they are never silently used or overwritten. To recover,
    move/delete only the named cached file and its metadata, then rerun the download.
    """
    if name not in SOURCE_COLUMNS:
        raise NhanesDataError(f"Unknown NHANES source: {name}.")
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{name}.xpt"
    metadata_path = cache_dir / f"{name}.xpt.json"
    source_url = f"{BASE_URL}/{name}.xpt"
    cached = path.exists()
    if cached:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise NhanesDataError(f"{name}: cache metadata missing or invalid; re-download.") from exc
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if (not isinstance(metadata, dict) or metadata.get("name") != name
                or metadata.get("source_url") != source_url or metadata.get("cycle") != CYCLE
                or metadata.get("sha256") != digest or metadata.get("bytes") != len(payload)
                or not metadata.get("retrieved_at_utc")):
            raise NhanesDataError(f"{name}: cache metadata/hash mismatch; re-download.")
        try:
            retrieved = datetime.fromisoformat(metadata["retrieved_at_utc"])
            if retrieved.tzinfo is None:
                raise ValueError("timestamp is not timezone-aware")
        except (TypeError, ValueError) as exc:
            raise NhanesDataError(f"{name}: invalid cache retrieval timestamp.") from exc
        frame = _parse_xpt(payload, name)
    else:
        request = Request(source_url, headers={"User-Agent": "BehavioralResearchWorkbench/0.1"})
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(payload) > MAX_DOWNLOAD_BYTES:
                    raise NhanesDataError(f"{name}: source exceeded the download size limit.")
        except (URLError, OSError) as exc:
            raise NhanesDataError(f"{name}: CDC download failed: {exc}") from exc
        frame = _parse_xpt(payload, name)
        metadata = {
            "name": name, "cycle": CYCLE, "source_url": source_url,
            "codebook_url": f"{BASE_URL}/{name}.htm",
            "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
            "retrieved_at_utc": _utc_now(),
        }
        _atomic_bytes(path, payload)
        _atomic_bytes(metadata_path, (json.dumps(metadata, indent=2) + "\n").encode("utf-8"))
    provenance = {
        **metadata, "codebook_url": f"{BASE_URL}/{name}.htm", "cached": cached,
        "verified_at_utc": _utc_now(), "records": len(frame),
        "selected_columns": SOURCE_COLUMNS[name],
        "xport_zero_artifacts_normalized": frame.attrs.get("xport_zero_artifacts_normalized", {}),
    }
    return frame[SOURCE_COLUMNS[name]].copy(), provenance


def _smoking_status(row: pd.Series) -> str:
    lifetime, now = row["SMQ020"], row["SMQ040"]
    if pd.isna(lifetime):
        return "missing" if pd.isna(now) else "inconsistent"
    if lifetime in (2, 7, 9):
        if pd.notna(now):
            return "inconsistent"
        return {2: "below_100_lifetime", 7: "refused", 9: "dont_know"}[lifetime]
    if pd.isna(now):
        return "missing"
    return {1: "current_every_day", 2: "current_some_days", 3: "former",
            7: "refused", 9: "dont_know"}[now]


def _smq040_reason(row: pd.Series) -> str:
    if pd.notna(row["SMQ040"]):
        return "observed"
    lifetime = row["SMQ020"]
    if pd.isna(lifetime):
        return "missing_prerequisite"
    return "expected_skip" if lifetime in (2, 7, 9) else "missing_required_followup"


def _response_counts(series: pd.Series, mappings: dict[str, str]) -> dict[str, int]:
    result = {label: int(series.eq(int(code)).sum())
              for code, label in mappings.items() if code != "missing"}
    result["missing"] = int(series.isna().sum())
    return result


def analyze_frames(frames: Mapping[str, pd.DataFrame]) -> tuple[dict, pd.DataFrame]:
    """Validate and join same-cycle frames, returning only aggregate public-data results."""
    if set(frames) != set(SOURCE_COLUMNS):
        raise NhanesDataError("Exactly P_DEMO, P_SMQ and P_COT from one release are required.")
    for name, frame in frames.items():
        _validate_frame(name, frame)
    demo = frames["P_DEMO"][SOURCE_COLUMNS["P_DEMO"]].copy()
    for name in ("P_SMQ", "P_COT"):
        if not frames[name]["SEQN"].isin(demo["SEQN"]).all():
            raise NhanesDataError(f"{name}: SEQN not found in same-cycle P_DEMO; join rejected.")
    adults = demo.loc[demo["RIDAGEYR"].ge(18)].copy()
    adults = adults.merge(frames["P_SMQ"][SOURCE_COLUMNS["P_SMQ"]], on="SEQN", how="left",
                          validate="one_to_one", indicator="_smq_join")
    adults = adults.merge(frames["P_COT"][SOURCE_COLUMNS["P_COT"]], on="SEQN", how="left",
                          validate="one_to_one", indicator="_cot_join")
    adults["smoking_status"] = (
        adults.apply(_smoking_status, axis=1) if len(adults) else pd.Series(dtype="object")
    )
    adults["smq040_observation"] = (
        adults.apply(_smq040_reason, axis=1) if len(adults) else pd.Series(dtype="object")
    )
    classifiable = adults["smoking_status"].isin(CLASSIFIABLE_STATUSES)
    measured = adults["LBXCOT"].notna()
    paired = classifiable & measured
    rows = []
    for status, label in STATUS_LABELS.items():
        group = adults.loc[adults["smoking_status"].eq(status)]
        values = group["LBXCOT"].dropna()
        denominator = len(group)
        rows.append({
            "smoking_status": status, "label": label,
            "n_adults": denominator, "n_with_cotinine": len(values),
            "n_missing_cotinine": denominator - len(values),
            "pct_missing_cotinine_within_group": (
                round(100 * (denominator - len(values)) / denominator, 2) if denominator else None
            ),
            "n_below_lod": int(group["LBDCOTLC"].eq(1).sum()),
            "median_cotinine_ng_ml": float(values.median()) if len(values) else None,
            "q25_cotinine_ng_ml": float(values.quantile(.25)) if len(values) else None,
            "q75_cotinine_ng_ml": float(values.quantile(.75)) if len(values) else None,
            "included_in_classifiable_paired_sample": status in CLASSIFIABLE_STATUSES,
        })
    summary = {
        "analysis_name": "NHANES adult cigarette responses and serum cotinine",
        "data_kind": "public_cross_sectional", "cycle": CYCLE,
        "analysis_type": "unweighted analyzed-sample description",
        "nationally_representative_estimates": False,
        "generated_at_utc": _utc_now(),
        "counts": {
            "demographic_records": len(demo), "adult_demographic_records": len(adults),
            "adult_smoking_questionnaire_records": int(adults["_smq_join"].eq("both").sum()),
            "adult_cotinine_file_records": int(adults["_cot_join"].eq("both").sum()),
            "adult_with_cotinine": int(measured.sum()),
            "adult_cotinine_missing": int((~measured).sum()),
            "adult_with_classifiable_smoking": int(classifiable.sum()),
            "adult_unknown_smoking": int((~classifiable).sum()),
            "analyzed_sample": int(paired.sum()),
            "excluded_from_paired_sample": int((~paired).sum()),
            "adult_below_lod": int(adults["LBDCOTLC"].eq(1).sum()),
        },
        "sample_flow": [
            {"step": "All demographic records", "n": len(demo)},
            {"step": "Age at screening >=18", "n": len(adults)},
            {"step": "Classifiable cigarette responses", "n": int(classifiable.sum())},
            {"step": "Also has serum cotinine result (paired sample)", "n": int(paired.sum())},
        ],
        "join_validation": {
            "key": "SEQN", "cardinality": "one_to_one", "cycle_code": 66,
            "unmatched_smq_source_keys": 0, "unmatched_cot_source_keys": 0,
            "all_adult_demographic_rows_retained": True,
        },
        "smoking_questionnaire": {
            "smq020_response_counts": _response_counts(adults["SMQ020"], CODE_MAPPINGS["SMQ020"]),
            "smq040_response_counts": _response_counts(adults["SMQ040"], CODE_MAPPINGS["SMQ040"]),
            "smq040_observation_counts": {
                value: int(adults["smq040_observation"].eq(value).sum())
                for value in ("observed", "expected_skip", "missing_prerequisite",
                              "missing_required_followup")
            },
        },
        "cotinine": {
            "unit": "ng/mL", "lower_limit_of_detection": LLOD_NG_ML,
            "below_lod_handling": "Retain CDC LLOD/sqrt(2) fill value and LBDCOTLC flag; "
                                  "allow published rounding (0.011 ng/mL).",
            "biomarker_cutoff_applied": False,
        },
        "code_mappings": CODE_MAPPINGS, "groups": rows, "limitations": LIMITATIONS,
    }
    return summary, pd.DataFrame(rows)


def _format_value(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, float):
        return f"{value:,.5f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return html.escape(str(value))


def render_public_report(summary: dict, provenance: dict) -> str:
    """Render standalone, escaped HTML; data remain separate from synthetic reports."""
    escape = html.escape
    flow = "".join(
        f'<div class="step"><strong>{item["n"]:,}</strong><span>{escape(item["step"])}</span></div>'
        for item in summary["sample_flow"]
    )
    group_rows = "".join(
        "<tr>" + "".join(f"<td>{_format_value(row[key])}</td>" for key in (
            "label", "n_adults", "n_with_cotinine", "n_missing_cotinine", "n_below_lod",
            "median_cotinine_ng_ml", "q25_cotinine_ng_ml", "q75_cotinine_ng_ml"
        )) + "</tr>" for row in summary["groups"] if row["n_adults"]
    )
    notes = "".join(f"<li>{escape(note)}</li>" for note in summary["limitations"])
    sources = "".join(
        f'<li><a href="{escape(source["source_url"], quote=True)}">{escape(source["name"])} '
        f'XPT</a> · <a href="{escape(source["codebook_url"], quote=True)}">CDC codebook</a>'
        f'<br>Retrieved: {escape(source["retrieved_at_utc"])} · {source["records"]:,} records'
        f'<br><code>SHA256 {escape(source["sha256"])}</code></li>'
        for source in provenance["sources"]
    )
    mappings = "".join(
        f"<tr><td>{escape(variable)}</td><td>{escape(code)}</td><td>{escape(label)}</td></tr>"
        for variable, mapping in summary["code_mappings"].items() for code, label in mapping.items()
    )
    counts = summary["counts"]
    observations = summary["smoking_questionnaire"]["smq040_observation_counts"]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NHANES public-data sample report</title><style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{font:15px/1.55 system-ui,sans-serif;background:#f0f4f6;color:#172b3a;margin:0}}
main{{max-width:1120px;margin:auto;padding:32px}}h1{{font-size:30px;line-height:1.2;margin:12px 0}}h2{{font-size:20px;margin:28px 0 12px}}
.badge{{display:inline-block;background:#dcece7;color:#175947;padding:5px 10px;border-radius:16px;font-size:12px;font-weight:700;letter-spacing:.04em}}
.lead{{max-width:850px;color:#42586a}}.notice{{background:#fff3db;border-left:4px solid #aa7013;padding:14px 18px;margin:22px 0}}
.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.step{{background:white;border:1px solid #d6e1e6;border-radius:8px;padding:18px}}
.step strong{{display:block;font-size:26px;color:#116c63}}.step span{{display:block;font-size:13px;margin-top:6px}}
.table-wrap{{overflow:auto;background:white;border:1px solid #d6e1e6;border-radius:8px}}table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:11px;text-align:left;border-bottom:1px solid #e2e9ed;vertical-align:top}}th{{background:#e8f0f3;font-weight:600}}
td:not(:first-child){{font-variant-numeric:tabular-nums}}li{{margin:8px 0}}code{{font-size:11px;overflow-wrap:anywhere}}a{{color:#075f79}}
footer{{margin-top:30px;border-top:1px solid #cbd8df;padding-top:14px;color:#596e7c;font-size:12px}}
@media(max-width:700px){{main{{padding:18px}}.flow{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:25px}}}}
@media print{{body{{background:white}}main{{max-width:none;padding:0}}.step{{break-inside:avoid}}a{{color:inherit}}}}
</style></head><body><main>
<span class="badge">PUBLIC CROSS-SECTIONAL DATA · INDEPENDENT CASE</span>
<h1>Adult cigarette responses &amp; serum cotinine</h1>
<p class="lead">CDC NHANES {escape(summary["cycle"])}. This reproducible case joins three official files,
documents questionnaire skips and missing laboratory results, and describes nicotine-exposure measurements by self-reported cigarette category.</p>
<div class="notice"><strong>Unweighted sample description.</strong> These results describe the records analyzed here.
They are not national prevalence estimates, clinical diagnoses, abstinence verification, or intervention results.</div>
<div class="flow">{flow}</div>
<h2>Available results and missingness</h2>
<p>Among {counts["adult_demographic_records"]:,} adult demographic records,
{counts["adult_with_cotinine"]:,} have cotinine results and {counts["adult_cotinine_missing"]:,} do not.
The paired sample contains {counts["analyzed_sample"]:,} adults with both classifiable cigarette responses and a cotinine result.
All adults remain visible below, including those with unavailable questionnaire or laboratory data.</p>
<div class="table-wrap"><table><thead><tr><th>Cigarette response category</th><th>Adults</th><th>Cotinine available</th><th>Cotinine missing</th><th>Below LLOD</th><th>Median ng/mL</th><th>25th percentile</th><th>75th percentile</th></tr></thead><tbody>{group_rows}</tbody></table></div>
<p><small>Laboratory summaries use available values within each row, including CDC-supplied below-LOD fill values.
The LLOD is 0.015 ng/mL. Row counts are unweighted; no biomarker threshold is used to assign cigarette status.</small></p>
<h2>Skip logic and merge checks</h2>
<p>The three files use the same release and are joined one-to-one on SEQN, with duplicate, missing and unmatched source keys rejected.
Adult demographic records are retained using left joins. SMQ040 is an expected skip after SMQ020 = 2, 7 or 9;
{observations["expected_skip"]:,} adult records follow this skip. There are
{observations["missing_required_followup"]:,} unavailable required SMQ040 responses and
{observations["missing_prerequisite"]:,} records without the prerequisite response.</p>
<div class="table-wrap"><table><thead><tr><th>Variable</th><th>Raw code</th><th>Meaning / handling</th></tr></thead><tbody>{mappings}</tbody></table></div>
<h2>Interpretation and limits</h2><ul>{notes}</ul>
<h2>Source provenance</h2><ul>{sources}</ul>
<footer>Generated {escape(summary["generated_at_utc"])} · Behavioral Research Data Workbench ·
Public-data analysis is independent of all synthetic participant operations. Aggregate exports only; raw downloads remain in the local cache.</footer>
</main></body></html>'''


def run_analysis(output_dir: Path | str, cache_dir: Path | str | None = None) -> dict:
    """Download/verify CDC sources and write an aggregate, independently labeled case.

    Returns {"summary": ..., "paths": ..., "provenance": ...}. A valid cache supports
    subsequent offline runs. Network/download failures raise NhanesDataError and never
    produce a report claiming real data were analyzed.
    """
    output_dir = Path(output_dir).resolve()
    cache_dir = Path(cache_dir) if cache_dir is not None else Path("data/nhanes/raw")
    frames, sources = {}, []
    for name in SOURCE_COLUMNS:
        frames[name], source = load_source(name, cache_dir)
        sources.append(source)
    summary, table = analyze_frames(frames)
    provenance = {
        "analysis": summary["analysis_name"], "cycle": CYCLE,
        "generated_at_utc": summary["generated_at_utc"],
        "checksum_algorithm": "SHA-256", "sources": sources,
        "methodology_file": "docs/NHANES_METHODS.md",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(output_dir / "summary.json"),
        "report": str(output_dir / "report.html"),
        "sample_summary": str(output_dir / "sample_summary.csv"),
        "provenance_manifest": str(output_dir / "provenance_manifest.json"),
    }
    _write_json(Path(paths["summary"]), summary)
    _write_json(Path(paths["provenance_manifest"]), provenance)
    table.to_csv(paths["sample_summary"], index=False)
    Path(paths["report"]).write_text(render_public_report(summary, provenance), encoding="utf-8")
    return {"summary": summary, "paths": paths, "provenance": provenance}
