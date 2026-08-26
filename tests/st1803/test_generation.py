"""Deterministic no-drift and single-output atomic publication tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .support import REPOSITORY_ROOT
from scripts import build_st1803_gate2_observation as builder


def test_rendered_bytes_match_owned_generated_pack() -> None:
    expected = builder.render_pack()
    observed = (REPOSITORY_ROOT / builder.OUTPUT_PATH).read_bytes()
    assert observed == expected
    assert observed.endswith(b"\n")
    parsed = json.loads(observed)
    assert parsed["schema"] == "ST1803_GATE2_PACK_V1"
    assert parsed["overall"] == "BLOCKED"


def test_check_mode_is_read_only_and_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = 0

    def forbidden_write(content: bytes) -> None:
        nonlocal writes
        del content
        writes += 1
        raise AssertionError("write attempted")

    monkeypatch.setattr(builder, "_atomic_write", forbidden_write)
    assert builder.main(["--check"]) == 0
    assert writes == 0


def test_atomic_writer_recovers_stale_stage_and_replaces_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUT_PATH", Path("generated/pack.json"))
    target = tmp_path / "generated/pack.json"
    target.parent.mkdir()
    target.write_bytes(b"old")
    stage = target.parent / builder._STAGE_NAME
    stage.write_bytes(b"stale")
    builder._atomic_write(b"new")
    assert target.read_bytes() == b"new"
    assert not stage.exists()
    assert target.stat().st_mode & 0o777 == 0o644


def test_failed_replace_preserves_old_target_then_next_run_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUT_PATH", Path("generated/pack.json"))
    target = tmp_path / "generated/pack.json"
    target.parent.mkdir()
    target.write_bytes(b"old")
    original_replace = os.replace

    def fail_replace(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("simulated rename interruption")

    monkeypatch.setattr(builder.os, "replace", fail_replace)
    with pytest.raises(OSError):
        builder._atomic_write(b"new")
    assert target.read_bytes() == b"old"
    assert (target.parent / builder._STAGE_NAME).read_bytes() == b"new"
    monkeypatch.setattr(builder.os, "replace", original_replace)
    builder._atomic_write(b"recovered")
    assert target.read_bytes() == b"recovered"
    assert not (target.parent / builder._STAGE_NAME).exists()


def test_generator_rejects_symlinked_bound_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    (safe / "link").symlink_to(outside)
    monkeypatch.setattr(builder, "REPO_ROOT", safe)
    with pytest.raises(SystemExit):
        builder._safe_read(Path("link"))


def test_generator_source_and_output_have_no_dynamic_clock_or_environment() -> None:
    source = (REPOSITORY_ROOT / builder.GENERATOR_PATH).read_text()
    for forbidden in (
        "datetime.now",
        "date.today",
        "os.environ",
        "getenv(",
        "requests",
        "urlopen",
        "subprocess",
    ):
        assert forbidden not in source
    output = (REPOSITORY_ROOT / builder.OUTPUT_PATH).read_text()
    assert 'actual_observations": []' in output
    assert '"gate_pass_claim": false' in output
    assert '"publication": "NONE"' in output
