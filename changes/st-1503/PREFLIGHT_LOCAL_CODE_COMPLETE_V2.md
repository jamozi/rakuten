# ST-1503 local-code-complete preflight v2

## Story and objective

- Story: `ST-1503` — Compute/CDN/WAF infrastructure.
- Objective: close the maximum-safe repository-local part of the
  ECS/Fargate/ECR/ALB/CloudFront/WAF/Route53/ACM-equivalent compute and edge
  topology while every physical provider and Production choice remains unset.

## Inputs read

- Canonical integration priority/protocol, Story `ST-1503`, dependency
  `ST-1501`, INT-DEC-007, OD-002/009/010/011/013/015.
- RAOS architecture, security/privacy and control catalog, operations design,
  test acceptance design, formal TST-026/TST-027 definitions.
- Current ST-1503 design handoff, source contract, builder, reference plan,
  manifest, tests, and `DEBT-W1-028`.
- Integrated ST-1501 validation-only Terraform foundation and ST-1502
  provider-schema-free logical-HCL implementation pattern.

## Ambiguities and safe decision

No live account, domain, region, provider schema/plugin, network, image digest,
workload identity, secret reference, health endpoint, WAF rule/rate, or sizing
value is approved. The implementation therefore uses logical declarations,
closed empty activation inputs, recorded no-apply fixtures, and the exact
ST-1501 Terraform 1.15.9 parser/formatter boundary. It does not invent any
physical value or provider schema.

## Planned owned files

- `changes/st-1503/**`
- `infra/terraform/compute-edge/**`
- `scripts/build_st1503_compute_edge.py`
- `tests/st1503/**`

The generated module will use only `terraform`, `variable`, `locals`, `check`,
and `output` blocks. It will contain no provider/backend/module/data/resource/
provisioner block and expose no infrastructure action.

## Planned checks

- isolated `tests/st1503` and exact ST-1501/ST-1502 dependency regressions;
- owner regeneration, no-write check, and checksum-pinned offline native
  `fmt`/`validate` under a denied-network namespace;
- Python compile/import, Ruff lint/format, strict mypy, Pyright;
- maintained sensitive-data scan over exact owned paths;
- `git diff --check` and owned-scope review.

## Out of scope

Formal TST-026/TST-027, AWS/provider schema validation, actual account/region/
network/domain/DNS/TLS/WAF/image/identity/secret/health bindings, load/failure
tests, hosted CI, staging, deployment, release, apply, and Production remain
`NOT_EXECUTED`. No status-registry or central debt-ledger entry is changed by
this isolated Story commit.
