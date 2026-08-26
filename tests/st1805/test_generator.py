from __future__ import annotations

import copy
import json
import subprocess

import pytest

from scripts import build_st1805_portfolio_decision as builder


def test_contract_dependency_bindings_are_semantic_paths() -> None:
    contract = builder.load_contract()
    bindings = builder._flatten_bindings(contract)
    assert set(bindings) == {
        *builder.EXPECTED_CANONICAL_BINDINGS,
        *builder.EXPECTED_PREDECESSOR_PATHS,
    }
    assert all((builder.REPO_ROOT / path).is_file() for path in bindings)


def test_pack_is_deterministic_and_current(output_path) -> None:
    first = builder.render_pack()
    second = builder.render_pack()
    assert first == second
    assert output_path.read_bytes() == first


def test_pack_is_blocked_and_non_attesting(generated_pack) -> None:
    builder.validate_pack(generated_pack)
    assert generated_pack["overall"] == "BLOCKED"
    assert generated_pack["decision"]["outcome"] == "NO_DECISION"
    assert generated_pack["actual_observations"] == []
    assert generated_pack["verification"]["formal_TST-032"] == "NOT_EXECUTED"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("overall",), "PASS"),
        (("acceptance_criteria_satisfied",), True),
        (("decision", "authorized"), True),
        (("decision", "outcome"), "SCALE"),
        (("decision", "human_decision_required"), False),
        (("authority", "scale_hold_pivot"), "AUTOMATION"),
        (("finance_editorial_boundary", "profit_used_for_product_ranking"), True),
        (("mandatory_criteria", 0, "status"), "PASS"),
    ],
)
def test_pack_rejects_promotion(generated_pack, path, value) -> None:
    mutated = copy.deepcopy(generated_pack)
    target = mutated
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises(SystemExit):
        builder.validate_pack(mutated)


def test_pack_rejects_unknown_field(generated_pack) -> None:
    generated_pack["unknown"] = True
    with pytest.raises(SystemExit):
        builder.validate_pack(generated_pack)


def test_dependency_state_preserves_block(generated_pack) -> None:
    state = generated_pack["dependency_state"]
    assert state["qualifies_for_business_decision"] is False
    assert state["ST-1804"] == {
        "acceptance_criteria_satisfied": False,
        "actual_observation_count": 0,
        "gate_pass_claim": False,
        "overall": "BLOCKED",
        "owner_id": "build_st1804_gate3_economics",
        "owner_version": 2,
        "scale_authority": "NONE",
        "schema": "ST1804_GATE3_PACK_V1",
        "synthetic": True,
    }


def test_cli_requires_isolated_no_bytecode_mode() -> None:
    result = subprocess.run(
        [
            "/home/minami/rakuten/.venv/bin/python",
            str(builder.REPO_ROOT / builder.GENERATOR_PATH),
            "--check",
        ],
        cwd=builder.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "ISOLATED_MODE_REQUIRED" in result.stderr
    assert "ST1805_CHECK_OK" not in result.stdout


def test_generated_json_has_no_nan_or_financial_value_fields() -> None:
    rendered = builder.render_pack()
    parsed = json.loads(rendered, parse_constant=lambda value: pytest.fail(value))
    assert parsed["recorded_synthetic_evaluation"]["decision"]["outcome"] == (
        "NO_DECISION"
    )
    forbidden = (b'"reward_jpy"', b'"epc"', b'"rpm"', b'"profit_jpy"')
    assert all(token not in rendered for token in forbidden)
