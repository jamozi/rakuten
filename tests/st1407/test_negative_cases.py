"""Fail-closed and boundary tests for the ST-1407 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1407_external_policy_registry_reference_plan as generator


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("pro_assistance", "status", "CAPTURED"),
        ("pro_assistance", "authority", "UNAPPROVED_PROPOSAL"),
        ("pro_assistance", "proposal_captured", True),
        ("pro_assistance", "content_used", True),
        ("projection_rules", "infer_official_reference_links", True),
        ("projection_rules", "infer_source_snapshot_links", True),
        ("projection_rules", "infer_rule_version_links", True),
        ("projection_rules", "identify_external_snapshot_as_policy_bundle", True),
        ("projection_rules", "interpret_review_frequency_as_deadline", True),
        ("evaluation_defaults", "overdue", True),
        ("evaluation_defaults", "impact_query", "COMPLETE"),
        ("evaluation_defaults", "affected_articles", ["article-1"]),
        ("execution_defaults", "network", "EXECUTED"),
        ("execution_defaults", "database", "EXECUTED"),
        ("execution_defaults", "alert", "EXECUTED"),
        ("execution_defaults", "audit", "EXECUTED"),
        ("execution_defaults", "publication", "EXECUTED"),
        ("verification_defaults", "formal_tst_005", "PASS"),
        ("verification_defaults", "production", "READY"),
    ],
)
def test_forbidden_inference_execution_or_false_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.ExternalPolicyReferenceError):
        generator.validate_contract(contract)


def test_bool_does_not_bypass_exact_integer_counts() -> None:
    contract = deepcopy(generator.load_contract())
    contract["projection_rules"]["exact_external_rule_count"] = True
    with pytest.raises(generator.ExternalPolicyReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("candidate_seam_defaults"),
        lambda value: value.update({"unknown": None}),
        lambda value: value["authority"]["sources"].reverse(),
        lambda value: value["candidate_seam_defaults"]["alert"].update(
            {"unknown": None}
        ),
        lambda value: value["unresolved_gates"].reverse(),
        lambda value: value["evaluation_defaults"].update(
            {"affected_articles_empty_interpretation": "ZERO_AFFECTED"}
        ),
    ],
)
def test_missing_unknown_reordered_and_meaning_drift_are_rejected(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]
    with pytest.raises(generator.ExternalPolicyReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(payload)
    with pytest.raises(
        (generator.ExternalPolicyReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.ExternalPolicyReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_symlink_authority_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    authority = isolated_repository / generator.EXTERNAL_RULE_PATH
    outside_directory = tmp_path / "outside-contracts"
    authority.parent.rename(outside_directory)
    authority.parent.symlink_to(outside_directory, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.EXTERNAL_RULE_PATH,
        generator.OFFICIAL_REFERENCE_PATH,
        generator.EDITORIAL_POLICY_PATH,
        Path("changes/st-0405/README.md"),
        Path("python/raos/domain/editorial/policy_engine.py"),
        generator.HELPER_PATH,
    ],
)
def test_authority_dependency_or_helper_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(
        (generator.ExternalPolicyReferenceError, base.StagingDeploymentContractError)
    ):
        generator.render_outputs(isolated_repository)


def test_external_mapping_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.EXTERNAL_RULE_PATH
    catalog = yaml.safe_load(path.read_bytes())
    catalog["rules"][0]["content_policy_ids"] = ["POL-CONT-040"]
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (
            role,
            source,
            digest
            if source == path.relative_to(isolated_repository).as_posix()
            else expected,
        )
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for source in contract["authority"]["sources"]:
        if source["role"] == "external_rule_snapshot":
            source["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.ExternalPolicyReferenceError):
        generator.render_outputs(isolated_repository)


def test_official_reference_url_drift_is_rejected_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.OFFICIAL_REFERENCE_PATH
    catalog = yaml.safe_load(path.read_bytes())
    catalog["sources"][0]["url"] = "https://example.invalid/not-authority"
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = path.relative_to(isolated_repository).as_posix()
    rebound = tuple(
        (role, source, digest if source == relative else expected)
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for source in contract["authority"]["sources"]:
        if source["role"] == "official_references":
            source["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.ExternalPolicyReferenceError):
        generator.render_outputs(isolated_repository)


def test_raw_content_or_snapshot_instance_selection_is_rejected_and_sanitized() -> None:
    canary = "secret-canary-official-page-body"
    contract = deepcopy(generator.load_contract())
    contract["candidate_seam_defaults"]["source_snapshot"]["content_byte_artifacts"] = [
        canary
    ]
    with pytest.raises(generator.ExternalPolicyReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


def test_builder_has_no_runtime_module_or_unowned_story_files() -> None:
    root = generator.REPO_ROOT
    assert not (root / "python/raos/domain/policy/external_policy_registry.py").exists()
    expected = {
        generator.CONTRACT_PATH,
        generator.REFERENCE_PLAN_PATH,
        generator.MANIFEST_PATH,
        generator.README_PATH,
        generator.GENERATOR_PATH,
        *generator.TEST_PATHS,
    }
    actual = {
        path.relative_to(root)
        for parent in (root / "changes/st-1407", root / "tests/st1407")
        for path in parent.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    actual.add(generator.GENERATOR_PATH)
    assert actual == expected


def test_builder_ast_has_no_network_provider_clock_database_or_action_surface() -> None:
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
            "datetime",
            "httpx",
            "logging",
            "requests",
            "socket",
            "sqlite3",
            "subprocess",
            "urllib",
        }
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
    assert called.isdisjoint({"eval", "exec", "getenv", "open", "Popen", "system"})
    assert attributes.isdisjoint(
        {
            "activate",
            "connect",
            "execute",
            "getenv",
            "now",
            "publish",
            "request",
            "send",
            "notify",
            "urlopen",
        }
    )
