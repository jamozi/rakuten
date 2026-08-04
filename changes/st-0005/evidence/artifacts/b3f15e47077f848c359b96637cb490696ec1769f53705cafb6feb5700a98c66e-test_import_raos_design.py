"""TST-001 coverage for the immutable RAOS design import."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import stat
from zipfile import ZipFile, ZipInfo

import pytest

from scripts import import_raos_design as design


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPOSITORY_ROOT / "docs"
COMPLETE_ARCHIVE = REPOSITORY_ROOT / "zip" / "RAOS_complete_design_package_v1.0.zip"


def tree_hashes(root: Path) -> dict[Path, str]:
    return {
        path.relative_to(root): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def load_imported_files() -> dict[str, dict[str, object]]:
    manifest = json.loads((DOCS / "manifest.json").read_text(encoding="utf-8"))
    return {item["package_path"]: item for item in manifest["files"]}


def test_repository_import_verifies(capsys: pytest.CaptureFixture[str]) -> None:
    design.verify_import(DOCS)
    result = json.loads(capsys.readouterr().out)

    assert result == {
        "imported_files": 105,
        "read_order": "PASS",
        "source_archives": 6,
        "status": "PASS",
        "story_id": "ST-0001",
        "verified_package_checksums": 104,
        "verified_package_manifest_entries": 103,
    }


def test_imported_evidence_disables_git_eol_normalization() -> None:
    attributes = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".gitattributes")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    assert "/docs/canonical/** -text" in attributes
    assert "/docs/upstream/** -text" in attributes
    assert "/docs/manifest.json -text" in attributes
    assert "/zip/*.zip -text" in attributes


@pytest.mark.parametrize("mutation", ["added", "symlink", "directory"])
def test_source_archive_inventory_rejects_unlisted_or_nonregular_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    copied_root = tmp_path / "repository"
    shutil.copytree(REPOSITORY_ROOT / "zip", copied_root / "zip")
    target = copied_root / "zip" / "unexpected.zip"
    if mutation == "added":
        target.write_bytes(b"not listed\n")
        expected_error = "archive file set differs"
    elif mutation == "symlink":
        target.symlink_to(COMPLETE_ARCHIVE)
        expected_error = "non-regular source archive entry"
    else:
        target.mkdir()
        expected_error = "non-regular source archive entry"
    monkeypatch.setattr(design, "REPOSITORY_ROOT", copied_root)
    monkeypatch.setattr(
        design,
        "DEFAULT_ARCHIVE",
        copied_root / "zip" / COMPLETE_ARCHIVE.name,
    )

    with pytest.raises(design.DesignPackageError, match=expected_error):
        design.verify_import(DOCS, require_readme=False)


def test_clean_import_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated = tmp_path / "docs"
    design.import_package(COMPLETE_ARCHIVE, generated)
    capsys.readouterr()

    assert tree_hashes(generated / "canonical") == tree_hashes(DOCS / "canonical")
    assert tree_hashes(generated / "upstream") == tree_hashes(DOCS / "upstream")
    assert (generated / "manifest.json").read_bytes() == (
        DOCS / "manifest.json"
    ).read_bytes()

    with pytest.raises(design.DesignPackageError, match="already exists"):
        design.import_package(COMPLETE_ARCHIVE, generated)


@pytest.mark.parametrize("mutation", ["modified", "missing", "added", "symlink"])
def test_imported_tree_tampering_is_rejected(
    tmp_path: Path,
    mutation: str,
) -> None:
    copied = tmp_path / "docs"
    shutil.copytree(DOCS, copied)
    target = copied / "canonical" / "START_HERE.md"

    if mutation == "modified":
        target.chmod(0o644)
        target.write_bytes(target.read_bytes() + b"\nchanged\n")
    elif mutation == "missing":
        target.unlink()
    elif mutation == "added":
        (copied / "canonical" / "unexpected.txt").write_text(
            "unexpected",
            encoding="utf-8",
        )
    else:
        (copied / "canonical" / "unexpected-link").symlink_to(target)

    with pytest.raises(design.DesignPackageError):
        design.verify_import(copied)


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "traversal.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            f"{design.PACKAGE_ROOT}/../../outside.txt",
            "blocked",
        )

    with ZipFile(archive_path) as archive:
        with pytest.raises(design.DesignPackageError, match="Unsafe ZIP entry"):
            design.collect_zip_entries(archive)


def test_zip_symlink_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    link = ZipInfo(f"{design.PACKAGE_ROOT}/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "target")

    with ZipFile(archive_path) as archive:
        with pytest.raises(design.DesignPackageError, match="not a regular"):
            design.collect_zip_entries(archive)


def test_case_insensitive_zip_collision_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "collision.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{design.PACKAGE_ROOT}/Artifact.txt", "first")
        archive.writestr(f"{design.PACKAGE_ROOT}/artifact.txt", "second")

    with ZipFile(archive_path) as archive:
        with pytest.raises(
            design.DesignPackageError,
            match="Case-insensitive ZIP path collision",
        ):
            design.collect_zip_entries(archive)


def test_zip_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "mismatch.zip"
    expected = sha256(b"expected").hexdigest()
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            f"{design.PACKAGE_ROOT}/{design.CHECKSUM_FILE}",
            f"{expected}  artifact.txt\n",
        )
        archive.writestr(
            f"{design.PACKAGE_ROOT}/artifact.txt",
            b"actual",
        )

    with ZipFile(archive_path) as archive:
        entries = design.collect_zip_entries(archive)
        with pytest.raises(design.DesignPackageError, match="Checksum mismatch"):
            design.verify_archive(archive, entries)


def test_manifest_cannot_remap_package_path() -> None:
    manifest: dict[str, object] = {
        "files": [
            {
                "package_path": "upstream/artifact.zip",
                "repository_path": "canonical/artifact.zip",
                "bytes": 0,
                "sha256": "0" * 64,
            }
        ]
    }

    with pytest.raises(design.DesignPackageError, match="path mapping is invalid"):
        design.manifest_files(manifest)


def test_checksum_list_must_cover_exact_imported_set(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    artifact_digest = sha256(b"artifact").hexdigest()
    (canonical / design.CHECKSUM_FILE).write_text(
        f"{artifact_digest}  artifact.txt\n",
        encoding="utf-8",
    )
    imported = {
        "artifact.txt": {
            "bytes": 8,
            "sha256": artifact_digest,
        },
        design.CHECKSUM_FILE: {
            "bytes": 0,
            "sha256": "0" * 64,
        },
        "unexpected.txt": {
            "bytes": 0,
            "sha256": "0" * 64,
        },
    }

    with pytest.raises(design.DesignPackageError, match="file set differs"):
        design.verify_package_checksums(tmp_path, imported)


def test_producer_manifest_must_cover_exact_source_set() -> None:
    imported = load_imported_files()
    producer = json.loads(
        (
            DOCS / "canonical" / "00_master" / "RAOS_package_manifest_v1.0.json"
        ).read_text(encoding="utf-8")
    )
    producer["files"] = producer["files"][:-1]

    with pytest.raises(design.DesignPackageError, match="file set differs"):
        design.verify_producer_manifest(producer, imported)


def test_readme_required_artifacts_must_be_in_order(tmp_path: Path) -> None:
    for relative_path in design.REQUIRED_READ_ORDER:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    links = [f"[entry]({path})" for path in reversed(design.REQUIRED_READ_ORDER)]
    (tmp_path / "README.md").write_text("\n".join(links), encoding="utf-8")

    with pytest.raises(design.DesignPackageError, match="reading order"):
        design.verify_read_order(tmp_path)
