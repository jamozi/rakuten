"""Fail-closed schema gaps and redacted failure behavior for ST-0801."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from conftest import CONTENT_ROOT, encoded
import raos.domain.editorial.content_ast as loader_module
from raos.domain.editorial import (
    ContentAstContractError,
    ContentAstValidationError,
    load_content_ast,
)


@pytest.mark.parametrize("version", (None, "0.9.0", "1.0.1", 1, True))
def test_missing_or_unsupported_schema_version_fails_closed(
    baseline_payload, version: object
) -> None:
    payload = deepcopy(baseline_payload)
    if version is None:
        del payload["schema_version"]
    else:
        payload["schema_version"] = version

    with pytest.raises(ContentAstValidationError):
        load_content_ast(encoded(payload))


def test_unknown_root_nested_rich_text_and_block_types_are_rejected(
    baseline_payload,
) -> None:
    root_unknown = deepcopy(baseline_payload)
    root_unknown["unknown"] = True
    nested_unknown = deepcopy(baseline_payload)
    nested_unknown["blocks"][1]["content"][0]["onclick"] = "synthetic"
    unknown_block = deepcopy(baseline_payload)
    unknown_block["blocks"][1]["type"] = "raw_html"

    for payload in (root_unknown, nested_unknown, unknown_block):
        with pytest.raises(ContentAstValidationError):
            load_content_ast(encoded(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("visibility", None),
        ("show_unknown_values", 1),
        ("show_unknown_values", "true"),
    ),
)
def test_frozen_schema_closes_generated_model_coercion_gaps(
    baseline_payload, field: str, value: object
) -> None:
    payload = deepcopy(baseline_payload)
    block = payload["blocks"][6]
    assert block["type"] == "comparison_table"
    schema = json.loads(
        (CONTENT_ROOT / "schemas/content-ast.schema.json").read_text(encoding="utf-8")
    )
    assert field in schema["$defs"]["block_comparison_table"]["properties"]
    if field == "show_unknown_values":
        assert field in block
    block[field] = value

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    assert captured.value.category == "SCHEMA"


def test_unique_items_and_optional_non_null_contracts_are_enforced(
    baseline_payload,
) -> None:
    duplicate_claim = deepcopy(baseline_payload)
    duplicate_claim["blocks"][1]["claim_ids"] = ["CLM-CASE-001", "CLM-CASE-001"]
    null_optional = deepcopy(baseline_payload)
    null_optional["blocks"][2]["items"][0]["recommendation_ref"] = None

    for payload in (duplicate_claim, null_optional):
        with pytest.raises(ContentAstValidationError) as captured:
            load_content_ast(encoded(payload))
        assert captured.value.category == "SCHEMA"


def test_date_time_format_is_checked_before_generated_model_projection(
    baseline_payload,
) -> None:
    payload = deepcopy(baseline_payload)
    payload["blocks"][-1]["last_checked_at"] = "not-a-date-time"

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    assert captured.value.category == "SCHEMA"


@pytest.mark.parametrize(
    "source",
    (
        '{"schema_version":"1.0.0","schema_version":"canary-secret"}',
        '{"value":NaN,"canary":"canary-secret"}',
        '{"unterminated":"canary-secret"',
    ),
)
def test_json_failures_are_redacted_and_never_logged(
    source: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(source)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert "canary-secret" not in rendered
    assert capsys.readouterr() == ("", "")


def test_schema_failure_pointer_and_keyword_do_not_echo_unknown_names_or_values(
    baseline_payload,
) -> None:
    payload = deepcopy(baseline_payload)
    payload["attacker_canary_name"] = "attacker-canary-value"

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    rendered = f"{captured.value!s} {captured.value!r}"
    assert "attacker_canary" not in rendered
    assert "attacker-canary" not in rendered
    assert captured.value.pointer == "/"
    assert captured.value.keyword == "additionalProperties"


def test_contract_reader_rejects_symlinked_relative_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    content = b"synthetic-pinned-content"
    (outside / "schema.json").write_bytes(content)
    (tmp_path / "contracts").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(loader_module, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ContentAstContractError):
        loader_module._read_pinned_file(
            Path("contracts/schema.json"),
            hashlib.sha256(content).hexdigest(),
            len(content),
        )


def test_contract_reader_rejects_hash_drift_without_echoing_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"contract-canary-value"
    (tmp_path / "schema.json").write_bytes(content)
    monkeypatch.setattr(loader_module, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ContentAstContractError) as captured:
        loader_module._read_pinned_file(Path("schema.json"), "0" * 64, len(content))

    rendered = f"{captured.value!s} {captured.value!r}"
    assert "contract-canary" not in rendered


@pytest.mark.parametrize(
    ("content", "expected_size"),
    ((b"short", 6), (b"oversized", 8)),
)
def test_contract_reader_rejects_size_drift_before_bounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    expected_size: int,
) -> None:
    (tmp_path / "schema.json").write_bytes(content)
    monkeypatch.setattr(loader_module, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ContentAstContractError):
        loader_module._read_pinned_file(
            Path("schema.json"), hashlib.sha256(content).hexdigest(), expected_size
        )


def test_contract_reader_rejects_fifo_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.mkfifo(tmp_path / "schema.json", mode=0o600)
    monkeypatch.setattr(loader_module, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ContentAstContractError):
        loader_module._read_pinned_file(Path("schema.json"), "0" * 64, 0)


def test_contract_reader_closes_all_descriptors_after_primary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"short"
    (tmp_path / "schema.json").write_bytes(content)
    monkeypatch.setattr(loader_module, "_REPOSITORY_ROOT", tmp_path)
    real_close = os.close
    closed: list[int] = []

    def close_with_first_error(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)
        if len(closed) == 1:
            raise OSError("synthetic close failure")

    monkeypatch.setattr(loader_module.os, "close", close_with_first_error)

    with pytest.raises(ContentAstContractError):
        loader_module._read_pinned_file(
            Path("schema.json"), hashlib.sha256(content).hexdigest(), len(content) + 1
        )

    assert len(closed) == 2


def test_oversized_integer_json_failure_is_redacted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = '{"value":' + "9" * 5000 + ',"canary":"integer-canary-secret"}'

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(source)

    rendered = f"{captured.value!s} {captured.value!r}"
    assert captured.value.category == "JSON"
    assert "integer-canary" not in rendered
    assert capsys.readouterr() == ("", "")


def test_rfc3339_leap_second_reaches_redacted_generated_model_boundary(
    baseline_payload, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = deepcopy(baseline_payload)
    source_summary = payload["blocks"][-1]
    assert source_summary["type"] == "source_summary"
    source_summary["last_checked_at"] = "2016-12-31T23:59:60Z"

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    rendered = f"{captured.value!s} {captured.value!r}"
    assert captured.value.category == "MODEL"
    assert "23:59:60" not in rendered
    assert capsys.readouterr() == ("", "")
