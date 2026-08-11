# ST-0708 — OpenAI live bounded evaluation reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_OPENAI_LIVE_BOUNDED_EVALUATION_REFERENCE_PLAN`

This implementation-first slice is partial, non-authoritative, local-only,
non-executable, interface-only, and runtime-ineligible. It records the maximum
safe ST-0708 boundary while OD-015 remains unresolved and blocking. Its safe
default is exactly `RECORDED_FIXTURE_ONLY` (`Recorded fixtureのみ`). It is not a
live evaluator, a runnable command, a provider observation, a release decision
candidate, or formal TST-018 evidence.

## Closed reference boundary

- The plan binds the current committed ST-0707 bootstrap-smoke implementation
  and ST-0703 recorded adapter implementation by exact repository paths and
  SHA-256 digests.
- ST-0707 remains `BOOTSTRAP_SMOKE_ONLY` and `NON_AUTHORITATIVE`. The canonical
  bootstrap payload is unavailable and unbound, the locked holdout is
  `NOT_LOADED`, formal TST-018/TST-019 remain `NOT_EXECUTED`, and even a local
  smoke pass cannot authorize a release.
- ST-0703 remains recorded-only. It contributes no credential resolution,
  account selection, live-provider authorization, live retry, live execution,
  release approval, or Production readiness to this Story.
- No candidate task, risk profile, prompt, output schema, route, model,
  provider, application artifact, or artifact SHA-256 is selected.
- No approved, locked, or adjudicated dataset identity, version, digest, split,
  holdout, or observed case count is claimed. The absent bootstrap payload is
  not reconstructed or treated as evaluation data.
- No risk-specific threshold, zero-tolerance selection, statistical method,
  runner, command, environment, account, endpoint, credential, request,
  response, report, provider request ID, cost, latency, quota, or timestamp is
  configured or observed.
- Empty observations and findings mean `NO_EXECUTION_EVIDENCE`, not successful
  execution, zero failures, threshold satisfaction, or release eligibility.

The generated JSON is produced only by the strict fixed-path owner builder. It
contains reference-plan and boundary metadata only. The builder cannot read
process environment, resolve a credential, contact a provider, invoke the
ST-0703 adapter, run ST-0707, write a repository/database/job/event artifact,
or approve, activate, or release anything.

## Safety and completion boundary

Activation is disabled. Provider, network, credential, filesystem, repository,
database, job, event, release, staging, and Production actions are forbidden or
`NOT_EXECUTED`. Every action count is an exact built-in integer zero and the
external action list is empty. There is no run, apply, approve, activate,
promote, deploy, or release command.

Formal TST-018, live and staging evaluation, human labels, Judge calibration,
security, data, policy, canary, rollback, and monitoring evidence remain
unexecuted or unobtained. The decision is `NOT_READY`; Story acceptance,
release-candidate status, release eligibility, and Production eligibility are
false. Local generation and pytest do not change canonical implementation or
verification status and do not authorize a live-provider request.

## Owner generation

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py \
  --check
```
