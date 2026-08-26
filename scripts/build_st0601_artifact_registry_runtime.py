#!/usr/bin/env python3
"""Generate the deterministic ST-0601 V2 local runtime contract IR."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, NoReturn, cast

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for import_root in (REPOSITORY_ROOT, PYTHON_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts.raos_build_core import input_hash_required  # noqa: E402


CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "changes/st-0601/contracts/local-artifact-registry-runtime.v2.yaml"
)
OUTPUT_PATH = (
    REPOSITORY_ROOT / "changes/st-0601/generated/artifact-registry-runtime.v2.json"
)
class GenerationFailure(RuntimeError):
    __slots__ = ()


def _fail(message: str) -> NoReturn:
    raise GenerationFailure(message) from None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{name} must be an exact string-keyed mapping")
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail(f"{name} must be an exact string-keyed mapping")
    return {cast(str, key): cast(Any, item) for key, item in raw.items()}


def _list(value: object, name: str) -> list[Any]:
    if type(value) is not list:
        _fail(f"{name} must be a list")
    return [cast(Any, item) for item in cast(list[object], value)]


def _load_contract() -> dict[str, Any]:
    try:
        value: object = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise GenerationFailure("contract cannot be loaded") from error
    contract = _mapping(value, "contract")
    if set(contract) != {
        "document",
        "story",
        "sources",
        "runtime",
        "security_controls",
        "evidence",
        "generation",
    }:
        _fail("contract section inventory differs")
    document = _mapping(contract["document"], "document")
    if document != {
        "id": "RAOS-LOCAL-ARTIFACT-REGISTRY-RUNTIME-002",
        "version": "2.0.0",
        "story_id": "ST-0601",
        "status": "LOCAL_CODE_COMPLETE",
        "formal_tst_014": "NOT_EXECUTED",
        "live_object_storage": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        _fail("document status boundary differs")
    runtime = _mapping(contract["runtime"], "runtime")
    if runtime.get("mode") != "RECORDED_LOCAL":
        _fail("runtime mode differs")
    retention = _mapping(runtime.get("retention"), "runtime.retention")
    if retention != {
        "decision": "OD_014_UNRESOLVED",
        "retention_class": None,
        "retention_period": None,
        "default": None,
        "lifecycle": "ABSENT",
        "delete": "ABSENT",
        "purge": "ABSENT",
    }:
        _fail("retention safe default differs")
    action_counts = _mapping(runtime.get("action_counts"), "runtime.action_counts")
    if set(action_counts) != {
        "external",
        "provider",
        "publication",
        "retention",
        "delete",
        "export",
    } or any(type(value) is not int or value != 0 for value in action_counts.values()):
        _fail("action counts must be exact zero")
    forbidden = _list(runtime.get("forbidden_surfaces"), "runtime.forbidden_surfaces")
    required_forbidden = {
        "credential",
        "network",
        "provider_call",
        "live_object_storage",
        "delete",
        "purge",
        "lifecycle",
        "export",
        "publication",
        "staging",
        "release",
        "production",
    }
    if not required_forbidden.issubset(forbidden):
        _fail("forbidden capability boundary differs")
    evidence = _mapping(contract["evidence"], "evidence")
    for name in (
        "formal_tst_014",
        "authenticated_st0202_fixture",
        "s3_version_object_lock",
        "live_provider",
        "staging",
        "release",
        "production",
    ):
        if evidence.get(name) != "NOT_EXECUTED":
            _fail(f"{name} cannot be promoted by local generation")
    generation = _mapping(contract["generation"], "generation")
    if generation != {
        "owner": "scripts/build_st0601_artifact_registry_runtime.py",
        "source": ("changes/st-0601/contracts/local-artifact-registry-runtime.v2.yaml"),
        "output": ("changes/st-0601/generated/artifact-registry-runtime.v2.json"),
        "deterministic": True,
        "network": "FORBIDDEN",
        "write_on_check": "FORBIDDEN",
    }:
        _fail("generation ownership differs")
    return contract


def _verify_sources(contract: dict[str, Any]) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, value in enumerate(_list(contract["sources"], "sources")):
        source = _mapping(value, f"sources[{index}]")
        relative = source["path"]
        if (
            type(relative) is not str
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or relative in seen
        ):
            _fail("source path is invalid")
        seen.add(relative)
        path = REPOSITORY_ROOT / relative
        if not path.is_file() or path.is_symlink():
            _fail(f"source unavailable: {relative}")
        if input_hash_required(relative):
            if set(source) != {"path", "kind", "sha256"}:
                _fail("immutable source entry shape differs")
            expected = source["sha256"]
            if (
                source["kind"] != "immutable"
                or type(expected) is not str
                or len(expected) != 64
                or _sha256(path) != expected
            ):
                _fail(f"source drift: {relative}")
            result.append(
                {"path": relative, "kind": "immutable", "sha256": expected}
            )
            continue
        if set(source) != {"path", "kind", "semantic_id", "version"}:
            _fail("tracked source entry shape differs")
        semantic_id = source["semantic_id"]
        version = source["version"]
        if (
            source["kind"] != "tracked"
            or type(semantic_id) is not str
            or not semantic_id
            or type(version) is not int
            or version < 1
        ):
            _fail("tracked source identity is invalid")
        result.append(
            {
                "path": relative,
                "kind": "tracked",
                "semantic_id": semantic_id,
                "version": version,
            }
        )
    if not result:
        _fail("sources cannot be empty")
    return tuple(result)


def render() -> bytes:
    contract = _load_contract()
    sources = _verify_sources(contract)
    output = {
        "authority": {
            "credential": "NOT_GRANTED",
            "external_operation": "NOT_GRANTED",
            "formal_validation": "NOT_GRANTED",
            "publication": "NOT_GRANTED",
            "release": "NOT_GRANTED",
            "repository_local_development": "STANDING_OWNER_AUTHORIZATION",
            "staging": "NOT_GRANTED",
            "production": "NOT_GRANTED",
        },
        "contract": {
            "uri": "repo://changes/st-0601/contracts/local-artifact-registry-runtime.v2.yaml",
            "semantic_id": "local-artifact-registry-runtime",
            "version": 2,
        },
        "document": contract["document"],
        "evidence": contract["evidence"],
        "generation": contract["generation"],
        "runtime": contract["runtime"],
        "security_controls": contract["security_controls"],
        "sources": sources,
        "story": contract["story"],
    }
    return (
        json.dumps(
            output,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rendered = render()
    if args.check:
        try:
            current = OUTPUT_PATH.read_bytes()
        except OSError:
            return 1
        return 0 if current == rendered else 1
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
