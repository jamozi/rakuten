# ST-0703 V5 D5 canonical reconciliation proposal

Status: `PASS_D5_CORRECTION_PROPOSAL_PENDING_EXACT_APPROVAL`

Story: `ST-0703`

Implementation authority from V5: `NOT_GRANTED`

Formal TST-017: `NOT_EXECUTED`

Live provider, staging, release, and production: `NOT_EXECUTED`

## Exact proposal identity

- V5 decision request:
  `changes/st-0703/DESIGN-DECISION-REQUEST-v5.md`
- V5 decision-request SHA-256:
  `e2cec557d0c412effd5ae4a7fa7d1069ff46579caada980a9c8dd7479a6a51cd`
- V5 handoff proposal:
  `changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v5.yaml`
- V5 handoff proposal SHA-256:
  `ac8afef5f18b4602c099d27ad7f86f3880acb28be5e57badc47d45b27c3abe97`
- Prior approved V4 handoff:
  `changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v4.yaml`
- Prior approved V4 handoff SHA-256:
  `7d384015c2975d7a718ff348cb4d1538a354f095cc0d9a2b0c76dbca5f6e4898`
- Prior V4 reconciliation SHA-256:
  `6c3285712156781c9a107dfb5417f87896246c75e3158fec485f1ea07be54887`
- Prior V4 approval SHA-256:
  `ed717125191c26dc609c61341320f020be7883add1f0967096b20d11e60eb202`

V3 and V4 authority artifacts remain immutable. V5 is an append-only
replacement authority proposal for D5 only.

## Fixed-ref evidence

- Candidate commit:
  `f251edb31c52c775c46bcca8f4af26f6d8cdb5eb`
- Comparison base:
  `48a807672caa845df8e0251782f00bce8040663b`
- Base Makefile target header:
  `config-check: | python-sync`
- Candidate Makefile target header:
  `config-check:`
- Candidate V4 composite:
  `openai-recorded-gate` names `config-check` as a prerequisite.

The base/candidate comparison confirms that removing the `python-sync`
prerequisite and changing the ST-0204 README statement are semantic ST-0204
command-contract changes. V4 permits only ST-0204 manifest regeneration, not
that semantic change.

The implementation worker stopped before editing when the contradiction was
observed.

## Local owner-check evidence

`UV_READONLY_RUN` is defined as locked, offline, no-cache, no-sync,
no-env-file, and no-python-downloads after clearing inherited uv and Python
override inputs.

`scripts/build_st0204_config_loader.py --check` calls `check_generated`, renders
the expected ST-0204 schema and manifest bytes, and compares existing regular
files. Only the non-check path calls `install_generated`. The direct `--check`
operation is therefore the existing owner-controlled read-only check required
by the corrected ST-0703 gate.

## Decision reconciliation

| Decision | V5 result | Semantic delta from approved V4 |
| --- | --- | --- |
| `ST0703-V3-D1` | Preserved byte-for-byte in the decision model | `NONE` |
| `ST0703-V3-D2` | Preserved byte-for-byte in the decision model | `NONE` |
| `ST0703-V3-D3` | Preserved byte-for-byte in the decision model | `NONE` |
| `ST0703-V3-D4` | Preserved byte-for-byte in the decision model | `NONE` |
| `ST0703-V3-D5` | Replaced by `ST0703-V5-D5-CORRECTION` | `CORRECTED` |

The corrected D5 restores the ST-0204 target and README to base semantics,
removes `config-check` from the ST-0703 composite prerequisites, and adds one
direct `UV_READONLY_RUN` invocation of the existing ST-0204 owner generator
with `--check`.

Hydration remains an explicit operation performed before the read-only gate.
The gate cannot invoke `python-sync`, `UV_RUN`, sync, install, hydrate,
recursive Make, network, cache synchronization, environment credential access,
live provider calls, or an external service.

## Canonical precedence check

| Evidence | SHA-256 | V5 use |
| --- | --- | --- |
| `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` | `4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d` | ST-0703 scope and dependency boundary |
| `docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml` | `7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b` | recorded TST-017 boundary |
| `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md` | `540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a` | precedence and one-Story protocol |
| `docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml` | `c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8` | fail-closed AI/provider controls |

Option 2 is the minimal canonical-aligned closure. It introduces no second
semantic Story, no new provider or credential capability, no generated-file
hand edit, and no runtime or production authority.

## Preserved PR and runtime boundaries

- Exactly one semantic Story: `ST-0703`.
- Final ST-0204 Make target, README, generator, contracts, tests, and schema
  semantics remain base-identical.
- Only owner-generated metadata-only manifests for ST-0204, ST-0701, and
  ST-0801 may accompany ST-0703.
- ST-0106, ST-0107, ST-0202, ST-1203, and ST-1204 remain outside the PR.
- ST-1203/ST-1204 predecessor debt remains unresolved and unwaived.
- `OD-015`, `AI-OD-001`, and `AI-OD-008` remain unresolved external decisions.
- Formal TST-017, live provider validation, credentials, production pricing,
  staging, publication, release, and production remain outside this proposal.

## Approval boundary

This reconciliation and the V5 handoff are proposals. They grant no
implementation authority until the repository owner explicitly approves both
exact SHA-256 values. Only after that approval may an immutable
`changes/st-0703/DESIGN-HANDOFF-APPROVAL-v5.yaml` record
`ST0703_RECORDED_SCOPE_ONLY` and implementation resume.
