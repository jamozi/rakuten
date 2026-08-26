# RAOS Bounded Operator 2.0.0

This deterministic package preserves the closed ST-1506 v1 status, Yoast, and
child-theme surfaces and adds the ST-1704 publication controller under the
separate `raos-operator/v2` namespace.
The v2 controller supports only the WordPress 7.1.x release line and remains
unregistered on any other core version.

The v2 controller can only publish one of four generated article bindings after
a different wp-admin human approves the exact proposal hash. Both
`RAOS_OPERATOR_WRITES_ENABLED` and
`RAOS_ST1704_PUBLICATION_WRITES_ENABLED` are default-off host constants. There
is no REST approval route, generic post/taxonomy surface, term creation,
content/media mutation, or Codex self-approval.

Installation, activation, host-constant changes, and live publication are
external human-gated operations. The package and local tests are not staging or
Production evidence.
