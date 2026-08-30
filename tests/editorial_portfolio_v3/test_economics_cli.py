from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_editorial_economics_v3.py"
SPEC = importlib.util.spec_from_file_location("raos_editorial_economics_v3", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cli = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cli
SPEC.loader.exec_module(cli)


def test_candidate_query_template_cli_writes_private_independent_input(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)

    assert (
        cli.main(
            [
                "--private-root",
                private_root.as_posix(),
                "candidate-query-template",
                "--output",
                "candidate.json",
            ]
        )
        == 0
    )

    output = private_root / "candidate.json"
    document = json.loads(output.read_text(encoding="utf-8"))
    assert (
        document["aggregation_basis"]
        == "GSC_QUERY_DIMENSION_CANDIDATE_CLUSTER_NOT_ARTICLE_TOTAL"
    )
    assert document["article_totals_reused"] is False
    assert document["raw_queries_included"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_followup_parser_accepts_private_candidate_query_input() -> None:
    arguments = cli._parser().parse_args(
        [
            "evaluate-followups",
            "--baseline",
            "baseline.json",
            "--candidate-query-demand",
            "candidate.json",
            "--as-of",
            "2026-11-27",
            "--output",
            "followups.json",
        ]
    )
    assert arguments.candidate_query_demand == "candidate.json"


def test_establish_t0_parser_requires_exact_activation_dry_run() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "establish-t0",
                "--observation",
                "production-readbacks.json",
                "--output",
                "t0.json",
            ]
        )

    arguments = cli._parser().parse_args(
        [
            "establish-t0",
            "--observation",
            "production-readbacks.json",
            "--rakuten-activation-dry-run",
            "rakuten-activation.json",
            "--output",
            "t0.json",
        ]
    )
    assert arguments.rakuten_activation_dry_run == "rakuten-activation.json"
