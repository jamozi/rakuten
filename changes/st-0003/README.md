# ST-0003 AI governance canonical revision

This bundle layers `INT-DEC-004` on the verified ST-0002 v0.2 candidate. It is
an implementation candidate for later installation by ST-0104/ST-0301; it is
not a production migration, provider integration, or release approval.

## Build

```bash
python3 scripts/build_st0003_revision.py
python3 scripts/build_st0003_revision.py --check
```

The CLI accepts only the owned `changes/st-0003` destination. Generation
verifies immutable package/proposal hashes and every artifact in the ST-0002
manifest, renders the complete contract tree in sibling staging, and restores
the previous tree if installation fails.

## Database checkpoints

Apply and record each file as a separate checkpoint:

1. `202607300007_ai_governance_expand.sql`
2. `202607300008_ai_governance_expand_validate.sql`
3. repeat `202607300009_ai_governance_migrate_batch.sql` until
   the automatic backlog is zero; explicitly classify any reported legacy
   `BLOCKED` AI Jobs or `REJECTED` prompts from operational evidence
4. deploy canonical writers only after that classification, then
   `202607300010_ai_governance_contract_prepare.sql`
5. `202607300011_ai_governance_contract.sql`
6. use `202607300012_ai_governance_guarded_downgrade.sql` only as a separate,
   explicitly requested recovery checkpoint after reviewing its refusal
   report; it is never part of the forward install sequence

The reusable migration runner/history/advisory-lock ABI belongs to ST-0301.
Do not concatenate the checkpoints into one transaction. See
`database/forward-recovery.md` before recovery or downgrade.

The guarded downgrade is deliberately conservative: it refuses non-empty
governance resources, lossy canonical-only states, or meaningful new
metadata. A refusal means forward recovery is required; it must not be
bypassed by deleting governance evidence.

This revision does not seed or activate task definitions. Catalog loading,
conflict detection, and safe initial task state belong to ST-0701; proposal
SQL using `ON CONFLICT DO UPDATE` is retained only as provenance and is never
executed.

## Contract contents

- the complete verified ST-0002 contract set promoted to v0.3;
- Admin/Internal OpenAPI and AsyncAPI revisions;
- canonical AI Job/Prompt/Route/Dataset/Run/Calibration/Release state
  contracts, including append-only phase-specific Release Approval bundles;
- exact frozen suites for all 12 accepted tasks, resolved-model and
  model-judge provenance, complete metric/grader/split/human evidence gates,
  hash-bound rollback/canary evidence, and Prompt-author separation of duties;
- non-empty canonical required splits and blocking metric aggregates for each
  HOLDOUT/ADVERSARIAL/REGRESSION split overall and for every represented Case
  category, so a pooled score cannot hide a failing subgroup;
- DB-derived ratio values from integer numerator/denominator counts, weighted
  ratio aggregation, and scope-local percentile aggregation for latency/cost
  p95 metrics; Wilson lower bounds and pairwise win/tie/loss confidence
  intervals are report evidence and never replace the exact DB point-estimate
  gate;
- both latency and cost observations from `grader.cost_latency.v1` for every
  Case; current canonical suites store their threshold/operator/pass state as
  null report-only evidence, while a future versioned suite that adds either
  metric to `required_metrics` must provide all three and uses scope-local p95
  as a blocking gate;
- exact eight-code zero-tolerance JSON and immutable evidence-artifact hashes,
  with a generated failure count and all six metric-backed safety observations
  required for every Case;
- current-Champion regression protection through a separate Champion-config
  rerun on the candidate Suite/Dataset, with exact per-Case grader/threshold/
  judge pairing and overall/category margin checks; a null baseline is accepted
  only when no `APPROVED_ACTIVE` Champion exists;
- exact provider-attempt result truth tables, immutable case-input and
  successful-output artifact/hash identity, and one canonical metric per
  run/case/metric;
- permanent Task/Prompt/Route/Output-Schema/Model/Policy content freezing once
  an Evaluation Run starts, with API-only authority mutation and append-only
  worker findings;
- append-only non-empty Bundle Rule membership, DRAFT-parent/ACTIVE-Rule
  assembly, post-DRAFT Rule content/hash immutability, and retirement only
  after every referencing Bundle leaves ACTIVE;
- same-task prior-Active rollback targets, six-component Active-state checks,
  reverse dependency guards, and server-owned immutable Canary timing;
- Critical-task Canary percentage capped at one percent and at the route cap,
  with at most one `APPROVED_CANARY` per task under task-level serialization;
- AI task, prompt, route, evaluation, failure, quality, observability, and
  review catalogs;
- 12 prompt templates and 14 RAOS-AI-001 task/evaluation schemas copied with
  their original hashes;
- generated strict JSON Schema types for governance resources, requests, and
  internal lifecycle events.

Category is the DB-enforced subgroup boundary. Article type, evidence quality,
language complexity, route, model, tags, and other multi-value slices remain
mandatory report dimensions but are not allowed to satisfy a blocking category
gate. Canonical suites currently define no latency/cost release threshold, so
their p95 metrics use null threshold/operator/pass state and remain report-only
until a versioned suite adds one.

The public OpenAPI is copied byte-for-byte from its immutable v0.1 archive
member and hash-checked as the public-isolation compatibility boundary; it is
never widened. Final Python/TypeScript type/client generation remains owned by
ST-0105.

## Status boundary

Local tests are implementation evidence only. Formal CI TST-002, TST-003,
TST-008, and TST-012, PostgreSQL 18.4, application HTTP integration, staging,
provider live validation, and production deployment remain `NOT_EXECUTED`.
