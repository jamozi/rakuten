from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/ui-parity.mjs"
EXPECTED_NODE_VERSION = "v24.18.1"


def _node24() -> Path:
    candidates = [
        os.environ.get("RAOS_NODE"),
        "/home/minami/.local/share/raos-toolchains/node/24.18.1-npm11.16.0/bin/node",
        shutil.which("node"),
    ]
    for value in candidates:
        if value is None:
            continue
        candidate = Path(value)
        try:
            result = subprocess.run(
                [str(candidate), "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip() == EXPECTED_NODE_VERSION:
            return candidate
    raise AssertionError("RAOS_V2_EXACT_NODE_24_18_1_NOT_AVAILABLE")


def test_t_v2_023_024_033_ts_and_preview_contracts_execute_in_parity() -> None:
    result = subprocess.run(
        [str(_node24()), str(HARNESS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "RAOS_V2_UI_PARITY_RESULT_V1"
    assert payload["classification"] == "PASSED_LOCAL"
    assert payload["nodeVersion"] == "24.18.1"
    assert payload["routeCount"] == 9
    assert payload["caseCount"] == 9
    assert payload["externalActions"] == "NOT_EXECUTED"
    assert {
        row["id"]: row["state"] for row in payload["caseParity"]
    }["ANA_MISSING_AIRCRAFT_OVERSIZE_UNKNOWN"] == "UNKNOWN"


def test_t_v2_023_parity_ledger_and_preview_core_are_both_live_inputs() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    for contract in (
        "checker-parity-cases.v2.json",
        "evaluateCarryOnDecisionV2",
        "__RAOS_V2_CHECKER_CONTRACT__",
        "BROWSER_CASE_FAILED",
        "TS_CASE_FAILED",
        "CHECKER_SEGMENT_DRIFT",
        "RENDER_SEMANTIC_DRIFT",
        "DECISION_SUPPORT_V2_ROUTES",
    ):
        assert contract in source
    checker = (
        ROOT
        / "packages/web-ui/src/decision-support-v2/preview/checker.js"
    ).read_text(encoding="utf-8")
    assert (
        "if (!applicabilityMissing && (allFail || allPass || results.length === 1))"
        in checker
    )
