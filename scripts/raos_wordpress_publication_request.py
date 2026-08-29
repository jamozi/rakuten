#!/usr/bin/env python3
"""Request and finish one locally verified WordPress publication batch.

Python is used so the workflow can reuse the repository's owner-private
Application Password format. Editor calls use the fixed project MCP endpoint;
deployment calls use the fixed, pinned stdio MCP bridge.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
from typing import Any, Final, NoReturn
import urllib.error
import urllib.request


ROOT: Final = Path(__file__).resolve().parents[1]
PREVIEW_ROOT: Final = ROOT / "changes/wordpress-local-preview-v1"
FIXTURE_PATH: Final = PREVIEW_ROOT / "fixtures/posts.json"
MAPPING_PATH: Final = PREVIEW_ROOT / "production-mapping.v1.json"
THEME_STYLE_PATH: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/style.css"
)
THEME_ROOT: Final = THEME_STYLE_PATH.parent
ORIGIN: Final = "https://kurashinoshirube.com"
EDITOR_ENDPOINT: Final = f"{ORIGIN}/wp-json/raos-codex-mcp/v1/editor"
REVIEW_URL: Final = f"{ORIGIN}/wp-admin/tools.php?page=raos-codex-proposals"
EDITOR_CREDENTIAL_PATH: Final = (
    ROOT / ".secrets/wordpress-mcp/editor-application-password.v1.json"
)
PRIVATE_REQUEST_DIRECTORY: Final = ROOT / ".secrets/wordpress-mcp/publication-requests"
NODE_BIN: Final = Path("/home/minami/.nvm/versions/node/v24.18.1/bin/node")
DEPLOYMENT_BRIDGE: Final = ROOT / "packages/wordpress-mcp-bridge/src/index.ts"
MAKE_BIN: Final = Path("/usr/bin/make")
SG_BIN: Final = Path("/usr/bin/sg")
DOCKER_SOCKET: Final = Path("/var/run/docker.sock")
PROTOCOL_VERSION: Final = "2025-11-25"
EXPECTED_PLUGIN_VERSION: Final = "1.2.0"
MAX_CONTENT_BYTES: Final = 1024 * 1024
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024
MAX_RECEIPT_BYTES: Final = 4 * 1024 * 1024
MAX_THEME_PACKAGE_BYTES: Final = 32 * 1024 * 1024
MAX_THEME_FILE_BYTES: Final = 8 * 1024 * 1024
MAX_THEME_FILE_COUNT: Final = 2048
LIST_PER_PAGE: Final = 10
MAX_LIST_DOCUMENTS: Final = 10_000
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE: Final = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")
EXPECTED_TOOLS: Final = {
    "raos-codex-site-status",
    "raos-codex-content-list",
    "raos-codex-content-get",
    "raos-codex-content-create-draft",
    "raos-codex-content-update-draft",
    "raos-codex-content-propose-release",
    "raos-codex-publication-batch-register",
    "raos-codex-operation-get",
}
EXPECTED_DEPLOYMENT_TOOLS: Final = {
    "deployment-status",
    "release-wait-and-apply",
    "content-apply-release",
    "theme-propose-release",
    "theme-apply-release",
    "plugin-propose-change",
    "plugin-apply-change",
    "operation-recover",
}
WRITE_FIELDS: Final = (
    "post_type",
    "title",
    "slug",
    "excerpt",
    "block_markup",
    "taxonomies",
    "media_ids",
)


class PublicationFailure(RuntimeError):
    """Fail-closed error whose message is a stable, non-sensitive code."""


class _RefuseRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn every HTTP redirect into an HTTPError before a second request."""

    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def fail(code: str) -> NoReturn:
    raise PublicationFailure(code) from None


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail("RAOS_WORDPRESS_REQUEST_JSON_INVALID")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def exact_object(
    value: object, required: set[str], optional: set[str] | None = None
) -> dict[str, object]:
    if type(value) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    record = value
    allowed = required | (optional or set())
    if set(record) - allowed or not required.issubset(record):
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    if any(type(key) is not str for key in record):
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    return record


def load_json(path: Path, maximum: int, code: str) -> dict[str, object]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail(code)
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != len(payload)
        or not 1 <= len(payload) <= maximum
    ):
        fail(code)
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail(code)
    if type(value) is not dict:
        fail(code)
    return value


@dataclass(frozen=True)
class Article:
    local_slug: str
    production_slug: str
    title: str
    excerpt: str
    block_markup: str
    taxonomies: dict[str, list[int]]

    def document(self) -> dict[str, object]:
        return {
            "post_type": "post",
            "title": self.title,
            "slug": self.production_slug,
            "excerpt": self.excerpt,
            "block_markup": self.block_markup,
            "taxonomies": self.taxonomies,
            "media_ids": [],
        }

    def desired_sha256(self) -> str:
        return sha256_json(self.document())


def _valid_taxonomies(value: object) -> dict[str, list[int]]:
    expected = {"category", "post_format", "post_tag"}
    if type(value) is not dict or set(value) != expected:
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
    result: dict[str, list[int]] = {}
    for taxonomy in sorted(expected):
        term_ids = value[taxonomy]
        if (
            type(term_ids) is not list
            or len(term_ids) > 128
            or any(type(term_id) is not int or term_id < 1 for term_id in term_ids)
            or len(set(term_ids)) != len(term_ids)
            or term_ids != sorted(term_ids)
            or (taxonomy == "category" and not term_ids)
            or (taxonomy != "category" and term_ids)
        ):
            fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
        result[taxonomy] = list(term_ids)
    return result


def load_articles(selection: str) -> list[Article]:
    fixture = exact_object(
        load_json(FIXTURE_PATH, 256 * 1024, "RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID"),
        {"schema", "seed_version", "posts"},
    )
    mapping = exact_object(
        load_json(MAPPING_PATH, 256 * 1024, "RAOS_WORDPRESS_REQUEST_MAPPING_INVALID"),
        {"schema", "origin", "editor_endpoint", "review_url", "articles"},
    )
    if (
        fixture["schema"] != "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
        or mapping["schema"] != "RAOS_WORDPRESS_PRODUCTION_MAPPING_V1"
        or mapping["origin"] != ORIGIN
        or mapping["editor_endpoint"] != EDITOR_ENDPOINT
        or mapping["review_url"] != REVIEW_URL
        or type(fixture["posts"]) is not list
        or type(mapping["articles"]) is not list
        or not fixture["posts"]
        or len(fixture["posts"]) != len(mapping["articles"])
    ):
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")

    fixture_by_slug: dict[str, dict[str, object]] = {}
    for raw_post in fixture["posts"]:
        post = exact_object(
            raw_post,
            {
                "article_id",
                "category",
                "content_file",
                "date",
                "excerpt",
                "slug",
                "title",
            },
        )
        local_slug = post["slug"]
        if (
            type(local_slug) is not str
            or not local_slug.startswith("local-preview-")
            or SLUG_RE.fullmatch(local_slug) is None
            or post["article_id"] != local_slug
            or local_slug in fixture_by_slug
        ):
            fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
        fixture_by_slug[local_slug] = post

    mapping_by_production: dict[str, dict[str, object]] = {}
    mapped_local: set[str] = set()
    for raw_mapping in mapping["articles"]:
        row = exact_object(
            raw_mapping,
            {"local_slug", "production_slug", "local_category", "taxonomies"},
        )
        local_slug = row["local_slug"]
        production_slug = row["production_slug"]
        if (
            type(local_slug) is not str
            or type(production_slug) is not str
            or local_slug not in fixture_by_slug
            or local_slug in mapped_local
            or SLUG_RE.fullmatch(production_slug) is None
            or production_slug != local_slug.removeprefix("local-preview-")
            or production_slug in mapping_by_production
            or row["local_category"] != fixture_by_slug[local_slug]["category"]
        ):
            fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
        _valid_taxonomies(row["taxonomies"])
        mapped_local.add(local_slug)
        mapping_by_production[production_slug] = row
    if mapped_local != set(fixture_by_slug):
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")

    available = set(mapping_by_production)
    if selection == "all":
        selected = available
    else:
        parts = selection.split(",")
        if (
            not parts
            or any(not part or part.strip() != part for part in parts)
            or len(set(parts)) != len(parts)
            or any(SLUG_RE.fullmatch(part) is None for part in parts)
            or not set(parts).issubset(available)
        ):
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID")
        selected = set(parts)

    result: list[Article] = []
    for production_slug, row in mapping_by_production.items():
        if production_slug not in selected:
            continue
        local_slug = str(row["local_slug"])
        post = fixture_by_slug[local_slug]
        title = post["title"]
        excerpt = post["excerpt"]
        content_file = post["content_file"]
        if (
            type(title) is not str
            or not title.strip()
            or len(title) > 500
            or len(title.encode("utf-8")) > 2000
            or "<" in title
            or ">" in title
            or type(excerpt) is not str
            or len(excerpt.encode("utf-8")) > 10_000
            or type(content_file) is not str
            or content_file != f"articles/{production_slug}.html"
            or re.fullmatch(r"articles/[a-z0-9-]+\.html", content_file) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
        content_path = PREVIEW_ROOT / "fixtures" / content_file
        try:
            metadata = content_path.lstat()
            payload = content_path.read_bytes()
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_UNAVAILABLE")
        expected_parent = (PREVIEW_ROOT / "fixtures/articles").resolve()
        if (
            content_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or content_path.parent.resolve() != expected_parent
            or metadata.st_size != len(payload)
            or not 1 <= len(payload) <= MAX_CONTENT_BYTES
        ):
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        try:
            markup = payload.decode("utf-8", errors="strict")
        except UnicodeError:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        if "\x00" in markup:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        result.append(
            Article(
                local_slug=local_slug,
                production_slug=production_slug,
                title=title,
                excerpt=excerpt,
                block_markup=markup,
                taxonomies=_valid_taxonomies(row["taxonomies"]),
            )
        )
    if not result:
        fail("RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID")
    return result


def theme_version() -> str:
    try:
        payload = THEME_STYLE_PATH.read_bytes()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if not 1 <= len(payload) <= 1024 * 1024:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    match = re.search(rb"(?im)^\s*(?:\*\s*)?Version:\s*([^\r\n]+)", payload[:8192])
    if match is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    try:
        value = match.group(1).decode("utf-8", errors="strict").strip()
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if VERSION_RE.fullmatch(value) is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    return value


def _git(*arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            (
                "/usr/bin/git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                ROOT.as_posix(),
                *arguments,
            ),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except OSError, subprocess.SubprocessError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_GIT_FAILED")
    if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
        fail("RAOS_WORDPRESS_REQUEST_THEME_GIT_FAILED")
    return completed.stdout


def tracked_theme_tree_sha256() -> str:
    """Hash the exact clean tracked tree using the deployment manifest contract."""
    relative_root = THEME_ROOT.relative_to(ROOT).as_posix()
    if _git("status", "--porcelain=v1", "--", relative_root):
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_DIRTY")
    raw_files = _git("ls-files", "-z", "--", relative_root)
    try:
        tracked = [
            value.decode("utf-8", errors="strict")
            for value in raw_files.split(b"\0")
            if value
        ]
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if not tracked or len(tracked) > MAX_THEME_FILE_COUNT:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    manifest: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    for repository_relative in sorted(tracked):
        source = ROOT / repository_relative
        try:
            metadata = source.lstat()
            payload = source.read_bytes()
            relative = source.relative_to(THEME_ROOT).as_posix()
        except OSError, ValueError:
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        folded = relative.casefold()
        if (
            source.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != len(payload)
            or not 0 <= len(payload) <= MAX_THEME_FILE_BYTES
            or re.fullmatch(r"[A-Za-z0-9._/-]+", relative) is None
            or len(relative) > 300
            or folded in seen
        ):
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        seen.add(folded)
        total += len(payload)
        if total > MAX_THEME_PACKAGE_BYTES:
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        manifest.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest.sort(key=lambda entry: str(entry["path"]))
    return sha256_json(manifest)


def run_preview_checks(
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> None:
    use_stale_group_bridge = _docker_group_membership_is_stale()
    for target, code in (
        ("wordpress-preview-up", "RAOS_WORDPRESS_REQUEST_PREVIEW_UP_FAILED"),
        ("wordpress-preview-sync", "RAOS_WORDPRESS_REQUEST_PREVIEW_SYNC_FAILED"),
        ("wordpress-preview-check", "RAOS_WORDPRESS_REQUEST_PREVIEW_CHECK_FAILED"),
    ):
        command = (
            (SG_BIN.as_posix(), "docker", "-c", f"{MAKE_BIN.as_posix()} {target}")
            if use_stale_group_bridge
            else (MAKE_BIN.as_posix(), target)
        )
        try:
            completed = runner(
                command,
                cwd=ROOT,
                stdin=None,
                stdout=None,
                stderr=None,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            fail(code)
        if completed.returncode != 0:
            fail(code)


def _docker_group_membership_is_stale() -> bool:
    try:
        metadata = DOCKER_SOCKET.stat()
        group = grp.getgrgid(metadata.st_gid)
        username = pwd.getpwuid(os.geteuid()).pw_name
    except OSError, KeyError:
        return False
    return (
        stat.S_ISSOCK(metadata.st_mode)
        and group.gr_name == "docker"
        and username in group.gr_mem
        and metadata.st_gid not in os.getgroups()
    )


def _secure_credential() -> tuple[str, str]:
    try:
        metadata = EDITOR_CREDENTIAL_PATH.lstat()
        payload = EDITOR_CREDENTIAL_PATH.read_bytes()
        parent_metadata = EDITOR_CREDENTIAL_PATH.parent.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_UNAVAILABLE")
    if (
        EDITOR_CREDENTIAL_PATH.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 1 <= len(payload) <= 16 * 1024
        or EDITOR_CREDENTIAL_PATH.parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INSECURE")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INVALID")
    record = exact_object(
        value,
        {"schema", "origin", "username", "application_password", "purpose"},
    )
    if (
        record["schema"] != "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1"
        or record["origin"] != ORIGIN
        or record["purpose"] != "editor_mcp"
        or type(record["username"]) is not str
        or not record["username"]
        or type(record["application_password"]) is not str
        or not 20 <= len(record["application_password"]) <= 512
    ):
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INVALID")
    return record["username"], record["application_password"]


class EditorMcpClient:
    """Small fixed-endpoint Streamable HTTP MCP client."""

    def __init__(self) -> None:
        self.endpoint = EDITOR_ENDPOINT
        self.username, self.application_credential = _secure_credential()
        self.session_id: str | None = None
        self.next_id = 1

    def _request(
        self, value: object, *, notification: bool = False
    ) -> tuple[int, bytes, Mapping[str, str]]:
        data = canonical_json_bytes(value)
        authorization = base64.b64encode(
            f"{self.username}:{self.application_credential}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/json",
            "User-Agent": "raos-wordpress-publication-request/1.0.0",
        }
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
            headers["Mcp-Protocol-Version"] = PROTOCOL_VERSION
        request = urllib.request.Request(
            self.endpoint, data=data, headers=headers, method="POST"
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RefuseRedirectHandler(),
        )
        try:
            with opener.open(request, timeout=45) as response:
                if response.geturl() != EDITOR_ENDPOINT:
                    fail("RAOS_WORDPRESS_REQUEST_REDIRECT_REFUSED")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    fail("RAOS_WORDPRESS_REQUEST_RESPONSE_TOO_LARGE")
                return response.status, body, response.headers
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                fail("RAOS_WORDPRESS_REQUEST_REDIRECT_REFUSED")
            code = f"RAOS_WORDPRESS_REQUEST_HTTP_{error.code}"
            try:
                error_body = error.read(64 * 1024)
                parsed = json.loads(error_body.decode("utf-8", errors="strict"))
                candidate = parsed.get("code") if type(parsed) is dict else None
                if type(candidate) is str and re.fullmatch(
                    r"[a-z0-9_]{3,96}", candidate
                ):
                    code = candidate.upper()
            except OSError, UnicodeError, json.JSONDecodeError:
                pass
            fail(code)
        except urllib.error.URLError, TimeoutError, OSError:
            fail("RAOS_WORDPRESS_REQUEST_TRANSPORT_FAILED")
        if notification:
            fail("RAOS_WORDPRESS_REQUEST_NOTIFICATION_FAILED")

    def message(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self.next_id
        self.next_id += 1
        _, body, headers = self._request(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except UnicodeError, json.JSONDecodeError:
            fail("RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_INVALID")
        if (
            type(payload) is not dict
            or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != request_id
            or "error" in payload
            or type(payload.get("result")) is not dict
        ):
            fail("RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_INVALID")
        if method == "initialize":
            session = headers.get("Mcp-Session-Id")
            if type(session) is not str or not session:
                fail("RAOS_WORDPRESS_REQUEST_MCP_SESSION_INVALID")
            self.session_id = session
        return payload["result"]

    def initialize(self) -> dict[str, object]:
        result = self.message(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "raos-wordpress-publication-request",
                    "version": "1.0.0",
                },
            },
        )
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            fail("RAOS_WORDPRESS_REQUEST_MCP_PROTOCOL_INVALID")
        status, body, _ = self._request(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            notification=True,
        )
        if status != 202 or body not in {b"", b"null"}:
            fail("RAOS_WORDPRESS_REQUEST_MCP_NOTIFICATION_INVALID")
        return result

    def tools(self) -> dict[str, dict[str, object]]:
        value = self.message("tools/list", {}).get("tools")
        if type(value) is not list:
            fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
        result: dict[str, dict[str, object]] = {}
        for raw_tool in value:
            if type(raw_tool) is not dict or type(raw_tool.get("name")) is not str:
                fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
            result[raw_tool["name"]] = raw_tool
        return result

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = self.message("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if result.get("isError") is True or type(structured) is not dict:
            code = structured.get("code") if type(structured) is dict else None
            if type(code) is str and re.fullmatch(r"[a-z0-9_]{3,96}", code):
                fail(code.upper())
            fail("RAOS_WORDPRESS_REQUEST_TOOL_CALL_FAILED")
        return structured


def validate_tool_contract(tools: Mapping[str, Mapping[str, object]]) -> None:
    if set(tools) != EXPECTED_TOOLS:
        fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
    proposal = tools["raos-codex-content-propose-release"]
    schema = proposal.get("inputSchema")
    if type(schema) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED")
    properties = schema.get("properties")
    required = schema.get("required")
    key = properties.get("idempotency_key") if type(properties) is dict else None
    if (
        schema.get("additionalProperties") is not False
        or type(key) is not dict
        or key.get("type") != "string"
        or key.get("pattern") != "^[0-9a-f]{64}$"
        or type(required) is not list
        or "idempotency_key" in required
    ):
        fail("RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED")
    batch = tools["raos-codex-publication-batch-register"].get("inputSchema")
    batch_properties = batch.get("properties") if type(batch) is dict else None
    proposal_ids = (
        batch_properties.get("proposal_ids") if type(batch_properties) is dict else None
    )
    items = proposal_ids.get("items") if type(proposal_ids) is dict else None
    if (
        type(batch) is not dict
        or batch.get("additionalProperties") is not False
        or batch.get("required") != ["proposal_ids"]
        or type(proposal_ids) is not dict
        or proposal_ids.get("type") != "array"
        or proposal_ids.get("minItems") != 1
        or proposal_ids.get("maxItems") != 20
        or proposal_ids.get("uniqueItems") is not True
        or type(items) is not dict
        or items.get("type") != "string"
        or items.get("pattern") != "^[0-9a-f]{64}$"
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_BOOTSTRAP_REQUIRED")


def validate_site_status(status: Mapping[str, object]) -> None:
    writes = status.get("writes_enabled")
    theme = status.get("theme")
    server = status.get("server")
    authorization = status.get("apply_authorization")
    if (
        status.get("schema") != "RAOSWordPressSiteStatusV1"
        or status.get("origin") != ORIGIN
        or status.get("wordpress_version_compatible") is not True
        or status.get("mcp_adapter_version") != "0.6.1"
        or status.get("mcp_adapter_version_compatible") is not True
        or status.get("plugin_version") != EXPECTED_PLUGIN_VERSION
        or type(writes) is not dict
        or any(
            writes.get(name) is not True
            for name in ("global", "draft", "content_apply", "theme_apply")
        )
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("exists") is not True
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
        or authorization
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "ttl_seconds": 900,
        }
        or type(server) is not dict
        or server.get("endpoint") != EDITOR_ENDPOINT
        or server.get("publish_tool_exposed") is not False
        or server.get("delete_tool_exposed") is not False
        or server.get("media_write_tool_exposed") is not False
        or server.get("proposal_ttl_seconds") != 900
    ):
        fail("RAOS_WORDPRESS_REQUEST_SITE_NOT_READY")


def precondition(document: Mapping[str, object]) -> dict[str, object]:
    revision = document.get("revision_id")
    modified = document.get("modified_gmt")
    content_hash = document.get("content_sha256")
    if (
        type(revision) is not int
        or revision < 1
        or type(modified) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", modified) is None
        or type(content_hash) is not str
        or SHA256_RE.fullmatch(content_hash) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_DOCUMENT_INVALID")
    return {
        "revision_id": revision,
        "modified_gmt": modified,
        "content_sha256": content_hash,
    }


def document_projection(document: Mapping[str, object]) -> dict[str, object]:
    if any(field not in document for field in WRITE_FIELDS):
        fail("RAOS_WORDPRESS_REQUEST_DOCUMENT_INVALID")
    return {field: document[field] for field in WRITE_FIELDS}


def list_all_documents(client: Any) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    expected_total: int | None = None
    page = 1
    while True:
        response = client.call(
            "raos-codex-content-list",
            {
                "post_type": "post",
                "status": "any",
                "page": page,
                "per_page": LIST_PER_PAGE,
            },
        )
        total = response.get("total")
        batch = response.get("documents")
        if (
            response.get("schema") != "ContentDocumentListV1"
            or response.get("page") != page
            or response.get("per_page") != LIST_PER_PAGE
            or type(total) is not int
            or total < 0
            or total > MAX_LIST_DOCUMENTS
            or type(batch) is not list
            or len(batch) > LIST_PER_PAGE
            or (expected_total is not None and total != expected_total)
        ):
            fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
        expected_total = total
        for raw_document in batch:
            if type(raw_document) is not dict:
                fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
            document = raw_document
            post_id = document.get("id")
            if type(post_id) is not int or post_id < 1 or post_id in seen_ids:
                fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
            precondition(document)
            seen_ids.add(post_id)
            documents.append(document)
        if len(documents) >= total:
            break
        if not batch:
            fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
        page += 1
    if len(documents) != expected_total:
        fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
    return documents


def _ensure_private_directory() -> None:
    parent = PRIVATE_REQUEST_DIRECTORY.parent
    try:
        parent_metadata = parent.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_UNAVAILABLE")
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_INSECURE")
    try:
        PRIVATE_REQUEST_DIRECTORY.mkdir(mode=0o700, exist_ok=True)
        metadata = PRIVATE_REQUEST_DIRECTORY.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_UNAVAILABLE")
    if (
        PRIVATE_REQUEST_DIRECTORY.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_INSECURE")


@contextmanager
def request_lock() -> Any:
    _ensure_private_directory()
    path = PRIVATE_REQUEST_DIRECTORY / "publication-request.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd_metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
    except BlockingIOError:
        fail("RAOS_WORDPRESS_REQUEST_ALREADY_RUNNING")
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_LOCK_FAILED")
    if (
        not stat.S_ISREG(fd_metadata.st_mode)
        or fd_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(fd_metadata.st_mode) != 0o600
        or fd_metadata.st_nlink != 1
        or (fd_metadata.st_dev, fd_metadata.st_ino)
        != (path_metadata.st_dev, path_metadata.st_ino)
    ):
        os.close(descriptor)
        fail("RAOS_WORDPRESS_REQUEST_LOCK_INSECURE")
    try:
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _receipt_path(articles: Sequence[Article]) -> Path:
    identity = sha256_json(
        {
            "schema": "RAOS_WORDPRESS_PUBLICATION_SELECTION_V1",
            "slugs": sorted(article.production_slug for article in articles),
        }
    )
    return PRIVATE_REQUEST_DIRECTORY / f"request-{identity}.json"


def _read_receipt(path: Path) -> dict[str, object] | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        metadata = path.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INSECURE")
    return load_json(path, MAX_RECEIPT_BYTES, "RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def _atomic_receipt(path: Path, value: Mapping[str, object]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    if len(payload) > MAX_RECEIPT_BYTES:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_TOO_LARGE")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_fd = os.open(PRIVATE_REQUEST_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")


def _fresh_receipt(
    articles: Sequence[Article],
    path: Path,
    desired_theme_tree_sha256: str | None = None,
) -> dict[str, object]:
    theme_tree = (
        tracked_theme_tree_sha256()
        if desired_theme_tree_sha256 is None
        else desired_theme_tree_sha256
    )
    if SHA256_RE.fullmatch(theme_tree) is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    return {
        "schema": "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1",
        "receipt_path_sha256": hashlib.sha256(path.name.encode("ascii")).hexdigest(),
        "selected_slugs": sorted(article.production_slug for article in articles),
        "desired_sha256": {
            article.production_slug: article.desired_sha256() for article in articles
        },
        "desired_theme_tree_sha256": theme_tree,
        "state": "LOCAL_VERIFIED",
        "attempt_id": None,
        "attempt_created_at_gmt": None,
        "drafts": {},
        "proposal_keys": {},
        "proposals": [],
        "batch_registration": None,
        "review_url": REVIEW_URL,
        "apply_receipt": None,
        "updated_at_gmt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _validate_receipt(
    receipt: dict[str, object], articles: Sequence[Article]
) -> dict[str, object]:
    required = {
        "schema",
        "receipt_path_sha256",
        "selected_slugs",
        "desired_sha256",
        "desired_theme_tree_sha256",
        "state",
        "attempt_id",
        "attempt_created_at_gmt",
        "drafts",
        "proposal_keys",
        "proposals",
        "batch_registration",
        "review_url",
        "apply_receipt",
        "updated_at_gmt",
    }
    exact_object(receipt, required)
    selected = sorted(article.production_slug for article in articles)
    if (
        receipt["schema"] != "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1"
        or receipt["selected_slugs"] != selected
        or type(receipt["desired_sha256"]) is not dict
        or type(receipt["desired_theme_tree_sha256"]) is not str
        or SHA256_RE.fullmatch(receipt["desired_theme_tree_sha256"]) is None
        or type(receipt["drafts"]) is not dict
        or type(receipt["proposal_keys"]) is not dict
        or type(receipt["proposals"]) is not list
        or receipt["review_url"] != REVIEW_URL
        or type(receipt["state"]) is not str
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return receipt


def _touch_receipt(path: Path, receipt: dict[str, object], state: str) -> None:
    receipt["state"] = state
    receipt["updated_at_gmt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _atomic_receipt(path, receipt)


def _known_draft(
    receipt: Mapping[str, object], slug: str, document: Mapping[str, object]
) -> bool:
    drafts = receipt.get("drafts")
    known = drafts.get(slug) if type(drafts) is dict else None
    return (
        type(known) is dict
        and known.get("id") == document.get("id")
        and known.get("content_sha256") == document.get("content_sha256")
    )


def reconcile_drafts(
    client: Any,
    articles: Sequence[Article],
    documents: Sequence[Mapping[str, object]],
    receipt: dict[str, object],
    path: Path,
) -> dict[str, dict[str, object]]:
    by_slug: dict[str, list[Mapping[str, object]]] = {}
    selected = {article.production_slug for article in articles}
    for document in documents:
        slug = document.get("slug")
        if type(slug) is str and slug in selected:
            by_slug.setdefault(slug, []).append(document)
    result: dict[str, dict[str, object]] = {}
    receipt_drafts = receipt["drafts"]
    if type(receipt_drafts) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    for article in articles:
        candidates = by_slug.get(article.production_slug, [])
        if len(candidates) > 1:
            fail("RAOS_WORDPRESS_REQUEST_SLUG_CONFLICT")
        desired = article.document()
        if not candidates:
            document = client.call("raos-codex-content-create-draft", desired)
        else:
            current = candidates[0]
            if current.get("status") == "publish":
                fail("RAOS_WORDPRESS_REQUEST_PUBLISHED_CONFLICT")
            if current.get("status") != "draft":
                fail("RAOS_WORDPRESS_REQUEST_DRAFT_TARGET_INVALID")
            if document_projection(current) == desired:
                document = dict(current)
            elif _known_draft(receipt, article.production_slug, current):
                document = client.call(
                    "raos-codex-content-update-draft",
                    {
                        "id": current["id"],
                        "mode": "replace",
                        "precondition": precondition(current),
                        "changes": desired,
                    },
                )
            else:
                fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_DRAFT_DRIFT")
        if (
            document.get("status") != "draft"
            or document_projection(document) != desired
            or type(document.get("id")) is not int
        ):
            fail("RAOS_WORDPRESS_REQUEST_DRAFT_WRITE_INVALID")
        readback = client.call("raos-codex-content-get", {"id": document["id"]})
        if (
            readback.get("status") != "draft"
            or document_projection(readback) != desired
            or readback.get("content_sha256") != document.get("content_sha256")
        ):
            fail("RAOS_WORDPRESS_REQUEST_DRAFT_READBACK_FAILED")
        precondition(readback)
        result[article.production_slug] = readback
        receipt_drafts[article.production_slug] = {
            "id": readback["id"],
            "content_sha256": readback["content_sha256"],
        }
        _touch_receipt(path, receipt, "DRAFTS_IN_PROGRESS")
    _touch_receipt(path, receipt, "DRAFTS_READY")
    return result


def _validate_deployment_tools(tools: object) -> None:
    if type(tools) is not list:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    by_name: dict[str, dict[str, object]] = {}
    for tool in tools:
        if type(tool) is not dict or type(tool.get("name")) is not str:
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
        by_name[tool["name"]] = tool
    if set(by_name) != EXPECTED_DEPLOYMENT_TOOLS:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    for name, tool in by_name.items():
        annotations = tool.get("annotations")
        read_only = name == "deployment-status"
        destructive = name in {
            "release-wait-and-apply",
            "content-apply-release",
            "theme-apply-release",
            "plugin-apply-change",
            "operation-recover",
        }
        idempotent = name not in {"theme-propose-release", "plugin-propose-change"}
        open_world = name == "plugin-propose-change"
        if (
            type(annotations) is not dict
            or annotations.get("readOnlyHint") is not read_only
            or annotations.get("destructiveHint") is not destructive
            or annotations.get("idempotentHint") is not idempotent
            or annotations.get("openWorldHint") is not open_world
        ):
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    status_schema = by_name["deployment-status"].get("inputSchema")
    theme_schema = by_name["theme-propose-release"].get("inputSchema")
    wait_schema = by_name["release-wait-and-apply"].get("inputSchema")
    theme_properties = (
        theme_schema.get("properties") if type(theme_schema) is dict else None
    )
    theme_key = (
        theme_properties.get("idempotency_key")
        if type(theme_properties) is dict
        else None
    )
    wait_properties = (
        wait_schema.get("properties") if type(wait_schema) is dict else None
    )
    wait_ids = (
        wait_properties.get("proposal_ids") if type(wait_properties) is dict else None
    )
    wait_batch_token = (
        wait_properties.get("batch_token") if type(wait_properties) is dict else None
    )
    wait_batch_manifest = (
        wait_properties.get("batch_manifest_sha256")
        if type(wait_properties) is dict
        else None
    )
    wait_items = wait_ids.get("items") if type(wait_ids) is dict else None
    if (
        type(status_schema) is not dict
        or status_schema.get("type") != "object"
        or status_schema.get("properties") != {}
        or type(theme_schema) is not dict
        or theme_schema.get("type") != "object"
        or type(theme_key) is not dict
        or theme_key.get("type") != "string"
        or theme_key.get("pattern") != "^[0-9a-f]{64}$"
        or type(wait_ids) is not dict
        or wait_schema.get("type") != "object"
        or set(wait_schema.get("required", []))
        != {"batch_token", "batch_manifest_sha256", "proposal_ids"}
        or type(wait_batch_token) is not dict
        or wait_batch_token.get("type") != "string"
        or wait_batch_token.get("pattern") != "^[0-9a-f]{64}$"
        or type(wait_batch_manifest) is not dict
        or wait_batch_manifest.get("type") != "string"
        or wait_batch_manifest.get("pattern") != "^[0-9a-f]{64}$"
        or wait_ids.get("type") != "array"
        or wait_ids.get("minItems") != 1
        or wait_ids.get("maxItems") != 20
        or type(wait_items) is not dict
        or wait_items.get("type") != "string"
        or wait_items.get("pattern") != "^[0-9a-f]{64}$"
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")


def _deployment_mcp_call(
    command: str,
    value: Mapping[str, object],
    *,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    if command not in {
        "deployment-status",
        "theme-propose-release",
        "release-wait-and-apply",
    }:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_COMMAND_INVALID")
    messages = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "raos-wordpress-publication-request",
                    "version": "1.0.0",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": command, "arguments": dict(value)},
        },
    )
    stdin = b"".join(canonical_json_bytes(message) + b"\n" for message in messages)
    try:
        completed = runner(
            (
                NODE_BIN.as_posix(),
                "--experimental-strip-types",
                DEPLOYMENT_BRIDGE.as_posix(),
            ),
            cwd=ROOT,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
        )
    except subprocess.TimeoutExpired:
        fail("RAOS_WORDPRESS_REQUEST_APPROVAL_TIMEOUT")
    except OSError, subprocess.SubprocessError:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_UNAVAILABLE")
    if len(completed.stdout) > MAX_RECEIPT_BYTES or len(completed.stderr) > 4096:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if completed.returncode != 0:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_FAILED")
    responses: dict[int, dict[str, object]] = {}
    try:
        for line in completed.stdout.splitlines():
            if not line:
                continue
            response = json.loads(line.decode("utf-8", errors="strict"))
            if (
                type(response) is not dict
                or response.get("jsonrpc") != "2.0"
                or type(response.get("id")) is not int
                or response["id"] in responses
            ):
                fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
            responses[response["id"]] = response
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if set(responses) != {1, 2, 3} or any(
        "error" in responses[response_id] for response_id in responses
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    initialized = responses[1].get("result")
    initialized_server = (
        initialized.get("serverInfo") if type(initialized) is dict else None
    )
    listed = responses[2].get("result")
    if (
        type(initialized) is not dict
        or initialized.get("protocolVersion") != PROTOCOL_VERSION
        or type(initialized_server) is not dict
        or initialized_server.get("name") != "raos-wordpress-bridge"
        or initialized_server.get("version") != "1.1.0"
        or type(listed) is not dict
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    _validate_deployment_tools(listed.get("tools"))
    call_result = responses[3].get("result")
    structured = (
        call_result.get("structuredContent") if type(call_result) is dict else None
    )
    if type(call_result) is not dict or type(structured) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if call_result.get("isError") is True:
        code = structured.get("code")
        if type(code) is str and re.fullmatch(r"[A-Z0-9_]{3,96}", code):
            fail(code)
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_TOOL_FAILED")
    return structured


def _proposal_record(
    *,
    kind: str,
    slug: str | None,
    key: str,
    response: Mapping[str, object],
    expected_after: str | None = None,
) -> dict[str, object]:
    payload: object = response
    if kind == "THEME_RELEASE":
        payload = response.get("proposal")
    if type(payload) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_INVALID")
    proposal_id = payload.get("proposal_id")
    after_sha256 = payload.get(
        "after_sha256" if kind == "CONTENT_RELEASE" else "after_tree_sha256"
    )
    expires = payload.get("expires_at_gmt")
    if (
        type(proposal_id) is not str
        or SHA256_RE.fullmatch(proposal_id) is None
        or type(after_sha256) is not str
        or SHA256_RE.fullmatch(after_sha256) is None
        or (expected_after is not None and after_sha256 != expected_after)
        or type(expires) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_INVALID")
    return {
        "kind": kind,
        "slug": slug,
        "proposal_id": proposal_id,
        "after_sha256": after_sha256,
        "expires_at_gmt": expires,
        "idempotency_key": key,
    }


def deployment_status(
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    response = _deployment_mcp_call("deployment-status", {}, timeout=120, runner=runner)
    theme = response.get("theme")
    gates = response.get("gates")
    authorization = response.get("apply_authorization")
    if (
        response.get("schema") != "RAOSWordPressDeploymentStatusV1"
        or response.get("origin") != ORIGIN
        or response.get("private_directory_ready") is not True
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
        or type(theme.get("tree_sha256")) is not str
        or SHA256_RE.fullmatch(theme["tree_sha256"]) is None
        or type(gates) is not dict
        or any(
            gates.get(name) is not True
            for name in ("global", "content_apply", "theme_apply")
        )
        or authorization
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "ttl_seconds": 900,
        }
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID")
    return response


def _content_after_sha256(document: Mapping[str, object], post_id: int) -> str:
    material = {
        "schema": "ContentDocumentV1",
        "post_type": document["post_type"],
        "id": post_id,
        "status": "publish",
        "title": document["title"],
        "slug": document["slug"],
        "excerpt": document["excerpt"],
        "block_markup": document["block_markup"],
        "taxonomies": document["taxonomies"],
        "media_ids": document["media_ids"],
    }
    return sha256_json(material)


def _attempt_expired(receipt: Mapping[str, object]) -> bool:
    proposals = receipt.get("proposals")
    if type(proposals) is not list or not proposals:
        created = receipt.get("attempt_created_at_gmt")
        if type(created) is not str:
            return False
        try:
            created_at = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
        except ValueError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        return datetime.now(UTC) >= created_at + timedelta(seconds=930)
    expirations: list[datetime] = []
    for proposal in proposals:
        if (
            type(proposal) is not dict
            or type(proposal.get("expires_at_gmt")) is not str
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        try:
            expirations.append(
                datetime.strptime(
                    proposal["expires_at_gmt"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC)
            )
        except ValueError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return datetime.now(UTC) >= min(expirations)


def _prepare_attempt(
    receipt: dict[str, object],
    articles: Sequence[Article],
    drafts: Mapping[str, Mapping[str, object]],
    include_theme: bool,
    path: Path,
) -> None:
    attempt = receipt.get("attempt_id")
    if type(attempt) is not str or SHA256_RE.fullmatch(attempt) is None:
        attempt = secrets.token_hex(32)
        receipt["attempt_id"] = attempt
        receipt["attempt_created_at_gmt"] = datetime.now(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        receipt["proposals"] = []
        receipt["batch_registration"] = None
        receipt["proposal_keys"] = {}
    keys = receipt["proposal_keys"]
    if type(keys) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if include_theme:
        desired_tree = receipt.get("desired_theme_tree_sha256")
        if type(desired_tree) is not str or SHA256_RE.fullmatch(desired_tree) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        keys.setdefault(
            "theme",
            sha256_json(
                {
                    "schema": "RAOS_WORDPRESS_THEME_PROPOSAL_KEY_V1",
                    "attempt_id": attempt,
                    "theme_version": theme_version(),
                    "theme_tree_sha256": desired_tree,
                }
            ),
        )
    for article in articles:
        draft = drafts[article.production_slug]
        keys.setdefault(
            f"content:{article.production_slug}",
            sha256_json(
                {
                    "schema": "RAOS_WORDPRESS_CONTENT_PROPOSAL_KEY_V1",
                    "attempt_id": attempt,
                    "id": draft["id"],
                    "precondition": precondition(draft),
                    "document": article.document(),
                }
            ),
        )
    _touch_receipt(path, receipt, "ATTEMPT_PREPARED")


def create_proposals(
    client: Any,
    articles: Sequence[Article],
    drafts: Mapping[str, Mapping[str, object]],
    include_theme: bool,
    receipt: dict[str, object],
    path: Path,
    deployment_runner: Callable[
        ..., subprocess.CompletedProcess[bytes]
    ] = subprocess.run,
) -> list[dict[str, object]]:
    _prepare_attempt(receipt, articles, drafts, include_theme, path)
    keys = receipt["proposal_keys"]
    if type(keys) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    existing = receipt["proposals"]
    if type(existing) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    by_identity: dict[str, dict[str, object]] = {}
    for proposal in existing:
        if type(proposal) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        identity = (
            "theme"
            if proposal.get("kind") == "THEME_RELEASE"
            else f"content:{proposal.get('slug')}"
        )
        by_identity[identity] = proposal

    if include_theme and "theme" not in by_identity:
        key = keys.get("theme")
        desired_tree = receipt.get("desired_theme_tree_sha256")
        if type(key) is not str or SHA256_RE.fullmatch(key) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if type(desired_tree) is not str or SHA256_RE.fullmatch(desired_tree) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        response = _deployment_mcp_call(
            "theme-propose-release",
            {"idempotency_key": key},
            timeout=120,
            runner=deployment_runner,
        )
        proposal = _proposal_record(
            kind="THEME_RELEASE",
            slug=None,
            key=key,
            response=response,
            expected_after=desired_tree,
        )
        existing.append(proposal)
        by_identity["theme"] = proposal
        _touch_receipt(path, receipt, "PROPOSALS_IN_PROGRESS")

    for article in articles:
        identity = f"content:{article.production_slug}"
        if identity in by_identity:
            continue
        key = keys.get(identity)
        if type(key) is not str or SHA256_RE.fullmatch(key) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        draft = drafts[article.production_slug]
        expected_after = _content_after_sha256(article.document(), draft["id"])
        response = client.call(
            "raos-codex-content-propose-release",
            {
                "id": draft["id"],
                "precondition": precondition(draft),
                "document": article.document(),
                "idempotency_key": key,
            },
        )
        proposal = _proposal_record(
            kind="CONTENT_RELEASE",
            slug=article.production_slug,
            key=key,
            response=response,
            expected_after=expected_after,
        )
        existing.append(proposal)
        by_identity[identity] = proposal
        _touch_receipt(path, receipt, "PROPOSALS_IN_PROGRESS")

    ordered: list[dict[str, object]] = []
    if include_theme:
        ordered.append(by_identity["theme"])
    ordered.extend(
        by_identity[f"content:{article.production_slug}"] for article in articles
    )
    receipt["proposals"] = ordered
    _touch_receipt(path, receipt, "PROPOSALS_READY")
    return ordered


def _proposal_ids(receipt: Mapping[str, object]) -> list[str]:
    proposals = receipt.get("proposals")
    selected_slugs = receipt.get("selected_slugs")
    desired_tree = receipt.get("desired_theme_tree_sha256")
    if (
        type(proposals) is not list
        or not 1 <= len(proposals) <= 20
        or type(selected_slugs) is not list
        or any(type(slug) is not str for slug in selected_slugs)
        or type(desired_tree) is not str
        or SHA256_RE.fullmatch(desired_tree) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    result: list[str] = []
    content_slugs: list[str] = []
    theme_count = 0
    required = {
        "kind",
        "slug",
        "proposal_id",
        "after_sha256",
        "expires_at_gmt",
        "idempotency_key",
    }
    for proposal in proposals:
        if type(proposal) is not dict or set(proposal) != required:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        kind = proposal.get("kind")
        slug = proposal.get("slug")
        proposal_id = proposal.get("proposal_id")
        after_sha256 = proposal.get("after_sha256")
        key = proposal.get("idempotency_key")
        expires = proposal.get("expires_at_gmt")
        if (
            kind not in {"CONTENT_RELEASE", "THEME_RELEASE"}
            or type(proposal_id) is not str
            or SHA256_RE.fullmatch(proposal_id) is None
            or proposal_id in result
            or type(after_sha256) is not str
            or SHA256_RE.fullmatch(after_sha256) is None
            or type(key) is not str
            or SHA256_RE.fullmatch(key) is None
            or type(expires) is not str
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if kind == "THEME_RELEASE":
            theme_count += 1
            if slug is not None or after_sha256 != desired_tree:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        else:
            if type(slug) is not str or SLUG_RE.fullmatch(slug) is None:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            content_slugs.append(slug)
        result.append(proposal_id)
    if (
        theme_count > 1
        or len(content_slugs) != len(set(content_slugs))
        or sorted(content_slugs) != selected_slugs
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return result


def register_publication_batch(
    client: Any,
    receipt: dict[str, object],
    path: Path,
) -> dict[str, object]:
    proposal_ids = sorted(_proposal_ids(receipt))
    response = client.call(
        "raos-codex-publication-batch-register",
        {"proposal_ids": proposal_ids},
    )
    batch_token = response.get("batch_token")
    manifest_hash = response.get("batch_manifest_sha256")
    expires = response.get("expires_at_gmt")
    if (
        response.get("schema") != "RAOSWordPressPublicationBatchV1"
        or type(batch_token) is not str
        or SHA256_RE.fullmatch(batch_token) is None
        or type(manifest_hash) is not str
        or SHA256_RE.fullmatch(manifest_hash) is None
        or response.get("proposal_count") != len(proposal_ids)
        or response.get("proposal_ids") != proposal_ids
        or type(expires) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
        or response.get("review_url") != REVIEW_URL
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    receipt["batch_registration"] = response
    _touch_receipt(path, receipt, "BATCH_REGISTERED")
    return response


def _registered_proposal_ids(receipt: Mapping[str, object]) -> list[str]:
    registration = receipt.get("batch_registration")
    proposal_ids = (
        registration.get("proposal_ids") if type(registration) is dict else None
    )
    if (
        type(registration) is not dict
        or registration.get("schema") != "RAOSWordPressPublicationBatchV1"
        or type(registration.get("batch_token")) is not str
        or SHA256_RE.fullmatch(registration["batch_token"]) is None
        or type(registration.get("batch_manifest_sha256")) is not str
        or SHA256_RE.fullmatch(registration["batch_manifest_sha256"]) is None
        or type(proposal_ids) is not list
        or proposal_ids != sorted(proposal_ids)
        or len(proposal_ids) != len(set(proposal_ids))
        or any(
            type(value) is not str or SHA256_RE.fullmatch(value) is None
            for value in proposal_ids
        )
        or proposal_ids != sorted(_proposal_ids(receipt))
        or registration.get("proposal_count") != len(proposal_ids)
        or type(registration.get("expires_at_gmt")) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            registration["expires_at_gmt"],
        )
        is None
        or registration.get("review_url") != REVIEW_URL
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    return proposal_ids


def wait_and_apply(
    receipt: dict[str, object],
    path: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    proposal_ids = _registered_proposal_ids(receipt)
    registration = receipt.get("batch_registration")
    if type(registration) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    batch_token = registration.get("batch_token")
    manifest_hash = registration.get("batch_manifest_sha256")
    if type(batch_token) is not str or type(manifest_hash) is not str:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    proposals = receipt.get("proposals")
    if type(proposals) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    print("\nWordPress管理画面で内容を確認し、「一括承認」を押してください。")
    print(f"承認対象バッチtoken末尾12文字: {batch_token[-12:]}")
    print(f"入力するbatch manifest hash末尾8文字: {manifest_hash[-8:]}")
    print(REVIEW_URL)
    print("承認待機中です。このコマンドは閉じないでください。", flush=True)
    _touch_receipt(path, receipt, "WAITING_FOR_APPROVAL")
    aggregate = _deployment_mcp_call(
        "release-wait-and-apply",
        {
            "batch_token": batch_token,
            "batch_manifest_sha256": manifest_hash,
            "proposal_ids": proposal_ids,
        },
        timeout=1080,
        runner=runner,
    )
    if (
        aggregate.get("schema") != "ReleaseWaitApplyReceiptV1"
        or aggregate.get("state") != "APPLIED"
        or type(aggregate.get("receipts")) is not list
        or len(aggregate["receipts"]) != len(proposal_ids)
    ):
        fail("RAOS_WORDPRESS_REQUEST_APPLY_RECEIPT_INVALID")
    proposal_by_id = {
        proposal["proposal_id"]: proposal
        for proposal in proposals
        if type(proposal) is dict and type(proposal.get("proposal_id")) is str
    }
    expected_order = sorted(
        proposal_ids,
        key=lambda proposal_id: (
            proposal_by_id[proposal_id].get("kind") != "THEME_RELEASE",
            proposal_ids.index(proposal_id),
        ),
    )
    for proposal_id, operation in zip(
        expected_order, aggregate["receipts"], strict=True
    ):
        proposal = proposal_by_id.get(proposal_id)
        expected_after = (
            proposal.get("after_sha256") if type(proposal) is dict else None
        )
        if (
            type(operation) is not dict
            or operation.get("schema") != "OperationReceiptV1"
            or operation.get("proposal_id") != proposal_id
            or operation.get("operation_id") != proposal_id
            or operation.get("state") != "APPLIED"
            or type(operation.get("result_code")) is not str
            or re.fullmatch(r"[A-Z0-9_]{3,96}", operation["result_code"]) is None
            or type(operation.get("after_sha256")) is not str
            or SHA256_RE.fullmatch(operation["after_sha256"]) is None
            or operation["after_sha256"] != expected_after
        ):
            fail("RAOS_WORDPRESS_REQUEST_APPLY_RECEIPT_INVALID")
    receipt["apply_receipt"] = aggregate
    _touch_receipt(path, receipt, "APPLY_RETURNED")
    return aggregate


def verify_published(
    client: Any,
    articles: Sequence[Article],
    receipt: dict[str, object],
    path: Path,
    *,
    expected_theme_version: str,
    expected_theme_tree_sha256: str,
    theme_was_proposed: bool,
    deployment_runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    drafts = receipt.get("drafts")
    if type(drafts) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    for article in articles:
        draft = drafts.get(article.production_slug)
        if type(draft) is not dict or type(draft.get("id")) is not int:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        document = client.call("raos-codex-content-get", {"id": draft["id"]})
        if (
            document.get("status") != "publish"
            or document_projection(document) != article.document()
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED")
    status = client.call("raos-codex-site-status", {})
    theme = status.get("theme")
    if theme_was_proposed and (
        type(theme) is not dict or theme.get("version") != expected_theme_version
    ):
        fail("RAOS_WORDPRESS_REQUEST_THEME_READBACK_FAILED")
    deployed = deployment_status(deployment_runner)
    deployed_theme = deployed.get("theme")
    if (
        type(deployed_theme) is not dict
        or deployed_theme.get("tree_sha256") != expected_theme_tree_sha256
    ):
        fail("RAOS_WORDPRESS_REQUEST_THEME_READBACK_FAILED")
    _touch_receipt(path, receipt, "APPLIED")


def _same_desired(
    receipt: Mapping[str, object],
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
) -> bool:
    return (
        receipt.get("desired_sha256")
        == {article.production_slug: article.desired_sha256() for article in articles}
        and receipt.get("desired_theme_tree_sha256") == desired_theme_tree_sha256
    )


def _resume_ready(receipt: Mapping[str, object], expected_count: int) -> bool:
    proposals = receipt.get("proposals")
    return (
        receipt.get("state")
        in {"BATCH_REGISTERED", "WAITING_FOR_APPROVAL", "APPLY_RETURNED", "APPLIED"}
        and type(proposals) is list
        and len(proposals) in {expected_count, expected_count + 1}
        and type(receipt.get("batch_registration")) is dict
    )


def execute(
    selection: str,
    *,
    preview: Callable[[], None] = run_preview_checks,
    client_factory: Callable[[], Any] = EditorMcpClient,
    deployment_runner: Callable[
        ..., subprocess.CompletedProcess[bytes]
    ] = subprocess.run,
) -> Path:
    articles = load_articles(selection)
    with request_lock():
        # This ordering is a safety invariant: no credential read, remote status,
        # draft write, or proposal can happen before all local checks pass.
        theme_tree_before_preview = tracked_theme_tree_sha256()
        preview()
        local_theme_version = theme_version()
        local_theme_tree_sha256 = tracked_theme_tree_sha256()
        if local_theme_tree_sha256 != theme_tree_before_preview:
            fail("RAOS_WORDPRESS_REQUEST_THEME_CHANGED_DURING_PREVIEW")
        path = _receipt_path(articles)
        loaded = _read_receipt(path)
        is_new_receipt = loaded is None
        receipt = (
            _fresh_receipt(articles, path, local_theme_tree_sha256)
            if loaded is None
            else _validate_receipt(loaded, articles)
        )
        desired_matches = _same_desired(receipt, articles, local_theme_tree_sha256)
        if not desired_matches and receipt.get("proposals"):
            if not _attempt_expired(receipt):
                fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
            receipt = _fresh_receipt(articles, path, local_theme_tree_sha256) | {
                "drafts": receipt.get("drafts", {})
            }
        elif not desired_matches:
            receipt["desired_sha256"] = {
                article.production_slug: article.desired_sha256()
                for article in articles
            }
            receipt["desired_theme_tree_sha256"] = local_theme_tree_sha256
            receipt["attempt_id"] = None
            receipt["attempt_created_at_gmt"] = None
            receipt["proposal_keys"] = {}
            receipt["proposals"] = []
            receipt["batch_registration"] = None
            receipt["apply_receipt"] = None
        if is_new_receipt or not desired_matches:
            _touch_receipt(path, receipt, "LOCAL_VERIFIED")
        else:
            _atomic_receipt(path, receipt)

        client = client_factory()
        client.initialize()
        tools = client.tools()
        validate_tool_contract(tools)
        status = client.call("raos-codex-site-status", {})
        validate_site_status(status)
        live_theme = status["theme"]
        if type(live_theme) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_SITE_NOT_READY")
        deployed_before = deployment_status(deployment_runner)
        deployed_theme = deployed_before.get("theme")
        if type(deployed_theme) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID")
        include_theme = deployed_theme.get("tree_sha256") != local_theme_tree_sha256

        if _resume_ready(receipt, len(articles)):
            proposal_ids = _proposal_ids(receipt)
            proposals = receipt.get("proposals")
            if type(proposals) is not list or not proposal_ids:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            has_desired_theme = any(
                type(proposal) is dict
                and proposal.get("kind") == "THEME_RELEASE"
                and proposal.get("after_sha256") == local_theme_tree_sha256
                for proposal in proposals
            )
            if include_theme and not has_desired_theme:
                # A content-only approval batch cannot publish after the live
                # theme drifts away from the locally reviewed exact tree.
                fail("RAOS_WORDPRESS_REQUEST_PENDING_THEME_DRIFT")
            try:
                wait_and_apply(receipt, path, deployment_runner)
            except PublicationFailure as error:
                if str(error) != "WORDPRESS_MCP_RELEASE_EXPIRED":
                    raise
                # The remote operation state, not the receipt clock, decides
                # whether an interrupted apply succeeded. Only a confirmed
                # EXPIRED result permits a new proposal attempt.
                receipt["attempt_id"] = None
                receipt["attempt_created_at_gmt"] = None
                receipt["proposal_keys"] = {}
                receipt["proposals"] = []
                receipt["batch_registration"] = None
                receipt["apply_receipt"] = None
                _touch_receipt(path, receipt, "EXPIRED_ATTEMPT_REPLACED")
            else:
                verify_published(
                    client,
                    articles,
                    receipt,
                    path,
                    expected_theme_version=local_theme_version,
                    expected_theme_tree_sha256=local_theme_tree_sha256,
                    theme_was_proposed=len(receipt["proposals"]) == len(articles) + 1,
                    deployment_runner=deployment_runner,
                )
                return path

        if receipt.get("attempt_id") is not None and _attempt_expired(receipt):
            receipt["attempt_id"] = None
            receipt["attempt_created_at_gmt"] = None
            receipt["proposal_keys"] = {}
            receipt["proposals"] = []
            receipt["batch_registration"] = None
            receipt["apply_receipt"] = None
            _touch_receipt(path, receipt, "EXPIRED_ATTEMPT_REPLACED")

        documents = list_all_documents(client)
        drafts = reconcile_drafts(client, articles, documents, receipt, path)
        proposals = create_proposals(
            client,
            articles,
            drafts,
            include_theme,
            receipt,
            path,
            deployment_runner,
        )
        if len(proposals) != len(articles) + (1 if include_theme else 0):
            fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_SET_INVALID")
        register_publication_batch(client, receipt, path)
        wait_and_apply(receipt, path, deployment_runner)
        verify_published(
            client,
            articles,
            receipt,
            path,
            expected_theme_version=local_theme_version,
            expected_theme_tree_sha256=local_theme_tree_sha256,
            theme_was_proposed=include_theme,
            deployment_runner=deployment_runner,
        )
        return path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument(
        "--articles",
        default=os.environ.get("ARTICLES", "all"),
        help="all (default) or a comma-separated list of exact production slugs",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        path = execute(arguments.articles)
        print("公開と本番read-backが完了しました。")
        print(f"受領書: {path}")
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("RAOS_WORDPRESS_REQUEST_INTERRUPTED\n")
        return 130
    except PublicationFailure as error:
        sys.stderr.write(str(error) + "\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
