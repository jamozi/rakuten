"""Canonical, contract, privacy, and no-scrape assertions for ST-1206."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml

from conftest import REPOSITORY_ROOT
from raos.domain.analytics.keyword_rank import (
    DEFAULT_KEYWORD_RANK_SCOPE,
    KeywordRankScope,
)


CONTRACT_PATH = Path("changes/st-1206/contracts/keyword-rank-import.v1.yaml")
BOUND_HASHES = {
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    "contracts/raos-v0.4/contracts/schemas/imports/keyword-rank-row.schema.json": "d1c311cf0afabf6c83c5acb0154ca8f89d023165683a08adff28f09e607bec4c",
    "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-keyword-rank-csv-v1.schema.json": "1b4328b6eba2bb1a3e9e34e91049f0cec2bc4080310690f50971656df2bb5cc1",
    "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-provider-data-v1.schema.json": "7610a9b4927ffddd191409b597497eac39f49712c34115a3f27fb254694c16ab",
    "changes/st-1205/contracts/kpi-read-model.v2.yaml": "8f7e0664c844615a291c926520fff14af399daa5fd21bac8d002bfc7857218ed",
    "changes/st-1205/manifest.yaml": "9b25af0167a195de99d57e7d4e2eb54c4832a9051ec2b42de666bf6e32eb7548",
}


def _yaml(path: str | Path) -> object:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_exact_canonical_contract_and_predecessor_bytes_are_bound() -> None:
    observed = {
        path: hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
        for path in BOUND_HASHES
    }
    assert observed == BOUND_HASHES


def test_story_remains_post_mvp_deferred_and_requires_no_serp_scrape() -> None:
    document = _yaml("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
    assert isinstance(document, dict)
    story = next(row for row in document["stories"] if row["id"] == "ST-1206")
    assert story["depends_on"] == ["ST-1205"]
    assert story["deliverables"] == ["optional adapter"]
    assert story["acceptance_criteria"] == ["no SERP scrape"]
    assert story["test_suites"] == ["TST-030"]
    assert story["mvp"] is False
    assert story["open_decisions"] == ["OD-004"]
    assert story["implementation_status"] == "DEFERRED_POST_MVP"
    assert story["verification_status"] == "NOT_EXECUTED"


def test_od004_remains_unresolved_with_manual_csv_safe_default() -> None:
    document = _yaml("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml")
    assert isinstance(document, dict)
    decision = next(row for row in document["items"] if row["id"] == "OD-004")
    assert decision == {
        "id": "OD-004",
        "topic": "keyword_and_rank_provider",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "GATE-2 automation",
        "owner": "Product Owner",
        "decision_needed": "規約適合した順位/Keyword Providerまたは手動Importを選定",
        "default_behavior": "Search Consoleと手動CSVのみ",
        "blocking": False,
    }


def test_canonical_row_and_jobs_are_projected_without_extension() -> None:
    row = json.loads(
        (
            REPOSITORY_ROOT
            / "contracts/raos-v0.4/contracts/schemas/imports/keyword-rank-row.schema.json"
        ).read_text()
    )
    csv_job = json.loads(
        (
            REPOSITORY_ROOT
            / "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-keyword-rank-csv-v1.schema.json"
        ).read_text()
    )
    dispatch = json.loads(
        (
            REPOSITORY_ROOT
            / "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-provider-data-v1.schema.json"
        ).read_text()
    )
    assert row["additionalProperties"] is False
    assert "query" not in row["properties"]
    assert "keyword_text" not in row["properties"]
    assert row["properties"]["metric_type"]["enum"] == [
        "POSITION",
        "SEARCH_VOLUME",
        "DIFFICULTY",
    ]
    assert csv_job["title"] == "analytics.import_keyword_rank_csv.v1"
    source_enum = dispatch["allOf"][1]["properties"]["payload"]["properties"][
        "source_type"
    ]["enum"]
    assert source_enum == ["SEARCH_CONSOLE", "GA4", "KEYWORD_RANK_CSV"]


def test_local_contract_has_no_live_state_or_authority_escalation() -> None:
    contract = _yaml(CONTRACT_PATH)
    assert isinstance(contract, dict)
    scope = contract["feature_scope"]
    execution = contract["execution_boundary"]
    assert DEFAULT_KEYWORD_RANK_SCOPE is KeywordRankScope.DISABLED
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_EVALUATION_ONLY",
    ]
    assert scope["live_enabled_state_exists"] is False
    assert scope["activation_interface_exists"] is False
    assert execution["serp_scrape"] == "FORBIDDEN"
    assert execution["provider"] == "NOT_EXECUTED"
    assert execution["network"] == "NOT_EXECUTED"
    assert execution["tracking_activation"] == "DISABLED"
    assert execution["recommendation_input"] == "DISABLED"
    assert execution["formal_TST-030"] == "NOT_EXECUTED"
    assert execution["story_acceptance"] is False


def test_runtime_modules_have_no_network_filesystem_environment_or_provider_sdk() -> (
    None
):
    paths = [
        "python/raos/domain/analytics/keyword_rank.py",
        "python/raos/ports/keyword_rank.py",
        "python/raos/application/analytics/keyword_rank_import.py",
        "python/raos/adapters/recorded_keyword_rank.py",
    ]
    forbidden_roots = {
        "boto3",
        "google",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {"open", "getenv", "urlopen"}
    for path in paths:
        tree = ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
        imported: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        assert imported.isdisjoint(forbidden_roots), path
        assert calls.isdisjoint(forbidden_calls), path
