# RAOS implementation-first deferred verification ledger

This ledger supports the owner-approved
`docs/execplans/RAOS-IMPLEMENTATION-FIRST.md`. It records work that may be
deferred during local feature implementation but must be reconciled before
`LOCAL_INTEGRATION_COMPLETE`.

It is not canonical status, formal evidence, a waiver, or production
readiness. Entries are append-only in identity: do not delete or reuse an ID.
Close an item by adding dated closure evidence to the same entry.

## Required entry fields

- ID and status: `OPEN`, `IN_PROGRESS`, `CLOSED`, or `EXTERNAL_BLOCKED`.
- Introduced by Story/commit or inherited fixed snapshot.
- Exact failing or skipped command and sanitized observed result.
- Runtime/safety impact.
- Affected source, owner generator, generated artifacts, and downstream pins.
- Closure Wave and acceptance evidence.
- Formal/live boundary when applicable.

## Initial ledger

### DEBT-W0-001 — ST-0703 direct runtime pin and provenance fan-out

- Status: `OPEN`.
- Introduced by: ST-0703 local implementation candidate based on approval
  checkpoint `4e0a75f658c08a8d124255b522d23e59ac457163`.
- Evidence:
  - `pyproject.toml` and `uv.lock` require `openai==2.52.0`.
  - Base-byte `tests/st0102/test_toolchain_contract.py` lacks the matching
    direct-runtime requirement and pin entries.
  - Exact ST-0102 wrapper result: `3 failed, 45 passed`.
  - Direct isolated parent confirmation: `2 failed, 27 passed, 19 skipped`;
    the skips are exact-uv discovery cases not run through the wrapper.
- Required source closure: add the exact sorted requirement
  `openai==2.52.0` and pin `openai: 2.52.0` to the ST-0102 inventory.
- Provenance impact: the source is tracked by ST-0801, ST-0703, and ST-0301;
  ST-0301 then participates in ST-0302/ST-0303/ST-0307 and later hash chains.
- Safety impact: no live/provider/credential/production path; local contract
  and generated provenance are stale until closure.
- Closure Wave: source update in W0/W1; complete downstream owner regeneration
  in the final source-to-owner audit unless an earlier Wave freeze can close it
  without semantic changes.
- Acceptance: ST-0102 exact wrapper green, all affected owner no-write checks
  green, semantic projections unchanged except the approved direct pin, and no
  hand-edited generated file.

### DEBT-W0-002 — ST-1203/ST-1204 predecessor provenance debt

- Status: `OPEN`.
- Inherited from: fixed WIP audit at
  `1ced6434907c95ad063a472dc81644f8f00e4cce`.
- Evidence: ST-1203 and ST-1204 each reported four predecessor-hash failures;
  partial ST-0204 repair was explicitly rejected because an independent stale
  ST-0305 pin also exists.
- Safety impact: recorded/live analytics adapter readiness and production
  readiness remain blocked; no reason to block dependency-independent local
  implementation.
- Closure Wave: W2 source freeze or final audit, through each Story's owner
  contract/generator and complete predecessor reconciliation.
- Acceptance: no partial pin edit, both owner checks and isolated suites green,
  and live/provider validation remains separately classified.

### DEBT-W0-003 — synthetic security-fixture scanner classification

- Status: `OPEN`.
- Inherited from: fixed WIP audit at
  `1ced6434907c95ad063a472dc81644f8f00e4cce`.
- Evidence: six unchanged `GENERIC_CREDENTIAL` findings in synthetic security
  test material and zero new WIP finding groups.
- Safety impact: no evidence that the WIP added a credential, but the scanner
  gate cannot be called green and must not be weakened with a broad exclusion.
- Closure Wave: W5 security-verification work or final audit.
- Acceptance: content-addressed path/rule/fixture-digest classification,
  mutation tests proving new/changed credentials still fail, no matched value
  printed, and full worktree/history scan green under the approved policy.

### DEBT-W0-004 — formal and external verification boundary

- Status: `EXTERNAL_BLOCKED`.
- Inherited from: canonical status overlay and ST-0703 authority chain.
- Deferred work: formal TST/hosted CI where absent, live providers,
  credentials/Secrets, real external accounts, staging, real pilot/observation
  periods, human business/security/release decisions, publication, deployment,
  and production.
- Safety impact: local code may progress, but none of these states may be
  represented as executed, validated, deployed, or production-ready.
- Closure Wave: outside automatic local implementation unless separately
  authorized and actually executed.

### DEBT-W0-005 — unresolved canonical Open Decisions

- Status: `EXTERNAL_BLOCKED`.
- Source: `docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml`.
- Rule: implement only documented safe defaults, provider-neutral interfaces,
  synthetic/recorded fixtures, and default-disabled activation. Never invent a
  category, brand/domain, attribution method, cost/labor value, identity
  threshold, freshness SLA, legal decision, provider/credential choice,
  region, retention policy, or production activation.
- Closure Wave: individual decisions remain external until their named human
  owner supplies and approves the value.

## Concurrent ownership reservation

At creation time, another Codex owns ST-0101 resilient Pro-runtime work,
including `AGENTS.md`, `docs/worklogs/ST-0101.md`,
`scripts/chatgpt_pro_orchestrator.py`, and
`scripts/chatgpt_pro_mcp_runtime/**`. These paths are neither debt nor part of
ST-0703. Preserve them and serialize any root-policy integration after that
owner's checkpoint.

## Closure log

Append dated closure records here. A closure record must name the debt ID,
commit, commands, results, regenerated owners, reviewer, and remaining formal
boundary. Do not replace failure evidence with a summary that hides the
original result.

### 2026-08-10 W0 / ST-0703 implementation preflight

- Story and objective: finish the approved `ST-0703` recorded-only OpenAI
  Responses adapter under Wave W0 without live-provider, credential, routing,
  pricing-source, publication, release, or production activation.
- Authority and dependencies read: the root and canonical Codex instructions,
  the owner-approved implementation-first ExecPlan, `ST-0204`, `ST-0701`, and
  `ST-0703` backlog rows, `TST-017`, `SEC-AI-001` through `SEC-AI-008`, and the
  exact V5 handoff, reconciliation, and approval chain.
- Authority result: handoff SHA-256
  `ac8afef5f18b4602c099d27ad7f86f3880acb28be5e57badc47d45b27c3abe97`,
  reconciliation SHA-256
  `65021265c8c5bd40bd8949eb876542e53400333bb615794d67418975873d6ac3`,
  implementation authority `ST0703_RECORDED_SCOPE_ONLY`, and
  `open_decisions: []` all match.
- Ambiguities: none requiring a new design or policy decision. The approved
  ExecPlan explicitly permits closing the ST-0102 direct-pin inventory source
  mismatch and deferring unrelated transitive provenance fan-out.
- Planned owned changes: ST-0703 source, contract, generator, generated output,
  tests, Makefile and README sections; the exact ST-0102 pin inventory fix;
  owner-generated metadata-only ST-0204/ST-0701/ST-0801 manifests; and seeded
  base-byte cleanup of excluded Story semantic paths.
- Planned checks: ordered owner regeneration and no-write checks; isolated
  ST-0703/ST-0204/ST-0701/ST-0801 suites; exact ST-0102 wrapper; Ruff, format,
  strict mypy, canonical import, workspace drift, sensitive-data/network
  boundaries, `git diff --check`, and base/staged scope audits.
- Out of scope: ST-0301+ fan-out closure, ST-1203/ST-1204 repair, the synthetic
  security-fixture classification baseline, formal TST/hosted CI, live provider
  or credential use, staging, publication, release, deployment, and production.

### 2026-08-10 W0 / ST-0703 checkpoint evidence

- Implementation commit: `aff94a21ac9f03886b19e32fef6e1c8b16de5b95`.
- Local verifier: project `implementation_worker`; integration reviewer: root
  Codex integration owner, pending.
- Environment: WSL/Linux worktree
  `/home/minami/rakuten/.worktrees/goal`, CPython `3.14.6`, pinned uv `0.12.1`,
  and installed `openai==2.52.0`.
- Hydration command:
  `scripts/python_toolchain.sh --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv sync`.
  Result: `PASS`, 53 locked packages installed in the isolated `.venv`.
- Owner regeneration commands, in dependency order:
  `make --no-builtin-rules --no-builtin-variables --file Makefile config-generate UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv`;
  the corresponding `ai-registry-generate`, `content-ast-generate`, and
  `openai-recorded-generate` commands with the same fixed Make/uv arguments.
  Results: `PASS` for ST-0204, ST-0701, ST-0801, and ST-0703; the ST-0703
  registry contains five fixtures with SHA-256
  `215a38ace7e17064185c1ae4c17f92f57d88a71912d992a506d5f6484bd7e9d6`.
- No-write owner checks: `config-check`, `ai-registry-check`,
  `content-ast-check`, and `openai-recorded-check` with the same fixed
  Make/uv arguments all returned `PASS`. The final
  `openai-recorded-gate` returned `PASS`; an in-memory before/after snapshot of
  2,998 tracked and nonignored repository files found no path, mode, size,
  mtime, or SHA-256 change.
- Focused suites: `openai-recorded-test` returned `363 passed`; `config-test`
  returned `178 passed`; `ai-registry-test` returned `117 passed`; and
  `content-ast-test` returned `283 passed`. These are isolated local candidate
  results, not formal TST evidence.
- Exact ST-0102 wrapper command:
  `scripts/python_toolchain.sh --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv check`.
  Result: `PASS`, including Ruff, format, mypy, exact tool versions, and
  `48 passed` in `tests/st0102`.
- ST-0703 static command: `make --no-builtin-rules --no-builtin-variables
  --file Makefile openai-recorded-static
  UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv`. Result: Ruff
  lint `PASS`, Ruff format `11 files already formatted`, strict mypy
  `Success: no issues found in 11 source files`.
- Repository checks: `python3 scripts/import_raos_design.py verify` returned
  `PASS` for 105 imported files and 104 package checksums;
  `make --no-builtin-rules --no-builtin-variables --file Makefile
  check-workspace` returned `PASS` with `changed: []`; `bash -n
  scripts/object_storage_service.sh scripts/run_network_denied.sh` and
  `git diff --check` returned `PASS`.
- Semantic projection proof: owner-regenerated ST-0204, ST-0701, and ST-0801
  manifest projections remain respectively
  `ab5f98cee069733201e145c5c238547019edb0c3f9bbec1c2337d9629151b60a`,
  `a0d5aad3b2c95ba7a365d0fc0be5a7825834f7a9639260823e2729c27391ad0b`,
  and `7704359cb758e3bf35bbe88e91e41c7f484e8133f1ab7d4a139b2bafde7b2540`.
  ST-0204 and ST-0701 semantic generated-output hashes remain
  `5633b01e4f660a048e57ca4501a6a7e66f4aeca8412ff36f8644e68d4e04006e`
  and `33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07`.
- Base/scope proof: against comparison base
  `48a807672caa845df8e0251782f00bce8040663b`, ST-0106, ST-0107, ST-0202,
  and their delegated shell/test paths have no final delta; the only ST-0204,
  ST-0701, and ST-0801 deltas are their permitted owner-generated manifests;
  `changes/st-0204/README.md` and root `config-check: | python-sync` retain
  exact base semantics. The first checkpoint staged-scope audit returned
  `STAGED_SCOPE_PASS paths=22` with no unstaged path.
- `DEBT-W0-001` status update: `IN_PROGRESS`. The direct ST-0102 source
  mismatch is closed and the four W0 owner generations/checks are green.
  ST-0301 and later provenance fan-out remains `OPEN` for its owning Wave/final
  audit; this checkpoint does not claim that downstream closure.
- `DEBT-W0-002` remains `OPEN`; no partial ST-1203/ST-1204 pin repair was made.
- `DEBT-W0-003` remains `OPEN`. Exact attempted command
  `python3 -I scripts/scan_secrets.py --worktree` returned exit 2 with sanitized
  result `ERROR code=unsafe-git-metadata source="."` because the isolated Git
  worktree uses a `.git` indirection file. The passing ST-0703 suite includes
  the bounded no-environment, no-network, content-redaction, and raw-error
  leakage negative paths, but neither substitutes for nor weakens the full
  scanner policy; the inherited six synthetic-fixture findings remain
  unclassified and unclosed.
- `DEBT-W0-004` and `DEBT-W0-005` remain `EXTERNAL_BLOCKED`. Formal TST-017,
  hosted CI, live provider/account/credential validation, production pricing
  and FX, staging, publication, release, deployment, and production were not
  executed or authorized.

### 2026-08-10 W1 / ST-0401 implementation preflight

- Story and objective: implement the maximum safe `ST-0401` OIDC and session
  boundary permitted while `OD-010` remains unresolved: provider-neutral
  domain/application types and ports, strict authorization callback lifecycle,
  and one deterministic development-only fake adapter.
- Authority read: root and canonical Codex instructions, the owner-approved
  implementation-first ExecPlan, `ST-0401` plus dependency rows `ST-0103` and
  `ST-0204`, `OD-010`, `RAOS-SEC-001`, `RAOS-UI-001`, `SEC-SLICE-002`,
  `UI-SLICE-002`, `AUTH-001` through `AUTH-003`, `SEC-IAM-001` through
  `SEC-IAM-012`, `SEC-APP-001`, `SEC-DATA-003`, `SEC-DATA-007`, `THR-001`,
  `THR-020`, `THR-028`, `TST-012`, `TST-022`, `TST-026`, the Admin OpenAPI
  OAuth2/IAM shapes, the ST-0303 IAM migration, and the live ST-0204/ST-0703
  implementation patterns.
- Authority result: `PASS`. The ExecPlan is
  `OWNER_APPROVED_FOR_LOCAL_IMPLEMENTATION`; the Story design is
  `APPROVED_FOR_IMPLEMENTATION`; `OD-010` keeps real-provider and Production
  authentication blocked but explicitly permits local fake authentication in
  development only. The direct read-only ST-0204 predecessor check returned
  `PASS` with two generated artifacts unchanged.
- Ambiguity and safe default: browser-to-API transport remains intentionally
  unselected. No HTTP route, cookie, bearer-token delivery, browser client, or
  public activation will be implemented. The neutral seam is dependency-ready;
  transport and real issuer/client configuration will be recorded as
  `DEBT-W1-001` rather than inferred.
- Planned owned paths: `changes/st-0401/README.md`; IAM domain and application
  modules; the provider-neutral OIDC port; a development-only fake and in-memory
  adapters; isolated `tests/st0401`; narrow package exports, Make targets, and
  root README documentation; and append-only entries in this ledger.
- Planned checks: exact source import, isolated ST-0401 tests including replay,
  mismatch, expiry, rotation, revocation, environment rejection, and redaction
  negatives; Ruff lint/format; strict mypy for owned Python and tests; direct
  ST-0204 predecessor no-write check; sensitive-data scan or exact classified
  scanner result; `git diff --check`; and staged ownership/credential review.
- Out of scope: real issuer/audience/client registration, credentials, Secret
  resolution, provider SDK/network exchange, HTTP/web route activation,
  cookie-versus-bearer selection, MFA/step-up, authorization policy, broad HTTP
  security, secret manager, admin shell, persistence migration, formal TST,
  hosted CI, staging, publication, deployment, release, and Production.

### 2026-08-10 W1 / ST-0401 final local implementation checkpoint

- Implemented a provider-neutral IAM domain, inward `OidcProvider`, entropy,
  and authentication-repository ports, a transport-neutral application
  service, and an exact-`ENV-DEV` deterministic no-network fake plus ephemeral
  in-memory repository. The implementation has no password flow, provider SDK,
  HTTP framework type, database write, external configuration, Secret read, or
  live-provider call.
- Focused behavior includes independent canonical 256-bit state, nonce, and
  verifier values; S256-only PKCE; strict parsing and bounded expiry; atomic
  one-time transaction/code consumption; mismatch, unknown, expired, and replay
  denial; sanitized principal/failures; and bounded session create, refresh,
  rotation, revocation, idle expiry, and absolute expiry semantics. Rotation
  atomically invalidates the predecessor.
- Exact focused gate command: `make --no-builtin-rules
  --no-builtin-variables --file Makefile oidc-gate
  UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv`. Final result:
  `PASS`, including the import check, Ruff lint, Ruff format (`11 files already
  formatted`), strict mypy (`Success: no issues found in 11 source files`), and
  isolated pytest (`28 passed`). An earlier first focused run returned
  `23 passed`; the final suite adds static architecture, exact-environment,
  no-I/O/password surface, serialization, and immutable-failure assertions.
- Sensitive-data checks: the repository command `python3 -I
  scripts/scan_secrets.py --worktree` returned exit 2 with the inherited
  sanitized operational result `ERROR code=unsafe-git-metadata source="."` in
  this isolated Git worktree. The same scanner's `read_maintained_file` and
  `scan_payload` logic was then applied descriptor-relatively to all 14
  ST-0401-owned changed files and returned
  `FOCUSED_SECRET_SCAN findings=0 files=14`. This bounded result does not close
  or weaken `DEBT-W0-003`.
- `DEBT-W1-001` status: `OPEN`, introduced-by `ST-0401`, closure owner:
  `WAVE_FREEZE` plus the applicable human decision. Browser-to-API transport
  (cookie session versus bearer), HTTP activation, real provider selection and
  configuration under `OD-010`, durable persistence, Secret resolution, and
  external validation remain intentionally deferred. Safe impact: the inward
  seam and development fake are usable locally while every HTTP/live path
  remains absent and disabled.
- `DEBT-W1-002` status: `OPEN`, introduced-by `ST-0401`, closure owner:
  `WAVE_FREEZE` provenance regeneration. Exact failing command was the first
  invocation of the focused gate above while `oidc-check` still composed the
  ST-0204 owner check. Observed result:
  `error: generated ST-0204 artifact drift: changes/st-0204/manifest.yaml`.
  Affected owner artifact: `changes/st-0204/manifest.yaml`; root `Makefile` is
  one of its provenance inputs. The ST-0204 check remains recorded separately,
  while the final ST-0401 gate covers only owned import/static/test behavior.
  No ST-0204 generated artifact was regenerated or hand-edited. Safe impact:
  the stale hash inventory has no ST-0401 runtime effect and remains visible
  for ordered Wave-freeze closure.
- No generated status owner currently supports ST-0401 candidate evidence, so
  no generated status or evidence proposal was created or hand-edited. Formal
  TST-012/TST-022/TST-026, hosted CI, browser/runtime, live provider, staging,
  publication, deployment, release, and Production evidence remain
  `NOT_EXECUTED`; this checkpoint claims local implementation evidence only.

### 2026-08-10 W1 / ST-0402 implementation preflight

- Story and objective: implement the maximum safe `ST-0402` MFA/step-up seam:
  an immutable factor-neutral claim bound to the exact active ST-0401 session
  and principal, an inward verifier port, a transport-neutral application
  guard, and an exact-`ENV-DEV` scripted synthetic adapter.
- Authority read: root and canonical Codex instructions, canonical integration
  precedence and decision registers, the owner-approved implementation-first
  ExecPlan, the `ST-0402` row and `ST-0401` dependency, the live ST-0401
  README/domain/port/application/adapter/tests and inherited debt, `OD-010`,
  `RAOS-SEC-001`, `RAOS-UI-001`, `SEC-SLICE-002`, `UI-SLICE-002`,
  `AUTH-001` through `AUTH-003`, `SEC-IAM-001` through `SEC-IAM-012`, the
  critical-action role matrix, `THR-001`, `THR-003`, `THR-024`, `TST-012`,
  `TST-022`, `TST-026`, and the current Admin OpenAPI optional
  `mfa_satisfied` and step-up extension shapes.
- Authority result: `PASS`. `ST-0402` is
  `APPROVED_FOR_IMPLEMENTATION`, depends only on the present ST-0401 seam, and
  has no Story-local Open Decision. `OD-010` still blocks a real OIDC/MFA
  provider and external activation but permits an exact-development synthetic
  boundary. No new provider, factor, claim mapping, freshness, transport,
  action-policy, or persistence decision is required for this narrow seam.
- Owned paths: `changes/st-0402/README.md`,
  `python/raos/domain/iam/step_up.py`, `python/raos/ports/step_up.py`,
  `python/raos/application/iam/step_up.py`,
  `python/raos/adapters/development_step_up.py`, `tests/st0402/conftest.py`,
  `tests/st0402/test_step_up.py`, `tests/st0402/test_boundaries.py`, and
  append-only ST-0402 records in this ledger. No migration, generated output,
  shared package export, Make target, root README, or contract will change.
- Planned checks: direct import/compile, isolated ST-0401 and ST-0402 pytest,
  focused Ruff format/lint and strict mypy, active-session-before-assurance
  negatives, exact-development/no-I/O/static architecture checks, redaction
  and generic-serialization checks, a focused sensitive-data scan,
  `git diff --check`, and exact owned-path/staged credential review.
- Deferred debt identities reserved for the final checkpoint:
  `DEBT-W1-003` real provider/claim mapping/freshness decision,
  `DEBT-W1-004` HTTP/browser/middleware/Problem Details,
  `DEBT-W1-005` durable persistence/audit/action mapping, and
  `DEBT-W1-006` formal/live verification. Inherited debt remains unchanged.
- Out of scope: challenge begin/complete, OTP/TOTP/WebAuthn or factor secrets,
  provider `amr`/`acr`/`auth_time` interpretation, a production freshness TTL,
  critical-action registry, cookie/bearer/HTTP/browser delivery, `/admin/mfa`,
  database/migration/audit writes, real provider or Secret resolution, and any
  hosted, live, staging, publication, release, deployment, or Production work.

### 2026-08-10 W1 / ST-0402 final local implementation checkpoint

- Implemented an immutable factor-neutral `StepUpGrant` with explicit UTC
  `authenticated_at`/`expires_at`, exact ST-0401 session and stable
  issuer/subject binding, a provider-neutral inward verifier port, and an
  application `StepUpGuard`. The guard delegates to ST-0401 active-session
  enforcement before assurance lookup and then rejects absent, negative,
  malformed, future, expired, session-mismatched, principal-mismatched, and
  unsupported assurance with immutable sanitized typed failures.
- Implemented `DevelopmentScriptedStepUpVerifier`, which is construction- and
  operation-guarded to the exact `RuntimeEnvironment.ENV_DEV` enum member and
  returns only explicitly supplied synthetic already-verified grants. The
  owned AST has no file, network, process-environment, credential, factor,
  provider SDK, HTTP framework, database, challenge, or action-policy surface.
- Environment: WSL/Linux isolated worktree
  `/home/minami/rakuten/.worktrees/goal`, CPython `3.14.6`, pinned uv `0.12.1`.
  Direct import command used pinned uv with `run --locked --offline --no-cache
  --no-sync --no-env-file --no-python-downloads` and explicit
  `PYTHONPATH=<repository>/python`; result: `PASS` for the domain, port,
  application guard, and development adapter.
- First and final focused ST-0402 pytest command used the same read-only uv
  flags and `pytest -p no:cacheprovider -q tests/st0402`; both results:
  `27 passed`. The separately executed predecessor command with
  `tests/st0401` returned `28 passed`. These are isolated local candidate
  results, not formal TST evidence.
- Focused static commands used the same read-only uv flags over exactly the
  four owned source modules and `tests/st0402`: Ruff lint returned
  `All checks passed!`; Ruff format returned `7 files already formatted`;
  strict mypy with explicit package bases returned
  `Success: no issues found in 7 source files`. `git diff --check` returned
  `PASS`.
- Sensitive-data checks: the repository command
  `python3 -I scripts/scan_secrets.py --worktree` returned exit 2 with the
  inherited isolated-worktree result
  `ERROR code=unsafe-git-metadata source="."`. The scanner's maintained-file
  reader and payload classifier were then applied descriptor-relatively to all
  nine owned changed paths and returned
  `FOCUSED_SECRET_SCAN findings=0 files=9`. This does not close or weaken
  inherited `DEBT-W0-003`.
- `DEBT-W1-003` status: `EXTERNAL_BLOCKED`, introduced-by `ST-0402`, closure
  owner: Security Owner plus the authorized real-provider Story. Exact skipped
  command: `NOT_RUN — no authorized real MFA provider or claim-mapping command
  exists`; observed result: `NOT_EXECUTED`. Affected future owner sources are
  the real verifier adapter and approved provider-claim/freshness policy; no
  current generated artifact or downstream pin was changed. Closure boundary:
  after `OD-010`, provider `amr`/`acr`/`auth_time` mapping, and a production
  freshness lifetime are approved, implemented, and negatively tested. Safe
  impact: only exact-development explicit-lifetime synthetic grants exist.
- `DEBT-W1-004` status: `OPEN`, introduced-by `ST-0402`, closure owner: the
  first authorized Admin HTTP/UI integration Story and final integration
  audit. Exact skipped command: `NOT_RUN — TST-012/TST-022 HTTP/browser step-up
  command is not present in this interface-only slice`; observed result:
  `NOT_EXECUTED`. Affected future sources/artifacts are cookie-or-bearer
  delivery, middleware, RFC 9457 Problem Details, `/admin/mfa`, and browser
  tests; no OpenAPI or generated client was edited. Closure boundary: an
  approved transport implements and tests those surfaces without trusting the
  optional OpenAPI `mfa_satisfied` boolean. Safe impact: no HTTP or browser
  route can activate the local seam.
- `DEBT-W1-005` status: `OPEN`, introduced-by `ST-0402`, closure owner: the
  authorized persistence/audit/action-policy Stories and final integration
  audit. Exact skipped command: `NOT_RUN — no ST-0402 migration, durable audit,
  or critical-action registry is owned by this slice`; observed result:
  `NOT_EXECUTED`. Affected future sources/artifacts are durable grant/audit
  storage and the reviewed role/action mapping; no migration, database owner,
  generator, or generated artifact changed. Closure boundary: durable
  lifecycle/audit behavior and exact action mapping are implemented from
  approved policy with negative authorization tests. Safe impact: this seam
  grants no action authority and persists nothing.
- `DEBT-W1-006` status: `EXTERNAL_BLOCKED`, introduced-by `ST-0402`, closure
  owner: formal CI, Security Owner, and staging/release owners. Exact skipped
  command: `NOT_RUN — formal TST-012/TST-022/TST-026 and live/staging commands
  are outside local implementation authority`; observed result:
  `NOT_EXECUTED`. Affected evidence owners are the formal HTTP, browser, and
  security suites; no status/evidence generator supports this candidate and no
  generated status was edited. Closure boundary: those suites and applicable
  human reviews actually run in their authorized environments. Hosted CI,
  real provider/account/credential validation, staging, publication, release,
  deployment, and Production remain unexecuted.
- Inherited `DEBT-W0-001` through `DEBT-W0-005` and `DEBT-W1-001` through
  `DEBT-W1-002` remain unchanged and unclosed. This checkpoint claims only
  local implementation evidence for the scoped ST-0402 seam.

### 2026-08-10 W1 / ST-0404 final local implementation checkpoint

- Authority and scope: canonical `ST-0404` is
  `APPROVED_FOR_IMPLEMENTATION`, depends on the locally present ST-0401 seam,
  and has no Story-local Open Decision. The implementation is limited to a
  framework-neutral, default-deny HTTP security seam; real origins, domains,
  authentication transport, delivery framework, and operational production
  values were not inferred.
- Implemented strict immutable `CanonicalOrigin`, `CsrfProof`, request
  metadata, policy, failure, and RFC 9457 `ProblemDetails` values plus an
  application `HttpSecurityGuard`. The guard enforces exact origin/method/
  header/content-type/content-length policy before handler invocation and
  requires constant-time paired CSRF proof validation for unsafe
  cookie-authenticated commands.
- The owned source has no FastAPI, Starlette, HTTP client, SQLAlchemy, provider
  SDK, network, file, process-environment, database, credential, or external
  state dependency. Request objects contain no raw body, cookie value, bearer
  token, Secret, or personal data. Conservative response headers include a
  deny-by-default CSP without wildcard, `unsafe-inline`, or `unsafe-eval`.
- Environment: WSL/Linux isolated worktree
  `/home/minami/rakuten/.worktrees/goal`, CPython `3.14.6`, pinned uv `0.12.1`.
  The first isolated pytest attempt failed during collection because pytest
  `9.1` reserves parametrized argument name `request`; the local test parameter
  was renamed. Final isolated `tests/st0404` result: `27 passed`.
- Focused static results: Ruff lint `PASS`; Ruff format `7 files already
  formatted`; strict mypy `Success: no issues found in 7 source files`,
  including the isolated tests; `git diff --check` `PASS`. Focused invocations
  of the repository scanner engine covered the seven code/test paths plus the
  final Story README and ledger delta and returned an aggregate
  `FOCUSED_SECRET_SCAN findings=0 files=9`.
- The repository command `python3 -I scripts/scan_secrets.py --worktree`
  remains unable to traverse this linked isolated worktree and returns the
  inherited sanitized result
  `ERROR code=unsafe-git-metadata source="."`. This Story did not weaken the
  scanner and does not close `DEBT-W0-003`.
- `DEBT-W1-007` status: `OPEN`, introduced-by `ST-0404`, closure owner:
  authorized Admin HTTP/framework integration and final integration audit.
  Exact skipped command: `NOT_RUN — no approved real origin/domain, delivery
  framework, cookie/header names, authentication transport, production CSP
  source, HSTS duration, request/rate/timeout limit, or durable CSRF replay
  mechanism exists in this interface-only slice`; observed result:
  `NOT_EXECUTED`. Safe impact: all such values are caller-supplied and
  default-deny, and no route is activated.
- `DEBT-W1-008` status: `EXTERNAL_BLOCKED`, introduced-by `ST-0404`, closure
  owner: formal CI, Security Owner, browser/staging/release owners. Exact
  skipped command: `NOT_RUN — formal TST-012/TST-026, hosted browser/runtime,
  staging, publication, release, deployment, and Production commands are
  outside local authority`; observed result: `NOT_EXECUTED`. No generated
  status/evidence artifact was hand-edited, and no local result is promoted to
  formal validation or Production readiness.
- Inherited `DEBT-W0-001` through `DEBT-W0-005` and `DEBT-W1-001` through
  `DEBT-W1-006` remain unchanged and unclosed. This checkpoint claims only
  local implementation evidence for the scoped ST-0404 seam.

### 2026-08-10 W1 / ST-0407 final local implementation checkpoint

- Authority and scope: canonical `ST-0407` is
  `APPROVED_FOR_IMPLEMENTATION`, depends only on the locally present ST-0204
  configuration seam, and has no Story-local Open Decision. The owner-approved
  implementation-first ExecPlan authorizes this reversible metadata-only
  interface/fake boundary while the older preflight continues to prohibit real
  Secret material, provider, database, CI, and rotation-infrastructure choices.
- Implemented strict redacted workload binding, purpose, alias, request, lease
  metadata/state, rotation notice, sanitized failure values, material-free
  inward acquisition and rotation-hook ports, and a configuration-bound
  `WorkloadCredentialService`. The service validates only ST-0204 service,
  environment, and alias membership, explicit UTC windows, an injected maximum
  lifetime, exact request binding, freshness, replay, and non-overlapping newer
  rotation metadata.
- Implemented an exact-`ENV-DEV` deterministic single-use scripted adapter and
  an always-disabled adapter. The development adapter rejects CI deployment
  purpose and every non-development environment. Owned AST boundary tests prove
  there is no raw Secret resolution, provider SDK, ambient credential chain,
  network, file, process environment, database, migration, client/pool,
  JWT/OIDC, GitHub workflow, background execution, or external-write surface.
- Environment: WSL/Linux isolated worktree
  `/home/minami/rakuten/.worktrees/goal`, CPython `3.14.6`, pinned uv `0.12.1`.
  The final read-only command used `run --locked --offline --no-cache --no-sync
  --no-env-file --no-python-downloads`; isolated `tests/st0407` result:
  `42 passed`. Ruff lint and format returned `PASS`; strict mypy including the
  owned tests returned `PASS`; direct compile/import, staged-path audit, and
  `git diff --check` returned `PASS`.
- Sensitive-data checks: the worker's maintained scanner-engine pass covered
  the seven code/test paths and returned zero findings; the final aggregate
  pass included the Story README and this ledger and returned
  `FOCUSED_SECRET_SCAN findings=0 files=9`. The full repository command remains
  unable to traverse the linked worktree and returns the inherited sanitized
  `unsafe-git-metadata` result; this Story does not weaken or close
  `DEBT-W0-003`.
- `DEBT-W1-009` status: `EXTERNAL_BLOCKED`, introduced-by `ST-0407`, closure
  owner: Security Owner plus an approved provider/credential integration Story.
  Exact skipped command: `NOT_RUN — no authorized Secret backend, provider
  account, credential material, or live workload-identity command exists`;
  observed result: `NOT_EXECUTED`. Closure boundary: `OD-015` and applicable
  provider/account/data-control decisions are approved, then an outward adapter
  obtains short-lived material without exposing it to Domain, logs, evidence,
  or repository bytes. Safe impact: only material-free metadata exists.
- `DEBT-W1-010` status: `OPEN`, introduced-by `ST-0407`, closure owner: the
  authorized workload-identity, database, CI, and operations Stories plus final
  integration audit. Exact skipped command: `NOT_RUN — cache/refresh/revocation,
  durable rotation audit, database pool turnover, GitHub OIDC trust, and CI
  credential delivery are outside this interface slice`; observed result:
  `NOT_EXECUTED`. Closure boundary: those owners implement approved concrete
  contracts with concurrency, expiry, revocation, confused-deputy, and leakage
  negatives. Safe impact: no current caller receives material or live authority.
- `DEBT-W1-011` status: `EXTERNAL_BLOCKED`, introduced-by `ST-0407`, closure
  owner: formal CI, Security Owner, provider/database operators, and
  staging/release owners. Exact skipped command: `NOT_RUN — formal TST-026 and
  TST-031 plus live provider/database/credential, staging, release, deployment,
  and Production commands are outside local authority`; observed result:
  `NOT_EXECUTED`. No generated status/evidence artifact was edited and no local
  result is promoted to formal validation or Production readiness.
- Inherited `DEBT-W0-001` through `DEBT-W0-005` and `DEBT-W1-001` through
  `DEBT-W1-008` remain unchanged and unclosed. This checkpoint claims only
  local implementation evidence for the scoped ST-0407 seam.
