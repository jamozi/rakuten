# ST-1407 local implementation ExecPlan

## 1. Story and outcome

- Story: `ST-1407` — External policy change registry.
- Outcome: add a deterministic DEV/CI-only registry boundary that can load one
  exact recorded snapshot, retain explicit snapshot-to-policy version links,
  calculate an affected-article set from exact recorded article bindings, and
  create a non-deliverable overdue alert candidate from an explicit due time.
- Non-goals: network capture, current-official-source attestation, arbitrary URL
  fetch, database/API/job/event integration, notification delivery, audit write,
  reviewer assignment, PolicyBundle activation, article mutation, publication,
  release, staging, or Production behavior.

## 2. Context read

- Canonical integration design, Story backlog, Open Decisions, FR-017 master and
  acceptance traceability, TST-005/TST-019/TST-020 definitions, security control
  catalog, threat register, alert `ALT-019`, and runbook `RB-018`.
- Installed contracts `RAOS-CONTENT-EXTERNAL-001` v0.1,
  `RAOS-CONTENT-REF-001` v0.1, and `RAOS-CONTENT-POLICY-001` v0.1.
- Existing ST-1407 V1 non-attesting reference plan and its owner generator.
- ST-0405 process-local audit seam and ST-0805 V1/V2 pure local policy runtime.
- OPEN-018 remains unresolved. OD-008 blocks legal substitution/publication.
  OD-011 permits only local logging and forbids Production notification.

## 3. Invariants

- Recorded synthetic bytes are never described as current official source bytes.
- No caller-controlled URL, raw source body, legal conclusion, notification
  destination, review body, prompt, secret, personal data, or finance field is
  accepted or returned.
- External snapshots, PolicyBundles, rule versions, and publication snapshots
  remain distinct. This slice creates typed reference links, not activation.
- Due time and evaluation time are explicit fixture coordinates; `monthly and
  event-driven` is never converted into a real deadline.
- Empty affected results mean zero only within the exact complete recorded
  synthetic fixture queried; missing/incomplete input is `UNAVAILABLE`, not zero.
- Every accepted article universe is non-empty and bound to one owner-recorded
  binding-set hash. Recorded adapter fixtures additionally bind one exact
  fixture ID to one owner-generated request hash; caller-authored self-consistent
  fixtures are rejected.
- Recommendation order, article content, approval, publication, and external
  side effects cannot be changed by any result.
- Every result is content-addressed and deterministic; malformed, duplicate,
  unknown, cross-snapshot, cross-version, or tampered input fails closed.

## 4. Proposed design

- Add a pure `raos.domain.ops.external_policy_registry` module with strict value
  objects and pure snapshot/link/impact/overdue evaluators.
- Add a narrow read-only exchange port and a bounded immutable recorded adapter
  enabled only for the explicit development environment.
- Add an application service that snapshots one exchange response, re-evaluates
  it, and rejects mismatch or mutation. It never calls ST-0405 because this
  Story has no authorized business mutation to audit.
- Add a versioned YAML fixture contract, deterministic owner generator, generated
  JSON, and runtime manifest. The generated fixture contains synthetic IDs and
  hashes only; it embeds no official webpage body.
- Validate the complete ordered authority/contract/dependency inventory and pin
  every materially executed local runtime module in the manifest. A role, path,
  use, or byte substitution fails closed.
- Rollback is removal of this additive V2 boundary. Existing V1 artifacts remain
  compatible and independently reproducible.

## 5. Milestones

1. Preserve the passing V1 baseline and install this plan.
2. Implement the pure domain model and exhaustive unit/negative tests.
3. Implement the read-only port, recorded adapter, application service, and
   boundary tests.
4. Install the versioned fixture contract/generator/manifest, regenerate, and
   verify both V1 and V2 owner checks.
5. Run focused and dependency suites, static/type/security/workspace checks,
   record exact local evidence, and commit one ST-1407 change.

## 6. Test plan

- TST-005 local evidence: snapshot integrity, exact version links, deterministic
  impact intersection, overdue/not-due boundary, stable hashes, permutations,
  tamper/duplicate/unknown/cross-binding rejection, and adapter replay.
- TST-020 local evidence: all linked `POL-CONT-*` identifiers must exist in the
  exact ST-0805 catalog; article bindings cannot contain unknown policy IDs;
  query output has no content/recommendation/publication mutation authority.
- TST-008 and TST-019 remain formal `NOT_EXECUTED`; focused negative tests reject source
  bodies, arbitrary URLs, legal/notification/finance/review/prompt/secret fields.
- Provider failure, unauthorized writes, and rollback remain structurally absent:
  no network/provider/writer or activation port exists.

## 7. Evidence plan

- Owner generator `--check` for V1 and V2, focused pytest, ST-0405 and ST-0805
  regressions, Ruff check/format, strict mypy, compile/import, secret scan,
  canonical import verification, workspace drift check, and `git diff --check`.
- Canonical Story/master/acceptance traceability disagree on the TST-008 and
  TST-019 set. Both remain explicitly `NOT_EXECUTED`; local evidence does not
  resolve or erase that divergence.
- Local evidence may support `LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY`.
  It cannot support formal `VALIDATED`, live/staging/release/Production status.

## 8. Risks and decisions

- No Canonical rule defines a real review deadline. Chosen safe behavior: accept
  an explicit synthetic `review_due_at`; never infer it from catalog prose.
- No approved cross-aggregate database relation is installed. Chosen safe
  behavior: immutable recorded references and a read-only query only.
- Notification channels are unresolved. Chosen safe behavior: return a local
  candidate with delivery authorization false; expose no delivery port.
- A live source allowlist is unresolved. Chosen safe behavior: expose no URL or
  acquisition input and bind only installed catalog identifiers/hashes.

## 9. Progress log

- 2026-08-24: read Canonical authority, dependencies, contracts, controls,
  alert/runbook records, and existing V1 implementation. V1 generator check and
  isolated suite passed (`70 passed`). No implementation files changed before
  this plan was recorded.
- 2026-08-24: installed the additive V2 pure domain, read-only port, bounded
  recorded adapter, mutation-detecting application service, fixture contract,
  deterministic owner generator, runtime manifest, and negative/boundary tests.
- 2026-08-24: independent review found three medium boundary defects: hostile
  string-subclass equality, substitutable/incomplete provenance, and an unbound
  article-universe zero result. Exact-type validation, ordered inventory plus
  material dependency pins, owner request/binding-set hashes, and adversarial
  tests closed all three; the omitted formal TST-008 trace is now explicit.
- 2026-08-24: independent remediation re-review confirmed all prior findings
  closed and found no new high or medium issue.
- 2026-08-24: verified V2 (`95 passed`), historical V1 (`70 passed`), ST-0405
  (`78 passed`), and ST-0805 (`361 passed`). Both ST-1407 generators and the
  ST-0805 V2 owner check passed. Ruff check/format, strict mypy, strict Pyright,
  compile/import, reviewed-ledger secret scan, Canonical import verification,
  workspace drift, and diff checks passed.

## 10. Completion note

The maximum safe local implementation for the unresolved source-acquisition
boundary is complete with no introduced local debt. It provides only recorded
synthetic DEV/CI evidence and no external acquisition, current-source
attestation, legal conclusion, notification delivery, assignment, audit write,
activation, mutation, or publication authority. Formal
TST-005/TST-008/TST-019/TST-020,
live providers, databases, staging, release, publication, and Production remain
explicitly `NOT_EXECUTED`; this evidence does not claim `VALIDATED` status.
