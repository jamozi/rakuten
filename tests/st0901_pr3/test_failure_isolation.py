"""Tamper isolation, redaction, and forbidden-effect evidence for PR3."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import pickle

import pytest

from .support import (
    OTHER_REVIEWER_ID,
    adapter,
    empty_history,
    identity,
    recorded_grant,
    request,
    scripted_result,
    service,
    step,
    uuid7,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedReviewDecisionHistoryV1,
    RecordedSha256,
    ReviewDecisionOperationFailure,
    ReviewDecisionOperationFailureCode,
    fail_review_decision_operation,
)
from raos.domain.publishing.review_workflow import ReviewDecisionId, ReviewDecisionKind


def _assert_failure(
    captured: pytest.ExceptionInfo[ReviewDecisionOperationFailure],
    code: ReviewDecisionOperationFailureCode,
) -> None:
    error = captured.value
    assert error.code is code
    assert error.args == (code.value,)
    assert str(error) == code.value
    assert repr(error) == f"ReviewDecisionOperationFailure(code={code.value})"
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("field", ("_history", "_history_bytes"))
def test_replay_revalidates_current_retained_history_against_consumed_script(
    field: str,
) -> None:
    command = request()
    scripted = step(value=command, decision_suffix=1100, audit_suffix=1150)
    recorded = adapter(scripted)
    workflow = service(recorded)
    original = workflow.execute(request=command)
    if field == "_history":
        object.__setattr__(recorded, field, empty_history(command))
    else:
        object.__setattr__(recorded, field, b"tampered-history-bytes")

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        workflow.execute(request=command)

    _assert_failure(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert original.canonical_bytes() == scripted_result(scripted).canonical_bytes()
    assert object.__getattribute__(recorded, "_index") == 1


def test_replay_rejects_valid_shape_step_result_replacement() -> None:
    command = request()
    scripted = step(value=command, decision_suffix=1110, audit_suffix=1160)
    alternate = step(value=command, decision_suffix=1111, audit_suffix=1161)
    recorded = adapter(scripted)
    workflow = service(recorded)
    workflow.execute(request=command)
    object.__setattr__(scripted, "_result", scripted_result(alternate))

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        workflow.execute(request=command)

    _assert_failure(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)


def test_changed_request_digest_fails_before_consumption_and_can_be_restored() -> None:
    command = request()
    scripted = step(value=command)
    recorded = adapter(scripted)
    original_digest = command.request_sha256
    object.__setattr__(command, "request_sha256", RecordedSha256("0" * 64))

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        service(recorded).execute(request=command)

    _assert_failure(captured, ReviewDecisionOperationFailureCode.INVALID_ARGUMENT)
    assert object.__getattribute__(recorded, "_index") == 0
    object.__setattr__(command, "request_sha256", original_digest)
    assert service(recorded).execute(request=command).request_sha256 == original_digest


def test_valid_shape_prior_replacement_cannot_consume_next_step() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1120, audit_suffix=1170)
    second_request = request(
        assignment=first_request.assignment,
        decision=ReviewDecisionKind.REJECT,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:PRIOR:TAMPER",
        idempotency_key="ST0901-PR3-LOCAL-PRIOR-TAMPER-KEY",
    )
    second_step = step(
        value=second_request,
        prior_history=scripted_result(first_step).history,
        decision_suffix=1121,
        audit_suffix=1171,
    )
    recorded = adapter(first_step, second_step)
    workflow = service(recorded)
    workflow.execute(request=first_request)
    object.__setattr__(second_step, "prior_history", empty_history(second_request))

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        workflow.execute(request=second_request)

    _assert_failure(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert object.__getattribute__(recorded, "_index") == 1


@pytest.mark.parametrize("field", ("grant", "actor"))
def test_valid_shape_grant_or_actor_replacement_cannot_reach_exchange(
    field: str,
) -> None:
    command = request()
    scripted = step(value=command)
    recorded = adapter(scripted)
    replacement: object
    if field == "grant":
        replacement = recorded_grant(
            correlation_id=command.correlation_id,
            target=command.target,
            rule_id="ST0901_PR3_RECORDED_LOCAL_V1:VALID_ALT_RULE",
        )
    else:
        replacement = identity(OTHER_REVIEWER_ID)
    object.__setattr__(scripted, field, replacement)

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        service(recorded).execute(request=command)

    _assert_failure(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert object.__getattribute__(recorded, "_index") == 0


def test_duplicate_decision_id_and_forward_reference_fail_history_construction() -> (
    None
):
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1130, audit_suffix=1180)
    first = scripted_result(first_step)
    second_request = request(
        assignment=first_request.assignment,
        supersedes_decision_id=first.record.decision_id,
        correlation="ST0901_PR3_RECORDED_LOCAL_V1:DUPLICATE",
        idempotency_key="ST0901-PR3-LOCAL-DUPLICATE-KEY",
    )
    with pytest.raises(ReviewDecisionOperationFailure) as duplicate:
        step(
            value=second_request,
            prior_history=first.history,
            decision_suffix=1130,
            audit_suffix=1181,
        )
    _assert_failure(duplicate, ReviewDecisionOperationFailureCode.HISTORY_MISMATCH)

    second_step = step(
        value=second_request,
        prior_history=first.history,
        decision_suffix=1131,
        audit_suffix=1181,
    )
    second = scripted_result(second_step)
    future_id = ReviewDecisionId(uuid7(1132))
    forward = replace(
        first.record,
        supersedes_decision_id=future_id,
        superseded_record_sha256=second.record.record_sha256,
    )
    with pytest.raises(ReviewDecisionOperationFailure) as forward_failure:
        RecordedReviewDecisionHistoryV1(
            assignment_id=first.history.assignment_id,
            article_version_id=first.history.article_version_id,
            records=(forward, second.record),
        )
    _assert_failure(
        forward_failure,
        ReviewDecisionOperationFailureCode.HISTORY_MISMATCH,
    )


def test_missing_self_and_cross_binding_prior_fail_without_append() -> None:
    first_request = request()
    first_step = step(value=first_request, decision_suffix=1140, audit_suffix=1190)
    first = scripted_result(first_step)
    missing_or_self = (
        ReviewDecisionId(uuid7(1141)),
        first.record.decision_id,
    )
    for index, prior_id in enumerate(missing_or_self, start=1):
        command = request(
            assignment=first_request.assignment,
            supersedes_decision_id=prior_id,
            idempotency_key=f"ST0901-PR3-LOCAL-MISSING-SELF-{index}",
        )
        decision_suffix = 1140 if prior_id == first.record.decision_id else 1142
        with pytest.raises(ReviewDecisionOperationFailure) as captured:
            step(
                value=command,
                prior_history=first.history,
                decision_suffix=decision_suffix,
                audit_suffix=1190 + index,
            )
        _assert_failure(
            captured,
            ReviewDecisionOperationFailureCode.HISTORY_MISMATCH,
        )

    other = request()
    cross = request(
        assignment=replace(
            other.assignment,
            assignment_id=type(other.assignment.assignment_id)(uuid7(1999)),
        ),
        supersedes_decision_id=first.record.decision_id,
        idempotency_key="ST0901-PR3-LOCAL-CROSS-BINDING-KEY",
    )
    with pytest.raises(ReviewDecisionOperationFailure) as cross_failure:
        step(value=cross, prior_history=first.history)
    _assert_failure(
        cross_failure,
        ReviewDecisionOperationFailureCode.HISTORY_MISMATCH,
    )


def test_raw_key_and_human_text_never_enter_replay_envelopes_or_failures() -> None:
    raw_key = "ST0901-PR3-SECRET-LIKE-RAW-KEY"
    raw_text = "sensitive human review explanation"
    command = request(idempotency_key=raw_key, summary=raw_text)
    result = service(adapter(step(value=command))).execute(request=command)
    changed = request(
        assignment=command.assignment,
        idempotency_key=raw_key,
        summary="different sensitive explanation",
    )

    for rendered in (
        command.canonical_bytes(),
        result.canonical_bytes(),
        result.audit.canonical_bytes(),
        result.idempotency.canonical_bytes(),
    ):
        assert raw_key.encode() not in rendered
        assert raw_text.encode() not in rendered

    recorded = adapter(step(value=command))
    workflow = service(recorded)
    workflow.execute(request=command)
    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        workflow.execute(request=changed)
    _assert_failure(
        captured,
        ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE,
    )
    assert raw_key not in repr(captured.value)
    assert raw_text not in repr(captured.value)


def test_closed_failures_and_values_deny_pickle() -> None:
    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        fail_review_decision_operation()
    value = request()
    for item in (captured.value, value, value.request_sha256, step(value=value)):
        with pytest.raises(TypeError):
            pickle.dumps(item)


def test_owned_source_has_no_runtime_or_external_effect_dependencies() -> None:
    repository = Path(__file__).resolve().parents[2]
    owned = (
        repository / "python/raos/domain/publishing/review_decision_operations.py",
        repository / "python/raos/ports/review_decision.py",
        repository / "python/raos/application/publishing/review_decision.py",
        repository / "python/raos/adapters/recorded_review_decision.py",
    )
    forbidden_imports = {
        "asyncio",
        "fastapi",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "socket",
        "sqlalchemy",
        "subprocess",
        "time",
        "urllib",
    }
    forbidden_calls = {
        "clock",
        "now",
        "time",
        "today",
        "uuid1",
        "uuid4",
        "uuid6",
        "uuid7",
    }
    for path in owned:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not (
                    {alias.name.split(".")[0] for alias in node.names}
                    & forbidden_imports
                )
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.module.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None
                )
                assert name not in forbidden_calls
    combined = "\n".join(path.read_text(encoding="utf-8") for path in owned)
    for forbidden in (
        "PolicyFinding",
        "PolicyEvaluationResult",
        "resolve_finding",
        "waive_finding",
        "def publish(",
        ".publish(",
        "outbox.append",
        "emit_event",
        "transition_review_assignment",
        "complete_assignment",
        "effective_decision",
        "latest_decision",
    ):
        assert forbidden not in combined
