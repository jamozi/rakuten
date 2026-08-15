# ST-1402 — value-free safe-degradation decision boundary

Classification:
`PURE_DETERMINISTIC_RECORDED_DEV_CI_VALUE_FREE_SAFE_DEGRADATION_DECISION`.

This is the maximum safe local ST-1402 slice available while ST-1002 remains
a disabled headless candidate and the Public Read Model mapping, renderer
input, CTA/link surface, notice-copy/DOM contract, and category freshness SLA
remain unavailable. It produces only a closed decision; it does not render,
hide, pause, update, publish, persist, approve, or attest anything.

Canonical Story status remains `NOT_STARTED`, formal verification remains
`NOT_EXECUTED`, and this local implementation does not satisfy TST-020,
TST-021, or TST-028.

## Exact ST-1401 binding

The application requires the complete ST-1401 `FreshnessEvaluationRequest`
and its complete `FreshnessEvaluation`. It reruns the owner
`evaluate_freshness` function and compares the full reconstructed result and
both request/evaluation fingerprints. A caller-supplied hash, internally
consistent-looking forged result, mismatched request/result pair, subclass, or
invalid nested policy binding is not evidence and fails before the decision
port is called.

Accepted evaluations must be exact non-latest ST-1401 safe-default results:

- state `UNKNOWN` with
  `KEEP_LAST_WITH_STALE_STATE_NOT_LATEST`; or
- state `CRITICAL` with `SAFE_DEGRADE`.

Both require `stale=true`, `latest=false`, recommendation ordering
`FORBIDDEN`, persistence `NOT_EXECUTED`, attestation `NOT_ATTESTED`, and live
eligibility false. Fresh and warning results are not degradation inputs.

The inherited policy remains
`PROVISIONAL_CANONICAL_SAFE_DEFAULT` /
`DISABLED_UNRESOLVED_OD_007`. `OD-007` remains
`HUMAN_DECISION_REQUIRED`, inactive, and unresolved. This slice does not
activate ST-1401, choose a category/provider override, or claim that the
provisional threshold is a live SLA.

## Closed value-free decisions

Only the three Canonical dynamic classes with complete, non-value mappings are
accepted:

- `FRESH-001`: emit action `HIDE_VALUE` and notice code
  `FRESH_001_OFFER_PRICE_NOT_LATEST`;
- `FRESH-002`: emit `HIDE_AVAILABILITY_ASSERTION`; only an explicit
  `ALL_PRIMARY_OFFERS_UNAVAILABLE` aggregate additionally emits
  `CTA_PAUSE_CANDIDATE` and `CREATE_REVIEW_CANDIDATE`;
- `FRESH-003`: emit `HIDE_CTA` and `RETAIN_ARTICLE_BODY` only when the bound
  ST-1401 result says the recommendation basis is unaffected. An affected
  basis rejects because this slice has no authorized article-pause renderer.

An ST-1401 review candidate for price or availability is preserved. The
decision never authorizes recommendation reordering. `FRESH-004` through
`FRESH-012` reject rather than extrapolate a renderer policy from prose.

The exact availability aggregate enum and the price notice code are reversible
local interface details following the nearest recorded-domain pattern. They
carry no price, stock, availability assertion, URL, link, notice copy, article
body, HTML, DOM, or payload. They remain subject to integration review before
any future value-bearing renderer contract is designed.

## Trust and execution boundary

- Domain values and failures are immutable, redacted, non-pickleable, and
  exact-type validated.
- The inward port exposes only `decide`.
- Application and recorded adapter construction accept exactly `ENV-DEV` or
  `ENV-CI`; Integration, staging, recovery, and Production fail closed.
- Recorded fixtures bind one exact request fingerprint to one deterministic
  decision fingerprint. Duplicate and unbound requests fail closed.
- The collaborator is called once with a defensive request snapshot. A
  collaborator exception, request mutation, subclass, or different
  shape-valid decision becomes a closed failure code.
- Decisions set renderer effects and persistence to `NOT_EXECUTED`,
  `can_change_state=false`, `publication_authorized=false`, and
  `live_eligible=false`.
- No clock, environment read, filesystem, database, queue, API, provider,
  network, generated contract runtime, public read model, renderer, CTA
  enablement, publication, or external service is used.

This slice adds no schema, generated output, migration, repository, API, job,
event, provider adapter, state store, public route, React/Next component,
status transition, evidence record, release workflow, or Production
capability.

## Owned files

The exact nine owned paths are:

```text
changes/st-1402/README.md
python/raos/domain/freshness/safe_degradation.py
python/raos/application/freshness/safe_degradation.py
python/raos/ports/safe_degradation.py
python/raos/adapters/recorded_safe_degradation.py
tests/st1402/conftest.py
tests/st1402/test_safe_degradation.py
tests/st1402/test_recorded_service.py
tests/st1402/test_boundaries.py
```

## Focused local checks

Run Story and affected predecessor suites in separate processes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st1402
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st1401
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st1403
```

Static checks use the pinned repository environment and exact owned Python
paths:

```bash
/home/minami/rakuten/.venv/bin/ruff check <owned Python paths>
/home/minami/rakuten/.venv/bin/ruff format --check <owned Python paths>
MYPYPATH=python /home/minami/rakuten/.venv/bin/mypy --strict \
  <owned production Python paths>
PYTHONPYCACHEPREFIX=<private temporary directory> \
  /home/minami/rakuten/.venv/bin/python -m py_compile \
  <owned production Python paths>
```

The disabled ST-1002 and ST-1004 Node suites are affected boundary checks;
they remain local headless evidence rather than browser or formal TST evidence.

## Remaining unexecuted work

The authoritative Public Read Model allowlist and projection mapping, actual
Publication Snapshot/AST renderer, value input, notice copy and DOM semantics,
link/URL verification, CTA implementation and kill-switch binding, article
pause behavior, public-isolation runtime proof, browser/accessibility tests,
formal/hosted TST-020/TST-021/TST-028, live/provider tests, persistence,
publication, staging, release, and Production all remain `NOT_EXECUTED` or
unimplemented. No local result is `VALIDATED` evidence.

`PRO_NOT_INVOKED`: the user did not request optional Pro advice. The slice
follows approved Canonical rules and existing ST-1401/ST-1403 repository
patterns without selecting a new policy, security, migration, irreversible,
external-cost, or Open Decision value.
