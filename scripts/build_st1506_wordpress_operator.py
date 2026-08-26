#!/usr/bin/env python3
"""Validate, package, and hash the bounded ST-1506 WordPress operator slice."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Final, NoReturn
import zipfile


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE_RELATIVE: Final = Path("changes/st-1506/self-hosted-wordpress-operator-bridge-v1")
SLICE_ROOT: Final = ROOT / SLICE_RELATIVE
PLUGIN_SLUG: Final = "raos-bounded-operator"
PLUGIN_VERSION: Final = "1.0.0"
PLUGIN_ROOT: Final = SLICE_ROOT / "wordpress-plugin" / PLUGIN_SLUG
MANIFEST_RELATIVE: Final = SLICE_RELATIVE / "runtime-manifest.v1.json"
MANIFEST_PATH: Final = ROOT / MANIFEST_RELATIVE
OUTPUT_DIRECTORY: Final = ROOT / ".secrets/st1506-wordpress-operator/plugin"
OUTPUT_PATH: Final = OUTPUT_DIRECTORY / f"{PLUGIN_SLUG}-{PLUGIN_VERSION}.zip"
ZIP_TIMESTAMP: Final = (2026, 8, 26, 0, 0, 0)
MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 8 * 1024 * 1024

PLUGIN_FILES: Final = (
    "README.md",
    "raos-bounded-operator.php",
)

RUNTIME_PATHS: Final = (
    (
        "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/"
        "ADR-001-HASH-BOUND-WORDPRESS-OPERATOR.md"
    ),
    ("changes/st-1506/self-hosted-wordpress-operator-bridge-v1/DESIGN_HANDOFF_V1.yaml"),
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/Makefile",
    ("changes/st-1506/self-hosted-wordpress-operator-bridge-v1/OPERATIONS_RUNBOOK.md"),
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/PREFLIGHT.md",
    "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/README.md",
    (
        "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/contracts/"
        "canonical-proposal-golden.v1.json"
    ),
    (
        "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/contracts/"
        "self-hosted-wordpress-operator.v1.yaml"
    ),
    (
        "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/wordpress-plugin/"
        "raos-bounded-operator/README.md"
    ),
    (
        "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/wordpress-plugin/"
        "raos-bounded-operator/raos-bounded-operator.php"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json",
    "python/raos/__init__.py",
    "python/raos/adapters/__init__.py",
    "python/raos/domain/operations/self_hosted_wordpress_operator.py",
    "python/raos/ports/__init__.py",
    "python/raos/ports/self_hosted_wordpress_operator.py",
    "python/raos/adapters/self_hosted_wordpress_operator_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_operator_https.py",
    "scripts/build_st1704_self_hosted_editorial_manifest.py",
    "scripts/build_st1704_self_hosted_theme.py",
    "scripts/st1506_wordpress_operator.py",
    "scripts/st1506_wordpress_operator_python.sh",
    "scripts/build_st1506_wordpress_operator.py",
)

FORBIDDEN_SURFACES: Final = (
    "ARBITRARY_HTTP",
    "ARBITRARY_OPTION",
    "ARBITRARY_PHP",
    "ARBITRARY_SHELL_OR_PROCESS",
    "ARBITRARY_SQL",
    "CODEX_SELF_APPROVAL",
    "MEDIA",
    "PLUGIN_MUTATION",
    "POST_CONTENT_OR_STATUS",
    "PUBLICATION_OR_SCHEDULING",
    "TAXONOMY",
    "GENERIC_OR_RUNTIME_USER_OR_ROLE_MUTATION",
)


class WordPressOperatorBuildFailure(RuntimeError):
    """Closed build failure without source or secret material."""


def _fail(code: str = "ST1506_WORDPRESS_OPERATOR_BUILD_INVALID") -> NoReturn:
    raise WordPressOperatorBuildFailure(code) from None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
        _fail("ST1506_WORDPRESS_OPERATOR_SOURCE_MISSING")
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


def _read_repository(relative: str) -> bytes:
    return _read_regular(ROOT, relative)


def _validate_exact_plugin_tree() -> None:
    try:
        metadata = PLUGIN_ROOT.lstat()
    except OSError:
        _fail("ST1506_WORDPRESS_OPERATOR_SOURCE_MISSING")
    if PLUGIN_ROOT.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail()
    observed: list[str] = []
    try:
        candidates = sorted(PLUGIN_ROOT.rglob("*"))
    except OSError:
        _fail()
    for candidate in candidates:
        try:
            item = candidate.lstat()
        except OSError:
            _fail()
        if candidate.is_symlink():
            _fail()
        if stat.S_ISDIR(item.st_mode):
            continue
        if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
            _fail()
        observed.append(candidate.relative_to(PLUGIN_ROOT).as_posix())
    if tuple(observed) != PLUGIN_FILES:
        _fail("ST1506_WORDPRESS_OPERATOR_PLUGIN_TREE_INVALID")


def validate_sources() -> dict[str, str]:
    _validate_exact_plugin_tree()
    payloads = {name: _read_regular(PLUGIN_ROOT, name) for name in PLUGIN_FILES}
    try:
        php = payloads["raos-bounded-operator.php"].decode("utf-8", errors="strict")
        readme = payloads["README.md"].decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()
    for token in (
        "Plugin Name: RAOS Bounded Operator",
        "Version: 1.0.0",
        "raos-operator/v1",
        "yoast-checksum",
        "proposals",
        "RAOS_OPERATOR_WRITES_ENABLED",
        "raos_operator_read",
        "raos_operator_propose",
        "raos_operator_apply",
        "manage_options",
        "wp_check_password",
    ):
        if token not in php:
            _fail("ST1506_WORDPRESS_OPERATOR_PLUGIN_CONTRACT_DRIFT")
    for token in (
        "raos_operator_executor",
        "raos_operator_writes_enabled",
        "application password",
        "rest namespace",
        "no generic url",
    ):
        if token not in readme.lower():
            _fail("ST1506_WORDPRESS_OPERATOR_PLUGIN_README_DRIFT")
    for forbidden_function in (
        "eval",
        "base64_decode",
        "shell_exec",
        "system",
        "passthru",
        "proc_open",
        "popen",
    ):
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(forbidden_function)}\s*\(",
            php,
            re.IGNORECASE,
        ):
            _fail("ST1506_WORDPRESS_OPERATOR_PLUGIN_UNSAFE_SOURCE")
    if "`$" in php:
        _fail("ST1506_WORDPRESS_OPERATOR_PLUGIN_UNSAFE_SOURCE")
    return {name: sha256_bytes(payload) for name, payload in payloads.items()}


def build_package() -> bytes:
    validate_sources()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in PLUGIN_FILES:
            info = zipfile.ZipInfo(f"{PLUGIN_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, _read_regular(PLUGIN_ROOT, relative))
    payload = output.getvalue()
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        _fail()
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            expected = [f"{PLUGIN_SLUG}/{name}" for name in PLUGIN_FILES]
            if archive.namelist() != expected:
                _fail()
            for name in expected:
                info = archive.getinfo(name)
                if (
                    info.date_time != ZIP_TIMESTAMP
                    or info.compress_type != zipfile.ZIP_STORED
                    or stat.S_IFMT(info.external_attr >> 16) != stat.S_IFREG
                    or stat.S_IMODE(info.external_attr >> 16) != 0o644
                    or archive.read(name)
                    != _read_regular(PLUGIN_ROOT, name.split("/", 1)[1])
                ):
                    _fail()
    except OSError, zipfile.BadZipFile, KeyError:
        _fail()
    return payload


def build_manifest() -> bytes:
    package = build_package()
    semantic_inputs = [
        {"path": relative, "semantic_id": relative, "version": 1}
        for relative in RUNTIME_PATHS
    ]
    manifest = {
        "canonical_package_modified": False,
        "external_action_authority": "INDEPENDENT_HUMAN_APPROVAL_ONLY",
        "forbidden_surfaces": list(FORBIDDEN_SURFACES),
        "generated_by": "scripts/build_st1506_wordpress_operator.py",
        "operator_contract_version": 1,
        "package": {
            "bytes": len(package),
            "compression": "ZIP_STORED",
            "file_count": len(PLUGIN_FILES),
            "root": f"{PLUGIN_SLUG}/",
            "sha256": sha256_bytes(package),
            "version": PLUGIN_VERSION,
        },
        "semantic_inputs": semantic_inputs,
        "production_readiness": "NOT_READY",
        "publication_authority": "NONE",
        "schema": "RAOS_SELF_HOSTED_WORDPRESS_OPERATOR_RUNTIME_MANIFEST_V1",
        "slice_id": "SELF_HOSTED_WORDPRESS_OPERATOR_BRIDGE_V1",
        "story_id": "ST-1506",
        "supported_mutations": ["APPLY_YOAST_PROFILE", "UPDATE_CHILD_THEME"],
        "writes_default": "DISABLED",
    }
    return (
        json.dumps(
            manifest,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii", errors="strict")


def _write_private_package(payload: bytes) -> None:
    temporary: Path | None = None
    try:
        OUTPUT_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
        if OUTPUT_DIRECTORY.is_symlink() or not OUTPUT_DIRECTORY.is_dir():
            _fail()
        os.chmod(OUTPUT_DIRECTORY, 0o700)
        temporary = OUTPUT_DIRECTORY / f".{OUTPUT_PATH.name}.{os.getpid()}.tmp"
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
        os.chmod(OUTPUT_PATH, 0o600)
    except WordPressOperatorBuildFailure:
        raise
    except OSError:
        _fail()
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _write_manifest(payload: bytes) -> None:
    temporary = MANIFEST_PATH.with_name(f".{MANIFEST_PATH.name}.{os.getpid()}.tmp")
    try:
        if MANIFEST_PATH.parent.is_symlink() or not MANIFEST_PATH.parent.is_dir():
            _fail()
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o644,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, MANIFEST_PATH)
        os.chmod(MANIFEST_PATH, 0o644)
    except WordPressOperatorBuildFailure:
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
        _fail("ST1506_WORDPRESS_OPERATOR_MANIFEST_MISSING")
    if current != expected:
        _fail("ST1506_WORDPRESS_OPERATOR_MANIFEST_DRIFT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--source-check", action="store_true")
    commands.add_argument("--package-check", action="store_true")
    commands.add_argument("--package", action="store_true")
    commands.add_argument("--manifest", action="store_true")
    commands.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.source_check:
            validate_sources()
            print("ST1506_WORDPRESS_OPERATOR_SOURCE_OK")
            return 0
        first = build_package()
        second = build_package()
        if first != second:
            _fail("ST1506_WORDPRESS_OPERATOR_PACKAGE_NONDETERMINISTIC")
        if arguments.package_check:
            print("ST1506_WORDPRESS_OPERATOR_PACKAGE_OK")
            return 0
        if arguments.package:
            _write_private_package(first)
            print(
                json.dumps(
                    {
                        "artifact": OUTPUT_PATH.as_posix(),
                        "bytes": len(first),
                        "publication_authority": "NONE",
                        "sha256": sha256_bytes(first),
                    },
                    allow_nan=False,
                    sort_keys=True,
                )
            )
            return 0
        manifest = build_manifest()
        if arguments.manifest or not any(vars(arguments).values()):
            _write_manifest(manifest)
            print("ST1506_WORDPRESS_OPERATOR_MANIFEST_GENERATED")
            return 0
        check_manifest(manifest)
        print("ST1506_WORDPRESS_OPERATOR_MANIFEST_OK")
        return 0
    except WordPressOperatorBuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
