"""Built-in alternatives for every Story and unresolved canonical decision."""

from __future__ import annotations

from dataclasses import dataclass
import re

from raos.strategy_switchboard.model import (
    Environment,
    ExecutionKind,
    FallbackPolicy,
    GateRequirements,
    StrategyCandidate,
    StrategyCatalog,
    StrategyProfile,
    StrategyTier,
)


SAFE_LOCAL_PROFILE = StrategyProfile(
    profile_id="safe-local",
    preferred_tier=StrategyTier.SAFE,
    fallback_policy=FallbackPolicy.SAFE_ONLY,
)
BALANCED_STAGING_PROFILE = StrategyProfile(
    profile_id="balanced-staging",
    preferred_tier=StrategyTier.STANDARD,
    fallback_policy=FallbackPolicy.FALLBACK_CHAIN,
)
ADVANCED_EXTERNAL_PROFILE = StrategyProfile(
    profile_id="advanced-external",
    preferred_tier=StrategyTier.ADVANCED,
    fallback_policy=FallbackPolicy.FAIL_CLOSED,
)


@dataclass(frozen=True, slots=True)
class _Alternative:
    slug: str
    title: str
    description: str
    execution_kind: ExecutionKind
    adapter_key: str | None = None
    approvals: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _DecisionSpec:
    boundary_id: str
    safe: _Alternative
    standard: _Alternative
    advanced: _Alternative


def _alternative(
    slug: str,
    title: str,
    description: str,
    execution_kind: ExecutionKind,
    *,
    adapter_key: str | None = None,
    approvals: tuple[str, ...] = (),
    evidence: tuple[str, ...] = (),
    capabilities: tuple[str, ...] = (),
    side_effects: tuple[str, ...] = (),
) -> _Alternative:
    return _Alternative(
        slug=slug,
        title=title,
        description=description,
        execution_kind=execution_kind,
        adapter_key=adapter_key,
        approvals=approvals,
        evidence=evidence,
        capabilities=capabilities,
        side_effects=side_effects,
    )


_OPEN_DECISION_SPECS = (
    _DecisionSpec(
        "OD-001",
        _alternative(
            "synthetic-fixture",
            "Synthetic category fixture",
            "Use category-neutral synthetic products and prevent category-specific publication.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "reviewed-single-category",
            "Reviewed single category",
            "Accept one explicitly reviewed category packet without enabling unrelated categories.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-001",),
        ),
        _alternative(
            "approved-multi-category",
            "Approved multi-category portfolio",
            "Delegate category activation to an injected portfolio adapter after approval and evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="category.portfolio",
            approvals=("OD-001", "production-use"),
            evidence=("category-portfolio-evidence",),
            capabilities=("external-io",),
            side_effects=("external-read",),
        ),
    ),
    _DecisionSpec(
        "OD-002",
        _alternative(
            "example-invalid",
            "Non-routable placeholder identity",
            "Use example.invalid and a temporary brand while public exposure remains disabled.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "verified-staging-identity",
            "Verified staging identity",
            "Accept a reviewed staging name, domain, and operator disclosure packet.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-002",),
        ),
        _alternative(
            "verified-production-identity",
            "Verified production identity",
            "Resolve production identity through an injected domain and disclosure adapter.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="site.production-identity",
            approvals=("OD-002", "production-use"),
            evidence=("domain-control-evidence", "operator-disclosure-evidence"),
            capabilities=("external-io",),
            side_effects=("external-read",),
        ),
    ),
    _DecisionSpec(
        "OD-003",
        _alternative(
            "synthetic-report",
            "Synthetic affiliate report",
            "Use content-free synthetic finance fixtures and mark attribution unverified.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "manual-anonymized-csv",
            "Manual anonymized report import",
            "Validate an explicitly supplied anonymized CSV packet without provider access.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-003",),
            evidence=("anonymized-report-sample",),
        ),
        _alternative(
            "verified-provider-report",
            "Verified provider report adapter",
            "Invoke an injected report adapter after schema, identity, and reconciliation evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="finance.provider-report",
            approvals=("OD-003", "production-use"),
            evidence=("provider-report-schema", "provider-reconciliation-evidence"),
            capabilities=("external-io", "finance-write"),
            side_effects=("external-read", "finance-write"),
        ),
    ),
    _DecisionSpec(
        "OD-004",
        _alternative(
            "search-console-only",
            "Search Console only",
            "Use first-party Search Console inputs and disable third-party rank automation.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "manual-rank-csv",
            "Manual rank CSV",
            "Validate a manually supplied keyword and rank snapshot with explicit provenance.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-004",),
        ),
        _alternative(
            "approved-rank-provider",
            "Approved rank provider",
            "Use an injected terms-reviewed rank provider with bounded collection.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="analytics.rank-provider",
            approvals=("OD-004", "production-use"),
            evidence=("rank-provider-terms",),
            capabilities=("external-io",),
            side_effects=("external-read",),
        ),
    ),
    _DecisionSpec(
        "OD-005",
        _alternative(
            "unknown-cost-publication-blocked",
            "Unknown review cost and blocked publication",
            "Keep reviewer cost unknown and refuse publication or contribution-profit claims.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "named-primary-and-backup",
            "Named primary and backup reviewers",
            "Accept a reviewed assignment and rate-card packet for one primary and one backup.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-005",),
        ),
        _alternative(
            "reviewer-pool-rate-card",
            "Reviewer pool with rate card",
            "Delegate assignment to an injected reviewer-pool adapter with approved cost controls.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="review.reviewer-pool",
            approvals=("OD-005", "production-use"),
            evidence=("reviewer-rate-card",),
            capabilities=("human-workflow",),
            side_effects=("human-task-create",),
        ),
    ),
    _DecisionSpec(
        "OD-006",
        _alternative(
            "no-auto-merge",
            "No automatic product merge",
            "Keep product identities separate and route uncertain matches to human review.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "versioned-category-rules",
            "Versioned category identity rules",
            "Apply an explicitly supplied and reviewed category identity ruleset.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-006",),
            evidence=("category-identity-rules",),
        ),
        _alternative(
            "verified-identity-resolver",
            "Verified identity resolver",
            "Invoke an injected resolver only after category rules and external identity evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="catalog.identity-resolver",
            approvals=("OD-006", "production-use"),
            evidence=("category-identity-rules", "identity-provider-evidence"),
            capabilities=("external-io", "catalog-write"),
            side_effects=("catalog-write", "external-read"),
        ),
    ),
    _DecisionSpec(
        "OD-007",
        _alternative(
            "conservative-hide-stale",
            "Conservative hide-stale policy",
            "Use conservative temporary ages and hide stale price, stock, specification, image, and link data.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "versioned-category-sla",
            "Versioned category freshness SLA",
            "Accept a reviewed category SLA packet and evaluate each field independently.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-007",),
            evidence=("category-freshness-sla",),
        ),
        _alternative(
            "risk-adaptive-freshness",
            "Risk-adaptive freshness",
            "Use an injected freshness evaluator bounded by approved category maximum ages.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="publication.freshness-evaluator",
            approvals=("OD-007", "production-use"),
            evidence=("category-freshness-sla", "freshness-evaluation-evidence"),
            capabilities=("external-io",),
            side_effects=("external-read",),
        ),
    ),
    _DecisionSpec(
        "OD-008",
        _alternative(
            "block-legal-judgment",
            "Block legal judgment",
            "Do not let software or AI substitute for legal review; keep affected publication blocked.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "legal-checklist-escalation",
            "Legal checklist with mandatory escalation",
            "Evaluate an approved checklist while escalating every legal judgment to a named reviewer.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-008",),
            evidence=("legal-checklist",),
        ),
        _alternative(
            "external-legal-workflow",
            "External legal review workflow",
            "Create a bounded request through an injected legal workflow adapter and require a signed outcome.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="compliance.legal-workflow",
            approvals=("OD-008", "production-use"),
            evidence=("legal-workflow-definition",),
            capabilities=("human-workflow",),
            side_effects=("human-task-create",),
        ),
    ),
    _DecisionSpec(
        "OD-009",
        _alternative(
            "development-hard-cap",
            "Low development hard cap",
            "Use low non-production ceilings and keep every production cost path disabled.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "approved-static-caps",
            "Approved static caps",
            "Accept explicit monthly and per-operation ceilings with deterministic stop behavior.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-009",),
            evidence=("approved-budget-caps",),
        ),
        _alternative(
            "adaptive-reservation-breaker",
            "Adaptive reservation and circuit breaker",
            "Use an injected budget service while preserving approved absolute ceilings.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="finance.budget-service",
            approvals=("OD-009", "production-use"),
            evidence=("approved-budget-caps", "budget-service-evidence"),
            capabilities=("external-io", "budget-reservation"),
            side_effects=("budget-reservation", "external-read"),
        ),
    ),
    _DecisionSpec(
        "OD-010",
        _alternative(
            "local-fake-auth",
            "Development-only fake authentication",
            "Provide deterministic local principals and refuse every externally exposed use.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "generic-oidc",
            "Generic approved OIDC",
            "Use an injected OIDC verifier configured only from an explicit reviewed packet.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="iam.generic-oidc",
            approvals=("OD-010",),
            evidence=("oidc-configuration-evidence",),
            capabilities=("identity-verification",),
        ),
        _alternative(
            "aws-cognito",
            "AWS Cognito",
            "Use an injected Cognito verifier with issuer, audience, key-rotation, and outage evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="iam.aws-cognito",
            approvals=("OD-010", "production-use"),
            evidence=("cognito-configuration-evidence", "identity-recovery-evidence"),
            capabilities=("external-io", "identity-verification"),
            side_effects=("external-read",),
        ),
    ),
    _DecisionSpec(
        "OD-011",
        _alternative(
            "local-structured-log",
            "Local structured incident log",
            "Emit content-free local diagnostic records and mark production notification unavailable.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "signed-webhook",
            "Signed notification webhook",
            "Send bounded notifications through an injected signed-webhook adapter.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="ops.signed-webhook",
            approvals=("OD-011",),
            evidence=("notification-routing-evidence",),
            capabilities=("external-io",),
            side_effects=("notification-send",),
        ),
        _alternative(
            "managed-escalation",
            "Managed escalation service",
            "Use an injected multi-channel escalation adapter with acknowledgement and fallback evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="ops.managed-escalation",
            approvals=("OD-011", "production-use"),
            evidence=("notification-routing-evidence", "escalation-drill-evidence"),
            capabilities=("external-io", "incident-escalation"),
            side_effects=("incident-escalation", "notification-send"),
        ),
    ),
    _DecisionSpec(
        "OD-012",
        _alternative(
            "minimal-first-party",
            "Minimal first-party analytics",
            "Disable non-essential tracking and retain only bounded first-party operational events.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "explicit-opt-in",
            "Explicit opt-in analytics",
            "Apply an approved consent packet and enable optional analytics only after affirmative consent.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-012",),
            evidence=("privacy-notice", "consent-policy"),
        ),
        _alternative(
            "approved-consent-platform",
            "Approved consent platform",
            "Use an injected consent adapter with region, withdrawal, and audit evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="privacy.consent-platform",
            approvals=("OD-012", "production-use"),
            evidence=("privacy-notice", "consent-platform-evidence"),
            capabilities=("consent-state", "external-io"),
            side_effects=("consent-state-write", "external-read"),
        ),
    ),
    _DecisionSpec(
        "OD-013",
        _alternative(
            "tokyo-reference-no-apply",
            "Tokyo reference with apply disabled",
            "Render ap-northeast-1 reference plans while forbidding infrastructure apply.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "approved-primary-backup",
            "Approved primary and backup regions",
            "Accept reviewed primary, backup, transfer, and recovery parameters without applying them.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-013",),
            evidence=("region-residency-approval",),
        ),
        _alternative(
            "approved-multi-region",
            "Approved multi-region deployment",
            "Invoke an injected deployment planner after residency, recovery, and cost approval.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="infra.multi-region",
            approvals=("OD-013", "production-use"),
            evidence=("region-residency-approval", "recovery-drill-evidence"),
            capabilities=("infrastructure-plan",),
            side_effects=("infrastructure-plan",),
        ),
    ),
    _DecisionSpec(
        "OD-014",
        _alternative(
            "minimal-collection-no-delete",
            "Minimal collection with deletion disabled",
            "Minimize collected data and keep automatic deletion disabled until periods are approved.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "approved-static-ttl",
            "Approved static retention periods",
            "Accept explicit per-class retention periods and produce a dry-run deletion plan.",
            ExecutionKind.MANUAL_INPUT,
            approvals=("OD-014",),
            evidence=("retention-schedule",),
        ),
        _alternative(
            "legal-hold-aware-retention",
            "Legal-hold-aware retention",
            "Use an injected retention executor with hold, preview, approval, and audit controls.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="privacy.retention-executor",
            approvals=("OD-014", "production-use"),
            evidence=("retention-schedule", "deletion-recovery-evidence"),
            capabilities=("destructive-write", "legal-hold"),
            side_effects=("destructive-write",),
        ),
    ),
    _DecisionSpec(
        "OD-015",
        _alternative(
            "recorded-only",
            "Recorded providers only",
            "Use sanitized recorded fixtures and refuse credential resolution or live calls.",
            ExecutionKind.DETERMINISTIC_PLAN,
        ),
        _alternative(
            "injected-secret-provider",
            "Injected secret provider",
            "Resolve opaque credential handles through application wiring without reading ambient environment variables.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="credentials.secret-provider",
            approvals=("OD-015",),
            evidence=("credential-scope-evidence",),
            capabilities=("credential-resolution",),
        ),
        _alternative(
            "workload-identity",
            "Workload identity",
            "Use an injected short-lived workload identity adapter with rotation and revocation evidence.",
            ExecutionKind.INJECTED_ADAPTER,
            adapter_key="credentials.workload-identity",
            approvals=("OD-015", "production-use"),
            evidence=("credential-scope-evidence", "workload-identity-evidence"),
            capabilities=("credential-resolution", "external-io"),
            side_effects=("external-read",),
        ),
    ),
)


def _candidate(
    *,
    boundary_id: str,
    alternative: _Alternative,
    tier: StrategyTier,
    safe_default: bool,
) -> StrategyCandidate:
    if tier is StrategyTier.SAFE:
        environments = (Environment.LOCAL,)
    elif tier is StrategyTier.STANDARD:
        environments = (Environment.LOCAL, Environment.STAGING)
    else:
        environments = (
            Environment.LOCAL,
            Environment.PRODUCTION,
            Environment.STAGING,
        )
    return StrategyCandidate(
        strategy_id=f"{boundary_id}:{alternative.slug}",
        boundary_id=boundary_id,
        tier=tier,
        title=alternative.title,
        description=alternative.description,
        execution_kind=alternative.execution_kind,
        adapter_key=alternative.adapter_key,
        requirements=GateRequirements(
            approvals=alternative.approvals,
            evidence=alternative.evidence,
            capabilities=alternative.capabilities,
            allowed_environments=environments,
        ),
        safe_default=safe_default,
        side_effects=alternative.side_effects,
    )


def open_decision_candidates() -> tuple[StrategyCandidate, ...]:
    result: list[StrategyCandidate] = []
    for spec in _OPEN_DECISION_SPECS:
        result.extend(
            (
                _candidate(
                    boundary_id=spec.boundary_id,
                    alternative=spec.safe,
                    tier=StrategyTier.SAFE,
                    safe_default=True,
                ),
                _candidate(
                    boundary_id=spec.boundary_id,
                    alternative=spec.standard,
                    tier=StrategyTier.STANDARD,
                    safe_default=False,
                ),
                _candidate(
                    boundary_id=spec.boundary_id,
                    alternative=spec.advanced,
                    tier=StrategyTier.ADVANCED,
                    safe_default=False,
                ),
            )
        )
    return tuple(result)


def story_candidates(story_ids: tuple[str, ...]) -> tuple[StrategyCandidate, ...]:
    normalized = tuple(sorted(set(story_ids)))
    if not normalized or any(
        re.fullmatch(r"ST-[0-9]{4}", item) is None for item in normalized
    ):
        raise ValueError("story_ids must be non-empty canonical ST-xxxx identifiers")
    result: list[StrategyCandidate] = []
    for story_id in normalized:
        result.extend(
            (
                StrategyCandidate(
                    strategy_id=f"{story_id}:recorded",
                    boundary_id=story_id,
                    tier=StrategyTier.SAFE,
                    title=f"{story_id} recorded fail-closed boundary",
                    description=(
                        "Execute deterministic fixtures or a content-free plan and "
                        "perform no external or production side effect."
                    ),
                    execution_kind=ExecutionKind.DETERMINISTIC_PLAN,
                    requirements=GateRequirements(),
                    safe_default=True,
                ),
                StrategyCandidate(
                    strategy_id=f"{story_id}:reviewed-local",
                    boundary_id=story_id,
                    tier=StrategyTier.STANDARD,
                    title=f"{story_id} reviewed local implementation",
                    description=(
                        "Execute from an explicit reviewed input packet in local or "
                        "staging without implicit provider or production access."
                    ),
                    execution_kind=ExecutionKind.MANUAL_INPUT,
                    requirements=GateRequirements(
                        approvals=(f"{story_id}:local",),
                        allowed_environments=(
                            Environment.LOCAL,
                            Environment.STAGING,
                        ),
                    ),
                ),
                StrategyCandidate(
                    strategy_id=f"{story_id}:injected-external",
                    boundary_id=story_id,
                    tier=StrategyTier.ADVANCED,
                    title=f"{story_id} injected external implementation",
                    description=(
                        "Delegate the approved boundary to an injected adapter only "
                        "after Story-specific approval, evidence, and external capability."
                    ),
                    execution_kind=ExecutionKind.INJECTED_ADAPTER,
                    adapter_key=f"story.{story_id}.external",
                    requirements=GateRequirements(
                        approvals=(f"{story_id}:external", "production-use"),
                        evidence=(f"{story_id}:external-evidence",),
                        capabilities=("external-io",),
                        allowed_environments=(
                            Environment.LOCAL,
                            Environment.PRODUCTION,
                            Environment.STAGING,
                        ),
                    ),
                    side_effects=("external-io",),
                ),
            )
        )
    return tuple(result)


def build_complete_catalog(story_ids: tuple[str, ...]) -> StrategyCatalog:
    return StrategyCatalog(
        version="all-stories-switchable-v1",
        candidates=story_candidates(story_ids) + open_decision_candidates(),
    )
