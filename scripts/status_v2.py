#!/usr/bin/env python3
"""Build the compact Git/CI-backed RAOS status v2 projection."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from raos_build_core import REPOSITORY_ROOT, atomic_write, discover_registry


OUTPUT = Path("changes/status/status.v2.yaml")
CANONICAL_BACKLOG = Path(
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
)
CANONICAL_BACKLOG_SHA256 = (
    "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
)


def render(root: Path = REPOSITORY_ROOT) -> bytes:
    backlog = yaml.safe_load((root / CANONICAL_BACKLOG).read_text(encoding="utf-8"))
    registry = discover_registry(root=root)
    owners_by_story: dict[str, list[str]] = {}
    for owner, spec in registry.items():
        for story_id in spec.story_ids:
            owners_by_story.setdefault(story_id, []).append(owner)

    stories: list[dict[str, object]] = []
    for canonical in backlog["stories"]:
        story_id = canonical["id"]
        owners = sorted(owners_by_story.get(story_id, []))
        outputs = [path for owner in owners for path in registry[owner].outputs]
        test_directory = root / "tests" / story_id.lower().replace("-", "")
        if not owners and not test_directory.is_dir():
            implementation = "NOT_STARTED"
        elif test_directory.is_dir() or (
            outputs and all((root / path).is_file() for path in outputs)
        ):
            implementation = "IMPLEMENTED"
        else:
            implementation = "IN_PROGRESS"
        stories.append(
            {
                "story_id": story_id,
                "implementation": implementation,
                "verification": "NOT_RUN",
                "external_not_run": ["live", "external", "owner_private"],
            }
        )

    document = {
        "document": {
            "id": "RAOS-STATUS-002",
            "version": "2.0.0",
            "history": "GIT_AND_CI",
            "legacy_v1": "ARCHIVE_ONLY",
        },
        "canonical_source": {
            "uri": f"repo://{CANONICAL_BACKLOG.as_posix()}",
            "sha256": CANONICAL_BACKLOG_SHA256,
        },
        "stories": stories,
    }
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = render()
    if arguments.check:
        if not (REPOSITORY_ROOT / OUTPUT).is_file():
            raise SystemExit("status v2 output is missing")
        if (REPOSITORY_ROOT / OUTPUT).read_bytes() != expected:
            raise SystemExit("status v2 output drift")
    else:
        atomic_write(OUTPUT, expected)
    print("RAOS_STATUS_V2 status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
