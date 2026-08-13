"""Trust, authority, architecture, and no-side-effect boundaries for ST-1703."""

from __future__ import annotations

import ast
import builtins
from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
from typing import cast
from urllib import request as urllib_request
import webbrowser

import pytest

from raos.adapters.recorded_wordpress_draft import RecordedWordPressDraftAdapter
from raos.adapters.wordpress_rest import OfficialWordPressRestRequestBuilder
from raos.application.editorial.market_learning_pilot import (
    MarketLearningPilotService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import (
    RakutenItemSearchResult,
    RateLimitMetadata,
)
from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    DraftDisposition,
    DraftOperation,
    MarketLearningPilotFailure,
    MarketLearningPilotFailureCode,
    PilotAuthorizationStatus,
    PilotEconomics,
    PilotEvidenceAuthority,
    PilotExecutionStatus,
    PilotObservationStatus,
    WordPressDraftReceipt,
    WordPressDraftIntent,
)
from raos.domain.editorial.policy_engine import (
    PolicyEvaluationResult,
    WaiverEvaluation,
)
from raos.ports.wordpress_draft import WordPressDraftPort


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTICLE_VERSION_ID = "ARTICLE-VERSION-1703"


def _intent(*, article_version_id: str = ARTICLE_VERSION_ID) -> WordPressDraftIntent:
    return WordPressDraftIntent(
        operation=DraftOperation.CREATE_DRAFT,
        article_version_id=article_version_id,
        title="Synthetic local pilot",
        content="<p>No external side effect.</p>",
    )


def _service(port: WordPressDraftPort | None = None) -> MarketLearningPilotService:
    return MarketLearningPilotService(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_port=(
            RecordedWordPressDraftAdapter(
                environment=RuntimeEnvironment.ENV_DEV,
                draft_capacity=2,
            )
            if port is None
            else port
        ),
    )


def _execute(
    *,
    policy_result: PolicyEvaluationResult,
    rakuten_result: RakutenItemSearchResult,
    intent: WordPressDraftIntent | None = None,
    port: WordPressDraftPort | None = None,
):
    return _service(port).execute(
        pilot=PilotEconomics(),
        intent=_intent() if intent is None else intent,
        policy_result=policy_result,
        rakuten_result=rakuten_result,
    )


def _replace_policy_json(
    result: PolicyEvaluationResult,
    payload: dict[str, object],
) -> PolicyEvaluationResult:
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return replace(
        result,
        local_result_json=serialized,
        local_result_digest=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    )


def test_policy_result_rejects_nonempty_waiver_evaluations_before_exchange(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    unsafe = replace(
        eligible_policy_result,
        waiver_evaluations=cast(tuple[WaiverEvaluation, ...], (object(),)),
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_INELIGIBLE


@pytest.mark.parametrize("raw_score", [None, "100", True, float("nan"), Decimal("84")])
def test_policy_result_rejects_invalid_score_types_without_leaking_runtime_errors(
    raw_score: object,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    unsafe = replace(
        eligible_policy_result,
        raw_quality_score=raw_score,  # type: ignore[arg-type]
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_INELIGIBLE


def test_policy_json_rejects_oversized_integer_valueerror_with_closed_code(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    serialized = '{"oversized":' + ("9" * 5_000) + "}"
    unsafe = replace(
        eligible_policy_result,
        local_result_json=serialized,
        local_result_digest=hashlib.sha256(serialized.encode()).hexdigest(),
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID


@pytest.mark.parametrize("shape", ["duplicate", "noncanonical"])
def test_policy_json_must_be_unique_key_canonical_serialization(
    shape: str,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    if shape == "duplicate":
        serialized = (
            '{"article_version_id":"ARTICLE-VERSION-1703",'
            '"article_version_id":"ARTICLE-VERSION-1703"}'
        )
    else:
        serialized = eligible_policy_result.local_result_json + " "
    unsafe = replace(
        eligible_policy_result,
        local_result_json=serialized,
        local_result_digest=hashlib.sha256(serialized.encode()).hexdigest(),
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("derived", "local_eligibility", False),
        ("derived", "policy_rules_passed", False),
        ("derived", "predecessors_available", False),
        ("derived", "quality_floors_met", False),
        ("derived", "quality_gates_passed", False),
        ("derived", "quality_threshold_met", False),
        ("derived", "raw_quality_score", "99"),
        ("derived", "zero_tolerance_clear", False),
        ("authority", "publication_authorized", True),
        ("authority", "production_eligible", True),
        ("authority", "formal_test", "EXECUTED"),
    ],
)
def test_every_relayed_policy_flag_must_match_its_canonical_json(
    section: str,
    key: str,
    value: object,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    payload = cast(
        dict[str, object], json.loads(eligible_policy_result.local_result_json)
    )
    nested = cast(dict[str, object], payload[section])
    nested[key] = value
    unsafe = _replace_policy_json(eligible_policy_result, payload)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID


@pytest.mark.parametrize(
    ("typed_field", "json_key", "typed_value", "json_value"),
    [
        ("publication_authorized", "publication_authorized", True, True),
        ("production_eligible", "production_eligible", True, True),
        ("formal_test_status", "formal_test", "EXECUTED", "EXECUTED"),
        (
            "live_validation_status",
            "live_validation",
            "EXECUTED",
            "EXECUTED",
        ),
        ("staging_status", "staging", "EXECUTED", "EXECUTED"),
        ("release_status", "release", "EXECUTED", "EXECUTED"),
        ("production_status", "production", "EXECUTED", "EXECUTED"),
    ],
)
def test_consistently_inflated_typed_policy_authority_is_rejected(
    typed_field: str,
    json_key: str,
    typed_value: object,
    json_value: object,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    payload = cast(
        dict[str, object], json.loads(eligible_policy_result.local_result_json)
    )
    authority = cast(dict[str, object], payload["authority"])
    authority[json_key] = json_value
    unsafe = _replace_policy_json(eligible_policy_result, payload)
    unsafe = replace(unsafe, **{typed_field: typed_value})

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID


def test_policy_payload_may_not_invent_an_input_findings_collection(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    payload = cast(
        dict[str, object], json.loads(eligible_policy_result.local_result_json)
    )
    payload["input_findings"] = []
    unsafe = _replace_policy_json(eligible_policy_result, payload)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=unsafe, rakuten_result=recorded_rakuten_result)

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID


def test_policy_digest_and_article_binding_fail_before_draft_exchange(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as digest_failure:
        _execute(
            policy_result=replace(
                eligible_policy_result,
                local_result_digest="0" * 64,
            ),
            rakuten_result=recorded_rakuten_result,
        )
    assert (
        digest_failure.value.code
        is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID
    )

    with pytest.raises(MarketLearningPilotFailure) as article_failure:
        _execute(
            policy_result=eligible_policy_result,
            rakuten_result=recorded_rakuten_result,
            intent=_intent(article_version_id="ARTICLE-VERSION-FOREIGN"),
        )
    assert (
        article_failure.value.code
        is MarketLearningPilotFailureCode.POLICY_RESULT_INVALID
    )


def test_rakuten_result_requires_exact_page_rate_binding(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    different_rate = RateLimitMetadata(
        limit=101,
        remaining=100,
        reset_at=recorded_rakuten_result.rate.reset_at + timedelta(seconds=1),
    )
    mismatched = replace(recorded_rakuten_result, rate=different_rate)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(policy_result=eligible_policy_result, rakuten_result=mismatched)

    assert failure.value.code is MarketLearningPilotFailureCode.RAKUTEN_RESULT_INVALID


class _WrongReceiptPort:
    def __init__(self) -> None:
        self.call_count = 0

    def apply(self, candidate: object) -> object:
        del candidate
        self.call_count += 1
        return object()


class _ExplodingPort:
    def apply(self, candidate: object) -> object:
        del candidate
        raise RuntimeError("RAW_CREDENTIAL_VALUE_CANARY")


class _TamperedReceiptPort:
    def __init__(self, field_name: str, unsafe_value: object) -> None:
        self._field_name = field_name
        self._unsafe_value = unsafe_value
        self.call_count = 0

    def apply(self, candidate: BoundWordPressDraft) -> WordPressDraftReceipt:
        self.call_count += 1
        receipt = WordPressDraftReceipt(
            draft_id=1703,
            operation=candidate.intent.operation,
            disposition=DraftDisposition.CREATED,
            status="draft",
            content_binding_sha256=candidate.content_binding_sha256,
            operation_binding_sha256=candidate.operation_binding_sha256,
            logical_draft_sha256="d" * 64,
            network_status=PilotExecutionStatus.NOT_EXECUTED,
            publication_authorized=False,
            production_eligible=False,
        )
        object.__setattr__(receipt, self._field_name, self._unsafe_value)
        return receipt


def test_invalid_policy_fails_before_the_draft_port_is_called(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    port = _WrongReceiptPort()
    ineligible = replace(eligible_policy_result, local_eligibility=False)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(
            policy_result=ineligible,
            rakuten_result=recorded_rakuten_result,
            port=cast(WordPressDraftPort, port),
        )

    assert failure.value.code is MarketLearningPilotFailureCode.POLICY_INELIGIBLE
    assert port.call_count == 0


def test_collaborator_failures_are_one_call_and_sanitized(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    wrong = _WrongReceiptPort()
    with pytest.raises(MarketLearningPilotFailure) as mismatch:
        _execute(
            policy_result=eligible_policy_result,
            rakuten_result=recorded_rakuten_result,
            port=cast(WordPressDraftPort, wrong),
        )
    assert mismatch.value.code is MarketLearningPilotFailureCode.OUTCOME_MISMATCH
    assert wrong.call_count == 1

    with pytest.raises(MarketLearningPilotFailure) as unavailable:
        _execute(
            policy_result=eligible_policy_result,
            rakuten_result=recorded_rakuten_result,
            port=cast(WordPressDraftPort, _ExplodingPort()),
        )
    assert (
        unavailable.value.code
        is MarketLearningPilotFailureCode.DRAFT_EXCHANGE_UNAVAILABLE
    )
    assert "CANARY" not in str(unavailable.value)
    assert "CANARY" not in repr(unavailable.value)
    assert unavailable.value.__cause__ is None
    assert unavailable.value.__suppress_context__ is True


@pytest.mark.parametrize(
    ("field_name", "unsafe_value"),
    [
        ("draft_id", []),
        ("operation", DraftOperation.UPDATE_DRAFT),
        ("disposition", []),
        ("status", "publish"),
        ("content_binding_sha256", "0" * 64),
        ("operation_binding_sha256", object()),
        ("logical_draft_sha256", "not-a-digest"),
        ("network_status", "EXECUTED"),
        ("publication_authorized", True),
        ("production_eligible", True),
    ],
)
def test_typed_tampered_receipt_fails_closed_before_evidence(
    field_name: str,
    unsafe_value: object,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    port = _TamperedReceiptPort(field_name, unsafe_value)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(
            policy_result=eligible_policy_result,
            rakuten_result=recorded_rakuten_result,
            port=port,
        )

    assert failure.value.code is MarketLearningPilotFailureCode.OUTCOME_MISMATCH
    assert port.call_count == 1


@pytest.mark.parametrize("environment", list(RuntimeEnvironment)[2:])
def test_service_rejects_every_nonlocal_environment(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        MarketLearningPilotService(
            environment=environment,
            draft_port=RecordedWordPressDraftAdapter(
                environment=RuntimeEnvironment.ENV_DEV,
                draft_capacity=1,
            ),
        )

    assert failure.value.code is MarketLearningPilotFailureCode.ENVIRONMENT_DISABLED


@pytest.mark.parametrize(
    ("nested", "unsafe_value"), [("page", object()), ("rate", None)]
)
def test_exact_tampered_rakuten_result_is_sanitized(
    nested: str,
    unsafe_value: object,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    object.__setattr__(recorded_rakuten_result, nested, unsafe_value)

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(
            policy_result=eligible_policy_result,
            rakuten_result=recorded_rakuten_result,
        )

    assert failure.value.code is MarketLearningPilotFailureCode.RAKUTEN_RESULT_INVALID


def _forbidden_side_effect(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("external side effect attempted")


def test_recorded_service_and_request_builder_attempt_no_external_side_effect(
    monkeypatch: pytest.MonkeyPatch,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    monkeypatch.setattr(builtins, "open", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_bytes", _forbidden_side_effect)
    monkeypatch.setattr(Path, "write_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "write_bytes", _forbidden_side_effect)
    monkeypatch.setattr(io, "open", _forbidden_side_effect)
    monkeypatch.setattr(os, "open", _forbidden_side_effect)
    monkeypatch.setattr(os, "getenv", _forbidden_side_effect)
    monkeypatch.setattr(os, "system", _forbidden_side_effect)
    monkeypatch.setattr(time, "time", _forbidden_side_effect)
    monkeypatch.setattr(time, "monotonic", _forbidden_side_effect)
    monkeypatch.setattr(time, "monotonic_ns", _forbidden_side_effect)
    monkeypatch.setattr(socket, "socket", _forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", _forbidden_side_effect)
    monkeypatch.setattr(subprocess, "run", _forbidden_side_effect)
    monkeypatch.setattr(subprocess, "Popen", _forbidden_side_effect)
    monkeypatch.setattr(webbrowser, "open", _forbidden_side_effect)
    monkeypatch.setattr(urllib_request, "urlopen", _forbidden_side_effect)

    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_capacity=2,
    )
    result = _execute(
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
        port=adapter,
    )
    replay = _execute(
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
        port=adapter,
    )
    update = _execute(
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
        intent=WordPressDraftIntent(
            operation=DraftOperation.UPDATE_DRAFT,
            article_version_id=ARTICLE_VERSION_ID,
            title="Synthetic local pilot",
            content="<p>Updated without an external side effect.</p>",
            existing_draft_id=result.receipt.draft_id,
        ),
        port=adapter,
    )
    builder = OfficialWordPressRestRequestBuilder(
        origin="https://wordpress.example.invalid"
    )
    request = builder.build(
        candidate=result.candidate,
        endpoint_url=("https://wordpress.example.invalid/wp-json/wp/v2/posts"),
        credential_secret_alias="wordpress_application_password",
    )
    update_request = builder.build(
        candidate=update.candidate,
        endpoint_url=(
            f"https://wordpress.example.invalid/wp-json/wp/v2/posts/"
            f"{result.receipt.draft_id}"
        ),
        credential_secret_alias="wordpress_application_password",
        existing_draft_receipt=result.receipt,
    )

    assert request.method == "POST"
    assert request.expected_http_status == 201
    assert replay.receipt.disposition is DraftDisposition.REPLAYED
    assert update.receipt.disposition is DraftDisposition.UPDATED
    assert update_request.expected_http_status == 200


def test_evidence_keeps_local_and_all_external_authorities_separate(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    evidence = _execute(
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
    ).evidence

    assert evidence.authority is PilotEvidenceAuthority.LOCAL_RECORDED_ONLY
    assert evidence.local_execution is PilotExecutionStatus.EXECUTED_LOCAL_RECORDED
    assert evidence.formal_test is PilotExecutionStatus.NOT_EXECUTED
    assert evidence.live_validation is PilotExecutionStatus.NOT_EXECUTED
    assert evidence.staging is PilotExecutionStatus.NOT_EXECUTED
    assert evidence.release is PilotExecutionStatus.NOT_EXECUTED
    assert evidence.publication is PilotAuthorizationStatus.NOT_AUTHORIZED
    assert evidence.revenue is PilotObservationStatus.NOT_OBSERVED
    assert evidence.production is PilotExecutionStatus.NOT_EXECUTED
    field_names = {field.name for field in fields(evidence)}
    assert not field_names & {
        "credential",
        "password",
        "raw_body",
        "provider_body",
        "publication_approval",
    }


def test_four_layer_imports_have_no_network_client_or_framework_dependency() -> None:
    files = (
        "python/raos/domain/editorial/market_learning_pilot.py",
        "python/raos/application/editorial/market_learning_pilot.py",
        "python/raos/ports/wordpress_draft.py",
        "python/raos/adapters/recorded_wordpress_draft.py",
        "python/raos/adapters/wordpress_rest.py",
    )
    forbidden_imports = {
        "boto3",
        "django",
        "fastapi",
        "httpx",
        "playwright",
        "requests",
        "selenium",
        "sqlalchemy",
        "urllib.request",
        "wordpress",
    }
    for relative in files:
        source = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert not imported & forbidden_imports

    public_port_members = {
        name for name in WordPressDraftPort.__dict__ if not name.startswith("_")
    }
    assert public_port_members == {"apply"}
    assert {operation.value for operation in DraftOperation} == {
        "CREATE_DRAFT",
        "UPDATE_DRAFT",
    }
    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_capacity=1,
    )
    for forbidden in ("publish", "schedule", "delete", "upload", "send"):
        assert not hasattr(adapter, forbidden)
