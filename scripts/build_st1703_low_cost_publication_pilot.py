#!/usr/bin/env python3
"""Build the semantic ST-1703 low-cost publication pilot plan."""

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
PILOT_ROOT: Final = Path("changes/st-1703/low-cost-publication-pilot")
CONTRACT_PATH: Final = PILOT_ROOT / "low-cost-publication-pilot.v1.yaml"
OUTPUT_PATH: Final = PILOT_ROOT / "generated/low-cost-publication-pilot.v1.json"
MANIFEST_PATH: Final = PILOT_ROOT / "manifest.yaml"
GENERATOR_PATH: Final = Path("scripts/build_st1703_low_cost_publication_pilot.py")
GENERATED_PATHS: Final = (OUTPUT_PATH, MANIFEST_PATH)
SOURCE_PATHS: Final = (CONTRACT_PATH, GENERATOR_PATH)
MAX_SOURCE_BYTES: Final = 512 * 1024


class LowCostPublicationPilotError(RuntimeError):
    """Closed build failure without source material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise LowCostPublicationPilotError(code)


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
        with path.open("rb") as stream:
            content = stream.read(MAX_SOURCE_BYTES + 1)
    except LowCostPublicationPilotError:
        raise
    except OSError:
        _fail("INPUT_INVALID")
    if len(content) != metadata.st_size:
        _fail("INPUT_INVALID")
    return content


def load_yaml(root: Path = REPO_ROOT, relative: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        value = yaml.safe_load(_read_regular(root, relative))
    except LowCostPublicationPilotError:
        raise
    except (UnicodeError, yaml.YAMLError):
        _fail("CONTRACT_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("CONTRACT_INVALID")
    return cast(dict[str, Any], value)


def validate_contract(contract: dict[str, Any]) -> None:
    expected_keys = (
        "document",
        "decision_context",
        "pilot",
        "spend_boundary",
        "quality_and_ux_requirements",
        "planned_checkpoints",
        "inherited_blockers",
        "evidence_boundary",
        "action_boundary",
        "effect_boundary",
        "evidence_records",
    )
    if tuple(contract) != expected_keys:
        _fail("CONTRACT_INVALID")
    document = contract["document"]
    decision = contract["decision_context"]
    pilot = contract["pilot"]
    spend = contract["spend_boundary"]
    evidence = contract["evidence_boundary"]
    actions = contract["action_boundary"]
    effects = contract["effect_boundary"]
    if not all(type(value) is dict for value in (document, decision, pilot, spend, evidence, actions, effects)):
        _fail("CONTRACT_INVALID")
    if (
        document.get("schema") != "RAOS_LOW_COST_PUBLICATION_PILOT_V2"
        or document.get("story_id") != "ST-1703"
        or document.get("development_status") != "CONTINUOUS_LOCAL_IMPLEMENTATION"
        or document.get("production_readiness") != "NOT_READY"
        or decision.get("development_authority")
        != "CONTINUOUS_REVERSIBLE_REPOSITORY_WORK"
        or pilot.get("duration_days") != 30
        or spend.get("exact_incremental_external_spend_cap") != 2000
        or spend.get("purchase_authority") != "NOT_AUTHORIZED"
        or any(value != [] for value in actions.values())
        or any(value != [] for value in effects.values())
        or contract["evidence_records"] != []
        or evidence.get("staging") != "NOT_EXECUTED"
        or evidence.get("publication") != "NOT_EXECUTED"
        or evidence.get("production") != "NOT_EXECUTED"
    ):
        _fail("SAFETY_BOUNDARY_DRIFT")
    encoded = yaml.safe_dump(contract, allow_unicode=True, sort_keys=False).encode("utf-8")
    lowered = encoded.lower()
    if any(
        marker in lowered
        for marker in (
            b"approved_base_commit",
            b"handoff_sha256",
            b"approval_sha256",
            b"implementation_authority:",
        )
    ):
        _fail("GOVERNANCE_BINDING_FORBIDDEN")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render(root: Path = REPO_ROOT) -> tuple[bytes, bytes]:
    contract = load_yaml(root)
    validate_contract(contract)
    output = _json_bytes(copy.deepcopy(contract))
    manifest = {
        "schema_version": 2,
        "generator_owner_id": "build_st1703_low_cost_publication_pilot",
        "generator_version": 2,
        "story_ids": ["ST-1703"],
        "semantic_inputs": [
            {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "semantic_id": "st1703-low-cost-publication-pilot",
                "semantic_version": "2.0.0",
            }
        ],
        "outputs": [
            {
                "uri": f"repo://{OUTPUT_PATH.as_posix()}",
                "bytes": len(output),
                "sha256": hashlib.sha256(output).hexdigest(),
            }
        ],
    }
    return output, yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).encode(
        "utf-8"
    )


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
    expected = {OUTPUT_PATH: output, MANIFEST_PATH: manifest}
    if check:
        for path, content in expected.items():
            try:
                current = (root / path).read_bytes()
            except OSError:
                _fail("GENERATED_DRIFT")
            if current != content:
                _fail("GENERATED_DRIFT")
        return
    for path, content in expected.items():
        _write_atomic(root, path, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(check=arguments.check)
    except LowCostPublicationPilotError as error:
        print(f"ERROR code={error.code}", file=sys.stderr)
        return 1
    print("ST-1703 low-cost pilot checked" if arguments.check else "ST-1703 low-cost pilot generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
