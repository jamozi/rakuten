"""One-use application orchestration for the ST-0505 owner-local read surface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import final

from raos.domain.catalog.rakuten_owner_local import (
    RakutenOwnerLocalApi,
    RakutenOwnerLocalCredentials,
    RakutenOwnerLocalFailure,
    RakutenOwnerLocalFailureCode,
    RakutenOwnerLocalItemSearchRequest,
    RakutenOwnerLocalOutcome,
    RakutenOwnerLocalProductSearchRequest,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
    RakutenOwnerLocalRequestDisposition,
    RakutenOwnerLocalResultEnvelope,
    api_definition,
    contextual_failure,
    fail_owner_local,
    validate_run_id,
)
from raos.ports.rakuten_owner_local import (
    RakutenOwnerLocalCredentialReader,
    RakutenOwnerLocalResultWriter,
    RakutenOwnerLocalTransport,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_hits(request: RakutenOwnerLocalRequest) -> int:
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        return request.policy.hits
    if type(request) is RakutenOwnerLocalProductSearchRequest:
        return request.hits
    fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)


def _response_failure(
    code: RakutenOwnerLocalFailureCode,
    *,
    api: RakutenOwnerLocalApi,
    request_fingerprint: str,
    result: RakutenOwnerLocalProviderResult,
) -> RakutenOwnerLocalFailure:
    return RakutenOwnerLocalFailure(
        code=code,
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=result.http_status,
        body_byte_count=result.body_byte_count,
        response_sha256=result.response_sha256,
    )


@final
@dataclass(slots=True)
class RakutenOwnerLocalService:
    """Preflight, read credentials, issue at most one GET, and write once."""

    credential_reader: RakutenOwnerLocalCredentialReader
    transport: RakutenOwnerLocalTransport
    result_writer: RakutenOwnerLocalResultWriter
    clock: Callable[[], datetime] = _utc_now
    _attempted: bool = False

    def __post_init__(self) -> None:
        if (
            not _implements(self.credential_reader, RakutenOwnerLocalCredentialReader)
            or not _implements(self.transport, RakutenOwnerLocalTransport)
            or not _implements(self.result_writer, RakutenOwnerLocalResultWriter)
            or not callable(self.clock)
            or type(self._attempted) is not bool
            or self._attempted
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)

    def run(
        self,
        api: RakutenOwnerLocalApi,
        request: RakutenOwnerLocalRequest,
        *,
        run_id: str,
    ) -> RakutenOwnerLocalResultEnvelope:
        if self._attempted:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.REQUEST_ALREADY_ATTEMPTED,
                api=api if type(api) is RakutenOwnerLocalApi else None,
            )
        if (
            type(api) is not RakutenOwnerLocalApi
            or type(request)
            not in {
                RakutenOwnerLocalItemSearchRequest,
                RakutenOwnerLocalProductSearchRequest,
            }
            or request.api is not api
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        validate_run_id(run_id)
        self._attempted = True
        started_at = self.clock()
        request_fingerprint = request.fingerprint

        try:
            self.result_writer.preflight()
        except Exception:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
                api=api,
                request_fingerprint=request_fingerprint,
            )

        failure: RakutenOwnerLocalFailure | None = None
        provider_result: RakutenOwnerLocalProviderResult | None = None
        credentials: RakutenOwnerLocalCredentials | None = None
        try:
            credentials = self.credential_reader.read()
        except RakutenOwnerLocalFailure as error:
            if error.disposition is RakutenOwnerLocalRequestDisposition.NOT_SENT:
                failure = contextual_failure(
                    error,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
            else:
                failure = RakutenOwnerLocalFailure(
                    code=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
        except Exception:
            failure = RakutenOwnerLocalFailure(
                code=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                api=api,
                request_fingerprint=request_fingerprint,
            )
        if failure is None and type(credentials) is not RakutenOwnerLocalCredentials:
            failure = RakutenOwnerLocalFailure(
                code=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                api=api,
                request_fingerprint=request_fingerprint,
            )

        if failure is None:
            if type(credentials) is not RakutenOwnerLocalCredentials:
                fail_owner_local(
                    RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
            try:
                provider_result = self.transport.execute(
                    api_definition(api),
                    request,
                    credentials,
                )
            except RakutenOwnerLocalFailure as error:
                failure = contextual_failure(
                    error,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
            except Exception:
                failure = RakutenOwnerLocalFailure(
                    code=RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                    disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )

        if failure is None:
            if type(provider_result) is not RakutenOwnerLocalProviderResult:
                failure = RakutenOwnerLocalFailure(
                    code=RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                    disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
                provider_result = None
            elif (
                provider_result.api is not api
                or provider_result.request_fingerprint != request_fingerprint
                or provider_result.hits != _request_hits(request)
            ):
                failure = _response_failure(
                    RakutenOwnerLocalFailureCode.RESULT_MISMATCH,
                    api=api,
                    request_fingerprint=request_fingerprint,
                    result=provider_result,
                )
                provider_result = None

        finished_at = self.clock()
        if failure is None:
            if provider_result is None:
                fail_owner_local(
                    RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                    disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
            envelope = RakutenOwnerLocalResultEnvelope(
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                api=api,
                request_fingerprint=request_fingerprint,
                outcome=RakutenOwnerLocalOutcome.SUCCESS,
                provider_result=provider_result,
                failure=None,
            )
        else:
            envelope = RakutenOwnerLocalResultEnvelope(
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                api=api,
                request_fingerprint=request_fingerprint,
                outcome=RakutenOwnerLocalOutcome.FAILURE,
                provider_result=None,
                failure=failure,
            )
        try:
            self.result_writer.write(envelope)
        except Exception:
            write_failure = envelope.failure
            if envelope.provider_result is not None:
                write_failure = _response_failure(
                    RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
                    api=api,
                    request_fingerprint=request_fingerprint,
                    result=envelope.provider_result,
                )
            if write_failure is None:
                fail_owner_local(
                    RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
                    api=api,
                    request_fingerprint=request_fingerprint,
                )
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
                disposition=write_failure.disposition,
                api=api,
                request_fingerprint=request_fingerprint,
                http_status=write_failure.http_status,
                body_byte_count=write_failure.body_byte_count,
                response_sha256=write_failure.response_sha256,
            )
        return envelope


__all__ = ["RakutenOwnerLocalService"]
