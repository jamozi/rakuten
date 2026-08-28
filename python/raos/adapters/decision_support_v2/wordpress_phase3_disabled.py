"""Disabled Phase 3 WordPress adapter with a hash-only deterministic diff."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Mapping

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.domain.decision_support_v2.phase3_publication import (
    PHASE3_CONTRACT_VERSION,
    PHASE3_TARGET_ORIGIN,
    PHASE3_TARGET_ROUTE,
    WORDPRESS_FIELD_NAMES,
    Phase3PublicationPackage,
    Phase3PublicationState,
    Phase3WordPressExportBinding,
    Phase3WordPressExportRole,
    Phase3WordPressIntent,
    wordpress_field_digest,
)
from raos.domain.decision_support_v2.publication import semantic_digest


_INTENT: Final = (
    Phase3WordPressIntent.UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER
)
_PUBLISH_STATUS_HASH: Final = wordpress_field_digest("post_status", "publish")
PHASE3_WORDPRESS_EXPORT_MAX_AGE: Final = timedelta(minutes=5)


class DisabledPhase3WordPressUpdate:
    """Produce a verified local receipt; no endpoint or transport exists here."""

    mode = "DISABLED_DRY_RUN"
    external_action_count = 0
    request_count = 0

    __slots__ = ()

    def dry_run(
        self,
        package: Phase3PublicationPackage,
        *,
        export_binding: Phase3WordPressExportBinding,
        evaluated_at: object,
    ) -> Mapping[str, object]:
        if (
            type(package) is not Phase3PublicationPackage
            or package.state is not Phase3PublicationState.PACKAGE_SEALED
        ):
            raise AdapterError(AdapterFailure.DISABLED)
        if (
            type(export_binding) is not Phase3WordPressExportBinding
            or not export_binding.verify_integrity()
            or not isinstance(evaluated_at, datetime)
            or evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or export_binding.export_role
            is not Phase3WordPressExportRole.PRE_WRITE_EXPORT
        ):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        payload = package.review_candidate.update_payload
        preaction = payload.preaction_binding
        if (
            payload.intent is not _INTENT
            or payload.target_origin != PHASE3_TARGET_ORIGIN
            or payload.target_route != PHASE3_TARGET_ROUTE
            or payload.target_kind != "EXISTING_POST"
            or payload.expected_existing_post_count != 1
            or payload.expected_current_post_status != "publish"
            or payload.required_after_post_status != "publish"
            or payload.fields.post_status != "publish"
            or preaction is None
            or not preaction.verify_integrity()
        ):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        if (
            export_binding.target_origin != payload.target_origin
            or export_binding.target_route != payload.target_route
            or export_binding.target_kind != payload.target_kind
            or export_binding.exact_match_count != payload.expected_existing_post_count
            or export_binding.post_id != preaction.post_id
            or export_binding.field_hashes["post_status"] != _PUBLISH_STATUS_HASH
            or export_binding.captured_at > evaluated_at
        ):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        if (
            export_binding.public_body_sha256 != payload.expected_public_body_sha256
            or export_binding.public_body_sha256 != preaction.current_public_body_sha256
            or export_binding.preaction_binding_sha256 != preaction.binding_digest
            or export_binding.captured_at < package.review_receipt.reviewed_at
            or evaluated_at - export_binding.captured_at
            > PHASE3_WORDPRESS_EXPORT_MAX_AGE
            or package.review_candidate.seal_blockers(reviewed_at=evaluated_at)
        ):
            raise AdapterError(AdapterFailure.STALE)
        if not package.verify_seal(as_of=evaluated_at):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)

        before_field_hashes = export_binding.field_hashes
        after_fields = payload.fields.to_contract_record()
        field_diff: list[Mapping[str, object]] = []
        for field_name in sorted(WORDPRESS_FIELD_NAMES):
            before_sha256 = before_field_hashes[field_name]
            after_sha256 = wordpress_field_digest(field_name, after_fields[field_name])
            field_diff.append(
                {
                    "field": field_name,
                    "before_sha256": before_sha256,
                    "after_sha256": after_sha256,
                    "changed": before_sha256 != after_sha256,
                }
            )

        target = {
            "origin": PHASE3_TARGET_ORIGIN,
            "route": PHASE3_TARGET_ROUTE,
            "kind": "EXISTING_POST",
            "post_id": export_binding.post_id,
            "expected_match_count": 1,
        }
        preconditions = {
            "export_role": export_binding.export_role.value,
            "expected_current_post_status": "publish",
            "before_post_status_sha256": before_field_hashes["post_status"],
            "expected_public_body_sha256": payload.expected_public_body_sha256,
            "observed_public_body_sha256": export_binding.public_body_sha256,
            "export_captured_at": export_binding.captured_at.isoformat(),
            "human_reviewed_at": package.review_receipt.reviewed_at.isoformat(),
            "preaction_status": preaction.status.value,
            "preaction_binding_sha256": preaction.binding_digest,
            "observed_preaction_binding_sha256": (
                export_binding.preaction_binding_sha256
            ),
            "preaction_captured_at": preaction.captured_at.isoformat(),
            "evaluated_at": evaluated_at.isoformat(),
            "max_export_age_seconds": int(
                PHASE3_WORDPRESS_EXPORT_MAX_AGE.total_seconds()
            ),
            "satisfied": (
                before_field_hashes["post_status"] == _PUBLISH_STATUS_HASH
                and export_binding.public_body_sha256
                == payload.expected_public_body_sha256
                and export_binding.public_body_sha256
                == preaction.current_public_body_sha256
                and export_binding.preaction_binding_sha256 == preaction.binding_digest
                and export_binding.captured_at >= package.review_receipt.reviewed_at
                and export_binding.captured_at <= evaluated_at
                and evaluated_at - export_binding.captured_at
                <= PHASE3_WORDPRESS_EXPORT_MAX_AGE
            ),
        }
        postconditions = {
            "required_after_post_status": "publish",
            "after_post_status_sha256": wordpress_field_digest(
                "post_status", after_fields["post_status"]
            ),
            "satisfied": after_fields["post_status"] == "publish",
        }
        export_binding_sha256 = export_binding.binding_digest
        idempotency_key = semantic_digest(
            {
                "target": target,
                "intent": _INTENT.value,
                "package_digest": package.package_digest,
                "payload_digest": package.review_candidate.payload_digest,
                "export_binding_sha256": export_binding_sha256,
                "preconditions": preconditions,
                "postconditions": postconditions,
                "field_diff": field_diff,
            }
        )
        return {
            "schema": "RAOS_V2_PHASE3_WORDPRESS_DRY_RUN_RECEIPT_V1",
            "version": PHASE3_CONTRACT_VERSION,
            "mode": self.mode,
            "request_count": 0,
            "external_action_count": 0,
            "external_status": "NOT_EXECUTED",
            "status": "DRY_RUN",
            "intent": _INTENT.value,
            "target": target,
            "package_digest": package.package_digest,
            "payload_digest": package.review_candidate.payload_digest,
            "export_binding_sha256": export_binding_sha256,
            "preconditions": preconditions,
            "postconditions": postconditions,
            "field_diff": field_diff,
            "idempotency_key": idempotency_key,
        }


__all__ = [
    "PHASE3_WORDPRESS_EXPORT_MAX_AGE",
    "DisabledPhase3WordPressUpdate",
    "wordpress_field_digest",
]
