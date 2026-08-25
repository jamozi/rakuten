# ST-0707 deterministic evaluation runtime

The runtime is a provider-neutral post-validation aggregator. It accepts only a
strict `RecordedEvaluationBundle` loaded from exact content-addressed owner
artifacts. The bundle binds the Canonical suite, locked synthetic dataset,
ST-0705 validation contract, twelve-profile registry, runtime manifest, recorded
fixture, task schema, and the evaluated report identity.

## Integrity boundary

- JSON inputs must be bounded, duplicate-free, and byte-for-byte canonical.
- The owner contract is pinned in code; every generated/dependency artifact is
  hash checked before construction.
- Dataset, case, and holdout identities are independently recomputed.
- The ST-0705 fixture is loaded through its trusted profile registry and
  re-evaluated. Report/profile/manifest/output/provider-exchange hashes must
  match the locked case.
- Frozen objects recompute their anchors before each run/read, so post-load
  mutation is refused.
- Generation uses the shared hardened descriptor-relative publication helper:
  `renameat2(RENAME_EXCHANGE)` for existing targets, no-clobber hardlink
  publication for missing targets, displaced-identity verification, reverse
  verification, rollback, and identity-checked cleanup. Foreign files are never
  enumerated or removed.

## Evaluation boundary

Available ratios contain integer numerator/denominator, point estimate in
millionths, and one-sided 95% Wilson lower bound in millionths. Unavailable
metrics contain no numerator, denominator, point estimate, or Wilson value.
Exact zero-tolerance counts are evaluated separately and never averaged or
waived.

The included dataset is deliberately insufficient for release: one synthetic
plumbing case, only the HOLDOUT split, no labels, no Judge calibration, and no
resolved model binding. The runner can produce only a refusal proposal. It
cannot approve, activate, mutate a route/model, call a model, persist, publish,
release, or change an external system.

Formal TST-018/TST-019, real locked/adjudicated datasets, human review, Judge
calibration, live provider, staging, release, publication, and Production remain
outside this local Story completion.
