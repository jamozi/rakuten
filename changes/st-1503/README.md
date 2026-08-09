# ST-1503 compute and edge interface-only candidate

This Story-owned slice records the maximum-safe logical compute, edge, route,
and health intent that can be derived from the approved RAOS design. It does
not select a provider account, native IaC toolchain, network, domain, route,
certificate, WAF policy, workload size, image, identity, or health matcher. It
is not executable Terraform, an AWS configuration, a native plan, or a
deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026 and TST-027: `NOT_EXECUTED`
- Native Terraform/OpenTofu and AWS/provider validation: `NOT_EXECUTED`
- Health, performance, hosted CI, staging, release, apply, and Production:
  `NOT_EXECUTED`

ST-1501 exists only as a disabled local reference/interface predecessor. The
ST-1503 builder binds its exact contract and reference-plan bytes plus its
fail-closed activation and zero-action semantics. That predecessor does not
establish a native IaC toolchain or make this Story Done or `VALIDATED`.

## Logical intent and safe defaults

The source contract names only the canonical reference component families:
ECS Fargate compute, ECR registry, an ALB origin boundary,
CloudFront/WAF/ACM edge, and Route53 DNS. These names are inert labels, not
provider resources or configuration payloads.

Four logical workload roles are fixed: `public_web`, `admin_web`, `core_api`,
and `worker_pool`. Public, Admin, and Internal surfaces require separate trust,
cache, cookie, host, CSP, and authentication boundaries. Public access is
limited to the Public Projection and cannot reach the internal data plane
directly. Admin access requires approved identity and authorization, without
selecting an IdP. Core API, Worker, and data origins remain private-only.

Immutable digest-selected images, signed provenance, SBOMs, scanning,
least-privilege workload identities, encrypted logs, and graceful shutdown are
future requirements recorded as `REQUIRED_NOT_CONFIGURED`. No secret material
is present.

Liveness and readiness are distinct logical requirements. Liveness is process
only and must not fail because an external provider is unavailable. Readiness
must account for dependencies and migration compatibility with bounded failure
behavior. Endpoint paths, ports, status codes, ALB matchers, response schemas,
intervals, timeouts, and thresholds all remain unset; a successful HTTP body
is not inferred to be a readiness contract.

All CDN, WAF, TLS, DNS, certificate, origin, target group, listener, route,
domain, host, WAF-rule, rate, cache, task CPU/memory/count/autoscaling, ECR,
image, subnet, security-group, public-IP, IAM, account, region, backend,
credential, tool, and provider values remain null or empty. Activation is
disabled, native operations and external writes are forbidden, and planned
create/update/delete actions are exactly zero.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the Story contract or builder and
regenerate.

| Classification | Path | Role |
| --- | --- | --- |
| Story source | `changes/st-1503/contracts/compute-edge-foundation.v1.yaml` | Closed logical intent and safety boundary |
| Implementation source | `scripts/build_st1503_compute_edge.py` | Strict validator and deterministic owner builder |
| Test source | `tests/st1503/*.py` | Positive, hostile, exact-type, provenance, and no-write checks |
| Generated reference plan | `infra/terraform/compute-edge/compute-edge.reference-plan.v1.json` | Non-executable logical compute/edge successor plan |
| Generated inventory | `changes/st-1503/manifest.yaml` | Source, predecessor, authority, and generated-output hashes |

Generate the two ST-1503-owned outputs:

```bash
uv run --locked --no-sync python scripts/build_st1503_compute_edge.py
```

Verify all source/predecessor bindings and committed bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1503_compute_edge.py --check
```

The builder exposes no provider, resource, domain, route, health, credential,
network, sizing, activation, or native-operation argument. It imports no AWS
SDK, reads no ambient credential or environment selection, invokes no
subprocess or native IaC, accesses no network, and performs no external write.

## Completion boundary

This slice supports only a local partial implementation checkpoint. Exact
Terraform/OpenTofu and AWS-provider provenance, HCL/resources, physical
network/IAM/edge/compute configuration, runtime health and load tests, formal
TST-026/TST-027, hosted CI, AWS, staging, release, deployment, and Production
remain separately unexecuted.
