"""Closed ST-1602 SLO and alert runtime values.

The runtime compiles an exact generated catalog and evaluates only caller-
supplied recorded synthetic windows.  It has no clock, telemetry backend,
notification channel, network, credential, release, or Production authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NoReturn, cast


EXPECTED_CONTRACT_SHA256: Final = (
    "3737fd25156119db659138bf372b68a8730261f9785aa12b2d8be65bbae27095"
)
EXPECTED_CATALOG_CANONICAL_SHA256: Final = (
    "a79bc393feb4c52c87ef9acc7cfae3a34791289ef5b28293b68b77158e42eee4"
)
SYNTHETIC_SOURCE: Final = "SYNTHETIC_RECORDED_FIXTURE_ONLY"
OWNER_ID: Final = "Operations Owner"
ZERO_SHA256: Final = "0" * 64
SLO_IDS: Final = tuple(f"SLO-{index:03d}" for index in range(1, 15))
ALERT_IDS: Final = tuple(f"ALT-{index:03d}" for index in range(1, 21))
RUNBOOK_IDS: Final = tuple(f"RB-{index:03d}" for index in range(1, 21))

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_INSTANCE_ID = re.compile(r"[a-z0-9][a-z0-9.-]{2,95}\Z")
_MAX_CANONICAL_BYTES = 262_144
_MAX_DEPTH = 24
_MAX_EPOCH_SECONDS = 32_503_680_000
_MAX_METRIC_VALUE = 10**18


class SloAlertFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"
    DATA_BLOCKED = "DATA_BLOCKED"
    JOURNAL_UNAVAILABLE = "JOURNAL_UNAVAILABLE"
    JOURNAL_TAMPERED = "JOURNAL_TAMPERED"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    COMMIT_AMBIGUOUS = "COMMIT_AMBIGUOUS"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"
    NOTIFICATION_UNAVAILABLE = "NOTIFICATION_UNAVAILABLE"


class SloAlertFailure(ValueError):
    """Sanitized regular failure that never retains collaborator material."""

    __slots__ = ("_code", "_field")
    _code: SloAlertFailureCode
    _field: str

    def __init__(self, code: SloAlertFailureCode, field: str) -> None:
        if type(code) is not SloAlertFailureCode:
            raise TypeError("code must be an exact SloAlertFailureCode")
        if (
            type(field) is not str
            or re.fullmatch(r"[a-z][a-z0-9_.]{0,95}", field) is None
        ):
            raise TypeError("field must be a closed safe identifier")
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_field", field)
        ValueError.__init__(self, code.value)

    @property
    def code(self) -> SloAlertFailureCode:
        return self._code

    @property
    def field(self) -> str:
        return self._field

    def __repr__(self) -> str:
        return f"SloAlertFailure(code={self._code.value}, field={self._field})"

    def __setattr__(self, name: str, value: object) -> None:
        if name in {
            "__traceback__",
            "__cause__",
            "__context__",
            "__suppress_context__",
        }:
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("SloAlertFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("SloAlertFailure is immutable")


def fail(code: SloAlertFailureCode, field: str) -> NoReturn:
    raise SloAlertFailure(code, field) from None


def _closed_json(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_DEPTH:
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
    if value is None or type(value) in {bool, int, str}:
        if type(value) is str and (len(value) > 4096 or "\x00" in value):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
        return value
    if type(value) in {list, tuple}:
        items = cast(Sequence[object], value)
        if len(items) > 1024:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
        return [_closed_json(item, depth=depth + 1) for item in items]
    if type(value) is dict:
        raw = cast(dict[object, object], value)
        if len(raw) > 1024 or any(type(key) is not str for key in raw):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
        return {
            cast(str, key): _closed_json(item, depth=depth + 1)
            for key, item in raw.items()
        }
    fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")


def canonical_bytes(value: object) -> bytes:
    try:
        content = json.dumps(
            _closed_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except UnicodeEncodeError, ValueError:
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
    if not content or len(content) > _MAX_CANONICAL_BYTES:
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "canonical")
    return content


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if type(value) is not list:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, maximum: int = 4096) -> str:
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_METRIC_VALUE:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    return value


def _sha256(value: object, field: str) -> str:
    text = _string(value, field, maximum=64)
    if _SHA256.fullmatch(text) is None:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, field)
    return text


class SloTargetKind(StrEnum):
    RATIO_MINIMUM = "RATIO_MINIMUM"
    UPPER_BOUND = "UPPER_BOUND"
    COMPOSITE_UPPER_BOUND = "COMPOSITE_UPPER_BOUND"


class SloEvaluationState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class DataBlockReason(StrEnum):
    NONE = "NONE"
    MISSING = "MISSING"
    INVALID = "INVALID"
    STALE = "STALE"
    IMMATURE = "IMMATURE"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"


class AlertSeverity(StrEnum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class AlertConditionState(StrEnum):
    BREACH = "BREACH"
    CLEAR = "CLEAR"
    UNAVAILABLE = "UNAVAILABLE"


class AlertLifecycleState(StrEnum):
    PENDING = "PENDING"
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"


class AlertTransitionOutcome(StrEnum):
    DATA_BLOCKED = "DATA_BLOCKED"
    PENDING = "PENDING"
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"
    UNCHANGED = "UNCHANGED"


class HoldKind(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    DURATION = "DURATION"
    DUAL_DURATION = "DUAL_DURATION"
    CYCLE = "CYCLE"
    DUAL_CYCLE = "DUAL_CYCLE"


class HoldVariant(StrEnum):
    DEFAULT = "DEFAULT"
    FAST = "FAST"
    SLOW = "SLOW"
    PER_BATCH = "PER_BATCH"
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    RELEASE = "RELEASE"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True, slots=True)
class SloRule:
    slo_id: str
    name: str
    scope: str
    sli: str
    target_text: str
    window_text: str
    notes: str
    target_kind: SloTargetKind
    component_names: tuple[str, ...]
    thresholds: tuple[int, ...]
    canonical_fingerprint: str

    def __post_init__(self) -> None:
        if (
            self.slo_id not in SLO_IDS
            or any(
                type(value) is not str or not value or len(value) > 4096
                for value in (
                    self.name,
                    self.scope,
                    self.sli,
                    self.target_text,
                    self.window_text,
                    self.notes,
                )
            )
            or type(self.target_kind) is not SloTargetKind
            or not self.component_names
            or len(self.component_names) != len(self.thresholds)
            or len(set(self.component_names)) != len(self.component_names)
            or any(
                re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item) is None
                for item in self.component_names
            )
            or any(type(item) is not int or item < 0 for item in self.thresholds)
            or _SHA256.fullmatch(self.canonical_fingerprint) is None
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.rule")
        if self.target_kind is SloTargetKind.RATIO_MINIMUM and (
            self.component_names != ("numerator", "denominator")
            or len(self.thresholds) != 2
            or self.thresholds[1] != 1_000_000
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.ratio")


@dataclass(frozen=True, slots=True)
class AlertHoldVariant:
    variant: HoldVariant
    duration_seconds: int | None
    cycle_required: bool

    def __post_init__(self) -> None:
        if (
            type(self.variant) is not HoldVariant
            or (
                self.duration_seconds is not None
                and (
                    type(self.duration_seconds) is not int or self.duration_seconds < 0
                )
            )
            or type(self.cycle_required) is not bool
            or (self.duration_seconds is None) == (not self.cycle_required)
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.hold")


@dataclass(frozen=True, slots=True)
class AlertRule:
    alert_id: str
    severity: AlertSeverity
    name: str
    condition: str
    detection: str
    initial_action: str
    owner_id: str
    runbook_id: str
    hold_kind: HoldKind
    hold_variants: tuple[AlertHoldVariant, ...]
    dedup_fingerprint: str

    def __post_init__(self) -> None:
        if (
            self.alert_id not in ALERT_IDS
            or type(self.severity) is not AlertSeverity
            or any(
                type(value) is not str or not value or len(value) > 4096
                for value in (
                    self.name,
                    self.condition,
                    self.detection,
                    self.initial_action,
                )
            )
            or self.owner_id != OWNER_ID
            or self.runbook_id not in RUNBOOK_IDS
            or type(self.hold_kind) is not HoldKind
            or not self.hold_variants
            or len({item.variant for item in self.hold_variants})
            != len(self.hold_variants)
            or _SHA256.fullmatch(self.dedup_fingerprint) is None
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.rule")

    def hold(self, variant: HoldVariant) -> AlertHoldVariant:
        matches = tuple(item for item in self.hold_variants if item.variant is variant)
        if len(matches) != 1:
            fail(SloAlertFailureCode.DATA_BLOCKED, "alert.hold_variant")
        return matches[0]


@dataclass(frozen=True, slots=True)
class RuntimeCatalog:
    contract_sha256: str
    catalog_sha256: str
    slo_rules: tuple[SloRule, ...]
    alert_rules: tuple[AlertRule, ...]
    runbook_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.contract_sha256 != EXPECTED_CONTRACT_SHA256
            or _SHA256.fullmatch(self.catalog_sha256) is None
            or tuple(rule.slo_id for rule in self.slo_rules) != SLO_IDS
            or tuple(rule.alert_id for rule in self.alert_rules) != ALERT_IDS
            or self.runbook_ids != RUNBOOK_IDS
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog")

    def slo(self, slo_id: str) -> SloRule:
        matches = tuple(rule for rule in self.slo_rules if rule.slo_id == slo_id)
        if len(matches) != 1:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "slo.id")
        return matches[0]

    def alert(self, alert_id: str) -> AlertRule:
        matches = tuple(rule for rule in self.alert_rules if rule.alert_id == alert_id)
        if len(matches) != 1:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.id")
        return matches[0]


def _compile_slo(value: object) -> SloRule:
    row = _mapping(value, "slo")
    if tuple(row) != (
        "id",
        "name",
        "scope",
        "sli",
        "target",
        "window",
        "notes",
        "status",
        "implementation_status",
        "measurement_status",
        "evaluation",
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.schema")
    if (
        row.get("status") != "PROVISIONAL_TARGET"
        or row.get("implementation_status") != "NOT_STARTED"
        or row.get("measurement_status") != "NOT_EXECUTED"
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.status")
    evaluation = _mapping(row.get("evaluation"), "slo.evaluation")
    if tuple(evaluation) != ("kind", "components", "thresholds"):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.evaluation")
    components = tuple(
        _string(item, "slo.component", maximum=64)
        for item in _sequence(evaluation.get("components"), "slo.components")
    )
    thresholds = tuple(
        _integer(item, "slo.threshold")
        for item in _sequence(evaluation.get("thresholds"), "slo.thresholds")
    )
    raw_fingerprint = canonical_sha256({key: row[key] for key in tuple(row)[:-1]})
    try:
        kind = SloTargetKind(_string(evaluation.get("kind"), "slo.kind", maximum=64))
    except ValueError:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "slo.kind")
    return SloRule(
        slo_id=_string(row.get("id"), "slo.id", maximum=7),
        name=_string(row.get("name"), "slo.name"),
        scope=_string(row.get("scope"), "slo.scope"),
        sli=_string(row.get("sli"), "slo.sli"),
        target_text=_string(row.get("target"), "slo.target"),
        window_text=_string(row.get("window"), "slo.window"),
        notes=_string(row.get("notes"), "slo.notes"),
        target_kind=kind,
        component_names=components,
        thresholds=thresholds,
        canonical_fingerprint=raw_fingerprint,
    )


def _compile_alert(value: object) -> AlertRule:
    row = _mapping(value, "alert")
    if tuple(row) != (
        "id",
        "severity",
        "name",
        "condition",
        "detection",
        "initial_action",
        "implementation_status",
        "test_status",
        "route",
        "hold",
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.schema")
    if (
        row.get("implementation_status") != "NOT_STARTED"
        or row.get("test_status") != "NOT_EXECUTED"
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.status")
    route = _mapping(row.get("route"), "alert.route")
    if (
        tuple(route) != ("owner", "runbook_id", "notification_mode")
        or route.get("owner") != OWNER_ID
        or route.get("notification_mode") != "LOCAL_LOG_ONLY_DISABLED"
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.route")
    hold = _mapping(row.get("hold"), "alert.hold")
    if tuple(hold) != ("kind", "variants"):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.hold")
    try:
        hold_kind = HoldKind(_string(hold.get("kind"), "alert.hold_kind", maximum=64))
        severity = AlertSeverity(
            _string(row.get("severity"), "alert.severity", maximum=4)
        )
    except ValueError:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.enum")
    variants: list[AlertHoldVariant] = []
    for raw_variant in _sequence(hold.get("variants"), "alert.hold_variants"):
        variant = _mapping(raw_variant, "alert.hold_variant")
        if tuple(variant) != ("variant", "duration_seconds", "cycle_required"):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.hold_variant")
        try:
            variant_name = HoldVariant(
                _string(variant.get("variant"), "alert.variant", maximum=16)
            )
        except ValueError:
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.variant")
        duration = variant.get("duration_seconds")
        if duration is not None:
            duration = _integer(duration, "alert.duration")
        cycle = variant.get("cycle_required")
        if type(cycle) is not bool:
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "alert.cycle")
        variants.append(AlertHoldVariant(variant_name, duration, cycle))
    alert_id = _string(row.get("id"), "alert.id", maximum=7)
    condition = _string(row.get("condition"), "alert.condition")
    detection = _string(row.get("detection"), "alert.detection")
    runbook_id = _string(route.get("runbook_id"), "alert.runbook", maximum=6)
    fingerprint = canonical_sha256(
        {
            "alert_id": alert_id,
            "severity": severity.value,
            "condition": condition,
            "detection": detection,
            "owner": OWNER_ID,
            "runbook_id": runbook_id,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
        }
    )
    return AlertRule(
        alert_id=alert_id,
        severity=severity,
        name=_string(row.get("name"), "alert.name"),
        condition=condition,
        detection=detection,
        initial_action=_string(row.get("initial_action"), "alert.initial_action"),
        owner_id=OWNER_ID,
        runbook_id=runbook_id,
        hold_kind=hold_kind,
        hold_variants=tuple(variants),
        dedup_fingerprint=fingerprint,
    )


def compile_runtime_catalog(value: object) -> RuntimeCatalog:
    """Compile the generated exact catalog into closed typed rules."""

    document = _mapping(value, "catalog")
    if tuple(document) != (
        "document",
        "authority",
        "slos",
        "alerts",
        "runbooks",
        "boundary",
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog.schema")
    header = _mapping(document.get("document"), "catalog.document")
    if header != {
        "id": "RAOS-ST1602-SLO-ALERT-RUNTIME-CATALOG-002",
        "version": "2.0.0",
        "story_id": "ST-1602",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "classification": "LOCAL_SYNTHETIC_NON_ATTESTING_SLO_ALERT_RUNTIME",
    }:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog.document")
    authority = _mapping(document.get("authority"), "catalog.authority")
    if tuple(authority) != (
        "slo_catalog_sha256",
        "alert_catalog_sha256",
        "runbook_catalog_sha256",
    ):
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog.authority")
    for name in authority:
        _sha256(authority[name], "catalog.authority")
    slos = tuple(
        _compile_slo(item) for item in _sequence(document.get("slos"), "catalog.slos")
    )
    alerts = tuple(
        _compile_alert(item)
        for item in _sequence(document.get("alerts"), "catalog.alerts")
    )
    raw_runbooks = _sequence(document.get("runbooks"), "catalog.runbooks")
    runbooks: list[str] = []
    for raw in raw_runbooks:
        row = _mapping(raw, "runbook")
        if tuple(row) != (
            "id",
            "title",
            "severity",
            "minimum_steps",
            "document_status",
            "implementation_status",
            "drill_status",
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "runbook.schema")
        if (
            row.get("document_status") != "DESIGNED_INDEX_ONLY"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("drill_status") != "NOT_EXECUTED"
        ):
            fail(SloAlertFailureCode.CONTRACT_DRIFT, "runbook.status")
        runbooks.append(_string(row.get("id"), "runbook.id", maximum=6))
    boundary = _mapping(document.get("boundary"), "catalog.boundary")
    if boundary != {
        "source": SYNTHETIC_SOURCE,
        "notifications_enabled": False,
        "notification_mode": "LOCAL_LOG_ONLY_DISABLED",
        "external_action_count": 0,
        "formal_tst_027": "NOT_EXECUTED",
        "formal_tst_028": "NOT_EXECUTED",
        "production": "NOT_AUTHORIZED",
    }:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog.boundary")
    catalog_sha256 = canonical_sha256(document)
    if catalog_sha256 != EXPECTED_CATALOG_CANONICAL_SHA256:
        fail(SloAlertFailureCode.CONTRACT_DRIFT, "catalog.digest")
    return RuntimeCatalog(
        contract_sha256=EXPECTED_CONTRACT_SHA256,
        catalog_sha256=catalog_sha256,
        slo_rules=slos,
        alert_rules=alerts,
        runbook_ids=tuple(runbooks),
    )


@dataclass(frozen=True, slots=True, repr=False)
class SloMetricWindow:
    slo_id: str
    source: str
    observed_at_epoch_seconds: int
    evaluated_at_epoch_seconds: int
    fresh_until_epoch_seconds: int
    window_start_epoch_seconds: int
    window_end_epoch_seconds: int
    sample_count: int
    mature: bool
    values: tuple[tuple[str, int | None], ...]

    def __post_init__(self) -> None:
        numeric = (
            self.observed_at_epoch_seconds,
            self.evaluated_at_epoch_seconds,
            self.fresh_until_epoch_seconds,
            self.window_start_epoch_seconds,
            self.window_end_epoch_seconds,
            self.sample_count,
        )
        if (
            self.slo_id not in SLO_IDS
            or self.source != SYNTHETIC_SOURCE
            or any(
                type(item) is not int or not 0 <= item <= _MAX_EPOCH_SECONDS
                for item in numeric[:-1]
            )
            or type(self.sample_count) is not int
            or type(self.mature) is not bool
            or self.window_start_epoch_seconds > self.window_end_epoch_seconds
            or self.observed_at_epoch_seconds < self.window_end_epoch_seconds
            or self.evaluated_at_epoch_seconds < self.observed_at_epoch_seconds
            or self.fresh_until_epoch_seconds < self.observed_at_epoch_seconds
            or not self.values
            or len(self.values) > 8
            or len({name for name, _ in self.values}) != len(self.values)
            or any(
                type(name) is not str
                or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) is None
                or (
                    value is not None
                    and (type(value) is not int or abs(value) > _MAX_METRIC_VALUE)
                )
                for name, value in self.values
            )
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "slo.window")

    def __repr__(self) -> str:
        return "SloMetricWindow(<redacted-recorded-metrics>)"


@dataclass(frozen=True, slots=True)
class SloEvaluation:
    slo_id: str
    state: SloEvaluationState
    reason: DataBlockReason
    rule_fingerprint: str
    actual_measurement_claim: bool = False

    def __post_init__(self) -> None:
        if (
            self.slo_id not in SLO_IDS
            or type(self.state) is not SloEvaluationState
            or type(self.reason) is not DataBlockReason
            or _SHA256.fullmatch(self.rule_fingerprint) is None
            or type(self.actual_measurement_claim) is not bool
            or self.actual_measurement_claim
            or (self.state is SloEvaluationState.UNAVAILABLE)
            != (self.reason is not DataBlockReason.NONE)
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "slo.evaluation")


def evaluate_slo(rule: SloRule, window: SloMetricWindow) -> SloEvaluation:
    """Evaluate one recorded synthetic metric window without ambient state."""

    if (
        type(rule) is not SloRule
        or type(window) is not SloMetricWindow
        or window.slo_id != rule.slo_id
    ):
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "slo.input")
    blocked: DataBlockReason | None = None
    if window.source != SYNTHETIC_SOURCE:
        blocked = DataBlockReason.SOURCE_MISMATCH
    elif window.evaluated_at_epoch_seconds > window.fresh_until_epoch_seconds:
        blocked = DataBlockReason.STALE
    elif not window.mature:
        blocked = DataBlockReason.IMMATURE
    elif window.sample_count <= 0:
        blocked = (
            DataBlockReason.MISSING
            if window.sample_count == 0
            else DataBlockReason.INVALID
        )
    elif tuple(name for name, _ in window.values) != rule.component_names:
        blocked = DataBlockReason.INVALID
    elif any(value is None for _, value in window.values):
        blocked = DataBlockReason.MISSING
    elif any(cast(int, value) < 0 for _, value in window.values):
        blocked = DataBlockReason.INVALID
    if blocked is not None:
        return SloEvaluation(
            rule.slo_id,
            SloEvaluationState.UNAVAILABLE,
            blocked,
            rule.canonical_fingerprint,
        )
    values = tuple(cast(int, value) for _, value in window.values)
    if rule.target_kind is SloTargetKind.RATIO_MINIMUM:
        numerator, denominator = values
        if denominator == 0:
            return SloEvaluation(
                rule.slo_id,
                SloEvaluationState.UNAVAILABLE,
                DataBlockReason.ZERO_DENOMINATOR,
                rule.canonical_fingerprint,
            )
        if numerator > denominator:
            return SloEvaluation(
                rule.slo_id,
                SloEvaluationState.UNAVAILABLE,
                DataBlockReason.INVALID,
                rule.canonical_fingerprint,
            )
        threshold_ppm = rule.thresholds[0]
        passed = numerator * 1_000_000 >= denominator * threshold_ppm
    else:
        passed = all(
            value <= threshold
            for value, threshold in zip(values, rule.thresholds, strict=True)
        )
    return SloEvaluation(
        rule.slo_id,
        SloEvaluationState.PASS if passed else SloEvaluationState.FAIL,
        DataBlockReason.NONE,
        rule.canonical_fingerprint,
    )


@dataclass(frozen=True, slots=True, repr=False)
class AlertObservation:
    alert_id: str
    source: str
    observed_at_epoch_seconds: int
    evaluated_at_epoch_seconds: int
    fresh_until_epoch_seconds: int
    sample_count: int
    mature: bool
    condition_state: AlertConditionState
    hold_variant: HoldVariant
    condition_started_at_epoch_seconds: int | None
    cycle_complete: bool
    observation_sha256: str

    def __post_init__(self) -> None:
        numeric = (
            self.observed_at_epoch_seconds,
            self.evaluated_at_epoch_seconds,
            self.fresh_until_epoch_seconds,
        )
        if (
            self.alert_id not in ALERT_IDS
            or self.source != SYNTHETIC_SOURCE
            or any(
                type(item) is not int or not 0 <= item <= _MAX_EPOCH_SECONDS
                for item in numeric
            )
            or self.evaluated_at_epoch_seconds < self.observed_at_epoch_seconds
            or self.fresh_until_epoch_seconds < self.observed_at_epoch_seconds
            or type(self.sample_count) is not int
            or type(self.mature) is not bool
            or type(self.condition_state) is not AlertConditionState
            or type(self.hold_variant) is not HoldVariant
            or type(self.cycle_complete) is not bool
            or _SHA256.fullmatch(self.observation_sha256) is None
            or (
                self.condition_started_at_epoch_seconds is not None
                and (
                    type(self.condition_started_at_epoch_seconds) is not int
                    or not 0
                    <= self.condition_started_at_epoch_seconds
                    <= self.observed_at_epoch_seconds
                )
            )
            or (
                self.condition_state is not AlertConditionState.BREACH
                and self.condition_started_at_epoch_seconds is not None
            )
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.observation")

    def __repr__(self) -> str:
        return "AlertObservation(<redacted-recorded-condition>)"

    def canonical_document(self) -> dict[str, object]:
        return {
            "alert_id": self.alert_id,
            "source": self.source,
            "observed_at_epoch_seconds": self.observed_at_epoch_seconds,
            "evaluated_at_epoch_seconds": self.evaluated_at_epoch_seconds,
            "fresh_until_epoch_seconds": self.fresh_until_epoch_seconds,
            "sample_count": self.sample_count,
            "mature": self.mature,
            "condition_state": self.condition_state.value,
            "hold_variant": self.hold_variant.value,
            "condition_started_at_epoch_seconds": self.condition_started_at_epoch_seconds,
            "cycle_complete": self.cycle_complete,
            "observation_sha256": self.observation_sha256,
        }


@dataclass(frozen=True, slots=True)
class AlertSnapshot:
    instance_key: str
    alert_id: str
    rule_fingerprint: str
    current_version: int
    state: AlertLifecycleState
    pending_since_epoch_seconds: int | None
    result_sha256: str
    latest_sequence: int
    latest_entry_sha256: str

    def __post_init__(self) -> None:
        if (
            not _valid_instance_key(self.instance_key, self.alert_id)
            or self.alert_id not in ALERT_IDS
            or _SHA256.fullmatch(self.rule_fingerprint) is None
            or type(self.current_version) is not int
            or self.current_version < 1
            or type(self.state) is not AlertLifecycleState
            or (
                self.pending_since_epoch_seconds is not None
                and (
                    type(self.pending_since_epoch_seconds) is not int
                    or self.pending_since_epoch_seconds < 0
                )
            )
            or (self.state is AlertLifecycleState.PENDING)
            != (self.pending_since_epoch_seconds is not None)
            or _SHA256.fullmatch(self.result_sha256) is None
            or type(self.latest_sequence) is not int
            or self.latest_sequence < 1
            or _SHA256.fullmatch(self.latest_entry_sha256) is None
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "snapshot")


@dataclass(frozen=True, slots=True)
class AlertDecision:
    instance_key: str
    alert_id: str
    severity: AlertSeverity
    owner_id: str
    runbook_id: str
    rule_fingerprint: str
    dedup_fingerprint: str
    from_state: AlertLifecycleState
    state: AlertLifecycleState
    outcome: AlertTransitionOutcome
    reason: DataBlockReason
    pending_since_epoch_seconds: int | None
    notification_mode: str = "LOCAL_LOG_ONLY_DISABLED"
    notification_delivery_claim: bool = False
    external_action_count: int = 0

    def __post_init__(self) -> None:
        transition_valid = {
            AlertTransitionOutcome.DATA_BLOCKED: self.state is self.from_state,
            AlertTransitionOutcome.PENDING: (
                self.state is AlertLifecycleState.PENDING
                and self.from_state is not AlertLifecycleState.PENDING
            ),
            AlertTransitionOutcome.FIRING: (
                self.state is AlertLifecycleState.FIRING
                and self.from_state is not AlertLifecycleState.FIRING
            ),
            AlertTransitionOutcome.RESOLVED: (
                self.state is AlertLifecycleState.RESOLVED
                and self.from_state is not AlertLifecycleState.RESOLVED
            ),
            AlertTransitionOutcome.UNCHANGED: self.state is self.from_state,
        }
        if (
            not _valid_instance_key(self.instance_key, self.alert_id)
            or self.alert_id not in ALERT_IDS
            or type(self.severity) is not AlertSeverity
            or self.owner_id != OWNER_ID
            or self.runbook_id not in RUNBOOK_IDS
            or _SHA256.fullmatch(self.rule_fingerprint) is None
            or _SHA256.fullmatch(self.dedup_fingerprint) is None
            or type(self.from_state) is not AlertLifecycleState
            or type(self.state) is not AlertLifecycleState
            or type(self.outcome) is not AlertTransitionOutcome
            or type(self.reason) is not DataBlockReason
            or (
                self.pending_since_epoch_seconds is not None
                and (
                    type(self.pending_since_epoch_seconds) is not int
                    or self.pending_since_epoch_seconds < 0
                )
            )
            or (self.state is AlertLifecycleState.PENDING)
            != (self.pending_since_epoch_seconds is not None)
            or self.notification_mode != "LOCAL_LOG_ONLY_DISABLED"
            or type(self.notification_delivery_claim) is not bool
            or self.notification_delivery_claim
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
            or (self.outcome is AlertTransitionOutcome.DATA_BLOCKED)
            != (self.reason is not DataBlockReason.NONE)
            or not transition_valid[self.outcome]
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.decision")

    def document(self) -> dict[str, object]:
        return {
            "instance_key": self.instance_key,
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "owner_id": self.owner_id,
            "runbook_id": self.runbook_id,
            "rule_fingerprint": self.rule_fingerprint,
            "dedup_fingerprint": self.dedup_fingerprint,
            "from_state": self.from_state.value,
            "state": self.state.value,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "pending_since_epoch_seconds": self.pending_since_epoch_seconds,
            "notification_mode": self.notification_mode,
            "notification_delivery_claim": self.notification_delivery_claim,
            "external_action_count": self.external_action_count,
        }


def _valid_instance_key(instance_key: object, alert_id: str) -> bool:
    if type(instance_key) is not str:
        return False
    prefix = f"{alert_id}:"
    return (
        instance_key.startswith(prefix)
        and _INSTANCE_ID.fullmatch(instance_key[len(prefix) :]) is not None
    )


def alert_instance_key(alert_id: str, instance_id: str) -> str:
    if (
        alert_id not in ALERT_IDS
        or type(instance_id) is not str
        or _INSTANCE_ID.fullmatch(instance_id) is None
    ):
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.instance")
    return f"{alert_id}:{instance_id}"


def _dedup(rule: AlertRule, instance_key: str) -> str:
    return canonical_sha256(
        {
            "rule_fingerprint": rule.dedup_fingerprint,
            "instance_key": instance_key,
            "severity": rule.severity.value,
            "owner_id": rule.owner_id,
            "runbook_id": rule.runbook_id,
            "condition": rule.condition,
            "detection": rule.detection,
        }
    )


def evaluate_alert(
    rule: AlertRule,
    instance_key: str,
    observation: AlertObservation,
    prior: AlertSnapshot | None,
) -> AlertDecision:
    """Evaluate one explicit alert step; never loops or emits externally."""

    if (
        type(rule) is not AlertRule
        or type(observation) is not AlertObservation
        or observation.alert_id != rule.alert_id
        or not _valid_instance_key(instance_key, rule.alert_id)
        or (prior is not None and type(prior) is not AlertSnapshot)
    ):
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.input")
    if prior is not None and (
        prior.instance_key != instance_key
        or prior.alert_id != rule.alert_id
        or prior.rule_fingerprint != rule.dedup_fingerprint
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "alert.prior")
    from_state = AlertLifecycleState.RESOLVED if prior is None else prior.state
    previous_pending = None if prior is None else prior.pending_since_epoch_seconds
    blocked: DataBlockReason | None = None
    if observation.source != SYNTHETIC_SOURCE:
        blocked = DataBlockReason.SOURCE_MISMATCH
    elif observation.evaluated_at_epoch_seconds > observation.fresh_until_epoch_seconds:
        blocked = DataBlockReason.STALE
    elif not observation.mature:
        blocked = DataBlockReason.IMMATURE
    elif observation.sample_count <= 0:
        blocked = (
            DataBlockReason.MISSING
            if observation.sample_count == 0
            else DataBlockReason.INVALID
        )
    elif observation.condition_state is AlertConditionState.UNAVAILABLE:
        blocked = DataBlockReason.MISSING
    if blocked is not None:
        return AlertDecision(
            instance_key,
            rule.alert_id,
            rule.severity,
            rule.owner_id,
            rule.runbook_id,
            rule.dedup_fingerprint,
            _dedup(rule, instance_key),
            from_state,
            from_state,
            AlertTransitionOutcome.DATA_BLOCKED,
            blocked,
            previous_pending,
        )
    if observation.condition_state is AlertConditionState.CLEAR:
        state = AlertLifecycleState.RESOLVED
        outcome = (
            AlertTransitionOutcome.UNCHANGED
            if from_state is state
            else AlertTransitionOutcome.RESOLVED
        )
        pending_since = None
    else:
        try:
            hold = rule.hold(observation.hold_variant)
        except SloAlertFailure:
            return AlertDecision(
                instance_key,
                rule.alert_id,
                rule.severity,
                rule.owner_id,
                rule.runbook_id,
                rule.dedup_fingerprint,
                _dedup(rule, instance_key),
                from_state,
                from_state,
                AlertTransitionOutcome.DATA_BLOCKED,
                DataBlockReason.INVALID,
                previous_pending,
            )
        started = observation.condition_started_at_epoch_seconds
        if hold.duration_seconds is not None:
            if started is None or (
                previous_pending is not None and started != previous_pending
            ):
                return AlertDecision(
                    instance_key,
                    rule.alert_id,
                    rule.severity,
                    rule.owner_id,
                    rule.runbook_id,
                    rule.dedup_fingerprint,
                    _dedup(rule, instance_key),
                    from_state,
                    from_state,
                    AlertTransitionOutcome.DATA_BLOCKED,
                    DataBlockReason.MISSING
                    if started is None
                    else DataBlockReason.INVALID,
                    previous_pending,
                )
            satisfied = (
                observation.evaluated_at_epoch_seconds - started
                >= hold.duration_seconds
            )
            pending_since = started
        else:
            satisfied = observation.cycle_complete
            pending_since = previous_pending or observation.observed_at_epoch_seconds
        if satisfied:
            state = AlertLifecycleState.FIRING
            outcome = (
                AlertTransitionOutcome.UNCHANGED
                if from_state is state
                else AlertTransitionOutcome.FIRING
            )
            pending_since = None
        else:
            state = AlertLifecycleState.PENDING
            outcome = (
                AlertTransitionOutcome.UNCHANGED
                if from_state is state
                else AlertTransitionOutcome.PENDING
            )
    return AlertDecision(
        instance_key,
        rule.alert_id,
        rule.severity,
        rule.owner_id,
        rule.runbook_id,
        rule.dedup_fingerprint,
        _dedup(rule, instance_key),
        from_state,
        state,
        outcome,
        DataBlockReason.NONE,
        pending_since,
    )


@dataclass(frozen=True, slots=True)
class AlertPersistCommand:
    instance_key: str
    alert_id: str
    rule_fingerprint: str
    idempotency_key_sha256: str
    request_sha256: str
    expected_version: int
    current_version: int
    decision: AlertDecision
    result_sha256: str
    result_json: bytes

    def __post_init__(self) -> None:
        if (
            not _valid_instance_key(self.instance_key, self.alert_id)
            or self.alert_id not in ALERT_IDS
            or _SHA256.fullmatch(self.rule_fingerprint) is None
            or _SHA256.fullmatch(self.idempotency_key_sha256) is None
            or _SHA256.fullmatch(self.request_sha256) is None
            or type(self.expected_version) is not int
            or self.expected_version < 0
            or type(self.current_version) is not int
            or self.current_version != self.expected_version + 1
            or type(self.decision) is not AlertDecision
            or self.decision.instance_key != self.instance_key
            or self.decision.alert_id != self.alert_id
            or self.decision.rule_fingerprint != self.rule_fingerprint
            or _SHA256.fullmatch(self.result_sha256) is None
            or type(self.result_json) is not bytes
            or not self.result_json
            or len(self.result_json) > _MAX_CANONICAL_BYTES
            or hashlib.sha256(self.result_json).hexdigest() != self.result_sha256
            or self.result_json != canonical_bytes(self.decision.document())
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.command")


@dataclass(frozen=True, slots=True)
class AlertPersistReceipt:
    instance_key: str
    current_version: int
    request_sha256: str
    result_sha256: str
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        alert_id = self.instance_key.partition(":")[0]
        if (
            not _valid_instance_key(self.instance_key, alert_id)
            or type(self.current_version) is not int
            or self.current_version < 1
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.request_sha256,
                    self.result_sha256,
                    self.previous_entry_sha256,
                    self.entry_sha256,
                )
            )
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.replayed) is not bool
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.receipt")


@dataclass(frozen=True, slots=True)
class PersistedAlertStep:
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    instance_key: str
    alert_id: str
    rule_fingerprint: str
    idempotency_key_sha256: str
    request_sha256: str
    expected_version: int
    current_version: int
    state: AlertLifecycleState
    outcome: AlertTransitionOutcome
    reason: DataBlockReason
    pending_since_epoch_seconds: int | None
    result_sha256: str
    result_json: bytes

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or self.sequence < 1
            or any(
                _SHA256.fullmatch(value) is None
                for value in (
                    self.previous_entry_sha256,
                    self.entry_sha256,
                    self.rule_fingerprint,
                    self.idempotency_key_sha256,
                    self.request_sha256,
                    self.result_sha256,
                )
            )
            or not _valid_instance_key(self.instance_key, self.alert_id)
            or self.alert_id not in ALERT_IDS
            or type(self.expected_version) is not int
            or self.expected_version < 0
            or type(self.current_version) is not int
            or self.current_version != self.expected_version + 1
            or type(self.state) is not AlertLifecycleState
            or type(self.outcome) is not AlertTransitionOutcome
            or type(self.reason) is not DataBlockReason
            or (self.state is AlertLifecycleState.PENDING)
            != (self.pending_since_epoch_seconds is not None)
            or (self.outcome is AlertTransitionOutcome.DATA_BLOCKED)
            != (self.reason is not DataBlockReason.NONE)
            or type(self.result_json) is not bytes
            or hashlib.sha256(self.result_json).hexdigest() != self.result_sha256
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.persisted")

    def receipt(self, *, replayed: bool) -> AlertPersistReceipt:
        return AlertPersistReceipt(
            self.instance_key,
            self.current_version,
            self.request_sha256,
            self.result_sha256,
            self.sequence,
            self.previous_entry_sha256,
            self.entry_sha256,
            replayed,
        )

    def snapshot(self) -> AlertSnapshot:
        return AlertSnapshot(
            self.instance_key,
            self.alert_id,
            self.rule_fingerprint,
            self.current_version,
            self.state,
            self.pending_since_epoch_seconds,
            self.result_sha256,
            self.sequence,
            self.entry_sha256,
        )


def make_persist_command(
    *,
    rule: AlertRule,
    instance_key: str,
    observation: AlertObservation,
    expected_version: int,
    decision: AlertDecision,
) -> AlertPersistCommand:
    if type(expected_version) is not int or expected_version < 0:
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.version")
    request_document = {
        "instance_key": instance_key,
        "expected_version": expected_version,
        "rule_fingerprint": rule.dedup_fingerprint,
        "observation": observation.canonical_document(),
    }
    request_sha256 = canonical_sha256(request_document)
    result_json = canonical_bytes(decision.document())
    return AlertPersistCommand(
        instance_key=instance_key,
        alert_id=rule.alert_id,
        rule_fingerprint=rule.dedup_fingerprint,
        idempotency_key_sha256=request_sha256,
        request_sha256=request_sha256,
        expected_version=expected_version,
        current_version=expected_version + 1,
        decision=decision,
        result_sha256=hashlib.sha256(result_json).hexdigest(),
        result_json=result_json,
    )


def entry_sha256(
    *,
    sequence: int,
    previous_entry_sha256: str,
    command: AlertPersistCommand,
) -> str:
    if (
        type(sequence) is not int
        or sequence < 1
        or _SHA256.fullmatch(previous_entry_sha256) is None
        or type(command) is not AlertPersistCommand
    ):
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.entry")
    return canonical_sha256(
        {
            "sequence": sequence,
            "previous_entry_sha256": previous_entry_sha256,
            "instance_key": command.instance_key,
            "alert_id": command.alert_id,
            "rule_fingerprint": command.rule_fingerprint,
            "idempotency_key_sha256": command.idempotency_key_sha256,
            "request_sha256": command.request_sha256,
            "expected_version": command.expected_version,
            "current_version": command.current_version,
            "state": command.decision.state.value,
            "outcome": command.decision.outcome.value,
            "reason": command.decision.reason.value,
            "pending_since_epoch_seconds": command.decision.pending_since_epoch_seconds,
            "result_sha256": command.result_sha256,
        }
    )


def validate_receipt(
    receipt: AlertPersistReceipt, command: AlertPersistCommand
) -> None:
    if (
        type(receipt) is not AlertPersistReceipt
        or type(command) is not AlertPersistCommand
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.receipt")
    if (
        receipt.instance_key != command.instance_key
        or receipt.current_version != command.current_version
        or receipt.request_sha256 != command.request_sha256
        or receipt.result_sha256 != command.result_sha256
        or receipt.entry_sha256
        != entry_sha256(
            sequence=receipt.sequence,
            previous_entry_sha256=receipt.previous_entry_sha256,
            command=command,
        )
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.receipt")


__all__ = [
    "ALERT_IDS",
    "AlertConditionState",
    "AlertDecision",
    "AlertHoldVariant",
    "AlertLifecycleState",
    "AlertObservation",
    "AlertPersistCommand",
    "AlertPersistReceipt",
    "AlertRule",
    "AlertSeverity",
    "AlertSnapshot",
    "AlertTransitionOutcome",
    "DataBlockReason",
    "EXPECTED_CONTRACT_SHA256",
    "EXPECTED_CATALOG_CANONICAL_SHA256",
    "HoldKind",
    "HoldVariant",
    "OWNER_ID",
    "PersistedAlertStep",
    "RUNBOOK_IDS",
    "RuntimeCatalog",
    "SLO_IDS",
    "SYNTHETIC_SOURCE",
    "SloAlertFailure",
    "SloAlertFailureCode",
    "SloEvaluation",
    "SloEvaluationState",
    "SloMetricWindow",
    "SloRule",
    "SloTargetKind",
    "ZERO_SHA256",
    "alert_instance_key",
    "canonical_bytes",
    "canonical_sha256",
    "compile_runtime_catalog",
    "entry_sha256",
    "evaluate_alert",
    "evaluate_slo",
    "fail",
    "make_persist_command",
    "validate_receipt",
]
