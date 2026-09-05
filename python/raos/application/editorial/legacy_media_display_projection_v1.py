"""Closed render-only removal of two captured legacy image layouts.

No stored content is edited. No image is fabricated or promoted to verified.
Byte ranges, fragment hashes and complete before/after hashes are all required.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, NoReturn, cast

from raos.application.editorial.verified_incremental_v1 import _Markup  # pyright: ignore[reportPrivateUsage]

SCHEMA = "RAOS_LEGACY_MEDIA_DISPLAY_PROJECTION_V1"
CONTRACT_PATH = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/"
    "assets/legacy-media-display-projection.v1.json"
)
ROOT = Path(__file__).resolve().parents[4]
BROKEN_PATH = "/wp-content/themes/kurashinoshirube-child/assets/images/article-portable-power-guide.png"
PROFILES = frozenset({"production", "local-fixture", "local-stored"})
TARGETS = {
    "st1704-portable-power-station-guide": ("portable-power-station-guide", 28, 8, 2),
    "st1704-anker-solix-c300-c800-c1000-differences": (
        "anker-solix-c300-c800-c1000-differences",
        29,
        8,
        4,
    ),
}
KINDS = frozenset({"decorative-image", "neutral-media"})
HASH = re.compile(r"[a-f0-9]{64}\Z")


class LegacyMediaProjectionFailure(ValueError):
    pass


def reject(reason: str) -> NoReturn:
    raise LegacyMediaProjectionFailure("LEGACY_MEDIA_PROJECTION_" + reason)


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _hash(value: object) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        reject("CONTRACT_INVALID")
    return cast(dict[str, Any], value)


def validate_contract(contract: Mapping[str, Any]) -> None:
    if (
        set(contract) != {"schema", "version", "broken_image_path", "articles"}
        or contract["schema"] != SCHEMA
        or contract["version"] != "1.0.0"
        or contract["broken_image_path"] != BROKEN_PATH
    ):
        reject("CONTRACT_INVALID")
    articles = _object(contract["articles"])
    if set(articles) != set(TARGETS):
        reject("CONTRACT_INVALID")
    for article_id, expected in TARGETS.items():
        row = _object(articles[article_id])
        slug, post_id, decorations, neutral = expected
        if (
            set(row) != {"slug", "post_id", "baseline_document_sha256", "profiles"}
            or row["slug"] != slug
            or type(row["post_id"]) is not int
            or row["post_id"] != post_id
            or not _hash(row["baseline_document_sha256"])
        ):
            reject("CONTRACT_INVALID")
        profiles = _object(row["profiles"])
        if frozenset(profiles) != PROFILES:
            reject("CONTRACT_INVALID")
        for raw_profile in profiles.values():
            profile = _object(raw_profile)
            if (
                set(profile) != {"input_sha256", "output_sha256", "removals"}
                or not _hash(profile["input_sha256"])
                or not _hash(profile["output_sha256"])
                or profile["input_sha256"] == profile["output_sha256"]
                or not isinstance(profile["removals"], list)
            ):
                reject("CONTRACT_INVALID")
            removals = cast(list[Any], profile.get("removals"))
            if len(removals) != decorations + neutral:
                reject("CONTRACT_INVALID")
            previous_end = 0
            kinds: Counter[str] = Counter()
            for raw_removal in removals:
                removal = _object(raw_removal)
                if (
                    set(removal) != {"offset", "length", "sha256", "kind"}
                    or type(removal["offset"]) is not int
                    or type(removal["length"]) is not int
                    or not previous_end <= removal["offset"] <= 1048576
                    or not 1 <= removal["length"] <= 4096
                    or removal["offset"] + removal["length"] > 1048576
                    or not _hash(removal["sha256"])
                    or removal["kind"] not in KINDS
                ):
                    reject("CONTRACT_INVALID")
                previous_end = removal["offset"] + removal["length"]
                kinds[removal["kind"]] += 1
            if kinds != {"decorative-image": decorations, "neutral-media": neutral}:
                reject("CONTRACT_INVALID")


def load_contract() -> tuple[dict[str, Any], str]:
    raw = (ROOT / CONTRACT_PATH).read_bytes()
    if not 1 <= len(raw) <= 65536:
        reject("CONTRACT_INVALID")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                reject("CONTRACT_INVALID")
            value[key] = item
        return value

    contract = json.loads(raw, object_pairs_hook=unique)
    validate_contract(contract)
    return contract, digest(raw)


def validate_fragment(raw: bytes, kind: str) -> None:
    fragment = raw.decode("utf-8", errors="strict")
    parser = _Markup(fragment)
    parser.feed(fragment)
    parser.close()
    if parser.stack:
        reject("FRAGMENT_INVALID")
    elements = parser.elements
    if kind == "decorative-image":
        if len(elements) != 1 or elements[0].tag != "img":
            reject("FRAGMENT_INVALID")
        expected = {
            "class": "raos-comparison__product-image",
            "src": BROKEN_PATH,
            "alt": "",
            "width": "64",
            "height": "64",
            "loading": "lazy",
        }
        if elements[0].attrs != expected:
            reject("FRAGMENT_INVALID")
    elif kind == "neutral-media":
        if (
            len(elements) != 2
            or elements[0].tag != "div"
            or elements[1].tag != "img"
            or elements[0].attrs != {"class": "raos-product-card__media"}
            or elements[0].start != 0
            or elements[0].end != len(fragment)
            or elements[1].start != elements[0].opening_end
            or fragment[elements[1].end :] != "</div>"
        ):
            reject("FRAGMENT_INVALID")
        attrs = elements[1].attrs
        if (
            set(attrs)
            != {
                "src",
                "alt",
                "width",
                "height",
                "loading",
                "data-raos-product-image-id",
                "data-raos-product-image-state",
            }
            or attrs["src"] != BROKEN_PATH
            or attrs["width"] != "128"
            or attrs["height"] != "128"
            or attrs["loading"] != "lazy"
            or attrs["data-raos-product-image-state"] != "neutral"
            or not isinstance(attrs["data-raos-product-image-id"], str)
            or re.fullmatch(r"PRD-[A-Z0-9-]+", attrs["data-raos-product-image-id"])
            is None
            or not isinstance(attrs["alt"], str)
            or not attrs["alt"].endswith(
                "を比較検討するための中立イメージ。商品写真ではありません"
            )
        ):
            reject("FRAGMENT_INVALID")
    else:
        reject("FRAGMENT_INVALID")


@dataclass(frozen=True)
class DisplayProjection:
    markup: str
    proof: Mapping[str, object]


def project_legacy_media(
    markup: str,
    article_id: str,
    *,
    profile: str | None = None,
    contract: Mapping[str, Any] | None = None,
    contract_sha256: str | None = None,
) -> DisplayProjection:
    """Apply only an exact captured input; changed legacy input fails closed."""
    if contract is None:
        contract, contract_sha256 = load_contract()
    else:
        validate_contract(contract)
    if not _hash(contract_sha256) or (profile is not None and profile not in PROFILES):
        reject("CONTRACT_INVALID")
    raw = markup.encode("utf-8")
    input_hash = digest(raw)
    proof: dict[str, object] = {
        "state": "NOT_APPLICABLE",
        "contract_sha256": contract_sha256,
        "input_sha256": input_hash,
        "output_sha256": input_hash,
        "profile": None,
        "removed_decoration_count": 0,
        "removed_neutral_media_count": 0,
    }
    if article_id not in TARGETS:
        return DisplayProjection(markup, proof)
    if BROKEN_PATH not in markup and not re.search(
        r'data-raos-product-image-state\s*=\s*["\']neutral["\']', markup
    ):
        return DisplayProjection(markup, proof)
    row = contract["articles"][article_id]
    matches = [
        name
        for name, candidate in row["profiles"].items()
        if (profile is None or profile == name)
        and candidate["input_sha256"] == input_hash
    ]
    if not matches:
        reject("INPUT_MISMATCH")
    # Identical production/local-fixture inputs are possible when no remote
    # product image needs replay; an explicit caller profile remains binding.
    selected_profile = matches[0]
    selected = row["profiles"][selected_profile]
    for removal in selected["removals"]:
        fragment = raw[removal["offset"] : removal["offset"] + removal["length"]]
        if digest(fragment) != removal["sha256"]:
            reject("FRAGMENT_MISMATCH")
        validate_fragment(fragment, removal["kind"])
    output = raw
    for removal in reversed(selected["removals"]):
        offset = removal["offset"]
        output = output[:offset] + output[offset + removal["length"] :]
    if digest(output) != selected["output_sha256"]:
        reject("OUTPUT_MISMATCH")
    proof.update(
        state="APPLIED",
        profile=selected_profile,
        output_sha256=digest(output),
        removed_decoration_count=TARGETS[article_id][2],
        removed_neutral_media_count=TARGETS[article_id][3],
    )
    return DisplayProjection(output.decode("utf-8"), proof)
