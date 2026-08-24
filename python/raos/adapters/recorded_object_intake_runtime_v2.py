"""Owner-private SQLite quarantine and deterministic recorded ST-0406 adapters."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tarfile
from threading import Lock
from typing import Mapping, NoReturn, cast, final
from uuid import UUID
import zipfile

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.object_intake import (
    DuplicateStatus,
    IntakeDescriptor,
    IntakePrivacyClass,
    ObjectIntakeKind,
    Sha256Digest,
)
from raos.domain.ops.object_intake_runtime_v2 import (
    ContentInspectionSummaryV2,
    DurableIntakeDescriptorV2,
    DurableIntakeState,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    IntakeFormat,
    IntakeRuntimePolicyV2,
    MalwareScanReceiptV2,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
    PrivacyClassificationReceiptV2,
    RecordedMalwareVerdict,
    RecordedPrivacyVerdict,
    RecoveredIntakeOutcomeV2,
    RejectedQuarantineReceiptV2,
    fail_intake_runtime,
)


_DATABASE_NAME = "secure-object-intake-runtime-v2.sqlite3"
_SCHEMA_VERSION = 2
_GENESIS = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_DOCUMENT_BYTES = 65_536
_MAX_SCRIPT_ROWS = 10_000
_ALLOWED_ENVIRONMENTS = {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
_EVENT_KINDS = frozenset({"OPEN", "APPEND", "SEAL", "ACCEPT", "REJECT"})
_FINAL_STATES = frozenset(
    {DurableIntakeState.CLEAN_QUARANTINED.value, DurableIntakeState.REJECTED.value}
)


_SCHEMA_OBJECTS: Mapping[str, str] = {
    "st0406_runtime_metadata": """
        CREATE TABLE st0406_runtime_metadata(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          schema_version INTEGER NOT NULL,
          event_count INTEGER NOT NULL CHECK(event_count>=0),
          event_head TEXT NOT NULL,
          record_sha256 TEXT NOT NULL
        )
    """,
    "st0406_quarantine": """
        CREATE TABLE st0406_quarantine(
          command_id TEXT PRIMARY KEY,
          request_digest TEXT NOT NULL,
          descriptor_digest TEXT NOT NULL,
          authorization_digest TEXT NOT NULL,
          intake_id TEXT NOT NULL UNIQUE,
          quarantine_id TEXT NOT NULL UNIQUE,
          site_id TEXT NOT NULL,
          authorization_resource_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          leaf_name TEXT NOT NULL,
          media_type TEXT NOT NULL,
          declared_size INTEGER NOT NULL CHECK(declared_size>0),
          declared_sha256 TEXT NOT NULL,
          privacy_class TEXT NOT NULL,
          state TEXT NOT NULL,
          version INTEGER NOT NULL CHECK(version>0),
          received_bytes INTEGER NOT NULL CHECK(received_bytes>=0),
          chunk_count INTEGER NOT NULL CHECK(chunk_count>=0),
          content BLOB NOT NULL,
          sealed_sha256 TEXT,
          failure_code TEXT,
          result_document TEXT,
          record_sha256 TEXT NOT NULL
        )
    """,
    "st0406_quarantine_event": """
        CREATE TABLE st0406_quarantine_event(
          sequence INTEGER PRIMARY KEY,
          command_id TEXT NOT NULL REFERENCES st0406_quarantine(command_id),
          version INTEGER NOT NULL CHECK(version>0),
          event_kind TEXT NOT NULL,
          event_document TEXT NOT NULL,
          previous_digest TEXT NOT NULL,
          digest TEXT NOT NULL UNIQUE,
          record_sha256 TEXT NOT NULL
        )
    """,
    "st0406_duplicate_index": """
        CREATE TABLE st0406_duplicate_index(
          sha256 TEXT PRIMARY KEY,
          intake_id TEXT NOT NULL UNIQUE,
          command_id TEXT NOT NULL UNIQUE REFERENCES st0406_quarantine(command_id),
          record_sha256 TEXT NOT NULL
        )
    """,
    "st0406_intake_result": """
        CREATE TABLE st0406_intake_result(
          command_id TEXT PRIMARY KEY REFERENCES st0406_quarantine(command_id),
          request_digest TEXT NOT NULL,
          descriptor_digest TEXT NOT NULL,
          authorization_digest TEXT NOT NULL,
          outcome TEXT NOT NULL,
          document TEXT NOT NULL,
          digest TEXT NOT NULL,
          record_sha256 TEXT NOT NULL
        )
    """,
    "st0406_event_no_update": """
        CREATE TRIGGER st0406_event_no_update
        BEFORE UPDATE ON st0406_quarantine_event
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_event_no_delete": """
        CREATE TRIGGER st0406_event_no_delete
        BEFORE DELETE ON st0406_quarantine_event
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_duplicate_no_update": """
        CREATE TRIGGER st0406_duplicate_no_update
        BEFORE UPDATE ON st0406_duplicate_index
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_duplicate_no_delete": """
        CREATE TRIGGER st0406_duplicate_no_delete
        BEFORE DELETE ON st0406_duplicate_index
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_result_no_update": """
        CREATE TRIGGER st0406_result_no_update
        BEFORE UPDATE ON st0406_intake_result
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_result_no_delete": """
        CREATE TRIGGER st0406_result_no_delete
        BEFORE DELETE ON st0406_intake_result
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
}


def _fail(code: ObjectIntakeRuntimeFailureCode) -> NoReturn:
    fail_intake_runtime(code)


def _recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in _ALLOWED_ENVIRONMENTS:
        _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
    return value


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _text(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > (1 << 63) - 1:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except TypeError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if len(encoded) > _MAX_DOCUMENT_BYTES:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return encoded


def _digest_document(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _row_digest(values: tuple[object, ...]) -> str:
    return _digest_document({"schema": "ST0406_ROW_V2", "values": values})


def _document(value: object) -> dict[str, object]:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _MAX_DOCUMENT_BYTES
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError, UnicodeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if type(parsed) is not dict:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    raw = cast(dict[object, object], parsed)
    if any(type(key) is not str for key in raw):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return {cast(str, key): item for key, item in raw.items()}


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    raw = cast(dict[object, object], value)
    if (
        any(type(key) is not str for key in raw)
        or frozenset(cast(str, key) for key in raw) != keys
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return {cast(str, key): item for key, item in raw.items()}


def _sql_normalized(value: str) -> str:
    return (
        " ".join(value.split()).replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    )


def _schema_is_exact(connection: sqlite3.Connection) -> bool:
    rows = connection.execute(
        "SELECT name,sql FROM sqlite_master "
        "WHERE type IN ('table','trigger') AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    observed = {str(name): _sql_normalized(str(sql)) for name, sql in rows}
    expected = {
        name: _sql_normalized(sql) for name, sql in sorted(_SCHEMA_OBJECTS.items())
    }
    version = connection.execute("PRAGMA user_version").fetchone()
    return (
        observed == expected
        and version is not None
        and tuple(version) == (_SCHEMA_VERSION,)
    )


def _metadata_values(event_count: int, event_head: str) -> tuple[object, ...]:
    return (1, _SCHEMA_VERSION, event_count, event_head)


def _event_digest(
    *,
    sequence: int,
    command_id: str,
    version: int,
    event_kind: str,
    event_document: str,
    previous_digest: str,
) -> str:
    return _digest_document(
        {
            "schema": "ST0406_EVENT_V2",
            "sequence": sequence,
            "command_id": command_id,
            "version": version,
            "event_kind": event_kind,
            "event_document_sha256": hashlib.sha256(
                event_document.encode("ascii")
            ).hexdigest(),
            "previous_digest": previous_digest,
        }
    )


def _quarantine_id(command_id: IntakeCommandId) -> UUID:
    raw = bytearray(hashlib.sha256(command_id.value.encode("ascii")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    value = UUID(bytes=bytes(raw))
    if value.int == 0:
        _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
    return value


def _descriptor_document(descriptor: DurableIntakeDescriptorV2) -> dict[str, object]:
    base = descriptor.descriptor
    return {
        "intake_id": str(base.intake_id),
        "site_id": str(base.site_id),
        "authorization_resource_id": str(descriptor.authorization_resource_id),
        "kind": base.kind.value,
        "leaf_name": base.leaf_name.value,
        "media_type": base.media_type.value,
        "declared_size": base.declared_size,
        "declared_sha256": base.declared_sha256.value,
        "privacy_class": base.privacy_class.value,
    }


def _inspection_document(value: ContentInspectionSummaryV2) -> dict[str, object]:
    return {
        "format": value.format.value,
        "archive_entry_count": value.archive_entry_count,
        "archive_uncompressed_bytes": value.archive_uncompressed_bytes,
        "csv_row_count": value.csv_row_count,
        "csv_column_count": value.csv_column_count,
        "csv_max_cell_bytes": value.csv_max_cell_bytes,
        "formula_prefix_safe": value.formula_prefix_safe,
    }


def _inspection_from_document(value: object) -> ContentInspectionSummaryV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "format",
                "archive_entry_count",
                "archive_uncompressed_bytes",
                "csv_row_count",
                "csv_column_count",
                "csv_max_cell_bytes",
                "formula_prefix_safe",
            }
        ),
    )
    try:
        format_value = IntakeFormat(_text(row["format"], maximum=16))
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    formula = row["formula_prefix_safe"]
    if type(formula) is not bool:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return ContentInspectionSummaryV2(
        format=format_value,
        archive_entry_count=_integer(row["archive_entry_count"]),
        archive_uncompressed_bytes=_integer(row["archive_uncompressed_bytes"]),
        csv_row_count=_integer(row["csv_row_count"]),
        csv_column_count=_integer(row["csv_column_count"]),
        csv_max_cell_bytes=_integer(row["csv_max_cell_bytes"]),
        formula_prefix_safe=formula,
    )


def _privacy_document(value: PrivacyClassificationReceiptV2) -> dict[str, object]:
    return {
        "verdict": value.verdict.value,
        "classified_as": None
        if value.classified_as is None
        else value.classified_as.value,
        "classifier_revision": value.classifier_revision,
    }


def _privacy_from_document(value: object) -> PrivacyClassificationReceiptV2:
    row = _exact_mapping(
        value, frozenset({"verdict", "classified_as", "classifier_revision"})
    )
    try:
        verdict = RecordedPrivacyVerdict(_text(row["verdict"], maximum=16))
        raw_class = row["classified_as"]
        classified = (
            None
            if raw_class is None
            else IntakePrivacyClass(_text(raw_class, maximum=32))
        )
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return PrivacyClassificationReceiptV2(
        verdict=verdict,
        classified_as=classified,
        classifier_revision=_text(row["classifier_revision"]),
    )


def _malware_document(value: MalwareScanReceiptV2) -> dict[str, object]:
    return {"verdict": value.verdict.value, "engine_revision": value.engine_revision}


def _malware_from_document(value: object) -> MalwareScanReceiptV2:
    row = _exact_mapping(value, frozenset({"verdict", "engine_revision"}))
    try:
        verdict = RecordedMalwareVerdict(_text(row["verdict"], maximum=16))
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return MalwareScanReceiptV2(
        verdict=verdict, engine_revision=_text(row["engine_revision"])
    )


def _accepted_document(receipt: DurableQuarantineReceiptV2) -> dict[str, object]:
    return {
        "schema": "ST0406_ACCEPTED_RECEIPT_V2",
        "command_id": receipt.command_id.value,
        "intake_id": str(receipt.intake_id),
        "quarantine_id": str(receipt.quarantine_id),
        "site_id": str(receipt.site_id),
        "authorization_resource_id": str(receipt.authorization_resource_id),
        "kind": receipt.kind.value,
        "state": receipt.state.value,
        "version": receipt.version,
        "received_bytes": receipt.received_bytes,
        "chunk_count": receipt.chunk_count,
        "sha256": receipt.sha256.value,
        "duplicate_status": receipt.duplicate_status.value,
        "duplicate_of_intake_id": (
            None
            if receipt.duplicate_of_intake_id is None
            else str(receipt.duplicate_of_intake_id)
        ),
        "inspection": _inspection_document(receipt.inspection),
        "privacy": _privacy_document(receipt.privacy),
        "malware": _malware_document(receipt.malware),
        "journal_head_sha256": receipt.journal_head_sha256,
    }


def _accepted_from_document(value: object) -> DurableQuarantineReceiptV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "schema",
                "command_id",
                "intake_id",
                "quarantine_id",
                "site_id",
                "authorization_resource_id",
                "kind",
                "state",
                "version",
                "received_bytes",
                "chunk_count",
                "sha256",
                "duplicate_status",
                "duplicate_of_intake_id",
                "inspection",
                "privacy",
                "malware",
                "journal_head_sha256",
            }
        ),
    )
    if row["schema"] != "ST0406_ACCEPTED_RECEIPT_V2":
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        intake_id = UUID(_text(row["intake_id"], maximum=36))
        quarantine_id = UUID(_text(row["quarantine_id"], maximum=36))
        site_id = UUID(_text(row["site_id"], maximum=36))
        authorization_resource_id = UUID(
            _text(row["authorization_resource_id"], maximum=36)
        )
        kind = ObjectIntakeKind(_text(row["kind"], maximum=32))
        state = DurableIntakeState(_text(row["state"], maximum=32))
        duplicate_status = DuplicateStatus(_text(row["duplicate_status"], maximum=32))
        raw_duplicate = row["duplicate_of_intake_id"]
        duplicate_id = (
            None if raw_duplicate is None else UUID(_text(raw_duplicate, maximum=36))
        )
    except ValueError, AttributeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return DurableQuarantineReceiptV2(
        command_id=IntakeCommandId(_text(row["command_id"])),
        intake_id=intake_id,
        quarantine_id=quarantine_id,
        site_id=site_id,
        authorization_resource_id=authorization_resource_id,
        kind=kind,
        state=state,
        version=_integer(row["version"], minimum=1),
        received_bytes=_integer(row["received_bytes"], minimum=1),
        chunk_count=_integer(row["chunk_count"], minimum=1),
        sha256=Sha256Digest(_sha(row["sha256"])),
        duplicate_status=duplicate_status,
        duplicate_of_intake_id=duplicate_id,
        inspection=_inspection_from_document(row["inspection"]),
        privacy=_privacy_from_document(row["privacy"]),
        malware=_malware_from_document(row["malware"]),
        journal_head_sha256=_sha(row["journal_head_sha256"]),
    )


def _rejected_document(receipt: RejectedQuarantineReceiptV2) -> dict[str, object]:
    return {
        "schema": "ST0406_REJECTED_RECEIPT_V2",
        "command_id": receipt.command_id.value,
        "intake_id": str(receipt.intake_id),
        "quarantine_id": str(receipt.quarantine_id),
        "state": receipt.state.value,
        "version": receipt.version,
        "failure_code": receipt.failure_code.value,
        "journal_head_sha256": receipt.journal_head_sha256,
    }


def _rejected_from_document(value: object) -> RejectedQuarantineReceiptV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "schema",
                "command_id",
                "intake_id",
                "quarantine_id",
                "state",
                "version",
                "failure_code",
                "journal_head_sha256",
            }
        ),
    )
    if row["schema"] != "ST0406_REJECTED_RECEIPT_V2":
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        return RejectedQuarantineReceiptV2(
            command_id=IntakeCommandId(_text(row["command_id"])),
            intake_id=UUID(_text(row["intake_id"], maximum=36)),
            quarantine_id=UUID(_text(row["quarantine_id"], maximum=36)),
            state=DurableIntakeState(_text(row["state"], maximum=32)),
            version=_integer(row["version"], minimum=1),
            failure_code=ObjectIntakeRuntimeFailureCode(
                _text(row["failure_code"], maximum=32)
            ),
            journal_head_sha256=_sha(row["journal_head_sha256"]),
        )
    except ValueError, AttributeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)


def _outcome_from_result_row(row: tuple[object, ...]) -> RecoveredIntakeOutcomeV2:
    if len(row) != 8:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    values = row[:-1]
    if _sha(row[-1]) != _row_digest(values):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    (
        command_id,
        request_digest,
        descriptor_digest,
        authorization_digest,
        outcome,
        document,
        result_digest,
    ) = values
    raw_document = _text(document, maximum=_MAX_DOCUMENT_BYTES)
    if _sha(result_digest) != hashlib.sha256(raw_document.encode("ascii")).hexdigest():
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    parsed = _document(raw_document)
    accepted: DurableQuarantineReceiptV2 | None = None
    rejected: RejectedQuarantineReceiptV2 | None = None
    if outcome == DurableIntakeState.CLEAN_QUARANTINED.value:
        accepted = _accepted_from_document(parsed)
    elif outcome == DurableIntakeState.REJECTED.value:
        rejected = _rejected_from_document(parsed)
    else:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if (accepted is not None and accepted.command_id.value != command_id) or (
        rejected is not None and rejected.command_id.value != command_id
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return RecoveredIntakeOutcomeV2(
        request_digest=_sha(request_digest),
        descriptor_digest=_sha(descriptor_digest),
        authorization_digest=_sha(authorization_digest),
        accepted=accepted,
        rejected=rejected,
    )


def _quarantine_values(row: sqlite3.Row) -> tuple[object, ...]:
    content = row["content"]
    if type(content) is not bytes:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return (
        row["command_id"],
        row["request_digest"],
        row["descriptor_digest"],
        row["authorization_digest"],
        row["intake_id"],
        row["quarantine_id"],
        row["site_id"],
        row["authorization_resource_id"],
        row["kind"],
        row["leaf_name"],
        row["media_type"],
        row["declared_size"],
        row["declared_sha256"],
        row["privacy_class"],
        row["state"],
        row["version"],
        row["received_bytes"],
        row["chunk_count"],
        hashlib.sha256(content).hexdigest(),
        row["sealed_sha256"],
        row["failure_code"],
        row["result_document"],
    )


@final
class RecordedMalwareScannerV2:
    """Digest-scripted scanner; it cannot contact or execute a scanner engine."""

    def __init__(
        self, scripts: tuple[tuple[Sha256Digest, MalwareScanReceiptV2], ...]
    ) -> None:
        if (
            type(scripts) is not tuple
            or not scripts
            or len(scripts) > _MAX_SCRIPT_ROWS
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not MalwareScanReceiptV2
                for row in scripts
            )
            or len({row[0] for row in scripts}) != len(scripts)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._scripts = scripts

    @property
    def action_count(self) -> int:
        return 0

    def scan(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> MalwareScanReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED)
        for expected, receipt in self._scripts:
            if expected == sha256:
                return receipt
        _fail(ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED)


@final
class DisabledMalwareScannerV2:
    @property
    def action_count(self) -> int:
        return 0

    def scan(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> MalwareScanReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.MALWARE_DISABLED)
        return MalwareScanReceiptV2(
            verdict=RecordedMalwareVerdict.UNAVAILABLE,
            engine_revision="DISABLED",
        )


@final
class RecordedPrivacyClassifierV2:
    def __init__(
        self,
        scripts: tuple[tuple[Sha256Digest, PrivacyClassificationReceiptV2], ...],
    ) -> None:
        if (
            type(scripts) is not tuple
            or not scripts
            or len(scripts) > _MAX_SCRIPT_ROWS
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not PrivacyClassificationReceiptV2
                for row in scripts
            )
            or len({row[0] for row in scripts}) != len(scripts)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._scripts = scripts

    @property
    def action_count(self) -> int:
        return 0

    def classify(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> PrivacyClassificationReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED)
        for expected, receipt in self._scripts:
            if expected == sha256:
                return receipt
        _fail(ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED)


def _safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith(("/", "~")):
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False
    return not (len(path.parts[0]) >= 2 and path.parts[0][1] == ":")


def _nested_archive(name: str, prefix: bytes) -> bool:
    lowered = name.lower()
    suffixes = (".zip", ".tar", ".tgz", ".tar.gz", ".gz")
    return (
        lowered.endswith(suffixes)
        or prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b"))
        or (len(prefix) >= 265 and prefix[257:262] == b"ustar")
    )


def _csv_summary(
    content: bytes, policy: IntakeRuntimePolicyV2
) -> ContentInspectionSummaryV2:
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if any(ord(character) < 32 and character not in "\r\n\t" for character in text):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if not rows or len(rows) > policy.max_csv_rows:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    width = len(rows[0])
    if (
        width == 0
        or width > policy.max_csv_columns
        or any(len(row) != width for row in rows)
    ):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if (
        any(not header or header != header.strip() for header in rows[0])
        or len(set(rows[0])) != width
    ):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    maximum = 0
    for row in rows:
        for cell in row:
            cell_bytes = len(cell.encode("utf-8"))
            maximum = max(maximum, cell_bytes)
            if cell_bytes > policy.max_csv_cell_bytes:
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            stripped = cell.lstrip(" \t\r\n")
            if stripped.startswith(("=", "+", "-", "@")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.CSV,
        archive_entry_count=0,
        archive_uncompressed_bytes=0,
        csv_row_count=len(rows),
        csv_column_count=width,
        csv_max_cell_bytes=maximum,
        formula_prefix_safe=True,
    )


def _zip_summary(
    content: bytes, policy: IntakeRuntimePolicyV2
) -> ContentInspectionSummaryV2:
    names: set[str] = set()
    total = 0
    count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
            for entry in archive.infolist():
                count += 1
                if count > policy.max_archive_entries or not _safe_archive_name(
                    entry.filename
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.filename in names or entry.flag_bits & 0x1:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                names.add(entry.filename)
                mode = (entry.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                total += entry.file_size
                if (
                    total > policy.max_archive_uncompressed_bytes
                    or entry.file_size
                    > max(entry.compress_size, 1) * policy.max_archive_ratio
                    or total > len(content) * policy.max_archive_ratio
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.is_dir():
                    continue
                with archive.open(entry, mode="r") as stream:
                    data = stream.read(policy.max_archive_uncompressed_bytes + 1)
                if (
                    len(data) != entry.file_size
                    or len(data) > policy.max_archive_uncompressed_bytes
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if _nested_archive(entry.filename, data[:512]):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    except ObjectIntakeRuntimeFailure:
        raise
    except OSError, RuntimeError, ValueError, zipfile.BadZipFile, NotImplementedError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if count == 0:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.ZIP,
        archive_entry_count=count,
        archive_uncompressed_bytes=total,
        csv_row_count=0,
        csv_column_count=0,
        csv_max_cell_bytes=0,
        formula_prefix_safe=True,
    )


def _tar_summary(
    content: bytes, policy: IntakeRuntimePolicyV2, *, compressed: bool
) -> ContentInspectionSummaryV2:
    names: set[str] = set()
    total = 0
    count = 0
    try:
        if compressed:
            with gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb") as probe:
                uncompressed_probe = probe.read(
                    policy.max_archive_uncompressed_bytes + 1
                )
            if len(uncompressed_probe) > policy.max_archive_uncompressed_bytes:
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            for entry in archive:
                count += 1
                if count > policy.max_archive_entries or not _safe_archive_name(
                    entry.name
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.name in names or entry.issym() or entry.islnk():
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                names.add(entry.name)
                if not (entry.isfile() or entry.isdir()):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                total += entry.size
                if (
                    total > policy.max_archive_uncompressed_bytes
                    or total > len(content) * policy.max_archive_ratio
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.isdir():
                    continue
                stream = archive.extractfile(entry)
                if stream is None:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                with stream:
                    data = stream.read(policy.max_archive_uncompressed_bytes + 1)
                if (
                    len(data) != entry.size
                    or len(data) > policy.max_archive_uncompressed_bytes
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if _nested_archive(entry.name, data[:512]):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    except ObjectIntakeRuntimeFailure:
        raise
    except gzip.BadGzipFile, OSError, EOFError, tarfile.TarError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if count == 0:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.TAR_GZIP if compressed else IntakeFormat.TAR,
        archive_entry_count=count,
        archive_uncompressed_bytes=total,
        csv_row_count=0,
        csv_column_count=0,
        csv_max_cell_bytes=0,
        formula_prefix_safe=True,
    )


@final
class DeterministicContentInspectorV2:
    """Closed local parser; archives are read from memory and never extracted."""

    @property
    def action_count(self) -> int:
        return 0

    def inspect(
        self,
        *,
        descriptor: IntakeDescriptor,
        content: bytes,
        policy: IntakeRuntimePolicyV2,
    ) -> ContentInspectionSummaryV2:
        if (
            type(descriptor) is not IntakeDescriptor
            or type(content) is not bytes
            or not content
            or type(policy) is not IntakeRuntimePolicyV2
            or len(content) != descriptor.declared_size
            or len(content) > policy.max_object_bytes
            or descriptor.media_type.value not in policy.allowed_media_types
        ):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        name = descriptor.leaf_name.value.lower()
        media = descriptor.media_type.value
        if name.endswith(".csv") and media == "text/csv":
            if content.startswith((b"PK", b"\x1f\x8b", b"%PDF")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _csv_summary(content, policy)
        if name.endswith(".zip") and media == "application/zip":
            if not content.startswith((b"PK\x03\x04", b"PK\x05\x06")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _zip_summary(content, policy)
        if name.endswith(".tar") and media == "application/x-tar":
            if len(content) < 265 or content[257:262] != b"ustar":
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _tar_summary(content, policy, compressed=False)
        if name.endswith((".tar.gz", ".tgz")) and media == "application/gzip":
            if not content.startswith(b"\x1f\x8b"):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _tar_summary(content, policy, compressed=True)
        binary: tuple[str, str, bytes, IntakeFormat] | None = None
        if name.endswith(".png"):
            binary = (".png", "image/png", b"\x89PNG\r\n\x1a\n", IntakeFormat.PNG)
        elif name.endswith((".jpg", ".jpeg")):
            binary = (".jpg", "image/jpeg", b"\xff\xd8\xff", IntakeFormat.JPEG)
        elif name.endswith(".webp"):
            if (
                media == "image/webp"
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            ):
                return ContentInspectionSummaryV2(
                    format=IntakeFormat.WEBP,
                    archive_entry_count=0,
                    archive_uncompressed_bytes=0,
                    csv_row_count=0,
                    csv_column_count=0,
                    csv_max_cell_bytes=0,
                    formula_prefix_safe=True,
                )
        elif name.endswith(".pdf"):
            binary = (".pdf", "application/pdf", b"%PDF-", IntakeFormat.PDF)
        if binary is None or media != binary[1] or not content.startswith(binary[2]):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        return ContentInspectionSummaryV2(
            format=binary[3],
            archive_entry_count=0,
            archive_uncompressed_bytes=0,
            csv_row_count=0,
            csv_column_count=0,
            csv_max_cell_bytes=0,
            formula_prefix_safe=True,
        )


class _InjectedCommitFault(RuntimeError):
    pass


class RecordedIntakeCommitFault(str):
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


@final
class RecordedSqliteObjectIntakeRepositoryV2:
    """Recorded-only durable quarantine with no byte read/export lifecycle API."""

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        fault_once_at: str | None = None,
    ) -> None:
        self._environment = _recorded_environment(environment)
        if fault_once_at not in {
            None,
            RecordedIntakeCommitFault.BEFORE_COMMIT,
            RecordedIntakeCommitFault.AFTER_COMMIT,
        }:
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._private_root = self._prepare_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._fault_once_at = fault_once_at
        self._fault_lock = Lock()
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @property
    def action_count(self) -> int:
        return 0

    @staticmethod
    def _prepare_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        root = Path(os.path.abspath(value))
        if not root.exists():
            parent = root.parent
            if not parent.exists():
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            RecordedSqliteObjectIntakeRepositoryV2._validate_ancestor_chain(parent)
            try:
                os.mkdir(root, 0o700)
            except OSError:
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        RecordedSqliteObjectIntakeRepositoryV2._validate_ancestor_chain(root)
        metadata = os.lstat(root)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        return root

    @staticmethod
    def _validate_ancestor_chain(path: Path) -> None:
        current_fd = os.open(
            "/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        )
        descriptors = [current_fd]
        try:
            for component in path.parts[1:]:
                named = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                    _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
                opened = os.fstat(child)
                if (
                    opened.st_dev != named.st_dev
                    or opened.st_ino != named.st_ino
                    or opened.st_mode != named.st_mode
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
                descriptors.append(child)
                current_fd = child
        except ObjectIntakeRuntimeFailure:
            raise
        except OSError:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def _create_or_validate_database_file(self) -> None:
        self._prepare_private_root(self._private_root)
        root_fd = os.open(
            self._private_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            os.close(descriptor)
        except ObjectIntakeRuntimeFailure:
            raise
        except OSError:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            os.close(root_fd)

    def _connect(self) -> sqlite3.Connection:
        self._create_or_validate_database_file()
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=10.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            self._create_or_validate_database_file()
            return connection
        except sqlite3.Error:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            present = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if not present:
                for sql in _SCHEMA_OBJECTS.values():
                    connection.execute(sql)
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                values = _metadata_values(0, _GENESIS)
                connection.execute(
                    "INSERT INTO st0406_runtime_metadata VALUES (?,?,?,?,?)",
                    (*values, _row_digest(values)),
                )
            if not _schema_is_exact(connection):
                _fail(ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT)
            self._validate_all(connection, allow_in_progress=False)
            connection.commit()
        except ObjectIntakeRuntimeFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            connection.close()

    def _validate_all(
        self, connection: sqlite3.Connection, *, allow_in_progress: bool
    ) -> None:
        if not _schema_is_exact(connection):
            _fail(ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or tuple(integrity) != ("ok",):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        metadata = connection.execute(
            "SELECT singleton,schema_version,event_count,event_head,record_sha256 "
            "FROM st0406_runtime_metadata"
        ).fetchall()
        if len(metadata) != 1:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        meta = tuple(metadata[0])
        if (
            len(meta) != 5
            or meta[0] != 1
            or meta[1] != _SCHEMA_VERSION
            or _integer(meta[2]) < 0
            or _sha(meta[3]) != meta[3]
            or _sha(meta[4]) != _row_digest(meta[:-1])
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        event_count = cast(int, meta[2])
        event_head = cast(str, meta[3])

        quarantine_rows = connection.execute(
            "SELECT * FROM st0406_quarantine ORDER BY command_id"
        ).fetchall()
        quarantine: dict[str, sqlite3.Row] = {}
        for row in quarantine_rows:
            values = _quarantine_values(row)
            if _sha(row["record_sha256"]) != _row_digest(values):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            command = _text(row["command_id"])
            try:
                UUID(_text(row["intake_id"], maximum=36))
                UUID(_text(row["quarantine_id"], maximum=36))
                UUID(_text(row["site_id"], maximum=36))
                UUID(_text(row["authorization_resource_id"], maximum=36))
                ObjectIntakeKind(_text(row["kind"], maximum=32))
                IntakePrivacyClass(_text(row["privacy_class"], maximum=32))
                state = DurableIntakeState(_text(row["state"], maximum=32))
            except ValueError, AttributeError:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            version = _integer(row["version"], minimum=1)
            received = _integer(row["received_bytes"])
            chunks = _integer(row["chunk_count"])
            declared = _integer(row["declared_size"], minimum=1)
            content = row["content"]
            _text(row["leaf_name"], maximum=128)
            _text(row["media_type"], maximum=127)
            if (
                _sha(row["request_digest"]) != row["request_digest"]
                or _sha(row["descriptor_digest"]) != row["descriptor_digest"]
                or _sha(row["authorization_digest"]) != row["authorization_digest"]
                or _sha(row["declared_sha256"]) != row["declared_sha256"]
                or type(content) is not bytes
                or len(content) != received
                or received > declared
                or (received == 0) != (chunks == 0)
                or (not allow_in_progress and state.value not in _FINAL_STATES)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state in {
                DurableIntakeState.SEALED,
                DurableIntakeState.CLEAN_QUARANTINED,
            } and (
                received != declared
                or _sha(row["sealed_sha256"]) != hashlib.sha256(content).hexdigest()
                or row["sealed_sha256"] != row["declared_sha256"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state is DurableIntakeState.CLEAN_QUARANTINED and (
                row["failure_code"] is not None or row["result_document"] is None
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state is DurableIntakeState.REJECTED and (
                row["failure_code"] is None or row["result_document"] is None
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            quarantine[command] = row

        previous = _GENESIS
        last_version: dict[str, int] = {}
        final_head: dict[str, str] = {}
        first_kind: set[str] = set()
        event_rows = connection.execute(
            "SELECT sequence,command_id,version,event_kind,event_document,"
            "previous_digest,digest,record_sha256 "
            "FROM st0406_quarantine_event ORDER BY sequence"
        ).fetchall()
        if len(event_rows) != event_count:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for expected_sequence, raw in enumerate(event_rows, start=1):
            row = tuple(raw)
            values = row[:-1]
            if row[0] != expected_sequence or _sha(row[-1]) != _row_digest(values):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            command = _text(row[1])
            version = _integer(row[2], minimum=1)
            kind = _text(row[3], maximum=16)
            event_document = _text(row[4], maximum=_MAX_DOCUMENT_BYTES)
            prior = _sha(row[5])
            digest = _sha(row[6])
            if (
                command not in quarantine
                or kind not in _EVENT_KINDS
                or prior != previous
                or digest
                != _event_digest(
                    sequence=expected_sequence,
                    command_id=command,
                    version=version,
                    event_kind=kind,
                    event_document=event_document,
                    previous_digest=prior,
                )
                or version != last_version.get(command, 0) + 1
                or (command not in first_kind and kind != "OPEN")
                or (command in first_kind and kind == "OPEN")
                or version > quarantine[command]["version"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            _document(event_document)
            first_kind.add(command)
            last_version[command] = version
            final_head[command] = digest
            previous = digest
        if previous != event_head or event_count != len(event_rows):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for command, row in quarantine.items():
            if last_version.get(command) != row["version"]:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        result_rows = connection.execute(
            "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
            "outcome,document,digest,record_sha256 FROM st0406_intake_result "
            "ORDER BY command_id"
        ).fetchall()
        results: dict[str, RecoveredIntakeOutcomeV2] = {}
        for raw in result_rows:
            outcome = _outcome_from_result_row(tuple(raw))
            command = _text(raw["command_id"])
            if command not in quarantine or command in results:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            projection = quarantine[command]
            if (
                projection["request_digest"] != outcome.request_digest
                or projection["descriptor_digest"] != outcome.descriptor_digest
                or projection["authorization_digest"] != outcome.authorization_digest
                or projection["result_document"] != raw["document"]
                or projection["state"] != raw["outcome"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            receipt = outcome.accepted or outcome.rejected
            if receipt is None or receipt.journal_head_sha256 != final_head.get(
                command
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            results[command] = outcome
        if not allow_in_progress and set(results) != set(quarantine):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        duplicate_rows = connection.execute(
            "SELECT sha256,intake_id,command_id,record_sha256 "
            "FROM st0406_duplicate_index ORDER BY sha256"
        ).fetchall()
        for raw in duplicate_rows:
            values = tuple(raw)[:-1]
            sha256, intake_id, command_id = values
            if (
                _sha(raw[-1]) != _row_digest(values)
                or _sha(sha256) != sha256
                or _text(command_id) not in results
                or results[_text(command_id)].accepted is None
                or quarantine[_text(command_id)]["intake_id"] != intake_id
                or quarantine[_text(command_id)]["sealed_sha256"] != sha256
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        command_id: str,
        version: int,
        event_kind: str,
        event: dict[str, object],
    ) -> str:
        meta = connection.execute(
            "SELECT singleton,schema_version,event_count,event_head,record_sha256 "
            "FROM st0406_runtime_metadata WHERE singleton=1"
        ).fetchone()
        if meta is None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        values = tuple(meta)
        if _sha(values[-1]) != _row_digest(values[:-1]):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        sequence = _integer(values[2]) + 1
        previous = _sha(values[3])
        document = _json_bytes(event).decode("ascii")
        digest = _event_digest(
            sequence=sequence,
            command_id=command_id,
            version=version,
            event_kind=event_kind,
            event_document=document,
            previous_digest=previous,
        )
        event_values = (
            sequence,
            command_id,
            version,
            event_kind,
            document,
            previous,
            digest,
        )
        connection.execute(
            "INSERT INTO st0406_quarantine_event VALUES (?,?,?,?,?,?,?,?)",
            (*event_values, _row_digest(event_values)),
        )
        metadata_values = _metadata_values(sequence, digest)
        cursor = connection.execute(
            "UPDATE st0406_runtime_metadata SET event_count=?,event_head=?,record_sha256=? "
            "WHERE singleton=1 AND event_count=? AND event_head=? AND record_sha256=?",
            (
                sequence,
                digest,
                _row_digest(metadata_values),
                values[2],
                previous,
                values[-1],
            ),
        )
        if cursor.rowcount != 1:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        return digest

    def _begin(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        descriptor_digest: str,
        authorization_digest: str,
        descriptor: DurableIntakeDescriptorV2,
    ) -> RecordedObjectIntakeUnitOfWorkV2:
        if (
            type(command_id) is not IntakeCommandId
            or type(descriptor) is not DurableIntakeDescriptorV2
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        for digest in (request_digest, descriptor_digest, authorization_digest):
            if type(digest) is not str or _SHA256.fullmatch(digest) is None:
                _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        if _digest_document(_descriptor_document(descriptor)) != descriptor_digest:
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        base = descriptor.descriptor
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection, allow_in_progress=False)
            existing = connection.execute(
                "SELECT request_digest,descriptor_digest,authorization_digest "
                "FROM st0406_quarantine WHERE command_id=?",
                (command_id.value,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (
                    request_digest,
                    descriptor_digest,
                    authorization_digest,
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
                outcome_row = connection.execute(
                    "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
                    "outcome,document,digest,record_sha256 FROM st0406_intake_result "
                    "WHERE command_id=?",
                    (command_id.value,),
                ).fetchone()
                if outcome_row is None:
                    _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
                return RecordedObjectIntakeUnitOfWorkV2(
                    repository=self,
                    connection=connection,
                    command_id=command_id,
                    existing=_outcome_from_result_row(tuple(outcome_row)),
                )
            collision = connection.execute(
                "SELECT command_id FROM st0406_quarantine WHERE intake_id=?",
                (str(base.intake_id),),
            ).fetchone()
            if collision is not None:
                _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
            quarantine_id = _quarantine_id(command_id)
            base_values = (
                command_id.value,
                request_digest,
                descriptor_digest,
                authorization_digest,
                str(base.intake_id),
                str(quarantine_id),
                str(base.site_id),
                str(descriptor.authorization_resource_id),
                base.kind.value,
                base.leaf_name.value,
                base.media_type.value,
                base.declared_size,
                base.declared_sha256.value,
                base.privacy_class.value,
                DurableIntakeState.OPEN.value,
                1,
                0,
                0,
                b"",
                None,
                None,
                None,
            )
            digest_values = (
                *base_values[:18],
                hashlib.sha256(b"").hexdigest(),
                *base_values[19:],
            )
            connection.execute(
                "INSERT INTO st0406_quarantine VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*base_values, _row_digest(digest_values)),
            )
            self._append_event(
                connection,
                command_id=command_id.value,
                version=1,
                event_kind="OPEN",
                event={
                    "schema": "ST0406_OPEN_V2",
                    "descriptor_digest": descriptor_digest,
                    "authorization_digest": authorization_digest,
                },
            )
            return RecordedObjectIntakeUnitOfWorkV2(
                repository=self,
                connection=connection,
                command_id=command_id,
                existing=None,
            )
        except ObjectIntakeRuntimeFailure:
            connection.rollback()
            connection.close()
            raise
        except sqlite3.Error:
            connection.rollback()
            connection.close()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            connection.rollback()
            connection.close()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def begin(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        descriptor_digest: str,
        authorization_digest: str,
        descriptor: DurableIntakeDescriptorV2,
    ) -> RecordedObjectIntakeUnitOfWorkV2:
        return self._begin(
            command_id=command_id,
            request_digest=request_digest,
            descriptor_digest=descriptor_digest,
            authorization_digest=authorization_digest,
            descriptor=descriptor,
        )

    def recover(
        self, *, command_id: IntakeCommandId, request_digest: str
    ) -> RecoveredIntakeOutcomeV2:
        if (
            type(command_id) is not IntakeCommandId
            or type(request_digest) is not str
            or _SHA256.fullmatch(request_digest) is None
        ):
            _fail(ObjectIntakeRuntimeFailureCode.RECOVERY_NOT_FOUND)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection, allow_in_progress=False)
            row = connection.execute(
                "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
                "outcome,document,digest,record_sha256 FROM st0406_intake_result "
                "WHERE command_id=?",
                (command_id.value,),
            ).fetchone()
            if row is None:
                _fail(ObjectIntakeRuntimeFailureCode.RECOVERY_NOT_FOUND)
            outcome = _outcome_from_result_row(tuple(row))
            if outcome.request_digest != request_digest:
                _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
            connection.rollback()
            return outcome
        except ObjectIntakeRuntimeFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            connection.close()

    def verify_integrity(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection, allow_in_progress=False)
            connection.rollback()
        except ObjectIntakeRuntimeFailure:
            connection.rollback()
            raise
        except Exception:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            connection.close()

    def _inject_fault(self, point: str) -> None:
        with self._fault_lock:
            if self._fault_once_at == point:
                self._fault_once_at = None
                raise _InjectedCommitFault("ST0406_RECORDED_COMMIT_FAULT")


@final
class RecordedObjectIntakeUnitOfWorkV2:
    def __init__(
        self,
        *,
        repository: RecordedSqliteObjectIntakeRepositoryV2,
        connection: sqlite3.Connection,
        command_id: IntakeCommandId,
        existing: RecoveredIntakeOutcomeV2 | None,
    ) -> None:
        self._repository = repository
        self._connection = connection
        self._command_id = command_id
        self._existing = existing
        self._closed = False
        self._finalized = existing is not None

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        return self._connection

    def existing(self) -> RecoveredIntakeOutcomeV2 | None:
        self._require_open()
        return self._existing

    def _projection(self) -> sqlite3.Row:
        row = (
            self._require_open()
            .execute(
                "SELECT * FROM st0406_quarantine WHERE command_id=?",
                (self._command_id.value,),
            )
            .fetchone()
        )
        if row is None or _sha(row["record_sha256"]) != _row_digest(
            _quarantine_values(row)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        return cast(sqlite3.Row, row)

    def _update_projection(
        self,
        row: sqlite3.Row,
        *,
        expected_version: int,
        state: DurableIntakeState,
        received_bytes: int,
        chunk_count: int,
        content: bytes,
        sealed_sha256: str | None,
        failure_code: str | None,
        result_document: str | None,
    ) -> int:
        if type(expected_version) is not int or expected_version != row["version"]:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        next_version = expected_version + 1
        base = (
            row["command_id"],
            row["request_digest"],
            row["descriptor_digest"],
            row["authorization_digest"],
            row["intake_id"],
            row["quarantine_id"],
            row["site_id"],
            row["authorization_resource_id"],
            row["kind"],
            row["leaf_name"],
            row["media_type"],
            row["declared_size"],
            row["declared_sha256"],
            row["privacy_class"],
            state.value,
            next_version,
            received_bytes,
            chunk_count,
            hashlib.sha256(content).hexdigest(),
            sealed_sha256,
            failure_code,
            result_document,
        )
        cursor = self._require_open().execute(
            "UPDATE st0406_quarantine SET state=?,version=?,received_bytes=?,"
            "chunk_count=?,content=?,sealed_sha256=?,failure_code=?,result_document=?,"
            "record_sha256=? WHERE command_id=? AND version=? AND record_sha256=?",
            (
                state.value,
                next_version,
                received_bytes,
                chunk_count,
                content,
                sealed_sha256,
                failure_code,
                result_document,
                _row_digest(base),
                self._command_id.value,
                expected_version,
                row["record_sha256"],
            ),
        )
        if cursor.rowcount != 1:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        return next_version

    def append(self, *, expected_version: int, chunk: bytes) -> int:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.OPEN.value
            or type(chunk) is not bytes
            or not chunk
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        content = row["content"]
        if type(content) is not bytes:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        combined = content + chunk
        if len(combined) > row["declared_size"]:
            _fail(ObjectIntakeRuntimeFailureCode.STREAM_LIMIT_EXCEEDED)
        next_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.OPEN,
            received_bytes=len(combined),
            chunk_count=row["chunk_count"] + 1,
            content=combined,
            sealed_sha256=None,
            failure_code=None,
            result_document=None,
        )
        self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="APPEND",
            event={
                "schema": "ST0406_APPEND_V2",
                "chunk_bytes": len(chunk),
                "chunk_sha256": hashlib.sha256(chunk).hexdigest(),
                "received_bytes": len(combined),
            },
        )
        return next_version

    def seal(
        self,
        *,
        expected_version: int,
        sha256: Sha256Digest,
        received_bytes: int,
        chunk_count: int,
    ) -> int:
        row = self._projection()
        content = row["content"]
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.OPEN.value
            or type(sha256) is not Sha256Digest
            or type(content) is not bytes
            or type(received_bytes) is not int
            or type(chunk_count) is not int
            or received_bytes != len(content)
            or received_bytes != row["received_bytes"]
            or received_bytes != row["declared_size"]
            or chunk_count != row["chunk_count"]
            or sha256.value != row["declared_sha256"]
            or sha256.value != hashlib.sha256(content).hexdigest()
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONTENT_MISMATCH)
        next_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.SEALED,
            received_bytes=received_bytes,
            chunk_count=chunk_count,
            content=content,
            sealed_sha256=sha256.value,
            failure_code=None,
            result_document=None,
        )
        self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="SEAL",
            event={
                "schema": "ST0406_SEAL_V2",
                "received_bytes": received_bytes,
                "chunk_count": chunk_count,
                "sha256": sha256.value,
            },
        )
        return next_version

    def reject(
        self,
        *,
        expected_version: int,
        failure_code: ObjectIntakeRuntimeFailureCode,
    ) -> RejectedQuarantineReceiptV2:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or type(failure_code) is not ObjectIntakeRuntimeFailureCode
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        content = row["content"]
        if type(content) is not bytes:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        next_version = expected_version + 1
        head = self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="REJECT",
            event={
                "schema": "ST0406_REJECT_V2",
                "failure_code": failure_code.value,
                "received_bytes": row["received_bytes"],
            },
        )
        receipt = RejectedQuarantineReceiptV2(
            command_id=self._command_id,
            intake_id=UUID(row["intake_id"]),
            quarantine_id=UUID(row["quarantine_id"]),
            state=DurableIntakeState.REJECTED,
            version=next_version,
            failure_code=failure_code,
            journal_head_sha256=head,
        )
        document = _json_bytes(_rejected_document(receipt)).decode("ascii")
        observed_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.REJECTED,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            content=content,
            sealed_sha256=row["sealed_sha256"],
            failure_code=failure_code.value,
            result_document=document,
        )
        if observed_version != next_version:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        self._insert_result(
            row=row, outcome=DurableIntakeState.REJECTED, document=document
        )
        self._finalized = True
        return receipt

    def accept(
        self,
        *,
        expected_version: int,
        inspection: ContentInspectionSummaryV2,
        privacy: PrivacyClassificationReceiptV2,
        malware: MalwareScanReceiptV2,
    ) -> DurableQuarantineReceiptV2:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.SEALED.value
            or type(inspection) is not ContentInspectionSummaryV2
            or type(privacy) is not PrivacyClassificationReceiptV2
            or privacy.verdict is not RecordedPrivacyVerdict.MATCH
            or privacy.classified_as is None
            or privacy.classified_as.value != row["privacy_class"]
            or type(malware) is not MalwareScanReceiptV2
            or malware.verdict is not RecordedMalwareVerdict.CLEAN
        ):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        duplicate = self._connection.execute(
            "SELECT intake_id FROM st0406_duplicate_index WHERE sha256=?",
            (row["sealed_sha256"],),
        ).fetchone()
        duplicate_status = (
            DuplicateStatus.NEW
            if duplicate is None
            else DuplicateStatus.EXACT_DUPLICATE
        )
        duplicate_id = None if duplicate is None else UUID(duplicate[0])
        next_version = expected_version + 1
        head = self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="ACCEPT",
            event={
                "schema": "ST0406_ACCEPT_V2",
                "inspection_sha256": _digest_document(_inspection_document(inspection)),
                "privacy_sha256": _digest_document(_privacy_document(privacy)),
                "malware_sha256": _digest_document(_malware_document(malware)),
                "duplicate_status": duplicate_status.value,
            },
        )
        receipt = DurableQuarantineReceiptV2(
            command_id=self._command_id,
            intake_id=UUID(row["intake_id"]),
            quarantine_id=UUID(row["quarantine_id"]),
            site_id=UUID(row["site_id"]),
            authorization_resource_id=UUID(row["authorization_resource_id"]),
            kind=ObjectIntakeKind(row["kind"]),
            state=DurableIntakeState.CLEAN_QUARANTINED,
            version=next_version,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            sha256=Sha256Digest(row["sealed_sha256"]),
            duplicate_status=duplicate_status,
            duplicate_of_intake_id=duplicate_id,
            inspection=inspection,
            privacy=privacy,
            malware=malware,
            journal_head_sha256=head,
        )
        document = _json_bytes(_accepted_document(receipt)).decode("ascii")
        observed_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.CLEAN_QUARANTINED,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            content=row["content"],
            sealed_sha256=row["sealed_sha256"],
            failure_code=None,
            result_document=document,
        )
        if observed_version != next_version:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        if duplicate is None:
            values = (row["sealed_sha256"], row["intake_id"], self._command_id.value)
            try:
                self._connection.execute(
                    "INSERT INTO st0406_duplicate_index VALUES (?,?,?,?)",
                    (*values, _row_digest(values)),
                )
            except sqlite3.IntegrityError:
                _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        self._insert_result(
            row=row,
            outcome=DurableIntakeState.CLEAN_QUARANTINED,
            document=document,
        )
        self._finalized = True
        return receipt

    def _insert_result(
        self, *, row: sqlite3.Row, outcome: DurableIntakeState, document: str
    ) -> None:
        values = (
            self._command_id.value,
            row["request_digest"],
            row["descriptor_digest"],
            row["authorization_digest"],
            outcome.value,
            document,
            hashlib.sha256(document.encode("ascii")).hexdigest(),
        )
        try:
            self._connection.execute(
                "INSERT INTO st0406_intake_result VALUES (?,?,?,?,?,?,?,?)",
                (*values, _row_digest(values)),
            )
        except sqlite3.IntegrityError:
            _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)

    def commit(self) -> None:
        if self._closed or (self._existing is None and not self._finalized):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        committed = False
        commit_started = False
        try:
            if self._existing is None:
                self._repository._validate_all(  # pyright: ignore[reportPrivateUsage]
                    self._connection, allow_in_progress=False
                )
            self._repository._inject_fault(  # pyright: ignore[reportPrivateUsage]
                RecordedIntakeCommitFault.BEFORE_COMMIT
            )
            commit_started = True
            self._connection.commit()
            committed = True
            self._repository._inject_fault(  # pyright: ignore[reportPrivateUsage]
                RecordedIntakeCommitFault.AFTER_COMMIT
            )
        except _InjectedCommitFault:
            if not committed:
                self._connection.rollback()
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if committed
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        except ObjectIntakeRuntimeFailure:
            if not committed:
                self._connection.rollback()
            raise
        except sqlite3.Error:
            if not committed:
                try:
                    self._connection.rollback()
                except sqlite3.Error:
                    pass
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        except Exception:
            if not committed:
                self._connection.rollback()
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        finally:
            self._closed = True
            self._connection.close()

    def rollback(self) -> None:
        if self._closed:
            return
        try:
            self._connection.rollback()
        except sqlite3.Error:
            pass
        finally:
            self._closed = True
            self._connection.close()


__all__ = [
    "DeterministicContentInspectorV2",
    "DisabledMalwareScannerV2",
    "RecordedIntakeCommitFault",
    "RecordedMalwareScannerV2",
    "RecordedObjectIntakeUnitOfWorkV2",
    "RecordedPrivacyClassifierV2",
    "RecordedSqliteObjectIntakeRepositoryV2",
]
