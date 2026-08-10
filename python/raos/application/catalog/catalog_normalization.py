"""Fail-closed application seam for recorded lossless catalog normalization."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization import (
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
    CatalogNormalizationFailureCode,
    fail_catalog_normalization,
    lossless_batch_from_command,
)
from raos.ports.catalog_normalization import CatalogNormalizationExchange


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class CatalogNormalizationService:
    """Call one recorded normalizer once and validate its complete projection."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchange: CatalogNormalizationExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(exchange, CatalogNormalizationExchange)
        ):
            fail_catalog_normalization()
        self._exchange = exchange

    def normalize(
        self, command: CatalogNormalizationCommand
    ) -> CatalogNormalizationBatch:
        if type(command) is not CatalogNormalizationCommand:
            fail_catalog_normalization()
        outcome: object = None
        failed = False
        try:
            outcome = self._exchange.normalize(command)
        except Exception:
            failed = True
        if failed:
            fail_catalog_normalization(
                CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE
            )
        if type(outcome) is not CatalogNormalizationBatch:
            fail_catalog_normalization(CatalogNormalizationFailureCode.OUTCOME_MISMATCH)
        expected = lossless_batch_from_command(command)
        if outcome != expected:
            fail_catalog_normalization(CatalogNormalizationFailureCode.OUTCOME_MISMATCH)
        return outcome


__all__ = ["CatalogNormalizationService"]
