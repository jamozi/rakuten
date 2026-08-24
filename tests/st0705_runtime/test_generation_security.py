from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
import yaml

from scripts import build_st0705_ai_output_validation_runtime as generator


ROOT = Path(__file__).resolve().parents[2]


def test_pure_evaluator_has_no_io_clock_random_or_mutation_surface() -> None:
    source = (ROOT / generator.DOMAIN_PATH).read_bytes()
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint(
        {
            "boto3",
            "httpx",
            "os",
            "pathlib",
            "random",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "time",
            "urllib",
        }
    )
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(
        {"connect", "execute", "getenv", "publish", "request", "send"}
    )


def test_transaction_rolls_back_even_on_base_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    real_exchange = generator._rename_exchange
    calls = 0

    def interrupted(parent_descriptor: int, left: str, right: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        real_exchange(parent_descriptor, left, right)

    monkeypatch.setattr(generator, "_rename_exchange", interrupted)
    with pytest.raises(KeyboardInterrupt):
        generator._replace_generated(
            ((first, b"first-after"), (second, b"second-after"))
        )
    assert first.read_bytes() == b"first-before"
    assert second.read_bytes() == b"second-before"


def test_existing_hardlinked_target_is_rejected_without_mutation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.json"
    alias = tmp_path / "alias.json"
    target.write_bytes(b"before")
    os.link(target, alias)
    with pytest.raises(generator.St0705BuildError):
        generator._replace_generated(((target, b"after"),))
    assert target.read_bytes() == b"before"
    assert alias.read_bytes() == b"before"


def test_target_swap_before_commit_is_detected_without_reowning_foreign_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.json"
    foreign = tmp_path / "foreign.json"
    target.write_bytes(b"before")
    foreign.write_bytes(b"foreign")
    real_named_identity = generator._named_identity
    swapped = False

    def swap_once(stage: generator._StagedOutput, name: str) -> tuple[int, ...] | None:
        nonlocal swapped
        if name == stage.target_name and not swapped:
            os.replace(foreign, target)
            swapped = True
        return real_named_identity(stage, name)

    monkeypatch.setattr(generator, "_named_identity", swap_once)
    with pytest.raises(generator.St0705BuildError):
        generator._replace_generated(((target, b"after"),))
    assert swapped is True
    assert target.read_bytes() == b"foreign"


def test_atomic_exchange_restores_a_foreign_target_swapped_at_syscall_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.json"
    foreign = tmp_path / "foreign.json"
    target.write_bytes(b"before")
    foreign.write_bytes(b"foreign")
    real_exchange = generator._rename_exchange
    calls = 0

    def race_then_exchange(parent_descriptor: int, left: str, right: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            os.replace(foreign, target)
        real_exchange(parent_descriptor, left, right)

    monkeypatch.setattr(generator, "_rename_exchange", race_then_exchange)
    with pytest.raises(generator.St0705BuildError):
        generator._replace_generated(((target, b"after"),))
    assert calls >= 2
    assert target.read_bytes() == b"foreign"


def test_commit_protocol_never_calls_clobbering_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"before")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("clobbering replace must not be used")

    monkeypatch.setattr(generator.os, "replace", forbidden)
    generator._replace_generated(((target, b"after"),))
    assert target.read_bytes() == b"after"


def test_fresh_install_uses_no_replace_and_preserves_racing_foreign_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.json"
    real_link = generator.os.link

    def race_then_link(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        target.write_bytes(b"foreign")
        real_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(generator.os, "link", race_then_link)
    with pytest.raises(generator.St0705BuildError):
        generator._replace_generated(((target, b"after"),))
    assert target.read_bytes() == b"foreign"


def test_all_outputs_are_staged_before_first_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    real_stage = generator._stage_output
    staged: list[str] = []

    def record_stage(
        destination: Path, payload: bytes, ordinal: int
    ) -> generator._StagedOutput:
        staged.append(destination.name)
        return real_stage(destination, payload, ordinal)

    real_exchange = generator._rename_exchange

    def require_complete_stage(parent_descriptor: int, left: str, right: str) -> None:
        assert staged == ["first.json", "second.json"]
        real_exchange(parent_descriptor, left, right)

    monkeypatch.setattr(generator, "_stage_output", record_stage)
    monkeypatch.setattr(generator, "_rename_exchange", require_complete_stage)
    generator._replace_generated(((first, b"first-after"), (second, b"second-after")))
    assert first.read_bytes() == b"first-after"
    assert second.read_bytes() == b"second-after"


def test_repository_path_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.St0705BuildError):
        generator._repository_path(root, Path("linked/file.json"))


def test_runtime_manifest_has_closed_authority_and_generated_hashes() -> None:
    manifest = yaml.safe_load((ROOT / generator.RUNTIME_MANIFEST_PATH).read_bytes())
    assert manifest["document"]["authority"] == "NONE"
    assert manifest["document"]["production_eligible"] is False
    assert manifest["profile_count"] == 12
    assert manifest["formal_tst_019"] == "NOT_EXECUTED"
    assert manifest["formal_tst_020"] == "NOT_EXECUTED"
    assert manifest["live"] == "NOT_EXECUTED"
    for path, digest in manifest["generated_sha256"].items():
        assert generator._sha((ROOT / path).read_bytes()) == digest
