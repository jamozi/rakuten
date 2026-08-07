from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from scripts import build_st0205_synthetic_data as generator


def test_rendered_outputs_are_byte_deterministic_and_match_committed_bytes() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for path, expected in first.items():
        assert (generator.REPO_ROOT / path).read_bytes() == expected


def test_bundle_round_trip_and_catalog_generation() -> None:
    bundle_bytes = generator.render_fixture_bundle()
    loaded = json.loads(bundle_bytes)
    assert loaded == generator.build_seed_bundle()
    catalog = json.loads(generator.render_catalog(bundle_bytes))
    assert catalog["bundle"]["sha256"] == hashlib.sha256(bundle_bytes).hexdigest()
    assert catalog["bundle"]["fixture_count"] == len(generator.FIXTURE_SCENARIOS)


def test_catalog_hash_license_and_origin_are_bound_per_fixture() -> None:
    bundle = json.loads(generator.render_fixture_bundle())
    catalog = json.loads(generator.render_catalog())
    rows = {row["fixture_id"]: row for row in catalog["fixtures"]}
    assert set(rows) == {fixture["fixture_id"] for fixture in bundle["fixtures"]}
    for fixture in bundle["fixtures"]:
        content = generator._json_bytes(fixture, compact=True)
        row = rows[fixture["fixture_id"]]
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
        assert row["origin"] == generator.ORIGIN
        assert row["license"] == "UNLICENSED"


def test_manifest_inventories_all_sources_and_generated_payloads() -> None:
    outputs = generator.render_outputs()
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])
    sources = manifest["source_artifacts"]
    generated = manifest["generated_artifacts"]
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in sources] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert len({row["uri"] for row in sources}) == len(sources)
    assert manifest["generated_artifact_count"] == 2
    assert [row["uri"] for row in generated] == [
        f"repo://{generator.FIXTURE_BUNDLE_PATH.as_posix()}",
        f"repo://{generator.CATALOG_PATH.as_posix()}",
    ]
    for row in generated:
        path = Path(row["uri"].removeprefix("repo://"))
        content = outputs[path]
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()


def test_manifest_binds_both_dependency_manifests() -> None:
    manifest = yaml.safe_load(generator.render_outputs()[generator.MANIFEST_PATH])
    assert manifest["provenance"]["predecessor_manifests"] == [
        {
            "story_id": story,
            "uri": f"repo://{path.as_posix()}",
            "sha256": digest,
        }
        for story, path, digest in generator.PREDECESSOR_MANIFESTS
    ]


def test_check_mode_is_read_only_and_matches_generated_bytes() -> None:
    before = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    generator.check_generated()
    after = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    assert after == before


def test_cli_check_reports_sanitized_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert generator.main(["--check"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "domains": 13,
        "fixtures": 18,
        "generated_artifacts": 3,
        "mode": "check",
        "status": "PASS",
        "story_id": "ST-0205",
    }


def test_atomic_writer_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "changes")
    with pytest.raises((OSError, RuntimeError)):
        generator._write_artifact_atomic(
            tmp_path,
            generator.FIXTURE_BUNDLE_PATH,
            b"unsafe\n",
        )
    assert list(outside.iterdir()) == []


def test_secure_reader_is_descriptor_relative_and_sets_required_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "nested" / "payload.json"
    source.parent.mkdir()
    source.write_bytes(b'{"safe":true}\n')
    real_open = os.open
    calls: list[tuple[str, int, int | None, int]] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        calls.append((os.fsdecode(path), flags, dir_fd, descriptor))
        return descriptor

    monkeypatch.setattr(generator.os, "open", tracked_open)

    content, metadata = generator._read_repository_file(
        tmp_path,
        Path("nested/payload.json"),
        "test source",
    )

    assert content == b'{"safe":true}\n'
    assert metadata.st_size == len(content)
    assert [path for path, *_rest in calls] == [
        os.fspath(tmp_path),
        "nested",
        "payload.json",
    ]
    assert calls[0][2] is None
    for previous, current in zip(calls, calls[1:]):
        assert current[2] == previous[3]
        assert "/" not in current[0]
    assert all(flags & os.O_NOFOLLOW for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_CLOEXEC for _path, flags, _dir_fd, _fd in calls)
    assert all(flags & os.O_DIRECTORY for _path, flags, _dir_fd, _fd in calls[:-1])
    assert calls[-1][1] & os.O_NONBLOCK
    assert not calls[-1][1] & os.O_DIRECTORY


@pytest.mark.parametrize(
    "flag_name",
    ["O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"],
)
def test_secure_reader_fails_closed_without_required_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
) -> None:
    (tmp_path / "payload.json").write_bytes(b"safe\n")
    monkeypatch.setattr(generator.os, flag_name, 0)

    with pytest.raises(RuntimeError, match="filesystem safety is unavailable"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.json"),
            "missing-flag test source",
        )


def test_secure_reader_rejects_repository_root_swap_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "payload.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "payload.json").write_bytes(b"untrusted\n")
    real_open = os.open
    swapped = False

    def swap_root_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fsdecode(path) == os.fspath(root) and not swapped:
            swapped = True
            root.rename(tmp_path / "captured-repository")
            replacement.rename(root)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", swap_root_then_open)

    with pytest.raises(RuntimeError, match="root changed before secure capture"):
        generator._read_repository_file(
            root,
            Path("payload.json"),
            "root-swap test source",
        )


def test_secure_reader_rejects_symlink_ancestor_without_following_it(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.json").write_bytes(b"outside\n")
    os.symlink(outside, tmp_path / "linked")

    with pytest.raises(RuntimeError, match="ancestor"):
        generator._read_repository_file(
            tmp_path,
            Path("linked/payload.json"),
            "symlink test source",
        )


def test_secure_reader_rejects_fifo_before_opening_the_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo = tmp_path / "payload.fifo"
    os.mkfifo(fifo)
    real_open = os.open
    opened: list[str] = []

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        opened.append(os.fsdecode(path))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", tracked_open)

    with pytest.raises(RuntimeError, match="regular non-symlink file"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.fifo"),
            "FIFO test source",
        )
    assert "payload.fifo" not in opened


def test_secure_reader_rejects_multiply_linked_file(tmp_path: Path) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"linked\n")
    os.link(source, tmp_path / "second-name.json")

    with pytest.raises(RuntimeError, match="one filesystem link"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.json"),
            "hardlink test source",
        )


def test_secure_reader_rejects_ancestor_replacement_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    (trusted / "nested").mkdir(parents=True)
    (trusted / "nested" / "payload.json").write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement"
    (replacement / "nested").mkdir(parents=True)
    (replacement / "nested" / "payload.json").write_bytes(b"replacement\n")
    real_open = os.open
    swapped = False

    def swap_after_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "trusted" and not swapped:
            swapped = True
            trusted.rename(tmp_path / "captured-trusted")
            replacement.rename(trusted)
        return descriptor

    monkeypatch.setattr(generator.os, "open", swap_after_open)

    with pytest.raises(RuntimeError, match="changed during secure capture"):
        generator._read_repository_file(
            tmp_path,
            Path("trusted/nested/payload.json"),
            "ancestor replacement test source",
        )


def test_secure_reader_rejects_target_replacement_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b"untrusted\n")
    real_open = os.open
    real_read = os.read
    target_descriptor: int | None = None
    swapped = False

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal target_descriptor
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "payload.json":
            target_descriptor = descriptor
        return descriptor

    def swap_then_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if descriptor == target_descriptor and not swapped:
            swapped = True
            source.rename(tmp_path / "captured-payload.json")
            replacement.rename(source)
        return real_read(descriptor, count)

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "read", swap_then_read)

    with pytest.raises(RuntimeError, match="changed while it was read"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.json"),
            "target replacement test source",
        )


def test_secure_reader_rejects_target_replacement_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "payload.json"
    source.write_bytes(b"trusted\n")
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b"untrusted\n")
    real_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fsdecode(path) == "payload.json" and not swapped:
            swapped = True
            source.rename(tmp_path / "captured-payload.json")
            replacement.rename(source)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", swap_before_open)

    with pytest.raises(RuntimeError, match="changed before secure capture"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.json"),
            "pre-open target replacement test source",
        )


@pytest.mark.parametrize(
    "replacement",
    [b"mutated!", b"x", b"extended-content"],
    ids=["same-size", "truncated", "extended"],
)
def test_secure_reader_rejects_same_inode_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"original")
    real_read = os.read
    mutated = False

    def mutate_then_read(descriptor: int, count: int) -> bytes:
        nonlocal mutated
        if not mutated:
            mutated = True
            source.write_bytes(replacement)
            metadata = source.stat()
            os.utime(
                source,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )
        return real_read(descriptor, count)

    monkeypatch.setattr(generator.os, "read", mutate_then_read)

    with pytest.raises(RuntimeError, match="changed while it was read"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.bin"),
            "same-inode mutation test source",
        )


def test_secure_reader_size_bound_accepts_exact_limit_and_rejects_limit_plus_one(
    tmp_path: Path,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"1234")
    content, _metadata = generator._read_repository_file(
        tmp_path,
        Path("payload.bin"),
        "size-bound test source",
        maximum_bytes=4,
    )
    assert content == b"1234"

    source.write_bytes(b"12345")
    with pytest.raises(RuntimeError, match="exceeds its size limit"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.bin"),
            "size-bound test source",
            maximum_bytes=4,
        )


def test_contract_yaml_parser_enforces_the_exact_two_mib_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = b"\n{}\n"
    content = (
        b"#" + (b"x" * (generator.shared.MAX_YAML_BYTES - len(suffix) - 1)) + suffix
    )

    assert len(content) == generator.shared.MAX_YAML_BYTES
    assert generator._load_yaml_bytes(content, label="exact-limit contract") == {}

    def forbidden_yaml_scan(_text: str) -> object:
        raise AssertionError("oversized contract must be rejected before parsing")

    monkeypatch.setattr(generator.yaml, "scan", forbidden_yaml_scan)
    with pytest.raises(RuntimeError, match="exceeds its YAML size limit"):
        generator._load_yaml_bytes(content + b"#", label="oversized contract")


def test_contract_capture_rejects_over_two_mib_before_yaml_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = tmp_path / generator.CONTRACT_PATH
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b"#" + (b"x" * generator.shared.MAX_YAML_BYTES) + b"\n{}\n")

    def skip_pinned_inputs(
        _root: Path,
        *,
        captured_files: object = None,
    ) -> None:
        assert captured_files is None

    def forbidden_yaml_scan(_text: str) -> object:
        raise AssertionError("oversized contract must be rejected before parsing")

    monkeypatch.setattr(generator, "assert_pinned_inputs", skip_pinned_inputs)
    monkeypatch.setattr(generator.yaml, "scan", forbidden_yaml_scan)

    with pytest.raises(RuntimeError, match="exceeds its size limit"):
        generator.load_and_validate_contract(tmp_path)


def test_secure_reader_rejects_short_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"content")
    monkeypatch.setattr(generator.os, "read", lambda _descriptor, _count: b"")

    with pytest.raises(RuntimeError, match="changed while it was read"):
        generator._read_repository_file(
            tmp_path,
            Path("payload.bin"),
            "short-read test source",
        )


def test_secure_reader_sanitizes_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-read-failure-canary"
    (tmp_path / "payload.bin").write_bytes(b"content")

    def fail_read(_descriptor: int, _count: int) -> bytes:
        raise OSError(canary)

    monkeypatch.setattr(generator.os, "read", fail_read)
    with pytest.raises(RuntimeError, match="captured safely") as exc_info:
        generator._read_repository_file(
            tmp_path,
            Path("payload.bin"),
            "failed-read test source",
        )
    assert canary not in str(exc_info.value)


def test_secure_reader_sanitizes_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-close-failure-canary"
    source = tmp_path / "nested" / "payload.bin"
    source.parent.mkdir()
    source.write_bytes(b"content")
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []
    failed = False

    def tracked_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    def close_then_fail(descriptor: int) -> None:
        nonlocal failed
        real_close(descriptor)
        closed.append(descriptor)
        if not failed:
            failed = True
            raise OSError(canary)

    monkeypatch.setattr(generator.os, "open", tracked_open)
    monkeypatch.setattr(generator.os, "close", close_then_fail)
    with pytest.raises(RuntimeError, match="descriptor cleanup failed") as exc_info:
        generator._read_repository_file(
            tmp_path,
            Path("nested/payload.bin"),
            "close-failure test source",
        )
    assert canary not in str(exc_info.value)
    assert sorted(closed) == sorted(opened)
    assert len(closed) == len(set(closed))


def test_secure_reader_preserves_primary_failure_when_close_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "payload.bin").write_bytes(b"too large")
    real_close = os.close

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("private cleanup detail")

    monkeypatch.setattr(generator.os, "close", close_then_fail)
    with pytest.raises(RuntimeError, match="exceeds its size limit") as exc_info:
        generator._read_repository_file(
            tmp_path,
            Path("payload.bin"),
            "primary-failure test source",
            maximum_bytes=1,
        )
    assert "descriptor cleanup also failed" in getattr(
        exc_info.value,
        "__notes__",
        (),
    )


def test_render_outputs_captures_each_repository_input_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_read = generator._read_repository_file
    counts: dict[Path, int] = {}
    limits: dict[Path, int] = {}

    def counted_read(
        root: Path,
        relative: Path,
        label: str,
        *,
        maximum_bytes: int = generator.MAXIMUM_REPOSITORY_ARTIFACT_BYTES,
    ) -> generator.CapturedRepositoryFile:
        counts[relative] = counts.get(relative, 0) + 1
        limits[relative] = maximum_bytes
        return real_read(root, relative, label, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(generator, "_read_repository_file", counted_read)
    generator.render_outputs()

    assert counts
    assert set(counts) == set(
        [
            *(Path(name) for name in generator.PINNED_CANONICAL_INPUTS),
            *(path for _story, path, _digest in generator.PREDECESSOR_MANIFESTS),
            generator.LICENSE_AUTHORITY_PATH,
            generator.CONTRACT_PATH,
            *generator.SOURCE_ARTIFACT_PATHS,
        ]
    )
    assert set(counts.values()) == {1}
    assert limits[generator.CONTRACT_PATH] == generator.shared.MAX_YAML_BYTES
    assert all(
        maximum == generator.MAXIMUM_REPOSITORY_ARTIFACT_BYTES
        for path, maximum in limits.items()
        if path != generator.CONTRACT_PATH
    )


def test_render_outputs_does_not_reopen_a_secure_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_reopen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("securely captured files must not be reopened")

    monkeypatch.setattr(generator.shared, "_repository_regular_file", forbidden_reopen)
    monkeypatch.setattr(generator.shared, "sha256_file", forbidden_reopen)
    monkeypatch.setattr(generator.shared, "load_yaml", forbidden_reopen)

    outputs = generator.render_outputs()
    assert tuple(outputs) == generator.GENERATED_PATHS


def test_check_mode_uses_one_captured_read_per_output_and_no_write_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_read = generator._read_repository_file
    real_open = os.open
    counts: dict[Path, int] = {}
    write_mask = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def counted_read(
        root: Path,
        relative: Path,
        label: str,
        *,
        maximum_bytes: int = generator.MAXIMUM_REPOSITORY_ARTIFACT_BYTES,
    ) -> generator.CapturedRepositoryFile:
        if relative in generator.GENERATED_PATHS:
            counts[relative] = counts.get(relative, 0) + 1
        return real_read(root, relative, label, maximum_bytes=maximum_bytes)

    def read_only_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        assert not flags & write_mask
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def forbidden_mutation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("check mode must not mutate the repository")

    monkeypatch.setattr(generator, "_read_repository_file", counted_read)
    monkeypatch.setattr(generator.os, "open", read_only_open)
    for mutation_name in ("write", "mkdir", "replace", "unlink", "fsync"):
        monkeypatch.setattr(generator.os, mutation_name, forbidden_mutation)
    generator.check_generated()

    assert counts == {path: 1 for path in generator.GENERATED_PATHS}


def test_check_mode_uses_mode_from_the_same_output_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = generator.render_outputs()
    unsafe = tmp_path / "unsafe-output.json"
    unsafe.write_bytes(outputs[generator.FIXTURE_BUNDLE_PATH])
    unsafe.chmod(0o660)
    real_read = generator._read_repository_file
    output_reads = 0

    def substitute_output(
        root: Path,
        relative: Path,
        label: str,
        *,
        maximum_bytes: int = generator.MAXIMUM_REPOSITORY_ARTIFACT_BYTES,
    ) -> generator.CapturedRepositoryFile:
        nonlocal output_reads
        if relative == generator.FIXTURE_BUNDLE_PATH and label == "ST-0205 output":
            output_reads += 1
            return unsafe.read_bytes(), unsafe.stat()
        return real_read(root, relative, label, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(generator, "_read_repository_file", substitute_output)
    with pytest.raises(RuntimeError, match="group/world writable"):
        generator.check_generated()
    assert output_reads == 1


def test_root_make_and_readme_route_the_story_surface() -> None:
    makefile = (generator.REPO_ROOT / "Makefile").read_text()
    readme = (generator.REPO_ROOT / "README.md").read_text()
    assert (
        "synthetic-data-generate synthetic-data-check synthetic-data-test" in makefile
    )
    assert "scripts/build_st0205_synthetic_data.py --check" in makefile
    assert "tests/st0205" in makefile
    assert (
        "synthetic-data-check"
        in makefile.split("ci-repository-policy:", 1)[1].split("ci-static:", 1)[0]
    )
    assert (
        "tests/st0205" in makefile.split("ci-unit:", 1)[1].split("ci-contracts:", 1)[0]
    )
    assert "make synthetic-data-generate" in readme
    assert "make synthetic-data-check" in readme
    assert "make synthetic-data-test" in readme
