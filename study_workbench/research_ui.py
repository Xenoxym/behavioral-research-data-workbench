"""Artifact-driven interface for the real NHANES Tobacco Exposure Equity Study.

No raw-source downloads, model fitting, or synthetic data generation occur at startup.
"""

from __future__ import annotations

from base64 import b64encode
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "Study overview", "Questions & methods", "Weighted results",
    "Sensitivity & selection", "Sources & provenance", "Research report",
]
PERIODS = {"I": "2015–2016", "P": "2017–March 2020", "L": "August 2021–August 2023"}
COLORS = {"I": "#9ab6c4", "P": "#187e86", "L": "#bd6e45"}
GROUPS = {
    "overall": "Overall analytic domain",
    "poverty_group": "Income-to-poverty ratio",
    "education": "Educational attainment",
    "indoor_smoking": "Indoor household smoking",
}
LABELS = {
    "all": "All eligible adults", "lt1": "Below poverty (<1)", "1to2": "1 to <2",
    "2to4": "2 to <4", "ge4": "4 or higher", "unknown": "Unknown / not reported",
    "lt_hs": "Less than high school", "hs": "High school / GED",
    "some_college": "Some college / AA", "college": "College graduate or higher",
    "yes": "Indoor smoking reported", "no": "No indoor smoking reported",
}
GROUP_ORDER = ["all", "lt1", "1to2", "2to4", "ge4", "lt_hs", "hs", "some_college", "college", "no", "yes", "unknown"]
TABLES = ["estimates", "contrasts", "models", "sensitivities", "missingness", "sample_flow", "harmonization"]
JSON_FILES = ["analysis_metadata", "source_manifest", "data_quality"]
OPTIONAL_JSON_FILES = ["pipeline_run"]
CORE_COLUMNS = {
    "estimates": {"period", "group_variable", "group", "n", "events", "prevalence", "se", "ci_low", "ci_high", "df", "quality_flag"},
    "contrasts": {"period", "contrast", "estimate", "se", "ci_low", "ci_high", "df"},
    "models": {"period", "model", "term", "coefficient", "se", "odds_ratio", "ci_low", "ci_high", "p_value", "n", "events", "converged", "df"},
    "sensitivities": {"period", "scenario", "n", "events", "prevalence", "se", "ci_low", "ci_high", "df"},
    "missingness": {"period", "denominator", "group_variable", "group", "n", "missing_n", "missing_rate", "se", "ci_low", "ci_high", "df"},
}
CSS = """<style>
[data-testid="stAppViewContainer"]{background:#f4f7f9;color:#17384c}
[data-testid="stHeader"]{background:rgba(244,247,249,.96)}
[data-testid="stSidebar"]{background:#eaf0f3;border-right:1px solid #d5e0e7}
.block-container{max-width:1360px;padding-top:2.2rem;padding-bottom:3rem}
h1,h2,h3{color:#17384c;letter-spacing:-.025em}h1{font-size:2.3rem!important;font-weight:750!important}
h2{font-size:1.35rem!important}.brand{color:#17384c;font-size:1.25rem;font-weight:800;line-height:1.4}
.eyebrow{font-size:.7rem;letter-spacing:.15em;font-weight:800;color:#187e86;margin-bottom:8px}
.intro{color:#607686;line-height:1.65;max-width:950px;margin-bottom:20px}
.study-note{background:#e5f0f4;border:1px solid #c4dbe3;border-radius:9px;padding:11px 16px;font-size:.86rem;color:#27576b;margin-bottom:22px}
.research-card{background:white;border:1px solid #d9e4eb;border-radius:11px;padding:18px 20px;min-height:127px;margin-bottom:14px}
.metric-label{color:#627a8a;font-size:.72rem;text-transform:uppercase;font-weight:750;letter-spacing:.04em}
.metric-value{font-size:2rem;font-weight:780;color:#17384c;line-height:1.45}
.metric-note{font-size:.76rem;color:#6a8090}.footer{font-size:.74rem;color:#748b99;border-top:1px solid #d8e3e9;padding-top:14px;margin-top:30px}
[data-testid="stDataFrame"]{border-radius:9px;overflow:hidden}
</style>"""


def load_artifacts(directory: Path) -> dict:
    """Read saved aggregate artifacts; report missing or malformed files explicitly."""
    state = {"tables": {}, "json": {}, "errors": [], "directory": directory}
    for name in TABLES:
        path = directory / f"{name}.csv"
        if not path.exists():
            state["errors"].append(f"Missing {path.name}")
            continue
        try:
            frame = pd.read_csv(path, keep_default_na=True)
            missing = CORE_COLUMNS.get(name, set()) - set(frame.columns)
            if missing:
                raise ValueError(f"required columns absent: {', '.join(sorted(missing))}")
            state["tables"][name] = frame
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            state["errors"].append(f"Could not read {path.name}: {exc}")
    for name in JSON_FILES + OPTIONAL_JSON_FILES:
        path = directory / f"{name}.json"
        if not path.exists():
            if name in JSON_FILES:
                state["errors"].append(f"Missing {path.name}")
            continue
        try:
            state["json"][name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            state["errors"].append(f"Could not read {path.name}: {exc}")
    return state


def _heading(eyebrow: str, title: str, description: str) -> None:
    st.markdown(f'<div class="eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="intro">{escape(description)}</div>', unsafe_allow_html=True)


def _cards(items: list[tuple[str, str, str]]) -> None:
    for column, (label, value, note) in zip(st.columns(len(items)), items, strict=True):
        column.markdown(
            '<div class="research-card">'
            f'<div class="metric-label">{escape(label)}</div>'
            f'<div class="metric-value">{escape(value)}</div>'
            f'<div class="metric-note">{escape(note)}</div></div>', unsafe_allow_html=True,
        )


def _table(state: dict, name: str) -> pd.DataFrame:
    return state["tables"].get(name, pd.DataFrame())


def _download_table(frame: pd.DataFrame, name: str, label: str | None = None) -> None:
    st.download_button(
        label or f"Download {name.replace('_', ' ')} CSV", frame.to_csv(index=False).encode("utf-8-sig"),
        f"{name}.csv", "text/csv", key=f"download_{name}",
    )


def _archive(directory: Path) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name in TABLES + JSON_FILES + OPTIONAL_JSON_FILES:
            suffix = ".csv" if name in TABLES else ".json"
            path = directory / f"{name}{suffix}"
            if path.exists():
                archive.writestr(path.name, path.read_bytes())
    return target.getvalue()


def _periods(frame: pd.DataFrame, values: list[str]) -> pd.DataFrame:
    if "period" not in frame:
        return frame.copy()
    # A secondary I_to_L contrast belongs to both selected periods; retain it
    # when both are selected instead of silently hiding all cross-period results.
    selected = set(values)
    keep = frame["period"].astype(str).map(
        lambda value: all(part in selected for part in value.split("_to_"))
    )
    return frame.loc[keep].copy()


def _quality_note(frame: pd.DataFrame) -> None:
    if "quality_flag" not in frame:
        return
    flags = frame["quality_flag"].fillna("").astype(str)
    informational = "secondary_independent_periods_satterthwaite"
    flagged = ~flags.str.lower().isin(["", "ok", "none", "reliable", informational])
    if flagged.any():
        st.warning(f"{int(flagged.sum())} displayed result rows have quality flags. Read the flags and unweighted counts before interpreting estimates.")
    if flags.eq(informational).any():
        st.caption("Secondary cross-period contrasts use independent-period variance and Satterthwaite degrees of freedom; this method label is not an estimate-failure flag.")


def _prevalence_chart(
    frame: pd.DataFrame, *, category: str = "group", title: str = "Weighted exposure prevalence",
    y_title: str = "Weighted prevalence (%)", event_label: str = "events",
) -> None:
    if frame.empty:
        st.info("No saved estimates match this selection.")
        return
    plotted = frame.copy()
    for column in ["prevalence", "ci_low", "ci_high"]:
        plotted[column] = pd.to_numeric(plotted[column], errors="coerce")
    plotted = plotted.loc[plotted["prevalence"].notna()]
    if plotted.empty:
        st.info("Selected estimates are unavailable; inspect quality flags in the result table.")
        return
    if category == "group":
        plotted["_group_order"] = plotted[category].map(
            {value: index for index, value in enumerate(GROUP_ORDER)}
        ).fillna(len(GROUP_ORDER))
        plotted = plotted.sort_values("_group_order", kind="stable")
    fig = go.Figure()
    for period in [code for code in PERIODS if code in plotted["period"].astype(str).unique()]:
        part = plotted.loc[plotted["period"].astype(str).eq(period)]
        labels = part[category].astype(str).map(lambda value: LABELS.get(value, value.replace("_", " ")))
        fig.add_trace(go.Scatter(
            x=labels, y=part["prevalence"] * 100, mode="markers+lines",
            name=PERIODS[period], marker=dict(size=10, color=COLORS[period]),
            line=dict(color=COLORS[period], width=2),
            error_y=dict(type="data", symmetric=False,
                         array=(part["ci_high"] - part["prevalence"]).clip(lower=0) * 100,
                         arrayminus=(part["prevalence"] - part["ci_low"]).clip(lower=0) * 100),
            customdata=part[["n", "events"]].to_numpy(),
            hovertemplate="%{x}<br>Weighted estimate %{y:.1f}%<br>n=%{customdata[0]}, " + event_label + "=%{customdata[1]}<extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=17)), template="plotly_white", height=425,
        margin=dict(l=0, r=0, t=55, b=10), yaxis_title=y_title, xaxis_title=None,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#17384c"), legend=dict(orientation="h", y=-.22),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Markers show weighted estimates; bars show 95% confidence intervals. Samples are separate repeated cross-sections.")


def _unavailable(state: dict) -> None:
    st.info("Saved research outputs are not ready. This interface never substitutes demonstration data.")
    st.code("python -m study_workbench.cli research", language="bash")
    st.caption("Run the explicit research pipeline to collect official source files and fit the prespecified survey analyses. Opening this app does not download files or fit models.")
    with st.expander("Artifact readiness details"):
        for error in state["errors"]:
            st.write(error)


def _overview(state: dict) -> None:
    _heading("PUBLIC HEALTH / SECONDARY RESEARCH", "Tobacco exposure and the income gradient",
             "A harmonized NHANES study of biomarker-defined recent exposure among adults reporting no current cigarette use and no recent nicotine-product use.")
    estimates = _table(state, "estimates")
    if estimates.empty:
        _unavailable(state)
        return
    overall = estimates.loc[estimates["group_variable"].eq("overall")]
    n = int(pd.to_numeric(overall["n"], errors="coerce").fillna(0).sum())
    _cards([
        ("Non-overlapping survey periods", str(estimates["period"].nunique()), "2015–16 / 2017–Mar 2020 / 2021–23"),
        ("Primary analytic observations", f"{n:,}", "Unweighted records across independent periods"),
        ("Primary exposure threshold", "0.05 ng/mL", "Serum cotinine range: 0.05 to 10 ng/mL"),
    ])
    income = estimates.loc[estimates["group_variable"].eq("poverty_group") & estimates["group"].isin(["lt1", "1to2", "2to4", "ge4"])]
    _prevalence_chart(income, title="Prespecified income groups, with design-based uncertainty")
    contrasts = _table(state, "contrasts")
    if not contrasts.empty:
        primary = contrasts.loc[contrasts["contrast"].eq("poverty_lt1_minus_ge4")]
        st.subheader("Primary contrast: below poverty minus income ratio ≥4")
        st.caption("Absolute prevalence difference. Positive values indicate a larger estimated exposure prevalence in the below-poverty group. Confidence intervals and quality flags are retained.")
        display = primary.copy()
        for field in ["estimate", "ci_low", "ci_high"]:
            display[f"{field}_percentage_points"] = pd.to_numeric(display[field], errors="coerce") * 100
        st.dataframe(display, hide_index=True, width="stretch")
        _quality_note(primary)
    st.info("Independent public-source collection and secondary analysis. CDC/NHANES collected the original interviews and specimens. These data cannot establish individual follow-up, treatment effects, or causal pandemic effects.")


def _methods(state: dict) -> None:
    _heading("FROZEN QUESTIONS / ANALYSIS DECISIONS", "Define the study before interpreting it",
             "A documented replication and extension with a measurement and selection sensitivity audit. The income gradient is an existing research question, not a claimed new discovery.")
    st.subheader("Three prespecified questions")
    st.markdown("1. How large is the income gradient in the exposure indicator in each independent survey period?\n2. How are indoor household smoking and education associated with exposure, and how do income associations change with household adjustment?\n3. How much do age, product-use screening, biomarker thresholds, and missingness change the results?")
    st.subheader("Primary analytic domain")
    st.write("Age 25 or older; noncurrent cigarette responses; explicit exclusion of recent smoking, smokeless tobacco, nicotine-replacement, and e-cigarette use under the harmonized rules; observed serum cotinine ≤10 ng/mL. Exposure is 0.05–10 ng/mL. Biomarkers cannot identify the nicotine source or establish individual honesty.")
    st.dataframe(pd.DataFrame([
        {"Period": PERIODS["I"], "Analysis weight": "WTMEC2YR", "Assay LLOD": "0.015 ng/mL"},
        {"Period": PERIODS["P"], "Analysis weight": "WTMECPRP", "Assay LLOD": "0.015 ng/mL"},
        {"Period": PERIODS["L"], "Analysis weight": "WTPH2YR", "Assay LLOD": "0.010 ng/mL"},
    ]), hide_index=True, width="stretch")
    st.write("Survey inference constructs the full positive-weight design before domain subsetting, retains strata/PSU structure, and estimates each period separately. Primary prevalence intervals use survey logit intervals; contrasts use joint design covariance. Sparse or unstable estimates retain warnings.")
    st.subheader("Adjustment and sample comparability")
    st.write("M1_all uses income/demographic-complete observations. M1_common uses the exact household-complete sample used by M2; only M1_common versus M2 supports coefficient-change discussion. Household adjustment is an association comparison, not causal mediation.")
    st.warning("The 2021–23 recent-use interview mode changed to ACASI, phlebotomy weighting differs, and assay detection limits changed. These differences limit attribution of period contrasts.")
    flow = _table(state, "sample_flow")
    if not flow.empty:
        st.subheader("Reconciled sample flow")
        st.dataframe(flow, hide_index=True, width="stretch")
        _download_table(flow, "sample_flow")
    plan = ROOT / "docs" / "RESEARCH_PLAN_V2.md"
    if plan.exists():
        st.download_button("Download frozen analysis plan", plan.read_bytes(), "RESEARCH_PLAN_V2.md", "text/markdown")
        with st.expander("Full frozen plan and recorded deviations"):
            st.markdown(plan.read_text(encoding="utf-8"))


def _weighted(state: dict) -> None:
    _heading("DESIGN-BASED ESTIMATES", "Explore the weighted results and uncertainty",
             "Keep effect size, confidence interval, unweighted sample size, design degrees of freedom, and estimate-quality flags together.")
    estimates = _table(state, "estimates")
    if estimates.empty:
        _unavailable(state)
        return
    selected = st.multiselect("Survey periods", list(PERIODS), default=list(PERIODS), format_func=PERIODS.get)
    grouping = st.selectbox("Compare by", list(GROUPS), index=1, format_func=GROUPS.get)
    filtered = _periods(estimates.loc[estimates["group_variable"].eq(grouping)], selected)
    options = filtered["group"].astype(str).drop_duplicates().tolist()
    groups = st.multiselect("Subgroups", options, default=options, format_func=lambda key: LABELS.get(key, key))
    filtered = filtered.loc[filtered["group"].astype(str).isin(groups)]
    _prevalence_chart(filtered)
    _quality_note(filtered)
    st.dataframe(filtered, hide_index=True, width="stretch")
    _download_table(filtered, "filtered_estimates", "Download selected weighted estimates")
    tabs = st.tabs(["Prespecified contrasts", "Adjusted associations"])
    with tabs[0]:
        contrasts = _periods(_table(state, "contrasts"), selected)
        if contrasts.empty:
            st.info("No saved contrasts for this selection.")
        else:
            st.dataframe(contrasts, hide_index=True, width="stretch")
            _quality_note(contrasts)
            _download_table(contrasts, "contrasts")
            st.caption("Primary: poverty_lt1_minus_ge4. Cross-period gap differences are secondary and use independent-period variances. Values are proportions; multiply by 100 for percentage points.")
    with tabs[1]:
        models = _periods(_table(state, "models"), selected)
        if models.empty:
            st.info("Adjusted model results have not been generated.")
        else:
            model = st.selectbox("Model sample and adjustment", models["model"].drop_duplicates().tolist())
            displayed = models.loc[models["model"].eq(model)]
            periods = state["json"].get("analysis_metadata", {}).get("periods", {})
            diagnostics = []
            for period in selected:
                details = periods.get(period, {}).get("model_diagnostics", {}).get(model)
                if details:
                    diagnostics.append({"period": period, "model": model, **details})
            if diagnostics:
                st.subheader("Model sample and fit audit")
                st.dataframe(pd.DataFrame(diagnostics), hide_index=True, width="stretch")
            st.dataframe(displayed, hide_index=True, width="stretch")
            _quality_note(displayed)
            _download_table(displayed, "selected_model", "Download selected model results")
            st.caption("Survey quasibinomial logistic associations. Odds ratios are not risk ratios. M1_common and M2 share the same observations; M1_all can have a different sample. Read convergence, sample loss, and quality flags before interpretation.")


def _sensitivity(state: dict) -> None:
    _heading("MEASUREMENT / SELECTION AUDIT", "Check what changes when the definition changes",
             "Prespecified alternatives expose dependence on screening, thresholds, sample restrictions, and missing measurements. No optimal cutoff or favorable result is selected.")
    sensitivities = _table(state, "sensitivities")
    if sensitivities.empty:
        _unavailable(state)
        return
    selected = st.multiselect("Sensitivity periods", list(PERIODS), default=list(PERIODS), format_func=PERIODS.get)
    scenarios = sensitivities["scenario"].drop_duplicates().tolist()
    scenario = st.selectbox("Prespecified scenario", scenarios)
    filtered = _periods(sensitivities.loc[sensitivities["scenario"].eq(scenario)], selected)
    if "description" in filtered and filtered["description"].notna().any():
        st.info(str(filtered["description"].dropna().iloc[0]))
    st.dataframe(filtered, hide_index=True, width="stretch")
    _quality_note(filtered)
    _download_table(_periods(sensitivities, selected), "sensitivities")
    with st.expander("Compare all prespecified sensitivity estimates"):
        all_scenarios = _periods(sensitivities, selected)
        st.dataframe(all_scenarios, hide_index=True, width="stretch")
        _quality_note(all_scenarios)
    st.subheader("Laboratory availability and income")
    missingness = _table(state, "missingness")
    if missingness.empty:
        st.info("The laboratory-missingness audit is not available yet.")
    else:
        denominators = missingness["denominator"].drop_duplicates().tolist()
        denominator = st.selectbox("Missingness denominator", denominators)
        audit = _periods(missingness.loc[missingness["denominator"].eq(denominator)], selected)
        by_income = audit.loc[audit["group_variable"].eq("poverty_group")].rename(
            columns={"missing_rate": "prevalence", "missing_n": "events"}
        )
        _prevalence_chart(by_income, title="Weighted laboratory missingness by income",
                          y_title="Weighted missingness (%)", event_label="missing assays")
        st.dataframe(audit, hide_index=True, width="stretch")
        _quality_note(audit)
        _download_table(audit, "missingness")
    st.warning("A missing assay is never set to zero. Full-MEC availability uses MEC weights; the 2021–23 blood-outcome design uses phlebotomy weights, which already adjust blood nonresponse. An unknown category is not imputation or a bias correction.")


def _sources(state: dict) -> None:
    _heading("REPRODUCIBLE PUBLIC-SOURCE RESEARCH", "Trace every result back to its source",
             "Official-source provenance, same-period joins, harmonized meanings, and recorded software/method decisions support independent verification.")
    harmonization = _table(state, "harmonization")
    if not harmonization.empty:
        st.subheader("Variable harmonization")
        st.dataframe(harmonization, hide_index=True, width="stretch")
        _download_table(harmonization, "harmonization")
    for name, title in [("data_quality", "Source and analytic data quality"), ("source_manifest", "Source URLs, retrieval times, and checksums"), ("analysis_metadata", "Survey engine, formulas, warnings, and versions"), ("pipeline_run", "Pipeline completion and code/output checksums")]:
        value = state["json"].get(name)
        with st.expander(title, expanded=name == "data_quality"):
            if value is None:
                st.info(f"{name}.json has not been generated.")
            else:
                st.json(value)
                st.download_button(f"Download {name.replace('_', ' ')}", json.dumps(value, indent=2).encode("utf-8"), f"{name}.json", "application/json", key=f"download_{name}")
    st.subheader("Aggregate evidence package")
    if state["tables"] or state["json"]:
        st.download_button("Download research evidence ZIP", _archive(state["directory"]), "research_evidence.zip", "application/zip")
        st.caption("Aggregate result tables and provenance only. Raw XPT files and participant-level analytic data are excluded.")
    else:
        _unavailable(state)


def _report(state: dict, report_path: Path) -> None:
    _heading("RESEARCH COMMUNICATION", "Read the findings with their limitations",
             "The manuscript-style report connects prespecified questions, harmonized data, uncertainty, sensitivity results, and interpretation limits.")
    if not report_path.exists():
        st.info("The final research report has not been generated yet. Saved result tables remain available in the other sections.")
        return
    report = report_path.read_bytes()
    st.download_button("Download research report HTML", report, "RESEARCH_REPORT.html", "text/html", type="primary")
    st.caption("A standalone document with its source links and figures. Original measurements were collected by CDC/NHANES.")
    data_url = "data:text/html;base64," + b64encode(report).decode("ascii")
    st.iframe(data_url, height=1100, alt="Tobacco Exposure Equity Study research report")


def main() -> None:
    """Show saved real-data research by default; legacy demo is a separate entrypoint."""
    st.set_page_config(page_title="Tobacco Exposure Equity Study", page_icon="◉", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    directory = Path(os.environ.get("WORKBENCH_RESEARCH_DIR", str(ROOT / "reports" / "research")))
    report_path = Path(os.environ.get("WORKBENCH_RESEARCH_REPORT", str(ROOT / "reports" / "RESEARCH_REPORT.html")))
    state = load_artifacts(directory)
    with st.sidebar:
        st.markdown('<div class="eyebrow">REAL PUBLIC DATA / NHANES</div><div class="brand">Tobacco Exposure<br>Equity Study</div>', unsafe_allow_html=True)
        st.caption("Independent secondary research across three non-overlapping U.S. survey periods.")
        st.divider()
        page = st.radio("Research workspace", PAGES, key="research_page")
        st.divider()
        st.caption("2015–2016\n\n2017–March 2020\n\nAugust 2021–August 2023")
        st.caption("Design-based estimates · Explicit uncertainty · Selection audit")
        if state["errors"]:
            st.warning(f"{len(state['errors'])} artifact readiness issues")
        else:
            st.success("Saved research artifacts loaded")
        st.caption("Historical synthetic operations: run legacy_app.py separately.")
    st.markdown('<div class="study-note"><strong>REAL PUBLIC CROSS-SECTIONAL DATA.</strong> Original interviews and specimens: CDC/NHANES. Independent source-file collection, harmonization, and secondary analysis.</div>', unsafe_allow_html=True)
    if page == "Study overview":
        _overview(state)
    elif page == "Questions & methods":
        _methods(state)
    elif page == "Weighted results":
        _weighted(state)
    elif page == "Sensitivity & selection":
        _sensitivity(state)
    elif page == "Sources & provenance":
        _sources(state)
    elif page == "Research report":
        _report(state, report_path)
    st.markdown('<div class="footer">Tobacco Exposure Equity Study · Repeated cross-sectional associations, not causal effects or individual clinical diagnoses.</div>', unsafe_allow_html=True)
