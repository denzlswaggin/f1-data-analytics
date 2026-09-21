# Important audit findings: corrections before feature expansion

Branch: `fix/important-audit-findings`, based on `main`. The separate
`feat/evidence-backed-insights` branch is preserved; new Cockpit findings and
direct teammate battles are not part of this correction branch.

## Requirements

1. Keep pit-timing scenarios explicitly experimental. Remove promoted timing-gain
   headlines and stop recommendations. Show eligible/analysed counts and boundary
   minima while retaining conditional scenario diagnostics and exclusions.
2. Align rating claims with actual static/dynamic resampling units. Individual
   rating intervals do not establish exact-rank probabilities or isolate talent.
3. Put paired Saturday/Sunday uncertainty in the primary display, distinguish
   missing intervals from intervals crossing zero, and avoid specialist labels.
   Explain the exploratory nature of screening multiple drivers.
4. Generate current evidence counts from the verified snapshot and distinguish
   those counts from dated historical diagnostics. Refresh README statistics
   without rewriting historical reports as current evaluations.
5. Preserve and test missing-versus-zero, censored-versus-exact, partial-field and
   failed-publication safeguards. Publish no accuracy claim from passing tests.

## Pit-timing promotion gate

The 18 September diagnostic evaluates a fitting component, not complete strategy
accuracy: 1.136 s MAE versus 0.652 s for a training-median baseline. It does not
justify selecting a more attractive model after inspecting the same holdout.
The current release leaves the estimator unchanged and removes recommendation
framing from its presentation.

Before any future promotion, freeze the model, cohort, exclusions, metrics and
baseline before observing a new race holdout. Evaluate observable held-out pace
targets with race-clustered uncertainty and report coverage and failures as well
as errors. Training must precede evaluation. An improvement in that component
does not establish the unobserved outcome of a different stop: a separate,
explicit identification argument and calibrated uncertainty are required before
causal or optimal-strategy claims. No passed publication check waives this gate.

## Completion evidence

| Finding | Implemented correction | Verification |
| --- | --- | --- |
| Pit-timing readiness | Experimental headline and navigation; no promoted largest gain; live model-scope counts; conditional diagnostics and explicit promotion gate | Executed overview query covers eligible/interior/boundary/excluded/empty cases. Pit-model and publication tests pass. Browser checks exercise an eligible interior stop. |
| Rating certainty | Static edge resampling and dynamic weekend resampling are distinguished in the UI and docs; exact-rank certainty and equal-car experiment claims removed | Samplers inspected directly; rating/backtest tests pass. Published rating values and snapshot are unchanged. |
| Saturday/Sunday uncertainty | Primary paired-interval chart, zero reference, neutral directional labels, unavailable/inconclusive states and multiple-driver screening caveat | Executed serving/page queries test positive, negative, crossing/touching zero, missing, invalid and insufficient-draw intervals. Coverage now uses the published profile scope. Browser checks show Gasly and Hamilton with their intervals. |
| Stale evidence reports | Atomic snapshot-bound audit export; current counts and historical diagnostic records separated; generated README statistics | Hash/version mismatch and missing/historical-artifact tests pass. README block matches the export. Current counts come from the snapshot, not copied historical reports. |
| Publication safeguards | Existing missing/zero, censored/exact, partial-field and snapshot rollback rules retained; empty chart rendering guarded | Full Python suite includes negative publication tests. All 45 serving checks, processing integrity and 12 metric/robustness checks pass. Snapshot SHA-256 is unchanged. |

The audit export contains ten metric coverage summaries, three dataset-size rows
and four separately scoped validation records. It opens the snapshot read-only,
verifies the adjacent manifest hash and embedded version, and checks again before
atomically replacing `data/dashboard/audit-evidence.parquet`. A failed export
leaves the previous artifact intact and prevents source preparation from proceeding.

The page reports all loaded pit-model seasons from 2024, currently 85 eligible
transitions out of 2,197, with 73 eligible boundary minima. The general evidence
table includes the full snapshot and labels its separate units and denominator.
Saturday/Sunday's badge describes published profiles; unavailable independent
weekend counts and latest input-event dates remain blank rather than borrowing
the broader warehouse's scope.

## Verification and reproduction

Verified on 21 September 2026 against `20260918-audit-pages34`, SHA-256
`6b320289160b54308d126d40ddc0b9f4878e60a7fa64162c8c61a2d082e57f30`.
The complete Python suite passed: 822 tests. Targeted Mypy, Ruff, strict Evidence
build and all 52 serving queries passed. The clean production bundle is about
108 MB, with a 37.5 MB largest file, within the existing 275/60 MB limits.

The 21-route browser smoke test and the audit-specific browser test run at
1440px and 390px. Screenshots under the ignored
`data/important-audit-findings/` directory support visual review. The browser
test checks eligible pit scenarios, paired uncertainty, missing validation,
rating claims and homepage evidence navigation, including console and overflow
checks. It caught an empty-chart loading state, now guarded in both analytical
pages. The smoke test uses the existing “Data & methodology” label.

```bash
.venv/bin/python -m pytest --no-cov
F1_DUCKDB_PATH=data/dashboard/latest.duckdb .venv/bin/python scripts/check_dashboard_data.py --scope serving
npm --prefix dashboard run build:strict
.venv/bin/python scripts/check_dashboard_bundle.py dashboard/.evidence/template/build --max-total-mb 275
PLAYWRIGHT_CHANNEL=chrome node scripts/test_important_audit_findings.mjs
PLAYWRIGHT_CHANNEL=chrome node scripts/test_dashboard_smoke.mjs
```

The browser commands expect a production preview at
`http://127.0.0.1:4174/f1-data-analytics`. Restart preview after rebuilding so it
loads the new asset manifest. Evidence may accumulate old assets in its copied
root output; use the clean template build for the size check and final output.

Regenerate the README statistics explicitly with
`.venv/bin/python scripts/export_audit_evidence.py --update-readme`. Normal
source/build hooks refresh serving evidence without editing the README. Historical
reports retain their original evaluated snapshots and limitations. None of these
checks claims improved predictive or counterfactual strategy accuracy.
