"""Hostile and authority-escalation tests for the ST-1903 candidate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1903_autonomous_publication_policy as generator


Mutation = tuple[tuple[str, ...], object]


def _set_path(document: dict[str, Any], path: tuple[str, ...], value: object) -> None:
    current: Any = document
    for key in path[:-1]:
        if type(current) is not dict:
            raise AssertionError("test mutation path is not a mapping")
        current = current[key]
    if type(current) is not dict:
        raise AssertionError("test mutation target is not a mapping")
    current[path[-1]] = value


MUTATIONS: tuple[Mutation, ...] = (
    (("candidate_status",), "APPROVED"),
    (("activation",), "ENABLED"),
    (("canonical_reconciliation",), "EXECUTED"),
    (("approval_binding", "approval_record"), "generated-approval.yaml"),
    (("prerequisites", "st_1805", "current_status"), "MET"),
    (("prerequisites", "tst_032", "current_status"), "PASS"),
    (("publication_policy", "rate_limit", "maximum_new_articles_per_calendar_day"), 2),
    (("publication_policy", "rate_limit", "catch_up"), "ALLOWED"),
    (("publication_policy", "risk_gate", "denied_categories"), []),
    (("publication_policy", "risk_gate", "unknown_or_ambiguous_result"), "PUBLISH"),
    (
        ("publication_policy", "commercial_component", "maximum_weight_basis_points"),
        1001,
    ),
    (("publication_policy", "commercial_component", "activation"), "ENABLED"),
    (("publication_policy", "pro_review", "outage_result"), "BYPASS"),
    (("publication_policy", "affiliate", "hand_built_url"), "ALLOWED"),
    (("publication_policy", "affiliate", "raos_redirect"), "ALLOWED"),
    (
        ("publication_policy", "wordpress", "blind_retry_after_ambiguous_result"),
        "ALLOWED",
    ),
    (("code_change_policy", "current_auto_merge_authority"), "CODEX"),
    (("analytics_privacy_policy", "fingerprinting"), "ALLOWED"),
    (("editorial_style_policy", "fabricated_first_person_experience"), "ALLOWED"),
    (("editorial_style_policy", "detector_evasion"), "REQUIRED"),
    (("optimizer_containment", "may_publish_or_unpublish"), True),
    (("projection_boundary", "may_call_provider_or_write_external_state"), True),
    (("actions",), [{"kind": "PUBLISH"}]),
)


@pytest.mark.parametrize(("path", "replacement"), MUTATIONS)
def test_policy_mutation_is_rejected(
    contract: dict[str, Any], path: tuple[str, ...], replacement: object
) -> None:
    """Any authority, safety, privacy, or optimizer drift fails closed."""

    mutated = deepcopy(contract)
    _set_path(mutated, path, replacement)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_contract(mutated)
    assert captured.value.code == "CONTRACT_SEMANTICS_INVALID"


def test_extra_contract_key_is_rejected(contract: dict[str, Any]) -> None:
    """Unreviewed extension fields cannot enter the generated policy."""

    mutated = deepcopy(contract)
    mutated["runtime"] = {"enabled": True}
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_contract(mutated)
    assert captured.value.code == "CONTRACT_SHAPE_INVALID"


@pytest.mark.parametrize(
    "payload",
    (
        "schema: one\nschema: two\n",
        "base: &shared\n  value: one\ncopy: *shared\n",
        "value: !!python/object:builtins.str {}\n",
        "base: &base\n  value: one\nmerged:\n  <<: *base\n",
        "merged:\n  <<: {value: one}\n",
    ),
)
def test_hostile_yaml_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    """Duplicate keys, aliases, anchors, tags, and merges never deserialize."""

    path = tmp_path / "hostile.yaml"
    path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._load_yaml(Path("hostile.yaml"), "HOSTILE_YAML")
    assert captured.value.code == "HOSTILE_YAML"


def test_symlink_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation never follows a source symlink."""

    target = tmp_path / "target.yaml"
    link = tmp_path / "link.yaml"
    target.write_text("value: safe\n", encoding="utf-8")
    link.symlink_to(target)
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._read_regular(Path("link.yaml"))
    assert captured.value.code == "SOURCE_NOT_REGULAR"


def test_symlink_source_ancestor_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation never traverses a symlinked repository ancestor."""

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.yaml").write_text("value: safe\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._read_regular(Path("linked/source.yaml"))
    assert captured.value.code == "PATH_ANCESTOR_INVALID"


def test_path_traversal_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source path cannot escape the physical repository binding."""

    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._read_regular(Path("../outside.yaml"))
    assert captured.value.code == "PATH_INVALID"


def test_handoff_bytes_are_immutable(handoff: dict[str, Any]) -> None:
    """A semantic edit requires a new owner-visible SHA-256 target."""

    mutated = deepcopy(handoff)
    mutated["activation_status"] = "ENABLED"
    raw = (generator.REPO_ROOT / generator.HANDOFF_PATH).read_bytes()
    contract, contract_raw = generator._load_yaml(
        generator.CONTRACT_PATH, "CONTRACT_YAML_INVALID"
    )
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_handoff(mutated, raw + b"\n", contract, contract_raw)
    assert captured.value.code == "HANDOFF_BYTES_INVALID"


def test_contract_revision_requires_a_new_root_handoff_sha(
    handoff: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-digested contract cannot reuse an old root-policy approval target."""

    handoff_raw = (generator.REPO_ROOT / generator.HANDOFF_PATH).read_bytes()
    contract_raw = (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    mutated_raw = contract_raw.replace(
        b"scheduler: LOCAL_SCHEDULED_CODEX", b"scheduler: OTHER_SCHEDULER"
    )
    assert mutated_raw != contract_raw
    mutated = yaml.safe_load(mutated_raw)
    semantic_digest = generator._sha256(generator._canonical_json(mutated))
    monkeypatch.setattr(generator, "EXPECTED_CONTRACT_SEMANTIC_SHA256", semantic_digest)
    generator._validate_contract(mutated)
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_handoff(handoff, handoff_raw, mutated, mutated_raw)
    assert captured.value.code == "HANDOFF_CONTRACT_BINDING_INVALID"


def test_parallel_lineage_is_not_candidate_ancestor() -> None:
    """The separately edited Wave3 lineage remains reference-only."""

    _contract, handoff = generator.load_inputs()
    binding = handoff["repository_bindings"]["parallel_lineage"]
    assert binding["relationship"] == "REFERENCE_ONLY_PARALLEL_LINEAGE_NOT_MERGED"
    assert binding["merged_into_candidate"] is False
    assert binding["source_files_copied"] is False
    current_head = generator._git("rev-parse", "HEAD", code="CURRENT_HEAD_INVALID")
    assert generator._git_is_ancestor(
        generator.EXPECTED_BASE_COMMIT, current_head, "BASE_GIT_BINDING_INVALID"
    )
    assert not generator._git_is_ancestor(
        generator.EXPECTED_PARALLEL_COMMIT,
        current_head,
        "PARALLEL_GIT_BINDING_INVALID",
    )
