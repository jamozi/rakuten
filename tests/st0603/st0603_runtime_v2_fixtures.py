"""Exact persisted ST-0602 inputs for focused ST-0603 V2 tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
from uuid import UUID

from raos.adapters.sqlite_fact_conflict_runtime_v2 import (
    FactConflictSqliteCommitFaultV2,
    OwnerPrivateSqliteFactConflictStoreV2,
)
from raos.application.evidence.fact_extraction_runtime_v2 import (
    DurableFactExtractionServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FACT_EXTRACTION_GENESIS_SHA256_V2,
    FACT_EXTRACTION_SCHEMA_VERSION_V2,
    ExactOfferFactV2,
    FactExtractionBatchV2,
    FactExtractionCommandV2,
    FactExtractionSourceBindingV2,
    FactLocatorV2,
    FactValidationRecordV2,
    FactsExtractedOutboxEventV2,
    PersistedFactExtractionV2,
    canonical_json_bytes_v2,
    fact_chain_hash_v2,
)
from raos.domain.shared.identity import deterministic_uuid7
from tests.st0602.runtime_v2_fixtures import (
    exact_dependencies_v2,
    fact_store_v2,
)


_EXTRACTION_ID_NAMESPACE = UUID("8ca28da8-cbb0-43c1-8e40-43335609d8ad")
_FIXTURE_ID_NAMESPACE = UUID("c6b7cd11-3d38-4e6e-8703-6e3793943e7a")


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _fixture_id(kind: str, label: str) -> UUID:
    return deterministic_uuid7(
        _FIXTURE_ID_NAMESPACE,
        canonical_json_bytes_v2({"kind": kind, "label": label}),
    )


def _extraction_id(kind: str, material: object) -> UUID:
    return deterministic_uuid7(
        _EXTRACTION_ID_NAMESPACE,
        canonical_json_bytes_v2(
            {
                "kind": kind,
                "material": material,
                "schema_version": FACT_EXTRACTION_SCHEMA_VERSION_V2,
            }
        ),
    )


def exact_persisted_fact_v2(
    root: Path,
    *,
    item_ordinals: tuple[int, ...] = (1,),
) -> PersistedFactExtractionV2:
    dependencies = exact_dependencies_v2(root, item_ordinals=item_ordinals)
    return (
        DurableFactExtractionServiceV2(fact_store_v2(root))
        .extract(
            artifact=dependencies.artifact,
            normalization=dependencies.normalization,
        )
        .persisted
    )


def derive_persisted_fact_v2(
    base: PersistedFactExtractionV2,
    *,
    label: str,
    price_delta: int = 0,
) -> PersistedFactExtractionV2:
    """Make a second internally exact ST-0602 recorded fixture.

    Source evidence identifiers are synthetic and owner-local. Subject IDs and
    validity starts intentionally remain exact so ST-0603 can compare the same
    subject/predicate without inventing identity authority.
    """

    if type(base) is not PersistedFactExtractionV2 or type(label) is not str:
        raise TypeError("invalid ST-0603 fixture input")
    if type(price_delta) is not int:
        raise TypeError("invalid ST-0603 fixture price delta")
    prior = base.command.source_binding
    source_snapshot_id = _fixture_id("source_snapshot", label)
    catalog_batch_id = _fixture_id("catalog_batch", label)
    normalized_at = prior.normalized_at + timedelta(seconds=1)
    source_binding = FactExtractionSourceBindingV2(
        source_snapshot_id=source_snapshot_id,
        source_receipt_id=_fixture_id("source_receipt", label),
        artifact_id=_fixture_id("artifact", label),
        artifact_ref_sha256=_digest(f"artifact-ref:{label}"),
        artifact_record_sha256=_digest(f"artifact-record:{label}"),
        artifact_entry_sha256=_digest(f"artifact-entry:{label}"),
        artifact_object_version=prior.artifact_object_version,
        artifact_registry_sequence=prior.artifact_registry_sequence,
        raw_sha256=_digest(f"raw:{label}"),
        raw_byte_size=prior.raw_byte_size,
        raw_artifact_version=prior.raw_artifact_version,
        raw_request_fingerprint=_digest(f"request:{label}"),
        raw_page=prior.raw_page,
        observed_at=prior.observed_at,
        normalized_at=normalized_at,
        catalog_batch_id=catalog_batch_id,
        catalog_version=prior.catalog_version,
        catalog_chain_hash=_digest(f"catalog-chain:{label}"),
        catalog_batch_sha256=_digest(f"catalog-batch:{label}"),
        catalog_event_id=_fixture_id("catalog_event", label),
        catalog_event_sha256=_digest(f"catalog-event:{label}"),
    )
    command = FactExtractionCommandV2.issue(source_binding)
    facts: list[ExactOfferFactV2] = []
    validations: list[FactValidationRecordV2] = []
    for original, original_validation in zip(
        base.batch.facts,
        base.batch.validations,
        strict=True,
    ):
        locator = FactLocatorV2(
            pointer=original.locator.pointer,
            normalized_observation_id=_fixture_id(
                "observation",
                f"{label}:{original.locator.normalized_observation_ordinal}",
            ),
            normalized_observation_ordinal=(
                original.locator.normalized_observation_ordinal
            ),
            normalized_observation_kind=(original.locator.normalized_observation_kind),
            catalog_batch_id=catalog_batch_id,
        )
        numeric = original.value_numeric
        if numeric is not None:
            numeric += Decimal(price_delta)
        material = {
            "extractor_version": original.extractor_version,
            "locator": locator.canonical_material,
            "predicate": original.predicate,
            "source_snapshot_id": str(source_snapshot_id),
            "subject_id": str(original.subject_id),
            "subject_type": original.subject_type.value,
            "unit_code": original.unit_code,
            "value_boolean": original.value_boolean,
            "value_numeric": (
                None if numeric is None else str(numeric.to_integral_value())
            ),
        }
        fact_id = _extraction_id("fact", material)
        fact = ExactOfferFactV2(
            fact_id=fact_id,
            display_id=f"FCT-{fact_id.hex[:20].upper()}",
            source_snapshot_id=source_snapshot_id,
            subject_type=original.subject_type,
            subject_id=original.subject_id,
            predicate=original.predicate,
            value_kind=original.value_kind,
            value_numeric=numeric,
            value_boolean=original.value_boolean,
            unit_code=original.unit_code,
            locale=original.locale,
            fact_kind=original.fact_kind,
            confidence=original.confidence,
            confidence_basis=original.confidence_basis,
            valid_from=source_binding.observed_at,
            valid_to=None,
            locator=locator,
            extractor_version=original.extractor_version,
            created_at=normalized_at,
        )
        facts.append(fact)
        validations.append(
            replace(
                original_validation,
                fact_id=fact.fact_id,
                source_snapshot_id=source_snapshot_id,
            )
        )
    batch_id = _extraction_id(
        "fact_batch",
        {
            "extractor_version": command.extractor_version,
            "payload_sha256": command.payload_sha256,
            "source_snapshot_id": str(command.source_snapshot_id),
        },
    )
    batch = FactExtractionBatchV2(
        batch_id=batch_id,
        command=command,
        facts=tuple(facts),
        validations=tuple(validations),
        extracted_at=normalized_at,
        identity_status=base.batch.identity_status,
        readiness=base.batch.readiness,
        open_decision=base.batch.open_decision,
        truth_attestation=base.batch.truth_attestation,
        confidence_basis=base.batch.confidence_basis,
        external_action_count=0,
        provider_action_count=0,
        publication_action_count=0,
        ai_action_count=0,
    )
    event = FactsExtractedOutboxEventV2.from_batch(batch)
    chain_hash = fact_chain_hash_v2(
        previous_chain_hash=FACT_EXTRACTION_GENESIS_SHA256_V2,
        sequence=1,
        command_payload_sha256=command.payload_sha256,
        batch_sha256=batch.sha256,
        event_sha256=event.sha256,
        committed_at=batch.extracted_at,
    )
    return PersistedFactExtractionV2(
        sequence=1,
        previous_chain_hash=FACT_EXTRACTION_GENESIS_SHA256_V2,
        chain_hash=chain_hash,
        command=command,
        batch=batch,
        event=event,
        committed_at=batch.extracted_at,
    )


def conflict_store_v2(
    root: Path,
    *,
    faults: tuple[FactConflictSqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteFactConflictStoreV2:
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return OwnerPrivateSqliteFactConflictStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "conflict-private",
        commit_faults=faults,
    )


__all__ = [
    "conflict_store_v2",
    "derive_persisted_fact_v2",
    "exact_persisted_fact_v2",
]
