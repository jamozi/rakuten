from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

from raos.adapters.recorded_ai_output_validation import (
    TrustedTaskValidationProfiles,
    load_recorded_ai_output_validation_fixture,
    load_trusted_ai_output_validation_profiles,
)
from raos.domain.ai.output_validation import (
    AiOutputValidationInput,
    CoverageEvidenceBinding,
    OrderExpectation,
    PROFILE_REGISTRY_VERSION,
    ProviderMode,
    RecordedOutputEnvelope,
    ResourceBinding,
    ResourceKind,
    ResourceValidationStatus,
    ScalarExpectation,
    SemanticReceiptBinding,
    SemanticReceiptKind,
    SemanticReceiptStatus,
    TRUSTED_PROFILE_REGISTRY_SHA256,
    ValidationManifest,
)
from raos.domain.ai.provider import (
    CanonicalJsonObject,
    Sha256Digest,
    StructuredOutputSchema,
)


ROOT = Path(__file__).resolve().parents[2]
PROFILE_REGISTRY = (
    ROOT / "changes/st-0705/generated/ai-output-validation-profiles.v1.json"
)
PASS_FIXTURE = ROOT / "changes/st-0705/generated/ai-output-validation-pass.v1.json"
EVALUATED_AT = datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def trusted_profiles() -> TrustedTaskValidationProfiles:
    return load_trusted_ai_output_validation_profiles(PROFILE_REGISTRY.read_bytes())


@pytest.fixture(scope="session")
def passing_input(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> AiOutputValidationInput:
    profile = trusted_profiles.get("AIT-001")
    assert profile is not None
    return load_recorded_ai_output_validation_fixture(
        fixture_bytes=PASS_FIXTURE.read_bytes(),
        profiles=trusted_profiles,
        schema_bytes=(ROOT / profile.output_schema_path).read_bytes(),
    )


CaseFactory = Callable[..., AiOutputValidationInput]


@pytest.fixture
def case_factory(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> CaseFactory:
    def make(
        task_id: str,
        *,
        document: Mapping[str, object] | None = None,
        raw_bytes: bytes | None = None,
        locator_document: Mapping[str, object] | None = None,
        input_fields: tuple[str, ...] | None = None,
        resource_status: ResourceValidationStatus = ResourceValidationStatus.VALID,
        omit_resources: bool = False,
        scalar_values: Mapping[str, tuple[None | bool | int | float | str, ...]]
        | None = None,
        order_values: Mapping[str, tuple[tuple[str, ...], tuple[int, ...]]]
        | None = None,
        omit_receipt: SemanticReceiptKind | None = None,
        receipt_statuses: Mapping[SemanticReceiptKind, SemanticReceiptStatus]
        | None = None,
        coverage: CoverageEvidenceBinding | None = None,
    ) -> AiOutputValidationInput:
        profile = trusted_profiles.get(task_id)
        assert profile is not None
        if raw_bytes is None:
            assert document is not None
            raw_bytes = CanonicalJsonObject(document).canonical_bytes()
        observed_document = document if locator_document is None else locator_document
        if observed_document is None:
            observed_document = {}
        request_sha = Sha256Digest.of(f"{task_id}:REQUEST".encode())
        exchange_sha = Sha256Digest.of(f"{task_id}:EXCHANGE".encode())
        context_sha = Sha256Digest.of(f"{task_id}:CONTEXT".encode())
        envelope = RecordedOutputEnvelope(
            task_code=profile.task_code,
            provider_mode=ProviderMode.RECORDED_SYNTHETIC_ONLY,
            request_sha256=request_sha,
            provider_exchange_sha256=exchange_sha,
            raw_artifact_sha256=exchange_sha,
            output_bytes=raw_bytes,
            raw_output_sha256=Sha256Digest.of(raw_bytes),
        )
        resources_by_id: dict[str, ResourceBinding] = {}
        if not omit_resources:
            for locator in profile.resource_locators:
                for observed in locator.locator.values(observed_document):
                    if type(observed) is not str:
                        continue
                    identity = (
                        Sha256Digest.of(f"{observed}:IDENTITY".encode())
                        if locator.resource_kind is ResourceKind.PRODUCT
                        else None
                    )
                    resources_by_id.setdefault(
                        observed,
                        ResourceBinding(
                            resource_id=observed,
                            resource_kind=locator.resource_kind,
                            validation_status=resource_status,
                            value_sha256=Sha256Digest.of(f"{observed}:VALUE".encode()),
                            expected_subject_identity_sha256=identity,
                            observed_subject_identity_sha256=identity,
                        ),
                    )
        scalar_overrides = {} if scalar_values is None else dict(scalar_values)
        scalars = tuple(
            ScalarExpectation(
                locator_id=locator.locator.locator_id,
                scalar_kind=locator.scalar_kind,
                expected_values=scalar_overrides.get(
                    locator.locator.locator_id,
                    tuple(
                        value
                        for value in locator.locator.values(observed_document)
                        if type(value) in {type(None), bool, int, float, str}
                    ),
                ),
            )
            for locator in profile.scalar_locators
        )
        order_overrides = {} if order_values is None else dict(order_values)
        orders: list[OrderExpectation] = []
        for locator in profile.order_locators:
            if locator.locator_id in order_overrides:
                identities, ranks = order_overrides[locator.locator_id]
            else:
                values = locator.collection.values(observed_document)
                rows = values[0] if len(values) == 1 and type(values[0]) is list else []
                identities = tuple(
                    row[locator.identity_field]
                    for row in rows
                    if type(row) is dict
                    and type(row.get(locator.identity_field)) is str
                )
                ranks = tuple(
                    row[locator.rank_field]
                    for row in rows
                    if type(row) is dict and type(row.get(locator.rank_field)) is int
                )
            orders.append(
                OrderExpectation(
                    locator_id=locator.locator_id,
                    ordered_resource_ids=identities,
                    ordered_ranks=ranks,
                )
            )
        statuses = {} if receipt_statuses is None else dict(receipt_statuses)
        receipts = tuple(
            SemanticReceiptBinding(
                receipt_kind=requirement.receipt_kind,
                owner_story_id=requirement.owner_story_id,
                owner_contract_sha256=requirement.owner_contract_sha256,
                request_sha256=request_sha,
                raw_output_sha256=envelope.raw_output_sha256,
                output_sha256=envelope.output_sha256,
                input_context_sha256=context_sha,
                evidence_sha256=Sha256Digest.of(
                    f"{task_id}:{requirement.receipt_kind.value}:EVIDENCE".encode()
                ),
                status=statuses.get(
                    requirement.receipt_kind, SemanticReceiptStatus.PASS
                ),
            )
            for requirement in profile.required_semantic_receipts
            if requirement.receipt_kind is not omit_receipt
        )
        if input_fields is None:
            default_field = profile.allowed_input_fields[:1]
            input_fields = tuple(
                dict.fromkeys((*default_field, *profile.alignment_required_inputs))
            )
        article = {}
        if coverage is not None:
            article = {
                "article_version_id": coverage.article_version_id,
                "article_body_sha256": coverage.article_body_sha256,
                "source_packet_version_id": coverage.source_packet_version_id,
                "source_packet_content_sha256": coverage.source_packet_content_sha256,
                "complete_claim_set_sha256": coverage.complete_claim_set_sha256,
                "coverage_evaluation_input_sha256": coverage.evaluation_input_sha256,
            }
        manifest = ValidationManifest(
            manifest_version="ST0705_VALIDATION_MANIFEST_V1",
            profile_registry_version=PROFILE_REGISTRY_VERSION,
            profile_registry_sha256=TRUSTED_PROFILE_REGISTRY_SHA256,
            task_id=profile.task_id,
            task_code=profile.task_code,
            profile_sha256=profile.profile_sha256,
            task_binding_sha256=profile.task_binding_sha256,
            task_sha256=profile.task_sha256,
            prompt_sha256=profile.prompt_sha256,
            route_sha256=profile.route_sha256,
            output_schema_id=profile.output_schema_id,
            output_schema_sha256=profile.output_schema_sha256,
            expected_request_sha256=request_sha,
            expected_raw_output_sha256=envelope.raw_output_sha256,
            expected_output_sha256=envelope.output_sha256,
            expected_input_context_sha256=context_sha,
            input_field_names=input_fields,
            resources=tuple(resources_by_id.values()),
            scalar_expectations=scalars,
            order_expectations=tuple(orders),
            semantic_receipts=receipts,
            **article,
        )
        schema = StructuredOutputSchema(
            name=profile.task_code.replace(".", "_"),
            uri=profile.output_schema_id,
            sha256=profile.output_schema_sha256,
            document_bytes=(ROOT / profile.output_schema_path).read_bytes(),
        )
        return AiOutputValidationInput(
            profile=profile,
            schema=schema,
            manifest=manifest,
            envelope=envelope,
            evaluated_at=EVALUATED_AT,
            coverage=coverage,
        )

    return make
