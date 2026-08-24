"""Recorded-synthetic adapter for the ST-0904 public projection candidate.

The adapter rebuilds the exact committed ST-0903 V2 fixture, then exposes only
an in-memory source/exchange seam.  It owns no network, database, job, event,
route activation, public serving, CMS, publication, or release capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final

from raos.adapters.recorded_publication_snapshot_v2 import (
    RecordedPublicationSnapshotStep,
    load_recorded_publication_snapshot_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.public_projection_v2 import (
    PROFILE,
    PublicProjectionFailure,
    PublicProjectionFailureCode,
    PublicProjectionInputV2,
    PublicProjectionRequestV2,
    PublicProjectionResultV2,
    build_public_projection_v2,
    fail_public_projection,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    canonical_json_bytes,
    parse_canonical_object,
)
from raos.domain.shared.persistence import Sha256Digest


_MAX_FIXTURE_BYTES: Final = 8 * 1024 * 1024
_MAX_STEPS: Final = 128
_SOURCE_KEYS: Final = frozenset(
    {
        "final_approval_fixture_sha256",
        "policy_fixture_sha256",
        "review_fixture_sha256",
        "seo_fixture_sha256",
        "st0903_fixture_sha256",
    }
)
_AUTHORITY: Final[dict[str, object]] = {
    "browser": "NOT_EXECUTED",
    "credential": False,
    "database_write": False,
    "event_emit": False,
    "external_write": False,
    "formal_tst_011": "NOT_EXECUTED",
    "formal_tst_021": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "network": False,
    "persistence": False,
    "production": "NOT_EXECUTED",
    "production_authorized": False,
    "public_projection_authorized": False,
    "public_read_served": False,
    "publication": "NOT_EXECUTED",
    "publication_authorized": False,
    "release": "NOT_EXECUTED",
    "release_authorized": False,
    "route_activated": False,
    "staging": "NOT_EXECUTED",
}


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0904-adapter>)"

    def __str__(self) -> str:
        return "<redacted-st0904-adapter>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded public projection serialization is forbidden")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, keys: frozenset[str] | None = None) -> Mapping[str, object]:
    if type(value) is not dict:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    result = cast(dict[str, object], value)
    if keys is not None and frozenset(result) != keys:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    return result


def _sha_text(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    return value


def _same_request(left: object, right: PublicProjectionRequestV2) -> bool:
    try:
        return (
            type(left) is PublicProjectionRequestV2
            and left.canonical_bytes() == right.canonical_bytes()
        )
    except Exception:
        return False


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedPublicProjectionStep(_Redacted):
    request: PublicProjectionRequestV2
    source: PublicProjectionInputV2
    result: PublicProjectionResultV2 = field(init=False)
    request_bytes: bytes = field(init=False)
    result_bytes: bytes = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not PublicProjectionRequestV2
            or type(self.source) is not PublicProjectionInputV2
        ):
            fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
        self.request.require_valid()
        self.source.require_valid()
        result = build_public_projection_v2(request=self.request, source=self.source)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "request_bytes", self.request.canonical_bytes())
        object.__setattr__(self, "result_bytes", result.canonical_bytes())

    def require_valid(self) -> None:
        rebuilt = RecordedPublicProjectionStep(
            request=self.request,
            source=self.source,
        )
        if (
            rebuilt.request_bytes != self.request_bytes
            or rebuilt.result_bytes != self.result_bytes
            or rebuilt.result.projection_bytes != self.result.projection_bytes
        ):
            fail_public_projection(PublicProjectionFailureCode.OUTCOME_MISMATCH)


def build_recorded_public_projection_step(
    snapshot_step: RecordedPublicationSnapshotStep,
    *,
    source_fixture_sha256: object,
) -> RecordedPublicProjectionStep:
    """Build one exact local projection step from the ST-0903 V2 step."""

    if type(snapshot_step) is not RecordedPublicationSnapshotStep:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    try:
        snapshot_step.require_valid()
        digest = Sha256Digest(_sha_text(source_fixture_sha256))
        source = PublicProjectionInputV2(
            snapshot_request=snapshot_step.request,
            snapshot_result=snapshot_step.result,
            source_fixture_sha256=digest,
        )
        request = PublicProjectionRequestV2(
            expected_source_binding_sha256=source.binding_sha256,
            idempotency_key="st0904-v2-public-projection-0001",
            projection_generation=1,
        )
        return RecordedPublicProjectionStep(request=request, source=source)
    except PublicProjectionFailure:
        raise
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)


def recorded_public_projection_fixture_document(
    *,
    sources: object,
    step: RecordedPublicProjectionStep,
) -> dict[str, object]:
    """Return the exact closed owner-generated local fixture document."""

    if type(step) is not RecordedPublicProjectionStep:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    step.require_valid()
    source_values = _mapping(sources, _SOURCE_KEYS)
    for value in source_values.values():
        _sha_text(value)
    projection = step.result.projection()
    return {
        "authority": dict(_AUTHORITY),
        "compatibility": {
            "badges_shape": "NO_PRODUCT_ROWS_SOURCE_UNAVAILABLE",
            "destination_host": "NO_OFFER_ROWS_SOURCE_UNAVAILABLE",
            "heading_level": "NULL_COMMON_SUBSET_NO_HEADING_ROWS",
            "legacy_publication_snapshot_schema": ("RECONCILIATION_REQUIRED_PRESERVED"),
            "projection_generation": "ONE_COMMON_VALID_SUBSET_LOCAL_ONLY",
        },
        "input": {
            "request": step.request.canonical_bytes().decode("ascii"),
            "snapshot_artifact_sha256": (
                step.source.snapshot_result.snapshot_artifact_sha256.value
            ),
            "snapshot_request_sha256": (
                step.source.snapshot_request.request_sha256.value
            ),
            "snapshot_result_sha256": (step.source.snapshot_result.result_sha256.value),
            "snapshot_sha256": step.source.snapshot_result.snapshot_sha256.value,
            "source_binding_sha256": step.source.binding_sha256.value,
        },
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "output": {
            "projection": projection,
            "result": step.result.canonical_bytes().decode("ascii"),
        },
        "profile": PROFILE,
        "schema_version": 2,
        "sources": dict(source_values),
        "story_id": "ST-0904",
    }


def load_recorded_public_projection_fixture(
    payload: bytes,
    *,
    st0903_fixture: bytes,
    final_approval_fixture: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
    seo_fixture: bytes,
) -> RecordedPublicProjectionStep:
    """Load the closed fixture and independently rebuild both Story outputs."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_FIXTURE_BYTES
        or not payload.endswith(b"\n")
    ):
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    body = payload[:-1]
    try:
        document = parse_canonical_object(body)
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    if (
        canonical_json_bytes(document) != body
        or frozenset(document)
        != frozenset(
            {
                "authority",
                "compatibility",
                "input",
                "local_status",
                "output",
                "profile",
                "schema_version",
                "sources",
                "story_id",
            }
        )
        or document.get("schema_version") != 2
        or document.get("story_id") != "ST-0904"
        or document.get("profile") != PROFILE
        or document.get("local_status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document.get("authority") != _AUTHORITY
    ):
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    sources = _mapping(document.get("sources"), _SOURCE_KEYS)
    exact_sources = {
        "final_approval_fixture_sha256": _sha256(final_approval_fixture),
        "policy_fixture_sha256": _sha256(policy_fixture),
        "review_fixture_sha256": _sha256(review_fixture),
        "seo_fixture_sha256": _sha256(seo_fixture),
        "st0903_fixture_sha256": _sha256(st0903_fixture),
    }
    if dict(sources) != exact_sources:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    try:
        snapshot_step = load_recorded_publication_snapshot_fixture(
            st0903_fixture,
            final_approval_fixture=final_approval_fixture,
            policy_fixture=policy_fixture,
            review_fixture=review_fixture,
            seo_fixture=seo_fixture,
        )
        step = build_recorded_public_projection_step(
            snapshot_step,
            source_fixture_sha256=exact_sources["st0903_fixture_sha256"],
        )
    except PublicProjectionFailure:
        raise
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    expected = recorded_public_projection_fixture_document(
        sources=exact_sources,
        step=step,
    )
    if canonical_json_bytes(expected) != body:
        fail_public_projection(PublicProjectionFailureCode.FIXTURE_INVALID)
    return step


@final
class RecordedPublicProjectionAdapter(_Redacted):
    """Thread-safe scripted source and idempotent local pure exchange."""

    __slots__ = ("_cursor", "_lock", "_replays", "_steps")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        steps: tuple[RecordedPublicProjectionStep, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(steps) is not tuple
            or not 1 <= len(steps) <= _MAX_STEPS
            or any(type(step) is not RecordedPublicProjectionStep for step in steps)
        ):
            fail_public_projection(
                PublicProjectionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        identities: set[str] = set()
        for step in steps:
            step.require_valid()
            identity = step.request.idempotency_key
            if identity in identities:
                fail_public_projection(PublicProjectionFailureCode.IDEMPOTENCY_CONFLICT)
            identities.add(identity)
        self._steps = steps
        self._cursor = 0
        self._replays: dict[
            str,
            tuple[bytes, PublicProjectionInputV2, PublicProjectionResultV2],
        ] = {}
        self._lock = RLock()

    def load(self, request: PublicProjectionRequestV2) -> PublicProjectionInputV2:
        if type(request) is not PublicProjectionRequestV2:
            fail_public_projection()
        request.require_valid()
        identity = request.idempotency_key
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, source, _result = replay
                if request.canonical_bytes() != request_bytes:
                    fail_public_projection(
                        PublicProjectionFailureCode.IDEMPOTENCY_CONFLICT
                    )
                source.require_valid()
                return source
            if self._cursor >= len(self._steps):
                fail_public_projection(
                    PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if identity == step.request.idempotency_key and not _same_request(
                request, step.request
            ):
                fail_public_projection(PublicProjectionFailureCode.IDEMPOTENCY_CONFLICT)
            if not _same_request(request, step.request):
                fail_public_projection(
                    PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            return step.source

    def exchange(
        self,
        request: PublicProjectionRequestV2,
        source: PublicProjectionInputV2,
    ) -> PublicProjectionResultV2:
        if (
            type(request) is not PublicProjectionRequestV2
            or type(source) is not PublicProjectionInputV2
        ):
            fail_public_projection()
        identity = request.idempotency_key
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, retained_source, result = replay
                if (
                    request.canonical_bytes() != request_bytes
                    or retained_source.binding_sha256 != source.binding_sha256
                ):
                    fail_public_projection(
                        PublicProjectionFailureCode.IDEMPOTENCY_CONFLICT
                    )
                return result
            if self._cursor >= len(self._steps):
                fail_public_projection(
                    PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if (
                not _same_request(request, step.request)
                or source.binding_sha256 != step.source.binding_sha256
            ):
                fail_public_projection(
                    PublicProjectionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            self._replays[identity] = (step.request_bytes, step.source, step.result)
            self._cursor += 1
            return step.result

    @property
    def consumed_steps(self) -> int:
        with self._lock:
            return self._cursor


__all__ = (
    "RecordedPublicProjectionAdapter",
    "RecordedPublicProjectionStep",
    "build_recorded_public_projection_step",
    "load_recorded_public_projection_fixture",
    "recorded_public_projection_fixture_document",
)
