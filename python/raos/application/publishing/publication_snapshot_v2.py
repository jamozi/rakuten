"""ENV-DEV/CI-only ST-0903 publication snapshot application service."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotBuildRequestV2,
    PublicationSnapshotFailureCode,
    PublicationSnapshotInputBundleV2,
    PublicationSnapshotResultV2,
    build_publication_snapshot_v2,
    fail_publication_snapshot,
)
from raos.ports.publication_snapshot_v2 import (
    PublicationSnapshotExchange,
    RecordedPublicationSnapshotSource,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


def _bundle_matches(
    observed: object,
    request: PublicationSnapshotBuildRequestV2,
) -> bool:
    try:
        if type(observed) is not PublicationSnapshotInputBundleV2:
            return False
        observed.require_valid()
        return observed.input_bundle_sha256 == request.expected_input_bundle_sha256
    except Exception:
        return False


def _result_matches(
    *,
    request: PublicationSnapshotBuildRequestV2,
    bundle: PublicationSnapshotInputBundleV2,
    observed: object,
) -> bool:
    try:
        if type(observed) is not PublicationSnapshotResultV2:
            return False
        expected = build_publication_snapshot_v2(request=request, bundle=bundle)
        return (
            observed.canonical_bytes() == expected.canonical_bytes()
            and observed.content_manifest_bytes == expected.content_manifest_bytes
            and observed.snapshot_bytes == expected.snapshot_bytes
        )
    except Exception:
        return False


@final
class PublicationSnapshotService:
    """Build one checked local candidate through closed recorded collaborators."""

    __slots__ = ("_exchange", "_source")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: RecordedPublicationSnapshotSource,
        exchange: PublicationSnapshotExchange,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, source),
                RecordedPublicationSnapshotSource,
            )
            or not _implements(cast(object, exchange), PublicationSnapshotExchange)
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._source = source
        self._exchange = exchange

    def execute(
        self,
        *,
        request: PublicationSnapshotBuildRequestV2,
    ) -> PublicationSnapshotResultV2:
        if type(request) is not PublicationSnapshotBuildRequestV2:
            fail_publication_snapshot()
        request.require_valid()
        observed_bundle: object = None
        try:
            observed_bundle = self._source.load(request)
        except Exception:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _bundle_matches(observed_bundle, request):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH
            )
        bundle = observed_bundle
        observed_result: object = None
        try:
            observed_result = self._exchange.exchange(request, bundle)
        except Exception:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
            )
        if not _result_matches(
            request=request,
            bundle=bundle,
            observed=observed_result,
        ):
            fail_publication_snapshot(PublicationSnapshotFailureCode.OUTCOME_MISMATCH)
        return observed_result


__all__ = ("PublicationSnapshotService",)
