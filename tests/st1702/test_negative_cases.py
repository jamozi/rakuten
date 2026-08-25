"""Hostile closed-boundary tests for the ST-1702 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import os
from pathlib import Path
import shutil
from typing import Any, Callable, cast

import pytest

from scripts import (
    build_st1702_category_fixtures_rules_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "decision", "READY"),
        ("document", "story_acceptance", True),
        ("document", "st1702_ready", True),
        ("document", "production_eligible", True),
        ("document", "approval", "approved"),
        ("document", "canonical_mutation_authority", "WRITE"),
        ("runtime_blockers", "status", "READY"),
        ("runtime_blockers", "canonical_global_unresolved_blocker_count", 0),
        ("runtime_blockers", "canonical_scoped_unresolved_count", 0),
        ("runtime_blockers", "gate_state", "PASS"),
        ("runtime_blockers", "st1701_acceptance", "ACHIEVED"),
        ("runtime_blockers", "st1702_ready", True),
        ("category_candidate", "classification", "CANONICAL_CATEGORY"),
        ("category_candidate", "canonical_resolution", "RESOLVED"),
        ("category_candidate", "runtime_activation", "ACTIVE"),
        ("category_candidate", "category_specific_implementation", "ENABLED"),
        ("category_candidate", "runtime_category_config", "CREATED"),
        ("category_candidate", "golden_products", "CREATED"),
        ("category_candidate", "attribute_schema", "CREATED"),
        ("category_candidate", "category_attributes", ["capacity"]),
        ("category_candidate", "source_observations", ["observation"]),
        ("category_candidate", "provider_evidence", ["evidence"]),
        ("category_candidate", "production_data", "ALLOWED"),
        ("fixture_boundary", "reference_only", False),
        ("fixture_boundary", "runtime_category_config", "CREATED"),
        ("fixture_boundary", "fixture_schema", "schema"),
        ("fixture_boundary", "fixture_records", ["fixture"]),
        ("fixture_boundary", "golden_products", "CREATED"),
        ("fixture_boundary", "golden_product_records", ["product"]),
        ("fixture_boundary", "runtime_loader", "CREATED"),
        ("fixture_boundary", "provider_observations", ["provider"]),
        ("fixture_boundary", "creation_authority", "OWNER"),
        ("identity_boundary", "gold_evidence_status", "SUFFICIENT"),
        ("identity_boundary", "domain_editor_approval", "OBTAINED"),
        ("identity_boundary", "human_review_required", False),
        ("identity_boundary", "automatic_merge_enabled", True),
        ("identity_boundary", "automatic_split_enabled", True),
        ("identity_boundary", "candidate_rule_source_bound_not_applied", False),
        ("identity_boundary", "rule_config", "CREATED"),
        ("identity_boundary", "rules", ["same-model"]),
        ("identity_boundary", "thresholds", [0.9]),
        ("identity_boundary", "scores", [90]),
        ("identity_boundary", "identity_decisions", ["merge"]),
        ("identity_boundary", "merge_records", ["merge"]),
        ("identity_boundary", "split_records", ["split"]),
        ("identity_boundary", "rule_engine", "EXECUTED"),
        ("freshness_boundary", "policy_authority", "CANONICAL_ACTIVE"),
        ("freshness_boundary", "policy_activation", "ACTIVE"),
        ("freshness_boundary", "policy_active", True),
        ("freshness_boundary", "st1701_candidate_sla_bound_not_applied", False),
        ("freshness_boundary", "runtime_freshness_config", "CREATED"),
        ("freshness_boundary", "category_overrides", ["price-72h"]),
        ("freshness_boundary", "provider_overrides", ["provider"]),
        ("freshness_boundary", "category_override_applied", True),
        ("freshness_boundary", "provider_override_applied", True),
        ("freshness_boundary", "stale_never_treated_as_fresh", False),
        ("freshness_boundary", "recommendation_auto_reorder", "ALLOWED"),
        ("freshness_boundary", "scheduler_connection", "EXECUTED"),
        ("freshness_boundary", "persistence", "EXECUTED"),
        ("human_review", "required", False),
        ("human_review", "status", "EXECUTED"),
        ("human_review", "domain_reviewer_approval", "OBTAINED"),
        ("human_review", "routing_status", "CONFIGURED"),
        ("human_review", "queue", "category-review"),
        ("human_review", "reviewer", "reviewer-1"),
        ("human_review", "approval", "approved"),
        ("human_review", "review_records", ["review"]),
        ("execution_boundary", "enabled", True),
        ("execution_boundary", "status", "ENABLED"),
        ("execution_boundary", "runtime_category_config", "CREATED"),
        ("execution_boundary", "golden_products", "CREATED"),
        ("execution_boundary", "category_rule_engine", "EXECUTED"),
        ("execution_boundary", "freshness_scheduler", "EXECUTED"),
        ("execution_boundary", "human_review", "EXECUTED"),
        ("execution_boundary", "repository", "AVAILABLE"),
        ("execution_boundary", "database", "EXECUTED"),
        ("execution_boundary", "job", "EXECUTED"),
        ("execution_boundary", "event", "EXECUTED"),
        ("execution_boundary", "provider", "EXECUTED"),
        ("execution_boundary", "live", "EXECUTED"),
        ("execution_boundary", "publication", "EXECUTED"),
        ("execution_boundary", "production", "READY"),
        ("execution_boundary", "external_authority", "GRANTED"),
        ("verification_boundary", "formal_tst_020", "PASS"),
        ("verification_boundary", "domain_reviewer_approval", "PASS"),
        ("verification_boundary", "runtime", "PASS"),
        ("verification_boundary", "live", "PASS"),
        ("verification_boundary", "production", "READY"),
        ("verification_boundary", "story_acceptance", True),
        ("verification_boundary", "st1702_ready", True),
    ],
)
def test_forbidden_configuration_execution_or_completion_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_bool_float_string_and_nonzero_do_not_bypass_exact_zero_actions(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("decision_index", range(3))
def test_open_decision_cannot_be_unblocked_resolved_or_activated(
    decision_index: int,
) -> None:
    for field, value in (
        ("blocking", False),
        ("resolved", True),
        ("runtime_activation", "ACTIVE"),
        ("candidate_authority", "CANONICAL"),
    ):
        contract = deepcopy(generator.load_contract())
        contract["open_decisions"][decision_index][field] = value
        with pytest.raises(generator.CategoryFixturesRulesReferenceError):
            generator.validate_contract(contract)


def test_dependency_cannot_claim_readiness_connection_or_runtime_completion() -> None:
    mutations = (
        ("canonical_story_status", "IMPLEMENTED"),
        ("canonical_verification_status", "PASS"),
        ("canonical_acceptance", "ACHIEVED"),
        ("st1702_ready", True),
        ("connection_status", "CONNECTED"),
    )
    for index in range(3):
        for field, value in mutations:
            contract = deepcopy(generator.load_contract())
            contract["dependencies"][index][field] = value
            with pytest.raises(generator.CategoryFixturesRulesReferenceError):
                generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("fixture_boundary")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["identity_boundary"]["unknown"] = None


def _reverse_sources(value: dict[str, Any]) -> None:
    value["authority"]["sources"].reverse()


def _reverse_dependencies(value: dict[str, Any]) -> None:
    value["dependencies"].reverse()


def _reverse_blockers(value: dict[str, Any]) -> None:
    value["runtime_blockers"]["required_conditions"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [
        _remove_top,
        _add_top,
        _add_nested,
        _reverse_sources,
        _reverse_dependencies,
        _reverse_blockers,
        _reverse_actions,
    ],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        (
            b"execution_boundary:\n"
            b"  freshness_scheduler: NOT_EXECUTED\n"
            b"  freshness_scheduler: NOT_EXECUTED\n"
        ),
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [generator.CONTRACT_PATH, generator.STORY_PATH],
)
def test_oversized_contract_or_authority_source_fails_before_parse_or_output_write(
    relative: Path,
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        output: (
            (isolated_repository / output).read_bytes(),
            (isolated_repository / output).lstat().st_ino,
            (isolated_repository / output).lstat().st_mode,
            (isolated_repository / output).lstat().st_mtime_ns,
        )
        for output in generator.GENERATED_PATHS
    }
    (isolated_repository / relative).write_bytes(
        b"x" * (generator.MAX_SOURCE_BYTES + 1)
    )

    def parse_must_not_run(_content: bytes, _field: str) -> dict[str, Any]:
        raise AssertionError("parser ran before the descriptor size gate")

    monkeypatch.setattr(generator, "_parse_yaml", parse_must_not_run)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "FILE_SIZE_LIMIT"
    assert {
        output: (
            (isolated_repository / output).read_bytes(),
            (isolated_repository / output).lstat().st_ino,
            (isolated_repository / output).lstat().st_mode,
            (isolated_repository / output).lstat().st_mtime_ns,
        )
        for output in generator.GENERATED_PATHS
    } == before


def test_post_validation_source_symlink_swap_never_returns_outside_bytes(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_repository / generator.CONTRACT_PATH
    parked = target.with_name("contract.parked-for-test")
    outside = tmp_path / "outside-contract.yaml"
    outside_payload = b"outside-synthetic-bytes-must-never-be-returned\n"
    outside.write_bytes(outside_payload)
    swapped = False

    def swap_after_open(_root: Path, relative: Path, _descriptor: int) -> None:
        nonlocal swapped
        if relative == generator.CONTRACT_PATH and not swapped:
            swapped = True
            target.rename(parked)
            target.symlink_to(outside)

    monkeypatch.setattr(generator, "_after_input_open", swap_after_open)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator._read(isolated_repository, generator.CONTRACT_PATH, "contract")
    assert caught.value.code in {"PATH_CHANGED", "UNSAFE_FILE"}
    assert outside.read_bytes() == outside_payload
    assert outside_payload.decode().strip() not in str(caught.value)


def test_source_regular_to_fifo_swap_is_nonblocking_and_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_repository / generator.CONTRACT_PATH
    parked = target.with_name("contract.parked-before-fifo")
    swapped = False

    def swap_leaf(
        _root: Path,
        relative: Path,
        _parent_descriptor: int,
    ) -> None:
        nonlocal swapped
        if relative == generator.CONTRACT_PATH and not swapped:
            swapped = True
            target.rename(parked)
            os.mkfifo(target, mode=0o600)

    monkeypatch.setattr(generator, "_after_input_leaf_stat", swap_leaf)
    try:
        with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
            generator._read(
                isolated_repository,
                generator.CONTRACT_PATH,
                "contract",
            )
        assert caught.value.code in {"PATH_CHANGED", "UNSAFE_FILE"}
    finally:
        if target.exists():
            target.unlink()
        if parked.exists():
            parked.rename(target)


def test_output_regular_to_fifo_swap_is_nonblocking_and_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    parked = target.with_name("reference.parked-before-fifo")
    real_open = os.open
    swapped = False

    def swap_output_leaf(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == target.name and dir_fd is not None and not swapped:
            assert flags & os.O_NONBLOCK
            swapped = True
            target.rename(parked)
            os.mkfifo(target, mode=0o600)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_output_leaf)
    try:
        with pytest.raises(generator.CategoryFixturesRulesReferenceError):
            generator.build(isolated_repository)
    finally:
        if target.exists():
            target.unlink()
        if parked.exists():
            parked.rename(target)


def test_validated_ancestor_swap_before_descriptor_open_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_repository / generator.CONTRACT_PATH
    parent = target.parent
    parked = parent.with_name("contracts.parked-before-open")
    outside_parent = tmp_path / "outside-contracts-before-open"
    outside_parent.mkdir()
    outside_payload = b"outside-before-open-must-never-be-returned\n"
    (outside_parent / target.name).write_bytes(outside_payload)
    swapped = False

    def swap_component(
        _root: Path,
        relative: Path,
        component: str,
        _parent_descriptor: int,
    ) -> None:
        nonlocal swapped
        if (
            relative == generator.CONTRACT_PATH
            and component == generator.CONTRACT_PATH.parent.name
            and not swapped
        ):
            swapped = True
            parent.rename(parked)
            parent.symlink_to(outside_parent, target_is_directory=True)

    monkeypatch.setattr(generator, "_after_input_component_stat", swap_component)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._read(isolated_repository, generator.CONTRACT_PATH, "contract")
    assert (outside_parent / target.name).read_bytes() == outside_payload


def test_open_parent_descriptor_prevents_ancestor_swap_redirection(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_repository / generator.CONTRACT_PATH
    original = target.read_bytes()
    parent = target.parent
    parked = parent.with_name("contracts.parked-for-test")
    outside_parent = tmp_path / "outside-contracts"
    outside_parent.mkdir()
    outside_payload = b"outside-ancestor-bytes-must-never-be-returned\n"
    (outside_parent / target.name).write_bytes(outside_payload)
    swapped = False

    def swap_ancestor_after_open(_root: Path, relative: Path, _descriptor: int) -> None:
        nonlocal swapped
        if relative == generator.CONTRACT_PATH and not swapped:
            swapped = True
            parent.rename(parked)
            parent.symlink_to(outside_parent, target_is_directory=True)

    monkeypatch.setattr(generator, "_after_input_open", swap_ancestor_after_open)
    captured = generator._read(isolated_repository, generator.CONTRACT_PATH, "contract")
    assert captured == original
    assert captured != outside_payload


def test_hash_and_semantic_validation_share_one_capture_per_input(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_read = generator._read
    counts: dict[Path, int] = {}

    def count_read(root: Path, relative: Path, field: str) -> bytes:
        counts[relative] = counts.get(relative, 0) + 1
        return real_read(root, relative, field)

    monkeypatch.setattr(generator, "_read", count_read)
    generator.render_outputs(isolated_repository)
    assert counts == {relative: 1 for relative in generator.INPUT_PATHS}


def test_symlink_contract_and_ancestor_are_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.load_contract(isolated_repository)

    isolated_repository = tmp_path / "second-repository"
    isolated_repository.mkdir()
    source_changes = generator.REPO_ROOT / "changes"
    outside_changes = tmp_path / "outside-changes"
    outside_changes.mkdir()
    target = outside_changes / "st-1702" / "contracts"
    target.mkdir(parents=True)
    (target / generator.CONTRACT_PATH.name).write_bytes(
        (
            source_changes / "st-1702" / "contracts" / generator.CONTRACT_PATH.name
        ).read_bytes()
    )
    (isolated_repository / "changes").symlink_to(
        outside_changes, target_is_directory=True
    )
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.load_contract(isolated_repository)


def test_static_symlink_in_physical_repository_root_is_rejected_for_input_and_output(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    anchor = tmp_path / "physical-root-anchor"
    anchor.mkdir()
    physical_repository = anchor / "repository"
    isolated_repository.rename(physical_repository)
    alias = tmp_path / "physical-root-alias"
    alias.symlink_to(anchor, target_is_directory=True)
    aliased_repository = alias / "repository"

    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as input_error:
        generator._read(
            aliased_repository,
            generator.CONTRACT_PATH,
            "contract",
        )
    assert input_error.value.code == "UNSAFE_ROOT"
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as output_error:
        generator.build(aliased_repository)
    assert output_error.value.code == "UNSAFE_ROOT"


def test_physical_repository_root_swap_never_redirects_input_capture(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = tmp_path / "root-race-anchor"
    anchor.mkdir()
    physical_repository = anchor / "repository"
    isolated_repository.rename(physical_repository)
    parked = tmp_path / "root-race-anchor-parked"
    outside_anchor = tmp_path / "root-race-outside"
    outside_repository = outside_anchor / "repository"
    outside_contract = outside_repository / generator.CONTRACT_PATH
    outside_contract.parent.mkdir(parents=True)
    canary = b"outside-root-swap-canary\n"
    outside_contract.write_bytes(canary)
    swapped = False

    def swap_root_component(
        _absolute: Path,
        component: str,
        _parent_descriptor: int,
    ) -> None:
        nonlocal swapped
        if component == anchor.name and not swapped:
            swapped = True
            anchor.rename(parked)
            anchor.symlink_to(outside_anchor, target_is_directory=True)

    monkeypatch.setattr(
        generator,
        "_before_repository_root_component_open",
        swap_root_component,
    )
    try:
        with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
            generator._read(
                physical_repository,
                generator.CONTRACT_PATH,
                "contract",
            )
        assert caught.value.code == "UNSAFE_ROOT"
        assert outside_contract.read_bytes() == canary
    finally:
        if anchor.is_symlink():
            anchor.unlink()
        if parked.exists():
            parked.rename(anchor)


def test_physical_repository_root_swap_never_redirects_output_publication(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    anchor = tmp_path / "output-root-race-anchor"
    anchor.mkdir()
    physical_repository = anchor / "repository"
    isolated_repository.rename(physical_repository)
    outside_anchor = tmp_path / "output-root-race-outside"
    outside_repository = outside_anchor / "repository"
    shutil.copytree(physical_repository, outside_repository)
    outside_reference = outside_repository / generator.REFERENCE_PLAN_PATH
    outside_reference.write_bytes(b"outside-output-root-swap-canary\n")
    outside_before = outside_reference.read_bytes()
    parked = tmp_path / "output-root-race-anchor-parked"
    swapped = False

    def swap_root_component(
        _absolute: Path,
        component: str,
        _parent_descriptor: int,
    ) -> None:
        nonlocal swapped
        if component == anchor.name and not swapped:
            swapped = True
            anchor.rename(parked)
            anchor.symlink_to(outside_anchor, target_is_directory=True)

    monkeypatch.setattr(
        generator,
        "_before_repository_root_component_open",
        swap_root_component,
    )
    try:
        with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
            generator.build(physical_repository)
        assert caught.value.code == "UNSAFE_ROOT"
        assert outside_reference.read_bytes() == outside_before
    finally:
        if anchor.is_symlink():
            anchor.unlink()
        if parked.exists():
            parked.rename(anchor)


def test_output_symlink_target_and_ancestor_are_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"

    target.unlink()
    target.parent.rmdir()
    outside_directory = tmp_path / "outside-generated"
    outside_directory.mkdir()
    target.parent.symlink_to(outside_directory, target_is_directory=True)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.build(isolated_repository)
    assert not tuple(outside_directory.iterdir())


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        *(path for _role, path, _digest in generator.EXPECTED_SOURCES),
        *generator.DEPENDENCY_PATHS,
    ],
)
def test_authority_or_dependency_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.render_outputs(isolated_repository)


def test_st1701_semantic_promotion_is_rejected_independently_of_hash(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.ST1701_ARTIFACTS[1][0]
    text = path.read_text(encoding="utf-8").replace(
        "    st1702_ready: false", "    st1702_ready: true", 1
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._validate_st1701_semantics(
            generator._capture_inputs(isolated_repository)
        )


def test_st0504_semantic_merge_activation_is_rejected_independently_of_hash(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.ST0504_ARTIFACTS[0][0]
    text = path.read_text(encoding="utf-8").replace(
        "  automatic_merge_enabled: false",
        "  automatic_merge_enabled: true",
        1,
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._validate_st0504_semantics(
            generator._capture_inputs(isolated_repository)
        )


def test_st1401_semantic_override_activation_is_rejected_independently_of_hash(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.ST1401_ARTIFACTS[2][0]
    text = path.read_text(encoding="utf-8").replace(
        "category_override_applied=False",
        "category_override_applied=True",
        1,
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._validate_st1401_semantics(
            generator._capture_inputs(isolated_repository)
        )


def test_canonical_story_promotion_is_rejected_independently_of_hash(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    text = path.read_text(encoding="utf-8")
    story_start = text.index("- id: ST-1702\n")
    story_end = text.index("\n- id:", story_start)
    story = text[story_start:story_end]
    assert story.count("  implementation_status: NOT_STARTED\n") == 1
    story = story.replace(
        "  implementation_status: NOT_STARTED\n",
        "  implementation_status: IMPLEMENTED\n",
        1,
    )
    text = text[:story_start] + story + text[story_end:]
    path.write_text(text, encoding="utf-8")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._validate_authority_semantics(
            generator._capture_inputs(isolated_repository)
        )


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-category-provider-value"
    contract = deepcopy(generator.load_contract())
    contract["category_candidate"]["display_name_ja"] = canary
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


def test_builder_ast_has_no_external_runtime_or_action_surface() -> None:
    source = (generator.REPO_ROOT / generator.GENERATOR_PATH).read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "boto3",
            "httpx",
            "requests",
            "socket",
            "subprocess",
            "urllib",
            "sqlalchemy",
            "psycopg",
            "random",
            "time",
            "uuid",
        }
    )
    assert not any(
        module == "scripts" or module.startswith("scripts.") for module in imported
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called.isdisjoint(
        {"eval", "exec", "getenv", "Popen", "system", "sleep", "urlopen"}
    )
    assert attributes.isdisjoint(
        {
            "connect",
            "execute",
            "publish",
            "send",
            "request",
            "enqueue",
            "approve",
            "merge",
            "split",
            "getenv",
        }
    )
