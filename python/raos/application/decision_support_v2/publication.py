"""Build real-content evidence candidates without review or publish authority."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from raos.domain.decision_support_v2.publication import (
    ClaimEvidenceBinding,
    PublicationPackage,
    real_content_candidate,
)


def build_evidence_candidate(
    *,
    package_id: str,
    route: str,
    article_id: str,
    input_hashes: Mapping[str, str],
    render_hash: str,
    source_snapshot_hash: str,
    claim_evidence: tuple[ClaimEvidenceBinding, ...],
    migration_manifest: Mapping[str, object],
    created_at: datetime,
) -> PublicationPackage:
    return real_content_candidate(
        package_id=package_id,
        target_route=route,
        article_id=article_id,
        input_hashes=input_hashes,
        render_hash=render_hash,
        source_snapshot_hash=source_snapshot_hash,
        claim_evidence=claim_evidence,
        migration_manifest=migration_manifest,
        created_at=created_at,
    )


__all__ = ["build_evidence_candidate"]
