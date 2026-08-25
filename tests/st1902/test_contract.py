"""Canonical, dependency, and local boundary assertions for ST-1902."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from raos.adapters.recorded_champion_challenger import (
    TRUSTED_ROUTE_CATALOG_SHA256,
    TRUSTED_ST0708_REPORT_SHA256,
)

from .support import FIXTURE_PATH, REPOSITORY_ROOT


CONTRACT_PATH = Path("changes/st-1902/contracts/champion-challenger-shadow.v1.yaml")
ST0708_BINDINGS = {
    "changes/st-0708/contracts/recorded-live-evaluation-runtime.v2.yaml": (
        "02f1592d11086f09b51a11b0f9fce92cff1467d64c4ad7bb05b7ee17bcc370d3"
    ),
    "changes/st-0708/generated/recorded-live-evaluation-request.v2.json": (
        "15f816b1a98d36ffd1d31c826db0bf7cbac30b901df01a7c49c44ae3420eabe0"
    ),
    "changes/st-0708/generated/recorded-live-evaluation-report.v2.json": (
        "65ca1c03208c2be6ab34caa449d5f7bc5f28c760c60d20b3af0f066f338c6635"
    ),
    "changes/st-0708/runtime-manifest.v2.json": (
        "0506e8f618b01d26bff9cbf51b8ad88c34f55586d4ea647a8172d9e64ee57b42"
    ),
    "python/raos/domain/ai/live_evaluation.py": (
        "e574167f1ce9028c773f9a295cae06bb5bf71480115248e217b812921a0e6976"
    ),
    "python/raos/application/ai/live_evaluation.py": (
        "9fe29acc16ff0e5a6f540c45d0f9db2930ccdfb9e563fea8307dc55f9359e88a"
    ),
    "python/raos/ports/live_evaluation.py": (
        "4fb29af21dd1efb9f46867041f5772dacf9d57a5f3ab5e75de2f4e7eec0a64d6"
    ),
    "python/raos/adapters/recorded_live_evaluation.py": (
        "48778329088e43da5a6b22dba41c397ebc82bf2fdf3cfd19800abf934509f89d"
    ),
}


def _sha(relative: str | Path) -> str:
    return hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()


def _contract() -> dict[str, object]:
    loaded = yaml.safe_load((REPOSITORY_ROOT / CONTRACT_PATH).read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def test_canonical_story_remains_deferred_post_mvp() -> None:
    contract = _contract()
    document = contract["document"]
    assert isinstance(document, dict)
    assert document == {
        "schema_version": "1.0.0",
        "story_id": "ST-1902",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_CHAMPION_CHALLENGER_SHADOW_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }
    assert contract["debt"] == {
        "introduced": [],
        "external_or_formal_remaining": [
            "separate external release decision",
            "formal TST-032 gate acceptance",
            "licensed locked holdout and human labels",
            "live provider/account/credential validation",
            "staging canary, monitoring, rollback, and manual re-enable drill",
        ],
    }


def test_exact_dependency_and_authority_hashes_match_base_bytes() -> None:
    contract = _contract()
    predecessor = contract["predecessor"]
    assert isinstance(predecessor, dict)
    assert predecessor["base_commit"] == ("975ff87fd4297927be1c66da789ee7bb7b748ae4")
    assert predecessor["artifacts"] == ST0708_BINDINGS
    for relative, digest in ST0708_BINDINGS.items():
        assert _sha(relative) == digest

    authority = contract["authority"]
    assert isinstance(authority, dict)
    for item in authority.values():
        if isinstance(item, dict) and "path" in item and "sha256" in item:
            assert _sha(str(item["path"])) == item["sha256"]


def test_route_and_fixture_bindings_are_exact() -> None:
    contract = _contract()
    route = contract["route_binding"]
    fixture = contract["recorded_fixture"]
    assert isinstance(route, dict)
    assert isinstance(fixture, dict)
    catalog = route["catalog"]
    assert isinstance(catalog, dict)
    assert _sha(str(catalog["path"])) == TRUSTED_ROUTE_CATALOG_SHA256
    assert fixture["path"] == FIXTURE_PATH.as_posix()
    assert fixture["sha256"] == _sha(FIXTURE_PATH)
    assert fixture["bytes"] == (REPOSITORY_ROOT / FIXTURE_PATH).stat().st_size
    assert predecessor_report_hash(contract) == TRUSTED_ST0708_REPORT_SHA256


def predecessor_report_hash(contract: dict[str, object]) -> str:
    predecessor = contract["predecessor"]
    assert isinstance(predecessor, dict)
    artifacts = predecessor["artifacts"]
    assert isinstance(artifacts, dict)
    value = artifacts[
        "changes/st-0708/generated/recorded-live-evaluation-report.v2.json"
    ]
    assert isinstance(value, str)
    return value


def test_contract_has_no_activation_or_live_authority() -> None:
    contract = _contract()
    scope = contract["feature_scope"]
    mutation = contract["mutation_boundary"]
    execution = contract["execution_boundary"]
    assert isinstance(scope, dict)
    assert isinstance(mutation, dict)
    assert isinstance(execution, dict)
    assert scope["default"] == "DISABLED"
    assert scope["live_enabled_state_exists"] is False
    assert scope["canary_state_exists"] is False
    assert scope["activation_interface_exists"] is False
    assert mutation["authority"] == "NONE"
    for key in (
        "route_mutation",
        "editorial_selection",
        "recommendation_order",
        "cta_mutation",
        "article_mutation",
        "publication_snapshot_mutation",
        "publication",
    ):
        assert mutation[key] == "FORBIDDEN"
    assert execution["network"] == "FORBIDDEN"
    assert execution["credentials"] == "NOT_USED"
    assert execution["provider"] == "NOT_EXECUTED"
    assert execution["canary"] == "RELEASE_DECISION_REQUIRED"
    assert execution["story_acceptance"] is False
