"""Synthetic exact builders for the isolated ST-0601 suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_artifact_registry import (  # noqa: E402
    RecordedArtifactCandidateObserver,
    RecordedArtifactFixture,
)
from raos.application.ops.artifact_registry import (  # noqa: E402
    ArtifactRegistryReferenceService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ops.artifact_registry import (  # noqa: E402
    ArtifactKind,
    ArtifactProvenance,
    ObjectLocationCandidate,
    RegistryIntent,
    RegistryMode,
    Sha256Digest,
)


SYNTHETIC_CONTENT = b'{"synthetic":"raw-provider-response"}'
ACQUIRED_AT = datetime(2026, 8, 10, 5, 0, tzinfo=timezone.utc)


def location_candidate(
    *,
    object_key: str = "raw/test-only/rakuten/item-search/response.json",
    version_id: str = "TEST_ONLY_VERSION_001",
) -> ObjectLocationCandidate:
    return ObjectLocationCandidate(
        scheme="s3",
        bucket="raos-raw",
        object_key=object_key,
        version_id=version_id,
    )


def provenance(
    *,
    digest: Sha256Digest | None = None,
    byte_size: int = len(SYNTHETIC_CONTENT),
) -> ArtifactProvenance:
    return ArtifactProvenance(
        kind=ArtifactKind.RAW_PROVIDER_RESPONSE,
        source="TEST_ONLY:RAKUTEN_ITEM_SEARCH",
        acquired_at=ACQUIRED_AT,
        content_type="application/json",
        byte_size=byte_size,
        digest=Sha256Digest.of(SYNTHETIC_CONTENT) if digest is None else digest,
        location=location_candidate(),
        intent=RegistryIntent.REFERENCE_PLAN_ONLY,
    )


def observer_for(
    candidate: ArtifactProvenance,
    *,
    synthetic_content: bytes = SYNTHETIC_CONTENT,
) -> RecordedArtifactCandidateObserver:
    return RecordedArtifactCandidateObserver(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=RegistryMode.RECORDED_TEST_ONLY,
        fixture_capacity=1,
        fixtures=(
            RecordedArtifactFixture(
                candidate=candidate,
                synthetic_content=synthetic_content,
            ),
        ),
    )


def service_for(candidate: ArtifactProvenance) -> ArtifactRegistryReferenceService:
    return ArtifactRegistryReferenceService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=RegistryMode.RECORDED_TEST_ONLY,
        observer=observer_for(candidate),
    )
