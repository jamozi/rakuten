"""In-memory recorded ST-0502 raw page source for ST-0601 V2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import RawArchiveReceiptV2
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2,
    ArtifactRegistryRuntimeFailureCodeV2,
    fail_artifact_registry_runtime_v2,
)


def _copy_receipt(value: object) -> RawArchiveReceiptV2:
    if type(value) is not RawArchiveReceiptV2:
        fail_artifact_registry_runtime_v2()
    invalid = False
    copied: RawArchiveReceiptV2 | None = None
    try:
        copied = RawArchiveReceiptV2(
            receipt_id=value.receipt_id,
            artifact_sha256=value.artifact_sha256,
            byte_size=value.byte_size,
            artifact_version=value.artifact_version,
            logical_key=value.logical_key,
            request_fingerprint=value.request_fingerprint,
            page=value.page,
            observed_at=value.observed_at,
        )
    except Exception:
        invalid = True
    if invalid or copied is None:
        fail_artifact_registry_runtime_v2(
            ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
        )
    return copied


@dataclass(frozen=True, slots=True, repr=False)
class RecordedItemSearchRawFixtureV2:
    receipt: RawArchiveReceiptV2
    content: bytes

    def __post_init__(self) -> None:
        copied_receipt = _copy_receipt(self.receipt)
        if type(self.content) is not bytes:
            fail_artifact_registry_runtime_v2()
        copied_content = bytes(bytearray(self.content))
        if (
            len(copied_content) != copied_receipt.byte_size
            or hashlib.sha256(copied_content).hexdigest()
            != copied_receipt.artifact_sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )
        object.__setattr__(self, "receipt", copied_receipt)
        object.__setattr__(self, "content", copied_content)

    def __repr__(self) -> str:
        return "RecordedItemSearchRawFixtureV2(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded raw fixture cannot be serialized")


@final
class RecordedItemSearchRawArchiveSourceV2:
    """Exact receipt lookup; it has no network, provider, or retry surface."""

    __slots__ = ("_fixtures",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixtures: tuple[RecordedItemSearchRawFixtureV2, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixtures) is not tuple
            or not fixtures
            or len(fixtures) > 1024
            or any(
                type(value) is not RecordedItemSearchRawFixtureV2 for value in fixtures
            )
        ):
            fail_artifact_registry_runtime_v2()
        by_receipt: dict[object, RecordedItemSearchRawFixtureV2] = {}
        for fixture in fixtures:
            key = fixture.receipt.receipt_id
            if key in by_receipt:
                fail_artifact_registry_runtime_v2(
                    ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                )
            by_receipt[key] = fixture
        self._fixtures = by_receipt

    @property
    def external_action_count(self) -> int:
        return ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        exact = _copy_receipt(receipt)
        fixture = self._fixtures.get(exact.receipt_id)
        if fixture is None:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_UNAVAILABLE
            )
        if fixture.receipt != exact:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )
        content = bytes(bytearray(fixture.content))
        if (
            len(content) != exact.byte_size
            or hashlib.sha256(content).hexdigest() != exact.artifact_sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )
        return content

    def __repr__(self) -> str:
        return "RecordedItemSearchRawArchiveSourceV2(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded raw source cannot be serialized")


__all__ = [
    "RecordedItemSearchRawArchiveSourceV2",
    "RecordedItemSearchRawFixtureV2",
]
