from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture
from raos.domain.editorial.policy_engine import evaluate_editorial_policy
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationReportV2,
    evaluate_editorial_policy_v2,
    policy_evaluation_input_sha256,
    policy_result_sha256,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "changes/st-0805/generated/policy-pass.v2.json"


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def envelope(fixture_bytes: bytes) -> PolicyEvaluationEnvelopeV2:
    return load_recorded_policy_fixture(fixture_bytes)


@pytest.fixture
def report(envelope: PolicyEvaluationEnvelopeV2) -> PolicyEvaluationReportV2:
    return evaluate_editorial_policy_v2(envelope)


def rehash_policy_input(
    envelope: PolicyEvaluationEnvelopeV2,
) -> PolicyEvaluationEnvelopeV2:
    legacy = evaluate_editorial_policy(envelope.policy_input)
    policy_hash = policy_result_sha256(legacy)
    return replace(
        envelope,
        policy_result_sha256=policy_hash,
        evaluation_input_sha256=policy_evaluation_input_sha256(
            contract=envelope.contract,
            draft=envelope.draft,
            coverage_report=envelope.coverage_report,
            coverage_receipt=envelope.coverage_receipt,
            recommendation_report=envelope.recommendation_report,
            recommendation_receipt=envelope.recommendation_receipt,
            policy_result_digest=policy_hash,
        ),
    )
