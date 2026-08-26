from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

import pytest

from .support import read
from scripts import build_st0904_public_projection_runtime_v2 as generator
from raos.adapters.recorded_public_projection_v2 import (
    RecordedPublicProjectionAdapter,
    RecordedPublicProjectionStep,
    load_recorded_public_projection_fixture,
)
from raos.application.publishing.public_projection_v2 import PublicProjectionService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.public_projection_v2 import (
    PublicProjectionFailure,
    PublicProjectionFailureCode,
)


def _service(
    step: RecordedPublicProjectionStep,
) -> tuple[PublicProjectionService, RecordedPublicProjectionAdapter]:
    adapter = RecordedPublicProjectionAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    return (
        PublicProjectionService(
            environment=RuntimeEnvironment.CI,
            source=adapter,
            exchange=adapter,
        ),
        adapter,
    )


def test_service_replays_idempotently(step: RecordedPublicProjectionStep) -> None:
    service, adapter = _service(step)
    first = service.execute(request=step.request)
    second = service.execute(request=step.request)
    assert first is second
    assert first.result_sha256 == step.result.result_sha256
    assert adapter.consumed_steps == 1


def test_adapter_replay_is_thread_safe(step: RecordedPublicProjectionStep) -> None:
    service, adapter = _service(step)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outputs = tuple(
            pool.map(lambda _index: service.execute(request=step.request), range(32))
        )
    assert {item.result_sha256 for item in outputs} == {step.result.result_sha256}
    assert adapter.consumed_steps == 1


def test_nonlocal_environment_is_rejected(
    step: RecordedPublicProjectionStep,
) -> None:
    adapter = RecordedPublicProjectionAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    with pytest.raises(PublicProjectionFailure) as captured:
        PublicProjectionService(
            environment=RuntimeEnvironment.PRODUCTION,
            source=adapter,
            exchange=adapter,
        )
    assert captured.value.code is (
        PublicProjectionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )


def test_same_idempotency_key_with_different_request_fails_closed(
    step: RecordedPublicProjectionStep,
) -> None:
    _service_instance, adapter = _service(step)
    conflicting = replace(
        step.request,
        expected_source_binding_sha256=type(
            step.request.expected_source_binding_sha256
        )("1" * 64),
    )
    with pytest.raises(PublicProjectionFailure) as captured:
        adapter.load(conflicting)
    assert captured.value.code is PublicProjectionFailureCode.IDEMPOTENCY_CONFLICT


def test_fixture_loader_rebuilds_st0903_and_projection(
    step: RecordedPublicProjectionStep,
) -> None:
    loaded = load_recorded_public_projection_fixture(
        read(generator.FIXTURE_PATH),
        st0903_fixture=read(generator.ST0903_FIXTURE_PATH),
        final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
        policy_fixture=read(generator.POLICY_FIXTURE_PATH),
        review_fixture=read(generator.REVIEW_FIXTURE_PATH),
        seo_fixture=read(generator.SEO_FIXTURE_PATH),
    )
    assert loaded.request_bytes == step.request_bytes
    assert loaded.result_bytes == step.result_bytes
    assert loaded.result.projection_bytes == step.result.projection_bytes


def test_fixture_source_hash_tampering_is_rejected() -> None:
    fixture = json.loads(read(generator.FIXTURE_PATH))
    fixture["sources"]["st0903_fixture_sha256"] = "0" * 64
    payload = (
        json.dumps(
            fixture,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )
    with pytest.raises(PublicProjectionFailure) as captured:
        load_recorded_public_projection_fixture(
            payload,
            st0903_fixture=read(generator.ST0903_FIXTURE_PATH),
            final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
            policy_fixture=read(generator.POLICY_FIXTURE_PATH),
            review_fixture=read(generator.REVIEW_FIXTURE_PATH),
            seo_fixture=read(generator.SEO_FIXTURE_PATH),
        )
    assert captured.value.code is PublicProjectionFailureCode.FIXTURE_INVALID
