# ST-1501 local-code-complete preflight

- Story and objective: `ST-1501` — replace the interface-only candidate with a
  deterministic, provider-neutral Terraform foundation/admission module that is
  executable only for offline formatting and validation.
- Authority read: root and Canonical `AGENTS.md`, `RAOS-INTEGRATION-001`,
  `INT-DEC-007`, `OD-013`, the Canonical `ST-1501` backlog record,
  `RAOS-ARCH-001`, `RAOS-OPS-001`, `RAOS-SEC-001`, the infrastructure and SDLC
  controls, `TST-026`, the existing handoff, contract, builder, manifest,
  generated reference plan, and isolated tests.
- Open decision: `OD-013` remains unresolved. AWS and `ap-northeast-1` remain
  reference metadata only. No provider, account, backend, credential, live
  region, network, resource, budget, or apply authority will be selected.
- Planned owned changes: additive v1 contract revision, deterministic HCL and
  toolchain-lock outputs under `infra/terraform/foundation/`, the ST-1501 owner
  builder, isolated Story tests, README, manifest, and local completion record.
- Planned checks: deterministic generation and no-write check; isolated pytest;
  Terraform 1.15.9 `fmt -check` and `validate -json` in a network namespace and
  temporary directory; hostile provider/resource/backend/apply/drift tests;
  Ruff format/lint, mypy, Pyright, sensitive-data scan, and `git diff --check`.
- Out of scope: `terraform init/plan/apply/destroy/import/refresh`, provider or
  module download, provider lock/cache, AWS resources, remote state, account or
  region binding, credential access, external write, formal `TST-026`, hosted
  CI, staging, release, deployment, and Production.
