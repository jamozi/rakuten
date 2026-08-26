# ADR-001: Hash-bound independent approval for WordPress operations

Status: accepted as an additive ST-1506 integration decision. The repository
owner also permits an upper-Canonical revision, but none is required for this
compatible refinement. The imported Canonical package remains unchanged to avoid
invalidating unrelated owner-generated evidence.

## Context

The repository owner authorizes Codex to operate the existing WordPress site,
including maintenance writes, while retaining a human check for security-sensitive
actions. Codex needs a stable server-side interface to read selected WordPress state
and to apply narrowly defined maintenance changes. Giving its Application Password
an Administrator role, a generic REST proxy, or an approval flag in the same API
request would let the executor widen or approve its own authority. That would
contradict the inherited `INT-DEC-013` boundary.

## Decision

Codex may execute an operation only when a default-disabled bounded server operator
has validated it and a different human has approved the exact immutable proposal
identifier. This additive permission does not authorize Codex to approve itself.

The bridge exposes exactly four REST resources under `raos-operator/v1`: status,
Yoast checksum verification, immutable proposal creation, and application of one
approved proposal. The only write operation types are `APPLY_YOAST_PROFILE` and
`UPDATE_CHILD_THEME`.

The first valid Application Password authentication for an exact single-role
executor atomically binds its positive WordPress user ID in the fixed,
non-autoloaded `raos_operator_bound_user_id_v1` option and the write-once,
network-global `raos_operator_network_identity_v1` user-meta quarantine marker.
A database-scoped zero-wait mutex serializes creation, and neither binding is
overwritten, reconciled, or deleted by the plugin. Multisite is unsupported:
activation and bridge execution are refused, while the global marker ensures the
bound credential is also refused on every subsite without blocking unrelated
Application Password users. The credential is additionally refused for XML-RPC,
non-REST authentication, a different origin, and all REST callbacks outside the
four exact method/route/plugin-callback pairs.

The proposal identifier is the lower-case hexadecimal SHA-256 of the canonical
validated proposal request bytes. Those bytes bind the exact site origin, integer
contract and profile versions, internally generated request token, operation, TTL,
and closed operation payload. The identifier is also the sole ETag. The server
stores the validated request and before-state immutably. Application requires a
quoted `If-Match` containing that identifier and an unquoted `Idempotency-Key`
containing the same identifier.

Both mutation types share one database advisory apply mutex scoped by database,
table prefix, and exact origin. A zero-wait failure refuses before target mutation;
the mutex remains held through target mutation, recovery/readback, terminal state,
and terminal audit. Connection ownership is verified before before-state capture,
immediately after the `APPLYING` compare-and-swap commit and before target
mutation, and before terminal persistence. Verified release occurs in `finally`.

Before its first proposal-create request, the client persists a non-credential
owner-private intent containing the operation, internally generated request token,
proposal identifier, and an explicit canonical-request SHA-256 equal to that
identifier. Full-file fsync, atomic hard-link publication, and directory fsync
precede transport. A retry for the
same operation reuses that exact unresolved intent; it cannot silently mint a
second proposal after a response is lost. Transport failure, response ambiguity,
input drift, or an invalid receipt leaves the intent unchanged. A validated matching
receipt with the exact 900-second TTL clears it. An exact expired or terminal replay
also clears the now-resolved communication intent but returns non-success
`NEW_PROPOSAL_REQUIRED`; it cannot permanently block a fresh intent. Python and PHP
canonicalization are both bound to the committed golden proposal vector.

Operational commands enter only through the fixed executable BusyBox launcher.
It replaces the inherited environment, pins the owner-managed CPython 3.14.6 with
`-B -I -S`, accepts only the closed command shapes, streams the exact current-HEAD
CLI blob over FIFO stdin, and verifies every declared runtime working file against
the same HEAD. Runtime modules are then compiled from those already captured
committed bytes through a closed in-memory loader; their filesystem paths are not
reopened for import. Direct script execution or an imported `main()` refuses before
credential or network access. Credential and journal objects capture the effective
UID once at construction. Every HTTPS connection forces and verifies `debuglevel`
zero before a secret-bearing request.

A fresh intent accepts only `replayed:false`; a contradictory replay or any
malformed post-write receipt is `OUTCOME_AMBIGUOUS` and retains the intent. An
`APPLIED` receipt must bind `YOAST_PROFILE_APPLIED` to `APPLY_YOAST_PROFILE` or
`THEME_UPDATE_APPLIED` to `UPDATE_CHILD_THEME`; cross-operation success codes are
also ambiguous and cannot clear the journal.

If the create response was lost but the proposal ID was obtained through the human
admin review path and later applied, a validated `APPLIED` receipt also clears an
unresolved intent only when both operation and proposal ID match. No intent or a
different ID is left unchanged without error. Ambiguous or unsuccessful apply never
clears the intent.

Approval is never a REST operation. A different `manage_options` user must use the
plugin's `wp-admin` Tools page in a cookie-authenticated session. The approval
handler requires the proposal-specific WordPress nonce, current-password
reauthentication, a 10–300 character reason, and the exact final 12 hexadecimal
characters of the proposal identifier. It compare-and-swaps `PROPOSED` to
`APPROVED`, binds the approver, approval and expiry times, reason, proposal
identifier, and audit hash, and refuses the proposing executor as approver.
Application Password authentication cannot create that browser session or nonce.

Every mutation additionally requires the immutable host configuration constant
`RAOS_OPERATOR_WRITES_ENABLED` to be defined and exactly `true`. No REST or
WordPress option can enable it. Plugin installation/activation and that host
constant remain human bootstrap operations under the inherited Production gates.
Activation may idempotently create or reconcile only the exact
`raos_operator_executor` role and four-capability set, without deleting and
recreating the role. Runtime REST/CLI role or user mutation is absent. Deactivation
and uninstall never delete users, proposals, audit data, either fixed bound-user
identity record, or the role automatically.

## Consequences

- Codex can create an exact proposal, wait for a human decision, then apply and
  verify the already-approved proposal without receiving Administrator authority.
- A proposal edit changes its identifier and invalidates the approval.
- Approval replay, expiry, state drift, capability mismatch, missing `If-Match`,
  or disabled host configuration fails closed.
- Yoast application revalidates the profile stored in the approved request against
  both the fixed contract and runtime prerequisites, then merges those stored
  values only into `wpseo` and `wpseo_social`. Runtime-derived values cannot replace
  the approved write source. It locks both raw option rows, preserves every other
  entry, numeric key, and autoload value, conditionally updates the captured rows
  using byte-exact binary predicates, and verifies them before commit. The exact
  current-prefix options table must first be proven by exactly one byte-exact
  information-schema row reporting `InnoDB`. Failure uses transaction rollback and
  exact raw-row verification; stale option restoration is forbidden.
- A child-theme restore is allowed only from a symlink-free backup whose complete
  manifest matches the captured before tree. Backup cleanup is an irreversible
  boundary: after it begins, cleanup failure retains and verifies the new theme and
  reports recovery-required without attempting restore.
- Publication remains a separate `ST-0905`/`ST-1704` extension and is not smuggled
  into this maintenance bridge.
- Local package and contract checks are implementation evidence only. They do not
  establish a live connection, execute `TST-032`, or make ST-1506 Production-ready.
