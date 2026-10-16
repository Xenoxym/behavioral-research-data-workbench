"""Real CDC source collection and frozen-plan harmonization, without outcome estimation.

Every DEMO row is exported so the survey design can be defined before domain selection.
No data are generated, imputed as observations, or mixed with the legacy synthetic study.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


PERIODS = {
    "I": {"label": "2015-2016", "year": 2015, "cycle": 9, "lod": .015,
          "mec_weight": "WTMEC2YR"},
    "P": {"label": "2017-March 2020", "year": 2017, "cycle": 66, "lod": .015,
          "mec_weight": "WTMECPRP"},
    "L": {"label": "August 2021-August 2023", "year": 2021, "cycle": 12, "lod": .010,
          "mec_weight": "WTMEC2YR"},
}
XPT_SIGNATURE = b"HEADER RECORD*******LIBRARY HEADER RECORD!!!!!!!"
XPORT_ZERO_ARTIFACT = 2.0 ** -260
MAX_BYTES = 25 * 1024 * 1024
PLAN_COMMIT = "4ceb883"


@dataclass(frozen=True)
class Source:
    name: str
    period: str
    component: str
    expected_rows: int
    columns: tuple[str, ...]

    @property
    def url(self) -> str:
        return (f"https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/"
                f"{PERIODS[self.period]['year']}/DataFiles/{self.name}.xpt")

    @property
    def codebook_url(self) -> str:
        return self.url.removesuffix(".xpt") + ".htm"


def _make_sources() -> tuple[Source, ...]:
    counts = {"I": [9971, 7001, 6744, 9971, 8608],
              "P": [15560, 11137, 10409, 15560, 13027],
              "L": [11933, 9015, 7199, 11933, 8493]}
    sources = []
    for period, details in PERIODS.items():
        columns = {
            "DEMO": ("SEQN", "SDDSRVYR", "RIDSTATR", "RIDAGEYR", "RIAGENDR", "RIDRETH3",
                     "INDFMPIR", "DMDEDUC2", "SDMVSTRA", "SDMVPSU", details["mec_weight"]),
            "SMQ": ("SEQN", "SMQ020", "SMQ040", "SMD641"),
            "SMQRTU": ("SEQN", "SMQ681", "SMQ851", "SMQ863", "SMDANY", "SMQ690A",
                       "SMQ690F", "SMQ846" if period == "L" else "SMQ690H"),
            "SMQFAM": ("SEQN", "SMD460", "SMD470"),
            "COT": ("SEQN", "LBXCOT", "LBDCOTLC"),
        }
        for (component, required), count in zip(columns.items(), counts[period]):
            name = f"P_{component}" if period == "P" else f"{component}_{period}"
            sources.append(Source(name, period, component, count, required))
    sources.extend([
        Source("HEPA_L", "L", "WEIGHT", 8611, ("SEQN", "WTPH2YR")),
        Source("HEPB_S_L", "L", "WEIGHT_CHECK", 8611, ("SEQN", "WTPH2YR")),
    ])
    return tuple(sources)


SOURCES = _make_sources()
SOURCE_BY_NAME = {source.name: source for source in SOURCES}


class ResearchDataError(ValueError):
    """A source or harmonization invariant failed; estimates must not be generated."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def validate_source(source: Source, frame: pd.DataFrame, *, check_count: bool = True) -> None:
    """Validate published schemas/codes; do not silently clean unexpected source values."""
    missing = set(source.columns) - set(frame.columns)
    if frame.columns.duplicated().any() or missing:
        raise ResearchDataError(f"{source.name}: duplicate/missing columns: {sorted(missing)}.")
    if frame.empty or (check_count and len(frame) != source.expected_rows):
        raise ResearchDataError(f"{source.name}: record count {len(frame)} differs from documented "
                                f"{source.expected_rows}; review the source revision.")
    for column in source.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            raise ResearchDataError(f"{source.name}.{column}: numeric source field required.")
        if not np.isfinite(frame[column].dropna().to_numpy()).all():
            raise ResearchDataError(f"{source.name}.{column}: infinite value.")
    seqn = frame["SEQN"]
    if seqn.isna().any() or seqn.duplicated().any() or (seqn <= 0).any() or (seqn % 1 != 0).any():
        raise ResearchDataError(f"{source.name}: SEQN must be nonmissing, unique positive integers.")

    def codes(column: str, allowed: list[int]) -> None:
        if not frame[column].dropna().isin(allowed).all():
            raise ResearchDataError(f"{source.name}.{column}: unexpected code.")

    if source.component == "DEMO":
        if not frame["SDDSRVYR"].eq(PERIODS[source.period]["cycle"]).all():
            raise ResearchDataError(f"{source.name}: wrong or missing release-cycle identifier.")
        age = frame["RIDAGEYR"]
        if age.isna().any() or not age.between(0, 80).all() or (age % 1 != 0).any():
            raise ResearchDataError(f"{source.name}: invalid age/top-code.")
        codes("RIDSTATR", [1, 2])
        codes("RIAGENDR", [1, 2])
        codes("RIDRETH3", [1, 2, 3, 4, 6, 7])
        codes("DMDEDUC2", [1, 2, 3, 4, 5, 7, 9])
        if not frame["INDFMPIR"].dropna().between(0, 5).all():
            raise ResearchDataError(f"{source.name}: income ratio outside public-use 0-5.")
        for column in ("SDMVSTRA", "SDMVPSU"):
            values = frame[column]
            if values.isna().any() or (values <= 0).any() or (values % 1 != 0).any():
                raise ResearchDataError(f"{source.name}.{column}: missing/invalid survey design.")
        codes("SDMVPSU", [1, 2, 3] if source.period == "P" else [1, 2])
    elif source.component == "SMQ":
        codes("SMQ020", [1, 2, 7, 9])
        codes("SMQ040", [1, 2, 3, 7, 9])
        codes("SMD641", [*range(31), 77, 99])
    elif source.component == "SMQRTU":
        for column in ("SMQ681", "SMQ851", "SMQ863", "SMDANY"):
            codes(column, [1, 2, 7, 9])
        codes("SMQ690A", [1, 77, 99])
        codes("SMQ690F", [6, 77, 99])
        if source.period == "L":
            codes("SMQ846", [1, 2, 7, 9])
        else:
            codes("SMQ690H", [8, 77, 99])
    elif source.component == "SMQFAM":
        for column in ("SMD460", "SMD470"):
            codes(column, [0, 1, 2, 777, 999] + ([3] if source.period == "I" else []))
    elif source.component == "COT":
        cot, flag = frame["LBXCOT"], frame["LBDCOTLC"]
        codes("LBDCOTLC", [0, 1, 2] if source.period == "I" else [0, 1])
        if cot.isna().ne(flag.isna()).any() or (cot.dropna() < 0).any():
            raise ResearchDataError(f"{source.name}: invalid cotinine/flag pair.")
        lod = PERIODS[source.period]["lod"]
        if (cot[flag.isin([0, 2])] < lod).any():
            raise ResearchDataError(f"{source.name}: at/above-LOD flag conflicts with result.")
        if not np.isclose(cot[flag.eq(1)], lod / math.sqrt(2), atol=.0005, rtol=0).all():
            raise ResearchDataError(f"{source.name}: invalid rounded below-LOD fill value.")
    for column in ("WTMEC2YR", "WTMECPRP", "WTPH2YR"):
        if column in frame and (frame[column].isna().any() or (frame[column] < 0).any()):
            raise ResearchDataError(f"{source.name}.{column}: missing/negative source weight.")


def parse_source(source: Source, payload: bytes) -> pd.DataFrame:
    if not payload.startswith(XPT_SIGNATURE) or len(payload) < 240 or len(payload) % 80:
        raise ResearchDataError(f"{source.name}: invalid/truncated XPORT payload, possibly HTML.")
    try:
        frame = pd.read_sas(io.BytesIO(payload), format="xport", encoding="utf-8")
    except (ValueError, OSError, IndexError, UnicodeError, struct.error) as exc:
        raise ResearchDataError(f"{source.name}: XPORT parsing failed: {exc}") from exc
    normalized = {}
    for column in frame.select_dtypes(include="number").columns.intersection(source.columns):
        mask = frame[column].abs().eq(XPORT_ZERO_ARTIFACT)
        if mask.any():
            normalized[column] = int(mask.sum())
            frame.loc[mask, column] = 0.
    validate_source(source, frame)
    selected = frame[list(source.columns)].copy()
    selected.attrs["zero_artifacts_normalized"] = normalized
    return selected


def load_source(source: Source, cache_dir: Path | str, *, offline: bool = False) -> tuple[pd.DataFrame, dict]:
    """Load only an allowlisted original source; a corrupt cache fails without replacement."""
    registered = SOURCE_BY_NAME.get(source.name)
    if registered is None or source != registered:
        raise ResearchDataError("Only registered official research sources are downloadable.")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    data_path = cache / f"{source.name}.xpt"
    meta_path = cache / f"{source.name}.xpt.json"
    cached = data_path.exists()
    if offline and not cached:
        raise ResearchDataError(f"{source.name}: missing cached source in offline mode; run online once.")
    if cached:
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            payload = data_path.read_bytes()
        except (OSError, ValueError) as exc:
            raise ResearchDataError(f"{source.name}: cache metadata unreadable; re-download.") from exc
        if (not isinstance(metadata, dict) or metadata.get("name") != source.name
                or metadata.get("source_url") != source.url or metadata.get("period") != source.period
                or metadata.get("sha256") != _digest(payload)
                or metadata.get("bytes") != len(payload)):
            raise ResearchDataError(f"{source.name}: cache provenance/checksum mismatch.")
        try:
            stamp = datetime.fromisoformat(metadata["retrieved_at_utc"])
            if stamp.tzinfo is None:
                raise ValueError("timezone missing")
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchDataError(f"{source.name}: invalid original retrieval timestamp.") from exc
        frame = parse_source(source, payload)
    else:
        try:
            request = Request(source.url, headers={"User-Agent": "TobaccoExposureEquityStudy/0.2"})
            with urlopen(request, timeout=60) as response:
                payload = response.read(MAX_BYTES + 1)
        except (URLError, OSError) as exc:
            raise ResearchDataError(f"{source.name}: CDC download failed: {exc}") from exc
        if len(payload) > MAX_BYTES:
            raise ResearchDataError(f"{source.name}: source exceeds download size limit.")
        frame = parse_source(source, payload)
        metadata = {
            "name": source.name, "period": source.period, "source_url": source.url,
            "codebook_url": source.codebook_url, "sha256": _digest(payload), "bytes": len(payload),
            "retrieved_at_utc": _now(),
        }
        _atomic_write(data_path, payload)
        _atomic_write(meta_path, _json_bytes(metadata))
    return frame, {
        **metadata, "period_label": PERIODS[source.period]["label"],
        "component": source.component, "codebook_url": source.codebook_url,
        "records": len(frame), "documented_records": source.expected_rows,
        "selected_columns": list(source.columns), "verified_at_utc": _now(), "cached": cached,
        "zero_artifacts_normalized": frame.attrs.get("zero_artifacts_normalized", {}),
    }


def _noncurrent(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    lifetime, current = frame["SMQ020"], frame["SMQ040"]
    result = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    result.loc[lifetime.eq(2) & current.isna()] = 1
    result.loc[lifetime.eq(1) & current.eq(3)] = 1
    result.loc[lifetime.eq(1) & current.isin([1, 2])] = 0
    contradictory = ~lifetime.eq(1) & current.notna()
    result.loc[contradictory] = pd.NA
    return result, contradictory


def _recent_nonuse(frame: pd.DataFrame, period: str) -> tuple[pd.Series, pd.Series]:
    broad = frame[["SMQ681", "SMQ851", "SMQ863"]]
    yes = broad.eq(1).any(axis=1)
    all_no = broad.eq(2).all(axis=1)
    detail_yes = frame["SMQ690A"].eq(1) | frame["SMQ690F"].eq(6)
    detail_conflict = ((frame["SMQ681"].eq(2) & frame["SMQ690A"].notna())
                       | (frame["SMQ863"].eq(2) & frame["SMQ690F"].notna()))
    if period == "L":
        yes = yes | frame["SMQ846"].eq(1)
        all_no = all_no & frame["SMQ846"].eq(2)
    else:
        yes = yes | frame["SMQ690H"].eq(8)
        # A skipped multi-select item is not itself an observed 'no'. Broad screens
        # supply nonuse evidence; an explicit H positive always overrides them.
        all_no = all_no & frame["SMQ690H"].isna()
        detail_conflict = detail_conflict | (frame["SMQ681"].eq(2)
                                              & frame["SMQ690H"].notna())
    result = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    result.loc[all_no & ~detail_conflict] = 1
    result.loc[yes | detail_yes] = 0
    return result, detail_conflict


def _household(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    resident, inside = frame["SMD460"], frame["SMD470"]
    household = resident.map({0: "no", 1: "yes", 2: "yes", 3: "yes"}).fillna("unknown")
    indoor = inside.map({0: "no", 1: "yes", 2: "yes", 3: "yes"}).fillna("unknown")
    skipped_zero = resident.eq(0) & inside.isna()
    indoor.loc[skipped_zero] = "no"
    # Topcodes differ by period; comparison remains valid only for definite count conflicts.
    contradiction = ((resident.eq(0) & inside.notna() & ~inside.eq(0))
                     | (resident.isin([1, 2, 3]) & inside.isin([1, 2, 3]) & inside.gt(resident)))
    household.loc[contradiction] = "unknown"
    indoor.loc[contradiction] = "unknown"
    return household, indoor, contradiction


def harmonize_period(period: str, frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Left-join original files and retain the entire demographic sample for one period."""
    if period not in PERIODS:
        raise ResearchDataError(f"Unknown period {period}.")
    expected = [source for source in SOURCES if source.period == period]
    if set(frames) != {source.name for source in expected}:
        raise ResearchDataError(f"{period}: missing/extra or mixed-period source files.")
    for source in expected:
        validate_source(source, frames[source.name], check_count=False)
    by_component = {source.component: source for source in expected}
    demo = frames[by_component["DEMO"].name].copy()
    joins = []
    merged = demo
    for component in ("SMQ", "SMQRTU", "SMQFAM", "COT", "WEIGHT"):
        if component not in by_component:
            continue
        source = by_component[component]
        other = frames[source.name]
        if not other["SEQN"].isin(demo["SEQN"]).all():
            raise ResearchDataError(f"{source.name}: foreign SEQN outside same-period DEMO.")
        merged = merged.merge(other, on="SEQN", how="left", validate="one_to_one",
                              indicator=f"_{component.lower()}_join")
        joins.append({"source": source.name, "source_records": len(other), "foreign_keys": 0,
                      "demographic_rows_retained": len(merged) == len(demo)})
    weight_check = None
    if period == "L":
        reference = frames[by_component["WEIGHT"].name]
        independent = frames[by_component["WEIGHT_CHECK"].name]
        weights = reference.merge(independent, on="SEQN", how="outer", validate="one_to_one",
                                  suffixes=("_a", "_b"), indicator=True)
        if (not weights["_merge"].eq("both").all()
                or not weights["WTPH2YR_a"].eq(weights["WTPH2YR_b"]).all()):
            raise ResearchDataError("L: HEPA_L and HEPB_S_L weight keys/values disagree.")
        cot = frames[by_component["COT"].name]
        coverage = cot.merge(reference, on="SEQN", how="left", validate="one_to_one")
        if coverage["WTPH2YR"].isna().any():
            raise ResearchDataError("L: HEPA_L does not cover every COT_L source key.")
        if (coverage["LBXCOT"].notna() & ~coverage["WTPH2YR"].gt(0)).any():
            raise ResearchDataError("L: available cotinine result lacks a positive phlebotomy weight.")
        weight_check = {"weight_source": "HEPA_L", "independent_check_source": "HEPB_S_L",
                        "matched_weight_keys": len(weights), "all_weights_identical": True,
                        "cotinine_source_keys": len(cot), "cotinine_keys_without_weight": 0,
                        "available_cotinine_without_positive_weight": 0}
    noncurrent, smoking_conflict = _noncurrent(merged)
    recent, recent_conflict = _recent_nonuse(merged, period)
    household, indoor, household_conflict = _household(merged)
    ratio = merged["INDFMPIR"]
    poverty = pd.Series("unknown", index=merged.index)
    for mask, group in ((ratio.lt(1), "lt1"), (ratio.ge(1) & ratio.lt(2), "1to2"),
                        (ratio.ge(2) & ratio.lt(4), "2to4"), (ratio.ge(4), "ge4")):
        poverty.loc[mask] = group
    mec_weight = PERIODS[period]["mec_weight"]
    canonical = pd.DataFrame({
        "period": period, "period_label": PERIODS[period]["label"],
        "SEQN": merged["SEQN"].astype("int64"),
        "stratum": merged["SDMVSTRA"].astype("int64"),
        "psu": merged["SDMVPSU"].astype("int64"),
        "weight": merged["WTPH2YR"] if period == "L" else merged[mec_weight],
        "mec_weight": merged[mec_weight], "age": merged["RIDAGEYR"],
        "sex": merged["RIAGENDR"].map({1: "male", 2: "female"}).fillna("unknown"),
        "race_group": merged["RIDRETH3"].map({1: "hispanic", 2: "hispanic", 3: "nh_white",
                          4: "nh_black", 6: "nh_asian", 7: "other"}).fillna("unknown"),
        "income_ratio": ratio, "poverty_group": poverty,
        "education": merged["DMDEDUC2"].map({1: "lt_hs", 2: "lt_hs", 3: "hs",
                                               4: "some_college", 5: "college"}).fillna("unknown"),
        "indoor_smoking": indoor, "household_smoker": household,
        "noncurrent": noncurrent, "no_recent_all": recent,
        "cotinine": merged["LBXCOT"],
        "below_lod": merged["LBDCOTLC"].map({0: 0, 1: 1, 2: 0}).astype("Int64"),
        "lod": PERIODS[period]["lod"],
    })
    for column in ("RIDSTATR", "RIAGENDR", "RIDRETH3", "DMDEDUC2", "SMQ020", "SMQ040",
                   "SMD641", "SMQ681", "SMQ851", "SMQ863", "SMDANY", "SMQ690A", "SMQ690F",
                   "SMQ690H", "SMQ846", "SMD460", "SMD470", "LBDCOTLC"):
        canonical[column] = merged[column] if column in merged else np.nan
    for component in ("SMQ", "SMQRTU", "SMQFAM", "COT"):
        canonical[f"has_{component.lower()}_row"] = merged[f"_{component.lower()}_join"].eq("both").astype(int)
    canonical["household_conflict"] = household_conflict.astype(int)
    canonical["smoking_skip_conflict"] = smoking_conflict.astype(int)
    canonical["recent_detail_conflict"] = recent_conflict.astype(int)
    canonical["household_indoor_structural_skip"] = (
        merged["SMD460"].eq(0) & merged["SMD470"].isna()).astype(int)
    missing_weight = canonical.weight.isna()
    missing_non_mec = missing_weight & ~canonical.mec_weight.gt(0)
    missing_young = missing_weight & canonical.mec_weight.gt(0) & canonical.age.lt(2)
    unexplained_missing_weight = missing_weight & ~missing_non_mec & ~missing_young
    if period == "L" and unexplained_missing_weight.any():
        raise ResearchDataError("L: examined participant aged2+ has no linked phlebotomy weight.")
    if weight_check is not None:
        weight_check.update({
            "full_demographic_weight_missing": int(missing_weight.sum()),
            "weight_missing_not_mec_examined": int(missing_non_mec.sum()),
            "weight_missing_examined_age_under2": int(missing_young.sum()),
            "weight_missing_unexplained": int(unexplained_missing_weight.sum()),
            "outside_weight_population_handling": "Retain NA; never replace with MEC weights or zero.",
        })
    age25 = canonical["age"].ge(25)
    quality = {
        "period": period, "demographic_rows": len(demo), "analytic_export_rows": len(canonical),
        "all_demographic_rows_retained": len(canonical) == len(demo), "joins": joins,
        "household_count_conflicts": int(household_conflict.sum()),
        "smoking_skip_conflicts": int(smoking_conflict.sum()),
        "recent_detail_conflicts": int(recent_conflict.sum()),
        "household_structural_skips_mapped_to_no": int(canonical.household_indoor_structural_skip.sum()),
        "age25_unknown_income": int((age25 & poverty.eq("unknown")).sum()),
        "age25_unknown_education": int((age25 & canonical.education.eq("unknown")).sum()),
        "age25_unknown_indoor_smoking": int((age25 & indoor.eq("unknown")).sum()),
        "age25_unknown_noncurrent": int((age25 & noncurrent.isna()).sum()),
        "age25_unknown_recent_nonuse": int((age25 & recent.isna()).sum()),
        "age25_smoking_skip_conflicts": int((age25 & smoking_conflict).sum()),
        "age25_household_count_conflicts": int((age25 & household_conflict).sum()),
        "age25_recent_detail_conflicts": int((age25 & recent_conflict).sum()),
        "recent_summary_disagreements": int((
            (recent.eq(1) & merged["SMDANY"].eq(1))
            | (recent.eq(0) & merged["SMDANY"].eq(2))).fillna(False).sum()),
        "analysis_weight_missing": int(missing_weight.sum()),
        "analysis_weight_missing_outside_mec": int(missing_non_mec.sum()),
        "analysis_weight_missing_examined_age_under2": int(missing_young.sum()),
        "analysis_weight_missing_unexplained": int(unexplained_missing_weight.sum()),
        "analysis_weight_zero": int(canonical.weight.eq(0).sum()),
        "age25_positive_detail_override_broad_no": int((
            age25 & merged[["SMQ681", "SMQ851", "SMQ863"]].eq(2).all(axis=1)
            & (merged["SMQ690A"].eq(1) | merged["SMQ690F"].eq(6)
               | (merged["SMQ690H"].eq(8) if period != "L" else merged["SMQ846"].eq(1)))
        ).sum()),
        "weight_linkage": weight_check,
    }
    return canonical, quality


def sample_flow(analytic: pd.DataFrame) -> pd.DataFrame:
    """Unweighted prespecified exclusion accounting; no endpoint prevalence comparisons."""
    rows = []
    for period, frame in analytic.groupby("period", sort=False):
        mask = pd.Series(True, index=frame.index)
        previous = len(frame)
        stages = [
            ("all_demographic_records", mask.copy(), "Full export; no domain filtering"),
            ("positive_analysis_weight", frame.weight.gt(0), "Blood weight in L; MEC in I/P"),
            ("age25plus", frame.age.ge(25), "Primary adult age restriction"),
            ("noncurrent_cigarette", frame.noncurrent.eq(1), "Unknown not treated as noncurrent"),
            ("no_recent_all_products", frame.no_recent_all.eq(1), "Explicit five-day nonuse"),
            ("cotinine_observed", frame.cotinine.notna(), "No missing assay substitution"),
            ("cotinine_at_most10", frame.cotinine.le(10), "Prespecified biomarker cohort cap"),
            ("income_observed", frame.poverty_group.ne("unknown"), "Poverty contrasts available"),
            ("education_observed", frame.education.ne("unknown"), "Descriptive complete cases"),
            ("indoor_smoking_observed", frame.indoor_smoking.ne("unknown"), "Full covariate cases"),
        ]
        for stage, criterion, note in stages:
            mask = mask & criterion.fillna(False)
            n = int(mask.sum())
            rows.append({"period": period, "period_label": PERIODS[period]["label"],
                         "stage": stage, "n": n, "excluded_from_previous": previous - n,
                         "note": note})
            previous = n
    return pd.DataFrame(rows)


def harmonization_table() -> pd.DataFrame:
    definitions = {
        "SEQN": ("SEQN", "Unchanged original public-use key; same-period one-to-one joins"),
        "stratum": ("SDMVSTRA", "Full-design masked variance stratum, not a participant attribute"),
        "psu": ("SDMVPSU", "Masked PSU nested in stratum"),
        "age": ("RIDAGEYR", "Screening age; top-coded at 80"),
        "sex": ("RIAGENDR", "1 male; 2 female; missing unknown; recorded sex variable"),
        "race_group": ("RIDRETH3", "1/2 Hispanic; 3 NH white; 4 NH black; 6 NH Asian; 7 other"),
        "income_ratio": ("INDFMPIR", "Observed 0-5 ratio; 5 represents 5+; missing remains blank"),
        "poverty_group": ("INDFMPIR", "<1 lt1; [1,2) 1to2; [2,4) 2to4; >=4 ge4; missing unknown"),
        "education": ("DMDEDUC2", "1/2 lt_hs; 3 hs; 4 some_college; 5 college; 7/9/missing unknown; ages20+"),
        "household_smoker": ("SMD460/SMD470", "460=0 no; positive yes; unknown/refused/conflict unknown"),
        "indoor_smoking": ("SMD460/SMD470", "470=0 no; positive yes; 460=0 and structurally skipped470 no; conflicts unknown"),
        "noncurrent": ("SMQ020/SMQ040", "020=2 with skipped040 or 020=1 &040=3 ->1; 020=1 &040=1/2 ->0; others unknown"),
        "cotinine": ("LBXCOT", "Original serum ng/mL including CDC below-LOD fill; missing remains blank"),
        "below_lod": ("LBDCOTLC", "1 below; 0 above; I code2 above calibrated range maps0 with raw flag preserved"),
    }
    rows = []
    for period in PERIODS:
        definitions_for_period = dict(definitions)
        definitions_for_period["weight"] = (
            "HEPA_L.WTPH2YR + HEPB_S_L validation" if period == "L" else PERIODS[period]["mec_weight"],
            "Nonnegative original survey weight; L linked1:1 and independently verified; no substitution")
        definitions_for_period["mec_weight"] = (PERIODS[period]["mec_weight"], "Retained for laboratory-availability denominator")
        definitions_for_period["no_recent_all"] = (
            "SMQ681/SMQ851/SMQ863/" + ("SMQ846" if period == "L" else "SMQ690H"),
            "All broad screens explicitly2; L846 explicitly2; I/P H8 overrides broad no; positive detail evidence excludes; unknown preserved")
        definitions_for_period["lod"] = ("CDC laboratory codebook", str(PERIODS[period]["lod"]) + " ng/mL")
        for target, (source, rule) in definitions_for_period.items():
            rows.append({"period": period, "period_label": PERIODS[period]["label"],
                         "target": target, "source_fields": source, "derivation": rule})
    return pd.DataFrame(rows)


def prepare_research(cache_dir: Path | str = "data/research/raw",
                     work_dir: Path | str = "data/research",
                     output_dir: Path | str = "reports/research", *, offline: bool = False) -> dict:
    """Collect 17 real files and export all 37,464 DEMO rows for later survey estimation.

    Downloads require an explicit call. A verified raw cache supports offline repeats.
    This function writes source/quality/flow metadata, never comparative study outcomes.
    """
    cache_dir, work_dir, output_dir = map(Path, (cache_dir, work_dir, output_dir))
    with ThreadPoolExecutor(max_workers=4) as executor:
        loaded = list(executor.map(lambda source: load_source(source, cache_dir, offline=offline), SOURCES))
    frames = {source.name: frame for source, (frame, _) in zip(SOURCES, loaded)}
    sources = [provenance for _, provenance in loaded]
    canonical, diagnostics = [], []
    original_keys = set()
    for period in PERIODS:
        same_period = {source.name: frames[source.name] for source in SOURCES if source.period == period}
        prepared, quality = harmonize_period(period, same_period)
        keys = set(prepared.SEQN)
        if keys & original_keys:
            raise ResearchDataError("Overlapping respondent keys across periods; independent samples required.")
        original_keys.update(keys)
        canonical.append(prepared)
        diagnostics.append(quality)
    analytic = pd.concat(canonical, ignore_index=True)
    analytic_bytes = analytic.to_csv(index=False, lineterminator="\n").encode("utf-8")
    plan_path = Path(__file__).resolve().parents[1] / "docs/RESEARCH_PLAN_V2.md"
    quality = {
        "scope": "source integrity, harmonization and unweighted exclusion accounting only",
        "generated_at_utc": _now(), "source_count": len(sources),
        "analytic_rows": len(analytic), "periods": diagnostics,
        "no_demographic_rows_dropped": True, "outcome_comparisons_run": False,
        "known_source_discrepancies": [
            "COT_L documents WTPH2YR but its XPT omits it; linked the common public weight "
            "from HEPA_L and checked all keys/values against HEPB_S_L.",
            "L recent-use interviewing changed to self-administered ACASI; separate SMQ846 "
            "is mandatory. No SMQSHS_L is released, so household constructs alone are harmonized.",
        ],
    }
    manifest = {
        "study": "Tobacco Exposure Equity Study", "data_kind": "real_public_secondary_analysis",
        "generated_at_utc": quality["generated_at_utc"], "checksum_algorithm": "SHA-256",
        "frozen_plan_commit": PLAN_COMMIT,
        "frozen_plan_sha256": _digest(plan_path.read_bytes()) if plan_path.exists() else None,
        "analytic_csv_sha256": _digest(analytic_bytes), "analytic_rows": len(analytic),
        "analytic_columns": list(analytic.columns), "sources": sources,
        "weight_linkage": next(item["weight_linkage"] for item in diagnostics if item["period"] == "L"),
        "software": {"pandas": pd.__version__, "numpy": np.__version__},
        "original_measurements": "CDC/NHANES; collected independently here as public source files, "
                                 "not participant recruitment or new physical measurements",
    }
    paths = {
        "analytic_path": str((work_dir / "analytic.csv").resolve()),
        "manifest_path": str((output_dir / "source_manifest.json").resolve()),
        "flow_path": str((output_dir / "sample_flow.csv").resolve()),
        "quality_path": str((output_dir / "data_quality.json").resolve()),
        "harmonization_path": str((output_dir / "harmonization.csv").resolve()),
    }
    _atomic_write(Path(paths["analytic_path"]), analytic_bytes)
    _atomic_write(Path(paths["manifest_path"]), _json_bytes(manifest))
    _atomic_write(Path(paths["quality_path"]), _json_bytes(quality))
    _atomic_write(Path(paths["flow_path"]), sample_flow(analytic).to_csv(index=False).encode("utf-8"))
    _atomic_write(Path(paths["harmonization_path"]), harmonization_table().to_csv(index=False).encode("utf-8"))
    return {**paths, "row_count": len(analytic), "source_count": len(sources)}
