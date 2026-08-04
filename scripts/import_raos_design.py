#!/usr/bin/env python3
"""Import and verify the immutable RAOS v1.0 design package.

The complete package contains both the canonical v1.0 design and the six
historical upstream archives.  This command keeps those two classes separate
in the repository while preserving every package byte and checksum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from typing import IO, Sequence
from zipfile import BadZipFile, ZipFile, ZipInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = REPOSITORY_ROOT / "zip" / "RAOS_complete_design_package_v1.0.zip"
DEFAULT_DESTINATION = REPOSITORY_ROOT / "docs"
PACKAGE_ROOT = "RAOS_complete_design_v1.0"
CHECKSUM_FILE = "SHA256SUMS.txt"
IMPORT_MANIFEST = "manifest.json"
CHECKSUM_PATTERN = re.compile(r"^([0-9a-f]{64})  (.+)$")
BUFFER_SIZE = 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
REQUIRED_READ_ORDER = (
    "canonical/00_master/RAOS_MASTER_README_v1.0.md",
    "canonical/08_codex/AGENTS.md",
    "canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    "canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
    "canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
    "canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
    "canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
)


class DesignPackageError(RuntimeError):
    """Raised when the design package or imported tree is invalid."""


def sha256_stream(stream: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(BUFFER_SIZE):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def repository_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def validate_zip_path(info: ZipInfo) -> PurePosixPath | None:
    name = info.filename
    if info.flag_bits & 0x1:
        raise DesignPackageError(f"Encrypted ZIP entry is not allowed: {name!r}")
    if "\\" in name:
        raise DesignPackageError(f"ZIP entry uses a backslash: {name!r}")

    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise DesignPackageError(f"Unsafe ZIP entry: {name!r}")
    if not path.parts or path.parts[0] != PACKAGE_ROOT:
        raise DesignPackageError(f"ZIP entry is outside {PACKAGE_ROOT}: {name!r}")

    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}:
        raise DesignPackageError(f"ZIP entry is not a regular file/directory: {name!r}")

    if info.is_dir():
        return None
    if len(path.parts) == 1:
        raise DesignPackageError(f"ZIP entry has no package-relative path: {name!r}")
    if info.file_size > MAX_MEMBER_BYTES:
        raise DesignPackageError(f"ZIP entry is too large: {name!r}")
    if (
        info.file_size > BUFFER_SIZE
        and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO
    ):
        raise DesignPackageError(
            f"ZIP entry has a suspicious compression ratio: {name!r}"
        )
    return PurePosixPath(*path.parts[1:])


def collect_zip_entries(archive: ZipFile) -> dict[PurePosixPath, ZipInfo]:
    entries: dict[PurePosixPath, ZipInfo] = {}
    casefolded: dict[str, PurePosixPath] = {}
    total_size = 0
    for info in archive.infolist():
        relative = validate_zip_path(info)
        if relative is None:
            continue
        if relative in entries:
            raise DesignPackageError(f"Duplicate ZIP entry: {relative}")
        folded = relative.as_posix().casefold()
        if folded in casefolded:
            raise DesignPackageError(
                "Case-insensitive ZIP path collision: "
                f"{casefolded[folded]} and {relative}"
            )
        total_size += info.file_size
        if total_size > MAX_PACKAGE_BYTES:
            raise DesignPackageError("ZIP package exceeds the safe size limit")
        entries[relative] = info
        casefolded[folded] = relative
    return entries


def parse_checksums(text: str) -> dict[PurePosixPath, str]:
    checksums: dict[PurePosixPath, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = CHECKSUM_PATTERN.fullmatch(line)
        if not match:
            raise DesignPackageError(
                f"Malformed {CHECKSUM_FILE} line {line_number}: {line!r}"
            )
        digest, raw_path = match.groups()
        path = PurePosixPath(raw_path)
        if path.is_absolute() or ".." in path.parts or "\\" in raw_path:
            raise DesignPackageError(
                f"Unsafe path in {CHECKSUM_FILE} line {line_number}: {raw_path!r}"
            )
        if path in checksums:
            raise DesignPackageError(f"Duplicate checksum path: {raw_path}")
        checksums[path] = digest
    if not checksums:
        raise DesignPackageError(f"{CHECKSUM_FILE} is empty")
    return checksums


def destination_path(package_path: PurePosixPath) -> PurePosixPath:
    if package_path.parts[0] == "upstream":
        if len(package_path.parts) == 1:
            raise DesignPackageError("Upstream package path has no filename")
        return PurePosixPath("upstream", *package_path.parts[1:])
    return PurePosixPath("canonical", *package_path.parts)


def verify_archive(
    archive: ZipFile,
    entries: dict[PurePosixPath, ZipInfo],
) -> dict[PurePosixPath, str]:
    checksum_path = PurePosixPath(CHECKSUM_FILE)
    checksum_info = entries.get(checksum_path)
    if checksum_info is None:
        raise DesignPackageError(f"Package does not contain {CHECKSUM_FILE}")

    with archive.open(checksum_info) as stream:
        try:
            checksum_text = stream.read().decode("utf-8")
        except UnicodeDecodeError as error:
            raise DesignPackageError(f"{CHECKSUM_FILE} is not UTF-8") from error
    checksums = parse_checksums(checksum_text)

    unlisted = set(entries) - set(checksums) - {checksum_path}
    missing = set(checksums) - set(entries)
    if unlisted:
        raise DesignPackageError(
            "Package contains unlisted files: "
            + ", ".join(str(path) for path in sorted(unlisted))
        )
    if missing:
        raise DesignPackageError(
            "Checksum file references missing files: "
            + ", ".join(str(path) for path in sorted(missing))
        )

    for path, expected_digest in checksums.items():
        with archive.open(entries[path]) as stream:
            actual_digest, _ = sha256_stream(stream)
        if actual_digest != expected_digest:
            raise DesignPackageError(
                f"Checksum mismatch for {path}: "
                f"expected {expected_digest}, got {actual_digest}"
            )
    return checksums


def discover_source_archives(
    complete_archive: Path,
    imported_files: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    complete_digest, complete_size = sha256_file(complete_archive)
    sources: list[dict[str, object]] = [
        {
            "path": repository_relative(complete_archive),
            "role": "complete_design",
            "bytes": complete_size,
            "sha256": complete_digest,
        }
    ]

    zip_directory = complete_archive.parent
    for candidate in sorted(zip_directory.glob("RAOS_[0-9][0-9]_*.zip")):
        destination = f"upstream/{candidate.name}"
        imported = imported_files.get(destination)
        if imported is None:
            raise DesignPackageError(
                f"Standalone source has no matching imported upstream archive: "
                f"{candidate.name}"
            )
        digest, size = sha256_file(candidate)
        if digest != imported["sha256"] or size != imported["bytes"]:
            raise DesignPackageError(
                f"Standalone source differs from canonical upstream archive: "
                f"{candidate.name}"
            )
        sources.append(
            {
                "path": repository_relative(candidate),
                "role": "standalone_upstream",
                "bytes": size,
                "sha256": digest,
            }
        )
    return sources


def make_manifest(
    archive_path: Path,
    extracted: list[dict[str, object]],
) -> dict[str, object]:
    indexed = {str(item["repository_path"]): item for item in extracted}
    package_manifest_path = "canonical/00_master/RAOS_package_manifest_v1.0.json"
    package_manifest_file = indexed.get(package_manifest_path)
    if package_manifest_file is None:
        raise DesignPackageError("Canonical package manifest was not imported")

    sources = discover_source_archives(archive_path, indexed)
    return {
        "schema_version": 1,
        "story_id": "ST-0001",
        "package": {
            "name": "RAOS Complete Design Package",
            "version": "1.0",
            "root": PACKAGE_ROOT,
            "package_manifest": package_manifest_path,
            "package_checksums": f"canonical/{CHECKSUM_FILE}",
        },
        "source_archives": sources,
        "layout": {
            "canonical": "canonical",
            "upstream": "upstream",
            "policy": "Imported files are immutable; revisions must be new artifacts.",
        },
        "files": extracted,
    }


def write_bytes_read_only(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o444)


def import_package(archive_path: Path, destination: Path) -> None:
    if destination.exists():
        raise DesignPackageError(
            f"Destination already exists: {destination}. "
            "Use the verify command for an existing import."
        )
    if not archive_path.is_file():
        raise DesignPackageError(f"Archive does not exist: {archive_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=".raos-design-import-",
            dir=destination.parent,
        )
    )
    try:
        with ZipFile(archive_path) as archive:
            entries = collect_zip_entries(archive)
            verify_archive(archive, entries)
            extracted: list[dict[str, object]] = []

            for package_path, info in sorted(
                entries.items(), key=lambda item: item[0].as_posix()
            ):
                repository_path = destination_path(package_path)
                output_path = staging.joinpath(*repository_path.parts)
                with archive.open(info) as stream:
                    data = stream.read()
                write_bytes_read_only(output_path, data)
                extracted.append(
                    {
                        "package_path": package_path.as_posix(),
                        "repository_path": repository_path.as_posix(),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )

        manifest = make_manifest(archive_path, extracted)
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        write_bytes_read_only(staging / IMPORT_MANIFEST, manifest_bytes)
        staging.replace(destination)
    except (BadZipFile, OSError, ValueError) as error:
        raise DesignPackageError(str(error)) from error
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    verify_import(destination, require_readme=False)


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DesignPackageError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise DesignPackageError(f"JSON root must be an object: {path}")
    return value


def manifest_files(manifest: dict[str, object]) -> list[dict[str, object]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise DesignPackageError("Import manifest files must be an array")
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise DesignPackageError(f"Import manifest file {index} is not an object")
        try:
            package_path = item["package_path"]
            repository_path = item["repository_path"]
            size = item["bytes"]
            digest = item["sha256"]
        except KeyError as error:
            raise DesignPackageError(
                f"Import manifest file {index} is missing {error.args[0]}"
            ) from error
        if (
            not isinstance(package_path, str)
            or not isinstance(repository_path, str)
            or not isinstance(size, int)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise DesignPackageError(
                f"Import manifest file {index} has invalid field types"
            )
        package_relative = PurePosixPath(package_path)
        if (
            not package_relative.parts
            or package_relative.is_absolute()
            or ".." in package_relative.parts
            or "\\" in package_path
        ):
            raise DesignPackageError(
                f"Import manifest has unsafe package path: {package_path}"
            )
        relative = PurePosixPath(repository_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] not in {"canonical", "upstream"}
        ):
            raise DesignPackageError(
                f"Import manifest has unsafe repository path: {repository_path}"
            )
        expected_repository_path = destination_path(package_relative).as_posix()
        if repository_path != expected_repository_path:
            raise DesignPackageError(
                "Import manifest path mapping is invalid: "
                f"{package_path} must map to {expected_repository_path}, "
                f"not {repository_path}"
            )
        normalized.append(item)
    return normalized


def verify_source_archives(
    source_archives: object,
    imported_by_path: dict[str, dict[str, object]],
) -> int:
    if not isinstance(source_archives, list) or not source_archives:
        raise DesignPackageError(
            "Import manifest source_archives must be a nonempty array"
        )

    archive_root = REPOSITORY_ROOT / "zip"
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise DesignPackageError(
            f"Source archive directory is missing/not regular: {archive_root}"
        )

    normalized_sources: list[tuple[Path, int, str, str]] = []
    expected_paths: set[Path] = set()
    expected_casefolded: dict[str, Path] = {}
    for index, source in enumerate(source_archives):
        if not isinstance(source, dict) or set(source) != {
            "path",
            "role",
            "bytes",
            "sha256",
        }:
            raise DesignPackageError(f"Source archive {index} is not an object")
        path_value = source.get("path")
        expected_size = source.get("bytes")
        expected_digest = source.get("sha256")
        role = source.get("role")
        if (
            not isinstance(path_value, str)
            or type(expected_size) is not int
            or expected_size < 0
            or not isinstance(expected_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
            or role not in {"complete_design", "standalone_upstream"}
        ):
            raise DesignPackageError(f"Source archive {index} has invalid fields")

        relative = PurePosixPath(path_value)
        if (
            relative.is_absolute()
            or "\\" in path_value
            or ".." in relative.parts
            or len(relative.parts) != 2
            or relative.parts[0] != "zip"
            or relative.suffix != ".zip"
        ):
            raise DesignPackageError(
                f"Source archive {index} has unsafe/noncanonical path: {path_value}"
            )
        repository_path = Path(*relative.parts)
        if repository_path in expected_paths:
            raise DesignPackageError(f"Duplicate source archive path: {path_value}")
        folded = relative.as_posix().casefold()
        if folded in expected_casefolded:
            raise DesignPackageError(
                "Case-insensitive source archive path collision: "
                f"{expected_casefolded[folded].as_posix()} and {path_value}"
            )
        expected_paths.add(repository_path)
        expected_casefolded[folded] = repository_path
        normalized_sources.append(
            (REPOSITORY_ROOT / repository_path, expected_size, expected_digest, role)
        )

    expected_complete = Path("zip") / DEFAULT_ARCHIVE.name
    complete_paths = {
        path.relative_to(REPOSITORY_ROOT)
        for path, _, _, role in normalized_sources
        if role == "complete_design"
    }
    if complete_paths != {expected_complete}:
        raise DesignPackageError(
            "Source archive inventory must contain exactly the canonical complete design "
            f"archive: {expected_complete.as_posix()}"
        )

    actual_paths: set[Path] = set()
    actual_casefolded: dict[str, Path] = {}
    for source_path in archive_root.iterdir():
        if source_path.is_symlink() or not source_path.is_file():
            raise DesignPackageError(
                f"Unexpected/non-regular source archive entry: {source_path}"
            )
        repository_path = source_path.relative_to(REPOSITORY_ROOT)
        folded = repository_path.as_posix().casefold()
        if folded in actual_casefolded:
            raise DesignPackageError(
                "Case-insensitive source archive path collision: "
                f"{actual_casefolded[folded].as_posix()} and "
                f"{repository_path.as_posix()}"
            )
        actual_casefolded[folded] = repository_path
        actual_paths.add(repository_path)

    if actual_paths != expected_paths:
        unexpected = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        details = []
        if unexpected:
            details.append(
                "unexpected=" + ",".join(path.as_posix() for path in unexpected)
            )
        if missing:
            details.append("missing=" + ",".join(path.as_posix() for path in missing))
        raise DesignPackageError(
            "Source archive file set differs: " + " ".join(details)
        )

    verified = 0
    for source_path, expected_size, expected_digest, role in normalized_sources:
        if source_path.is_symlink() or not source_path.is_file():
            raise DesignPackageError(
                f"Source archive is missing/not regular: {source_path}"
            )
        actual_digest, actual_size = sha256_file(source_path)
        if actual_digest != expected_digest or actual_size != expected_size:
            raise DesignPackageError(f"Source archive changed: {source_path}")

        if role == "standalone_upstream":
            imported = imported_by_path.get(f"upstream/{source_path.name}")
            if imported is None:
                raise DesignPackageError(
                    f"No imported file for standalone source: {source_path.name}"
                )
            if imported["sha256"] != actual_digest or imported["bytes"] != actual_size:
                raise DesignPackageError(
                    f"Standalone source and imported upstream differ: {source_path.name}"
                )
        verified += 1
    return verified


def verify_package_checksums(
    destination: Path,
    imported_by_package_path: dict[str, dict[str, object]],
) -> int:
    checksum_path = destination / "canonical" / CHECKSUM_FILE
    try:
        checksum_text = checksum_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DesignPackageError(
            f"Cannot read imported {CHECKSUM_FILE}: {error}"
        ) from error
    checksums = parse_checksums(checksum_text)
    expected_package_paths = {path.as_posix() for path in checksums} | {CHECKSUM_FILE}
    actual_package_paths = set(imported_by_package_path)
    if actual_package_paths != expected_package_paths:
        unexpected = sorted(actual_package_paths - expected_package_paths)
        missing = sorted(expected_package_paths - actual_package_paths)
        details = []
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise DesignPackageError(
            "Import manifest package file set differs from checksums: "
            + " ".join(details)
        )

    for package_path, expected_digest in checksums.items():
        item = imported_by_package_path.get(package_path.as_posix())
        if item is None:
            raise DesignPackageError(
                f"Package checksum path is absent from import manifest: {package_path}"
            )
        if item["sha256"] != expected_digest:
            raise DesignPackageError(
                f"Package checksum differs from import manifest: {package_path}"
            )
    return len(checksums)


def verify_producer_manifest(
    package_manifest: dict[str, object],
    imported_by_package_path: dict[str, dict[str, object]],
) -> int:
    producer_files = package_manifest.get("files")
    if not isinstance(producer_files, list):
        raise DesignPackageError("Canonical package manifest files must be an array")

    manifest_path = "00_master/RAOS_package_manifest_v1.0.json"
    expected_paths = set(imported_by_package_path) - {
        manifest_path,
        CHECKSUM_FILE,
    }
    actual_paths: set[str] = set()

    for index, item in enumerate(producer_files):
        if not isinstance(item, dict):
            raise DesignPackageError(
                f"Canonical package manifest file {index} is not an object"
            )
        package_path = item.get("path")
        size = item.get("bytes")
        digest = item.get("sha256")
        if (
            not isinstance(package_path, str)
            or not isinstance(size, int)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise DesignPackageError(
                f"Canonical package manifest file {index} has invalid fields"
            )
        if package_path in actual_paths:
            raise DesignPackageError(
                f"Canonical package manifest has duplicate path: {package_path}"
            )
        actual_paths.add(package_path)

        imported = imported_by_package_path.get(package_path)
        if imported is None:
            raise DesignPackageError(
                f"Canonical package manifest references missing file: {package_path}"
            )
        if imported["bytes"] != size or imported["sha256"] != digest:
            raise DesignPackageError(
                f"Canonical package manifest metadata differs: {package_path}"
            )

    if actual_paths != expected_paths:
        unexpected = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        details = []
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise DesignPackageError(
            "Canonical package manifest file set differs: " + " ".join(details)
        )
    return len(producer_files)


def verify_read_order(destination: Path) -> None:
    readme_path = destination / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DesignPackageError(f"Cannot read {readme_path}: {error}") from error

    previous_position = -1
    for relative_path in REQUIRED_READ_ORDER:
        target = destination / relative_path
        if not target.is_file():
            raise DesignPackageError(f"Required reading artifact is missing: {target}")
        link = f"]({relative_path})"
        position = readme.find(link)
        if position < 0:
            raise DesignPackageError(
                f"README does not link required reading artifact: {relative_path}"
            )
        if position <= previous_position:
            raise DesignPackageError(
                f"README reading order is incorrect at: {relative_path}"
            )
        previous_position = position


def verify_import(destination: Path, *, require_readme: bool = True) -> None:
    manifest_path = destination / IMPORT_MANIFEST
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("story_id") != "ST-0001":
        raise DesignPackageError("Unsupported import manifest")

    files = manifest_files(manifest)
    expected_paths: set[Path] = set()
    imported_by_path: dict[str, dict[str, object]] = {}
    imported_by_package_path: dict[str, dict[str, object]] = {}

    for item in files:
        repository_path = str(item["repository_path"])
        package_path = str(item["package_path"])
        if repository_path in imported_by_path:
            raise DesignPackageError(
                f"Duplicate repository path in import manifest: {repository_path}"
            )
        if package_path in imported_by_package_path:
            raise DesignPackageError(
                f"Duplicate package path in import manifest: {package_path}"
            )
        imported_by_path[repository_path] = item
        imported_by_package_path[package_path] = item
        expected_paths.add(Path(repository_path))

        path = destination / repository_path
        if path.is_symlink() or not path.is_file():
            raise DesignPackageError(
                f"Imported artifact is missing/not regular: {path}"
            )
        actual_digest, actual_size = sha256_file(path)
        if actual_digest != item["sha256"] or actual_size != item["bytes"]:
            raise DesignPackageError(f"Imported artifact changed: {path}")

    actual_paths: set[Path] = set()
    for directory_name in ("canonical", "upstream"):
        directory = destination / directory_name
        if not directory.is_dir():
            raise DesignPackageError(f"Imported directory is missing: {directory}")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise DesignPackageError(f"Symlink is not allowed in import: {path}")
            if path.is_file():
                actual_paths.add(path.relative_to(destination))

    unexpected = actual_paths - expected_paths
    missing = expected_paths - actual_paths
    if unexpected or missing:
        details = []
        if unexpected:
            details.append(
                "unexpected=" + ",".join(path.as_posix() for path in sorted(unexpected))
            )
        if missing:
            details.append(
                "missing=" + ",".join(path.as_posix() for path in sorted(missing))
            )
        raise DesignPackageError("Imported file set differs: " + " ".join(details))

    checksum_count = verify_package_checksums(
        destination,
        imported_by_package_path,
    )
    source_count = verify_source_archives(
        manifest.get("source_archives"),
        imported_by_path,
    )

    package_manifest = load_json(
        destination / "canonical" / "00_master" / "RAOS_package_manifest_v1.0.json"
    )
    package = package_manifest.get("package")
    if not isinstance(package, dict) or package.get("version") != "1.0":
        raise DesignPackageError("Imported package manifest is not RAOS v1.0")
    package_manifest_count = verify_producer_manifest(
        package_manifest,
        imported_by_package_path,
    )
    if require_readme:
        verify_read_order(destination)

    result = {
        "status": "PASS",
        "story_id": "ST-0001",
        "source_archives": source_count,
        "imported_files": len(files),
        "verified_package_checksums": checksum_count,
        "verified_package_manifest_entries": package_manifest_count,
        "read_order": "PASS" if require_readme else "NOT_CHECKED",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import or verify the immutable RAOS design package."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import",
        help="verify the complete ZIP and import it into docs/",
    )
    import_parser.add_argument(
        "--archive",
        type=Path,
        default=DEFAULT_ARCHIVE,
        help=f"complete design ZIP (default: {DEFAULT_ARCHIVE})",
    )
    import_parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"new import root (default: {DEFAULT_DESTINATION})",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="verify an existing imported design tree",
    )
    verify_parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"import root (default: {DEFAULT_DESTINATION})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            import_package(args.archive.resolve(), args.destination.resolve())
        else:
            verify_import(args.destination.resolve())
    except DesignPackageError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
