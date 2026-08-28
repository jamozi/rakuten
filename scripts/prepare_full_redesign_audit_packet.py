#!/usr/bin/env python3
"""Build and validate the owner-private RAOS full-redesign Pro audit packet."""

from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import gzip
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import tarfile
import tempfile
from typing import Any, Final, NoReturn
from urllib.parse import urlsplit


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONFIG_PATH: Final = (
    REPOSITORY_ROOT / "changes/full-redesign-v2/audit-packet-inputs.v1.json"
)
PRIVATE_ROOT: Final = REPOSITORY_ROOT / ".secrets/full-redesign-audit"
BROWSER_EVIDENCE_ROOT: Final = PRIVATE_ROOT / "browser-source"
PUBLIC_CAPTURE_PATH: Final = PRIVATE_ROOT / "public-capture.v1.json"
PACKET_SCHEMA: Final = "RAOS_FULL_REDESIGN_AUDIT_PACKET_V1"
CAPTURE_SCHEMA: Final = "RAOS_FULL_REDESIGN_PUBLIC_CAPTURE_V1"
CONFIG_SCHEMA: Final = "RAOS_FULL_REDESIGN_AUDIT_PACKET_INPUTS_V1"
METADATA_SUFFIX: Final = ".metadata.json"
MEMBERS_SUFFIX: Final = ".members.sha256"
MAX_CONFIG_BYTES: Final = 1_048_576
MAX_CAPTURE_BYTES: Final = 16_777_216
MAX_GIT_OUTPUT_BYTES: Final = 4_194_304
MAX_ARCHIVE_BYTES: Final = 67_108_864
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
TEXT_SUFFIXES: Final = frozenset(
    {
        ".css",
        ".csv",
        ".html",
        ".json",
        ".md",
        ".mjs",
        ".php",
        ".py",
        ".svg",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
        ".xml",
    }
)
SENSITIVE_PATTERNS: Final = (
    re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(rb"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"(?im)^\s*(?:cookie|set-cookie)\s*:\s*(?!<redacted>)[^\r\n]{24,}"),
    re.compile(
        rb"(?im)^\s*authorization\s*:\s*(?:bearer|basic)\s+"
        rb"(?!<redacted>)[A-Za-z0-9+/._=-]{12,}\s*$"
    ),
    re.compile(
        rb"(?i)(?:session[_-]?token|cf_clearance)\s*[=:]\s*(?!<redacted>)[^\s,;]{12,}"
    ),
)
CONFIG_KEYS: Final = frozenset(
    {
        "schema",
        "archive_name",
        "max_member_bytes",
        "max_total_bytes",
        "exact_files",
        "tracked_prefixes",
        "inventory_roots",
        "allowed_extensions",
        "excluded_path_fragments",
        "browser_evidence",
        "public_urls",
    }
)


class PacketError(RuntimeError):
    """A sanitized packet preparation failure."""


def _fail(code: str) -> NoReturn:
    raise PacketError(code)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _load_json_bytes(payload: bytes, code: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail(code)
            result[key] = value
        return result

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail(code)


def _read_regular(path: Path, limit: int, code: str) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _fail(code)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            _fail(code)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > limit:
            _fail(code)
        return payload
    finally:
        os.close(descriptor)


def _safe_relative(value: str, code: str = "PATH_INVALID") -> Path:
    posix = PurePosixPath(value)
    if (
        not value
        or posix.is_absolute()
        or value != posix.as_posix()
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        _fail(code)
    return Path(*posix.parts)


def _safe_member(value: str) -> str:
    relative = _safe_relative(value, "ARCHIVE_MEMBER_INVALID")
    if relative.parts[0] in {".git", ".secrets", "node_modules", ".venv"}:
        _fail("ARCHIVE_MEMBER_FORBIDDEN")
    return relative.as_posix()


def _ensure_no_symlink_ancestors(path: Path, *, stop: Path) -> None:
    resolved_stop = stop.resolve()
    try:
        relative = path.relative_to(resolved_stop)
    except ValueError:
        _fail("PATH_OUTSIDE_ROOT")
    current = resolved_stop
    for part in relative.parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            _fail("PATH_SYMLINK")


def _ensure_private_directory(path: Path) -> None:
    _ensure_no_symlink_ancestors(path, stop=REPOSITORY_ROOT)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("PRIVATE_DIRECTORY_INVALID")


def _atomic_private_write(path: Path, payload: bytes) -> None:
    _ensure_private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("PRIVATE_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _string_list(value: object, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        _fail(code)
    if len(value) != len(set(value)):
        _fail(code)
    return list(value)


def _load_config(path: Path) -> dict[str, Any]:
    value = _load_json_bytes(
        _read_regular(path, MAX_CONFIG_BYTES, "CONFIG_INVALID"), "CONFIG_INVALID"
    )
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        _fail("CONFIG_INVALID")
    if value.get("schema") != CONFIG_SCHEMA:
        _fail("CONFIG_INVALID")
    archive_name = value.get("archive_name")
    if (
        not isinstance(archive_name, str)
        or PurePosixPath(archive_name).name != archive_name
        or not archive_name.endswith(".tar.gz")
    ):
        _fail("CONFIG_INVALID")
    for key in ("max_member_bytes", "max_total_bytes"):
        if not isinstance(value.get(key), int) or value[key] <= 0:
            _fail("CONFIG_INVALID")
    if value["max_total_bytes"] > MAX_ARCHIVE_BYTES:
        _fail("CONFIG_INVALID")
    for key in (
        "exact_files",
        "tracked_prefixes",
        "inventory_roots",
        "allowed_extensions",
        "excluded_path_fragments",
        "browser_evidence",
    ):
        value[key] = _string_list(value.get(key), "CONFIG_INVALID")
    public_urls = value.get("public_urls")
    if not isinstance(public_urls, list) or not public_urls:
        _fail("CONFIG_INVALID")
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for row in public_urls:
        if not isinstance(row, dict) or set(row) != {"id", "url"}:
            _fail("CONFIG_INVALID")
        identifier = row.get("id")
        url = row.get("url")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier)
            or identifier in seen_ids
            or not isinstance(url, str)
            or url in seen_urls
        ):
            _fail("CONFIG_INVALID")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "kurashinoshirube.com"
            or parsed.netloc != "kurashinoshirube.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            _fail("CONFIG_PUBLIC_URL_INVALID")
        seen_ids.add(identifier)
        seen_urls.add(url)
    for raw in (
        value["exact_files"] + value["tracked_prefixes"] + value["inventory_roots"]
    ):
        _safe_relative(raw, "CONFIG_INVALID")
    for name in value["browser_evidence"]:
        if PurePosixPath(name).name != name or not name.endswith(".png"):
            _fail("CONFIG_INVALID")
    return value


def _run_git(arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0 or len(completed.stdout) > MAX_GIT_OUTPUT_BYTES:
        _fail("GIT_STATE_UNAVAILABLE")
    return completed.stdout


def _git_text(arguments: Sequence[str]) -> str:
    try:
        return _run_git(arguments).decode("utf-8")
    except UnicodeDecodeError:
        _fail("GIT_STATE_UNAVAILABLE")


def _tracked_files(prefixes: Sequence[str]) -> set[Path]:
    raw = _run_git(("ls-files", "-z", "--", *prefixes))
    result: set[Path] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            value = item.decode("utf-8")
        except UnicodeDecodeError:
            _fail("GIT_PATH_INVALID")
        result.add(_safe_relative(value, "GIT_PATH_INVALID"))
    return result


def _excluded(relative: Path, fragments: Sequence[str]) -> bool:
    normalized = f"/{relative.as_posix()}/"
    return any(fragment in normalized for fragment in fragments)


def _repository_inputs(config: Mapping[str, Any]) -> tuple[Path, ...]:
    exact = {_safe_relative(value) for value in config["exact_files"]}
    tracked = _tracked_files(config["tracked_prefixes"])
    allowed_extensions = set(config["allowed_extensions"])
    selected = exact | {
        path
        for path in tracked
        if path.suffix.lower() in allowed_extensions
        and not _excluded(path, config["excluded_path_fragments"])
    }
    result: list[Path] = []
    for relative in sorted(selected):
        absolute = REPOSITORY_ROOT / relative
        _ensure_no_symlink_ancestors(absolute, stop=REPOSITORY_ROOT)
        try:
            metadata = absolute.stat()
        except FileNotFoundError:
            _fail("REPOSITORY_INPUT_MISSING")
        if not stat.S_ISREG(metadata.st_mode):
            _fail("REPOSITORY_INPUT_INVALID")
        if metadata.st_size > config["max_member_bytes"]:
            _fail("REPOSITORY_INPUT_TOO_LARGE")
        result.append(relative)
    return tuple(result)


def _scan_sensitive(member: str, payload: bytes) -> None:
    if PurePosixPath(member).suffix.lower() not in TEXT_SUFFIXES:
        return
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(payload):
            _fail("SENSITIVE_CONTENT_DETECTED")


def _repository_payload(config: Mapping[str, Any]) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    for relative in _repository_inputs(config):
        member = f"repository/{relative.as_posix()}"
        value = _read_regular(
            REPOSITORY_ROOT / relative,
            config["max_member_bytes"],
            "REPOSITORY_INPUT_INVALID",
        )
        _scan_sensitive(member, value)
        payload[member] = value
    return payload


def _repository_state(observed_at: str) -> dict[str, Any]:
    top = _git_text(("rev-parse", "--show-toplevel")).strip()
    if Path(top).resolve() != REPOSITORY_ROOT.resolve():
        _fail("GIT_ROOT_INVALID")
    branch = _git_text(("branch", "--show-current")).strip() or "DETACHED"
    return {
        "schema": "RAOS_FULL_REDESIGN_REPOSITORY_STATE_V1",
        "observed_at": observed_at,
        "repository_root": str(REPOSITORY_ROOT),
        "head": _git_text(("rev-parse", "HEAD")).strip(),
        "branch": branch,
        "status_porcelain": _git_text(
            ("status", "--porcelain=v1", "--branch", "--untracked-files=all")
        ),
        "worktree_diffstat": _git_text(("diff", "--stat", "--no-ext-diff")),
        "index_diffstat": _git_text(("diff", "--cached", "--stat", "--no-ext-diff")),
        "recent_history": _git_text(("log", "--oneline", "--decorate", "-20")),
        "evidence_boundary": {
            "repository": "LIVE_WORKTREE_OBSERVATION_NOT_FORMAL_CI",
            "public_site": "SEPARATE_PUBLIC_READ_ONLY_CAPTURE",
            "staging": "NOT_CLAIMED",
            "production_readiness": "NOT_CLAIMED",
        },
    }


def _source_inventory(config: Mapping[str, Any]) -> dict[str, Any]:
    tracked = sorted(_tracked_files(config["inventory_roots"]))
    rows: list[dict[str, Any]] = []
    for relative in tracked:
        absolute = REPOSITORY_ROOT / relative
        _ensure_no_symlink_ancestors(absolute, stop=REPOSITORY_ROOT)
        try:
            metadata = absolute.stat()
        except FileNotFoundError:
            rows.append({"path": relative.as_posix(), "worktree_state": "MISSING"})
            continue
        if not stat.S_ISREG(metadata.st_mode):
            _fail("INVENTORY_PATH_INVALID")
        rows.append(
            {
                "path": relative.as_posix(),
                "bytes": metadata.st_size,
                "suffix": relative.suffix.lower(),
                "worktree_state": "PRESENT",
            }
        )
    return {
        "schema": "RAOS_FULL_REDESIGN_SOURCE_INVENTORY_V1",
        "tracked_files": len(rows),
        "entries": rows,
        "note": "Inventory records paths and sizes only; only allowlisted files are copied.",
    }


def _content_suffix(content_type: str) -> str:
    lowered = content_type.lower()
    if "html" in lowered:
        return ".html"
    if "xml" in lowered:
        return ".xml"
    if "text/plain" in lowered:
        return ".txt"
    return ".bin"


def _capture_public(config: Mapping[str, Any]) -> dict[str, Any]:
    captured_at = _utc_now()
    responses: list[dict[str, Any]] = []
    tls = ssl.create_default_context()
    for row in config["public_urls"]:
        parsed = urlsplit(row["url"])
        path = parsed.path or "/"
        connection = http.client.HTTPSConnection(
            "kurashinoshirube.com", timeout=20, context=tls
        )
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "text/html,application/xml,text/plain;q=0.9,*/*;q=0.1",
                    "User-Agent": "RAOS-Full-Redesign-Audit/1.0",
                },
            )
            response = connection.getresponse()
            body = response.read(config["max_member_bytes"] + 1)
            if len(body) > config["max_member_bytes"]:
                _fail("PUBLIC_CAPTURE_TOO_LARGE")
            content_type = response.getheader("Content-Type", "")
            location = response.getheader("Location")
            responses.append(
                {
                    "id": row["id"],
                    "url": row["url"],
                    "captured_at": captured_at,
                    "status": response.status,
                    "reason": response.reason,
                    "content_type": content_type,
                    "location": location,
                    "body_sha256": _sha256(body),
                    "body_base64": base64.b64encode(body).decode("ascii"),
                }
            )
        except OSError, http.client.HTTPException, ssl.SSLError:
            _fail("PUBLIC_CAPTURE_FAILED")
        finally:
            connection.close()
    capture = {
        "schema": CAPTURE_SCHEMA,
        "captured_at": captured_at,
        "redirects_followed": False,
        "credentials_used": False,
        "cookies_sent": False,
        "responses": responses,
    }
    _atomic_private_write(PUBLIC_CAPTURE_PATH, _json_bytes(capture))
    return capture


def _load_public_capture(config: Mapping[str, Any]) -> dict[str, Any]:
    value = _load_json_bytes(
        _read_regular(PUBLIC_CAPTURE_PATH, MAX_CAPTURE_BYTES, "PUBLIC_CAPTURE_MISSING"),
        "PUBLIC_CAPTURE_INVALID",
    )
    if not isinstance(value, dict) or value.get("schema") != CAPTURE_SCHEMA:
        _fail("PUBLIC_CAPTURE_INVALID")
    responses = value.get("responses")
    if not isinstance(responses, list) or len(responses) != len(config["public_urls"]):
        _fail("PUBLIC_CAPTURE_INVALID")
    expected = {(row["id"], row["url"]) for row in config["public_urls"]}
    observed: set[tuple[str, str]] = set()
    for row in responses:
        if not isinstance(row, dict):
            _fail("PUBLIC_CAPTURE_INVALID")
        identifier = row.get("id")
        url = row.get("url")
        if not isinstance(identifier, str) or not isinstance(url, str):
            _fail("PUBLIC_CAPTURE_INVALID")
        observed.add((identifier, url))
        body_value = row.get("body_base64")
        if not isinstance(body_value, str):
            _fail("PUBLIC_CAPTURE_INVALID")
        try:
            body = base64.b64decode(body_value, validate=True)
        except ValueError:
            _fail("PUBLIC_CAPTURE_INVALID")
        if len(body) > config["max_member_bytes"] or row.get("body_sha256") != _sha256(
            body
        ):
            _fail("PUBLIC_CAPTURE_INVALID")
        if not isinstance(row.get("status"), int) or not isinstance(
            row.get("content_type"), str
        ):
            _fail("PUBLIC_CAPTURE_INVALID")
    if observed != expected:
        _fail("PUBLIC_CAPTURE_INVALID")
    return value


def _public_payload(capture: Mapping[str, Any]) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    index_rows: list[dict[str, Any]] = []
    for row in capture["responses"]:
        body = base64.b64decode(row["body_base64"], validate=True)
        suffix = _content_suffix(row["content_type"])
        member = f"public/{row['id']}{suffix}"
        _scan_sensitive(member, body)
        payload[member] = body
        index_rows.append(
            {
                key: row[key]
                for key in (
                    "id",
                    "url",
                    "captured_at",
                    "status",
                    "reason",
                    "content_type",
                    "location",
                    "body_sha256",
                )
            }
        )
    payload["public/index.json"] = _json_bytes(
        {
            "schema": "RAOS_FULL_REDESIGN_PUBLIC_INDEX_V1",
            "redirects_followed": False,
            "credentials_used": False,
            "responses": index_rows,
        }
    )
    return payload


def _browser_payload(config: Mapping[str, Any]) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    for name in config["browser_evidence"]:
        path = BROWSER_EVIDENCE_ROOT / name
        _ensure_no_symlink_ancestors(path, stop=REPOSITORY_ROOT)
        value = _read_regular(
            path, config["max_member_bytes"], "BROWSER_EVIDENCE_MISSING"
        )
        if not value.startswith(PNG_SIGNATURE):
            _fail("BROWSER_EVIDENCE_INVALID")
        member = f"browser/{name}"
        payload[member] = value
        rows.append({"member": member, "bytes": len(value), "sha256": _sha256(value)})
    payload["browser/index.json"] = _json_bytes(
        {
            "schema": "RAOS_FULL_REDESIGN_BROWSER_EVIDENCE_V1",
            "capture_mode": "PUBLIC_READ_ONLY_PLAYWRIGHT",
            "production_readiness": "NOT_CLAIMED",
            "entries": rows,
        }
    )
    return payload


def _packet_readme() -> bytes:
    return (
        "# RAOS full-redesign audit packet v1\n\n"
        "This is a time-bounded, read-only evidence packet for ChatGPT Pro design work.\n"
        "It is not implementation authority, approval, formal CI, staging, release, or\n"
        "Production evidence. Repository files are under `repository/`; Git and source\n"
        "inventories are under `context/`; public HTTP captures are under `public/`; and\n"
        "browser captures are under `browser/`. Verify `MANIFEST.sha256` before use.\n"
    ).encode("utf-8")


def _manifest_bytes(payload: Mapping[str, bytes]) -> bytes:
    return "".join(
        f"{_sha256(value)}  {member}\n" for member, value in sorted(payload.items())
    ).encode("utf-8")


def _archive_bytes(payload: Mapping[str, bytes]) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(
        fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT
    ) as archive:
        for member, value in sorted(payload.items()):
            safe_member = _safe_member(member)
            info = tarfile.TarInfo(safe_member)
            info.size = len(value)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(value))
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="", mode="wb", fileobj=compressed, compresslevel=9, mtime=0
    ) as output:
        output.write(tar_buffer.getvalue())
    return compressed.getvalue()


def _compose_payload(
    config: Mapping[str, Any], capture: Mapping[str, Any]
) -> dict[str, bytes]:
    assembled_at = capture.get("captured_at")
    if not isinstance(assembled_at, str) or not assembled_at:
        _fail("PUBLIC_CAPTURE_INVALID")
    payload = _repository_payload(config)
    payload.update(_public_payload(capture))
    payload.update(_browser_payload(config))
    repository_state = _repository_state(assembled_at)
    payload["context/repository-state.json"] = _json_bytes(repository_state)
    payload["context/source-inventory.json"] = _json_bytes(_source_inventory(config))
    payload["README.md"] = _packet_readme()
    payload["PACKET-METADATA.json"] = _json_bytes(
        {
            "schema": PACKET_SCHEMA,
            "assembled_at": assembled_at,
            "repository_head": repository_state["head"],
            "repository_branch": repository_state["branch"],
            "canonical_mutated": False,
            "private_general_scan_performed": False,
            "private_inputs": [
                "four exact public screenshots",
                "one exact public-capture document",
            ],
            "credentials_used": False,
            "external_writes": False,
            "pro_submission": "NOT_PERFORMED_BY_PACKET_BUILDER",
            "authority": "UNAPPROVED_DESIGN_INPUT_ONLY",
            "payload_members_before_manifest": len(payload),
        }
    )
    for member, value in payload.items():
        _safe_member(member)
        if len(value) > config["max_member_bytes"]:
            _fail("PACKET_MEMBER_TOO_LARGE")
        _scan_sensitive(member, value)
    payload["MANIFEST.sha256"] = _manifest_bytes(payload)
    total = sum(len(value) for value in payload.values())
    if total > config["max_total_bytes"]:
        _fail("PACKET_TOO_LARGE")
    return payload


def _parse_manifest(value: bytes) -> dict[str, str]:
    try:
        lines = value.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        _fail("MANIFEST_INVALID")
    result: dict[str, str] = {}
    for line in lines:
        if not re.fullmatch(r"[0-9a-f]{64}  .+", line):
            _fail("MANIFEST_INVALID")
        digest, member = line.split("  ", 1)
        safe_member = _safe_member(member)
        if safe_member in result:
            _fail("MANIFEST_INVALID")
        result[safe_member] = digest
    if not result:
        _fail("MANIFEST_INVALID")
    return result


def _read_archive(path: Path, config: Mapping[str, Any]) -> dict[str, bytes]:
    archive_bytes = _read_regular(path, MAX_ARCHIVE_BYTES, "ARCHIVE_MISSING")
    result: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for info in archive:
                member = _safe_member(info.name)
                if (
                    member in result
                    or not info.isreg()
                    or info.size > config["max_member_bytes"]
                ):
                    _fail("ARCHIVE_MEMBER_INVALID")
                extracted = archive.extractfile(info)
                if extracted is None:
                    _fail("ARCHIVE_MEMBER_INVALID")
                value = extracted.read(config["max_member_bytes"] + 1)
                if len(value) != info.size or len(value) > config["max_member_bytes"]:
                    _fail("ARCHIVE_MEMBER_INVALID")
                result[member] = value
    except tarfile.TarError, OSError, EOFError:
        _fail("ARCHIVE_INVALID")
    if sum(len(value) for value in result.values()) > config["max_total_bytes"]:
        _fail("ARCHIVE_INVALID")
    return result


def _validate_archive(
    archive_path: Path,
    config: Mapping[str, Any],
    *,
    compare_current_inputs: bool,
) -> dict[str, Any]:
    payload = _read_archive(archive_path, config)
    manifest_value = payload.get("MANIFEST.sha256")
    if manifest_value is None:
        _fail("MANIFEST_MISSING")
    manifest = _parse_manifest(manifest_value)
    if set(manifest) != set(payload) - {"MANIFEST.sha256"}:
        _fail("MANIFEST_CLOSURE_INVALID")
    for member, digest in manifest.items():
        if _sha256(payload[member]) != digest:
            _fail("MANIFEST_HASH_INVALID")
        _scan_sensitive(member, payload[member])
    metadata = _load_json_bytes(
        payload.get("PACKET-METADATA.json", b""), "PACKET_METADATA_INVALID"
    )
    if not isinstance(metadata, dict) or metadata.get("schema") != PACKET_SCHEMA:
        _fail("PACKET_METADATA_INVALID")
    if "repository/changes/full-redesign-v2/PRO_FULL_REDESIGN_PROMPT.md" not in payload:
        _fail("PROMPT_MISSING")
    public_index = _load_json_bytes(
        payload.get("public/index.json", b""), "PUBLIC_INDEX_INVALID"
    )
    if not isinstance(public_index, dict) or len(
        public_index.get("responses", [])
    ) != len(config["public_urls"]):
        _fail("PUBLIC_INDEX_INVALID")
    expected_browser = {f"browser/{name}" for name in config["browser_evidence"]}
    if not expected_browser.issubset(payload):
        _fail("BROWSER_EVIDENCE_MISSING")
    if compare_current_inputs:
        expected_repo = {
            f"repository/{relative.as_posix()}"
            for relative in _repository_inputs(config)
        }
        observed_repo = {
            member for member in payload if member.startswith("repository/")
        }
        if expected_repo != observed_repo:
            _fail("REPOSITORY_INPUT_CLOSURE_DRIFT")
        for member in expected_repo:
            relative = Path(*PurePosixPath(member).parts[1:])
            current = _read_regular(
                REPOSITORY_ROOT / relative,
                config["max_member_bytes"],
                "REPOSITORY_INPUT_INVALID",
            )
            if current != payload[member]:
                _fail("REPOSITORY_INPUT_DRIFT")
        for name in config["browser_evidence"]:
            current = _read_regular(
                BROWSER_EVIDENCE_ROOT / name,
                config["max_member_bytes"],
                "BROWSER_EVIDENCE_MISSING",
            )
            if current != payload[f"browser/{name}"]:
                _fail("BROWSER_EVIDENCE_DRIFT")
    members_path = archive_path.with_name(archive_path.name + MEMBERS_SUFFIX)
    if (
        _read_regular(members_path, MAX_CAPTURE_BYTES, "COMPANION_MANIFEST_MISSING")
        != manifest_value
    ):
        _fail("COMPANION_MANIFEST_INVALID")
    companion_path = archive_path.with_name(archive_path.name + METADATA_SUFFIX)
    companion = _load_json_bytes(
        _read_regular(companion_path, MAX_CONFIG_BYTES, "COMPANION_METADATA_MISSING"),
        "COMPANION_METADATA_INVALID",
    )
    archive_bytes = _read_regular(archive_path, MAX_ARCHIVE_BYTES, "ARCHIVE_MISSING")
    if (
        not isinstance(companion, dict)
        or companion.get("schema") != "RAOS_FULL_REDESIGN_AUDIT_PACKET_COMPANION_V1"
        or companion.get("archive_sha256") != _sha256(archive_bytes)
        or companion.get("archive_bytes") != len(archive_bytes)
        or companion.get("members") != len(payload)
    ):
        _fail("COMPANION_METADATA_INVALID")
    return {
        "status": "PASS",
        "archive": str(archive_path),
        "archive_sha256": _sha256(archive_bytes),
        "archive_bytes": len(archive_bytes),
        "members": len(payload),
        "repository_inputs_compared": compare_current_inputs,
        "network_used": False,
        "authority": "UNAPPROVED_DESIGN_INPUT_ONLY",
    }


def _build(config: Mapping[str, Any], *, capture_public: bool) -> dict[str, Any]:
    _ensure_private_directory(PRIVATE_ROOT)
    _ensure_private_directory(BROWSER_EVIDENCE_ROOT)
    capture = (
        _capture_public(config) if capture_public else _load_public_capture(config)
    )
    payload = _compose_payload(config, capture)
    archive = _archive_bytes(payload)
    if len(archive) > config["max_total_bytes"]:
        _fail("ARCHIVE_TOO_LARGE")
    archive_path = PRIVATE_ROOT / config["archive_name"]
    _atomic_private_write(archive_path, archive)
    manifest = payload["MANIFEST.sha256"]
    _atomic_private_write(
        archive_path.with_name(archive_path.name + MEMBERS_SUFFIX), manifest
    )
    _atomic_private_write(
        archive_path.with_name(archive_path.name + METADATA_SUFFIX),
        _json_bytes(
            {
                "schema": "RAOS_FULL_REDESIGN_AUDIT_PACKET_COMPANION_V1",
                "archive": archive_path.name,
                "archive_sha256": _sha256(archive),
                "archive_bytes": len(archive),
                "members": len(payload),
                "authority": "UNAPPROVED_DESIGN_INPUT_ONLY",
            }
        ),
    )
    result = _validate_archive(archive_path, config, compare_current_inputs=True)
    result["network_used"] = capture_public
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--capture-public", action="store_true")
    check = subparsers.add_parser("check")
    check.add_argument(
        "--skip-current-input-comparison",
        action="store_true",
        help="validate an older packet without claiming current worktree parity",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        config = _load_config(arguments.config.resolve())
        if arguments.command == "build":
            result = _build(config, capture_public=arguments.capture_public)
        else:
            archive_path = PRIVATE_ROOT / config["archive_name"]
            result = _validate_archive(
                archive_path,
                config,
                compare_current_inputs=not arguments.skip_current_input_comparison,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except PacketError as error:
        print(f"RAOS_FULL_REDESIGN_PACKET_ERROR {error}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
