"""Durable, authorization-first application service for ST-0406 V2."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import NoReturn, final

from raos.application.iam.authorization import DurableAuthorizationService
from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationCommandResult,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    DecisionEffect,
    OperationId,
    ResourceScopeKind,
    ResourceState,
)
from raos.domain.ops.object_intake import (
    IntakeDescriptor,
    ObjectIntakeKind,
    Sha256Digest,
)
from raos.domain.ops.object_intake_runtime_v2 import (
    DurableIntakeDescriptorV2,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    IntakeRuntimeMode,
    IntakeRuntimePolicyV2,
    MalwareScanReceiptV2,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
    PrivacyClassificationReceiptV2,
    RecordedMalwareVerdict,
    RecordedPrivacyVerdict,
    RecoveredIntakeOutcomeV2,
    fail_intake_runtime,
)
from raos.ports.object_intake_runtime_v2 import (
    BoundedIntakeSourceV2,
    ContentInspectorV2,
    IntakeRuntimeRepositoryV2,
    IntakeRuntimeUnitOfWorkV2,
    MalwareScannerV2,
    PrivacyClassifierV2,
)


_INTAKE_OPERATION = OperationId("ED-011")
_INTAKE_ACTION = ActionCode("edit_article_draft")
_INTAKE_STATE = ResourceState("DRAFT")
_ALLOWED_KINDS = {ObjectIntakeKind.SOURCE_DOCUMENT, ObjectIntakeKind.MEDIA_ASSET}


def _fail(code: ObjectIntakeRuntimeFailureCode) -> NoReturn:
    fail_intake_runtime(code)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
    try:
        normalized = value.astimezone(timezone.utc)
    except OverflowError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
    if normalized.utcoffset() is None:
        _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
    return normalized


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except TypeError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
    return hashlib.sha256(encoded).hexdigest()


def _descriptor_document(value: DurableIntakeDescriptorV2) -> dict[str, object]:
    descriptor = value.descriptor
    return {
        "intake_id": str(descriptor.intake_id),
        "site_id": str(descriptor.site_id),
        "authorization_resource_id": str(value.authorization_resource_id),
        "kind": descriptor.kind.value,
        "leaf_name": descriptor.leaf_name.value,
        "media_type": descriptor.media_type.value,
        "declared_size": descriptor.declared_size,
        "declared_sha256": descriptor.declared_sha256.value,
        "privacy_class": descriptor.privacy_class.value,
    }


def _authorization_digest(
    *,
    command: AuthorizationEvaluationCommand,
    result: AuthorizationCommandResult,
) -> str:
    target = command.target
    decision = result.decision
    return _digest(
        {
            "schema": "ST0406_ST0403_AUTHORIZATION_BINDING_V2",
            "authorization_command_id": command.command_id.value,
            "operation_id": command.operation_id.value,
            "request_digest": result.request_digest,
            "session_fingerprint": result.session_fingerprint,
            "audit_sequence": result.audit.sequence,
            "audit_digest": result.audit.digest,
            "effect": decision.effect.value,
            "reason": decision.reason.value,
            "action": decision.action.value,
            "site_id": str(target.scope.site_id),
            "resource_kind": target.scope.kind.value,
            "resource_id": str(target.scope.resource_id),
            "resource_state": None if target.state is None else target.state.value,
            "policy_revision": decision.policy_revision.value,
            "policy_fingerprint": decision.policy_fingerprint,
            "entitlement_revision": decision.entitlement_revision.value,
            "matched_rule_id": decision.matched_rule_id.value
            if decision.matched_rule_id is not None
            else None,
        }
    )


@final
class SecureObjectIntakeRuntimeV2:
    """Authorize, quarantine, inspect and persist one local recorded intake."""

    def __init__(
        self,
        *,
        policy: IntakeRuntimePolicyV2,
        authorization_service: DurableAuthorizationService,
        repository: IntakeRuntimeRepositoryV2,
        inspector: ContentInspectorV2,
        privacy_classifier: PrivacyClassifierV2,
        malware_scanner: MalwareScannerV2,
    ) -> None:
        if (
            type(policy) is not IntakeRuntimePolicyV2
            or type(authorization_service) is not DurableAuthorizationService
            or not _implements(repository, IntakeRuntimeRepositoryV2)
            or not _implements(inspector, ContentInspectorV2)
            or not _implements(privacy_classifier, PrivacyClassifierV2)
            or not _implements(malware_scanner, MalwareScannerV2)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._policy = policy
        self._authorization_service = authorization_service
        self._repository = repository
        self._inspector = inspector
        self._privacy = privacy_classifier
        self._malware = malware_scanner

    @property
    def action_count(self) -> int:
        """External/provider/publication actions are structurally absent."""

        return 0

    def _authorize(
        self,
        *,
        descriptor: DurableIntakeDescriptorV2,
        session_id: SessionId,
        authorization_command: AuthorizationEvaluationCommand,
        authorization_result: AuthorizationCommandResult,
        authorization_checked_at: datetime,
    ) -> AuthorizationCommandResult:
        """Recheck the active session and durable decision before intake I/O."""

        if (
            type(descriptor) is not DurableIntakeDescriptorV2
            or type(session_id) is not SessionId
            or type(authorization_command) is not AuthorizationEvaluationCommand
            or type(authorization_result) is not AuthorizationCommandResult
        ):
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
        checked_at = _utc(authorization_checked_at)
        if checked_at < authorization_command.observed_at:
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
        try:
            recovered = self._authorization_service.recover_admin(
                command_id=authorization_command.command_id,
                session_id=session_id,
                now=checked_at,
            )
        except Exception:
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_NOT_DURABLE)
        if type(recovered) is not AuthorizationCommandResult:
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_NOT_DURABLE)
        try:
            recomputed_request = authorization_command.request_digest(
                session_fingerprint=recovered.session_fingerprint
            )
        except Exception:
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
        base = descriptor.descriptor
        target = authorization_command.target
        decision = recovered.decision
        if (
            recovered != authorization_result
            or authorization_command.command_id != recovered.command_id
            or not hmac.compare_digest(recomputed_request, recovered.request_digest)
            or authorization_command.operation_id != _INTAKE_OPERATION
            or decision.effect is not DecisionEffect.ALLOW
            or decision.reason is not AuthorizationDecisionReason.RULE_MATCH
            or decision.action != _INTAKE_ACTION
            or decision.target != target
            or target.scope.kind is not ResourceScopeKind.ARTICLE_VERSION
            or target.state != _INTAKE_STATE
            or target.scope.site_id != base.site_id
            or target.scope.resource_id != descriptor.authorization_resource_id
            or base.kind not in _ALLOWED_KINDS
            or recovered.step_up_receipt_fingerprint is not None
        ):
            _fail(ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED)
        return recovered

    @staticmethod
    def _outcome(value: RecoveredIntakeOutcomeV2) -> DurableQuarantineReceiptV2:
        if type(value) is not RecoveredIntakeOutcomeV2:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        if value.accepted is not None:
            return value.accepted
        if value.rejected is None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        _fail(value.rejected.failure_code)

    def _recover(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        fallback: ObjectIntakeRuntimeFailureCode,
    ) -> DurableQuarantineReceiptV2:
        try:
            recovered = self._repository.recover(
                command_id=command_id, request_digest=request_digest
            )
        except Exception:
            _fail(fallback)
        return self._outcome(recovered)

    def _commit_or_recover(
        self,
        *,
        uow: IntakeRuntimeUnitOfWorkV2,
        command_id: IntakeCommandId,
        request_digest: str,
    ) -> None:
        try:
            uow.commit()
            return
        except Exception:
            self._recover(
                command_id=command_id,
                request_digest=request_digest,
                fallback=ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN,
            )

    def _reject(
        self,
        *,
        uow: IntakeRuntimeUnitOfWorkV2,
        command_id: IntakeCommandId,
        request_digest: str,
        version: int,
        code: ObjectIntakeRuntimeFailureCode,
    ) -> NoReturn:
        try:
            uow.reject(expected_version=version, failure_code=code)
            self._commit_or_recover(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
            )
        except ObjectIntakeRuntimeFailure as error:
            if error.code is code:
                raise
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if error.code is ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        except Exception:
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        _fail(code)

    def intake(
        self,
        *,
        command_id: IntakeCommandId,
        descriptor: DurableIntakeDescriptorV2,
        session_id: SessionId,
        authorization_command: AuthorizationEvaluationCommand,
        authorization_result: AuthorizationCommandResult,
        authorization_checked_at: datetime,
        source: BoundedIntakeSourceV2,
    ) -> DurableQuarantineReceiptV2:
        """Execute one bounded recorded command; no external action is possible."""

        if (
            type(command_id) is not IntakeCommandId
            or type(descriptor) is not DurableIntakeDescriptorV2
            or self._policy.mode is not IntakeRuntimeMode.RECORDED_LOCAL
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        base: IntakeDescriptor = descriptor.descriptor
        if (
            base.media_type.value not in self._policy.allowed_media_types
            or base.privacy_class not in self._policy.allowed_privacy_classes
            or base.declared_size > self._policy.max_object_bytes
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)

        # This durable ST-0403 recovery is intentionally before source/quarantine I/O.
        recovered_authorization = self._authorize(
            descriptor=descriptor,
            session_id=session_id,
            authorization_command=authorization_command,
            authorization_result=authorization_result,
            authorization_checked_at=authorization_checked_at,
        )
        if not _implements(source, BoundedIntakeSourceV2):
            _fail(ObjectIntakeRuntimeFailureCode.SOURCE_FAILED)

        descriptor_digest = _digest(_descriptor_document(descriptor))
        authorization_digest = _authorization_digest(
            command=authorization_command,
            result=recovered_authorization,
        )
        request_digest = _digest(
            {
                "schema": "ST0406_INTAKE_REQUEST_V2",
                "command_id": command_id.value,
                "descriptor_digest": descriptor_digest,
                "authorization_digest": authorization_digest,
            }
        )
        try:
            uow = self._repository.begin(
                command_id=command_id,
                request_digest=request_digest,
                descriptor_digest=descriptor_digest,
                authorization_digest=authorization_digest,
                descriptor=descriptor,
            )
        except ObjectIntakeRuntimeFailure:
            raise
        except Exception:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        if not _implements(uow, IntakeRuntimeUnitOfWorkV2):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        try:
            existing = uow.existing()
        except Exception:
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        if existing is not None:
            self._commit_or_recover(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
            )
            return self._outcome(existing)

        version = 1
        total = 0
        chunk_count = 0
        digest = hashlib.sha256()
        content = bytearray()
        while True:
            try:
                chunk = source.read_chunk(maximum_bytes=self._policy.max_chunk_bytes)
            except Exception:
                self._reject(
                    uow=uow,
                    command_id=command_id,
                    request_digest=request_digest,
                    version=version,
                    code=ObjectIntakeRuntimeFailureCode.SOURCE_FAILED,
                )
            if type(chunk) is not bytes or len(chunk) > self._policy.max_chunk_bytes:
                self._reject(
                    uow=uow,
                    command_id=command_id,
                    request_digest=request_digest,
                    version=version,
                    code=ObjectIntakeRuntimeFailureCode.SOURCE_FAILED,
                )
            if chunk == b"":
                break
            chunk_count += 1
            total += len(chunk)
            if (
                chunk_count > self._policy.max_chunk_count
                or total > self._policy.max_object_bytes
                or total > base.declared_size
            ):
                self._reject(
                    uow=uow,
                    command_id=command_id,
                    request_digest=request_digest,
                    version=version,
                    code=ObjectIntakeRuntimeFailureCode.STREAM_LIMIT_EXCEEDED,
                )
            try:
                version = uow.append(expected_version=version, chunk=chunk)
            except ObjectIntakeRuntimeFailure:
                try:
                    uow.rollback()
                except Exception:
                    pass
                raise
            except Exception:
                try:
                    uow.rollback()
                except Exception:
                    pass
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            content.extend(chunk)
            digest.update(chunk)
        computed = Sha256Digest(digest.hexdigest())
        if total != base.declared_size or computed != base.declared_sha256:
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=ObjectIntakeRuntimeFailureCode.CONTENT_MISMATCH,
            )
        try:
            version = uow.seal(
                expected_version=version,
                sha256=computed,
                received_bytes=total,
                chunk_count=chunk_count,
            )
        except ObjectIntakeRuntimeFailure:
            try:
                uow.rollback()
            except Exception:
                pass
            raise
        except Exception:
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

        try:
            inspection = self._inspector.inspect(
                descriptor=base,
                content=bytes(content),
                policy=self._policy,
            )
        except Exception:
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED,
            )
        try:
            privacy = self._privacy.classify(descriptor=base, sha256=computed)
        except Exception:
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED,
            )
        if (
            type(privacy) is not PrivacyClassificationReceiptV2
            or privacy.verdict is not RecordedPrivacyVerdict.MATCH
            or privacy.classified_as is not base.privacy_class
        ):
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED,
            )
        try:
            malware = self._malware.scan(descriptor=base, sha256=computed)
        except Exception:
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED,
            )
        if (
            type(malware) is not MalwareScanReceiptV2
            or malware.verdict is not RecordedMalwareVerdict.CLEAN
        ):
            self._reject(
                uow=uow,
                command_id=command_id,
                request_digest=request_digest,
                version=version,
                code=(
                    ObjectIntakeRuntimeFailureCode.MALWARE_DISABLED
                    if type(malware) is MalwareScanReceiptV2
                    and malware.verdict is RecordedMalwareVerdict.UNAVAILABLE
                    else ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED
                ),
            )
        try:
            receipt = uow.accept(
                expected_version=version,
                inspection=inspection,
                privacy=privacy,
                malware=malware,
            )
        except ObjectIntakeRuntimeFailure:
            try:
                uow.rollback()
            except Exception:
                pass
            raise
        except Exception:
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        if type(receipt) is not DurableQuarantineReceiptV2:
            try:
                uow.rollback()
            except Exception:
                pass
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        self._commit_or_recover(
            uow=uow,
            command_id=command_id,
            request_digest=request_digest,
        )
        return receipt


__all__ = ["SecureObjectIntakeRuntimeV2"]
