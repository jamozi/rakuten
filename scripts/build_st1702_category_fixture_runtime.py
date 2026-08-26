#!/usr/bin/env python3
"""Build the recorded/synthetic maximum-safe ST-1702 runtime fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from scripts import secure_generated_publication  # noqa: E402

from raos.domain.catalog.category_fixtures import (  # noqa: E402
    build_category_fixture_bundle,
)


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"

CONTRACT_PATH: Final = Path(
    "changes/st-1702/contracts/category-fixture-runtime.v2.json"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1702/generated/category-fixture-runtime-recorded.v2.json"
)
GENERATED_PYTHON_PATH: Final = Path(
    "python/raos/adapters/recorded_category_fixture_v2.py"
)
MANIFEST_PATH: Final = Path("changes/st-1702/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1702_category_fixture_runtime.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")

BINDINGS: Final = (
    (
        "v1_reference_plan",
        Path(
            "changes/st-1702/generated/category-fixtures-rules-reference-plan.v1.json"
        ),
        "build_st1702_category_fixtures_rules_reference_plan",
        2,
    ),
    (
        "st1701_decision_package",
        Path("changes/st-1701/contracts/mvp-business-decision-package.v1.yaml"),
        "build_st1701_business_inputs",
        2,
    ),
    (
        "st0504_reference_plan",
        Path(
            "changes/st-0504/generated/product-identity-human-review-reference-plan.v1.json"
        ),
        "build_st0504_product_identity_human_review_reference_plan",
        2,
    ),
    (
        "st1401_completion",
        Path("changes/st-1401/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"),
        "st1401_freshness_safe_default",
        1,
    ),
    (
        "st1401_freshness_policy",
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_freshness_update_policy_v0.1.yaml"
        ),
        "st1401_freshness_policy",
        1,
    ),
)

CANONICAL_BINDINGS: Final = (
    (
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/catalog/category_fixtures.py"),
    Path("python/raos/ports/category_fixtures.py"),
    Path("python/raos/application/catalog/category_fixtures.py"),
    Path("python/raos/adapters/recorded_category_fixtures.py"),
)
SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *(path for _name, path, _owner_id, _version in BINDINGS),
    *(path for path, _digest in CANONICAL_BINDINGS),
    SECURE_HELPER_PATH,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, GENERATED_PYTHON_PATH, MANIFEST_PATH)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024


class CategoryFixtureRuntimeGenerationError(ValueError):
    __slots__ = ()


def _fail(code: str) -> NoReturn:
    raise CategoryFixtureRuntimeGenerationError(code) from None


def _validate_toolchain() -> None:
    """Tool versions are verified once by setup/final."""


def _validate_relative(relative: Path) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_PATH")


def _lexical_root(root: Path) -> Path:
    if not root.parts or any(part in {"", ".", ".."} for part in root.parts):
        _fail("UNSAFE_ROOT")
    absolute = root if root.is_absolute() else Path.cwd() / root
    normalized = Path(os.path.abspath(os.fspath(absolute)))
    if not normalized.is_absolute() or any(
        part in {"", ".", ".."} for part in normalized.parts[1:]
    ):
        _fail("UNSAFE_ROOT")
    return normalized


def _open_root(root: Path) -> int:
    absolute = _lexical_root(root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, flags))
        for component in absolute.parts[1:]:
            descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
        return descriptors.pop()
    except OSError:
        _fail("UNSAFE_ROOT")
    finally:
        while descriptors:
            os.close(descriptors.pop())


def _validate_directory(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("SOURCE_ANCESTOR_INVALID")


def _validate_regular(metadata: os.stat_result, *, maximum: int) -> None:
    prohibited = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | 0o022
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & prohibited
        or metadata.st_nlink != 1
        or metadata.st_size > maximum
    ):
        _fail("SOURCE_IDENTITY_INVALID")


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_regular(
    root: Path,
    relative: Path,
    *,
    maximum: int = MAX_SOURCE_BYTES,
) -> bytes:
    _validate_relative(relative)
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor = _open_root(root)
        _validate_directory(os.fstat(parent_descriptor))
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        for component in relative.parts[:-1]:
            before = os.stat(
                component,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            _validate_directory(before)
            child = os.open(component, directory_flags, dir_fd=parent_descriptor)
            opened = os.fstat(child)
            _validate_directory(opened)
            if _identity(opened) != _identity(before):
                os.close(child)
                _fail("SOURCE_CHANGED_DURING_READ")
            os.close(parent_descriptor)
            parent_descriptor = child
        name = relative.parts[-1]
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        _validate_regular(before, maximum=maximum)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        _validate_regular(opened, maximum=maximum)
        if _identity(opened) != _identity(before):
            _fail("SOURCE_CHANGED_DURING_READ")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _fail("SOURCE_SIZE_INVALID")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _validate_regular(named_after, maximum=maximum)
        if (
            _identity(after) != _identity(opened)
            or _identity(named_after) != _identity(opened)
            or total != opened.st_size
        ):
            _fail("SOURCE_CHANGED_DURING_READ")
        return b"".join(chunks)
    except CategoryFixtureRuntimeGenerationError:
        raise
    except OSError:
        _fail("SOURCE_OPEN_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _capture_sources(root: Path) -> dict[Path, bytes]:
    if len(set(SOURCE_PATHS)) != len(SOURCE_PATHS):
        _fail("SOURCE_INVENTORY_INVALID")
    captured = {path: _read_regular(root, path) for path in SOURCE_PATHS}
    if tuple(captured) != SOURCE_PATHS:
        _fail("SOURCE_INVENTORY_INVALID")
    return captured


def _require_hashes(inputs: dict[Path, bytes]) -> None:
    for path, digest in CANONICAL_BINDINGS:
        if hashlib.sha256(inputs[path]).hexdigest() != digest:
            _fail("SOURCE_HASH_DRIFT")


def _output_path(root: Path, relative: Path) -> Path:
    _validate_relative(relative)
    return _lexical_root(root) / relative


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail("CONTRACT_PARSE_FAILED")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    del value
    _fail("CONTRACT_PARSE_FAILED")


CONTRACT_KEYS: Final = (
    "schemaVersion",
    "storyId",
    "classification",
    "dataClass",
    "environment",
    "fixtureId",
    "category",
    "attributeSchema",
    "goldenProducts",
    "identityCases",
    "identityPolicy",
    "freshnessPolicy",
    "authority",
)


def _parse_contract(payload: bytes) -> dict[str, Any]:
    if not 2 <= len(payload) <= 256 * 1024:
        _fail("CONTRACT_SHAPE_INVALID")
    try:
        parsed: object = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except CategoryFixtureRuntimeGenerationError:
        raise
    except UnicodeError, json.JSONDecodeError, RecursionError, ValueError, TypeError:
        _fail("CONTRACT_PARSE_FAILED")
    if type(parsed) is not dict or tuple(parsed) != CONTRACT_KEYS:
        _fail("CONTRACT_SHAPE_INVALID")
    return cast(dict[str, Any], parsed)


def _record(contract: dict[str, Any]) -> dict[str, Any]:
    record = {
        "schemaVersion": contract["schemaVersion"],
        "storyId": contract["storyId"],
        "classification": contract["classification"],
        "dataClass": contract["dataClass"],
        "environment": contract["environment"],
        "fixtureId": contract["fixtureId"],
        "localStatus": "LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY",
        "canonicalStatus": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
        "bindings": {
            name: {"owner_id": owner_id, "owner_version": version}
            for name, _path, owner_id, version in BINDINGS
        },
        "category": contract["category"],
        "attributeSchema": contract["attributeSchema"],
        "goldenProducts": contract["goldenProducts"],
        "identityCases": contract["identityCases"],
        "identityPolicy": contract["identityPolicy"],
        "freshnessPolicy": contract["freshnessPolicy"],
        "authority": contract["authority"],
    }
    return record


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _fail("CANONICAL_JSON_FAILED")


def _python_bytes(fixture: bytes) -> bytes:
    digest = hashlib.sha256(fixture).hexdigest()
    encoded = repr(fixture.decode("utf-8", errors="strict"))
    return (
        '"""Generated ST-1702 recorded category fixture; do not edit."""\n\n'
        "ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256 = (\n"
        f'    "{digest}"\n'
        ")\n"
        f"ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON = {encoded}\n\n"
        "__all__ = [\n"
        '    "ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON",\n'
        '    "ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256",\n'
        "]\n"
    ).encode("utf-8")


def _manifest_bytes(
    _inputs: dict[Path, bytes], fixture: bytes, generated_python: bytes
) -> bytes:
    document = {
        "schema_version": 2,
        "generator_owner_id": "build_st1702_category_fixture_runtime",
        "generator_version": 2,
        "story_ids": ["ST-1702"],
        "semantic_inputs": [
            {
                "uri": f"repo://{path.as_posix()}",
                "semantic_id": path.as_posix(),
                "semantic_version": "2",
            }
            for path in (*OWNED_SOURCE_PATHS, SECURE_HELPER_PATH)
        ],
        "owner_dependencies": [
            {
                "name": name,
                "uri": f"repo://{path.as_posix()}",
                "owner_id": owner_id,
                "owner_version": version,
            }
            for name, path, owner_id, version in BINDINGS
        ],
        "canonical_inputs": [
            {
                "uri": f"repo://{path.as_posix()}",
                "sha256": digest,
            }
            for path, digest in CANONICAL_BINDINGS
        ],
        "outputs": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "bytes": len(fixture),
                "sha256": hashlib.sha256(fixture).hexdigest(),
            },
            {
                "uri": f"repo://{GENERATED_PYTHON_PATH.as_posix()}",
                "bytes": len(generated_python),
                "sha256": hashlib.sha256(generated_python).hexdigest(),
            },
        ],
        "boundary": {
            "data_class": "SYNTHETIC_VALIDATOR_FIXTURE_ONLY",
            "human_review_required": True,
            "runtime_enabled": False,
            "provider_access_enabled": False,
            "network_enabled": False,
            "persistence_enabled": False,
            "publication_authorized": False,
            "activation_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_020": "NOT_EXECUTED",
            "domain_reviewer_approval": "NOT_OBTAINED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    inputs = _capture_sources(root)
    _require_hashes(inputs)
    fixture = _canonical_bytes(_record(_parse_contract(inputs[CONTRACT_PATH])))
    parsed = json.loads(fixture)
    build_category_fixture_bundle(
        parsed,
        source_fixture_sha256=hashlib.sha256(fixture).hexdigest(),
    )
    generated_python = _python_bytes(fixture)
    manifest = _manifest_bytes(inputs, fixture, generated_python)
    return (
        (FIXTURE_PATH, fixture),
        (GENERATED_PYTHON_PATH, generated_python),
        (MANIFEST_PATH, manifest),
    )


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for path, expected in artifacts:
            if (
                _read_regular(
                    root,
                    path,
                    maximum=MAX_GENERATED_BYTES,
                )
                != expected
            ):
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    try:
        secure_generated_publication.publish_generated(
            tuple((_output_path(root, path), payload) for path, payload in artifacts),
            namespace="st1702v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-1702 V2 category fixture generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1702 V2 category fixture checked"
        if arguments.check
        else "ST-1702 V2 category fixture generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
