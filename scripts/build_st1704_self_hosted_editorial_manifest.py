#!/usr/bin/env python3
"""Generate or verify the closed ST-1704 editorial-pilot file manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Final, NoReturn, cast


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE: Final = "changes/st-1704/self-hosted-editorial-pilot-v1"
SINGLE_URL_SLICE: Final = "changes/st-1704/carry-on-single-url-evidence-loop-v1"
OUTPUT_PATH: Final = ROOT / SLICE / "runtime-manifest.v1.json"
PREDECESSOR_PATH: Final = (
    ROOT / "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
MAX_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_MANIFEST_BYTES: Final = 256 * 1024
GENERATED_CONTRACT_ROOT: Final = ROOT / "python/raos/generated/contracts"

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)

_BASE_RUNTIME_PATHS: Final[tuple[str, ...]] = (
    f"{SINGLE_URL_SLICE}/DESIGN_HANDOFF_V1.yaml",
    f"{SINGLE_URL_SLICE}/PREFLIGHT.md",
    f"{SINGLE_URL_SLICE}/README.md",
    f"{SINGLE_URL_SLICE}/contracts/carry-on-single-url-evidence-loop.v1.json",
    f"{SLICE}/DESIGN_HANDOFF_V1.yaml",
    f"{SLICE}/EDITORIAL_RESEARCH_NOTES.md",
    f"{SLICE}/Makefile",
    f"{SLICE}/OPERATIONS_RUNBOOK.md",
    f"{SLICE}/PREFLIGHT.md",
    f"{SLICE}/README.md",
    f"{SLICE}/REVENUE_EXPERIMENT_RUNBOOK.md",
    f"{SLICE}/REVENUE_UNBLOCK_WORKLOG.md",
    f"{SLICE}/content/articles.v1.json",
    f"{SLICE}/media/product-media-registry.v1.json",
    f"{SLICE}/operations/measurement-ledger.v1.json",
    f"{SLICE}/operations/publication-plan.v1.json",
    f"{SLICE}/sources/source-locator-contract.v1.json",
    f"{SLICE}/sources/source-registry.v1.json",
    f"{SLICE}/theme/kurashinoshirube-child/assets/editorial-v2.css",
    f"{SLICE}/theme/kurashinoshirube-child/assets/images/article-portable-power-guide.png",
    f"{SLICE}/theme/kurashinoshirube-child/assets/images/article-suitcase-guide.webp",
    f"{SLICE}/theme/kurashinoshirube-child/assets/images/brand-mark.svg",
    f"{SLICE}/theme/kurashinoshirube-child/assets/images/home-hero.webp",
    f"{SLICE}/theme/kurashinoshirube-child/assets/theme.css",
    f"{SLICE}/theme/kurashinoshirube-child/functions.php",
    f"{SLICE}/theme/kurashinoshirube-child/parts/footer.html",
    f"{SLICE}/theme/kurashinoshirube-child/parts/header.html",
    f"{SLICE}/theme/kurashinoshirube-child/raos-assets.v1.json",
    f"{SLICE}/theme/kurashinoshirube-child/style.css",
    f"{SLICE}/theme/kurashinoshirube-child/templates/front-page.html",
    f"{SLICE}/theme/kurashinoshirube-child/templates/single.html",
    f"{SLICE}/theme/kurashinoshirube-child/theme-contract.v1.json",
    f"{SLICE}/theme/kurashinoshirube-child/theme.json",
    f"{SLICE}/theme/yoast-seo-28.3.lock.json",
    "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json",
    "python/raos/adapters/self_hosted_editorial_pilot_https.py",
    "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    "python/raos/adapters/self_hosted_editorial_source_capture.py",
    "python/raos/adapters/self_hosted_wordpress_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_https.py",
    "python/raos/adapters/self_hosted_wordpress_rest.py",
    "python/raos/adapters/wordpress_rest.py",
    "python/raos/application/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/editorial/content_ast.py",
    "python/raos/domain/editorial/market_learning_pilot.py",
    "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/editorial/self_hosted_wordpress.py",
    "python/raos/ports/self_hosted_editorial_pilot.py",
    "scripts/build_st1704_self_hosted_editorial_manifest.py",
    "scripts/build_st1704_self_hosted_theme.py",
    "scripts/st1704_official_source_capture.py",
    "scripts/st1704_self_hosted_editorial_pilot.py",
)


def _generated_runtime_paths() -> tuple[str, ...]:
    try:
        root_metadata = GENERATED_CONTRACT_ROOT.lstat()
    except OSError:
        raise RuntimeError("generated contract root is unavailable") from None
    if not stat.S_ISDIR(root_metadata.st_mode) or GENERATED_CONTRACT_ROOT.is_symlink():
        raise RuntimeError("generated contract root is unsafe")
    paths = tuple(
        sorted(
            path.relative_to(ROOT).as_posix()
            for path in GENERATED_CONTRACT_ROOT.rglob("*.py")
        )
    )
    if not paths or len(set(paths)) != len(paths):
        raise RuntimeError("generated contract inventory is invalid")
    return paths


GENERATED_RUNTIME_PATHS: Final[tuple[str, ...]] = _generated_runtime_paths()
REQUIRED_RUNTIME_PATHS: Final[tuple[str, ...]] = tuple(
    sorted((*_BASE_RUNTIME_PATHS, *GENERATED_RUNTIME_PATHS))
)


class ManifestFailure(RuntimeError):
    """Closed manifest generation or verification failure."""


def _fail() -> NoReturn:
    raise ManifestFailure("SELF_HOSTED_EDITORIAL_MANIFEST_INVALID") from None


def _safe_relative(value: str) -> PurePosixPath:
    if type(value) is not str or not value or value != value.strip() or "\\" in value:
        _fail()
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail()
    return relative


def _read_regular_file(relative: str, *, maximum: int = MAX_FILE_BYTES) -> bytes:
    safe = _safe_relative(relative)
    path = ROOT.joinpath(*safe.parts)
    try:
        metadata = path.lstat()
    except OSError:
        _fail()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        _fail()
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        _fail()
    try:
        payload = path.read_bytes()
    except OSError:
        _fail()
    if len(payload) != metadata.st_size:
        _fail()
    return payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json(relative: str) -> object:
    payload = _read_regular_file(relative)
    try:
        return json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail()


def _validate_content_identity() -> None:
    document = _load_json(f"{SLICE}/content/articles.v1.json")
    if type(document) is not dict:
        _fail()
    document = cast(dict[str, object], document)
    articles_value = document.get("articles")
    if type(articles_value) is not list:
        _fail()
    articles = cast(list[object], articles_value)
    if len(articles) != 5:
        _fail()
    identities: list[str] = []
    for article_value in articles:
        if type(article_value) is not dict:
            _fail()
        article = cast(dict[str, object], article_value)
        article_id = article.get("article_id")
        if type(article_id) is not str:
            _fail()
        identities.append(article_id)
        if article.get("publication_authority") != "NONE":
            _fail()
    if tuple(identities) != ARTICLE_IDS or len(set(identities)) != 5:
        _fail()


def _validate_required_paths() -> None:
    if tuple(sorted(REQUIRED_RUNTIME_PATHS)) != REQUIRED_RUNTIME_PATHS:
        _fail()
    if len(set(REQUIRED_RUNTIME_PATHS)) != len(REQUIRED_RUNTIME_PATHS):
        _fail()
    for relative in REQUIRED_RUNTIME_PATHS:
        _read_regular_file(relative)


def build_manifest() -> bytes:
    _validate_required_paths()
    _validate_content_identity()
    _read_regular_file(
        "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json",
        maximum=MAX_MANIFEST_BYTES,
    )
    paths: list[dict[str, object]] = []
    for relative in REQUIRED_RUNTIME_PATHS:
        payload = _read_regular_file(relative)
        paths.append(
            {
                "bytes": len(payload),
                "path": relative,
                "sha256": _sha256(payload),
            }
        )
    manifest = {
        "article_ids": list(ARTICLE_IDS),
        "external_action_authority": "NONE",
        "generated_by": "scripts/build_st1704_self_hosted_editorial_manifest.py",
        "paths": paths,
        "generator_owner": "build_st1704_self_hosted_editorial_manifest",
        "generator_version": "2",
        "predecessor": {"owner_id": "build_st1703_self_hosted_runtime_manifest", "version": "2"},
        "publication_authority": "NONE",
        "schema": "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_EDITORIAL_PILOT_V1",
        "story_id": "ST-1704",
    }
    encoded = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        _fail()
    return encoded


def _write_atomic(payload: bytes) -> None:
    temporary = OUTPUT_PATH.with_name(f".{OUTPUT_PATH.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, OUTPUT_PATH)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        expected = build_manifest()
        if arguments.check:
            actual = _read_regular_file(
                f"{SLICE}/runtime-manifest.v1.json", maximum=MAX_MANIFEST_BYTES
            )
            if actual != expected:
                _fail()
        else:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(expected)
    except ManifestFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    print("SELF_HOSTED_EDITORIAL_MANIFEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
