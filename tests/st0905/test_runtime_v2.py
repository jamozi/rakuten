"""Focused behavior checks for the additive ST-0905 V2 runtime."""

from __future__ import annotations

import pytest

from raos.adapters.publishing.recorded_publication_command_fixture_v2 import (
    RecordedPublicationCommandScenarioV2,
)
from raos.adapters.publishing.recorded_publication_commands_v2 import (
    RecordedPublicationCommandStoreV2,
)
from raos.application.publishing.publication_commands_v2 import (
    PublicationCommandServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.publication_commands_v2 import (
    ExternalGateStatus,
    PublicationCommandFailure,
    PublicationCommandFailureCode,
    PublicationLocalState,
)
from raos.generated.contracts.jp_raos_publishing_article_published_v1 import (
    Schema as PublishedEvent,
)
from raos.generated.contracts.jp_raos_publishing_article_rolled_back_v1 import (
    Schema as RolledBackEvent,
)


def _service(
    scenario: RecordedPublicationCommandScenarioV2,
) -> tuple[PublicationCommandServiceV2, RecordedPublicationCommandStoreV2]:
    store = RecordedPublicationCommandStoreV2(
        environment=RuntimeEnvironment.CI,
        sources=scenario.sources,
    )
    return (
        PublicationCommandServiceV2(
            environment=RuntimeEnvironment.CI,
            store=store,
        ),
        store,
    )


def test_publish_replay_and_double_publish_are_exactly_once(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    initial = store.snapshot()
    assert initial.state is PublicationLocalState.UNPUBLISHED
    assert initial.generation == 0

    result = service.publish(runtime_scenario.publish)
    published = store.snapshot()
    exact_replay = service.publish(runtime_scenario.publish)
    replayed = store.snapshot()
    semantic_replay = service.publish(runtime_scenario.duplicate_publish)
    duplicated = store.snapshot()

    assert exact_replay.canonical_bytes() == result.canonical_bytes()
    assert semantic_replay.canonical_bytes() == result.canonical_bytes()
    assert replayed.snapshot_sha256 == published.snapshot_sha256
    assert duplicated.generation == 1
    assert duplicated.idempotency_receipts == 2
    assert (
        duplicated.projection_records,
        duplicated.event_intents,
        duplicated.audit_intents,
        duplicated.outbox_intents,
    ) == (1, 1, 1, 1)
    assert result.projection_persisted is False
    assert result.event_emitted is False
    assert result.audit_persisted is False
    assert result.outbox_persisted is False
    assert result.route_activated is False
    assert result.public_read_served is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert result.formal_tst_012_status is ExternalGateStatus.NOT_EXECUTED
    assert result.formal_tst_013_status is ExternalGateStatus.NOT_EXECUTED
    assert result.formal_tst_021_status is ExternalGateStatus.NOT_EXECUTED


def test_rollback_restores_only_the_known_previous_projection_and_replays(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    result = service.rollback(runtime_scenario.rollback)
    rolled_back = store.snapshot()
    replay = service.rollback(runtime_scenario.rollback)

    previous, latest = runtime_scenario.sources.snapshots
    assert result.from_snapshot_id == latest.snapshot_id
    assert result.to_snapshot_id == previous.snapshot_id
    assert result.projection_bytes == previous.projection_result.projection_bytes
    assert result.canonical_bytes() == replay.canonical_bytes()
    assert rolled_back.current_snapshot_id == previous.snapshot_id
    assert rolled_back.generation == 2
    assert (
        rolled_back.projection_records,
        rolled_back.event_intents,
        rolled_back.audit_intents,
        rolled_back.outbox_intents,
    ) == (2, 2, 2, 2)
    assert store.snapshot().snapshot_sha256 == rolled_back.snapshot_sha256


def test_local_event_intents_validate_against_the_exact_schemas(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, _store = _service(runtime_scenario)
    publish = service.publish(runtime_scenario.publish)
    rollback = service.rollback(runtime_scenario.rollback)
    published = PublishedEvent.model_validate_json(publish.event_bytes, strict=True)
    rolled_back = RolledBackEvent.model_validate_json(
        rollback.event_bytes,
        strict=True,
    )
    assert published.type == "jp.raos.publishing.article_published.v1"
    assert rolled_back.type == "jp.raos.publishing.article_rolled_back.v1"


def test_unpublish_is_typed_but_default_denied_without_store_mutation(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    before = store.snapshot()
    with pytest.raises(PublicationCommandFailure) as captured:
        service.unpublish(runtime_scenario.unpublish)
    assert (
        captured.value.code
        is PublicationCommandFailureCode.UNPUBLISH_ROLE_ACTION_UNDEFINED
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256


@pytest.mark.parametrize(
    "environment",
    [RuntimeEnvironment.STAGING, RuntimeEnvironment.PRODUCTION],
)
def test_nonlocal_environments_are_denied(
    environment: RuntimeEnvironment,
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    with pytest.raises(PublicationCommandFailure) as captured:
        RecordedPublicationCommandStoreV2(
            environment=environment,
            sources=runtime_scenario.sources,
        )
    assert (
        captured.value.code is PublicationCommandFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )
