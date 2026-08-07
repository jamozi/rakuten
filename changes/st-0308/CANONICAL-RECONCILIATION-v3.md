# ST-0308 DESIGN_HANDOFF_V1 v2 reconciliation

Status: `MATERIAL_CONFLICT_REQUIRES_REPLACEMENT_AND_REAPPROVAL`

This is a local, read-only reconciliation record. It is not canonical authority,
an approved design handoff, implementation authority, formal TST evidence, or a
staging/production readiness claim.

## Candidate identity

- Path: `/mnt/c/Users/naoki/Downloads/DESIGN_HANDOFF_V1_v2.yaml`
- Bytes: `1559979`
- SHA-256: `1019e7ef84066c78870332402fb87143fc8499d772cd4c4c7dca0db24e24157f`
- Root: `DESIGN_HANDOFF_V1`
- Story: `ST-0308`
- Dependencies: `ST-0304`, `ST-0105`
- Required suites: `TST-005`, `TST-008`
- `open_decisions`: `[]`
- Self-declared authority: `PROPOSED_UNAPPROVED_HANDOFF`
- Self-declared implementation authority: `BLOCKED`

The bytes are materially different from the previously approved-but-rejected
candidate (`33a9078095bfa7fd0f2517eba4ee941b9c9584222692e1069d35252a2b04a510`).
No prior approval transfers to this candidate or to a future replacement.

## Automated preflight

The exact candidate fails the current deterministic validator at the YAML
safety boundary. It contains 154 YAML anchors and 155 aliases. The first pair
is `&id001` at line 618 and `*id001` at line 718. Candidate YAML must be a
single, alias-free, tag-free document.

A diagnostic-only alias expansion then exposed two additional structural
failures before semantic activation:

1. `source_design_refs` treats
   `approved-input/DESIGN_HANDOFF_V1.yaml` as a repository file, contains four
   duplicate identities, has no structured archive-member tuple, and omits four
   predecessor references plus the four current V3/package references now
   required by preflight:
   - `changes/st-0308/PRO-CORRECTION-REQUEST-v3.md`
     (`0906d9bf46920bfd1d018590490857a6665ab9fc8eecc92411e3fcdb9d206270`)
   - `changes/st-0308/CANONICAL-RECONCILIATION-v3.md`
     (the exact self-bytes are bound externally by the V3 submission manifest)
   - `changes/st-0308/IMPLEMENTATION-READINESS-v3.md`
     (`29e90628cc8ed4259b54486ab12abddb606ae414e3a2391c5055dbbf521577f7`)
   - `changes/st-0308/pro-correction-input.v2.members.sha256`
     (`dcd754d9b5d6211c52c3fa5811b65207b0d80a7fc398b14c8c58c9c93048bc7b`)
   - `changes/st-0308/pro-correction-bundle.v2.yaml`
     (`62be122dbd16f2fbff2e2e9737eca4b0f4504574d2c6d943258e0ee7e59a33b0`)
   - `changes/st-0308/pro-correction-input.v2.tar.gz`
     (`209aba655caa6e29d14452ccf8ba7d74f79a9835549fe71fad9bfc7c22ef6baf`)
   - `changes/st-0303/generated/iam-ops-validation.v1.sql`
     (`33be33b53b9a14c7e9ad686f8dd08834a2bc8211e6fab82577f78811219fde32`)
   - `changes/st-0304/generated/domain-validation.v1.sql`
     (`7e1ce307a5751fc5d95e4c06652f0e6fb41b8bdc29c583ea9cd0a3d83d1fa3a5`)
2. The pending approval boundary uses non-null `approved_by` and `approved_at`
   sentinel strings and a non-allowlisted reconciliation token.

The live validation contract now requires the exact 24-relation non-version
state-CAS set. The historical nine-relation assumption is superseded and no
longer causes a validator failure. All 15 additional relations are physical
tables with no `lock_version`, a constrained lifecycle/status column, and an
exposed transition in the proposal. The 24-relation set is disjoint from the
exact 27-relation physical `lock_version` set. The validation contract still
declares `semantic_authority: MANUAL_ONLY` and remains non-implementation
authority.

A diagnostic-only alias expansion followed by factual source/boundary repairs
proved that no further hidden automated shape/source/inventory/lock/D6 error is
present. That diagnostic copy is not a handoff and is not approval evidence.

To remove the remaining packet-member ambiguity, the local support artifact
`changes/st-0308/pro-correction-input.v2.members.sha256` records all 369 regular
archive members by safe relative path and exact hash. Its SHA-256 is
`dcd754d9b5d6211c52c3fa5811b65207b0d80a7fc398b14c8c58c9c93048bc7b`;
an independent archive-to-manifest comparison passes exactly. This manifest is
verification input only, not a design handoff or implementation authority.

## Semantic reconciliation against the V2 correction request

| Topic | Result | Finding |
|---|---|---|
| 103 tables and one view | `PASS` | The eight-schema physical inventory and normalized digest match current pinned bytes. |
| 27 `lock_version` relations | `PASS` | The corrected set includes all eight previously omitted AI relations and is used by the detailed root-CAS matrix. |
| 24 non-version state-CAS relations | `PASS_CLASSIFICATION` | The set is physical, disjoint from the 27-set, and must remain 24; detailed predicates still need corrections below. |
| Eight module UoW surfaces | `PASS_AGAINST_V2_REQUEST_ONLY` | All eight base/joined surfaces are present, but they conflict with the later owner-supplied Pro advice described below. |
| Shared Audit/Outbox/Idempotency ownership | `PASS` | Shared inward protocols plus shared SQLAlchemy adapters own narrow OPS infrastructure DML. |
| Opaque idempotency handle and completion CAS | `PASS_AGAINST_V2_REQUEST_ONLY` | The SQL/CAS design is expressible, but the public method/union surface conflicts with later Pro advice. |
| Event aggregate versions and exclusions | `PASS_AGAINST_V2_REQUEST_ONLY` | Eighteen allowlisted events have persisted sources and non-versioned roots are excluded; the event-journal API conflicts with later Pro advice. |
| Domain types and mapper targets | `PASS_AGAINST_V2_REQUEST_ONLY` | The proposal covers 103 tables plus one view, aggregate assembly, public type resolution, and corruption behavior. |
| D6 provider/identity boundary | `PASS_CONDITIONAL` | The provider is injected and ST-0306 remains candidate-only; runtime identity evidence is still unexecuted. |
| Exact state predicates and atomic sets | `FAIL_MATERIAL` | Five relation contracts contain an omitted predicate, conditional columns, or a nonexistent column. |

## Exact state-CAS defects

### `policy.waiver`

- The public Repository summary still says `relevant existing timestamps`.
- `WaiverRepository.decide` predicates every undecided field except
  `expires_at IS NULL`. That predicate is required before either APPROVED or
  REJECTED completion.
- The detailed approve/reject/revoke/expire WHERE and SET lists must be copied
  into, or normatively referenced from, every summary, protocol, matrix,
  acceptance criterion, and test row. No `expected_version` is allowed.

### `ops.runtime_setting_version`

The proposal says activation sets `approved_at`, but the physical relation has
no such column. Its relevant physical columns are
`status`, `effective_from`, `effective_to`, `approved_by_principal_id`, and
`approval_reason`. The replacement must define exact transition-specific WHERE
and SET lists using only physical columns; it must not invent an approval
timestamp.

### Editorial version relations

The following three relations have no `effective_from` or `effective_to`:

- `editorial.article_type_version`
- `editorial.article_template_version`
- `editorial.editorial_methodology_version`

Their transition contracts currently say `where physical columns exist` and
conditionally mention those nonexistent columns. The replacement must enumerate
relation-specific exact SET lists. Activation sets only `status`,
`approved_by_principal_id`, and `approved_at`; later transitions set only
`status` and preserve approval history. Transition time is Audit-only for these
relations.

`editorial.content_schema_version` does have an immutable non-null
`effective_from` and nullable `effective_to`. Activation must preserve
`effective_from`, set approval fields, and set `effective_to=NULL`. Leaving
ACTIVE must set `effective_to` to a timestamp strictly after `effective_from`.
No `COALESCE` or conditional-column wording is permitted.

The five allowed lifecycle edges remain:

- `DRAFT -> ACTIVE`
- `DRAFT -> RETIRED`
- `ACTIVE -> DEPRECATED`
- `ACTIVE -> RETIRED`
- `DEPRECATED -> RETIRED`

## Material conflict with the later owner-supplied Pro advice

The owner subsequently supplied `PRO_ADVICE_V1` with
`authority: UNAPPROVED_ADVICE`. It cannot silently override canonical or become
implementation authority. It also cannot be treated as the same proposal as
this candidate because four interfaces differ materially:

1. **UoW capability separation.** The advice separates base outer,
   idempotent outer, and joined UoWs and their factories; only API composition
   receives idempotent factories. The candidate exposes idempotency on every
   base and joined UoW, exposes `join_token` and `closed` on joined UoWs, and
   allows worker idempotency.
2. **Idempotency result types.** The advice uses
   `claim(...) -> IdempotencyClaimDecision` and
   `lookup(...) -> IdempotencyLookupDecision`. The candidate uses
   `begin(...) -> IdempotencyDecision` and allows the same union (including a
   new-claim variant) from lookup.
3. **Event acknowledgement.** The advice exposes immutable
   `pending_events()` plus `acknowledge_events(event_ids)` after Outbox staging.
   The candidate uses a private drain/confirm/restore batch protocol.
4. **Six machine-readable matrices.** The advice requires exact
   `contracts/persistence/{concurrency_matrix.v1,state_cas_matrix.v1,uow_surface_matrix.v1,domain_mapper_matrix.v1,event_emission_matrix.v1,identity_matrix.v1}`
   artifacts and repeated SHA-256 bindings. The candidate names none of them.

A replacement must select and express one coherent design for these four areas,
with rationale and rejected alternatives. Codex must not select between these
unapproved alternatives during implementation.

## Treatment of the informational 91-table advisory

The owner also supplied a long `ST0308_DESIGN_ADVISORY_V1`. That document is
not a handoff: it declares `INFORMATIONAL_NONCANONICAL_ADVICE_ONLY`,
`PARTIAL_DESK_REVIEW_ONLY`, `human_approval: NOT_PROVIDED`, and
`implementation_authority: BLOCKED`. It says the exact ST-0105, ST-0304, and
ST-0306 bytes were inaccessible and therefore proposes a provisional 91-table
baseline cut.

Current local reconstruction uses the exact pinned predecessor bytes and proves
an eight-schema 103-table plus one-view physical cut. The informational
advisory's older generic UoW, idempotency, versioning, and inventory statements
also conflict with the later, more exact proposal set. It is therefore retained
only as historical rationale/rejected-alternative context. It cannot reduce the
physical inventory, override the 27/24 concurrency classification, authorize
implementation, or transfer approval to replacement bytes.

## Activation result

`BLOCKED`. No ST-0308 implementation-safe subset is authorized. The next
candidate must:

1. resolve every structural, reference, state-CAS, and proposal-conflict item;
2. pass the current deterministic preflight without weakening the verified
   physical 27/24 classifications;
3. receive a fresh conflict-free manual canonical reconciliation; and
4. receive explicit repository-owner approval of its exact SHA-256 bytes.

Only after all four conditions may `implementation_worker` implement ST-0308.
