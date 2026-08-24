"""Owner generation compatibility tests for ST-0708."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_mode_accepts_exact_outputs() -> None:
    assert generator.main(["--check"]) == 0


def test_isolated_publication_is_0644_and_checkable(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert not tuple(path.parent.glob(f".{path.name}.st0708-*"))
    generator.build(isolated_repository, check=True)


def test_generated_output_drift_is_rejected(isolated_repository: Path) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        original = path.read_bytes()
        path.write_bytes(original + b"drift")
        with pytest.raises(generator.OpenAiLiveBoundedEvaluationReferenceError):
            generator.build(isolated_repository, check=True)
        path.write_bytes(original)


def test_v2_json_outputs_are_canonical_utf8() -> None:
    for relative in (
        generator.REQUEST_PATH,
        generator.REPORT_PATH,
        generator.RUNTIME_MANIFEST_PATH,
    ):
        content = (generator.REPO_ROOT / relative).read_bytes()
        parsed = json.loads(content)
        assert content == generator._canonical_output(parsed)
        assert content.endswith(b"\n")
        assert b"\r" not in content


def test_cli_rejects_every_argument_except_exact_check() -> None:
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2
