# ST-1704 publication operator v2 preflight

- Scope is only the four `PUBLISH_NEW` article IDs in the frozen ST-1704 v1
  publication plan. AT-003 and every generic post operation are excluded.
- The ST-1506 v1 main plugin, README, and both predecessor runtime manifests are
  SHA-256 pinned. The builder changes no v1 repository byte.
- `RAOS_OPERATOR_WRITES_ENABLED` and
  `RAOS_ST1704_PUBLICATION_WRITES_ENABLED` are both absent/false by default.
- A proposal can be applied only after a different `manage_options` human
  approves its exact SHA-256 in wp-admin with nonce, password reauthentication,
  reason, and the final 12 hash characters.
- Local tests and a deterministic package are not staging, Production, release,
  or publication evidence. Installation, activation, gate changes, and live
  publication remain external gated operations.

Result at implementation start: `LOCAL_PREFLIGHT_ONLY`; no live action executed.
