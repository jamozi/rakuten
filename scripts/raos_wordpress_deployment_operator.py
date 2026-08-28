#!/usr/bin/env python3
"""Bounded deployment operator used only by the local WordPress MCP bridge.

The caller selects one of six closed operations and supplies JSON on stdin.  It
cannot provide a URL, command, PHP, SQL, credential path, or local package path.
Publication and code mutation remain impossible until a distinct administrator
has approved the hash-bound proposal in wp-admin and all host gates are true.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping, Sequence
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Final, NoReturn
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT: Final = Path(__file__).resolve().parents[1]
ORIGIN: Final = "https://kurashinoshirube.com"
DEPLOY_API: Final = f"{ORIGIN}/wp-json/raos-codex-deploy/v1"
CREDENTIAL_PATH: Final = (
    ROOT / ".secrets/wordpress-mcp/operator-application-password.v1.json"
)
THEME_ROOT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
THEME_SLUG: Final = "kurashinoshirube-child"
ARTIFACT_REGISTRY: Final = (
    ROOT / "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json"
)
REPO_ARTIFACT_DIRECTORY: Final = ROOT / ".secrets/wordpress-mcp/repo-plugin-artifacts"
MAX_STDIN_BYTES: Final = 64 * 1024
MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 32 * 1024 * 1024
MAX_FILE_BYTES: Final = 8 * 1024 * 1024
MAX_FILE_COUNT: Final = 2048
ZIP_TIMESTAMP: Final = (2026, 8, 28, 0, 0, 0)
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE: Final = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")
ARTIFACT_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
MIGRATION_SIGNALS: Final = (
    re.compile(rb"register_activation_hook\s*\(", re.IGNORECASE),
    re.compile(rb"\bdbDelta\s*\(", re.IGNORECASE),
    re.compile(rb"\$wpdb\b", re.IGNORECASE),
    re.compile(rb"\b(?:ALTER|CREATE|DROP|TRUNCATE)\s+TABLE\b", re.IGNORECASE),
    re.compile(rb"\b(?:update|add|delete)_site_option\s*\(", re.IGNORECASE),
    re.compile(rb"\b(?:update|add|delete)_option\s*\(", re.IGNORECASE),
    re.compile(rb"migrat(?:e|ion|ing)", re.IGNORECASE),
)


class OperatorFailure(RuntimeError):
    """Closed failure whose message is a non-sensitive result code."""


def fail(code: str = "WORDPRESS_MCP_OPERATOR_REFUSED") -> NoReturn:
    raise OperatorFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail("WORDPRESS_MCP_JSON_INVALID")


def exact_object(
    value: object, required: set[str], optional: set[str] | None = None
) -> dict[str, object]:
    if type(value) is not dict:
        fail("WORDPRESS_MCP_INPUT_INVALID")
    result = value
    allowed = required | (optional or set())
    if set(result) - allowed or not required.issubset(result):
        fail("WORDPRESS_MCP_INPUT_INVALID")
    if any(type(key) is not str for key in result):
        fail("WORDPRESS_MCP_INPUT_INVALID")
    return result


def read_stdin() -> dict[str, object]:
    payload = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if len(payload) > MAX_STDIN_BYTES:
        fail("WORDPRESS_MCP_INPUT_TOO_LARGE")
    try:
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_INPUT_INVALID")
    return exact_object(
        decoded, set(), set(decoded) if type(decoded) is dict else set()
    )


def require_sha256(value: object, code: str = "WORDPRESS_MCP_INPUT_INVALID") -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        fail(code)
    return value


def require_slug(value: object) -> str:
    if type(value) is not str or len(value) > 100 or SLUG_RE.fullmatch(value) is None:
        fail("WORDPRESS_MCP_PLUGIN_SLUG_INVALID")
    return value


def require_version(value: object) -> str:
    if type(value) is not str or len(value) > 64 or VERSION_RE.fullmatch(value) is None:
        fail("WORDPRESS_MCP_PLUGIN_VERSION_INVALID")
    return value


def _secure_regular_file(path: Path, maximum: int) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_PRIVATE_FILE_UNAVAILABLE")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 1 <= metadata.st_size <= maximum
        or len(payload) != metadata.st_size
    ):
        fail("WORDPRESS_MCP_PRIVATE_FILE_INSECURE")
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
    except OSError:
        fail("WORDPRESS_MCP_PRIVATE_FILE_INSECURE")
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        fail("WORDPRESS_MCP_PRIVATE_FILE_INSECURE")
    return payload


def credentials() -> tuple[str, str]:
    payload = _secure_regular_file(CREDENTIAL_PATH, 16 * 1024)
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_CREDENTIAL_INVALID")
    record = exact_object(
        value,
        {"schema", "origin", "username", "application_password", "purpose"},
    )
    if (
        record["schema"] != "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1"
        or record["origin"] != ORIGIN
        or record["purpose"] != "deployment_operator"
        or type(record["username"]) is not str
        or not record["username"]
        or type(record["application_password"]) is not str
        or len(record["application_password"]) < 20
    ):
        fail("WORDPRESS_MCP_CREDENTIAL_INVALID")
    return record["username"], record["application_password"]


def request_json(
    method: str,
    path: str,
    body: Mapping[str, object] | None = None,
    proposal_id: str | None = None,
) -> dict[str, object]:
    if method not in {"GET", "POST"} or not path.startswith("/") or ".." in path:
        fail("WORDPRESS_MCP_TRANSPORT_INVALID")
    username, application_password = credentials()
    headers = {
        "Accept": "application/json",
        "Authorization": "Basic "
        + base64.b64encode(f"{username}:{application_password}".encode()).decode(
            "ascii"
        ),
        "User-Agent": "raos-wordpress-bridge/1.0.0",
    }
    data = None
    if body is not None:
        data = canonical_json(dict(body))
        headers["Content-Type"] = "application/json"
    if proposal_id is not None:
        proposal_id = require_sha256(proposal_id)
        headers["If-Match"] = f'"{proposal_id}"'
        headers["Idempotency-Key"] = proposal_id
    request = urllib.request.Request(
        DEPLOY_API + path,
        data=data,
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:
            if response.geturl() != DEPLOY_API + path:
                fail("WORDPRESS_MCP_REDIRECT_REFUSED")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                fail("WORDPRESS_MCP_RESPONSE_TOO_LARGE")
    except urllib.error.HTTPError as error:
        code = f"WORDPRESS_MCP_HTTP_{error.code}"
        try:
            error_payload = error.read(16 * 1024)
            parsed = json.loads(error_payload.decode("utf-8", errors="strict"))
            if type(parsed) is dict and type(parsed.get("code")) is str:
                candidate = parsed["code"].upper().replace("-", "_")
                if re.fullmatch(r"[A-Z0-9_]{3,96}", candidate):
                    code = candidate
        except OSError, UnicodeError, json.JSONDecodeError:
            pass
        fail(code)
    except urllib.error.URLError, TimeoutError, OSError:
        fail("WORDPRESS_MCP_TRANSPORT_FAILED")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_RESPONSE_INVALID")
    return exact_object(value, set(), set(value) if type(value) is dict else set())


def git(*arguments: str) -> bytes:
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
        fail("WORDPRESS_MCP_GIT_FAILED")
    if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
        fail("WORDPRESS_MCP_GIT_FAILED")
    return completed.stdout


def _safe_zip_name(filename: str, slug: str) -> PurePosixPath:
    if (
        not filename
        or "\\" in filename
        or filename.startswith("/")
        or "\x00" in filename
    ):
        fail("WORDPRESS_MCP_ZIP_PATH_INVALID")
    path = PurePosixPath(filename)
    if any(part in {"", ".", ".."} for part in path.parts):
        fail("WORDPRESS_MCP_ZIP_PATH_INVALID")
    if not path.parts or path.parts[0] != slug:
        fail("WORDPRESS_MCP_ZIP_ROOT_INVALID")
    if len(filename) > 300:
        fail("WORDPRESS_MCP_ZIP_PATH_INVALID")
    return path


def validate_package(
    payload: bytes, *, kind: str, slug: str, expected_version: str
) -> tuple[list[dict[str, object]], str, str, bool]:
    if not 1 <= len(payload) <= MAX_PACKAGE_BYTES:
        fail("WORDPRESS_MCP_PACKAGE_SIZE_INVALID")
    manifest: list[dict[str, object]] = []
    seen_casefolded: set[str] = set()
    migration_signal = False
    header_payload: bytes | None = None
    header_count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_FILE_COUNT:
                fail("WORDPRESS_MCP_PACKAGE_FILE_COUNT_INVALID")
            total = 0
            for info in infos:
                path = _safe_zip_name(info.filename, slug)
                normalized = path.as_posix()
                folded = normalized.casefold()
                if folded in seen_casefolded:
                    fail("WORDPRESS_MCP_ZIP_CASE_COLLISION")
                seen_casefolded.add(folded)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    fail("WORDPRESS_MCP_ZIP_SYMLINK_REFUSED")
                if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    fail("WORDPRESS_MCP_ZIP_SPECIAL_FILE_REFUSED")
                if info.is_dir():
                    continue
                if info.file_size < 0 or info.file_size > MAX_FILE_BYTES:
                    fail("WORDPRESS_MCP_PACKAGE_FILE_SIZE_INVALID")
                total += info.file_size
                if total > MAX_PACKAGE_BYTES:
                    fail("WORDPRESS_MCP_PACKAGE_EXPANDED_SIZE_INVALID")
                file_payload = archive.read(info)
                if len(file_payload) != info.file_size:
                    fail("WORDPRESS_MCP_PACKAGE_READ_INVALID")
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                manifest.append(
                    {
                        "path": relative,
                        "size": len(file_payload),
                        "sha256": sha256(file_payload),
                    }
                )
                if kind == "theme" and relative == "style.css":
                    header_payload = file_payload
                    header_count += 1
                if (
                    kind == "plugin"
                    and len(path.parts) == 2
                    and relative.endswith(".php")
                ):
                    if b"Plugin Name:" in file_payload[:8192]:
                        header_payload = file_payload
                        header_count += 1
                if kind == "plugin" and relative.endswith(".php"):
                    if any(signal.search(file_payload) for signal in MIGRATION_SIGNALS):
                        migration_signal = True
    except OperatorFailure:
        raise
    except zipfile.BadZipFile, RuntimeError, OSError, KeyError:
        fail("WORDPRESS_MCP_ZIP_INVALID")
    if header_payload is None or header_count != 1:
        fail("WORDPRESS_MCP_PACKAGE_HEADER_MISSING")
    header_name = b"Version:" if kind == "theme" else b"Version:"
    match = re.search(
        rb"(?im)^\s*(?:\*\s*)?" + header_name + rb"\s*([^\r\n]+)", header_payload[:8192]
    )
    if match is None:
        fail("WORDPRESS_MCP_PACKAGE_VERSION_MISSING")
    try:
        package_version = match.group(1).decode("utf-8", errors="strict").strip()
    except UnicodeError:
        fail("WORDPRESS_MCP_PACKAGE_VERSION_INVALID")
    if package_version != expected_version:
        fail("WORDPRESS_MCP_PACKAGE_VERSION_MISMATCH")
    manifest.sort(key=lambda entry: str(entry["path"]))
    manifest_hash = sha256(canonical_json(manifest))
    return manifest, manifest_hash, package_version, not migration_signal


def theme_package() -> tuple[bytes, dict[str, object]]:
    relative_root = THEME_ROOT.relative_to(ROOT).as_posix()
    status = git("status", "--porcelain=v1", "--", relative_root)
    if status:
        fail("WORDPRESS_MCP_THEME_SOURCE_DIRTY")
    head = git("rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        fail("WORDPRESS_MCP_GIT_FAILED")
    raw_files = git("ls-files", "-z", "--", relative_root)
    tracked = [
        value.decode("utf-8", errors="strict")
        for value in raw_files.split(b"\0")
        if value
    ]
    if not tracked:
        fail("WORDPRESS_MCP_THEME_SOURCE_EMPTY")
    output = io.BytesIO()
    style_payload: bytes | None = None
    seen: set[str] = set()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for repository_relative in sorted(tracked):
            source = ROOT / repository_relative
            try:
                metadata = source.lstat()
                payload = source.read_bytes()
            except OSError:
                fail("WORDPRESS_MCP_THEME_SOURCE_INVALID")
            if (
                source.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                fail("WORDPRESS_MCP_THEME_SOURCE_INVALID")
            relative = source.relative_to(THEME_ROOT).as_posix()
            if relative.casefold() in seen:
                fail("WORDPRESS_MCP_ZIP_CASE_COLLISION")
            seen.add(relative.casefold())
            if relative == "style.css":
                style_payload = payload
            info = zipfile.ZipInfo(f"{THEME_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.create_system = 3
            archive.writestr(
                info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    if style_payload is None:
        fail("WORDPRESS_MCP_THEME_STYLE_MISSING")
    match = re.search(
        rb"(?im)^\s*(?:\*\s*)?Version:\s*([^\r\n]+)", style_payload[:8192]
    )
    if match is None:
        fail("WORDPRESS_MCP_PACKAGE_VERSION_MISSING")
    try:
        version = require_version(
            match.group(1).decode("utf-8", errors="strict").strip()
        )
    except UnicodeError:
        fail("WORDPRESS_MCP_PACKAGE_VERSION_INVALID")
    payload = output.getvalue()
    manifest, manifest_hash, _, safe = validate_package(
        payload, kind="theme", slug=THEME_SLUG, expected_version=version
    )
    if not safe:
        fail("WORDPRESS_MCP_THEME_ASSESSMENT_INVALID")
    descriptor: dict[str, object] = {
        "schema": "CodePackageV1",
        "kind": "theme",
        "source": "tracked_child_theme",
        "artifact_id": None,
        "git_commit": head,
        "slug": THEME_SLUG,
        "old_version": None,
        "new_version": version,
        "package_sha256": sha256(payload),
        "file_manifest_sha256": manifest_hash,
        "file_manifest": manifest,
        "activation_intent": "preserve",
        "migration_assessment": "NO_IRREVERSIBLE_MIGRATION_SIGNALS",
        "automatic_apply_eligible": True,
    }
    return payload, descriptor


def _download_official_plugin(slug: str, version: str) -> bytes:
    query = urllib.parse.urlencode(
        {
            "action": "plugin_information",
            "request[slug]": slug,
            "request[fields][versions]": "1",
            "format": "json",
        }
    )
    metadata_url = f"https://api.wordpress.org/plugins/info/1.2/?{query}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(metadata_url, timeout=30) as response:
            if response.geturl() != metadata_url:
                fail("WORDPRESS_MCP_WORDPRESS_ORG_REDIRECT_REFUSED")
            raw = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.URLError, TimeoutError, OSError:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_FAILED")
    if len(raw) > 2 * 1024 * 1024:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_RESPONSE_TOO_LARGE")
    try:
        metadata = json.loads(raw.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_RESPONSE_INVALID")
    if type(metadata) is not dict or type(metadata.get("versions")) is not dict:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_VERSION_NOT_FOUND")
    download_url = metadata["versions"].get(version)
    if type(download_url) is not str:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_VERSION_NOT_FOUND")
    parsed = urllib.parse.urlsplit(download_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "downloads.wordpress.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        fail("WORDPRESS_MCP_WORDPRESS_ORG_URL_INVALID")
    try:
        with opener.open(download_url, timeout=60) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "downloads.wordpress.org":
                fail("WORDPRESS_MCP_WORDPRESS_ORG_REDIRECT_REFUSED")
            payload = response.read(MAX_PACKAGE_BYTES + 1)
    except urllib.error.URLError, TimeoutError, OSError:
        fail("WORDPRESS_MCP_WORDPRESS_ORG_DOWNLOAD_FAILED")
    if len(payload) > MAX_PACKAGE_BYTES:
        fail("WORDPRESS_MCP_PACKAGE_SIZE_INVALID")
    return payload


def _repo_artifact(artifact_id: str, slug: str, version: str) -> bytes:
    try:
        registry_raw = ARTIFACT_REGISTRY.read_bytes()
        registry = json.loads(registry_raw.decode("utf-8", errors="strict"))
    except OSError, UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_ARTIFACT_REGISTRY_INVALID")
    if (
        type(registry) is not dict
        or registry.get("schema") != "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1"
        or type(registry.get("artifacts")) is not list
    ):
        fail("WORDPRESS_MCP_ARTIFACT_REGISTRY_INVALID")
    match: dict[str, object] | None = None
    for candidate in registry["artifacts"]:
        if type(candidate) is dict and candidate.get("artifact_id") == artifact_id:
            match = candidate
            break
    if match is None:
        fail("WORDPRESS_MCP_ARTIFACT_NOT_REGISTERED")
    if match.get("slug") != slug or match.get("version") != version:
        fail("WORDPRESS_MCP_ARTIFACT_BINDING_MISMATCH")
    expected = require_sha256(
        match.get("package_sha256"), "WORDPRESS_MCP_ARTIFACT_REGISTRY_INVALID"
    )
    path = REPO_ARTIFACT_DIRECTORY / f"{artifact_id}.zip"
    payload = _secure_regular_file(path, MAX_PACKAGE_BYTES)
    if sha256(payload) != expected:
        fail("WORDPRESS_MCP_ARTIFACT_DIGEST_MISMATCH")
    return payload


def plugin_package(inputs: dict[str, object]) -> tuple[bytes, dict[str, object]]:
    record = exact_object(
        inputs,
        {"source", "slug", "version", "activation_intent"},
        {"artifact_id"},
    )
    source = record["source"]
    slug = require_slug(record["slug"])
    version = require_version(record["version"])
    intent = record["activation_intent"]
    if intent not in {"preserve", "activate", "deactivate"}:
        fail("WORDPRESS_MCP_ACTIVATION_INTENT_INVALID")
    artifact_id: str | None = None
    if source == "wordpress_org":
        if "artifact_id" in record:
            fail("WORDPRESS_MCP_INPUT_INVALID")
        payload = _download_official_plugin(slug, version)
    elif source == "repo_artifact":
        value = record.get("artifact_id")
        if type(value) is not str or ARTIFACT_ID_RE.fullmatch(value) is None:
            fail("WORDPRESS_MCP_ARTIFACT_ID_INVALID")
        artifact_id = value
        payload = _repo_artifact(artifact_id, slug, version)
    else:
        fail("WORDPRESS_MCP_PLUGIN_SOURCE_REFUSED")
    manifest, manifest_hash, _, migration_safe = validate_package(
        payload, kind="plugin", slug=slug, expected_version=version
    )
    descriptor: dict[str, object] = {
        "schema": "CodePackageV1",
        "kind": "plugin",
        "source": source,
        "artifact_id": artifact_id,
        "git_commit": None,
        "slug": slug,
        "old_version": None,
        "new_version": version,
        "package_sha256": sha256(payload),
        "file_manifest_sha256": manifest_hash,
        "file_manifest": manifest,
        "activation_intent": intent,
        "migration_assessment": (
            "NO_IRREVERSIBLE_MIGRATION_SIGNALS"
            if migration_safe
            else "MANUAL_REVIEW_REQUIRED"
        ),
        "automatic_apply_eligible": migration_safe,
    }
    return payload, descriptor


def run(command: str, inputs: dict[str, object]) -> dict[str, object]:
    if command == "content-apply-release":
        record = exact_object(inputs, {"proposal_id"})
        proposal_id = require_sha256(record["proposal_id"])
        return request_json("POST", f"/proposals/{proposal_id}/apply", {}, proposal_id)
    if command == "theme-propose-release":
        exact_object(inputs, set())
        payload, descriptor = theme_package()
        status = request_json("GET", "/status")
        current_theme = status.get("theme")
        if type(current_theme) is dict:
            old_version = current_theme.get("version")
            if old_version is not None and type(old_version) is not str:
                fail("WORDPRESS_MCP_STATUS_INVALID")
            descriptor["old_version"] = old_version
        return request_json(
            "POST",
            "/proposals",
            {
                "kind": "theme_release",
                "code_package": descriptor,
                "package_base64": base64.b64encode(payload).decode("ascii"),
            },
        )
    if command == "theme-apply-release":
        record = exact_object(inputs, {"proposal_id"})
        proposal_id = require_sha256(record["proposal_id"])
        return request_json("POST", f"/proposals/{proposal_id}/apply", {}, proposal_id)
    if command == "plugin-propose-change":
        payload, descriptor = plugin_package(inputs)
        return request_json(
            "POST",
            "/proposals",
            {
                "kind": "plugin_change",
                "code_package": descriptor,
                "package_base64": base64.b64encode(payload).decode("ascii"),
            },
        )
    if command == "plugin-apply-change":
        record = exact_object(inputs, {"proposal_id"})
        proposal_id = require_sha256(record["proposal_id"])
        return request_json("POST", f"/proposals/{proposal_id}/apply", {}, proposal_id)
    if command == "operation-recover":
        record = exact_object(inputs, {"operation_id"})
        operation_id = require_sha256(record["operation_id"])
        return request_json("POST", f"/operations/{operation_id}/recover", {})
    fail("WORDPRESS_MCP_COMMAND_REFUSED")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument(
        "command",
        choices=(
            "content-apply-release",
            "theme-propose-release",
            "theme-apply-release",
            "plugin-propose-change",
            "plugin-apply-change",
            "operation-recover",
        ),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        inputs = read_stdin()
        output = run(arguments.command, inputs)
        sys.stdout.buffer.write(canonical_json(output) + b"\n")
        return 0
    except OperatorFailure as error:
        sys.stderr.write(str(error) + "\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
