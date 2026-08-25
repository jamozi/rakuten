from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import inspect
import json
import pickle
from typing import Any, cast

import pytest

from raos.adapters.recorded_live_evaluation import (
    RecordedLiveEvaluationAdapter,
    RecordedLiveEvaluationError,
    load_recorded_live_evaluation_result,
)
from raos.application.ai.live_evaluation import EvaluateRecordedLiveCandidateService
from raos.domain.ai.live_evaluation import (
    LiveEvaluationError,
    RecordedLiveEvaluationResult,
    evaluate_recorded_live_evidence,
    finalize_evidence,
    finalize_request,
)
from tests.st0708_v2.support import PATHS, ROOT, artifact_bytes


def _mutate_one_byte(value: bytes) -> bytes:
    index = len(value) // 2
    replacement = b"0" if value[index : index + 1] != b"0" else b"1"
    return value[:index] + replacement + value[index + 1 :]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _rebind_generated_artifact(
    values: dict[str, bytes],
    *,
    artifact_name: str,
    relative_path: str,
    payload: bytes,
) -> dict[str, bytes]:
    rebound = values | {artifact_name: payload}
    manifest = cast(dict[str, Any], json.loads(rebound["runtime_manifest_bytes"]))
    generated = cast(dict[str, Any], manifest["generated_sha256"])
    generated[relative_path] = hashlib.sha256(payload).hexdigest()
    material = {key: item for key, item in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(_canonical_json(material)).hexdigest()
    rebound["runtime_manifest_bytes"] = _canonical_json(manifest) + b"\n"
    return rebound


@pytest.mark.parametrize("artifact_name", tuple(PATHS))
def test_every_runtime_and_dependency_artifact_tamper_fails_closed(
    artifact_name: str,
) -> None:
    values = artifact_bytes()
    values[artifact_name] = _mutate_one_byte(values[artifact_name])
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(**values)


def test_duplicate_noncanonical_and_oversized_generated_json_fail_closed() -> None:
    values = artifact_bytes()
    duplicate = values["request_artifact_bytes"].replace(
        b'{"document":', b'{"document":{},"document":', 1
    )
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(
            **(values | {"request_artifact_bytes": duplicate})
        )
    padded = values["report_artifact_bytes"] + b" "
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(
            **(values | {"report_artifact_bytes": padded})
        )
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(
            **(values | {"request_artifact_bytes": oversized})
        )


def test_unknown_request_field_is_rejected_after_manifest_rebind() -> None:
    values = artifact_bytes()
    request = cast(dict[str, Any], json.loads(values["request_artifact_bytes"]))
    evidence = cast(dict[str, Any], request["evidence"])
    candidate = cast(dict[str, Any], evidence["candidate"])
    candidate["raw_prompt"] = "opaque-canary"
    rebound = _rebind_generated_artifact(
        values,
        artifact_name="request_artifact_bytes",
        relative_path=(
            "changes/st-0708/generated/recorded-live-evaluation-request.v2.json"
        ),
        payload=_canonical_json(request) + b"\n",
    )
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(**rebound)


def test_unknown_report_field_is_rejected_after_manifest_rebind() -> None:
    values = artifact_bytes()
    report = cast(dict[str, Any], json.loads(values["report_artifact_bytes"]))
    formal = cast(dict[str, Any], report["formal_status"])
    formal["review_body"] = "NOT_EXECUTED"
    rebound = _rebind_generated_artifact(
        values,
        artifact_name="report_artifact_bytes",
        relative_path=(
            "changes/st-0708/generated/recorded-live-evaluation-report.v2.json"
        ),
        payload=_canonical_json(report) + b"\n",
    )
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(**rebound)


def test_unknown_runtime_manifest_field_is_rejected_after_self_rehash() -> None:
    values = artifact_bytes()
    manifest = cast(dict[str, Any], json.loads(values["runtime_manifest_bytes"]))
    manifest["provider_url"] = "opaque-canary"
    material = {key: item for key, item in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(_canonical_json(material)).hexdigest()
    values["runtime_manifest_bytes"] = _canonical_json(manifest) + b"\n"
    with pytest.raises(RecordedLiveEvaluationError):
        load_recorded_live_evaluation_result(**values)


def test_post_load_mutation_is_detected_before_decision(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    object.__setattr__(recorded_result, "evidence_sha256", "f" * 64)
    with pytest.raises(LiveEvaluationError):
        evaluate_recorded_live_evidence(recorded_result)


def test_errors_and_report_are_sanitized_and_not_serializable(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    canary = b"secret-canary-st0708-runtime"
    with pytest.raises(RecordedLiveEvaluationError) as caught:
        load_recorded_live_evaluation_result(
            **artifact_bytes(request_artifact_bytes=canary)
        )
    assert canary.decode() not in f"{caught.value!s} {caught.value!r}"
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)
    report = evaluate_recorded_live_evidence(recorded_result)
    assert canary.decode() not in f"{report!s} {report!r}"
    with pytest.raises(TypeError):
        pickle.dumps(report)


def test_request_rejects_urls_secrets_and_unbounded_identifiers(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    for value in (
        "https://example.invalid/live",
        "".join(("sec", "ret://provider/key")),
        "raw prompt body",
        "x" * 161,
    ):
        request = replace(
            recorded_result.request,
            evaluation_id=value,
            request_sha256="0" * 64,
        )
        with pytest.raises(LiveEvaluationError):
            finalize_request(request)


def test_generated_request_and_report_have_no_raw_or_operational_material() -> None:
    material = (
        ROOT / "changes/st-0708/generated/recorded-live-evaluation-request.v2.json"
    ).read_text(encoding="utf-8").lower() + (
        ROOT / "changes/st-0708/generated/recorded-live-evaluation-report.v2.json"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "https://",
        "secret://",
        "api_key",
        "authorization:",
        '"raw_prompt":',
        '"review_body":',
        '"provider_response_body":',
    ):
        assert forbidden not in material


def test_runtime_modules_expose_no_live_provider_or_operational_capability() -> None:
    files = (
        ROOT / "python/raos/domain/ai/live_evaluation.py",
        ROOT / "python/raos/application/ai/live_evaluation.py",
        ROOT / "python/raos/adapters/recorded_live_evaluation.py",
        ROOT / "python/raos/ports/live_evaluation.py",
    )
    forbidden_import_roots = {
        "openai",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "sqlalchemy",
        "psycopg",
    }
    forbidden_calls = {
        "open",
        "exec",
        "eval",
        "system",
        "popen",
        "remove",
        "unlink",
        "write_text",
        "write_bytes",
    }
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in forbidden_import_roots
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_import_roots
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in forbidden_calls


def test_public_surfaces_are_only_evaluate_and_execute() -> None:
    service = {
        name
        for name, value in inspect.getmembers(
            EvaluateRecordedLiveCandidateService, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    adapter = {
        name
        for name, value in inspect.getmembers(
            RecordedLiveEvaluationAdapter, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert service == {"evaluate"}
    assert adapter == {"execute"}


def test_forged_loaded_flags_fail_hash_validation(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    forged = replace(
        recorded_result,
        formal_tst_018_executed=True,
    )
    with pytest.raises(LiveEvaluationError):
        forged.require_valid()
    repaired = finalize_evidence(replace(forged, evidence_sha256="0" * 64))
    assert repaired.formal_tst_018_executed is True
    # The pure domain can evaluate supplied evidence, but the exact recorded
    # loader never accepts this forged artifact and still grants no authority.
    assert evaluate_recorded_live_evidence(repaired).authority == "NONE"
