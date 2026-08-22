# ST-1503 provider-neutral compute and edge interface candidate

This Story-owned slice records a strict provider-neutral compute and
public-edge admission boundary. The direct owner
`DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml` governs this new
decision together with the Canonical Story and design sources; the older
Pro-derived implementation-first slice alone does not govern it. No provider,
account or project, region, runtime, scheduler, registry, network, domain,
route, certificate, WAF or abuse policy, workload size, image, identity,
secret, credential, or health matcher is selected. This is not executable
Terraform, a provider configuration, a native plan, or a deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026 and TST-027: `NOT_EXECUTED`
- Native IaC and provider validation: `NOT_EXECUTED`
- Health, performance, hosted CI, staging, release, apply, and Production:
  `NOT_EXECUTED`

ST-1501 exists only as a disabled provider-neutral reference/interface
predecessor. The ST-1503 builder hash-binds and fully validates its direct
handoff, contract, deterministic reference-plan bytes, admission boundary,
forbidden operations, and zero-action semantics. That predecessor does not
select a provider or establish a native IaC toolchain, and it does not make
this Story Done or `VALIDATED`.

## Capability admission and safe defaults

The closed capability inventory covers workload runtime, scheduling, and
supply chain; public ingress, edge/CDN, and private origin control; DNS/TLS and
certificate lifecycle across Public, Internal, Provider, and origin traffic;
WAF, abuse, rate limiting, and attack controls;
Public/Admin/Internal/data-plane isolation; workload identity, secrets, and
controlled egress; observability, health, canary, and rollback; and
region/residency/failure-domain evidence. A future AWS, other-cloud, or
owner-managed profile is eligible only after exactly one mapping exists for
every capability and identical security, operations, release, performance,
health, rollback, isolation, and residency evidence exists.

ECS, Fargate, ECR, ALB, CloudFront, WAF, Route53, and ACM remain only optional
historical AWS reference mappings inherited from INT-DEC-007 and
RAOS-ARCH-001. They are never defaults, implicit fallbacks, selected bindings,
eligibility shortcuts, admission requirements, or evidence substitutes.
Missing, unknown, duplicate, reordered, partial, implicit,
provider-label-only, service-label-only, and reference-only mappings fail
closed. No concrete alternate provider is selected.

Four logical workload roles are fixed: `public_web`, `admin_web`,
`core_api`, and `worker_pool`. Public, Admin, and Internal surfaces require
separate route, trust, cache, cookie, host, CSP, and authentication boundaries.
Public access is limited to the Public Projection and cannot reach the
internal data plane directly. Admin access requires approved identity and
authorization without selecting an IdP. Core API, Worker, provider, and data
origins remain private-only.

Immutable digest-selected images, signed provenance, SBOMs, scanning, bounded
scaling, failure-domain distribution, least-privilege workload identities,
controlled egress, encrypted logs, and graceful shutdown are future
requirements recorded as `REQUIRED_NOT_CONFIGURED`. No secret material is
present.

Liveness and readiness are distinct logical requirements. Liveness is process
only and must not fail because an external provider is unavailable. Readiness
must account for dependencies and migration compatibility with bounded failure
behavior. Endpoint paths, ports, status codes, response schemas, intervals,
timeouts, and thresholds all remain unset; a successful HTTP body is not
inferred to be a readiness contract. Telemetry, SLO capacity, alert ownership,
runbooks, canary promotion, rollback, and health/load evidence remain required
but not configured or executed.

All runtime, scheduler, registry, ingress, edge, WAF, TLS, DNS, certificate,
origin, route, domain, host, rule, rate, cache, workload sizing, image,
failure-domain, network-segment, traffic-policy, workload-identity, secret,
account/project, region, credential, plugin/adapter, and provider values remain
null or empty. OD-002, OD-009, OD-010, OD-011, OD-013, and OD-015 remain
unresolved with their fail-closed defaults. Activation is disabled; network,
credential, provider, deploy, release, Production, native-operation, and
external-write paths are forbidden; planned create/update/delete actions are
exactly zero.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the Story handoff, contract, or
builder and regenerate.

| Classification | Path | Role |
| --- | --- | --- |
| Story decision source | `changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml` | Durable provider-neutral decision and gates |
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

The builder exposes no provider, profile, resource, domain, route, health,
credential, network, sizing, activation, or native-operation argument. It
imports no provider SDK, reads no ambient credential or environment selection,
invokes no subprocess or native IaC, accesses no network, and performs no
external write.

## Completion boundary

This slice supports only a local partial implementation checkpoint. Native-IaC
and provider-plugin provenance, resource payloads, physical
network/identity/edge/compute configuration, runtime health and load tests,
formal TST-026/TST-027, hosted CI, any live provider, staging, release,
deployment, and Production remain separately unexecuted.
