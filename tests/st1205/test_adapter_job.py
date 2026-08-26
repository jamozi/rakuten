"""Recorded adapter, port, and application failure-isolation tests."""

from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import pickle
from typing import Any

import pytest

from .support import REPOSITORY_ROOT
from raos.adapters import recorded_kpi_input as adapter_module
from raos.adapters.recorded_kpi_input import RecordedKpiInputAdapter
from raos.application.analytics.kpi_read_model import RecordedKpiCalculationJob
from raos.domain.analytics.kpi_read_model import (
    KpiCalculationCommand,
    KpiFailure,
    KpiFailureCode,
    KpiInputFrame,
    RecordedKpiInputBatch,
)
from scripts import build_st1205_kpi_read_model_reference_plan as builder


def _rebind_fixture(monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:
    monkeypatch.setattr(adapter_module, "COMPLETE_FIXTURE_BYTES", len(content))
    monkeypatch.setattr(
        adapter_module, "COMPLETE_FIXTURE_SHA256", hashlib.sha256(content).hexdigest()
    )


def _rebound_command(
    command: KpiCalculationCommand, content: bytes
) -> KpiCalculationCommand:
    return replace(
        command,
        fixture_digest=type(command.fixture_digest)(
            hashlib.sha256(content).hexdigest()
        ),
        fixture_length=type(command.fixture_length)(len(content)),
    )


def test_adapter_consumes_exact_fixture_once(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    adapter = RecordedKpiInputAdapter(fixture_bytes)
    batch = adapter.read(command)
    assert type(batch) is RecordedKpiInputBatch
    assert len(batch.input_frame.observations) == 47
    with pytest.raises(KpiFailure) as captured:
        adapter.read(command)
    assert captured.value.code is KpiFailureCode.RECORDED_EXCHANGE_EXHAUSTED


def test_fixture_byte_tamper_fails_before_parsing(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    with pytest.raises(KpiFailure) as captured:
        RecordedKpiInputAdapter(fixture_bytes + b" ").read(command)
    assert captured.value.code is KpiFailureCode.FIXTURE_BYTES_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace(
            '"schema_version": "2.0.0",',
            '"schema_version": "2.0.0", "schema_version": "2.0.0",',
            1,
        ),
        lambda text: text.replace(
            '"synthetic": true,', '"synthetic": true, "unknown": null,', 1
        ),
        lambda text: text.replace('"value":"1200.00"', '"value":1.2', 1),
        lambda text: text.replace('"value":"1200.00"', '"value":"NaN"', 1),
        lambda text: text.replace(
            '"source":"PROVIDER_REVENUE"', '"source":"SECRET"', 1
        ),
    ],
)
def test_strict_fixture_schema_rejects_adversarial_documents(
    fixture_bytes: bytes,
    command: KpiCalculationCommand,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
) -> None:
    content = mutation(fixture_bytes.decode()).encode()
    _rebind_fixture(monkeypatch, content)
    with pytest.raises(KpiFailure) as captured:
        RecordedKpiInputAdapter(content).read(_rebound_command(command, content))
    assert captured.value.code is KpiFailureCode.FIXTURE_DOCUMENT_INVALID
    assert "SECRET" not in str(captured.value)


def test_port_exception_is_redacted_and_not_retried(
    command: KpiCalculationCommand,
) -> None:
    class ExplodingExchange:
        calls = 0

        def read(self, candidate: KpiCalculationCommand) -> RecordedKpiInputBatch:
            del candidate
            self.calls += 1
            raise RuntimeError("SECRET_CANARY_ST1205")

    exchange = ExplodingExchange()
    with pytest.raises(KpiFailure) as captured:
        RecordedKpiCalculationJob(exchange=exchange).calculate(command)
    assert captured.value.code is KpiFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
    assert exchange.calls == 1
    assert "SECRET_CANARY" not in str(captured.value)


def test_malicious_port_result_is_rejected(
    command: KpiCalculationCommand,
) -> None:
    class WrongExchange:
        def read(self, candidate: KpiCalculationCommand) -> object:
            del candidate
            return object()

    with pytest.raises(KpiFailure) as captured:
        RecordedKpiCalculationJob(exchange=WrongExchange()).calculate(command)
    assert captured.value.code is KpiFailureCode.RECORDED_RESULT_MISMATCH


def test_exact_typed_but_forged_recorded_batch_is_digest_rejected(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    forged_observation = replace(
        batch.input_frame.observations[0],
        value=batch.input_frame.observations[0].value + 1,
    )
    forged = replace(
        batch,
        input_frame=KpiInputFrame(
            (forged_observation, *batch.input_frame.observations[1:])
        ),
    )

    class ForgedExchange:
        def read(self, candidate: KpiCalculationCommand) -> RecordedKpiInputBatch:
            del candidate
            return forged

    with pytest.raises(KpiFailure) as captured:
        RecordedKpiCalculationJob(exchange=ForgedExchange()).calculate(command)
    assert captured.value.code is KpiFailureCode.RECORDED_RESULT_MISMATCH


def test_sensitive_domain_values_and_failures_are_not_pickleable(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> None:
    batch = RecordedKpiInputAdapter(fixture_bytes).read(command)
    for value in (
        batch,
        batch.input_frame,
        batch.input_frame.observations[0],
        KpiFailure(KpiFailureCode.INVALID_ARGUMENT),
    ):
        assert "1200.00" not in repr(value)
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
            "public_projection=kpiboundarystatus.in_memory_only",
            "production_write",
            "credential_lookup",
        ):
            assert token not in lowered


def test_fixture_expected_results_are_not_used_as_formula_inputs(
    fixture_document: dict[str, Any],
) -> None:
    assert set(fixture_document["observations"][0]) == {
        "metric_key",
        "value",
        "source",
        "verified",
        "cohort_state",
        "attribution_basis",
        "attribution_verified",
    }
    assert (
        json.dumps(fixture_document["expected_results"])
        not in (REPOSITORY_ROOT / builder.DOMAIN_PATH).read_text()
    )
