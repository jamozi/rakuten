#!/usr/bin/env python3
"""Build and verify the deterministic RAOS Codex MCP WordPress package."""

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
SLICE: Final = ROOT / "changes/wordpress-mcp-v1"
PLUGIN_SLUG: Final = "raos-codex-mcp-abilities"
PLUGIN_VERSION: Final = "1.0.2"
PLUGIN_ROOT: Final = SLICE / "wordpress-plugin" / PLUGIN_SLUG
MANIFEST: Final = SLICE / "runtime-manifest.v1.json"
OUTPUT: Final = (
    ROOT / ".secrets/wordpress-mcp/plugin" / f"{PLUGIN_SLUG}-{PLUGIN_VERSION}.zip"
)
ZIP_TIMESTAMP: Final = (2026, 8, 29, 0, 0, 0)
MAX_FILE_BYTES: Final = 8 * 1024 * 1024
PLUGIN_FILES: Final = (
    "README.md",
    "includes/class-raos-codex-mcp-content.php",
    "includes/class-raos-codex-mcp-deployment.php",
    "includes/class-raos-codex-mcp-store.php",
    "raos-codex-mcp-abilities.php",
)
RUNTIME_PATHS: Final = (
    ".codex/config.toml",
    "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json",
    "changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.json",
    "changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.schema.json",
    "changes/wordpress-mcp-v1/Makefile",
    "changes/wordpress-mcp-v1/README.md",
    "packages/wordpress-mcp-bridge/package.json",
    "packages/wordpress-mcp-bridge/src/index.ts",
    "packages/wordpress-mcp-bridge/tsconfig.json",
    "scripts/build_wordpress_mcp_v1.py",
    "scripts/check_wordpress_public_ui_playwright.sh",
    "scripts/raos_wordpress_deployment_operator.py",
    "scripts/raos_wordpress_editor_mcp_launcher.mjs",
    "scripts/store_wordpress_mcp_credential.py",
    "scripts/wordpress_public_ui_audit.function.js",
    "tests/wordpress_mcp_v1/e2e/approve_harness.php",
    "tests/wordpress_mcp_v1/e2e/client.py",
    "tests/wordpress_mcp_v1/e2e/compose.yaml",
    "tests/wordpress_mcp_v1/e2e/gateway/nginx.conf",
    "tests/wordpress_mcp_v1/e2e/mutate_harness.php",
    "tests/wordpress_mcp_v1/e2e/prepare_packages.py",
    "tests/wordpress_mcp_v1/e2e/run.sh",
    *(
        f"changes/wordpress-mcp-v1/wordpress-plugin/{PLUGIN_SLUG}/{name}"
        for name in PLUGIN_FILES
    ),
)
EXTERNAL_PINS: Final = {
    "mcp_adapter": {
        "source": "https://github.com/WordPress/mcp-adapter",
        "version": "0.6.1",
        "git_commit": "23cb53e0b82f39238eec1c38cb055e28aa30fa7c",
        "release_zip_sha256": "1c3cd47c32e99b4e7d8690a44a7890256e92a8b96f61776cbe1894e5483cf676",
    },
    "remote_proxy": {
        "package": "@automattic/mcp-wordpress-remote",
        "version": "0.4.0",
        "npm_integrity": "sha512-YIu0Am3yDHtxajDpa9R7uAMnonR7if7PfHwck0pe8XPfY43O+R9HlQdBVhi75gNNK++BDo9fUz2vl+Dvn4EFGA==",
    },
    "typescript_sdk": {
        "package": "@modelcontextprotocol/sdk",
        "version": "1.30.0",
    },
    "terminal_playwright": {
        "package": "@playwright/cli",
        "version": "0.1.18",
    },
    "e2e_images": {
        "mariadb": "mariadb:11.8.3@sha256:ae6119716edac6998ae85508431b3d2e666530ddf4e94c61a10710caec9b0f71",
        "wordpress": "wordpress:7.1.0-php8.3-apache@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e",
        "wp_cli": "wordpress:cli-2.12.0-php8.3@sha256:2b5e9d4d3e51909dca1aaa4732e9f5e5bf0377c2114dbd8ff39f060bff202586",
    },
}


class BuildFailure(RuntimeError):
    """A closed build failure."""


def fail(code: str = "WORDPRESS_MCP_V1_BUILD_INVALID") -> NoReturn:
    raise BuildFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail()


def safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/"):
        fail()
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        fail()
    return path


def read_regular(root: Path, relative: str) -> bytes:
    safe = safe_relative(relative)
    path = root.joinpath(*safe.parts)
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_V1_SOURCE_MISSING")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 1
        or metadata.st_size > MAX_FILE_BYTES
        or len(payload) != metadata.st_size
    ):
        fail("WORDPRESS_MCP_V1_SOURCE_INVALID")
    return payload


def plugin_payloads() -> dict[str, bytes]:
    seen: set[str] = set()
    result: dict[str, bytes] = {}
    for relative in PLUGIN_FILES:
        safe = safe_relative(relative).as_posix()
        if safe.casefold() in seen:
            fail("WORDPRESS_MCP_V1_CASE_COLLISION")
        seen.add(safe.casefold())
        result[safe] = read_regular(PLUGIN_ROOT, safe)
    return result


def package_bytes(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative in sorted(payloads):
            info = zipfile.ZipInfo(f"{PLUGIN_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                payloads[relative],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def file_manifest(payloads: dict[str, bytes]) -> list[dict[str, object]]:
    return [
        {"path": path, "size": len(payload), "sha256": sha256(payload)}
        for path, payload in sorted(payloads.items())
    ]


def runtime_manifest() -> dict[str, object]:
    payloads = plugin_payloads()
    package = package_bytes(payloads)
    runtime = []
    for relative in RUNTIME_PATHS:
        payload = read_regular(ROOT, relative)
        runtime.append(
            {"path": relative, "size": len(payload), "sha256": sha256(payload)}
        )
    manifest = file_manifest(payloads)
    return {
        "schema": "RAOS_WORDPRESS_MCP_RUNTIME_MANIFEST_V1",
        "version": "1.0.0",
        "site_origin": "https://kurashinoshirube.com",
        "wordpress_version": "7.1.x",
        "plugin": {
            "slug": PLUGIN_SLUG,
            "version": PLUGIN_VERSION,
            "package_sha256": sha256(package),
            "file_manifest_sha256": sha256(
                json.dumps(
                    manifest,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
            ),
            "files": manifest,
        },
        "external_pins": EXTERNAL_PINS,
        "runtime_files": runtime,
    }


def write_manifest() -> None:
    payload = canonical_json(runtime_manifest())
    MANIFEST.write_bytes(payload)


def check_manifest() -> None:
    expected = canonical_json(runtime_manifest())
    try:
        actual = MANIFEST.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_V1_MANIFEST_MISSING")
    if actual != expected:
        fail("WORDPRESS_MCP_V1_MANIFEST_DRIFT")


def write_package() -> None:
    payload = package_bytes(plugin_payloads())
    OUTPUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(OUTPUT.parent, 0o700)
    temporary = OUTPUT.with_suffix(".zip.tmp")
    temporary.write_bytes(payload)
    os.chmod(temporary, 0o600)
    temporary.replace(OUTPUT)


def check_package() -> None:
    expected = package_bytes(plugin_payloads())
    try:
        actual = OUTPUT.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_V1_PRIVATE_PACKAGE_MISSING")
    if actual != expected:
        fail("WORDPRESS_MCP_V1_PRIVATE_PACKAGE_DRIFT")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    actions = result.add_mutually_exclusive_group()
    actions.add_argument("--manifest", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--package", action="store_true")
    actions.add_argument("--package-check", action="store_true")
    actions.add_argument("--source-check", action="store_true")
    return result


def main() -> int:
    try:
        arguments = parser().parse_args()
        if arguments.manifest or not any(
            (
                arguments.check,
                arguments.package,
                arguments.package_check,
                arguments.source_check,
            )
        ):
            write_manifest()
        elif arguments.check:
            check_manifest()
        elif arguments.package:
            write_package()
        elif arguments.package_check:
            check_package()
        else:
            plugin_payloads()
        return 0
    except BuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
