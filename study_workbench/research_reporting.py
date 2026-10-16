"""Manuscript-style real-data report and standard, exportable scientific figures."""
from __future__ import annotations

import base64
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PERIODS = {"I": "2015–2016", "P": "2017–March 2020", "L": "August 2021–August 2023"}
POVERTY = {"lt1": "<100% FPL", "1to2": "100–<200% FPL", "2to4": "200–<400% FPL", "ge4": "≥400% FPL", "unknown": "Income unknown"}
COLORS = {"I": "#347c8a", "P": "#b46d36", "L": "#62599a"}
SCENARIOS = {
    "primary": "Primary (age 25+, cutoff 0.05)", "age18": "Age 18+",
    "cigarette_only": "Cigarette-only screen", "cutoff_0_10": "Cutoff 0.10 ng/mL",
    "cutoff_0_015": "Common cutoff 0.015 ng/mL",
    "naive_native_detectability": "Native LOD (different cutoffs)",
    "upper_cap3": "Upper cotinine cap 3 ng/mL", "household_complete": "Household complete",
    "income_complete": "Income complete", "education_complete": "Education complete",
    "lab_missing_unexposed": "Missing assays all unexposed", "lab_missing_exposed": "Missing assays all exposed",
}
REFERENCES = [
    ("Brody, Faust & Tsai. NCHS Data Brief 396 (2021): prior socioeconomic gradients and cotinine definition.", "https://www.cdc.gov/nchs/products/databriefs/db396.htm"),
    ("Tsai et al. MMWR 2018: historical secondhand-smoke exposure research.", "https://www.cdc.gov/mmwr/volumes/67/wr/mm6748a3.htm"),
    ("CDC NHANES: sample weighting guidance.", "https://wwwn.cdc.gov/nchs/nhanes/tutorials/weighting.aspx"),
    ("CDC NHANES: variance estimation and domain analysis.", "https://wwwn.cdc.gov/nchs/nhanes/tutorials/varianceestimation.aspx"),
    ("CDC COT_L: August 2026 release, phlebotomy weights, detection limits and missingness.", "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/COT_L.htm"),
    ("R survey: design-based generalized linear models.", "https://r-survey.r-forge.r-project.org/pkgdown/docs/reference/svyglm.html"),
]


def _rate(value, digits=1):
    return f"{100 * float(value):.{digits}f}%" if pd.notna(value) else "Not estimable"


def _interval(row, percentage=True):
    factor = 100 if percentage else 1
    if pd.isna(row.get("ci_low")) or pd.isna(row.get("ci_high")):
        return "Not estimable"
    return f"{factor * row['ci_low']:.1f} to {factor * row['ci_high']:.1f}"


def _md_table(frame):
    cols = list(frame.columns)
    def cell(x):
        return str(x).replace("|", "\\|").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(map(cell, cols)) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
        *("| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None)),
    ])


def _save(fig, output, name):
    fig.savefig(output / f"{name}.png", dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_figures(output_dir: str | Path) -> list[tuple[str, str]]:
    root = Path(output_dir)
    figures = root / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    estimates = pd.read_csv(root / "estimates.csv")
    sensitivity = pd.read_csv(root / "sensitivities.csv")
    missingness = pd.read_csv(root / "missingness.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "tobacco-exposure-equity"})
    plots = []
    income = estimates.loc[estimates.group_variable.eq("poverty_group") & estimates.group.isin(POVERTY)].copy()
    if not income.empty:
        fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.3), sharex=True, sharey=True)
        groups = ["lt1", "1to2", "2to4", "ge4"]
        for ax, period in zip(axes, PERIODS):
            sub = income.loc[income.period.eq(period)].set_index("group").reindex(groups)
            x = sub.prevalence.to_numpy(float) * 100
            lo, hi = sub.ci_low.to_numpy(float) * 100, sub.ci_high.to_numpy(float) * 100
            ax.errorbar(x, range(len(groups)), xerr=np.maximum(0, np.vstack([x-lo, hi-x])), fmt="o", capsize=4, color=COLORS[period])
            ax.set_title(PERIODS[period], fontsize=10)
            ax.set_xlabel("Weighted exposure prevalence (%)")
            ax.grid(axis="x", alpha=.2)
            ax.set_xlim(left=0)
        axes[0].set_yticks(range(len(groups)), [POVERTY[g] for g in groups])
        axes[0].invert_yaxis()
        fig.suptitle("Income gradient in cotinine-defined exposure", fontsize=15, y=1.02)
        fig.text(.06, -.04, "Adults 25+; strict reported nonuse; cotinine ≤10 ng/mL; exposure ≥0.05 ng/mL.\nPoints: survey-weighted estimates. Whiskers: 95% logit confidence intervals. Independent cross-sections.", fontsize=9)
        fig.tight_layout()
        _save(fig, figures, "income_gradient")
        plots.append(("income_gradient", "Income gradient with survey-based 95% confidence intervals; FPL = federal poverty level."))
    if not sensitivity.empty:
        scenarios = sensitivity.scenario.drop_duplicates().tolist()
        fig, axes = plt.subplots(1, 3, figsize=(13.5, max(5, len(scenarios) * .32)), sharex=True, sharey=True)
        for ax, period in zip(axes, PERIODS):
            sub = sensitivity.loc[sensitivity.period.eq(period)].drop_duplicates("scenario").set_index("scenario").reindex(scenarios)
            x, lo, hi = (sub[c].to_numpy(float) * 100 for c in ("prevalence", "ci_low", "ci_high"))
            ax.errorbar(x, range(len(scenarios)), xerr=np.maximum(0, np.vstack([x-lo, hi-x])), fmt="o", capsize=3, color=COLORS[period])
            ax.set_title(PERIODS[period], fontsize=10)
            ax.set_xlabel("Weighted prevalence (%)")
            ax.grid(axis="x", alpha=.2)
            ax.set_xlim(left=0)
        axes[0].set_yticks(range(len(scenarios)), [SCENARIOS.get(s, s) for s in scenarios], fontsize=8)
        axes[0].invert_yaxis()
        fig.suptitle("Prespecified sensitivity analyses", fontsize=15)
        fig.text(.02, -.01, "Scenario definitions and denominators are supplied in sensitivities.csv; detectability uses a different outcome. Descriptive bounds have no sampling CI.", fontsize=8)
        fig.tight_layout()
        _save(fig, figures, "sensitivity")
        plots.append(("sensitivity", "Sensitivity audit. Different cutoffs and selection rules change the estimand; these are not competing estimates of an identical quantity."))
    if not missingness.empty and {"group_variable", "group", "missing_rate"}.issubset(missingness.columns):
        sub = missingness.loc[missingness.group_variable.eq("poverty_group") & missingness.group.isin(POVERTY)]
        if not sub.empty:
            denominators = sub.denominator.unique()
            fig, axes = plt.subplots(1, len(denominators), figsize=(max(7, 5 * len(denominators)), 4.6), squeeze=False)
            for ax, denominator in zip(axes[0], denominators):
                for i, period in enumerate(PERIODS):
                    data = sub.loc[sub.denominator.eq(denominator) & sub.period.eq(period)].set_index("group").reindex(["lt1", "1to2", "2to4", "ge4"])
                    if data.missing_rate.notna().any():
                        ax.plot(np.arange(4), 100 * data.missing_rate, "o--", color=COLORS[period], label=PERIODS[period])
                ax.set_xticks(range(4), ["<100%", "100–<200%", "200–<400%", "≥400%"], rotation=20)
                ax.set_ylabel("Weighted missing assay (%)")
                ax.set_xlabel("Family income / poverty threshold")
                ax.set_title(str(denominator).replace("_", " "), fontsize=10)
                ax.set_ylim(bottom=0)
                ax.grid(axis="y", alpha=.2)
                ax.legend(fontsize=7)
            fig.suptitle("Laboratory availability and its denominator", fontsize=14)
            fig.tight_layout()
            _save(fig, figures, "missingness")
            plots.append(("missingness", "Missing assay proportions have explicitly different denominators. MEC nonresponse and residual phlebotomy-weight-positive missingness must not be conflated."))
    return plots


def build_research_report(output_dir: str | Path) -> dict:
    root = Path(output_dir)
    tables = {name: pd.read_csv(root / f"{name}.csv") for name in
              ("estimates", "contrasts", "models", "sensitivities", "missingness", "sample_flow")}
    manifest = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((root / "analysis_metadata.json").read_text(encoding="utf-8"))
    plots = make_figures(root)
    overall = tables["estimates"].loc[tables["estimates"].group_variable.eq("overall")].copy()
    headline = []
    for _, row in overall.iterrows():
        headline.append({"Period": PERIODS.get(row.period, row.period), "Analytic n": int(row.n),
                         "Exposed n": int(row.events), "Weighted exposure": _rate(row.prevalence),
                         "95% CI (%)": _interval(row), "Design df": int(row.df) if pd.notna(row.df) else "NA"})
    headline = pd.DataFrame(headline)
    contrast = tables["contrasts"].copy()
    contrast_display = contrast[[c for c in ("period", "contrast", "estimate", "se", "ci_low", "ci_high", "df") if c in contrast]].copy()
    for col in ("estimate", "se", "ci_low", "ci_high"):
        if col in contrast_display:
            contrast_display[col] = contrast_display[col].map(lambda v: f"{100*v:.2f}" if pd.notna(v) else "NA")
    findings = []
    for _, row in overall.iterrows():
        findings.append(f"{PERIODS.get(row.period, row.period)}: {_rate(row.prevalence)} (95% CI {_interval(row)}%), based on {int(row.n):,} eligible observed assays and {int(row.events):,} exposed observations.")
    contrast_findings = []
    for _, row in contrast.iterrows():
        if pd.isna(row.estimate):
            continue
        uncertainty = "the interval excludes zero" if row.ci_low > 0 or row.ci_high < 0 else "the interval includes zero"
        contrast_findings.append(f"{row.period}, {row.contrast}: {100*row.estimate:.2f} percentage points (95% CI {_interval(row)}); {uncertainty}.")
    model = tables["models"]
    selected_models = model.loc[
        (model.model.isin(["M1_common", "M2"]) & model.term.eq("poverty_grouplt1")) |
        (model.model.eq("M2") & model.term.eq("indoor_smokingyes"))].copy()
    model_display = pd.DataFrame({
        "Period": selected_models.period, "Model": selected_models.model,
        "Association": selected_models.term.map({"poverty_grouplt1": "Poverty <1 vs ≥4", "indoor_smokingyes": "Indoor smoking yes vs no"}),
        "OR": selected_models.odds_ratio.map(lambda v: f"{v:.2f}"),
        "95% CI": selected_models.apply(lambda r: f"{r.ci_low:.2f} to {r.ci_high:.2f}", axis=1),
        "n": selected_models.n, "Quality flag": selected_models.quality_flag.fillna("None"),
    })
    sensitivity = tables["sensitivities"]
    audit_display = sensitivity.pivot(index="scenario", columns="period", values="prevalence").reindex(
        ["primary", "age18", "cutoff_0_015", "naive_native_detectability", "lab_missing_unexposed", "lab_missing_exposed"])
    audit_display = audit_display.map(_rate).rename(index=SCENARIOS).rename_axis("Scenario").reset_index()
    substantive = []
    crossperiod = contrast.loc[contrast.period.str.contains("_to_")]
    if not crossperiod.empty and (crossperiod.ci_low.le(0) & crossperiod.ci_high.ge(0)).all():
        substantive.append("Income differences persist in every primary period, but all prespecified crossperiod changes in the gap have confidence intervals including zero. Point estimates alone do not establish that inequality widened. This distinction is the primary interpretive conclusion.")
    def scenario_row(period, scenario):
        rows = sensitivity.loc[sensitivity.period.eq(period) & sensitivity.scenario.eq(scenario)]
        return rows.iloc[0] if len(rows) else None
    common_l, native_l = scenario_row("L", "cutoff_0_015"), scenario_row("L", "naive_native_detectability")
    if common_l is not None and native_l is not None:
        substantive.append(f"Measurement audit: in L, native detectability is {_rate(native_l.prevalence)}, while the harmonized 0.015 ng/mL cutoff gives {_rate(common_l.prevalence)} on exactly the same participants. The {100*(native_l.prevalence-common_l.prevalence):.1f}-percentage-point difference is due to the threshold definition. Comparing native detectability across periods would conceal a change visible under a common threshold; neither detectability outcome is the primary 0.05 endpoint.")
    age_i, age_l = scenario_row("I", "age18"), scenario_row("L", "age18")
    if age_i is not None and age_l is not None:
        substantive.append(f"Population-definition audit: with age18+ rather than25+, the income-gap point estimates are {100*age_i.poverty_gap:.1f} percentage points in I and {100*age_l.poverty_gap:.1f} in L. Thus the visual direction of the period comparison depends on the target age population. This is a comparison of estimands, not evidence for selecting the age cutoff with a preferred story.")
    for period in PERIODS:
        pair = selected_models.loc[selected_models.period.eq(period) & selected_models.term.eq("poverty_grouplt1")].set_index("model")
        if {"M1_common", "M2"}.issubset(pair.index):
            substantive.append(f"{period}, matched-sample income OR: {pair.loc['M1_common','odds_ratio']:.2f} before household adjustment and {pair.loc['M2','odds_ratio']:.2f} afterward (n={int(pair.loc['M2','n']):,}). Household adjustment does not remove the income association. Odds-ratio changes cannot quantify a proportion mediated, including because odds ratios are non-collapsible.")
    substantive.append("Missingness extremes describe the overall marker prevalence when every unresolved assay is assigned unexposed or exposed and eligible. They are not identified estimates, confidence intervals, or worst-case bounds on the between-income difference; group-specific missingness could move that difference in other ways.")
    n_total = int(overall.n.sum()) if not overall.empty else 0
    introduction = (
        "This independent secondary study examines socioeconomic differences in recent nicotine exposure "
        "using three non-overlapping NHANES periods. The analysis plan was committed before comparative "
        "outcomes were calculated. The work combines biological measurement, behavioral questionnaires, "
        "survey inference and a documented measurement/selection audit. It is a replication and extension, "
        "not a claim that socioeconomic gradients are a newly discovered phenomenon."
    )
    chinese = (
        f"这是一项真实公开数据的独立二次研究：从 CDC 收集 {len(manifest['sources'])} 个原始数据文件，"
        f"保留 {manifest['analytic_rows']:,} 条人口学记录用于完整抽样设计，再按预先确定的规则形成 "
        f"{n_total:,} 条主要分析记录。研究问题是收入、家庭室内吸烟与可替宁暴露指标的关系，"
        "并检查测量方式、检测限和缺失数据对比较的影响。所有研究观察均来自 CDC；没有合成参与者进入结果。"
    )
    methods = [
        "Population: adults aged 25+ reporting no current cigarettes and explicit five-day nonuse of smoking, smokeless and nicotine-replacement products; the latest period additionally requires the separate e-cigarette item. Unknown responses are retained in audit and excluded from the strict cohort. Current status is not proof of 30-day abstinence; this differs from the exact CDC Data Brief 396 cohort.",
        "Biomarker: observed serum cotinine ≤10 ng/mL defines the marker-restricted cohort; exposure is ≥0.05 ng/mL. Native LODs are 0.015 ng/mL in I/P and 0.010 in L. Published below-LOD values and flags are preserved; missing assays are never replaced by zero. The marker is compatible with secondhand exposure but does not establish its source.",
        "Design: separate period-specific R survey designs use masked strata/PSUs and I WTMEC2YR, P WTMECPRP, L WTPH2YR weights. Full positive-weight samples precede analytic-domain subsetting. L's missing weight column is recovered through a one-to-one HEPA_L link and independently verified against HEPB_S_L; no hepatitis outcomes are analyzed.",
        "Inference: survey-weighted prevalence, logit 95% intervals and design degrees of freedom; poor-minus-affluent prevalence differences use their joint survey covariance. Crossperiod gap contrasts are secondary and assume independent samples. Models use quasibinomial survey logistic regression with robust covariance; odds ratios are association measures, not risk ratios.",
        "Models: M1_all adjusts poverty for age (per decade), recorded sex and race/Hispanic-origin group. M1_common repeats M1 on M2's household-complete sample; M2 adds indoor household smoking. Only M1_common versus M2 supports discussion of coefficient changes, with no causal-mediation interpretation.",
        "Sensitivity: all planned scenarios, income/education/household completeness, assay availability, bounds, native detectability and alternate thresholds are exported. Intervals are pointwise; no familywise multiplicity control is claimed. Exploratory quality flags are not a full certification against NCHS presentation standards. No p-value-based model or threshold selection was performed.",
    ]
    reasoning = [
        "The engineering contribution is not the dashboard alone. It is a traceable chain from a prespecified question to source-codebook reconciliation, harmonized eligibility, correct design-based uncertainty, sensitivity checks and an interpretable report.",
        "The L weight discrepancy demonstrates why reading documentation without inspecting file contents is insufficient. The independent weight-file comparison tests a specific repair rather than silently substituting generic examination weights.",
        "The apparent time pattern combines changes in sampling, blood response, laboratory limits and recent-use interviewing (CAPI versus ACASI). It cannot be interpreted as an intervention effect, individual follow-up, or a causal pandemic effect.",
        "Household indoor smoking is one possible exposure context. The association between income and the biomarker can also reflect unmeasured settings, product reporting and selection. Adjustment and a smaller coefficient alone do not prove mediation.",
    ]
    limitations = [
        "CDC collected the original measurements. This repository independently acquires and analyzes public files; it does not establish recruitment, consent, participant communication, IRB implementation or clinical employment experience.",
        "Repeated cross-sectional observational data do not identify causal effects. Income is top-coded, age is top-coded, nicotine has multiple sources, and short-window questionnaires may misclassify exposure. The cohort definition is explicitly CDC-aligned rather than an exact replication.",
        "Missing laboratory and questionnaire data can leave selection bias after published weighting. Phlebotomy weights already address blood nonresponse; no second correction for the same missing draws is applied. Descriptive missing-outcome bounds are not confidence intervals.",
        "Sparse indoor-smoking subgroups and wide model intervals require caution. All planned estimates, warnings and unstable results are retained in the CSVs. This is a portfolio research study, not a peer-reviewed publication or validated clinical tool.",
    ]
    sources = pd.DataFrame([{"Source": s["name"], "Period": s["period"], "Records": s["records"],
                             "SHA256": s["sha256"]} for s in manifest["sources"]])
    body_md = ["# Tobacco Exposure Equity Study", "Independent real-data research · NHANES 2015–2023 · Analysis date 2026-10-16",
               "## 中文研究摘要", chinese, "## Research question and contribution", introduction,
               "## Primary results", _md_table(headline), *findings,
               "## Prespecified contrasts", "All values below are percentage points; confidence intervals include sampling uncertainty, not every source of bias.",
               _md_table(contrast_display), *contrast_findings,
               "## Substantive findings and sensitivity audit", *substantive,
               _md_table(audit_display), "## Adjusted associations", _md_table(model_display),
               "Odds ratios are not prevalence ratios or causal effects. All other model terms are retained in research/models.csv.",
               "## Methods", *methods,
               "## Figures"]
    for name, caption in plots:
        body_md += [f"![{caption}](research/figures/{name}.png)", caption]
    body_md += ["## Sample flow", "The stages are sequential unweighted exclusions. Overall prevalence uses the cotinine-at-most10 stage; later covariate stages are not its denominator.",
                _md_table(tables["sample_flow"]), "## Research interpretation", *reasoning,
                "## Limitations", *limitations,
                "## Reproducibility and provenance", "Run `uv run research-workbench research --offline` after the initial verified acquisition. See research/pipeline_run.json for code, input and output hashes; analysis_metadata.json for runtime, formulas and warnings. Raw/canonical individual records are excluded from Git; aggregate tables and source metadata are retained.",
                _md_table(sources), "## Complete results", "All subgroup estimates, complete model coefficients, scenario definitions and missingness denominators are in reports/research/*.csv. The saved app reads these exact files.",
                "## References", *[f"- [{title}]({url})" for title, url in REFERENCES]]
    md = "\n\n".join(body_md) + "\n"
    target = root.parent
    target.mkdir(parents=True, exist_ok=True)
    (target / "RESEARCH_REPORT.md").write_text(md, encoding="utf-8")
    # Build HTML from structured values, escaping text/data rather than executing Markdown.
    parts = []
    def para(text):
        return "<p>" + escape(text) + "</p>"
    def heading(text):
        return "<h2>" + escape(text) + "</h2>"
    def table(frame):
        return '<div class="table">' + frame.to_html(index=False, escape=True, border=0) + '</div>'
    parts += [heading("中文研究摘要"), para(chinese), heading("Research question and contribution"), para(introduction),
              heading("Primary results"), table(headline), *map(para, findings),
              heading("Prespecified contrasts"), para("Differences and intervals in the table are percentage points."), table(contrast_display), *map(para, contrast_findings),
              heading("Substantive findings and sensitivity audit"), *map(para, substantive), table(audit_display),
              heading("Adjusted associations"), table(model_display), para("Odds ratios are not prevalence ratios or causal effects. The complete models.csv retains all terms."),
              heading("Methods"), *map(para, methods), heading("Scientific figures")]
    for name, caption in plots:
        png = base64.b64encode((root / f"figures/{name}.png").read_bytes()).decode("ascii")
        parts.append(f'<figure><img src="data:image/png;base64,{png}" alt="{escape(caption, quote=True)}"><figcaption>{escape(caption)}</figcaption></figure>')
    parts += [heading("Sample flow"), para("Sequential unweighted exclusions. Overall prevalence uses cotinine_at_most10; later covariate stages do not define its denominator."), table(tables["sample_flow"]),
              heading("Research interpretation"), *map(para, reasoning), heading("Limitations"), *map(para, limitations),
              heading("Complete results and reproducibility"), para("The CSVs retain all planned subgroup estimates, model coefficients, scenario definitions, missingness denominators and quality flags. Run uv run research-workbench research --offline to reproduce after initial acquisition. Code/input/output hashes are recorded in research/pipeline_run.json."),
              '<div class="links">' + " · ".join(f'<a href="research/{name}.csv">{name}.csv</a>' for name in tables) + '</div>',
              heading("Source provenance"), table(sources), heading("Statistical engine metadata"),
              '<details><summary>Runtime, formulas, degrees of freedom and warnings</summary><pre>' + escape(json.dumps(metadata, indent=2, ensure_ascii=False)) + '</pre></details>',
              heading("References"), '<ol>' + ''.join(f'<li><a href="{escape(url, quote=True)}">{escape(title)}</a></li>' for title, url in REFERENCES) + '</ol>']
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tobacco Exposure Equity Study — Research Report</title><style>' + REPORT_CSS + '</style></head><body><main><div class="eyebrow">INDEPENDENT SECONDARY RESEARCH · REAL CDC DATA</div><h1>Tobacco Exposure<br>Equity Study</h1><p class="subtitle">NHANES 2015–2023 · Prespecified survey analysis · 16 October 2026</p>' + ''.join(parts) + '</main></body></html>'
    (target / "RESEARCH_REPORT.html").write_text(html, encoding="utf-8")
    return {"html": str(target / "RESEARCH_REPORT.html"), "md": str(target / "RESEARCH_REPORT.md"), "analytic_n": n_total, "figures": [p[0] for p in plots]}


REPORT_CSS = """
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#eef1ed;color:#22332f;font:16px/1.65 system-ui,'Segoe UI',sans-serif}main{max-width:1120px;margin:40px auto;padding:64px;background:white;border-top:8px solid #2e6f61}h1{font-size:56px;line-height:1.08;letter-spacing:-2px;margin:20px 0}h2{font-size:25px;margin:44px 0 12px;color:#235e51;border-bottom:1px solid #dce5de;padding-bottom:8px}.eyebrow{font-size:12px;letter-spacing:2px;color:#466e63}.subtitle{color:#526c62;font-size:18px}p{max-width:95ch}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;margin:16px 0}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid #dde4df;vertical-align:top}th{background:#edf3ef}td:last-child{overflow-wrap:anywhere}figure{margin:28px 0}img{width:100%;height:auto}figcaption{font-size:13px;color:#52675e}a{color:#276e75}pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f1;padding:18px}.links{font-size:13px;overflow-wrap:anywhere}@media(max-width:700px){main{margin:0;padding:25px}h1{font-size:40px}}@media print{body{background:white}main{padding:0;margin:0;border:0;max-width:none}h1{font-size:40px}h2{break-after:avoid}figure{break-inside:avoid}a{color:inherit}details{display:none}table{font-size:9px}th,td{padding:5px}p{orphans:3;widows:3}}
"""
