"""Offline template refreshes must never create fresh or successful evidence."""

import json
from pathlib import Path

import pytest

from scripts import build_wordpress_quality_baseline as generator
from scripts.raos_build_core import affected_generation_owners, discover_registry


def test_make_and_test_changes_refresh_baseline_before_its_consumers() -> None:
    registry = discover_registry()
    for path in ("Makefile", "tests/wordpress_quality_audit_v1/test_contract.py"):
        owners = affected_generation_owners(registry, (Path(path),))
        assert owners.index("build_wordpress_quality_baseline") < owners.index(
            "build_wordpress_mcp_v1"
        )


def test_changed_fingerprints_remain_not_executed_at_the_fixed_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fingerprints(_contract, _root):
        return {name: "a" * 64 for name in generator.audit.EXPECTED_FINGERPRINT_INPUTS}

    monkeypatch.setattr(generator.audit, "repository_fingerprints", fingerprints)
    first = generator.render()
    assert generator.render() == first
    ledger = json.loads(first)
    assert ledger["evaluated_at"] == generator.TEMPLATE_ANCHOR
    assert ledger["completion"]["status"] == "BLOCKED"
    assert ledger["completion"]["consecutive_clean_rounds"] == 0
    assert set(ledger["external_execution"].values()) == {"NOT_EXECUTED"}
