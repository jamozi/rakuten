# ST-0107 GitHub governance v2

This directory owns the local desired state for the repository ruleset. ST-0107 is
a tracking identifier, not an implementation or approval boundary.

The v2 policy keeps only irreversible-history protections at the GitHub boundary:

- default-branch deletion and force-push are prohibited;
- required approval count is zero;
- code-owner, last-push, stale-review, and review-thread approval gates are disabled;
- `Final Integration` is the only required check;
- a green final integration result enables squash auto-merge.

The contract and generator are normal tracked sources. Their URI and semantic
version identify them; their bytes are not approval authority. Generated ruleset
output remains content-addressed and is checked by the shared build manifest.

Use the repository-wide commands from the root `Makefile`:

```text
make setup
make generate
make check
make fast
make final
```

The old Story-specific preflight, evidence ledger, and live activation procedure
are archived history. GitHub branch/ruleset/PR operations are ordinary development
operations under the repository standing authorization. Credentials are never read
or printed. Deployment, staging, release, publication, provider, and Production
actions remain outside this scope.
