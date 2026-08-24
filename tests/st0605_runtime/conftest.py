from __future__ import annotations

from pathlib import Path

import pytest

from raos.adapters.recorded_claim_evidence import (
    load_recorded_claim_evidence_fixture,
)
from raos.domain.evidence.claim_evidence import ClaimEvidenceSnapshot


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPOSITORY_ROOT / (
    "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)


@pytest.fixture(scope="session")
def passing_snapshot() -> ClaimEvidenceSnapshot:
    return load_recorded_claim_evidence_fixture(FIXTURE_PATH.read_bytes())
