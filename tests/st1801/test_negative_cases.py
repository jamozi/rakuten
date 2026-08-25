from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_st1801_portfolio_expansion as builder


def test_st1705_dependency_drift_fails_closed(repository_copy: Path) -> None:
    path = (
        repository_copy
        / "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json"
    )
    document = json.loads(path.read_text())
    document["decision"]["downstream_st_1801_eligibility"] = "ELIGIBLE"
    path.write_text(json.dumps(document))
    with pytest.raises(builder.PortfolioExpansionError, match="PINNED_INPUT_DRIFT"):
        builder.load_contract(repository_copy)


def test_contract_unknown_category_fails_closed(contract: dict[str, object]) -> None:
    contract["portfolio_policy"]["category"]["planning_category_ref"] = "INVENTED"  # type: ignore[index]
    with pytest.raises(builder.PortfolioExpansionError):
        builder._exact(contract, builder._expected_contract_sections(), "contract")


def test_contract_unknown_program_fails_closed(contract: dict[str, object]) -> None:
    contract["portfolio_policy"]["program"] = "INVENTED_PROGRAM"  # type: ignore[index]
    with pytest.raises(builder.PortfolioExpansionError):
        builder._exact(contract, builder._expected_contract_sections(), "contract")


def test_json_duplicate_key_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1801/fixtures/duplicate.json")
    path = repository_copy / relative
    path.write_text('{"value": 1, "value": 2}\n')
    with pytest.raises(builder.PortfolioExpansionError, match="JSON_DUPLICATE_KEY"):
        builder._load_json(repository_copy, relative, "duplicate")


def test_yaml_duplicate_key_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1801/fixtures/duplicate.yaml")
    path = repository_copy / relative
    path.write_text("value: 1\nvalue: 2\n")
    with pytest.raises(builder.PortfolioExpansionError, match="YAML_INVALID"):
        builder._load_yaml(repository_copy, relative, "duplicate")


def test_yaml_alias_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1801/fixtures/alias.yaml")
    path = repository_copy / relative
    path.write_text("value: &anchor 1\ncopy: *anchor\n")
    with pytest.raises(builder.PortfolioExpansionError, match="YAML_ALIAS_FORBIDDEN"):
        builder._load_yaml(repository_copy, relative, "alias")


def test_input_symlink_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    moved = target.with_suffix(".real")
    target.rename(moved)
    target.symlink_to(moved.name)
    with pytest.raises(builder.PortfolioExpansionError, match="UNSAFE_FILE_TYPE"):
        builder.load_contract(repository_copy)


def test_input_hardlink_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    linked = target.with_suffix(".linked")
    os.link(target, linked)
    with pytest.raises(builder.PortfolioExpansionError, match="UNSAFE_FILE_LINK_COUNT"):
        builder.load_contract(repository_copy)


def test_oversized_input_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    target.write_bytes(b"x" * (builder.MAX_INPUT_BYTES + 1))
    with pytest.raises(builder.PortfolioExpansionError, match="INPUT_SIZE_LIMIT"):
        builder.load_contract(repository_copy)


@pytest.mark.parametrize("target_path", [builder.PACK_PATH, builder.MANIFEST_PATH])
def test_output_symlink_is_rejected(repository_copy: Path, target_path: Path) -> None:
    destination = repository_copy / target_path
    destination.write_text("foreign")
    moved = destination.with_suffix(destination.suffix + ".real")
    destination.rename(moved)
    destination.symlink_to(moved.name)
    with pytest.raises(builder.PortfolioExpansionError, match="UNSAFE_OUTPUT_TARGET"):
        builder.build(repository_copy)


def test_check_refuses_pending_recovery_without_writing(repository_copy: Path) -> None:
    output = repository_copy / builder.PACK_PATH.parent
    journal = output / builder.TRANSACTION_NAME
    journal.write_text("{}\n")
    journal.chmod(0o600)
    before = journal.read_bytes()
    with pytest.raises(
        builder.PortfolioExpansionError, match="OUTPUT_RECOVERY_REQUIRED"
    ):
        builder.build(repository_copy, check=True)
    assert journal.read_bytes() == before
