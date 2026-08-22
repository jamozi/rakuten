"""Hostile fail-closed tests for ST-1701."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1506_production_deployment as base_generator
from scripts import build_st1701_business_inputs as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_BUSINESS_INPUT_1701"


def _validate(document: dict[str, Any]) -> None:
    generator.validate_contract(document, REPOSITORY_ROOT)


def _validate_decision_package(document: dict[str, Any]) -> None:
    generator.validate_decision_package(document, REPOSITORY_ROOT)


def _leaf_paths(
    value: object, prefix: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    if isinstance(value, dict):
        return [
            path
            for key, nested in value.items()
            for path in _leaf_paths(nested, (*prefix, str(key)))
        ]
    if isinstance(value, list):
        return [
            path
            for index, nested in enumerate(value)
            for path in _leaf_paths(nested, (*prefix, index))
        ]
    return [prefix]


def _different_leaf(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return f"{value}_DRIFT"
    if value is None:
        return MARKER
    raise AssertionError("unsupported test leaf")


@pytest.mark.parametrize("field", tuple(generator.EXPECTED_BUSINESS_INPUTS))
def test_no_business_value_or_resolution_payload_can_be_selected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["business_inputs"][field] = MARKER
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("blocking", False),
        ("resolution_state", "RESOLVED"),
        ("active_blocker", False),
        ("blocked_targets", ["GATE-0"]),
        ("safe_default_is_resolution", True),
        ("selected_value", MARKER),
        ("resolution_payload", {"value": MARKER}),
    ),
)
def test_decision_rows_cannot_be_resolved_or_weakened(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["decisions"][0][field] = value
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("mutation", ("remove", "duplicate", "reorder", "extra"))
def test_exact_decision_inventory_cannot_change(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    decisions = document["decisions"]
    if mutation == "remove":
        decisions.pop()
    elif mutation == "duplicate":
        decisions[1] = copy.deepcopy(decisions[0])
    elif mutation == "reorder":
        decisions[0], decisions[1] = decisions[1], decisions[0]
    else:
        decisions.append(copy.deepcopy(decisions[-1]))
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


@pytest.mark.parametrize("value", (1, True, 0.0, "0"))
def test_action_counts_require_exact_builtin_zero(
    contract_document: dict[str, Any], value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["action_boundary"]["action_counts"]["production"] = value
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("safe_defaults", "selected_values", "ALLOWED"),
        ("safe_defaults", "safe_defaults_are_resolutions", True),
        ("safe_defaults", "external_publication", "ALLOWED"),
        ("safe_defaults", "production", "ENABLED"),
        ("activation", "enabled", True),
        ("activation", "status", "ACTIVE"),
        ("action_boundary", "external_actions", "ALLOWED"),
        ("action_boundary", "publication", "ALLOWED"),
        ("action_boundary", "staging", "ALLOWED"),
        ("action_boundary", "release", "ALLOWED"),
        ("action_boundary", "production", "ALLOWED"),
        ("evidence_boundary", "formal_tst_032", "PASS"),
        ("evidence_boundary", "human_approvals", "OBTAINED"),
        ("evidence_boundary", "st_1701_acceptance_achieved", True),
        ("downstream_boundary", "st_1702_ready", True),
        ("downstream_boundary", "publication_ready", True),
        ("downstream_boundary", "release_ready", True),
        ("downstream_boundary", "production_ready", True),
    ),
)
def test_safe_gate_evidence_and_downstream_boundaries_cannot_be_promoted(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


def test_source_inventory_is_ordered_unique_and_hash_bound(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("reorder", "duplicate", "hash", "bytes"):
        document = copy.deepcopy(contract_document)
        sources = document["sources"]
        if mutation == "reorder":
            sources[0], sources[1] = sources[1], sources[0]
        elif mutation == "duplicate":
            sources[0] = copy.deepcopy(sources[1])
        elif mutation == "hash":
            sources[0]["sha256"] = "0" * 64
        else:
            sources[0]["bytes"] = 1
        with pytest.raises(generator.BusinessInputsError):
            _validate(document)


def test_unknown_missing_and_reordered_contract_keys_are_rejected(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("unknown", "missing", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "unknown":
            document[MARKER] = MARKER
        elif mutation == "missing":
            document.pop("downstream_boundary")
        else:
            first = document.pop("document")
            document["document"] = first
        with pytest.raises(generator.BusinessInputsError) as captured:
            _validate(document)
        assert MARKER not in str(captured.value)


def test_strict_yaml_rejects_duplicates_aliases_and_unsafe_tags(tmp_path: Path) -> None:
    payloads = (
        "document: safe\ndocument: blocked\n",
        "value: &blocked safe\ncopy: *blocked\n",
        "value: !!python/object/apply:os.system ['blocked']\n",
    )
    for index, payload in enumerate(payloads):
        path = tmp_path / f"hostile-{index}.yaml"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(base_generator.ProductionDeploymentContractError):
            base_generator.load_yaml(path)


@pytest.mark.parametrize("mutation", ("unknown", "missing", "reorder"))
def test_decision_package_top_level_is_closed_and_ordered(
    decision_package: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(decision_package)
    if mutation == "unknown":
        document[MARKER] = MARKER
    elif mutation == "missing":
        document.pop("action_boundary")
    else:
        first = document.pop("document")
        document["document"] = first
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate_decision_package(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("identifier", "field_path", "value"),
    (
        ("OD-001", ("record_status",), "RESOLVED"),
        ("OD-001", ("runtime_activation",), "ACTIVE"),
        ("OD-002", ("execution_state", "domain_purchase"), "EXECUTED"),
        ("OD-005", ("selected_value", "alternate_reviewer"), "REVIEWER_2"),
        ("OD-005", ("selected_value", "standard_labor_cost", "amount"), 3000.0),
        ("OD-006", ("evidence_gate", "minimum_listing_count"), 29),
        ("OD-006", ("evidence_gate", "minimum_product_family_count"), 9),
        ("OD-006", ("evidence_gate", "minimum_shop_count"), 4),
        ("OD-006", ("evidence_gate", "maximum_false_automatic_merges"), 1),
        ("OD-007", ("selected_value", "maximum_age", "price_hours"), 73),
        ("OD-009", ("selected_value", "monthly_external_spend_cap"), 30001),
        (
            "OD-009",
            ("selected_value", "thresholds", "hard_stop_new_external_spend_percent"),
            101,
        ),
    ),
)
def test_scoped_candidate_status_values_and_thresholds_are_exact(
    decision_package: dict[str, Any],
    identifier: str,
    field_path: tuple[str, ...],
    value: object,
) -> None:
    document = copy.deepcopy(decision_package)
    row = next(row for row in document["scoped_decisions"] if row["id"] == identifier)
    target = row
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate_decision_package(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("identifier", "original_status"),
    (
        ("OD-002", "EXECUTION_PENDING"),
        ("OD-005", "PARTIAL"),
        ("OD-006", "EVIDENCE_PENDING"),
    ),
)
def test_each_pending_scoped_status_cannot_be_promoted_to_resolved(
    decision_package: dict[str, Any], identifier: str, original_status: str
) -> None:
    document = copy.deepcopy(decision_package)
    row = next(row for row in document["scoped_decisions"] if row["id"] == identifier)
    assert row["record_status"] == original_status
    row["record_status"] = "RESOLVED"
    with pytest.raises(generator.BusinessInputsError):
        _validate_decision_package(document)


@pytest.mark.parametrize("mutation", ("remove", "duplicate", "reorder", "extra"))
def test_decision_package_scoped_inventory_is_exact(
    decision_package: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(decision_package)
    rows = document["scoped_decisions"]
    if mutation == "remove":
        rows.pop()
    elif mutation == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows.append(copy.deepcopy(rows[-1]))
    with pytest.raises(generator.BusinessInputsError):
        _validate_decision_package(document)


def test_every_scoped_decision_leaf_is_exactly_closed(
    decision_package: dict[str, Any],
) -> None:
    handoff, _approval = generator._authority_documents(REPOSITORY_ROOT)  # noqa: SLF001
    for row_index, row in enumerate(decision_package["scoped_decisions"]):
        for path in _leaf_paths(row):
            document = copy.deepcopy(decision_package)
            target: Any = document["scoped_decisions"][row_index]
            for field in path[:-1]:
                target = target[field]
            leaf = path[-1]
            target[leaf] = _different_leaf(target[leaf])
            with pytest.raises(generator.BusinessInputsError):
                generator.validate_decision_package(
                    document, REPOSITORY_ROOT, handoff=handoff
                )


@pytest.mark.parametrize("mutation", ("remove", "duplicate", "reorder", "promote"))
def test_informational_inventory_is_exact_and_cannot_promote_status(
    decision_package: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(decision_package)
    rows = document["informational_cross_story_owner_inputs"]["rows"]
    if mutation == "remove":
        rows.pop()
    elif mutation == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[0]["record_status"] = "RESOLVED"
    with pytest.raises(generator.BusinessInputsError):
        _validate_decision_package(document)


def test_final_package_cannot_self_approve_or_promote_revision_readiness(
    decision_package: dict[str, Any],
) -> None:
    mutations = (
        ("status", "APPROVED"),
        ("approved_source_contract_sha256", "0" * 64),
        ("canonical_revision_evidence_authority", "OWNER_APPROVED"),
    )
    for field, value in mutations:
        document = copy.deepcopy(decision_package)
        document["final_package_approval"][field] = value
        with pytest.raises(generator.BusinessInputsError):
            _validate_decision_package(document)


def test_candidate_cannot_change_canonical_gate_or_downstream_truth(
    decision_package: dict[str, Any],
) -> None:
    mutations = (
        ("canonical_open_decisions_document_status", "RESOLVED"),
        ("scoped_unresolved_count", 0),
        ("global_unresolved_blocker_count", 0),
        ("activation", "ACTIVE"),
        ("gate_state", "PASS"),
        ("st1701_acceptance", "ACHIEVED"),
    )
    for field, value in mutations:
        document = copy.deepcopy(decision_package)
        document["canonical_truth_boundary"][field] = value
        with pytest.raises(generator.BusinessInputsError):
            _validate_decision_package(document)


@pytest.mark.parametrize("value", (1, True, 0.0, "0"))
def test_decision_action_counts_require_exact_builtin_zero(
    decision_package: dict[str, Any], value: object
) -> None:
    document = copy.deepcopy(decision_package)
    document["action_boundary"]["action_counts"]["external"] = value
    with pytest.raises(generator.BusinessInputsError):
        _validate_decision_package(document)


def test_nested_mapping_key_reordering_is_rejected(
    decision_package: dict[str, Any],
) -> None:
    document = copy.deepcopy(decision_package)
    selected = document["scoped_decisions"][0]["selected_value"]
    first = selected.pop("category_id")
    selected["category_id"] = first
    with pytest.raises(generator.BusinessInputsError):
        _validate_decision_package(document)


def test_authority_hash_or_scope_drift_is_rejected(
    decision_package: dict[str, Any],
) -> None:
    for path, value in (
        (("implementation_authority", "handoff", "sha256"), "0" * 64),
        (("implementation_authority", "approval", "sha256"), "0" * 64),
        (("implementation_authority", "approved_story"), "ST-1702"),
    ):
        document = copy.deepcopy(decision_package)
        target = document
        for field in path[:-1]:
            target = target[field]
        target[path[-1]] = value
        with pytest.raises(generator.BusinessInputsError):
            _validate_decision_package(document)


def _copy_gold_authority_fixture(root: Path) -> None:
    relative_paths = dict.fromkeys(
        (
            generator.HANDOFF_PATH,
            generator.HANDOFF_APPROVAL_PATH,
            generator.DECISION_PACKAGE_PATH,
            generator.FINAL_PACKAGE_APPROVAL_PATH,
            generator.GOLD_HANDOFF_PATH,
            generator.GOLD_HANDOFF_APPROVAL_PATH,
            *(
                Path(path)
                for path, _size, _digest in generator.EXPECTED_GOLD_SOURCE_ROWS[:-2]
            ),
        )
    )
    for relative in relative_paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY_ROOT / relative).read_bytes())


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_handoff",
        "missing_approval",
        "tampered_handoff",
        "tampered_approval",
        "mismatched_binding",
        "predecessor_drift",
    ),
)
def test_gold_authority_missing_tampered_or_mismatched_input_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _copy_gold_authority_fixture(root)
    handoff, approval = generator.load_gold_authority(root)
    assert handoff["approved_story"] == "ST-1701"
    assert approval["handoff_sha256"] == generator.GOLD_HANDOFF_SHA256

    if mutation == "missing_handoff":
        (root / generator.GOLD_HANDOFF_PATH).unlink()
    elif mutation == "missing_approval":
        (root / generator.GOLD_HANDOFF_APPROVAL_PATH).unlink()
    elif mutation == "tampered_handoff":
        path = root / generator.GOLD_HANDOFF_PATH
        path.write_bytes(path.read_bytes() + b"# tampered\n")
    elif mutation == "tampered_approval":
        path = root / generator.GOLD_HANDOFF_APPROVAL_PATH
        path.write_bytes(path.read_bytes() + b"# tampered\n")
    elif mutation == "mismatched_binding":
        path = root / generator.GOLD_HANDOFF_APPROVAL_PATH
        content = path.read_bytes()
        assert generator.GOLD_HANDOFF_SHA256.encode() in content
        path.write_bytes(
            content.replace(generator.GOLD_HANDOFF_SHA256.encode(), b"0" * 64)
        )
    else:
        predecessor = root / Path(generator.EXPECTED_GOLD_SOURCE_ROWS[0][0])
        predecessor.write_bytes(predecessor.read_bytes() + b"# drift\n")

    with pytest.raises(
        (
            generator.BusinessInputsError,
            base_generator.ProductionDeploymentContractError,
        )
    ):
        generator.load_gold_authority(root)


@pytest.mark.parametrize(
    ("relative", "error_code"),
    (
        (
            generator.GOLD_LEDGER_PATH,
            "GOLD_LEDGER_ACCEPTANCE_UNAVAILABLE",
        ),
        (
            generator.GOLD_EVIDENCE_APPROVAL_PATH,
            "GOLD_APPROVAL_ACCEPTANCE_UNAVAILABLE",
        ),
        *(
            (relative, "GOLD_POSTAPPROVAL_ARTIFACT_FORBIDDEN")
            for relative in generator.GOLD_POSTAPPROVAL_PATHS
        ),
    ),
)
def test_any_unvalidated_gold_ledger_approval_or_postapproval_artifact_fails_closed(
    tmp_path: Path, relative: Path, error_code: str
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _copy_gold_authority_fixture(root)
    assert generator.gold_evidence_validation_document(root)["status"] == (
        "EVIDENCE_INSUFFICIENT"
    )

    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"intentionally-incomplete-test-marker\n")
    with pytest.raises(generator.BusinessInputsError) as captured:
        generator.gold_evidence_validation_document(root)
    assert f"code={error_code}" in str(captured.value)


@pytest.mark.parametrize(
    "relative", (generator.GOLD_LEDGER_PATH, generator.GOLD_EVIDENCE_APPROVAL_PATH)
)
@pytest.mark.parametrize("shape", ("symlink", "directory"))
def test_optional_gold_input_non_regular_leaf_fails_closed(
    tmp_path: Path, relative: Path, shape: str
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _copy_gold_authority_fixture(root)
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if shape == "symlink":
        outside = tmp_path / "outside.yaml"
        outside.write_bytes(b"outside\n")
        target.symlink_to(outside)
    else:
        target.mkdir()

    with pytest.raises(generator.BusinessInputsError) as captured:
        generator.gold_evidence_validation_document(root)
    assert "code=UNSAFE_FILE_TYPE" in str(captured.value)


def test_optional_gold_input_symlinked_ancestor_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _copy_gold_authority_fixture(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_parent = root / generator.GOLD_LEDGER_PATH.parent
    assert not evidence_parent.exists()
    evidence_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(generator.BusinessInputsError) as captured:
        generator.gold_evidence_validation_document(root)
    assert "code=UNSAFE_ANCESTOR" in str(captured.value)


def test_current_development_authority_drift_fails_closed_without_echo(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    marker = b"REJECTED_CURRENT_AUTHORITY_1701"
    (root / generator.STANDING_DEVELOPMENT_AUTHORITY_PATH).write_bytes(marker)
    with pytest.raises(generator.BusinessInputsError) as captured:
        generator._validate_current_development_authority(root)
    assert captured.value.code == "CURRENT_DEVELOPMENT_AUTHORITY_DRIFT"
    assert marker.decode() not in str(captured.value)


def test_current_execplan_drift_uses_separate_fail_closed_binding(
    contract_document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original_read = generator._read

    def drifted_read(root: Path, relative: Path, field: str) -> bytes:
        if relative == Path("docs/execplans/RAOS-IMPLEMENTATION-FIRST.md"):
            return b"rejected current execplan"
        return original_read(root, relative, field)

    monkeypatch.setattr(generator, "_read", drifted_read)
    with pytest.raises(generator.BusinessInputsError) as captured:
        generator._verify_rows(
            REPOSITORY_ROOT,
            contract_document["sources"],
            generator.EXPECTED_SOURCE_ROWS,
            "sources",
        )
    assert captured.value.code == "CURRENT_DEVELOPMENT_SOURCE_DRIFT"


def test_current_production_helper_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = generator._read

    def drifted_read(root: Path, relative: Path, field: str) -> bytes:
        if relative == Path("scripts/build_st1506_production_deployment.py"):
            return b"rejected current production helper"
        return original_read(root, relative, field)

    monkeypatch.setattr(generator, "_read", drifted_read)
    with pytest.raises(generator.BusinessInputsError) as captured:
        generator._validate_implementation_dependencies(REPOSITORY_ROOT)
    assert captured.value.code == "IMPLEMENTATION_DEPENDENCY_DRIFT"


def test_historical_execplan_row_cannot_be_silently_replaced_by_current_binding(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    current_size, current_digest = generator.CURRENT_DEVELOPMENT_SOURCE_OVERRIDES[
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md"
    ]
    row = next(
        item
        for item in document["sources"]
        if item["uri"] == "repo://docs/execplans/RAOS-IMPLEMENTATION-FIRST.md"
    )
    row["bytes"] = current_size
    row["sha256"] = current_digest
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate(document)
    assert captured.value.code == "INVENTORY_DRIFT"


def _copy_final_approval_authority_fixture(root: Path) -> None:
    for relative in (
        generator.HANDOFF_PATH,
        generator.HANDOFF_APPROVAL_PATH,
        generator.DECISION_PACKAGE_PATH,
        generator.FINAL_PACKAGE_APPROVAL_PATH,
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY_ROOT / relative).read_bytes())


@pytest.mark.parametrize(
    "mutation",
    ("missing_approval", "tampered_approval", "mismatched_source"),
)
def test_detached_final_approval_file_and_bound_source_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _copy_final_approval_authority_fixture(root)
    assert generator.load_final_package_approval(root)["status"] == (
        generator.FINAL_PACKAGE_APPROVAL_STATUS
    )

    if mutation == "missing_approval":
        (root / generator.FINAL_PACKAGE_APPROVAL_PATH).unlink()
    elif mutation == "tampered_approval":
        path = root / generator.FINAL_PACKAGE_APPROVAL_PATH
        path.write_bytes(path.read_bytes() + b"# tampered\n")
    else:
        path = root / generator.DECISION_PACKAGE_PATH
        source = path.read_bytes()
        path.write_bytes(source[:-1] + (b" " if source[-1:] != b" " else b"\n"))

    with pytest.raises(
        (
            generator.BusinessInputsError,
            base_generator.ProductionDeploymentContractError,
        )
    ):
        generator.load_final_package_approval(root)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("story_id",), "ST-1702"),
        (("source_package_uri",), "repo://changes/st-1701/contracts/other.yaml"),
        (("source_package_sha256",), "0" * 64),
        (("source_package_bytes",), generator.APPROVED_DECISION_PACKAGE_BYTES + 1),
        (("status",), "RESOLVED"),
        (("authority",), "CANONICAL_MUTATION"),
        (("implementation_handoff", "sha256"), "0" * 64),
        (("implementation_handoff_approval", "sha256"), "0" * 64),
        (("open_decisions",), ["UNRESOLVED"]),
        (("effective_boundary", "canonical_mutation_authority"), "WRITE"),
        (("effective_boundary", "gate_state"), "PASS"),
        (("effective_boundary", "st1701_acceptance"), "ACHIEVED"),
    ),
)
def test_detached_final_approval_binding_or_promotion_mismatch_is_rejected(
    path: tuple[str, ...], value: object
) -> None:
    document = copy.deepcopy(generator.EXPECTED_FINAL_PACKAGE_APPROVAL_DOCUMENT)
    target: dict[str, Any] = document["MVP_BUSINESS_DECISION_PACKAGE_APPROVAL_V1"]
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    with pytest.raises(generator.BusinessInputsError):
        generator.validate_final_package_approval(document, REPOSITORY_ROOT)


def test_projection_helpers_cannot_accept_a_forged_effective_approval(
    decision_package: dict[str, Any], contract_document: dict[str, Any]
) -> None:
    forged = copy.deepcopy(dict(generator.load_final_package_approval(REPOSITORY_ROOT)))
    forged["effective_boundary"]["gate_state"] = "PASS"
    with pytest.raises(generator.BusinessInputsError):
        generator.decision_read_model(
            decision_package,
            contract_document,
            REPOSITORY_ROOT,
            final_approval=forged,
        )
    with pytest.raises(generator.BusinessInputsError):
        generator.canonical_revision_request_bytes(
            decision_package,
            REPOSITORY_ROOT,
            final_approval=forged,
        )


def test_projection_helpers_cannot_claim_approved_hash_for_forged_package(
    decision_package: dict[str, Any], contract_document: dict[str, Any]
) -> None:
    forged = copy.deepcopy(decision_package)
    forged["scoped_decisions"][0]["record_status"] = "RESOLVED"
    with pytest.raises(generator.BusinessInputsError):
        generator.decision_read_model(forged, contract_document, REPOSITORY_ROOT)
    with pytest.raises(generator.BusinessInputsError):
        generator.canonical_revision_request_bytes(forged, REPOSITORY_ROOT)


def test_projection_helpers_cannot_claim_source_truth_for_forged_unresolved_input(
    decision_package: dict[str, Any], contract_document: dict[str, Any]
) -> None:
    forged = copy.deepcopy(contract_document)
    forged["gates"][0]["status"] = "PASS"
    with pytest.raises(generator.BusinessInputsError):
        generator.reference_document(forged, REPOSITORY_ROOT)
    with pytest.raises(generator.BusinessInputsError):
        generator.decision_read_model(decision_package, forged, REPOSITORY_ROOT)


def test_repository_path_traversal_and_symlinked_input_ancestor_are_rejected(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.yaml").write_text("safe: true\n", encoding="utf-8")
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(  # noqa: SLF001
            tmp_path, Path("../outside/payload.yaml"), "hostile"
        )
    assert captured.value.code == "UNSAFE_REPOSITORY_PATH"

    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(root, Path("linked/payload.yaml"), "hostile")  # noqa: SLF001
    assert captured.value.code == "UNSAFE_ANCESTOR"


def test_input_leaf_root_and_regular_file_ancestor_shapes_are_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("safe: true\n", encoding="utf-8")

    (root / "leaf.yaml").symlink_to(outside)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(root, Path("leaf.yaml"), "hostile")  # noqa: SLF001
    assert captured.value.code == "UNSAFE_FILE_TYPE"

    (root / "leaf.yaml").unlink()
    (root / "leaf.yaml").mkdir()
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(root, Path("leaf.yaml"), "hostile")  # noqa: SLF001
    assert captured.value.code == "UNSAFE_FILE_TYPE"

    (root / "ancestor").write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(root, Path("ancestor/leaf.yaml"), "hostile")  # noqa: SLF001
    assert captured.value.code == "UNSAFE_ANCESTOR"

    root_link = tmp_path / "root-link"
    root_link.symlink_to(root, target_is_directory=True)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator._read(root_link, Path("leaf.yaml"), "hostile")  # noqa: SLF001
    assert captured.value.code == "UNSAFE_ROOT_TYPE"


def test_output_leaf_symlink_and_directory_are_rejected_without_escape(
    tmp_path: Path,
) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged\n")
    output = tmp_path / generator.REFERENCE_PATH
    output.unlink()
    output.symlink_to(outside)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"unchanged\n"

    output.unlink()
    output.mkdir()
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"unchanged\n"


def test_mutating_build_rejects_symlinked_output_leaf_without_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged\n")
    output = tmp_path / generator.REFERENCE_PATH
    output.parent.mkdir(parents=True)
    output.symlink_to(outside)

    def fake_render_outputs(_root: Path = tmp_path) -> dict[Path, bytes]:
        return {generator.REFERENCE_PATH: b"replacement\n"}

    monkeypatch.setattr(generator, "render_outputs", fake_render_outputs)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.build(tmp_path)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"unchanged\n"


def test_check_outputs_rejects_generated_drift(tmp_path: Path) -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in expected.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (tmp_path / generator.DECISION_READ_MODEL_PATH).write_bytes(b"{}\n")
    with pytest.raises(generator.BusinessInputsError) as captured:
        generator.check_outputs(tmp_path, expected)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
