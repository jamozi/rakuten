"""Shared exact synthetic fixtures for ST-1407 V2."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from raos.adapters.recorded_external_policy_registry import (
    RecordedExternalPolicyRegistryAdapter,
    RecordedExternalPolicyRegistryFixture,
)
from raos.application.ops.external_policy_registry import ExternalPolicyRegistryService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.policy_engine import (
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
)
from raos.domain.ops.external_policy_registry import (
    EXTERNAL_RULE_POLICY_LINKS,
    ArticlePolicyBinding,
    ExternalPolicyRegistryRequest,
    ExternalPolicySnapshot,
    PolicyVersionLink,
    RegistryContractBinding,
    article_binding_set_fingerprint,
    evaluate_external_policy_registry,
)
from raos.domain.shared.persistence import Sha256Digest


RULE_MAP = dict(EXTERNAL_RULE_POLICY_LINKS)
ACQUIRED_AT = datetime(2026, 8, 1, tzinfo=timezone.utc)
DUE_AT = datetime(2026, 8, 20, tzinfo=timezone.utc)
EVALUATED_AT = datetime(2026, 8, 24, tzinfo=timezone.utc)


def build_request(
    *,
    external_rule_id: str = "EXT-GOOGLE-003",
    snapshot_id: UUID = UUID("10000000-0000-4000-8000-000000001407"),
    source_content_sha256: str = (
        "704ac3ba39de4c6685839d88aaae3407d5c65b2a6b0d01397faf4fec33171b14"
    ),
    acquired_at: datetime = ACQUIRED_AT,
    review_due_at: datetime = DUE_AT,
    evaluated_at: datetime = EVALUATED_AT,
    article_fixture: str = "affected",
) -> ExternalPolicyRegistryRequest:
    binding = RegistryContractBinding.current()
    snapshot = ExternalPolicySnapshot(
        snapshot_id=snapshot_id,
        external_rule_id=external_rule_id,
        source_content_sha256=Sha256Digest(source_content_sha256),
        acquired_at=acquired_at,
        review_due_at=review_due_at,
        contract_binding_sha256=Sha256Digest(binding.fingerprint),
    )
    links = tuple(
        PolicyVersionLink(
            snapshot_id=snapshot_id,
            external_rule_id=external_rule_id,
            policy_id=policy_id,
            policy_version=POLICY_CATALOG_VERSION,
            policy_catalog_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
        )
        for policy_id in sorted(RULE_MAP[external_rule_id])
    )
    article_rows: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    if article_fixture == "affected":
        article_rows = (
            (
                "20000000-0000-4000-8000-000000001407",
                "30000000-0000-4000-8000-000000001407",
                "07fffa938d2125f8d6d038977bac128d71b5589df4ae17cc6293c6bdc909ed94",
                ("POL-CONT-010", "POL-CONT-020"),
            ),
            (
                "20000000-0000-4000-8000-000000001408",
                "30000000-0000-4000-8000-000000001408",
                "db495e81b6fda8e5b197f43d9614d069f8bb23af0fe7989ed6d7e8514d3219f4",
                ("POL-CONT-019",),
            ),
        )
    elif article_fixture == "empty":
        article_rows = (
            (
                "20000000-0000-4000-8000-000000001409",
                "30000000-0000-4000-8000-000000001409",
                "f799686a8a72b5d097bdb62b2d8bd171340ea533760387d8cdf3c82f0342de98",
                ("POL-CONT-019",),
            ),
        )
    else:
        raise AssertionError("unknown recorded article fixture")
    article_bindings = tuple(
        ArticlePolicyBinding(
            article_id=UUID(article_id),
            article_version_id=UUID(article_version_id),
            publication_snapshot_sha256=Sha256Digest(snapshot_sha256),
            policy_ids=policy_ids,
        )
        for article_id, article_version_id, snapshot_sha256, policy_ids in article_rows
    )
    return ExternalPolicyRegistryRequest(
        binding=binding,
        snapshot=snapshot,
        version_links=links,
        article_bindings=article_bindings,
        article_binding_set_sha256=Sha256Digest(
            article_binding_set_fingerprint(article_bindings)
        ),
        evaluated_at=evaluated_at,
    )


def build_not_due_empty_request() -> ExternalPolicyRegistryRequest:
    return build_request(
        external_rule_id="EXT-W3C-001",
        snapshot_id=UUID("10000000-0000-4000-8000-000000001408"),
        source_content_sha256=(
            "f916366ca6de80add63f94d78c0f02266ad627c9dfb7e8ec4ddfadbb172d7ed6"
        ),
        review_due_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        article_fixture="empty",
    )


@pytest.fixture
def overdue_request() -> ExternalPolicyRegistryRequest:
    return build_request()


@pytest.fixture
def recorded_adapter(
    overdue_request: ExternalPolicyRegistryRequest,
) -> RecordedExternalPolicyRegistryAdapter:
    report = evaluate_external_policy_registry(overdue_request)
    return RecordedExternalPolicyRegistryAdapter(
        environment=RuntimeEnvironment.CI,
        fixture_capacity=1,
        fixtures=(
            RecordedExternalPolicyRegistryFixture(
                overdue_request,
                report,
                "ST1407-OVERDUE-AFFECTED-001",
            ),
        ),
    )


@pytest.fixture
def registry_service(
    recorded_adapter: RecordedExternalPolicyRegistryAdapter,
) -> ExternalPolicyRegistryService:
    return ExternalPolicyRegistryService(
        environment=RuntimeEnvironment.CI,
        exchange=recorded_adapter,
    )
