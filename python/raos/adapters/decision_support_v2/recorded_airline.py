"""Read normalized airline rule fixtures without retaining page bodies."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import cast

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.strict_json import loads_strict_json
from raos.domain.decision_support_v2.models import (
    AirlineRuleSet,
    AirlineRuleVariant,
    DimensionEdges,
    DimensionOrientation,
    FreshnessState,
    ItemAllowance,
    ItemPlacement,
    JourneySegment,
    JourneyScope,
    RuleApplicability,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    untyped = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in untyped):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return cast(Mapping[str, object], untyped)


def _exact_mapping(value: object, fields: set[str]) -> Mapping[str, object]:
    result = _mapping(value)
    if set(result) != fields:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return result


def _object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return cast(list[object], value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return value


def _optional_boolean(value: object) -> bool | None:
    if value is None:
        return None
    return _boolean(value)


def _strings(value: object) -> tuple[str, ...]:
    return tuple(_string(item) for item in _object_list(value))


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return Decimal(value)


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
    if parsed.tzinfo is None:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return parsed


def _edges(value: object) -> DimensionEdges:
    edges = _object_list(value)
    if len(edges) != 3:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    if not all(
        isinstance(item, (str, int)) and not isinstance(item, bool) for item in edges
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    first = cast(str | int, edges[0])
    second = cast(str | int, edges[1])
    third = cast(str | int, edges[2])
    return DimensionEdges(Decimal(first), Decimal(second), Decimal(third))


_CAPTURE_FIELDS = {"source_id", "status", "body_sha256"}
_RULE_FIELDS = {
    "schema_version",
    "rule_set_id",
    "carrier",
    "journey_scope",
    "effective_from",
    "observed_applicable_from",
    "applicability_basis",
    "effective_interval_semantics",
    "effective_to",
    "source_id",
    "checked_at",
    "source_next_review_at",
    "source_content_sha256",
    "recheck_required_before_use",
    "variants",
}
_REQUIRED_VARIANT_FIELDS = {
    "variant_id",
    "applicability",
    "bag_count",
    "personal_item_count",
    "dimension_edges_cm",
    "sum_edges_cm",
    "total_weight_kg",
    "orientation",
    "includes_wheels_and_handles",
    "notes",
    "resolution_requirements",
}
_OPTIONAL_VARIANT_FIELDS = {"max_per_item_weight_kg", "item_allowances"}
_APPLICABILITY_FIELDS = {
    "operator",
    "min_seat_count",
    "max_seat_count",
    "fare_classes",
    "required_options",
    "forbidden_options",
}
_ALLOWANCE_FIELDS = {
    "slot_id",
    "placement",
    "dimension_edges_cm",
    "orientation",
    "includes_wheels_and_handles",
    "max_weight_kg",
    "fit_requirement",
}


def _parse_capture(value: object) -> tuple[str, FreshnessState, str]:
    capture = _exact_mapping(value, _CAPTURE_FIELDS)
    source_id = _string(capture["source_id"])
    status = FreshnessState(_string(capture["status"]))
    body_sha256 = _string(capture["body_sha256"])
    if not _SHA256.fullmatch(body_sha256):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return source_id, status, body_sha256


def _parse_allowance(value: object) -> ItemAllowance:
    allowance = _exact_mapping(value, _ALLOWANCE_FIELDS)
    dimensions = allowance["dimension_edges_cm"]
    return ItemAllowance(
        slot_id=_string(allowance["slot_id"]),
        placement=ItemPlacement(_string(allowance["placement"])),
        dimension_edges_cm=_edges(dimensions) if dimensions is not None else None,
        orientation=DimensionOrientation(_string(allowance["orientation"])),
        includes_wheels_and_handles=_optional_boolean(
            allowance["includes_wheels_and_handles"]
        ),
        max_weight_kg=_optional_decimal(allowance["max_weight_kg"]),
        fit_requirement=_optional_string(allowance["fit_requirement"]),
    )


def _parse_variant(value: object, *, carrier: str) -> AirlineRuleVariant:
    variant = _mapping(value)
    if not _REQUIRED_VARIANT_FIELDS.issubset(variant) or not set(variant).issubset(
        _REQUIRED_VARIANT_FIELDS | _OPTIONAL_VARIANT_FIELDS
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    applicability = _mapping(variant["applicability"])
    if "operator" not in applicability or not set(applicability).issubset(
        _APPLICABILITY_FIELDS
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    allowances = tuple(
        _parse_allowance(item)
        for item in _object_list(variant.get("item_allowances", []))
    )
    return AirlineRuleVariant(
        variant_id=_string(variant["variant_id"]),
        applicability=RuleApplicability(
            carrier=carrier,
            operator=_optional_string(applicability.get("operator")),
            min_seat_count=_optional_integer(applicability.get("min_seat_count")),
            max_seat_count=_optional_integer(applicability.get("max_seat_count")),
            fare_classes=_strings(applicability.get("fare_classes", [])),
            required_options=_strings(applicability.get("required_options", [])),
            forbidden_options=_strings(applicability.get("forbidden_options", [])),
        ),
        carry_on_bag_count=_integer(variant["bag_count"]),
        personal_item_count=_integer(variant["personal_item_count"]),
        dimension_edges_cm=_edges(variant["dimension_edges_cm"]),
        sum_edges_cm=_optional_decimal(variant["sum_edges_cm"]),
        total_weight_kg=_optional_decimal(variant["total_weight_kg"]),
        max_per_item_weight_kg=_optional_decimal(variant.get("max_per_item_weight_kg")),
        orientation=DimensionOrientation(_string(variant["orientation"])),
        appendages_included=_boolean(variant["includes_wheels_and_handles"]),
        item_allowances=allowances,
        notes=_strings(variant["notes"]),
        resolution_requirements=_strings(variant["resolution_requirements"]),
    )


def _parse_rule_set(
    value: object,
    *,
    captures: Mapping[str, tuple[FreshnessState, str]],
    capture_window_ended_at: datetime,
) -> AirlineRuleSet:
    record = _exact_mapping(value, _RULE_FIELDS)
    if record["schema_version"] != "1.0.0":
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    checked_at = _datetime(record["checked_at"])
    if checked_at != capture_window_ended_at:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    source_id = _string(record["source_id"])
    source_content_sha256 = _string(record["source_content_sha256"])
    capture = captures.get(source_id)
    if capture is None or capture[1] != source_content_sha256:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    carrier = _string(record["carrier"])
    variants = tuple(
        _parse_variant(item, carrier=carrier)
        for item in _object_list(record["variants"])
    )
    effective_from = record["effective_from"]
    effective_to = record["effective_to"]
    return AirlineRuleSet(
        rule_set_id=_string(record["rule_set_id"]),
        carrier=carrier,
        journey_scope=JourneyScope(_string(record["journey_scope"])),
        effective_from=(
            _datetime(effective_from) if effective_from is not None else None
        ),
        observed_applicable_from=_datetime(record["observed_applicable_from"]),
        applicability_basis=_string(record["applicability_basis"]),
        effective_interval_semantics=_string(record["effective_interval_semantics"]),
        effective_to=_datetime(effective_to) if effective_to is not None else None,
        variants=variants,
        source_id=source_id,
        checked_at=checked_at,
        source_next_review_at=_datetime(record["source_next_review_at"]),
        source_content_sha256=source_content_sha256,
        recheck_required_before_use=_boolean(record["recheck_required_before_use"]),
        source_status=capture[0],
    )


def load_rule_fixture(path: Path) -> tuple[AirlineRuleSet, ...]:
    try:
        payload_object: object = loads_strict_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
    payload = _mapping(payload_object)
    if payload.get("schema") != "RAOS_V2_RECORDED_AIRLINE_RULES_V1":
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    expected_payload = {
        "schema",
        "version",
        "capture_mode",
        "capture_status",
        "capture_window_ended_at",
        "capture_provenance",
        "external_write",
        "source_captures",
        "rule_sets",
    }
    if (
        set(payload) != expected_payload
        or payload["version"] != "2.0.0"
        or payload["capture_mode"] != "PUBLIC_READ_ONLY_NORMALIZED_NO_BODY"
        or payload["capture_status"] != "CAPTURED_PUBLIC_READ_ONLY"
        or payload["capture_provenance"]
        != "ALLOWLIST_BROWSER_UA_NO_CREDENTIAL_NO_COOKIE_NO_QUERY"
        or payload["external_write"] != "NOT_EXECUTED"
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    source_captures = _object_list(payload["source_captures"])
    rule_sets = _object_list(payload["rule_sets"])
    capture_window_ended_at = _datetime(payload["capture_window_ended_at"])
    results: list[AirlineRuleSet] = []
    try:
        captures: dict[str, tuple[FreshnessState, str]] = {}
        for capture_object in source_captures:
            source_id, status, body_sha256 = _parse_capture(capture_object)
            if source_id in captures:
                raise AdapterError(AdapterFailure.INVALID_RESPONSE)
            captures[source_id] = (status, body_sha256)
        for record_object in rule_sets:
            results.append(
                _parse_rule_set(
                    record_object,
                    captures=captures,
                    capture_window_ended_at=capture_window_ended_at,
                )
            )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
    return tuple(results)


class RecordedRuleRegistry:
    mode = "RECORDED_ONLY"
    external_action_count = 0

    def __init__(self, rule_sets: tuple[AirlineRuleSet, ...]) -> None:
        self._rule_sets = rule_sets

    @classmethod
    def from_file(cls, path: Path) -> RecordedRuleRegistry:
        return cls(load_rule_fixture(path))

    def resolve(
        self, segment: JourneySegment, *, at: datetime
    ) -> tuple[AirlineRuleSet, ...]:
        if at != segment.departure_at:
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        if segment.carrier is None:
            return ()
        return tuple(
            rule
            for rule in self._rule_sets
            if rule.carrier.casefold() == segment.carrier.casefold()
            and (rule.effective_from or rule.observed_applicable_from) <= at
            and (rule.effective_to is None or at < rule.effective_to)
        )


__all__ = ["RecordedRuleRegistry", "load_rule_fixture"]
