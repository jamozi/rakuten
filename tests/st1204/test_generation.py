"""Determinism and fail-closed checks for ST-1204 recorded fixtures."""

from __future__ import annotations

import ast
import builtins
from copy import deepcopy
import hashlib
import importlib
import os
from pathlib import Path
import socket
import subprocess
from typing import Any
import urllib.request

import pytest
import yaml
from yaml.tokens import AliasToken, AnchorToken

from scripts import build_st1204_ga4_recorded_adapter as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_GENERATOR_IMPORTS = frozenset(
    {
        ("__future__", "annotations", None),
        ("", "argparse", None),
        ("collections.abc", "Mapping", None),
        ("collections.abc", "Sequence", None),
        ("copy", "deepcopy", None),
        ("", "ctypes", None),
        ("datetime", "date", None),
        ("datetime", "datetime", None),
        ("", "fcntl", None),
        ("", "hashlib", None),
        ("", "json", None),
        ("", "math", None),
        ("", "os", None),
        ("pathlib", "Path", None),
        ("pathlib", "PurePosixPath", None),
        ("", "re", None),
        ("", "stat", None),
        ("", "sys", None),
        ("typing", "Final", None),
        ("typing", "NoReturn", None),
        ("typing", "cast", None),
        ("urllib.parse", "urlsplit", None),
        ("uuid", "UUID", None),
        ("jsonschema", "Draft202012Validator", None),
        ("jsonschema", "FormatChecker", None),
        ("jsonschema.exceptions", "SchemaError", None),
        ("jsonschema.exceptions", "ValidationError", None),
        ("", "yaml", None),
        ("yaml.constructor", "ConstructorError", None),
        ("yaml.nodes", "MappingNode", None),
        ("yaml.tokens", "AliasToken", None),
        ("yaml.tokens", "AnchorToken", None),
    }
)
ALLOWED_GENERATOR_OS_ATTRIBUTES = frozenset(
    {
        "O_CLOEXEC",
        "O_CREAT",
        "O_DIRECTORY",
        "O_EXCL",
        "O_NOFOLLOW",
        "O_RDONLY",
        "O_WRONLY",
        "close",
        "fchmod",
        "fsencode",
        "fstat",
        "fsync",
        "mkdir",
        "open",
        "read",
        "replace",
        "rmdir",
        "scandir",
        "stat",
        "stat_result",
        "strerror",
        "unlink",
        "write",
    }
)
FORBIDDEN_DYNAMIC_REFERENCES = frozenset({"__builtins__", "__import__", "eval", "exec"})
FORBIDDEN_GENERATOR_MODULES = frozenset(
    {
        "_socket",
        "google",
        "googleapiclient",
        "httpx",
        "importlib",
        "requests",
        "socket",
        "subprocess",
        "urllib.request",
        "urllib3",
    }
)


def _is_banned_os_name(name: str) -> bool:
    return name in {
        "environ",
        "environb",
        "getenv",
        "getenvb",
        "popen",
        "putenv",
        "startfile",
        "system",
        "unsetenv",
    } or name.startswith(("exec", "fork", "posix_spawn", "spawn"))


def _assert_generator_ast_is_closed(source: str) -> None:
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    observed_imports: list[tuple[str, str, str | None]] = []
    imported_module_candidates: set[str] = set()
    forbidden_references: list[ast.AST] = []
    invalid_os_references: list[ast.AST] = []
    observed_os_attributes: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                observed_imports.append(("", alias.name, alias.asname))
                imported_module_candidates.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                raise AssertionError("generator relative import is forbidden")
            module = node.module or ""
            for alias in node.names:
                observed_imports.append((module, alias.name, alias.asname))
                imported_module_candidates.add(module)
                imported_module_candidates.add(f"{module}.{alias.name}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_DYNAMIC_REFERENCES:
                forbidden_references.append(node)
            if node.id == "os":
                parent = parents.get(node)
                if not (
                    isinstance(parent, ast.Attribute)
                    and parent.value is node
                    and parent.attr in ALLOWED_GENERATOR_OS_ATTRIBUTES
                ):
                    invalid_os_references.append(node)

        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DYNAMIC_REFERENCES or _is_banned_os_name(
                node.attr
            ):
                forbidden_references.append(node)
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                observed_os_attributes.add(node.attr)
                if node.attr not in ALLOWED_GENERATOR_OS_ATTRIBUTES:
                    invalid_os_references.append(node)

    if (
        len(observed_imports) != len(EXPECTED_GENERATOR_IMPORTS)
        or set(observed_imports) != EXPECTED_GENERATOR_IMPORTS
    ):
        raise AssertionError("generator import surface drifted")
    if [
        imported
        for imported in observed_imports
        if imported[0] == "urllib" or imported[0].startswith("urllib.")
    ] != [("urllib.parse", "urlsplit", None)]:
        raise AssertionError("generator urllib import surface drifted")
    if any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imported_module_candidates
        for forbidden in FORBIDDEN_GENERATOR_MODULES
    ):
        raise AssertionError("generator imports a forbidden module")
    if forbidden_references:
        raise AssertionError("generator contains a forbidden dynamic reference")
    if invalid_os_references:
        raise AssertionError("generator contains a forbidden os reference")
    if observed_os_attributes != ALLOWED_GENERATOR_OS_ATTRIBUTES:
        raise AssertionError("generator os attribute surface drifted")


def _snapshot(path: Path) -> tuple[int, int, int, int, int, int]:
    metadata = path.stat()
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
    )


def _rehash_run_response(recording: dict[str, Any]) -> None:
    capture = recording["run_report_capture"]
    capture["expected_response_sha256"] = generator.canonical_json_sha256(
        capture["response"]
    )


def _rehash_identity_response(recording: dict[str, Any]) -> None:
    capture = recording["reporting_identity_capture"]
    capture["expected_response_sha256"] = generator.canonical_json_sha256(
        capture["response"]
    )


def _synthetic_outputs(tag: str) -> dict[Path, bytes]:
    fixtures = {
        name: generator._sorted_json({"name": name, "tag": tag}, compact=False)
        for name in generator.EXPECTED_FIXTURE_NAMES
    }
    manifest = generator._sorted_json(
        {
            "document": {
                "id": "RAOS-GA4-RECORDED-MANIFEST-001",
                "story_id": "ST-1204",
                "version": generator.MANIFEST_VERSION,
            },
            "fixture_count": len(fixtures),
            "fixtures": [
                {
                    "bytes": len(fixtures[name]),
                    "path": name,
                    "sha256": hashlib.sha256(fixtures[name]).hexdigest(),
                }
                for name in generator.EXPECTED_FIXTURE_NAMES
            ],
        },
        compact=False,
    )
    return {
        generator.MANIFEST_PATH: manifest,
        **{
            generator.FIXTURE_ROOT / name: content for name, content in fixtures.items()
        },
    }


def test_generation_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.build_outputs(REPOSITORY_ROOT)
    second = generator.build_outputs(REPOSITORY_ROOT)
    assert first == second
    assert set(first) == {
        generator.MANIFEST_PATH,
        *(generator.FIXTURE_ROOT / name for name in generator.EXPECTED_FIXTURE_NAMES),
    }
    for relative, content in first.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content


def test_check_mode_is_read_only() -> None:
    paths = [
        REPOSITORY_ROOT / generator.MANIFEST_PATH,
        *(
            REPOSITORY_ROOT / generator.FIXTURE_ROOT / name
            for name in generator.EXPECTED_FIXTURE_NAMES
        ),
    ]
    before = {path: _snapshot(path) for path in paths}
    digest = generator.check(REPOSITORY_ROOT)
    assert (
        digest
        == hashlib.sha256(
            (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes()
        ).hexdigest()
    )
    assert {path: _snapshot(path) for path in paths} == before


def test_source_contract_has_no_yaml_anchors_or_aliases() -> None:
    content = (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8")
    tokens = tuple(yaml.scan(content))
    assert not any(isinstance(token, (AnchorToken, AliasToken)) for token in tokens)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"document: {}\ndocument: {}\n", "malformed"),
        (b"document: &shared {}\nstory: *shared\n", "YAML aliases"),
        (b"\xef\xbb\xbfdocument: {}\n", "BOM"),
        (b"document: {}\r\n", "use LF"),
        (b"document: {}", "use LF"),
    ],
)
def test_yaml_loader_rejects_noncanonical_documents(
    content: bytes, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        generator._load_yaml(content)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"a":1,"a":2}\n', "strict JSON"),
        (b'{"value":NaN}\n', "strict JSON"),
        (b"\xef\xbb\xbf{}\n", "BOM"),
        (b"{}\r\n", "strict JSON"),
        (b"{}", "strict JSON"),
    ],
)
def test_json_loader_rejects_noncanonical_documents(
    content: bytes, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        generator._load_json(content, label="synthetic JSON")


def test_json_graph_depth_limit_fails_closed() -> None:
    value: dict[str, object] = {}
    current = value
    for _index in range(66):
        nested: dict[str, object] = {}
        current["next"] = nested
        current = nested
    with pytest.raises(RuntimeError, match="document graph limit"):
        generator._validate_json_graph(value, label="synthetic graph")


def test_schema_is_parsed_from_the_hash_checked_capture(
    source_contract: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = generator._validate_pinned_sources(REPOSITORY_ROOT, source_contract)

    def forbidden_reopen(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("a captured schema must not be reopened")

    monkeypatch.setattr(generator, "_read_regular", forbidden_reopen)
    schema = generator._schema_by_role(source_contract, "run_report_request", captured)
    assert str(schema["$id"]).endswith("ga4-run-report-request.schema.json")


def test_regular_read_is_descriptor_relative_after_parent_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_parent = tmp_path / "trusted"
    trusted_source = trusted_parent / "nested" / "payload.json"
    trusted_source.parent.mkdir(parents=True)
    trusted_source.write_bytes(b"trusted\n")

    replacement_parent = tmp_path / "replacement"
    replacement_source = replacement_parent / "nested" / "payload.json"
    replacement_source.parent.mkdir(parents=True)
    replacement_source.write_bytes(b"replacement\n")

    real_open = os.open
    calls: list[tuple[str, int, int | None, int]] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        decoded = os.fsdecode(path)
        calls.append((decoded, flags, dir_fd, descriptor))
        if decoded == "trusted":
            trusted_parent.rename(tmp_path / "captured-trusted")
            replacement_parent.rename(trusted_parent)
        return descriptor

    monkeypatch.setattr(os, "open", tracked_open)

    assert (
        generator._read_regular(
            tmp_path,
            Path("trusted/nested/payload.json"),
            label="descriptor-relative test source",
            maximum_bytes=64,
        )
        == b"trusted\n"
    )
    assert [path for path, *_rest in calls] == [
        os.fspath(tmp_path),
        "trusted",
        "nested",
        "payload.json",
    ]
    assert calls[0][2] is None
    for index in range(1, len(calls)):
        previous = calls[index - 1]
        current = calls[index]
        assert current[2] == previous[3]
        assert "/" not in current[0]
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_DIRECTORY for _path, flags, _dir_fd, _fd in calls[:-1])
    assert not calls[-1][1] & os.O_DIRECTORY


def test_regular_read_preserves_primary_error_when_descriptor_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"too large")
    real_close = os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("synthetic descriptor close failure")

    monkeypatch.setattr(os, "close", close_then_fail)

    with pytest.raises(RuntimeError, match="exceeds its size limit") as exc_info:
        generator._read_regular(
            tmp_path,
            Path("payload.json"),
            label="primary-error test source",
            maximum_bytes=1,
        )

    assert "descriptor cleanup also failed" in getattr(exc_info.value, "__notes__", ())


def test_fixture_traversal_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="below the repository root"):
        generator._normalized_relative("../escape.json", label="fixture_file")


def test_credential_shaped_recorded_material_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["run_report_capture"]["response"]["metadata"]["emptyReason"] = (
        "Bearer synthetic"
    )
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="credential-shaped"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_url_sensitive_components_in_recorded_material_are_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["run_report_capture"]["response"]["metadata"]["emptyReason"] = (
        "https://example.invalid/synthetic?token=redacted"
    )
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="sensitive components"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_real_property_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["internal_request"]["property_id"] = "123456789"
    with pytest.raises(RuntimeError, match="synthetic allowlist"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize(
    "page_path",
    [
        "/real/page",
        "/synthetic/../escape",
        "/synthetic/page?raw=1",
        "/synthetic/page#raw",
        "/synthetic//double",
        "https://example.invalid/synthetic/page",
    ],
)
def test_non_synthetic_page_path_is_rejected(
    page_path: str,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["run_report_capture"]["response"]["rows"][0]["dimensionValues"][1][
        "value"
    ] = page_path
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="pagePath.*synthetic allowlist"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimension_filter", {"filter": {}}),
        ("metric_filter", {"filter": {}}),
        ("order_bys", [{"dimension": {"dimensionName": "date"}}]),
    ],
)
def test_filters_and_ordering_are_rejected_in_the_recorded_checkpoint(
    field: str,
    value: object,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["internal_request"][field] = value
    with pytest.raises(RuntimeError, match="outside this recorded slice"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_wire_request_must_be_exact_and_keep_int64_strings(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["wire_request"]["limit"] = 2
    with pytest.raises(RuntimeError, match="does not match the internal request"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_mismatched_dimension_headers_are_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    response = recording["run_report_capture"]["response"]
    response["dimensionHeaders"][1]["name"] = "deviceCategory"
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="dimension headers.*request order"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_mismatched_metric_headers_are_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    response = recording["run_report_capture"]["response"]
    response["metricHeaders"][0]["type"] = "TYPE_FLOAT"
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="metric headers.*request order and types"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_provider_value_count_must_match_header_count(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    response = recording["run_report_capture"]["response"]
    response["rows"][0]["metricValues"].pop()
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="values do not match header counts"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_metric_values_must_remain_provider_numeric_strings(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    response = recording["run_report_capture"]["response"]
    response["rows"][0]["metricValues"][0]["value"] = 12
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="metric value must be a non-empty string"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_negative_quota_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    response = recording["run_report_capture"]["response"]
    response["propertyQuota"]["tokensPerDay"]["remaining"] = -1
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="quota values cannot be negative"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_unsupported_reporting_identity_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["reporting_identity_capture"]["response"]["reportingIdentity"] = (
        "UNSPECIFIED"
    )
    _rehash_identity_response(recording)
    with pytest.raises(RuntimeError, match="identity value is unsupported"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_identity_retrieval_after_recording_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["reporting_identity_capture"]["retrieved_at"] = "2026-08-05T00:00:03Z"
    with pytest.raises(RuntimeError, match="retrieval cannot follow recorded_at"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_provider_row_count_cannot_be_below_returned_rows(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["run_report_capture"]["response"]["rowCount"] = 1
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="below returned row count"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_provider_error_shape_is_exact(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["provider-error-429"])
    recording["run_report_capture"]["response"]["error"]["message"] = (
        "Synthetic changed error."
    )
    _rehash_run_response(recording)
    with pytest.raises(RuntimeError, match="not the sanitized 429"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_closed_inventory_rejects_extra_missing_and_symlink_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _synthetic_outputs("closed-inventory")
    for relative, content in outputs.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)

    generator.check(tmp_path)
    extra = tmp_path / generator.FIXTURE_ROOT / "extra.json"
    extra.write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="inventory drifted"):
        generator.check(tmp_path)
    extra.unlink()

    baseline = tmp_path / generator.FIXTURE_ROOT / "baseline.json"
    baseline.unlink()
    with pytest.raises(RuntimeError, match="inventory drifted"):
        generator.check(tmp_path)

    outside = tmp_path / "outside.json"
    outside.write_bytes(b"unchanged")
    baseline.symlink_to(outside)
    with pytest.raises(RuntimeError, match="one-link regular file"):
        generator.check(tmp_path)
    assert outside.read_bytes() == b"unchanged"


def test_generate_uses_atomic_closed_output_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _synthetic_outputs("fresh")
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    digest = generator.generate(tmp_path)
    assert digest == hashlib.sha256(outputs[generator.MANIFEST_PATH]).hexdigest()
    for relative, content in outputs.items():
        assert (tmp_path / relative).read_bytes() == content
    assert not tuple(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize(
    "snippet",
    [
        "_run = alias.system\n",
        "_env = alias.environ\n",
        "_dynamic = __import__\n",
        "_dynamic = eval\n",
        "_dynamic = exec\n",
        "_dynamic = __builtins__\n",
        "alias = os\n",
        "_dynamic = getattr(os, 'O_CLOEXEC', 0)\n",
        "_dynamic = os.__dict__\n",
    ],
)
def test_generator_ast_guard_rejects_prebound_capability_paths(snippet: str) -> None:
    source = (REPOSITORY_ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_generator_ast_is_closed(f"{source}\n{snippet}")


def test_generator_has_no_network_sdk_or_environment_credential_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (REPOSITORY_ROOT / generator.GENERATOR_PATH).read_text(encoding="utf-8")
    _assert_generator_ast_is_closed(source)

    def forbidden_runtime(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "network, subprocess, and environment access are forbidden"
        )

    class ForbiddenEnvironment:
        def __getattribute__(self, _name: str) -> object:
            raise AssertionError("environment access is forbidden")

        def __getitem__(self, _key: object) -> object:
            raise AssertionError("environment access is forbidden")

        def __iter__(self) -> object:
            raise AssertionError("environment access is forbidden")

        def __len__(self) -> int:
            raise AssertionError("environment access is forbidden")

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        candidates = {name, *(f"{name}.{item}" for item in fromlist if item != "*")}
        if any(
            candidate == forbidden or candidate.startswith(f"{forbidden}.")
            for candidate in candidates
            for forbidden in FORBIDDEN_GENERATOR_MODULES
        ):
            raise AssertionError("forbidden runtime import")
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as runtime_guard:
        for name in (
            "create_connection",
            "create_server",
            "fromfd",
            "fromshare",
            "socket",
            "socketpair",
        ):
            if hasattr(socket, name):
                runtime_guard.setattr(socket, name, forbidden_runtime)
        runtime_guard.setattr(urllib.request, "urlopen", forbidden_runtime)
        for name in (
            "Popen",
            "call",
            "check_call",
            "check_output",
            "getoutput",
            "getstatusoutput",
            "run",
        ):
            runtime_guard.setattr(subprocess, name, forbidden_runtime)
        for name in dir(os):
            if _is_banned_os_name(name) and callable(getattr(os, name)):
                runtime_guard.setattr(os, name, forbidden_runtime)
        runtime_guard.setattr(os, "environ", ForbiddenEnvironment())
        if hasattr(os, "environb"):
            runtime_guard.setattr(os, "environb", ForbiddenEnvironment())
        runtime_guard.setattr(importlib, "import_module", forbidden_runtime)
        runtime_guard.setattr(builtins, "__import__", guarded_import)
        generator.build_outputs(REPOSITORY_ROOT)
