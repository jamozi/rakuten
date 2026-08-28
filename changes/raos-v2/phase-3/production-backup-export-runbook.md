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
   and the exact target binding for review by the local generator.

6. Reissue the local update/review candidate from the verified pre-action
   binding. Only that reissued digest may be given to the human reviewer.
7. After owner review and local sealing, create `PRE_WRITE_EXPORT` and its
   disabled dry-run receipt. This pre-write export must bind the existing
   field hashes, sealed pre-action digest and same current body, be no older than
   five minutes at evaluation and be captured after the human review. Any
   intervening change requires a new pre-action binding, candidate reissue and
   review. It is not post-publication evidence.

If any field, restore byte sequence, target identity or checksum is unavailable,
record `UNAVAILABLE` and stop. Missing data is never equivalent to an empty field.

## Deploy, preview and metadata gate

The route-scoped plugin renders CSS and the exact content-verification envelope;
it does not generate JSON-LD. The candidate therefore depends on the existing
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
owner-controlled storage outside Git. A future independent recorder/verifier
must recalculate the public HTTP receipt digest, resource manifest, screenshot
bytes/hashes and the harness, browser binary and exact command hashes. That
validator is not implemented here: the schema is classified
`UNVERIFIED_EXTERNAL_TEMPLATE_NO_ACCEPTANCE_AUTHORITY`, the gate is
`REQUIRED_VALIDATOR_NOT_IMPLEMENTED`, and Phase 3 stays `BLOCKED_EXTERNAL`.

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
