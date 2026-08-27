"""Current-HEAD sealed-loader and frozen-v1 regression tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import subprocess
import types

import pytest

import scripts.st1704_wordpress_publication_operator_v2 as cli
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
)


ROOT = Path(__file__).resolve().parents[2]
V1_PATHS = (
    "python/raos/domain/operations/self_hosted_wordpress_operator.py",
    "python/raos/ports/self_hosted_wordpress_operator.py",
    "python/raos/adapters/self_hosted_wordpress_operator_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_operator_https.py",
    "scripts/st1506_wordpress_operator.py",
    "scripts/st1506_wordpress_operator_python.sh",
)


def test_every_v1_runtime_byte_remains_exactly_head() -> None:
    for relative in V1_PATHS:
        committed = subprocess.run(
            ["/usr/bin/git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        assert (ROOT / relative).read_bytes() == committed
    assert "PUBLISH_ST1704_ARTICLE" not in (
        ROOT / "scripts/st1506_wordpress_operator.py"
    ).read_text(encoding="utf-8")


def test_direct_main_refuses_before_parser_credentials_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reached = {"parser": False}

    def parser() -> object:
        reached["parser"] = True
        raise AssertionError("direct entry reached parser")

    monkeypatch.setattr(cli, "_parser", parser)
    monkeypatch.setattr(cli, "_STAGE_ZERO_VERIFIED", False)
    with pytest.raises(SystemExit) as refused:
        cli.main(["status"])
    assert refused.value.code == 69
    assert reached == {"parser": False}


def test_loader_executes_captured_bytes_without_reopening_runtime_path(
    tmp_path: Path,
) -> None:
    relative = (
        "python/raos/domain/operations/self_hosted_wordpress_publication_operator_v2.py"
    )
    captured = b"BOUND_VALUE = 'captured-current-head'\n"
    replacement = tmp_path / "replacement.py"
    replacement.write_text("BOUND_VALUE = 'path-swap'\n", encoding="utf-8")
    loader = cli._VerifiedSourceLoader("raos.bound_test", relative, captured)
    module = types.ModuleType("raos.bound_test")
    specification = importlib.util.spec_from_loader(module.__name__, loader)
    assert specification is not None
    module.__spec__ = specification

    loader.exec_module(module)

    assert getattr(module, "BOUND_VALUE") == "captured-current-head"
    assert "path-swap" not in module.__dict__.values()


def test_v2_stage_map_is_closed_and_does_not_import_v1_cli() -> None:
    assert "scripts/st1506_wordpress_operator.py" not in cli._STAGE_RUNTIME_PATHS
    assert "scripts.st1506_wordpress_operator" not in cli._STAGE_MODULE_PATHS
    assert set(cli._STAGE_MODULE_PATHS.values()).issubset(cli._STAGE_RUNTIME_PATHS)
    assert (
        "changes/st-1704/publication-operator-v2/runtime-manifest.v2.json"
        in cli._STAGE_RUNTIME_PATHS
    )
    assert set(cli._STAGE_MODULE_PATHS) == {
        "raos.adapters.self_hosted_editorial_pilot_json",
        "raos.adapters.self_hosted_wordpress_operator_credentials",
        "raos.adapters.self_hosted_wordpress_publication_operator_https_v2",
        "raos.adapters.self_hosted_wordpress_publication_operator_journal_v2",
        "raos.adapters.self_hosted_wordpress_publication_operator_json_v2",
        "raos.domain.editorial.self_hosted_editorial_pilot",
        "raos.domain.operations.self_hosted_wordpress_operator",
        "raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2",
        "raos.domain.operations.self_hosted_wordpress_publication_operator_v2",
        "raos.ports.self_hosted_editorial_pilot",
        "raos.ports.self_hosted_wordpress_publication_operator_v2",
    }


def test_launcher_is_executable_and_parser_never_echoes_invalid_argv(
    capsys: pytest.CaptureFixture[str],
) -> None:
    launcher = ROOT / "scripts/st1704_wordpress_publication_operator_v2_python.sh"
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755
    launcher_source = launcher.read_text(encoding="utf-8")
    for command_shape in (
        "revision-status:1",
        "propose-review-draft-revision:3",
        "recover-review-draft-revision:5",
        "apply-review-draft-revision:5",
        "verify-review-draft-revision:5",
    ):
        assert command_shape in launcher_source
    assert (
        "python/raos/domain/operations/"
        "self_hosted_wordpress_draft_revision_operator_v2.py"
        in launcher_source
    )
    with pytest.raises(PublicationOperatorFailure) as invalid:
        cli._parser().parse_args(["--credential=SUPERSECRET"])
    assert invalid.value.code is PublicationOperatorFailureCode.INVALID_ARGUMENT
    captured = capsys.readouterr()
    assert "SUPERSECRET" not in captured.out + captured.err
