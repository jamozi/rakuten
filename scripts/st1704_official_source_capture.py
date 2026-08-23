#!/usr/bin/env python3
"""Manifest-bound official-source capture CLI for the ST-1704 pilot."""

from __future__ import annotations

import argparse
from collections.abc import Container
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import types
from typing import Callable, Final, NoReturn, Protocol, TextIO, cast


SOURCE_CLI_PATH: Final = Path(os.path.abspath(__file__))
REPOSITORY_ROOT: Final = SOURCE_CLI_PATH.parent.parent
OWNER_PYTHON: Final = (REPOSITORY_ROOT / ".venv/bin/python").as_posix()
MANIFEST_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
)
PREDECESSOR_RELATIVE: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
BOOTSTRAP_RELATIVE: Final = "scripts/st1704_official_source_capture.py"
MAX_MANIFEST_BYTES: Final = 256 * 1024
MAX_RUNTIME_BYTES: Final = 4 * 1024 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT_OBJECT_ID: Final = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
SOURCE_REFS: Final = (
    "SRC-ACE-CRESTA-06316",
    "SRC-ACE-DIFFERENCE-05721",
    "SRC-ACE-MAXPASS4-01471",
    "SRC-ANA-CARRY-ON-BAGGAGE",
    "SRC-ANKER-SOLIX-C300",
    "SRC-JACKERY-500-NEW",
    "SRC-BLUETTI-AC70",
    "SRC-ECOFLOW-DELTA3-CLASSIC",
    "SRC-PANASONIC-NP-TMLK1",
    "SRC-THANKO-RAKUA-MINI-PLUS",
    "SRC-SIROCA-SS-MA251",
    "SRC-PANASONIC-NP-TSP1",
    "SRC-ANKER-SOLIX-C800-PLUS",
    "SRC-ANKER-SOLIX-C1000",
    "SRC-ANKER-SOLIX-C1000-GEN2",
    "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
    "SRC-SWITCHBOT-K11-PRO",
    "SRC-SWITCHBOT-K10-PRO-COMBO",
    "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
    "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
    "SRC-CAA-STEALTH-MARKETING-QA",
    "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
)

EXPECTED_RUNTIME_PATHS: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/self-hosted-editorial-pilot-v1/EDITORIAL_RESEARCH_NOTES.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/Makefile",
    "changes/st-1704/self-hosted-editorial-pilot-v1/OPERATIONS_RUNBOOK.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/PREFLIGHT.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/README.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-locator-contract.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/article-suitcase-guide.webp",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/brand-mark.svg",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-hero.webp",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/parts/footer.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/parts/header.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/raos-assets.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/style.css",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/front-page.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/single.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme-contract.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/yoast-seo-28.3.lock.json",
    "python/raos/adapters/self_hosted_editorial_pilot_https.py",
    "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    "python/raos/adapters/self_hosted_editorial_source_capture.py",
    "python/raos/application/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/editorial/content_ast.py",
    "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    "python/raos/ports/self_hosted_editorial_pilot.py",
    "scripts/build_st1704_self_hosted_editorial_manifest.py",
    "scripts/build_st1704_self_hosted_theme.py",
    BOOTSTRAP_RELATIVE,
    "scripts/st1704_self_hosted_editorial_pilot.py",
)
_MODULE_PATHS: Final = (
    (
        "raos.domain.editorial.self_hosted_editorial_pilot",
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.ports.self_hosted_editorial_pilot",
        "python/raos/ports/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_pilot_json",
        "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_source_capture",
        "python/raos/adapters/self_hosted_editorial_source_capture.py",
    ),
)
_PACKAGE_NAMES: Final = (
    "raos",
    "raos.domain",
    "raos.domain.editorial",
    "raos.ports",
    "raos.adapters",
)
_TRACKED_SOURCE_PATHS: Final = frozenset(
    {
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-locator-contract.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    }
)
_CAPTURE_FAILURE_CODES: Final = frozenset(
    {
        "ARTICLE_NOT_ALLOWLISTED",
        "BODY_TOO_LARGE",
        "CONNECTION_FAILED",
        "CONTRACT_INVALID",
        "DNS_ADDRESS_REJECTED",
        "DNS_FAILED",
        "HTML_INVALID",
        "INVALID_ARGUMENT",
        "LOCATOR_MISMATCH",
        "LOCATORS_PENDING",
        "MIME_INVALID",
        "NETWORK_ENVIRONMENT_UNSAFE",
        "REQUEST_AMBIGUOUS",
        "RESPONSE_INVALID",
        "SOURCE_NOT_ALLOWLISTED",
        "STORE_CONFLICT",
        "STORE_UNSAFE",
        "TLS_CONTEXT_INVALID",
    }
)
RootIdentity = tuple[int, int]


class _CaptureResult(Protocol):
    body_sha256: str
    credentials_used: bool
    production_evidence: bool
    publication_authority: bool
    request_count: int
    response_sha256: str
    retrieved_at: str
    source_ref: str
    status: str


class _RuntimeFailure(RuntimeError):
    """Sanitized stage-zero integrity refusal."""


class _CommandFailure(RuntimeError):
    """Sanitized verified-runtime refusal."""


def _fail_runtime() -> NoReturn:
    raise _RuntimeFailure("OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID") from None


def _canonical_manifest(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail_runtime()


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail_runtime()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail_runtime()


def _parse_integer(value: str) -> int:
    if not 1 <= len(value) <= 20:
        _fail_runtime()
    try:
        return int(value)
    except ValueError:
        _fail_runtime()


def _decode_json(raw: bytes) -> dict[str, object]:
    if not raw or raw.startswith(b"\xef\xbb\xbf"):
        _fail_runtime()
    try:
        decoded = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_int=_parse_integer,
            parse_constant=_reject_number,
        )
    except _RuntimeFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail_runtime()
    if type(decoded) is not dict:
        _fail_runtime()
    return cast(dict[str, object], decoded)


def _relative_parts(relative: str) -> tuple[str, ...]:
    if type(relative) is not str or not relative or relative != relative.strip():
        _fail_runtime()
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail_runtime()
    return path.parts


def _safe_directory(fd: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        _fail_runtime()
    return observed


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail_runtime()
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        _safe_directory(current)
        return current
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    current = -1
    try:
        current = os.dup(root_fd)
        for part in parts[:-1]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            _safe_directory(following)
            os.close(current)
            current = following
        return current, parts[-1]
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _safe_file(fd: int, *, maximum: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) & 0o022
        or not 0 < observed.st_size <= maximum
    ):
        _fail_runtime()
    return observed


def _read_relative(root_fd: int, relative: str, *, maximum: int) -> bytes:
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail_runtime()
        try:
            before = _safe_file(descriptor, maximum=maximum)
            remaining = before.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    _fail_runtime()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail_runtime()
            after = _safe_file(descriptor, maximum=maximum)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                _fail_runtime()
            try:
                rebound_fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
            except OSError:
                _fail_runtime()
            try:
                rebound = _safe_file(rebound_fd, maximum=maximum)
                if (before.st_dev, before.st_ino) != (
                    rebound.st_dev,
                    rebound.st_ino,
                ):
                    _fail_runtime()
            finally:
                os.close(rebound_fd)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _rebind_root(root: Path, identity: RootIdentity) -> None:
    descriptor = _open_absolute_directory(root)
    try:
        observed = _safe_directory(descriptor)
        if (observed.st_dev, observed.st_ino) != identity:
            _fail_runtime()
    finally:
        os.close(descriptor)


def _verify_stage_zero() -> None:
    flags = sys.flags
    try:
        current_directory = os.getcwd()
    except OSError:
        _fail_runtime()
    if (
        SOURCE_CLI_PATH != REPOSITORY_ROOT / BOOTSTRAP_RELATIVE
        or sys.executable != OWNER_PYTHON
        or sys.version_info[:3] != (3, 14, 6)
        or flags.dont_write_bytecode != 1
        or flags.ignore_environment != 1
        or flags.isolated != 1
        or flags.no_site != 1
        or flags.no_user_site != 1
        or not flags.safe_path
        or current_directory != REPOSITORY_ROOT.as_posix()
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(REPOSITORY_ROOT)
    try:
        root = _safe_directory(root_fd)
        try:
            cwd_fd = os.open(".", _DIRECTORY_FLAGS)
        except OSError:
            _fail_runtime()
        try:
            cwd = _safe_directory(cwd_fd)
            if (root.st_dev, root.st_ino) != (cwd.st_dev, cwd.st_ino):
                _fail_runtime()
        finally:
            os.close(cwd_fd)
    finally:
        os.close(root_fd)


def _git(root: Path, *arguments: str, maximum_stdout: int = MAX_RUNTIME_BYTES) -> bytes:
    if type(maximum_stdout) is not int or not 1 <= maximum_stdout <= MAX_RUNTIME_BYTES:
        _fail_runtime()
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-optional-locks", "-C", root.as_posix(), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_GIT_ENVIRONMENT,
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        _fail_runtime()
    if (
        completed.returncode != 0
        or type(completed.stdout) is not bytes
        or len(completed.stdout) > maximum_stdout
    ):
        _fail_runtime()
    return completed.stdout


def _require_git_root(root: Path) -> None:
    expected = os.fsencode(root.as_posix()) + b"\n"
    if (
        _git(
            root,
            "rev-parse",
            "--show-toplevel",
            maximum_stdout=max(128, len(expected)),
        )
        != expected
    ):
        _fail_runtime()


def _committed_blob(
    root: Path,
    *,
    head: str,
    relative: str,
    maximum: int,
) -> bytes:
    if (
        _GIT_OBJECT_ID.fullmatch(head) is None
        or type(maximum) is not int
        or not 1 <= maximum <= MAX_RUNTIME_BYTES
    ):
        _fail_runtime()
    _relative_parts(relative)
    object_spec = f"{head}:{relative}"
    raw_size = _git(root, "cat-file", "-s", object_spec, maximum_stdout=128)
    try:
        size_text = raw_size.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _fail_runtime()
    if str(size) != size_text or not 0 < size <= maximum:
        _fail_runtime()
    blob = _git(root, "cat-file", "blob", object_spec, maximum_stdout=size)
    if len(blob) != size:
        _fail_runtime()
    return blob


def _committed_manifest(root: Path) -> tuple[bytes, str]:
    _require_git_root(root)
    raw_object_id = _git(
        root, "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128
    )
    try:
        object_id = raw_object_id.decode("ascii", errors="strict").strip()
    except UnicodeError:
        _fail_runtime()
    if _GIT_OBJECT_ID.fullmatch(object_id) is None:
        _fail_runtime()
    manifest = _committed_blob(
        root,
        head=object_id,
        relative=MANIFEST_RELATIVE,
        maximum=MAX_MANIFEST_BYTES,
    )
    return manifest, object_id


def _require_same_head(root: Path, expected: str) -> None:
    observed_raw = _git(
        root, "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128
    )
    try:
        observed = observed_raw.decode("ascii", errors="strict").strip()
    except UnicodeError:
        _fail_runtime()
    if observed != expected:
        _fail_runtime()


def _validate_predecessor(raw: bytes) -> None:
    predecessor = _decode_json(raw)
    if raw != _canonical_manifest(predecessor) or set(predecessor) != {
        "approved_base_commit",
        "external_action_authority",
        "generated_by",
        "paths",
        "repository_development_authority",
        "schema",
        "slice_id",
        "story_id",
    }:
        _fail_runtime()
    if (
        predecessor["approved_base_commit"]
        != "b5a6157b878ca0435ee4120d33162aba5ae51f77"
        or predecessor["external_action_authority"] != "NONE"
        or predecessor["generated_by"]
        != "scripts/build_st1703_self_hosted_runtime_manifest.py"
        or predecessor["repository_development_authority"]
        != "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"
        or predecessor["schema"] != "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1"
        or predecessor["slice_id"] != "SELF_HOSTED_MINIMUM_START_V1"
        or predecessor["story_id"] != "ST-1703"
        or type(predecessor["paths"]) is not list
        or not predecessor["paths"]
    ):
        _fail_runtime()


def _contains_exact(values: Container[str], expected: str) -> bool:
    return expected in values


def _verify_runtime_integrity(
    root: object,
) -> tuple[dict[str, bytes], RootIdentity]:
    """Verify the closed tree before importing any RAOS runtime module."""

    runtime_paths = set(EXPECTED_RUNTIME_PATHS)
    if (
        not isinstance(root, Path)
        or not root.is_absolute()
        or tuple(sorted(EXPECTED_RUNTIME_PATHS)) != EXPECTED_RUNTIME_PATHS
        or len(runtime_paths) != len(EXPECTED_RUNTIME_PATHS)
        or _contains_exact(runtime_paths, MANIFEST_RELATIVE)
        or not _contains_exact(runtime_paths, BOOTSTRAP_RELATIVE)
        or not _TRACKED_SOURCE_PATHS < runtime_paths
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(root)
    try:
        verified_root = _safe_directory(root_fd)
        manifest_raw = _read_relative(
            root_fd, MANIFEST_RELATIVE, maximum=MAX_MANIFEST_BYTES
        )
        committed_manifest, committed_head = _committed_manifest(root)
        if manifest_raw != committed_manifest:
            _fail_runtime()
        manifest = _decode_json(manifest_raw)
        if manifest_raw != _canonical_manifest(manifest) or set(manifest) != {
            "approved_base_commit",
            "article_ids",
            "external_action_authority",
            "generated_by",
            "paths",
            "predecessor",
            "publication_authority",
            "repository_development_authority",
            "schema",
            "slice_id",
            "story_id",
        }:
            _fail_runtime()
        if (
            manifest["approved_base_commit"]
            != "ca271187c4c8606487193110b29597a40e4c1c9f"
            or manifest["article_ids"] != list(ARTICLE_IDS)
            or manifest["external_action_authority"] != "NONE"
            or manifest["generated_by"]
            != "scripts/build_st1704_self_hosted_editorial_manifest.py"
            or manifest["publication_authority"] != "NONE"
            or manifest["repository_development_authority"]
            != "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"
            or manifest["schema"] != "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
            or manifest["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
            or manifest["story_id"] != "ST-1704"
        ):
            _fail_runtime()
        predecessor_value = manifest["predecessor"]
        if type(predecessor_value) is not dict:
            _fail_runtime()
        predecessor = cast(dict[str, object], predecessor_value)
        if set(predecessor) != {"path", "sha256"}:
            _fail_runtime()
        predecessor_sha256 = predecessor["sha256"]
        if (
            predecessor["path"] != PREDECESSOR_RELATIVE
            or type(predecessor_sha256) is not str
            or _SHA256.fullmatch(predecessor_sha256) is None
        ):
            _fail_runtime()
        entries_value = manifest["paths"]
        if type(entries_value) is not list:
            _fail_runtime()
        entries = cast(list[object], entries_value)
        if len(entries) != len(EXPECTED_RUNTIME_PATHS):
            _fail_runtime()
        sources: dict[str, bytes] = {}
        for expected_path, entry_value in zip(
            EXPECTED_RUNTIME_PATHS, entries, strict=True
        ):
            if type(entry_value) is not dict:
                _fail_runtime()
            entry = cast(dict[str, object], entry_value)
            if set(entry) != {"bytes", "path", "sha256"}:
                _fail_runtime()
            byte_count = entry["bytes"]
            sha256 = entry["sha256"]
            if (
                entry["path"] != expected_path
                or type(byte_count) is not int
                or not 0 < byte_count <= MAX_RUNTIME_BYTES
                or type(sha256) is not str
                or _SHA256.fullmatch(sha256) is None
            ):
                _fail_runtime()
            raw = _read_relative(root_fd, expected_path, maximum=MAX_RUNTIME_BYTES)
            committed_raw = _committed_blob(
                root,
                head=committed_head,
                relative=expected_path,
                maximum=MAX_RUNTIME_BYTES,
            )
            if (
                raw != committed_raw
                or len(raw) != byte_count
                or hashlib.sha256(raw).hexdigest() != sha256
            ):
                _fail_runtime()
            sources[expected_path] = raw
        predecessor_raw = _read_relative(
            root_fd, PREDECESSOR_RELATIVE, maximum=MAX_MANIFEST_BYTES
        )
        committed_predecessor = _committed_blob(
            root,
            head=committed_head,
            relative=PREDECESSOR_RELATIVE,
            maximum=MAX_MANIFEST_BYTES,
        )
        if (
            predecessor_raw != committed_predecessor
            or hashlib.sha256(predecessor_raw).hexdigest() != predecessor_sha256
        ):
            _fail_runtime()
        _validate_predecessor(predecessor_raw)
        _require_same_head(root, committed_head)
        rebound = _open_absolute_directory(root)
        try:
            final_root = _safe_directory(rebound)
            if (verified_root.st_dev, verified_root.st_ino) != (
                final_root.st_dev,
                final_root.st_ino,
            ):
                _fail_runtime()
        finally:
            os.close(rebound)
        return sources, (final_root.st_dev, final_root.st_ino)
    except _RuntimeFailure:
        raise
    except Exception:
        _fail_runtime()
    finally:
        os.close(root_fd)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    setattr(module, "__path__", [])
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
    return module


def _load_verified_modules(sources: dict[str, bytes]) -> dict[str, types.ModuleType]:
    runtime_names = {*_PACKAGE_NAMES, *(name for name, _path in _MODULE_PATHS)}
    if runtime_names & set(sys.modules):
        _fail_runtime()
    for name in _PACKAGE_NAMES:
        _package(name)
    loaded: dict[str, types.ModuleType] = {}
    for module_name, relative in _MODULE_PATHS:
        raw = sources.get(relative)
        if type(raw) is not bytes:
            _fail_runtime()
        module = types.ModuleType(module_name)
        module.__file__ = (REPOSITORY_ROOT / relative).as_posix()
        module.__package__ = module_name.rsplit(".", 1)[0]
        sys.modules[module_name] = module
        parent_name, child_name = module_name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
        try:
            code = compile(raw, module.__file__, "exec", dont_inherit=True)
            exec(code, module.__dict__)
        except BaseException:
            _fail_runtime()
        loaded[module_name] = module
    return loaded


def _bind_verified_source_documents(
    module: types.ModuleType,
    sources: dict[str, bytes],
    root_identity: RootIdentity,
) -> None:
    verified = {relative: sources[relative] for relative in _TRACKED_SOURCE_PATHS}
    source_directory_value = getattr(module, "_source_directory", None)
    if not callable(source_directory_value):
        _fail_runtime()
    source_directory = cast(Callable[[Path], object], source_directory_value)

    def read_tracked_file(
        repository_root: object, relative: object, maximum: object
    ) -> bytes:
        if (
            not isinstance(repository_root, Path)
            or repository_root != REPOSITORY_ROOT
            or not isinstance(relative, Path)
            or type(maximum) is not int
            or maximum <= 0
        ):
            _fail_runtime()
        key = relative.as_posix()
        raw = verified.get(key)
        if raw is None or len(raw) > maximum:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, root_identity)
        return raw

    def checked_source_directory(repository_root: object) -> Path:
        if not isinstance(repository_root, Path) or repository_root != REPOSITORY_ROOT:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, root_identity)
        result = source_directory(repository_root)
        if not isinstance(result, Path):
            _fail_runtime()
        return result

    setattr(module, "_read_tracked_file", read_tracked_file)
    setattr(module, "_source_directory", checked_source_directory)


def _write_json(value: object, *, target: TextIO | None = None) -> None:
    destination = sys.stdout if target is None else target
    if destination is None:
        _fail_runtime()
    destination.write(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="st1704_official_source_capture.py",
        description=(
            "Capture exact allowlisted official HTML sources with read-only HTTPS. "
            "There is no caller URL, credential, WordPress, Rakuten API, product "
            "retrieval, publication, plugin, theme, or generic HTTP capability."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("capture-source", allow_abbrev=False)
    source.add_argument("--source-ref", choices=SOURCE_REFS, required=True)
    article = commands.add_parser("capture-article", allow_abbrev=False)
    article.add_argument("--article-id", choices=ARTICLE_IDS, required=True)
    return parser


def _execute(
    command: str,
    *,
    source_ref: str | None,
    article_id: str | None,
    sources: dict[str, bytes],
    root_identity: RootIdentity,
) -> dict[str, object]:
    if (
        type(root_identity) is not tuple
        or len(root_identity) != 2
        or any(type(value) is not int or value < 0 for value in root_identity)
    ):
        _fail_runtime()
    _rebind_root(REPOSITORY_ROOT, root_identity)
    modules = _load_verified_modules(sources)
    capture = modules["raos.adapters.self_hosted_editorial_source_capture"]
    _bind_verified_source_documents(capture, sources, root_identity)
    capture_source_ref = getattr(capture, "capture_source_ref", None)
    capture_article_sources = getattr(capture, "capture_article_sources", None)
    failure_type = getattr(capture, "OfficialSourceCaptureFailure", None)
    result_type = getattr(capture, "SourceCaptureResult", None)
    if (
        not callable(capture_source_ref)
        or not callable(capture_article_sources)
        or not isinstance(failure_type, type)
        or not isinstance(result_type, type)
    ):
        _fail_runtime()
    results_value: object
    try:
        if (
            command == "capture-source"
            and source_ref in SOURCE_REFS
            and article_id is None
        ):
            results_value = capture_source_ref(
                REPOSITORY_ROOT,
                source_ref=source_ref,
                clock=lambda: datetime.now(timezone.utc),
            )
        elif (
            command == "capture-article"
            and article_id in ARTICLE_IDS
            and source_ref is None
        ):
            results_value = capture_article_sources(
                REPOSITORY_ROOT,
                article_id=article_id,
                clock=lambda: datetime.now(timezone.utc),
            )
        else:
            _fail_runtime()
    except _RuntimeFailure:
        raise
    except Exception as error:
        if type(error) is failure_type:
            code = getattr(getattr(error, "code", None), "value", None)
            if type(code) is str and code in _CAPTURE_FAILURE_CODES:
                raise _CommandFailure(code) from None
        raise
    if type(results_value) is not tuple:
        _fail_runtime()
    results = cast(tuple[object, ...], results_value)
    documents: list[dict[str, object]] = []
    for value in results:
        if type(value) is not result_type:
            _fail_runtime()
        result = cast(_CaptureResult, value)
        if (
            type(result.body_sha256) is not str
            or _SHA256.fullmatch(result.body_sha256) is None
            or result.credentials_used is not False
            or result.production_evidence is not False
            or result.publication_authority is not False
            or type(result.request_count) is not int
            or result.request_count != 1
            or type(result.response_sha256) is not str
            or _SHA256.fullmatch(result.response_sha256) is None
            or type(result.retrieved_at) is not str
            or not result.retrieved_at
            or type(result.source_ref) is not str
            or result.source_ref not in SOURCE_REFS
            or type(result.status) is not str
            or result.status
            not in {
                "BODY_CAPTURED_LOCATORS_PENDING",
                "CAPTURED_WITH_VERIFIED_LOCATORS",
            }
        ):
            _fail_runtime()
        documents.append(
            {
                "body_sha256": result.body_sha256,
                "request_count": result.request_count,
                "response_sha256": result.response_sha256,
                "retrieved_at": result.retrieved_at,
                "source_ref": result.source_ref,
                "status": result.status,
            }
        )
    return {
        "article_id": article_id,
        "command": command,
        "credentials_used": False,
        "network_requests": len(results),
        "production_evidence": False,
        "publication_authority": False,
        "results": documents,
        "source_ref": source_ref,
        "status": "CAPTURE_COMPLETED",
    }


def _refusal(
    arguments: argparse.Namespace, code: str, *, target: TextIO | None = None
) -> None:
    if target is None:
        target = sys.stderr
    _write_json(
        {
            "article_id": getattr(arguments, "article_id", None),
            "command": arguments.command,
            "credentials_used": False,
            "error": code,
            "production_evidence": False,
            "publication_authority": False,
            "source_ref": getattr(arguments, "source_ref", None),
            "status": "REFUSED",
        },
        target=target,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _verify_stage_zero()
        sources, root_identity = _verify_runtime_integrity(REPOSITORY_ROOT)
        result = _execute(
            arguments.command,
            source_ref=getattr(arguments, "source_ref", None),
            article_id=getattr(arguments, "article_id", None),
            sources=sources,
            root_identity=root_identity,
        )
    except _RuntimeFailure:
        _refusal(arguments, "OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID")
        return 1
    except _CommandFailure as error:
        _refusal(arguments, str(error))
        return 1
    except Exception:
        _refusal(arguments, "OFFICIAL_SOURCE_CAPTURE_INTERNAL_FAILURE")
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
