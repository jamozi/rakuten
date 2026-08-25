# ST-1902 — disabled champion/challenger shadow seam

Status: `LOCAL_IMPLEMENTATION_COMPLETE` within the maximum-safe Post-MVP
boundary. Canonical status remains `DEFERRED_POST_MVP`; formal TST-032 remains
`NOT_EXECUTED`.

This Story provides a provider-neutral inward source port, a one-shot
caller-bytes adapter for a sanitized synthetic recording, and a deterministic
shadow evaluator. The output contains only fixed identifiers, hashes, counts,
closed status values, and synthetic integer metrics. It has no content, prompt,
provider response, URL, credential, personal data, review body, finance value,
or arbitrary metadata field.

The feature defaults to `DISABLED`. Local evaluation requires the exact
`RECORDED_SYNTHETIC_SHADOW_ONLY` enum member in `ENV-DEV` or `ENV-CI`. Any
non-zero canary allocation or release-decision input is rejected before the
source port is called. There is no canary/live enum member, activation port,
provider adapter, persistence port, or traffic router.

The exact ST-0708 dependency report is
`REFUSED_INCOMPLETE_EVIDENCE`. Therefore every recorded result keeps the
champion and retains the blockers for missing release evidence, formal TST-032,
and the separate release decision. A schema or zero-tolerance failure can only
pause/reject the recorded challenger more strongly. Even a better synthetic
challenger score cannot change a route, editorial selection, recommendation
order, CTA, article, publication snapshot, public projection, or publication.

## Owner generation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1902_champion_challenger.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1902_champion_challenger.py --check
```

Generated report and manifest files must not be edited by hand. Local checks do
not constitute formal TST-032, live, staging, release, or Production evidence.
