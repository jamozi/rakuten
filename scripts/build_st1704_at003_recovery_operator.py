#!/usr/bin/env python3
"""Build and verify the deterministic AT-003 recovery operator package."""

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
SLICE: Final = ROOT / "changes/st-1704/at003-recovery-operator-v1"
PLUGIN_SLUG: Final = "raos-at003-recovery-operator"
PLUGIN_VERSION: Final = "1.1.0"
PLUGIN_ROOT: Final = SLICE / "wordpress-plugin" / PLUGIN_SLUG
OUTPUT: Final = (
    ROOT
    / ".secrets/st1704-at003-recovery-operator-v1/plugin"
    / f"{PLUGIN_SLUG}-{PLUGIN_VERSION}.zip"
)
MANIFEST: Final = SLICE / "runtime-manifest.v1.json"
ZIP_TIMESTAMP: Final = (2026, 8, 27, 0, 0, 0)
FILES: Final = (
    "README.md",
    "at003-snapshot.v1.json",
    "raos-at003-recovery-operator.php",
)


class BuildFailure(RuntimeError):
    pass


def fail(code: str = "ST1704_AT003_RECOVERY_BUILD_INVALID") -> NoReturn:
    raise BuildFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_file(relative: str) -> bytes:
    safe = PurePosixPath(relative)
    if safe.is_absolute() or safe.as_posix() != relative or ".." in safe.parts:
        fail()
    path = PLUGIN_ROOT.joinpath(*safe.parts)
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("ST1704_AT003_RECOVERY_SOURCE_MISSING")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not payload
        or len(payload) != metadata.st_size
        or len(payload) > 1024 * 1024
    ):
        fail()
    return payload


def files() -> dict[str, bytes]:
    result = {name: read_file(name) for name in FILES}
    source = result["raos-at003-recovery-operator.php"].decode("utf-8")
    required = (
        "Version: 1.1.0",
        "RAOS_AT003_RECOVERY_WRITES_ENABLED",
        "SOURCE_POST_ID = 26",
        "TARGET_POST_ID = 19",
        "PAYLOAD_SHA256",
        "wp_check_password(",
        "add_option(self::LOCK_KEY",
        "'post_status' => 'publish'",
        "self::rollback($context)",
        "SNAPSHOT_RAW_SHA256",
    )
    forbidden = (
        "register_rest_route",
        "wp_ajax_",
        "admin_post_nopriv_",
        "wp_insert_post(",
        "wp_delete_post(",
        "wp_create_category(",
        "wp_insert_term(",
        "delete_option(",
    )
    if any(token not in source for token in required) or any(
        token in source for token in forbidden
    ):
        fail("ST1704_AT003_RECOVERY_SURFACE_INVALID")
    if source.count("wp_update_post(") != 2 or source.count("update_post_meta(") != 4:
        fail("ST1704_AT003_RECOVERY_SURFACE_INVALID")
    snapshot = result["at003-snapshot.v1.json"].rstrip(b"\r\n")
    if sha256(snapshot) != "bd71097b68c3c4386459195e7e41a08ebb3e60f2912594b25ed66763bb25ba9a":
        fail("ST1704_AT003_RECOVERY_SNAPSHOT_INVALID")
    return result


def package_bytes() -> bytes:
    payloads = files()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in FILES:
            info = zipfile.ZipInfo(f"{PLUGIN_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, payloads[relative])
    package = buffer.getvalue()
    if not package or len(package) > 2 * 1024 * 1024:
        fail()
    with zipfile.ZipFile(io.BytesIO(package), "r") as archive:
        expected = [f"{PLUGIN_SLUG}/{name}" for name in FILES]
        if archive.namelist() != expected:
            fail()
        for name in expected:
            info = archive.getinfo(name)
            relative = name.removeprefix(f"{PLUGIN_SLUG}/")
            if (
                info.date_time != ZIP_TIMESTAMP
                or info.compress_type != zipfile.ZIP_STORED
                or stat.S_IFMT(info.external_attr >> 16) != stat.S_IFREG
                or stat.S_IMODE(info.external_attr >> 16) != 0o644
                or archive.read(name) != payloads[relative]
            ):
                fail()
    return package


def manifest_bytes() -> bytes:
    package = package_bytes()
    payloads = files()
    document = {
        "approval": "COOKIE_AUTHENTICATED_MANAGE_OPTIONS_HUMAN_REAUTHENTICATION",
        "article_id": "st1703-first-suitcase-comparison",
        "generated_by": "scripts/build_st1704_at003_recovery_operator.py",
        "host_gate": "RAOS_AT003_RECOVERY_WRITES_ENABLED_DEFAULT_DISABLED",
        "package": {
            "bytes": len(package),
            "files": [
                {
                    "bytes": len(payloads[name]),
                    "path": name,
                    "sha256": sha256(payloads[name]),
                }
                for name in FILES
            ],
            "sha256": sha256(package),
            "slug": PLUGIN_SLUG,
            "version": PLUGIN_VERSION,
        },
        "schema": "RAOS_ST1704_AT003_RECOVERY_OPERATOR_MANIFEST_V1",
        "source_post_id": 26,
        "supported_mutations": [
            "COPY_FIXED_REVIEW_FIELDS",
            "TARGET_DRAFT_TO_PUBLISH",
        ],
        "target_post_id": 19,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("ascii")


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == 0o600:
        os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def check() -> dict[str, object]:
    package = package_bytes()
    expected_manifest = manifest_bytes()
    if not MANIFEST.is_file() or MANIFEST.read_bytes() != expected_manifest:
        fail("ST1704_AT003_RECOVERY_MANIFEST_DRIFT")
    return {"bytes": len(package), "sha256": sha256(package), "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "check", "package"))
    command = parser.parse_args().command
    try:
        if command == "generate":
            atomic_write(MANIFEST, manifest_bytes(), 0o644)
        elif command == "package":
            check()
            atomic_write(OUTPUT, package_bytes(), 0o600)
        result = check()
        result["command"] = command
        if command == "package":
            result["output"] = str(OUTPUT)
        print(json.dumps(result, sort_keys=True))
        return 0
    except BuildFailure as error:
        print(str(error), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
