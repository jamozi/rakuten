"""Application, port, and recorded-adapter tests for ST-1702 V2."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from raos.adapters import recorded_category_fixtures as adapter_module
from raos.adapters.recorded_category_fixtures import RecordedCategoryFixtureAdapter
from raos.application.catalog.category_fixtures import CategoryFixtureService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog import category_fixtures as domain_module
from raos.domain.catalog.category_fixtures import (
    CategoryFixtureFailure,
    CategoryFixtureFailureCode,
    CategoryFixtureLoadRequest,
    CategoryFixtureLoadResult,
)
from raos.adapters.recorded_category_fixture_v2 import (
    ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256,
)
from raos.ports.category_fixtures import RecordedCategoryFixturePort


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ID = "00000000-0000-7000-8000-000000001702"


def _request() -> CategoryFixtureLoadRequest:
    from uuid import UUID

    return CategoryFixtureLoadRequest(
        fixture_id=UUID(FIXTURE_ID),
        expected_source_fixture_sha256=ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256,
    )


@pytest.mark.parametrize(
    "environment", (RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI)
)
def test_recorded_adapter_and_service_load_deterministically(
    environment: RuntimeEnvironment,
) -> None:
    adapter = RecordedCategoryFixtureAdapter(environment=environment)
    assert isinstance(adapter, RecordedCategoryFixturePort)
    service = CategoryFixtureService(environment=environment, port=adapter)
    first = service.load(_request())
    second = service.load(_request())
    assert first == second
    assert first.request_fingerprint == _request().fingerprint
    assert first.source_mode == "RECORDED_SYNTHETIC_DEV_CI_ONLY"
    assert first.persistence == "NOT_EXECUTED"
    assert first.external_actions == "NOT_EXECUTED"


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_non_dev_ci_environments_are_rejected(environment: RuntimeEnvironment) -> None:
    with pytest.raises(CategoryFixtureFailure):
        RecordedCategoryFixtureAdapter(environment=environment)
    adapter = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI)
    with pytest.raises(CategoryFixtureFailure):
        CategoryFixtureService(environment=environment, port=adapter)


def test_request_id_or_hash_mismatch_fails_closed() -> None:
    from uuid import UUID

    adapter = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI)
    bad_id = CategoryFixtureLoadRequest(
        fixture_id=UUID("00000000-0000-7000-8000-000000001799"),
        expected_source_fixture_sha256=ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256,
    )
    bad_hash = CategoryFixtureLoadRequest(
        fixture_id=UUID(FIXTURE_ID), expected_source_fixture_sha256="0" * 64
    )
    for request in (bad_id, bad_hash):
        with pytest.raises(CategoryFixtureFailure) as captured:
            adapter.load(request)
        assert captured.value.code is CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("fixture_id", "not-a-uuid"),
        ("expected_source_fixture_sha256", "not-a-hash"),
    ),
)
def test_mutated_request_is_revalidated_before_port_use(
    field: str, value: object
) -> None:
    request = _request()
    object.__setattr__(request, field, value)
    adapter = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI)
    with pytest.raises(CategoryFixtureFailure):
        adapter.load(request)
    port = _CountingPort()
    service = CategoryFixtureService(environment=RuntimeEnvironment.CI, port=port)
    with pytest.raises(CategoryFixtureFailure):
        service.load(request)
    assert port.calls == 0


def test_generated_hash_anchor_cannot_be_rebound_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter_module,
        "ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256",
        "0" * 64,
    )
    with pytest.raises(CategoryFixtureFailure) as captured:
        RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI)
    assert captured.value.code is CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH


def test_adapter_rejects_post_init_fixture_rebinding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI)
    changed = json.loads(
        adapter_module.ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON  # type: ignore[attr-defined]
    )
    changed["category"]["displayName"] = "Changed synthetic category"
    payload = (
        json.dumps(changed, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + "\n"
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    monkeypatch.setattr(
        adapter_module, "ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON", payload
    )
    monkeypatch.setattr(
        adapter_module, "ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256", digest
    )
    with pytest.raises(CategoryFixtureFailure) as captured:
        adapter.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH


class _CountingPort:
    def __init__(
        self, result: object = None, failure: BaseException | None = None
    ) -> None:
        self.calls = 0
        self.result = result
        self.failure = failure

    def load(self, request: CategoryFixtureLoadRequest) -> CategoryFixtureLoadResult:
        del request
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.result  # type: ignore[return-value]


def test_service_calls_port_exactly_once() -> None:
    expected = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        _request()
    )
    port = _CountingPort(expected)
    service = CategoryFixtureService(environment=RuntimeEnvironment.CI, port=port)
    assert service.load(_request()) == expected
    assert port.calls == 1


@pytest.mark.parametrize("result", (None, object(), "unsafe"))
def test_service_rejects_wrong_result_shape_without_retry(result: object) -> None:
    port = _CountingPort(result)
    service = CategoryFixtureService(environment=RuntimeEnvironment.CI, port=port)
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.RESULT_MISMATCH
    assert port.calls == 1


def test_service_sanitizes_unknown_port_exception_without_retry() -> None:
    port = _CountingPort(failure=RuntimeError("secret-canary"))
    service = CategoryFixtureService(environment=RuntimeEnvironment.CI, port=port)
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.SOURCE_UNAVAILABLE
    assert "secret-canary" not in repr(captured.value)
    assert port.calls == 1


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("automatic_merge_enabled", True),
        ("automatic_split_enabled", True),
        ("runtime_enabled", True),
        ("provider_access_enabled", True),
        ("network_enabled", True),
        ("persistence_enabled", True),
        ("external_actions_enabled", True),
        ("publication_authorized", True),
        ("activation_authorized", True),
        ("release_authorized", True),
        ("production_authorized", True),
        ("formal_acceptance_achieved", True),
        ("human_review_required", False),
        ("domain_reviewer_approval", "APPROVED"),
        ("category_overrides", ("unsafe",)),
        ("provider_overrides", ("unsafe",)),
        ("stale_never_fresh", False),
        ("recommendation_auto_reorder", "ALLOWED"),
        ("formal_tst_020", "PASS"),
        ("data_class", "PRODUCTION"),
        ("category_activation", "ACTIVE"),
        ("identity_activation", "ACTIVE"),
        ("freshness_activation", "ACTIVE"),
    ),
)
def test_service_rejects_forged_policy_or_authority_result(
    field: str, value: object
) -> None:
    result = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        _request()
    )
    object.__setattr__(result.bundle, field, value)
    port = _CountingPort(result)
    service = CategoryFixtureService(environment=RuntimeEnvironment.CI, port=port)
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.RESULT_MISMATCH


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_mode", "LIVE"),
        ("persistence", "EXECUTED"),
        ("external_actions", "EXECUTED"),
    ),
)
def test_service_rejects_forged_result_envelope(field: str, value: str) -> None:
    result = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        _request()
    )
    object.__setattr__(result, field, value)
    service = CategoryFixtureService(
        environment=RuntimeEnvironment.CI, port=_CountingPort(result)
    )
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.RESULT_MISMATCH


def test_service_rejects_policy_safe_content_mutation_with_stale_fingerprint() -> None:
    result = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        _request()
    )
    object.__setattr__(result.bundle.golden_products[0], "display_name", "Changed")
    service = CategoryFixtureService(
        environment=RuntimeEnvironment.CI, port=_CountingPort(result)
    )
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.RESULT_MISMATCH


def test_service_rejects_content_mutation_with_recomputed_record_fingerprint() -> None:
    result = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        _request()
    )
    object.__setattr__(result.bundle.golden_products[0], "display_name", "Changed")
    object.__setattr__(
        result.bundle,
        "record_fingerprint",
        domain_module._bundle_fingerprint(result.bundle),
    )
    service = CategoryFixtureService(
        environment=RuntimeEnvironment.CI, port=_CountingPort(result)
    )
    with pytest.raises(CategoryFixtureFailure) as captured:
        service.load(_request())
    assert captured.value.code is CategoryFixtureFailureCode.RESULT_MISMATCH


def test_result_and_request_are_immutable() -> None:
    request = _request()
    result = RecordedCategoryFixtureAdapter(environment=RuntimeEnvironment.CI).load(
        request
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.fixture_id = request.fixture_id  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.source_mode = "unsafe"  # type: ignore[misc,assignment]


def test_runtime_modules_do_not_import_effectful_surfaces() -> None:
    paths = (
        ROOT / "python/raos/domain/catalog/category_fixtures.py",
        ROOT / "python/raos/ports/category_fixtures.py",
        ROOT / "python/raos/application/catalog/category_fixtures.py",
        ROOT / "python/raos/adapters/recorded_category_fixtures.py",
    )
    prohibited = ("requests", "urllib", "socket", "subprocess", "sqlalchemy", "boto3")
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert all(f"import {name}" not in source for name in prohibited)
    assert "os.environ" not in source
    assert "open(" not in source
