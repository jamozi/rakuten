# ST-1904 — disabled recorded multi-category seam

Canonical ST-1904 remains `DEFERRED_POST_MVP`. This implementation reaches only
`LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED`: it validates a provider-neutral
multi-category contract against recorded synthetic bytes. It does not select a
real category, activate a template, resolve identity or freshness rules, or
authorize release.

`DEFAULT_MULTI_CATEGORY_SCOPE` is exactly `DISABLED`. The only other closed
state is `RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY`, executable solely in
`ENV-DEV` and `ENV-CI`. Disabled evaluation fails before calling the inward
port. No live, provider, activation, mutation, or release state exists.

The one-shot adapter accepts exact caller-owned canonical JSON, consumes it at
most once, and rejects duplicate or unknown keys, numbers, noncanonical bytes,
size/hash drift, unexpected bindings, real-category claims, identity decisions,
freshness overrides, active templates, provider/network/persistence flags, and
any publication/release/Production authority. Rejected bytes do not appear in
values, exceptions, logs, or generated evidence.

The two profiles are deliberately synthetic and inactive. Identity remains
`HUMAN_REVIEW_REQUIRED`; automatic merge and split remain false. Freshness keeps
the existing provisional safe default, has no category/provider override,
cannot mark stale evidence fresh, and cannot reorder recommendations. Template
bindings are compatibility candidates only and are never applied.

## Owner commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1904_multi_category.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1904_multi_category.py --check
```

Only the owner generator writes the evaluation and manifest. Local evidence is
not formal TST-032, a category or release decision, staging, Production, or
Canonical Story acceptance.
