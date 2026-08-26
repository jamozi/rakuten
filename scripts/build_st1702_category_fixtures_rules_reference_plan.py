#!/usr/bin/env python3
"""Build the semantic, non-executable ST-1702 category fixture plan."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1702/contracts/category-fixtures-rules-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1702/generated/category-fixtures-rules-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1702/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1702_category_fixtures_rules_reference_plan.py"
)
SOURCE_PATHS: Final = (CONTRACT_PATH, GENERATOR_PATH)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024


class CategoryFixturesRulesReferenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise CategoryFixturesRulesReferenceError(code)


def _read_regular(root: Path, relative: Path) -> bytes:
    path = root / relative
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 1 <= metadata.st_size <= MAX_SOURCE_BYTES
        ):
            _fail("INPUT_INVALID")
        content = path.read_bytes()
    except CategoryFixturesRulesReferenceError:
        raise
    except OSError:
        _fail("INPUT_INVALID")
    if len(content) != metadata.st_size:
        _fail("INPUT_INVALID")
    return content


def _load_yaml(root: Path, relative: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(_read_regular(root, relative))
    except CategoryFixturesRulesReferenceError:
        raise
    except (UnicodeError, yaml.YAMLError):
        _fail("CONTRACT_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("CONTRACT_INVALID")
    return cast(dict[str, Any], value)


def _canonical_path(uri: object) -> Path:
    if type(uri) is not str or not uri.startswith("repo://docs/canonical/"):
        _fail("CANONICAL_INPUT_INVALID")
    relative = Path(uri.removeprefix("repo://"))
    if relative.is_absolute() or ".." in relative.parts:
        _fail("CANONICAL_INPUT_INVALID")
    return relative


def validate_contract(contract: dict[str, Any], root: Path = REPO_ROOT) -> None:
    required = {
        "document",
        "authority",
        "security_controls",
        "dependencies",
        "runtime_blockers",
        "open_decisions",
        "category_candidate",
        "fixture_boundary",
        "identity_boundary",
        "freshness_boundary",
        "human_review",
        "execution_boundary",
        "verification_boundary",
    }
    if set(contract) != required:
        _fail("CONTRACT_INVALID")
    document = contract["document"]
    authority = contract["authority"]
    dependencies = contract["dependencies"]
    execution = contract["execution_boundary"]
    if (
        type(document) is not dict
        or type(authority) is not dict
        or type(dependencies) is not list
        or type(execution) is not dict
    ):
        _fail("CONTRACT_INVALID")
    if (
        document.get("story_id") != "ST-1702"
        or document.get("executable") is not False
        or document.get("st1702_ready") is not False
        or execution.get("enabled") is not False
        or execution.get("external_authority") != "NONE"
        or any(value != 0 for value in execution.get("action_counts", {}).values())
    ):
        _fail("SAFETY_BOUNDARY_DRIFT")
    expected_dependencies = {
        "ST-1701": ("build_st1701_business_inputs", "2"),
        "ST-0504": (
            "build_st0504_product_identity_human_review_reference_plan",
            "2",
        ),
    }
    for raw in dependencies:
        if type(raw) is not dict:
            _fail("DEPENDENCY_INVALID")
        story_id = raw.get("story_id")
        if story_id in expected_dependencies:
            owner_id, owner_version = expected_dependencies[story_id]
            if (
                raw.get("owner_id") != owner_id
                or raw.get("owner_version") != owner_version
            ):
                _fail("DEPENDENCY_INVALID")
        elif story_id == "ST-1401":
            if (
                raw.get("semantic_id") != "st1401-freshness-safe-default"
                or raw.get("semantic_version") != "1.0.0"
            ):
                _fail("DEPENDENCY_INVALID")
        else:
            _fail("DEPENDENCY_INVALID")
    sources = authority.get("sources")
    if type(sources) is not list:
        _fail("CANONICAL_INPUT_INVALID")
    for raw in sources:
        if type(raw) is not dict or type(raw.get("sha256")) is not str:
            _fail("CANONICAL_INPUT_INVALID")
        relative = _canonical_path(raw.get("uri"))
        if hashlib.sha256(_read_regular(root, relative)).hexdigest() != raw["sha256"]:
            _fail("CANONICAL_INPUT_DRIFT")
    serialized = yaml.safe_dump(contract, allow_unicode=True, sort_keys=False).lower()
    if any(
        marker in serialized
        for marker in (
            "approved_base_commit",
            "handoff_sha256",
            "approval_sha256",
            "integration_base_commit",
        )
    ):
        _fail("GOVERNANCE_BINDING_FORBIDDEN")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = _load_yaml(root, CONTRACT_PATH)
    validate_contract(contract, root)
    return contract


def reference_plan(contract: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(contract)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render(root: Path = REPO_ROOT) -> tuple[bytes, bytes]:
    contract = load_contract(root)
    output = _json_bytes(reference_plan(contract))
    manifest = {
        "schema_version": 2,
        "generator_owner_id": "build_st1702_category_fixtures_rules_reference_plan",
        "generator_version": 2,
        "story_ids": ["ST-1702"],
        "semantic_inputs": [
            {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "semantic_id": "st1702-category-fixtures-rules-reference-plan",
                "semantic_version": "1.0.0",
            }
        ],
        "owner_dependencies": [
            {
                "owner_id": "build_st1701_business_inputs",
                "owner_version": 2,
            },
            {
                "owner_id": "build_st0504_product_identity_human_review_reference_plan",
                "owner_version": 2,
            },
        ],
        "canonical_inputs": copy.deepcopy(contract["authority"]["sources"]),
        "outputs": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(output),
                "sha256": hashlib.sha256(output).hexdigest(),
            }
        ],
    }
    return output, yaml.safe_dump(
        manifest, allow_unicode=True, sort_keys=False
    ).encode("utf-8")


def _write_atomic(root: Path, relative: Path, content: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.next")
    try:
        with temporary.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    output, manifest = render(root)
    expected = {REFERENCE_PLAN_PATH: output, MANIFEST_PATH: manifest}
    if check:
        for relative, content in expected.items():
            try:
                current = (root / relative).read_bytes()
            except OSError:
                _fail("GENERATED_DRIFT")
            if current != content:
                _fail("GENERATED_DRIFT")
        return
    for relative, content in expected.items():
        _write_atomic(root, relative, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(check=arguments.check)
    except CategoryFixturesRulesReferenceError as error:
        print(f"ERROR code={error.code}", file=sys.stderr)
        return 1
    print("ST-1702 category plan checked" if arguments.check else "ST-1702 category plan generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
