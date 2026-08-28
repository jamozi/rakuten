# RAOS V2 Phase 3 production backup/export runbook

## Boundary

This is a human runbook for `B-V2-035`; no backup, credential access, WordPress
read/write, deployment or production mutation was executed while generating it.
Stop before any action unless the owner has separately approved the exact
production task and has a recoverable storage location outside this repository.

## Exact target

- Origin: `https://kurashinoshirube.com`
- Existing route: `/carry-on-suitcase-comparison/`
- Migration mode: update the existing public route in place; do not create a
  redirect, alternate public slug or second indexable page.

## Create-once pre-action binding before final review

The Phase 0 body hash is historical evidence only. Never overwrite or relabel it
as current. First create a new `RAOS_V2_PHASE3_PREACTION_BINDING_V1` from one
bounded public read-only capture and one owner-held WordPress export of the same
existing post. If the public body, post ID or export identity cannot be bound
exactly, keep the historical candidate unsealable and stop.

1. Record the WordPress site, core version, active theme/version, relevant
   plugin versions and the exact target post ID. Do not put credentials or raw
   database exports in Git, logs or the review packet.
2. Export recoverable bytes for the target post: title, slug, excerpt, content,
   status, author, publish/modified dates, taxonomy, comment/ping state, featured
   media references and every SEO/Yoast field that affects title, description,
   canonical, robots or schema.
3. Export the active theme/plugin artifact needed to restore the previous
   presentation, and record its version plus SHA-256 outside the repository.
4. Record public status, redirect chain, canonical, HTML/meta and HTTP robots,
   sitemap membership, H1 and body hash using the bounded
   `capture-phase3-public --public-read-only` command immediately before the
   external action. The same capture must fetch the fixed same-origin
   `/robots.txt`, accept only status 200, 404 or 410, retain only its SHA-256
   and metadata, discard its body, and prove that the target route is allowed
   for Googlebot. Enumerate crawler-specific robots meta such as `googlebot`
   and `googlebot-news` and require every directive to remain indexability
   safe; metadata nested in `template` or `noscript` is not accepted as head
   metadata evidence. Phase 0 evidence is a historical baseline and must not
   be overwritten.
5. Store raw exports in recoverable owner-controlled storage. Create only a
   sanitized receipt containing opaque hashes, version identifiers, field names
   and the exact target binding for review by the local generator. The local,
   network-free derivation command is:

   ```text
   python scripts/raos_v2_phase3_execution.py derive-preaction      --public-capture changes/raos-v2/recorded-inputs/phase3/<capture>.json      --owner-export /absolute/owner/storage/wordpress-owner-export.json      --restore-artifact /absolute/owner/storage/restore-artifact      --theme-plugin-artifact /absolute/owner/storage/theme-plugin-artifact      --seo-state /absolute/owner/storage/seo-state      --redirect-map /absolute/owner/storage/redirect-map      --sitemap-state /absolute/owner/storage/sitemap-state      --output changes/raos-v2/recorded-inputs/phase3/<preaction-input>.json
   ```

   Every owner-held path must resolve to a nonsymlink regular file outside the
   repository. The command is create-once, rejects a capture/export pair more
   than five minutes apart and persists no raw WordPress field value or external
   path. The currently recorded public observation is deliberately unpaired and
   cannot be substituted for this receipt.

6. Reissue the local update/review candidate from the verified pre-action
   binding. Only that reissued digest may be given to the human reviewer. Run:

   ```text
   python scripts/raos_v2_phase3_execution.py reissue-candidate      --preaction-input changes/raos-v2/recorded-inputs/phase3/<preaction-input>.json      --output changes/raos-v2/recorded-inputs/phase3/<reissued-review-bundle>.json
   ```

   The reissue is local and create-once, rejects pre-action evidence older than
   five minutes, reconstructs the historical candidate through the versioned
   domain contract and leaves all network/WordPress/publication capabilities
   false. The bundle is independently verified against
   `contracts/raos-v2/v2/reissued-review-bundle.schema.json`, the current
   generator-owned candidate and the exact pre-action input. A generic
   conversation approval is not an artifact-specific receipt. The current JSON
   receipt has no trusted signature or approval source: even with
   `accepted=true` it is classified `UNAUTHENTICATED_OWNER_ASSERTION` with
   `acceptance_authority=false`. The identity-bearing fields are fixed to
   `reviewer_id=OWNER_ASSERTION_LOCAL` and
   `review_version=P3-OWNER-ASSERTION-V1`; a name, email or caller-selected ID is
   rejected rather than persisted. It may create only a simulation seal. After
   the owner creates that schema-valid assertion, seal locally with:

   ```text
   python scripts/raos_v2_phase3_execution.py seal-candidate      --review-bundle changes/raos-v2/recorded-inputs/phase3/<reissued-review-bundle>.json      --human-review-receipt /absolute/owner/storage/human-review-receipt.json      --output changes/raos-v2/recorded-inputs/phase3/<sealed-simulation-package>.json
   ```

   The seal command has no network or WordPress capability and rejects a
   synthetic, stale, schema-mismatched or digest-mismatched assertion. Its
   package is explicitly `simulation_only=true` and
   `approval_acceptance_authority=false`; it never satisfies human approval,
   public-write authority or the Phase 3 exit. The tracked plugin binding stays
   `DEPLOYMENT_DISABLED`; never hand-edit or deploy it as armed.

   `derive-cutover-binding` is deliberately fail-closed. It independently
   reconstructs any caller-supplied sealed package through the same domain seal
   blockers, then returns
   `RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED`. It cannot emit or certify
   `ARMED_EXACT_LEGACY_OR_SEALED` until a separately designed trusted
   artifact-specific approval source plus fresh post-approval `PRE_WRITE_EXPORT`
   and disabled-plugin dry-run verifiers are all implemented. A caller-authored
   digest or JSON receipt cannot substitute for any of them.
7. After the local simulation seal, create `PRE_WRITE_EXPORT` and its
   disabled dry-run receipt. This pre-write export must bind the existing
   field hashes, sealed pre-action digest and same current body, be no older than
   five minutes at evaluation and be captured after the owner assertion. Any
   intervening change requires a new pre-action binding, candidate reissue and
   assertion. It is not post-publication evidence and the current operator does
   not consume it to arm the plugin. Keep the binding disabled and stop.

If any field, restore byte sequence, target identity or checksum is unavailable,
record `UNAVAILABLE` and stop. Missing data is never equivalent to an empty field.

## Deploy, preview and metadata gate

The route-scoped plugin renders CSS and the exact content-verification envelope;
it does not generate JSON-LD. Plugin version 0.6.0 models one future safe cutover
order, but the trusted approval/pre-write verifier needed to create its armed
artifact is not implemented. Do not activate or write. If that verifier is
implemented in a later approved phase, the order is: install inactive,
atomically replace the disabled adjacent binding with the independently verified
owner-export-bound artifact, activate while the exact legacy database bytes
still remain, and only then write the exact sealed bytes.
The exact legacy state preserves the existing filtered response without V2 CSS;
the exact sealed state discards earlier filter output and envelopes only the
reviewed raw fragment. Disabled, missing, partial, intermediate or drifted
states block the target. Writing sealed bytes before activation is prohibited
because an inactive plugin cannot protect the route. A content filter registered after RAOS at `PHP_INT_MAX`
terminates only the target request with a fixed 503 before the later callback
can mutate it. V2 projection is limited to the exact current target post inside
the singular main query's main loop. Only a verified different current post is
treated as a secondary `the_content` call and preserves its filtered input;
missing, ambiguous or out-of-main-loop target context is blocked. The candidate depends on the existing
Yoast or single metadata-owner configuration. Before publication, a nonpublic
WordPress preview must prove the
exact `Article`, `BreadcrumbList`, `Organization` and `WebSite` graph required by
T-V2-036, with visible-title/canonical parity and no forbidden rich-result type.
It must also emit exactly one HTML title equal to the sealed `post_title` (no
unreviewed site-name suffix) and exactly one meta description equal to the
sealed `meta_description`.
This is an unexecuted external blocker. A mismatch must not be accepted as a
completed publication: correct the metadata configuration before cutover, or
restore the exported state if the mismatch is discovered after a write.

After an approved publication, the HTTP verification receipt must be derived
from three independent inputs: the fresh bounded public capture, the sealed
package and a separate `POST_ACTION_OWNER_EXPORT` of every sealed WordPress
field after the write. This after-state export must bind the same post ID,
sealed AFTER field hashes, final public body and pre-action digest. It is not the
pre-write dry-run export. The post-action HTTP capture and export form one
atomic paired-capture contract: both must be independently derived and evaluated
within the same five-minute window. A capture alone or a self-asserted receipt
cannot satisfy this gate. The HTTP receipt's indexability evidence scope is
`HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT`: it must include the safe HTML/meta and
HTTP robots state, sitemap membership, plus the hashed-and-discarded
same-origin `/robots.txt` response and a positive Googlebot allowance for the
target route. Crawler-specific meta must also be counted and free of `noindex`,
`nofollow` and `none` directives.

After any separately approved publication, B-V2-040 also requires a separate
public read-only browser receipt at 390, 768 and 1440px. It must bind the public
body, sealed package and deployed plugin hashes while checking computed
disclosure/blocked-CTA visibility, keyboard use, 200% zoom, axe WCAG 2.2 AA and
resource/network behavior. Raw capture and screenshot bytes must remain in
owner-controlled storage outside Git. The local public-read-only recorder is
implemented in `tests/raos_v2/phase3-public-validation.mjs`; its raw receipt is
explicitly non-authoritative and cannot complete Phase 3. An independent
acceptance verifier must still recalculate the public HTTP receipt digest,
resource manifest, screenshot bytes/hashes and the harness, browser binary and
exact command hashes. Until that independent receipt exists, the generated
acceptance schema remains an unverified template and Phase 3 stays
`BLOCKED_EXTERNAL`.

## Restore rehearsal and triggers

Before publishing, the owner must be able to restore the exact post fields,
SEO fields, theme/plugin version and public route tuple from the export. Trigger
rollback for a wrong fact/model/CTA, hidden advertising disclosure, canonical or
indexability error, broken package binding, critical accessibility defect or
publication-state mismatch. Operational targets are to start rollback within 30
minutes of detection and verify the previous public state within two hours,
subject to host availability; these are targets, not guarantees.

## Evidence labels

- This runbook: `GENERATED_LOCAL`
- Production backup/export: `NOT_EXECUTED`
- Production restore: `NOT_EXECUTED`
- Public verification: `NOT_EXECUTED`
