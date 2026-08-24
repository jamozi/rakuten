"""Exact ST-0503/ST-0601 dependency builders for ST-0602 V2 tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from raos.adapters.sqlite_fact_extraction_runtime_v2 import (
    FactExtractionSqliteCommitFaultV2,
    OwnerPrivateSqliteFactExtractionStoreV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    PersistedCatalogNormalizationV2,
)
from raos.domain.ops.artifact_registry_runtime_v2 import ArtifactReadbackV2
from tests.st0503.runtime_v2_fixtures import (
    PersistedSourceFixtureV2,
    normalization_service_v2,
    normalization_store_v2,
    source_fixture_v2,
)
from tests.st0601.runtime_v2_fixtures import (
    private_root,
    request_for,
    service_for,
)


@dataclass(frozen=True, slots=True)
class ExactFactDependenciesV2:
    source: PersistedSourceFixtureV2
    artifact: ArtifactReadbackV2
    normalization: PersistedCatalogNormalizationV2


def exact_dependencies_v2(
    root: Path,
    *,
    item_ordinals: tuple[int, ...] = (1, 2),
    item_name: str | None = "Unicode 商品 Ω 東京",
) -> ExactFactDependenciesV2:
    source = source_fixture_v2(
        root / "upstream",
        item_ordinals=item_ordinals,
        item_name=item_name,
    )
    normalization_store = normalization_store_v2(root / "normalization")
    normalization = (
        normalization_service_v2(
            fixture=source,
            store=normalization_store,
        )
        .normalize(source.command)
        .persisted
    )
    receipt = source.source_step.receipt
    assert receipt is not None
    artifact_root = private_root(root, name="artifact-private")
    artifact_service, _factory = service_for(
        artifact_root,
        (receipt, source.raw_body),
    )
    commit = artifact_service.register(
        request_for(receipt, label="st0602-artifact-operation")
    )
    artifact = artifact_service.readback(commit.record.artifact_ref)
    return ExactFactDependenciesV2(
        source=source,
        artifact=artifact,
        normalization=normalization,
    )


def fact_store_v2(
    root: Path,
    *,
    faults: tuple[FactExtractionSqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteFactExtractionStoreV2:
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return OwnerPrivateSqliteFactExtractionStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "fact-private",
        commit_faults=faults,
    )


__all__ = [
    "ExactFactDependenciesV2",
    "exact_dependencies_v2",
    "fact_store_v2",
]
