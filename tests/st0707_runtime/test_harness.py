from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from raos.adapters.recorded_ai_output_validation import (
    load_recorded_ai_output_validation_fixture,
    load_trusted_ai_output_validation_profiles,
)
from raos.adapters.recorded_ai_evaluation import RecordedAiEvaluationBundleReader
from raos.application.ai.evaluation_harness import (
    EvaluateRecordedHarnessService,
    RecordedEvaluationHarness,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.evaluation_harness import (
    EvidenceStatus,
    GateStatus,
    LockedEvaluationCase,
    LockedEvaluationDataset,
    MetricStatus,
    ProposalOutcome,
    RecordedEvaluationBundle,
    canonical_json_bytes,
    sha256_bytes,
)
from raos.domain.ai import output_validation
from tests.st0707_runtime.support import artifact_bytes


def _rebind_report(
    bundle: RecordedEvaluationBundle,
    report: output_validation.AiOutputValidationReport,
) -> RecordedEvaluationBundle:
    original = bundle.dataset.cases[0]
    case_document: dict[str, object] = {
        "case_id": original.case_id,
        "category": original.category,
        "evaluation_case_sha256": original.evaluation_case_sha256,
        "output_sha256": original.output_sha256,
        "profile_sha256": original.profile_sha256,
        "provenance": original.provenance.value,
        "provider_exchange_sha256": original.provider_exchange_sha256,
        "split": original.split.value,
        "st0705_report_sha256": report.report_sha256.value,
        "validation_manifest_sha256": original.validation_manifest_sha256,
    }
    case = LockedEvaluationCase(
        case_id=original.case_id,
        split=original.split,
        category=original.category,
        provenance=original.provenance,
        st0705_report_sha256=report.report_sha256.value,
        profile_sha256=original.profile_sha256,
        validation_manifest_sha256=original.validation_manifest_sha256,
        output_sha256=original.output_sha256,
        provider_exchange_sha256=original.provider_exchange_sha256,
        evaluation_case_sha256=original.evaluation_case_sha256,
        case_sha256=sha256_bytes(canonical_json_bytes(case_document)),
    )
    holdout_document: dict[str, object] = {
        "case_sha256": [case.case_sha256],
        "dataset_id": bundle.dataset.dataset_id,
        "split": "HOLDOUT",
        "version": bundle.dataset.version,
    }
    holdout_sha256 = sha256_bytes(canonical_json_bytes(holdout_document))
    dataset_document = {
        "canonical_dataset": False,
        "cases": [case_document | {"case_sha256": case.case_sha256}],
        "dataset_id": bundle.dataset.dataset_id,
        "holdout_sha256": holdout_sha256,
        "human_label_status": bundle.dataset.human_label_status.value,
        "human_labeled": False,
        "label_provenance": [],
        "locked_at": bundle.dataset.locked_at,
        "provenance": bundle.dataset.provenance.value,
        "release_eligible": False,
        "representative_dataset": False,
        "source_kind": bundle.dataset.source_kind,
        "status": bundle.dataset.status.value,
        "version": bundle.dataset.version,
    }
    dataset = LockedEvaluationDataset(
        dataset_id=bundle.dataset.dataset_id,
        version=bundle.dataset.version,
        status=bundle.dataset.status,
        provenance=bundle.dataset.provenance,
        source_kind=bundle.dataset.source_kind,
        locked_at=bundle.dataset.locked_at,
        human_label_status=bundle.dataset.human_label_status,
        label_provenance_count=0,
        cases=(case,),
        holdout_sha256=holdout_sha256,
        dataset_sha256=sha256_bytes(canonical_json_bytes(dataset_document)),
    )
    return RecordedEvaluationBundle(
        runtime_contract_sha256=bundle.runtime_contract_sha256,
        runtime_manifest_sha256=bundle.runtime_manifest_sha256,
        suite=bundle.suite,
        dataset=dataset,
        reports=(report,),
    )


def _recorded_input() -> output_validation.AiOutputValidationInput:
    values = artifact_bytes()
    profiles = load_trusted_ai_output_validation_profiles(
        values["st0705_profile_registry_bytes"]
    )
    return load_recorded_ai_output_validation_fixture(
        fixture_bytes=values["st0705_fixture_bytes"],
        profiles=profiles,
        schema_bytes=values["task_schema_bytes"],
    )


def test_run_is_deterministic_content_addressed_and_proposal_only(
    bundle: RecordedEvaluationBundle,
) -> None:
    runner = RecordedEvaluationHarness()
    first = runner.run(bundle)
    second = runner.run(bundle)
    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert json.loads(first.canonical_bytes())["report_sha256"] == first.report_sha256
    assert first.dataset_sha256 == bundle.dataset.dataset_sha256
    assert first.holdout_sha256 == bundle.dataset.holdout_sha256
    assert first.case_count == 1
    assert first.proposal.outcome is ProposalOutcome.REFUSED_INCOMPLETE_EVIDENCE
    assert first.proposal.decision_kind == "PROPOSAL"
    assert first.proposal.authority == "NONE"
    assert first.proposal.resolved_model_binding_status is EvidenceStatus.UNAVAILABLE
    assert first.proposal.external_action_count == 0
    assert all(
        value is False
        for value in (
            first.proposal.approval_authorized,
            first.proposal.activation_authorized,
            first.proposal.route_mutation_authorized,
            first.proposal.model_mutation_authorized,
            first.proposal.publication_authorized,
            first.proposal.release_authorized,
            first.proposal.production_eligible,
        )
    )


def test_insufficient_denominator_splits_and_human_evidence_never_pass(
    bundle: RecordedEvaluationBundle,
) -> None:
    report = RecordedEvaluationHarness().run(bundle)
    gates = {item.code: item.status for item in report.gates}
    assert gates["MINIMUM_ADJUDICATED_CASES"] is GateStatus.FAIL
    assert gates["REQUIRED_SPLITS"] is GateStatus.FAIL
    assert gates["HUMAN_LABEL_PROVENANCE"] is GateStatus.UNAVAILABLE
    assert gates["RESOLVED_MODEL_BINDING"] is GateStatus.UNAVAILABLE
    assert gates["REQUIRED_METRICS"] is GateStatus.UNAVAILABLE
    assert {
        "MINIMUM_ADJUDICATED_CASES_UNMET",
        "REQUIRED_SPLITS_INCOMPLETE",
        "HUMAN_LABEL_PROVENANCE_UNAVAILABLE",
        "REQUIRED_METRICS_UNAVAILABLE",
    } <= set(report.proposal.reasons)


def test_metrics_preserve_unavailable_and_apply_wilson_and_exact_zero_gates(
    bundle: RecordedEvaluationBundle,
) -> None:
    report = RecordedEvaluationHarness().run(bundle)
    metrics = {item.code: item for item in report.metrics}
    assert metrics["schema_valid_rate"].point_estimate_micros == 1_000_000
    assert metrics["schema_valid_rate"].wilson_lower_bound_micros == 269865
    assert metrics["schema_valid_rate"].status is MetricStatus.FAIL
    assert metrics["complete_response_rate"].status is MetricStatus.FAIL
    assert metrics["human_acceptance_rate"].status is MetricStatus.UNAVAILABLE
    assert metrics["human_acceptance_rate"].numerator is None
    assert metrics["editorial_business_separation"].status is MetricStatus.UNAVAILABLE
    for code in (
        "fabricated_experience_rate",
        "rakuten_review_body_leakage_rate",
        "affiliate_bias_violation_rate",
        "prompt_injection_follow_rate",
    ):
        assert metrics[code].status is MetricStatus.PASS
        assert metrics[code].numerator == 0
        assert metrics[code].denominator == 1
    assert all(item.status is MetricStatus.PASS for item in report.zero_tolerance)
    assert all(item.observed_failures == 0 for item in report.zero_tolerance)


def test_exact_st0705_profile_manifest_output_and_runtime_bindings_survive(
    bundle: RecordedEvaluationBundle,
) -> None:
    case = bundle.dataset.cases[0]
    report = bundle.reports[0]
    assert report.profile_sha256 is not None
    assert report.manifest_sha256 is not None
    assert report.output_sha256 is not None
    assert report.provider_exchange_sha256 is not None
    assert case.st0705_report_sha256 == report.report_sha256.value
    assert case.profile_sha256 == report.profile_sha256.value
    assert case.validation_manifest_sha256 == report.manifest_sha256.value
    assert case.output_sha256 == report.output_sha256.value
    assert case.provider_exchange_sha256 == report.provider_exchange_sha256.value
    assert bundle.suite.profile_registry_sha256 == (
        "1831c39897914faa3695eef1b2ca8239d3172f937f00511d173aa41a3074592b"
    )
    assert bundle.suite.st0705_runtime_contract_sha256 == (
        "26673778bd1d73110714ca7568b16d249599069fcc2a59f9505d49086fbed2e6"
    )


def test_local_read_service_has_no_missing_bundle_fallback_or_nonlocal_mode(
    bundle: RecordedEvaluationBundle,
) -> None:
    reader = RecordedAiEvaluationBundleReader(
        environment=RuntimeEnvironment.CI, bundles=(("locked", bundle),)
    )
    service = EvaluateRecordedHarnessService(
        environment=RuntimeEnvironment.CI, reader=reader
    )
    assert service.evaluate("locked") == RecordedEvaluationHarness().run(bundle)
    with pytest.raises(ValueError):
        service.evaluate("missing")
    with pytest.raises(ValueError):
        EvaluateRecordedHarnessService(
            environment=RuntimeEnvironment.STAGING, reader=reader
        )


def test_unavailable_zero_tolerance_is_not_pass_and_observed_failure_precedes(
    bundle: RecordedEvaluationBundle,
) -> None:
    value = _recorded_input()
    unavailable_gates = (
        output_validation.GateResult(
            output_validation.GATE_IDS[0],
            output_validation.GateStatus.UNEVALUABLE,
            (output_validation.FindingCode.BINDING_UNAVAILABLE,),
        ),
    ) + tuple(
        output_validation.GateResult(
            gate_id, output_validation.GateStatus.NOT_EXECUTED, ()
        )
        for gate_id in output_validation.GATE_IDS[1:]
    )
    unavailable = output_validation._make_report(
        value=value,
        evaluated_at=value.evaluated_at,
        status=output_validation.LocalValidationStatus.UNEVALUABLE,
        gates=unavailable_gates,
    )
    unavailable_report = RecordedEvaluationHarness().run(
        _rebind_report(bundle, unavailable)
    )
    assert all(
        item.status is MetricStatus.UNAVAILABLE
        for item in unavailable_report.zero_tolerance
    )
    assert {item.code: item.status for item in unavailable_report.gates}[
        "ZERO_TOLERANCE"
    ] is GateStatus.UNAVAILABLE
    assert unavailable_report.proposal.outcome is (
        ProposalOutcome.REFUSED_INCOMPLETE_EVIDENCE
    )
    assert "ZERO_TOLERANCE_EVIDENCE_UNAVAILABLE" in (
        unavailable_report.proposal.reasons
    )

    blocked_gates = tuple(
        output_validation.GateResult(
            gate_id,
            (
                output_validation.GateStatus.BLOCKED
                if gate_id == output_validation.GATE_IDS[8]
                else output_validation.GateStatus.PASS
            ),
            (
                (output_validation.FindingCode.SECRET_OR_RESTRICTED_DATA,)
                if gate_id == output_validation.GATE_IDS[8]
                else ()
            ),
        )
        for gate_id in output_validation.GATE_IDS
    )
    blocked = output_validation._make_report(
        value=value,
        evaluated_at=value.evaluated_at,
        status=output_validation.LocalValidationStatus.BLOCKED,
        gates=blocked_gates,
    )
    blocked_report = RecordedEvaluationHarness().run(_rebind_report(bundle, blocked))
    assert blocked_report.proposal.outcome is ProposalOutcome.REFUSED_ZERO_TOLERANCE
    assert {item.code: item.status for item in blocked_report.gates}[
        "ZERO_TOLERANCE"
    ] is GateStatus.FAIL
    secret_result = blocked_report.zero_tolerance[-1]
    assert secret_result.status is MetricStatus.FAIL
    assert secret_result.observed_failures == 1


def test_bundle_and_report_are_immutable(bundle: RecordedEvaluationBundle) -> None:
    report = RecordedEvaluationHarness().run(bundle)
    with pytest.raises(FrozenInstanceError):
        report.case_count = 150  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bundle.dataset.release_eligible = True  # type: ignore[misc]
