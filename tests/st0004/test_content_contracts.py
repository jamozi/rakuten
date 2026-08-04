"""Independent RAOS-06 content package and TST-020 acceptance tests."""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from scripts import build_st0004_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPOSITORY_ROOT / "changes" / "st-0004"
CONTENT_ROOT = BUNDLE_ROOT / "contracts" / "content"
PREDECESSOR_SCHEMAS = REPOSITORY_ROOT / "changes" / "st-0003" / "contracts" / "schemas"
EXPECTED_VALID = {
    "condition_filtering.json",
    "model_generation_capacity_difference.json",
    "product_comparison.json",
    "selection_guide.json",
    "use_case_recommendation.json",
}
EXPECTED_INVALID_CODES = {
    *(f"INV-{number:03d}" for number in range(1, 11)),
    *(f"INV-{number:03d}" for number in range(101, 106)),
}
FORBIDDEN_FORMULA_INPUTS = {
    "affiliate_rate",
    "commission",
    "contribution_profit",
    "epc",
    "revenue",
    "rpm",
}
FORBIDDEN_AST_PROPERTIES = {
    "affiliate_rate",
    "affiliate_url",
    "commission",
    "raw_html",
    "review_body",
    "review_text",
}
TRACEABILITY_COLUMNS = {
    "requirement_id",
    "design_id",
    "artifact",
    "enforcement",
    "test_area",
    "implementation_slice",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def schema_property_names(value: Any) -> set[str]:
    """Collect every JSON Schema property name without executing archive code."""

    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for child in value.values():
            names.update(schema_property_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(schema_property_names(child))
    return names


def policy_findings(
    article: dict[str, Any], article_types: dict[str, dict[str, Any]]
) -> list[str]:
    """Independent port of the five normative cross-document policy rules."""

    findings: list[str] = []
    blocks = article.get("blocks", [])
    types = [block.get("type") for block in blocks]
    block_ids = [block.get("block_id") for block in blocks]
    if not blocks or types[0] != "disclosure_slot":
        findings.append("POL-CONT-008")
    if "source_summary" not in types:
        findings.append("POL-CONT-001")
    if "methodology" not in types:
        findings.append("POL-CONT-019")
    if len(block_ids) != len(set(block_ids)):
        findings.append("POL-CONT-036")
    definition = article_types.get(article.get("article_type"))
    if definition is None or set(definition.get("required_blocks", [])) - set(types):
        findings.append("POL-CONT-020")
    if {"POL-CONT-001", "POL-CONT-019", "POL-CONT-020", "POL-CONT-036"} & set(findings):
        findings.append("QG-CONT-003")
    return sorted(set(findings))


def test_all_thirty_three_frozen_schemas_and_twenty_four_blocks_are_valid_and_hash_bound() -> None:
    registry = load_yaml(CONTENT_ROOT / "RAOS_06_schema_registry_v0.1.yaml")
    entries = registry["schemas"]
    assert len(entries) == 33
    assert sum(entry["path"].startswith("schemas/blocks/") for entry in entries) == 24
    assert len({entry["schema_id"] for entry in entries}) == 33
    assert len({entry["path"].casefold() for entry in entries}) == 33
    actual = {
        path.relative_to(CONTENT_ROOT).as_posix(): path
        for path in (CONTENT_ROOT / "schemas").rglob("*.json")
    }
    assert {entry["path"] for entry in entries} == set(actual)
    for entry in entries:
        path = actual[entry["path"]]
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        assert schema["$id"] == entry["schema_id"]
        assert sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_five_valid_and_ten_schema_invalid_tst020_fixtures_behave_normatively() -> None:
    validator = Draft202012Validator(load_json(CONTENT_ROOT / "schemas" / "content-ast.schema.json"))
    valid_paths = sorted((CONTENT_ROOT / "fixtures" / "valid").glob("*.json"))
    assert {path.name for path in valid_paths} == EXPECTED_VALID
    for path in valid_paths:
        assert list(validator.iter_errors(load_json(path))) == [], path.name

    expected = load_yaml(CONTENT_ROOT / "fixtures" / "invalid" / "expected_results.yaml")
    schema_cases = [item for item in expected["fixtures"] if item["category"] == "schema"]
    assert len(schema_cases) == 10
    for item in schema_cases:
        errors = list(validator.iter_errors(load_json(CONTENT_ROOT / item["path"])))
        assert errors, f"{item['code']} unexpectedly passed schema validation"
        assert item["expected"] == "FAIL_SCHEMA"


def test_five_policy_invalid_tst020_fixtures_pass_schema_then_fail_expected_policy() -> None:
    validator = Draft202012Validator(load_json(CONTENT_ROOT / "schemas" / "content-ast.schema.json"))
    expected = load_yaml(CONTENT_ROOT / "fixtures" / "invalid" / "expected_results.yaml")
    cases = expected["fixtures"]
    assert len(cases) == 15
    assert {item["code"].split("-", 2)[0] + "-" + item["code"].split("-", 2)[1] for item in cases} == EXPECTED_INVALID_CODES
    article_type_document = load_yaml(CONTENT_ROOT / "RAOS_06_article_type_catalog_v0.1.yaml")
    article_types = {item["code"]: item for item in article_type_document["article_types"]}
    policy_cases = [item for item in cases if item["category"] == "policy"]
    assert len(policy_cases) == 5
    for item in policy_cases:
        article = load_json(CONTENT_ROOT / item["path"])
        assert list(validator.iter_errors(article)) == [], item["code"]
        assert item["expected"] in policy_findings(article, article_types), item["code"]


def test_five_article_templates_match_catalog_and_known_block_contracts() -> None:
    article_types = load_yaml(CONTENT_ROOT / "RAOS_06_article_type_catalog_v0.1.yaml")[
        "article_types"
    ]
    blocks = load_yaml(CONTENT_ROOT / "RAOS_06_content_block_catalog_v0.1.yaml")["blocks"]
    templates = sorted((CONTENT_ROOT / "templates").glob("*.yaml"))
    assert len(article_types) == 5 and len(templates) == 5
    known_blocks = {block["code"] for block in blocks}
    assert len(known_blocks) == 24
    for definition in article_types:
        path = CONTENT_ROOT / definition["template"]
        assert path in templates
        template = load_yaml(path)
        assert template["article_type"] == definition["code"]
        assert set(definition["required_blocks"]) <= known_blocks
        assert set(template["required_sequence"]) - {"disclosure_slot"} == set(
            definition["required_blocks"]
        )


def test_methodology_formula_and_content_ast_exclude_finance_and_renderer_owned_fields() -> None:
    methodology = load_yaml(
        CONTENT_ROOT / "RAOS_06_recommendation_methodology_v0.1.yaml"
    )
    formula = json.dumps(
        methodology["formula"], ensure_ascii=False, sort_keys=True
    ).casefold()
    assert {field for field in FORBIDDEN_FORMULA_INPUTS if field in formula} == set()

    content_ast = load_json(CONTENT_ROOT / "schemas" / "content-ast.schema.json")
    assert schema_property_names(content_ast) & FORBIDDEN_AST_PROPERTIES == set()


def test_traceability_matrix_has_complete_required_rows() -> None:
    path = CONTENT_ROOT / "RAOS_06_traceability_matrix_v0.1.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames is not None
    assert set(reader.fieldnames) == TRACEABILITY_COLUMNS
    assert len(rows) >= 100
    assert all(
        all((row.get(column) or "").strip() for column in TRACEABILITY_COLUMNS)
        for row in rows
    )
    assert len({tuple(row[column] for column in reader.fieldnames) for row in rows}) == len(
        rows
    )


def test_every_adopted_archive_artifact_is_byte_frozen_and_reference_code_is_not_installed() -> None:
    payloads = revision.verify_content_archive()
    manifest = load_yaml(BUNDLE_ROOT / "manifest.yaml")
    frozen = manifest["content_adoption"]["frozen_artifacts"]
    expected_members = {
        relative for relative in payloads if revision.frozen_content_member(relative)
    }
    assert {entry["archive_member"].removeprefix(revision.CONTENT_ROOT) for entry in frozen} == expected_members
    for entry in frozen:
        relative = entry["archive_member"].removeprefix(revision.CONTENT_ROOT)
        output = BUNDLE_ROOT / "contracts" / entry["output_path"]
        assert output.read_bytes() == payloads[relative]
        assert entry["byte_identical"] is True
        assert entry["bytes"] == len(payloads[relative])
        assert entry["sha256"] == sha256(payloads[relative]).hexdigest()
    assert not (CONTENT_ROOT / "reference").exists()
    assert all("reference/validate_content_contracts.py" not in entry["output_path"] for entry in frozen)


def test_raos06_schema_ids_do_not_collide_with_predecessor_and_legacy_ast_is_distinct() -> None:
    content_ids = {
        load_json(path)["$id"] for path in (CONTENT_ROOT / "schemas").rglob("*.json")
    }
    predecessor_ids = {
        load_json(path)["$id"]
        for path in PREDECESSOR_SCHEMAS.rglob("*.json")
        if "$id" in load_json(path)
    }
    assert len(content_ids) == 33 and not (content_ids & predecessor_ids)
    legacy = BUNDLE_ROOT / "contracts" / "schemas" / "common" / "article-ast.schema.json"
    canonical = CONTENT_ROOT / "schemas" / "content-ast.schema.json"
    assert legacy.read_bytes() != canonical.read_bytes()
    with (CONTENT_ROOT / "RAOS_06_content_test_matrix_v0.1.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        matrix = list(csv.DictReader(handle))
    assert len(matrix) >= 1000
    assert len({row["test_id"] for row in matrix}) == len(matrix)
