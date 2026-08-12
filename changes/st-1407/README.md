# ST-1407 external policy registry reference plan

This Story slice installs a deterministic, source-derived reference plan for
the approved ST-1407 external policy change registry. It projects the exact
installed `RAOS-CONTENT-EXTERNAL-001` v0.1 catalog (13 external rules), the
exact `RAOS-CONTENT-REF-001` v0.1 catalog (12 official references), and every
canonical `EXT-*` to `POL-CONT-*` mapping. The generator verifies the installed
source bytes against their pinned SHA-256 values before producing output.

This is deliberately a non-executable and non-attesting boundary. It is not a
live official-page snapshot, a registry service, an impact query, an overdue
calculation, an alert, an audit record, or evidence that ST-1407 acceptance has
passed.

## Authority and unavailable design assistance

The approved Story names ST-0405 and ST-0805 as predecessors, FR-017 as its
requirement, `policy snapshot` and `impact query` as deliverables, and `overdue
alert` plus `version links` as acceptance criteria. The canonical sources do
not define the cross-aggregate relationships or lifecycle rules needed to
implement those runtime outcomes safely.

The gated Pro workflow produced no captured proposal. No response content is
used here. The plan records only the permitted high-level `PRO_UNAVAILABLE`
state, no authority, no captured proposal, and no content use. Private run
identity, transport state, generic refusal, and recovery-only diagnostics are
not persisted or projected through these tracked Story artifacts.

## Closed boundary

- The external-rule snapshot is a curated installed contract, not captured
  official webpage bytes. Its contract hash must never be described as the
  hash of a current official page.
- `evidence.source_snapshot`, `policy.policy_bundle`,
  `publishing.publication_snapshot`, `ops.alert`, and `ops.audit_event` remain
  distinct, unlinked candidate seams. An external snapshot is not identified
  as a PolicyBundle.
- Official-reference records are projected independently. The implementation
  does not infer links between their `REF-*` IDs and the `EXT-*` catalog.
- `monthly and event-driven` is preserved as inert catalog text. It is not
  converted into a deadline. Due and overdue remain `NOT_EVALUATED`.
- Snapshot instances, official content bytes, diffs, join records, bundle and
  rule-version links, publication-version links, impact results, alert records,
  and audit events are empty. In particular, `affected_articles: []` means
  `QUERY_NOT_EXECUTED_NOT_ZERO_AFFECTED`; it never asserts zero affected
  articles.
- ALT-019 remains inert `SEV4` catalog text. The generic alert model's P0-P3
  vocabulary has no approved mapping here. RB-018 steps are also inert text.
- OPEN-018 (primary source domain allowlist), OD-008 (legal review boundary),
  and OD-011 (notification channels) remain unresolved or human-gated. Their
  safe defaults remain restrictive.
- No network or runtime filesystem reader, database, API, job, event, provider,
  ambient clock, alert writer, audit writer, activation, notification, hold,
  kill, re-review, publication, or external action is implemented.

ST-0405 currently supplies only a process-local recorded audit seam and is not
called. ST-0805 supplies a pure local editorial policy evaluator and no
authoritative PolicyBundle identity; it is not called. Canonical activation,
publication, hold, kill-switch, and legal interpretation remain human-controlled.

## Trace and verification boundary

The source package contains an existing traceability divergence which this
Story records without resolving:

- ST-1407 lists TST-005 and TST-020.
- Master FR-017 traceability lists TST-005, TST-019, and TST-020.
- Acceptance FR-017 traceability lists TST-008 and TST-020.

The focused tests in `tests/st1407` validate only deterministic local source
projection, strict rejection, generation, and the inert boundary. Formal
TST-005, TST-019, and TST-020 remain `NOT_EXECUTED`; this slice also makes no
formal TST-008 claim. Live, staging, release, Production, Story acceptance, and
Production eligibility all remain `NOT_EXECUTED` or false.

Generated files are owned exclusively by:

```text
uv run --locked --no-sync python scripts/build_st1407_external_policy_registry_reference_plan.py
uv run --locked --no-sync python scripts/build_st1407_external_policy_registry_reference_plan.py --check
```

Local generation and focused tests provide implementation evidence only. They
do not revalidate any official source, establish a current policy snapshot,
execute an affected-article query, emit an overdue alert, create version links,
or satisfy ST-1407 acceptance.

The repository-approved pinned uv 0.12.1 wrapper was available for the
read-only `contract-gate`, but this linked worktree did not have an already
hydrated project `.venv`. The wrapper's first offline `uv run --no-sync`
created an empty disposable `.venv` and failed before the contract check with
`ModuleNotFoundError: No module named 'yaml'`; that disposable directory was
removed. No install, sync, hydrate, network access, retry, or guard relaxation
was performed. The exact unmet prerequisite is an already hydrated locked
project environment containing PyYAML for the pinned interpreter, so
`contract-gate` remains `NOT_EXECUTED` rather than failed product evidence.
