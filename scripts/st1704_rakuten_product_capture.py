#!/usr/bin/env python3
"""Manifest-bound owner-authorized Rakuten product capture for ST-1704."""

from __future__ import annotations

import argparse
from collections.abc import Container
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import types
from typing import Final, NoReturn, Protocol, TextIO, cast


CLI_PATH: Final = Path(os.path.abspath(__file__))
REPOSITORY_ROOT: Final = CLI_PATH.parent.parent
OWNER_PYTHON: Final = (REPOSITORY_ROOT / ".venv/bin/python").as_posix()
BOOTSTRAP_RELATIVE: Final = "scripts/st1704_rakuten_product_capture.py"
MANIFEST_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/"
    "rakuten-capture-runtime-manifest.v1.json"
)
MAX_MANIFEST_BYTES: Final = 128 * 1024
MAX_RUNTIME_BYTES: Final = 4 * 1024 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT_OBJECT_ID: Final = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_PROCESS_ENVIRONMENT: Final = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    **_PROCESS_ENVIRONMENT,
}
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
EXPECTED_RUNTIME_PATHS: Final = tuple(
    sorted(
        (
            "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml",
            "changes/st-1704/self-hosted-editorial-pilot-v1/Makefile",
            "changes/st-1704/self-hosted-editorial-pilot-v1/OPERATIONS_RUNBOOK.md",
            "changes/st-1704/self-hosted-editorial-pilot-v1/PREFLIGHT.md",
            "changes/st-1704/self-hosted-editorial-pilot-v1/RAKUTEN_CAPTURE_WORKLOG.md",
            "changes/st-1704/self-hosted-editorial-pilot-v1/README.md",
            "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
            "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json",
            "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
            "python/raos/adapters/self_hosted_editorial_rakuten_capture.py",
            "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
            "scripts/build_st1704_rakuten_capture_manifest.py",
            BOOTSTRAP_RELATIVE,
        )
    )
)
_TRACKED_DOCUMENT_PATHS: Final = frozenset(
    {
        "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    }
)
_PACKAGE_NAMES: Final = (
    "raos",
    "raos.domain",
    "raos.domain.editorial",
    "raos.adapters",
)
_MODULE_PATHS: Final = (
    (
        "raos.domain.editorial.self_hosted_editorial_pilot",
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_rakuten_capture",
        "python/raos/adapters/self_hosted_editorial_rakuten_capture.py",
    ),
)
_CAPTURE_FAILURE_CODES: Final = frozenset(
    {
        "ARTICLE_NOT_ALLOWLISTED",
        "BODY_TOO_LARGE",
        "CONNECTION_FAILED",
        "CONTRACT_INVALID",
        "CREDENTIAL_UNAVAILABLE",
        "CREDENTIAL_REFLECTION",
        "CREDENTIAL_UNSAFE",
        "DNS_ADDRESS_REJECTED",
        "DNS_FAILED",
        "IMAGE_INVALID",
        "INVALID_ARGUMENT",
        "MIME_INVALID",
        "NETWORK_ENVIRONMENT_UNSAFE",
        "PRODUCT_IDENTITY_AMBIGUOUS",
        "PRODUCT_IDENTITY_INVALID",
        "PRODUCT_NOT_FOUND",
        "REQUEST_AMBIGUOUS",
        "RESPONSE_INVALID",
        "STORE_CONFLICT",
        "STORE_UNSAFE",
        "TLS_CONTEXT_INVALID",
    }
)
RootIdentity = tuple[int, int]


class _CaptureResult(Protocol):
    affiliate_response_sha256: str
    credentials_used: bool
    image_sha256: str
    item_code: str
    product_id: str
    production_evidence: bool
    publication_authority: bool
    request_count: int
    response_sha256: str
    retrieved_at: str
    status: str


class _RuntimeFailure(RuntimeError):
    """Sanitized stage-zero refusal."""


class _CommandFailure(RuntimeError):
    """Sanitized verified-runtime refusal."""

    __slots__ = ("credentials_used",)

    def __init__(self, code: str, *, credentials_used: bool) -> None:
        if type(credentials_used) is not bool:
            _fail_runtime()
        self.credentials_used = credentials_used
        super().__init__(code)


def _fail_runtime() -> NoReturn:
    raise _RuntimeFailure("RAKUTEN_PRODUCT_CAPTURE_RUNTIME_INVALID") from None


def _canonical_manifest(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except TypeError, ValueError, UnicodeError:
        _fail_runtime()


def _decode_json(raw: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[object, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if type(key) is not str or key in result:
                _fail_runtime()
            result[key] = value
        return result

    def reject(value: str) -> NoReturn:
        del value
        _fail_runtime()

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=reject,
        )
    except _RuntimeFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail_runtime()
    if type(value) is not dict:
        _fail_runtime()
    return cast(dict[str, object], value)


def _relative_parts(relative: str) -> tuple[str, ...]:
    if type(relative) is not str or not relative:
        _fail_runtime()
    value = PurePosixPath(relative)
    if (
        value.is_absolute()
        or value.as_posix() != relative
        or any(part in {"", ".", ".."} for part in value.parts)
    ):
        _fail_runtime()
    return value.parts


def _open_absolute_directory(path: Path) -> int:
    try:
        return os.open(path, _DIRECTORY_FLAGS)
    except OSError:
        _fail_runtime()


def _safe_directory(descriptor: int) -> os.stat_result:
    try:
        observed = os.fstat(descriptor)
    except OSError:
        _fail_runtime()
    if not stat.S_ISDIR(observed.st_mode):
        _fail_runtime()
    return observed


def _safe_file(descriptor: int, *, maximum: int) -> os.stat_result:
    try:
        observed = os.fstat(descriptor)
    except OSError:
        _fail_runtime()
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_nlink != 1
        or not 1 <= observed.st_size <= maximum
    ):
        _fail_runtime()
    return observed


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    try:
        current = os.dup(root_fd)
    except OSError:
        _fail_runtime()
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            except OSError:
                _fail_runtime()
            os.close(current)
            current = child
            _safe_directory(current)
        return current, parts[-1]
    except BaseException:
        os.close(current)
        raise


def _read_relative(root_fd: int, relative: str, *, maximum: int) -> bytes:
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail_runtime()
        try:
            before = _safe_file(descriptor, maximum=maximum)
            chunks: list[bytes] = []
            remaining = before.st_size
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
    try:
        current_directory = os.getcwd()
    except OSError:
        _fail_runtime()
    flags = sys.flags
    if (
        CLI_PATH != REPOSITORY_ROOT / BOOTSTRAP_RELATIVE
        or sys.executable != OWNER_PYTHON
        or sys.version_info[:3] != (3, 14, 6)
        or flags.dont_write_bytecode != 1
        or flags.ignore_environment != 1
        or flags.isolated != 1
        or flags.no_site != 1
        or flags.no_user_site != 1
        or not flags.safe_path
        or current_directory != REPOSITORY_ROOT.as_posix()
        or dict(os.environ) != _PROCESS_ENVIRONMENT
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
    if completed.returncode != 0 or len(completed.stdout) > maximum_stdout:
        _fail_runtime()
    return completed.stdout


def _committed_blob(root: Path, *, head: str, relative: str, maximum: int) -> bytes:
    if _GIT_OBJECT_ID.fullmatch(head) is None:
        _fail_runtime()
    _relative_parts(relative)
    spec = f"{head}:{relative}"
    raw_size = _git(root, "cat-file", "-s", spec, maximum_stdout=128)
    try:
        text = raw_size.decode("ascii", errors="strict").strip()
        size = int(text)
    except UnicodeError, ValueError:
        _fail_runtime()
    if str(size) != text or not 1 <= size <= maximum:
        _fail_runtime()
    blob = _git(root, "cat-file", "blob", spec, maximum_stdout=size)
    if len(blob) != size:
        _fail_runtime()
    return blob


def _contains_exact(values: Container[str], expected: str) -> bool:
    return expected in values


def _verify_runtime_integrity(root: Path) -> tuple[dict[str, bytes], RootIdentity]:
    if (
        tuple(sorted(EXPECTED_RUNTIME_PATHS)) != EXPECTED_RUNTIME_PATHS
        or len(set(EXPECTED_RUNTIME_PATHS)) != len(EXPECTED_RUNTIME_PATHS)
        or not _TRACKED_DOCUMENT_PATHS < set(EXPECTED_RUNTIME_PATHS)
        or not _contains_exact(EXPECTED_RUNTIME_PATHS, BOOTSTRAP_RELATIVE)
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(root)
    try:
        root_state = _safe_directory(root_fd)
        expected_root = os.fsencode(root.as_posix()) + b"\n"
        if (
            _git(
                root,
                "rev-parse",
                "--show-toplevel",
                maximum_stdout=max(128, len(expected_root)),
            )
            != expected_root
        ):
            _fail_runtime()
        raw_head = _git(
            root, "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128
        )
        try:
            head = raw_head.decode("ascii", errors="strict").strip()
        except UnicodeError:
            _fail_runtime()
        if _GIT_OBJECT_ID.fullmatch(head) is None:
            _fail_runtime()
        manifest_raw = _read_relative(
            root_fd, MANIFEST_RELATIVE, maximum=MAX_MANIFEST_BYTES
        )
        if manifest_raw != _committed_blob(
            root, head=head, relative=MANIFEST_RELATIVE, maximum=MAX_MANIFEST_BYTES
        ):
            _fail_runtime()
        manifest = _decode_json(manifest_raw)
        if manifest_raw != _canonical_manifest(manifest) or set(manifest) != {
            "article_ids",
            "external_action_authority",
            "generated_by",
            "paths",
            "publication_authority",
            "schema",
            "slice_id",
            "story_id",
        }:
            _fail_runtime()
        if (
            manifest["article_ids"] != list(ARTICLE_IDS)
            or manifest["external_action_authority"]
            != "HUMAN_OWNER_BOUNDED_RAKUTEN_READ"
            or manifest["generated_by"]
            != "scripts/build_st1704_rakuten_capture_manifest.py"
            or manifest["publication_authority"] != "NONE"
            or manifest["schema"] != "ST1704_BOUNDED_RAKUTEN_CAPTURE_MANIFEST_V1"
            or manifest["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
            or manifest["story_id"] != "ST-1704"
        ):
            _fail_runtime()
        entries = manifest["paths"]
        if type(entries) is not list or len(entries) != len(EXPECTED_RUNTIME_PATHS):
            _fail_runtime()
        sources: dict[str, bytes] = {}
        for relative, raw_entry in zip(
            EXPECTED_RUNTIME_PATHS, cast(list[object], entries), strict=True
        ):
            if type(raw_entry) is not dict:
                _fail_runtime()
            entry = cast(dict[str, object], raw_entry)
            if set(entry) != {"bytes", "path", "sha256"}:
                _fail_runtime()
            count = entry["bytes"]
            digest = entry["sha256"]
            if (
                entry["path"] != relative
                or type(count) is not int
                or not 1 <= count <= MAX_RUNTIME_BYTES
                or type(digest) is not str
                or _SHA256.fullmatch(digest) is None
            ):
                _fail_runtime()
            raw = _read_relative(root_fd, relative, maximum=MAX_RUNTIME_BYTES)
            committed = _committed_blob(
                root, head=head, relative=relative, maximum=MAX_RUNTIME_BYTES
            )
            if (
                raw != committed
                or len(raw) != count
                or hashlib.sha256(raw).hexdigest() != digest
            ):
                _fail_runtime()
            sources[relative] = raw
        if (
            _git(root, "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=128)
            != raw_head
        ):
            _fail_runtime()
        rebound = _open_absolute_directory(root)
        try:
            final = _safe_directory(rebound)
            if (root_state.st_dev, root_state.st_ino) != (final.st_dev, final.st_ino):
                _fail_runtime()
        finally:
            os.close(rebound)
        return sources, (root_state.st_dev, root_state.st_ino)
    finally:
        os.close(root_fd)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    setattr(module, "__path__", [])
    sys.modules[name] = module
    if "." in name:
        parent, child = name.rsplit(".", 1)
        setattr(sys.modules[parent], child, module)
    return module


def _load_verified_modules(sources: dict[str, bytes]) -> dict[str, types.ModuleType]:
    names = {*_PACKAGE_NAMES, *(name for name, _relative in _MODULE_PATHS)}
    if names & set(sys.modules):
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
        parent, child = module_name.rsplit(".", 1)
        setattr(sys.modules[parent], child, module)
        try:
            exec(
                compile(raw, module.__file__, "exec", dont_inherit=True),
                module.__dict__,
            )
        except BaseException:
            _fail_runtime()
        loaded[module_name] = module
    return loaded


def _bind_tracked_documents(
    module: types.ModuleType, sources: dict[str, bytes], identity: RootIdentity
) -> None:
    verified = {relative: sources[relative] for relative in _TRACKED_DOCUMENT_PATHS}

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
        raw = verified.get(relative.as_posix())
        if raw is None or len(raw) > maximum:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, identity)
        return raw

    setattr(module, "_read_tracked_file", read_tracked_file)


def _write_json(value: object, *, target: TextIO | None = None) -> None:
    destination = sys.stdout if target is None else target
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
        prog="st1704_rakuten_product_capture.py",
        description=(
            "Capture exact Rakuten link and 128x128 image evidence for one "
            "allowlisted ST-1704 article. No caller URL or publication capability."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    article = commands.add_parser("capture-article", allow_abbrev=False)
    article.add_argument("--article-id", choices=ARTICLE_IDS, required=True)
    return parser


def _execute(
    article_id: str, sources: dict[str, bytes], identity: RootIdentity
) -> dict[str, object]:
    _rebind_root(REPOSITORY_ROOT, identity)
    modules = _load_verified_modules(sources)
    capture = modules["raos.adapters.self_hosted_editorial_rakuten_capture"]
    _bind_tracked_documents(capture, sources, identity)
    capture_article = getattr(capture, "capture_article_products", None)
    failure_type = getattr(capture, "RakutenProductCaptureFailure", None)
    result_type = getattr(capture, "ProductCaptureResult", None)
    if (
        not callable(capture_article)
        or not isinstance(failure_type, type)
        or not isinstance(result_type, type)
    ):
        _fail_runtime()
    try:
        results_value = capture_article(REPOSITORY_ROOT, article_id=article_id)
    except _RuntimeFailure:
        raise
    except Exception as error:
        if type(error) is failure_type:
            code = getattr(getattr(error, "code", None), "value", None)
            credentials_used = getattr(error, "credentials_used", None)
            if (
                type(code) is str
                and code in _CAPTURE_FAILURE_CODES
                and type(credentials_used) is bool
            ):
                raise _CommandFailure(code, credentials_used=credentials_used) from None
        raise
    if type(results_value) is not tuple:
        _fail_runtime()
    documents: list[dict[str, object]] = []
    request_count = 0
    for value in cast(tuple[object, ...], results_value):
        if type(value) is not result_type:
            _fail_runtime()
        result = cast(_CaptureResult, value)
        for digest in (
            result.response_sha256,
            result.affiliate_response_sha256,
            result.image_sha256,
        ):
            if type(digest) is not str or _SHA256.fullmatch(digest) is None:
                _fail_runtime()
        if (
            result.credentials_used is not True
            or result.production_evidence is not False
            or result.publication_authority is not False
            or type(result.request_count) is not int
            or not 3 <= result.request_count <= 8
            or type(result.product_id) is not str
            or type(result.item_code) is not str
            or type(result.retrieved_at) is not str
            or result.status != "CAPTURED_EXACT_PRODUCT"
        ):
            _fail_runtime()
        request_count += result.request_count
        documents.append(
            {
                "affiliate_response_sha256": result.affiliate_response_sha256,
                "image_sha256": result.image_sha256,
                "item_code": result.item_code,
                "product_id": result.product_id,
                "request_count": result.request_count,
                "response_sha256": result.response_sha256,
                "retrieved_at": result.retrieved_at,
                "status": result.status,
            }
        )
    return {
        "article_id": article_id,
        "command": "capture-article",
        "credentials_used": True,
        "network_requests": request_count,
        "production_evidence": False,
        "publication_authority": False,
        "results": documents,
        "status": "CAPTURE_COMPLETED",
    }


def _refusal(
    arguments: argparse.Namespace, code: str, *, credentials_used: bool = False
) -> None:
    _write_json(
        {
            "article_id": getattr(arguments, "article_id", None),
            "command": getattr(arguments, "command", None),
            "credentials_used": credentials_used,
            "error": code,
            "production_evidence": False,
            "publication_authority": False,
            "status": "REFUSED",
        },
        target=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _verify_stage_zero()
        sources, identity = _verify_runtime_integrity(REPOSITORY_ROOT)
        result = _execute(arguments.article_id, sources, identity)
    except _RuntimeFailure:
        _refusal(arguments, "RAKUTEN_PRODUCT_CAPTURE_RUNTIME_INVALID")
        return 1
    except _CommandFailure as error:
        _refusal(
            arguments,
            str(error),
            credentials_used=error.credentials_used,
        )
        return 1
    except Exception:
        _refusal(arguments, "RAKUTEN_PRODUCT_CAPTURE_INTERNAL_FAILURE")
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
