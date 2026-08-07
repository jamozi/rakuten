"""Canonical and installed-contract binding for ST-0801."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts import build_st0801_content_ast as generator


def _record(document: dict[str, Any], collection: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[collection] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def test_contract_is_bound_to_approved_story_and_safe_slice() -> None:
    contract = generator.load_and_validate_contract()

    assert contract["document"] == {
        "id": "RAOS-CONTENT-AST-LOADER-001",
        "version": "1.0.0",
        "story_id": "ST-0801",
        "implementation_slice": "CONT-SLICE-002",
        "status": "LOCAL_AND_CI_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert contract["story"]["dependencies"] == ["ST-0004", "ST-0105"]
    assert contract["story"]["open_decisions"] == []
    assert contract["authority"]["open_decisions"]["story_items"] == []
    assert contract["boundary"]["effective_canonical_status"] == "UNCHANGED"


def test_canonical_story_and_tst020_remain_unpromoted() -> None:
    backlog = yaml.safe_load(
        (
            generator.REPO_ROOT
            / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_text(encoding="utf-8")
    )
    catalog = yaml.safe_load(
        (
            generator.REPO_ROOT
            / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
        ).read_text(encoding="utf-8")
    )

    story = _record(backlog, "stories", "ST-0801")
    suite = _record(catalog, "suites", "TST-020")
    assert story == generator.EXPECTED_STORY
    assert suite == generator.EXPECTED_TST020
    assert story["implementation_status"] == "NOT_STARTED"
    assert suite["execution_status"] == "NOT_EXECUTED"


def test_contract_pins_exact_content_and_generated_inventories() -> None:
    contract = generator.load_and_validate_contract()

    assert contract["content_contracts"]["block_catalog"]["codes"] == list(
        generator.BLOCK_CODES
    )
    assert contract["content_contracts"]["article_type_catalog"]["codes"] == list(
        generator.ARTICLE_TYPE_CODES
    )
    assert contract["schema_inventory"]["count"] == len(generator.SCHEMA_RELATIVE_PATHS)
    assert contract["fixture_inventory"]["valid_count"] == 5
    assert contract["fixture_inventory"]["invalid_count"] == 15
    assert "package" not in contract["generated_bindings"]["typescript"]
    assert contract["binding_support"] == {
        "typescript_package": {
            "uri": "repo://packages/web-contracts/package.json",
            "sha256": (
                "d2251bc89081cef93bfa495b351f7a5b44b1216441dfb6c3c6b1a08be0f8fef3"
            ),
        }
    }
    controls = contract["security"]["controls"]
    assert [item["id"] for item in controls] == ["SEC-APP-001", "SEC-APP-004"]


def test_loader_contract_keeps_later_policy_and_renderer_out_of_scope() -> None:
    contract = generator.load_and_validate_contract()

    integrity = contract["loader"]["generated_code_integrity"]
    assert integrity == {
        "selected_file_disk_parity": (
            "AFTER_PYTHON_MODULE_IMPORT_ON_EACH_LOAD_AND_DUMP"
        ),
        "pre_execution_integrity": (
            "ST0105_DEPLOYMENT_AND_CODEGEN_GATE_RESPONSIBILITY"
        ),
        "bundle_generator_check": "ALL_ST0105_DECLARED_OUTPUT_BYTES_AND_SHA256",
    }
    assert contract["security"]["script_like_text"] == (
        "PRESERVED_FOR_LATER_RENDERER_ESCAPING"
    )
    assert contract["fixture_execution"]["deferred_to_cont_slice_003"] == [
        "INV-101-disclosure-not-first",
        "INV-102-missing-source-summary",
        "INV-103-missing-methodology-block",
        "INV-105-missing-required-article-block",
    ]
    for boundary in (
        "renderer",
        "article_template_semantics",
        "claim_evidence_semantics",
        "recommendation_semantics",
        "review_semantics",
        "publication",
    ):
        assert contract["boundary"][boundary] == "NOT_IMPLEMENTED"


def test_yaml_authorities_are_parsed_from_digest_verified_bytes(
    monkeypatch,
) -> None:
    contract = generator._load_contract_only()

    def forbidden_reopen(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("digest-verified YAML must not be reopened")

    monkeypatch.setattr(generator.shared, "load_yaml", forbidden_reopen)
    monkeypatch.setattr(Path, "read_bytes", forbidden_reopen)
    monkeypatch.setattr(Path, "read_text", forbidden_reopen)

    generator._validate_authority(contract, generator.REPO_ROOT)
