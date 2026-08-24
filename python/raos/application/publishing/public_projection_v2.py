"""ENV-DEV/CI-only application service for the ST-0904 V2 projector."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.public_projection_v2 import (
    PublicProjectionFailureCode,
    PublicProjectionInputV2,
    PublicProjectionRequestV2,
    PublicProjectionResultV2,
    build_public_projection_v2,
    fail_public_projection,
)
from raos.ports.public_projection_v2 import (
    PublicProjectionExchange,
    RecordedPublicProjectionSource,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


def _source_matches(
    observed: object,
    request: PublicProjectionRequestV2,
) -> bool:
    try:
        if type(observed) is not PublicProjectionInputV2:
            return False
        observed.require_valid()
        return observed.binding_sha256 == request.expected_source_binding_sha256
    except Exception:
        return False


def _result_matches(
    *,
    request: PublicProjectionRequestV2,
    source: PublicProjectionInputV2,
    observed: object,
) -> bool:
    try:
        if type(observed) is not PublicProjectionResultV2:
            return False
        expected = build_public_projection_v2(request=request, source=source)
        return (
            observed.canonical_bytes() == expected.canonical_bytes()
            and observed.projection_bytes == expected.projection_bytes
        )
    except Exception:
        return False


@final
class PublicProjectionService:
    """Create one checked local projection through closed collaborators."""

    __slots__ = ("_exchange", "_source")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: RecordedPublicProjectionSource,
        exchange: PublicProjectionExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(cast(object, source), RecordedPublicProjectionSource)
            or not _implements(cast(object, exchange), PublicProjectionExchange)
        ):
            fail_public_projection(
                PublicProjectionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._source = source
        self._exchange = exchange

    def execute(
        self,
        *,
        request: PublicProjectionRequestV2,
    ) -> PublicProjectionResultV2:
        if type(request) is not PublicProjectionRequestV2:
            fail_public_projection()
        request.require_valid()
        observed_source: object = None
        try:
            observed_source = self._source.load(request)
        except Exception:
            fail_public_projection(
                PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _source_matches(observed_source, request):
            fail_public_projection(
                PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH
            )
        source = observed_source
        observed_result: object = None
        try:
            observed_result = self._exchange.exchange(request, source)
        except Exception:
            fail_public_projection(
                PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _result_matches(
            request=request,
            source=source,
            observed=observed_result,
        ):
            fail_public_projection(PublicProjectionFailureCode.OUTCOME_MISMATCH)
        return observed_result


__all__ = ("PublicProjectionService",)
