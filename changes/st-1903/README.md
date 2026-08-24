# ST-1903 — maximum-safe disabled partial auto-publication seam

Canonical ST-1903 remains `DEFERRED_POST_MVP`. This implementation is a
provider-neutral, caller-bytes, recorded/synthetic eligibility evaluator. It is
not an approval, Release Decision, publication command, CMS adapter, public
write path, TST-032 evidence, staging validation, or Production readiness.

The default feature scope is exactly `DISABLED`. Its sole executable scope is
`RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY`, accepted only in `ENV-DEV`
and `ENV-CI`. The closed scope has no live, activation, canary, publish, or
release member. Disabled evaluation fails before the inward port is called.

Only two contraction-only metadata classes are representable: suppressing a
stale value and disabling an invalid affiliate CTA. Article bodies, HTML, URLs,
CMS payloads, credentials, provider types, approvals, and release artifacts are
not port values. Any ambiguity, high-risk flag, content/claim/rank/identity/
destination change, new price or stock assertion, personal data, finance input,
or public-write request fails closed.

The current exact ST-1805 dependency is `BLOCKED / NO_DECISION`. Formal
TST-032, a separate human Release Decision, Security/Operations review,
kill-switch safe-state evidence, idempotency and rollback evidence are also
unavailable. The recorded report is therefore
`REFUSED_DEPENDENCY_BLOCKED`. Its outcome vocabulary contains no positive
publication result; all authority flags are false and actions/effects/mutations
are empty.

Generate and verify with:

```bash
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1903_partial_auto_publication.py
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1903_partial_auto_publication.py --check
```

Only the owner generator writes the report and manifest. Local checks are not
formal TST-032, a Human Gate, release, publication, or Production evidence.
