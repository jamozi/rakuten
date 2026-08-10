"""Immutable ordered synthetic media-validation fixture adapter for ST-0808."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.media_asset import (
    MediaAssetFailureCode,
    MediaAssetMode,
    MediaValidationCommand,
    RecordedMediaValidationObservation,
    fail_media_asset,
)


_MAX_SCRIPT_CAPACITY = 100_000


@dataclass(frozen=True, slots=True, repr=False)
class RecordedMediaAssetStep:
    command: MediaValidationCommand
    observation: RecordedMediaValidationObservation

    def __post_init__(self) -> None:
        if (
            type(self.command) is not MediaValidationCommand
            or type(self.observation) is not RecordedMediaValidationObservation
            or self.observation.candidate_fingerprint
            != self.command.request.candidate.fingerprint
            or self.observation.rights_disposition
            is not self.command.rights_disposition
        ):
            fail_media_asset()

    def __repr__(self) -> str:
        return "RecordedMediaAssetStep(<redacted-media-asset>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded media step serialization is not supported")


@final
class RecordedMediaAssetValidator:
    """Consume an exact ordered fixture without content, storage, or I/O."""

    __slots__ = ("_index", "_lock", "_scripts")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: MediaAssetMode,
        script_capacity: int,
        scripts: tuple[RecordedMediaAssetStep, ...],
    ) -> None:
        if (
            environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not MediaAssetMode.RECORDED_TEST_ONLY
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) is not RecordedMediaAssetStep for step in scripts)
            or any(
                left.command == right.command
                for index, left in enumerate(scripts)
                for right in scripts[index + 1 :]
            )
        ):
            fail_media_asset()
        self._scripts = scripts
        self._index = 0
        self._lock = RLock()

    def __repr__(self) -> str:
        return "RecordedMediaAssetValidator(<redacted-media-asset>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded media validator serialization is not supported")

    def validate(
        self, command: MediaValidationCommand
    ) -> RecordedMediaValidationObservation:
        with self._lock:
            if self._index >= len(self._scripts):
                fail_media_asset(MediaAssetFailureCode.LOCAL_VALIDATION_UNAVAILABLE)
            step = self._scripts[self._index]
            if type(command) is not MediaValidationCommand or command != step.command:
                fail_media_asset(MediaAssetFailureCode.LOCAL_VALIDATION_UNAVAILABLE)
            self._index += 1
            return step.observation


__all__ = ["RecordedMediaAssetStep", "RecordedMediaAssetValidator"]
