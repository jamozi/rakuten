# ST-1705 local Pilot security/recovery sign-off decision

This Story owns a deterministic, local-only, non-attesting decision record. It
consumes exact hash-bound predecessor artifacts and deliberately returns only:

- overall decision: `BLOCKED`;
- security and recovery sign-off: `NOT_SIGNED_OFF`;
- Pilot eligibility: `NOT_ELIGIBLE`.

The exact ST-1704 collection contains five tracked article packets. Their local
existence is not evidence that a 5-article Pilot ran, that an article was published,
that a public page was verified, or that revenue was observed. The publication plan
still has five absent immutable snapshots and five `NOT_EXECUTED` public checks. The
affiliate-learning contract contains only a measurement interface; no owner-private
ledger or observation is read by this generator.

ST-1607 is bound byte-for-byte and reports every Gate blocked, fourteen active
blocking Open Decisions, no source freeze/reviewed implementation tree, no human
approval, and formal TST-032 not executed. ST-1705 additionally preserves formal
TST-026 and TST-029 as `NOT_EXECUTED`.

## Owner generation

From the exact physical repository root, with the already synchronized pinned local
environment (generation itself performs no dependency installation or synchronization):

```bash
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1705_pilot_signoff.py

/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1705_pilot_signoff.py --check
```

The default build publishes the decision record and manifest as one recoverable
transaction. A subsequent default build rolls back an interrupted pre-commit
transaction or finishes cleanup after a committed transaction. `--check` is strictly
read-only and refuses pending recovery state.

All bound inputs are captured through descriptor-relative, no-follow reads under a
2 MiB ceiling. JSON and YAML duplicate keys are rejected. Fixed output companions,
unsafe ancestors, symlinks, hardlinks, unexpected modes, ambiguous transaction state,
and target races fail closed.

## Future evidence input port

`contracts/pilot-signoff-evidence-input.v1.schema.json` defines a closed shape for a
future independently authorized formal evidence pipeline. The current contract binds
that schema but sets the input URI to `null`, activation to `DISABLED`, and default
decision to `BLOCKED`. This generator has no CLI option or dynamic path that can load
formal evidence. Merely creating a schema-shaped file cannot grant eligibility.

## Authority boundary

This implementation performs no network or provider call, reads no environment value
or credential, and offers no status, Gate approval, publication, staging, release,
deployment, or Production action. Formal TST-026/TST-029/TST-032, hosted CI, security
review, backup restore, source freeze, reviewed implementation tree, human approval,
live Pilot, publication, staging, release, and Production remain `NOT_EXECUTED`.
