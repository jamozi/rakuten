"""Hostile parsing, capability, replay, and redaction tests for ST-1907."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import pickle

import pytest

from raos.adapters.recorded_content_portfolio_optimizer import (
    RecordedContentPortfolioOptimizerSource,
)
from raos.application.portfolio.content_optimizer import (
    ContentPortfolioOptimizerService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.portfolio.content_optimizer import (
    PortfolioOptimizerCommand,
    PortfolioOptimizerFailure,
    PortfolioOptimizerFailureCode,
    Sha256Digest,
    digest_bytes,
)

from .support import (
    canonical_payload,
    command_for,
    fixture_bytes,
    fixture_document,
    ready_document,
)


def _failure_code(payload: bytes) -> PortfolioOptimizerFailureCode:
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        RecordedContentPortfolioOptimizerSource(payload).read(command_for(payload))
    return caught.value.code


def test_duplicate_float_noncanonical_and_truncated_bytes_are_refused() -> None:
    raw = fixture_bytes()
    duplicate = raw.replace(b'{"document":', b'{"signals":[],"document":', 1)
    command = replace(
        command_for(),
        source_sha256=digest_bytes(duplicate),
        source_bytes=len(duplicate),
    )
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        RecordedContentPortfolioOptimizerSource(duplicate).read(command)
    assert caught.value.code is PortfolioOptimizerFailureCode.SOURCE_DOCUMENT_INVALID

    ready = canonical_payload(ready_document())
    floating = ready.replace(b'"denominator_count":100', b'"denominator_count":1e2')
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        RecordedContentPortfolioOptimizerSource(floating).read(
            replace(
                command_for(ready),
                source_sha256=digest_bytes(floating),
                source_bytes=len(floating),
            )
        )
    assert caught.value.code is PortfolioOptimizerFailureCode.SOURCE_DOCUMENT_INVALID

    pretty = (json.dumps(fixture_document(), indent=2) + "\n").encode()
    assert (
        _failure_code(pretty) is PortfolioOptimizerFailureCode.SOURCE_DOCUMENT_INVALID
    )
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        RecordedContentPortfolioOptimizerSource(raw[:-1]).read(command_for())
    assert caught.value.code is PortfolioOptimizerFailureCode.SOURCE_BYTES_MISMATCH


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_endpoint", "https://example.invalid"),
        ("credential", "forbidden"),
        ("raw_ip", "127.0.0.1"),
        ("reward", 100),
        ("commission", 100),
        ("epc", 100),
        ("rpm", 100),
        ("profit", 100),
        ("article_html", "forbidden"),
        ("publication_snapshot", "forbidden"),
    ],
)
def test_unknown_sensitive_finance_and_mutation_fields_fail_closed(
    field: str, value: object
) -> None:
    document = ready_document()
    document["signals"][0][field] = value
    payload = canonical_payload(document)
    assert (
        _failure_code(payload) is PortfolioOptimizerFailureCode.SOURCE_DOCUMENT_INVALID
    )


@pytest.mark.parametrize(
    "field",
    [
        "finance_signal_present",
        "personal_data_present",
        "recommendation_order_change_requested",
        "publication_mutation_requested",
    ],
)
def test_authority_bearing_signal_flags_are_refused(field: str) -> None:
    document = ready_document()
    document["signals"][0][field] = True
    payload = canonical_payload(document)
    assert _failure_code(payload) is PortfolioOptimizerFailureCode.INVALID_ARGUMENT


def test_release_decision_input_is_structurally_prohibited() -> None:
    baseline = command_for()
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        PortfolioOptimizerCommand(
            recording_id=baseline.recording_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            contract_sha256=baseline.contract_sha256,
            expected_dependency_pack_sha256=(baseline.expected_dependency_pack_sha256),
            measurement_contract_sha256=baseline.measurement_contract_sha256,
            signal_policy_sha256=baseline.signal_policy_sha256,
            program=baseline.program,
            period=baseline.period,
            release_decision_sha256=Sha256Digest("d" * 64),
            scope=baseline.scope,
        )
    assert (
        caught.value.code is PortfolioOptimizerFailureCode.RELEASE_DECISION_PROHIBITED
    )


def test_source_failures_are_sanitized_and_wrong_results_are_rejected() -> None:
    unsafe_source = "sensitive-source-material"

    class _Broken:
        def read(self, command: object) -> object:
            del command
            raise RuntimeError(unsafe_source)

    service = ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=_Broken(),
    )
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        service.evaluate(command_for())
    assert caught.value.code is PortfolioOptimizerFailureCode.SOURCE_UNAVAILABLE
    assert unsafe_source not in repr(caught.value)
    assert unsafe_source not in str(caught.value)

    class _Wrong:
        def read(self, command: object) -> object:
            del command
            return {"unsafe": unsafe_source}

    service = ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=_Wrong(),
    )
    with pytest.raises(PortfolioOptimizerFailure) as caught:
        service.evaluate(command_for())
    assert caught.value.code is PortfolioOptimizerFailureCode.SOURCE_RESULT_INVALID


def test_one_shot_adapter_has_exactly_one_concurrent_winner_and_redacts() -> None:
    source = RecordedContentPortfolioOptimizerSource(fixture_bytes())
    command = command_for()

    def call() -> str:
        try:
            source.read(command)
        except PortfolioOptimizerFailure as failure:
            return failure.code.value
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _index: call(), range(32)))
    assert outcomes.count("SUCCESS") == 1
    assert outcomes.count(PortfolioOptimizerFailureCode.SOURCE_EXHAUSTED.value) == 31
    assert "recording" not in repr(source).lower()
    with pytest.raises(TypeError):
        pickle.dumps(source)
