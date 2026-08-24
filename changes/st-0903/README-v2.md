# ST-0903 V2 local publication snapshot candidate

This Story adds a deterministic, immutable, process-local publication snapshot
candidate. It composes one exact recorded-synthetic ST-0902 approval, the exact
current Content AST, ST-0807 route-only/noindex SEO and structured-data inputs,
and an ST-0808 admin-only media-validation input. Every material input is
content-addressed in the snapshot.

The result is deliberately **not publication-ready**. The common legacy
`publication-snapshot` schema still models an older article AST, while the
current canonical Content AST is `1.0.0`; the legacy schema also types product
selection references as UUIDs while the current AST uses closed `PSEL-*`
references. V2 preserves the current AST bytes and exact product-selection
references and records
`CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED`; it does not claim
that the legacy schema validated. This is the maximum safe local boundary
without inventing a schema decision.

The service and adapter run only in `ENV_DEV` or `CI`. They expose no network,
credential, persistence, event, public projection, CMS, media upload,
plugin/theme, publication, staging, release, or Production capability. All
external/formal statuses remain `NOT_EXECUTED`, and the Canonical human
publication gate remains intact.

Owner generation:

```text
.venv/bin/python scripts/build_st0903_publication_snapshot_runtime_v2.py
.venv/bin/python scripts/build_st0903_publication_snapshot_runtime_v2.py --check
```

The V1 reference-plan owner was also repaired to bind the actual ST-0306 and
ST-0307 generated contract hashes. V1 remains a non-executable planning
artifact; V2 is the local executable candidate.
