"""Recorded-only media provenance and fail-closed rendering policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re

from raos.domain.decision_support_v2.models import (
    MediaState,
    OfferObservation,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_ID = re.compile(r"SRC-[A-Z0-9][A-Z0-9-]{0,127}\Z")
_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9-]+\Z")
_OFFER_ID = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,127}\Z")
_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_OPAQUE_IMAGE_REF = re.compile(r"OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class MediaBinding:
    """Sealed provenance for one recorded offer image.

    ``binding_sha256`` covers every semantic field.  The image itself is not
    fetched in Phase 2; its recorded content hash is bound to the opaque image
    reference so later mutation or substitution is detectable.
    """

    source_id: str
    offer_id: str
    product_id: str
    item_code: str
    image_ref: str
    content_sha256: str
    alt_text: str
    checked_at: datetime
    binding_sha256: str

    def __post_init__(self) -> None:
        if not _SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("invalid media source ID")
        if not _OFFER_ID.fullmatch(self.offer_id):
            raise ValueError("invalid media offer ID")
        if not _PRODUCT_ID.fullmatch(self.product_id):
            raise ValueError("invalid media product ID")
        lowered_item_code = self.item_code.casefold()
        if not _OPAQUE_REF.fullmatch(self.item_code) or lowered_item_code.startswith(
            ("javascript:", "data:")
        ):
            raise ValueError("invalid media item code")
        if not _OPAQUE_IMAGE_REF.fullmatch(self.image_ref):
            raise ValueError("invalid media image reference")
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("invalid media content hash")
        if not _SHA256.fullmatch(self.binding_sha256):
            raise ValueError("invalid media binding hash")
        if (
            not self.alt_text.strip()
            or self.alt_text != self.alt_text.strip()
            or any(character in self.alt_text for character in "<>")
            or "http://" in self.alt_text.casefold()
            or "https://" in self.alt_text.casefold()
        ):
            raise ValueError("invalid media alternative text")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("media checked_at must be timezone-aware")

    def semantic_payload(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "offer_id": self.offer_id,
            "product_id": self.product_id,
            "item_code": self.item_code,
            "image_ref": self.image_ref,
            "content_sha256": self.content_sha256,
            "alt_text": self.alt_text,
            "checked_at": self.checked_at.isoformat(),
        }

    def verify(self) -> bool:
        return self.binding_sha256 == media_binding_digest(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class MediaResolution:
    state: MediaState
    render_kind: str
    render_ref: str | None
    alt_text: str | None
    reason_codes: tuple[str, ...]


def media_binding_digest(payload: dict[str, str]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_offer_media(
    offer: OfferObservation,
    *,
    declared_state: MediaState,
    binding: MediaBinding | None,
) -> MediaResolution:
    """Resolve a recorded offer image without network access or optimistic fallback."""

    if declared_state is MediaState.NO_IMAGE_INTENTIONAL:
        if offer.image_ref is None and binding is None:
            return MediaResolution(
                MediaState.NO_IMAGE_INTENTIONAL,
                "NEUTRAL_PLACEHOLDER",
                None,
                None,
                ("NO_IMAGE_INTENTIONAL",),
            )
        return _blocked("NO_IMAGE_DECLARATION_CONFLICT")
    if declared_state is not MediaState.ELIGIBLE:
        return _blocked("MEDIA_DECLARED_BLOCKED")
    if offer.image_ref is None or binding is None:
        return _blocked("MEDIA_BINDING_MISSING")
    if not binding.verify():
        return _blocked("MEDIA_BINDING_MODIFIED")
    if (
        binding.offer_id != offer.offer_id
        or binding.product_id != offer.product_id
        or binding.item_code != offer.item_code
        or binding.image_ref != offer.image_ref
        or binding.checked_at != offer.observed_at
    ):
        return _blocked("MEDIA_BINDING_MISMATCH")
    return MediaResolution(
        MediaState.ELIGIBLE,
        "RECORDED_IMAGE",
        binding.image_ref,
        binding.alt_text,
        ("MEDIA_PROVENANCE_VERIFIED",),
    )


def _blocked(reason: str) -> MediaResolution:
    return MediaResolution(MediaState.BLOCKED, "BLOCKED", None, None, (reason,))


__all__ = [
    "MediaBinding",
    "MediaResolution",
    "media_binding_digest",
    "resolve_offer_media",
]
