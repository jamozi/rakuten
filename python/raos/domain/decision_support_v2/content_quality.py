"""Pure editorial quality and intent-overlap checks."""

from __future__ import annotations

from dataclasses import dataclass
import re


_FALSE_HANDS_ON = re.compile(
    r"(?:使ってみた|実測した|使用して分かった|使用してわかった|試用した|耐久テストした|実機で確認)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ContentPacket:
    disclosure: str
    thirty_second_conclusion: str
    unknowns: tuple[str, ...]
    official_source_urls: tuple[str, ...]
    fits: tuple[str, ...]
    non_fits: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    experience_claims: tuple[str, ...] = ()


def validate_content_packet(packet: ContentPacket) -> tuple[str, ...]:
    errors: list[str] = []
    required = (
        ("MISSING_DISCLOSURE", packet.disclosure),
        ("MISSING_30_SECOND_CONCLUSION", packet.thirty_second_conclusion),
        ("MISSING_UNKNOWNS", packet.unknowns),
        ("MISSING_OFFICIAL_SOURCES", packet.official_source_urls),
        ("MISSING_FIT", packet.fits),
        ("MISSING_NON_FIT", packet.non_fits),
        ("MISSING_TRADEOFF", packet.tradeoffs),
    )
    errors.extend(code for code, value in required if not value)
    if any(not url.startswith("https://") for url in packet.official_source_urls):
        errors.append("NON_HTTPS_SOURCE")
    if packet.experience_claims:
        errors.append("UNVERIFIED_EXPERIENCE_CLAIM")
    visible_text = "\n".join(
        (
            packet.disclosure,
            packet.thirty_second_conclusion,
            *packet.unknowns,
            *packet.fits,
            *packet.non_fits,
            *packet.tradeoffs,
        )
    )
    if _FALSE_HANDS_ON.search(visible_text):
        errors.append("FALSE_HANDS_ON_LANGUAGE")
    return tuple(errors)


def intent_overlap(left: str, right: str) -> float:
    def tokens(value: str) -> set[str]:
        normalized = value.casefold()
        latin = set(re.findall(r"[a-z0-9]+", normalized))
        japanese_runs = re.findall(r"[\u3040-\u30ff\u3400-\u9fff]+", normalized)
        grams: set[str] = set()
        for run in japanese_runs:
            if len(run) < 3:
                grams.add(f"ja:{run}")
                continue
            grams.update(
                f"ja:{run[index : index + 3]}" for index in range(len(run) - 2)
            )
        return latin | grams

    left_tokens, right_tokens = tokens(left), tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def difference_route_allowed(
    *, difference_query: str, comparison_query: str, threshold: float = 0.72
) -> bool:
    return intent_overlap(difference_query, comparison_query) < threshold


def correction_rate(corrected_material_facts: int, reviewed_material_facts: int) -> str:
    if corrected_material_facts < 0 or reviewed_material_facts <= 0:
        raise ValueError("invalid correction-rate inputs")
    if corrected_material_facts > reviewed_material_facts:
        raise ValueError("corrections cannot exceed reviewed facts")
    return f"{corrected_material_facts}/{reviewed_material_facts}"


__all__ = [
    "ContentPacket",
    "correction_rate",
    "difference_route_allowed",
    "intent_overlap",
    "validate_content_packet",
]
