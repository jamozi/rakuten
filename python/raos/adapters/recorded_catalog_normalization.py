"""Immutable exact-fixture catalog normalizer for ST-0503."""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization import (
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
    CatalogNormalizationFailureCode,
    fail_catalog_normalization,
    lossless_batch_from_command,
)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedCatalogNormalizationFixture:
    command: CatalogNormalizationCommand
    batch: CatalogNormalizationBatch

    def __post_init__(self) -> None:
        if (
            type(self.command) is not CatalogNormalizationCommand
            or type(self.batch) is not CatalogNormalizationBatch
            or self.batch != lossless_batch_from_command(self.command)
        ):
            fail_catalog_normalization()

    def __repr__(self) -> str:
        return "RecordedCatalogNormalizationFixture(<redacted-catalog-normalization>)"


@final
class RecordedCatalogNormalizationAdapter:
    """Return one immutable pre-scripted batch for one exact command."""

    __slots__ = ("_fixtures",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedCatalogNormalizationFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= 10_000
            or type(fixtures) is not tuple
            or not fixtures
            or len(fixtures) > fixture_capacity
            or any(
                type(fixture) is not RecordedCatalogNormalizationFixture
                for fixture in fixtures
            )
            or len({fixture.command.fingerprint for fixture in fixtures})
            != len(fixtures)
        ):
            fail_catalog_normalization()
        self._fixtures = fixtures

    def normalize(
        self, command: CatalogNormalizationCommand
    ) -> CatalogNormalizationBatch:
        if type(command) is not CatalogNormalizationCommand:
            fail_catalog_normalization()
        matches = tuple(
            fixture
            for fixture in self._fixtures
            if fixture.command == command
            and fixture.command.fingerprint == command.fingerprint
        )
        if len(matches) != 1:
            fail_catalog_normalization(
                CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE
            )
        return matches[0].batch


__all__ = [
    "RecordedCatalogNormalizationAdapter",
    "RecordedCatalogNormalizationFixture",
]
