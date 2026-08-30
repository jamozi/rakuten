#!/usr/bin/env python3
"""Build and verify the deterministic RAOS Codex MCP WordPress package."""

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
from typing import TYPE_CHECKING, Final, NoReturn
import zipfile


if TYPE_CHECKING:
    from scripts import (  # noqa: F401
        build_editorial_measurement_v1 as editorial_measurement_owner,
        build_editorial_v3_theme_navigation as editorial_navigation_owner,
    )


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE: Final = ROOT / "changes/wordpress-mcp-v1"
PLUGIN_SLUG: Final = "raos-codex-mcp-abilities"
PLUGIN_VERSION: Final = "1.3.0"
PLUGIN_ROOT: Final = SLICE / "wordpress-plugin" / PLUGIN_SLUG
MANIFEST_PATH: Final = Path("changes/wordpress-mcp-v1/runtime-manifest.v1.json")
REGISTRY_PATH: Final = Path(
    "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json"
)
MEASUREMENT_MANIFEST_PATH: Final = Path(
    "changes/editorial-measurement-v1/runtime-manifest.v1.json"
)
MANIFEST: Final = ROOT / MANIFEST_PATH
REGISTRY: Final = ROOT / REGISTRY_PATH
OUTPUT_PATHS: Final = (MANIFEST_PATH, REGISTRY_PATH)
OUTPUT: Final = (
    ROOT / ".secrets/wordpress-mcp/plugin" / f"{PLUGIN_SLUG}-{PLUGIN_VERSION}.zip"
)
REPO_ARTIFACT_ID: Final = "raos-codex-mcp-abilities-v1"
REPO_OUTPUT: Final = (
    ROOT
    / ".secrets/wordpress-mcp/repo-plugin-artifacts"
    / f"{REPO_ARTIFACT_ID}.zip"
)
ZIP_TIMESTAMP: Final = (2026, 8, 29, 0, 0, 0)
MAX_FILE_BYTES: Final = 8 * 1024 * 1024
AUDIT_INVENTORY_PATH: Final = Path(
    "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)
PLUGIN_FILES: Final = (
    "README.md",
    "includes/class-raos-codex-mcp-content.php",
    "includes/class-raos-codex-mcp-deployment.php",
    "includes/class-raos-codex-mcp-store.php",
    "raos-codex-mcp-abilities.php",
)
RUNTIME_INPUT_PATHS: Final = (
    Path(".codex/config.toml"),
    Path("Makefile"),
    AUDIT_INVENTORY_PATH,
    MEASUREMENT_MANIFEST_PATH,
    Path("changes/wordpress-local-preview-v1/README.md"),
    Path("changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"),
    Path("changes/wordpress-local-preview-v1/browser/check.sh"),
    Path(
        "changes/wordpress-local-preview-v1/browser/"
        "wordpress_local_preview_audit.function.js"
    ),
    Path("changes/wordpress-local-preview-v1/compose.yaml"),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "anker-solix-c300-c800-c1000-differences.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-comparison.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-under-100-seats.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "compact-robot-vacuum-shortlist.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "countertop-dishwasher-for-small-households.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "front-open-carry-on-suitcase-with-stopper.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "lightweight-carry-on-suitcase-under-3kg.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "portable-power-station-guide.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "roomba-mini-vs-switchbot-k11-pro.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "solota-vs-rakua-mini-plus.html"
    ),
    Path("changes/wordpress-local-preview-v1/fixtures/pages/about-ad-policy.html"),
    Path("changes/wordpress-local-preview-v1/fixtures/pages/comparison-policy.html"),
    Path("changes/wordpress-local-preview-v1/fixtures/pages/privacy-policy.html"),
    Path("changes/wordpress-local-preview-v1/fixtures/pages.json"),
    Path("changes/wordpress-local-preview-v1/fixtures/posts.json"),
    Path("changes/wordpress-local-preview-v1/production-mapping.v1.json"),
    Path("changes/wordpress-local-preview-v1/seed.php"),
    Path("changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.json"),
    Path("changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.schema.json"),
    Path("changes/wordpress-mcp-v1/Makefile"),
    Path("changes/wordpress-mcp-v1/README.md"),
    Path("changes/wordpress-publication-bundle-v3/abilities_plugin_proposal.py"),
    Path("changes/wordpress-publication-bundle-v3/measurement_plugin_proposal.py"),
    Path("changes/wordpress-publication-bundle-v3/production-sequence.v3.json"),
    Path("changes/wordpress-seo-audit-v1/README.md"),
    Path("changes/wordpress-seo-audit-v1/seo-audit-contract.v1.json"),
    Path("packages/wordpress-mcp-bridge/package.json"),
    Path("packages/wordpress-mcp-bridge/src/index.ts"),
    Path("packages/wordpress-mcp-bridge/tsconfig.json"),
    Path("scripts/build_wordpress_mcp_v1.py"),
    Path("scripts/check_wordpress_public_ui_playwright.sh"),
    Path("scripts/raos_wordpress_deployment_operator.py"),
    Path("scripts/raos_wordpress_publication_request.py"),
    Path("scripts/raos_wordpress_seo_audit.py"),
    Path("scripts/raos_wordpress_editor_mcp_launcher.mjs"),
    Path("scripts/store_wordpress_mcp_credential.py"),
    Path("scripts/wordpress_public_ui_audit.function.js"),
    Path("tests/wordpress_mcp_v1/e2e/approve_harness.php"),
    Path("tests/wordpress_mcp_v1/e2e/batch_approve_harness.php"),
    Path("tests/wordpress_mcp_v1/e2e/client.py"),
    Path("tests/wordpress_mcp_v1/e2e/compose.yaml"),
    Path("tests/wordpress_mcp_v1/e2e/gateway/nginx.conf"),
    Path("tests/wordpress_mcp_v1/e2e/mutate_harness.php"),
    Path("tests/wordpress_mcp_v1/e2e/idempotency_harness.php"),
    Path("tests/wordpress_mcp_v1/e2e/prepare_packages.py"),
    Path("tests/wordpress_mcp_v1/e2e/run.sh"),
    Path("tests/wordpress_mcp_v1/e2e/store_upgrade_harness.php"),
    Path("tests/wordpress_mcp_v1/test_batch_approval.py"),
    Path("tests/wordpress_mcp_v1/test_release_watcher.py"),
    Path("tests/wordpress_local_preview/test_publication_request.py"),
)
RUNTIME_FILES: Final = tuple(path.as_posix() for path in RUNTIME_INPUT_PATHS)
TEST_PATHS: Final = (
    Path("tests/test_build_foundation_v2.py"),
    Path("tests/wordpress_local_preview"),
    Path("tests/wordpress_mcp_v1"),
    Path("tests/wordpress_seo_audit_v1"),
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
    for relative in RUNTIME_FILES:
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


def repo_artifact_registry() -> dict[str, object]:
    try:
        measurement = json.loads(
            read_regular(ROOT, MEASUREMENT_MANIFEST_PATH.as_posix()).decode(
                "utf-8", errors="strict"
            )
        )
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_V1_MEASUREMENT_MANIFEST_INVALID")
    if (
        type(measurement) is not dict
        or measurement.get("schema")
        != "RAOS_EDITORIAL_MEASUREMENT_RUNTIME_MANIFEST_V1"
        or measurement.get("artifact_id") != "raos-editorial-measurement-v1"
        or measurement.get("plugin_slug") != "raos-editorial-measurement"
        or measurement.get("plugin_version") != "1.0.0"
        or type(measurement.get("package_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", measurement["package_sha256"]) is None
    ):
        fail("WORDPRESS_MCP_V1_MEASUREMENT_MANIFEST_INVALID")
    abilities_sha256 = sha256(package_bytes(plugin_payloads()))
    return {
        "schema": "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1",
        "artifacts": [
            {
                "artifact_id": REPO_ARTIFACT_ID,
                "package_sha256": abilities_sha256,
                "slug": PLUGIN_SLUG,
                "version": PLUGIN_VERSION,
            },
            {
                "artifact_id": measurement["artifact_id"],
                "package_sha256": measurement["package_sha256"],
                "slug": measurement["plugin_slug"],
                "version": measurement["plugin_version"],
            },
        ],
    }


def write_manifest() -> None:
    payload = canonical_json(runtime_manifest())
    MANIFEST.write_bytes(payload)
    REGISTRY.write_bytes(canonical_json(repo_artifact_registry()))


def check_manifest() -> None:
    expected = canonical_json(runtime_manifest())
    try:
        actual = MANIFEST.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_V1_MANIFEST_MISSING")
    if actual != expected:
        fail("WORDPRESS_MCP_V1_MANIFEST_DRIFT")
    try:
        actual_registry = REGISTRY.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_V1_REGISTRY_MISSING")
    if actual_registry != canonical_json(repo_artifact_registry()):
        fail("WORDPRESS_MCP_V1_REGISTRY_DRIFT")


def write_package() -> None:
    payload = package_bytes(plugin_payloads())
    for target in (OUTPUT, REPO_OUTPUT):
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(target.parent, 0o700)
        temporary = target.with_suffix(".zip.tmp")
        temporary.write_bytes(payload)
        os.chmod(temporary, 0o600)
        temporary.replace(target)


def check_package() -> None:
    expected = package_bytes(plugin_payloads())
    for target in (OUTPUT, REPO_OUTPUT):
        try:
            actual = target.read_bytes()
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
