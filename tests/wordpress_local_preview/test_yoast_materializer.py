from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MATERIALIZER = (
    ROOT / "changes/wordpress-local-preview-v1/bin/materialize_yoast.py"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    archive_path = tmp_path / "wordpress-seo.28.3.zip"
    checksums: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as archive:
        for index in range(1952):
            relative = "wp-seo.php" if index == 0 else f"vendor/file-{index:04d}.php"
            payload = f"<?php // fixture {index}\n".encode()
            info = zipfile.ZipInfo(f"wordpress-seo/{relative}")
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, payload)
            checksums[relative] = {"sha256": _sha256(payload)}
    checksum_path = tmp_path / "checksums.json"
    checksum_payload = json.dumps(
        {"files": checksums, "plugin": "wordpress-seo", "version": "28.3"},
        sort_keys=True,
    ).encode()
    checksum_path.write_bytes(checksum_payload)
    archive_payload = archive_path.read_bytes()
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "archive": {
                    "byte_length": len(archive_payload),
                    "sha256": _sha256(archive_payload),
                },
                "official_checksum_api": {
                    "manifest_byte_length": len(checksum_payload),
                    "manifest_sha256": _sha256(checksum_payload),
                },
                "plugin_slug": "wordpress-seo",
                "schema": "RAOS_WORDPRESS_PLUGIN_LOCK_V1",
                "version": "28.3",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return archive_path, checksum_path, lock_path


def _run(
    archive_path: Path,
    checksum_path: Path,
    lock_path: Path,
    output_parent: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(MATERIALIZER),
            "--archive",
            str(archive_path),
            "--checksums",
            str(checksum_path),
            "--lock",
            str(lock_path),
            "--output-parent",
            str(output_parent),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_materializer_is_reproducible_and_validates_every_file(tmp_path: Path) -> None:
    archive_path, checksum_path, lock_path = _inputs(tmp_path)
    output_parent = tmp_path / "plugins"

    first = _run(archive_path, checksum_path, lock_path, output_parent)
    second = _run(archive_path, checksum_path, lock_path, output_parent)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == "RAOS_WORDPRESS_PREVIEW_YOAST_28_3_READY\n"
    materialized = output_parent / "wordpress-seo"
    assert (materialized / "wp-seo.php").is_file()
    assert len([path for path in materialized.rglob("*") if path.is_file()]) == 1952


def test_materializer_rejects_archive_tampering(tmp_path: Path) -> None:
    archive_path, checksum_path, lock_path = _inputs(tmp_path)
    payload = bytearray(archive_path.read_bytes())
    payload[-1] ^= 1
    archive_path.write_bytes(payload)

    result = _run(archive_path, checksum_path, lock_path, tmp_path / "plugins")

    assert result.returncode == 69
    assert result.stderr == "RAOS_WORDPRESS_PREVIEW_YOAST_LOCK_MISMATCH\n"
    assert not (tmp_path / "plugins/wordpress-seo").exists()
