# RAOS Bounded Operator 2.1.0

This deterministic package preserves the closed ST-1506 v1 status, Yoast, and
child-theme surfaces and adds the ST-1704 publication controller under the
separate `raos-operator/v2` namespace. Version 2.1 adds the bounded
`REVISE_ST1704_DRAFT` operation while preserving the 2.0 publication status and
proposal contract.
The v2 controller supports only the WordPress 7.1.x release line and remains
unregistered on any other core version.

The v2 controller can only publish one of four generated article bindings, or
revise the exact existing Draft IDs 28, 29, 41, and 30. A revision is
predecessor/successor hash-bound, remains Draft, and preserves post identity,
dates, taxonomy, media, and non-snapshot metadata. A different wp-admin human
must approve the exact proposal hash. Both
`RAOS_OPERATOR_WRITES_ENABLED` and
`RAOS_ST1704_PUBLICATION_WRITES_ENABLED` are default-off host constants. There
is no REST approval route, generic post/taxonomy surface, term creation,
generic content/media mutation, or Codex self-approval.

Authenticated revision recovery is limited to the same proposal ID. A terminal
proposal is classified under the publication mutex as the exact successor or
predecessor; an `APPLYING` proposal can only use the exact idempotent apply
retry.

Installation, activation, host-constant changes, and live publication are
external human-gated operations. The package and local tests are not staging or
Production evidence.
