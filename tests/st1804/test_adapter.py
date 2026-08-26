"""Strict adapter, replay, redaction and capability-negative tests."""

from __future__ import annotations

from dataclasses import replace
import ast
import hashlib
import json
import pickle
from typing import Any, cast

import pytest

from .support import REPOSITORY_ROOT
from raos.adapters.recorded_gate3_economics import RecordedGate3EconomicsAdapter
from raos.application.analytics.gate3_economics import RecordedGate3EconomicsJob
from raos.domain.analytics.gate3_economics import (
    FixtureByteLength,
    Gate3Command,
    Gate3Failure,
    Gate3FailureCode,
    RecordedEconomicsBatch,
    Sha256Digest,
)
from raos.ports.gate3_economics import RecordedGate3EconomicsExchange
from scripts import build_st1804_gate3_economics as builder


def _rebound(command: Gate3Command, content: bytes) -> Gate3Command:
    return replace(
        command,
        fixture_digest=Sha256Digest.of(content),
        fixture_length=FixtureByteLength(len(content)),
    )


def test_adapter_consumes_exact_fixture_once(
    fixture_bytes: bytes,
    command: Gate3Command,
) -> None:
    adapter = RecordedGate3EconomicsAdapter(fixture_bytes)
    assert type(adapter.read(command)) is RecordedEconomicsBatch
    with pytest.raises(Gate3Failure) as captured:
        adapter.read(command)
    assert captured.value.code is Gate3FailureCode.RECORDED_EXCHANGE_EXHAUSTED


def test_fixture_byte_tamper_fails_before_parse(
    fixture_bytes: bytes,
    command: Gate3Command,
) -> None:
    with pytest.raises(Gate3Failure) as captured:
        RecordedGate3EconomicsAdapter(fixture_bytes + b" ").read(command)
    assert captured.value.code is Gate3FailureCode.FIXTURE_BYTES_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace(
            '"synthetic": true', '"synthetic": true, "synthetic": true', 1
        ),
        lambda text: text.replace(
            '"synthetic": true', '"synthetic": true, "unknown": null', 1
        ),
        lambda text: text.replace('"synthetic": true', '"synthetic": false', 1),
        lambda text: text.replace(
            '"actual_observation": false', '"actual_observation": true', 1
        ),
        lambda text: text.replace('"append_only": true', '"append_only": false', 1),
        lambda text: text.replace('"immutable": true', '"immutable": false', 1),
        lambda text: text.replace('"value": 10000', '"value": 1.5', 1),
        lambda text: text.replace('"value": 10000', f'"value": {"9" * 5000}', 1),
        lambda text: text.replace('"value": 10000', '"value": true', 1),
        lambda text: text.replace('"value": 10000', '"value": -1', 1),
        lambda text: text.replace(
            '"attribution_verified": true',
            '"email": "secret@example.invalid", "attribution_verified": true',
            1,
        ),
        lambda text: text.replace('"sequence": 2', '"sequence": 3', 1),
        lambda text: text.replace('"entry_sha256": "c6', '"entry_sha256": "99', 1),
        lambda text: text.replace(
            '"program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"',
            '"program": "OTHER_PROGRAM"',
            1,
        ),
    ],
)
def test_hostile_fixture_documents_fail_closed_without_reflection(
    fixture_bytes: bytes,
    command: Gate3Command,
    mutation: Any,
) -> None:
    content = mutation(fixture_bytes.decode()).encode()
    with pytest.raises(Gate3Failure) as captured:
        RecordedGate3EconomicsAdapter(content).read(_rebound(command, content))
    assert captured.value.code is Gate3FailureCode.FIXTURE_DOCUMENT_INVALID
    assert "secret@example.invalid" not in str(captured.value)


def test_port_exception_is_redacted_and_not_retried(command: Gate3Command) -> None:
    class ExplodingExchange:
        calls = 0

        def read(self, candidate: Gate3Command) -> RecordedEconomicsBatch:
            del candidate
            self.calls += 1
            raise RuntimeError("SECRET_CANARY_ST1804")

    exchange = ExplodingExchange()
    with pytest.raises(Gate3Failure) as captured:
        RecordedGate3EconomicsJob(exchange=exchange).evaluate(command)
    assert captured.value.code is Gate3FailureCode.RECORDED_EXCHANGE_UNAVAILABLE
    assert exchange.calls == 1
    assert "SECRET_CANARY" not in str(captured.value)


def test_wrong_port_result_is_rejected(command: Gate3Command) -> None:
    class WrongExchange:
        def read(self, candidate: Gate3Command) -> object:
            del candidate
            return object()

    with pytest.raises(Gate3Failure) as captured:
        RecordedGate3EconomicsJob(
            exchange=cast(RecordedGate3EconomicsExchange, WrongExchange())
        ).evaluate(command)
    assert captured.value.code is Gate3FailureCode.RECORDED_RESULT_MISMATCH


def test_domain_values_and_failures_are_redacted_and_non_pickleable(
    batch: RecordedEconomicsBatch,
    command: Gate3Command,
) -> None:
    for value in (
        command,
        batch,
        batch.months[0],
        batch.months[0].metrics[0],
        Gate3Failure(Gate3FailureCode.INVALID_ARGUMENT),
    ):
        assert "10000" not in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_owned_runtime_has_no_provider_network_storage_or_public_capability() -> None:
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


def test_fixture_contains_no_personal_secret_or_real_provider_rows(
    fixture_bytes: bytes,
) -> None:
    lowered = fixture_bytes.lower()
    for token in (
        b"email",
        b"phone",
        b"raw_ip",
        b"full_user_agent",
        b"article_body",
        b"raw_provider_row",
        b"source_packet_text",
        b"token",
        b"secret",
    ):
        assert token not in lowered
    assert hashlib.sha256(fixture_bytes).hexdigest() == builder.FIXTURE_SHA256
    parsed = json.loads(fixture_bytes)
    assert parsed["synthetic"] is True
    assert parsed["actual_observation"] is False
