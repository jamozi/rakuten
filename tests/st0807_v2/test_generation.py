from __future__ import annotations

# pyright: reportPrivateUsage=false

from collections.abc import Callable
import hashlib
import os
from pathlib import Path
from typing import cast

import pytest

from scripts import build_st0807_seo_render_runtime as generator


_CONTRACT_MUTATIONS: tuple[Callable[[str], str], ...] = (
    lambda value: value.replace(
        "  id: RAOS-ST0807-SEO-RENDER-RUNTIME-002",
        "  id: RAOS-ST0807-SEO-RENDER-RUNTIME-002\n"
        "  id: RAOS-ST0807-SEO-RENDER-RUNTIME-002",
        1,
    ),
    lambda value: value.replace(
        "  id: RAOS-ST0807-SEO-RENDER-RUNTIME-002",
        "  id: &forbidden RAOS-ST0807-SEO-RENDER-RUNTIME-002",
        1,
    ),
    lambda value: value.replace("  version: 2.0.0", "  version: !!str 2.0.0", 1),
    lambda value: value + "unknown_top_level: false\n",
    lambda value: value.replace(
        "  publication_authorized: false",
        "  publication_authorized: true",
        1,
    ),
    lambda value: value.replace("    - TITLE_UNIQUENESS\n", "", 1),
    lambda value: value.replace("    - Product\n", "", 1),
)


def test_owner_generation_and_check_are_deterministic() -> None:
    generator.build(generator.REPO_ROOT)
    paths = tuple(generator.REPO_ROOT / path for path in generator.GENERATED_PATHS)
    before = tuple(path.read_bytes() for path in paths)

    generator.build(generator.REPO_ROOT, check=True)
    generator.build(generator.REPO_ROOT)

    assert tuple(path.read_bytes() for path in paths) == before


def test_check_path_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_artifacts: object) -> None:
        raise AssertionError("check attempted the publication transaction")

    monkeypatch.setattr(generator, "_replace_generated", forbidden)
    paths = tuple(generator.REPO_ROOT / path for path in generator.GENERATED_PATHS)
    before = tuple((path.stat().st_mtime_ns, path.read_bytes()) for path in paths)
    generator.build(generator.REPO_ROOT, check=True)
    assert (
        tuple((path.stat().st_mtime_ns, path.read_bytes()) for path in paths) == before
    )


def test_manifest_binds_every_source_and_generated_result(
    runtime_manifest: dict[str, object],
) -> None:
    source_hashes = runtime_manifest["source_sha256"]
    assert type(source_hashes) is dict
    typed_hashes = cast(dict[str, str], source_hashes)
    assert tuple(typed_hashes) == tuple(
        path.as_posix() for path in generator.SOURCE_PATHS
    )
    for relative, expected in typed_hashes.items():
        assert (
            hashlib.sha256((generator.REPO_ROOT / relative).read_bytes()).hexdigest()
            == expected
        )
    result = (generator.REPO_ROOT / generator.RESULT_PATH).read_bytes()
    assert runtime_manifest["generated_sha256"] == {
        generator.RESULT_PATH.as_posix(): hashlib.sha256(result).hexdigest()
    }
    assert runtime_manifest["toolchain"] == {
        "uv_version": "0.12.1",
        "python_implementation": "cpython",
        "python_version": "3.14.6",
        "pyyaml_version": "6.0.3",
    }


def test_toolchain_source_is_verified_by_setup_and_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = generator._read_regular

    def tampered_read(
        root: object,
        relative: object,
        *,
        maximum_bytes: int = generator.MAXIMUM_SOURCE_BYTES,
    ) -> bytes:
        if relative == Path(".python-version"):
            return b"3.14.7\n"
        return original_read(root, relative, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(generator, "_read_regular", tampered_read)
    assert generator._require_toolchain(generator.REPO_ROOT) is None


@pytest.mark.parametrize(
    "mutation",
    _CONTRACT_MUTATIONS,
)
def test_contract_tamper_and_yaml_extensions_fail_closed(
    mutation: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = generator._read_regular
    original = original_read(generator.REPO_ROOT, generator.CONTRACT_PATH)
    mutated = mutation(original.decode("utf-8")).encode("utf-8")

    def substituted_read(
        root: Path,
        relative: Path,
        *,
        maximum_bytes: int = generator.MAXIMUM_SOURCE_BYTES,
    ) -> bytes:
        if relative == generator.CONTRACT_PATH:
            return mutated
        return original_read(root, relative, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(generator, "_read_regular", substituted_read)
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SHA256",
        hashlib.sha256(mutated).hexdigest(),
    )
    with pytest.raises(generator.SeoRuntimeBuildError):
        generator._load_contract(generator.REPO_ROOT)


def test_source_symlink_hardlink_and_identity_swap_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"source")
    hardlink = tmp_path / "hardlink"
    os.link(source, hardlink)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(source)
    for path in (source, hardlink, symlink):
        with pytest.raises(generator.SeoRuntimeBuildError):
            generator._read_regular(tmp_path, Path(path.name))

    hardlink.unlink()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"foreign")
    original_read = os.read
    swapped = False

    def swap_on_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        payload = original_read(descriptor, size)
        if not swapped:
            swapped = True
            replacement.replace(source)
        return payload

    monkeypatch.setattr(os, "read", swap_on_read)
    with pytest.raises(generator.SeoRuntimeBuildError) as caught:
        generator._read_regular(tmp_path, Path("source"))
    assert caught.value.code == "SOURCE_FILE_CHANGED"
    assert source.read_bytes() == b"foreign"


def test_secure_multioutput_preserves_foreign_and_rejects_unsafe_targets(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    foreign = tmp_path / "foreign"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    foreign.write_bytes(b"foreign")

    generator._replace_generated(((first, b"new-first"), (second, b"new-second")))
    assert first.read_bytes() == b"new-first"
    assert second.read_bytes() == b"new-second"
    assert foreign.read_bytes() == b"foreign"

    hardlink = tmp_path / "hardlink"
    os.link(foreign, hardlink)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(foreign)
    for artifacts in (
        ((hardlink, b"unsafe"),),
        ((symlink, b"unsafe"),),
        ((tmp_path / "duplicate", b"a"),) * 2,
    ):
        with pytest.raises(generator.SeoRuntimeBuildError) as caught:
            generator._replace_generated(artifacts)
        assert caught.value.code == "SECURE_PUBLICATION_FAILED"
    assert foreign.read_bytes() == b"foreign"


def test_generator_has_no_clobbering_replace_and_cli_parse_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(generator.__file__).read_text(encoding="utf-8")
    assert "os.replace" not in source
    assert "secure_publication.publish_generated" in source
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(generator, "build", forbidden)
    with pytest.raises(SystemExit) as caught:
        generator._main(["--unknown"])
    assert caught.value.code == 2
    assert not called
