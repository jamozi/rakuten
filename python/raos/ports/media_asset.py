"""Inward recorded-only media validation port for ST-0808."""

from __future__ import annotations

from typing import Protocol

from raos.domain.editorial.media_asset import (
    MediaValidationCommand,
    RecordedMediaValidationObservation,
)


class RecordedMediaAssetValidator(Protocol):
    """One exact synthetic exchange; not storage, rendering, or publication."""

    def validate(
        self, command: MediaValidationCommand
    ) -> RecordedMediaValidationObservation: ...
