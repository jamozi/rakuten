# ST-0703 V4 canonical reconciliation proposal

Status: `PASS_MECHANICAL_REBIND_PROPOSAL_PENDING_EXACT_APPROVAL`
Story: `ST-0703`
Semantic delta from approved V3 D1 through D5: `NONE`
Implementation authority from V4: `NOT_GRANTED`
Formal TST-017: `NOT_EXECUTED`
Live provider, staging, release, and production: `NOT_EXECUTED`

## Exact proposal identity

- V4 handoff proposal:
  `changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v4.yaml`
- V4 handoff proposal SHA-256:
  `7d384015c2975d7a718ff348cb4d1538a354f095cc0d9a2b0c76dbca5f6e4898`
- Current decision source:
  `changes/st-0703/DESIGN-DECISION-REQUEST-v3.md`
- Current decision-source SHA-256:
  `85bb47958a36e994e97cb182589c7e8eb7e20c283476bfd5e823951eea76d76c`
- Current V3 reconciliation source:
  `changes/st-0703/CANONICAL-RECONCILIATION-v3.md`
- Current V3 reconciliation-source SHA-256:
  `3c0629b4c308e316991d64ae49d4a9b002f77dd78afe684c17da7e47d3bca290`
- Superseded historical V3 handoff:
  `changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v3.yaml`
- Historical V3 handoff SHA-256:
  `a510526678190b0512a5d28e016f1ab978469e10cc5063d6a2482f93b6ce43c8`
- Superseded historical V3 approval:
  `changes/st-0703/DESIGN-HANDOFF-APPROVAL-v3.yaml`
- Historical V3 approval SHA-256:
  `df9b39bf9969618a34a58fc0dfab679467ab02a360f22c306d4d408a8ecd5eae`

The current decision request and current V3 reconciliation bytes are
intentional repository-owner inputs. The immutable V3 handoff and approval bind
an earlier decision-source byte identity, so they do not automatically approve
the new V4 bytes. They remain unchanged as superseded historical evidence.

The current V3 reconciliation is rebound as exact provenance evidence. Its
embedded V3 identities describe the earlier approved V3 chain; they are not
substituted for the exact V4 proposal identities above.

## Mechanical rebind result

| Decision | Approved V3 semantics retained by V4 | Semantic delta |
| --- | --- | --- |
| `ST0703-V3-D1` | Closed provider class/status conflict, retryability, sanitation, and raise-from-None rules | `NONE` |
| `ST0703-V3-D2` | Exact content-free canonical exchange schema, validation order, bounds, hash, and artifact disposition | `NONE` |
| `ST0703-V3-D3` | Expiring synthetic quote, exact Decimal formula/context, binding digests, and independent reference recomputation | `NONE` |
| `ST0703-V3-D4` | Owner-generator-only mechanical provenance propagation and semantic-delta stop rule | `NONE` |
| `ST0703-V3-D5` | Exact Make/static/isolated-test/Base-CI wiring with no new workflow, secret, or network authority | `NONE` |

The V4 handoff retains the five existing V3 decision identities. It does not
rename them, add a decision, change a deferred decision, or treat mechanical
rebinding as prospective approval.

## Canonical precedence check

| Evidence | SHA-256 | V4 use |
| --- | --- | --- |
| `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` | `4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d` | ST-0703 scope and dependency boundary |
| `docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml` | `7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b` | recorded TST-017 boundary |
| `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md` | `540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a` | precedence and one-Story implementation protocol |
| `docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml` | `c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8` | fail-closed, secret, logging, provider, and artifact controls |

No canonical scope, architecture, security, approval, or external-runtime gate
changes. The V4 handoff remains limited to the recorded ST-0703 scope and the
same mechanical owner-generated provenance closure.

## Preserved boundaries

- `open_decisions: []` applies only to the fully specified recorded ST-0703
  implementation scope.
- `OD-015` remains unresolved and blocks live provider credentials/evidence.
- `AI-OD-001` remains unresolved and blocks live/production account-data and
  ZDR decisions.
- `AI-OD-008` remains unresolved and blocks production pricing, FX, and budget
  enforcement.
- Formal TST-017, live provider validation, credential or Secret use, staging,
  release, and production remain outside this proposal and unexecuted.
- Protected canonical/upstream/ZIP/status/evidence inputs and the historical V3
  handoff/approval are not modified by this rebind.

## Approval boundary

This file is a reconciliation proposal, not an approval artifact. V4 grants no
implementation authority until the repository owner explicitly approves both
the exact V4 handoff SHA-256 above and this reconciliation file's exact
SHA-256. Only after that approval may a new immutable
`changes/st-0703/DESIGN-HANDOFF-APPROVAL-v4.yaml` record be created and ST-0703
implementation resume within the recorded scope.

An approval does not authorize formal TST-017, a live provider request,
credentials, Secrets, staging, release, publication, or production.
