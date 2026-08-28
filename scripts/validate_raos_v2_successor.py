#!/usr/bin/env python3
"""Validate or explicitly capture sanitized RAOS V2 successor inputs.

Normal validation is offline.  The only network-capable path is the explicit
``capture-phase0 --public-read-only`` command; it is origin-bound, credential-
free, query-free and capped.  Captured response bodies are hashed and discarded.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape as html_escape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import sys
import tempfile
from typing import Any, Final, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)
import xml.etree.ElementTree as ElementTree
import zipfile
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_ROOT: Final = ROOT / "changes/raos-v2/source-package/2.0.0-design"
RECORDED_INPUT: Final = ROOT / "changes/raos-v2/recorded-inputs/phase0-capture.v1.json"
LOCAL_TEST_EVIDENCE_INPUT: Final = (
    ROOT
    / "changes/raos-v2/recorded-inputs/phase2-local-test-evidence.v1.json"
)
VISUAL_EVIDENCE_INPUT: Final = (
    ROOT / "changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"
)
PACKAGE_PATH: Final = Path("/mnt/c/Users/naoki/Downloads/RAOS_V2_DESIGN_PACKAGE.zip")
PACKAGE_SHA256: Final = (
    "7ea856e74d73589ae37d1248e08e685e5d022b90bfc45c9bf1d6cb414b5fc42a"
)
IMMUTABLE_BASE_HEAD: Final = "ae92eb8f50e9d439c1c292cc6c76d5a9c50f85c7"
SOURCE_MANIFEST_SHA256: Final = (
    "db9dc42bebd84090b18103cc9a48a6098f9d890af3f52b93cc33a6d52f821a44"
)
PACKAGE_ROOT: Final = "RAOS_V2_DESIGN_PACKAGE"
PROMPT_PATH: Final = "CODEX_MASTER_IMPLEMENTATION_PROMPT.md"
PROMPT_SHA256: Final = (
    "a122782725efb57b9fbaa7c916e821252736c0556c993b15604872f2a424f54f"
)
ORIGIN: Final = "https://kurashinoshirube.com"
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_REDIRECTS: Final = 1
MAX_SITEMAPS: Final = 8
MAX_CAPTURE_URLS: Final = 40
TIMEOUT_SECONDS: Final = 15
LOCAL_TEST_COMMAND: Final = "TMPDIR=/tmp uv run --offline pytest -s -q tests/raos_v2"
LOCAL_TEST_COMMAND_CONTRACT: Final = (
    "BASH_PIPEFAIL_TEE_TEMP_PROMOTED_BY_RECORDER_V2"
)
LOCAL_TEST_RAW_OUTPUT_PATH: Final = Path(
    "output/pytest/raos-v2-local-test-output.txt"
)
LOCAL_TEST_RAW_OUTPUT_TEMP_PATH: Final = Path(
    "output/pytest/raos-v2-local-test-output.txt.next"
)
VISUAL_RAW_RECEIPT_PATH: Final = Path(
    "output/playwright/raos-v2-visual-review/capture-receipt.json"
)
VISUAL_HARNESS_PATH: Final = Path("tests/raos_v2/visual-validation.mjs")
VISUAL_CAPTURE_CANONICAL_CONTRACT: Final = (
    "SORT_KEYS_COMPACT_JSON_NEWLINE_FIELDS_ROUTE_VIEWPORT_CLASSIFICATION_"
    "PREVIEW_SHA_SCREENSHOT_SHA_BYTES_WIDTH_HEIGHT_V1"
)
VISUAL_CAPTURE_CANONICAL_KEYS: Final = (
    "route",
    "viewport",
    "classification",
    "previewSha256",
    "screenshotSha256",
    "bytes",
    "width",
    "height",
)
VISUAL_VIEWPORT_WIDTHS: Final = {
    "mobile-390": 390,
    "tablet-768": 768,
    "desktop-1440": 1440,
}
KNOWN_PATHS: Final = (
    "/",
    "/carry-on-suitcase-comparison/",
    "/portable-power-station-guide/",
    "/anker-solix-c300-c800-c1000-differences/",
    "/countertop-dishwasher-for-small-households/",
    "/compact-robot-vacuum-shortlist/",
    "/advertising-policy/",
    "/about-ad-policy/",
    "/privacy-policy/",
)
FORBIDDEN_SEGMENTS: Final = frozenset(
    {"wp-admin", "wp-login.php", "admin", "login", "preview", "private"}
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")

LOCAL_TEST_SOURCE_ROOTS: Final = (
    Path("changes/raos-v2/phase-2/content"),
    Path("changes/raos-v2/phase-2/data"),
    Path("changes/raos-v2/phase-2/editorial"),
    Path("changes/raos-v2/phase-2/events"),
    Path("changes/raos-v2/phase-2/fixtures"),
    Path("changes/raos-v2/phase-2/media"),
    Path("changes/raos-v2/phase-2/reviews"),
    Path("changes/raos-v2/phase-2/rules"),
    Path("changes/raos-v2/phase-2/sources"),
    Path("packages/web-ui/src/decision-support-v2"),
    Path("python/raos/adapters/decision_support_v2"),
    Path("python/raos/application/decision_support_v2"),
    Path("python/raos/domain/decision_support_v2"),
    Path("python/raos/ports/decision_support_v2"),
)
LOCAL_TEST_SOURCE_FILES: Final = (
    Path("changes/raos-v2/recorded-inputs/phase0-capture.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json"),
    Path("scripts/build_raos_v2_successor.py"),
    Path("scripts/raos_build_core.py"),
    Path("scripts/validate_raos_v2_successor.py"),
)
LOCAL_TEST_MACHINE_CONTRACT_ROOTS: Final = (
    Path("contracts/raos-v2"),
    Path("changes/raos-v2/design"),
    Path("changes/raos-v2/phase-0"),
    Path("changes/raos-v2/phase-2/claims"),
    Path("changes/raos-v2/phase-2/preview"),
)
LOCAL_TEST_MACHINE_CONTRACT_FILES: Final = (
    Path("changes/raos-v2/source-import.v1.json"),
    Path("changes/raos-v2/clarifications.v1.yaml"),
    Path("changes/raos-v2/product-spec.v2.yaml"),
    Path("changes/raos-v2/route-registry.v2.yaml"),
    Path("changes/raos-v2/generated/phase-1-validation.v1.json"),
    Path("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/publication-candidate.v2.json"),
    Path("changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"),
    Path("changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"),
    Path("changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"),
)


class ValidationFailure(RuntimeError):
    """Sanitized successor validation failure."""


def fail(code: str) -> NoReturn:
    raise ValidationFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def compact_canonical_json_bytes(value: object) -> bytes:
    """Canonical compact bytes used by the visual capture row contract."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _inventory_files(root: Path, roots: Sequence[Path]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for relative_root in roots:
        absolute_root = root / relative_root
        if not absolute_root.is_dir() or absolute_root.is_symlink():
            fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
        for path in absolute_root.rglob("*"):
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
            if path.is_file():
                files.add(relative)
    return tuple(sorted(files))


def content_inventory_binding(
    paths: Sequence[Path], *, root: Path = ROOT
) -> dict[str, object]:
    """Bind an exact file-name and byte inventory for recorded local evidence."""

    unique = tuple(sorted(set(paths)))
    if not unique or len(unique) != len(paths):
        fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
    rows: list[dict[str, object]] = []
    for relative in unique:
        if relative.is_absolute() or ".." in relative.parts:
            fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
        path = root / relative
        try:
            path.lstat()
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
        if path.is_symlink() or not path.is_file():
            fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                fail("RAOS_V2_LOCAL_TEST_INVENTORY_INVALID")
        rows.append(
            {
                "path": relative.as_posix(),
                "bytes": len(payload),
                "sha256": sha256(payload),
            }
        )
    path_names = [str(row["path"]) for row in rows]
    return {
        "schema": "RAOS_V2_FILE_INVENTORY_BINDING_V1",
        "file_count": len(rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "path_set_sha256": sha256(canonical_json_bytes(path_names)),
        "content_inventory_sha256": sha256(canonical_json_bytes(rows)),
    }


def local_test_evidence_bindings(*, root: Path = ROOT) -> dict[str, object]:
    test_paths = tuple(
        sorted(
            path.relative_to(root)
            for pattern in ("*.py", "*.mjs")
            for path in (root / "tests/raos_v2").glob(pattern)
            if path.is_file() and not path.is_symlink()
        )
    )
    source_paths = (
        *_inventory_files(root, LOCAL_TEST_SOURCE_ROOTS),
        *LOCAL_TEST_SOURCE_FILES,
    )
    machine_contract_paths = (
        *_inventory_files(root, LOCAL_TEST_MACHINE_CONTRACT_ROOTS),
        *LOCAL_TEST_MACHINE_CONTRACT_FILES,
    )
    return {
        "test_inventory": content_inventory_binding(test_paths, root=root),
        "implementation_source_inventory": content_inventory_binding(
            source_paths, root=root
        ),
        "machine_contract_inventory": content_inventory_binding(
            machine_contract_paths, root=root
        ),
    }


def _git_head_and_ancestry(
    executed_head: str, *, root: Path
) -> tuple[str, bool]:
    if not re.fullmatch(r"[0-9a-f]{40}", executed_head):
        return "", False
    try:
        current = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", executed_head, "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
    except OSError:
        return "", False
    return current, ancestor == 0


def _pytest_summary(raw_text: str) -> tuple[int, int, int]:
    passed_matches = re.findall(r"(?<!\d)(\d+) passed\b", raw_text)
    failed_matches = re.findall(r"(?<!\d)(\d+) failed\b", raw_text)
    skipped_matches = re.findall(r"(?<!\d)(\d+) skipped\b", raw_text)
    if not passed_matches:
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_SUMMARY_INVALID")
    return (
        int(passed_matches[-1]),
        int(failed_matches[-1]) if failed_matches else 0,
        int(skipped_matches[-1]) if skipped_matches else 0,
    )


def _read_local_evidence_file(path: Path, *, root: Path) -> bytes:
    try:
        relative = path.relative_to(root)
    except ValueError:
        fail("RAOS_V2_LOCAL_EVIDENCE_PATH_INVALID")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError:
            fail("RAOS_V2_LOCAL_EVIDENCE_PATH_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            fail("RAOS_V2_LOCAL_EVIDENCE_PATH_INVALID")
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("RAOS_V2_LOCAL_EVIDENCE_PATH_INVALID")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not payload
        or len(payload) > MAX_RESPONSE_BYTES
    ):
        fail("RAOS_V2_LOCAL_EVIDENCE_PATH_INVALID")
    return payload


def verify_local_test_evidence(
    value: Mapping[str, object],
    *,
    root: Path = ROOT,
    require_raw: bool = False,
) -> dict[str, object]:
    """Recompute the local suite binding; never trust a PASSED label alone."""

    if (
        value.get("schema") != "RAOS_V2_RECORDED_LOCAL_TEST_EVIDENCE_V1"
        or value.get("status") not in {"NOT_EXECUTED", "PASSED_LOCAL"}
        or value.get("classification") != "LOCAL_ONLY"
        or value.get("external_actions") != "NOT_EXECUTED"
        or value.get("formal_ci") != "NOT_CLAIMED"
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    if value.get("status") == "NOT_EXECUTED":
        return {
            "effective_status": "NOT_EXECUTED",
            "binding_verification": "NOT_EXECUTED",
            "raw_verification": "NOT_EXECUTED",
        }
    if (
        value.get("version") != "2.0.0"
        or value.get("command") != LOCAL_TEST_COMMAND
        or value.get("command_contract") != LOCAL_TEST_COMMAND_CONTRACT
        or value.get("exit_code") != 0
        or not isinstance(value.get("passed"), int)
        or isinstance(value.get("passed"), bool)
        or int(value.get("passed", 0)) <= 0
        or value.get("failed") != 0
        or not isinstance(value.get("skipped"), int)
        or isinstance(value.get("skipped"), bool)
        or int(value.get("skipped", -1)) < 0
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    executed_at = value.get("executed_at_jst")
    executed_head = value.get("executed_head")
    if (
        not isinstance(executed_at, str)
        or not executed_at.endswith("+09:00")
        or not isinstance(executed_head, str)
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    try:
        instant = datetime.fromisoformat(executed_at)
    except ValueError:
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo"))
    if instant.tzinfo is None or instant.utcoffset() is None or instant > now_jst:
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    current_bindings = local_test_evidence_bindings(root=root)
    _current_head, head_is_ancestor = _git_head_and_ancestry(
        executed_head, root=root
    )
    binding_matches = (
        value.get("test_inventory") == current_bindings["test_inventory"]
        and value.get("implementation_source_inventory")
        == current_bindings["implementation_source_inventory"]
        and value.get("machine_contract_inventory")
        == current_bindings["machine_contract_inventory"]
        and head_is_ancestor
    )
    raw_binding = value.get("raw_output")
    if not isinstance(raw_binding, Mapping) or (
        raw_binding.get("local_path") != LOCAL_TEST_RAW_OUTPUT_PATH.as_posix()
        or not isinstance(raw_binding.get("bytes"), int)
        or isinstance(raw_binding.get("bytes"), bool)
        or int(raw_binding.get("bytes", 0)) <= 0
        or not isinstance(raw_binding.get("sha256"), str)
        or not HEX64.fullmatch(str(raw_binding.get("sha256")))
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    raw_path = root / LOCAL_TEST_RAW_OUTPUT_PATH
    raw_verification = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists() or raw_path.is_symlink():
        try:
            raw_payload = _read_local_evidence_file(raw_path, root=root)
            raw_text = raw_payload.decode("utf-8")
        except UnicodeError:
            fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_INVALID")
        if (
            len(raw_payload) != raw_binding.get("bytes")
            or sha256(raw_payload) != raw_binding.get("sha256")
        ):
            fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_DRIFT")
        passed, failed, skipped = _pytest_summary(raw_text)
        if (
            passed != value.get("passed")
            or failed != value.get("failed")
            or skipped != value.get("skipped")
        ):
            fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_SUMMARY_INVALID")
        raw_verification = "RAW_OUTPUT_VERIFIED_LOCAL"
    elif require_raw:
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_MISSING")
    return {
        "effective_status": (
            "PASSED_LOCAL" if binding_matches else "AWAITING_GATE_STALE_BINDING"
        ),
        "binding_verification": (
            "CURRENT_TREE_BOUND"
            if binding_matches
            else "STALE_IMPLEMENTATION_OR_TEST_INVENTORY"
        ),
        "raw_verification": raw_verification,
        "current_bindings": current_bindings,
    }


def _visual_capture_subset(rows: Sequence[Mapping[str, object]]) -> bytes:
    subset: list[dict[str, object]] = []
    for row in rows:
        if any(key not in row for key in VISUAL_CAPTURE_CANONICAL_KEYS):
            fail("RAOS_V2_VISUAL_CAPTURE_ROW_INVALID")
        subset.append({key: row[key] for key in VISUAL_CAPTURE_CANONICAL_KEYS})
    return compact_canonical_json_bytes(subset)


def verify_visual_review_evidence(
    value: Mapping[str, object],
    *,
    preview_digests: Mapping[str, str],
    route_classifications: Mapping[str, str],
    root: Path = ROOT,
    require_raw: bool = False,
) -> dict[str, object]:
    """Verify the independent review and its distinct pending capture layer."""

    expected_root_keys = {
        "schema",
        "version",
        "recorded_date_jst",
        "classification",
        "reviewer_class",
        "reviewed_at_jst",
        "review_scope",
        "capture_receipt",
        "aggregate_findings",
        "capture_hash_review",
        "reviews",
        "external_actions",
        "formal_ci",
        "ci_behavior",
    }
    if (
        set(value) != expected_root_keys
        or value.get("schema")
        != "RAOS_V2_RECORDED_VISUAL_REVIEW_EVIDENCE_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification")
        != "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
        or value.get("reviewer_class") != "CODEX_MANUAL_VISUAL_REVIEW"
        or value.get("external_actions") != "NOT_EXECUTED"
        or value.get("formal_ci") != "NOT_CLAIMED"
        or value.get("ci_behavior")
        != "VERIFY_COMMITTED_REVIEW_AND_PREVIEW_BINDINGS_WHEN_RAW_CAPTURE_IS_ABSENT"
    ):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    reviewed_at = value.get("reviewed_at_jst")
    if not isinstance(reviewed_at, str) or not reviewed_at.endswith("+09:00"):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    try:
        reviewed_instant = datetime.fromisoformat(reviewed_at)
    except ValueError:
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    if (
        reviewed_instant.tzinfo is None
        or reviewed_instant.utcoffset() is None
        or reviewed_instant > datetime.now(ZoneInfo("Asia/Tokyo"))
        or value.get("recorded_date_jst") != reviewed_instant.date().isoformat()
    ):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    scope = value.get("review_scope")
    aggregate = value.get("aggregate_findings")
    hash_review = value.get("capture_hash_review")
    capture_binding = value.get("capture_receipt")
    reviews = value.get("reviews")
    if (
        scope
        != {
            "routes": 9,
            "viewports": list(VISUAL_VIEWPORT_WIDTHS),
            "captures": 27,
        }
        or aggregate != {"critical": 0, "major": 0}
        or hash_review != {"verified": 27, "mismatches": []}
        or not isinstance(capture_binding, Mapping)
        or not isinstance(reviews, list)
        or len(reviews) != 27
        or set(preview_digests) != set(route_classifications)
        or len(preview_digests) != 9
    ):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    expected_capture_keys = {
        "local_path",
        "sha256",
        "bytes",
        "schema",
        "command_contract",
        "harness_path",
        "harness_sha256",
        "harness_bytes",
        "capture_rows_canonical_contract",
        "capture_rows_canonical_sha256",
        "capture_rows_canonical_bytes",
    }
    if (
        set(capture_binding) != expected_capture_keys
        or capture_binding.get("local_path") != VISUAL_RAW_RECEIPT_PATH.as_posix()
        or capture_binding.get("schema")
        != "RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1"
        or capture_binding.get("command_contract")
        != "PLAYWRIGHT_CLI_FULL_PAGE_CAPTURE_HASH_BINDING_V1"
        or capture_binding.get("harness_path") != VISUAL_HARNESS_PATH.as_posix()
        or capture_binding.get("capture_rows_canonical_contract")
        != VISUAL_CAPTURE_CANONICAL_CONTRACT
    ):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    for digest_key in (
        "sha256",
        "harness_sha256",
        "capture_rows_canonical_sha256",
    ):
        if not isinstance(capture_binding.get(digest_key), str) or not HEX64.fullmatch(
            str(capture_binding[digest_key])
        ):
            fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    for byte_key in ("bytes", "harness_bytes", "capture_rows_canonical_bytes"):
        amount = capture_binding.get(byte_key)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    try:
        harness_payload = _read_local_evidence_file(
            root / VISUAL_HARNESS_PATH, root=root
        )
    except ValidationFailure:
        fail("RAOS_V2_VISUAL_HARNESS_INVALID")
    if (
        len(harness_payload) != capture_binding.get("harness_bytes")
        or sha256(harness_payload) != capture_binding.get("harness_sha256")
    ):
        fail("RAOS_V2_VISUAL_HARNESS_DRIFT")

    expected_pairs = {
        (route, viewport)
        for route in preview_digests
        for viewport in VISUAL_VIEWPORT_WIDTHS
    }
    observed_pairs: set[tuple[str, str]] = set()
    normalized_raw_rows: list[dict[str, object]] = []
    expected_review_keys = {
        "route",
        "viewport",
        "classification",
        "preview_sha256",
        "screenshot_path",
        "screenshot_sha256",
        "screenshot_bytes",
        "width",
        "height",
        "critical_findings",
        "major_findings",
    }
    for item in reviews:
        if not isinstance(item, Mapping) or set(item) != expected_review_keys:
            fail("RAOS_V2_VISUAL_REVIEW_ROW_INVALID")
        route = item.get("route")
        viewport = item.get("viewport")
        pair = (str(route), str(viewport))
        screenshot_path = item.get("screenshot_path")
        if (
            not isinstance(route, str)
            or route not in preview_digests
            or not isinstance(viewport, str)
            or viewport not in VISUAL_VIEWPORT_WIDTHS
            or pair in observed_pairs
            or item.get("classification") != route_classifications.get(route)
            or item.get("preview_sha256") != preview_digests.get(route)
            or item.get("width") != VISUAL_VIEWPORT_WIDTHS[viewport]
            or not isinstance(item.get("height"), int)
            or isinstance(item.get("height"), bool)
            or not 1 <= int(item["height"]) <= 20_000
            or item.get("critical_findings") != 0
            or item.get("major_findings") != 0
            or not isinstance(item.get("screenshot_bytes"), int)
            or isinstance(item.get("screenshot_bytes"), bool)
            or int(item["screenshot_bytes"]) <= 0
            or not isinstance(item.get("screenshot_sha256"), str)
            or not HEX64.fullmatch(str(item["screenshot_sha256"]))
            or not isinstance(screenshot_path, str)
        ):
            fail("RAOS_V2_VISUAL_REVIEW_ROW_INVALID")
        screenshot_relative = PurePosixPath(screenshot_path)
        if (
            screenshot_relative.is_absolute()
            or ".." in screenshot_relative.parts
            or screenshot_relative.suffix != ".png"
            or screenshot_relative.parts[:4]
            != ("output", "playwright", "raos-v2-visual-review", "cli-captures")
        ):
            fail("RAOS_V2_VISUAL_SCREENSHOT_PATH_INVALID")
        observed_pairs.add(pair)
        normalized_raw_rows.append(
            {
                "route": route,
                "viewport": viewport,
                "classification": item.get("classification"),
                "previewSha256": item.get("preview_sha256"),
                "screenshotSha256": item.get("screenshot_sha256"),
                "bytes": item.get("screenshot_bytes"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
    if observed_pairs != expected_pairs:
        fail("RAOS_V2_VISUAL_REVIEW_SET_INVALID")
    canonical_subset = _visual_capture_subset(normalized_raw_rows)
    if (
        len(canonical_subset) != capture_binding.get("capture_rows_canonical_bytes")
        or sha256(canonical_subset)
        != capture_binding.get("capture_rows_canonical_sha256")
    ):
        fail("RAOS_V2_VISUAL_CAPTURE_SUBSET_DRIFT")

    raw_path = root / VISUAL_RAW_RECEIPT_PATH
    raw_status = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists():
        raw_payload = _read_local_evidence_file(raw_path, root=root)
        if (
            len(raw_payload) != capture_binding.get("bytes")
            or sha256(raw_payload) != capture_binding.get("sha256")
        ):
            fail("RAOS_V2_VISUAL_RAW_RECEIPT_DRIFT")
        raw = load_json_strict(raw_payload)
        if not isinstance(raw, Mapping):
            fail("RAOS_V2_VISUAL_RAW_RECEIPT_INVALID")
        raw_captures = raw.get("captures")
        if (
            raw.get("schema") != "RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1"
            or raw.get("classification") != "PENDING_LOCAL_VISUAL_REVIEW"
            or raw.get("reviewBoundary")
            != "MANUAL_REVIEW_REQUIRED_SEPARATE_RECORD"
            or raw.get("commandContract") != capture_binding.get("command_contract")
            or raw.get("harnessPath") != capture_binding.get("harness_path")
            or raw.get("harnessSha256") != capture_binding.get("harness_sha256")
            or raw.get("harnessBytes") != capture_binding.get("harness_bytes")
            or raw.get("captureCount") != 27
            or raw.get("routes") != 9
            or raw.get("viewports") != list(VISUAL_VIEWPORT_WIDTHS)
            or raw.get("criticalFindings") is not None
            or raw.get("majorFindings") is not None
            or raw.get("externalActions") != "NOT_EXECUTED"
            or "reviewerClass" in raw
            or "reviewedAt" in raw
            or not isinstance(raw_captures, list)
            or len(raw_captures) != 27
        ):
            fail("RAOS_V2_VISUAL_RAW_RECEIPT_INVALID")
        if _visual_capture_subset(raw_captures) != canonical_subset:
            fail("RAOS_V2_VISUAL_RAW_CAPTURE_SET_DRIFT")
        raw_by_pair = {
            (str(row.get("route")), str(row.get("viewport"))): row
            for row in raw_captures
            if isinstance(row, Mapping)
        }
        if set(raw_by_pair) != expected_pairs:
            fail("RAOS_V2_VISUAL_RAW_CAPTURE_SET_DRIFT")
        for review in reviews:
            assert isinstance(review, Mapping)
            pair = (str(review["route"]), str(review["viewport"]))
            raw_row = raw_by_pair[pair]
            if (
                raw_row.get("screenshot") != review.get("screenshot_path")
                or raw_row.get("reviewStatus")
                != "PENDING_SEPARATE_MANUAL_REVIEW"
                or raw_row.get("criticalFindings") is not None
                or raw_row.get("majorFindings") is not None
            ):
                fail("RAOS_V2_VISUAL_RAW_CAPTURE_SET_DRIFT")
            image_path = root / str(review["screenshot_path"])
            image_payload = _read_local_evidence_file(image_path, root=root)
            if (
                len(image_payload) != review.get("screenshot_bytes")
                or sha256(image_payload) != review.get("screenshot_sha256")
            ):
                fail("RAOS_V2_VISUAL_SCREENSHOT_DRIFT")
        raw_status = "RAW_CAPTURE_AND_27_PNGS_VERIFIED_LOCAL"
    elif require_raw:
        fail("RAOS_V2_VISUAL_RAW_RECEIPT_MISSING")
    return {
        "effective_status": "PASSED_LOCAL_MANUAL_VISUAL_REVIEW",
        "review_binding": "CURRENT_PREVIEW_AND_CAPTURE_SET_BOUND",
        "raw_verification": raw_status,
        "captures": 27,
        "critical_findings": 0,
        "major_findings": 0,
    }


def record_local_test_evidence(*, root: Path = ROOT) -> dict[str, object]:
    """Sanitize an ignored pytest tee into a tree-bound local-only receipt."""

    temporary_path = root / LOCAL_TEST_RAW_OUTPUT_TEMP_PATH
    try:
        raw_payload = _read_local_evidence_file(temporary_path, root=root)
        raw_text = raw_payload.decode("utf-8")
    except (UnicodeError, ValidationFailure):
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_MISSING")
    passed, failed, skipped = _pytest_summary(raw_text)
    if failed != 0:
        fail("RAOS_V2_LOCAL_TEST_SUITE_FAILED")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    bindings = local_test_evidence_bindings(root=root)
    document: dict[str, object] = {
        "schema": "RAOS_V2_RECORDED_LOCAL_TEST_EVIDENCE_V1",
        "version": "2.0.0",
        "recorded_date_jst": now.date().isoformat(),
        "executed_at_jst": now.isoformat(),
        "executed_head": head,
        "command": LOCAL_TEST_COMMAND,
        "command_contract": LOCAL_TEST_COMMAND_CONTRACT,
        "status": "PASSED_LOCAL",
        "exit_code": 0,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        **bindings,
        "raw_output": {
            "local_path": LOCAL_TEST_RAW_OUTPUT_PATH.as_posix(),
            "sha256": sha256(raw_payload),
            "bytes": len(raw_payload),
        },
        "classification": "LOCAL_ONLY",
        "formal_ci": "NOT_CLAIMED",
        "external_actions": "NOT_EXECUTED",
    }
    raw_path = root / LOCAL_TEST_RAW_OUTPUT_PATH
    for candidate in (temporary_path, raw_path):
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            try:
                metadata = current.lstat()
            except OSError:
                fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
    try:
        final_metadata = raw_path.lstat()
    except FileNotFoundError:
        final_metadata = None
    except OSError:
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
    if final_metadata is not None and (
        stat.S_ISLNK(final_metadata.st_mode)
        or not stat.S_ISREG(final_metadata.st_mode)
    ):
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
    try:
        os.replace(temporary_path, raw_path)
    except OSError:
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PROMOTION_FAILED")
    verification = verify_local_test_evidence(
        document, root=root, require_raw=True
    )
    if verification.get("effective_status") != "PASSED_LOCAL":
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_STALE")
    return document


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader which rejects duplicate mapping keys."""


def _construct_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate mapping key",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_yaml_strict(payload: bytes) -> Any:
    if not payload or len(payload) > MAX_RESPONSE_BYTES:
        fail("RAOS_V2_YAML_SIZE_INVALID")
    try:
        text = payload.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                fail("RAOS_V2_YAML_FEATURE_FORBIDDEN")
        return yaml.load(text, Loader=UniqueKeyLoader)
    except (UnicodeError, yaml.YAMLError):
        fail("RAOS_V2_YAML_INVALID")


def load_json_strict(payload: bytes) -> Any:
    if not payload or len(payload) > MAX_RESPONSE_BYTES:
        fail("RAOS_V2_JSON_SIZE_INVALID")

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                fail("RAOS_V2_JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    def reject_constant(_value: str) -> NoReturn:
        fail("RAOS_V2_JSON_NONFINITE_NUMBER")

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError):
        fail("RAOS_V2_JSON_INVALID")


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write only allowlisted recorded inputs without following links."""

    repository = ROOT.resolve()
    if path not in {RECORDED_INPUT, LOCAL_TEST_EVIDENCE_INPUT}:
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    target = path
    try:
        relative = target.relative_to(ROOT)
    except ValueError:
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    if relative.parts[:3] != ("changes", "raos-v2", "recorded-inputs"):
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    current = ROOT
    for part in relative.parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    try:
        target_metadata = target.lstat()
    except FileNotFoundError:
        target_metadata = None
    except OSError:
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    if target_metadata is not None and (
        stat.S_ISLNK(target_metadata.st_mode)
        or not stat.S_ISREG(target_metadata.st_mode)
    ):
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.resolve() != (repository / relative.parent).resolve():
        fail("RAOS_V2_CAPTURE_OUTPUT_UNSAFE")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".next", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def validate_public_url(url: str) -> str:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        fail("RAOS_V2_CAPTURE_URL_REJECTED")
    if (
        parts.scheme != "https"
        or parts.netloc != "kurashinoshirube.com"
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/")
        or "//" in parts.path
        or "%" in parts.path
    ):
        fail("RAOS_V2_CAPTURE_URL_REJECTED")
    raw_segments = parts.path.split("/")
    if any(value in {".", ".."} for value in raw_segments):
        fail("RAOS_V2_CAPTURE_URL_REJECTED")
    segments = {value.lower() for value in raw_segments if value}
    if segments & FORBIDDEN_SEGMENTS:
        fail("RAOS_V2_CAPTURE_PRIVATE_PATH_REJECTED")
    return parts.path


def validate_redirect_rules(rows: Sequence[Mapping[str, object]]) -> None:
    sources: set[str] = set()
    destinations: dict[str, str] = {}
    home_sources = 0
    for row in rows:
        source = row.get("source")
        destination = row.get("destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            fail("RAOS_V2_REDIRECT_INVALID")
        if source in sources or source == destination:
            fail("RAOS_V2_REDIRECT_LOOP_OR_DUPLICATE")
        sources.add(source)
        destinations[source] = destination
        if destination == "/":
            home_sources += 1
    if home_sources > 1:
        fail("RAOS_V2_REDIRECT_MANY_TO_HOME")
    for source, destination in destinations.items():
        if destination in destinations:
            if destinations[destination] == source:
                fail("RAOS_V2_REDIRECT_LOOP_OR_DUPLICATE")
            fail("RAOS_V2_REDIRECT_CHAIN_TOO_LONG")


RouteSnapshot = tuple[str, int, str | None, str]


def _route_snapshot_bytes(snapshot: RouteSnapshot) -> bytes:
    route, status, canonical, robots = snapshot
    if (
        not isinstance(route, str)
        or not isinstance(status, int)
        or isinstance(status, bool)
        or not 100 <= status <= 599
        or (canonical is not None and not isinstance(canonical, str))
        or not isinstance(robots, str)
        or not robots
    ):
        fail("RAOS_V2_ROUTE_SNAPSHOT_INVALID")
    validate_public_url(f"{ORIGIN}{route}")
    if canonical is not None:
        validate_public_url(canonical)
    return (
        json.dumps(
            {
                "canonical": canonical,
                "robots": robots,
                "route": route,
                "status": status,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def apply_route_projection(
    baseline: RouteSnapshot, candidate: RouteSnapshot
) -> RouteSnapshot:
    _route_snapshot_bytes(baseline)
    _route_snapshot_bytes(candidate)
    if baseline[0] != candidate[0]:
        fail("RAOS_V2_ROUTE_PROJECTION_ROUTE_MISMATCH")
    return candidate


def restore_route_projection(
    current: RouteSnapshot,
    baseline: RouteSnapshot,
    *,
    expected_baseline_sha256: str,
) -> RouteSnapshot:
    _route_snapshot_bytes(current)
    baseline_payload = _route_snapshot_bytes(baseline)
    if not HEX64.fullmatch(expected_baseline_sha256):
        fail("RAOS_V2_ROLLBACK_BINDING_INVALID")
    if sha256(baseline_payload) != expected_baseline_sha256:
        fail("RAOS_V2_ROLLBACK_BASELINE_TAMPERED")
    if current[0] != baseline[0]:
        fail("RAOS_V2_ROLLBACK_ROUTE_MISMATCH")
    return baseline


def simulate_route_round_trip(
    baseline: RouteSnapshot, candidate: RouteSnapshot
) -> dict[str, object]:
    baseline_payload = _route_snapshot_bytes(baseline)
    binding = sha256(baseline_payload)
    applied = apply_route_projection(baseline, candidate)
    restored = restore_route_projection(
        applied,
        baseline,
        expected_baseline_sha256=binding,
    )
    if restored != baseline:
        fail("RAOS_V2_ROLLBACK_NOT_EXACT")
    return {
        "status": "PASSED_LOCAL",
        "baseline_sha256": binding,
        "candidate_sha256": sha256(_route_snapshot_bytes(applied)),
        "restored_sha256": sha256(_route_snapshot_bytes(restored)),
        "exact_tuple_restored": True,
        "external_action": "NOT_EXECUTED",
    }


def _package_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        payload = archive.read(f"{PACKAGE_ROOT}/package_manifest.json")
    except (KeyError, RuntimeError):
        fail("RAOS_V2_PACKAGE_MANIFEST_MISSING")
    manifest = load_json_strict(payload)
    if not isinstance(manifest, dict):
        fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
    return manifest


def validate_package(path: Path = PACKAGE_PATH) -> dict[str, object]:
    try:
        payload = path.read_bytes()
    except OSError:
        fail("RAOS_V2_PACKAGE_MISSING")
    if sha256(payload) != PACKAGE_SHA256:
        fail("RAOS_V2_PACKAGE_HASH_MISMATCH")
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile):
        fail("RAOS_V2_PACKAGE_ZIP_INVALID")
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) != 20 or len(names) != len(set(names)):
            fail("RAOS_V2_PACKAGE_ENTRY_COUNT_INVALID")
        for info in infos:
            safe = PurePosixPath(info.filename)
            if (
                safe.is_absolute()
                or not safe.parts
                or safe.parts[0] != PACKAGE_ROOT
                or any(part in {"", ".", ".."} for part in safe.parts)
                or info.is_dir()
                or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK
                or info.file_size > MAX_RESPONSE_BYTES
            ):
                fail("RAOS_V2_PACKAGE_ENTRY_UNSAFE")
        for name in names:
            relative = name.removeprefix(f"{PACKAGE_ROOT}/")
            item = archive.read(name)
            if relative == PROMPT_PATH:
                if sha256(item) != PROMPT_SHA256 or (SOURCE_ROOT / relative).exists():
                    fail("RAOS_V2_PACKAGE_PROMPT_RECEIPT_INVALID")
            else:
                try:
                    imported = (SOURCE_ROOT / relative).read_bytes()
                except OSError:
                    fail("RAOS_V2_IMPORTED_SOURCE_MISSING")
                if imported != item:
                    fail("RAOS_V2_IMPORTED_SOURCE_DRIFT")
        manifest = _package_manifest(archive)
        file_rows = manifest.get("files")
        if not isinstance(file_rows, list):
            fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
        expected: dict[str, tuple[str, int]] = {}
        for row in file_rows:
            if not isinstance(row, dict):
                fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
            relative = row.get("path")
            digest = row.get("sha256")
            size = row.get("size_bytes")
            if (
                not isinstance(relative, str)
                or not isinstance(digest, str)
                or not isinstance(size, int)
                or relative in expected
            ):
                fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
            expected[relative] = (digest, size)
        if expected.get(PROMPT_PATH) != (PROMPT_SHA256, 22093):
            fail("RAOS_V2_PACKAGE_PROMPT_RECEIPT_INVALID")
        for relative, (digest, size) in expected.items():
            try:
                item = archive.read(f"{PACKAGE_ROOT}/{relative}")
            except (KeyError, RuntimeError):
                fail("RAOS_V2_PACKAGE_ENTRY_MISSING")
            if len(item) != size or sha256(item) != digest:
                fail("RAOS_V2_PACKAGE_ENTRY_HASH_MISMATCH")
            imported = SOURCE_ROOT / relative
            if relative == PROMPT_PATH:
                if imported.exists():
                    fail("RAOS_V2_PROMPT_WAS_IMPORTED")
            elif imported.read_bytes() != item:
                fail("RAOS_V2_IMPORTED_SOURCE_DRIFT")
    return {
        "schema": "RAOS_V2_PACKAGE_VALIDATION_RECEIPT_V1",
        "status": "PASSED_LOCAL",
        "package_sha256": PACKAGE_SHA256,
        "entries": 20,
        "imported_non_prompt": 19,
        "prompt_executed": False,
    }


def _ids(rows: object, label: str) -> set[str]:
    if not isinstance(rows, list):
        fail("RAOS_V2_TRACEABILITY_INVALID")
    result: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            fail("RAOS_V2_TRACEABILITY_INVALID")
        identifier = row["id"]
        if identifier in result:
            fail(f"RAOS_V2_{label}_DUPLICATE")
        result.add(identifier)
    return result


def validate_source_traceability() -> None:
    trace = load_yaml_strict(
        (SOURCE_ROOT / "07_DECISION_TRACEABILITY.yaml").read_bytes()
    )
    if not isinstance(trace, dict):
        fail("RAOS_V2_TRACEABILITY_INVALID")
    decisions = _ids(trace.get("decisions"), "DECISION_ID")
    requirements = _ids(trace.get("requirements"), "REQUIREMENT_ID")
    backlog = _ids(trace.get("backlog"), "BACKLOG_ID")
    tests = _ids(trace.get("tests"), "TEST_ID")
    if (len(decisions), len(requirements), len(backlog), len(tests)) != (
        34,
        36,
        49,
        51,
    ):
        fail("RAOS_V2_TRACEABILITY_COUNT_INVALID")
    backlog_rows = trace["backlog"]
    assert isinstance(backlog_rows, list)
    graph: dict[str, set[str]] = {}
    for row in backlog_rows:
        assert isinstance(row, dict)
        identifier = str(row["id"])
        dependencies = {str(value) for value in row.get("depends_on", [])}
        requirement_ids = {str(value) for value in row.get("requirement_ids", [])}
        test_ids = {str(value) for value in row.get("test_ids", [])}
        if (
            not dependencies <= backlog
            or not requirement_ids <= requirements
            or not test_ids <= tests
        ):
            fail("RAOS_V2_TRACEABILITY_CROSS_REFERENCE_INVALID")
        graph[identifier] = dependencies
    pending = dict(graph)
    while pending:
        ready = {
            key for key, values in pending.items() if not (values & pending.keys())
        }
        if not ready:
            fail("RAOS_V2_BACKLOG_CYCLE")
        for key in ready:
            pending.pop(key)


def _load_generated(relative: str) -> object:
    path = ROOT / relative
    try:
        payload = path.read_bytes()
    except OSError:
        fail("RAOS_V2_GENERATED_OUTPUT_MISSING")
    return (
        load_json_strict(payload)
        if path.suffix == ".json"
        else load_yaml_strict(payload)
    )


def _read_required(relative: str) -> tuple[bytes, object]:
    try:
        payload = (ROOT / relative).read_bytes()
    except OSError:
        fail("RAOS_V2_GENERATED_OUTPUT_MISSING")
    value = (
        load_json_strict(payload)
        if Path(relative).suffix == ".json"
        else load_yaml_strict(payload)
    )
    return payload, value


def _mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        fail(code)
    return value


def _rows(value: object, code: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        fail(code)
    return value  # type: ignore[return-value]


def _exact_file_set_sha256(paths: Sequence[str]) -> str:
    rows: list[dict[str, object]] = []
    for relative in paths:
        try:
            payload = (ROOT / relative).read_bytes()
        except OSError:
            fail("RAOS_V2_PUBLICATION_INPUT_MISSING")
        rows.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256(payload)}
        )
    return sha256(canonical_json_bytes({"files": rows}))


def _semantic_digest(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload)


def _validate_contract_instances() -> dict[str, object]:
    schema_root = ROOT / "contracts/raos-v2/v1"
    schema_paths = sorted(schema_root.glob("*.schema.json"))
    if len(schema_paths) != 10:
        fail("RAOS_V2_SCHEMA_COUNT_INVALID")
    schemas: dict[str, dict[str, object]] = {}
    registry = Registry()
    for path in schema_paths:
        document = _mapping(load_json_strict(path.read_bytes()), "RAOS_V2_SCHEMA_INVALID")
        try:
            Draft202012Validator.check_schema(document)
            resource = Resource.from_contents(document)
            identifier = document.get("$id")
            if not isinstance(identifier, str):
                fail("RAOS_V2_SCHEMA_INVALID")
            registry = registry.with_resource(identifier, resource)
        except Exception as exc:
            if isinstance(exc, ValidationFailure):
                raise
            fail("RAOS_V2_SCHEMA_INVALID")
        if document.get("additionalProperties") is not False:
            fail("RAOS_V2_SCHEMA_INVALID")
        schemas[path.stem.removesuffix(".schema")] = document

    def validate(name: str, value: object) -> None:
        try:
            errors = list(
                Draft202012Validator(
                    schemas[name], registry=registry, format_checker=FormatChecker()
                ).iter_errors(value)
            )
        except Exception:
            fail("RAOS_V2_SCHEMA_INSTANCE_INVALID")
        if errors:
            fail("RAOS_V2_SCHEMA_INSTANCE_INVALID")

    _source_payload, source_document = _read_required(
        "changes/raos-v2/phase-2/sources/source-registry.v2.yaml"
    )
    source_rows = _rows(
        _mapping(source_document, "RAOS_V2_SOURCE_REGISTRY_INVALID").get("sources"),
        "RAOS_V2_SOURCE_REGISTRY_INVALID",
    )
    for row in source_rows:
        validate("source-record", row)
    sources = {str(row["source_id"]): row for row in source_rows}
    if len(sources) != len(source_rows):
        fail("RAOS_V2_SOURCE_REGISTRY_INVALID")

    claim_payload, claim_document = _read_required(
        "changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"
    )
    claim_rows = _rows(
        _mapping(claim_document, "RAOS_V2_CLAIM_LEDGER_INVALID").get("claims"),
        "RAOS_V2_CLAIM_LEDGER_INVALID",
    )
    if len(claim_rows) != 32:
        fail("RAOS_V2_CLAIM_LEDGER_INVALID")
    claims = {str(row["claim_id"]): row for row in claim_rows}
    if len(claims) != len(claim_rows):
        fail("RAOS_V2_CLAIM_LEDGER_INVALID")
    for row in claim_rows:
        validate("claim", row)
        claim_type = row.get("claim_type")
        source_ids = row.get("source_ids")
        logic_inputs = row.get("logic_inputs")
        if not isinstance(source_ids, list) or not isinstance(logic_inputs, list):
            fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")
        if claim_type == "UNKNOWN":
            if source_ids or row.get("value") is not None or row.get("status") != "BLOCKED":
                fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")
        else:
            if not source_ids or any(source_id not in sources for source_id in source_ids):
                fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")
            if any(
                not str(sources[str(source_id)].get("source_class", "")).endswith(
                    "_PRIMARY"
                )
                for source_id in source_ids
            ):
                fail("RAOS_V2_CLAIM_SOURCE_INELIGIBLE")
        if claim_type == "D_EDITORIAL_JUDGEMENT" and any(
            not isinstance(item, dict)
            or item.get("value_ref") not in claims
            for item in logic_inputs
        ):
            fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")

    _product_payload, product_document = _read_required(
        "changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json"
    )
    product_rows = _rows(
        _mapping(product_document, "RAOS_V2_PRODUCT_DATA_INVALID").get("products"),
        "RAOS_V2_PRODUCT_DATA_INVALID",
    )
    products = {str(row["product_id"]): row for row in product_rows}
    if len(products) != 3:
        fail("RAOS_V2_PRODUCT_DATA_INVALID")
    for row in product_rows:
        validate("product-model", row)
        for variant in _rows(row.get("variants"), "RAOS_V2_PRODUCT_DATA_INVALID"):
            validate("product-variant", variant)
        official_ids = row.get("official_source_ids")
        if not isinstance(official_ids, list) or any(
            source_id not in sources for source_id in official_ids
        ):
            fail("RAOS_V2_PRODUCT_SOURCE_BINDING_INVALID")
        if any(
            str(row.get("model_name"))
            not in str(sources[str(source_id)].get("title", ""))
            for source_id in official_ids
        ):
            fail("RAOS_V2_PRODUCT_SOURCE_BINDING_INVALID")

    _offer_payload, offer_document = _read_required(
        "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
    )
    offer_rows = _rows(
        _mapping(offer_document, "RAOS_V2_OFFER_FIXTURE_INVALID").get("offers"),
        "RAOS_V2_OFFER_FIXTURE_INVALID",
    )
    for envelope in offer_rows:
        observation = envelope.get("offer_observation")
        validate("offer-observation", observation)
        if not isinstance(observation, dict) or observation.get("product_id") not in products:
            fail("RAOS_V2_OFFER_PRODUCT_BINDING_INVALID")

    _airline_payload, airline_document = _read_required(
        "changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"
    )
    airline = _mapping(airline_document, "RAOS_V2_AIRLINE_FIXTURE_INVALID")
    capture_rows = _rows(
        airline.get("source_captures"), "RAOS_V2_AIRLINE_FIXTURE_INVALID"
    )
    captures = {str(row["source_id"]): row for row in capture_rows}
    rule_rows = _rows(airline.get("rule_sets"), "RAOS_V2_AIRLINE_FIXTURE_INVALID")
    if len(rule_rows) != 6:
        fail("RAOS_V2_AIRLINE_FIXTURE_INVALID")
    for row in rule_rows:
        validate("airline-rule-set", row)
        source_id = row.get("source_id")
        source = sources.get(str(source_id))
        capture = captures.get(str(source_id))
        if not isinstance(source, dict) or not isinstance(capture, dict) or any(
            (
                row.get("source_content_sha256") != source.get("content_sha256"),
                row.get("source_content_sha256") != capture.get("body_sha256"),
                row.get("source_next_review_at") != source.get("next_review_at"),
                row.get("checked_at") != source.get("checked_at"),
                capture.get("status") != source.get("status"),
            )
        ):
            fail("RAOS_V2_AIRLINE_SOURCE_BINDING_INVALID")

    _article_payload, article_document = _read_required(
        "changes/raos-v2/phase-2/content/article-definitions.v2.yaml"
    )
    article_rows = _rows(
        _mapping(article_document, "RAOS_V2_ARTICLE_LEDGER_INVALID").get("articles"),
        "RAOS_V2_ARTICLE_LEDGER_INVALID",
    )
    _editorial_payload, editorial_document = _read_required(
        "changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"
    )
    editorial_rows = _rows(
        _mapping(editorial_document, "RAOS_V2_EDITORIAL_LEDGER_INVALID").get(
            "decisions"
        ),
        "RAOS_V2_EDITORIAL_LEDGER_INVALID",
    )
    editorial = {str(row["decision_id"]): row for row in editorial_rows}
    for row in editorial_rows:
        validate("editorial-decision", row)
        if any(
            not isinstance(item, dict) or item.get("value_ref") not in claims
            for item in _rows(row.get("inputs"), "RAOS_V2_EDITORIAL_LEDGER_INVALID")
        ):
            fail("RAOS_V2_EDITORIAL_CLAIM_BINDING_INVALID")
    articles = {str(row["article_id"]): row for row in article_rows}
    if set(articles) != {"A02", "A03", "A05"}:
        fail("RAOS_V2_ARTICLE_LEDGER_INVALID")
    for row in article_rows:
        validate("article-definition", row)
        if any(value not in claims for value in row.get("claim_ids", [])) or any(
            value not in editorial for value in row.get("editorial_decisions", [])
        ):
            fail("RAOS_V2_ARTICLE_CROSS_REFERENCE_INVALID")
    if set(articles["A05"].get("claim_ids", [])) != {
        claim_id for claim_id in claims if claim_id.startswith("CLM-A05-")
    }:
        fail("RAOS_V2_ARTICLE_CLAIM_CLOSURE_INVALID")

    _candidate_payload, candidate_value = _read_required(
        "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
    )
    candidate = _mapping(candidate_value, "RAOS_V2_PUBLICATION_CANDIDATE_INVALID")
    validate("publication-package", candidate)
    _seal_payload, seal_value = _read_required(
        "changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"
    )
    seal = _mapping(seal_value, "RAOS_V2_SYNTHETIC_SEAL_INVALID")
    package = _mapping(seal.get("package"), "RAOS_V2_SYNTHETIC_SEAL_INVALID")
    validate("publication-package", package)

    return {
        "schemas": schemas,
        "sources": sources,
        "claims": claims,
        "products": products,
        "articles": articles,
        "editorial": editorial,
        "candidate": candidate,
        "synthetic_seal": seal,
        "claim_payload": claim_payload,
    }


def _validate_publication_closure(values: Mapping[str, object]) -> None:
    candidate = _mapping(values.get("candidate"), "RAOS_V2_PUBLICATION_CANDIDATE_INVALID")
    claims = _mapping(values.get("claims"), "RAOS_V2_CLAIM_LEDGER_INVALID")
    sources = _mapping(values.get("sources"), "RAOS_V2_SOURCE_REGISTRY_INVALID")
    articles = _mapping(values.get("articles"), "RAOS_V2_ARTICLE_LEDGER_INVALID")
    input_hashes = _mapping(
        candidate.get("input_hashes"), "RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID"
    )
    expected_hashes = {
        "article": _exact_file_set_sha256(
            (
                "changes/raos-v2/phase-2/content/article-definitions.v2.yaml",
                "changes/raos-v2/phase-2/content/carry-on-comparison.v2.yaml",
            )
        ),
        "claims": sha256(
            (ROOT / "changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml").read_bytes()
        ),
        "sources": sha256(
            (ROOT / "changes/raos-v2/phase-2/sources/source-registry.v2.yaml").read_bytes()
        ),
        "render": sha256(
            (
                ROOT
                / "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
            ).read_bytes()
        ),
        "migration": sha256(
            (
                ROOT
                / "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
            ).read_bytes()
        ),
        "editorial": sha256(
            (
                ROOT
                / "changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"
            ).read_bytes()
        ),
        "products": sha256(
            (ROOT / "changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json").read_bytes()
        ),
        "review": sha256(
            (ROOT / "changes/raos-v2/phase-2/reviews/review-packet.v2.yaml").read_bytes()
        ),
        "render_model": sha256(
            (
                ROOT
                / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
            ).read_bytes()
        ),
    }
    migration = _mapping(
        candidate.get("migration_manifest"),
        "RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID",
    )
    if (
        input_hashes != expected_hashes
        or candidate.get("render_hash") != expected_hashes["render"]
        or candidate.get("source_snapshot_hash") != expected_hashes["sources"]
        or migration.get("sha256") != expected_hashes["migration"]
        or candidate.get("article_id") != "A05"
        or candidate.get("target_route") != articles["A05"].get("route")
    ):
        fail("RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID")
    migration_document = _mapping(
        _load_generated(
            "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
        ),
        "RAOS_V2_MIGRATION_MANIFEST_INVALID",
    )
    rollback = _mapping(
        migration_document.get("rollback"), "RAOS_V2_MIGRATION_MANIFEST_INVALID"
    )
    restore_steps = _rows(
        rollback.get("ordered_restore_steps"),
        "RAOS_V2_MIGRATION_MANIFEST_INVALID",
    )
    expected_actions = [
        "VERIFY_PRECONDITIONS_AND_EXPORT_RECEIPT",
        "RESTORE_PRIOR_CONTENT_METADATA_THEME_AND_URL",
        "PUBLIC_READ_ONLY_VERIFY_STATUS_CANONICAL_ROBOTS_AND_BODY",
    ]
    if (
        rollback.get("plan_scope")
        != "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION"
        or [row.get("sequence") for row in restore_steps] != [1, 2, 3]
        or [row.get("action") for row in restore_steps] != expected_actions
        or any(
            row.get("production_status") != "NOT_EXECUTED"
            or not isinstance(row.get("requires"), list)
            or not row.get("requires")
            for row in restore_steps
        )
    ):
        fail("RAOS_V2_MIGRATION_MANIFEST_INVALID")

    created_raw = candidate.get("created_at")
    evidence_rows = candidate.get("claim_evidence")
    if not isinstance(created_raw, str) or not isinstance(evidence_rows, list):
        fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
    try:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError:
        fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
    expected_evidence: list[dict[str, object]] = []
    for claim_id in articles["A05"].get("claim_ids", []):
        claim = _mapping(claims.get(str(claim_id)), "RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
        if claim.get("claim_type") == "UNKNOWN":
            freshness = "UNKNOWN"
        else:
            resolved = [
                _mapping(sources.get(str(source_id)), "RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
                for source_id in claim.get("source_ids", [])
            ]
            if not resolved or any(
                source.get("status") not in {"FRESH", "DUE"} for source in resolved
            ):
                fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
            try:
                checked = max(
                    datetime.fromisoformat(str(source["checked_at"]).replace("Z", "+00:00"))
                    for source in resolved
                )
                next_review = min(
                    datetime.fromisoformat(
                        str(source["next_review_at"]).replace("Z", "+00:00")
                    )
                    for source in resolved
                )
            except (KeyError, ValueError):
                fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
            if (
                claim.get("checked_at") != checked.isoformat()
                or claim.get("next_review_at") != next_review.isoformat()
                or created_at > next_review
            ):
                fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
            freshness = (
                "DUE"
                if created_at == next_review
                or any(source.get("status") == "DUE" for source in resolved)
                else "FRESH"
            )
        expected_evidence.append(
            {
                "claim_id": claim_id,
                "risk_class": claim.get("risk_class"),
                "freshness": freshness,
            }
        )
    if evidence_rows != sorted(expected_evidence, key=lambda row: str(row["claim_id"])):
        fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")

    seal = _mapping(values.get("synthetic_seal"), "RAOS_V2_SYNTHETIC_SEAL_INVALID")
    package = _mapping(seal.get("package"), "RAOS_V2_SYNTHETIC_SEAL_INVALID")
    synthetic_hashes = _mapping(
        package.get("input_hashes"), "RAOS_V2_SYNTHETIC_SEAL_INVALID"
    )
    synthetic_migration = _mapping(
        package.get("migration_manifest"), "RAOS_V2_SYNTHETIC_SEAL_INVALID"
    )
    semantic_migration = {
        key: synthetic_migration.get(key)
        for key in ("previous", "next", "wordpress_intent")
    }
    if synthetic_migration.get("sha256") != sha256(
        canonical_json_bytes(semantic_migration)
    ) or synthetic_hashes.get("migration") != synthetic_migration.get("sha256"):
        fail("RAOS_V2_SYNTHETIC_MIGRATION_BINDING_INVALID")
    semantic_payload = {
        key: package.get(key)
        for key in (
            "package_id",
            "target_origin",
            "target_route",
            "article_id",
            "input_hashes",
            "render_hash",
            "source_snapshot_hash",
            "claim_evidence",
            "review_binding",
            "migration_manifest",
            "created_at",
            "content_class",
            "state",
        )
    }
    semantic_payload["synthetic"] = True
    digest = _semantic_digest(semantic_payload)
    if (
        package.get("package_digest") != digest
        or seal.get("package_digest") != digest
        or seal.get("digest_verified") is not True
    ):
        fail("RAOS_V2_SYNTHETIC_SEAL_INVALID")
    wordpress = _mapping(
        seal.get("wordpress_dry_run"), "RAOS_V2_WORDPRESS_RECEIPT_INVALID"
    )
    after = _mapping(wordpress.get("after"), "RAOS_V2_WORDPRESS_RECEIPT_INVALID")
    target = _mapping(wordpress.get("target"), "RAOS_V2_WORDPRESS_RECEIPT_INVALID")
    expected_idempotency = _semantic_digest(
        {
            "target": target,
            "intent": wordpress.get("intent"),
            "after": after,
            "package_digest": digest,
        }
    )
    if (
        wordpress.get("mode") != "DISABLED_DRY_RUN"
        or wordpress.get("status") != "DRY_RUN"
        or wordpress.get("external_status") != "NOT_EXECUTED"
        or wordpress.get("request_count") != 0
        or wordpress.get("external_action_count") != 0
        or wordpress.get("package_digest") != digest
        or wordpress.get("idempotency_key") != expected_idempotency
        or target
        != {"origin": package.get("target_origin"), "route": package.get("target_route")}
        or after.get("render_hash") != package.get("render_hash")
    ):
        fail("RAOS_V2_WORDPRESS_RECEIPT_INVALID")


def _validate_visual_and_browser_evidence() -> dict[str, object]:
    _visual_payload, visual_value = _read_required(
        "changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json"
    )
    visual = _mapping(visual_value, "RAOS_V2_VISUAL_EVIDENCE_INVALID")
    screenshots = _rows(
        visual.get("screenshots"), "RAOS_V2_VISUAL_EVIDENCE_INVALID"
    )
    expected_paths = {
        "/",
        "/carry-on-suitcase-comparison/",
        "/portable-power-station-guide/",
        "/anker-solix-c300-c800-c1000-differences/",
    }
    expected_viewports = {"390x844", "768x1024", "1440x900"}
    observed_pairs: set[tuple[object, object]] = set()
    for row in screenshots:
        pair = (row.get("path"), row.get("viewport"))
        if (
            row.get("path") not in expected_paths
            or row.get("viewport") not in expected_viewports
            or not isinstance(row.get("bytes"), int)
            or isinstance(row.get("bytes"), bool)
            or int(row["bytes"]) <= 0
            or not isinstance(row.get("sha256"), str)
            or not HEX64.fullmatch(str(row["sha256"]))
            or pair in observed_pairs
        ):
            fail("RAOS_V2_VISUAL_EVIDENCE_INVALID")
        observed_pairs.add(pair)
    if observed_pairs != {
        (path, viewport)
        for path in expected_paths
        for viewport in expected_viewports
    }:
        fail("RAOS_V2_VISUAL_EVIDENCE_INVALID")
    inventory = _mapping(
        _load_generated("changes/raos-v2/phase-0/public-url-inventory.yaml"),
        "RAOS_V2_PUBLIC_URL_INVENTORY_INVALID",
    )
    if inventory.get("visual_baseline") != screenshots:
        fail("RAOS_V2_VISUAL_EVIDENCE_DRIFT")

    _browser_payload, browser_value = _read_required(
        "changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"
    )
    browser = _mapping(browser_value, "RAOS_V2_BROWSER_EVIDENCE_INVALID")
    raw_binding = _mapping(
        browser.get("raw_receipt"), "RAOS_V2_BROWSER_EVIDENCE_INVALID"
    )
    assertions = _mapping(
        browser.get("assertions"), "RAOS_V2_BROWSER_EVIDENCE_INVALID"
    )
    preview_digests = _mapping(
        browser.get("preview_digests"), "RAOS_V2_BROWSER_EVIDENCE_INVALID"
    )
    harness_path = raw_binding.get("harness_path")
    if harness_path != "tests/raos_v2/browser-validation.mjs":
        fail("RAOS_V2_BROWSER_EVIDENCE_INVALID")
    try:
        harness_payload = (ROOT / str(harness_path)).read_bytes()
    except OSError:
        fail("RAOS_V2_BROWSER_EVIDENCE_INVALID")
    if (
        raw_binding.get("harness_bytes") != len(harness_payload)
        or raw_binding.get("harness_sha256") != sha256(harness_payload)
        or raw_binding.get("exit_status") != 0
        or raw_binding.get("command_contract")
        != "NODE24_LOCAL_CDP_AXE_WITH_ABSOLUTE_BROWSER_AND_OUTPUT_PLAYWRIGHT_RECEIPT_V1"
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INVALID")
    preview_paths = {
        "/": "changes/raos-v2/phase-2/preview/index.html",
        "/carry-on/": "changes/raos-v2/phase-2/preview/carry-on/index.html",
        "/tools/carry-on-size-checker/": "changes/raos-v2/phase-2/preview/tools/carry-on-size-checker/index.html",
        "/guides/carry-on-baggage-rules/": "changes/raos-v2/phase-2/preview/guides/carry-on-baggage-rules/index.html",
        "/guides/low-cost-carrier-7kg-packing/": "changes/raos-v2/phase-2/preview/guides/low-cost-carrier-7kg-packing/index.html",
        "/carry-on-suitcase-comparison/": "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html",
        "/guides/carry-on-bag-measurement/": "changes/raos-v2/phase-2/preview/guides/carry-on-bag-measurement/index.html",
        "/policy/how-we-compare-carry-on-products/": "changes/raos-v2/phase-2/preview/policy/how-we-compare-carry-on-products/index.html",
        "/differences/ace-cresta-vs-difference-vs-maxpass4/": "changes/raos-v2/phase-2/preview/differences/ace-cresta-vs-difference-vs-maxpass4/index.html",
    }
    if set(preview_digests) != set(preview_paths):
        fail("RAOS_V2_BROWSER_PREVIEW_BINDING_INVALID")
    for route, relative in preview_paths.items():
        try:
            digest = sha256((ROOT / relative).read_bytes())
        except OSError:
            fail("RAOS_V2_BROWSER_PREVIEW_BINDING_INVALID")
        if preview_digests.get(route) != digest:
            fail("RAOS_V2_BROWSER_PREVIEW_BINDING_INVALID")
    checker_states = _mapping(
        assertions.get("checker_states"), "RAOS_V2_BROWSER_EVIDENCE_INVALID"
    )
    if (
        assertions.get("routes") != 9
        or assertions.get("viewports") != [320, 360, 390, 768, 1440]
        or assertions.get("axe_runs") != 45
        or any(
            assertions.get(key) != 0
            for key in (
                "axe_violations",
                "axe_incomplete",
                "horizontal_overflow",
                "outbound_requests",
                "persistent_records",
            )
        )
        or any(
            assertions.get(key) is not True
            for key in (
                "keyboard_only",
                "zoom_200_percent",
                "forced_colors",
                "reduced_motion",
                "screen_reader_smoke",
                "reflow_400_percent",
                "javascript_disabled_fallback",
                "transfer_budgets",
            )
        )
        or assertions.get("accessibility_tree_routes") != 9
        or assertions.get("unnamed_interactive_count") != 0
        or assertions.get("keyboard_routes") != 9
        or assertions.get("javascript_disabled_routes") != 2
        or assertions.get("transfer_budget_routes") != 9
        or checker_states.get("unknown_dominates_no_match") != "UNKNOWN"
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INVALID")
    if raw_binding.get("local_path") != (
        "output/playwright/raos-v2-local-browser-evidence.json"
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INVALID")
    raw_path = ROOT / str(raw_binding.get("local_path"))
    raw_status = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists() or raw_path.is_symlink():
        try:
            payload = _read_local_evidence_file(raw_path, root=ROOT)
        except ValidationFailure:
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        if (
            len(payload) != raw_binding.get("bytes")
            or sha256(payload) != raw_binding.get("sha256")
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        raw = _mapping(load_json_strict(payload), "RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        raw_routes = raw.get("routes")
        raw_viewports = raw.get("viewports")
        raw_accessibility = raw.get("accessibility")
        raw_keyboard = raw.get("keyboard")
        raw_media = raw.get("media")
        raw_javascript = raw.get("javascriptDisabled")
        raw_reflow = raw.get("reflow")
        raw_transfer = raw.get("transfer")
        raw_checker = raw.get("checker")
        raw_network = raw.get("network")
        raw_persistence = raw.get("persistence")
        viewport_names = {
            "reflow-320-equivalent-400pct",
            "mobile-360",
            "mobile-390",
            "tablet-768",
            "desktop-1440",
        }
        checker_field_map = {
            "pass": "pass",
            "fail": "fail",
            "count_fail": "countFail",
            "unknown": "unknown",
            "underseat_unknown": "underseatUnknown",
            "before_observed_boundary_unknown": "beforeObservedBoundaryUnknown",
            "review_deadline_stale": "reviewDeadlineStale",
            "ana_international_no_match": "anaInternationalNoMatch",
            "ana_unknown_scope": "anaUnknownScope",
            "peach_international_pass": "peachInternationalPass",
            "unknown_dominates_no_match": "unknownDominatesNoMatch",
            "all_segment_intersection": "allSegmentIntersection",
        }
        if (
            raw.get("classification") != "PASSED_LOCAL"
            or raw.get("previewDigests") != preview_digests
            or raw.get("harnessSha256") != raw_binding.get("harness_sha256")
            or raw.get("harnessBytes") != raw_binding.get("harness_bytes")
            or raw.get("commandContract") != raw_binding.get("command_contract")
            or raw.get("exitStatus") != 0
            or raw.get("externalActions") != "NOT_EXECUTED"
            or not isinstance(raw_routes, Mapping)
            or set(raw_routes) != set(preview_digests)
            or any(
                not isinstance(row, Mapping)
                or row.get("axeViolations") != 0
                or row.get("axeIncomplete") != []
                or row.get("mobileOverflow") is not False
                or not isinstance(row.get("viewportAudits"), Mapping)
                or set(row["viewportAudits"]) != viewport_names
                or any(
                    not isinstance(audit, Mapping)
                    or audit.get("axeViolations") != 0
                    or audit.get("axeIncomplete") != []
                    or audit.get("horizontalOverflow") is not False
                    for audit in row["viewportAudits"].values()
                )
                for row in raw_routes.values()
            )
            or not isinstance(raw_viewports, Mapping)
            or set(raw_viewports) != viewport_names
            or any(
                not isinstance(row, Mapping)
                or row.get("axeRuns") != 9
                or row.get("routes") != 9
                or row.get("horizontalOverflow") is not False
                for row in raw_viewports.values()
            )
            or not isinstance(raw_accessibility, Mapping)
            or raw_accessibility.get("routes") != 9
            or raw_accessibility.get("fullAxTreeAllRoutes") is not True
            or raw_accessibility.get("screenReaderSmokeAllRoutes") is not True
            or raw_accessibility.get("unnamedInteractiveCount") != 0
            or not isinstance(raw_keyboard, Mapping)
            or raw_keyboard.get("routes") != 9
            or raw_keyboard.get("focusTraversalAllRoutes") is not True
            or raw_keyboard.get("skipLinkAllRoutes") is not True
            or not isinstance(raw_media, Mapping)
            or not isinstance(raw_media.get("zoom"), Mapping)
            or raw_media["zoom"].get("routes") != 9
            or raw_media["zoom"].get("horizontalOverflow") is not False
            or not isinstance(raw_media.get("media"), Mapping)
            or raw_media["media"].get("routes") != 9
            or raw_media["media"].get("forcedColors") is not True
            or raw_media["media"].get("reducedMotion") is not True
            or not isinstance(raw_javascript, Mapping)
            or raw_javascript.get("testedRoutes") != 2
            or not isinstance(raw_javascript.get("routes"), Mapping)
            or any(
                not isinstance(row, Mapping)
                or row.get("fallbackVisible") is not True
                or row.get("formVisible") is not True
                or row.get("initialState") != "UNKNOWN"
                for row in raw_javascript["routes"].values()
            )
            or not isinstance(raw_reflow, Mapping)
            or raw_reflow.get("equivalentZoomPercent") != 400
            or raw_reflow.get("horizontalOverflow") is not False
            or raw_reflow.get("routes") != 9
            or not isinstance(raw_transfer, Mapping)
            or not isinstance(raw_transfer.get("routes"), Mapping)
            or set(raw_transfer["routes"]) != set(preview_digests)
            or any(
                not isinstance(row, Mapping)
                or row.get("withinCeiling") is not True
                or row.get("inlineSingleDocument") is not True
                or row.get("additionalResourceBytes") != 0
                for row in raw_transfer["routes"].values()
            )
            or not isinstance(raw_network, Mapping)
            or raw_network.get("outboundRequests") != 0
            or not isinstance(raw_persistence, Mapping)
            or any(entry != 0 for entry in raw_persistence.values())
            or not isinstance(raw_checker, Mapping)
            or any(
                raw_checker.get(raw_key) != checker_states.get(recorded_key)
                for recorded_key, raw_key in checker_field_map.items()
            )
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        raw_status = "RAW_RECEIPT_VERIFIED_LOCAL"
    pages_value = _mapping(
        load_json_strict(
            (
                ROOT
                / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
            ).read_bytes()
        ),
        "RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID",
    )
    page_rows = _rows(
        pages_value.get("pages"), "RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID"
    )
    state_to_classification = {
        "LOCAL_PREVIEW": "PUBLIC_CANDIDATE",
        "PLANNED_LOCKED": "PLANNED_LOCKED",
        "FIXTURE_ONLY": "FIXTURE_ONLY",
    }
    route_classifications: dict[str, str] = {}
    for row in page_rows:
        route = row.get("route")
        state = row.get("publication_state")
        if (
            not isinstance(route, str)
            or route in route_classifications
            or state not in state_to_classification
        ):
            fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
        route_classifications[route] = state_to_classification[str(state)]
    if set(route_classifications) != set(preview_digests):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    _review_payload, review_value = _read_required(
        "changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"
    )
    review = _mapping(
        review_value, "RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID"
    )
    verification = verify_visual_review_evidence(
        review,
        preview_digests={str(key): str(value) for key, value in preview_digests.items()},
        route_classifications=route_classifications,
        root=ROOT,
    )
    return {
        "browser": browser.get("classification"),
        "browser_raw": raw_status,
        "visual": verification.get("effective_status"),
        "visual_raw": verification.get("raw_verification"),
        "gate_passed": (
            browser.get("classification") == "PASSED_LOCAL"
            and raw_status
            in {"RAW_RECEIPT_VERIFIED_LOCAL", "RECORDED_NOT_REVERIFIED"}
            and verification.get("effective_status")
            == "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
            and verification.get("raw_verification")
            in {
                "RAW_CAPTURE_AND_27_PNGS_VERIFIED_LOCAL",
                "RECORDED_NOT_REVERIFIED",
            }
        ),
    }


def _validate_effective_traceability(
    *, evidence_gate_passed: bool
) -> dict[str, object]:
    effective = _mapping(
        _load_generated(
            "changes/raos-v2/generated/decision-traceability.effective.v1.yaml"
        ),
        "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID",
    )
    invariants = _mapping(
        effective.get("invariants"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID"
    )
    if not invariants or any(value is not True for value in invariants.values()):
        fail("RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID")
    decisions = _rows(
        effective.get("decisions"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID"
    )
    requirements = _rows(
        effective.get("requirements"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID"
    )
    backlog = _rows(
        effective.get("backlog"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID"
    )
    tests = _rows(effective.get("tests"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID")
    d_map = {str(row["id"]): row for row in decisions}
    r_map = {str(row["id"]): row for row in requirements}
    b_map = {str(row["id"]): row for row in backlog}
    t_map = {str(row["id"]): row for row in tests}
    if (
        len(d_map) != len(decisions)
        or len(r_map) != len(requirements)
        or set(b_map) != {f"B-V2-{number:03d}" for number in range(1, 35)}
        or set(t_map)
        != {*(f"T-V2-{number:03d}" for number in range(1, 47)), "T-V2-051"}
    ):
        fail("RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID")
    for decision_id, row in d_map.items():
        for requirement_id in row.get("requirement_ids", []):
            if decision_id not in r_map.get(str(requirement_id), {}).get(
                "decision_ids", []
            ):
                fail("RAOS_V2_EFFECTIVE_TRACEABILITY_BIDIRECTIONAL_INVALID")
    for requirement_id, row in r_map.items():
        for backlog_id in row.get("backlog_ids", []):
            if requirement_id not in b_map.get(str(backlog_id), {}).get(
                "requirement_ids", []
            ):
                fail("RAOS_V2_EFFECTIVE_TRACEABILITY_BIDIRECTIONAL_INVALID")
        for test_id in row.get("test_ids", []):
            if requirement_id not in t_map.get(str(test_id), {}).get(
                "requirement_ids", []
            ):
                fail("RAOS_V2_EFFECTIVE_TRACEABILITY_BIDIRECTIONAL_INVALID")
    for backlog_id, row in b_map.items():
        for test_id in row.get("test_ids", []):
            if backlog_id not in t_map.get(str(test_id), {}).get("backlog_ids", []):
                fail("RAOS_V2_EFFECTIVE_TRACEABILITY_BIDIRECTIONAL_INVALID")
    graph = {
        backlog_id: {str(value) for value in row.get("depends_on", [])}
        for backlog_id, row in b_map.items()
    }
    pending = dict(graph)
    while pending:
        ready = {
            identifier
            for identifier, dependencies in pending.items()
            if not dependencies & pending.keys()
        }
        if not ready:
            fail("RAOS_V2_EFFECTIVE_BACKLOG_CYCLE")
        for identifier in ready:
            pending.pop(identifier)
    local_test = _mapping(
        _load_generated(
            "changes/raos-v2/recorded-inputs/phase2-local-test-evidence.v1.json"
        ),
        "RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID",
    )
    verification = verify_local_test_evidence(local_test, root=ROOT)
    local_test_status = verification["effective_status"]
    gate_passed = local_test_status == "PASSED_LOCAL" and evidence_gate_passed
    for identifier, row in b_map.items():
        number = int(identifier.rsplit("-", 1)[1])
        expected = (
            "GENERATED_LOCAL"
            if number <= 18
            else "VERIFIED_LOCAL_RECORDED"
            if gate_passed
            else "AWAITING_LOCAL_TEST_GATE"
            if number == 34
            else "IMPLEMENTED_LOCAL_PENDING_GATE"
        )
        if row.get("implementation_status") != expected:
            fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
    expected_test_status = (
        "PASSED_LOCAL_RECORDED" if gate_passed else "NOT_EXECUTED_RECORDED"
    )
    if any(row.get("execution_status") != expected_test_status for row in tests):
        fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
    validation = _mapping(
        _load_generated("changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    test_contracts = _mapping(
        validation.get("local_test_contracts"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    generated_browser = _mapping(
        validation.get("browser_evidence"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    generated_visual = _mapping(
        validation.get("visual_review_evidence"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    recorded_browser = _mapping(
        _load_generated(
            "changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"
        ),
        "RAOS_V2_BROWSER_EVIDENCE_INVALID",
    )
    recorded_visual = _mapping(
        _load_generated(
            "changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"
        ),
        "RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID",
    )
    recorded_browser_raw = _mapping(
        recorded_browser.get("raw_receipt"), "RAOS_V2_BROWSER_EVIDENCE_INVALID"
    )
    generated_visual_verification = _mapping(
        generated_visual.get("verification"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    generated_receipt = _mapping(
        test_contracts.get("receipt"), "RAOS_V2_PHASE2_VALIDATION_INVALID"
    )
    expected_completed = (
        [f"B-V2-{number:03d}" for number in range(19, 35)] if gate_passed else []
    )
    if (
        validation.get("completed_backlog_ids") != expected_completed
        or validation.get("status")
        != ("PASSED_LOCAL_RECORDED" if gate_passed else "READY_FOR_LOCAL_TEST_GATE")
        or test_contracts.get("status") != local_test_status
        or generated_receipt.get("status") != local_test_status
        or generated_receipt.get("claimed_status") != local_test.get("status")
        or generated_receipt.get("binding_verification")
        != verification["binding_verification"]
        or generated_receipt.get("raw_verification")
        != verification["raw_verification"]
        or generated_browser.get("classification")
        != recorded_browser.get("classification")
        or generated_browser.get("receipt_sha256")
        != recorded_browser_raw.get("sha256")
        or generated_browser.get("receipt_bytes")
        != recorded_browser_raw.get("bytes")
        or generated_visual.get("classification")
        != recorded_visual.get("classification")
        or generated_visual.get("reviewer_class")
        != recorded_visual.get("reviewer_class")
        or generated_visual.get("reviewed_at_jst")
        != recorded_visual.get("reviewed_at_jst")
        or generated_visual.get("capture_receipt")
        != recorded_visual.get("capture_receipt")
        or generated_visual.get("aggregate_findings")
        != recorded_visual.get("aggregate_findings")
        or generated_visual.get("capture_hash_review")
        != recorded_visual.get("capture_hash_review")
        or generated_visual_verification.get("effective_status")
        != "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
        or generated_visual_verification.get("captures") != 27
        or generated_visual_verification.get("critical_findings") != 0
        or generated_visual_verification.get("major_findings") != 0
    ):
        fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
    return {
        "local_test_status": local_test_status,
        "gate_passed": gate_passed,
        "binding_verification": verification["binding_verification"],
        "raw_verification": verification["raw_verification"],
    }


def _validate_generated_artifact_inventory() -> None:
    evidence = _mapping(
        _load_generated(
            "changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"
        ),
        "RAOS_V2_LOCAL_EVIDENCE_INVALID",
    )
    rows = _rows(
        evidence.get("generated_artifacts"), "RAOS_V2_LOCAL_EVIDENCE_INVALID"
    )
    observed: set[str] = set()
    for row in rows:
        relative = row.get("path")
        if not isinstance(relative, str) or relative in observed:
            fail("RAOS_V2_LOCAL_EVIDENCE_INVALID")
        observed.add(relative)
        try:
            payload = (ROOT / relative).read_bytes()
        except OSError:
            fail("RAOS_V2_LOCAL_EVIDENCE_INVALID")
        if row.get("bytes") != len(payload) or row.get("sha256") != sha256(payload):
            fail("RAOS_V2_LOCAL_EVIDENCE_DRIFT")
    validation = _mapping(
        _load_generated("changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"),
        "RAOS_V2_PHASE2_VALIDATION_INVALID",
    )
    visual_rows = _rows(
        evidence.get("visual_a11y_evidence"), "RAOS_V2_LOCAL_EVIDENCE_INVALID"
    )
    if (
        evidence.get("gate_status") != validation.get("status")
        or len(visual_rows) != 2
        or visual_rows[0] != validation.get("browser_evidence")
        or visual_rows[1] != validation.get("visual_review_evidence")
        or evidence.get("classification")
        != (
            "PASSED_LOCAL_RECORDED_WITH_BROWSER_AND_MANUAL_VISUAL_EVIDENCE"
            if validation.get("status") == "PASSED_LOCAL_RECORDED"
            else "GENERATED_LOCAL_PENDING_COMBINED_EVIDENCE_GATE"
        )
    ):
        fail("RAOS_V2_LOCAL_EVIDENCE_INVALID")


def protected_path_changes(base_head: str, *, root: Path = ROOT) -> list[str]:
    """Return protected-path changes in history or the current worktree."""

    if not re.fullmatch(r"[0-9a-f]{40}", base_head):
        fail("RAOS_V2_IMMUTABLE_BASE_INVALID")

    def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=root,
                check=check,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            fail("RAOS_V2_IMMUTABLE_BASE_INVALID")

    git("cat-file", "-e", f"{base_head}^{{commit}}")
    ancestor = git("merge-base", "--is-ancestor", base_head, "HEAD", check=False)
    if ancestor.returncode != 0:
        fail("RAOS_V2_IMMUTABLE_BASE_INVALID")
    protected = ("docs/canonical", "docs/upstream", "zip")
    committed = git(
        "diff", "--name-only", f"{base_head}..HEAD", "--", *protected
    ).stdout.splitlines()
    worktree = git(
        "status", "--porcelain=v1", "--untracked-files=all", "--", *protected
    ).stdout.splitlines()
    return sorted({*committed, *worktree})


def _validate_authoritative_ui_parity(
    page_document: Mapping[str, object], page_rows: Sequence[Mapping[str, object]]
) -> None:
    ui_root = ROOT / "packages/web-ui/src/decision-support-v2"
    try:
        contracts = (ui_root / "contracts.ts").read_text(encoding="utf-8")
        typescript_checker = (ui_root / "checker.ts").read_text(encoding="utf-8")
        preview_checker = (ui_root / "preview/checker.js").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    pattern = re.compile(
        r"\{\s*route: '([^']+)',\s*template: '([^']+)',\s*"
        r"articleId: '([^']+)',\s*publicationState: '([^']+)',\s*"
        r"publicCandidate: (true|false),\s*"
        r"intendedIndexCandidate: (true|false),\s*"
        r"previewRobots: '([^']+)',\s*\}",
        re.DOTALL,
    )
    contract_rows = [
        (route, template, article, state, public == "true", intended == "true", robots)
        for route, template, article, state, public, intended, robots in pattern.findall(
            contracts
        )
    ]
    expected_rows = [
        (
            row.get("route"),
            row.get("template"),
            row.get("article_id"),
            row.get("publication_state"),
            row.get("public_candidate"),
            row.get("intended_index_candidate"),
            page_document.get("preview_robots"),
        )
        for row in page_rows
    ]
    if contract_rows != expected_rows:
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")

    def priorities(source: str) -> dict[str, int]:
        match = re.search(
            r"const STATE_PRIORITY[^=]*= Object\.freeze\(\{(.*?)\}\);",
            source,
            re.DOTALL,
        )
        if match is None:
            fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
        return {
            state: int(value)
            for state, value in re.findall(
                r"\b(PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH):\s*(\d+)",
                match.group(1),
            )
        }

    typescript_priority = priorities(typescript_checker)
    preview_priority = priorities(preview_checker)
    if (
        typescript_priority != preview_priority
        or set(typescript_priority)
        != {"PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"}
        or typescript_priority["PASS"] != 0
        or typescript_priority["UNKNOWN"] <= typescript_priority["NO_MATCH"]
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")


def _validate_cross_ledger_and_sitemap(
    product: Mapping[str, object],
    routes: Mapping[str, object],
    contract_values: Mapping[str, object],
) -> None:
    route_rows = _rows(routes.get("routes"), "RAOS_V2_ROUTE_REGISTRY_INVALID")
    portfolio_rows = _rows(
        product.get("portfolio"), "RAOS_V2_PRODUCT_SPEC_INVALID"
    )
    page_document = _mapping(
        _load_generated(
            "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
        ),
        "RAOS_V2_UI_PAGE_SOURCE_INVALID",
    )
    page_rows = _rows(page_document.get("pages"), "RAOS_V2_UI_PAGE_SOURCE_INVALID")
    _validate_authoritative_ui_parity(page_document, page_rows)
    article_rows = list(
        _mapping(
            contract_values.get("articles"), "RAOS_V2_ARTICLE_LEDGER_INVALID"
        ).values()
    )

    def index(rows: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
        result: dict[str, Mapping[str, object]] = {}
        for row in rows:
            route = row.get("route")
            if not isinstance(route, str) or route in result:
                fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
            result[route] = row
        return result

    registry = index(route_rows)
    portfolio = index(portfolio_rows)
    pages = index(page_rows)
    articles = index(article_rows)
    if set(portfolio) != set(registry) - {"/"}:
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, row in portfolio.items():
        if any(
            registry[route].get(field) != row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, row in pages.items():
        if route not in registry or any(
            registry[route].get(field) != row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, row in articles.items():
        if route not in registry or any(
            registry[route].get(field) != row.get(field)
            for field in (
                "article_id",
                "primary_intent_id",
                "template",
                "parent_hub",
            )
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")

    sitemap = _mapping(
        _load_generated(
            "changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"
        ),
        "RAOS_V2_SITEMAP_CANDIDATE_INVALID",
    )
    entries = _rows(sitemap.get("entries"), "RAOS_V2_SITEMAP_CANDIDATE_INVALID")
    entries_by_route = index(entries)
    if (
        set(entries_by_route) != set(pages)
        or sitemap.get("production_sitemap_write") != "NOT_EXECUTED"
        or sitemap.get("mode") != "LOCAL_CONTRACT_ONLY"
    ):
        fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
    intended_count = 0
    for route, page in pages.items():
        entry = entries_by_route[route]
        preview_path = (
            ROOT / "changes/raos-v2/phase-2/preview/index.html"
            if route == "/"
            else ROOT
            / "changes/raos-v2/phase-2/preview"
            / route.strip("/")
            / "index.html"
        )
        try:
            preview_payload = preview_path.read_bytes()
            preview_text = preview_payload.decode("utf-8")
        except (OSError, UnicodeError):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        intended = page.get("intended_index_candidate") is True
        intended_count += int(intended)
        if (
            entry.get("article_id") != page.get("article_id")
            or entry.get("title") != page.get("title")
            or entry.get("description") != page.get("description")
            or entry.get("canonical_candidate")
            != f"https://kurashinoshirube.com{route}"
            or entry.get("preview_robots") != "noindex,nofollow"
            or entry.get("phase2_sitemap_included") is not False
            or entry.get("phase3_intended_candidate") is not intended
            or entry.get("lastmod") != "UNAVAILABLE"
            or entry.get("render_sha256") != sha256(preview_payload)
            or '<meta name="robots" content="noindex,nofollow">' not in preview_text
            or (
                f'<link rel="canonical" href="https://kurashinoshirube.com{route}">'
                not in preview_text
            )
            or f"<title>{html_escape(str(page.get('title')))} | 暮らしのしるべ</title>"
            not in preview_text
            or (
                f'<meta name="description" content="'
                f'{html_escape(str(page.get("description")), quote=True)}">'
                not in preview_text
            )
        ):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
    if sitemap.get("candidate_count") != intended_count:
        fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")


def validate_generated() -> dict[str, object]:
    validate_source_traceability()
    capture = _mapping(
        _load_generated("changes/raos-v2/recorded-inputs/phase0-capture.v1.json"),
        "RAOS_V2_PHASE0_CAPTURE_INVALID",
    )
    repository = _mapping(
        capture.get("repository"), "RAOS_V2_PHASE0_CAPTURE_INVALID"
    )
    base_head = repository.get("head")
    if (
        base_head != IMMUTABLE_BASE_HEAD
        or protected_path_changes(IMMUTABLE_BASE_HEAD)
    ):
        fail("RAOS_V2_IMMUTABLE_PATH_CHANGED")
    preflight = _mapping(
        _load_generated("changes/raos-v2/phase-0/preflight-report.json"),
        "RAOS_V2_PREFLIGHT_INVALID",
    )
    if (
        preflight.get("immutable_base_head") != IMMUTABLE_BASE_HEAD
        or _mapping(
            preflight.get("repository"), "RAOS_V2_PREFLIGHT_INVALID"
        ).get("head")
        != IMMUTABLE_BASE_HEAD
    ):
        fail("RAOS_V2_IMMUTABLE_BASE_INVALID")
    source_import = _mapping(
        _load_generated("changes/raos-v2/source-import.v1.json"),
        "RAOS_V2_SOURCE_IMPORT_INVALID",
    )
    if source_import.get("package_sha256") != PACKAGE_SHA256:
        fail("RAOS_V2_SOURCE_IMPORT_INVALID")
    imported = source_import.get("imported_files")
    excluded = source_import.get("excluded_files")
    if (
        not isinstance(imported, list)
        or len(imported) != 19
        or not isinstance(excluded, list)
    ):
        fail("RAOS_V2_SOURCE_IMPORT_INVALID")
    if any(
        isinstance(row, dict) and row.get("path") == PROMPT_PATH for row in imported
    ):
        fail("RAOS_V2_PROMPT_WAS_IMPORTED")
    for row in imported:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            fail("RAOS_V2_SOURCE_IMPORT_INVALID")
        relative = str(row["path"])
        try:
            payload = (SOURCE_ROOT / relative).read_bytes()
        except OSError:
            fail("RAOS_V2_IMPORTED_SOURCE_MISSING")
        if row.get("bytes") != len(payload) or row.get("sha256") != sha256(payload):
            fail("RAOS_V2_IMPORTED_SOURCE_DRIFT")
    try:
        manifest_payload = (SOURCE_ROOT / "MANIFEST.sha256").read_bytes()
    except OSError:
        fail("RAOS_V2_IMPORTED_SOURCE_MISSING")
    if sha256(manifest_payload) != SOURCE_MANIFEST_SHA256:
        fail("RAOS_V2_SOURCE_MANIFEST_ANCHOR_MISMATCH")
    if (SOURCE_ROOT / PROMPT_PATH).exists() or not any(
        isinstance(row, dict)
        and row.get("path") == PROMPT_PATH
        and row.get("sha256") == PROMPT_SHA256
        and row.get("reason") == "PROMPT_IS_DATA_NOT_EXECUTABLE_AUTHORITY"
        for row in excluded
    ):
        fail("RAOS_V2_PACKAGE_PROMPT_RECEIPT_INVALID")

    metrics = _mapping(
        _load_generated("changes/raos-v2/phase-0/metric-dictionary.yaml"),
        "RAOS_V2_METRIC_DICTIONARY_INVALID",
    )
    if (
        not isinstance(metrics.get("rules"), dict)
        or metrics["rules"].get("missing_value") != "UNAVAILABLE"
    ):
        fail("RAOS_V2_METRIC_DICTIONARY_INVALID")
    metric_rows = _rows(metrics.get("metrics"), "RAOS_V2_METRIC_DICTIONARY_INVALID")
    metric_ids = {row.get("id") for row in metric_rows}
    required_metrics = {
        "QDS",
        "NON_BRAND_ORGANIC_SESSIONS",
        "NON_BRAND_IMPRESSIONS",
        "NON_BRAND_QUERY_WIDTH",
        "AFFILIATE_OUTBOUND_CTR",
        "CONFIRMED_EPC",
        "CONFIRMED_RPM",
        "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT",
        "ARTICLE_PAYBACK_MONTHS",
        "CATEGORY_PAYBACK_MONTHS",
        "DIRECT_AND_RETURN_RATE",
        "CORRECTION_RATE",
        "MAJOR_FACT_DEFECTS",
        "STALE_EXPOSURE_RATE",
        "HUMAN_HOURS_PER_ARTICLE",
        "UPDATE_COST_PER_PAGE",
        "COMPLAINT_FIRST_RESPONSE_WITHIN_72H_RATE",
    }
    if not required_metrics <= metric_ids:
        fail("RAOS_V2_METRIC_DICTIONARY_INVALID")
    for row in metric_rows:
        if not isinstance(row, dict) or not all(
            row.get(key)
            for key in (
                "id",
                "formula",
                "source",
                "required_maturity",
                "unavailable_rule",
            )
        ):
            fail("RAOS_V2_METRIC_DICTIONARY_INVALID")
    rollback = _mapping(
        _load_generated("changes/raos-v2/phase-0/rollback-contract.yaml"),
        "RAOS_V2_ROLLBACK_CONTRACT_INVALID",
    )
    simulation = rollback.get("simulation")
    if not isinstance(simulation, dict) or not isinstance(
        simulation.get("redirect_rules"), list
    ):
        fail("RAOS_V2_ROLLBACK_CONTRACT_INVALID")
    validate_redirect_rules(simulation["redirect_rules"])
    deprecation = _mapping(
        _load_generated("changes/raos-v2/phase-0/deprecation-ledger.yaml"),
        "RAOS_V2_DEPRECATION_LEDGER_INVALID",
    )
    deprecation_rows = _rows(
        deprecation.get("assets"), "RAOS_V2_DEPRECATION_LEDGER_INVALID"
    )
    if len(deprecation_rows) != 15 or deprecation.get(
        "retire_requires_verified_unused"
    ) is not True:
        fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
    for row in deprecation_rows:
        if not all(
            isinstance(row.get(key), dict)
            for key in ("usage_evidence", "replacement", "rollback")
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        usage = _mapping(row["usage_evidence"], "RAOS_V2_DEPRECATION_LEDGER_INVALID")
        replacement = _mapping(
            row["replacement"], "RAOS_V2_DEPRECATION_LEDGER_INVALID"
        )
        asset_rollback = _mapping(
            row["rollback"], "RAOS_V2_DEPRECATION_LEDGER_INVALID"
        )
        if (
            not isinstance(usage.get("status"), str)
            or not usage["status"]
            or not isinstance(usage.get("source"), str)
            or not usage["source"]
            or not isinstance(usage.get("verified_unused"), bool)
            or not isinstance(replacement.get("status"), str)
            or not replacement["status"]
            or not isinstance(replacement.get("plan"), str)
            or not replacement["plan"]
            or not isinstance(asset_rollback.get("status"), str)
            or not asset_rollback["status"]
            or not isinstance(asset_rollback.get("plan"), str)
            or not asset_rollback["plan"]
            or asset_rollback.get("production_execution") != "NOT_EXECUTED"
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        if row.get("decision") == "RETIRE" and (
            usage.get("verified_unused") is not False
            or row.get("removal_readiness") != "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
    product = _mapping(
        _load_generated("changes/raos-v2/product-spec.v2.yaml"),
        "RAOS_V2_PRODUCT_SPEC_INVALID",
    )
    routes = _mapping(
        _load_generated("changes/raos-v2/route-registry.v2.yaml"),
        "RAOS_V2_ROUTE_REGISTRY_INVALID",
    )
    if (
        len(product.get("portfolio", [])) != 25
        or len(product.get("templates", [])) != 7
    ):
        fail("RAOS_V2_PRODUCT_SPEC_INVALID")
    route_rows = routes.get("routes")
    if not isinstance(route_rows, list):
        fail("RAOS_V2_ROUTE_REGISTRY_INVALID")
    route_values = [row.get("route") for row in route_rows if isinstance(row, dict)]
    if len(route_values) != 26 or len(route_values) != len(set(route_values)):
        fail("RAOS_V2_ROUTE_COLLISION")
    route_set = set(route_values)
    for row in route_rows:
        if not isinstance(row, dict):
            fail("RAOS_V2_ROUTE_REGISTRY_INVALID")
        links = row.get("internal_links")
        if not isinstance(links, list) or not links or not set(links) <= route_set:
            fail("RAOS_V2_ROUTE_ORPHAN_OR_UNKNOWN_LINK")

    contract_values = _validate_contract_instances()
    _validate_publication_closure(contract_values)
    _validate_cross_ledger_and_sitemap(product, routes, contract_values)
    evidence_status = _validate_visual_and_browser_evidence()
    trace_status = _validate_effective_traceability(
        evidence_gate_passed=evidence_status.get("gate_passed") is True
    )
    _validate_generated_artifact_inventory()
    return {
        "schema": "RAOS_V2_LOCAL_VALIDATION_RECEIPT_V1",
        "status": "STRUCTURAL_VALIDATION_PASSED_LOCAL",
        "portfolio": 25,
        "routes": 26,
        "schemas": 10,
        "contract_instances": {
            "sources": len(contract_values["sources"]),
            "claims": len(contract_values["claims"]),
            "products": len(contract_values["products"]),
            "articles": len(contract_values["articles"]),
        },
        "browser_evidence": evidence_status,
        "recorded_local_test_status": trace_status["local_test_status"],
        "external_actions": "NOT_EXECUTED",
    }


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: str | None = None
        self.robots: str | None = None
        self.h1_parts: list[str] = []
        self.in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag.lower() == "link" and values.get("rel", "").lower() == "canonical":
            self.canonical = values.get("href")
        elif tag.lower() == "meta" and values.get("name", "").lower() == "robots":
            self.robots = values.get("content")
        elif tag.lower() == "h1" and not self.h1_parts:
            self.in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h1":
            self.in_h1 = False

    def handle_data(self, data: str) -> None:
        if self.in_h1:
            value = " ".join(data.split())
            if value:
                self.h1_parts.append(value)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.chain: list[dict[str, object]] = []

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Mapping[str, str],
        new_url: str,
    ) -> Request | None:
        destination = urljoin(request.full_url, new_url)
        validate_public_url(destination)
        if len(self.chain) >= MAX_REDIRECTS:
            fail("RAOS_V2_CAPTURE_REDIRECT_LIMIT")
        self.chain.append({"status": code, "from": request.full_url, "to": destination})
        return super().redirect_request(
            request, file_pointer, code, message, headers, destination
        )


def _fetch(url: str) -> tuple[int, bytes, Mapping[str, str], list[dict[str, object]]]:
    validate_public_url(url)
    redirect_handler = _SafeRedirectHandler()
    opener = build_opener(
        ProxyHandler({}),
        HTTPSHandler(context=ssl.create_default_context()),
        redirect_handler,
    )
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "text/html,application/xml;q=0.9,text/xml;q=0.8",
            "User-Agent": "RAOS-V2-Public-Read-Only-Capture/1.0",
        },
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(response.status)
            headers = dict(response.headers.items())
    except HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
        headers = dict(exc.headers.items())
    except (OSError, URLError):
        fail("RAOS_V2_CAPTURE_NETWORK_FAILURE")
    if len(payload) > MAX_RESPONSE_BYTES:
        fail("RAOS_V2_CAPTURE_RESPONSE_TOO_LARGE")
    return status, payload, headers, redirect_handler.chain


def _sitemap_urls() -> tuple[set[str], list[dict[str, object]]]:
    queue = [f"{ORIGIN}/sitemap_index.xml"]
    visited: set[str] = set()
    public_urls: set[str] = set()
    evidence: list[dict[str, object]] = []
    while queue and len(visited) < MAX_SITEMAPS:
        url = queue.pop(0)
        if url in visited:
            continue
        status, payload, _headers, redirects = _fetch(url)
        visited.add(url)
        evidence.append(
            {
                "url": url,
                "status": status,
                "sha256": sha256(payload),
                "redirect_chain": redirects,
            }
        )
        if status != 200:
            continue
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            fail("RAOS_V2_SITEMAP_XML_INVALID")
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
                continue
            candidate = element.text.strip()
            path = validate_public_url(candidate)
            if path.endswith(".xml") and len(queue) + len(visited) < MAX_SITEMAPS:
                queue.append(candidate)
            elif len(public_urls) < MAX_CAPTURE_URLS:
                public_urls.add(candidate)
    return public_urls, evidence


def _repository_capture() -> dict[str, object]:
    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            fail("RAOS_V2_GIT_PREFLIGHT_FAILED")

    status = [line for line in git("status", "--porcelain=v1").splitlines() if line]
    diffstat = [
        line for line in git("diff", "--stat", "--no-ext-diff").splitlines() if line
    ]
    return {
        "worktree": str(ROOT),
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "root_agents_read": True,
        "original_dirty_worktree_preserved": True,
        "generator_owner": "scripts/build_raos_v2_successor.py",
        "initial_worktree_state": "CLEAN" if not status else "DIRTY",
        "initial_status_porcelain": status,
        "initial_diffstat": diffstat,
    }


def capture_phase0(*, public_read_only: bool) -> dict[str, object]:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    urls: list[dict[str, object]] = []
    sitemap_evidence: list[dict[str, object]] = []
    if public_read_only:
        sitemap_members, sitemap_evidence = _sitemap_urls()
        capture_paths = list(KNOWN_PATHS)
        for sitemap_url in sorted(sitemap_members):
            sitemap_path = validate_public_url(sitemap_url)
            if (
                sitemap_path not in capture_paths
                and len(capture_paths) < MAX_CAPTURE_URLS
            ):
                capture_paths.append(sitemap_path)
        for path in capture_paths:
            url = f"{ORIGIN}{path.lstrip('/') if path == '/' else path}"
            if path == "/":
                url = ORIGIN + "/"
            status, payload, headers, redirects = _fetch(url)
            parser = _MetadataParser()
            content_type = headers.get("Content-Type", "")
            if "html" in content_type.lower() or payload.lstrip().startswith(b"<!"):
                try:
                    parser.feed(payload.decode("utf-8", errors="replace"))
                except (UnicodeError, ValueError):
                    fail("RAOS_V2_CAPTURE_HTML_INVALID")
            urls.append(
                {
                    "path": path,
                    "status": status,
                    "redirect_chain": redirects,
                    "canonical": parser.canonical,
                    "robots": parser.robots
                    or headers.get("X-Robots-Tag")
                    or "UNAVAILABLE",
                    "h1": " ".join(parser.h1_parts) or "UNAVAILABLE",
                    "sitemap_membership": url in sitemap_members,
                    "body_sha256": sha256(payload),
                    "body_bytes": len(payload),
                    "observed_at": now,
                }
            )
    document = {
        "schema": "RAOS_V2_PHASE0_CAPTURE_V1",
        "captured_at": now,
        "repository": _repository_capture(),
        "public_observation_status": (
            "PUBLIC_READ_ONLY" if public_read_only else "NOT_EXECUTED"
        ),
        "public_urls": urls,
        "supporting_resources": {
            "sitemaps": sitemap_evidence,
            "capture_scope": "KNOWN_UNION_SITEMAP_BOUNDED",
            "maximum_capture_urls": MAX_CAPTURE_URLS,
        },
        "visual_baseline": [],
        "visual_baseline_note": (
            "Browser screenshots are a separate manual recorded-evidence input; "
            "this bounded HTTP capture command never claims to create them."
        ),
    }
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(RECORDED_INPUT, payload)
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate", help="offline generated/source validation")
    package = subcommands.add_parser(
        "validate-package",
        help="validate the attached package without executing its prompt",
    )
    package.add_argument("--zip", type=Path, default=PACKAGE_PATH)
    capture = subcommands.add_parser(
        "capture-phase0",
        help="capture repository preflight; network remains off by default",
    )
    capture.add_argument("--public-read-only", action="store_true")
    subcommands.add_parser(
        "record-local-test",
        help="bind an ignored pytest tee to the current local source/test inventory",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate-package":
            result = validate_package(arguments.zip)
        elif arguments.command == "capture-phase0":
            if RECORDED_INPUT.exists():
                fail("RAOS_V2_PHASE0_BASELINE_ALREADY_CAPTURED")
            result = capture_phase0(public_read_only=arguments.public_read_only)
        elif arguments.command == "record-local-test":
            result = record_local_test_evidence()
            _atomic_write(LOCAL_TEST_EVIDENCE_INPUT, canonical_json_bytes(result))
        else:
            result = validate_generated()
    except ValidationFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
