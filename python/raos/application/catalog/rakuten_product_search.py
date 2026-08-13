"""One-call recorded-only Product Search application seam for ST-0502."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_product_search import (
    ProductSelectorKind,
    RakutenProductSearchFailure,
    RakutenProductSearchFailureCode,
    RakutenProductSearchRequest,
    RakutenProductSearchResult,
    fail_product_search,
)
from raos.ports.rakuten_product_search import RecordedRakutenProductSearchPort


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class RakutenProductSearchService:
    """Call one recorded port once and reject an unbound domain result."""

    __slots__ = ("_port",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        port: RecordedRakutenProductSearchPort,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(port, RecordedRakutenProductSearchPort)
        ):
            fail_product_search()
        self._port = port

    def search(
        self, request: RakutenProductSearchRequest
    ) -> RakutenProductSearchResult:
        if type(request) is not RakutenProductSearchRequest:
            fail_product_search()
        result: object = None
        failure_code: RakutenProductSearchFailureCode | None = None
        try:
            result = self._port.search(request)
        except RakutenProductSearchFailure as error:
            failure_code = error.code
        except Exception:
            failure_code = RakutenProductSearchFailureCode.PROVIDER_UNAVAILABLE
        if failure_code is not None:
            fail_product_search(failure_code)
        if (
            type(result) is not RakutenProductSearchResult
            or result.request_fingerprint != request.fingerprint
            or result.receipt.request_fingerprint != request.fingerprint
            or (
                request.selector_kind is ProductSelectorKind.PRODUCT_ID
                and result.product.product_id != request.selector_value
            )
            or (
                request.selector_kind is ProductSelectorKind.PRODUCT_CODE
                and result.product.product_code != request.selector_value
            )
        ):
            fail_product_search(RakutenProductSearchFailureCode.RESULT_MISMATCH)
        return result


__all__ = ["RakutenProductSearchService"]
