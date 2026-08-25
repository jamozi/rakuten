"""Recorded adapter and application failure-isolation tests."""

from __future__ import annotations

from dataclasses import replace
import ast
import hashlib
import json
import pickle
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT
from raos.adapters.recorded_gate2_observation import RecordedGate2ObservationAdapter
from raos.application.analytics.gate2_observation import RecordedGate2ObservationJob
from raos.domain.analytics.gate2_observation import (
    FixtureByteLength,
    ObservationCommand,
    ObservationFailure,
    ObservationFailureCode,
    RecordedObservationBatch,
    Sha256Digest,
)
from scripts import build_st1803_gate2_observation as builder


def _rebound(command: ObservationCommand, content: bytes) -> ObservationCommand:
    return replace(
        command,
        fixture_digest=Sha256Digest.of(content),
        fixture_length=FixtureByteLength(len(content)),
    )


def test_adapter_consumes_exact_fixture_once(
    fixture_bytes: bytes, command: ObservationCommand
) -> None:
    adapter = RecordedGate2ObservationAdapter(fixture_bytes)
    observed = adapter.read(command)
    assert type(observed) is RecordedObservationBatch
    assert len(observed.articles) == 5
    with pytest.raises(ObservationFailure) as captured:
        adapter.read(command)
    assert captured.value.code is ObservationFailureCode.RECORDED_EXCHANGE_EXHAUSTED


def test_fixture_byte_tamper_fails_before_parsing(
    fixture_bytes: bytes, command: ObservationCommand
) -> None:
    with pytest.raises(ObservationFailure) as captured:
        RecordedGate2ObservationAdapter(fixture_bytes + b" ").read(command)
    assert captured.value.code is ObservationFailureCode.FIXTURE_BYTES_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace(
            '"schema": "ST1803_RECORDED_SYNTHETIC_OBSERVATION_V1",',
            '"schema": "ST1803_RECORDED_SYNTHETIC_OBSERVATION_V1", "schema": "ST1803_RECORDED_SYNTHETIC_OBSERVATION_V1",',
            1,
        ),
        lambda text: text.replace(
            '"synthetic": true', '"synthetic": true, "unknown": null', 1
        ),
        lambda text: text.replace('"value": 260', '"value": 2.6', 1),
        lambda text: text.replace('"value": 260', '"value": true', 1),
        lambda text: text.replace('"value": 260', '"value": -1', 1),
        lambda text: text.replace(
            '"article_id":', '"email": "secret@example.invalid", "article_id":', 1
        ),
        lambda text: text.replace('"sequence": 2', '"sequence": 3', 1),
        lambda text: text.replace('"entry_sha256": "88', '"entry_sha256": "99', 1),
        lambda text: text.replace(
            '"program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"',
            '"program": "OTHER_PROGRAM"',
            1,
        ),
    ],
)
def test_strict_fixture_rejects_hostile_documents(
    fixture_bytes: bytes,
    command: ObservationCommand,
    mutation: Any,
) -> None:
    content = mutation(fixture_bytes.decode()).encode()
    with pytest.raises(ObservationFailure) as captured:
        RecordedGate2ObservationAdapter(content).read(_rebound(command, content))
    assert captured.value.code is ObservationFailureCode.FIXTURE_DOCUMENT_INVALID
    assert "secret@example.invalid" not in str(captured.value)


def test_oversized_fixture_is_rejected_without_parse(
    command: ObservationCommand,
) -> None:
    content = b"{" + b" " * (4 * 1024 * 1024) + b"}"
    with pytest.raises(ObservationFailure):
        RecordedGate2ObservationAdapter(content)


def test_port_exception_is_redacted_and_not_retried(
    command: ObservationCommand,
) -> None:
    class ExplodingExchange:
        calls = 0

        def read(self, candidate: ObservationCommand) -> RecordedObservationBatch:
            del candidate
            self.calls += 1
            raise RuntimeError("SECRET_CANARY_ST1803")

    exchange = ExplodingExchange()
    with pytest.raises(ObservationFailure) as captured:
        RecordedGate2ObservationJob(exchange=exchange).observe(command)
    assert captured.value.code is ObservationFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
    assert exchange.calls == 1
    assert "SECRET_CANARY" not in str(captured.value)


def test_wrong_port_result_is_rejected(command: ObservationCommand) -> None:
    class WrongExchange:
        def read(self, candidate: ObservationCommand) -> object:
            del candidate
            return object()

    with pytest.raises(ObservationFailure) as captured:
        RecordedGate2ObservationJob(exchange=WrongExchange()).observe(command)
    assert captured.value.code is ObservationFailureCode.RECORDED_RESULT_MISMATCH


def test_sensitive_domain_values_and_failures_are_not_pickleable(
    fixture_bytes: bytes, command: ObservationCommand
) -> None:
    batch = RecordedGate2ObservationAdapter(fixture_bytes).read(command)
    for value in (
        command,
        batch,
        batch.articles[0],
        batch.articles[0].metrics[0],
        ObservationFailure(ObservationFailureCode.INVALID_ARGUMENT),
    ):
        assert "st1704" not in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_runtime_ast_has_no_provider_network_storage_or_public_capability() -> None:
    forbidden_imports = {
        "boto3",
        "botocore",
        "http",
        "os",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    for path in (
        builder.DOMAIN_PATH,
        builder.PORT_PATH,
        builder.APPLICATION_PATH,
        builder.ADAPTER_PATH,
    ):
        source = (REPOSITORY_ROOT / path).read_text()
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden_imports)
        lowered = source.lower()
        for token in (
            "publish(",
            "requests.get",
            "urlopen",
            "credential_lookup",
            "recommendation_order =",
            "article_html =",
        ):
            assert token not in lowered


def test_fixture_contains_no_prohibited_personal_or_secret_material(
    fixture_bytes: bytes,
) -> None:
    lowered = fixture_bytes.lower()
    for token in (
        b"email",
        b"phone",
        b"raw_ip",
        b"full_user_agent",
        b"article_body",
        b"source_packet_text",
        b"token",
        b"secret",
    ):
        assert token not in lowered
    assert hashlib.sha256(fixture_bytes).hexdigest() == builder.FIXTURE_SHA256
    parsed = json.loads(fixture_bytes)
    assert parsed["synthetic"] is True
    assert parsed["append_only"] is True
    assert parsed["immutable"] is True
