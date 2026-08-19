# ST-1505 disabled staging workflow candidate

This slice adds a real GitHub Actions staging workflow shape while keeping every external-write phase disabled by default.

The workflow has only a manual dispatch trigger, uses the protected `staging` environment, grants only `contents: read` and `id-token: write`, and does not start unless `RAOS_STAGING_DEPLOYMENT_ENABLED` is explicitly set to `true`. Immutable artifact, SBOM, vulnerability-result, provenance and rollback hashes are admitted before any OIDC session is requested. The source commit is bound from `github.sha`, not from user input.

Third-party actions are pinned to immutable commits. The AWS session is short-lived and restricted by the externally configured staging role/account/region boundary. No long-lived cloud credential is consumed.

The workflow currently stops after admission and OIDC acquisition: artifact promotion, deployment, migration, smoke and browser phases remain explicitly `DISABLED`, with external-write and Production action counts fixed to zero. This lets workflow security and supply-chain admission be reviewed independently before executable staging permissions and commands are added.

Actual staging execution, AWS permission attachment, environment protection, TST-009/TST-022 evidence, release and Production remain NOT_EXECUTED.
