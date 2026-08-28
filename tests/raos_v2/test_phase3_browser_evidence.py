from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.validate_raos_v2_successor import (
    ValidationFailure,
    record_phase3_local_browser_evidence,
    verify_phase3_local_browser_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = (
    ROOT / "changes/raos-v2/recorded-inputs/phase3-local-browser-evidence.v1.json"
)
PREVIEW_PATH = (
    ROOT / "changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"
)


def _evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_phase3_browser_evidence_is_current_tree_bound_and_local_only() -> None:
    result = verify_phase3_local_browser_evidence(
        _evidence(),
        expected_preview=PREVIEW_PATH.read_bytes(),
        root=ROOT,
    )
    assert result["effective_status"] == "PASSED_LOCAL_ASSEMBLY_SIMULATION"
    assert result["current_tree_binding"] == "CURRENT_PREVIEW_AND_HARNESS_BOUND"
    assert result["manual_visual_review"] == "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
    assert result["critical_findings"] == 0
    assert result["major_findings"] == 0
    assert result["external_actions"] == "NOT_EXECUTED"
    assert result["public_evidence"] == "NOT_CLAIMED"
    assert result["raw_verification"] in {
        "RAW_RECEIPT_VERIFIED_LOCAL",
        "RECORDED_NOT_REVERIFIED",
    }


def test_phase3_browser_evidence_rejects_preview_drift() -> None:
    with pytest.raises(ValidationFailure, match="PHASE3_BROWSER_PREVIEW_DRIFT"):
        verify_phase3_local_browser_evidence(
            _evidence(), expected_preview=b"changed", root=ROOT
        )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("assertions", "axeViolations", 1),
        ("assertions", "affiliateUrls", 1),
        ("network", "outboundRequests", 1),
        ("persistence", "cookies", 1),
    ],
)
def test_phase3_browser_evidence_rejects_safety_assertion_mutation(
    section: str, key: str, value: object
) -> None:
    evidence = deepcopy(_evidence())
    receipt = evidence["receipt"]
    assert isinstance(receipt, dict)
    target = receipt[section]
    assert isinstance(target, dict)
    target[key] = value
    with pytest.raises(ValidationFailure, match="PHASE3_BROWSER_EVIDENCE_INVALID"):
        verify_phase3_local_browser_evidence(
            evidence, expected_preview=PREVIEW_PATH.read_bytes(), root=ROOT
        )


def test_phase3_manual_visual_review_must_bind_exact_capture_hashes() -> None:
    evidence = deepcopy(_evidence())
    review = evidence["manual_visual_review"]
    assert isinstance(review, dict)
    hashes = review["reviewed_capture_sha256"]
    assert isinstance(hashes, list)
    hashes[0] = "f" * 64
    with pytest.raises(ValidationFailure, match="PHASE3_BROWSER_EVIDENCE_INVALID"):
        verify_phase3_local_browser_evidence(
            evidence, expected_preview=PREVIEW_PATH.read_bytes(), root=ROOT
        )


def test_phase3_browser_recorder_requires_explicit_visual_confirmation(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValidationFailure,
        match="RAOS_V2_PHASE3_VISUAL_REVIEW_CONFIRMATION_REQUIRED",
    ):
        record_phase3_local_browser_evidence(
            root=tmp_path,
            visual_review_confirmed=False,
        )
