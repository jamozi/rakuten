#!/usr/bin/env python3
"""Generate the complete, switchable RAOS strategy catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.strategy_switchboard.catalog import (  # noqa: E402
    ADVANCED_EXTERNAL_PROFILE,
    BALANCED_STAGING_PROFILE,
    SAFE_LOCAL_PROFILE,
    build_complete_catalog,
)
from raos.strategy_switchboard.model import canonical_json_bytes  # noqa: E402


BACKLOG_PATH = Path(
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
)
OPEN_DECISIONS_PATH = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
OUTPUT_PATH = Path(
    "changes/all-stories/generated/switchable-strategy-catalog.v1.json"
)
STORY_PATTERN = re.compile(r"\bST-[0-9]{4}\b")
DECISION_PATTERN = re.compile(r"\bOD-[0-9]{3}\b")
EXPECTED_OPEN_DECISIONS = tuple(f"OD-{number:03d}" for number in range(1, 16))


def _read_regular_file(root: Path, relative: Path) -> bytes:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"required regular file is unavailable: {relative}")
    return path.read_bytes()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_story_ids(root: Path) -> tuple[str, ...]:
    content = _read_regular_file(root, BACKLOG_PATH)
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        raise RuntimeError("canonical Story backlog is not UTF-8") from None
    story_ids = tuple(sorted(set(STORY_PATTERN.findall(text))))
    if len(story_ids) < 100:
        raise RuntimeError(
            f"canonical Story inventory is unexpectedly small: {len(story_ids)}"
        )
    return story_ids


def canonical_open_decision_ids(root: Path) -> tuple[str, ...]:
    content = _read_regular_file(root, OPEN_DECISIONS_PATH)
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        raise RuntimeError("canonical Open Decision catalog is not UTF-8") from None
    decision_ids = tuple(sorted(set(DECISION_PATTERN.findall(text))))
    if decision_ids != EXPECTED_OPEN_DECISIONS:
        raise RuntimeError(
            "canonical Open Decision inventory differs from OD-001 through OD-015"
        )
    return decision_ids


def render(root: Path) -> bytes:
    root = root.resolve()
    story_ids = canonical_story_ids(root)
    decision_ids = canonical_open_decision_ids(root)
    catalog = build_complete_catalog(story_ids)

    observed_boundaries = set(catalog.boundary_ids)
    expected_boundaries = set(story_ids) | set(decision_ids)
    if observed_boundaries != expected_boundaries:
        missing = sorted(expected_boundaries - observed_boundaries)
        extra = sorted(observed_boundaries - expected_boundaries)
        raise RuntimeError(
            f"strategy boundary mismatch: missing={missing} extra={extra}"
        )
    for boundary_id in catalog.boundary_ids:
        candidates = catalog.for_boundary(boundary_id)
        if len(candidates) != 3:
            raise RuntimeError(
                f"{boundary_id} must have exactly safe, standard, and advanced candidates"
            )

    backlog_bytes = _read_regular_file(root, BACKLOG_PATH)
    decision_bytes = _read_regular_file(root, OPEN_DECISIONS_PATH)
    document = {
        "document": {
            "generated_by": "repo://scripts/build_all_story_strategy_catalog.py",
            "id": "RAOS-SWITCHABLE-STRATEGY-CATALOG-001",
            "status": "IMPLEMENTATION_CANDIDATE",
            "version": "1.0.0",
        },
        "authority_boundary": {
            "external_values_invented": False,
            "human_approval_invented": False,
            "open_decisions_resolved": False,
            "production_activation": False,
            "selection_requires_explicit_gate_context": True,
        },
        "catalog": catalog.to_record(),
        "catalog_sha256": catalog.sha256,
        "coverage": {
            "candidate_count": len(catalog.candidates),
            "open_decision_boundary_count": len(decision_ids),
            "story_boundary_count": len(story_ids),
            "total_boundary_count": len(catalog.boundary_ids),
        },
        "profiles": [
            SAFE_LOCAL_PROFILE.to_record(),
            BALANCED_STAGING_PROFILE.to_record(),
            ADVANCED_EXTERNAL_PROFILE.to_record(),
        ],
        "sources": [
            {
                "bytes": len(backlog_bytes),
                "sha256": _sha256(backlog_bytes),
                "uri": f"repo://{BACKLOG_PATH.as_posix()}",
            },
            {
                "bytes": len(decision_bytes),
                "sha256": _sha256(decision_bytes),
                "uri": f"repo://{OPEN_DECISIONS_PATH.as_posix()}",
            },
        ],
    }
    return canonical_json_bytes(document) + b"\n"


def write(root: Path) -> str:
    content = render(root)
    output = root.resolve() / OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return _sha256(content)


def check(root: Path) -> str:
    expected = render(root)
    output = root.resolve() / OUTPUT_PATH
    if not output.is_file() or output.is_symlink():
        raise RuntimeError(f"generated catalog is unavailable: {OUTPUT_PATH}")
    actual = output.read_bytes()
    if actual != expected:
        raise RuntimeError(
            "generated switchable strategy catalog is stale; run --write"
        )
    return _sha256(actual)


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--write", action="store_true")
    operation.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        digest = write(options.root) if options.write else check(options.root)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output": OUTPUT_PATH.as_posix(),
                "sha256": digest,
                "status": "PASS",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
