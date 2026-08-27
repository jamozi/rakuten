# ST-1704 WordPress publication operator v2

This additive slice extends the bounded ST-1506 plugin with two closed
operations: the byte-compatible `PUBLISH_ST1704_ARTICLE` v2 contract and the
additive `REVISE_ST1704_DRAFT` contract. Both can represent only the four new
articles in the ST-1704 v1 publication plan, one unresolved proposal at a time.

The builder verifies pinned v1/editorial inputs, generates the fixed binding,
injects the v2 controller into package bytes without editing v1 source, and
produces a deterministic `ZIP_STORED` package in an owner-private directory.
The tracked runtime manifest binds every runtime source and each packaged file.
The generated package advertises WordPress 7.1 and the v2 controller also
refuses to initialize outside the 7.1.x release line.

Package 2.1.9 keeps the publication and revision REST contracts unchanged. It
fail-closes unless the WordPress 7.1 old-slug and old-date callbacks have their
exact core registration, and prevents those callbacks from creating Review URL
redirect metadata during bounded `post_updated` replay. All other metadata,
including any pre-existing `_wp_old_slug` or `_wp_old_date` rows, remains part
of the exact immutable-state readback.

Patch 2.1.2 also adds a wp-admin Tools-only, two-stage incident reconciliation
for the fixed portable-power post 28 and Anker post 29 terminal receipts. It
discovers no arbitrary target: each fixed article/post binding must have exactly
one canonical `NEEDS_RECOVERY` receipt with the pinned replay failure, valid
expired approval evidence, exact audit history, and exact published storage.
The cleanup transaction can delete only the one bound Review-slug redirect row
and, when WordPress 7.1 would have added it, the one bound previous-date row by
exact `meta_id` CAS. A second form records only the SHA-256 of owner-private
public verification evidence. Neither stage changes the terminal proposal or
adds a REST route.

Patch 2.1.3 adds a bounded administrator-only diagnostic code to a refused
reconciliation preview. Error messages, error data, proposal material, and
metadata values remain undisclosed.

Patch 2.1.4 broadens only the rolled-back candidate preview read so it can
classify a known replay-exception receipt or another result-code mismatch.
Cleanup still requires the single original pinned replay-uncertain code.

Patch 2.1.5 admits the two exact post-commit replay outcomes (`UNCERTAIN` and
`EXCEPTION`) only when the full existing receipt, audit, current-storage, and
redirect-meta proof succeeds. The actual result is audit-matched and operation-
hash-bound; no other result code becomes eligible.
The exception receipt remains terminal because target-post equality cannot
prove or reverse every hook side effect. The reconciliation attests only the
exact metadata restoration and separately verified public surface.

Patch 2.1.6 separates a refused cleanup submission into bounded administrator-
only authentication/evidence codes or one fixed execution-refused code. It
does not expose error messages, error data, submitted values, proposal
material, database details, or any new write authority; cleanup semantics and
both REST contracts remain unchanged.

Patch 2.1.7 adds the exact `raos_draft_writer` (`RAOS Draft Writer`) role during
ST-1704 controller activation for the distinct owner-verification credential.
The role grants only `read` and `edit_posts`; activation removes any extra
capabilities and verifies the exact display name and capabilities in the
persisted WordPress role option. Creation, persistence, or exact-readback
failure stops activation. The patch does not assign the role, create a user or
Application Password, alter the bound operator identity/firewall, or add REST
or publication authority.

Patch 2.1.8 adds a fail-closed, verify-only read projection for the distinct
fixed-login `raos-draft-writer` Application Password without changing its
persisted capabilities.
The credential transport is confined to raw HTTPS `GET` or `POST` requests on
the core `/wp/v2/posts` collection; XML-RPC, method overrides, every other
method, and every other REST path are refused. The pre-existing base-role
authority to create and recover the user's own Drafts is unchanged. After
WordPress 7.1 sanitizes an exact formal-verifier `GET`, the controller requires
the core posts-controller callback and permission callback plus one fixed query
shape. A per-request `user_has_cap` bridge may satisfy only an `edit_post`
check for fixed public post IDs 19, 28, 29, 41, and 30, or fixed Review Draft
post 26 at the exact payload-hash-bound carry-on Review slug. Nonmatching
`GET`/`POST` requests receive only base-role behavior and never arm the bridge.
State is cleared before every callback, at the first after-callback priority,
and at shutdown. The projection never persists an extra role/user capability,
authorizes a write, changes article state, or changes the bound operator
firewall. The transport guard recognizes either that immutable WordPress login
or the role marker, so removing/replacing the role before credential revocation
is refused rather than turning the credential into an ordinary WordPress
Application Password.

Patch 2.1.9 evaluates the transient `user_has_cap` projection at its earliest
bounded hook priority, before ordinary capability filters can alter the
received array.
The existing exact full-capability comparison is retained, as are the armed
request, controller, `get_items`/`check_update_permission` stack, fixed post
ID/slug/status, and mapped-capability checks.

Normal execution still requires two default-off host gates and a distinct wp-admin
human approval of the exact proposal hash. There is no REST approval route, no
generic post or taxonomy surface, no unbound content/media mutation, and no Codex
self-approval. Nothing in this directory is a live publication or Production
readiness claim.

Run from the repository root:

```sh
make -f changes/st-1704/publication-operator-v2/Makefile check
```
