#!/usr/bin/env python3
"""Create deterministic, disposable theme/plugin artifacts for WordPress E2E."""

from __future__ import annotations

import base64
import importlib.util
import io
import json
from pathlib import Path
import re
import stat
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[3]
OPERATOR_PATH = ROOT / "scripts/raos_wordpress_deployment_operator.py"
SPEC = importlib.util.spec_from_file_location(
    "raos_wordpress_e2e_operator", OPERATOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def write_private(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def zip_payload(slug: str, filename: str, payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        info = zipfile.ZipInfo(f"{slug}/{filename}", operator.ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(
            info,
            payload,
            compress_type=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        )
    return output.getvalue()


def plugin_release(
    slug: str, artifact_id: str, body: bytes
) -> tuple[bytes, dict[str, object]]:
    header = (
        b"<?php\n/*\n"
        b"Plugin Name: RAOS Disposable E2E Plugin\n"
        b"Version: 1.0.0\n"
        b"Requires at least: 7.1\n"
        b"Requires PHP: 8.1\n"
        b"*/\n"
    )
    payload = zip_payload(slug, f"{slug}.php", header + body)
    manifest, manifest_hash, version, migration_safe = operator.validate_package(
        payload, kind="plugin", slug=slug, expected_version="1.0.0"
    )
    assert migration_safe is True
    descriptor: dict[str, object] = {
        "schema": "CodePackageV1",
        "kind": "plugin",
        "source": "repo_artifact",
        "artifact_id": artifact_id,
        "git_commit": None,
        "slug": slug,
        "old_version": None,
        "new_version": version,
        "package_sha256": operator.sha256(payload),
        "file_manifest_sha256": manifest_hash,
        "file_manifest": manifest,
        "activation_intent": "activate",
        "migration_assessment": "NO_IRREVERSIBLE_MIGRATION_SIGNALS",
        "automatic_apply_eligible": True,
    }
    return payload, descriptor


def baseline_theme(current: bytes) -> bytes:
    output = io.BytesIO()
    replaced = False
    with zipfile.ZipFile(io.BytesIO(current), "r") as source:
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as target:
            for source_info in sorted(
                source.infolist(), key=lambda item: item.filename
            ):
                payload = source.read(source_info)
                if source_info.filename == "kurashinoshirube-child/style.css":
                    payload, count = re.subn(
                        rb"(?im)^Version:\s*[^\r\n]+",
                        b"Version: 0.0.1",
                        payload,
                        count=1,
                    )
                    replaced = count == 1
                info = zipfile.ZipInfo(source_info.filename, operator.ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                target.writestr(
                    info,
                    payload,
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    assert replaced
    return output.getvalue()


def proposal(
    kind: str, payload: bytes, descriptor: dict[str, object]
) -> dict[str, object]:
    return {
        "kind": kind,
        "code_package": descriptor,
        "package_base64": base64.b64encode(payload).decode("ascii"),
    }


def main() -> int:
    if len(sys.argv) != 2:
        return 64
    output_directory = Path(sys.argv[1]).resolve()
    output_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    output_directory.chmod(stat.S_IRWXU)

    theme_payload, theme_descriptor = operator.theme_package()
    baseline = baseline_theme(theme_payload)
    baseline_path = output_directory / "kurashinoshirube-child-baseline.zip"
    write_private(baseline_path, baseline)

    safe_payload, safe_descriptor = plugin_release(
        "raos-e2e-safe-plugin",
        "raos-e2e-safe-plugin-v1",
        b"function raos_e2e_safe_plugin_loaded() { return true; }\n",
    )
    broken_payload, broken_descriptor = plugin_release(
        "raos-e2e-broken-plugin",
        "raos-e2e-broken-plugin-v1",
        b"function raos_e2e_broken_plugin( {\n",
    )
    bundle = {
        "schema": "RAOS_WORDPRESS_E2E_CODE_ARTIFACTS_V1",
        "theme": proposal("theme_release", theme_payload, theme_descriptor),
        "plugin_success": proposal("plugin_change", safe_payload, safe_descriptor),
        "plugin_rollback": proposal("plugin_change", broken_payload, broken_descriptor),
    }
    bundle_path = output_directory / "artifacts.json"
    write_private(
        bundle_path,
        (json.dumps(bundle, separators=(",", ":"), sort_keys=True) + "\n").encode(
            "ascii"
        ),
    )
    print(bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
