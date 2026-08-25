# RAOS Bounded Operator 1.0.0

This WordPress plugin exposes a deliberately closed operator surface for the
RAOS owner. It supports only two operations: applying the repository-defined
Yoast 28.3 profile and updating the fixed `kurashinoshirube-child` theme from a
hash- and manifest-bound ZIP.

Activation creates the dedicated `raos_operator_executor` role and the
proposal/audit tables. It never deletes data on deactivation or uninstall.
Assign the dedicated role to a service account and authenticate it using a
WordPress Application Password over HTTPS. Do not assign any additional role.

The first valid Application Password authentication observed for a user whose
only role is `raos_operator_executor` atomically creates the non-autoloaded,
write-once site binding `raos_operator_bound_user_id_v1` and the write-once,
network-global user-meta quarantine marker
`raos_operator_network_identity_v1`. A database-scoped named lock serializes
that bootstrap, and neither record is overwritten or deleted by the plugin. A
conflicting, duplicated, unavailable, or malformed record fails closed for the
marked operator without blocking unrelated users' Application Passwords.
Plugin load also promotes an existing valid site binding to the global marker
before accepting subsequent operator authentication.
Once marked, that credential is rejected on XML-RPC, non-REST requests, every
REST method/route outside the four handlers below, and every site other than
the exact fixed origin. This firewall remains in force if the local option is
absent or the account role or capabilities drift.

Multisite is unsupported. Activation is refused on multisite, and a marked or
locally bound operator credential is quarantined through global user meta and
rejected on every multisite subsite. The four own routes separately require a
single-site runtime, the exact role, and the exact capability set.

All proposal and apply mutations are disabled unless trusted host configuration
defines the following constant. There is intentionally no UI or REST toggle:

```php
define('RAOS_OPERATOR_WRITES_ENABLED', true);
```

An administrator must independently approve every exact proposal under
**Tools → RAOS Operator** using a cookie-authenticated session, a proposal nonce,
their current password, a 10–300 character reason, and the final 12 characters
of the proposal ID. REST and Application Password authentication cannot approve.

The REST namespace is `raos-operator/v1`:

- `GET /status`
- `POST /yoast-checksum`
- `POST /proposals`
- `POST /proposals/{64-hex-proposal-id}/apply`

Apply requires `If-Match: "{proposal-id}"` and the same unquoted 64-hex value
as `Idempotency-Key`. Theme apply bodies are raw ZIP bytes with
`Content-Type: application/zip`. No generic URL, option, plugin, media, delete,
filesystem, or arbitrary HTML operation exists.

All applies acquire one database- and site-scoped MySQL named lock with a zero
wait. The lock is checked before compare-and-swap, checked again immediately
after the `APPLYING` compare-and-swap commit and before target mutation, held
across the external mutation and terminal audit, and explicitly released.
Uncertain ownership or release fails closed, and a proposal already in
`APPLYING` becomes `NEEDS_RECOVERY`. This also serializes use of WordPress
core's shared theme temporary-backup directory.

Yoast's `wpseo` and `wpseo_social` rows are selected `FOR UPDATE`, compared to
the proposal's exact raw before-state, changed with byte-exact `BINARY`
row-level compare-and-swap, verified while locked, and committed together.
Profile keys use exact replacement so numeric and string non-profile keys keep
their original keys. Transaction rollback never writes a stale array over a
concurrent value. Cache reconciliation and readback happen after commit; any
post-commit drift becomes `NEEDS_RECOVERY`.
The fixed WordPress options table must report the exact `InnoDB` engine through
exact binary schema/table predicates in `information_schema`; exactly one row
must match. An ambiguous, unavailable, or legacy non-transactional engine is
rejected before the transaction begins.

Theme updates capture the complete old tree and use WordPress core temporary
backup APIs. The backup tree must byte-match that capture before any restore.
If the live tree already matches the old capture no restore occurs. After
backup deletion begins, restore is forbidden: a cleanup failure keeps the
verified new theme and becomes `NEEDS_RECOVERY`.
