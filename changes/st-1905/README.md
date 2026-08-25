# ST-1905 — disabled advanced rank-provider seam

Status: `LOCAL_IMPLEMENTATION_COMPLETE` within the maximum-safe Post-MVP
boundary. Canonical status remains `DEFERRED_POST_MVP`; formal TST-032 remains
`NOT_EXECUTED`.

## Preflight and authority

- Story/objective: `ST-1905`, “承認済みProvider連携”.
- Read inputs: repository and Canonical implementation rules, integration
  precedence and decisions, ST-1905 plus dependency ST-1206, analytics design,
  keyword-rank/provider dispatch schemas, TST-032, security/privacy design,
  SEC-APP-001/005, SEC-DATA-003/004/007, SEC-INFRA-003,
  SEC-SDLC-006/009, and THR-005/010/020/022/025/027/030.
- Open decision: OD-004 remains `HUMAN_DECISION_REQUIRED`; no provider, terms,
  API version, endpoint, account, credential, quota, or release decision has
  been selected. The Canonical safe default remains Search Console plus manual
  CSV.
- Owned files: additive `changes/st-1905/**`, one domain module, one inward
  port, one application service, one caller-bytes recorded adapter, one owner
  generator, one work log, and `tests/st1905/**`.
- Out of scope: provider choice or SDK, arbitrary HTTP/URL, credentials, SERP
  scraping, filesystem discovery, database/queue/event, KPI or tracking writes,
  recommendation/editorial mutation, public projection, publication, formal
  TST-032, live/staging validation, release, and Production.

## Maximum-safe local implementation

The domain port accepts only RAOS values and returns an immutable batch whose
rows are ST-1206 `KeywordRankObservation` values. The current outward adapter
accepts one exact caller-supplied canonical JSON recording, exactly once. It
does not open a path, read configuration, use a provider SDK, or contact a
network. Unknown fields, duplicate JSON keys, floats, non-canonical encoding,
duplicate provider/canonical identities, invalid ST-1206 rows, source drift,
and period drift fail closed with a fixed code. Rejected input is never retained
in the error.

`DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE` is exactly `DISABLED`. The only other
enum member is `RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY`, accepted solely in
`ENV-DEV` or `ENV-CI`. The feature vocabulary has no selected-provider, live,
canary, or activation state. Provider-approval and release-decision hashes are
explicitly rejected rather than interpreted as authority.

The deterministic report proves only that six synthetic sanitized rows map to
the ST-1206 canonical value boundary. It contains fixed identifiers, hashes,
counts, period bounds, and closed status values. It cannot activate a provider,
write a KPI, enable tracking, influence recommendation order, change content,
publish, release, or write Production state. Finance and affiliate performance
values are not represented.

## Owner generation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1905_advanced_rank_provider.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1905_advanced_rank_provider.py --check
```

Only that owner writes
`changes/st-1905/generated/advanced-rank-provider-report.v1.json` and
`changes/st-1905/manifest.yaml`. Local evidence is not formal TST-032, live,
staging, release, Production, or Story-acceptance evidence.
