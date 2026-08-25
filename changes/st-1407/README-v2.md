# ST-1407 recorded external-policy registry V2

Status: `LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY`.

This additive V2 slice closes the maximum safe local portion of ST-1407. It
provides a pure deterministic registry model, a read-only inward exchange, a
bounded DEV/CI recorded adapter, and an application service that independently
re-evaluates every collaborator result. The historical V1 source-derived
reference plan remains unchanged and independently reproducible.

## Implemented local behavior

- One recorded synthetic snapshot is bound to an exact external-rule ID, source
  content hash, explicit acquisition time, explicit review due time, and the
  exact installed external-rule/official-reference/editorial-policy catalogs.
- Snapshot-to-policy version links must be the complete exact `EXT-*` to
  `POL-CONT-*` set from `RAOS-CONTENT-EXTERNAL-001` v0.1. All linked policy IDs
  must exist in the exact 40-policy ST-0805 catalog. A link is reference-only;
  it is not a PolicyBundle, approval, waiver, or activation.
- The impact query intersects those exact changed policy IDs with a complete,
  immutable recorded synthetic article-binding set. A zero result means zero
  only within that exact fixture. Missing, duplicate, unordered, unknown,
  cross-snapshot, or tampered data fails closed instead of becoming zero.
- The domain accepts only the two owner-recorded non-empty article-universe
  hashes. The adapter also requires the exact owner fixture-ID/request-hash
  pair, so a caller-authored self-consistent fixture cannot establish
  completeness or produce a scoped zero.
- Review status is calculated only from caller-supplied exact UTC coordinates.
  Before the explicit time it is `NOT_DUE`, at the exact time it is `DUE`, and
  afterwards it is `OVERDUE`. Catalog prose such as `monthly and event-driven`
  is never converted into a real deadline.
- An overdue evaluation returns a non-deliverable `ALT-019`/`RB-018` candidate
  with `LOCAL_LOG_ONLY`, `NOT_ASSIGNED`, and all delivery, assignment, audit,
  mutation, activation, and publication authorities false.
- Requests and results are deterministic, content-addressed, immutable, and
  redacted. The recorded adapter replays only exact prevalidated bindings; the
  service calls one collaborator once, detects input mutation, rebuilds the
  result independently, and rejects mismatch.

## Deliberately absent authority and I/O

OPEN-018 remains unresolved, so no URL or acquisition input, HTTP client,
browser, redirect, DNS, provider, or arbitrary fetch surface exists. Recorded
synthetic source hashes are not official webpage attestations and are not
claimed current.

OD-008 remains human-controlled. No legal conclusion, legal-review completion,
article change, recommendation change, approval, publication, hold, kill,
rollback, or release authority exists.

OD-011 remains unresolved. There is no notification destination or writer. The
local alert candidate does not assign a reviewer or deliver a notification.
ST-0405 is intentionally not called because this slice makes no authorized
business mutation; audit persistence remains `NOT_EXECUTED`.

There is also no database, API, job, event, ambient clock, filesystem runtime
reader, activation port, live provider, staging, release, or Production path.

## Deterministic fixture ownership

The versioned YAML contract contains two recorded synthetic fixtures: an
overdue affected-article case and a not-due exact-empty case. It contains IDs,
timestamps, policy IDs, and hashes only—no official source body. Its owner
generator verifies every pinned Canonical/dependency byte, the exact 13
external-rule mappings, 12 official-reference records, and 40 policy IDs before
atomically generating the recorded JSON and runtime manifest.
Its ordered role/path/use inventory is closed, and every materially imported
local runtime dependency is hash-pinned; substitutions fail before generation.

```text
.venv/bin/python scripts/build_st1407_external_policy_registry_runtime.py
.venv/bin/python scripts/build_st1407_external_policy_registry_runtime.py --check
```

Focused tests provide local TST-005/TST-020-aligned implementation evidence.
The Canonical Story/master/acceptance sources disagree on the TST-008 and
TST-019 set, so both remain explicit. These tests do not promote formal
TST-005, TST-008, TST-019, or TST-020, live official-source
validation, staging, release, Story `VALIDATED`, or Production readiness.
