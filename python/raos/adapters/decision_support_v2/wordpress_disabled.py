"""Disabled WordPress port. It has no URL, credential, or HTTP dependency."""

from __future__ import annotations

from typing import Mapping

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.domain.decision_support_v2.publication import (
    PublicationPackage,
    PublicationState,
    semantic_digest,
)


class DisabledWordPressDraft:
    mode = "DISABLED_DRY_RUN"
    external_action_count = 0
    request_count = 0

    __slots__ = ()

    def dry_run(self, package: PublicationPackage) -> Mapping[str, object]:
        if (
            package.state
            not in {
                PublicationState.PACKAGE_SEALED,
            }
            or not package.verify_seal()
        ):
            raise AdapterError(AdapterFailure.DISABLED)
        intent = package.migration_manifest.get("wordpress_intent")
        if intent != "CREATE_OR_UPDATE":
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        after = {
            "post_status": "draft",
            "comment_status": "closed",
            "ping_status": "closed",
            "render_hash": package.render_hash,
        }
        target = {
            "origin": package.target_origin,
            "route": package.target_route,
        }
        idempotency_key = semantic_digest(
            {
                "target": target,
                "intent": intent,
                "after": after,
                "package_digest": package.package_digest,
            }
        )
        return {
            "schema_version": "1.0.0",
            "mode": self.mode,
            "external_action_count": 0,
            "request_count": 0,
            "target": target,
            "intent": intent,
            "before": {"state": "NOT_OBSERVED", "reason": "DISABLED"},
            "after": after,
            "idempotency_key": idempotency_key,
            "package_digest": package.package_digest,
            "status": "DRY_RUN",
            "external_status": "NOT_EXECUTED",
        }


__all__ = ["DisabledWordPressDraft"]
