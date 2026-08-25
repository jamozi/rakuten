"""Strict fixture loader and process-local atomic adapter for ST-1302."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import stat
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final
from uuid import RFC_4122, UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.provider_fact_commit import (
    PROFILE,
    Currency,
    JpyAmount,
    LocalIdempotencyKey,
    ProviderEventKey,
    ProviderFactCommitFailureCode,
    ProviderFactCommitReason,
    ProviderFactCommitRequest,
    ProviderFactCommitResult,
    ProviderFactCommitRole,
    ProviderFactStatusSummary,
    RecordedAcceptedRevenueRow,
    RecordedMfaState,
    RecordedProviderFactCommitAuthorization,
    RecordedRevenueDryRunBundle,
    RecordedStepUpState,
    RecordedSubjectState,
    build_provider_fact_commit_result,
    fail_provider_fact_commit,
)
from raos.domain.finance.revenue_import import (
    FormulaDetectionStatus,
    RevenueDecision,
    RevenueDryRunState,
    RevenueEventType,
    RevenueExecutionStatus,
    RevenueFactStatus,
    RevenueMappingStatus,
    RevenueObservedSum,
    RevenueProviderCode,
    RevenueRowCode,
    RevenueRowParseStatus,
    RevenueRowPreview,
    RevenueSourceStatus,
    SyntheticPeriodLabel,
    SyntheticRevenueDryRun,
    SyntheticRevenuePeriod,
    SyntheticRevenueProfile,
    SyntheticRevenueSourceReference,
)
from raos.domain.ops.object_intake import Sha256Digest


_MAX_FIXTURE_BYTES: Final = 512 * 1024
_MAX_NODES: Final = 8192
_MAX_DEPTH: Final = 24
_ROOT_KEYS: Final = (
    "schema_version",
    "profile",
    "local_status",
    "scenario_id",
    "dry_run",
    "accepted_rows",
    "commit",
    "authorization",
    "authority",
)
_DRY_RUN_KEYS: Final = (
    "source",
    "state",
    "previews",
    "row_count",
    "accepted_count",
    "rejected_count",
    "duplicate_count",
    "ignored_count",
    "observed_sums",
    "period",
    "formula_detection",
    "source_status",
    "execution",
    "mapping",
    "reconciliation",
    "persistence",
    "audit",
    "outbox",
    "events",
    "facts",
    "tst026",
    "tst030",
    "decision",
    "provider_total_jpy",
    "revenue_import_id",
    "source_artifact_id",
    "approval_id",
)
_SOURCE_KEYS: Final = (
    "intake_id",
    "site_id",
    "source_sha256",
    "source_size",
    "profile",
    "command_fingerprint",
    "csv_row_count",
    "csv_column_count",
    "csv_max_cell_bytes",
    "is_dry_run",
)
_PREVIEW_KEYS: Final = (
    "row_no",
    "row_sha256",
    "status",
    "code",
    "event_type",
    "event_at",
    "generated_commission_jpy",
    "confirmed_commission_jpy",
)
_SUMMARY_KEYS: Final = (
    "event_type",
    "row_count",
    "generated_commission_jpy",
    "confirmed_commission_jpy",
    "confirmed_missing_count",
)
_PERIOD_KEYS: Final = ("label", "period_from", "period_to")
_ACCEPTED_ROW_KEYS: Final = (
    "row_no",
    "row_sha256",
    "provider_event_key",
    "event_type",
    "event_at",
    "generated_commission_jpy",
    "confirmed_commission_jpy",
)
_COMMIT_KEYS: Final = (
    "revenue_import_id",
    "expected_site_id",
    "expected_source_sha256",
    "expected_local_preview_binding_sha256",
    "expected_accepted_count",
    "expected_generated_commission_jpy",
    "expected_confirmed_commission_jpy",
    "expected_confirmed_missing_count",
    "expected_currency",
    "expected_period_from",
    "expected_period_to",
    "expected_status_summaries",
    "idempotency_key",
    "reason",
    "requested_at",
)
_AUTHORIZATION_KEYS: Final = (
    "principal_id",
    "site_id",
    "role",
    "subject_state",
    "mfa_state",
    "step_up_state",
    "step_up_authenticated_at",
    "authorized_at",
    "prepared_by_principal_id",
)
_AUTHORITY_KEYS: Final = (
    "recorded_synthetic_only",
    "database_write_authorized",
    "provider_call_authorized",
    "network_authorized",
    "publication_authorized",
    "live_authorized",
    "staging_authorized",
    "release_authorized",
    "production_authorized",
    "database",
    "provider",
    "network",
    "publication",
    "live",
    "staging",
    "release",
    "production",
)


class RecordedCommitMode(str, Enum):
    COMMIT = "COMMIT"
    FAIL_BEFORE_ATOMIC_SWAP = "FAIL_BEFORE_ATOMIC_SWAP"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1302-adapter>)"

    def __str__(self) -> str:
        return "<redacted-st1302-adapter>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded provider-fact adapter serialization is forbidden")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
        result[key] = value
    return result


def _mapping(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    result = cast(dict[str, object], value)
    if tuple(result) != keys:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return result


def _list(value: object, *, maximum: int = 10_000) -> list[object]:
    if type(value) is not list:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    result = cast(list[object], value)
    if len(result) > maximum:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return result


def _bounded_tree(value: object) -> None:
    remaining = _MAX_NODES

    def visit(current: object, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_DEPTH:
            fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
        if type(current) is dict:
            for key, child in cast(dict[object, object], current).items():
                if type(key) is not str:
                    fail_provider_fact_commit(
                        ProviderFactCommitFailureCode.FIXTURE_INVALID
                    )
                visit(child, depth + 1)
        elif type(current) is list:
            for child in cast(list[object], current):
                visit(child, depth + 1)
        elif current is not None and type(current) not in {str, int, bool}:
            fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)

    visit(value, 0)


def _string(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return value


def _integer(value: object, *, minimum: int = 0, maximum: int = (1 << 63) - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value)


def _uuid(value: object) -> UUID:
    try:
        parsed = UUID(_string(value, maximum=36))
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    if str(parsed) != value or parsed.version != 7 or parsed.variant != RFC_4122:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return parsed


def _sha(value: object) -> Sha256Digest:
    text = _string(value, maximum=64)
    try:
        return Sha256Digest(text)
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)


def _instant(value: object) -> datetime:
    text = _string(value, maximum=32)
    if not text.endswith("Z"):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    if parsed.tzinfo is not timezone.utc or parsed.microsecond != 0 or parsed.fold:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return parsed


def _date(value: object) -> date:
    text = _string(value, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    if parsed.isoformat() != text:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return parsed


def _amount(value: object) -> JpyAmount:
    text = _string(value, maximum=19)
    if not text.isascii() or not text.isdecimal() or (len(text) > 1 and text[0] == "0"):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    try:
        return JpyAmount(Decimal(text))
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)


def _optional_amount(value: object) -> JpyAmount | None:
    return None if value is None else _amount(value)


def _enum(enum_type: type[Enum], value: object) -> Enum:
    text = _string(value, maximum=128)
    try:
        observed = enum_type(text)
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return observed


def _preview(value: object) -> RevenueRowPreview:
    row = _mapping(value, _PREVIEW_KEYS)
    event_type = (
        None
        if row["event_type"] is None
        else cast(RevenueEventType, _enum(RevenueEventType, row["event_type"]))
    )
    event_at = None if row["event_at"] is None else _instant(row["event_at"])
    return RevenueRowPreview(
        row_no=_integer(row["row_no"], minimum=2, maximum=10_001),
        row_sha256=_sha(row["row_sha256"]),
        status=cast(
            RevenueRowParseStatus,
            _enum(RevenueRowParseStatus, row["status"]),
        ),
        code=cast(RevenueRowCode, _enum(RevenueRowCode, row["code"])),
        event_type=event_type,
        event_at=event_at,
        generated_commission_jpy=_optional_integer(row["generated_commission_jpy"]),
        confirmed_commission_jpy=_optional_integer(row["confirmed_commission_jpy"]),
    )


def _observed_sum(value: object) -> RevenueObservedSum:
    row = _mapping(value, _SUMMARY_KEYS)
    return RevenueObservedSum(
        event_type=cast(RevenueEventType, _enum(RevenueEventType, row["event_type"])),
        row_count=_integer(row["row_count"], maximum=10_000),
        generated_commission_jpy=_integer(row["generated_commission_jpy"]),
        confirmed_commission_jpy=_optional_integer(row["confirmed_commission_jpy"]),
        confirmed_missing_count=_integer(
            row["confirmed_missing_count"], maximum=10_000
        ),
    )


def _dry_run(value: object) -> SyntheticRevenueDryRun:
    row = _mapping(value, _DRY_RUN_KEYS)
    source = _mapping(row["source"], _SOURCE_KEYS)
    period = _mapping(row["period"], _PERIOD_KEYS)
    return SyntheticRevenueDryRun(
        source=SyntheticRevenueSourceReference(
            intake_id=_uuid(source["intake_id"]),
            site_id=_uuid(source["site_id"]),
            source_sha256=_sha(source["source_sha256"]),
            source_size=_integer(source["source_size"], minimum=1),
            profile=cast(
                SyntheticRevenueProfile,
                _enum(SyntheticRevenueProfile, source["profile"]),
            ),
            command_fingerprint=_sha(source["command_fingerprint"]),
            csv_row_count=_integer(source["csv_row_count"], minimum=2),
            csv_column_count=_integer(source["csv_column_count"], minimum=1),
            csv_max_cell_bytes=_integer(source["csv_max_cell_bytes"], minimum=1),
            is_dry_run=source["is_dry_run"] is True,
        ),
        state=cast(RevenueDryRunState, _enum(RevenueDryRunState, row["state"])),
        previews=tuple(_preview(item) for item in _list(row["previews"])),
        row_count=_integer(row["row_count"], maximum=10_000),
        accepted_count=_integer(row["accepted_count"], maximum=10_000),
        rejected_count=_integer(row["rejected_count"], maximum=10_000),
        duplicate_count=_integer(row["duplicate_count"], maximum=10_000),
        ignored_count=_integer(row["ignored_count"], maximum=10_000),
        observed_sums=tuple(
            _observed_sum(item) for item in _list(row["observed_sums"], maximum=4)
        ),
        period=SyntheticRevenuePeriod(
            label=cast(
                SyntheticPeriodLabel,
                _enum(SyntheticPeriodLabel, period["label"]),
            ),
            period_from=(
                None if period["period_from"] is None else _date(period["period_from"])
            ),
            period_to=(
                None if period["period_to"] is None else _date(period["period_to"])
            ),
        ),
        formula_detection=cast(
            FormulaDetectionStatus,
            _enum(FormulaDetectionStatus, row["formula_detection"]),
        ),
        source_status=cast(
            RevenueSourceStatus,
            _enum(RevenueSourceStatus, row["source_status"]),
        ),
        execution=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["execution"]),
        ),
        mapping=cast(
            RevenueMappingStatus,
            _enum(RevenueMappingStatus, row["mapping"]),
        ),
        reconciliation=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["reconciliation"]),
        ),
        persistence=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["persistence"]),
        ),
        audit=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["audit"]),
        ),
        outbox=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["outbox"]),
        ),
        events=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["events"]),
        ),
        facts=cast(RevenueFactStatus, _enum(RevenueFactStatus, row["facts"])),
        tst026=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["tst026"]),
        ),
        tst030=cast(
            RevenueExecutionStatus,
            _enum(RevenueExecutionStatus, row["tst030"]),
        ),
        decision=cast(RevenueDecision, _enum(RevenueDecision, row["decision"])),
        provider_total_jpy=(
            None
            if row["provider_total_jpy"] is None
            else _integer(row["provider_total_jpy"])
        ),
        revenue_import_id=(
            None
            if row["revenue_import_id"] is None
            else _uuid(row["revenue_import_id"])
        ),
        source_artifact_id=(
            None
            if row["source_artifact_id"] is None
            else _uuid(row["source_artifact_id"])
        ),
        approval_id=(None if row["approval_id"] is None else _uuid(row["approval_id"])),
    )


def _accepted_row(value: object) -> RecordedAcceptedRevenueRow:
    row = _mapping(value, _ACCEPTED_ROW_KEYS)
    return RecordedAcceptedRevenueRow(
        row_no=_integer(row["row_no"], minimum=2, maximum=10_001),
        row_sha256=_sha(row["row_sha256"]),
        provider_event_key=ProviderEventKey(_string(row["provider_event_key"])),
        event_type=cast(RevenueEventType, _enum(RevenueEventType, row["event_type"])),
        event_at=_instant(row["event_at"]),
        generated_commission_jpy=_amount(row["generated_commission_jpy"]),
        confirmed_commission_jpy=_optional_amount(row["confirmed_commission_jpy"]),
    )


def _status_summary(value: object) -> ProviderFactStatusSummary:
    row = _mapping(value, _SUMMARY_KEYS)
    return ProviderFactStatusSummary(
        event_type=cast(RevenueEventType, _enum(RevenueEventType, row["event_type"])),
        row_count=_integer(row["row_count"], maximum=10_000),
        generated_commission_jpy=_amount(row["generated_commission_jpy"]),
        confirmed_commission_jpy=_optional_amount(row["confirmed_commission_jpy"]),
        confirmed_missing_count=_integer(
            row["confirmed_missing_count"], maximum=10_000
        ),
    )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedProviderFactCommitScenario(_Redacted):
    scenario_id: str
    fixture_sha256: Sha256Digest
    bundle: RecordedRevenueDryRunBundle
    request: ProviderFactCommitRequest
    authorization: RecordedProviderFactCommitAuthorization

    def __post_init__(self) -> None:
        if (
            type(self.scenario_id) is not str
            or self.scenario_id != "ST1302-RECORDED-SYNTHETIC-0001"
            or type(self.fixture_sha256) is not Sha256Digest
            or type(self.bundle) is not RecordedRevenueDryRunBundle
            or type(self.request) is not ProviderFactCommitRequest
            or type(self.authorization) is not RecordedProviderFactCommitAuthorization
        ):
            fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
        build_provider_fact_commit_result(
            request=self.request,
            bundle=self.bundle,
            authorization=self.authorization,
        )


def _read_fixture(path: object) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute():
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
        content = path.read_bytes()
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    if not content or len(content) > _MAX_FIXTURE_BYTES:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return content


def load_recorded_provider_fact_commit_fixture(
    path: object,
) -> RecordedProviderFactCommitScenario:
    """Load one bounded tracked synthetic scenario without paths or provider I/O."""

    content = _read_fixture(path)
    try:
        value = json.loads(content, object_pairs_hook=_pairs)
    except Exception:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    _bounded_tree(value)
    root = _mapping(value, _ROOT_KEYS)
    if (
        root["schema_version"] != "1.0.0"
        or root["profile"] != PROFILE
        or root["local_status"] != "RECORDED_SYNTHETIC_ONLY"
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    dry_run = _dry_run(root["dry_run"])
    accepted_rows = tuple(_accepted_row(item) for item in _list(root["accepted_rows"]))
    authorization_row = _mapping(root["authorization"], _AUTHORIZATION_KEYS)
    bundle = RecordedRevenueDryRunBundle(
        dry_run=dry_run,
        accepted_rows=accepted_rows,
        prepared_by_principal_id=_uuid(authorization_row["prepared_by_principal_id"]),
    )
    commit = _mapping(root["commit"], _COMMIT_KEYS)
    request = ProviderFactCommitRequest(
        revenue_import_id=_uuid(commit["revenue_import_id"]),
        expected_site_id=_uuid(commit["expected_site_id"]),
        expected_source_sha256=_sha(commit["expected_source_sha256"]),
        expected_local_preview_binding_sha256=_sha(
            commit["expected_local_preview_binding_sha256"]
        ),
        expected_accepted_count=_integer(
            commit["expected_accepted_count"], minimum=1, maximum=10_000
        ),
        expected_generated_commission_jpy=_amount(
            commit["expected_generated_commission_jpy"]
        ),
        expected_confirmed_commission_jpy=_optional_amount(
            commit["expected_confirmed_commission_jpy"]
        ),
        expected_confirmed_missing_count=_integer(
            commit["expected_confirmed_missing_count"], maximum=10_000
        ),
        expected_currency=cast(Currency, _enum(Currency, commit["expected_currency"])),
        expected_period_from=_date(commit["expected_period_from"]),
        expected_period_to=_date(commit["expected_period_to"]),
        expected_status_summaries=tuple(
            _status_summary(item)
            for item in _list(commit["expected_status_summaries"], maximum=4)
        ),
        idempotency_key=LocalIdempotencyKey(_string(commit["idempotency_key"])),
        reason=ProviderFactCommitReason(_string(commit["reason"], maximum=1000)),
        requested_at=_instant(commit["requested_at"]),
    )
    authorization = RecordedProviderFactCommitAuthorization(
        request_sha256=request.request_sha256,
        principal_id=_uuid(authorization_row["principal_id"]),
        site_id=_uuid(authorization_row["site_id"]),
        role=cast(
            ProviderFactCommitRole,
            _enum(ProviderFactCommitRole, authorization_row["role"]),
        ),
        subject_state=cast(
            RecordedSubjectState,
            _enum(RecordedSubjectState, authorization_row["subject_state"]),
        ),
        mfa_state=cast(
            RecordedMfaState,
            _enum(RecordedMfaState, authorization_row["mfa_state"]),
        ),
        step_up_state=cast(
            RecordedStepUpState,
            _enum(RecordedStepUpState, authorization_row["step_up_state"]),
        ),
        step_up_authenticated_at=_instant(
            authorization_row["step_up_authenticated_at"]
        ),
        authorized_at=_instant(authorization_row["authorized_at"]),
        prepared_by_principal_id=_uuid(authorization_row["prepared_by_principal_id"]),
    )
    authority = _mapping(root["authority"], _AUTHORITY_KEYS)
    if authority != {
        "recorded_synthetic_only": True,
        "database_write_authorized": False,
        "provider_call_authorized": False,
        "network_authorized": False,
        "publication_authorized": False,
        "live_authorized": False,
        "staging_authorized": False,
        "release_authorized": False,
        "production_authorized": False,
        "database": "NOT_EXECUTED",
        "provider": "NOT_EXECUTED",
        "network": "NOT_EXECUTED",
        "publication": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    scenario = RecordedProviderFactCommitScenario(
        scenario_id=_string(root["scenario_id"], maximum=64),
        fixture_sha256=Sha256Digest(hashlib.sha256(content).hexdigest()),
        bundle=bundle,
        request=request,
        authorization=authorization,
    )
    if (
        request.expected_local_preview_binding_sha256
        != bundle.local_preview_binding_sha256
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.FIXTURE_INVALID)
    return scenario


@dataclass(frozen=True, slots=True, repr=False)
class RecordedProviderFactStoreSnapshot(_Redacted):
    replay_count: int
    source_count: int
    fact_count: int
    commission_event_count: int
    audit_count: int
    outbox_count: int
    result_sha256s: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        for value in (
            self.replay_count,
            self.source_count,
            self.fact_count,
            self.commission_event_count,
            self.audit_count,
            self.outbox_count,
        ):
            if type(value) is not int or value < 0:
                fail_provider_fact_commit()
        if type(self.result_sha256s) is not tuple or any(
            type(value) is not Sha256Digest for value in self.result_sha256s
        ):
            fail_provider_fact_commit()


def _same_request(
    left: ProviderFactCommitRequest,
    right: ProviderFactCommitRequest,
) -> bool:
    return (
        type(left) is ProviderFactCommitRequest
        and type(right) is ProviderFactCommitRequest
        and left.canonical_bytes() == right.canonical_bytes()
    )


def _same_bundle(
    left: RecordedRevenueDryRunBundle,
    right: RecordedRevenueDryRunBundle,
) -> bool:
    return (
        type(left) is RecordedRevenueDryRunBundle
        and type(right) is RecordedRevenueDryRunBundle
        and left.local_preview_binding_sha256 == right.local_preview_binding_sha256
        and left.prepared_by_principal_id == right.prepared_by_principal_id
        and left == right
    )


@final
class RecordedProviderFactCommitAdapter(_Redacted):
    """One scripted authorization plus process-local atomic commit/replay."""

    __slots__ = ("_scenario", "_mode", "_replays", "_sources", "_lock")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        scenario: RecordedProviderFactCommitScenario,
        mode: RecordedCommitMode = RecordedCommitMode.COMMIT,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(scenario) is not RecordedProviderFactCommitScenario
            or type(mode) is not RecordedCommitMode
        ):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._scenario = scenario
        self._mode = mode
        self._replays: dict[str, tuple[bytes, ProviderFactCommitResult]] = {}
        self._sources: dict[str, ProviderFactCommitResult] = {}
        self._lock = RLock()

    def authorize(
        self,
        request: ProviderFactCommitRequest,
        bundle: RecordedRevenueDryRunBundle,
    ) -> RecordedProviderFactCommitAuthorization:
        if (
            type(request) is not ProviderFactCommitRequest
            or type(bundle) is not RecordedRevenueDryRunBundle
            or not _same_request(request, self._scenario.request)
            or not _same_bundle(bundle, self._scenario.bundle)
        ):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.AUTHORIZATION_INVALID
            )
        return self._scenario.authorization

    def commit(
        self,
        request: ProviderFactCommitRequest,
        bundle: RecordedRevenueDryRunBundle,
        authorization: RecordedProviderFactCommitAuthorization,
    ) -> ProviderFactCommitResult:
        if (
            type(request) is not ProviderFactCommitRequest
            or type(bundle) is not RecordedRevenueDryRunBundle
            or type(authorization) is not RecordedProviderFactCommitAuthorization
        ):
            fail_provider_fact_commit()
        identity = request.idempotency_key.sha256.value
        source_identity = hashlib.sha256(
            (
                str(request.expected_site_id)
                + PROVIDER_CODE_LITERAL
                + request.expected_source_sha256.value
            ).encode("ascii")
        ).hexdigest()
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                retained_request, retained_result = replay
                if request.canonical_bytes() != retained_request:
                    fail_provider_fact_commit(
                        ProviderFactCommitFailureCode.IDEMPOTENCY_CONFLICT
                    )
                if (
                    not _same_bundle(bundle, self._scenario.bundle)
                    or authorization.canonical_bytes()
                    != self._scenario.authorization.canonical_bytes()
                ):
                    fail_provider_fact_commit(
                        ProviderFactCommitFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
                    )
                expected_replay = build_provider_fact_commit_result(
                    request=request,
                    bundle=bundle,
                    authorization=authorization,
                )
                if (
                    expected_replay != retained_result
                    or expected_replay.canonical_bytes()
                    != retained_result.canonical_bytes()
                ):
                    fail_provider_fact_commit(
                        ProviderFactCommitFailureCode.OUTCOME_MISMATCH
                    )
                return retained_result
            if source_identity in self._sources:
                fail_provider_fact_commit(
                    ProviderFactCommitFailureCode.SOURCE_ALREADY_COMMITTED
                )
            if (
                not _same_request(request, self._scenario.request)
                or not _same_bundle(bundle, self._scenario.bundle)
                or authorization.canonical_bytes()
                != self._scenario.authorization.canonical_bytes()
            ):
                fail_provider_fact_commit(
                    ProviderFactCommitFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
                )
            result = build_provider_fact_commit_result(
                request=request,
                bundle=bundle,
                authorization=authorization,
            )
            if self._mode is RecordedCommitMode.FAIL_BEFORE_ATOMIC_SWAP:
                fail_provider_fact_commit(
                    ProviderFactCommitFailureCode.ATOMIC_COMMIT_UNAVAILABLE
                )
            next_replays = dict(self._replays)
            next_sources = dict(self._sources)
            next_replays[identity] = (request.canonical_bytes(), result)
            next_sources[source_identity] = result
            self._replays = next_replays
            self._sources = next_sources
            return result

    def snapshot(self) -> RecordedProviderFactStoreSnapshot:
        with self._lock:
            results = tuple(self._sources.values())
            return RecordedProviderFactStoreSnapshot(
                replay_count=len(self._replays),
                source_count=len(self._sources),
                fact_count=sum(len(result.facts) for result in results),
                commission_event_count=sum(
                    len(result.commission_events) for result in results
                ),
                audit_count=len(results),
                outbox_count=sum(len(result.outbox) for result in results),
                result_sha256s=tuple(
                    sorted(
                        (result.result_sha256 for result in results),
                        key=lambda value: value.value,
                    )
                ),
            )


PROVIDER_CODE_LITERAL: Final = RevenueProviderCode.RAKUTEN_AFFILIATE.value


__all__ = (
    "RecordedCommitMode",
    "RecordedProviderFactCommitAdapter",
    "RecordedProviderFactCommitScenario",
    "RecordedProviderFactStoreSnapshot",
    "load_recorded_provider_fact_commit_fixture",
)
