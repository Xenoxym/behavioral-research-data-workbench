"""Transparent descriptive summaries for the synthetic study demonstration."""

from __future__ import annotations

from datetime import timedelta
from html import escape

import pandas as pd

from study_workbench.followup import followup_metrics


def _dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="ISO8601", errors="coerce", utc=True).dt.tz_localize(None)


def _present(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _missingness(bundle: dict[str, pd.DataFrame], as_of: str) -> list[dict]:
    """Summarize expected measurement fields, respecting response/visit states."""
    cutoff = pd.Timestamp(as_of) + timedelta(days=1)
    measures = {
        "baseline": ["cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"],
        "visits": ["cigarettes_7d", "abstinent_7d", "co_ppm"],
        "ema": ["urge", "stress"],
    }
    result = []
    for table, fields in measures.items():
        frame = bundle[table]
        if table == "baseline":
            frame = frame.loc[_dates(frame["assessed_at"]) < cutoff]
        elif table == "visits":
            frame = frame.loc[
                frame["status"].eq("completed") & (_dates(frame["completed_at"]) < cutoff)
            ]
        else:
            frame = frame.loc[
                frame["response_state"].eq("answered")
                & (_dates(frame["responded_at"]) < cutoff)
            ]
        for field in fields:
            missing = int((~_present(frame[field])).sum())
            expected = len(frame)
            result.append(
                {
                    "table": table,
                    "field": field,
                    "missing": missing,
                    "expected": expected,
                    "missing_rate": missing / expected if expected else None,
                }
            )
    return result


def build_summary(bundle: dict[str, pd.DataFrame], as_of: str = "2026-10-16") -> dict:
    """Build JSON-friendly descriptive metrics; no treatment-effect inference."""
    cutoff = pd.Timestamp(as_of) + timedelta(days=1)
    participants = bundle["participants"]
    screened = participants.loc[_dates(participants["screening_date"]) < cutoff]
    enrolled = screened.loc[_dates(screened["enrollment_date"]) < cutoff]
    withdrawn = enrolled.loc[_dates(enrolled["withdrawal_date"]) < cutoff]
    ema = bundle["ema"]
    prompted = ema.loc[_dates(ema["prompted_at"]) < cutoff]
    answered = prompted.loc[
        prompted["response_state"].eq("answered")
        & (_dates(prompted["responded_at"]) < cutoff)
    ]
    ages = pd.to_numeric(enrolled["age"], errors="coerce")
    followup_error = None
    try:
        followup = followup_metrics(bundle, as_of)
    except ValueError as exc:
        followup_error = str(exc)
        followup = dict.fromkeys(
            ["due_visits", "completed_due_visits", "completion_rate", "overdue_visits", "withdrawn_visits"]
        )
    return {
        "as_of": str(pd.Timestamp(as_of).date()),
        "data_label": "SYNTHETIC DEMONSTRATION",
        "screened": int(len(screened)),
        "eligible": int(pd.to_numeric(screened["eligible"], errors="coerce").eq(1).sum()),
        "enrolled": int(len(enrolled)),
        "withdrawn": int(len(withdrawn)),
        "mean_age": float(ages.mean()) if ages.notna().any() else None,
        "baseline_records": int(
            (_dates(bundle["baseline"]["assessed_at"]) < cutoff).sum()
        ),
        "ema_prompts": int(len(prompted)),
        "ema_answered": int(len(answered)),
        "ema_response_rate": len(answered) / len(prompted) if len(prompted) else None,
        "followup": followup,
        "followup_error": followup_error,
        "missingness": _missingness(bundle, as_of),
        "table_rows": {name: int(len(frame)) for name, frame in bundle.items()},
    }


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def render_report(
    bundle: dict[str, pd.DataFrame], issues: pd.DataFrame, as_of: str = "2026-10-16"
) -> str:
    """Return a self-contained, escaped HTML report suitable for browser print/PDF."""
    summary = build_summary(bundle, as_of)
    followup = summary["followup"]
    errors = int(issues["severity"].eq("error").sum()) if not issues.empty else 0
    reviews = int(issues["severity"].eq("review").sum()) if not issues.empty else 0
    expected = sum(item["expected"] for item in summary["missingness"])
    missing = sum(item["missing"] for item in summary["missingness"])
    missing_rate = f"{missing / expected:.1%}" if expected else "N/A"
    missing_rows = "".join(
        "<tr>"
        f"<td>{escape(item['table'])} · {escape(item['field'])}</td>"
        f"<td>{item['missing']} / {item['expected']}</td>"
        f"<td>{'N/A' if item['missing_rate'] is None else format(item['missing_rate'], '.1%')}</td>"
        "</tr>"
        for item in summary["missingness"]
    )
    if issues.empty:
        issue_rows = '<tr><td colspan="3">No open automated findings.</td></tr>'
    else:
        issue_rows = "".join(
            "<tr>"
            f"<td>{escape(str(row.rule_id))}</td>"
            f"<td>{escape(str(row.table))} / {escape(str(row.row_id))}</td>"
            f"<td>{escape(str(row.message))}</td>"
            "</tr>"
            for row in issues.head(5).itertuples(index=False)
        )
    as_of_safe = escape(summary["as_of"])
    completion_rate = _pct(followup["completion_rate"])
    denominator = (
        "Unavailable until participant identity conflicts are resolved."
        if summary["followup_error"]
        else f"{followup['completed_due_visits']} / {followup['due_visits']}"
    )
    followup_warning = (
        f'<p class="banner">Follow-up metrics unavailable: {escape(summary["followup_error"])}</p>'
        if summary["followup_error"] else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Synthetic study operations report — {as_of_safe}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#edf3f4;color:#183346;font:13px/1.5 system-ui,Arial,sans-serif}}
main{{max-width:1000px;margin:28px auto;background:white;padding:32px 38px;border-top:7px solid #087f83}}
.eyebrow{{font-size:11px;letter-spacing:1.7px;color:#087f83;font-weight:800}}h1{{font-size:27px;line-height:1.2;margin:8px 0}}
.sub{{color:#586e7a;margin:8px 0 18px}}.banner{{background:#fff4d9;padding:9px 12px;border-left:3px solid #b17c13}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
.metric{{padding:12px;background:#f0f7f7;border:1px solid #d9e8e8;border-radius:7px}}
.metric strong{{display:block;font-size:26px;color:#086e72}}.metric span{{font-size:11px;color:#4b6572}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}h2{{font-size:15px;margin:16px 0 7px}}p{{margin:6px 0}}
table{{border-collapse:collapse;width:100%;font-size:11px}}th,td{{padding:5px 7px;border-bottom:1px solid #e4ebef;text-align:left;vertical-align:top}}
th{{background:#f2f6f8;font-weight:650}}.note{{font-size:11px;color:#5d707b}}.small{{font-size:11px}}
footer{{margin-top:18px;padding-top:10px;border-top:1px solid #d8e2e7;font-size:10px;color:#627682}}
@media print{{@page{{size:A4 landscape;margin:10mm}}body{{background:white;font-size:11px}}main{{margin:0;padding:14px 18px;max-width:none}}h1{{font-size:23px}}.metrics{{margin:12px 0}}.metric{{padding:9px}}h2{{margin:11px 0 5px}}th,td{{padding:3px 6px}}footer{{margin-top:10px}}}}
@media(max-width:700px){{main{{margin:0;padding:22px}}.grid{{grid-template-columns:1fr}}.metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<div class="eyebrow">BEHAVIORAL RESEARCH DATA WORKBENCH / OPERATIONS BRIEF</div>
<h1>Study progress &amp; data readiness</h1>
<p class="sub">Synthetic smoking-cessation demonstration · As of {as_of_safe} · Descriptive operations report</p>
<div class="banner"><strong>SYNTHETIC DATA.</strong> No actual participants, recruitment, clinical outcomes, or notifications.</div>
<div class="metrics">
<div class="metric"><strong>{summary['enrolled']}</strong><span>ENROLLED / {summary['screened']} SCREENED ROWS</span></div>
<div class="metric"><strong>{completion_rate}</strong><span>DUE VISIT COMPLETION · {escape(denominator)}</span></div>
<div class="metric"><strong>{followup['overdue_visits'] if followup['overdue_visits'] is not None else 'N/A'}</strong><span>OVERDUE VISITS</span></div>
<div class="metric"><strong>{len(issues)}</strong><span>QUALITY FINDINGS · {errors} ERRORS / {reviews} REVIEWS</span></div>
</div>
<div class="grid"><section><h2>Participant &amp; follow-up flow</h2>
{followup_warning}
<p>{summary['eligible']} eligible screening rows; {summary['enrolled']} enrolled; {summary['withdrawn']} withdrawn by the report date.</p>
<p>{summary['baseline_records']} baseline records; {summary['ema_answered']} / {summary['ema_prompts']} EMA prompts answered ({_pct(summary['ema_response_rate'])}).</p>
<p class="note">Completion denominator uses enrolled visits whose window has opened by the as-of date. A completion counts only when recorded by that date. Visits affected by withdrawal before or during their window are excluded; visits already missed before withdrawal remain due. Pending windows are included once opened. Invalid schedules are excluded and require review.</p>
<h2>Interpretation &amp; limitations</h2>
<p class="small">These are row-based operational counts from the current working data. Duplicates and unresolved findings can distort totals. Rules support human review; they do not establish clinical truth.</p>
<p class="small">The demonstration does not estimate treatment effects, establish clinical validity, or represent experience recruiting real participants. Public NHANES analysis is a separate cross-sectional case and is not included here.</p>
</section><section><h2>Expected measurement completeness</h2>
<p class="note">{missing} / {expected} expected cells missing ({missing_rate}). Baseline assessments, completed visits, and answered EMA records observed by the report date only. Declined, missed, and not-applicable EMA responses are excluded.</p>
<table><thead><tr><th>Table · measurement</th><th>Missing / expected</th><th>Missing %</th></tr></thead><tbody>{missing_rows}</tbody></table>
</section></div>
<h2>Open findings · first five of {len(issues)}</h2>
<table><thead><tr><th>Rule</th><th>Record</th><th>Review prompt</th></tr></thead><tbody>{issue_rows}</tbody></table>
<footer>Reproducible local portfolio demonstration · pandas + SQLite + Streamlit · Original imports and reasoned corrections are preserved in the application audit history. This HTML contains no external scripts or assets.</footer>
</main></body></html>"""
