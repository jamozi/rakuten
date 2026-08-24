# ST-1501 local completion evidence v2

## Claim boundary

- Story: `ST-1501` only.
- Base integration commit:
  `cd0ce8fa5c9eff20b4bb9ea699e07e1260b6b340`.
- Proposed local state: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`.
- Formal `TST-026`, hosted CI, provider runtime, staging, release, deployment,
  and Production: `NOT_EXECUTED`.
- Canonical Story/status-registry transition: unchanged. This file is local
  evidence, not `VALIDATED`, release, provider, staging, or Production evidence.

## Implemented boundary

The owner generator now emits a deterministic five-file Terraform foundation
module. It is executable only for `fmt` and `validate`, is disabled by default,
contains no provider requirement, provider, backend, cloud, module, data,
resource, provisioner, credential, selected region, selected account, or state
binding, and declares exactly zero create/update/delete actions. AWS Tokyo is
retained only as Canonical Reference Architecture metadata.

The contract and generated lock pin the validation-only Terraform CLI to
version `1.15.9` on `linux_amd64`:

- official archive SHA-256:
  `76edd0b22d2f27d3d2e097cd793209646f719cf60f02ff3af626b07361137da1`;
- extracted binary SHA-256:
  `c39d41adb17963bac5dd610ad47815dd81e945371a7cabc344a45d63b1b093bd`;
- official signing-key fingerprint:
  `C874011F0AB405110D02105534365D9472D7468F`.

Normal generation and `--check` execute no subprocess and have no network
library surface. The explicit native check accepts only the pinned binary,
uses `/usr/bin/unshare --user --map-root-user --net`, passes a closed environment,
and invokes only `version -json`, `fmt -check -recursive`, and
`validate -json`. `init`, provider installation/discovery, plan, apply, destroy,
import, refresh, test, console, credential inheritance, backend access, provider
calls, and external writes remain forbidden.

## Verification-only tool acquisition

On 2026-08-25, an explicit verification-only maintenance step downloaded the
Terraform `1.15.9` Linux amd64 archive, checksum manifest, detached checksum
signature, and current HashiCorp public signing key from their official HTTPS
endpoints into a temporary directory outside the repository. The detached
signature was verified against the exact fingerprint above; the archive and
extracted binary matched the pinned SHA-256 values. No binary, public-key ring,
download cache, provider plugin, or `.terraform` directory was committed.

The checksum-verified temporary binary then passed the owner-native check in a
new network namespace. The reported version/platform were exactly
`1.15.9`/`linux_amd64`, provider selections were empty, format validation passed,
`terraform validate -json` reported `valid: true` with zero errors, and the
repository/generated HCL byte/mtime/mode snapshots remained unchanged.

## Local checks

The source-freeze gate produced these repository-local results:

| Gate | Result |
| --- | --- |
| `pytest -q tests/st1501` | `PASS`; `175 passed` |
| owner regeneration | `PASS`; all eight owner outputs regenerated |
| owner `--check` | `PASS`; byte-for-byte no-write check |
| checksum-pinned native check | `PASS`; exact version, format, init-free semantic validation, network namespace, and repository no-write |
| Ruff format and lint for the owner script and `tests/st1501` | `PASS` |
| strict mypy for the owner script | `PASS`; no issues |
| pinned Pyright `1.1.411` for the owner script | `PASS`; zero errors, warnings, or information diagnostics |
| Python compile/import for the owner script and five Story test modules | `PASS`; bytecode redirected outside the repository |
| focused maintained secret scan under a denied-network namespace | `PASS`; 20 exact Story-owned files, zero findings |
| `git diff --check` | `PASS` |

Hostile coverage includes forbidden CLI commands; tool hash, version, command,
and network-policy drift; provider/resource/data/module/backend/cloud/import HCL
injection; forbidden execution/provider fragments; selected binding and AWS
reference promotion; nonzero action counts; malformed/aliased YAML; symlink and
ancestor escape; generated-byte drift; alternate namespace runner; unpinned
validator; normal-check subprocess use; and native/repository write detection.

## Debt reconciliation

`DEBT-W1-021`'s ST-1501-owned interface-only gaps are locally closed by this
revision: an exact validation-tool provenance contract and lock exist, executable
provider-neutral HCL exists, offline/init-free format and semantic validation are
reproducible, and policy, drift, no-apply, no-network, and no-write negatives are
implemented. The global append-only debt ledger is intentionally not edited in
this isolated Story ownership scope; the integration owner can record this as the
local closure evidence for those clauses.

The remaining clauses are not hidden or converted into local failures:

- a provider lock/cache is not applicable to this zero-provider module and must
  be introduced and pinned only by a successor resource contract;
- remote-state selection/recovery evidence and AWS or alternative-provider
  resource graphs remain successor/external work;
- OD-013 primary/backup region, cross-border treatment, and data residency remain
  `HUMAN_DECISION_REQUIRED`;
- provider/account/backend/credential/live environment work remains externally
  blocked;
- formal `TST-026`, hosted CI, staging, release, deployment, and Production remain
  `NOT_EXECUTED`.

Accordingly `DEBT-W1-020` and the external/formal part of `DEBT-W1-023` remain
unchanged, while `DEBT-W1-021` no longer represents an ST-1501 local-code gap.
