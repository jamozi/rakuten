"""Critical fail-closed tests for the ST-1703 low-cost pilot."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1703_low_cost_publication_pilot as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _reject(document: dict[str, Any]) -> None:
    with pytest.raises(generator.PilotContractError):
        generator.validate_contract(document)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("spend_boundary", "exact_incremental_external_spend_cap"), 2001),
        (("spend_boundary", "purchase_authority"), "AUTHORIZED"),
        (("spend_boundary", "purchase_status"), "EXECUTED"),
        (("spend_boundary", "canonical_od_009", "status"), "RESOLVED"),
        (("pilot", "public_platforms", "candidate_count"), 2),
        (("pilot", "public_platforms", "dual_run"), "ENABLED"),
        (("pilot", "public_platforms", "cutover"), "AUTHORIZED"),
        (("pilot", "drafting_and_quality", "mode"), "UNATTENDED"),
        (
            ("pilot", "public_platforms", "candidates", 0, "subscription_status"),
            "EXECUTED",
        ),
        (
            ("pilot", "public_platforms", "candidates", 0, "custom_domain_authority"),
            "AUTHORIZED",
        ),
        (
            ("pilot", "public_platforms", "candidates", 0, "draft_authority"),
            "AUTHORIZED",
        ),
        (
            ("pilot", "public_platforms", "candidates", 0, "publication_authority"),
            "AUTHORIZED",
        ),
        (("inherited_blockers", "dependencies_promoted"), True),
        (("inherited_blockers", "story_acceptance_achieved"), True),
        (("evidence_boundary", "formal_suites", "TST-021"), "PASS"),
        (("evidence_boundary", "live_browser_provider"), "PASS"),
        (("evidence_boundary", "staging"), "PASS"),
        (("evidence_boundary", "release"), "PASS"),
        (("evidence_boundary", "publication"), "PASS"),
        (("evidence_boundary", "production"), "PASS"),
        (("quality_and_ux_requirements", "execution_status"), "EXECUTED"),
        (("quality_and_ux_requirements", "verification_status"), "VERIFIED"),
    ),
)
def test_semantic_and_status_inflation_is_rejected(
    contract_document: dict[str, Any], path: tuple[str | int, ...], value: object
) -> None:
    document = copy.deepcopy(contract_document)
    target: Any = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    _reject(document)


@pytest.mark.parametrize(
    ("path", "mutation"),
    (
        (("pilot", "deferred_disabled_components"), "remove"),
        (("pilot", "deferred_disabled_components"), "reorder"),
        (("pilot", "deferred_disabled_components"), "enable"),
        (("pilot", "public_platforms", "candidates"), "duplicate"),
        (("pilot", "drafting_and_quality", "forbidden_codex_roles"), "remove"),
        (("inherited_blockers", "open_decisions"), "remove"),
        (("inherited_blockers", "st_1703_dependencies"), "remove"),
    ),
)
def test_closed_inventories_reject_removal_reorder_enable_and_duplicate(
    contract_document: dict[str, Any],
    path: tuple[str, ...],
    mutation: str,
) -> None:
    document = copy.deepcopy(contract_document)
    target: Any = document
    for part in path:
        target = target[part]
    if mutation == "remove":
        target.pop()
    elif mutation == "reorder":
        target[0], target[1] = target[1], target[0]
    elif mutation == "enable":
        target[0] = "OPENAI_API_ENABLED"
    else:
        target.append(copy.deepcopy(target[0]))
    _reject(document)


@pytest.mark.parametrize(
    "field",
    tuple(
        ["external_actions", "provider_calls", "purchases", "credential_operations"]
        + ["domain_operations", "draft_operations", "publication_operations"]
        + ["staging_operations", "release_operations", "production_operations"]
    ),
)
def test_nonempty_actions_are_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["action_boundary"][field] = ["FORBIDDEN"]
    _reject(document)


def test_unknown_fields_are_rejected(contract_document: dict[str, Any]) -> None:
    document = copy.deepcopy(contract_document)
    document["unknown"] = "forbidden"
    _reject(document)


def test_nonempty_effect_or_evidence_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    for section, field in (
        ("effect_boundary", "external_effects"),
        ("effect_boundary", "financial_effects"),
        ("effect_boundary", "publication_effects"),
    ):
        document = copy.deepcopy(contract_document)
        document[section][field] = ["FORBIDDEN"]
        _reject(document)
    document = copy.deepcopy(contract_document)
    document["evidence_records"] = [{"status": "PASS"}]
    _reject(document)


def test_contract_key_order_is_part_of_the_closed_semantics(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    pilot = document.pop("pilot")
    document["pilot"] = pilot
    _reject(document)


def test_strict_yaml_rejects_duplicates_aliases_and_tags(tmp_path: Path) -> None:
    for index, content in enumerate(
        (
            b"document: safe\ndocument: drift\n",
            b"value: &anchor safe\ncopy: *anchor\n",
            b"base: &base {state: safe}\nvalue: {<<: *base}\n",
            b"value: !!python/object/apply:os.system ['blocked']\n",
        )
    ):
        path = tmp_path / f"unsafe-{index}.yaml"
        path.write_bytes(content)
        with pytest.raises(generator.PilotContractError):
            generator.load_yaml(tmp_path, Path(path.name))


def test_v2_approval_drift_and_authority_inflation_are_rejected() -> None:
    original = generator.load_yaml(REPOSITORY_ROOT, generator.V2_APPROVAL_PATH)
    mutations = (
        ("handoff_sha256", generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256),
        ("semantic_delta_from_approved_v1", "CHANGED"),
        ("open_decisions", ["INFERRED"]),
    )
    for field, value in mutations:
        document = copy.deepcopy(original)
        document["DESIGN_HANDOFF_APPROVAL_V1"][field] = value
        with pytest.raises(generator.PilotContractError) as captured:
            generator._validate_v2_approval(document)  # noqa: SLF001
        assert captured.value.code == "V2_APPROVAL_INVALID"

    document = copy.deepcopy(original)
    document["DESIGN_HANDOFF_APPROVAL_V1"]["boundaries"]["publication"] = "AUTHORIZED"
    with pytest.raises(generator.PilotContractError) as captured:
        generator._validate_v2_approval(document)  # noqa: SLF001
    assert captured.value.code == "V2_APPROVAL_INVALID"


def test_v2_handoff_rejects_historical_current_substitution() -> None:
    document = generator.load_yaml(REPOSITORY_ROOT, generator.V2_HANDOFF_PATH)
    rule = document["design_handoff"]["decision"][
        "historical_and_current_manifest_rule"
    ]
    rule["current_target_sha256"] = generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256
    rule["current_target_bytes"] = generator.HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES
    with pytest.raises(generator.PilotContractError) as captured:
        generator._validate_v2_handoff(document)  # noqa: SLF001
    assert captured.value.code == "V2_HANDOFF_INVALID"


def test_v3_approval_drift_and_authority_inflation_are_rejected() -> None:
    original = generator.load_yaml(REPOSITORY_ROOT, generator.V3_APPROVAL_PATH)
    mutations = (
        ("handoff_sha256", generator.V2_HANDOFF_SHA256),
        ("implementation_authority", "PUBLICATION_AUTHORIZED"),
        ("open_decisions", ["INFERRED"]),
    )
    for field, value in mutations:
        document = copy.deepcopy(original)
        document["DESIGN_HANDOFF_APPROVAL_V1"][field] = value
        with pytest.raises(generator.PilotContractError) as captured:
            generator._validate_v3_approval(document)  # noqa: SLF001
        assert captured.value.code == "V3_APPROVAL_INVALID"

    for field in ("local_commit", "push", "pull_request", "publication"):
        document = copy.deepcopy(original)
        document["DESIGN_HANDOFF_APPROVAL_V1"]["boundaries"][field] = "AUTHORIZED"
        with pytest.raises(generator.PilotContractError) as captured:
            generator._validate_v3_approval(document)  # noqa: SLF001
        assert captured.value.code == "V3_APPROVAL_INVALID"


def test_v3_handoff_rejects_target_runtime_substitution_and_scope_inflation() -> None:
    original = generator.load_yaml(REPOSITORY_ROOT, generator.V3_HANDOFF_PATH)

    document = copy.deepcopy(original)
    document["design_handoff"]["decision"]["exact_target"]["commit"] = (
        generator.CURRENT_TARGET_COMMIT
    )
    with pytest.raises(generator.PilotContractError) as captured:
        generator._validate_v3_handoff(document)  # noqa: SLF001
    assert captured.value.code == "V3_HANDOFF_INVALID"

    document = copy.deepcopy(original)
    reconciliation = document["design_handoff"]["decision"][
        "low_cost_v3_reconciliation"
    ]
    reconciliation["future_current_runtime_manifest_bytes"] = (
        generator.CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES
    )
    reconciliation["future_current_runtime_manifest_sha256"] = (
        generator.CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256
    )
    with pytest.raises(generator.PilotContractError) as captured:
        generator._validate_v3_handoff(document)  # noqa: SLF001
    assert captured.value.code == "V3_HANDOFF_INVALID"

    document = copy.deepcopy(original)
    document["design_handoff"]["decision"]["implementation_authority"] = (
        "PUBLICATION_AUTHORIZED"
    )
    with pytest.raises(generator.PilotContractError) as captured:
        generator._validate_v3_handoff(document)  # noqa: SLF001
    assert captured.value.code == "V3_HANDOFF_INVALID"
