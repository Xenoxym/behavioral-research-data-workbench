"""Local Streamlit interface for synthetic study operations and public-data evidence."""

from __future__ import annotations

from datetime import date
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from study_workbench.followup import followup_status
from study_workbench.quality import check_bundle, evaluate
from study_workbench.reporting import build_summary, render_report
from study_workbench.storage import Storage
from study_workbench.synthetic import generate_clean, inject_errors

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "Overview", "Quality review", "Follow-up", "Corrections & audit",
    "Data dictionary", "Public data", "Reports",
]
TEAL = "#087f83"
NAVY = "#14374b"

CSS = """
<style>
:root {--teal:#087f83;--ink:#14374b;--muted:#607888;}
[data-testid="stAppViewContainer"] {background:#f5f8fa;}
[data-testid="stHeader"] {background:rgba(245,248,250,.93);}
[data-testid="stSidebar"] {background:#edf3f5;border-right:1px solid #d9e5e9;}
.block-container {max-width:1320px;padding-top:2.3rem;padding-bottom:3rem;}
h1,h2,h3 {color:#14374b;letter-spacing:-.025em;}
h1 {font-size:2.35rem !important;font-weight:750 !important;}
h2 {font-size:1.35rem !important;}
.brand {color:#14374b;font-size:1.22rem;font-weight:800;line-height:1.35;margin:0 0 5px;}
.brand-mark {color:#087f83;font-size:.72rem;letter-spacing:.16em;font-weight:800;margin-bottom:10px;}
.eyebrow {color:#087f83;font-size:.72rem;font-weight:800;letter-spacing:.13em;margin:0 0 6px;}
.intro {color:#607888;font-size:1rem;line-height:1.6;max-width:820px;margin-bottom:20px;}
.study-banner {background:#e4f3f1;border:1px solid #bddcda;border-radius:9px;padding:11px 16px;color:#205c5d;font-size:.87rem;margin:14px 0 22px;}
.public-banner {background:#eaf0fa;border:1px solid #c9d8ed;border-radius:9px;padding:11px 16px;color:#31537d;font-size:.87rem;margin:14px 0 22px;}
.card {background:#fff;border:1px solid #dce7ec;border-radius:12px;padding:19px 22px;margin-bottom:15px;min-height:115px;}
.card-title {color:#607888;font-size:.76rem;letter-spacing:.045em;text-transform:uppercase;font-weight:700;}
.card-value {color:#14374b;font-size:2.05rem;font-weight:760;line-height:1.4;}
.card-note {color:#6c8290;font-size:.78rem;}
.empty {background:white;border:1px dashed #b8cdd5;border-radius:14px;padding:36px;margin:22px 0;}
.empty h3 {margin-top:0;}
[data-testid="stMetric"] {background:white;border:1px solid #dce7ec;border-radius:10px;padding:15px;}
[data-testid="stMetricValue"] {color:#14374b;}
.stButton button[kind="primary"],.stFormSubmitButton button[kind="primary"] {background:#087f83;border-color:#087f83;}
[data-testid="stDataFrame"] {border-radius:9px;overflow:hidden;}
.footer-note {color:#738996;font-size:.75rem;border-top:1px solid #dce7ec;margin-top:30px;padding-top:12px;}
</style>
"""


def _heading(eyebrow: str, title: str, description: str) -> None:
    st.markdown(f'<div class="eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="intro">{escape(description)}</div>', unsafe_allow_html=True)


def _cards(items: list[tuple[str, str | int, str]]) -> None:
    for column, (title, value, note) in zip(st.columns(len(items)), items, strict=True):
        with column:
            st.markdown(
                f'<div class="card"><div class="card-title">{escape(title)}</div>'
                f'<div class="card-value">{escape(str(value))}</div>'
                f'<div class="card-note">{escape(note)}</div></div>',
                unsafe_allow_html=True,
            )


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def _zip_bundle(bundle: dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for table, frame in bundle.items():
            archive.writestr(f"{table}.csv", _csv(frame))
    return buffer.getvalue()


def _chart(frame: pd.DataFrame, x: str, y: str, color: str | None = None) -> None:
    fig = px.bar(
        frame, x=x, y=y, color=color,
        color_discrete_sequence=[TEAL, "#89b7ba", NAVY, "#d6a65d", "#bdd5e2"],
        template="plotly_white",
    )
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color=NAVY),
        xaxis_title=None, yaxis_title="Records", showlegend=color is not None,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _empty() -> None:
    st.markdown(
        '<div class="empty"><h3>Your study workspace is ready.</h3>'
        '<p>Load the synthetic demonstration from the sidebar to explore screening, '
        'follow-up, quality review, and reasoned corrections.</p>'
        '<p>No participant data, external accounts, or devices are needed.</p></div>',
        unsafe_allow_html=True,
    )


def _overview(bundle: dict[str, pd.DataFrame], issues: pd.DataFrame, as_of: str) -> None:
    _heading(
        "STUDY OPERATIONS", "A clear view of study progress",
        "Follow the synthetic participant journey, review data readiness, and plan the next research task.",
    )
    summary = build_summary(bundle, as_of)
    followup = summary["followup"]
    rate = followup["completion_rate"]
    _cards([
        ("Enrolled", summary["enrolled"], f"of {summary['screened']} screened rows"),
        ("Due visit completion", f"{rate:.1%}" if rate is not None else "N/A",
         f"{followup['completed_due_visits']} / {followup['due_visits']} due visits"
         if not summary["followup_error"] else "Resolve identity conflicts"),
        ("Overdue visits", followup["overdue_visits"]
         if followup["overdue_visits"] is not None else "N/A", "Review the follow-up queue"),
        ("Open quality findings", len(issues), "Automated prompts for human review"),
    ])
    if summary["followup_error"]:
        st.warning(f"Follow-up metrics unavailable: {summary['followup_error']}")
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.subheader("Participant flow")
        flow = pd.DataFrame({
            "Stage": ["Screened", "Eligible", "Enrolled", "Withdrawn"],
            "Records": [summary[key] for key in ["screened", "eligible", "enrolled", "withdrawn"]],
        })
        _chart(flow, "Stage", "Records")
        st.caption("Row counts observed by the as-of date. Unresolved duplicates can distort totals.")
    with right:
        st.subheader("Visit status")
        if summary["followup_error"]:
            st.info("Resolve duplicate participant IDs before computing visit status.")
        else:
            status = followup_status(bundle, as_of)
            counts = status["computed_status"].value_counts().rename_axis("Status").reset_index(name="Records")
            _chart(counts, "Status", "Records")
        st.caption("Pending visits include future appointments. Only opened windows enter the completion denominator.")
    st.subheader("Working data")
    table = st.selectbox("Explore table", list(bundle), key="overview_table")
    st.dataframe(bundle[table], hide_index=True, use_container_width=True, height=300)
    st.download_button("Download this table", _csv(bundle[table]), f"synthetic_{table}.csv", "text/csv")
    with st.expander("How to read these numbers"):
        st.write(
            "The report date controls what is observable. Due visits are enrolled visits whose window "
            "has opened. Completions after the report date do not count yet. Withdrawal before or "
            "during a window removes that visit from the due denominator; visits already missed "
            "before withdrawal remain due. Invalid schedules are excluded and require review."
        )


def _quality(bundle: dict[str, pd.DataFrame], issues: pd.DataFrame) -> None:
    _heading(
        "DATA READINESS", "Review the evidence behind each finding",
        "Every finding points to a record, field, and documented rule. Review context before making a correction.",
    )
    tab_live, tab_benchmark = st.tabs(["Working data", "Injected-error benchmark"])
    with tab_live:
        errors = int(issues["severity"].eq("error").sum())
        _cards([
            ("Findings", len(issues), "Current working records"),
            ("Errors", errors, "Structural or protocol rule failures"),
            ("Needs review", len(issues) - errors, "Context-dependent inconsistencies"),
        ])
        severity = st.selectbox("Finding severity", ["All", "error", "review"])
        filtered = issues if severity == "All" else issues.loc[issues["severity"].eq(severity)]
        if issues.empty:
            st.success("No automated findings in the current working data.")
            st.caption("Use the injected-error benchmark to inspect known defects and legitimate special cases.")
        else:
            st.dataframe(filtered, hide_index=True, use_container_width=True)
        st.download_button("Download current findings", _csv(filtered), "synthetic_quality_findings.csv", "text/csv")
    with tab_benchmark:
        st.info("Independent synthetic benchmark. These injected records never replace your working database.")
        if st.button("Run injected-error benchmark", type="primary"):
            clean = generate_clean(seed=42, n=240)
            dirty, truth = inject_errors(clean)
            findings = check_bundle(dirty)
            st.session_state["quality_benchmark"] = {
                "findings": findings, "evaluation": evaluate(findings, truth),
                "clean_count": len(check_bundle(clean)), "truth_count": len(truth),
            }
        result = st.session_state.get("quality_benchmark")
        if result:
            st.write(f"Known injected defect labels: **{result['truth_count']}**. Clean-data findings: **{result['clean_count']}**.")
            st.json(result["evaluation"], expanded=True)
            st.dataframe(result["findings"], hide_index=True, use_container_width=True)
            st.caption("Matches are deduplicated by rule, table, row, and field. Detection rates describe this synthetic benchmark only.")
        else:
            st.caption("Run the benchmark to measure actual true positives, false positives, and false negatives.")
    with st.expander("Rule catalogue"):
        path = ROOT / "docs" / "QUALITY_RULES.md"
        if path.exists():
            st.markdown(path.read_text(encoding="utf-8"))
        else:
            st.info("The rule catalogue is not available in this checkout.")


def _followup(bundle: dict[str, pd.DataFrame], as_of: str) -> None:
    _heading(
        "PARTICIPANT CONTINUITY", "Plan the next follow-up",
        "A date-aware visit queue with explicit withdrawal handling. Contact records are documentation only; no messages are sent.",
    )
    try:
        status = followup_status(bundle, as_of)
    except ValueError as exc:
        st.error(f"Cannot calculate follow-up: {exc}")
        return
    options = ["All"] + sorted(status["computed_status"].unique().tolist())
    selected = st.selectbox("Visit status", options)
    queue = status if selected == "All" else status.loc[status["computed_status"].eq(selected)]
    query = st.text_input("Filter participant ID", placeholder="For example: SYN-0001")
    if query:
        queue = queue.loc[queue["participant_id"].astype(str).str.contains(query, case=False, regex=False)]
    st.dataframe(queue, hide_index=True, use_container_width=True, height=420)
    st.download_button("Download follow-up queue", _csv(queue), f"synthetic_followup_{as_of}.csv", "text/csv")
    st.caption(
        "An open window may still be pending. A visit becomes overdue after window_end. "
        "Missing or invalid windows require data review and are excluded from due counts."
    )
    with st.expander("Recorded contact attempts — synthetic"):
        st.dataframe(bundle["contacts"], hide_index=True, use_container_width=True)
        st.caption("No real phone numbers or email addresses are stored. This application never sends notifications.")


def _corrections(storage: Storage, bundle: dict[str, pd.DataFrame]) -> None:
    _heading(
        "TRACEABLE DATA MANAGEMENT", "Correct with a reason. Keep the history.",
        "Working records can change after review. Original imports and the before-and-after audit trail remain available.",
    )
    flash = st.session_state.pop("correction_flash", None)
    if flash:
        st.success(flash)
    table = st.selectbox("Table to correct", list(bundle), key="correction_table")
    frame = bundle[table]
    if frame.empty:
        st.info("This table has no records.")
        return
    row_id = st.selectbox("Record row ID", frame["row_id"].astype(str).tolist(), key=f"correction_row_{table}")
    row = frame.loc[frame["row_id"].astype(str).eq(row_id)].iloc[0]
    fields = [field for field in frame.columns if field not in {"row_id", "participant_id"}]
    field = st.selectbox("Field to correct", fields, key=f"correction_field_{table}")
    current = row[field]
    current_text = "" if pd.isna(current) else str(current)
    st.caption(f"Participant: {row['participant_id']} · Current value: {current_text or '(missing)'}")
    st.dataframe(frame.loc[frame["row_id"].astype(str).eq(row_id)], hide_index=True, use_container_width=True)
    with st.form("correction_form"):
        value = st.text_input("New value", value=current_text, key=f"new_value_{table}_{row_id}_{field}")
        col_actor, col_reason = st.columns([1, 2])
        actor = col_actor.text_input("Reviewer name", placeholder="Demo reviewer")
        reason = col_reason.text_input("Correction reason", placeholder="Explain the source or review decision")
        st.caption("Dates: YYYY-MM-DD. EMA timestamps require a timezone offset. Leave value blank to record missingness. Structural IDs are protected.")
        submitted = st.form_submit_button("Save reasoned correction", type="primary")
    if submitted:
        if not actor.strip() or not reason.strip():
            st.error("Reviewer name and correction reason are required.")
        else:
            try:
                storage.correct(table, row_id, field, value, reason.strip(), actor.strip())
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Correction was not saved: {exc}")
            else:
                st.session_state["correction_flash"] = f"Correction saved for {table} / {row_id} / {field}. Audit history preserved."
                st.rerun()
    st.subheader("Persistent audit history")
    audit = storage.audit_log()
    if audit.empty:
        st.info("No corrections yet. Every saved correction requires a reviewer and a reason.")
    else:
        st.dataframe(audit, hide_index=True, use_container_width=True)
    st.download_button("Download audit CSV", _csv(audit), "synthetic_correction_audit.csv", "text/csv")


def _dictionary() -> None:
    _heading(
        "STANDARDIZED COLLECTION", "A shared definition for every field",
        "Variable meaning, type, range, and missingness conventions for the synthetic study tables.",
    )
    st.info("Blank CSV cells mean missing. A declined response, a missed response, and a not-applicable response have distinct recorded states.")
    path = ROOT / "docs" / "data_dictionary.csv"
    if not path.exists():
        st.info("The data dictionary is not available in this checkout.")
        return
    dictionary = pd.read_csv(path, keep_default_na=False)
    table_column = "table" if "table" in dictionary else dictionary.columns[0]
    selected = st.selectbox("Dictionary table", ["All"] + dictionary[table_column].unique().tolist())
    filtered = dictionary if selected == "All" else dictionary.loc[dictionary[table_column].eq(selected)]
    st.dataframe(filtered, hide_index=True, use_container_width=True, height=500)
    st.download_button("Download full data dictionary", path.read_bytes(), "data_dictionary.csv", "text/csv")


def _public_data(reports_dir: Path) -> None:
    _heading(
        "INDEPENDENT PUBLIC-DATA CASE", "Smoking measures in NHANES",
        "A reproducible, descriptive cross-sectional analysis of public CDC questionnaire and serum cotinine data.",
    )
    st.markdown(
        '<div class="public-banner"><strong>PUBLIC SURVEY DATA.</strong> '
        'This analysis is separate from the synthetic longitudinal study. '
        'No public survey respondent is treated as a trial participant.</div>', unsafe_allow_html=True,
    )
    directory = reports_dir / "nhanes"
    summary_path = directory / "summary.json"
    report_path = directory / "report.html"
    if not summary_path.exists():
        st.info("The public-data analysis has not been generated locally yet.")
        st.code("python -m study_workbench.cli nhanes", language="bash")
        st.caption("Downloading is an explicit CLI step. Opening this application never downloads data.")
    else:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            st.error(f"Could not read the local analysis summary: {exc}")
        else:
            st.subheader("Saved analysis evidence")
            with st.expander("Counts, source provenance, and methods", expanded=False):
                st.json(summary)
            st.download_button("Download public analysis summary", summary_path.read_bytes(), "nhanes_summary.json", "application/json")
        if report_path.exists():
            components.html(report_path.read_text(encoding="utf-8"), height=850, scrolling=True)
            st.download_button("Download NHANES HTML report", report_path.read_bytes(), "nhanes_report.html", "text/html")
        sample_path = directory / "sample_summary.csv"
        if sample_path.exists():
            st.download_button("Download public sample summary CSV", sample_path.read_bytes(), "nhanes_sample_summary.csv", "text/csv")
        manifest_path = directory / "provenance_manifest.json"
        if manifest_path.exists():
            st.download_button("Download source provenance manifest", manifest_path.read_bytes(), "nhanes_provenance_manifest.json", "application/json")
    with st.expander("Methods and limitations"):
        methods = ROOT / "docs" / "NHANES_METHODS.md"
        if methods.exists():
            st.markdown(methods.read_text(encoding="utf-8"))
        else:
            st.write("Public survey descriptions do not establish causal treatment effects or validate a clinical classifier.")


def _reports(bundle: dict[str, pd.DataFrame], issues: pd.DataFrame, as_of: str) -> None:
    _heading(
        "RESEARCH COMMUNICATION", "A study brief you can reproduce",
        "Export a concise operations report and the current working tables. Metrics always state their date and denominator.",
    )
    report = render_report(bundle, issues, as_of)
    left, right = st.columns(2)
    left.download_button("Download one-page HTML report", report.encode("utf-8"), f"synthetic_study_report_{as_of}.html", "text/html", type="primary")
    right.download_button("Download all working tables (ZIP)", _zip_bundle(bundle), f"synthetic_working_tables_{as_of}.zip", "application/zip")
    st.caption("Open the downloaded HTML in a browser to print or save as PDF. The public NHANES report remains separate.")
    components.html(report, height=830, scrolling=True)


def main() -> None:
    """Render a local-only app; initializing a demo is always an explicit action."""
    st.set_page_config(page_title="Behavioral Research Data Workbench", page_icon="🧭", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    data_dir = Path(os.environ.get("WORKBENCH_DATA_DIR", str(ROOT / "data")))
    db_path = Path(os.environ.get("WORKBENCH_DB_PATH", str(data_dir / "workbench.sqlite")))
    reports_dir = Path(os.environ.get("WORKBENCH_REPORTS_DIR", str(ROOT / "reports")))
    storage = Storage(db_path)
    bundle = storage.load_bundle()
    has_data = not bundle["participants"].empty
    with st.sidebar:
        st.markdown('<div class="brand-mark">RESEARCH OPERATIONS / LOCAL</div><div class="brand">Behavioral Research<br>Data Workbench</div>', unsafe_allow_html=True)
        st.caption("A portfolio demonstration for careful research data work.")
        st.divider()
        page = st.radio("Workspace", PAGES, key="workspace_page")
        st.divider()
        as_of = st.date_input("Study as-of date", value=date(2026, 10, 16)).isoformat()
        st.caption("Metrics use this date, not your computer clock.")
        if st.button("Load synthetic demo", type="primary", disabled=has_data, use_container_width=True):
            storage.import_bundle(generate_clean(seed=42, n=240), source_name="synthetic_clean_seed42")
            st.session_state["demo_flash"] = True
            st.rerun()
        if has_data:
            st.caption("Demo loaded. Saved records and corrections persist between sessions.")
        st.caption("No hardware · No real participants · No notifications")
    if st.session_state.pop("demo_flash", False):
        st.success("Synthetic demonstration loaded. Your working database is ready.")
    if page != "Public data":
        st.markdown('<div class="study-banner"><strong>SYNTHETIC STUDY.</strong> All people, visits, and contact records are generated. No real recruitment or clinical care.</div>', unsafe_allow_html=True)
    if page == "Public data":
        _public_data(reports_dir)
    elif page == "Data dictionary":
        _dictionary()
    elif not has_data:
        _heading("WELCOME", "Good research starts with reliable records", "A local workbench for data quality, participant follow-up, and transparent reporting.")
        _empty()
    else:
        issues = check_bundle(bundle)
        if page == "Overview":
            _overview(bundle, issues, as_of)
        elif page == "Quality review":
            _quality(bundle, issues)
        elif page == "Follow-up":
            _followup(bundle, as_of)
        elif page == "Corrections & audit":
            _corrections(storage, bundle)
        elif page == "Reports":
            _reports(bundle, issues, as_of)
    st.markdown('<div class="footer-note">Behavioral Research Data Workbench · Reproducible operations, reasoned corrections, explicit limitations.</div>', unsafe_allow_html=True)
