# Verified-incremental audit interface

This explicit release profile is separate from the existing 37-PASS full-portfolio
ledger. It does not change that ledger, authenticate reviewers, create signatures,
approve publication, or approve new WordPress pages. It is not a claim of perfection.
Its output is an integrity binding marked `READY_FOR_OWNER_REVIEW`.

## Caller and trust boundary

Call `validate_verified_incremental_audit_v1` in
`python/raos/application/editorial/verified_incremental_audit_v1.py` with:

- `report`: the audit JSON object, schema
  `RAOS_WORDPRESS_VERIFIED_INCREMENTAL_AUDIT_V1`.
- `manifest_sha256`: current hash of the independently validated
  `RAOS_WORDPRESS_VERIFIED_INCREMENTAL_MANIFEST_V1` release manifest.
- `expected_artifact_hashes`: opaque artifact ID → SHA-256, recomputed from the
  final reviewed source/content/theme/configuration inputs, not copied from report.
- `evidence_artifacts`: opaque artifact ID → actual bytes read through the existing
  safe owner-private reader. Every byte is rehashed; all artifacts must be used.
- `expected_backup_snapshot` and `expected_backup_article_slugs`: the actual
  current MCP snapshot and the ten existing article slugs from the independently
  reconstructed candidate, never copied from the review report. Its original
  file-byte hash must be present as `expected_artifact_hashes["live-snapshot"]`.
- `implementation_execution_ids`: independently obtained IDs of implementation
  executions. These are not taken from the report itself.
- `scope`: `IncrementalAuditScopeV1`, derived from the validated manifest.
- `now`: timezone-aware current time.

The scope binds selected, existing and rendered article IDs; whether shared
surfaces change; nonempty retained claim IDs for **each selected article**;
retained product IDs; applicable cloud/disposal product subsets; and commercial
CTA/image IDs. Selected IDs must already exist. Shared changes require rendering
all existing article IDs, not only the changed articles. The publication owner
derives `required_noncontent_rollback_targets` from the validated manifest's
`theme`/`seo`/`plugins` shared targets and binds that set in the scope hash.
Existing home/policy stored-content changes are not noncontent targets. The owner
separately validates core-page/template/viewport coverage, HTML, claim truth,
product-to-placement identity, and every unmodified live baseline.

Fresh product/source/materialization checks, wp-admin approval, exact proposal and
single-use lease validation, and post-apply readback remain separate mandatory
controls. Use the earliest expiry across this binding **and** those inputs.
Never use the binding alone as a stored authorization receipt. Revalidate the
report and its real artifacts before proposal/resume/apply.

## Report and evidence format

`incomplete_audit_template_v1(...)` returns the exact report field structure with
no rounds and null times. `incomplete_evidence_template_v1(...)` returns the exact
evidence structure with `result: NOT_EXECUTED`. Both are intentionally invalid for
publication. Neither synthesizes a completed audit or an owner confirmation.

The report uses `publication_profile: verified-incremental`, `link_mode:
standard-api`, `review_kind: CODEX_TECHNICAL_REVIEW` and
`execution_identity_authentication: OWNER_REVIEW_REQUIRED`. Publication and
new-page approval authority and verified reviewer attestation are always false.
Owner approval is always required.

Two sequential clean review rounds are required. Each round has exact fields:
`round_id`, `reviewer_id`, `execution_id`, `started_at`, `completed_at`,
`manifest_sha256`, `scope_sha256`, `artifact_hashes`, `findings`, `surfaces`.
Reviewers, review executions and rounds are distinct; no review execution can be
a supplied implementer execution. Findings must be empty. Every round binds the
same complete manifest, scope and source artifact set.

Every surface appears once in `SURFACES` order, with exact fields `surface_id`,
`status`, `execution_status`, `reason_code`, `evidence_id`. Executed mandatory
surfaces require `PASS`, `EXECUTED`, null reason and a unique evidence ID.
Each evidence object must be canonical UTF-8 JSON (sorted keys, compact separators,
newline) with the template fields. It binds surface, round, execution, hashes and
capture time; contains nonempty observations and rehashed attached output
artifacts; and has empty findings plus surface-specific successful checks.

General `checks` contain `status: PASS` and `completed_checks` matching the exact
`REQUIRED_CHECKS[surface_id]` set. Specialized checks are:

- `code`: commands containing `command_id`, integer `exit_code: 0`, and bound
  `output_artifact_id`. `generate`, `check`, `focused`, `fast`, `final` are required.
- Contact: `state`, `address`, `owner_id`, `confirmation_artifact_id`,
  `delivery_artifact_id`. Address is `contact@kurashinoshirube.com`.
  `OWNER_CONFIRMED` requires a real owner-confirmation attachment and null delivery
  artifact. `TESTED` additionally requires an actual delivery-test attachment.
  The state must agree across both rounds. An address or MX record alone is neither.
- Backup: `backup_available`, `restore_rehearsal_passed`, `restored_hashes_match`
  must be true, with `rollback_owner_id` and **three distinct** attached IDs:
  `backup_artifact_id` (original MCP snapshot), `restoration_artifact_id` (actual
  `RAOS_WORDPRESS_SCRATCH_RESTORE_RECEIPT_V1`), and
  `restoration_readback_artifact_id` (actual scratch stored-field readback).
  The booleans alone cannot pass. The validator rebuilds the exact scratch seed
  from the current snapshot and replays all fourteen original ID/slug/content
  hashes, title/excerpt hashes, dates, taxonomy identities and stored values.
  It checks the receipt's exact profile, successful state, source/preparation/
  seed/readback hashes, scratch-only and false authority flags, and verification
  time no later than the review observation. It keeps the raw file-byte hash
  separate from the canonical snapshot hash (which omits the final newline).
  Backups remain owner-private, attached by hash; they are never report text or
  tracked fixtures. A plan, generic attachment, altered receipt or hash-only
  restamping cannot substitute for these replayed outputs.
- Operations: `immediate_readback_plan_bound: true`, `incident_owner_id` and
  `rollback_owner_id`, with the actual plan among the bound attachments.
- Freshness: `recheck_owner_id` and `expiry_enforced: true`.

Artifact hashes detect tampering, not fabricated observations. This validator
cannot prove a command actually executed, that declared identities belong to
different agents, or that an owner really confirmed a fact. Evidence must come
from actual executions. The owner must review that provenance and the exact
release proposal; no cryptographic independent-review claim is made.

Existing article/home/policy saved-content changes can use the fourteen-document
rehearsal. A content-only receipt cannot establish a theme rollback. When the
scope's `required_noncontent_rollback_targets` is exactly `["theme"]`, the backup
checks additionally require four distinct attachments: `theme_backup_artifact_id`,
`theme_candidate_artifact_id`, `theme_readback_artifact_id` and
`theme_restoration_artifact_id`. All seven backup attachments must be distinct.
The first two carry the actual, closed baseline/candidate file bytes. Their tree
hash is the deployment operator's sorted path/size/content-hash canonical JSON
projection, not a ZIP hash. The baseline must match the captured MCP deployment
baseline in the original snapshot; the candidate must match the audited
`theme-tree` input. Git history can provide matching backup bytes but cannot prove
that a restoration actually ran.

The separate portless scratch executor performs same-basename file replacement,
without activating themes or changing WordPress options: baseline → candidate →
baseline. Its readback must capture the exact tree, all fourteen restored content
documents and all stored WordPress option hashes at **each** stage. The validator
replays the actual package/readback/receipt bytes, exact source snapshot and
content-restoration receipt binding, and unchanged settings; booleans or a typed
receipt alone do not establish execution provenance. The real owner-private
outputs must originate from an executed scratch rehearsal and be inspected in
both review rounds. Preparing a package, passing synthetic tests, or writing this
interface does **not** constitute a completed rehearsal; until the frozen candidate
has actually been exercised, the theme restoration remains `NOT_EXECUTED`.

SEO/plugin/settings rollback is not implemented by this files-only test. Any
required `seo` or `plugins` rollback target remains rejected with
`SHARED_ROLLBACK_NOT_VERIFIED`. Revision history, author identity and post metadata
are not restored. The release contract checks the scope's noncontent target set
against the manifest, so omitting a theme/SEO target cannot bypass these gates.
Every binding remains non-authorizing; the existing full-profile workflow is
unchanged.

## Required, deferred and not applicable

Factual/safety/selection, attribution/rights/disclosure, SEO, UI/accessibility,
privacy/measurement OFF, security, source integrity, commercial identity,
performance, backup/restore and immediate operational ownership checks remain
required. Editorial products need not disappear solely because commercial assets
are unavailable; omitted commercial assets must be absent and correctly scoped.

The real-reader surface is always `DEFERRED`, `NOT_EXECUTED`, null evidence and
reason `REAL_READERS_NOT_EXECUTED`. Codex role-play cannot change it to PASS.
Only cloud or disposal surfaces may be `NOT_APPLICABLE`, and only when their
manifest-derived applicable product subset is empty, with reason
`NO_APPLICABLE_PRODUCTS`. Other exemptions are rejected.

`deferred_checks` lists exactly the following objects, each with `check_id`,
`execution_status: NOT_EXECUTED`, and `publication_blocking: false`:
`real_reader_research`, `longitudinal_operational_metrics`,
`external_alert_delivery_drill`, `formal_legal_opinion`; additionally
`automated_contact_delivery` when contact is OWNER_CONFIRMED. These are explicitly
unexecuted future work, not hidden PASS reports or a claim of legal compliance.

Evaluation must not be future-dated. Expiry must be later than now and at most
24 hours after evaluation, and no later than the earliest applicable review
observation expiry (24 hours after its capture). These are immutable-subject
review observations, not a publication activation. Actual provider/source captures
retain their independent 24-hour maximum. The separate activation envelope is
created only after current artifact, source, browser and baseline checks and
expires after at most 900 seconds; replay never extends that original expiry.
Reviewing an earlier hash-bound command output is not recorded as rerunning it.
Review rounds cannot overlap or contain out-of-round evidence capture times.

## Output and tests

The returned `VerifiedIncrementalAuditBindingV1.to_document()` is JSON serializable,
binds report/manifest/scope/input/evidence hashes and expiry, records contact state
and deferred work, and requires production readback. No live action occurs.

`tests/verified_incremental_audit_v1/` uses synthetic records only. Coverage includes
tamper, missing gates, failed commands despite recomputed hashes, invalid exemptions,
blank articles, partial render sets during shared changes, missing owner contact or
restore proof, review identity collisions, stale evidence, approval substitution,
real-reader impersonation, and unpublishable incomplete templates. Restoration
regressions also cover wrong snapshots, original IDs, dates and taxonomies,
rehashed receipt/readback tampering, authority/profile mixing, reused attachment
IDs, and shared-configuration claims unsupported by a content-only rehearsal.
