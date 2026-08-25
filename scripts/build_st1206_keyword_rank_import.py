#!/usr/bin/env python3
"""Build deterministic owner evidence for the disabled ST-1206 local seam."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import importlib
import json
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast
from uuid import UUID

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raos.adapters.recorded_keyword_rank import (  # noqa: E402
    RecordedKeywordRankCsvSource,
)
from raos.application.analytics.keyword_rank_import import (  # noqa: E402
    KeywordRankEvaluationService,
)
from raos.domain.analytics.keyword_rank import (  # noqa: E402
    KEYWORD_RANK_CONTRACT_VERSION,
    KEYWORD_RANK_PARSER_VERSION,
    KeywordRankEvaluationCommand,
    KeywordRankMetricType,
    KeywordRankPeriod,
    KeywordRankScope,
    Sha256Digest,
)

base: Any = importlib.import_module("scripts.build_st1505_staging_deployment")


CONTRACT_PATH: Final = Path("changes/st-1206/contracts/keyword-rank-import.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1206/fixtures/recorded/keyword-rank-synthetic.v1.csv"
)
README_PATH: Final = Path("changes/st-1206/README.md")
COMPLETION_PATH: Final = Path("changes/st-1206/completion/completion.v1.yaml")
DOMAIN_PATH: Final = Path("python/raos/domain/analytics/keyword_rank.py")
PORT_PATH: Final = Path("python/raos/ports/keyword_rank.py")
APPLICATION_PATH: Final = Path(
    "python/raos/application/analytics/keyword_rank_import.py"
)
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_keyword_rank.py")
GENERATOR_PATH: Final = Path("scripts/build_st1206_keyword_rank_import.py")
TEST_PATHS: Final = (
    Path("tests/st1206/conftest.py"),
    Path("tests/st1206/test_evaluation.py"),
    Path("tests/st1206/test_negative_cases.py"),
    Path("tests/st1206/test_contract.py"),
    Path("tests/st1206/test_generation.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    README_PATH,
    COMPLETION_PATH,
    DOMAIN_PATH,
    PORT_PATH,
    APPLICATION_PATH,
    ADAPTER_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
EVIDENCE_PATH: Final = Path("changes/st-1206/generated/keyword-rank-evaluation.v1.json")
MANIFEST_PATH: Final = Path("changes/st-1206/manifest.yaml")
GENERATED_PATHS: Final = (EVIDENCE_PATH, MANIFEST_PATH)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
ANALYTICS_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md"
)
SECURITY_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"
)
CONTROLS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
THREATS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)

KEYWORD_ROW_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/imports/keyword-rank-row.schema.json"
)
CSV_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-keyword-rank-csv-v1.schema.json"
)
DISPATCH_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/analytics-import-provider-data-v1.schema.json"
)

EXPECTED_CONTRACT_SHA256: Final = (
    "b02328d88ba7b9b4481e81e15eb58c413204fa412a14587fda5770a8e34ca723"
)
EXPECTED_FIXTURE_SHA256: Final = (
    "e06d21cf450a75250e096d3528ac45839fa3fb7d08d9988a58d0e0b9ecd59611"
)
EXPECTED_FIXTURE_BYTES: Final = 874
EXPECTED_NORMALIZED_SHA256: Final = (
    "b2767fb7b6d59537d918ba95e3082c1b3380c9b51fb1eeabfa65fb85d96d6c64"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SITE_ID: Final = UUID("018f3e90-7b00-7000-8000-000000001200")
GENERATION_COMMAND: Final = "python scripts/build_st1206_keyword_rank_import.py"

AUTHORITY_HASHES: Final = {
    STORY_PATH: "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    INTEGRATION_PATH: "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    DECISIONS_PATH: "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ANALYTICS_PATH: "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    SECURITY_PATH: "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    CONTROLS_PATH: "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    THREATS_PATH: "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    TEST_CATALOG_PATH: "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
}
PREDECESSOR_HASHES: Final = {
    Path(
        "changes/st-1205/contracts/kpi-read-model.v2.yaml"
    ): "8f7e0664c844615a291c926520fff14af399daa5fd21bac8d002bfc7857218ed",
    Path(
        "changes/st-1205/manifest.yaml"
    ): "9b25af0167a195de99d57e7d4e2eb54c4832a9051ec2b42de666bf6e32eb7548",
    Path(
        "python/raos/domain/analytics/kpi_read_model.py"
    ): "7cc8ad6e10c61add95f3543605e1b1305762c20a691b4a05f9c070143f3101ac",
    Path(
        "python/raos/application/analytics/kpi_read_model.py"
    ): "7485112a452eec41c93578863030893f5758c310430f7db5e899f6ec53c8adbf",
}
CANONICAL_CONTRACT_HASHES: Final = {
    KEYWORD_ROW_SCHEMA_PATH: "d1c311cf0afabf6c83c5acb0154ca8f89d023165683a08adff28f09e607bec4c",
    CSV_JOB_SCHEMA_PATH: "1b4328b6eba2bb1a3e9e34e91049f0cec2bc4080310690f50971656df2bb5cc1",
    DISPATCH_JOB_SCHEMA_PATH: "7610a9b4927ffddd191409b597497eac39f49712c34115a3f27fb254694c16ab",
}


class KeywordRankBuildError(RuntimeError):
    """Stable, sanitized owner-generator failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise KeywordRankBuildError(f"ST-1206 build failed: {code} field={field}")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    candidate = cast(dict[object, object], value)
    if not all(type(key) is str for key in candidate):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], candidate)


def _list(value: object, field: str) -> list[object]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[object], value)


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if type(content) is not bytes or len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_INVALID", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _find_row(
    rows: object, *, identity: str, expected_id: str, field: str
) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for candidate in _list(rows, field):
        if type(candidate) is not dict:
            continue
        row = _mapping(cast(object, candidate), field)
        if row.get(identity) == expected_id:
            matches.append(row)
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, CONTRACT_PATH, "contract")) != EXPECTED_CONTRACT_SHA256:
        _fail("SOURCE_HASH_DRIFT", "contract")
    fixture = _read(root, FIXTURE_PATH, "recorded_fixture")
    if (
        len(fixture) != EXPECTED_FIXTURE_BYTES
        or _sha256(fixture) != EXPECTED_FIXTURE_SHA256
    ):
        _fail("SOURCE_HASH_DRIFT", "recorded_fixture")
    for relative, digest in (
        *AUTHORITY_HASHES.items(),
        *PREDECESSOR_HASHES.items(),
        *CANONICAL_CONTRACT_HASHES.items(),
    ):
        if _sha256(_read(root, relative, "bound_source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "bound_source")


def _validate_story(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    story = _find_row(
        stories.get("stories"),
        identity="id",
        expected_id="ST-1206",
        field="authority.story",
    )
    expected = {
        "id": "ST-1206",
        "epic_id": "EPIC-12",
        "title": "Rank/keyword import extension",
        "objective": "承認ProviderまたはCSVを追加",
        "depends_on": ["ST-1205"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["optional adapter"],
        "acceptance_criteria": ["no SERP scrape"],
        "test_suites": ["TST-030"],
        "priority": "P2",
        "mvp": False,
        "size": "M",
        "open_decisions": ["OD-004"],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "DEFERRED_POST_MVP",
        "verification_status": "NOT_EXECUTED",
    }
    if story != expected or tuple(story) != tuple(expected):
        _fail("CANONICAL_SEMANTIC_DRIFT", "authority.story")


def _validate_decision(root: Path) -> None:
    decisions = _load_yaml(root, DECISIONS_PATH, "authority.od004")
    decision = _find_row(
        decisions.get("items"),
        identity="id",
        expected_id="OD-004",
        field="authority.od004",
    )
    expected = {
        "id": "OD-004",
        "topic": "keyword_and_rank_provider",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "GATE-2 automation",
        "owner": "Product Owner",
        "decision_needed": "規約適合した順位/Keyword Providerまたは手動Importを選定",
        "default_behavior": "Search Consoleと手動CSVのみ",
        "blocking": False,
    }
    if decision != expected or tuple(decision) != tuple(expected):
        _fail("CANONICAL_SEMANTIC_DRIFT", "authority.od004")


def _validate_canonical_contracts(root: Path) -> None:
    row = _load_json(root, KEYWORD_ROW_SCHEMA_PATH, "canonical.keyword_row")
    properties = _mapping(row.get("properties"), "canonical.keyword_row.properties")
    metric = _mapping(properties.get("metric_type"), "canonical.keyword_row.metric")
    if (
        row.get("additionalProperties") is not False
        or "query" in properties
        or "keyword_text" in properties
        or metric.get("enum") != ["POSITION", "SEARCH_VOLUME", "DIFFICULTY"]
    ):
        _fail("CANONICAL_SEMANTIC_DRIFT", "canonical.keyword_row")
    csv_job = _load_json(root, CSV_JOB_SCHEMA_PATH, "canonical.csv_job")
    dispatch = _load_json(root, DISPATCH_JOB_SCHEMA_PATH, "canonical.dispatch_job")
    if (
        csv_job.get("title") != "analytics.import_keyword_rank_csv.v1"
        or dispatch.get("title") != "analytics.import_provider_data.v1"
    ):
        _fail("CANONICAL_SEMANTIC_DRIFT", "canonical.jobs")


def _validate_contract(contract: Mapping[str, Any], root: Path) -> None:
    expected_keys = (
        "document",
        "authority",
        "predecessor",
        "canonical_contracts",
        "feature_scope",
        "port_contract",
        "recorded_fixture_contract",
        "csv_security_contract",
        "evaluation_contract",
        "execution_boundary",
        "debt",
    )
    if tuple(contract) != expected_keys:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    document = _mapping(contract["document"], "document")
    scope = _mapping(contract["feature_scope"], "feature_scope")
    port = _mapping(contract["port_contract"], "port_contract")
    recorded = _mapping(
        contract["recorded_fixture_contract"], "recorded_fixture_contract"
    )
    csv_security = _mapping(contract["csv_security_contract"], "csv_security_contract")
    evaluation = _mapping(contract["evaluation_contract"], "evaluation_contract")
    execution = _mapping(contract["execution_boundary"], "execution_boundary")
    if (
        document
        != {
            "schema_version": "1.0.0",
            "story_id": "ST-1206",
            "classification": "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_KEYWORD_RANK_EVALUATION_V1",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "mvp": False,
            "canonical_implementation_status": "DEFERRED_POST_MVP",
            "canonical_status_changed": False,
            "formal_validation": "NOT_EXECUTED",
            "production_eligible": False,
            "approval": None,
        }
        or scope.get("default") != "DISABLED"
        or scope.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_EVALUATION_ONLY"]
        or scope.get("live_enabled_state_exists") is not False
        or scope.get("activation_interface_exists") is not False
        or scope.get("disabled_fails_before_port_call") is not True
        or scope.get("evaluation_imports_rows") is not False
        or port.get("provider_sdk_types") is not False
        or port.get("url_field") is not False
        or port.get("credential_field") is not False
        or port.get("raw_query_field") is not False
        or recorded.get("sha256") != EXPECTED_FIXTURE_SHA256
        or recorded.get("bytes") != EXPECTED_FIXTURE_BYTES
        or recorded.get("normalized_sha256") != EXPECTED_NORMALIZED_SHA256
        or recorded.get("raw_keyword_text_present") is not False
        or csv_security.get("formula_prefixes_rejected") != ["=", "+", "-", "@"]
        or csv_security.get("partial_result_on_failure") is not False
        or csv_security.get("raw_rows_in_result_or_error") is not False
        or evaluation.get("observation_rows_returned") is not False
        or evaluation.get("raw_keyword_text_returned") is not False
        or evaluation.get("recommendation_order_modified") is not False
        or execution.get("runtime_feature_default") != "DISABLED"
        or execution.get("provider_selection") != "UNRESOLVED_OD-004"
        or execution.get("provider") != "NOT_EXECUTED"
        or execution.get("network") != "NOT_EXECUTED"
        or execution.get("serp_scrape") != "FORBIDDEN"
        or execution.get("tracking_activation") != "DISABLED"
        or execution.get("recommendation_input") != "DISABLED"
        or execution.get("production") != "NOT_EXECUTED"
        or execution.get("formal_TST-030") != "NOT_EXECUTED"
        or execution.get("story_acceptance") is not False
    ):
        _fail("CONTRACT_SEMANTIC_DRIFT", "safety_boundary")
    _validate_hashes(root)
    _validate_story(root)
    _validate_decision(root)
    _validate_canonical_contracts(root)


def _validate_completion(root: Path) -> None:
    completion = _load_yaml(root, COMPLETION_PATH, "completion")
    implementation = _mapping(
        completion.get("implementation"), "completion.implementation"
    )
    authority = _mapping(completion.get("authority"), "completion.authority")
    verification = _mapping(completion.get("verification"), "completion.verification")
    debt = _mapping(completion.get("debt"), "completion.debt")
    if (
        completion.get("schema_version") != 1
        or completion.get("story_id") != "ST-1206"
        or completion.get("base_commit") != "681318fe3a625819459aea89519731776d744b08"
        or completion.get("local_status") != "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED"
        or completion.get("canonical_status_transition") != "NONE"
        or completion.get("canonical_implementation_status") != "DEFERRED_POST_MVP"
        or implementation.get("runtime_feature_default") != "DISABLED"
        or implementation.get("live_enabled_state_exists") is not False
        or implementation.get("import_or_persistence") != "NOT_EXECUTED"
        or implementation.get("serp_scrape") != "FORBIDDEN"
        or any(value is not False for value in authority.values())
        or verification.get("formal_TST-030") != "NOT_EXECUTED"
        or verification.get("live_provider") != "NOT_EXECUTED"
        or verification.get("production") != "NOT_EXECUTED"
        or completion.get("story_acceptance") is not False
        or debt.get("introduced") != []
    ):
        _fail("COMPLETION_SEMANTIC_DRIFT", "completion")


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    _validate_contract(contract, root)
    _validate_completion(root)
    return contract


def _recorded_evaluation(root: Path) -> dict[str, object]:
    fixture = _read(root, FIXTURE_PATH, "recorded_fixture")
    command = KeywordRankEvaluationCommand(
        recording_id="complete",
        site_id=SITE_ID,
        source_sha256=Sha256Digest(EXPECTED_FIXTURE_SHA256),
        source_bytes=EXPECTED_FIXTURE_BYTES,
        period=KeywordRankPeriod(date(2026, 8, 1), date(2026, 8, 2)),
        scope=KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
    )
    snapshot = KeywordRankEvaluationService(
        source=RecordedKeywordRankCsvSource(fixture)
    ).evaluate(command)
    metric_counts = {row.metric_type.value: row.count for row in snapshot.metric_counts}
    if (
        snapshot.row_count != 6
        or snapshot.unique_keyword_count != 2
        or metric_counts != {metric.value: 2 for metric in KeywordRankMetricType}
        or snapshot.normalized_sha256.value != EXPECTED_NORMALIZED_SHA256
    ):
        _fail("FIXTURE_REPRODUCTION_FAILED", "recorded_fixture")
    return {
        "recording_id": snapshot.recording_id,
        "contract_version": KEYWORD_RANK_CONTRACT_VERSION,
        "parser_version": KEYWORD_RANK_PARSER_VERSION,
        "command_sha256": snapshot.command_sha256.value,
        "source_sha256": snapshot.source_sha256.value,
        "normalized_sha256": snapshot.normalized_sha256.value,
        "source_kind": snapshot.source_kind.value,
        "row_count": snapshot.row_count,
        "unique_keyword_count": snapshot.unique_keyword_count,
        "metric_counts": metric_counts,
        "observation_from": snapshot.observation_from.isoformat(),
        "observation_to": snapshot.observation_to.isoformat(),
        "scope": snapshot.scope.value,
        "default_scope": snapshot.default_scope.value,
        "import_state": snapshot.import_state.value,
        "persistence": snapshot.persistence.value,
        "provider": snapshot.provider.value,
        "network": snapshot.network.value,
        "credentials": snapshot.credentials.value,
        "serp_scrape": snapshot.serp_scrape.value,
        "tracking_activation": snapshot.tracking_activation.value,
        "kpi_read_model_write": snapshot.kpi_read_model_write.value,
        "recommendation_input": snapshot.recommendation_input.value,
        "formal_TST-030": snapshot.formal_tst_030.value,
        "canonical_status": snapshot.canonical_status.value,
    }


def evidence_document(root: Path = REPO_ROOT) -> dict[str, object]:
    contract = load_contract(root)
    return {
        "document": contract["document"],
        "authority": contract["authority"],
        "predecessor": contract["predecessor"],
        "canonical_contracts": contract["canonical_contracts"],
        "feature_scope": contract["feature_scope"],
        "port_contract": contract["port_contract"],
        "recorded_evaluation": _recorded_evaluation(root),
        "csv_security_contract": contract["csv_security_contract"],
        "evaluation_contract": contract["evaluation_contract"],
        "execution_boundary": contract["execution_boundary"],
        "debt": contract["debt"],
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "source_artifact")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, evidence_bytes: bytes) -> bytes:
    contract = load_contract(root)
    manifest: dict[str, object] = {
        "document": {
            "id": "RAOS-ST1206-KEYWORD-RANK-LOCAL-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1206",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "authority": contract["authority"],
            "predecessor": contract["predecessor"],
            "canonical_contracts": contract["canonical_contracts"],
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{EVIDENCE_PATH.as_posix()}",
                "bytes": len(evidence_bytes),
                "sha256": _sha256(evidence_bytes),
            }
        ],
        "local_completion": {
            "local_code_status": "LOCAL_CODE_COMPLETE",
            "implementation_boundary": "MAXIMUM_SAFE_DISABLED",
            "recorded_fixture_rows": 6,
            "deterministic_evaluation": "PASS",
            "default_feature_scope": "DISABLED",
            "serp_scrape": "FORBIDDEN",
            "introduced_debt": [],
            "OD-004": "HUMAN_DECISION_REQUIRED",
            "formal_TST-030": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "DEFERRED_POST_MVP",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    evidence_bytes = _json_bytes(evidence_document(root))
    return {
        EVIDENCE_PATH: evidence_bytes,
        MANIFEST_PATH: _manifest_bytes(root, evidence_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")
        if mode != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative in GENERATED_PATHS:
        base._atomic_write(root, relative, outputs[relative])  # noqa: SLF001


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except (KeywordRankBuildError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("ST-1206 build failed: UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    print(
        "ST-1206 keyword-rank evidence checked"
        if args.check
        else "ST-1206 keyword-rank evidence generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
