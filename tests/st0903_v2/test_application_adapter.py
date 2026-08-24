from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

import pytest

from .conftest import REPO_ROOT, read
from scripts import build_st0903_publication_snapshot_runtime_v2 as generator
from raos.adapters.recorded_publication_snapshot_v2 import (
    RecordedPublicationSnapshotAdapter,
    RecordedPublicationSnapshotStep,
    load_recorded_publication_snapshot_fixture,
)
from raos.application.publishing.publication_snapshot_v2 import (
    PublicationSnapshotService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotFailure,
    PublicationSnapshotFailureCode,
)


def _service(
    step: RecordedPublicationSnapshotStep,
) -> tuple[PublicationSnapshotService, RecordedPublicationSnapshotAdapter]:
    adapter = RecordedPublicationSnapshotAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    return (
        PublicationSnapshotService(
            environment=RuntimeEnvironment.CI,
            source=adapter,
            exchange=adapter,
        ),
        adapter,
    )


def test_service_executes_once_and_replays_idempotently(
    step: RecordedPublicationSnapshotStep,
) -> None:
    service, adapter = _service(step)
    first = service.execute(request=step.request)
    second = service.execute(request=step.request)

    assert first is second
    assert first.result_sha256 == step.result.result_sha256
    assert adapter.consumed_steps == 1


def test_replay_is_thread_safe(step: RecordedPublicationSnapshotStep) -> None:
    service, adapter = _service(step)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outputs = tuple(
            pool.map(lambda _index: service.execute(request=step.request), range(32))
        )
    assert {item.result_sha256 for item in outputs} == {step.result.result_sha256}
    assert adapter.consumed_steps == 1


def test_nonlocal_environment_is_rejected(
    step: RecordedPublicationSnapshotStep,
) -> None:
    adapter = RecordedPublicationSnapshotAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    with pytest.raises(PublicationSnapshotFailure) as captured:
        PublicationSnapshotService(
            environment=RuntimeEnvironment.PRODUCTION,
            source=adapter,
            exchange=adapter,
        )
    assert captured.value.code is (
        PublicationSnapshotFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )


def test_same_idempotency_key_with_different_request_fails_closed(
    step: RecordedPublicationSnapshotStep,
) -> None:
    _service_instance, adapter = _service(step)
    conflicting = replace(
        step.request,
        renderer_version="ST0807_LOCAL_RENDER_V1.CONFLICT",
    )
    with pytest.raises(PublicationSnapshotFailure) as captured:
        adapter.load(conflicting)
    assert captured.value.code is PublicationSnapshotFailureCode.IDEMPOTENCY_CONFLICT


def test_fixture_loader_rebuilds_all_dependencies(
    step: RecordedPublicationSnapshotStep,
) -> None:
    loaded = load_recorded_publication_snapshot_fixture(
        read(generator.FIXTURE_PATH),
        final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
        policy_fixture=read(generator.POLICY_FIXTURE_PATH),
        review_fixture=read(generator.REVIEW_FIXTURE_PATH),
        seo_fixture=read(generator.SEO_FIXTURE_PATH),
    )
    assert loaded.request_bytes == step.request_bytes
    assert loaded.result_bytes == step.result_bytes
    assert loaded.result.snapshot_bytes == step.result.snapshot_bytes


def test_fixture_hash_tampering_is_rejected() -> None:
    fixture = json.loads(read(generator.FIXTURE_PATH))
    fixture["sources"]["seo_fixture_sha256"] = "0" * 64
    payload = (
        json.dumps(
            fixture, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        + b"\n"
    )
    with pytest.raises(PublicationSnapshotFailure) as captured:
        load_recorded_publication_snapshot_fixture(
            payload,
            final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
            policy_fixture=read(generator.POLICY_FIXTURE_PATH),
            review_fixture=read(generator.REVIEW_FIXTURE_PATH),
            seo_fixture=read(generator.SEO_FIXTURE_PATH),
        )
    assert captured.value.code is PublicationSnapshotFailureCode.FIXTURE_INVALID


def test_fixture_file_is_repository_local() -> None:
    assert (REPO_ROOT / generator.FIXTURE_PATH).is_file()
