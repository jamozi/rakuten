"""Deterministic, closed theme-source and package tests for ST-1703."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_st1703_self_hosted_theme as theme  # noqa: E402


def _isolated_theme(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / theme.THEME_SLUG
    shutil.copytree(theme.THEME_ROOT, target)
    monkeypatch.setattr(theme, "THEME_ROOT", target)
    monkeypatch.setattr(theme, "MANIFEST_PATH", target / "raos-assets.v1.json")
    monkeypatch.setattr(theme, "OUTPUT_PATH", tmp_path / "generated" / "theme.zip")
    return target


def _manifest(path: Path) -> dict[str, object]:
    return json.loads((path / "raos-assets.v1.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, value: dict[str, object]) -> None:
    (path / "raos-assets.v1.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _synthetic_webp(seed: int) -> bytes:
    chunk = b"VP8 " + (10).to_bytes(4, "little") + bytes([seed]) * 10
    body = b"WEBP" + chunk
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def _complete_assets(path: Path) -> None:
    manifest = _manifest(path)
    images = manifest["required_images"]
    assert isinstance(images, list)
    for index, image_value in enumerate(images, start=1):
        assert isinstance(image_value, dict)
        relative = image_value["path"]
        assert isinstance(relative, str)
        payload = _synthetic_webp(index)
        image_path = path / relative
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(payload)
        image_value["status"] = "FINAL"
        image_value["sha256"] = hashlib.sha256(payload).hexdigest()
    _write_manifest(path, manifest)


def test_real_source_is_valid_but_final_assets_block_package() -> None:
    result = theme.source_check()
    assert result == {
        "asset_status": "PENDING_FINAL_ASSETS",
        "network_requests": 0,
        "package_ready": False,
        "pending_asset_count": 2,
        "source_file_count": 10,
        "status": "SOURCE_VALID",
        "theme_slug": "kurashinoshirube-child",
    }
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_MISSING"):
        theme.package_bytes()


def test_reveal_is_progressive_enhancement_with_failure_and_motion_fallbacks() -> None:
    stylesheet = (theme.THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    script = (theme.THEME_ROOT / "assets/theme.js").read_text(encoding="utf-8")
    default_rule = stylesheet.split(".raos-reveal {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "opacity: 1;" in default_rule
    assert "transform: none;" in default_rule
    assert ".raos-reveal-ready .raos-reveal:not(.is-visible)" in stylesheet
    reduced = stylesheet.split("@media (prefers-reduced-motion: reduce)", maxsplit=1)[1]
    assert ".raos-reveal-ready .raos-reveal" in reduced
    assert 'root.classList.add("raos-reveal-ready")' in script
    assert 'root.classList.remove("raos-reveal-ready")' in script
    assert script.index("observer = new IntersectionObserver") < script.index(
        'root.classList.add("raos-reveal-ready")'
    )
    assert "revealAll();" in script


def test_verified_theme_snapshot_does_not_reopen_mutated_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    payloads = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    (root / "assets/theme.css").write_bytes(b"unreviewed replacement")
    result = theme.source_check_from_verified_files(payloads)
    assert result["status"] == "SOURCE_VALID"
    assert result["package_ready"] is False


def test_complete_fixture_packages_deterministically_and_checks_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)

    first = theme.package_bytes()
    second = theme.package_bytes()
    assert first == second
    theme._write_package(first)
    before = theme.OUTPUT_PATH.stat().st_mtime_ns
    assert theme.main(["--check"]) == 0
    assert theme.OUTPUT_PATH.stat().st_mtime_ns == before
    assert '"status": "PACKAGE_VALID"' in capsys.readouterr().out

    with zipfile.ZipFile(theme.OUTPUT_PATH) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith("kurashinoshirube-child/") for name in names)
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()
        )
        embedded = json.loads(
            archive.read("kurashinoshirube-child/raos-assets.v1.json")
        )
        assert embedded["generated_by"] == "scripts/build_st1703_self_hosted_theme.py"
        assert embedded["package_command"] == (
            "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile "
            "theme-package"
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("traversal", "THEME_PATH_INVALID"),
        ("remote", "THEME_REMOTE_LOAD_FORBIDDEN"),
        ("motion", "THEME_ACCESSIBILITY_INVALID"),
        ("progressive", "THEME_ACCESSIBILITY_INVALID"),
    ],
)
def test_source_checks_reject_traversal_remote_load_and_missing_reduced_motion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    if mutation == "traversal":
        manifest = _manifest(root)
        source_files = manifest["source_files"]
        assert isinstance(source_files, list)
        source_files[0] = "../escape.css"
        _write_manifest(root, manifest)
    elif mutation == "remote":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + '\n.remote { background: url("https://untrusted.invalid/a.png"); }\n',
            encoding="utf-8",
        )
    elif mutation == "motion":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8").replace(
                "@media (prefers-reduced-motion: reduce)",
                "@media (min-width: 1px)",
            ),
            encoding="utf-8",
        )
    else:
        script = root / "assets/theme.js"
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                'root.classList.remove("raos-reveal-ready")',
                'root.classList.remove("broken-reveal-state")',
            ),
            encoding="utf-8",
        )
    with pytest.raises(theme.ThemeBuildFailure, match=code):
        theme.source_check()


def test_final_asset_hash_and_package_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert isinstance(images, list) and isinstance(images[0], dict)
    images[0]["sha256"] = "0" * 64
    _write_manifest(root, manifest)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_INVALID"):
        theme.package_bytes()

    _complete_assets(root)
    theme.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    theme.OUTPUT_PATH.write_bytes(b"stale")
    assert theme.main(["--check"]) == 2
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out


def test_source_snapshot_rejects_symlinked_ancestor_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    outside = tmp_path / "outside.css"
    outside.write_text("safe outside bytes", encoding="utf-8")
    source = root / "assets/theme.css"
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FILE_INVALID"):
        theme.source_check()

    shutil.rmtree(root)
    physical = tmp_path / "physical-theme"
    shutil.copytree(
        theme.REPOSITORY_ROOT
        / "changes/st-1703/self-hosted-minimum-start-v1/theme"
        / theme.THEME_SLUG,
        physical,
    )
    linked = tmp_path / "linked-theme"
    linked.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(theme, "THEME_ROOT", linked)
    monkeypatch.setattr(theme, "MANIFEST_PATH", linked / "raos-assets.v1.json")
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_ROOT_INVALID"):
        theme.source_check()


def test_snapshot_detects_file_replacement_after_bounded_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    original = theme._read_regular_at
    changed = False

    def replacing_read(
        root_fd: int,
        relative: str,
        *,
        max_bytes: int = theme.MAX_FILE_BYTES,
        error_code: str = "THEME_FILE_INVALID",
    ) -> tuple[bytes, tuple[int, ...]]:
        nonlocal changed
        result = original(root_fd, relative, max_bytes=max_bytes, error_code=error_code)
        if relative == "assets/theme.css" and not changed:
            changed = True
            stylesheet = root / relative
            replacement = stylesheet.with_suffix(".css.replacement")
            replacement.write_bytes(result[0] + b"\n")
            os.replace(replacement, stylesheet)
        return result

    monkeypatch.setattr(theme, "_read_regular_at", replacing_read)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_INVENTORY_CHANGED"):
        theme.source_check()


def test_package_archives_each_validated_input_without_reopening(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    original = theme._read_regular_at
    reads: dict[str, int] = {}

    def counting_read(
        root_fd: int,
        relative: str,
        *,
        max_bytes: int = theme.MAX_FILE_BYTES,
        error_code: str = "THEME_FILE_INVALID",
    ) -> tuple[bytes, tuple[int, ...]]:
        reads[relative] = reads.get(relative, 0) + 1
        return original(root_fd, relative, max_bytes=max_bytes, error_code=error_code)

    monkeypatch.setattr(theme, "_read_regular_at", counting_read)
    assert theme.package_bytes()
    assert reads
    assert set(reads.values()) == {1}


def test_final_asset_is_validated_during_source_readiness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert isinstance(images, list) and isinstance(images[0], dict)
    image_path = images[0]["path"]
    assert isinstance(image_path, str)
    (root / image_path).write_bytes(b"not-a-webp")
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_INVALID"):
        theme.source_check()


def test_output_check_rejects_symlink_and_oversize_without_following(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    output = theme.OUTPUT_PATH
    output.parent.mkdir(parents=True)
    victim = tmp_path / "victim.zip"
    victim.write_bytes(b"do-not-read-or-change")
    output.symlink_to(victim)
    assert theme.main(["--check"]) == 2
    assert victim.read_bytes() == b"do-not-read-or-change"
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out

    output.unlink()
    with output.open("wb") as stream:
        stream.truncate(theme.MAX_PACKAGE_BYTES + 1)
    assert theme.main(["--check"]) == 2
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out


def test_package_write_fsyncs_created_parent_and_published_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_fsync = os.fsync
    fsync_modes: list[int] = []

    def recording_fsync(descriptor: int) -> None:
        fsync_modes.append(os.fstat(descriptor).st_mode)
        original_fsync(descriptor)

    monkeypatch.setattr(theme.os, "fsync", recording_fsync)
    theme._write_package(payload)
    assert sum(stat.S_ISDIR(mode) for mode in fsync_modes) >= 2
    assert sum(stat.S_ISREG(mode) for mode in fsync_modes) >= 1


def test_package_write_rejects_post_replace_identity_swap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_replace = os.replace

    def replacing_output(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        attacker = ".hostile-replacement"
        descriptor = os.open(
            attacker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(descriptor, b"hostile")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        original_replace(
            attacker,
            destination,
            src_dir_fd=dst_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(theme.os, "replace", replacing_output)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
