"""One-call maximum-safe category fixture application seam for ST-1702."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.category_fixtures import (
    CategoryFixtureFailure,
    CategoryFixtureFailureCode,
    CategoryFixtureLoadRequest,
    CategoryFixtureLoadResult,
    fail_category_fixture,
    validate_category_fixture_bundle,
)
from raos.ports.category_fixtures import RecordedCategoryFixturePort


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class CategoryFixtureService:
    """Load one recorded fixture once without granting runtime authority."""

    __slots__ = ("_port",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        port: RecordedCategoryFixturePort,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(port, RecordedCategoryFixturePort)
        ):
            fail_category_fixture()
        self._port = port

    def load(self, request: CategoryFixtureLoadRequest) -> CategoryFixtureLoadResult:
        if type(request) is not CategoryFixtureLoadRequest:
            fail_category_fixture()
        try:
            request.__post_init__()
        except Exception:
            fail_category_fixture()
        result: object = None
        failure: CategoryFixtureFailureCode | None = None
        try:
            result = self._port.load(request)
        except CategoryFixtureFailure as error:
            failure = error.code
        except Exception:
            failure = CategoryFixtureFailureCode.SOURCE_UNAVAILABLE
        if failure is not None:
            fail_category_fixture(failure)
        if type(result) is not CategoryFixtureLoadResult:
            fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
        try:
            result.__post_init__()
            bundle = validate_category_fixture_bundle(result.bundle)
        except Exception:
            fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
        if (
            result.request_fingerprint != request.fingerprint
            or bundle.fixture_id != request.fixture_id
            or bundle.source_fixture_sha256 != request.expected_source_fixture_sha256
        ):
            fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
        return result


__all__ = ["CategoryFixtureService"]
