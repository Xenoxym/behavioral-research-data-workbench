"""Reproducible generation, checks, study report, and public-data case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import __version__


def _json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Behavioral Research Data Workbench")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate synthetic study and initialize SQLite")
    demo.add_argument("--output", default="data/demo")
    demo.add_argument("--db", default="data/workbench.sqlite")
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--n", type=int, default=240)
    check = commands.add_parser("check", help="Check a documented CSV bundle")
    check.add_argument("path")
    check.add_argument("--output", default="reports/quality")
    evaluate = commands.add_parser("evaluate", help="Score known injected defects")
    evaluate.add_argument("--data", default="data/demo")
    evaluate.add_argument("--output", default="reports/quality")
    report = commands.add_parser("report", help="Build one-page synthetic study HTML report")
    report.add_argument("--db", default="data/workbench.sqlite")
    report.add_argument("--as-of", default="2026-10-16")
    report.add_argument("--output", default="reports/study_report.html")
    export = commands.add_parser("export", help="Export corrected synthetic tables and audit history")
    export.add_argument("--db", default="data/workbench.sqlite")
    export.add_argument("--output", default="data/exports")
    public = commands.add_parser("nhanes", help="Analyze independent public CDC data")
    public.add_argument("--output", default="reports/nhanes")
    public.add_argument("--cache", default="data/nhanes")
    research = commands.add_parser("research", help="Reproduce the real-data tobacco exposure equity study")
    research.add_argument("--cache", default="data/research/raw")
    research.add_argument("--work", default="data/research")
    research.add_argument("--output", default="reports/research")
    research.add_argument("--offline", action="store_true", help="Require validated cached CDC sources")
    research.add_argument("--prepare-only", action="store_true", help="Collect and audit data without inference")
    research.add_argument("--rscript", help="Explicit Rscript executable; otherwise project-local or PATH")
    args = parser.parse_args()
    if args.command == "research":
        from .research_runner import run_research
        print(json.dumps(run_research(cache_dir=args.cache, work_dir=args.work,
                                     output_dir=args.output, offline=args.offline,
                                     prepare_only=args.prepare_only, rscript=args.rscript),
                         indent=2, default=str))
        return
    if args.command == "nhanes":
        from .nhanes import run_analysis
        print(json.dumps(run_analysis(args.output, args.cache), indent=2, default=str))
        return
    from .schema import load_bundle
    from .quality import check_bundle, evaluate as score
    from .storage import Storage
    if args.command == "demo":
        from .synthetic import generate_demo
        result = generate_demo(args.output, seed=args.seed, n=args.n)
        stored = Storage(args.db).import_bundle(load_bundle(Path(args.output) / "clean"))
        print(json.dumps({"generated": result, "storage": stored}, default=str, indent=2))
    elif args.command == "check":
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        findings = check_bundle(load_bundle(args.path))
        findings.to_csv(output / "findings.csv", index=False)
        _json(output / "check_summary.json", {"findings": len(findings), "severity": findings["severity"].value_counts().to_dict()})
        print(f"{len(findings)} findings -> {output / 'findings.csv'}")
    elif args.command == "evaluate":
        import pandas as pd
        root, output = Path(args.data), Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        findings = check_bundle(load_bundle(root / "dirty"))
        truth = pd.read_csv(root / "truth.csv", dtype=str, keep_default_na=False)
        result = score(findings, truth)
        result["clean_findings"] = len(check_bundle(load_bundle(root / "clean")))
        result["benchmark_kind"] = "synthetic injected defects; predefined rules, not clinical validation"
        result["truth_sha256"] = hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()
        result["definition"] = "Deduplicated (rule_id,table,row_id,field) matches; all severities included."
        findings.to_csv(output / "findings.csv", index=False)
        truth.to_csv(output / "expected_findings.csv", index=False)
        _json(output / "evaluation.json", result)
        pd.DataFrame(result["per_rule"]).to_csv(output / "per_rule.csv", index=False)
        print(json.dumps(result, indent=2))
    elif args.command == "report":
        from .reporting import render_report, build_summary
        bundle = Storage(args.db).load_bundle()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_report(bundle, check_bundle(bundle), args.as_of), encoding="utf-8")
        _json(output.with_suffix(".json"), build_summary(bundle, args.as_of))
        print(str(output.resolve()))
    elif args.command == "export":
        Storage(args.db).export_bundle(args.output)
        print(str(Path(args.output).resolve()))


if __name__ == "__main__":
    main()
