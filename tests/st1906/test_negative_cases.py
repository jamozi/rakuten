"""Hostile parser, privacy, replay, and binding tests for ST-1906."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import pickle

import pytest

from raos.adapters.recorded_causal_attribution import (
    RecordedCausalAttributionSource,
)
from raos.domain.analytics.causal_attribution import (
    CausalAttributionCommand,
    CausalAttributionFailure,
    CausalAttributionFailureCode,
    PrivacyReviewEvidence,
    PrivacyReviewStatus,
    digest_bytes,
    evaluate_recorded_causal_attribution,
)
from raos.domain.ops.object_intake import Sha256Digest

from .support import canonical_payload, command_for, fixture_bytes, fixture_document


def _failure_code(payload: bytes) -> CausalAttributionFailureCode:
    with pytest.raises(CausalAttributionFailure) as caught:
        RecordedCausalAttributionSource(payload).read(command_for(payload))
    return caught.value.code


def test_duplicate_keys_floats_noncanonical_and_truncation_are_refused() -> None:
    payload = fixture_bytes()
    duplicate = payload.replace(b'{"cells":[', b'{"cells":[],"cells":[', 1)
    with pytest.raises(CausalAttributionFailure) as caught:
        RecordedCausalAttributionSource(duplicate).read(
            replace(
                command_for(),
                source_sha256=digest_bytes(duplicate),
                source_bytes=len(duplicate),
            )
        )
    assert caught.value.code is CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID

    floating = payload.replace(
        b'"control_exposures":1000', b'"control_exposures":1e3', 1
    )
    with pytest.raises(CausalAttributionFailure) as caught:
        RecordedCausalAttributionSource(floating).read(
            replace(
                command_for(),
                source_sha256=digest_bytes(floating),
                source_bytes=len(floating),
            )
        )
    assert caught.value.code is CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID

    pretty = (json.dumps(fixture_document(), indent=2) + "\n").encode()
    assert _failure_code(pretty) is CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID
    with pytest.raises(CausalAttributionFailure) as caught:
        RecordedCausalAttributionSource(payload[:-1]).read(command_for())
    assert caught.value.code is CausalAttributionFailureCode.SOURCE_BYTES_MISMATCH


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("document",), ("provider_endpoint", "https://example.invalid")),
        (("document",), ("credential", "not-allowed")),
        (("cells", 0), ("raw_ip", "127.0.0.1")),
        (("cells", 0), ("commission", 100)),
        (("cells", 0), ("article_body", "not-allowed")),
    ],
)
def test_unknown_sensitive_or_finance_fields_are_refused(
    path: tuple[object, ...], value: tuple[str, object]
) -> None:
    document = fixture_document()
    target: object = document
    for key in path:
        target = target[key]  # type: ignore[index]
    assert isinstance(target, dict)
    target[value[0]] = value[1]
    payload = canonical_payload(document)
    assert (
        _failure_code(payload) is CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID
    )


def test_privacy_scope_cannot_represent_personal_tracking() -> None:
    baseline = command_for()
    for field_name in (
        "personal_data",
        "persistent_identifier",
        "raw_ip",
        "full_user_agent",
        "free_text",
        "tracking_activation",
    ):
        kwargs = {
            "status": PrivacyReviewStatus.RECORDED_SYNTHETIC_SCOPE_REVIEWED,
            "review_sha256": Sha256Digest("b" * 64),
            field_name: True,
        }
        with pytest.raises(CausalAttributionFailure):
            PrivacyReviewEvidence(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(CausalAttributionFailure) as caught:
        CausalAttributionCommand(
            recording_id=baseline.recording_id,
            experiment_id=baseline.experiment_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            contract=baseline.contract,
            program=baseline.program,
            period=baseline.period,
            privacy_review=baseline.privacy_review,
            preregistration_sha256=baseline.preregistration_sha256,
            release_decision_sha256=Sha256Digest("d" * 64),
            scope=baseline.scope,
        )
    assert caught.value.code is CausalAttributionFailureCode.RELEASE_DECISION_PROHIBITED


def test_duplicate_cells_and_command_binding_drift_are_refused() -> None:
    document = fixture_document()
    document["cells"].append(document["cells"][0])
    payload = canonical_payload(document)
    assert (
        _failure_code(payload) is CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID
    )

    command = command_for()
    batch = RecordedCausalAttributionSource(fixture_bytes()).read(command)
    with pytest.raises(CausalAttributionFailure) as caught:
        evaluate_recorded_causal_attribution(
            replace(command, experiment_id="st1906.synthetic.other"), batch
        )
    assert caught.value.code is CausalAttributionFailureCode.SOURCE_RESULT_INVALID
    with pytest.raises(CausalAttributionFailure) as caught:
        evaluate_recorded_causal_attribution(
            command, replace(batch, command_sha256=Sha256Digest("d" * 64))
        )
    assert caught.value.code is CausalAttributionFailureCode.SOURCE_RESULT_INVALID


def test_one_shot_adapter_has_exactly_one_concurrent_winner() -> None:
    source = RecordedCausalAttributionSource(fixture_bytes())
    command = command_for()

    def call() -> str:
        try:
            source.read(command)
        except CausalAttributionFailure as failure:
            return failure.code.value
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _index: call(), range(32)))
    assert outcomes.count("SUCCESS") == 1
    assert outcomes.count(CausalAttributionFailureCode.SOURCE_EXHAUSTED.value) == 31
    with pytest.raises(TypeError):
        pickle.dumps(source)
