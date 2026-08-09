"""Fail-closed application service for TEST_ONLY quarantine intake."""

from __future__ import annotations

import hashlib
from typing import NoReturn, final

from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.ops.object_intake import (
    DuplicateInspectionRecord,
    DuplicateStatus,
    InspectionStatus,
    IntakeDescriptor,
    IntakeOutcome,
    IntakePolicy,
    MalwareInspectionRecord,
    MalwareStatus,
    ObjectInspectionReport,
    ObjectIntakeFailureCode,
    ObjectIntakeResult,
    QuarantineDisposition,
    QuarantineRecord,
    QuarantineStatus,
    Sha256Digest,
    fail_object_intake,
)
from raos.ports.object_intake import (
    AppendOnlyQuarantine,
    BoundedChunkReader,
    DuplicateRegistry,
    MalwareScanner,
    ObjectInspector,
)


_UPLOAD_ACTION = "artifact:upload"


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class ObjectIntakeService:
    """Stream once into quarantine and return success only after every check."""

    __slots__ = ("_duplicate", "_inspector", "_malware", "_policy", "_quarantine")

    def __init__(
        self,
        *,
        policy: IntakePolicy,
        quarantine: AppendOnlyQuarantine,
        inspector: ObjectInspector,
        malware: MalwareScanner,
        duplicate_registry: DuplicateRegistry,
    ) -> None:
        if (
            type(policy) is not IntakePolicy
            or not _implements(quarantine, AppendOnlyQuarantine)
            or not _implements(inspector, ObjectInspector)
            or not _implements(malware, MalwareScanner)
            or not _implements(duplicate_registry, DuplicateRegistry)
        ):
            fail_object_intake()
        self._policy = policy
        self._quarantine = quarantine
        self._inspector = inspector
        self._malware = malware
        self._duplicate = duplicate_registry

    def _authorize(self, grant: object, descriptor: object, source: object) -> None:
        if (
            type(grant) is not AuthorizationGrant
            or type(descriptor) is not IntakeDescriptor
            or not _implements(source, BoundedChunkReader)
            or grant.action.value != _UPLOAD_ACTION
            or grant.target.scope.site_id != descriptor.site_id
            or descriptor.media_type not in self._policy.allowed_media_types
            or descriptor.privacy_class not in self._policy.allowed_privacy_classes
            or descriptor.declared_size > self._policy.max_object_bytes
        ):
            fail_object_intake(ObjectIntakeFailureCode.NOT_AUTHORIZED)

    def _reject(self, record: QuarantineRecord | None) -> None:
        if type(record) is not QuarantineRecord:
            return
        try:
            self._quarantine.record_disposition(
                record,
                disposition=QuarantineDisposition.REJECTED,
            )
        except Exception:
            pass

    def _fail_after_reject(
        self,
        record: QuarantineRecord | None,
        code: ObjectIntakeFailureCode,
    ) -> NoReturn:
        self._reject(record)
        fail_object_intake(code)

    def _require_record_transition(
        self,
        observed: object,
        *,
        previous: QuarantineRecord,
        status: QuarantineStatus,
        received_bytes: int,
        chunk_count: int,
    ) -> QuarantineRecord:
        if (
            type(observed) is not QuarantineRecord
            or observed.intake_id != previous.intake_id
            or observed.quarantine_id != previous.quarantine_id
            or observed.status is not status
            or observed.received_bytes != received_bytes
            or observed.chunk_count != chunk_count
        ):
            self._fail_after_reject(previous, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        return observed

    def _stream_and_seal(
        self,
        descriptor: IntakeDescriptor,
        source: BoundedChunkReader,
        record: QuarantineRecord,
    ) -> tuple[QuarantineRecord, Sha256Digest]:
        total = 0
        chunks = 0
        digest = hashlib.sha256()
        current = record
        while True:
            chunk: object = None
            source_failed = False
            try:
                chunk = source.read_chunk(maximum_bytes=self._policy.max_chunk_bytes)
            except Exception:
                source_failed = True
            if (
                source_failed
                or type(chunk) is not bytes
                or len(chunk) > self._policy.max_chunk_bytes
            ):
                self._fail_after_reject(current, ObjectIntakeFailureCode.SOURCE_FAILED)
            if chunk == b"":
                break
            chunks += 1
            total += len(chunk)
            if (
                chunks > self._policy.max_chunk_count
                or total > self._policy.max_object_bytes
                or total > descriptor.declared_size
            ):
                self._fail_after_reject(
                    current, ObjectIntakeFailureCode.STREAM_LIMIT_EXCEEDED
                )
            observed: object = None
            append_failed = False
            try:
                observed = self._quarantine.append(current, chunk)
            except Exception:
                append_failed = True
            if append_failed:
                self._fail_after_reject(
                    current, ObjectIntakeFailureCode.QUARANTINE_FAILED
                )
            current = self._require_record_transition(
                observed,
                previous=current,
                status=QuarantineStatus.OPEN,
                received_bytes=total,
                chunk_count=chunks,
            )
            digest.update(chunk)
        computed = Sha256Digest(digest.hexdigest())
        if total != descriptor.declared_size or computed != descriptor.declared_sha256:
            self._fail_after_reject(current, ObjectIntakeFailureCode.CONTENT_MISMATCH)
        observed = None
        seal_failed = False
        try:
            observed = self._quarantine.seal(current, sha256=computed, size=total)
        except Exception:
            seal_failed = True
        if seal_failed:
            self._fail_after_reject(current, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        sealed = self._require_record_transition(
            observed,
            previous=current,
            status=QuarantineStatus.SEALED,
            received_bytes=total,
            chunk_count=chunks,
        )
        if sealed.sealed_sha256 != computed or sealed.disposition is not None:
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        return sealed, computed

    def _inspect(
        self,
        descriptor: IntakeDescriptor,
        sealed: QuarantineRecord,
    ) -> ObjectInspectionReport:
        report: object = None
        inspection_failed = False
        try:
            report = self._inspector.inspect(descriptor, sealed)
        except Exception:
            inspection_failed = True
        if inspection_failed:
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.INSPECTION_FAILED)
        if type(report) is not ObjectInspectionReport:
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.INSPECTION_FAILED)
        if (
            report.magic.status is not InspectionStatus.SAFE
            or report.archive.status
            not in {InspectionStatus.SAFE, InspectionStatus.NOT_APPLICABLE}
            or report.csv.status
            not in {InspectionStatus.SAFE, InspectionStatus.NOT_APPLICABLE}
            or report.privacy.status is not InspectionStatus.SAFE
            or report.privacy.privacy_class is not descriptor.privacy_class
            or report.archive.entry_count > self._policy.max_archive_entries
            or report.archive.uncompressed_bytes
            > self._policy.max_archive_uncompressed_bytes
            or report.archive.uncompressed_bytes
            > descriptor.declared_size * self._policy.max_archive_ratio
            or report.csv.row_count > self._policy.max_csv_rows
            or report.csv.column_count > self._policy.max_csv_columns
            or report.csv.max_cell_bytes > self._policy.max_csv_cell_bytes
            or report.csv.formula_prefix_detected
        ):
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.INSPECTION_FAILED)
        return report

    def intake(
        self,
        *,
        grant: AuthorizationGrant,
        descriptor: IntakeDescriptor,
        source: BoundedChunkReader,
    ) -> ObjectIntakeResult:
        """Perform one bounded pass with no retry and no external action."""

        self._authorize(grant, descriptor, source)
        opened: object = None
        begin_failed = False
        try:
            opened = self._quarantine.begin(descriptor)
        except Exception:
            begin_failed = True
        if begin_failed:
            fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
        if (
            type(opened) is not QuarantineRecord
            or opened.intake_id != descriptor.intake_id
            or opened.status is not QuarantineStatus.OPEN
            or opened.received_bytes != 0
            or opened.chunk_count != 0
        ):
            self._fail_after_reject(None, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        sealed, digest = self._stream_and_seal(descriptor, source, opened)

        duplicate: object = None
        duplicate_failed = False
        try:
            duplicate = self._duplicate.lookup(digest)
        except Exception:
            duplicate_failed = True
        if duplicate_failed:
            self._fail_after_reject(
                sealed, ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED
            )
        if type(duplicate) is not DuplicateInspectionRecord or duplicate.status not in {
            DuplicateStatus.NEW,
            DuplicateStatus.EXACT_DUPLICATE,
        }:
            self._fail_after_reject(
                sealed, ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED
            )

        report = self._inspect(descriptor, sealed)
        malware: object = None
        malware_failed = False
        try:
            malware = self._malware.scan(descriptor, sealed)
        except Exception:
            malware_failed = True
        if malware_failed:
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.MALWARE_REJECTED)
        if (
            type(malware) is not MalwareInspectionRecord
            or malware.status is not MalwareStatus.CLEAN
        ):
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.MALWARE_REJECTED)

        if duplicate.status is DuplicateStatus.NEW:
            recorded_duplicate: object = None
            duplicate_record_failed = False
            try:
                recorded_duplicate = self._duplicate.record_clean(descriptor, digest)
            except Exception:
                duplicate_record_failed = True
            if duplicate_record_failed:
                self._fail_after_reject(
                    sealed, ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED
                )
            if type(
                recorded_duplicate
            ) is not DuplicateInspectionRecord or recorded_duplicate.status not in {
                DuplicateStatus.NEW,
                DuplicateStatus.EXACT_DUPLICATE,
            }:
                self._fail_after_reject(
                    sealed, ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED
                )
            duplicate = recorded_duplicate

        classified: object = None
        disposition_failed = False
        try:
            classified = self._quarantine.record_disposition(
                sealed,
                disposition=QuarantineDisposition.CLEAN_QUARANTINED,
            )
        except Exception:
            disposition_failed = True
        if disposition_failed:
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        if (
            type(classified) is not QuarantineRecord
            or classified.intake_id != sealed.intake_id
            or classified.quarantine_id != sealed.quarantine_id
            or classified.status is not QuarantineStatus.DISPOSITION_RECORDED
            or classified.disposition is not QuarantineDisposition.CLEAN_QUARANTINED
            or classified.sealed_sha256 != digest
        ):
            self._fail_after_reject(sealed, ObjectIntakeFailureCode.QUARANTINE_FAILED)
        return ObjectIntakeResult(
            descriptor=descriptor,
            quarantine=classified,
            inspection=report,
            malware=malware,
            duplicate=duplicate,
            outcome=IntakeOutcome.CLEAN_QUARANTINED,
        )


__all__ = ["ObjectIntakeService"]
