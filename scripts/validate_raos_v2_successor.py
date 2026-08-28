#!/usr/bin/env python3
"""Validate or explicitly capture sanitized RAOS V2 successor inputs.

Normal validation is offline.  Network access exists only behind the explicit
``--public-read-only`` flag on a capture command; it is origin-bound,
credential-free, query-free and capped.  Captured response bodies are hashed
and discarded.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
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
from urllib.parse import unquote, urljoin, urlsplit
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
import unicodedata

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
    ROOT / "changes/raos-v2/recorded-inputs/phase2-local-test-evidence.v1.json"
)
VISUAL_EVIDENCE_INPUT: Final = (
    ROOT / "changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"
)
PHASE3_LOCAL_BROWSER_EVIDENCE_INPUT: Final = (
    ROOT / "changes/raos-v2/recorded-inputs/phase3-local-browser-evidence.v1.json"
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
PHASE3_PUBLIC_PATH: Final = "/carry-on-suitcase-comparison/"
PHASE3_PUBLIC_URL: Final = f"{ORIGIN}{PHASE3_PUBLIC_PATH}"
PHASE3_ROBOTS_URL: Final = f"{ORIGIN}/robots.txt"
PHASE3_PACKAGE_MARKER: Final = "RAOS_V2_A05_POST_CONTENT_V1"
PHASE3_CONTENT_ENVELOPE: Final = "RAOS_V2_A05_ENVELOPE_V1"
PHASE3_PLUGIN_CSS_URL: Final = (
    ORIGIN + "/wp-content/plugins/raos-v2-decision-support/assets/decision-support.css"
)
PHASE3_PLUGIN_CSS_RESOURCE_URL: Final = PHASE3_PLUGIN_CSS_URL
PHASE3_PLUGIN_SOURCE_ROOT: Final = Path(
    "packages/web-ui/src/decision-support-v2/wordpress/plugin/raos-v2-decision-support"
)
PHASE3_PLUGIN_ARTIFACT_ROOT: Final = Path(
    "changes/raos-v2/phase-3/wordpress/artifact/raos-v2-decision-support"
)
PHASE3_AFFILIATE_HOSTS: Final = frozenset(
    {
        "a.r10.to",
        "affiliate.rakuten.co.jp",
        "hb.afl.rakuten.co.jp",
    }
)
PHASE3_RECORDED_ROOT: Final = Path("changes/raos-v2/recorded-inputs/phase3")
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_REDIRECTS: Final = 1
MAX_SITEMAPS: Final = 8
MAX_SITEMAP_ENTRIES: Final = 50_000
SITEMAP_NAMESPACE: Final = "http://www.sitemaps.org/schemas/sitemap/0.9"
MAX_CAPTURE_URLS: Final = 40
TIMEOUT_SECONDS: Final = 15
PHASE3_PUBLIC_CAPTURE_MAX_AGE_SECONDS: Final = 300
PHASE3_ROBOTS_MAX_BYTES: Final = 512_000
PHASE3_WORDPRESS_FIELD_NAMES: Final = frozenset(
    {
        "canonical_url",
        "comment_status",
        "meta_description",
        "ping_status",
        "post_content",
        "post_excerpt",
        "post_name",
        "post_status",
        "post_title",
    }
)
PHASE3_CAPTURE_KEYS: Final = frozenset(
    {
        "schema",
        "version",
        "captured_at",
        "target_url",
        "public_observation_status",
        "observation",
        "supporting_resources",
        "request_policy",
        "external_write_actions",
        "phase0_baseline_write",
    }
)
PHASE3_OBSERVATION_KEYS: Final = frozenset(
    {
        "url",
        "path",
        "status",
        "redirect_chain",
        "canonical",
        "canonical_tag_count",
        "head_tag_count",
        "metadata_location_violation_count",
        "title",
        "title_tag_count",
        "meta_description",
        "meta_description_tag_count",
        "robots",
        "robots_meta",
        "robots_http",
        "robots_http_indexability_safe",
        "content_type_media_type",
        "refresh_http_present",
        "link_http_sha256",
        "robots_tag_count",
        "crawler_robots_tag_count",
        "crawler_robots_indexability_safe",
        "h1",
        "h1_count",
        "sitemap_membership",
        "package_marker_count",
        "package_marker_attribute_count",
        "post_content_envelope_count",
        "post_content_envelope_attribute_count",
        "blocked_post_content_envelope_count",
        "post_content_envelope_marker_child_count",
        "post_content_envelope_valid",
        "post_content_marker_subtree_count",
        "post_content_semantic_sha256",
        "disclosure_marker_count",
        "cta_state_count",
        "blocked_cta_count",
        "affiliate_url_count",
        "ambiguous_attribute_count",
        "image_count",
        "inline_executable_script_count",
        "external_script_count",
        "resource_inventory",
        "json_ld_script_count",
        "json_ld_invalid_count",
        "json_ld_sha256",
        "json_ld_types",
        "json_ld_visible_content_match",
        "body_sha256",
        "body_bytes",
        "body_storage",
        "observed_at",
    }
)
LOCAL_TEST_COMMAND: Final = "TMPDIR=/tmp uv run --offline pytest -s -q tests/raos_v2"
LOCAL_TEST_COMMAND_CONTRACT: Final = "BASH_PIPEFAIL_TEE_TEMP_PROMOTED_BY_RECORDER_V2"
LOCAL_TEST_RAW_OUTPUT_PATH: Final = Path("output/pytest/raos-v2-local-test-output.txt")
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
PHASE3_BROWSER_RAW_RECEIPT_PATH: Final = Path(
    "output/playwright/raos-v2-phase3-local-browser-evidence.json"
)
PHASE3_BROWSER_HARNESS_PATH: Final = Path("tests/raos_v2/phase3-local-validation.mjs")
PHASE3_BROWSER_SUPPORT_HARNESS_PATH: Final = Path(
    "tests/raos_v2/browser-validation.mjs"
)
PHASE3_BROWSER_PREVIEW_PATH: Final = Path(
    "changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"
)
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
    Path("scripts/raos_v2_phase3_execution.py"),
    Path("scripts/raos_build_core.py"),
    Path("scripts/validate_raos_v2_successor.py"),
)
LOCAL_TEST_MACHINE_CONTRACT_ROOTS: Final = (
    Path("contracts/raos-v2"),
    Path("changes/raos-v2/design"),
    Path("changes/raos-v2/phase-0"),
    Path("changes/raos-v2/phase-2/claims"),
    Path("changes/raos-v2/phase-2/preview"),
    Path("changes/raos-v2/phase-3/generated"),
    Path("changes/raos-v2/phase-3/inputs"),
    Path("changes/raos-v2/phase-3/preview"),
    Path("changes/raos-v2/phase-3/wordpress/artifact"),
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
    Path("changes/raos-v2/phase-3/production-backup-export-runbook.md"),
    Path("changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase3-local-browser-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase3/" "preaction-public-20260828-v1.json"),
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


def _repository_regular_file_bytes(
    relative: Path,
    *,
    root: Path,
    maximum: int,
    code: str,
) -> bytes:
    """Read one repository file through no-follow directory descriptors."""

    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail(code)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_descriptor = -1
    try:
        directory_descriptor = os.open(root, directory_flags)
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
        try:
            opened = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or not 1 <= opened.st_size <= maximum
            ):
                fail(code)
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    fail(code)
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                fail(code)
            final = os.fstat(file_descriptor)
            if (
                final.st_dev != opened.st_dev
                or final.st_ino != opened.st_ino
                or final.st_nlink != 1
                or final.st_size != opened.st_size
                or final.st_mtime_ns != opened.st_mtime_ns
                or final.st_ctime_ns != opened.st_ctime_ns
            ):
                fail(code)
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except OSError:
        fail(code)
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _repository_directory_names(
    relative: Path, *, root: Path, code: str
) -> tuple[str, ...]:
    """List one repository directory through a stable no-follow descriptor."""

    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail(code)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_descriptor = -1
    try:
        directory_descriptor = os.open(root, directory_flags)
        for component in relative.parts:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        opened = os.fstat(directory_descriptor)
        names = os.listdir(directory_descriptor)
        final = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_ctime_ns != opened.st_ctime_ns
            or any(
                not isinstance(name, str) or name in {"", ".", ".."} or "/" in name
                for name in names
            )
        ):
            fail(code)
        return tuple(sorted(names))
    except OSError:
        fail(code)
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _contract_schema_documents(
    *, root: Path, code: str
) -> tuple[tuple[str, str, dict[str, object]], ...]:
    rows: list[tuple[str, str, dict[str, object]]] = []
    for version in ("v1", "v2"):
        directory = Path("contracts/raos-v2") / version
        for name in _repository_directory_names(directory, root=root, code=code):
            if not name.endswith(".schema.json"):
                continue
            relative = directory / name
            document = _mapping(
                load_json_strict(
                    _repository_regular_file_bytes(
                        relative,
                        root=root,
                        maximum=MAX_RESPONSE_BYTES,
                        code=code,
                    )
                ),
                code,
            )
            rows.append((version, name, document))
    if not rows:
        fail(code)
    return tuple(rows)


def _sanitized_resource_ref_sha256(value: str) -> str | None:
    """Hash a public resource origin/path/query without retaining raw values."""

    try:
        parsed = urlsplit(urljoin(PHASE3_PUBLIC_URL, value.strip()))
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    authority = parsed.hostname.casefold()
    if port is not None:
        authority += f":{port}"
    normalized = {
        "scheme": parsed.scheme.casefold(),
        "authority": authority,
        "path": parsed.path or "/",
        "query": parsed.query,
    }
    return sha256(canonical_json_bytes(normalized))


def _strict_navigation_host(value: str) -> tuple[bool, str | None]:
    """Match browser-relevant navigation authority or reject ambiguity."""

    text = value.strip()
    if any(ord(character) < 0x20 for character in text) or "\\" in text:
        return False, None
    try:
        direct = urlsplit(text)
        if direct.scheme.casefold() in {"mailto", "tel"}:
            return True, None
        parsed = urlsplit(urljoin(PHASE3_PUBLIC_URL, text))
        host = parsed.hostname
        _port = parsed.port
    except UnicodeError, ValueError:
        return False, None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or "%" in host
        or unquote(host) != host
        or host.endswith(".")
        or any(ord(character) > 0x7F for character in host)
        or unicodedata.normalize("NFKC", host) != host
    ):
        return False, None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False, None
    if ascii_host.casefold() != host.casefold():
        return False, None
    return True, ascii_host.casefold()


def verify_phase3_external_state(value: Mapping[str, object]) -> None:
    """Require the exact sanitized deny-default external-state shape."""

    code = "RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID"
    expected_sections: dict[str, dict[str, object]] = {
        "human_review": {
            "action_id": "OWNER-CONTENT-REVIEW",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "wordpress_export": {
            "external_action_id": "EXT-001",
            "status": "NOT_EXECUTED",
            "binding": None,
        },
        "post_action_wordpress_export": {
            "external_action_id": "V2-P3-EXT-POSTACTION-EXPORT",
            "status": "NOT_EXECUTED",
            "binding": None,
        },
        "wordpress_nonpublic_preview": {
            "external_action_id": "EXT-002",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "theme_or_plugin_deploy": {
            "external_action_id": "EXT-004",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "publication": {
            "external_action_id": "EXT-003",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "privacy_legal_review": {
            "external_action_id": "EXT-011",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "analytics_activation": {
            "external_action_id": "EXT-010",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "redirect_canonical_sitemap_change": {
            "external_action_id": "EXT-013",
            "status": "NOT_EXECUTED",
            "receipt": None,
        },
        "public_verification": {"status": "NOT_EXECUTED", "receipt": None},
    }
    if (
        set(value)
        != {
            "schema",
            "version",
            "classification",
            "target_origin",
            "target_route",
            "rule",
            *expected_sections,
            "stability_window",
        }
        or value.get("schema") != "RAOS_V2_PHASE3_EXTERNAL_ACTION_STATE_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification") != "SANITIZED_OVERLAY_INPUT"
        or value.get("target_origin") != ORIGIN
        or value.get("target_route") != PHASE3_PUBLIC_PATH
        or value.get("rule")
        != "Missing external evidence blocks the affected transition and is never treated as zero or success."
        or value.get("stability_window")
        != {"required_days": 7, "status": "NOT_STARTED", "receipt": None}
        or any(
            value.get(name) != section for name, section in expected_sections.items()
        )
    ):
        fail(code)


def verify_phase3_preaction_execution_input(
    value: Mapping[str, object], *, root: Path = ROOT
) -> dict[str, object]:
    """Verify the sanitized, raw-byte-derived input used to reissue Phase 3."""

    code = "RAOS_V2_PHASE3_PREACTION_EXECUTION_INPUT_INVALID"
    if set(value) != {
        "schema",
        "version",
        "classification",
        "status",
        "target",
        "pairing",
        "public_capture",
        "owner_export",
        "preaction_binding",
        "preaction_binding_sha256",
        "capabilities",
        "raw_values_persisted",
    } or (
        value.get("schema") != "RAOS_V2_PHASE3_PREACTION_EXECUTION_INPUT_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification") != "SANITIZED_DERIVED_INPUT_NO_RAW_EXPORT_BYTES"
        or value.get("status") != "VERIFIED_PREACTION_INPUT"
        or value.get("capabilities")
        != {
            "network": False,
            "wordpress_read": False,
            "wordpress_write": False,
            "publish": False,
        }
        or value.get("raw_values_persisted") is not False
    ):
        fail(code)
    target = _mapping(value.get("target"), code)
    if (
        set(target) != {"origin", "route", "kind", "post_id", "exact_match_count"}
        or target.get("origin") != ORIGIN
        or target.get("route") != PHASE3_PUBLIC_PATH
        or target.get("kind") != "EXISTING_POST"
        or type(target.get("post_id")) is not int
        or int(target["post_id"]) < 1
        or target.get("exact_match_count") != 1
    ):
        fail(code)
    pairing = _mapping(value.get("pairing"), code)
    delta = pairing.get("observed_delta_milliseconds")
    public_capture_age = pairing.get("public_capture_age_milliseconds")
    owner_export_age = pairing.get("owner_export_age_milliseconds")
    if (
        set(pairing)
        != {
            "maximum_age_seconds",
            "observed_delta_milliseconds",
            "evaluated_at",
            "public_capture_age_milliseconds",
            "owner_export_age_milliseconds",
            "status",
        }
        or pairing.get("maximum_age_seconds") != 300
        or type(delta) is not int
        or not 0 <= int(delta) <= 300_000
        or type(public_capture_age) is not int
        or not 0 <= int(public_capture_age) <= 300_000
        or type(owner_export_age) is not int
        or not 0 <= int(owner_export_age) <= 300_000
        or pairing.get("status") != "PAIRED_WITHIN_WINDOW"
    ):
        fail(code)
    public_capture = _mapping(value.get("public_capture"), code)
    if set(public_capture) != {
        "recorded_input",
        "semantic_sha256",
        "observed_at",
        "body_sha256",
    }:
        fail(code)
    relative_text = public_capture.get("recorded_input")
    if not isinstance(relative_text, str):
        fail(code)
    relative = Path(relative_text)
    allowed = PHASE3_RECORDED_ROOT.parts
    if (
        relative.is_absolute()
        or relative.parts[: len(allowed)] != allowed
        or len(relative.parts) != len(allowed) + 1
        or relative.suffix != ".json"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail(code)
    try:
        capture_value = load_json_strict(
            _repository_regular_file_bytes(
                relative,
                root=root,
                maximum=MAX_RESPONSE_BYTES,
                code=code,
            )
        )
    except ValidationFailure:
        fail(code)
    if not isinstance(capture_value, dict):
        fail(code)
    observation, _captured_at, observed_at = _phase3_capture_observation(
        capture_value, code=code
    )
    body_sha256 = observation.get("body_sha256")
    if (
        observation.get("status") != 200
        or observation.get("redirect_chain") != []
        or observation.get("canonical") != PHASE3_PUBLIC_URL
        or observation.get("canonical_tag_count") != 1
        or observation.get("sitemap_membership") is not True
        or observation.get("body_storage") != "DISCARDED_AFTER_HASH"
        or public_capture.get("semantic_sha256") != _semantic_digest(capture_value)
        or public_capture.get("observed_at") != observed_at.isoformat()
        or public_capture.get("body_sha256") != body_sha256
    ):
        fail(code)
    owner = _mapping(value.get("owner_export"), code)
    if set(owner) != {
        "captured_at",
        "raw_export_location",
        "raw_export_sha256",
        "raw_export_bytes",
        "field_hashes",
        "legacy_post_content_sha256",
        "restore_completeness",
        "wordpress_environment",
        "artifacts",
    }:
        fail(code)
    try:
        owner_at = datetime.fromisoformat(str(owner.get("captured_at")))
        evaluated_at = datetime.fromisoformat(str(pairing.get("evaluated_at")))
    except ValueError:
        fail(code)
    if (
        owner_at.tzinfo is None
        or owner_at.utcoffset() is None
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
        or abs(int((owner_at - observed_at).total_seconds() * 1000)) != delta
        or int((evaluated_at - observed_at).total_seconds() * 1000)
        != public_capture_age
        or int((evaluated_at - owner_at).total_seconds() * 1000) != owner_export_age
        or owner.get("raw_export_location") != "OWNER_STORAGE_ONLY_NOT_GIT"
        or not isinstance(owner.get("raw_export_sha256"), str)
        or HEX64.fullmatch(str(owner.get("raw_export_sha256"))) is None
        or type(owner.get("raw_export_bytes")) is not int
        or int(owner["raw_export_bytes"]) < 1
        or not isinstance(owner.get("legacy_post_content_sha256"), str)
        or HEX64.fullmatch(str(owner.get("legacy_post_content_sha256"))) is None
    ):
        fail(code)
    field_hashes = _mapping(owner.get("field_hashes"), code)
    if (
        set(field_hashes) != PHASE3_WORDPRESS_FIELD_NAMES
        or any(
            not isinstance(item, str) or HEX64.fullmatch(item) is None
            for item in field_hashes.values()
        )
        or field_hashes.get("post_status")
        != _semantic_digest({"field": "post_status", "value": "publish"})
    ):
        fail(code)
    restore = _mapping(owner.get("restore_completeness"), code)
    expected_restore = {
        "author",
        "comment_status",
        "content",
        "excerpt",
        "featured_media",
        "modified_at",
        "ping_status",
        "published_at",
        "seo_fields",
        "slug",
        "status",
        "taxonomy",
        "title",
    }
    if set(restore) != expected_restore or any(
        item is not True for item in restore.values()
    ):
        fail(code)
    environment = _mapping(owner.get("wordpress_environment"), code)
    theme = _mapping(environment.get("active_theme"), code)
    plugins = environment.get("relevant_plugins")
    version_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    slug_pattern = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
    if (
        set(environment)
        != {"wordpress_core_version", "active_theme", "relevant_plugins"}
        or not isinstance(environment.get("wordpress_core_version"), str)
        or version_pattern.fullmatch(environment["wordpress_core_version"]) is None
        or set(theme) != {"slug", "version"}
        or not isinstance(theme.get("slug"), str)
        or slug_pattern.fullmatch(theme["slug"]) is None
        or not isinstance(theme.get("version"), str)
        or version_pattern.fullmatch(theme["version"]) is None
        or not isinstance(plugins, list)
    ):
        fail(code)
    plugin_slugs: list[str] = []
    for plugin in plugins:
        row = _mapping(plugin, code)
        if (
            set(row) != {"slug", "version"}
            or not isinstance(row.get("slug"), str)
            or slug_pattern.fullmatch(row["slug"]) is None
            or not isinstance(row.get("version"), str)
            or version_pattern.fullmatch(row["version"]) is None
        ):
            fail(code)
        plugin_slugs.append(row["slug"])
    if plugin_slugs != sorted(set(plugin_slugs)):
        fail(code)
    artifacts = _mapping(owner.get("artifacts"), code)
    if set(artifacts) != {
        "redirect_map",
        "restore_artifact",
        "seo_state",
        "sitemap_state",
        "theme_plugin_artifact",
    }:
        fail(code)
    for artifact in artifacts.values():
        row = _mapping(artifact, code)
        if (
            set(row) != {"bytes", "sha256"}
            or type(row.get("bytes")) is not int
            or int(row["bytes"]) < 1
            or not isinstance(row.get("sha256"), str)
            or HEX64.fullmatch(str(row.get("sha256"))) is None
        ):
            fail(code)
    binding = _mapping(value.get("preaction_binding"), code)
    if (
        set(binding)
        != {
            "schema",
            "version",
            "status",
            "provenance",
            "captured_at",
            "target",
            "current_public_body_sha256",
            "public_capture_sha256",
            "wordpress_export_sha256",
            "wordpress_export_bytes",
            "owner_evidence_sha256",
            "legacy_post_content_sha256",
        }
        or binding.get("schema") != "RAOS_V2_PHASE3_PREACTION_BINDING_V1"
        or binding.get("version") != "1.0.0"
        or binding.get("status") != "VERIFIED_PREACTION"
        or binding.get("provenance")
        != "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT"
        or binding.get("target") != target
        or binding.get("captured_at") != max(observed_at, owner_at).isoformat()
        or binding.get("current_public_body_sha256") != body_sha256
        or binding.get("public_capture_sha256") != public_capture.get("semantic_sha256")
        or binding.get("wordpress_export_sha256") != owner.get("raw_export_sha256")
        or binding.get("wordpress_export_bytes") != owner.get("raw_export_bytes")
        or binding.get("legacy_post_content_sha256")
        != owner.get("legacy_post_content_sha256")
        or binding.get("owner_evidence_sha256")
        != _semantic_digest(
            {
                "field_hashes": field_hashes,
                "legacy_post_content_sha256": owner.get("legacy_post_content_sha256"),
                "restore_completeness": restore,
                "wordpress_environment": environment,
                "artifacts": artifacts,
            }
        )
        or value.get("preaction_binding_sha256") != _semantic_digest(binding)
    ):
        fail(code)
    schema_relative = Path("contracts/raos-v2/v2/preaction-binding.schema.json")
    try:
        from scripts import build_raos_v2_successor as successor_builder
    except ModuleNotFoundError:
        import build_raos_v2_successor as successor_builder  # type: ignore[no-redef]
    try:
        schema_document = _mapping(
            load_json_strict(
                _repository_regular_file_bytes(
                    schema_relative,
                    root=root,
                    maximum=MAX_RESPONSE_BYTES,
                    code=code,
                )
            ),
            code,
        )
        if schema_document != successor_builder.phase3_preaction_binding_schema():
            fail(code)
        Draft202012Validator.check_schema(schema_document)
        schema_errors = list(
            Draft202012Validator(
                schema_document, format_checker=FormatChecker()
            ).iter_errors(binding)
        )
    except Exception as exc:
        if isinstance(exc, ValidationFailure):
            raise
        fail(code)
    if schema_errors:
        fail(code)
    return {
        "status": "VERIFIED_PREACTION_INPUT",
        "preaction_binding_sha256": value["preaction_binding_sha256"],
        "post_id": target["post_id"],
        "raw_values_persisted": False,
    }


def verify_phase3_reissued_review_bundle(
    value: Mapping[str, object], *, root: Path = ROOT
) -> dict[str, object]:
    """Independently bind a reissued candidate to current generator inputs."""

    code = "RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_INVALID"
    expected_keys = {
        "schema",
        "version",
        "classification",
        "state",
        "reissued_at",
        "reissue_age_milliseconds",
        "public_capture_age_milliseconds",
        "owner_export_age_milliseconds",
        "maximum_reissue_age_seconds",
        "source",
        "review_candidate",
        "candidate_digest",
        "payload_digest",
        "review_request",
        "capabilities",
        "external_actions",
        "review_bundle_sha256",
    }
    if (
        set(value) != expected_keys
        or value.get("schema") != "RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification")
        != "LOCAL_REISSUE_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"
        or value.get("state") != "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"
        or value.get("maximum_reissue_age_seconds") != 300
        or value.get("capabilities")
        != {
            "network": False,
            "wordpress_read": False,
            "wordpress_write": False,
            "publish": False,
        }
        or value.get("external_actions") != "NOT_EXECUTED"
    ):
        fail(code)

    schema_relative = Path("contracts/raos-v2/v2/reissued-review-bundle.schema.json")
    try:
        from scripts import build_raos_v2_successor as successor_builder
    except ModuleNotFoundError:
        import build_raos_v2_successor as successor_builder  # type: ignore[no-redef]
    try:
        schema_document = _mapping(
            load_json_strict(
                _repository_regular_file_bytes(
                    schema_relative,
                    root=root,
                    maximum=MAX_RESPONSE_BYTES,
                    code=code,
                )
            ),
            code,
        )
        expected_schema = successor_builder.phase3_reissued_review_bundle_schema()
        if schema_document != expected_schema:
            fail(code)
        registry = Registry()
        for _version, _name, document in _contract_schema_documents(
            root=root, code=code
        ):
            Draft202012Validator.check_schema(document)
            identifier = document.get("$id")
            if not isinstance(identifier, str):
                fail(code)
            registry = registry.with_resource(
                identifier, Resource.from_contents(document)
            )
        schema_errors = list(
            Draft202012Validator(
                schema_document,
                registry=registry,
                format_checker=FormatChecker(),
            ).iter_errors(value)
        )
    except Exception as exc:
        if isinstance(exc, ValidationFailure):
            raise
        fail(code)
    if schema_errors:
        fail(code)
    unsigned = dict(value)
    bundle_digest = unsigned.pop("review_bundle_sha256", None)
    if (
        not isinstance(bundle_digest, str)
        or HEX64.fullmatch(bundle_digest) is None
        or bundle_digest != _semantic_digest(unsigned)
    ):
        fail(code)
    try:
        reissued_at = datetime.fromisoformat(str(value.get("reissued_at")))
    except ValueError:
        fail(code)
    if reissued_at.tzinfo is None or reissued_at.utcoffset() is None:
        fail(code)
    source = _mapping(value.get("source"), code)
    if set(source) != {
        "historical_review_candidate",
        "historical_review_candidate_sha256",
        "preaction_input",
        "preaction_input_sha256",
        "preaction_binding_sha256",
    } or source.get("historical_review_candidate") != (
        "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
    ):
        fail(code)
    preaction_path_value = source.get("preaction_input")
    if not isinstance(preaction_path_value, str):
        fail(code)
    preaction_path = Path(preaction_path_value)
    allowed = PHASE3_RECORDED_ROOT.parts
    if (
        preaction_path.is_absolute()
        or preaction_path.parts[: len(allowed)] != allowed
        or len(preaction_path.parts) != len(allowed) + 1
        or preaction_path.suffix != ".json"
        or any(part in {"", ".", ".."} for part in preaction_path.parts)
    ):
        fail(code)
    try:
        preaction_value = load_json_strict(
            _repository_regular_file_bytes(
                preaction_path,
                root=root,
                maximum=MAX_RESPONSE_BYTES,
                code=code,
            )
        )
    except ValidationFailure:
        fail(code)
    if not isinstance(preaction_value, dict):
        fail(code)
    verified_preaction = verify_phase3_preaction_execution_input(
        preaction_value, root=root
    )
    binding = _mapping(preaction_value.get("preaction_binding"), code)
    if source.get("preaction_input_sha256") != _semantic_digest(
        preaction_value
    ) or source.get("preaction_binding_sha256") != verified_preaction.get(
        "preaction_binding_sha256"
    ):
        fail(code)
    public_record = _mapping(preaction_value.get("public_capture"), code)
    owner_record = _mapping(preaction_value.get("owner_export"), code)
    try:
        public_at = datetime.fromisoformat(str(public_record.get("observed_at")))
        owner_at = datetime.fromisoformat(str(owner_record.get("captured_at")))
    except ValueError:
        fail(code)
    if any(
        instant.tzinfo is None or instant.utcoffset() is None
        for instant in (public_at, owner_at)
    ):
        fail(code)
    public_age = int((reissued_at - public_at).total_seconds() * 1000)
    owner_age = int((reissued_at - owner_at).total_seconds() * 1000)
    if (
        type(value.get("public_capture_age_milliseconds")) is not int
        or value.get("public_capture_age_milliseconds") != public_age
        or not 0 <= public_age <= 300_000
        or type(value.get("owner_export_age_milliseconds")) is not int
        or value.get("owner_export_age_milliseconds") != owner_age
        or not 0 <= owner_age <= 300_000
        or type(value.get("reissue_age_milliseconds")) is not int
        or value.get("reissue_age_milliseconds") != max(public_age, owner_age)
    ):
        fail(code)
    try:
        current_historical = (
            successor_builder.current_phase3_historical_review_candidate_document()
        )
    except successor_builder.BuildFailure:
        fail(code)
    historical_relative = Path(str(source["historical_review_candidate"]))
    try:
        historical_bytes = _repository_regular_file_bytes(
            historical_relative,
            root=root,
            maximum=MAX_RESPONSE_BYTES,
            code=code,
        )
    except ValidationFailure:
        fail(code)
    if historical_bytes != canonical_json_bytes(current_historical) or source.get(
        "historical_review_candidate_sha256"
    ) != sha256(historical_bytes):
        fail(code)
    expected_candidate = deepcopy(current_historical)
    update = _mapping(expected_candidate.get("update_payload"), code)
    target = _mapping(update.get("target"), code)
    binding_digest = _semantic_digest(binding)
    target["expected_public_body_sha256"] = binding.get("current_public_body_sha256")
    update["preaction"] = {
        "status": "VERIFIED_PREACTION",
        "binding_digest": binding_digest,
        "binding": binding,
    }
    expected_candidate["preaction_status"] = "VERIFIED_PREACTION"
    expected_candidate["preaction_binding_digest"] = binding_digest
    expected_candidate["payload_digest"] = _semantic_digest(update)
    candidate = _mapping(value.get("review_candidate"), code)
    candidate_digest = candidate.get("candidate_digest")
    payload_digest = candidate.get("payload_digest")
    review_request = _mapping(value.get("review_request"), code)
    if (
        candidate != expected_candidate
        or value.get("candidate_digest") != candidate_digest
        or value.get("payload_digest") != payload_digest
        or review_request
        != {
            "required_receipt_schema": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1",
            "candidate_digest": candidate_digest,
            "payload_digest": payload_digest,
            "target_route": PHASE3_PUBLIC_PATH,
            "generic_approval_accepted": False,
            "artifact_specific_review_required": True,
        }
    ):
        fail(code)
    bindings = _rows(candidate.get("claim_bindings"), code)
    for claim in bindings:
        try:
            checked_at = datetime.fromisoformat(str(claim.get("checked_at")))
            next_review_at = datetime.fromisoformat(str(claim.get("next_review_at")))
        except ValueError:
            fail(code)
        if not checked_at <= reissued_at < next_review_at:
            fail("RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_STALE")
    return {
        "state": "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW",
        "candidate_digest": candidate_digest,
        "payload_digest": payload_digest,
        "preaction_binding_sha256": binding_digest,
    }


def verify_phase3_wordpress_cutover_binding(
    value: Mapping[str, object],
    *,
    sealed_package: Mapping[str, object],
    review_bundle: Mapping[str, object],
    root: Path = ROOT,
) -> dict[str, object]:
    """Verify the activation-before-write guard against one sealed package."""

    code = "RAOS_V2_PHASE3_WORDPRESS_CUTOVER_BINDING_INVALID"
    schema_relative = Path("contracts/raos-v2/v2/wordpress-cutover-binding.schema.json")
    try:
        from scripts import build_raos_v2_successor as successor_builder
    except ModuleNotFoundError:
        import build_raos_v2_successor as successor_builder  # type: ignore[no-redef]
    try:
        schema_document = _mapping(
            load_json_strict(
                _repository_regular_file_bytes(
                    schema_relative,
                    root=root,
                    maximum=MAX_RESPONSE_BYTES,
                    code=code,
                )
            ),
            code,
        )
        if (
            schema_document
            != successor_builder.phase3_wordpress_cutover_binding_schema()
        ):
            fail(code)
        Draft202012Validator.check_schema(schema_document)
        errors = list(
            Draft202012Validator(
                schema_document, format_checker=FormatChecker()
            ).iter_errors(value)
        )
    except Exception as exc:
        if isinstance(exc, ValidationFailure):
            raise
        fail(code)
    if errors:
        fail(code)
    try:
        verify_phase3_reissued_review_bundle(review_bundle, root=root)
    except ValidationFailure:
        fail(code)
    try:
        from scripts import raos_v2_phase3_execution as phase3_operator
    except ModuleNotFoundError:
        import raos_v2_phase3_execution as phase3_operator  # type: ignore[no-redef]
    try:
        semantic_verification = phase3_operator.verify_phase3_sealed_package_semantics(
            sealed_package,
            review_bundle=review_bundle,
            root=root,
        )
    except phase3_operator.Phase3ExecutionFailure:
        fail(code)
    if (
        semantic_verification.get("state") != "PACKAGE_SEALED"
        or semantic_verification.get("simulation_only") is not True
        or semantic_verification.get("acceptance_authority") is not False
        or semantic_verification.get("phase_exit") != "BLOCKED_EXTERNAL"
        or semantic_verification.get("public_write_authority") is not False
    ):
        fail(code)
    # This verifier has no authenticated artifact-specific approval source and
    # accepts neither a post-review PRE_WRITE_EXPORT nor a disabled-plugin
    # dry-run receipt.  It therefore cannot certify an ARMED binding even when
    # the local simulation package itself is semantically valid.
    fail("RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED")


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
            for pattern in ("*.py", "*.mjs", "*.php")
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


def _git_head_and_ancestry(executed_head: str, *, root: Path) -> tuple[str, bool]:
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
    _current_head, head_is_ancestor = _git_head_and_ancestry(executed_head, root=root)
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
        if len(raw_payload) != raw_binding.get("bytes") or sha256(
            raw_payload
        ) != raw_binding.get("sha256"):
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
        or value.get("schema") != "RAOS_V2_RECORDED_VISUAL_REVIEW_EVIDENCE_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification") != "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
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
        or capture_binding.get("schema") != "RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1"
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
    if len(harness_payload) != capture_binding.get("harness_bytes") or sha256(
        harness_payload
    ) != capture_binding.get("harness_sha256"):
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
    if len(canonical_subset) != capture_binding.get(
        "capture_rows_canonical_bytes"
    ) or sha256(canonical_subset) != capture_binding.get(
        "capture_rows_canonical_sha256"
    ):
        fail("RAOS_V2_VISUAL_CAPTURE_SUBSET_DRIFT")

    raw_path = root / VISUAL_RAW_RECEIPT_PATH
    raw_status = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists():
        raw_payload = _read_local_evidence_file(raw_path, root=root)
        if len(raw_payload) != capture_binding.get("bytes") or sha256(
            raw_payload
        ) != capture_binding.get("sha256"):
            fail("RAOS_V2_VISUAL_RAW_RECEIPT_DRIFT")
        raw = load_json_strict(raw_payload)
        if not isinstance(raw, Mapping):
            fail("RAOS_V2_VISUAL_RAW_RECEIPT_INVALID")
        raw_captures = raw.get("captures")
        if (
            raw.get("schema") != "RAOS_V2_LOCAL_VISUAL_CAPTURE_RECEIPT_V1"
            or raw.get("classification") != "PENDING_LOCAL_VISUAL_REVIEW"
            or raw.get("reviewBoundary") != "MANUAL_REVIEW_REQUIRED_SEPARATE_RECORD"
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
                or raw_row.get("reviewStatus") != "PENDING_SEPARATE_MANUAL_REVIEW"
                or raw_row.get("criticalFindings") is not None
                or raw_row.get("majorFindings") is not None
            ):
                fail("RAOS_V2_VISUAL_RAW_CAPTURE_SET_DRIFT")
            image_path = root / str(review["screenshot_path"])
            image_payload = _read_local_evidence_file(image_path, root=root)
            if len(image_payload) != review.get("screenshot_bytes") or sha256(
                image_payload
            ) != review.get("screenshot_sha256"):
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


def _phase3_png_dimensions(payload: bytes) -> tuple[int, int]:
    """Read the PNG IHDR dimensions without invoking an image decoder."""

    if (
        len(payload) < 24
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
    ):
        fail("RAOS_V2_PHASE3_BROWSER_CAPTURE_INVALID")
    return (
        int.from_bytes(payload[16:20], "big"),
        int.from_bytes(payload[20:24], "big"),
    )


def verify_phase3_local_browser_evidence(
    value: Mapping[str, object],
    *,
    expected_preview: bytes,
    root: Path = ROOT,
    require_raw: bool = False,
) -> dict[str, object]:
    """Verify Phase 3 local browser and separate visual-review evidence.

    The tracked record remains local-only. CI can validate its current-tree
    bindings without treating an absent ignored browser receipt as production
    evidence.
    """

    code = "RAOS_V2_PHASE3_BROWSER_EVIDENCE_INVALID"
    expected_root_keys = {
        "schema",
        "version",
        "recorded_date_jst",
        "recorded_at_jst",
        "classification",
        "raw_receipt",
        "receipt",
        "manual_visual_review",
        "external_actions",
        "public_evidence",
        "formal_ci",
        "ci_behavior",
    }
    if (
        set(value) != expected_root_keys
        or value.get("schema") != "RAOS_V2_RECORDED_PHASE3_LOCAL_BROWSER_EVIDENCE_V1"
        or value.get("version") != "1.0.0"
        or value.get("classification") != "PASSED_LOCAL_ASSEMBLY_SIMULATION"
        or value.get("external_actions") != "NOT_EXECUTED"
        or value.get("public_evidence") != "NOT_CLAIMED"
        or value.get("formal_ci") != "NOT_CLAIMED"
        or value.get("ci_behavior")
        != "VERIFY_COMMITTED_RECEIPT_AND_CURRENT_TREE_BINDINGS_WHEN_RAW_LOCAL_FILES_ARE_ABSENT"
    ):
        fail(code)
    recorded_at = value.get("recorded_at_jst")
    if not isinstance(recorded_at, str) or not recorded_at.endswith("+09:00"):
        fail(code)
    try:
        recorded_instant = datetime.fromisoformat(recorded_at)
    except ValueError:
        fail(code)
    if (
        recorded_instant.tzinfo is None
        or recorded_instant.utcoffset() is None
        or recorded_instant > datetime.now(ZoneInfo("Asia/Tokyo"))
        or value.get("recorded_date_jst") != recorded_instant.date().isoformat()
    ):
        fail(code)

    raw_binding = _mapping(value.get("raw_receipt"), code)
    receipt = _mapping(value.get("receipt"), code)
    manual = _mapping(value.get("manual_visual_review"), code)
    if (
        set(raw_binding) != {"local_path", "sha256", "bytes", "exit_status", "tracked"}
        or raw_binding.get("local_path") != PHASE3_BROWSER_RAW_RECEIPT_PATH.as_posix()
        or raw_binding.get("exit_status") != 0
        or raw_binding.get("tracked") is not False
        or not isinstance(raw_binding.get("bytes"), int)
        or isinstance(raw_binding.get("bytes"), bool)
        or int(raw_binding.get("bytes", 0)) <= 0
        or not isinstance(raw_binding.get("sha256"), str)
        or not HEX64.fullmatch(str(raw_binding.get("sha256")))
    ):
        fail(code)

    expected_receipt_keys = {
        "accessibility",
        "assemblyClassification",
        "assertions",
        "browser",
        "classification",
        "commandContract",
        "externalActions",
        "harness",
        "keyboard",
        "media",
        "network",
        "persistence",
        "preview",
        "publicEvidence",
        "runtime",
        "schema",
        "supportHarness",
        "targetRoute",
        "visualCaptures",
        "visualReview",
        "viewports",
    }
    if (
        set(receipt) != expected_receipt_keys
        or receipt.get("schema") != "RAOS_V2_PHASE3_LOCAL_BROWSER_EVIDENCE_V1"
        or receipt.get("classification") != "PASSED_LOCAL_ASSEMBLY_SIMULATION"
        or receipt.get("assemblyClassification")
        != "LOCAL_WORDPRESS_ASSEMBLY_SIMULATION"
        or receipt.get("commandContract")
        != "NODE24_LOCAL_CDP_AXE_PHASE3_WORDPRESS_ASSEMBLY_SANITIZED_RECEIPT_V1"
        or receipt.get("targetRoute") != PHASE3_PUBLIC_PATH
        or receipt.get("externalActions") != "NOT_EXECUTED"
        or receipt.get("publicEvidence") != "NOT_CLAIMED"
        or receipt.get("visualReview") != "PENDING_SEPARATE_MANUAL_REVIEW"
    ):
        fail(code)

    assertions = _mapping(receipt.get("assertions"), code)
    if assertions != {
        "affiliateUrls": 0,
        "axeIncomplete": 0,
        "axeRuns": 4,
        "axeViolations": 0,
        "blockedCtas": 3,
        "externalResources": 0,
        "h1Count": 1,
        "horizontalOverflow": 0,
        "images": 0,
        "inlineScripts": 0,
        "reflowEquivalentZoomPercent": 400,
        "viewports": [320, 390, 768, 1440],
    }:
        fail(code)
    if _mapping(receipt.get("network"), code) != {
        "outboundRequests": 0,
        "resourceRequests": 0,
    } or any(
        amount != 0 for amount in _mapping(receipt.get("persistence"), code).values()
    ):
        fail(code)
    if _mapping(receipt.get("keyboard"), code) != {
        "focusableCount": 7,
        "focusRingMinimumPx": 3,
        "focusTraversal": True,
        "mainFocused": True,
        "skipLinkFirst": True,
    } or _mapping(receipt.get("media"), code) != {
        "forcedColors": True,
        "maximumMotionSeconds": 0,
        "reducedMotion": True,
        "zoom200Percent": True,
    }:
        fail(code)
    accessibility = _mapping(receipt.get("accessibility"), code)
    if (
        set(accessibility)
        != {
            "levelOneHeadings",
            "nodeCount",
            "screenReaderSmoke",
            "structuralSha256",
            "unnamedInteractive",
        }
        or accessibility.get("levelOneHeadings") != 1
        or not isinstance(accessibility.get("nodeCount"), int)
        or isinstance(accessibility.get("nodeCount"), bool)
        or int(accessibility.get("nodeCount", 0)) <= 0
        or accessibility.get("screenReaderSmoke") is not True
        or accessibility.get("unnamedInteractive") != 0
        or not isinstance(accessibility.get("structuralSha256"), str)
        or not HEX64.fullmatch(str(accessibility.get("structuralSha256")))
    ):
        fail(code)

    preview = _mapping(receipt.get("preview"), code)
    if preview != {
        "bytes": len(expected_preview),
        "path": PHASE3_BROWSER_PREVIEW_PATH.as_posix(),
        "sha256": sha256(expected_preview),
    }:
        fail("RAOS_V2_PHASE3_BROWSER_PREVIEW_DRIFT")
    for key, expected_path in (
        ("harness", PHASE3_BROWSER_HARNESS_PATH),
        ("supportHarness", PHASE3_BROWSER_SUPPORT_HARNESS_PATH),
    ):
        binding = _mapping(receipt.get(key), code)
        if (
            set(binding) != {"bytes", "path", "sha256"}
            or binding.get("path") != expected_path.as_posix()
        ):
            fail(code)
        try:
            payload = _read_local_evidence_file(root / expected_path, root=root)
        except ValidationFailure:
            fail("RAOS_V2_PHASE3_BROWSER_HARNESS_INVALID")
        if len(payload) != binding.get("bytes") or sha256(payload) != binding.get(
            "sha256"
        ):
            fail("RAOS_V2_PHASE3_BROWSER_HARNESS_DRIFT")

    browser = _mapping(receipt.get("browser"), code)
    runtime = _mapping(receipt.get("runtime"), code)
    if (
        set(browser) != {"executableSha256", "version"}
        or not isinstance(browser.get("version"), str)
        or not str(browser.get("version"))
        or not isinstance(browser.get("executableSha256"), str)
        or not HEX64.fullmatch(str(browser.get("executableSha256")))
        or set(runtime) != {"executableSha256", "nodeMajor", "nodeVersion"}
        or runtime.get("nodeMajor") != 24
        or not isinstance(runtime.get("nodeVersion"), str)
        or not str(runtime.get("nodeVersion", "")).startswith("24.")
        or not isinstance(runtime.get("executableSha256"), str)
        or not HEX64.fullmatch(str(runtime.get("executableSha256")))
    ):
        fail(code)

    viewports = _mapping(receipt.get("viewports"), code)
    expected_viewports = {
        "reflow-320": (320, 800, 1, "CARDS", None),
        "mobile-390": (390, 844, 1, "CARDS", None),
        "tablet-768": (768, 1024, 1, "TABLE", True),
        "desktop-1440": (1440, 900, 3, "TABLE", False),
    }
    if set(viewports) != set(expected_viewports):
        fail(code)
    for name, (
        width,
        height,
        columns,
        mode,
        table_contained,
    ) in expected_viewports.items():
        audit = _mapping(viewports.get(name), code)
        if audit != {
            "axeIncomplete": 0,
            "axeViolations": 0,
            "blockedCtas": 3,
            "gridColumns": columns,
            "height": height,
            "horizontalOverflow": False,
            "comparisonMode": mode,
            "tableOverflowContained": table_contained,
            "width": width,
        }:
            fail(code)

    captures = receipt.get("visualCaptures")
    if not isinstance(captures, list) or len(captures) != 3:
        fail(code)
    expected_capture_paths = {
        390: (
            "output/playwright/raos-v2-phase3-local-browser-evidence-captures/"
            "carry-on-suitcase-comparison__390.png"
        ),
        768: (
            "output/playwright/raos-v2-phase3-local-browser-evidence-captures/"
            "carry-on-suitcase-comparison__768.png"
        ),
        1440: (
            "output/playwright/raos-v2-phase3-local-browser-evidence-captures/"
            "carry-on-suitcase-comparison__1440.png"
        ),
    }
    observed_widths: set[int] = set()
    capture_hashes: list[str] = []
    for capture in captures:
        row = _mapping(capture, code)
        width = row.get("width")
        digest = row.get("sha256")
        if (
            set(row) != {"bytes", "height", "path", "sha256", "width"}
            or not isinstance(width, int)
            or isinstance(width, bool)
            or width not in expected_capture_paths
            or width in observed_widths
            or row.get("path") != expected_capture_paths[width]
            or not isinstance(row.get("height"), int)
            or isinstance(row.get("height"), bool)
            or int(row.get("height", 0)) <= 0
            or not isinstance(row.get("bytes"), int)
            or isinstance(row.get("bytes"), bool)
            or int(row.get("bytes", 0)) <= 0
            or not isinstance(digest, str)
            or not HEX64.fullmatch(digest)
        ):
            fail(code)
        observed_widths.add(width)
        capture_hashes.append(digest)
    if observed_widths != set(expected_capture_paths):
        fail(code)

    expected_manual_keys = {
        "classification",
        "reviewer_class",
        "reviewed_at_jst",
        "reviewed_viewports",
        "reviewed_capture_sha256",
        "findings",
        "checks",
    }
    if (
        set(manual) != expected_manual_keys
        or manual.get("classification") != "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
        or manual.get("reviewer_class") != "CODEX_MANUAL_VISUAL_REVIEW"
        or manual.get("reviewed_at_jst") != recorded_at
        or manual.get("reviewed_viewports") != [390, 768, 1440]
        or manual.get("reviewed_capture_sha256") != capture_hashes
        or _mapping(manual.get("findings"), code) != {"critical": 0, "major": 0}
        or _mapping(manual.get("checks"), code)
        != {
            "content_hierarchy_clear": True,
            "cta_blocked_state_clear": True,
            "mobile_cards_readable": True,
            "tablet_table_contained": True,
            "desktop_grid_readable": True,
            "official_editorial_unknown_labels_visible": True,
            "horizontal_clipping_observed": False,
        }
    ):
        fail(code)

    raw_path = root / PHASE3_BROWSER_RAW_RECEIPT_PATH
    raw_status = "RECORDED_NOT_REVERIFIED"
    capture_status = "RECORDED_HASHES_NOT_REVERIFIED"
    if raw_path.exists() or raw_path.is_symlink():
        raw_payload = _read_local_evidence_file(raw_path, root=root)
        if len(raw_payload) != raw_binding.get("bytes") or sha256(
            raw_payload
        ) != raw_binding.get("sha256"):
            fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_DRIFT")
        raw_value = load_json_strict(raw_payload)
        if raw_value != receipt:
            fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_INVALID")
        raw_status = "RAW_RECEIPT_VERIFIED_LOCAL"
        for capture in captures:
            assert isinstance(capture, Mapping)
            image_path = root / str(capture["path"])
            image_payload = _read_local_evidence_file(image_path, root=root)
            if (
                len(image_payload) != capture.get("bytes")
                or sha256(image_payload) != capture.get("sha256")
                or _phase3_png_dimensions(image_payload)
                != (capture.get("width"), capture.get("height"))
            ):
                fail("RAOS_V2_PHASE3_BROWSER_CAPTURE_DRIFT")
        capture_status = "THREE_PNGS_VERIFIED_LOCAL"
    elif require_raw:
        fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_MISSING")
    elif any(
        (root / path).exists() or (root / path).is_symlink()
        for path in expected_capture_paths.values()
    ):
        fail("RAOS_V2_PHASE3_BROWSER_CAPTURE_WITHOUT_RECEIPT")
    return {
        "effective_status": "PASSED_LOCAL_ASSEMBLY_SIMULATION",
        "current_tree_binding": "CURRENT_PREVIEW_AND_HARNESS_BOUND",
        "raw_verification": raw_status,
        "capture_verification": capture_status,
        "manual_visual_review": "PASSED_LOCAL_MANUAL_VISUAL_REVIEW",
        "critical_findings": 0,
        "major_findings": 0,
        "external_actions": "NOT_EXECUTED",
        "public_evidence": "NOT_CLAIMED",
    }


def record_phase3_local_browser_evidence(
    *,
    root: Path = ROOT,
    visual_review_confirmed: bool,
    reviewed_at: datetime | None = None,
) -> dict[str, object]:
    """Bind a successful raw harness receipt to an explicit visual review."""

    if visual_review_confirmed is not True:
        fail("RAOS_V2_PHASE3_VISUAL_REVIEW_CONFIRMATION_REQUIRED")
    raw_path = root / PHASE3_BROWSER_RAW_RECEIPT_PATH
    raw_payload = _read_local_evidence_file(raw_path, root=root)
    raw_value = load_json_strict(raw_payload)
    if not isinstance(raw_value, dict):
        fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_INVALID")
    captures = raw_value.get("visualCaptures")
    if not isinstance(captures, list) or len(captures) != 3:
        fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_INVALID")
    expected_widths = [390, 768, 1440]
    capture_hashes: list[str] = []
    for expected_width, capture_value in zip(expected_widths, captures, strict=True):
        capture = _mapping(capture_value, "RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_INVALID")
        digest = capture.get("sha256")
        path_value = capture.get("path")
        if (
            capture.get("width") != expected_width
            or not isinstance(path_value, str)
            or not isinstance(digest, str)
            or HEX64.fullmatch(digest) is None
        ):
            fail("RAOS_V2_PHASE3_BROWSER_RAW_RECEIPT_INVALID")
        image_payload = _read_local_evidence_file(root / path_value, root=root)
        if (
            len(image_payload) != capture.get("bytes")
            or sha256(image_payload) != digest
            or _phase3_png_dimensions(image_payload)
            != (capture.get("width"), capture.get("height"))
        ):
            fail("RAOS_V2_PHASE3_BROWSER_CAPTURE_DRIFT")
        capture_hashes.append(digest)
    instant = reviewed_at or datetime.now(ZoneInfo("Asia/Tokyo"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        fail("RAOS_V2_PHASE3_VISUAL_REVIEW_TIME_INVALID")
    instant_jst = instant.astimezone(ZoneInfo("Asia/Tokyo"))
    document: dict[str, object] = {
        "schema": "RAOS_V2_RECORDED_PHASE3_LOCAL_BROWSER_EVIDENCE_V1",
        "version": "1.0.0",
        "recorded_date_jst": instant_jst.date().isoformat(),
        "recorded_at_jst": instant_jst.isoformat(),
        "classification": "PASSED_LOCAL_ASSEMBLY_SIMULATION",
        "raw_receipt": {
            "local_path": PHASE3_BROWSER_RAW_RECEIPT_PATH.as_posix(),
            "sha256": sha256(raw_payload),
            "bytes": len(raw_payload),
            "exit_status": 0,
            "tracked": False,
        },
        "receipt": raw_value,
        "manual_visual_review": {
            "classification": "PASSED_LOCAL_MANUAL_VISUAL_REVIEW",
            "reviewer_class": "CODEX_MANUAL_VISUAL_REVIEW",
            "reviewed_at_jst": instant_jst.isoformat(),
            "reviewed_viewports": expected_widths,
            "reviewed_capture_sha256": capture_hashes,
            "findings": {"critical": 0, "major": 0},
            "checks": {
                "content_hierarchy_clear": True,
                "cta_blocked_state_clear": True,
                "mobile_cards_readable": True,
                "tablet_table_contained": True,
                "desktop_grid_readable": True,
                "official_editorial_unknown_labels_visible": True,
                "horizontal_clipping_observed": False,
            },
        },
        "external_actions": "NOT_EXECUTED",
        "public_evidence": "NOT_CLAIMED",
        "formal_ci": "NOT_CLAIMED",
        "ci_behavior": (
            "VERIFY_COMMITTED_RECEIPT_AND_CURRENT_TREE_BINDINGS_WHEN_RAW_LOCAL_"
            "FILES_ARE_ABSENT"
        ),
    }
    expected_preview = _read_local_evidence_file(
        root / PHASE3_BROWSER_PREVIEW_PATH, root=root
    )
    verify_phase3_local_browser_evidence(
        document,
        expected_preview=expected_preview,
        root=root,
        require_raw=True,
    )
    return document


def record_local_test_evidence(*, root: Path = ROOT) -> dict[str, object]:
    """Sanitize an ignored pytest tee into a tree-bound local-only receipt."""

    temporary_path = root / LOCAL_TEST_RAW_OUTPUT_TEMP_PATH
    try:
        raw_payload = _read_local_evidence_file(temporary_path, root=root)
        raw_text = raw_payload.decode("utf-8")
    except UnicodeError, ValidationFailure:
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
    except OSError, subprocess.CalledProcessError:
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
        stat.S_ISLNK(final_metadata.st_mode) or not stat.S_ISREG(final_metadata.st_mode)
    ):
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PATH_INVALID")
    try:
        os.replace(temporary_path, raw_path)
    except OSError:
        fail("RAOS_V2_LOCAL_TEST_RAW_OUTPUT_PROMOTION_FAILED")
    verification = verify_local_test_evidence(document, root=root, require_raw=True)
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
    except UnicodeError, yaml.YAMLError:
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
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_V2_JSON_INVALID")


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write only allowlisted recorded inputs without following links."""

    repository = ROOT.resolve()
    if path not in {
        RECORDED_INPUT,
        LOCAL_TEST_EVIDENCE_INPUT,
        PHASE3_LOCAL_BROWSER_EVIDENCE_INPUT,
    }:
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


def _validate_phase3_capture_output_name(output: Path) -> None:
    """Reject every Phase 3 output outside the single-file recorded-input scope."""

    allowed_prefix = PHASE3_RECORDED_ROOT.parts
    if (
        output.is_absolute()
        or output.parts[: len(allowed_prefix)] != allowed_prefix
        or len(output.parts) != len(allowed_prefix) + 1
        or output.suffix != ".json"
        or output.name.startswith(".")
        or any(part in {"", ".", ".."} for part in output.parts)
    ):
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_REJECTED")


def _repair_phase3_capture_link_residue(output: Path) -> bool:
    """Repair one interrupted link/unlink commit without inspecting its payload."""

    _validate_phase3_capture_output_name(output)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_descriptor = -1
    file_descriptor = -1
    try:
        try:
            directory_descriptor = os.open(ROOT, directory_flags)
        except OSError:
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
        for component in output.parts[:-1]:
            try:
                next_descriptor = os.open(
                    component,
                    directory_flags,
                    dir_fd=directory_descriptor,
                )
            except FileNotFoundError:
                return False
            except OSError:
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        try:
            file_descriptor = os.open(
                output.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
        except FileNotFoundError:
            return False
        except OSError:
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")

        opened = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened.st_mode):
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
        if opened.st_nlink == 1:
            return True
        if opened.st_nlink != 2:
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")

        temporary_pattern = re.compile(
            rf"\.{re.escape(output.name)}\.[0-9a-f]{{24}}\.next\Z"
        )
        linked_temporaries: list[str] = []
        for name in os.listdir(directory_descriptor):
            if temporary_pattern.fullmatch(name) is None:
                continue
            temporary_descriptor = -1
            try:
                temporary_descriptor = os.open(
                    name,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory_descriptor,
                )
                temporary_metadata = os.fstat(temporary_descriptor)
            except OSError:
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
            finally:
                if temporary_descriptor >= 0:
                    os.close(temporary_descriptor)
            if (
                stat.S_ISREG(temporary_metadata.st_mode)
                and temporary_metadata.st_nlink == 2
                and temporary_metadata.st_dev == opened.st_dev
                and temporary_metadata.st_ino == opened.st_ino
            ):
                linked_temporaries.append(name)
        if len(linked_temporaries) != 1:
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")

        os.unlink(linked_temporaries[0], dir_fd=directory_descriptor)
        os.fsync(directory_descriptor)
        final_descriptor = os.open(
            output.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
        try:
            final = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final.st_mode)
                or final.st_dev != opened.st_dev
                or final.st_ino != opened.st_ino
                or final.st_nlink != 1
            ):
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
        finally:
            os.close(final_descriptor)
        return True
    except ValidationFailure:
        raise
    except OSError:
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _phase3_capture_output_path(output: Path) -> Path:
    """Resolve one new Phase 3 recorded input without escaping its directory."""

    if _repair_phase3_capture_link_residue(output):
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS")
    return ROOT / output


def _recover_equal_phase3_capture(output: Path, payload: bytes) -> bool:
    """Recover or accept an exact prior no-replace write, never other bytes."""

    if not _repair_phase3_capture_link_residue(output):
        return False
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_descriptor = -1
    try:
        directory_descriptor = os.open(ROOT, directory_flags)
        for component in output.parts[:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        try:
            file_descriptor = os.open(
                output.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
        except FileNotFoundError:
            return False
        try:
            opened = os.fstat(file_descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
            if opened.st_size != len(payload):
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
                chunks.append(chunk)
                remaining -= len(chunk)
            final = os.fstat(file_descriptor)
            if (
                b"".join(chunks) != payload
                or final.st_dev != opened.st_dev
                or final.st_ino != opened.st_ino
                or final.st_size != opened.st_size
                or final.st_nlink != opened.st_nlink
                or final.st_mtime_ns != opened.st_mtime_ns
                or final.st_ctime_ns != opened.st_ctime_ns
            ):
                fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS")
        finally:
            os.close(file_descriptor)
        return True
    except FileNotFoundError:
        return False
    except ValidationFailure:
        raise
    except OSError:
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _write_new_phase3_capture(output: Path, payload: bytes) -> None:
    """Create a complete Phase 3 capture atomically and never overwrite it."""

    if not payload:
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
    if _recover_equal_phase3_capture(output, payload):
        return
    target = _phase3_capture_output_path(output)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")

    # Revalidate every ancestor after mkdir so an existing link cannot redirect
    # the temporary file outside the repository allowlist.
    current = ROOT
    for part in output.parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError:
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")
    if target.parent.resolve() != (ROOT.resolve() / output.parent).resolve():
        fail("RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_descriptor = -1
    current_descriptor = -1
    temporary_name = f".{target.name}.{os.urandom(12).hex()}.next"
    temporary_created = False
    failure_code: str | None = None
    try:
        current_descriptor = os.open(ROOT, directory_flags)
        for part in output.parts[:-1]:
            parent_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            os.close(current_descriptor)
            current_descriptor = parent_descriptor
            parent_descriptor = -1
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=current_descriptor,
        )
        temporary_created = True
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            temporary_name,
            target.name,
            src_dir_fd=current_descriptor,
            dst_dir_fd=current_descriptor,
            follow_symlinks=False,
        )
    except FileExistsError:
        failure_code = "RAOS_V2_PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS"
    except OSError:
        failure_code = "RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE"
    finally:
        if temporary_created and current_descriptor >= 0:
            try:
                os.unlink(temporary_name, dir_fd=current_descriptor)
            except FileNotFoundError:
                temporary_created = False
            except OSError:
                failure_code = "RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE"
            else:
                temporary_created = False
        if current_descriptor >= 0:
            try:
                os.fsync(current_descriptor)
            except OSError:
                failure_code = "RAOS_V2_PHASE3_CAPTURE_OUTPUT_UNSAFE"
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)
    if failure_code is not None:
        fail(failure_code)


def validate_public_url(url: str) -> str:
    try:
        if (
            not isinstance(url, str)
            or not url
            or url != url.strip()
            or "\\" in url
            or any(
                ord(character) > 0x7E or ord(character) < 0x21 or character.isspace()
                for character in url
            )
        ):
            fail("RAOS_V2_CAPTURE_URL_REJECTED")
        parts = urlsplit(url)
        port = parts.port
    except UnicodeError, ValueError:
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
    except KeyError, RuntimeError:
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
    except OSError, zipfile.BadZipFile:
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
            except KeyError, RuntimeError:
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
    schema_sets = {
        "v1": (ROOT / "contracts/raos-v2/v1", 10),
        "v2": (ROOT / "contracts/raos-v2/v2", 10),
    }
    schemas_by_version: dict[str, dict[str, dict[str, object]]] = {}
    registry = Registry()
    identifiers: set[str] = set()
    identified_schemas: list[tuple[str, Mapping[str, object]]] = []
    for version, (schema_root, expected_count) in schema_sets.items():
        schema_paths = sorted(schema_root.glob("*.schema.json"))
        if len(schema_paths) != expected_count:
            fail("RAOS_V2_SCHEMA_COUNT_INVALID")
        version_schemas: dict[str, dict[str, object]] = {}
        for path in schema_paths:
            document = _mapping(
                load_json_strict(path.read_bytes()), "RAOS_V2_SCHEMA_INVALID"
            )
            try:
                Draft202012Validator.check_schema(document)
                resource = Resource.from_contents(document)
                identifier = document.get("$id")
                expected_identifier = (
                    f"{ORIGIN}/contracts/raos-v2/{version}/{path.name}"
                )
                if (
                    not isinstance(identifier, str)
                    or identifier != expected_identifier
                    or identifier in identifiers
                    or document.get("$schema")
                    != "https://json-schema.org/draft/2020-12/schema"
                ):
                    fail("RAOS_V2_SCHEMA_INVALID")
                identifiers.add(identifier)
                identified_schemas.append((identifier, document))
                registry = registry.with_resource(identifier, resource)
            except Exception as exc:
                if isinstance(exc, ValidationFailure):
                    raise
                fail("RAOS_V2_SCHEMA_INVALID")
            if document.get("additionalProperties") is not False:
                fail("RAOS_V2_SCHEMA_INVALID")
            version_schemas[path.stem.removesuffix(".schema")] = document
        schemas_by_version[version] = version_schemas

    def referenced_uris(value: object) -> list[str]:
        if isinstance(value, Mapping):
            found = []
            reference = value.get("$ref")
            if isinstance(reference, str):
                found.append(reference)
            for nested in value.values():
                found.extend(referenced_uris(nested))
            return found
        if isinstance(value, list):
            return [reference for item in value for reference in referenced_uris(item)]
        return []

    for identifier, document in identified_schemas:
        for reference in referenced_uris(document):
            resolved = urljoin(identifier, reference).split("#", 1)[0]
            if resolved not in identifiers:
                fail("RAOS_V2_SCHEMA_REFERENCE_INVALID")

    def validate_schema(schema: Mapping[str, object], value: object) -> None:
        try:
            errors = list(
                Draft202012Validator(
                    schema, registry=registry, format_checker=FormatChecker()
                ).iter_errors(value)
            )
        except Exception:
            fail("RAOS_V2_SCHEMA_INSTANCE_INVALID")
        if errors:
            fail("RAOS_V2_SCHEMA_INSTANCE_INVALID")

    def validate(name: str, value: object, *, version: str = "v1") -> None:
        try:
            schema = schemas_by_version[version][name]
        except Exception:
            fail("RAOS_V2_SCHEMA_INSTANCE_INVALID")
        validate_schema(schema, value)

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
            if (
                source_ids
                or row.get("value") is not None
                or row.get("status") != "BLOCKED"
            ):
                fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")
        else:
            if not source_ids or any(
                source_id not in sources for source_id in source_ids
            ):
                fail("RAOS_V2_CLAIM_CROSS_REFERENCE_INVALID")
            if any(
                not str(sources[str(source_id)].get("source_class", "")).endswith(
                    "_PRIMARY"
                )
                for source_id in source_ids
            ):
                fail("RAOS_V2_CLAIM_SOURCE_INELIGIBLE")
        if claim_type == "D_EDITORIAL_JUDGEMENT" and any(
            not isinstance(item, dict) or item.get("value_ref") not in claims
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
        if (
            not isinstance(observation, dict)
            or observation.get("product_id") not in products
        ):
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
        if (
            not isinstance(source, dict)
            or not isinstance(capture, dict)
            or any(
                (
                    row.get("source_content_sha256") != source.get("content_sha256"),
                    row.get("source_content_sha256") != capture.get("body_sha256"),
                    row.get("source_next_review_at") != source.get("next_review_at"),
                    row.get("checked_at") != source.get("checked_at"),
                    capture.get("status") != source.get("status"),
                )
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

    _phase3_payload, phase3_update_value = _read_required(
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    )
    phase3_update = _mapping(
        phase3_update_value, "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID"
    )
    validate("wordpress-update-payload", phase3_update, version="v2")
    _review_payload, review_value = _read_required(
        "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
    )
    review_candidate = _mapping(review_value, "RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID")
    publication_schema = schemas_by_version["v2"]["publication-package"]
    publication_properties = _mapping(
        publication_schema.get("properties"), "RAOS_V2_SCHEMA_INVALID"
    )
    review_schema = _mapping(
        publication_properties.get("review_candidate"), "RAOS_V2_SCHEMA_INVALID"
    )
    validate_schema(review_schema, review_candidate)

    return {
        "schemas": schemas_by_version["v1"],
        "schemas_v2": schemas_by_version["v2"],
        "sources": sources,
        "claims": claims,
        "products": products,
        "articles": articles,
        "editorial": editorial,
        "candidate": candidate,
        "synthetic_seal": seal,
        "phase3_update": phase3_update,
        "phase3_review_candidate": review_candidate,
        "claim_payload": claim_payload,
    }


def _validate_publication_closure(values: Mapping[str, object]) -> None:
    candidate = _mapping(
        values.get("candidate"), "RAOS_V2_PUBLICATION_CANDIDATE_INVALID"
    )
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
            (
                ROOT / "changes/raos-v2/phase-2/sources/source-registry.v2.yaml"
            ).read_bytes()
        ),
        "render": sha256(
            (
                ROOT
                / "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
            ).read_bytes()
        ),
        "migration": sha256(
            (
                ROOT / "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
            ).read_bytes()
        ),
        "editorial": sha256(
            (
                ROOT / "changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"
            ).read_bytes()
        ),
        "products": sha256(
            (
                ROOT / "changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json"
            ).read_bytes()
        ),
        "review": sha256(
            (
                ROOT / "changes/raos-v2/phase-2/reviews/review-packet.v2.yaml"
            ).read_bytes()
        ),
        "render_model": sha256(
            (
                ROOT / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
            ).read_bytes()
        ),
    }
    evidence_rows = _rows(
        candidate.get("claim_evidence"),
        "RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID",
    )
    authority_rows: list[dict[str, object]] = []
    for evidence in sorted(evidence_rows, key=lambda row: str(row.get("claim_id"))):
        claim_id = evidence.get("claim_id")
        claim = claims.get(str(claim_id))
        if not isinstance(claim, Mapping):
            fail("RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID")
        authority_rows.append(
            {
                "claim_id": claim_id,
                "claim_type": claim.get("claim_type"),
                "risk_class": claim.get("risk_class"),
                "freshness": evidence.get("freshness"),
                "authoritative_source_status": claim.get("status"),
                "checked_at": claim.get("checked_at"),
                "next_review_at": claim.get("next_review_at"),
            }
        )
    expected_hashes["phase3_claim_authority"] = _semantic_digest(
        {
            "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
            "version": "1.0.0",
            "claims": authority_rows,
        }
    )
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
        _load_generated("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"),
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
        rollback.get("plan_scope") != "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION"
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
        claim = _mapping(
            claims.get(str(claim_id)), "RAOS_V2_PUBLICATION_EVIDENCE_INVALID"
        )
        if claim.get("claim_type") == "UNKNOWN":
            freshness = "UNKNOWN"
        else:
            resolved = [
                _mapping(
                    sources.get(str(source_id)), "RAOS_V2_PUBLICATION_EVIDENCE_INVALID"
                )
                for source_id in claim.get("source_ids", [])
            ]
            if not resolved or any(
                source.get("status") not in {"FRESH", "DUE"} for source in resolved
            ):
                fail("RAOS_V2_PUBLICATION_EVIDENCE_INVALID")
            try:
                checked = max(
                    datetime.fromisoformat(
                        str(source["checked_at"]).replace("Z", "+00:00")
                    )
                    for source in resolved
                )
                next_review = min(
                    datetime.fromisoformat(
                        str(source["next_review_at"]).replace("Z", "+00:00")
                    )
                    for source in resolved
                )
            except KeyError, ValueError:
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
        != {
            "origin": package.get("target_origin"),
            "route": package.get("target_route"),
        }
        or after.get("render_hash") != package.get("render_hash")
    ):
        fail("RAOS_V2_WORDPRESS_RECEIPT_INVALID")


def _validate_visual_and_browser_evidence() -> dict[str, object]:
    _visual_payload, visual_value = _read_required(
        "changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json"
    )
    visual = _mapping(visual_value, "RAOS_V2_VISUAL_EVIDENCE_INVALID")
    screenshots = _rows(visual.get("screenshots"), "RAOS_V2_VISUAL_EVIDENCE_INVALID")
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
        (path, viewport) for path in expected_paths for viewport in expected_viewports
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
    assertions = _mapping(browser.get("assertions"), "RAOS_V2_BROWSER_EVIDENCE_INVALID")
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
        if len(payload) != raw_binding.get("bytes") or sha256(
            payload
        ) != raw_binding.get("sha256"):
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
                ROOT / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
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
    review = _mapping(review_value, "RAOS_V2_VISUAL_REVIEW_EVIDENCE_INVALID")
    verification = verify_visual_review_evidence(
        review,
        preview_digests={
            str(key): str(value) for key, value in preview_digests.items()
        },
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
            and raw_status in {"RAW_RECEIPT_VERIFIED_LOCAL", "RECORDED_NOT_REVERIFIED"}
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
    backlog = _rows(effective.get("backlog"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID")
    tests = _rows(effective.get("tests"), "RAOS_V2_EFFECTIVE_TRACEABILITY_INVALID")
    d_map = {str(row["id"]): row for row in decisions}
    r_map = {str(row["id"]): row for row in requirements}
    b_map = {str(row["id"]): row for row in backlog}
    t_map = {str(row["id"]): row for row in tests}
    if (
        len(d_map) != len(decisions)
        or len(r_map) != len(requirements)
        or set(b_map) != {f"B-V2-{number:03d}" for number in range(1, 41)}
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
            else (
                (
                    "VERIFIED_LOCAL_RECORDED"
                    if gate_passed
                    else (
                        "AWAITING_LOCAL_TEST_GATE"
                        if number == 34
                        else "IMPLEMENTED_LOCAL_PENDING_GATE"
                    )
                )
                if number <= 34
                else (
                    (
                        "COMPLETE_LOCAL_RECORDED"
                        if gate_passed
                        else "IMPLEMENTED_LOCAL_PENDING_GATE"
                    )
                    if number in {35, 36, 38, 39}
                    else (
                        "REVIEW_READY_BLOCKED_EXTERNAL"
                        if number == 37
                        else "BLOCKED_EXTERNAL"
                    )
                )
            )
        )
        if row.get("implementation_status") != expected:
            fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
        if number >= 35 and row.get("external_action_status") != "NOT_EXECUTED":
            fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
    phase3_test_numbers = {4, 5, 8, 10, 23, *range(35, 47), 51}
    for identifier, row in t_map.items():
        number = int(identifier.rsplit("-", 1)[1])
        is_phase3 = number in phase3_test_numbers
        expected_execution = (
            (
                "PASSED_LOCAL_COMPONENT_RECORDED"
                if gate_passed
                else "LOCAL_COMPONENT_NOT_EXECUTED_RECORDED"
            )
            if is_phase3
            else ("PASSED_LOCAL_RECORDED" if gate_passed else "NOT_EXECUTED_RECORDED")
        )
        expected_external = "NOT_EXECUTED" if is_phase3 else "NOT_APPLICABLE"
        expected_acceptance = "BLOCKED_EXTERNAL" if is_phase3 else "NOT_APPLICABLE"
        if (
            row.get("execution_status") != expected_execution
            or row.get("phase3_external_execution_status") != expected_external
            or row.get("phase3_acceptance_status") != expected_acceptance
        ):
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
        or generated_receipt.get("raw_verification") != "RECORDED_NOT_REVERIFIED"
        or generated_browser.get("classification")
        != recorded_browser.get("classification")
        or generated_browser.get("raw_verification") != "RECORDED_NOT_REVERIFIED"
        or generated_browser.get("receipt_sha256") != recorded_browser_raw.get("sha256")
        or generated_browser.get("receipt_bytes") != recorded_browser_raw.get("bytes")
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
        or generated_visual_verification.get("raw_verification")
        != "RECORDED_NOT_REVERIFIED"
    ):
        fail("RAOS_V2_EFFECTIVE_TRACEABILITY_STATUS_INVALID")
    return {
        "local_test_status": local_test_status,
        "gate_passed": gate_passed,
        "binding_verification": verification["binding_verification"],
        "raw_verification": verification["raw_verification"],
    }


def _validate_phase3_publication_closure(
    values: Mapping[str, object],
) -> dict[str, object]:
    candidate = _mapping(
        values.get("candidate"), "RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID"
    )
    update = _mapping(
        values.get("phase3_update"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID"
    )
    review = _mapping(
        values.get("phase3_review_candidate"),
        "RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID",
    )
    claims = _mapping(values.get("claims"), "RAOS_V2_CLAIM_LEDGER_INVALID")
    if (
        review.get("phase2_candidate") != candidate
        or review.get("update_payload") != update
        or review.get("candidate_digest") != _semantic_digest(candidate)
        or review.get("payload_digest") != _semantic_digest(update)
    ):
        fail("RAOS_V2_PHASE3_REVIEW_BINDING_INVALID")

    fields = _mapping(update.get("fields"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID")
    target = _mapping(update.get("target"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID")
    preconditions = _mapping(
        update.get("preconditions"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID"
    )
    postconditions = _mapping(
        update.get("postconditions"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID"
    )
    preaction = _mapping(
        update.get("preaction"), "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID"
    )
    structured_data = _mapping(
        update.get("structured_data_expectation"),
        "RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID",
    )
    migration_document = _mapping(
        _load_generated("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"),
        "RAOS_V2_MIGRATION_MANIFEST_INVALID",
    )
    public_before = _mapping(
        migration_document.get("public_before"),
        "RAOS_V2_MIGRATION_MANIFEST_INVALID",
    )
    try:
        post_content = (
            ROOT / "changes/raos-v2/phase-3/generated/post-content.html"
        ).read_text(encoding="utf-8")
    except OSError, UnicodeError:
        fail("RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID")
    if (
        update.get("schema") != "RAOS_V2_PHASE3_WORDPRESS_UPDATE_PAYLOAD_V1"
        or update.get("version") != "1.0.0"
        or update.get("intent") != "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"
        or target
        != {
            "origin": "https://kurashinoshirube.com",
            "route": "/carry-on-suitcase-comparison/",
            "kind": "EXISTING_POST",
            "expected_match_count": 1,
            "expected_public_body_sha256": public_before.get("body_sha256"),
        }
        or preconditions != {"expected_current_post_status": "publish"}
        or postconditions != {"required_after_post_status": "publish"}
        or fields.get("post_status") != "publish"
        or fields.get("canonical_url")
        != "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
        or fields.get("post_content") != post_content
        or preaction
        != {
            "status": "HISTORICAL_BASELINE_ONLY",
            "binding_digest": None,
            "binding": None,
        }
        or review.get("preaction_status") != "HISTORICAL_BASELINE_ONLY"
        or review.get("preaction_binding_digest") is not None
        or structured_data != _phase3_expected_structured_data(fields)
        or review.get("structured_data_expectation_sha256")
        != structured_data.get("json_ld_sha256")
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID")

    phase2_evidence = {
        str(row.get("claim_id")): row
        for row in _rows(
            candidate.get("claim_evidence"),
            "RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID",
        )
    }
    bindings = _rows(
        review.get("claim_bindings"), "RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID"
    )
    bound = {str(row.get("claim_id")): row for row in bindings}
    if len(bound) != len(bindings) or set(bound) != set(phase2_evidence):
        fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
    try:
        candidate_at = datetime.fromisoformat(str(candidate.get("created_at")))
    except ValueError:
        fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
    if candidate_at.tzinfo is None or candidate_at.utcoffset() is None:
        fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
    authority_rows: list[dict[str, object]] = []
    for claim_id in sorted(bound):
        binding = bound[claim_id]
        claim = _mapping(claims.get(claim_id), "RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
        evidence = phase2_evidence[claim_id]
        claim_type = claim.get("claim_type")
        source_status = claim.get("status")
        expected_resolved = claim_type != "UNKNOWN" and source_status == "VERIFIED"
        expected_blocking = (
            source_status != "BLOCKED"
            if claim_type == "UNKNOWN"
            else source_status != "VERIFIED"
        )
        expected_disclosed = claim_type == "UNKNOWN" and source_status == "BLOCKED"
        try:
            checked_at = datetime.fromisoformat(str(binding.get("checked_at")))
            next_review_at = datetime.fromisoformat(str(binding.get("next_review_at")))
        except ValueError:
            fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
        if (
            binding.get("claim_type") != claim_type
            or binding.get("risk_class") != claim.get("risk_class")
            or binding.get("risk_class") != evidence.get("risk_class")
            or binding.get("freshness") != evidence.get("freshness")
            or binding.get("authoritative_source_status") != source_status
            or binding.get("checked_at") != claim.get("checked_at")
            or binding.get("next_review_at") != claim.get("next_review_at")
            or binding.get("resolved") is not expected_resolved
            or binding.get("blocking") is not expected_blocking
            or binding.get("intentionally_disclosed") is not expected_disclosed
            or checked_at.tzinfo is None
            or checked_at.utcoffset() is None
            or next_review_at.tzinfo is None
            or next_review_at.utcoffset() is None
            or next_review_at <= checked_at
            or candidate_at < checked_at
            or candidate_at >= next_review_at
        ):
            fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
        safely_bound = expected_resolved and not expected_blocking
        if claim_type == "A_OFFICIAL_FACT":
            safely_bound = safely_bound and binding.get("freshness") in {
                "FRESH",
                "DUE",
            }
        elif claim_type == "D_EDITORIAL_JUDGEMENT":
            safely_bound = safely_bound and binding.get("freshness") in {
                "FRESH",
                "DUE",
            }
        elif claim_type == "UNKNOWN":
            safely_bound = (
                not expected_resolved
                and not expected_blocking
                and expected_disclosed
                and binding.get("freshness") in {"UNKNOWN", "UNAVAILABLE"}
            )
        else:
            safely_bound = False
        if not safely_bound:
            fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")
        authority_rows.append(
            {
                "claim_id": claim_id,
                "claim_type": binding.get("claim_type"),
                "risk_class": binding.get("risk_class"),
                "freshness": binding.get("freshness"),
                "authoritative_source_status": binding.get(
                    "authoritative_source_status"
                ),
                "checked_at": binding.get("checked_at"),
                "next_review_at": binding.get("next_review_at"),
            }
        )
    candidate_hashes = _mapping(
        candidate.get("input_hashes"), "RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID"
    )
    if candidate_hashes.get("phase3_claim_authority") != _semantic_digest(
        {
            "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
            "version": "1.0.0",
            "claims": authority_rows,
        }
    ):
        fail("RAOS_V2_PHASE3_CLAIM_CLOSURE_INVALID")

    review_request = _mapping(
        _load_generated(
            "changes/raos-v2/phase-3/generated/human-review-request.v1.json"
        ),
        "RAOS_V2_PHASE3_REVIEW_REQUEST_INVALID",
    )
    dry_run = _mapping(
        _load_generated(
            "changes/raos-v2/phase-3/generated/wordpress-dry-run-status.v1.json"
        ),
        "RAOS_V2_PHASE3_DRY_RUN_STATUS_INVALID",
    )
    candidate_digest = review.get("candidate_digest")
    payload_digest = review.get("payload_digest")
    if (
        review_request.get("candidate_digest") != candidate_digest
        or review_request.get("payload_digest") != payload_digest
        or review_request.get("state") != "AWAITING_VERIFIED_PREACTION_BINDING"
        or review_request.get("candidate_reissue")
        != "BLOCKED_PENDING_VERIFIED_PREACTION_BINDING"
        or review_request.get("preaction_status") != "HISTORICAL_BASELINE_ONLY"
        or review_request.get("preaction_binding_digest") is not None
        or review_request.get("structured_data_expectation_sha256")
        != structured_data.get("json_ld_sha256")
        or review_request.get("receipt") is not None
        or review_request.get("human_review") != "NOT_EXECUTED"
        or review_request.get("package_seal") != "NOT_EXECUTED"
        or dry_run.get("candidate_digest") != candidate_digest
        or dry_run.get("payload_digest") != payload_digest
        or dry_run.get("preaction_status") != "HISTORICAL_BASELINE_ONLY"
        or dry_run.get("preaction_binding_digest") is not None
        or dry_run.get("structured_data_expectation_sha256")
        != structured_data.get("json_ld_sha256")
        or dry_run.get("mode") != "DISABLED_DRY_RUN"
        or dry_run.get("intent") != "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"
        or dry_run.get("status") != "BLOCKED_EXTERNAL"
        or dry_run.get("request_count") != 0
        or dry_run.get("external_action_count") != 0
        or dry_run.get("endpoint") is not None
        or dry_run.get("wordpress_write") != "NOT_EXECUTED"
        or dry_run.get("publication") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_PHASE3_EXTERNAL_BOUNDARY_INVALID")

    external_state = _mapping(
        _load_generated("changes/raos-v2/phase-3/inputs/external-action-state.v1.yaml"),
        "RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID",
    )
    verify_phase3_external_state(external_state)

    evidence_template = _mapping(
        _load_generated(
            "changes/raos-v2/phase-3/generated/external-action-evidence-template.v1.yaml"
        ),
        "RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID",
    )
    steps = _rows(
        evidence_template.get("steps"), "RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID"
    )
    steps_by_action = {str(row.get("action")): row for row in steps}
    expected_actions = (
        "PREACTION_PUBLIC_CAPTURE_AND_OWNER_EXPORT",
        "LOCAL_REISSUE_FROM_VERIFIED_PREACTION",
        "OWNER_CONTENT_REVIEW",
        "PRE_WRITE_EXPORT_AND_DISABLED_DRY_RUN",
        "DEPLOY_AND_WORDPRESS_NONPUBLIC_REVIEW_PREVIEW",
        "HUMAN_PUBLICATION",
        "POST_ACTION_OWNER_EXPORT",
        "ATOMIC_POST_ACTION_HTTP_AND_EXPORT_VERIFICATION",
        "PUBLIC_BROWSER_VERIFICATION",
        "SEVEN_DAY_STABILITY_WINDOW",
    )
    if (
        len(steps_by_action) != len(steps)
        or tuple(str(row.get("action")) for row in steps) != expected_actions
        or tuple(row.get("sequence") for row in steps) != tuple(range(1, 11))
        or steps_by_action["PREACTION_PUBLIC_CAPTURE_AND_OWNER_EXPORT"].get(
            "required_receipt_schema"
        )
        != "RAOS_V2_PHASE3_PREACTION_BINDING_V1"
        or steps_by_action["OWNER_CONTENT_REVIEW"].get("required_receipt_schema")
        != "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"
        or steps_by_action["PRE_WRITE_EXPORT_AND_DISABLED_DRY_RUN"].get(
            "required_receipt_schemas"
        )
        != [
            "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2",
            "RAOS_V2_PHASE3_WORDPRESS_DRY_RUN_RECEIPT_V1",
        ]
        or steps_by_action["PRE_WRITE_EXPORT_AND_DISABLED_DRY_RUN"].get("ordering")
        != "AFTER_HUMAN_REVIEW_BEFORE_WORDPRESS_WRITE"
        or steps_by_action["POST_ACTION_OWNER_EXPORT"].get("required_receipt_schema")
        != "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2"
        or steps_by_action["POST_ACTION_OWNER_EXPORT"].get("ordering")
        != "AFTER_WORDPRESS_WRITE_BEFORE_HTTP_VERIFICATION"
        or steps_by_action["ATOMIC_POST_ACTION_HTTP_AND_EXPORT_VERIFICATION"].get(
            "required_receipt_schema"
        )
        != "RAOS_V2_PUBLIC_VERIFICATION_RECEIPT_V2"
        or steps_by_action["PUBLIC_BROWSER_VERIFICATION"].get("required_receipt_schema")
        != "RAOS_V2_PHASE3_PUBLIC_BROWSER_VERIFICATION_RECEIPT_V1"
        or steps_by_action["PUBLIC_BROWSER_VERIFICATION"].get("acceptance_authority")
        is not False
        or steps_by_action["PUBLIC_BROWSER_VERIFICATION"].get("phase_exit")
        != "BLOCKED_EXTERNAL"
        or evidence_template.get("all_external_actions") != "NOT_EXECUTED"
        or evidence_template.get("phase_exit") != "BLOCKED_EXTERNAL"
    ):
        fail("RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID")

    validation = _mapping(
        _load_generated("changes/raos-v2/phase-3/generated/phase-3-validation.v1.json"),
        "RAOS_V2_PHASE3_VALIDATION_INVALID",
    )
    checks = _mapping(validation.get("checks"), "RAOS_V2_PHASE3_VALIDATION_INVALID")
    backlog_status = _mapping(
        validation.get("backlog_status"), "RAOS_V2_PHASE3_VALIDATION_INVALID"
    )
    if (
        validation.get("status") != "PASSED_LOCAL_PREPARATION"
        or validation.get("classification") != "LOCAL_PREPARATION_ONLY"
        or validation.get("external_actions") != "NOT_EXECUTED"
        or validation.get("phase_exit") != "BLOCKED_EXTERNAL"
        or not checks
        or any(value is not True for value in checks.values())
        or backlog_status.get("B-V2-037") != "AWAITING_VERIFIED_PREACTION_BINDING"
        or backlog_status.get("B-V2-040") != "BLOCKED_EXTERNAL"
    ):
        fail("RAOS_V2_PHASE3_VALIDATION_INVALID")
    return {
        "status": validation["status"],
        "phase_exit": validation["phase_exit"],
        "review_candidate": "AWAITING_VERIFIED_PREACTION_BINDING",
        "external_actions": "NOT_EXECUTED",
    }


def _validate_generated_artifact_inventory() -> None:
    evidence = _mapping(
        _load_generated(
            "changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"
        ),
        "RAOS_V2_LOCAL_EVIDENCE_INVALID",
    )
    rows = _rows(evidence.get("generated_artifacts"), "RAOS_V2_LOCAL_EVIDENCE_INVALID")
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
        except OSError, subprocess.CalledProcessError:
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
        preview_checker = (ui_root / "preview/checker.js").read_text(encoding="utf-8")
    except OSError, UnicodeError:
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
    portfolio_rows = _rows(product.get("portfolio"), "RAOS_V2_PRODUCT_SPEC_INVALID")
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
        _load_generated("changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"),
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
        except OSError, UnicodeError:
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
    repository = _mapping(capture.get("repository"), "RAOS_V2_PHASE0_CAPTURE_INVALID")
    base_head = repository.get("head")
    if base_head != IMMUTABLE_BASE_HEAD or protected_path_changes(IMMUTABLE_BASE_HEAD):
        fail("RAOS_V2_IMMUTABLE_PATH_CHANGED")
    preflight = _mapping(
        _load_generated("changes/raos-v2/phase-0/preflight-report.json"),
        "RAOS_V2_PREFLIGHT_INVALID",
    )
    if (
        preflight.get("immutable_base_head") != IMMUTABLE_BASE_HEAD
        or _mapping(preflight.get("repository"), "RAOS_V2_PREFLIGHT_INVALID").get(
            "head"
        )
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
    if (
        len(deprecation_rows) != 15
        or deprecation.get("retire_requires_verified_unused") is not True
    ):
        fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
    for row in deprecation_rows:
        if not all(
            isinstance(row.get(key), dict)
            for key in ("usage_evidence", "replacement", "rollback")
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        usage = _mapping(row["usage_evidence"], "RAOS_V2_DEPRECATION_LEDGER_INVALID")
        replacement = _mapping(row["replacement"], "RAOS_V2_DEPRECATION_LEDGER_INVALID")
        asset_rollback = _mapping(row["rollback"], "RAOS_V2_DEPRECATION_LEDGER_INVALID")
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
    phase3_status = _validate_phase3_publication_closure(contract_values)
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
        "phase3_schemas": 8,
        "schemas_total": 18,
        "contract_instances": {
            "sources": len(contract_values["sources"]),
            "claims": len(contract_values["claims"]),
            "products": len(contract_values["products"]),
            "articles": len(contract_values["articles"]),
        },
        "browser_evidence": evidence_status,
        "recorded_local_test_status": trace_status["local_test_status"],
        "phase3": phase3_status,
        "external_actions": "NOT_EXECUTED",
    }


def _is_crawler_robots_name(value: str) -> bool:
    name = value.strip().casefold()
    return (
        name
        in {
            "googlebot",
            "googlebot-news",
            "googlebot-image",
            "bingbot",
            "duckduckbot",
            "slurp",
            "baiduspider",
            "yandex",
            "yandexbot",
        }
        or re.fullmatch(r"[a-z0-9-]*(?:bot|crawler|spider|slurp)[a-z0-9-]*", name)
        is not None
    )


class _MetadataParser(HTMLParser):
    _CONTENT_EXCLUSION_TAGS = frozenset(
        {
            "template",
            "noscript",
            "textarea",
            "xmp",
            "iframe",
            "noembed",
            "noframes",
            "plaintext",
        }
    )
    _SELF_CLOSING_UNSAFE_TAGS = _CONTENT_EXCLUSION_TAGS | frozenset(
        {"script", "style", "title"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: str | None = None
        self.canonical_tag_count = 0
        self.head_tag_count = 0
        self.metadata_location_violation_count = 0
        self.in_head = False
        self.body_started = False
        self.metadata_exclusion_stack: list[str] = []
        self.robots: str | None = None
        self.robots_tag_count = 0
        self.crawler_robots_values: list[str] = []
        self.title_parts: list[str] = []
        self.title_tag_count = 0
        self.in_title = False
        self.meta_description: str | None = None
        self.meta_description_tag_count = 0
        self.h1_parts: list[str] = []
        self.h1_count = 0
        self.in_h1 = False
        self.package_marker_count = 0
        self.package_marker_attribute_count = 0
        self.post_content_envelope_count = 0
        self.blocked_post_content_envelope_count = 0
        self.disclosure_marker_count = 0
        self.cta_state_count = 0
        self.blocked_cta_count = 0
        self.affiliate_url_count = 0
        self.image_count = 0
        self.inline_executable_script_count = 0
        self.external_script_count = 0
        self.json_ld_script_count = 0
        self.json_ld_invalid_count = 0
        self.json_ld_documents: list[object] = []
        self._json_ld_parts: list[str] | None = None
        self._inline_script_parts: list[str] | None = None
        self._inline_style_parts: list[str] | None = None
        self.ambiguous_attribute_count = 0
        self.unsafe_resource_count = 0
        self.script_resource_sha256: list[str] = []
        self.image_resource_sha256: list[str] = []
        self.stylesheet_resource_sha256: list[str] = []
        self.active_resource_sha256: list[str] = []
        self.inline_executable_script_sha256: list[str] = []
        self.inline_style_sha256: list[str] = []
        self.executable_attribute_sha256: list[str] = []

    @property
    def metadata_exclusion_depth(self) -> int:
        return len(self.metadata_exclusion_stack)

    def _attributes(self, attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        values: dict[str, str | None] = {}
        for key, value in attrs:
            normalized = key.lower()
            if normalized in values:
                self.ambiguous_attribute_count += 1
                continue
            values[normalized] = value
        return values

    def _record_resource(self, category: str, value: str | None) -> None:
        safe_navigation = False
        if isinstance(value, str) and value.strip():
            safe_navigation, _host = _strict_navigation_host(value)
        digest = (
            _sanitized_resource_ref_sha256(value)
            if safe_navigation and isinstance(value, str)
            else None
        )
        if digest is None:
            self.unsafe_resource_count += 1
            return
        target = getattr(self, category)
        target.append(digest)

    def resource_inventory(self) -> dict[str, object]:
        names = (
            "script_resource_sha256",
            "image_resource_sha256",
            "stylesheet_resource_sha256",
            "active_resource_sha256",
            "inline_executable_script_sha256",
            "inline_style_sha256",
            "executable_attribute_sha256",
        )
        return {
            **{name: sorted(getattr(self, name)) for name in names},
            "unsafe_resource_count": self.unsafe_resource_count,
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attributes(attrs)
        normalized_tag = tag.lower()
        for key, value in values.items():
            if key.startswith("on") or key in {"formaction", "srcdoc"}:
                self.unsafe_resource_count += 1
                self.executable_attribute_sha256.append(
                    sha256(
                        canonical_json_bytes(
                            {"attribute": key, "value": str(value or "")}
                        )
                    )
                )
            elif key == "style":
                self.inline_style_sha256.append(
                    sha256(str(value or "").encode("utf-8"))
                )
            elif key in {"ping", "attributionsrc"}:
                self.unsafe_resource_count += 1
        if normalized_tag in self._CONTENT_EXCLUSION_TAGS:
            if normalized_tag == "iframe":
                self._record_resource("active_resource_sha256", values.get("src"))
            if any(key.startswith("data-raos-v2-") for key in values):
                self.metadata_location_violation_count += 1
            self.metadata_exclusion_stack.append(normalized_tag)
            return
        if self.metadata_exclusion_stack:
            rel = set(str(values.get("rel") or "").casefold().split())
            name = str(values.get("name") or "").casefold()
            sensitive = (
                normalized_tag in {"h1", "title"}
                or normalized_tag == "link"
                and "canonical" in rel
                or normalized_tag == "meta"
                and (name in {"robots", "description"} or _is_crawler_robots_name(name))
                or any(key.startswith("data-raos-v2-") for key in values)
            )
            if sensitive:
                self.metadata_location_violation_count += 1
            return
        if normalized_tag == "head":
            self.head_tag_count += 1
            if self.in_head or self.body_started:
                self.metadata_location_violation_count += 1
            self.in_head = True
        elif normalized_tag == "body":
            self.in_head = False
            self.body_started = True
        elif self.in_head and normalized_tag not in {
            "base",
            "link",
            "meta",
            "title",
            "style",
            "script",
            "noscript",
            "template",
        }:
            # HTML5 closes the head before body-only content. Do the same so
            # metadata placed after that point cannot masquerade as head data.
            self.in_head = False
            self.body_started = True
            self.metadata_location_violation_count += 1
        elif not self.in_head and normalized_tag not in {
            "html",
            "base",
            "link",
            "meta",
            "title",
            "style",
            "script",
            "noscript",
            "template",
        }:
            self.body_started = True
        marker = values.get("data-raos-v2-package-marker")
        if marker is not None:
            self.package_marker_attribute_count += 1
            if marker == PHASE3_PACKAGE_MARKER:
                self.package_marker_count += 1
        envelope = values.get("data-raos-v2-post-content-envelope")
        if envelope == PHASE3_CONTENT_ENVELOPE:
            self.post_content_envelope_count += 1
        if values.get("data-raos-v2-post-content-envelope-status") == "BLOCKED":
            self.blocked_post_content_envelope_count += 1
        if (
            values.get("aria-label") == "広告表示"
            and "raos-v2-decision-support__disclosure"
            in str(values.get("class", "")).split()
        ):
            self.disclosure_marker_count += 1
        cta_state = values.get("data-raos-v2-cta-state")
        if cta_state is not None:
            self.cta_state_count += 1
            if cta_state == "BLOCKED":
                self.blocked_cta_count += 1
        if normalized_tag in {"a", "area"}:
            href = str(values.get("href") or values.get("xlink:href") or "").strip()
            safe_navigation, destination_host = _strict_navigation_host(href)
            if not safe_navigation:
                self.unsafe_resource_count += 1
            elif destination_host in PHASE3_AFFILIATE_HOSTS:
                self.affiliate_url_count += 1
        elif normalized_tag == "img":
            self.image_count += 1
            self._record_resource("image_resource_sha256", values.get("src"))
            for candidate in str(values.get("srcset") or "").split(","):
                source = candidate.strip().split(" ", 1)[0]
                if source:
                    self._record_resource("image_resource_sha256", source)
        elif normalized_tag == "source":
            if values.get("src") is not None:
                self._record_resource("active_resource_sha256", values.get("src"))
            for candidate in str(values.get("srcset") or "").split(","):
                source = candidate.strip().split(" ", 1)[0]
                if source:
                    self._record_resource("image_resource_sha256", source)
        elif (
            normalized_tag == "input"
            and str(values.get("type") or "").casefold() == "image"
        ):
            self.image_count += 1
            self._record_resource("image_resource_sha256", values.get("src"))
        elif normalized_tag in {"image", "svg:image", "feimage", "svg:feimage"}:
            self.image_count += 1
            self._record_resource(
                "image_resource_sha256",
                values.get("href") or values.get("xlink:href"),
            )
        elif normalized_tag in {
            "use",
            "svg:use",
            "mpath",
            "svg:mpath",
            "animate",
            "animatemotion",
            "set",
        }:
            self._record_resource(
                "active_resource_sha256",
                values.get("href") or values.get("xlink:href"),
            )
        elif normalized_tag == "script":
            script_type = str(values.get("type") or "").strip().casefold()
            script_ref = (
                values.get("src") or values.get("href") or values.get("xlink:href")
            )
            if script_type == "application/ld+json" and script_ref is None:
                self.json_ld_script_count += 1
                self._json_ld_parts = []
            elif script_ref is None:
                self.inline_executable_script_count += 1
                self._inline_script_parts = []
            else:
                self.external_script_count += 1
                self._record_resource("script_resource_sha256", script_ref)
        elif normalized_tag == "style":
            self._inline_style_parts = []
        elif normalized_tag == "link":
            rel = set(str(values.get("rel") or "").casefold().split())
            if "stylesheet" in rel or (
                "preload" in rel and str(values.get("as") or "").casefold() == "style"
            ):
                self._record_resource("stylesheet_resource_sha256", values.get("href"))
            if rel.intersection(
                {
                    "modulepreload",
                    "prefetch",
                    "prerender",
                    "preload",
                    "preconnect",
                    "dns-prefetch",
                    "manifest",
                    "icon",
                    "apple-touch-icon",
                    "apple-touch-startup-image",
                    "mask-icon",
                }
            ):
                self._record_resource("active_resource_sha256", values.get("href"))
        elif normalized_tag == "base":
            # A base URL can silently turn reviewed relative links into an
            # affiliate or cross-origin destination in the browser.
            self.unsafe_resource_count += 1
        elif (
            normalized_tag == "meta"
            and str(values.get("http-equiv") or "").casefold() == "refresh"
        ):
            self.unsafe_resource_count += 1
        elif normalized_tag in {"embed", "video", "audio", "track"}:
            self._record_resource("active_resource_sha256", values.get("src"))
            if normalized_tag == "video" and values.get("poster") is not None:
                self._record_resource("image_resource_sha256", values.get("poster"))
        elif normalized_tag == "object":
            self._record_resource("active_resource_sha256", values.get("data"))
        elif normalized_tag == "form":
            self._record_resource("active_resource_sha256", values.get("action"))
        if (
            normalized_tag == "link"
            and "canonical" in str(values.get("rel", "")).lower().split()
        ):
            if not self.in_head or self.metadata_exclusion_depth:
                self.metadata_location_violation_count += 1
            self.canonical_tag_count += 1
            self.canonical = values.get("href")
        elif normalized_tag == "meta" and str(values.get("name", "")).lower() == (
            "robots"
        ):
            if not self.in_head or self.metadata_exclusion_depth:
                self.metadata_location_violation_count += 1
            self.robots_tag_count += 1
            self.robots = values.get("content")
        elif normalized_tag == "meta" and _is_crawler_robots_name(
            str(values.get("name") or "")
        ):
            if not self.in_head or self.metadata_exclusion_depth:
                self.metadata_location_violation_count += 1
            self.crawler_robots_values.append(str(values.get("content") or ""))
        elif (
            normalized_tag == "meta"
            and str(values.get("name", "")).casefold() == "description"
        ):
            if not self.in_head or self.metadata_exclusion_depth:
                self.metadata_location_violation_count += 1
            self.meta_description_tag_count += 1
            self.meta_description = values.get("content")
        elif normalized_tag == "title":
            if not self.in_head or self.metadata_exclusion_depth:
                self.metadata_location_violation_count += 1
            self.title_tag_count += 1
            self.in_title = self.title_tag_count == 1
        elif normalized_tag == "h1":
            self.h1_count += 1
            self.in_h1 = self.h1_count == 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self.metadata_exclusion_stack:
            if normalized_tag in self._CONTENT_EXCLUSION_TAGS:
                if self.metadata_exclusion_stack[-1] == normalized_tag:
                    self.metadata_exclusion_stack.pop()
                else:
                    self.metadata_location_violation_count += 1
            return
        if normalized_tag in self._CONTENT_EXCLUSION_TAGS:
            self.metadata_location_violation_count += 1
        elif normalized_tag == "head":
            self.in_head = False
        elif normalized_tag == "h1":
            self.in_h1 = False
        elif normalized_tag == "title":
            self.in_title = False
        elif normalized_tag == "script" and self._json_ld_parts is not None:
            try:
                parsed = load_json_strict("".join(self._json_ld_parts).encode("utf-8"))
            except RecursionError, ValidationFailure:
                self.json_ld_invalid_count += 1
            else:
                self.json_ld_documents.append(parsed)
            self._json_ld_parts = None
        elif normalized_tag == "script" and self._inline_script_parts is not None:
            self.inline_executable_script_sha256.append(
                sha256("".join(self._inline_script_parts).encode("utf-8"))
            )
            self._inline_script_parts = None
        elif normalized_tag == "style" and self._inline_style_parts is not None:
            self.inline_style_sha256.append(
                sha256("".join(self._inline_style_parts).encode("utf-8"))
            )
            self._inline_style_parts = None

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # HTML ignores the self-closing flag on non-void elements. Treat every
        # start/end token as a start here so ``<template/>`` cannot expose
        # browser-inert content to the verifier as visible document content.
        if tag.casefold() in self._SELF_CLOSING_UNSAFE_TAGS:
            self.unsafe_resource_count += 1
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.metadata_exclusion_stack:
            return
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)
        elif self._inline_script_parts is not None:
            self._inline_script_parts.append(data)
        if self._inline_style_parts is not None:
            self._inline_style_parts.append(data)
        if self.in_h1:
            value = " ".join(data.split())
            if value:
                self.h1_parts.append(value)
        if self.in_title:
            value = " ".join(data.split())
            if value:
                self.title_parts.append(value)


class _Phase3MarkerSubtreeParser(HTMLParser):
    """Create a stable token hash for the one package-marker root subtree."""

    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.marker_count = 0
        self.depth = 0
        self.tokens: list[object] = []
        self.completed = False
        self.invalid = False

    @staticmethod
    def _start_token(tag: str, attrs: list[tuple[str, str | None]]) -> list[object]:
        return [
            "start",
            tag.lower(),
            sorted([[key.lower(), value] for key, value in attrs]),
        ]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        values: dict[str, str | None] = {}
        for key, value in attrs:
            normalized = key.lower()
            if normalized in values:
                self.invalid = True
                continue
            values[normalized] = value
        is_marker = values.get("data-raos-v2-package-marker") == PHASE3_PACKAGE_MARKER
        if is_marker:
            self.marker_count += 1
            if self.depth != 0 or self.completed:
                self.invalid = True
        if self.depth == 0:
            if not is_marker:
                return
            self.depth = 1
            self.tokens.append(self._start_token(normalized_tag, attrs))
            return
        self.tokens.append(self._start_token(normalized_tag, attrs))
        if normalized_tag not in self._VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values: dict[str, str | None] = {}
        for key, value in attrs:
            normalized = key.lower()
            if normalized in values:
                self.invalid = True
                continue
            values[normalized] = value
        if values.get("data-raos-v2-package-marker") == PHASE3_PACKAGE_MARKER:
            self.marker_count += 1
            self.invalid = True
        if self.depth:
            self.tokens.append(["empty", tag.lower(), self._start_token(tag, attrs)[2]])

    def handle_endtag(self, tag: str) -> None:
        if self.depth == 0:
            return
        self.tokens.append(["end", tag.lower()])
        self.depth -= 1
        if self.depth == 0:
            self.completed = True

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.tokens.append(["data", data])

    def handle_comment(self, data: str) -> None:
        if self.depth:
            self.tokens.append(["comment", data])


def _phase3_post_content_semantic_summary(html: str) -> dict[str, object]:
    parser = _Phase3MarkerSubtreeParser()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError, RecursionError, ValueError:
        return {
            "post_content_marker_subtree_count": parser.marker_count,
            "post_content_semantic_sha256": "UNAVAILABLE",
        }
    digest = (
        _semantic_digest({"tokens": parser.tokens})
        if parser.marker_count == 1
        and parser.completed
        and parser.depth == 0
        and not parser.invalid
        else "UNAVAILABLE"
    )
    return {
        "post_content_marker_subtree_count": parser.marker_count,
        "post_content_semantic_sha256": digest,
    }


class _Phase3ContentEnvelopeParser(HTMLParser):
    """Require one envelope whose sole substantive child is the sealed marker."""

    _VOID_TAGS = _Phase3MarkerSubtreeParser._VOID_TAGS

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.envelope_count = 0
        self.stack: list[str] = []
        self.marker_child_count = 0
        self.invalid = False
        self.completed = False

    @property
    def depth(self) -> int:
        return len(self.stack)

    @staticmethod
    def _attributes(
        attrs: list[tuple[str, str | None]],
    ) -> tuple[dict[str, str | None], bool]:
        values: dict[str, str | None] = {}
        duplicate = False
        for key, value in attrs:
            normalized = key.casefold()
            if normalized in values:
                duplicate = True
                continue
            values[normalized] = value
        return values, duplicate

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        values, duplicate = self._attributes(attrs)
        if duplicate:
            self.invalid = True
        is_envelope = (
            values.get("data-raos-v2-post-content-envelope") == PHASE3_CONTENT_ENVELOPE
        )
        if is_envelope:
            self.envelope_count += 1
            if normalized_tag != "div" or self.depth != 0 or self.completed:
                self.invalid = True
            else:
                self.stack.append(normalized_tag)
            return
        if self.depth == 0:
            return
        if self.depth == 1:
            if (
                values.get("data-raos-v2-package-marker") != PHASE3_PACKAGE_MARKER
                or self.marker_child_count != 0
            ):
                self.invalid = True
            else:
                self.marker_child_count += 1
        if normalized_tag not in self._VOID_TAGS:
            self.stack.append(normalized_tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag, attrs
        if self.depth:
            self.invalid = True

    def handle_endtag(self, tag: str) -> None:
        if self.depth == 0:
            return
        normalized_tag = tag.casefold()
        if self.stack[-1] != normalized_tag:
            self.invalid = True
            return
        self.stack.pop()
        if self.depth == 0:
            self.completed = True

    def handle_data(self, data: str) -> None:
        if self.depth == 1 and data.strip():
            self.invalid = True

    def handle_comment(self, data: str) -> None:
        del data
        if self.depth:
            self.invalid = True


def _phase3_content_envelope_summary(html: str) -> dict[str, object]:
    parser = _Phase3ContentEnvelopeParser()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError, RecursionError, ValueError:
        parser.invalid = True
    return {
        "post_content_envelope_count": parser.envelope_count,
        "post_content_envelope_marker_child_count": parser.marker_child_count,
        "post_content_envelope_valid": (
            parser.envelope_count == 1
            and parser.marker_child_count == 1
            and parser.completed
            and parser.depth == 0
            and not parser.invalid
        ),
    }


def _phase3_json_ld_summary(
    parser: _MetadataParser, *, h1: str, canonical: str
) -> dict[str, object]:
    """Validate one sanitized Article graph against visible Phase 3 metadata."""

    allowed_types = {"Article", "BreadcrumbList", "Organization", "WebSite"}
    allowed_nested_types = allowed_types | {"ListItem"}
    typed_nodes: list[Mapping[str, object]] = []
    primary_types: list[str] = []

    def visit(value: object, *, graph_member: bool = False) -> None:
        if isinstance(value, Mapping):
            graph = value.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    visit(item, graph_member=True)
                remainder = {
                    key: item for key, item in value.items() if key != "@graph"
                }
                if remainder.get("@type") is not None:
                    visit(remainder, graph_member=graph_member)
            node_type = value.get("@type")
            node_types: list[str] = []
            if isinstance(node_type, str):
                node_types.append(node_type)
            elif isinstance(node_type, list):
                for item in node_type:
                    if isinstance(item, str):
                        node_types.append(item)
                    else:
                        parser.json_ld_invalid_count += 1
            elif node_type is not None:
                parser.json_ld_invalid_count += 1
            for item in node_types:
                if item not in allowed_nested_types:
                    parser.json_ld_invalid_count += 1
                if graph_member and item in allowed_types:
                    primary_types.append(item)
                    typed_nodes.append({**value, "@type": item})
            for key, item in value.items():
                if key not in {"@context", "@graph", "@id", "@type"}:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for document in parser.json_ld_documents:
        visit(document)
    by_type = {
        node_type: [node for node in typed_nodes if node.get("@type") == node_type]
        for node_type in allowed_types
    }
    article = by_type["Article"][0] if len(by_type["Article"]) == 1 else None
    breadcrumb = (
        by_type["BreadcrumbList"][0] if len(by_type["BreadcrumbList"]) == 1 else None
    )
    organization = (
        by_type["Organization"][0] if len(by_type["Organization"]) == 1 else None
    )
    website = by_type["WebSite"][0] if len(by_type["WebSite"]) == 1 else None
    article_page = article.get("mainEntityOfPage") if article is not None else None
    article_page_id = (
        article_page.get("@id") if isinstance(article_page, Mapping) else article_page
    )
    breadcrumb_items = (
        breadcrumb.get("itemListElement") if breadcrumb is not None else None
    )
    last_breadcrumb = (
        breadcrumb_items[-1]
        if isinstance(breadcrumb_items, list) and breadcrumb_items
        else None
    )
    last_item = (
        last_breadcrumb.get("item") if isinstance(last_breadcrumb, Mapping) else None
    )
    last_item_id = last_item.get("@id") if isinstance(last_item, Mapping) else last_item
    visible_match = (
        parser.json_ld_script_count == 1
        and parser.json_ld_invalid_count == 0
        and set(primary_types) == allowed_types
        and len(primary_types) == len(allowed_types)
        and article is not None
        and article.get("headline") == h1
        and article_page_id == canonical
        and breadcrumb is not None
        and isinstance(last_breadcrumb, Mapping)
        and last_breadcrumb.get("name") == h1
        and last_item_id == canonical
        and organization is not None
        and organization.get("url") == ORIGIN + "/"
        and website is not None
        and website.get("url") == ORIGIN + "/"
    )
    return {
        "json_ld_sha256": (
            _semantic_digest({"documents": parser.json_ld_documents})
            if parser.json_ld_documents
            else "UNAVAILABLE"
        ),
        "json_ld_types": sorted(set(primary_types)),
        "json_ld_visible_content_match": visible_match,
    }


def _phase3_expected_structured_data(
    fields: Mapping[str, object],
) -> dict[str, object]:
    headline = fields.get("post_title")
    description = fields.get("meta_description")
    canonical = fields.get("canonical_url")
    if (
        not isinstance(headline, str)
        or not headline
        or not isinstance(description, str)
        or not description
        or canonical != PHASE3_PUBLIC_URL
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
    document = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": headline,
                "description": description,
                "mainEntityOfPage": {"@id": PHASE3_PUBLIC_URL},
                "url": PHASE3_PUBLIC_URL,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": headline,
                        "item": PHASE3_PUBLIC_URL,
                    }
                ],
            },
            {"@type": "Organization", "url": ORIGIN + "/"},
            {"@type": "WebSite", "url": ORIGIN + "/"},
        ],
    }
    documents = [document]
    digest = _semantic_digest({"documents": documents})
    return {
        "schema": "RAOS_V2_PHASE3_STRUCTURED_DATA_EXPECTATION_V1",
        "version": "1.0.0",
        "derivation": "EXACT_WORDPRESS_FIELDS_V1",
        "json_ld_script_count": 1,
        "json_ld_document_count": 1,
        "json_ld_types": ["Article", "BreadcrumbList", "Organization", "WebSite"],
        "emission": {
            "owner": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION",
            "local_json_ld_emission": False,
            "external_configuration_status": "UNVERIFIED_EXTERNAL",
        },
        "documents": documents,
        "json_ld_sha256": digest,
    }


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
            headers = _collapse_response_headers(response.headers)
    except HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
        headers = _collapse_response_headers(exc.headers)
    except OSError, URLError:
        fail("RAOS_V2_CAPTURE_NETWORK_FAILURE")
    if len(payload) > MAX_RESPONSE_BYTES:
        fail("RAOS_V2_CAPTURE_RESPONSE_TOO_LARGE")
    return status, payload, headers, redirect_handler.chain


def _collapse_response_headers(headers: Any) -> dict[str, str]:
    """Preserve repeated response header values in a deterministic mapping."""

    collapsed: dict[str, str] = {}
    seen: set[str] = set()
    for key, value in headers.items():
        normalized = str(key).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        values = headers.get_all(key) if hasattr(headers, "get_all") else None
        collapsed[str(key)] = ",".join(str(item) for item in (values or [value]))
    return collapsed


def _sitemap_urls(
    *, membership_target: str | None = None
) -> tuple[set[str], list[dict[str, object]]]:
    if membership_target is not None:
        validate_public_url(membership_target)
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
        if not root.tag.startswith("{") or "}" not in root.tag:
            fail("RAOS_V2_SITEMAP_XML_INVALID")
        root_namespace, root_kind = root.tag[1:].split("}", 1)
        if root_namespace != SITEMAP_NAMESPACE:
            fail("RAOS_V2_SITEMAP_XML_INVALID")
        expected_entry = {
            "sitemapindex": "sitemap",
            "urlset": "url",
        }.get(root_kind)
        if expected_entry is None:
            fail("RAOS_V2_SITEMAP_XML_INVALID")
        entries = list(root)
        if len(entries) > MAX_SITEMAP_ENTRIES:
            fail("RAOS_V2_SITEMAP_ENTRY_LIMIT")
        locations: list[str] = []
        for entry in entries:
            if entry.tag != f"{{{SITEMAP_NAMESPACE}}}{expected_entry}":
                fail("RAOS_V2_SITEMAP_XML_INVALID")
            loc_nodes = [
                child
                for child in list(entry)
                if child.tag == f"{{{SITEMAP_NAMESPACE}}}loc"
            ]
            if len(loc_nodes) != 1 or not loc_nodes[0].text:
                fail("RAOS_V2_SITEMAP_XML_INVALID")
            locations.append(loc_nodes[0].text.strip())
        if len(locations) != len(set(locations)):
            fail("RAOS_V2_SITEMAP_XML_INVALID")
        for candidate in locations:
            validate_public_url(candidate)
            if root_kind == "sitemapindex":
                if candidate in visited or candidate in queue:
                    fail("RAOS_V2_SITEMAP_XML_INVALID")
                if len(queue) + len(visited) >= MAX_SITEMAPS:
                    fail("RAOS_V2_SITEMAP_LIMIT")
                queue.append(candidate)
            elif candidate == membership_target or len(public_urls) < MAX_CAPTURE_URLS:
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
        except OSError, subprocess.CalledProcessError:
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
                except UnicodeError, ValueError:
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


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def _content_type_media_type(headers: Mapping[str, str]) -> str:
    value = _header_value(headers, "Content-Type")
    if value is None:
        return "UNAVAILABLE"
    media_type = value.split(";", 1)[0].strip().casefold()
    return media_type or "UNAVAILABLE"


def _optional_header_sha256(headers: Mapping[str, str], name: str) -> str:
    value = _header_value(headers, name)
    if value is None or not value.strip():
        return "UNAVAILABLE"
    return sha256(value.strip().encode("utf-8"))


def _normalize_robots_directives(value: str | None) -> str:
    if value is None or not value.strip():
        return "UNAVAILABLE"
    tokens = {
        token.casefold()
        for token in re.split(r"[\s,]+", value.strip())
        if token.strip()
    }
    preferred = [token for token in ("index", "follow") if token in tokens]
    return ",".join([*preferred, *sorted(tokens - set(preferred))])


def _robots_indexability_safe(value: str) -> bool:
    if value == "UNAVAILABLE":
        return True
    tokens = set(value.split(","))
    if any("unavailable_after" in token for token in tokens):
        return False
    directives = {token.rsplit(":", 1)[-1] for token in tokens}
    return not bool(directives & {"noindex", "nofollow", "none"})


def _decode_robots_unreserved(value: str) -> str:
    """Normalize only RFC 3986 unreserved octets for robots rule matching."""

    unreserved = frozenset(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )

    def replace(match: re.Match[str]) -> str:
        decoded = chr(int(match.group(1), 16))
        return decoded if decoded in unreserved else match.group(0).upper()

    return re.sub(r"%([0-9A-Fa-f]{2})", replace, value)


def _phase3_robots_target_allowed(payload: bytes, *, status: int) -> bool:
    """Evaluate the target path for Googlebot without retaining robots.txt."""

    if status in {404, 410}:
        return True
    if status != 200:
        return False
    try:
        text = payload[:PHASE3_ROBOTS_MAX_BYTES].decode("utf-8-sig", errors="strict")
    except UnicodeError:
        return False
    groups: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []

    def commit() -> None:
        nonlocal agents, rules
        if agents:
            groups.append((tuple(agents), tuple(rules)))
        agents = []
        rules = []

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, raw_value = line.split(":", 1)
        name = field.strip().casefold()
        value = raw_value.strip()
        if name == "user-agent":
            if rules:
                commit()
            if value:
                agents.append(value.casefold())
        elif name in {"allow", "disallow"} and agents:
            rules.append((name, value))
    commit()

    def googlebot_agent(value: str) -> bool:
        return (
            value == "googlebot"
            or value.startswith("googlebot/")
            or value.startswith("googlebot*")
        )

    exact_rules = [
        rule
        for group_agents, group_rules in groups
        if any(googlebot_agent(agent) for agent in group_agents)
        for rule in group_rules
    ]
    applicable = exact_rules or [
        rule
        for group_agents, group_rules in groups
        if "*" in group_agents
        for rule in group_rules
    ]
    matches: list[tuple[int, bool]] = []
    for directive, pattern in applicable:
        if not pattern:
            continue
        candidate = _decode_robots_unreserved(pattern)
        anchored = candidate.endswith("$")
        core = candidate[:-1] if anchored else candidate
        expression = "^" + re.escape(core).replace(r"\*", ".*")
        try:
            matched = re.search(
                expression + ("$" if anchored else ""), PHASE3_PUBLIC_PATH
            )
        except re.error:
            return False
        if matched:
            specificity = len(candidate.encode("utf-8"))
            matches.append((specificity, directive == "allow"))
    if not matches:
        return True
    best = max(specificity for specificity, _allowed in matches)
    return any(allowed for specificity, allowed in matches if specificity == best)


def capture_phase3_public(*, public_read_only: bool, output: Path) -> dict[str, object]:
    """Capture the one Phase 3 migration URL, or record an offline non-run."""

    # Validate the caller-controlled path before any optional network request.
    _phase3_capture_output_path(output)
    captured_at = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    observation: dict[str, object] | None = None
    sitemap_evidence: list[dict[str, object]] = []
    plugin_stylesheet_evidence: dict[str, object] = {"status": "NOT_OBSERVED"}
    robots_txt_evidence: dict[str, object] = {"status": "NOT_OBSERVED"}
    if public_read_only:
        sitemap_members, sitemap_evidence = _sitemap_urls(
            membership_target=PHASE3_PUBLIC_URL
        )
        status, payload, headers, redirects = _fetch(PHASE3_PUBLIC_URL)
        robots_status, robots_payload, robots_headers, robots_redirects = _fetch(
            PHASE3_ROBOTS_URL
        )
        robots_txt_evidence = {
            "status": robots_status,
            "url": PHASE3_ROBOTS_URL,
            "sha256": sha256(robots_payload),
            "bytes": len(robots_payload),
            "redirect_chain": robots_redirects,
            "content_type": _header_value(robots_headers, "Content-Type")
            or "UNAVAILABLE",
            "target_path": PHASE3_PUBLIC_PATH,
            "target_allowed_for_googlebot": _phase3_robots_target_allowed(
                robots_payload, status=robots_status
            ),
            "body_storage": "DISCARDED_AFTER_HASH",
        }
        parser = _MetadataParser()
        content_type_media_type = _content_type_media_type(headers)
        decoded_html = ""
        if content_type_media_type == "text/html":
            try:
                decoded_html = payload.decode("utf-8", errors="replace")
                parser.feed(decoded_html)
                parser.close()
            except UnicodeError, ValueError:
                fail("RAOS_V2_PHASE3_CAPTURE_HTML_INVALID")

        canonical = "UNAVAILABLE"
        if parser.canonical:
            canonical = urljoin(PHASE3_PUBLIC_URL, parser.canonical)
            validate_public_url(canonical)
        robots_meta = _normalize_robots_directives(parser.robots)
        robots_http = _normalize_robots_directives(
            _header_value(headers, "X-Robots-Tag")
        )
        crawler_robots_directives = [
            _normalize_robots_directives(value)
            for value in parser.crawler_robots_values
        ]
        robots = robots_meta
        h1 = " ".join(parser.h1_parts) or "UNAVAILABLE"
        title = " ".join(parser.title_parts) or "UNAVAILABLE"
        meta_description = parser.meta_description or "UNAVAILABLE"
        if (
            len(robots) > 1024
            or len(h1) > 4096
            or len(title) > 4096
            or len(meta_description) > 4096
        ):
            fail("RAOS_V2_PHASE3_CAPTURE_METADATA_TOO_LARGE")
        json_ld = _phase3_json_ld_summary(parser, h1=h1, canonical=canonical)
        post_content = _phase3_post_content_semantic_summary(decoded_html)
        content_envelope = _phase3_content_envelope_summary(decoded_html)
        resource_inventory = parser.resource_inventory()
        expected_css_ref = _sanitized_resource_ref_sha256(
            PHASE3_PLUGIN_CSS_RESOURCE_URL
        )
        stylesheet_refs = resource_inventory.get("stylesheet_resource_sha256")
        if (
            expected_css_ref is not None
            and isinstance(stylesheet_refs, list)
            and expected_css_ref in stylesheet_refs
        ):
            css_status, css_payload, css_headers, css_redirects = _fetch(
                PHASE3_PLUGIN_CSS_URL
            )
            plugin_stylesheet_evidence = {
                "status": css_status,
                "url": PHASE3_PLUGIN_CSS_URL,
                "sha256": sha256(css_payload),
                "bytes": len(css_payload),
                "redirect_chain": css_redirects,
                "content_type": _header_value(css_headers, "Content-Type")
                or "UNAVAILABLE",
                "body_storage": "DISCARDED_AFTER_HASH",
            }
        observation = {
            "url": PHASE3_PUBLIC_URL,
            "path": PHASE3_PUBLIC_PATH,
            "status": status,
            "redirect_chain": redirects,
            "canonical": canonical,
            "canonical_tag_count": parser.canonical_tag_count,
            "head_tag_count": parser.head_tag_count,
            "metadata_location_violation_count": (
                parser.metadata_location_violation_count
            ),
            "title": title,
            "title_tag_count": parser.title_tag_count,
            "meta_description": meta_description,
            "meta_description_tag_count": parser.meta_description_tag_count,
            "robots": robots,
            "robots_meta": robots_meta,
            "robots_http": robots_http,
            "robots_http_indexability_safe": _robots_indexability_safe(robots_http),
            "content_type_media_type": content_type_media_type,
            "refresh_http_present": bool(
                (_header_value(headers, "Refresh") or "").strip()
            ),
            "link_http_sha256": _optional_header_sha256(headers, "Link"),
            "robots_tag_count": parser.robots_tag_count,
            "crawler_robots_tag_count": len(crawler_robots_directives),
            "crawler_robots_indexability_safe": all(
                _robots_indexability_safe(value) for value in crawler_robots_directives
            ),
            "h1": h1,
            "h1_count": parser.h1_count,
            "sitemap_membership": PHASE3_PUBLIC_URL in sitemap_members,
            "package_marker_count": parser.package_marker_count,
            "package_marker_attribute_count": parser.package_marker_attribute_count,
            "post_content_envelope_attribute_count": (
                parser.post_content_envelope_count
            ),
            "blocked_post_content_envelope_count": (
                parser.blocked_post_content_envelope_count
            ),
            **content_envelope,
            **post_content,
            "disclosure_marker_count": parser.disclosure_marker_count,
            "cta_state_count": parser.cta_state_count,
            "blocked_cta_count": parser.blocked_cta_count,
            "affiliate_url_count": parser.affiliate_url_count,
            "ambiguous_attribute_count": parser.ambiguous_attribute_count,
            "image_count": parser.image_count,
            "inline_executable_script_count": parser.inline_executable_script_count,
            "external_script_count": parser.external_script_count,
            "resource_inventory": resource_inventory,
            "json_ld_script_count": parser.json_ld_script_count,
            "json_ld_invalid_count": parser.json_ld_invalid_count,
            **json_ld,
            "body_sha256": sha256(payload),
            "body_bytes": len(payload),
            "body_storage": "DISCARDED_AFTER_HASH",
            "observed_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        }

    document = {
        "schema": "RAOS_V2_PHASE3_PUBLIC_CAPTURE_V1",
        "version": "1.0.0",
        "captured_at": captured_at,
        "target_url": PHASE3_PUBLIC_URL,
        "public_observation_status": (
            "PUBLIC_READ_ONLY" if public_read_only else "NOT_EXECUTED"
        ),
        "observation": observation,
        "supporting_resources": {
            "sitemaps": sitemap_evidence,
            "plugin_stylesheet": plugin_stylesheet_evidence,
            "robots_txt": robots_txt_evidence,
            "sitemap_root": f"{ORIGIN}/sitemap_index.xml",
            "maximum_sitemaps": MAX_SITEMAPS,
        },
        "request_policy": {
            "target_page_count": 1,
            "maximum_page_and_asset_requests": 3,
            "same_origin_only": True,
            "https_only": True,
            "credentials": "NOT_USED",
            "cookies": "NOT_USED",
            "query_strings": "REJECTED",
            "environment_proxies": "DISABLED",
            "maximum_redirects_per_request": MAX_REDIRECTS,
        },
        "external_write_actions": "NOT_EXECUTED",
        "phase0_baseline_write": "PROHIBITED",
    }
    _write_new_phase3_capture(output, canonical_json_bytes(document))
    return document


def _phase3_capture_observation(
    capture: Mapping[str, object], *, code: str
) -> tuple[dict[str, object], datetime, datetime]:
    if (
        set(capture) != PHASE3_CAPTURE_KEYS
        or capture.get("schema") != "RAOS_V2_PHASE3_PUBLIC_CAPTURE_V1"
        or capture.get("version") != "1.0.0"
        or capture.get("target_url") != PHASE3_PUBLIC_URL
        or capture.get("public_observation_status") != "PUBLIC_READ_ONLY"
        or capture.get("external_write_actions") != "NOT_EXECUTED"
        or capture.get("phase0_baseline_write") != "PROHIBITED"
    ):
        fail(code)
    request_policy = _mapping(capture.get("request_policy"), code)
    if request_policy != {
        "target_page_count": 1,
        "maximum_page_and_asset_requests": 3,
        "same_origin_only": True,
        "https_only": True,
        "credentials": "NOT_USED",
        "cookies": "NOT_USED",
        "query_strings": "REJECTED",
        "environment_proxies": "DISABLED",
        "maximum_redirects_per_request": MAX_REDIRECTS,
    }:
        fail(code)
    supporting = _mapping(capture.get("supporting_resources"), code)
    sitemaps = supporting.get("sitemaps")
    if (
        set(supporting)
        != {
            "sitemaps",
            "plugin_stylesheet",
            "robots_txt",
            "sitemap_root",
            "maximum_sitemaps",
        }
        or supporting.get("sitemap_root") != f"{ORIGIN}/sitemap_index.xml"
        or supporting.get("maximum_sitemaps") != MAX_SITEMAPS
        or not isinstance(sitemaps, list)
        or not 1 <= len(sitemaps) <= MAX_SITEMAPS
    ):
        fail(code)
    for row_value in sitemaps:
        row = _mapping(row_value, code)
        url = row.get("url")
        if (
            set(row) != {"url", "status", "redirect_chain", "sha256"}
            or not isinstance(url, str)
            or urlsplit(url).scheme != "https"
            or f"{urlsplit(url).scheme}://{urlsplit(url).netloc}" != ORIGIN
            or bool(urlsplit(url).query)
            or urlsplit(url).fragment != ""
            or row.get("status") != 200
            or row.get("redirect_chain") != []
            or not isinstance(row.get("sha256"), str)
            or HEX64.fullmatch(str(row.get("sha256"))) is None
        ):
            fail(code)
    _phase3_robots_txt_evidence(capture, required=True, code=code)
    plugin_evidence = _mapping(supporting.get("plugin_stylesheet"), code)
    _phase3_plugin_stylesheet_evidence(
        capture,
        required=plugin_evidence.get("status") != "NOT_OBSERVED",
        code=code,
    )
    observation = _mapping(capture.get("observation"), code)
    if (
        set(observation) != PHASE3_OBSERVATION_KEYS
        or observation.get("url") != PHASE3_PUBLIC_URL
        or observation.get("path") != PHASE3_PUBLIC_PATH
    ):
        fail(code)
    _phase3_resource_inventory(observation.get("resource_inventory"), code=code)
    try:
        captured_at = datetime.fromisoformat(str(capture.get("captured_at")))
        observed_at = datetime.fromisoformat(str(observation.get("observed_at")))
    except ValueError:
        fail(code)
    if (
        captured_at.tzinfo is None
        or captured_at.utcoffset() is None
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
        or captured_at > observed_at
    ):
        fail(code)
    return observation, captured_at, observed_at


def _phase3_export_binding_digest(
    export_binding: Mapping[str, object],
    *,
    fields: Mapping[str, object],
    body_sha256: str,
    preaction_binding_sha256: str,
    preaction_post_id: int,
) -> tuple[str, datetime]:
    code = "RAOS_V2_PUBLIC_VERIFICATION_EXPORT_INVALID"
    expected_keys = {
        "schema",
        "version",
        "export_role",
        "target",
        "captured_at",
        "field_hashes",
        "public_body_sha256",
        "preaction_binding_sha256",
        "export_sha256",
        "export_bytes",
        "restore_artifact_sha256",
        "theme_artifact_sha256",
        "seo_state_sha256",
        "redirect_map_sha256",
        "sitemap_state_sha256",
        "raw_export_location",
        "status",
    }
    if (
        set(export_binding) != expected_keys
        or export_binding.get("schema") != "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2"
        or export_binding.get("version") != "2.0.0"
        or export_binding.get("export_role") != "POST_ACTION_OWNER_EXPORT"
        or export_binding.get("raw_export_location") != "OWNER_STORAGE_ONLY_NOT_GIT"
        or export_binding.get("status") != "VERIFIED_HUMAN_EXPORT"
        or export_binding.get("public_body_sha256") != body_sha256
        or export_binding.get("preaction_binding_sha256") != preaction_binding_sha256
    ):
        fail(code)
    target = _mapping(export_binding.get("target"), code)
    if target != {
        "origin": ORIGIN,
        "route": PHASE3_PUBLIC_PATH,
        "kind": "EXISTING_POST",
        "post_id": preaction_post_id,
        "exact_match_count": 1,
    }:
        fail(code)
    hashes = _mapping(export_binding.get("field_hashes"), code)
    if set(hashes) != PHASE3_WORDPRESS_FIELD_NAMES or set(fields) != (
        PHASE3_WORDPRESS_FIELD_NAMES
    ):
        fail(code)
    expected_hashes = {
        name: _semantic_digest({"field": name, "value": fields[name]})
        for name in sorted(PHASE3_WORDPRESS_FIELD_NAMES)
    }
    digest_names = (
        "export_sha256",
        "restore_artifact_sha256",
        "theme_artifact_sha256",
        "seo_state_sha256",
        "redirect_map_sha256",
        "sitemap_state_sha256",
    )
    if hashes != expected_hashes or any(
        not isinstance(export_binding.get(name), str)
        or HEX64.fullmatch(str(export_binding.get(name))) is None
        for name in digest_names
    ):
        fail(code)
    export_bytes = export_binding.get("export_bytes")
    if (
        not isinstance(export_bytes, int)
        or isinstance(export_bytes, bool)
        or export_bytes < 1
    ):
        fail(code)
    try:
        captured_at = datetime.fromisoformat(str(export_binding.get("captured_at")))
    except ValueError:
        fail(code)
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        fail(code)
    return _semantic_digest(export_binding), captured_at


def _phase3_plugin_artifacts() -> dict[str, object]:
    """Bind the public stylesheet to the reviewed, repository-owned plugin."""

    code = "RAOS_V2_PUBLIC_VERIFICATION_PLUGIN_ARTIFACT_INVALID"
    root = ROOT / PHASE3_PLUGIN_ARTIFACT_ROOT
    paths = {
        "stylesheet": root / "assets/decision-support.css",
        "binding": root / "cutover-binding.v1.json",
        "php": root / "raos-v2-decision-support.php",
        "manifest": root / "plugin-manifest.v1.json",
        "post_content": (ROOT / "changes/raos-v2/phase-3/generated/post-content.html"),
    }
    payloads: dict[str, bytes] = {}
    for name, path in paths.items():
        try:
            if path.is_symlink() or not path.is_file():
                fail(code)
            payload = path.read_bytes()
        except OSError:
            fail(code)
        if not payload or len(payload) > MAX_RESPONSE_BYTES:
            fail(code)
        payloads[name] = payload
    manifest = _mapping(load_json_strict(payloads["manifest"]), code)
    expected_post_content_sha256 = sha256(payloads["post_content"])
    expected_php_constant = (
        "const RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256 = "
        f"'{expected_post_content_sha256}';"
    ).encode("ascii")
    expected_binding = {
        "schema": "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1",
        "version": "1.0.0",
        "state": "DEPLOYMENT_DISABLED",
        "target": {
            "article_id": "A05",
            "post_id": 0,
            "post_slug": "carry-on-suitcase-comparison",
            "route": PHASE3_PUBLIC_PATH,
        },
        "hashes": {
            "legacy_post_content_sha256": "UNAVAILABLE",
            "preaction_binding_sha256": "UNAVAILABLE",
            "sealed_package_sha256": "UNAVAILABLE",
            "sealed_post_content_sha256": expected_post_content_sha256,
            "source_owner_export_sha256": "UNAVAILABLE",
        },
    }
    expected_cutover_contract = {
        "adjacent_file": "cutover-binding.v1.json",
        "required_schema": "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1",
        "required_version": "1.0.0",
        "tracked_state": "DEPLOYMENT_DISABLED",
        "activation_state": "ARMED_EXACT_LEGACY_OR_SEALED",
        "source": "PREACTION_OWNER_EXPORT",
        "required_hashes": [
            "legacy_post_content_sha256",
            "preaction_binding_sha256",
            "sealed_package_sha256",
            "sealed_post_content_sha256",
            "source_owner_export_sha256",
        ],
    }
    file_rows = [
        {
            "path": "raos-v2-decision-support.php",
            "bytes": len(payloads["php"]),
            "sha256": sha256(payloads["php"]),
        },
        {
            "path": "cutover-binding.v1.json",
            "bytes": len(payloads["binding"]),
            "sha256": sha256(payloads["binding"]),
        },
        {
            "path": "assets/decision-support.css",
            "bytes": len(payloads["stylesheet"]),
            "sha256": sha256(payloads["stylesheet"]),
        },
    ]
    if (
        manifest.get("schema") != "RAOS_V2_WORDPRESS_PRESENTATION_PLUGIN_INPUT_V1"
        or manifest.get("plugin_slug") != "raos-v2-decision-support"
        or manifest.get("version") != "0.6.0"
        or manifest.get("target")
        != {
            "article_id": "A05",
            "exact_route": PHASE3_PUBLIC_PATH,
            "exact_post_slug": "carry-on-suitcase-comparison",
            "expected_post_id": "CUTOVER_BINDING_REQUIRED",
            "required_package_marker": PHASE3_PACKAGE_MARKER,
            "required_post_content_sha256": expected_post_content_sha256,
            "rendered_content_envelope": PHASE3_CONTENT_ENVELOPE,
        }
        or manifest.get("cutover_binding") != expected_cutover_contract
        or manifest.get("source_files")
        != [
            "assets/decision-support.css",
            "cutover-binding.v1.json",
            "raos-v2-decision-support.php",
        ]
        or manifest.get("installation")
        != (
            "INSTALL_INACTIVE_REPLACE_BINDING_ACTIVATE_THEN_WRITE_"
            "EXTERNAL_HUMAN_ACTIONS_NOT_EXECUTED"
        )
        or load_json_strict(payloads["binding"]) != expected_binding
        or payloads["php"].count(expected_php_constant) != 1
        or payloads["php"].count(b"const RAOS_V2_DECISION_SUPPORT_VERSION = '0.6.0';")
        != 1
        or manifest.get("classification")
        != "LOCAL_ARTIFACT_TEMPLATE_REQUIRES_OWNER_CUTOVER_BINDING"
        or manifest.get("files") != file_rows
        or manifest.get("artifact_sha256")
        != sha256(canonical_json_bytes({"files": file_rows}))
        or manifest.get("source_root") != PHASE3_PLUGIN_SOURCE_ROOT.as_posix()
        or manifest.get("external_action_id") != "EXT-004"
        or manifest.get("deployment_status") != "NOT_EXECUTED"
        or manifest.get("backlog_id") != "B-V2-036"
        or manifest.get("requirement_ids") != ["R-V2-006", "R-V2-024", "R-V2-033"]
        or manifest.get("test_ids") != ["T-V2-008", "T-V2-039", "T-V2-051"]
    ):
        fail(code)
    runtime = _mapping(manifest.get("runtime"), code)
    if (
        runtime.get("allowed_effect")
        != (
            "LEGACY_FILTERED_PASSTHROUGH_OR_SEALED_RAW_ENQUEUE_AND_ENVELOPE_"
            "OTHERWISE_BLOCK_TARGET"
        )
        or runtime.get("activation_gate")
        != "REPLACE_BINDING_THEN_ACTIVATE_BEFORE_SEALED_WRITE"
        or runtime.get("content_filter")
        != (
            "EXACT_RAW_DATABASE_STATE_FAIL_CLOSED_EARLIER_SEALED_FILTER_OUTPUT_"
            "DISCARDED"
        )
        or runtime.get("content_filter_position")
        != "TERMINATE_503_IF_NOT_LAST_AT_PHP_INT_MAX"
        or runtime.get("content_context_gate")
        != "SINGULAR_TARGET_REQUEST_VERIFIED_CURRENT_POST_MAIN_QUERY_MAIN_LOOP"
        or runtime.get("disabled_binding_behavior") != "BLOCK_TARGET_ROUTE"
        or runtime.get("exact_legacy_behavior")
        != "PRESERVE_EXISTING_FILTERED_CONTENT_WITHOUT_CSS_OR_ENVELOPE"
        or runtime.get("exact_sealed_behavior")
        != (
            "DISCARD_FILTERED_CANDIDATE_AND_ENVELOPE_EXACT_RAW_REVIEWED_"
            "FRAGMENT_WITH_CSS"
        )
        or runtime.get("inactive_behavior")
        != (
            "NO_RUNTIME_EFFECT_WRITE_BEFORE_ACTIVATION_IS_UNPROTECTED_AND_" "PROHIBITED"
        )
        or runtime.get("ambiguous_content_behavior") != "BLOCK_TARGET_ROUTE"
        or runtime.get("intermediate_content_behavior") != "BLOCK_TARGET_ROUTE"
        or runtime.get("post_render_verification")
        != "PUBLIC_CAPTURE_AND_BROWSER_RECEIPT_REQUIRED"
        or runtime.get("safe_cutover_order")
        != [
            "REPLACE_DISABLED_BINDING_WITH_OWNER_EXPORT_BOUND_ARTIFACT",
            "ACTIVATE_PLUGIN_WHILE_EXACT_LEGACY_BYTES_REMAIN",
            "WRITE_EXACT_SEALED_DATABASE_BYTES",
        ]
        or runtime.get("secondary_content_behavior")
        != "PRESERVE_FILTERED_INPUT_ONLY_FOR_VERIFIED_DIFFERENT_CURRENT_POST"
        or any(
            runtime.get(name) is not False
            for name in (
                "admin_ui",
                "cron",
                "database_write",
                "network_request",
                "option_write",
                "publication_capability",
                "rest_route",
                "telemetry",
            )
        )
    ):
        fail(code)
    return {
        "plugin_stylesheet_content_sha256": sha256(payloads["stylesheet"]),
        "plugin_stylesheet_bytes": len(payloads["stylesheet"]),
        "plugin_php_sha256": sha256(payloads["php"]),
        "plugin_manifest_sha256": sha256(payloads["manifest"]),
        "sealed_post_content_sha256": expected_post_content_sha256,
    }


def _phase3_plugin_stylesheet_evidence(
    capture: Mapping[str, object], *, required: bool, code: str
) -> dict[str, object]:
    resources = _mapping(capture.get("supporting_resources"), code)
    if set(resources) != {
        "sitemaps",
        "plugin_stylesheet",
        "robots_txt",
        "sitemap_root",
        "maximum_sitemaps",
    }:
        fail(code)
    if (
        not isinstance(resources.get("sitemaps"), list)
        or resources.get("sitemap_root") != f"{ORIGIN}/sitemap_index.xml"
        or resources.get("maximum_sitemaps") != MAX_SITEMAPS
    ):
        fail(code)
    evidence = _mapping(resources.get("plugin_stylesheet"), code)
    if not required:
        if evidence != {"status": "NOT_OBSERVED"}:
            fail(code)
        return evidence
    artifacts = _phase3_plugin_artifacts()
    if (
        set(evidence)
        != {
            "status",
            "url",
            "sha256",
            "bytes",
            "redirect_chain",
            "content_type",
            "body_storage",
        }
        or evidence.get("status") != 200
        or evidence.get("url") != PHASE3_PLUGIN_CSS_URL
        or evidence.get("sha256") != artifacts["plugin_stylesheet_content_sha256"]
        or evidence.get("bytes") != artifacts["plugin_stylesheet_bytes"]
        or evidence.get("redirect_chain") != []
        or not str(evidence.get("content_type", "")).casefold().startswith("text/css")
        or evidence.get("body_storage") != "DISCARDED_AFTER_HASH"
    ):
        fail(code)
    return evidence


def _phase3_robots_txt_evidence(
    capture: Mapping[str, object], *, required: bool, code: str
) -> dict[str, object]:
    resources = _mapping(capture.get("supporting_resources"), code)
    evidence = _mapping(resources.get("robots_txt"), code)
    if not required:
        if evidence != {"status": "NOT_OBSERVED"}:
            fail(code)
        return evidence
    if (
        set(evidence)
        != {
            "status",
            "url",
            "sha256",
            "bytes",
            "redirect_chain",
            "content_type",
            "target_path",
            "target_allowed_for_googlebot",
            "body_storage",
        }
        or evidence.get("status") not in {200, 404, 410}
        or evidence.get("url") != PHASE3_ROBOTS_URL
        or not isinstance(evidence.get("sha256"), str)
        or HEX64.fullmatch(str(evidence.get("sha256"))) is None
        or not isinstance(evidence.get("bytes"), int)
        or isinstance(evidence.get("bytes"), bool)
        or int(evidence["bytes"]) < 0
        or evidence.get("redirect_chain") != []
        or evidence.get("target_path") != PHASE3_PUBLIC_PATH
        or evidence.get("target_allowed_for_googlebot") is not True
        or evidence.get("body_storage") != "DISCARDED_AFTER_HASH"
    ):
        fail(code)
    return evidence


def _phase3_resource_inventory(value: object, *, code: str) -> dict[str, object]:
    inventory = _mapping(value, code)
    list_fields = {
        "script_resource_sha256",
        "image_resource_sha256",
        "stylesheet_resource_sha256",
        "active_resource_sha256",
        "inline_executable_script_sha256",
        "inline_style_sha256",
        "executable_attribute_sha256",
    }
    if set(inventory) != {*list_fields, "unsafe_resource_count"}:
        fail(code)
    for name in list_fields:
        rows = inventory.get(name)
        if (
            not isinstance(rows, list)
            or rows != sorted(rows)
            or any(
                not isinstance(row, str) or HEX64.fullmatch(row) is None for row in rows
            )
        ):
            fail(code)
    if inventory.get("unsafe_resource_count") != 0:
        fail(code)
    return inventory


def _validate_phase3_publication_package_schema(
    value: Mapping[str, object],
    *,
    root: Path = ROOT,
) -> None:
    code = "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
    registry = Registry()
    publication_schema: Mapping[str, object] | None = None
    try:
        for version, name, document in _contract_schema_documents(root=root, code=code):
            Draft202012Validator.check_schema(document)
            identifier = document.get("$id")
            if not isinstance(identifier, str):
                fail(code)
            registry = registry.with_resource(
                identifier, Resource.from_contents(document)
            )
            if version == "v2" and name == "publication-package.schema.json":
                publication_schema = document
        if publication_schema is None:
            fail(code)
        errors = list(
            Draft202012Validator(
                publication_schema,
                registry=registry,
                format_checker=FormatChecker(),
            ).iter_errors(value)
        )
    except Exception as exc:
        if isinstance(exc, ValidationFailure):
            raise
        fail(code)
    if errors:
        fail(code)


def derive_phase3_public_verification_receipt(
    *,
    preaction_capture: Mapping[str, object],
    capture: Mapping[str, object],
    sealed_package: Mapping[str, object],
    post_action_export_binding: Mapping[str, object],
    evaluated_at: datetime,
    rollback_invoked: bool,
) -> dict[str, object]:
    """Derive—not self-assert—the strict, time-bound public receipt."""

    if (
        rollback_invoked is not False
        or not isinstance(evaluated_at, datetime)
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    _phase3_robots_txt_evidence(
        capture,
        required=True,
        code="RAOS_V2_PUBLIC_VERIFICATION_ROBOTS_INVALID",
    )
    _phase3_plugin_stylesheet_evidence(
        capture,
        required=True,
        code="RAOS_V2_PUBLIC_VERIFICATION_PLUGIN_STYLESHEET_INVALID",
    )
    observation, captured_at, observed_at = _phase3_capture_observation(
        capture, code="RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID"
    )
    preaction_observation, preaction_captured_at, preaction_observed_at = (
        _phase3_capture_observation(
            preaction_capture,
            code="RAOS_V2_PUBLIC_VERIFICATION_PREACTION_INVALID",
        )
    )
    if (
        preaction_observation.get("url") != PHASE3_PUBLIC_URL
        or preaction_observation.get("path") != PHASE3_PUBLIC_PATH
        or preaction_observation.get("status") != 200
        or preaction_observation.get("redirect_chain") != []
        or preaction_observation.get("canonical") != PHASE3_PUBLIC_URL
        or preaction_observation.get("canonical_tag_count") != 1
        or preaction_observation.get("head_tag_count") != 1
        or preaction_observation.get("metadata_location_violation_count") != 0
        or preaction_observation.get("content_type_media_type") != "text/html"
        or preaction_observation.get("refresh_http_present") is not False
        or (
            preaction_observation.get("link_http_sha256") != "UNAVAILABLE"
            and (
                not isinstance(preaction_observation.get("link_http_sha256"), str)
                or HEX64.fullmatch(str(preaction_observation["link_http_sha256"]))
                is None
            )
        )
        or not isinstance(preaction_observation.get("crawler_robots_tag_count"), int)
        or isinstance(preaction_observation.get("crawler_robots_tag_count"), bool)
        or int(preaction_observation["crawler_robots_tag_count"]) < 0
        or preaction_observation.get("crawler_robots_indexability_safe") is not True
        or preaction_observation.get("ambiguous_attribute_count") != 0
        or not isinstance(preaction_observation.get("body_sha256"), str)
        or HEX64.fullmatch(str(preaction_observation.get("body_sha256"))) is None
        or preaction_observation.get("body_storage") != "DISCARDED_AFTER_HASH"
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PREACTION_INVALID")
    preaction_resources = _phase3_resource_inventory(
        preaction_observation.get("resource_inventory"),
        code="RAOS_V2_PUBLIC_VERIFICATION_PREACTION_INVALID",
    )
    public_resources = _phase3_resource_inventory(
        observation.get("resource_inventory"),
        code="RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID",
    )
    _phase3_plugin_stylesheet_evidence(
        preaction_capture,
        required=False,
        code="RAOS_V2_PUBLIC_VERIFICATION_PREACTION_INVALID",
    )
    plugin_stylesheet_evidence = _phase3_plugin_stylesheet_evidence(
        capture,
        required=True,
        code="RAOS_V2_PUBLIC_VERIFICATION_PLUGIN_STYLESHEET_INVALID",
    )
    plugin_artifacts = _phase3_plugin_artifacts()
    _phase3_robots_txt_evidence(
        preaction_capture,
        required=True,
        code="RAOS_V2_PUBLIC_VERIFICATION_PREACTION_ROBOTS_INVALID",
    )
    robots_txt_evidence = _phase3_robots_txt_evidence(
        capture,
        required=True,
        code="RAOS_V2_PUBLIC_VERIFICATION_ROBOTS_INVALID",
    )
    immutable_resource_fields = {
        "script_resource_sha256",
        "image_resource_sha256",
        "active_resource_sha256",
        "inline_executable_script_sha256",
        "inline_style_sha256",
        "executable_attribute_sha256",
    }
    if any(
        public_resources[name] != preaction_resources[name]
        for name in immutable_resource_fields
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_RESOURCE_DRIFT")
    expected_plugin_css = _sanitized_resource_ref_sha256(PHASE3_PLUGIN_CSS_RESOURCE_URL)
    before_styles = preaction_resources["stylesheet_resource_sha256"]
    after_styles = public_resources["stylesheet_resource_sha256"]
    if (
        expected_plugin_css is None
        or not isinstance(before_styles, list)
        or not isinstance(after_styles, list)
        or expected_plugin_css in before_styles
        or after_styles != sorted([*before_styles, expected_plugin_css])
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_RESOURCE_DRIFT")
    expected_package_keys = {
        "schema",
        "version",
        "state",
        "review_candidate",
        "human_review_receipt",
        "simulation_only",
        "approval_acceptance_authority",
        "structured_data_expectation_sha256",
        "capabilities",
        "package_digest",
    }
    if set(sealed_package) != expected_package_keys:
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    _validate_phase3_publication_package_schema(sealed_package)
    package_digest = sealed_package.get("package_digest")
    semantic_package = dict(sealed_package)
    semantic_package.pop("package_digest", None)
    if (
        sealed_package.get("schema") != "RAOS_V2_PHASE3_PUBLICATION_PACKAGE_V1"
        or sealed_package.get("version") != "1.0.0"
        or sealed_package.get("state") != "PACKAGE_SEALED"
        or sealed_package.get("capabilities")
        != {"network": False, "wordpress_write": False, "publish": False}
        or not isinstance(package_digest, str)
        or HEX64.fullmatch(package_digest) is None
        or package_digest != _semantic_digest(semantic_package)
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
    candidate = _mapping(
        sealed_package.get("review_candidate"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    phase2 = _mapping(
        candidate.get("phase2_candidate"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    expected_phase2 = _mapping(
        load_json_strict(
            _repository_regular_file_bytes(
                Path(
                    "changes/raos-v2/phase-2/generated/" "publication-candidate.v2.json"
                ),
                root=ROOT,
                maximum=MAX_RESPONSE_BYTES,
                code="RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
            )
        ),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    update = _mapping(
        candidate.get("update_payload"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    fields = _mapping(
        update.get("fields"), "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
    )
    preaction = _mapping(
        update.get("preaction"), "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
    )
    preaction_binding = _mapping(
        preaction.get("binding"), "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
    )
    preaction_target = _mapping(
        preaction_binding.get("target"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    structured_data = _mapping(
        update.get("structured_data_expectation"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    review = _mapping(
        sealed_package.get("human_review_receipt"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    bindings = _rows(
        candidate.get("claim_bindings"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    phase2_bindings = _rows(
        phase2.get("claim_evidence"),
        "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    )
    phase2_by_id = {
        str(binding.get("claim_id")): binding for binding in phase2_bindings
    }
    phase3_by_id = {str(binding.get("claim_id")): binding for binding in bindings}
    if (
        not bindings
        or len(phase2_by_id) != len(phase2_bindings)
        or len(phase3_by_id) != len(bindings)
        or set(phase2_by_id) != set(phase3_by_id)
        or any(
            phase3_by_id[claim_id].get("risk_class")
            != phase2_by_id[claim_id].get("risk_class")
            or phase3_by_id[claim_id].get("freshness")
            != phase2_by_id[claim_id].get("freshness")
            for claim_id in phase2_by_id
        )
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
    expected_structured_data = _phase3_expected_structured_data(fields)
    structured_data_sha256 = expected_structured_data["json_ld_sha256"]
    expected_preaction_keys = {
        "schema",
        "version",
        "status",
        "provenance",
        "captured_at",
        "target",
        "current_public_body_sha256",
        "public_capture_sha256",
        "wordpress_export_sha256",
        "wordpress_export_bytes",
        "owner_evidence_sha256",
        "legacy_post_content_sha256",
    }
    preaction_binding_digest = preaction.get("binding_digest")
    preaction_body_sha256 = preaction_binding.get("current_public_body_sha256")
    preaction_post_id = preaction_target.get("post_id")
    if (
        candidate.get("candidate_digest") != _semantic_digest(phase2)
        or phase2 != expected_phase2
        or candidate.get("payload_digest") != _semantic_digest(update)
        or review.get("candidate_digest") != candidate.get("candidate_digest")
        or review.get("payload_digest") != candidate.get("payload_digest")
        or review.get("accepted") is not True
        or review.get("synthetic") is not False
        or review.get("assertion_status") != "UNAUTHENTICATED_OWNER_ASSERTION"
        or review.get("acceptance_authority") is not False
        or sealed_package.get("simulation_only") is not True
        or sealed_package.get("approval_acceptance_authority") is not False
        or phase2.get("target_origin") != ORIGIN
        or phase2.get("target_route") != PHASE3_PUBLIC_PATH
        or update.get("intent") != "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"
        or fields.get("post_status") != "publish"
        or structured_data != expected_structured_data
        or candidate.get("structured_data_expectation_sha256") != structured_data_sha256
        or sealed_package.get("structured_data_expectation_sha256")
        != structured_data_sha256
        or set(preaction) != {"status", "binding_digest", "binding"}
        or preaction.get("status") != "VERIFIED_PREACTION"
        or set(preaction_binding) != expected_preaction_keys
        or preaction_binding.get("schema") != "RAOS_V2_PHASE3_PREACTION_BINDING_V1"
        or preaction_binding.get("version") != "1.0.0"
        or preaction_binding.get("status") != "VERIFIED_PREACTION"
        or preaction_binding.get("provenance")
        != "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT"
        or preaction_target
        != {
            "origin": ORIGIN,
            "route": PHASE3_PUBLIC_PATH,
            "kind": "EXISTING_POST",
            "post_id": preaction_post_id,
            "exact_match_count": 1,
        }
        or not isinstance(preaction_post_id, int)
        or isinstance(preaction_post_id, bool)
        or preaction_post_id < 1
        or not isinstance(preaction_binding_digest, str)
        or HEX64.fullmatch(preaction_binding_digest) is None
        or preaction_binding_digest != _semantic_digest(preaction_binding)
        or candidate.get("preaction_status") != "VERIFIED_PREACTION"
        or candidate.get("preaction_binding_digest") != preaction_binding_digest
        or preaction_binding.get("public_capture_sha256")
        != _semantic_digest(preaction_capture)
        or not isinstance(preaction_body_sha256, str)
        or HEX64.fullmatch(preaction_body_sha256) is None
        or preaction_body_sha256 != preaction_observation.get("body_sha256")
        or _mapping(
            update.get("target"), "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
        ).get("expected_public_body_sha256")
        != preaction_body_sha256
        or not isinstance(preaction_binding.get("wordpress_export_sha256"), str)
        or HEX64.fullmatch(str(preaction_binding.get("wordpress_export_sha256")))
        is None
        or not isinstance(preaction_binding.get("wordpress_export_bytes"), int)
        or isinstance(preaction_binding.get("wordpress_export_bytes"), bool)
        or int(preaction_binding["wordpress_export_bytes"]) < 1
        or not isinstance(preaction_binding.get("owner_evidence_sha256"), str)
        or HEX64.fullmatch(str(preaction_binding.get("owner_evidence_sha256"))) is None
        or not isinstance(preaction_binding.get("legacy_post_content_sha256"), str)
        or HEX64.fullmatch(str(preaction_binding.get("legacy_post_content_sha256")))
        is None
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
    try:
        reviewed_at = datetime.fromisoformat(str(review.get("reviewed_at")))
        preaction_binding_captured_at = datetime.fromisoformat(
            str(preaction_binding.get("captured_at"))
        )
    except ValueError:
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    if (
        any(
            instant.tzinfo is None or instant.utcoffset() is None
            for instant in (reviewed_at, preaction_binding_captured_at)
        )
        or not (
            preaction_captured_at
            <= preaction_observed_at
            <= preaction_binding_captured_at
            <= reviewed_at
            <= captured_at
            <= observed_at
            <= evaluated_at
        )
        or (evaluated_at - observed_at).total_seconds()
        > PHASE3_PUBLIC_CAPTURE_MAX_AGE_SECONDS
        or (evaluated_at - captured_at).total_seconds()
        > PHASE3_PUBLIC_CAPTURE_MAX_AGE_SECONDS
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    authority_rows: list[dict[str, object]] = []
    for binding in sorted(bindings, key=lambda row: str(row.get("claim_id"))):
        try:
            checked_at = datetime.fromisoformat(str(binding.get("checked_at")))
            next_review_at = datetime.fromisoformat(str(binding.get("next_review_at")))
        except ValueError:
            fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
        claim_type = binding.get("claim_type")
        source_status = binding.get("authoritative_source_status")
        expected_resolved = claim_type != "UNKNOWN" and source_status == "VERIFIED"
        expected_blocking = (
            source_status != "BLOCKED"
            if claim_type == "UNKNOWN"
            else source_status != "VERIFIED"
        )
        expected_disclosed = claim_type == "UNKNOWN" and source_status == "BLOCKED"
        safe_freshness = (
            binding.get("freshness") in {"UNKNOWN", "UNAVAILABLE"}
            if claim_type == "UNKNOWN"
            else binding.get("freshness") in {"FRESH", "DUE"}
        )
        if (
            checked_at.tzinfo is None
            or checked_at.utcoffset() is None
            or next_review_at.tzinfo is None
            or next_review_at.utcoffset() is None
            or not checked_at <= evaluated_at < next_review_at
            or binding.get("resolved") is not expected_resolved
            or binding.get("blocking") is not expected_blocking
            or binding.get("intentionally_disclosed") is not expected_disclosed
            or expected_blocking
            or not safe_freshness
        ):
            fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_STALE")
        authority_rows.append(
            {
                key: binding.get(key)
                for key in (
                    "claim_id",
                    "claim_type",
                    "risk_class",
                    "freshness",
                    "authoritative_source_status",
                    "checked_at",
                    "next_review_at",
                )
            }
        )
    phase2_hashes = _mapping(
        phase2.get("input_hashes"), "RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID"
    )
    if phase2_hashes.get("phase3_claim_authority") != _semantic_digest(
        {
            "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
            "version": "1.0.0",
            "claims": authority_rows,
        }
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID")
    post_content = fields.get("post_content")
    post_title = fields.get("post_title")
    body_digest = observation.get("body_sha256")
    if (
        not isinstance(body_digest, str)
        or HEX64.fullmatch(body_digest) is None
        or not isinstance(preaction_binding_digest, str)
        or not isinstance(preaction_post_id, int)
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    post_action_export_binding_sha256, post_action_export_captured_at = (
        _phase3_export_binding_digest(
            post_action_export_binding,
            fields=fields,
            body_sha256=body_digest,
            preaction_binding_sha256=preaction_binding_digest,
            preaction_post_id=preaction_post_id,
        )
    )
    if (
        post_action_export_captured_at < reviewed_at
        or post_action_export_captured_at > captured_at
        or (evaluated_at - post_action_export_captured_at).total_seconds()
        > PHASE3_PUBLIC_CAPTURE_MAX_AGE_SECONDS
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_EXPORT_STALE")
    sealed_post_content = (
        _phase3_post_content_semantic_summary(post_content)
        if isinstance(post_content, str)
        else {}
    )
    semantic_post_content_sha256 = sealed_post_content.get(
        "post_content_semantic_sha256"
    )
    if (
        not isinstance(post_content, str)
        or post_content.count(PHASE3_PACKAGE_MARKER) != 1
        or not isinstance(post_title, str)
        or not post_title
        or observation.get("url") != PHASE3_PUBLIC_URL
        or observation.get("path") != PHASE3_PUBLIC_PATH
        or observation.get("status") != 200
        or observation.get("redirect_chain") != []
        or observation.get("canonical") != PHASE3_PUBLIC_URL
        or observation.get("canonical_tag_count") != 1
        or observation.get("head_tag_count") != 1
        or observation.get("metadata_location_violation_count") != 0
        or observation.get("content_type_media_type") != "text/html"
        or observation.get("refresh_http_present") is not False
        or observation.get("link_http_sha256")
        != preaction_observation.get("link_http_sha256")
        or observation.get("title") != post_title
        or observation.get("title_tag_count") != 1
        or observation.get("meta_description") != fields.get("meta_description")
        or observation.get("meta_description_tag_count") != 1
        or observation.get("robots") != "index,follow"
        or observation.get("robots_meta") != "index,follow"
        or not isinstance(observation.get("robots_http"), str)
        or not _robots_indexability_safe(str(observation.get("robots_http")))
        or observation.get("robots_http_indexability_safe") is not True
        or observation.get("robots_tag_count") != 1
        or not isinstance(observation.get("crawler_robots_tag_count"), int)
        or isinstance(observation.get("crawler_robots_tag_count"), bool)
        or int(observation["crawler_robots_tag_count"]) < 0
        or observation.get("crawler_robots_indexability_safe") is not True
        or observation.get("sitemap_membership") is not True
        or observation.get("h1") != post_title
        or observation.get("h1_count") != 1
        or observation.get("package_marker_count") != 1
        or observation.get("package_marker_attribute_count") != 1
        or observation.get("post_content_envelope_count") != 1
        or observation.get("post_content_envelope_attribute_count") != 1
        or observation.get("blocked_post_content_envelope_count") != 0
        or observation.get("post_content_envelope_marker_child_count") != 1
        or observation.get("post_content_envelope_valid") is not True
        or observation.get("post_content_marker_subtree_count") != 1
        or not isinstance(semantic_post_content_sha256, str)
        or HEX64.fullmatch(semantic_post_content_sha256) is None
        or observation.get("post_content_semantic_sha256")
        != semantic_post_content_sha256
        or observation.get("disclosure_marker_count") != 1
        or observation.get("cta_state_count") != 3
        or observation.get("blocked_cta_count") != 3
        or observation.get("affiliate_url_count") != 0
        or observation.get("ambiguous_attribute_count") != 0
        or not isinstance(observation.get("image_count"), int)
        or isinstance(observation.get("image_count"), bool)
        or int(observation["image_count"]) < 0
        or not isinstance(observation.get("inline_executable_script_count"), int)
        or isinstance(observation.get("inline_executable_script_count"), bool)
        or int(observation["inline_executable_script_count"]) < 0
        or not isinstance(observation.get("external_script_count"), int)
        or isinstance(observation.get("external_script_count"), bool)
        or int(observation["external_script_count"]) < 0
        or observation.get("json_ld_script_count") != 1
        or observation.get("json_ld_invalid_count") != 0
        or not isinstance(observation.get("json_ld_sha256"), str)
        or HEX64.fullmatch(str(observation.get("json_ld_sha256"))) is None
        or observation.get("json_ld_types")
        != ["Article", "BreadcrumbList", "Organization", "WebSite"]
        or observation.get("json_ld_sha256") != structured_data_sha256
        or observation.get("json_ld_visible_content_match") is not True
        or not isinstance(observation.get("body_bytes"), int)
        or isinstance(observation.get("body_bytes"), bool)
        or int(observation["body_bytes"]) <= 0
        or observation.get("body_storage") != "DISCARDED_AFTER_HASH"
    ):
        fail("RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID")
    return {
        "schema": "RAOS_V2_PUBLIC_VERIFICATION_RECEIPT_V2",
        "version": "2.0.0",
        "derivation": ("STRICT_PREACTION_CAPTURE_SEALED_PACKAGE_POST_ACTION_EXPORT_V2"),
        "evidence_class": "PUBLIC_READ_ONLY_HTTP_AND_OWNER_EXPORT",
        "completion_scope": "HTTP_AND_OWNER_EXPORT_ONLY",
        "capture_sha256": _semantic_digest(capture),
        "preaction_capture_sha256": _semantic_digest(preaction_capture),
        "post_action_export_binding_sha256": post_action_export_binding_sha256,
        "target": {"origin": ORIGIN, "route": PHASE3_PUBLIC_PATH},
        "observed_at": observation["observed_at"],
        "evaluated_at": evaluated_at.isoformat(),
        "max_capture_age_seconds": PHASE3_PUBLIC_CAPTURE_MAX_AGE_SECONDS,
        "status": 200,
        "redirect_chain": [],
        "canonical": PHASE3_PUBLIC_URL,
        "head_tag_count": 1,
        "metadata_location_violation_count": 0,
        "title": post_title,
        "title_tag_count": 1,
        "meta_description": fields["meta_description"],
        "meta_description_tag_count": 1,
        "robots": "index,follow",
        "robots_meta": "index,follow",
        "robots_http": observation["robots_http"],
        "robots_http_indexability_safe": True,
        "content_type_media_type": "text/html",
        "refresh_http_present": False,
        "link_http_sha256": observation["link_http_sha256"],
        "robots_txt_status": robots_txt_evidence["status"],
        "robots_txt_sha256": robots_txt_evidence["sha256"],
        "robots_txt_target_allowed_for_googlebot": True,
        "indexability_evidence_scope": "HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT",
        "sitemap_membership": True,
        "h1": post_title,
        "h1_count": 1,
        "body_sha256": body_digest,
        "package_digest": package_digest,
        "structured_data_expectation_sha256": structured_data_sha256,
        "post_content_semantic_sha256": semantic_post_content_sha256,
        "package_marker": PHASE3_PACKAGE_MARKER,
        "package_marker_count": 1,
        "package_marker_attribute_count": 1,
        "post_content_envelope": PHASE3_CONTENT_ENVELOPE,
        "post_content_envelope_count": 1,
        "post_content_envelope_attribute_count": 1,
        "blocked_post_content_envelope_count": 0,
        "post_content_envelope_marker_child_count": 1,
        "post_content_envelope_valid": True,
        "post_content_marker_subtree_count": 1,
        "disclosure_marker_present": True,
        "disclosure_marker_count": 1,
        "cta_state_count": 3,
        "blocked_cta_count": 3,
        "affiliate_url_count": 0,
        "ambiguous_attribute_count": 0,
        "image_count": observation["image_count"],
        "inline_executable_script_count": observation["inline_executable_script_count"],
        "external_script_count": observation["external_script_count"],
        "resource_inventory_sha256": _semantic_digest(
            {"preaction": preaction_resources, "public": public_resources}
        ),
        "resource_change_status": "NO_UNAPPROVED_NEW_TRACKED_RESOURCE",
        "plugin_stylesheet_url": PHASE3_PLUGIN_CSS_URL,
        "plugin_stylesheet_resource_sha256": expected_plugin_css,
        "plugin_stylesheet_content_sha256": plugin_stylesheet_evidence["sha256"],
        "plugin_stylesheet_bytes": plugin_stylesheet_evidence["bytes"],
        "plugin_php_sha256": plugin_artifacts["plugin_php_sha256"],
        "plugin_manifest_sha256": plugin_artifacts["plugin_manifest_sha256"],
        "sealed_post_content_sha256": plugin_artifacts["sealed_post_content_sha256"],
        "plugin_artifact_status": "LOCAL_SOURCE_BOUND_AND_PUBLIC_CSS_MATCHED",
        "json_ld_script_count": 1,
        "json_ld_sha256": observation["json_ld_sha256"],
        "json_ld_types": ["Article", "BreadcrumbList", "Organization", "WebSite"],
        "json_ld_visible_content_match": True,
        "canonical_tag_count": 1,
        "robots_tag_count": 1,
        "crawler_robots_tag_count": observation["crawler_robots_tag_count"],
        "crawler_robots_indexability_safe": True,
        "critical_issue_count": 0,
        "public_browser_verification_status": "SEPARATE_RECEIPT_REQUIRED",
        "phase_exit_eligible": False,
        "rollback_invoked": False,
    }


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
    phase3_capture = subcommands.add_parser(
        "capture-phase3-public",
        help=(
            "capture only the Phase 3 migration URL; network remains off "
            "without --public-read-only"
        ),
    )
    phase3_capture.add_argument("--public-read-only", action="store_true")
    phase3_capture.add_argument(
        "--output",
        type=Path,
        required=True,
        help=(
            "new repository-relative JSON path directly under "
            "changes/raos-v2/recorded-inputs/phase3/"
        ),
    )
    subcommands.add_parser(
        "record-local-test",
        help="bind an ignored pytest tee to the current local source/test inventory",
    )
    phase3_browser = subcommands.add_parser(
        "record-phase3-local-browser",
        help="bind raw local browser evidence after reviewing all three PNGs",
    )
    phase3_browser.add_argument(
        "--visual-review-confirmed",
        action="store_true",
        help="assert that 390/768/1440 PNGs were manually reviewed",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate-package":
            result = validate_package(arguments.zip)
        elif arguments.command == "capture-phase0":
            if RECORDED_INPUT.exists():
                fail("RAOS_V2_PHASE0_BASELINE_ALREADY_CAPTURED")
            result = capture_phase0(public_read_only=arguments.public_read_only)
        elif arguments.command == "capture-phase3-public":
            result = capture_phase3_public(
                public_read_only=arguments.public_read_only,
                output=arguments.output,
            )
        elif arguments.command == "record-local-test":
            result = record_local_test_evidence()
            _atomic_write(LOCAL_TEST_EVIDENCE_INPUT, canonical_json_bytes(result))
        elif arguments.command == "record-phase3-local-browser":
            result = record_phase3_local_browser_evidence(
                visual_review_confirmed=arguments.visual_review_confirmed
            )
            _atomic_write(
                PHASE3_LOCAL_BROWSER_EVIDENCE_INPUT,
                canonical_json_bytes(result),
            )
        else:
            result = validate_generated()
    except ValidationFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
