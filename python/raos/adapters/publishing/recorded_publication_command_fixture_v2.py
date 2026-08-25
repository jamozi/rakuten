"""Owner-rebuildable recorded fixture for the ST-0905 local command runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Final, final
from uuid import UUID

from raos.adapters.publishing.recorded_publication_commands_v2 import (
    RecordedPublicationCommandStoreV2,
)
from raos.adapters.recorded_public_projection_v2 import (
    load_recorded_public_projection_fixture,
)
from raos.adapters.recorded_publication_snapshot_v2 import (
    load_recorded_publication_snapshot_fixture,
)
from raos.application.publishing.publication_commands_v2 import (
    PublicationCommandServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import Issuer, SessionId, Subject
from raos.domain.iam.step_up import StepUpAssuranceType, StepUpGrant
from raos.domain.publishing.public_projection_v2 import (
    PublicProjectionInputV2,
    PublicProjectionRequestV2,
    build_public_projection_v2,
)
from raos.domain.publishing.publication_commands_v2 import (
    PROFILE,
    KnownPublicationSnapshotV2,
    PublicationCommandAuthorizationV2,
    PublicationCommandRole,
    PublicationCommandSourcesV2,
    PublicationKillSwitchSafeStateV2,
    PublicationStoreSnapshotV2,
    PublishCommandV2,
    RollbackCommandV2,
    UnpublishCommandV2,
    fail_publication_command,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotBuildRequestV2,
    build_publication_snapshot_v2,
    canonical_json_bytes,
    parse_canonical_object,
)
from raos.domain.shared.persistence import Sha256Digest


_MAX_FIXTURE_BYTES: Final = 8 * 1024 * 1024
_AUTHORITY: Final = {
    "cms_write": False,
    "database_write": False,
    "event_emission": False,
    "external_write": False,
    "http_route": False,
    "live_provider": False,
    "outbox_write": False,
    "production_write": False,
    "public_state_change": False,
    "publication": False,
    "release": False,
    "staging_write": False,
}


def _sha(payload: bytes) -> Sha256Digest:
    if type(payload) is not bytes or not payload:
        fail_publication_command()
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is not UTC or result.microsecond:
        fail_publication_command()
    return result


def _uuid(value: str) -> UUID:
    result = UUID(value)
    if result.version != 7:
        fail_publication_command()
    return result


def _state(value: PublicationStoreSnapshotV2) -> dict[str, object]:
    return {
        "audit_intents": value.audit_intents,
        "current_projection_sha256": (
            value.current_projection_sha256.value
            if value.current_projection_sha256 is not None
            else None
        ),
        "current_snapshot_id": (
            str(value.current_snapshot_id)
            if value.current_snapshot_id is not None
            else None
        ),
        "current_source_binding_sha256": (
            value.current_source_binding_sha256.value
            if value.current_source_binding_sha256 is not None
            else None
        ),
        "event_intents": value.event_intents,
        "generation": value.generation,
        "idempotency_receipts": value.idempotency_receipts,
        "outbox_intents": value.outbox_intents,
        "projection_records": value.projection_records,
        "snapshot_sha256": value.snapshot_sha256.value,
        "state": value.state.value,
    }


@final
@dataclass(frozen=True, slots=True)
class RecordedPublicationCommandScenarioV2:
    sources: PublicationCommandSourcesV2
    publish: PublishCommandV2
    duplicate_publish: PublishCommandV2
    rollback: RollbackCommandV2
    unpublish: UnpublishCommandV2


def _authorization(
    *,
    site_id: UUID,
    observed_at: datetime,
) -> PublicationCommandAuthorizationV2:
    session = SessionId.from_bytes(b"\x95" * 32)
    return PublicationCommandAuthorizationV2(
        actor_id=_uuid("018f3e90-7b00-7000-8000-000000000951"),
        site_id=site_id,
        role=PublicationCommandRole.MANAGING_EDITOR,
        session_id=session,
        step_up_grant=StepUpGrant(
            session_id=session,
            issuer=Issuer("https://recorded.identity.invalid/st0905"),
            subject=Subject("st0905-recorded-active-human"),
            assurance_type=StepUpAssuranceType.MULTI_FACTOR,
            authenticated_at=_instant("2026-08-24T01:58:00Z"),
            expires_at=_instant("2026-08-24T02:10:00Z"),
        ),
        observed_at=observed_at,
    )


def _kill_state() -> PublicationKillSwitchSafeStateV2:
    return PublicationKillSwitchSafeStateV2(
        observation_id=_uuid("018f3e90-7b00-7000-8000-000000000952"),
        generation=1,
        observed_at=_instant("2026-08-24T01:59:00Z"),
        fresh_until=_instant("2026-08-24T02:10:00Z"),
        source_sha256=Sha256Digest(
            hashlib.sha256(b"st0905-recorded-kill-switch-safe-state").hexdigest()
        ),
    )


def build_recorded_publication_command_scenario_v2(
    *,
    st0903_fixture: bytes,
    st0904_fixture: bytes,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> RecordedPublicationCommandScenarioV2:
    """Rebuild both immutable source candidates and the closed command sequence."""

    try:
        snapshot_step = load_recorded_publication_snapshot_fixture(
            st0903_fixture,
            final_approval_fixture=final_approval_fixture,
            policy_fixture=policy_fixture,
            review_fixture=review_fixture,
            seo_fixture=seo_fixture,
        )
        projection_step = load_recorded_public_projection_fixture(
            st0904_fixture,
            st0903_fixture=st0903_fixture,
            final_approval_fixture=final_approval_fixture,
            policy_fixture=policy_fixture,
            review_fixture=review_fixture,
            seo_fixture=seo_fixture,
        )
        latest = KnownPublicationSnapshotV2(
            final_approval_request=snapshot_step.bundle.final_approval_request,
            final_approval_result=snapshot_step.bundle.final_approval_result,
            snapshot_request=snapshot_step.request,
            snapshot_result=snapshot_step.result,
            projection_request=projection_step.request,
            projection_result=projection_step.result,
            snapshot_fixture_sha256=_sha(st0903_fixture),
            projection_fixture_sha256=_sha(st0904_fixture),
        )
        request = snapshot_step.request
        previous_request = PublicationSnapshotBuildRequestV2(
            publication_candidate_id=request.publication_candidate_id,
            publication_content_manifest_id=request.publication_content_manifest_id,
            publication_id=request.publication_id,
            snapshot_artifact_id=_uuid("018f3e90-7b00-7000-8000-000000000939"),
            publication_version=request.publication_version,
            article_id=request.article_id,
            article_version_id=request.article_version_id,
            quality_result_id=request.quality_result_id,
            created_at=_instant("2026-08-24T01:35:30Z"),
            methodology_version_ref=request.methodology_version_ref,
            policy_bundle_version_ref=request.policy_bundle_version_ref,
            disclosure_policy_version_ref=request.disclosure_policy_version_ref,
            renderer_version=request.renderer_version,
            expected_input_bundle_sha256=request.expected_input_bundle_sha256,
            idempotency_key="st0905-v2-previous-snapshot-0001",
        )
        previous_result = build_publication_snapshot_v2(
            request=previous_request,
            bundle=snapshot_step.bundle,
        )
        previous_projection_input = PublicProjectionInputV2(
            snapshot_request=previous_request,
            snapshot_result=previous_result,
            source_fixture_sha256=_sha(st0903_fixture),
        )
        previous_projection_request = PublicProjectionRequestV2(
            expected_source_binding_sha256=previous_projection_input.binding_sha256,
            idempotency_key="st0905-v2-previous-projection-0001",
            projection_generation=1,
        )
        previous_projection_result = build_public_projection_v2(
            request=previous_projection_request,
            source=previous_projection_input,
        )
        previous = KnownPublicationSnapshotV2(
            final_approval_request=snapshot_step.bundle.final_approval_request,
            final_approval_result=snapshot_step.bundle.final_approval_result,
            snapshot_request=previous_request,
            snapshot_result=previous_result,
            projection_request=previous_projection_request,
            projection_result=previous_projection_result,
            snapshot_fixture_sha256=_sha(st0903_fixture),
            projection_fixture_sha256=_sha(st0904_fixture),
        )
        sources = PublicationCommandSourcesV2(snapshots=(previous, latest))
        site_id = latest.final_approval_result.record.site_id.value
        publish_at = _instant("2026-08-24T02:00:00Z")
        duplicate_at = _instant("2026-08-24T02:01:00Z")
        rollback_at = _instant("2026-08-24T02:02:00Z")
        publish = PublishCommandV2(
            publication_id=latest.publication_id,
            publication_candidate_id=latest.snapshot_request.publication_candidate_id,
            snapshot_id=latest.snapshot_id,
            expected_source_binding_sha256=latest.source_binding_sha256,
            expected_generation=0,
            idempotency_key="st0905-v2-publish-0001",
            authorization=_authorization(site_id=site_id, observed_at=publish_at),
            kill_switch=_kill_state(),
            occurred_at=publish_at,
            correlation_id=_uuid("018f3e90-7b00-7000-8000-000000000953"),
            event_id=_uuid("018f3e90-7b00-7000-8000-000000000954"),
            audit_id=_uuid("018f3e90-7b00-7000-8000-000000000955"),
            outbox_id=_uuid("018f3e90-7b00-7000-8000-000000000956"),
        )
        duplicate_publish = PublishCommandV2(
            publication_id=latest.publication_id,
            publication_candidate_id=latest.snapshot_request.publication_candidate_id,
            snapshot_id=latest.snapshot_id,
            expected_source_binding_sha256=latest.source_binding_sha256,
            expected_generation=1,
            idempotency_key="st0905-v2-publish-semantic-replay-0002",
            authorization=_authorization(site_id=site_id, observed_at=duplicate_at),
            kill_switch=_kill_state(),
            occurred_at=duplicate_at,
            correlation_id=_uuid("018f3e90-7b00-7000-8000-000000000957"),
            event_id=_uuid("018f3e90-7b00-7000-8000-000000000958"),
            audit_id=_uuid("018f3e90-7b00-7000-8000-000000000959"),
            outbox_id=_uuid("018f3e90-7b00-7000-8000-000000000960"),
        )
        rollback = RollbackCommandV2(
            publication_id=latest.publication_id,
            from_snapshot_id=latest.snapshot_id,
            to_snapshot_id=previous.snapshot_id,
            expected_from_source_binding_sha256=latest.source_binding_sha256,
            expected_to_source_binding_sha256=previous.source_binding_sha256,
            expected_generation=1,
            reason="Recorded rollback restores the prior immutable snapshot.",
            rollback_record_id=_uuid("018f3e90-7b00-7000-8000-000000000961"),
            idempotency_key="st0905-v2-rollback-0001",
            authorization=_authorization(site_id=site_id, observed_at=rollback_at),
            kill_switch=_kill_state(),
            occurred_at=rollback_at,
            correlation_id=_uuid("018f3e90-7b00-7000-8000-000000000962"),
            event_id=_uuid("018f3e90-7b00-7000-8000-000000000963"),
            audit_id=_uuid("018f3e90-7b00-7000-8000-000000000964"),
            outbox_id=_uuid("018f3e90-7b00-7000-8000-000000000965"),
        )
        unpublish = UnpublishCommandV2(
            publication_id=latest.publication_id,
            expected_generation=1,
            reason="Unpublish remains denied because no Canonical role action exists.",
            idempotency_key="st0905-v2-unpublish-denied-0001",
            authorization=_authorization(site_id=site_id, observed_at=rollback_at),
            kill_switch=_kill_state(),
            occurred_at=rollback_at,
            correlation_id=_uuid("018f3e90-7b00-7000-8000-000000000966"),
            event_id=_uuid("018f3e90-7b00-7000-8000-000000000967"),
            audit_id=_uuid("018f3e90-7b00-7000-8000-000000000968"),
            outbox_id=_uuid("018f3e90-7b00-7000-8000-000000000969"),
        )
        return RecordedPublicationCommandScenarioV2(
            sources=sources,
            publish=publish,
            duplicate_publish=duplicate_publish,
            rollback=rollback,
            unpublish=unpublish,
        )
    except Exception as error:
        if type(error).__module__.startswith("raos."):
            raise
        fail_publication_command()


def recorded_publication_command_fixture_document_v2(
    *,
    scenario: RecordedPublicationCommandScenarioV2,
    source_hashes: dict[str, str],
) -> dict[str, object]:
    if type(scenario) is not RecordedPublicationCommandScenarioV2:
        fail_publication_command()
    store = RecordedPublicationCommandStoreV2(
        environment=RuntimeEnvironment.CI,
        sources=scenario.sources,
    )
    service = PublicationCommandServiceV2(
        environment=RuntimeEnvironment.CI,
        store=store,
    )
    initial = store.snapshot()
    published = service.publish(scenario.publish)
    after_publish = store.snapshot()
    exact_replay = service.publish(scenario.publish)
    after_exact_replay = store.snapshot()
    semantic_replay = service.publish(scenario.duplicate_publish)
    after_semantic_replay = store.snapshot()
    rolled_back = service.rollback(scenario.rollback)
    after_rollback = store.snapshot()
    if (
        exact_replay.canonical_bytes() != published.canonical_bytes()
        or semantic_replay.canonical_bytes() != published.canonical_bytes()
        or after_exact_replay.snapshot_sha256 != after_publish.snapshot_sha256
        or after_semantic_replay.projection_records != after_publish.projection_records
        or after_semantic_replay.event_intents != after_publish.event_intents
        or after_semantic_replay.audit_intents != after_publish.audit_intents
        or after_semantic_replay.outbox_intents != after_publish.outbox_intents
    ):
        fail_publication_command()
    return {
        "authority": dict(_AUTHORITY),
        "commands": {
            "duplicate_publish": scenario.duplicate_publish.canonical_bytes().decode(
                "ascii"
            ),
            "publish": scenario.publish.canonical_bytes().decode("ascii"),
            "rollback": scenario.rollback.canonical_bytes().decode("ascii"),
            "unpublish": {
                "decision": "DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION",
                "executable": False,
            },
        },
        "external_gates": {
            "formal_tst_012": "NOT_EXECUTED",
            "formal_tst_013": "NOT_EXECUTED",
            "formal_tst_021": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "profile": PROFILE,
        "results": {
            "publish": published.canonical_bytes().decode("ascii"),
            "publish_event": parse_canonical_object(published.event_bytes),
            "rollback": rolled_back.canonical_bytes().decode("ascii"),
            "rollback_event": parse_canonical_object(rolled_back.event_bytes),
        },
        "schema_version": 2,
        "snapshots": [
            {
                "created_at": item.snapshot_request.created_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "snapshot_id": str(item.snapshot_id),
                "source_binding_sha256": item.source_binding_sha256.value,
            }
            for item in scenario.sources.snapshots
        ],
        "source_hashes": dict(sorted(source_hashes.items())),
        "states": {
            "after_exact_replay": _state(after_exact_replay),
            "after_publish": _state(after_publish),
            "after_rollback": _state(after_rollback),
            "after_semantic_replay": _state(after_semantic_replay),
            "initial": _state(initial),
        },
        "story_id": "ST-0905",
    }


def build_recorded_publication_command_fixture_bytes_v2(
    *,
    st0903_fixture: bytes,
    st0904_fixture: bytes,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> bytes:
    payloads = {
        "final_approval_fixture_sha256": final_approval_fixture,
        "policy_fixture_sha256": policy_fixture,
        "review_fixture_sha256": review_fixture,
        "seo_fixture_sha256": seo_fixture,
        "st0903_fixture_sha256": st0903_fixture,
        "st0904_fixture_sha256": st0904_fixture,
    }
    scenario = build_recorded_publication_command_scenario_v2(
        st0903_fixture=st0903_fixture,
        st0904_fixture=st0904_fixture,
        final_approval_fixture=final_approval_fixture,
        policy_fixture=policy_fixture,
        review_fixture=review_fixture,
        seo_fixture=seo_fixture,
    )
    document = recorded_publication_command_fixture_document_v2(
        scenario=scenario,
        source_hashes={key: _sha(value).value for key, value in payloads.items()},
    )
    return canonical_json_bytes(document) + b"\n"


def load_recorded_publication_command_fixture_v2(
    payload: bytes,
    *,
    st0903_fixture: bytes,
    st0904_fixture: bytes,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> RecordedPublicationCommandScenarioV2:
    if (
        type(payload) is not bytes
        or not payload.endswith(b"\n")
        or len(payload) > _MAX_FIXTURE_BYTES
    ):
        fail_publication_command()
    expected = build_recorded_publication_command_fixture_bytes_v2(
        st0903_fixture=st0903_fixture,
        st0904_fixture=st0904_fixture,
        final_approval_fixture=final_approval_fixture,
        policy_fixture=policy_fixture,
        review_fixture=review_fixture,
        seo_fixture=seo_fixture,
    )
    if payload != expected:
        fail_publication_command()
    return build_recorded_publication_command_scenario_v2(
        st0903_fixture=st0903_fixture,
        st0904_fixture=st0904_fixture,
        final_approval_fixture=final_approval_fixture,
        policy_fixture=policy_fixture,
        review_fixture=review_fixture,
        seo_fixture=seo_fixture,
    )


__all__ = (
    "RecordedPublicationCommandScenarioV2",
    "build_recorded_publication_command_fixture_bytes_v2",
    "build_recorded_publication_command_scenario_v2",
    "load_recorded_publication_command_fixture_v2",
    "recorded_publication_command_fixture_document_v2",
)
