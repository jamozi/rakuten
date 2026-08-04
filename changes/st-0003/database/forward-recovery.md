# ST-0003 forward recovery

Forward recovery is the default after a canonical writer may have observed or
written the ST-0003 AI governance model. Never collapse `AWAITING_HUMAN`,
`FAILED_RETRYABLE`, `RETRY_SCHEDULED`, `QUARANTINED`, `EXPIRED`,
`IN_REVIEW`, `EVALUATING`, `CERTIFIED`, `SUSPENDED`, `CANARY`, or
`ROLLED_BACK` merely to make a downgrade complete.

Each numbered SQL file is a separately recorded checkpoint. Do not concatenate
the files into one transaction, execute the proposal SQL, or mark a checkpoint
complete unless its complete payload succeeds. Registry seed/load remains
owned by ST-0701.

The checkpoint series is `202607300007` through `202607300012`.

## 007 Expand failed

The column/table/constraint/trigger/grant transaction rolls back as a unit.
Correct predecessor drift or the lock-timeout cause and rerun 007. If only part
of the expected shape is visible, stop and inspect migration history; do not
add `IF NOT EXISTS` clauses to hide a partial application.

The Expand preflight requires finalized ST-0002, the baseline AI constraints,
the baseline immutable-row guard, and all baseline roles. It intentionally
replaces only the blocking AI Job, Prompt, and Route lifecycle checks with
dual-compatible checks.

## 008 validation or concurrent index failed

Constraint validation commits before concurrent indexes. A validation failure
leaves NOT VALID constraints that still enforce new writes. Repair the invalid
legacy row and rerun 008.

Inspect a failed revision index with `pg_index.indisvalid`,
`pg_index.indisready`, and `pg_get_indexdef`. Drop only the wrong or invalid
named `*_st0003` index after recording evidence, then rerun 008. The payload
preflights and post-validates exact definitions; `IF NOT EXISTS` cannot mask a
same-name drifted index.

## 009 batch failed, was interrupted, or reports remaining work

Each invocation changes at most 1,000 rows total across AI Job, AI Attempt,
Prompt, Model, and Route tables. It locks rows in stable UUID order with
`FOR UPDATE SKIP LOCKED`. A failed invocation rolls back only that batch;
earlier committed checkpoints are idempotent.

Persist the per-entity/status checkpoint and all three counters:

- repeat 009 until `automatic_remaining_rows=0`;
- `operator_classification_rows` is the sum of `BLOCKED` AI Jobs and
  `REJECTED` Prompts and is never guessed by the migration;
- classify each ambiguous row from reviewed evidence through an audited
  operator/application action, then require total `remaining_rows=0`.

Rows skipped by a competing lock remain in the automatic count. A zero-row
batch with nonzero automatic count means wait for the competing transaction;
it does not authorize Contract.

## 010 Contract prepare failed

010 refuses any automatic backlog, `BLOCKED` AI Job, or `REJECTED` Prompt. It
also rechecks verified human Prompt-author provenance, exact critical indexes,
public/reporting/auditor isolation, the absence of PUBLIC EXECUTE on trigger
helpers, and the fixed-search-path `SECURITY DEFINER` boundary used by the three
Evaluation Run transition guards without granting the worker direct assertion
or authority-table access.

The transaction either installs all canonical lifecycle and required-field
NOT VALID checks or none. Once it commits, legacy writers are intentionally
incompatible. Prefer forward repair if an old writer raced the cutover.

## 011 Contract validation or finalization failed

Validation commits separately from final metadata changes. If validation
fails, repair the row under an approved audited action and rerun 011. Do not
remove or weaken a constraint to pass.

The final defaults, NOT NULL changes, Expand-check removal, canonical
constraint renames, predecessor Prompt-index replacement, and revision-index
renames are one short transaction. A failure rolls that transaction back and
leaves validated proof constraints and `*_st0003` indexes available for an
011 retry.

After 011, verify:

- lifecycle/default/NOT NULL/constraint/index exact shape;
- Suite/Dataset/Case/Run/Result/Human Evaluation/Judge Calibration lifecycle
  and immutability guards, including hash-matched dataset/case/rubric/report
  artifacts;
- exact frozen task risk/suite configuration, resolved-model start binding,
  non-empty required splits, full metric/grader/human/adjudication evidence,
  and immutable completion artifacts;
- split-wide and per-category blocking aggregates for HOLDOUT, ADVERSARIAL,
  and REGRESSION, including denominator-weighted ratios and scope-local p95;
- both latency and cost observations for every Case; their current canonical
  p95 rows carry null threshold/operator/pass state, while a future versioned
  suite may make either metric blocking through `required_metrics`;
- exact eight-code zero-tolerance evidence, generated failure counts, immutable
  evidence hashes, and all six metric-backed safety observations for every
  Case;
- permanent content freezing for the evaluated Task, Prompt, Route, Output
  Schema, resolved Model, and Policy Bundle after the run leaves `PLANNED`;
- append-only non-empty Policy Bundle membership, ACTIVE-only bound Rule
  Versions, post-DRAFT Rule content/hash immutability, and serialized Rule
  retirement versus Bundle activation;
- one immutable Attempt per Case Result, exact immutable case-input hash,
  success-only immutable output hash, and exact refusal/terminal-failure
  validation truth tables;
- exact-scope, current model-judge calibration provenance on every judge
  metric and its Release Decision;
- Release Decision direct bindings, completed/all-PASSED/zero-tolerance gate,
  safe immutable rollback/monitoring/canary evidence, Canary-before-Active
  transaction separation, phase-specific manifest signatures, Prompt-author
  separation of duties, and two distinct ACTIVE USER approvers;
- current-Champion detection independent of component lifecycle visibility,
  and a distinct Champion-config baseline rerun on the candidate Suite/Dataset
  with exact overall/category regression comparisons;
- server-owned immutable Canary start/completion timing and same-task prior
  Active rollback targets whose six components cannot leave Active while a
  live dependent exists;
- Critical-task Canary bounded to one percent and the route cap, with a single
  task-level `APPROVED_CANARY` enforced under advisory serialization;
- API/worker write, projection read-only, and public/reporting/auditor denial.

## 012 guarded downgrade refused or failed

Refusal is the expected safe result whenever governance tables contain rows,
canonical-only/ambiguous lifecycle states exist, or a new field contains
meaning that the baseline cannot represent. Do not delete evidence, empty a
governance table, rewrite a state, or clear hashes/bindings solely to satisfy
the guard.

012 freezes all affected writers before evaluating losslessness. It also
requires the exact finalized helper/column shape, explicitly breaks the
Release Decision/Release Approval circular FKs without `CASCADE`, removes only
named revision objects, and verifies the ST-0002 shape after reversal. If it
passes the guards but fails later, its single transaction rolls back
completely. Correct the exact cause and either retry with approval or continue
forward.

## Required production evidence

- approved release and migration/checkpoint IDs;
- PostgreSQL 18.4 CI and production-size staging rehearsal;
- recent backup and tested restore;
- per-batch counts, explicit classification records, and final zero backlog;
- lock, WAL, replica-lag, and runtime observations;
- old/new writer cutover and observation window;
- permission/trigger/concurrency negative tests;
- human approval for Contract and any guarded downgrade.
