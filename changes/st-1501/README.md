# ST-1501 provider-neutral Terraform foundation

ST-1501 now has a maximum-safe local implementation: a deterministic Terraform
module that is executable only for formatting and semantic validation. It
contains no provider requirement, provider block, backend, cloud block, module,
data source, resource, provisioner, state operation, or infrastructure action.

## Status boundary

- Local implementation: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`
- Canonical Story state: unchanged until the append-only governance workflow
- Formal `TST-026`: `NOT_EXECUTED`
- Live provider/account/backend/credential validation: `NOT_EXECUTED`
- Staging, release, deployment, infrastructure apply, and Production:
  `NOT_EXECUTED`

Local pytest, deterministic generation, and native Terraform validation are not
formal Security verification and do not make this Story `VALIDATED` or
Production-ready.

## OD-013 and reference metadata

`OD-013` remains `HUMAN_DECISION_REQUIRED`. AWS and `ap-northeast-1` remain the
Canonical reference architecture inherited from `INT-DEC-007`; neither is a
selected, default, fallback, or admitted provider/region binding. The module
requires every selected infrastructure field to remain null, every capability
mapping to remain empty, activation and Production-apply authority to remain
false, and create/update/delete counts to remain zero.

No real provider, account/project/tenant, primary or backup region, provider
plugin, state backend, credential source, CIDR, availability zone, KMS key,
budget, or resource is configured. Successor resource modules require their own
contract revision and complete security, operations, release, recovery, cost,
and residency evidence.

## Generated HCL

The owner builder generates a closed module under
`infra/terraform/foundation/`:

| File | Role |
| --- | --- |
| `versions.tf` | Exact Terraform CLI constraint; no providers or backend |
| `variables.tf` | Null/false/empty admission inputs with fail-closed validation |
| `locals.tf` | Reference metadata, capability inventory, and zero-action boundary |
| `checks.tf` | Disabled execution, null binding, empty mapping, and zero-action assertions |
| `outputs.tf` | Deterministic non-secret admission and safety projection |

The HCL permits only `terraform`, `variable`, `locals`, `check`, and `output`
top-level blocks. The Story policy validator rejects provider, backend, cloud,
module, data, resource, import, run, provisioner, remote-state, external
execution, or provider-source material before native validation.

## Validation-only toolchain

The contract and generated toolchain lock pin Terraform `1.15.9` for
`linux_amd64`. The official release archive SHA-256 is
`76edd0b22d2f27d3d2e097cd793209646f719cf60f02ff3af626b07361137da1`;
the extracted binary SHA-256 is
`c39d41adb17963bac5dd610ad47815dd81e945371a7cabc344a45d63b1b093bd`.
The checksum manifest is signed by the current HashiCorp key fingerprint
`C874011F0AB405110D02105534365D9472D7468F`.

Binary acquisition is an explicit online maintenance action. Normal generation
and checks never download a tool, provider, or module. Native verification
requires an already checksum-verified absolute binary path and executes only:

- `terraform version -json`
- `terraform fmt -check -recursive`
- `terraform validate -json`

The owner wrapper verifies the extracted binary digest, removes ambient
credentials by constructing a closed environment, creates an isolated temporary
module and data directory, and launches every command inside a fresh Linux user
and network namespace. It never runs `init`, `plan`, `apply`, `destroy`,
`import`, `refresh`, `test`, or `console`; it verifies that neither the temporary
module nor committed generated files changed.

## Owner-generated artifacts

Do not hand-edit the manifest, reference plan, toolchain lock, or HCL files.
Change the Story contract or owner builder, then regenerate:

```bash
uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py
```

Read-only deterministic check:

```bash
uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py --check
```

Read-only native validation after separately verifying the official archive,
checksum manifest, signature, signing fingerprint, and extracted binary:

```bash
uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py \
  --native-check \
  --terraform /absolute/path/to/terraform
```

The native command is init-free, provider-free, module-download-free,
backend-free, credential-free, and network-isolated. It does not produce a
Terraform plan or state file.

## Artifact ownership

| Classification | Path |
| --- | --- |
| Durable provider-neutral decision | `changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml` |
| Local implementation record | `changes/st-1501/IMPLEMENTATION_RECORD_V2_ST1501_HCL_FOUNDATION.yaml` |
| Local completion evidence | `changes/st-1501/LOCAL_COMPLETION_EVIDENCE_V2.md` |
| Story source contract | `changes/st-1501/contracts/terraform-foundation.v1.yaml` |
| Owner builder and offline/native validator | `scripts/build_st1501_terraform_foundation.py` |
| Generated HCL and locks | `infra/terraform/foundation/**` |
| Generated inventory | `changes/st-1501/manifest.yaml` |
| Hostile and positive tests | `tests/st1501/**` |

## Remaining external/formal work

Production and backup region/residency approval, accounts, provider/resource
modules, provider locks/cache, remote-state encryption/locking/audit/recovery,
credential and workload identity, live network topology, drift against a live
environment, budget/stop controls, Security review, formal `TST-026`, hosted CI,
staging, release, deployment, and Production remain outside this local Story
completion and remain `NOT_EXECUTED`.
