# Project agreement

## V2 user steering (supersedes the V1 product emphasis below)

The user found the demo/synthetic-led V1 insufficient and now explicitly wants active,
substantive independent research using entirely real public data collected from original
sources. AI assistance is allowed; the goal is research judgment, not an AI wrapper.
The main UI and new final report must focus on the real-data study. Keep V1 synthetic
operations as a clearly separated legacy artifact, never mix them into research findings.
Use the frozen docs/RESEARCH_PLAN_V2.md, record deviations, preserve all source/analysis
provenance, and report null or contrary results honestly. Continue autonomous parallel
work and milestone GitHub pushes. Original measurements belong to CDC/NHANES; describe
our work as independently collecting public source files and secondary analysis, not
personally recruiting participants or taking samples. R survey may be installed under
project-local .tools for validated traditional survey inference; do not alter global PATH.

## Authorized scope

Build Behavioral Research Data Workbench as a local Python application using pandas,
SQLite, and Streamlit. The user wants the implementation, integration, verification,
and documentation handled autonomously with minimal user involvement. The user has
explicitly authorized parallel subagents when useful; the primary agent owns integration
and final acceptance. Do not create separate user-facing chats merely for subtasks.

The agreed first version includes synthetic screening, baseline, and follow-up data;
data dictionaries; quality checks; follow-up tracking; reasoned corrections with audit
history; CSV exports; a concise report; and an independent public NHANES smoking and
serum cotinine data example. Keep synthetic longitudinal records distinct from real
cross-sectional survey data. Use no hardware, paid APIs, actual participant recruitment,
or real notifications. Install dependencies in a project-local virtual environment.

## GitHub synchronization requested by the user

The user explicitly requires ongoing GitHub synchronization during development.
The verified account is Xenoxym. On implementation start, create or reuse the intended
new repository, proposed name behavioral-research-data-workbench. If creating it without
a visibility instruction, use private visibility. Verify the remote before pushing.

- Commit and push after the initial runnable scaffold and after each coherent milestone
  passes its relevant checks; do not defer all pushes until final delivery.
- Save a truthful progress checkpoint before ending an unfinished implementation turn,
  and push any committed milestone changes. Describe incomplete work accurately.
- After each push, confirm the remote branch points to the expected commit. If pushing
  fails, preserve local commits and report the blocker; never claim synchronization.
- Add appropriate ignore rules before staging. Exclude credentials, virtual environments,
  caches, downloaded raw datasets, local databases, and temporary test artifacts. Track
  synthetic fixtures, source provenance, reproducible download scripts, and appropriate
  evaluation summaries instead.
- Use normal non-forced pushes. Preserve unrelated user changes and existing history.

## Evidence and acceptance

Report actual tested results only. Evaluate quality checks against explicit injected
defects and legitimate special cases; distinguish false positives and false negatives.
Keep raw records, correction reasons, and audit history traceable. Verify persistence,
repeated imports, exports, follow-up denominators, and the complete user workflow.
Deliver reproducible setup/run instructions and portfolio wording that clearly identifies
synthetic operations and public-data analysis. Do not claim real clinical experience or
clinical validation from this project.
