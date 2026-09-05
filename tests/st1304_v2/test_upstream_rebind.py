"""Hash-only maintenance of recorded synthetic dependencies; no live data."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
from types import ModuleType
from typing import Any

import pytest
import yaml

from scripts import build_st1303_attribution_engine as attribution
from scripts import build_st1304_cost_unit_economics as economics
from scripts import build_st1305_finance_reconciliation as reconciliation
from scripts import build_st1104_analytics_finance_dashboard as dashboard
from scripts.raos_build_core import discover_registry, topological_order


ROOT = Path(__file__).resolve().parents[2]
OWNERS = (economics, reconciliation)


def test_measurement_owner_precedes_the_complete_synthetic_finance_chain() -> None:
    order = topological_order(discover_registry(root=ROOT))
    chain = (
        "build_st1704_affiliate_learning",
        "build_st1303_attribution_engine",
        "build_st1304_cost_unit_economics",
        "build_st1305_finance_reconciliation",
        "build_st1104_analytics_finance_dashboard",
    )
    assert [order.index(owner) for owner in chain] == sorted(
        order.index(owner) for owner in chain
    )


def _copy_owner_root(tmp_path: Path) -> Path:
    paths = {
        *attribution.SOURCE_PATHS,
        attribution.OUTPUT_PATH,
        attribution.ST1704_CONTRACT_PATH,
        *(Path(row["path"]) for row in attribution.SOURCE_BINDINGS.values()),
    }
    for owner in OWNERS:
        paths.update(owner.SOURCE_PATHS)
        paths.add(owner.OUTPUT_PATH)
        paths.update(Path(value) for value in owner.SOURCE_BINDING_PATHS.values())
    paths.update(dashboard.OWNED_SOURCE_PATHS)
    paths.add(dashboard.SECURE_HELPER_PATH)
    paths.update(dashboard.LOCKED_TOOLCHAIN_PATHS)
    paths.update(
        (dashboard.OUTPUT_PATH, dashboard.GENERATED_TS_PATH, dashboard.MANIFEST_PATH)
    )
    dashboard_contract = yaml.safe_load((ROOT / dashboard.CONTRACT_PATH).read_bytes())
    paths.update(
        Path(row["path"]) for row in dashboard_contract["source_bindings"].values()
    )
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def _dependency_change(root: Path, owner: ModuleType) -> None:
    path = root / attribution.ST1704_CONTRACT_PATH
    source = json.loads(path.read_bytes())
    source["articles"][0]["packet_sha256"] = "f" * 64
    path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    attribution.build(root)
    if owner is reconciliation:
        economics.build(root)


def _state(root: Path, owner: ModuleType) -> dict[Path, bytes]:
    return {
        path: (root / path).read_bytes()
        for path in (owner.CONTRACT_PATH, owner.FIXTURE_PATH, owner.OUTPUT_PATH)
    }


@pytest.mark.parametrize("owner", OWNERS, ids=("economics", "reconciliation"))
def test_dependency_refresh_preserves_request_and_all_authority_states(
    tmp_path: Path,
    owner: ModuleType,
) -> None:
    root = _copy_owner_root(tmp_path)
    original_fixture = json.loads((root / owner.FIXTURE_PATH).read_bytes())
    original_contract = copy.deepcopy(owner.load_contract(root))
    _dependency_change(root, owner)
    before = _state(root, owner)
    with pytest.raises(RuntimeError):
        owner.build(root, check=True)
    assert _state(root, owner) == before
    owner.build(root)
    owner.build(root, check=True)
    fixture = json.loads((root / owner.FIXTURE_PATH).read_bytes())
    for key in ("schema_version", "profile", "scenario_id", "synthetic", "request"):
        assert fixture[key] == original_fixture[key]
    assert fixture["expected_input_sha256"] != original_fixture["expected_input_sha256"]
    assert (
        fixture["expected_result_sha256"] != original_fixture["expected_result_sha256"]
    )
    contract = owner.load_contract(root)
    for key in original_contract:
        if key not in {"source_bindings", "recorded_fixture"}:
            assert contract[key] == original_contract[key]
    for key in ("synthetic", "provider_execution", "path"):
        assert (
            contract["recorded_fixture"][key]
            == original_contract["recorded_fixture"][key]
        )
    before = _state(root, owner)
    timestamps = {
        path: (root / path).stat().st_mtime_ns
        for path in (owner.CONTRACT_PATH, owner.FIXTURE_PATH)
    }
    owner.build(root)
    assert _state(root, owner) == before
    assert timestamps == {path: (root / path).stat().st_mtime_ns for path in timestamps}


@pytest.mark.parametrize("owner", OWNERS, ids=("economics", "reconciliation"))
def test_fixture_mutation_is_not_relabelled_as_a_dependency_refresh(
    tmp_path: Path,
    owner: ModuleType,
) -> None:
    root = _copy_owner_root(tmp_path)
    _dependency_change(root, owner)
    path = root / owner.FIXTURE_PATH
    fixture = json.loads(path.read_bytes())
    fixture["request"]["requested_at"] = "2026-09-09T00:00:00Z"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    before = _state(root, owner)
    with pytest.raises(RuntimeError, match="SYNTHETIC_REBIND_INPUT_INVALID"):
        owner.build(root)
    assert _state(root, owner) == before


@pytest.mark.parametrize("owner", OWNERS, ids=("economics", "reconciliation"))
@pytest.mark.parametrize("mutation", ("live", "extra_field"))
def test_non_synthetic_or_unknown_schema_is_rejected_even_with_matching_fixture_hash(
    tmp_path: Path,
    owner: ModuleType,
    mutation: str,
) -> None:
    root = _copy_owner_root(tmp_path)
    _dependency_change(root, owner)
    path = root / owner.FIXTURE_PATH
    fixture = json.loads(path.read_bytes())
    if mutation == "live":
        fixture["synthetic"] = False
    else:
        fixture["unexpected"] = "fixture-only"
    payload = (json.dumps(fixture, indent=2) + "\n").encode()
    path.write_bytes(payload)
    contract = owner.load_contract(root)
    contract["recorded_fixture"]["sha256"] = hashlib.sha256(payload).hexdigest()
    (root / owner.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    before = _state(root, owner)
    with pytest.raises(RuntimeError, match="SYNTHETIC_REBIND_INPUT_INVALID"):
        owner.build(root)
    assert _state(root, owner) == before


@pytest.mark.parametrize("owner", OWNERS, ids=("economics", "reconciliation"))
def test_different_article_slot_identity_cannot_be_rebound(
    tmp_path: Path,
    owner: ModuleType,
) -> None:
    root = _copy_owner_root(tmp_path)
    _dependency_change(root, owner)
    path = root / owner.OUTPUT_PATH
    previous = json.loads(path.read_bytes())
    previous["measurement_boundary"]["article_slots"][0]["article_id"] = "other-article"
    path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
    before = _state(root, owner)
    with pytest.raises(RuntimeError, match="UPSTREAM_ARTICLE_IDENTITY_DRIFT"):
        owner.build(root)
    assert _state(root, owner) == before


@pytest.mark.parametrize("field", ("slug", "intent_classification"))
def test_reconciliation_also_requires_unchanged_slug_and_intent(
    tmp_path: Path,
    field: str,
) -> None:
    root = _copy_owner_root(tmp_path)
    _dependency_change(root, reconciliation)
    path = root / reconciliation.OUTPUT_PATH
    previous = json.loads(path.read_bytes())
    previous["measurement_boundary"]["article_slots"][0][field] = "other-identity"
    path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="UPSTREAM_ARTICLE_IDENTITY_DRIFT"):
        reconciliation.build(root)


@pytest.mark.parametrize("owner", OWNERS, ids=("economics", "reconciliation"))
def test_failed_contract_write_restores_previous_fixture(
    tmp_path: Path,
    owner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_owner_root(tmp_path)
    _dependency_change(root, owner)
    before = _state(root, owner)
    writer = owner._atomic_write
    failure = (
        economics.UnitEconomicsBuildError
        if owner is economics
        else (reconciliation.FinanceReconciliationBuildError)
    )

    def reject_contract(root: Path, payload: bytes, **kwargs: Any) -> None:
        if kwargs.get("relative") == owner.CONTRACT_PATH:
            raise failure("synthetic contract write failure")
        writer(root, payload, **kwargs)

    monkeypatch.setattr(owner, "_atomic_write", reject_contract)
    with pytest.raises(failure, match="synthetic contract write failure"):
        owner.build(root)
    assert _state(root, owner) == before


def test_dashboard_refresh_changes_only_upstream_references(
    tmp_path: Path,
) -> None:
    root = _copy_owner_root(tmp_path)
    fixture_before = json.loads((root / dashboard.FIXTURE_PATH).read_bytes())
    contract_before = copy.deepcopy(dashboard._load_contract(root))
    _dependency_change(root, reconciliation)
    before = _state(root, dashboard)
    with pytest.raises(Exception):
        dashboard.build(root, check=True)
    assert _state(root, dashboard) == before
    dashboard.build(root)
    dashboard.build(root, check=True)
    fixture = json.loads((root / dashboard.FIXTURE_PATH).read_bytes())
    assert (
        fixture["source_bindings"]["st1304_input_sha256"]
        != (fixture_before["source_bindings"]["st1304_input_sha256"])
    )
    fixture["source_bindings"] = fixture_before["source_bindings"]
    assert fixture == fixture_before
    contract = dashboard._load_contract(root)
    for key in contract_before:
        if key not in {"source_bindings", "recorded_fixture"}:
            assert contract[key] == contract_before[key]
    timestamps = {
        path: (root / path).stat().st_mtime_ns
        for path in (dashboard.CONTRACT_PATH, dashboard.FIXTURE_PATH)
    }
    dashboard.build(root)
    assert timestamps == {path: (root / path).stat().st_mtime_ns for path in timestamps}


@pytest.mark.parametrize("mutation", ("authority", "source_hash", "extra_field"))
def test_dashboard_refresh_cannot_normalize_false_authority_or_tampered_sources(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = _copy_owner_root(tmp_path)
    path = root / dashboard.FIXTURE_PATH
    fixture = json.loads(path.read_bytes())
    if mutation == "authority":
        fixture["publication_authorized"] = True
    elif mutation == "source_hash":
        fixture["source_bindings"]["st1304_input_sha256"] = "0" * 64
    else:
        fixture["unexpected"] = "fixture-only"
    payload = (json.dumps(fixture, indent=2) + "\n").encode()
    path.write_bytes(payload)
    contract_path = root / dashboard.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    contract["recorded_fixture"].update(
        sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)
    )
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    before = _state(root, dashboard)
    with pytest.raises(
        dashboard.DashboardBuildError, match="SYNTHETIC_REBIND_INPUT_INVALID"
    ):
        dashboard.build(root)
    assert _state(root, dashboard) == before
