"""ENV-DEV/CI-only application service for the ST-1302 recorded seam."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.provider_fact_commit import (
    ProviderFactCommitFailure,
    ProviderFactCommitFailureCode,
    ProviderFactCommitRequest,
    ProviderFactCommitResult,
    RecordedProviderFactCommitAuthorization,
    RecordedRevenueDryRunBundle,
    build_provider_fact_commit_result,
    fail_provider_fact_commit,
)
from raos.ports.provider_fact_commit import (
    ProviderFactCommitStore,
    RecordedProviderFactCommitAuthorizationSource,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class ProviderFactCommitService:
    """Obtain recorded authorization and execute one atomic local exchange."""

    __slots__ = ("_authorization_source", "_store")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        authorization_source: RecordedProviderFactCommitAuthorizationSource,
        store: ProviderFactCommitStore,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(
                cast(object, authorization_source),
                RecordedProviderFactCommitAuthorizationSource,
            )
            or not _implements(cast(object, store), ProviderFactCommitStore)
        ):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._authorization_source = authorization_source
        self._store = store

    def execute(
        self,
        *,
        request: ProviderFactCommitRequest,
        bundle: RecordedRevenueDryRunBundle,
    ) -> ProviderFactCommitResult:
        if (
            type(request) is not ProviderFactCommitRequest
            or type(bundle) is not RecordedRevenueDryRunBundle
        ):
            fail_provider_fact_commit()
        authorization: object = None
        try:
            authorization = self._authorization_source.authorize(request, bundle)
        except Exception:
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.AUTHORIZATION_INVALID
            )
        if type(authorization) is not RecordedProviderFactCommitAuthorization:
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.AUTHORIZATION_INVALID
            )
        # Validate all hashes, values and controls before the store can mutate.
        expected = build_provider_fact_commit_result(
            request=request,
            bundle=bundle,
            authorization=authorization,
        )
        observed: object = None
        try:
            observed = self._store.commit(request, bundle, authorization)
        except Exception as error:
            # Preserve closed domain failures; sanitize adapter/runtime failures.
            if type(error) is ProviderFactCommitFailure:
                raise error from None
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
            )
        if (
            type(observed) is not ProviderFactCommitResult
            or observed != expected
            or observed.canonical_bytes() != expected.canonical_bytes()
        ):
            fail_provider_fact_commit(ProviderFactCommitFailureCode.OUTCOME_MISMATCH)
        return observed


__all__ = ("ProviderFactCommitService",)
