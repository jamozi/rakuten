"""Determinism and fail-closed checks for ST-1203 recorded fixtures."""

from __future__ import annotations

import ast
import builtins
from copy import deepcopy
from datetime import date
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

from scripts import build_st1203_search_console_recorded_adapter as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_EXACT_STRUCTURE_MUTATION_COUNTS = {
    "story": 39,
    "generation": 26,
    "provenance": 161,
}
EXPECTED_GENERATOR_IMPORTS = frozenset(
    {
        ("__future__", "annotations", None),
        ("", "argparse", None),
        ("collections.abc", "Mapping", None),
        ("collections.abc", "Sequence", None),
        ("copy", "deepcopy", None),
        ("datetime", "date", None),
        ("datetime", "datetime", None),
        ("", "hashlib", None),
        ("", "json", None),
        ("", "math", None),
        ("", "os", None),
        ("pathlib", "Path", None),
        ("pathlib", "PurePosixPath", None),
        ("", "re", None),
        ("", "stat", None),
        ("", "sys", None),
        ("", "tempfile", None),
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
    }
)
EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS = {
    "argparse": frozenset({("ArgumentParser",)}),
    "hashlib": frozenset({("sha256",)}),
    "json": frozenset({("JSONDecodeError",), ("dumps",), ("loads",)}),
    "math": frozenset({("isfinite",)}),
    "os": frozenset(
        {
            ("O_CLOEXEC",),
            ("O_DIRECTORY",),
            ("O_NOFOLLOW",),
            ("O_RDONLY",),
            ("close",),
            ("fdopen",),
            ("fstat",),
            ("fsync",),
            ("open",),
            ("read",),
            ("replace",),
            ("scandir",),
            ("stat_result",),
        }
    ),
    "re": frozenset({("compile",)}),
    "stat": frozenset({("S_ISDIR",), ("S_ISLNK",), ("S_ISREG",)}),
    "sys": frozenset({("stderr",)}),
    "tempfile": frozenset({("mkstemp",)}),
    "yaml": frozenset(
        {
            ("SafeLoader",),
            ("YAMLError",),
            ("load",),
            ("resolver", "BaseResolver", "DEFAULT_MAPPING_TAG"),
        }
    ),
}
EXPECTED_GENERATOR_MODULE_DIRECT_ATTRIBUTES = {
    module: frozenset(chain[0] for chain in rooted_chains)
    for module, rooted_chains in EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS.items()
}
FORBIDDEN_DYNAMIC_REFERENCES = frozenset(
    {
        "__builtins__",
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "hasattr",
        "help",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)
FORBIDDEN_GENERATOR_MODULES = frozenset(
    {
        "_socket",
        "ctypes",
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


def _rooted_attribute_chain(node: ast.Attribute) -> tuple[str, tuple[str, ...]] | None:
    attributes: list[str] = []
    cursor: ast.expr = node
    while isinstance(cursor, ast.Attribute):
        attributes.append(cursor.attr)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name):
        return None
    return cursor.id, tuple(reversed(attributes))


def _assert_generator_ast_is_closed(source: str) -> None:
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    observed_imports: list[tuple[str, str, str | None]] = []
    observed_direct_module_imports: set[str] = set()
    imported_module_candidates: set[str] = set()
    forbidden_references: list[ast.AST] = []
    forbidden_attribute_traversals: list[ast.Attribute] = []
    invalid_module_references: list[ast.AST] = []
    invalid_sys_sinks: list[ast.Attribute] = []
    observed_module_rooted_chains: dict[str, set[tuple[str, ...]]] = {
        module: set() for module in EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                observed_imports.append(("", alias.name, alias.asname))
                imported_module_candidates.add(alias.name)
                observed_direct_module_imports.add(alias.asname or alias.name)
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
            if node.id in EXPECTED_GENERATOR_MODULE_DIRECT_ATTRIBUTES:
                parent = parents.get(node)
                if not (
                    isinstance(parent, ast.Attribute)
                    and parent.value is node
                    and parent.attr
                    in EXPECTED_GENERATOR_MODULE_DIRECT_ATTRIBUTES[node.id]
                ):
                    invalid_module_references.append(node)

        if isinstance(node, ast.Attribute):
            if (
                node.attr.startswith("_")
                or node.attr == "modules"
                or _is_banned_os_name(node.attr)
            ):
                forbidden_attribute_traversals.append(node)

            parent = parents.get(node)
            if isinstance(parent, ast.Attribute) and parent.value is node:
                continue
            rooted_chain = _rooted_attribute_chain(node)
            if rooted_chain is None:
                continue
            module, chain = rooted_chain
            if module not in EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS:
                continue
            observed_module_rooted_chains[module].add(chain)
            if chain not in EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS[module]:
                invalid_module_references.append(node)
            if module == "sys" and chain == ("stderr",):
                attribute_parent = parents.get(node)
                call_parent = parents.get(attribute_parent)
                if not (
                    isinstance(attribute_parent, ast.keyword)
                    and attribute_parent.arg == "file"
                    and attribute_parent.value is node
                    and isinstance(call_parent, ast.Call)
                    and isinstance(call_parent.func, ast.Name)
                    and call_parent.func.id == "print"
                ):
                    invalid_sys_sinks.append(node)

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
    if observed_direct_module_imports != set(EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS):
        raise AssertionError("generator direct module import coverage drifted")
    if forbidden_references:
        raise AssertionError("generator contains a forbidden dynamic reference")
    if forbidden_attribute_traversals:
        raise AssertionError(
            "generator contains private, dunder, modules, or process traversal"
        )
    if invalid_module_references:
        raise AssertionError("generator module attribute surface drifted")
    if invalid_sys_sinks:
        raise AssertionError("generator sys.stderr use drifted")
    if observed_module_rooted_chains != {
        module: set(chains)
        for module, chains in EXPECTED_GENERATOR_MODULE_ROOTED_CHAINS.items()
    }:
        raise AssertionError("generator rooted module attribute coverage drifted")


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


def _node_at(document: Any, path: tuple[str | int, ...]) -> Any:
    node = document
    for part in path:
        node = node[part]
    return node


def _format_mutation_path(path: tuple[str | int, ...]) -> str:
    rendered = ""
    for part in path:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered.removeprefix(".")


def _exact_structure_mutations(
    source: dict[str, Any], section: str
) -> list[tuple[str, dict[str, Any]]]:
    mutations: list[tuple[str, dict[str, Any]]] = []
    sentinel = "__ST1203_MUTATED__"

    without_section = deepcopy(source)
    del without_section[section]
    mutations.append((f"{section}:delete-section", without_section))

    substituted_section = deepcopy(source)
    substituted_section[section] = sentinel
    mutations.append((f"{section}:substitute-section", substituted_section))

    def visit(path: tuple[str | int, ...], value: Any) -> None:
        path_label = _format_mutation_path(path)
        if isinstance(value, dict):
            with_unknown_field = deepcopy(source)
            unknown_target = _node_at(with_unknown_field, path)
            unknown_target["__unexpected_field__"] = sentinel
            mutations.append((f"{path_label}:add-field", with_unknown_field))

            for key, child in value.items():
                without_key = deepcopy(source)
                deletion_target = _node_at(without_key, path)
                del deletion_target[key]
                mutations.append((f"{path_label}.{key}:delete-field", without_key))

                with_substitution = deepcopy(source)
                substitution_target = _node_at(with_substitution, path)
                substitution_target[key] = sentinel
                mutations.append(
                    (f"{path_label}.{key}:substitute-field", with_substitution)
                )
                visit((*path, key), child)
            return

        if isinstance(value, list):
            with_addition = deepcopy(source)
            addition_target = _node_at(with_addition, path)
            addition_target.append(sentinel)
            mutations.append((f"{path_label}:add-item", with_addition))

            if value:
                with_duplicate = deepcopy(source)
                duplicate_target = _node_at(with_duplicate, path)
                duplicate_target.append(deepcopy(duplicate_target[0]))
                mutations.append((f"{path_label}:duplicate-item", with_duplicate))

            reordered = list(reversed(value))
            if reordered != value:
                with_reordering = deepcopy(source)
                reordering_target = _node_at(with_reordering, path)
                reordering_target[:] = reordered
                mutations.append((f"{path_label}:reorder-items", with_reordering))

            for index, child in enumerate(value):
                without_item = deepcopy(source)
                deletion_target = _node_at(without_item, path)
                del deletion_target[index]
                mutations.append((f"{path_label}[{index}]:delete-item", without_item))

                with_substitution = deepcopy(source)
                substitution_target = _node_at(with_substitution, path)
                substitution_target[index] = sentinel
                mutations.append(
                    (f"{path_label}[{index}]:substitute-item", with_substitution)
                )
                visit((*path, index), child)

    visit((section,), source[section])
    return mutations


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


def test_duplicate_yaml_keys_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="malformed"):
        generator._load_yaml(b"document: {}\ndocument: {}\n")


@pytest.mark.parametrize(
    ("section", "expected_count"),
    EXPECTED_EXACT_STRUCTURE_MUTATION_COUNTS.items(),
)
def test_exact_contract_sections_reject_every_structural_mutation(
    section: str,
    expected_count: int,
    source_contract: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mutations = _exact_structure_mutations(source_contract, section)
    assert len(mutations) == expected_count
    assert len({label for label, _mutated in mutations}) == len(mutations)

    if section == "provenance":

        def forbidden_read(*_args: object, **_kwargs: object) -> bytes:
            raise AssertionError("provenance drift must be rejected before any read")

        monkeypatch.setattr(generator, "_read_regular", forbidden_read)

    for label, mutated in mutations:
        try:
            generator._validate_exact_contract(mutated)
        except RuntimeError:
            pass
        else:
            pytest.fail(f"exact contract accepted mutation: {label}")

        if section == "provenance":
            try:
                generator._validate_pinned_sources(REPOSITORY_ROOT, mutated)
            except RuntimeError:
                pass
            else:
                pytest.fail(f"pinned-source validation accepted mutation: {label}")


def test_schema_is_parsed_from_the_hash_checked_capture(
    source_contract: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = generator._validate_pinned_sources(REPOSITORY_ROOT, source_contract)

    def forbidden_reopen(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("a captured schema must not be reopened")

    monkeypatch.setattr(generator, "_read_regular", forbidden_reopen)
    schema = generator._schema_by_role(source_contract, "acquisition_request", captured)
    assert schema["$id"].endswith("gsc-search-analytics-request.schema.json")


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

    monkeypatch.setattr(generator.os, "open", tracked_open)

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

    monkeypatch.setattr(generator.os, "close", close_then_fail)

    with pytest.raises(RuntimeError, match="exceeds its size limit") as exc_info:
        generator._read_regular(
            tmp_path,
            Path("payload.json"),
            label="primary-error test source",
            maximum_bytes=1,
        )

    assert "descriptor cleanup also failed" in getattr(exc_info.value, "__notes__", ())


def test_fixture_traversal_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["fixture_file"] = "../escape.json"
    with pytest.raises(RuntimeError, match="below the repository root"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_credential_shaped_recorded_material_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["recording_id"] = "Bearer synthetic"
    with pytest.raises(RuntimeError, match="credential-shaped"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_real_site_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["request"]["site_url"] = "sc-domain:example.com"
    with pytest.raises(RuntimeError, match="synthetic allowlist"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize(
    "page",
    [
        "https://example.com/real-page",
        "https://user@example.invalid/synthetic-page",
        "https://example.invalid:443/synthetic-page",
        "https://example.invalid/synthetic-page?raw=1",
        "https://example.invalid/synthetic-page#raw",
    ],
)
def test_non_synthetic_page_is_rejected(
    page: str,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][2] = page
    with pytest.raises(RuntimeError, match="synthetic HTTPS allowlist"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_raw_query_is_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][1] = "best luggage"
    with pytest.raises(RuntimeError, match="synthetic convention"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize(
    ("provider_date", "expected_error"),
    [
        ("20260701", "ISO date"),
        ("2026-7-01", "ISO date"),
        ("2026-02-30", "ISO date"),
        ("2026-06-30", "requested date range"),
        ("2026-07-03", "requested date range"),
    ],
)
def test_invalid_recorded_date_keys_are_rejected(
    provider_date: str,
    expected_error: str,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][0] = provider_date
    with pytest.raises(RuntimeError, match=expected_error):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize("country", ["jp", "JPN", "jp1", "jpn ", None])
def test_invalid_recorded_country_keys_are_rejected(
    country: str | None,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][3] = country
    with pytest.raises(RuntimeError, match="lowercase ISO-style alpha-3"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize("device", ["mobile", "PHONE", "DESKTOP ", None])
def test_invalid_recorded_device_keys_are_rejected(
    device: str | None,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][4] = device
    with pytest.raises(RuntimeError, match="DESKTOP, MOBILE, or TABLET"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_recorded_tablet_device_key_is_allowed(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"][4] = "TABLET"
    _fixture_file, content, _inventory = generator._render_recording(
        recording, request_schema=request_schema, row_schema=row_schema
    )
    assert b'"TABLET"' in content


@pytest.mark.parametrize(
    ("dimension", "provider_key"),
    [
        ("hour", None),
        ("hour", "arbitrary"),
        ("searchAppearance", None),
        ("searchAppearance", "arbitrary"),
    ],
)
def test_unselected_dimensions_are_unsupported_by_the_recorded_profile(
    dimension: str,
    provider_key: str | None,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    with pytest.raises(RuntimeError, match="unsupported by bounded recorded profile"):
        generator._validate_synthetic_dimension_key(
            dimension,
            provider_key,
            request_start_date=date(2026, 7, 1),
            request_end_date=date(2026, 7, 2),
        )

    recording = deepcopy(recordings["baseline"])
    recording["request"]["dimensions"][0] = dimension
    recording["provider_response"]["rows"][0]["keys"][0] = provider_key
    with pytest.raises(RuntimeError, match="unsupported by bounded recorded profile"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_provider_row_count_cannot_exceed_requested_row_limit(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    rows = recording["provider_response"]["rows"]
    rows.append(deepcopy(rows[0]))
    with pytest.raises(RuntimeError, match="exceeds the requested row_limit"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


@pytest.mark.parametrize("response_aggregation", ["auto", "byProperty"])
def test_page_dimension_requires_the_selected_by_page_response_aggregation(
    response_aggregation: str,
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["responseAggregationType"] = response_aggregation
    with pytest.raises(RuntimeError, match="must be byPage"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_dimension_filters_are_rejected_in_the_recorded_checkpoint(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["request"]["dimension_filter_groups"] = [
        {
            "group_type": "and",
            "filters": [
                {
                    "dimension": "query",
                    "operator": "equals",
                    "expression": "synthetic luggage",
                }
            ],
        }
    ]
    with pytest.raises(RuntimeError, match="outside this synthetic slice"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_mismatched_dimension_keys_are_rejected(
    recordings: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    recording = deepcopy(recordings["baseline"])
    recording["provider_response"]["rows"][0]["keys"].pop()
    with pytest.raises(RuntimeError, match="key order"):
        generator._render_recording(
            recording, request_schema=request_schema, row_schema=row_schema
        )


def test_closed_inventory_rejects_extra_missing_and_symlink_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = {
        generator.MANIFEST_PATH: b"{}\n",
        **{
            generator.FIXTURE_ROOT / name: b"{}\n"
            for name in generator.EXPECTED_FIXTURE_NAMES
        },
    }
    for relative, content in outputs.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)

    generator.check(tmp_path)
    extra = tmp_path / generator.FIXTURE_ROOT / "extra.json"
    extra.write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="missing or extra"):
        generator.check(tmp_path)
    extra.unlink()

    baseline = tmp_path / generator.FIXTURE_ROOT / "baseline.json"
    baseline.unlink()
    with pytest.raises(RuntimeError, match="missing or extra"):
        generator.check(tmp_path)

    outside = tmp_path / "outside.json"
    outside.write_bytes(b"unchanged")
    baseline.symlink_to(outside)
    with pytest.raises(RuntimeError, match="regular files"):
        generator.check(tmp_path)
    assert outside.read_bytes() == b"unchanged"


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


@pytest.mark.parametrize(
    "snippet",
    [
        "_dynamic = sys.modules\n",
        "_dynamic = sys.modules['_socket']\n",
        "_dynamic = sys.modules['subprocess'].Popen\n",
        "_dynamic = os.sys\n",
        "_dynamic = os.sys.modules\n",
        "_dynamic = os.sys.modules['_socket']\n",
        "_dynamic = os.sys.modules['subprocess'].Popen\n",
        "_dynamic = sys.stdout\n",
        "_dynamic = sys.stderr.write\n",
        "alias = sys\n",
        "_dynamic = globals()['sys'].modules['_socket'].socket()\n",
        "_dynamic = argparse._sys.modules['_socket'].socket()\n",
        "_dynamic = tempfile._os.sys.modules['_socket'].socket()\n",
        "_dynamic = vars(argparse)['_sys'].modules['_socket'].socket()\n",
        "_dynamic = getattr(argparse, '_sys').modules['_socket'].socket()\n",
        "_dynamic = locals()['sys'].modules['_socket'].socket()\n",
        "setattr(argparse, 'recovered', sys.stderr)\n",
        "_dynamic = dir(argparse)\n",
        "_dynamic = argparse.Namespace()\n",
        "_dynamic = argparse.ArgumentParser.__mro__\n",
    ],
)
def test_generator_ast_guard_rejects_module_registry_capability_recovery(
    snippet: str,
) -> None:
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
