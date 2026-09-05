# Verified incremental publication port

This is an explicit alternative profile, not a replacement for the legacy
full-portfolio publication path or an authorization to publish. The first
executable candidate is A10 with **no retained commerce or editorial product
selection**. Existing IDs, published status, URLs, taxonomies and media IDs remain
unchanged. Other live articles remain their exact captured originals. Optional
tracked theme and existing policy changes require the mixed all-14-page audit.

The pure release contract can validate verified product/image/CTA records, but
the executable port currently rejects a selected article with nonempty product
IDs: `PRODUCT_AUDIT_APPLICABILITY_NOT_MATERIALIZED`. A trusted adapter mapping
retained products to applicable smart-device and disposal audit surfaces is not
implemented. It must not be replaced with invented NOT_APPLICABLE decisions.
There is no implicit fallback to the full profile, measured links, or an
unverified commercial candidate.

## Evidence and clocks

`verified_incremental_release_v1.build_verified_incremental_release_v1` binds the
validated manifest, two independent clean audit rounds, actual artifact bytes,
exact source/provider replays, ContentDocumentV1 hashes and unchanged complement.
HTML body hashes are not substituted for ContentDocumentV1 hashes.

The manifest is an immutable audit subject, valid for at most 24 hours and no
later than its selected sources. Review observations also expire within 24
hours. These are not activation authority. The activation envelope is built
after the reviews and current evidence replay and expires at the earliest of
900 seconds after activation, subject expiry, audit expiry and source/product
expiry. Browser evidence also has its own authoritative producer/validator
freshness check. No timestamp, source receipt or audit output is refreshed merely
to obtain a passing result.

On resume the original `activation_evaluated_at` is supplied to the builder.
Replayed evidence must reproduce the same envelope, not extend its expiry.
An expired activation permits only applied-state inspection and readback. A
different candidate or activation cannot silently replace an existing registered
request. Owner approval is a separate server-enforced single-use lease.

## Explicit CLI

The existing entry point is `scripts/raos_wordpress_publication_request.py`.
Choose all of these arguments for proposal preparation:

```text
--publication-profile verified-incremental
--link-mode standard-api
--quality-audit-mode codex-owner
--incremental-candidate <absolute owner-private candidate directory>
--incremental-preview-fixture <absolute owner-private mixed preview directory>
--incremental-implementation-execution-id <actual implementer execution ID>
--incremental-stage propose
```

Repeat the implementation-ID argument for every actual implementer. The candidate
owns the selected article set; legacy `--articles` remains `all`. The code never
constructs reviewer identities, clean audit findings, owner confirmations or
approval receipts. Signed full-profile and measurement receipts are not accepted
as substitutes. The default profile and link mode remain the legacy defaults.

The candidate is re-created from current authoring, current official source
replays, its exact original MCP snapshot and current tracked shared artifacts.
The port reopens every stored artifact and audit attachment, checks hashes, then
revalidates the actual mixed-browser report. The report's bytes must also be
included as the `mixed-browser-report` audited input. Proposed production markup
is connected to the exact candidate ContentDocumentV1 projection.

`propose` registers the exact content/theme batch and stops at owner approval;
it does not apply. `apply` requires the specific wp-admin-approved batch, current
preconditions and fresh activation. `readback` never starts apply, recover or
finalize. A server state query can perform the existing server-side expiry
bookkeeping, but cannot authorize a new publication.

## Private records and recovery

Credentials and publication records stay under the fixed saved checkout
`/home/minami/rakuten/.secrets/wordpress-mcp`; no credential copy into a worktree
is required. Source contracts and official source evidence use the explicit
current worktree roots. Symlink, ownership, permission and content-hash checks
remain mandatory.

The audit report is `audit/report.v1.json`. Additional audited bytes are stored
as `audit/inputs/<sha256>.bin`, and evidence/attachments as
`audit/evidence/<sha256>.bin`. Required inputs include the manifest, original live
snapshot, candidate preparation, all local/production/shared artifacts and the
actual mixed-browser report. Templates marked NOT_EXECUTED cannot pass.

`publication-request.v1.json` stores the original release envelope, proposal
identities, registration, actual apply response when received, and readback.
An uncertain proposal or registration stops for bounded reconciliation instead
of unconditional retransmission; automatic reconciliation of those two outcomes
is not implemented in this first port. A lost apply response first queries the
durable batch. If already APPLIED, it does not apply again, even after expiry.
Actual content operations and the theme operation are fetched through their
bounded status ports. Such GET observations are labeled operation readback, not
fabricated apply responses or owner approval receipts.

Completion additionally requires exact full-document inventory/complement
parity, the selected ContentDocumentV1 hashes, unchanged or updated audited theme
hash, real public SEO/content/image readback and freshly observed measurement OFF.
Generic PASS dictionaries cannot mark a request complete. An applied batch whose
public readback fails remains applied-but-unverified; it is not reported as
successful publication.

## Measurement OFF: independent public-runtime gate

The MCP `measurement` object describes only the RAOS measurement plugin. It is
not evidence that Jetpack Stats, Site Kit or another plugin is inactive.
`raos_wordpress_runtime_audit.py` performs a separate anonymous public read before
proposal creation and again on every apply/resume attempt. It checks the actual
currently installed theme against the captured baseline or bound candidate;
the candidate's not-yet-installed files are not assumed to be live. Unknown
scripts, executable inline code, unbound import maps, unexpected resource links,
active embedded content, CSS fetches and response cookies fail closed. Existing
image identities are bounded to the captured documents and audited theme.

Executable bytes are restricted to the two named audited theme scripts and the
six debug/minified variants of three WordPress core modules in
`changes/wordpress-local-preview-v1/wordpress-runtime.lock.json`. The dependency
hashes came from `/usr/src/wordpress` in the pinned, network-disabled, read-only
WordPress image, not a mutable preview installation or a live response. Exact
asset version queries remain intact; the ordinary HTTP page transport retains
its no-query boundary. CSS dependencies must be literal references into the
same audited image tree. No whole plugin directory or provider-name denylist
can confer an OFF result.

The same gate runs during full mixed public readback. Its report explicitly
means **closed declared runtime verified**, not a browser/service-worker or
conditional network observation. Actual browser checks remain separate required
release evidence. A client precheck cannot atomically lock third-party plugin
configuration; post-apply readback is still required. Failure never turns an
already applied batch into a reason to resend it. Source hashes, owner approval,
the single-use server lease and measurement OFF are independent requirements.

The focused tests use synthetic transports only. They are not actual independent
reviews, live publication evidence, or proof of owner approval.
