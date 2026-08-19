# ST-1506 disabled Production admission candidate

This slice adds a real Production admission workflow shape while keeping every Production mutation disabled by default.

The workflow requires four independent immutable SHA-256 references for the release decision, gate report, Security approval, and Operations approval. It also binds the exact staging artifact, staging evidence receipt, rollback artifact, and source commit from `github.sha`. Zero, malformed, duplicate approval references and rollback equal to the promoted staging artifact fail admission.

Only a manual dispatch trigger exists. The job is bound to the `production` GitHub environment and does not start unless `RAOS_PRODUCTION_DEPLOYMENT_ENABLED` is explicitly set to `true`. Permissions are limited to `contents: read` and `id-token: write`; third-party actions are immutable commit pins and checkout credentials are not persisted.

Even after admission and short-lived OIDC acquisition, artifact promotion, Production deployment, migration, canary, traffic change and rollback execution remain explicitly disabled. TST-032 stays NOT_EXECUTED and Production/traffic action counts remain zero.

This candidate does not approve a release or establish that the referenced evidence is human-approved; later executable work must verify the referenced artifacts against their authoritative stores and bind canary/telemetry/rollback commands before any Production attempt can be enabled.
