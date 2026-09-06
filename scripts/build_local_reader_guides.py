#!/usr/bin/env python3
"""Build evidence-bound guides for the isolated local preview only."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "python"))

from raos.application.editorial.local_reader_guides import build_local_guides  # noqa: E402
from scripts.raos_build_core import atomic_write, canonical_json_bytes  # noqa: E402

GENERATOR_PATH: Final = Path("scripts/build_local_reader_guides.py")
INPUT_PATHS: Final = (
    Path("changes/editorial-portfolio-v3/local-reader-guides.v1.json"),
    Path("changes/wordpress-local-preview-v1/fixtures/posts.json"),
    Path("changes/editorial-portfolio-v2/editorial-portfolio.v2.json"),
    Path("python/raos/application/editorial/local_reader_guides.py"),
    Path("python/raos/application/editorial/reader_running_cost.py"),
    Path("python/raos/application/editorial/reader_components.py"),
    Path("python/raos/application/editorial/reader_experience_v1.py"),
)
OUTPUT_PATHS: Final = (
    Path("changes/wordpress-local-preview-v1/fixtures/reader-guides.v1.json"),
)
TEST_PATHS: Final = (Path("tests/wordpress_local_preview"),)


def build_documents() -> tuple[dict[str, object], ...]:
    registry = json.loads((REPOSITORY_ROOT / INPUT_PATHS[0]).read_text(encoding="utf-8"))
    posts = json.loads((REPOSITORY_ROOT / INPUT_PATHS[1]).read_text(encoding="utf-8"))["posts"]
    portfolio = json.loads((REPOSITORY_ROOT / INPUT_PATHS[2]).read_text(encoding="utf-8"))
    available = {p["slug"] for p in posts}
    targets = {
        article["article_id"]: "/local-preview-" + article["production_slug"] + "/"
        for article in portfolio["articles"]
        if "local-preview-" + article["production_slug"] in available
    }
    result = build_local_guides(registry, today=date.today(), existing_targets=targets)
    return (result,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    for relative, document in zip(OUTPUT_PATHS, build_documents(), strict=True):
        content = canonical_json_bytes(document)
        if args.check:
            if not (REPOSITORY_ROOT / relative).is_file() or (REPOSITORY_ROOT / relative).read_bytes() != content:
                raise ValueError("LOCAL_READER_GUIDE_OUTPUT_DRIFT")
        else:
            atomic_write(relative, content)
    print("LOCAL_READER_GUIDES status=PASS publication_authority=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
