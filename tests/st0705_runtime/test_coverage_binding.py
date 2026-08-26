from __future__ import annotations

from pathlib import Path

from raos.adapters.recorded_claim_evidence import load_recorded_claim_evidence_fixture
from raos.domain.ai.output_validation import (
    CoverageEvidenceBinding,
    FindingCode,
    LocalValidationStatus,
    evaluate_ai_output,
)
from raos.domain.ai.provider import Sha256Digest
from raos.domain.evidence.claim_evidence import (
    CoverageFindingCode,
    CoverageFraction,
    CoverageStatus,
    ClaimEvidenceCoverageReport,
    _make_report,
    evaluate_claim_evidence,
)

from .support import CaseFactory


ROOT = Path(__file__).resolve().parents[2]
AIT005_DOCUMENT = {"schema_version": "1.0", "claims": []}


def _binding(
    report: ClaimEvidenceCoverageReport, output_sha256: Sha256Digest
) -> CoverageEvidenceBinding:
    assert report.article_version_id is not None
    assert report.article_body_sha256 is not None
    assert report.source_packet_version_id is not None
    assert report.source_packet_content_sha256 is not None
    assert report.complete_claim_set_sha256 is not None
    assert report.evaluation_input_sha256 is not None
    return CoverageEvidenceBinding(
        output_sha256=output_sha256,
        article_version_id=report.article_version_id.value,
        article_body_sha256=Sha256Digest(report.article_body_sha256.value),
        source_packet_version_id=report.source_packet_version_id.value,
        source_packet_content_sha256=Sha256Digest(
            report.source_packet_content_sha256.value
        ),
        complete_claim_set_sha256=Sha256Digest(report.complete_claim_set_sha256.value),
        evaluation_input_sha256=Sha256Digest(report.evaluation_input_sha256.value),
        report=report,
    )


def test_exact_st0605_pass_binding_is_separate_from_raw_ai_output(
    case_factory: CaseFactory,
) -> None:
    base = case_factory("AIT-005", document=AIT005_DOCUMENT)
    assert base.envelope.output_sha256 is not None
    snapshot = load_recorded_claim_evidence_fixture(
        (
            ROOT / "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
        ).read_bytes()
    )
    coverage_report = evaluate_claim_evidence(snapshot)
    binding = _binding(coverage_report, base.envelope.output_sha256)
    report = evaluate_ai_output(
        case_factory("AIT-005", document=AIT005_DOCUMENT, coverage=binding)
    )
    assert report.status is LocalValidationStatus.UNEVALUABLE
    assert FindingCode.COVERAGE_UNAVAILABLE not in report.findings
    assert binding.article_body_sha256 != binding.output_sha256
    assert FindingCode.SEMANTIC_CAPABILITY_UNAVAILABLE in report.findings


def test_valid_st0605_block_is_proven_block_but_mismatch_is_unevaluable(
    case_factory: CaseFactory,
) -> None:
    base = case_factory("AIT-005", document=AIT005_DOCUMENT)
    assert base.envelope.output_sha256 is not None
    snapshot = load_recorded_claim_evidence_fixture(
        (
            ROOT / "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
        ).read_bytes()
    )
    passed = evaluate_claim_evidence(snapshot)
    assert passed.major_coverage is not None
    assert passed.all_verifiable_coverage is not None
    blocked = _make_report(
        value=snapshot,
        requested_article_version_id=None,
        status=CoverageStatus.BLOCK,
        findings={CoverageFindingCode.EVIDENCE_REQUIRED},
        major=CoverageFraction(evidenced=0, total=1),
        all_claims=CoverageFraction(evidenced=0, total=1),
        major_satisfied=False,
        all_satisfied=False,
    )
    valid_binding = _binding(blocked, base.envelope.output_sha256)
    valid = evaluate_ai_output(
        case_factory("AIT-005", document=AIT005_DOCUMENT, coverage=valid_binding)
    )
    assert valid.status is LocalValidationStatus.BLOCKED
    assert FindingCode.COVERAGE_BLOCKED in valid.findings

    mismatched_binding = _binding(
        passed, Sha256Digest.of(b"different-canonical-output")
    )
    mismatch = evaluate_ai_output(
        case_factory("AIT-005", document=AIT005_DOCUMENT, coverage=mismatched_binding)
    )
    assert mismatch.status is LocalValidationStatus.UNEVALUABLE
    assert FindingCode.COVERAGE_UNAVAILABLE in mismatch.findings
    assert FindingCode.COVERAGE_BLOCKED not in mismatch.findings
