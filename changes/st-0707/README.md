# ST-0707 bootstrap smoke evaluation runner

This Story adds a pure, inward, metadata-only Python smoke evaluator for
caller-constructed immutable bootstrap cases and caller-supplied immutable
measured observations. It performs no provider, network, filesystem,
environment, database, repository, unit-of-work, queue, job, event, thread,
task, subprocess, logging, telemetry, generated-model, runtime, or release
action. No port or adapter is required.

The approved ST-0707 Story depends only on ST-0705 and has
`open_decisions: []`. The current committed ST-0705 source contract, generated
plan, and manifest are bound by these exact SHA-256 values:

- contract: `ea935831a1bb667229ae5a5495a27a801b9c21ab3c3ddbe53e266b8f7c311c42`
- generated plan: `eaa515bfdf5c87cacc434967f4648776f8b05ca5962818c49ed056b52f1e1692`
- manifest: `7266bdba4758bf53b3fde465b9e5d5d6066e0ff44b995e127ab273f36056aed6`

ST-0705 remains non-executable, `UNEVALUABLE`, `NOT_READY`, event-free, and
action-free. This Story does not import or depend on ST-0706.

The canonical design documents `bootstrap_cases_v0.1.jsonl` as 12 tasks by 10
scenarios, or 120 cases, for harness smoke testing only. That committed payload
is absent. This implementation never invents, reconstructs, creates, or claims
binding to those cases. The runner accepts only exact `bootstrap-v0.1` /
`BOOTSTRAP` caller metadata, from 1 through 120 cases, and every report states:

- `BOOTSTRAP_SMOKE_ONLY` and `NON_AUTHORITATIVE`;
- documented bootstrap count 120, with canonical payload binding `false`;
- locked holdout `NOT_LOADED`;
- human labels and Judge calibration `NOT_OBTAINED`;
- threshold, Wilson/statistical evaluation `NOT_PERFORMED`;
- formal TST-018 and TST-019 `NOT_EXECUTED`;
- Story acceptance `false`, release decision `NOT_READY`, and release and
  production eligibility `false`;
- external and action counts exactly zero.

Even an exact 120-case all-pass report is only `SMOKE_PASSED_NON_RELEASE`.
Any deterministic failure or disposition mismatch is `SMOKE_FAILED`; any of
the exact eight canonical zero-tolerance classes takes precedence and yields
`BLOCKED_ZERO_TOLERANCE`. The report contains integer counts and integer
per-check tallies only; it makes no threshold, Wilson, confidence, or other
statistical claim. There is no approve, release, activate, export, persist,
delete, or clear method.

The ordinary advisory run `20260811T140317Z-04e01212c6b2` is recorded only as
the sanitized verified fallback `PRO_UNAVAILABLE_FALLBACK` /
`RESPONSE_NOT_IDENTIFIABLE`, with `submission_attempted: true` and disposition
`CONTINUE_CANONICAL_LOCAL_ONLY`. It supplied no Pro advice or authority and was
not resent, recovered, or imported.

Local checks use pinned uv 0.12.1 with locked, offline, no-cache, no-sync, and
no-env-file options. They are local implementation evidence only. Formal
TST-018/TST-019, real locked or adjudicated datasets, live provider or staging,
human/Judge approval, release, and production remain `NOT_EXECUTED`.
