#!/usr/bin/env python3
"""Build the deterministic, default-disabled ST-1704 publication operator."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Final, NoReturn
import zipfile


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE_RELATIVE: Final = Path("changes/st-1704/publication-operator-v2")
SLICE_ROOT: Final = ROOT / SLICE_RELATIVE
PLUGIN_SLUG: Final = "raos-bounded-operator"
PLUGIN_VERSION: Final = "2.1.4"
PACKAGE_ROOT: Final = f"{PLUGIN_SLUG}/"
MANIFEST_RELATIVE: Final = SLICE_RELATIVE / "runtime-manifest.v2.json"
MANIFEST_PATH: Final = ROOT / MANIFEST_RELATIVE
BINDINGS_RELATIVE: Final = (
    SLICE_RELATIVE
    / "wordpress-plugin"
    / PLUGIN_SLUG
    / "includes"
    / "st1704-publication-bindings.v2.php"
)
BINDINGS_PATH: Final = ROOT / BINDINGS_RELATIVE
CONTROLLER_RELATIVE: Final = (
    SLICE_RELATIVE
    / "wordpress-plugin"
    / PLUGIN_SLUG
    / "includes"
    / "st1704-publication-controller.v2.php"
)
PACKAGE_README_RELATIVE: Final = (
    SLICE_RELATIVE / "wordpress-plugin" / PLUGIN_SLUG / "README.md"
)
V1_PLUGIN_ROOT_RELATIVE: Final = Path(
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/wordpress-plugin/"
    "raos-bounded-operator"
)
V1_MAIN_RELATIVE: Final = V1_PLUGIN_ROOT_RELATIVE / "raos-bounded-operator.php"
V1_README_RELATIVE: Final = V1_PLUGIN_ROOT_RELATIVE / "README.md"
V1_MANIFEST_RELATIVE: Final = Path(
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/runtime-manifest.v1.json"
)
ST1704_V1_MANIFEST_RELATIVE: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
)
PUBLICATION_PLAN_RELATIVE: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json"
)
ARTICLES_RELATIVE: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)
OUTPUT_DIRECTORY: Final = ROOT / ".secrets/st1704-publication-operator-v2/plugin"
OUTPUT_PATH: Final = OUTPUT_DIRECTORY / f"{PLUGIN_SLUG}-{PLUGIN_VERSION}.zip"
ZIP_TIMESTAMP: Final = (2026, 8, 26, 0, 0, 0)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 16 * 1024 * 1024

BASE_CANONICAL_DECISIONS_RELATIVE: Final = Path(
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"
)
BASE_CANONICAL_DECISIONS_SHA256: Final = (
    "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
)
BASE_CANONICAL_BACKLOG_RELATIVE: Final = Path(
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
)
BASE_CANONICAL_BACKLOG_SHA256: Final = (
    "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
)

PUBLISH_BINDINGS: Final = (
    ("st1704-portable-power-station-guide", "portable-power-station-guide"),
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "anker-solix-c300-c800-c1000-differences",
    ),
    (
        "st1704-countertop-dishwasher-for-small-households",
        "countertop-dishwasher-for-small-households",
    ),
    ("st1704-compact-robot-vacuum-shortlist", "compact-robot-vacuum-shortlist"),
)
REVISION_POST_IDS: Final = (
    ("st1704-portable-power-station-guide", 28),
    ("st1704-anker-solix-c300-c800-c1000-differences", 29),
    ("st1704-countertop-dishwasher-for-small-households", 41),
    ("st1704-compact-robot-vacuum-shortlist", 30),
)
EXCLUDED_UPDATE_ARTICLE: Final = "st1703-first-suitcase-comparison"

PLUGIN_FILES: Final = (
    "README.md",
    "includes/st1704-publication-bindings.v2.php",
    "includes/st1704-publication-controller.v2.php",
    "raos-bounded-operator.php",
)

RUNTIME_PATHS: Final = (
    BASE_CANONICAL_DECISIONS_RELATIVE.as_posix(),
    BASE_CANONICAL_BACKLOG_RELATIVE.as_posix(),
    "changes/st-1704/publication-operator-v2/INT-DEC-016-ADDITIVE-CLARIFICATION.yaml",
    "changes/st-1704/publication-operator-v2/ADR-001-HASH-BOUND-ST1704-PUBLICATION.md",
    "changes/st-1704/publication-operator-v2/DESIGN_HANDOFF_V2.yaml",
    "changes/st-1704/publication-operator-v2/Makefile",
    "changes/st-1704/publication-operator-v2/OPERATIONS_RUNBOOK.md",
    "changes/st-1704/publication-operator-v2/PREFLIGHT.md",
    "changes/st-1704/publication-operator-v2/README.md",
    "changes/st-1704/publication-operator-v2/contracts/canonical-publication-proposal-golden.v2.json",
    "changes/st-1704/publication-operator-v2/contracts/self-hosted-wordpress-draft-revision.v2.json",
    "changes/st-1704/publication-operator-v2/contracts/self-hosted-wordpress-publication-operator.v2.yaml",
    PACKAGE_README_RELATIVE.as_posix(),
    BINDINGS_RELATIVE.as_posix(),
    CONTROLLER_RELATIVE.as_posix(),
    V1_MANIFEST_RELATIVE.as_posix(),
    ST1704_V1_MANIFEST_RELATIVE.as_posix(),
    PUBLICATION_PLAN_RELATIVE.as_posix(),
    ARTICLES_RELATIVE.as_posix(),
    "python/raos/__init__.py",
    "python/raos/adapters/__init__.py",
    "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    "python/raos/adapters/self_hosted_wordpress_operator_credentials.py",
    "python/raos/domain/operations/self_hosted_wordpress_publication_operator_v2.py",
    "python/raos/domain/operations/self_hosted_wordpress_draft_revision_operator_v2.py",
    "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/operations/self_hosted_wordpress_operator.py",
    "python/raos/ports/__init__.py",
    "python/raos/ports/self_hosted_editorial_pilot.py",
    "python/raos/ports/self_hosted_wordpress_publication_operator_v2.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_json_v2.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_journal_v2.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_https_v2.py",
    "scripts/build_st1704_wordpress_publication_operator_v2.py",
    "scripts/st1704_wordpress_publication_operator_v2.py",
    "scripts/st1704_wordpress_publication_operator_v2_python.sh",
)


class PublicationOperatorBuildFailure(RuntimeError):
    """Closed build failure without source or private artifact material."""


def _fail(
    code: str = "ST1704_PUBLICATION_OPERATOR_V2_BUILD_INVALID",
) -> NoReturn:
    raise PublicationOperatorBuildFailure(code) from None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        _fail()


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


def _read_regular(root: Path, relative: str) -> bytes:
    safe = _safe_relative(relative)
    path = root.joinpath(*safe.parts)
    try:
        metadata = path.lstat()
    except OSError:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_SOURCE_MISSING")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > MAX_SOURCE_BYTES
        or metadata.st_nlink != 1
    ):
        _fail()
    try:
        payload = path.read_bytes()
    except OSError:
        _fail()
    if len(payload) != metadata.st_size:
        _fail()
    return payload


def _read_repository(relative: str | Path) -> bytes:
    return _read_regular(ROOT, Path(relative).as_posix())


def _load_json(relative: str | Path) -> object:
    try:
        return json.loads(_read_repository(relative).decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        _fail()


def validate_predecessors() -> None:
    pinned = (
        (BASE_CANONICAL_DECISIONS_RELATIVE, BASE_CANONICAL_DECISIONS_SHA256),
        (BASE_CANONICAL_BACKLOG_RELATIVE, BASE_CANONICAL_BACKLOG_SHA256),
    )
    for relative, expected in pinned:
        if sha256_bytes(_read_repository(relative)) != expected:
            _fail("ST1704_PUBLICATION_OPERATOR_V2_PREDECESSOR_DRIFT")

    v1_manifest = _load_json(V1_MANIFEST_RELATIVE)
    editorial_manifest = _load_json(ST1704_V1_MANIFEST_RELATIVE)
    if (
        not isinstance(v1_manifest, dict)
        or v1_manifest.get("schema")
        != "RAOS_SELF_HOSTED_WORDPRESS_OPERATOR_RUNTIME_MANIFEST_V1"
        or v1_manifest.get("story_id") != "ST-1506"
        or not isinstance(editorial_manifest, dict)
        or editorial_manifest.get("schema")
        != "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
        or editorial_manifest.get("story_id") != "ST-1704"
    ):
        _fail("ST1704_PUBLICATION_OPERATOR_V2_PREDECESSOR_DRIFT")


def validate_publication_bindings() -> None:
    plan = _load_json(PUBLICATION_PLAN_RELATIVE)
    articles = _load_json(ARTICLES_RELATIVE)
    if (
        not isinstance(plan, dict)
        or plan.get("schema") != "SELF_HOSTED_EDITORIAL_PUBLICATION_PLAN_V1"
        or plan.get("story_id") != "ST-1704"
        or plan.get("publication_authority") != "NONE"
        or not isinstance(plan.get("articles"), list)
        or not isinstance(articles, dict)
        or articles.get("schema") != "SELF_HOSTED_EDITORIAL_ARTICLE_COLLECTION_V1"
        or articles.get("publication_authority") != "NONE"
        or not isinstance(articles.get("articles"), list)
    ):
        _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
    plan_actions = [
        (item.get("article_id"), item.get("action"))
        for item in plan["articles"]
        if isinstance(item, dict)
    ]
    expected_actions = [(EXCLUDED_UPDATE_ARTICLE, "UPDATE_EXISTING")] + [
        (article_id, "PUBLISH_NEW") for article_id, _slug in PUBLISH_BINDINGS
    ]
    if plan_actions != expected_actions:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
    observed: list[tuple[str, str]] = []
    for item in articles["articles"]:
        if not isinstance(item, dict):
            _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
        article_id = item.get("article_id")
        if article_id == EXCLUDED_UPDATE_ARTICLE:
            continue
        if item.get("category") != "暮らしの道具":
            _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
        slug = item.get("slug")
        if type(article_id) is not str or type(slug) is not str:
            _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
        observed.append((article_id, slug))
    if tuple(observed) != PUBLISH_BINDINGS:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")
    if (
        tuple(article_id for article_id, _post_id in REVISION_POST_IDS)
        != tuple(article_id for article_id, _slug in PUBLISH_BINDINGS)
        or len({post_id for _article_id, post_id in REVISION_POST_IDS}) != 4
        or any(post_id < 1 for _article_id, post_id in REVISION_POST_IDS)
    ):
        _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDING_DRIFT")


def build_bindings() -> bytes:
    validate_predecessors()
    validate_publication_bindings()
    articles_json = canonical_json_bytes(dict(PUBLISH_BINDINGS)).decode("ascii")
    articles_sha256 = sha256_bytes(articles_json.encode("ascii"))
    revision_post_ids_json = canonical_json_bytes(dict(REVISION_POST_IDS)).decode(
        "ascii"
    )
    revision_post_ids_sha256 = sha256_bytes(revision_post_ids_json.encode("ascii"))
    return (
        "<?php\n"
        "/** Generated by scripts/build_st1704_wordpress_publication_operator_v2.py. */\n"
        "if (! defined('ABSPATH')) {\n"
        "    exit;\n"
        "}\n\n"
        "final class RAOS_ST1704_Publication_Bindings_V2\n"
        "{\n"
        "    const SCHEMA = 'RAOS_ST1704_PUBLICATION_BINDINGS_V2';\n"
        "    const CATEGORY_NAME = '\u66ae\u3089\u3057\u306e\u9053\u5177';\n"
        "    const CATEGORY_CONTRACT = 'KURASHINO_DOGU_SINGLE_V1';\n"
        f"    const ARTICLES_JSON = '{articles_json}';\n"
        f"    const ARTICLES_SHA256 = '{articles_sha256}';\n\n"
        f"    const REVISION_POST_IDS_JSON = '{revision_post_ids_json}';\n"
        f"    const REVISION_POST_IDS_SHA256 = '{revision_post_ids_sha256}';\n\n"
        "    public static function articles()\n"
        "    {\n"
        "        if (! hash_equals(\n"
        "            self::ARTICLES_SHA256,\n"
        "            hash('sha256', self::ARTICLES_JSON)\n"
        "        )) {\n"
        "            return array();\n"
        "        }\n"
        "        $articles = json_decode(self::ARTICLES_JSON, true);\n"
        "        if (! is_array($articles) || count($articles) !== 4) {\n"
        "            return array();\n"
        "        }\n"
        "        foreach ($articles as $article_id => $slug) {\n"
        "            if (! is_string($article_id) || ! is_string($slug)\n"
        "                || preg_match('/\\A[a-z0-9-]+\\z/D', $article_id) !== 1\n"
        "                || preg_match('/\\A[a-z0-9-]+\\z/D', $slug) !== 1) {\n"
        "                return array();\n"
        "            }\n"
        "        }\n"
        "        return $articles;\n"
        "    }\n"
        "\n    public static function revision_post_ids()\n"
        "    {\n"
        "        if (! hash_equals(\n"
        "            self::REVISION_POST_IDS_SHA256,\n"
        "            hash('sha256', self::REVISION_POST_IDS_JSON)\n"
        "        )) {\n"
        "            return array();\n"
        "        }\n"
        "        $post_ids = json_decode(self::REVISION_POST_IDS_JSON, true);\n"
        "        if (! is_array($post_ids) || count($post_ids) !== 4) {\n"
        "            return array();\n"
        "        }\n"
        "        foreach ($post_ids as $article_id => $post_id) {\n"
        "            if (! is_string($article_id) || ! is_int($post_id)\n"
        "                || $post_id < 1) {\n"
        "                return array();\n"
        "            }\n"
        "        }\n"
        "        return $post_ids;\n"
        "    }\n"
        "}\n"
    ).encode("utf-8", errors="strict")


def _check_bindings() -> None:
    if _read_repository(BINDINGS_RELATIVE) != build_bindings():
        _fail("ST1704_PUBLICATION_OPERATOR_V2_BINDINGS_DRIFT")


def _transform_v1_main() -> bytes:
    source = _read_repository(V1_MAIN_RELATIVE)
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()
    header = " * Version: 1.0.0\n"
    if text.count(header) != 1:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_V1_ANCHOR_DRIFT")
    text = text.replace(header, f" * Version: {PLUGIN_VERSION}\n", 1)
    minimum = " * Requires at least: 6.9\n"
    if text.count(minimum) != 1 or " * Tested up to:" in text:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_V1_ANCHOR_DRIFT")
    text = text.replace(
        minimum,
        " * Requires at least: 7.1\n * Tested up to: 7.1\n",
        1,
    )
    tail = (
        "register_activation_hook(__FILE__, array('RAOS_Bounded_Operator', 'activate'));\n"
        "RAOS_Bounded_Operator::instance();\n"
    )
    if text.count(tail) != 1 or not text.endswith(tail):
        _fail("ST1704_PUBLICATION_OPERATOR_V2_V1_ANCHOR_DRIFT")
    injection = tail + (
        "\nrequire_once __DIR__ . '/includes/st1704-publication-bindings.v2.php';\n"
        "require_once __DIR__ . '/includes/st1704-publication-controller.v2.php';\n"
        "register_activation_hook(\n"
        "    __FILE__,\n"
        "    array('RAOS_ST1704_Publication_Controller_V2', 'activate')\n"
        ");\n"
        "RAOS_ST1704_Publication_Controller_V2::instance(\n"
        "    RAOS_Bounded_Operator::instance()\n"
        ");\n"
    )
    return (text[: -len(tail)] + injection).encode("utf-8", errors="strict")


def package_files() -> dict[str, bytes]:
    validate_predecessors()
    validate_publication_bindings()
    _check_bindings()
    controller = _read_repository(CONTROLLER_RELATIVE)
    try:
        controller_text = controller.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()
    for token in (
        "final class RAOS_ST1704_Publication_Controller_V2",
        "raos-operator/v2",
        "PUBLISH_ST1704_ARTICLE",
        "REVISE_ST1704_DRAFT",
        "RAOS_ST1704_PUBLICATION_WRITES_ENABLED",
    ):
        if token not in controller_text:
            _fail("ST1704_PUBLICATION_OPERATOR_V2_CONTROLLER_DRIFT")
    return {
        "README.md": _read_repository(PACKAGE_README_RELATIVE),
        "includes/st1704-publication-bindings.v2.php": _read_repository(
            BINDINGS_RELATIVE
        ),
        "includes/st1704-publication-controller.v2.php": controller,
        "raos-bounded-operator.php": _transform_v1_main(),
    }


def build_package() -> bytes:
    files = package_files()
    if tuple(files) != PLUGIN_FILES:
        _fail()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in PLUGIN_FILES:
            info = zipfile.ZipInfo(PACKAGE_ROOT + relative, ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, files[relative])
    payload = output.getvalue()
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        _fail()
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            expected = [PACKAGE_ROOT + item for item in PLUGIN_FILES]
            if archive.namelist() != expected:
                _fail()
            for name in expected:
                info = archive.getinfo(name)
                relative = name[len(PACKAGE_ROOT) :]
                if (
                    info.date_time != ZIP_TIMESTAMP
                    or info.compress_type != zipfile.ZIP_STORED
                    or stat.S_IFMT(info.external_attr >> 16) != stat.S_IFREG
                    or stat.S_IMODE(info.external_attr >> 16) != 0o644
                    or archive.read(name) != files[relative]
                ):
                    _fail()
    except OSError, zipfile.BadZipFile, KeyError:
        _fail()
    return payload


def build_manifest() -> bytes:
    package = build_package()
    files = package_files()
    semantic_inputs = [
        {"path": relative, "semantic_id": relative, "version": 2}
        for relative in RUNTIME_PATHS
        if relative
        not in {
            BASE_CANONICAL_DECISIONS_RELATIVE.as_posix(),
            BASE_CANONICAL_BACKLOG_RELATIVE.as_posix(),
        }
    ]
    manifest = {
        "approval_authority": "DISTINCT_COOKIE_AUTHENTICATED_MANAGE_OPTIONS_HUMAN_ONLY",
        "base_canonical_package_bytes_modified": False,
        "canonical_addendum": "INT-DEC-016",
        "codex_approval_authority": "NONE",
        "external_action_authority": "DISTINCT_HUMAN_APPROVAL_ONLY",
        "generated_by": "scripts/build_st1704_wordpress_publication_operator_v2.py",
        "gates": {
            "RAOS_OPERATOR_WRITES_ENABLED": "DEFAULT_DISABLED",
            "RAOS_ST1704_PUBLICATION_WRITES_ENABLED": "DEFAULT_DISABLED",
            "RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED": (
                "DEFAULT_DISABLED_ADMIN_ONLY_INCIDENT_RECONCILIATION"
            ),
        },
        "operator_contract_version": 2,
        "package": {
            "bytes": len(package),
            "compression": "ZIP_STORED",
            "file_count": len(files),
            "files": [
                {
                    "bytes": len(files[name]),
                    "path": name,
                    "sha256": sha256_bytes(files[name]),
                }
                for name in PLUGIN_FILES
            ],
            "root": PACKAGE_ROOT,
            "sha256": sha256_bytes(package),
            "version": PLUGIN_VERSION,
        },
        "integrity_inputs": [
            {
                "path": BASE_CANONICAL_DECISIONS_RELATIVE.as_posix(),
                "sha256": BASE_CANONICAL_DECISIONS_SHA256,
            },
            {
                "path": BASE_CANONICAL_BACKLOG_RELATIVE.as_posix(),
                "sha256": BASE_CANONICAL_BACKLOG_SHA256,
            },
        ],
        "incident_reconciliation": {
            "authority": (
                "COOKIE_SESSION_MANAGE_OPTIONS_PUBLISH_POSTS_EDIT_POST_"
                "DISTINCT_HUMAN"
            ),
            "proposal_state_mutation": "NONE",
            "rest_authority": "NONE",
            "targets": [
                {"article_id": article_id, "post_id": post_id}
                for article_id, post_id in REVISION_POST_IDS[:2]
            ],
        },
        "semantic_inputs": semantic_inputs,
        "predecessors": {
            "st1506_wordpress_operator": {"owner_version": 1},
            "st1704_editorial_runtime": {"owner_version": 1},
        },
        "production_readiness": "NOT_READY",
        "publication_article_ids": [item[0] for item in PUBLISH_BINDINGS],
        "publication_authority": "DISTINCT_HUMAN_APPROVAL_ONLY",
        "schema": "RAOS_ST1704_PUBLICATION_OPERATOR_RUNTIME_MANIFEST_V2",
        "slice_id": "ST1704_PUBLICATION_OPERATOR_V2",
        "story_id": "ST-1704",
        "supported_mutations": [
            "PUBLISH_ST1704_ARTICLE",
            "REVISE_ST1704_DRAFT",
        ],
        "writes_default": "DISABLED",
    }
    return (
        json.dumps(
            manifest, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("ascii", errors="strict")


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(
            mode=0o700 if mode == 0o600 else 0o755, parents=True, exist_ok=True
        )
        if path.parent.is_symlink() or not path.parent.is_dir():
            _fail()
        if mode == 0o600:
            os.chmod(path.parent, 0o700)
        descriptor = os.open(
            temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except PublicationOperatorBuildFailure:
        raise
    except OSError:
        _fail()
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def check_manifest(expected: bytes) -> None:
    try:
        current = MANIFEST_PATH.read_bytes()
    except OSError:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_MANIFEST_MISSING")
    if current != expected:
        _fail("ST1704_PUBLICATION_OPERATOR_V2_MANIFEST_DRIFT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--bindings", action="store_true")
    commands.add_argument("--source-check", action="store_true")
    commands.add_argument("--package-check", action="store_true")
    commands.add_argument("--package", action="store_true")
    commands.add_argument("--manifest", action="store_true")
    commands.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.bindings:
            _atomic_write(BINDINGS_PATH, build_bindings(), 0o644)
            print("ST1704_PUBLICATION_OPERATOR_V2_BINDINGS_GENERATED")
            return 0
        if arguments.source_check:
            package_files()
            print("ST1704_PUBLICATION_OPERATOR_V2_SOURCE_OK")
            return 0
        default_generate = not any(vars(arguments).values())
        if arguments.manifest or default_generate:
            _atomic_write(BINDINGS_PATH, build_bindings(), 0o644)
        first = build_package()
        second = build_package()
        if first != second:
            _fail("ST1704_PUBLICATION_OPERATOR_V2_PACKAGE_NONDETERMINISTIC")
        if arguments.package_check:
            print("ST1704_PUBLICATION_OPERATOR_V2_PACKAGE_OK")
            return 0
        if arguments.package:
            _atomic_write(OUTPUT_PATH, first, 0o600)
            print(
                json.dumps(
                    {
                        "artifact": OUTPUT_PATH.as_posix(),
                        "bytes": len(first),
                        "publication_authority": "DISTINCT_HUMAN_APPROVAL_ONLY",
                        "sha256": sha256_bytes(first),
                    },
                    allow_nan=False,
                    sort_keys=True,
                )
            )
            return 0
        manifest = build_manifest()
        if arguments.manifest or default_generate:
            _atomic_write(MANIFEST_PATH, manifest, 0o644)
            print("ST1704_PUBLICATION_OPERATOR_V2_MANIFEST_GENERATED")
            return 0
        check_manifest(manifest)
        print("ST1704_PUBLICATION_OPERATOR_V2_MANIFEST_OK")
        return 0
    except PublicationOperatorBuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
