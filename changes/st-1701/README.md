# ST-1701 maximum-safe unresolved MVP business-input boundary

This Story slice provides a deterministic, source-derived registry for the
seven unresolved MVP business inputs owned by ST-1701. It is deliberately a
`NON_AUTHORITATIVE`, interface-only local artifact. It does not resolve an Open
Decision, obtain an approval or external evidence, satisfy ST-1701 acceptance,
make ST-1702 ready, pass a Gate, or authorize any external action.

## Preflight

- Story: `ST-1701` — preserve the maximum-safe unresolved interface while
  OD-001, OD-002, OD-005, OD-006, OD-007, OD-008, and OD-009 remain open.
- Dependency read: canonical `ST-0006`, its owner generator, decision-gate
  policy, blocker report, manifest, README, tests, ExecPlan, and work log.
- Canonical inputs read: integration precedence/boundaries, canonical and open
  decisions, ST-1701/ST-1702 backlog rows, TST-032, and the security control
  catalog.
- Patterns read: the ST-1501 through ST-1506 and ST-1603 source-contract,
  owner-generator, reference-plan, manifest, and hostile-test conventions.
- Open decisions: all seven scoped decisions remain unresolved. OD-006 still
  requires external evidence; the other six still require human decisions.
- Planned files: only this README, the closed source contract, its owner
  builder, one generated JSON registry, one generated manifest, and the four
  isolated ST-1701 test files.
- Migrations: none.
- Tests: deterministic build/check/no-write, exact contract and source parity,
  hostile promotion/drift/path cases, static prohibited-surface checks, Ruff,
  strict mypy, compile/import, focused sensitive-data scan, ST-0006 owner
  `--check`, and Git diff/scope checks.
- Out of scope: choosing business values; performing research; obtaining human
  approval or external evidence; editing canonical/status/debt/predecessor
  artifacts; browser, network, provider, database, staging, publication,
  release, deployment, or Production actions.

## Owned artifacts

| Path | Purpose |
| --- | --- |
| `contracts/unresolved-mvp-business-inputs.v1.yaml` | Closed source contract with exact canonical/predecessor bindings and disabled defaults |
| `generated/unresolved-mvp-business-inputs.v1.json` | Deterministic unresolved registry produced by the owner builder |
| `manifest.yaml` | Generated inventory, hashes, and explicit non-authoritative boundary |
| `../../scripts/build_st1701_business_inputs.py` | Strict validator and atomic owner builder; accepts only optional `--check` |
| `../../tests/st1701/*.py` | Positive, hostile, source-drift, path-safety, no-write, and prohibited-surface coverage |

Generated files must never be hand-edited. From the repository root, use the
pinned offline environment:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1701_business_inputs.py

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1701_business_inputs.py --check
```

The isolated test suite uses the same command prefix followed by
`pytest -p no:cacheprovider -q tests/st1701`.

## Safety and status boundary

The builder invokes the imported ST-0006 owner check in-process before using
the exact byte-bound policy and report; it never shells out. It copies only the
seven canonical source-fact fields as opaque text and preserves the current
global truth: 15 decisions, 14 unresolved blockers, and six blocked targets.
Safe defaults are fallback behavior, never selected values or resolutions.

Category, brand, domain, operator identity, reviewers, labor cost, product
identity rules, freshness SLA, legal boundary, budget, currency, and stop
threshold all remain unset. Synthetic fixtures are the only category input;
external publication remains blocked; labor cost is `UNKNOWN`; human review is
required but unconfigured; stale output is hidden; AI/developer legal judgment
is forbidden; and Production remains disabled.

Activation is `BLOCKED_UNRESOLVED_INPUTS`. GATE-0 through GATE-4 remain blocked,
and all decision, approval, research, external, publication, staging, release,
and Production action counts are exact integer zero. TST-032 and all formal,
live, staging, release, and Production work remain `NOT_EXECUTED`; human
approvals and external evidence remain `NOT_OBTAINED`; canonical status is
unchanged. Local generation/tests establish only partial local implementation
evidence, never `VALIDATED`, acceptance, readiness, or release authority.
