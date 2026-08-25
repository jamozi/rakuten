"""Hostile archive, CSV, magic, MIME and extension validation for ST-0406 V2."""

from __future__ import annotations

import gzip
import io
import stat
import struct
import tarfile
import zipfile

import pytest

from conftest import v2_descriptor, v2_policy
from raos.adapters.recorded_object_intake_runtime_v2 import (
    DeterministicContentInspectorV2,
)
from raos.domain.ops.object_intake_runtime_v2 import (
    ContentInspectionSummaryV2,
    IntakeFormat,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
)


def _zip(entries: tuple[tuple[zipfile.ZipInfo | str, bytes], ...]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return target.getvalue()


def _tar(
    entries: tuple[tuple[tarfile.TarInfo, bytes], ...], *, compressed: bool = False
) -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w:gz" if compressed else "w") as archive:
        for info, content in entries:
            archive.addfile(info, io.BytesIO(content) if info.isfile() else None)
    return target.getvalue()


def _regular_tar_info(name: str, content: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o600
    return info


def _inspect(content: bytes, *, leaf: str, media: str) -> ContentInspectionSummaryV2:
    return DeterministicContentInspectorV2().inspect(
        descriptor=v2_descriptor(
            content=content, leaf_name=leaf, media_type=media
        ).descriptor,
        content=content,
        policy=v2_policy(allowed_media_types=(media,)),
    )


def _assert_rejected(content: bytes, *, leaf: str, media: str) -> None:
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        _inspect(content, leaf=leaf, media=media)
    assert caught.value.code is ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED
    assert caught.value.__cause__ is None


def test_strict_csv_shape_encoding_and_formula_prefix_protection() -> None:
    summary = _inspect(b"name,value\nsafe,1\n", leaf="safe.csv", media="text/csv")
    assert summary.format is IntakeFormat.CSV
    assert (summary.csv_row_count, summary.csv_column_count) == (2, 2)

    hostile = (
        b"\xef\xbb\xbfname,value\nsafe,1\n",
        b"name,value\nsafe,\xff\n",
        b"name,value\nsafe\n",
        b"name,name\nsafe,1\n",
        b" name,value\nsafe,1\n",
        b"name,value\nsafe, =1+1\n",
        b"name,value\nsafe,\t@SUM(A1)\n",
        b"name,value\nsafe,-1\n",
        b"name,value\nsafe,\x00\n",
    )
    for content in hostile:
        _assert_rejected(content, leaf="unsafe.csv", media="text/csv")


def test_zip_and_tar_are_validated_without_any_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        zipfile.ZipFile,
        "extract",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("extract called")),
    )
    monkeypatch.setattr(
        zipfile.ZipFile,
        "extractall",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("extractall called")
        ),
    )
    monkeypatch.setattr(
        tarfile.TarFile,
        "extract",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("extract called")),
    )
    monkeypatch.setattr(
        tarfile.TarFile,
        "extractall",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("extractall called")
        ),
    )
    zip_content = _zip((("folder/safe.txt", b"safe"),))
    assert (
        _inspect(zip_content, leaf="safe.zip", media="application/zip").format
        is IntakeFormat.ZIP
    )

    item = _regular_tar_info("folder/safe.txt", b"safe")
    tar_content = _tar(((item, b"safe"),))
    assert (
        _inspect(tar_content, leaf="safe.tar", media="application/x-tar").format
        is IntakeFormat.TAR
    )
    compressed = _tar(((item, b"safe"),), compressed=True)
    assert (
        _inspect(compressed, leaf="safe.tar.gz", media="application/gzip").format
        is IntakeFormat.TAR_GZIP
    )


@pytest.mark.parametrize(
    "name",
    ("../escape.txt", "/absolute.txt", "C:/drive.txt", "safe/../../escape.txt"),
)
def test_zip_traversal_and_absolute_names_are_rejected(name: str) -> None:
    _assert_rejected(
        _zip(((name, b"unsafe"),)), leaf="unsafe.zip", media="application/zip"
    )


def test_zip_symlink_encrypted_nested_duplicate_and_bomb_are_rejected() -> None:
    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    _assert_rejected(
        _zip(((symlink, b"target"),)), leaf="unsafe.zip", media="application/zip"
    )

    encrypted = bytearray(_zip((("safe.txt", b"safe"),)))
    encrypted[6:8] = struct.pack("<H", struct.unpack("<H", encrypted[6:8])[0] | 1)
    central = encrypted.find(b"PK\x01\x02")
    assert central > 0
    encrypted[central + 8 : central + 10] = struct.pack(
        "<H", struct.unpack("<H", encrypted[central + 8 : central + 10])[0] | 1
    )
    _assert_rejected(bytes(encrypted), leaf="unsafe.zip", media="application/zip")

    nested = _zip((("inner.zip", _zip((("safe.txt", b"safe"),))),))
    _assert_rejected(nested, leaf="outer.zip", media="application/zip")
    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = _zip((("same.txt", b"one"), ("same.txt", b"two")))
    _assert_rejected(duplicate, leaf="duplicate.zip", media="application/zip")
    bomb = _zip((("large.txt", b"A" * 40_000),))
    _assert_rejected(bomb, leaf="bomb.zip", media="application/zip")


def test_tar_symlink_hardlink_special_nested_and_traversal_are_rejected() -> None:
    symlink = tarfile.TarInfo("link")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "target"
    hardlink = tarfile.TarInfo("hard")
    hardlink.type = tarfile.LNKTYPE
    hardlink.linkname = "target"
    fifo = tarfile.TarInfo("fifo")
    fifo.type = tarfile.FIFOTYPE
    traversal = _regular_tar_info("../escape", b"unsafe")
    nested_bytes = _zip((("safe.txt", b"safe"),))
    nested = _regular_tar_info("nested.zip", nested_bytes)
    for info, content in (
        (symlink, b""),
        (hardlink, b""),
        (fifo, b""),
        (traversal, b"unsafe"),
        (nested, nested_bytes),
    ):
        _assert_rejected(
            _tar(((info, content),)),
            leaf="unsafe.tar",
            media="application/x-tar",
        )


def test_empty_archives_entry_count_limit_and_gzip_bomb_are_rejected() -> None:
    _assert_rejected(_zip(()), leaf="empty.zip", media="application/zip")
    entries = tuple((f"{index}.txt", b"x") for index in range(17))
    _assert_rejected(_zip(entries), leaf="many.zip", media="application/zip")
    compressed_bomb = gzip.compress(b"A" * 40_000, mtime=0)
    _assert_rejected(compressed_bomb, leaf="bomb.tar.gz", media="application/gzip")


def test_mime_magic_and_extension_must_match_exactly() -> None:
    csv_content = b"name,value\nsafe,1\n"
    _assert_rejected(csv_content, leaf="safe.zip", media="application/zip")
    zip_content = _zip((("safe.txt", b"safe"),))
    _assert_rejected(zip_content, leaf="safe.csv", media="text/csv")
    _assert_rejected(zip_content, leaf="safe.bin", media="application/zip")
    _assert_rejected(b"not-a-png", leaf="image.png", media="image/png")


def test_binary_magic_allowlist_is_closed() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"recorded-only"
    summary = _inspect(png, leaf="image.png", media="image/png")
    assert summary.format is IntakeFormat.PNG
