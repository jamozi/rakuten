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
from typing import TYPE_CHECKING, Final, NoReturn, cast


ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if TYPE_CHECKING:
    # Static imports are owner edges for the affected-generator build graph.
    from scripts import build_editorial_measurement_v1 as measurement_owner  # noqa: F401
    from scripts import build_editorial_portfolio_v3 as portfolio_owner  # noqa: F401
    from scripts import (  # noqa: F401
        build_editorial_v3_theme_navigation as navigation_owner,
    )
    from scripts import build_st0105_generated_contracts as contract_owner  # noqa: F401
    from scripts import build_st1704_self_hosted_theme as theme_owner  # noqa: F401
    from scripts import build_st1704_theme_assets as theme_asset_owner  # noqa: F401


SLICE_PATH: Final = Path("changes/st-1704/self-hosted-editorial-pilot-v1")
SINGLE_URL_SLICE_PATH: Final = Path(
    "changes/st-1704/carry-on-single-url-evidence-loop-v1"
)
THEME_INPUT_ROOT: Final = SLICE_PATH / "theme/kurashinoshirube-child"
SLICE: Final = SLICE_PATH.as_posix()
SINGLE_URL_SLICE: Final = SINGLE_URL_SLICE_PATH.as_posix()
OUTPUT_PATH: Final = ROOT / SLICE_PATH / "runtime-manifest.v1.json"
PREDECESSOR_INPUT_PATH: Final = Path(
    "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
PREDECESSOR_PATH: Final = ROOT / PREDECESSOR_INPUT_PATH
MAX_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_MANIFEST_BYTES: Final = 256 * 1024
GENERATED_CONTRACT_INPUT_ROOT: Final = Path("python/raos/generated/contracts")
GENERATED_CONTRACT_ROOT: Final = ROOT / GENERATED_CONTRACT_INPUT_ROOT

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)

_BASE_RUNTIME_INPUT_PATHS: Final[tuple[Path, ...]] = (
    SINGLE_URL_SLICE_PATH / "DESIGN_HANDOFF_V1.yaml",
    SINGLE_URL_SLICE_PATH / "PREFLIGHT.md",
    SINGLE_URL_SLICE_PATH / "README.md",
    SINGLE_URL_SLICE_PATH / "contracts/carry-on-single-url-evidence-loop.v1.json",
    SLICE_PATH / "DESIGN_HANDOFF_V1.yaml",
    SLICE_PATH / "EDITORIAL_RESEARCH_NOTES.md",
    SLICE_PATH / "Makefile",
    SLICE_PATH / "OPERATIONS_RUNBOOK.md",
    SLICE_PATH / "PREFLIGHT.md",
    SLICE_PATH / "README.md",
    SLICE_PATH / "REVENUE_EXPERIMENT_RUNBOOK.md",
    SLICE_PATH / "REVENUE_UNBLOCK_WORKLOG.md",
    SLICE_PATH / "content/articles.v1.json",
    Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json"),
    Path("changes/editorial-portfolio-v3/generated/navigation.v3.json"),
    SLICE_PATH / "media/product-media-registry.v1.json",
    SLICE_PATH / "media/source-images/article-portable-power-guide.png",
    SLICE_PATH / "operations/measurement-ledger.v1.json",
    SLICE_PATH / "operations/publication-plan.v1.json",
    SLICE_PATH / "sources/source-locator-contract.v1.json",
    SLICE_PATH / "sources/source-registry.v1.json",
    THEME_INPUT_ROOT / "assets/editorial-v2.css",
    THEME_INPUT_ROOT / "assets/editorial-navigation.v3.json",
    THEME_INPUT_ROOT / "assets/images/article-portable-power-guide.webp",
    THEME_INPUT_ROOT / "assets/images/article-suitcase-guide.webp",
    THEME_INPUT_ROOT / "assets/images/brand-mark.svg",
    THEME_INPUT_ROOT / "assets/images/home-hero.webp",
    THEME_INPUT_ROOT / "assets/measurement.js",
    THEME_INPUT_ROOT / "assets/theme.css",
    THEME_INPUT_ROOT / "functions.php",
    THEME_INPUT_ROOT / "parts/footer.html",
    THEME_INPUT_ROOT / "parts/header.html",
    THEME_INPUT_ROOT / "raos-assets.v1.json",
    THEME_INPUT_ROOT / "style.css",
    THEME_INPUT_ROOT / "templates/front-page.html",
    THEME_INPUT_ROOT / "templates/single.html",
    THEME_INPUT_ROOT / "theme-contract.v1.json",
    THEME_INPUT_ROOT / "theme.json",
    SLICE_PATH / "theme/yoast-seo-28.3.lock.json",
    Path("contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json"),
    Path("python/raos/adapters/self_hosted_editorial_pilot_https.py"),
    Path("python/raos/adapters/self_hosted_editorial_pilot_json.py"),
    Path("python/raos/adapters/self_hosted_editorial_source_capture.py"),
    Path("python/raos/adapters/self_hosted_wordpress_credentials.py"),
    Path("python/raos/adapters/self_hosted_wordpress_https.py"),
    Path("python/raos/adapters/self_hosted_wordpress_rest.py"),
    Path("python/raos/adapters/wordpress_rest.py"),
    Path("python/raos/application/editorial/self_hosted_editorial_pilot.py"),
    Path("python/raos/domain/editorial/content_ast.py"),
    Path("python/raos/domain/editorial/market_learning_pilot.py"),
    Path("python/raos/domain/editorial/self_hosted_editorial_pilot.py"),
    Path("python/raos/domain/editorial/self_hosted_wordpress.py"),
    Path("python/raos/ports/self_hosted_editorial_pilot.py"),
    Path("scripts/build_st1704_self_hosted_editorial_manifest.py"),
    Path("scripts/build_editorial_v3_theme_navigation.py"),
    Path("scripts/build_st1704_theme_assets.py"),
    Path("scripts/build_st1704_self_hosted_theme.py"),
    Path("scripts/st1704_official_source_capture.py"),
    Path("scripts/st1704_self_hosted_editorial_pilot.py"),
)
_BASE_RUNTIME_PATHS: Final[tuple[str, ...]] = tuple(
    path.as_posix() for path in _BASE_RUNTIME_INPUT_PATHS
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
