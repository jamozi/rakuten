# RAOS Complete Design Package v1.0

**Baseline:** 2026-07-30  
**Design:** COMPLETE / APPROVED FOR IMPLEMENTATION  
**Product implementation:** NOT STARTED  
**Runtime validation:** NOT EXECUTED  
**Production readiness:** NOT READY

## Start here

1. [`RAOS_design_completion_status_v1.0.md`](RAOS_design_completion_status_v1.0.md)
2. [`RAOS_implementation_status_registry_v1.0.yaml`](RAOS_implementation_status_registry_v1.0.yaml)
3. [`RAOS_unimplemented_register_v1.0.csv`](RAOS_unimplemented_register_v1.0.csv)
4. [`../01_integration/RAOS_07_integration_design_v1.0.md`](../01_integration/RAOS_07_integration_design_v1.0.md)
5. [`../07_backlog/RAOS_13_story_backlog_v1.0.yaml`](../07_backlog/RAOS_13_story_backlog_v1.0.yaml)
6. [`../08_codex/RAOS_14_CODEX_MASTER_KICKOFF_v1.0.md`](../08_codex/RAOS_14_CODEX_MASTER_KICKOFF_v1.0.md)

Package rootにもCodex discovery用の`AGENTS.md`、`PLANS.md`、`CODEX_KICKOFF.md`を配置している。

## Canonical folders

| Folder | Purpose |
|---|---|
| `00_master` | 状態、未実施、Traceability、引渡し |
| `01_integration` | 正本優先順位、採用差分、Open decisions |
| `02_ui` | Admin/Public UI/UX、画面、Component、a11y |
| `03_analytics` | Event、KPI、成果帰属、Dashboard |
| `04_security` | IAM、Security、Privacy、Threat、Control |
| `05_test` | Test Suite、Environment、Acceptance、Release evidence |
| `06_ops` | SLO、Alert、Runbook、Backup/Restore |
| `07_backlog` | 20 Epic、129 Story、Critical path |
| `08_codex` | AGENTS、ExecPlan、Prompt、PR template |
| `09_references` | 公式参照Snapshot |
| `upstream` | 既存6設計Package、主要文書、採用Patch |

## Status source of truth

- Project/subsystem/environment/provider: `RAOS_implementation_status_registry_v1.0.yaml`
- Story: `../07_backlog/RAOS_13_story_backlog_v1.0.yaml`
- Runtime test: `../05_test/RAOS_11_test_suite_catalog_v1.0.yaml`
- Human/external decisions: `../01_integration/RAOS_07_open_decisions_v1.0.yaml`
- Combined outstanding work: `RAOS_unimplemented_register_v1.0.csv`

## Important boundary

`APPROVED_FOR_IMPLEMENTATION` means Codex can implement the design. It does not mean code exists, tests ran, providers were connected, legal review passed, or the system can be published.
