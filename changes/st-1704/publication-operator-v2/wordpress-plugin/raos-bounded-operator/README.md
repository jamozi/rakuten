# RAOS Bounded Operator 2.1.13

This deterministic package preserves the closed ST-1506 v1 status, Yoast, and
child-theme surfaces and adds the ST-1704 publication controller under the
separate `raos-operator/v2` namespace. Version 2.1 adds the bounded
`REVISE_ST1704_DRAFT` operation while preserving the 2.0 publication status and
proposal contract.
Patch 2.1.1 verifies the exact WordPress 7.1 priority-12 redirect callbacks and
suppresses only their exact `_wp_old_slug` and `_wp_old_date` metadata API
shapes while `post_updated` is replayed. Existing metadata remains immutable,
and the private Review URL is not converted into an old-slug redirect.
The v2 controller supports only the WordPress 7.1.x release line and remains
unregistered on any other core version.

Patch 2.1.2 adds an admin Tools-only, two-stage reconciliation for exactly the
fixed portable-power post 28 and Anker post 29 replay incidents. With the
dedicated reconciliation gate in its mutually exclusive mode, a different
cookie-authenticated administrator can remove only exact unexpected core
redirect rows by locked `meta_id` CAS and then attest one owner-private public
verification artifact SHA-256. The proposal remains terminal, its counts do not
change, and the REST routes and schemas are unchanged.

Patch 2.1.3 exposes only a bounded internal error code to an administrator when
that gated reconciliation preview is refused. It does not render error
messages, error data, proposal material, or metadata values.

Patch 2.1.4 makes that rolled-back preview classify the known replay-exception
receipt separately from other result-code mismatches without rendering the
stored value. Neither class is eligible for cleanup.

Patch 2.1.5 admits the two exact replay terminal codes to the same complete
state proof. The receipt's actual result must match its audit event and is
bound into the cleanup hash. Every other result remains ineligible, and a
replay exception without exact published storage plus exact redirect-only meta
drift remains fail-closed.
This does not claim hook replay completion or repair untracked hook side
effects; the original exception receipt and result code remain unchanged.

Patch 2.1.6 adds only a bounded administrator diagnostic for a refused cleanup
submission. It distinguishes fixed authentication/evidence classes from one
fixed execution-refused class without rendering messages, error data,
submitted values, identifiers, metadata, or database details. Cleanup behavior,
receipts, audit rules, and REST authority are unchanged.

Patch 2.1.7 installs the separate `raos_draft_writer` role during ST-1704
activation and exact-verifies its persisted display name (`RAOS Draft Writer`)
and its complete capability set (`read`, `edit_posts`). Any creation,
persistence, or readback failure stops activation. It does not assign a user,
create an Application Password, modify `raos_operator_executor`, broaden the
Application Password firewall, or add publication/REST authority.

Patch 2.1.8 confines the distinct fixed-login `raos-draft-writer` Application
Password transport to raw HTTPS `GET` or `POST` on the WordPress core
`/wp/v2/posts` collection.
XML-RPC, method overrides, other methods, and other REST paths are refused.
The existing base-role authority to create and recover the user's own Drafts
is unchanged. Only the formal verifier's fixed post-sanitization `GET` shapes
can activate a per-request `user_has_cap` projection. It may satisfy only
`edit_post` for fixed public posts 19, 28, 29, 41, and 30, or Review Draft 26
at the exact payload-hash-bound carry-on Review slug. Nonmatching collection
requests fall back to base-role behavior without projection. State is cleared
before callback dispatch, at the first after-callback priority, and at
shutdown. The guard recognizes either the immutable login or the role marker,
so role removal/replacement before credential revocation remains refused. No
extra role/user capability is persisted and no publish, plugin, theme,
operator, or administration authority is added.

Patch 2.1.9 runs the transient capability projection at its earliest bounded
`user_has_cap` hook priority so its exact full-capability comparison sees the
persisted role baseline before ordinary filters can alter the received array.
The exact request, controller, `get_items`/`check_update_permission` stack,
post, and mapped-capability gates are unchanged.

Patch 2.1.10 adds only the observed dishwasher terminal publication incident
to the fixed reconciliation allowlist, bound through generated data to article
`st1704-countertop-dishwasher-for-small-households`, post 41, and its fixed
public slug. The portable-power and Anker incidents remain eligible and the
robot-vacuum article remains excluded. The canonical receipt stays terminal;
the workflow can only remove the exact locked redirect metadata and record one
owner-private verification evidence SHA-256. It does not repair or complete
hook replay, change proposal state/result/counts, broaden normal gates, or add
a REST authority.

Patch 2.1.11 permits one additional disposition only for that exact dishwasher
binding when the terminal audit still requires cleanup and locked metadata is
already the exact before-state multiset. `VERIFIED_NO_REDIRECT_META_ROWS` binds
its empty cleanup set, disposition, and `CLEAN` state into V2 operation
material, performs no metadata deletion, and then uses the same published-state
readback, audit append, and transaction commit. Existing exact-row incidents
retain their byte-compatible V1 operation material and stored operation hashes.
Portable-power, Anker, Robot, another post/slug, partial redirect metadata, or
any storage/audit drift cannot enter the no-row path.

Patch 2.1.12 adds the server-computed cleanup disposition to the private Tools
preview projection. The dishwasher no-row plan therefore renders
`VERIFIED_NO_REDIRECT_META_ROWS`, while completed portable-power and Anker
plans render `ALREADY_RECONCILED`. The value still comes only from the locked
server plan; no request field, operation material/hash, receipt, gate,
permission, REST route, or execution behavior changes.

Patch 2.1.13 adds only the observed Robot terminal incident at fixed post 30
and its generated public slug. Robot is eligible only for the locked `CLEAN`
state with empty cleanup rows/digests and strict current/expected and
before/after multiset hash equality. The exact-row disposition and executor
remain limited to Portable-power, Anker, and Dishwasher, so a Robot exact-row
plan is refused before any metadata deletion. The no-row disposition remains
limited to the literal Dishwasher and Robot bindings; Portable-power and
Anker clean states remain refused. Robot V2 operation material binds its exact
article, post, and public-slug hash. The Dishwasher V2 bytes/hash and existing
V1 exact-row bytes/hashes are unchanged. Robot no-row execution issues no
`DELETE` and retains the same SERIALIZABLE transaction, published readback,
audit append, distinct-human check, terminal receipt, gates, counts, and REST
surface.

The v2 controller can only publish one of four generated article bindings, or
revise the exact existing Draft IDs 28, 29, 41, and 30. A revision is
predecessor/successor hash-bound, remains Draft, and preserves post identity,
dates, taxonomy, media, and non-snapshot metadata. A different wp-admin human
must approve the exact proposal hash. Both
`RAOS_OPERATOR_WRITES_ENABLED` and
`RAOS_ST1704_PUBLICATION_WRITES_ENABLED` are default-off host constants. There
is also a default-off
`RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED` incident gate, which is
valid only while the normal publication gate is strict false. There
is no REST approval route, generic post/taxonomy surface, term creation,
generic content/media mutation, or Codex self-approval.

Authenticated revision recovery is limited to the same proposal ID. A terminal
proposal is classified under the publication mutex as the exact successor or
predecessor; an `APPLYING` proposal can only use the exact idempotent apply
retry.

Installation, activation, host-constant changes, and live publication are
external human-gated operations. The package and local tests are not staging or
Production evidence.
