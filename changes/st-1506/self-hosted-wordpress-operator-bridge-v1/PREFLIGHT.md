# ST-1506 self-hosted WordPress operator bridge preflight

- Selected Story: `ST-1506` — Production environment protection and canary
  definition.
- Selected integration slice: `SELF_HOSTED_WORDPRESS_OPERATOR_BRIDGE_V1`.
- Objective: provide a default-disabled, least-privilege bridge through which Codex
  can inspect the existing WordPress installation and execute one exact operation
  only after a different, cookie-authenticated human has approved its immutable
  proposal hash.
- Canonical sources read: `RAOS-INTEGRATION-001`, `INT-DEC-013`, `ST-1506`, the
  security role/control catalogs, and `TST-001`, `TST-012`, `TST-026`, and
  `TST-032`.
- Existing implementation sources read: the provider-neutral ST-1506 production
  contract and the ST-1704 self-hosted editorial/Yoast boundary.
- Additive policy record: the repository-owner grant, including permission to
  revise upper Canonical sources, is recorded in this slice's ADR and handoff.
  This bridge is a compatible refinement, so the imported Canonical package is
  left byte-unchanged to avoid regenerating unrelated owners. Existing `OD-009`,
  `OD-011`, `OD-013`, and `OD-015` remain inherited and unresolved.
- Safe default: no installed executor principal and
  `RAOS_OPERATOR_WRITES_ENABLED !== true`.
- Planned files: a versioned contract and handoff, an approval-boundary ADR, a
  deterministic plugin package/runtime-manifest builder, a closed Python client,
  a WordPress plugin, a repository-local Makefile, tests, and this runbook.
- Planned checks: YAML parse, policy-boundary assertions, exact route and
  capability inventory, fixed Application Password identity and REST/XML-RPC
  firewall, network-global operator quarantine and complete Multisite refusal,
  three-point apply-mutex ownership, transactional byte-exact InnoDB Yoast row
  CAS, verified theme backup recovery, forbidden-surface scan, deterministic
  ZIP bytes and manifest hashes, fixed isolated launcher and current-HEAD runtime
  verification, closed CLI/transport checks, HTTP debug suppression,
  effective-UID ownership, ambiguous receipt retention, secret-redaction checks,
  and `git diff --check`.
- Out of scope: post content/status, publication, taxonomy, media, the human plugin
  install/activation action, generic or runtime users/roles mutation beyond the
  deterministic activation-time executor-role reconciliation, arbitrary options,
  except the fixed write-once bound-executor identity option and network-global
  user-meta quarantine marker,
  generic WordPress REST, arbitrary HTTP/PHP/SQL, credential entry, live execution,
  release, staging or Production evidence, and a claim that formal `TST-032`
  executed.
