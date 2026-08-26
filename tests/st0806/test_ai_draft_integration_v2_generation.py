"""Owner generation and syscall-boundary publication evidence for ST-0806 V2."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st0806_ai_draft_integration_v2 as generator
from scripts import secure_generated_publication
from .v2_support import REPOSITORY_ROOT


def test_rendered_outputs_exactly_match_committed_artifacts() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert tuple(outputs) == generator.GENERATED_PATHS
    for relative, expected in outputs.items():
        path = REPOSITORY_ROOT / relative
        assert path.read_bytes() == expected
        assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_manifest_binds_owner_sources_fixture_plan_and_hardened_helper() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["document"]["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert manifest["contract_sha256"] == generator.EXPECTED_CONTRACT_SHA256
    assert manifest["policy_sha256"] == generator.EXPECTED_POLICY_SHA256
    assert manifest["hardened_writer_sha256"] == generator.HARDENED_WRITER_SHA256
    assert set(manifest["source_sha256"]) == {
        path.as_posix() for path in generator.SOURCE_ARTIFACT_PATHS
    }
    for relative, digest in manifest["source_sha256"].items():
        assert (
            hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
            == digest
        )
    plan = (REPOSITORY_ROOT / generator.PLAN_PATH).read_bytes()
    fixture = (REPOSITORY_ROOT / generator.FIXTURE_PATH).read_bytes()
    assert manifest["generated_sha256"] == {
        generator.PLAN_PATH.as_posix(): hashlib.sha256(plan).hexdigest(),
        generator.FIXTURE_PATH.as_posix(): hashlib.sha256(fixture).hexdigest(),
    }
    assert json.loads(plan)["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert json.loads(plan)["enabled"] is False


def test_check_mode_is_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    before = {
        path: (
            (REPOSITORY_ROOT / path).read_bytes(),
            (REPOSITORY_ROOT / path).stat().st_mtime_ns,
        )
        for path in generator.GENERATED_PATHS
    }

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("check mode must not publish")

    monkeypatch.setattr(generator, "_replace_generated", forbidden)
    generator.build(REPOSITORY_ROOT, check=True)
    after = {
        path: (
            (REPOSITORY_ROOT / path).read_bytes(),
            (REPOSITORY_ROOT / path).stat().st_mtime_ns,
        )
        for path in generator.GENERATED_PATHS
    }
    assert after == before


def test_generator_binds_exact_hardened_publication_source() -> None:
    helper = REPOSITORY_ROOT / generator.HARDENED_WRITER_PATH
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == (
        "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
    )
    assert generator._writer(REPOSITORY_ROOT) is secure_generated_publication
    assert "os.replace" not in Path(generator.__file__).read_text(encoding="utf-8")


def test_pre_exchange_swap_restores_foreign_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    parked = tmp_path / "parked-original"
    foreign = tmp_path / "foreign"
    target.write_bytes(b"original")
    foreign.write_bytes(b"foreign")
    original = secure_generated_publication._rename_exchange
    swapped = False

    def swap_then_exchange(parent: int, source: str, destination: str) -> None:
        nonlocal swapped
        if not swapped and destination == target.name:
            swapped = True
            os.rename(target.name, parked.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.rename(foreign.name, target.name, src_dir_fd=parent, dst_dir_fd=parent)
        original(parent, source, destination)

    monkeypatch.setattr(
        secure_generated_publication, "_rename_exchange", swap_then_exchange
    )
    with pytest.raises(generator.AiDraftBuildError):
        generator._replace_generated(REPOSITORY_ROOT, ((target, b"generated"),))
    assert target.read_bytes() == b"foreign"
    assert parked.read_bytes() == b"original"


def test_post_exchange_swap_preserves_foreign_and_displaced_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    moved = tmp_path / "moved-generated"
    foreign = tmp_path / "foreign"
    target.write_bytes(b"original")
    foreign.write_bytes(b"foreign")
    original = secure_generated_publication._rename_exchange
    swapped = False

    def exchange_then_swap(parent: int, source: str, destination: str) -> None:
        nonlocal swapped
        original(parent, source, destination)
        if not swapped and destination == target.name:
            swapped = True
            os.rename(target.name, moved.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.rename(foreign.name, target.name, src_dir_fd=parent, dst_dir_fd=parent)

    monkeypatch.setattr(
        secure_generated_publication, "_rename_exchange", exchange_then_swap
    )
    with pytest.raises(generator.AiDraftBuildError):
        generator._replace_generated(REPOSITORY_ROOT, ((target, b"generated"),))
    assert target.read_bytes() == b"foreign"
    assert moved.read_bytes() == b"generated"
    recovery = tuple(
        path
        for path in tmp_path.iterdir()
        if path.name.startswith(".target.st0806-v2-")
    )
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"original"


def test_missing_target_hardlink_install_never_clobbers_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    original = os.link
    injected = False

    def inject_then_link(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        if not injected:
            injected = True
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            try:
                os.write(descriptor, b"foreign")
            finally:
                os.close(descriptor)
        original(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", inject_then_link)
    with pytest.raises(generator.AiDraftBuildError):
        generator._replace_generated(REPOSITORY_ROOT, ((target, b"generated"),))
    assert target.read_bytes() == b"foreign"
    assert tuple(path.name for path in tmp_path.iterdir()) == ("target",)


def test_parent_swap_preserves_foreign_replacement_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned"
    parked = tmp_path / "parked-owned"
    owned.mkdir()
    target = owned / "target"
    target.write_bytes(b"original")
    original = secure_generated_publication._commit_stage
    swapped = False

    def swap_then_commit(stage: secure_generated_publication._StagedOutput) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            owned.rename(parked)
            owned.mkdir()
            (owned / "target").write_bytes(b"foreign")
        original(stage)

    monkeypatch.setattr(secure_generated_publication, "_commit_stage", swap_then_commit)
    with pytest.raises(generator.AiDraftBuildError):
        generator._replace_generated(REPOSITORY_ROOT, ((target, b"generated"),))
    assert (owned / "target").read_bytes() == b"foreign"
    assert (parked / "target").read_bytes() == b"original"
