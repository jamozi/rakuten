# ST-1503 provider-schema-free compute and edge module

This Story-owned slice implements the maximum-safe local part of the strict
provider-neutral compute and public-edge admission boundary. The direct owner
`DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml` governs this new
decision together with the Canonical Story and design sources; the older
Pro-derived implementation-first slice alone does not govern it. No provider,
account or project, region, runtime, scheduler, registry, network, domain,
route, certificate, WAF or abuse policy, workload size, image, identity,
secret, credential, or health matcher is selected. The generated HCL is
executable only as a provider-free validation module; it is not a provider
configuration, physical plan, apply path, or deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026 and TST-027: `NOT_EXECUTED`
- Local provider-free native format/semantic validation:
  `EXECUTED_LOCAL_NOT_FORMAL`
- Provider-backed/native infrastructure validation: `NOT_EXECUTED`
- Health, performance, hosted CI, staging, release, apply, and Production:
  `NOT_EXECUTED`

ST-1501 remains a disabled provider-neutral predecessor. ST-1503 hash-binds its
direct handoff, contract, reference-plan bytes, and exact Terraform 1.15.9
validation-only toolchain. ST-1502 is used only as the integrated implementation
pattern and dependency regression target; it is not a Story dependency and no
ST-1502 artifact is owned or changed here. Neither predecessor nor local native
validation selects a provider or makes this Story formally `VALIDATED`.

## Logical HCL graph

The owner generates a five-file HCL module and a deterministic no-apply JSON
fixture. The graph has 37 logical components and 53 exact edges for:

- four isolated workload roles and an immutable image supply chain;
- distinct public/admin managed edges, private origins, and internal ingress;
- DNS/TLS lifecycle, WAF, rate-limit, cache/cookie/CSP boundaries;
- per-workload identity, controlled egress, liveness, and readiness;
- observability, bounded canary, and immutable rollback requirements.

The module contains only `terraform`, `variable`, `locals`, `check`, and
`output` blocks. It contains no provider requirement, provider, backend,
module, data, resource, provisioner, remote-state, credential, or physical
binding. Closed variables accept only the disabled/unset state. All
create/update/delete/deploy/promote/rollback/route/scale action counts are zero.

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

AWS Tokyo and the ECS, Fargate, ECR, ALB, CloudFront, WAF, Route53, and ACM
mappings remain the current Canonical Reference Architecture inherited from
INT-DEC-007 and RAOS-ARCH-001. This overlay does not erase, replace, or
complete the Canonical AWS-specific ST-1503 objective or modules deliverable.
Non-AWS and owner-managed profiles are additional portable implementation
paths only. Canonical reference status is never a default, implicit fallback,
selected binding, eligibility shortcut, admission requirement, or evidence
substitute. Missing, unknown, duplicate, reordered, partial, implicit,
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
| Implementation record | `changes/st-1503/IMPLEMENTATION_RECORD_V2_ST1503_LOGICAL_HCL.yaml` | Local implementation and authority boundary |
| Local evidence | `changes/st-1503/LOCAL_COMPLETION_EVIDENCE_V2.md` | Verification and debt reconciliation |
| Implementation source | `scripts/build_st1503_compute_edge.py` | Strict validator and deterministic owner builder |
| Test source | `tests/st1503/*.py` | Positive, hostile, exact-type, provenance, and no-write checks |
| Generated reference plan | `infra/terraform/compute-edge/compute-edge.reference-plan.v1.json` | Safe-boundary summary |
| Generated logical plan | `infra/terraform/compute-edge/compute-edge.logical-plan.v1.json` | Deterministic no-apply graph fixture |
| Toolchain lock | `infra/terraform/compute-edge/terraform-validation-toolchain.lock.v1.json` | Exact inherited ST-1501 validation boundary |
| HCL module | `infra/terraform/compute-edge/{versions,variables,locals,checks,outputs}.tf` | Provider-free executable logical module |
| Generated inventory | `changes/st-1503/manifest.yaml` | Source, predecessor, authority, and generated-output hashes |

Generate all ST-1503-owned outputs:

```bash
uv run --locked --no-sync python scripts/build_st1503_compute_edge.py
```

Verify all source/predecessor bindings and committed bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1503_compute_edge.py --check
```

An explicit native check is available only with the exact Terraform 1.15.9
Linux amd64 binary pinned by ST-1501:

```bash
uv run --locked --no-sync python scripts/build_st1503_compute_edge.py \
  --native-check --terraform /absolute/path/to/terraform
```

That path verifies the binary digest, enters a new user/network namespace,
uses a closed environment, and permits only `version -json`,
`fmt -check -recursive`, and `validate -json`. It never runs `init`, discovers
or installs providers, reads credentials, calls a provider, or invokes plan,
apply, destroy, import, or refresh.

## Completion boundary

This slice supports maximum-safe local code completion only. Provider schema
and plugin provenance, resource payloads, physical
network/identity/edge/compute configuration, runtime health and load tests,
formal TST-026/TST-027, hosted CI, any live provider, staging, release,
deployment, and Production remain separately unexecuted.
