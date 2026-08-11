#!/usr/bin/env python3
"""Build the non-executable, non-attesting ST-1205 KPI reference plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1205/contracts/kpi-read-model-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1205/generated/kpi-read-model-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1205/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1205_kpi_read_model_reference_plan.py")
README_PATH: Final = Path("changes/st-1205/README.md")
TEST_PATHS: Final = (
    Path("tests/st1205/conftest.py"),
    Path("tests/st1205/test_contract.py"),
    Path("tests/st1205/test_generation.py"),
    Path("tests/st1205/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1205_kpi_read_model_reference_plan.py"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "30541e0f5c78147220068856b0de72deab39f7353b1b39fe130b8d6e91fa6c35"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
KPI_CATALOG_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml"
)
KPI_CATALOG_SHA256: Final = (
    "f1cad721ade082f588461ff58c415fa21786e30b85c8281e651476514e2560a2"
)
INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
INTEGRATION_SHA256: Final = (
    "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
)

ST1201_COMMIT: Final = "db19e538ed5a8c7e208ded7c3319a15c5e809492"
ST1203_COMMIT: Final = "bdb97355eb27100d92787b6bbd3b5608b729250e"
ST1204_COMMIT: Final = "73b7782502f249f91eafd3d0bc9d229fb770d7c6"

ST1201_ARTIFACTS: Final = (
    (
        Path("changes/st-1201/README.md"),
        "f7264bda2e0e6c4fcfbd6d7050552170974f85ae014106d10ad36e03b94b2e09",
    ),
    (
        Path("python/raos/domain/analytics/event_collector.py"),
        "e7350bac934fc3d190d9c041915a7ea708092519e4ddccb2c70e0c850bde50ff",
    ),
    (
        Path("python/raos/ports/event_collector.py"),
        "ab3f5b8df9dd7c324006c948ec0322c0c583dffe1b2facf7900d000cb632298c",
    ),
    (
        Path("python/raos/application/analytics/event_collector.py"),
        "8d35153ee3bc801e9653d4773358b31746fce195fd651b9caeaddfa8b1ebea85",
    ),
    (
        Path("python/raos/adapters/recorded_event_store.py"),
        "1e80a17f648138c7cff885e06eae452c8c89f93e441c4efedbd3f65a9c6d6c30",
    ),
    (
        Path("tests/st1201/conftest.py"),
        "4ae5cb8ca3cc747a269fd9d552d639cb8846935101ff3e208004b269246c555e",
    ),
    (
        Path("tests/st1201/test_collector.py"),
        "e009577784a5450b66dbd421fdfdf1e6c5beb0b8ab3fb1593735363b402bd183",
    ),
    (
        Path("tests/st1201/test_failure_isolation.py"),
        "3acb571f2d5bc5323bd4246d71977342dad7d269196c2897b0c57000b7ea697e",
    ),
    (
        Path("tests/st1201/test_boundaries.py"),
        "411947c165fc0b8ae02f5286eba79efe0905ad2ac2a552366083311336c485e9",
    ),
)
ST1203_ARTIFACTS: Final = (
    (
        Path("changes/st-1203/README.md"),
        "c333b3400b8f0f13ce18be7e04d43345caa812b4d818dae8222cb8b498099c3e",
    ),
    (
        Path("python/raos/domain/analytics/search_console.py"),
        "e49396e6dfac336b05488ae4ba80100c106fc4bf64c2ed476d16f459c16759ce",
    ),
    (
        Path("python/raos/ports/search_console.py"),
        "569ee34c9202bf673338c0b87039a3ad461cf56d964537750427512288ac1bf5",
    ),
    (
        Path("python/raos/application/analytics/search_console_import.py"),
        "9a74033080728fa1b65bec071ec5e97ccf74cd0151153455e022029320ffa40e",
    ),
    (
        Path("python/raos/adapters/recorded_search_console.py"),
        "410e04383731edac7228a522d0275e8ea6f43a1bdb981075740c426655577e49",
    ),
    (
        Path("tests/st1203/test_search_console_domain.py"),
        "6ee3a1857d49d11447413955d0a65408c3a4f51e47f7d5c1eba95fd6783bea3c",
    ),
    (
        Path("tests/st1203/test_search_console_application.py"),
        "bc83080860f3217730876b48c1f6bd0f1b5c071d676984608da2eb4d99f30f98",
    ),
    (
        Path("tests/st1203/test_recorded_search_console.py"),
        "03f07ce52f9863a22ea83732d11a4d1a501ef356c8f85b930a2c111bf2ae571b",
    ),
    (
        Path("tests/st1203/test_runtime_boundaries.py"),
        "19ee7216c40948c888739a21c087f137019187a7e85abc88c8b6f768f4a8ce3d",
    ),
)
ST1204_ARTIFACTS: Final = (
    (
        Path("changes/st-1204/RUNTIME-SLICE-v1.md"),
        "e5ca8b2e38e0b46c9a40232af26bd5b4ebbbf20099c6a7856a7ab007443ca17e",
    ),
    (
        Path("python/raos/domain/analytics/ga4.py"),
        "785dd16788fffabd5ab6c05c6f43f535bc6521630a246c93a54d23d257de124f",
    ),
    (
        Path("python/raos/ports/ga4.py"),
        "16edfe96aad71f44d454a5474fc99fcf0528d9a85f88fc2047680f8b0a3d9a80",
    ),
    (
        Path("python/raos/application/analytics/ga4_import.py"),
        "663b057a4ce091d601ed0ea5b35a17632aaee0f53cb41d2c13eba69b27e28dc2",
    ),
    (
        Path("python/raos/adapters/recorded_ga4.py"),
        "9d07350b94109da403db764930be46fcfa666864350f1c6f6893f5daa759b840",
    ),
    (
        Path("tests/st1204/test_ga4_domain.py"),
        "d1afeb6e7537aa7be6e0e41bc51c02bbcec31d88af8cca493f083be665368a59",
    ),
    (
        Path("tests/st1204/test_ga4_application.py"),
        "8e8aae09e0749a31957c91a1de8f76abbc61f2e57a3bfecb7382f137196caf52",
    ),
    (
        Path("tests/st1204/test_recorded_ga4.py"),
        "e8c427264d11fd9e88bfa92a663a8704fbccd70c443bd055e658062c48a95677",
    ),
    (
        Path("tests/st1204/test_runtime_boundaries.py"),
        "b47d3981eb6d36b8c0aed93fddb9fd939e663e3261f6a444ebe8069f551c20a9",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessors",
    "catalog_projection",
    "calculation_boundary",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "catalog_projection",
    "calculation_boundary",
    "execution_boundary",
    "verification_boundary",
)
KPI_FIELDS: Final = (
    "id",
    "name",
    "formula",
    "domain",
    "interpretation",
    "cadence",
    "design_status",
    "implementation_status",
    "runtime_verification",
)
KPI_IDS: Final = tuple(f"KPI-{number:03d}" for number in range(1, 31))
KPI_ROW_HASHES: Final = (
    "028dab6ec388e2988bf76a69e285b44fba5d46fadeb5ac2ada17c5aab0087215",
    "b5d4908e5bd6092b1221c001aac8cb91cc333b1710d2b32c3d6c2c7b2debde68",
    "943740d37670096944d4a4089d68d7276211e8e26fd6ad0cfe7f8ce9a65fd7d0",
    "5ad2441fc6c89297c654eaddf47b5089a62234cbb5faec0d25eb339a01f0a8b9",
    "34f44730ae3a1700ced50b133e247611b28e6736efa906ad2fbfe8af376599e2",
    "fc5f59a0d91cab7bfbad21b87594a3eeef3dd433e5b75e187fcc5cada32559c2",
    "95a014fbc4da4d54113df7081ffd300225d25b0d1406dea7dc40fe54d2d2f408",
    "e809452d031ce2e6c2618c828cddae82fab85d4077591714aaf2664465c90501",
    "b31abd0e84c1310fffca538b9c6ec7f3a8a9bb235296e25ff4848cb666f57cb2",
    "4b8a684804834b4f48e7a2923487a24f7b0c3e5c84ceaf3c200c7af10e247262",
    "b5d0ad5bef152b01fb5aaaf5dc671d1ee2709a1b61c14f89243dc7a9282e88fc",
    "4f0abb4a606d9a7974e272b904abaa4bd27d1a7091d8887020439e0eea844754",
    "dfff640b8c6ae52663e4b5e457cc32d9b2b073c61dc452ec5fe936f5c8363000",
    "0f153c06d34e5fc990bd893a9dfa960cd754a57dfa0ebb5525d2f75c0968c20c",
    "41d5b66d264885f854fc039070d8cffb767aac432f69ab4bc543025748a1187d",
    "8d74d8f01dc022c84a2803f19b84cf5961702b6af6fd21dc7bace25963064d9f",
    "510f0741b933f4474f0d70ee11051686b140734ee1835340f0a90d959cd98b1e",
    "df6593cd5a0f66081f122c778963a2db6c84d72c4e7d10d97a86100899d6ba33",
    "54a465fd3d2a09b9dd6bbf42e3ff2f796ccbff5f7b78e733fb8ae3d2228d688b",
    "659124bd2358a797adfdfa39269f30f51df1cc84a2257ef4dbac2714ec6efbb9",
    "1277c6bbf9b82c2bff4573e53e618e46f9611d57028feda87fa83202a56f14f9",
    "2c2d98702fb413c1fa55e0e0ced593f60ee9883ffd84ed86b4ffb298ed1d6270",
    "3934e46df15c07e52f56c13d5d4fc999e893fe5d8266deb175bda532fb2f90e3",
    "c8492f31cfeb1b63e00354714e7c5a944258e1217baf73667170ec9d995a34fb",
    "2df16cbb4b569cacd40bc74c59cebe579df674634e4b8edd1eb63a3b2f2d3245",
    "7531d02a964f78319d7e463d13496c56f190fba14bd49f3f4e55ad300e4d3a9b",
    "55383ea4403a708defb1b3a39d83363d03d91f7562391436cbad3893ebb71c44",
    "ae1db042b5eea712209269e238da01788d430af4782031c2659ac8704a6f2924",
    "1dba9376666c9e4aafa8dfa2182a9370bc823395c7c78aba37893569ae7511fc",
    "1b31bc997745df0626eed399d44618aef6b0d73676683eb1456eb3273fe52009",
)
DOMAIN_DISTRIBUTION: Final = {
    "finance": 9,
    "finance+analytics": 2,
    "analytics": 3,
    "search": 6,
    "quality": 2,
    "freshness": 2,
    "ai+finance": 1,
    "ai/editorial": 1,
    "operations": 2,
    "ux": 1,
    "governance": 1,
}
ACTION_COUNT_KEYS: Final = (
    "calculate",
    "verify",
    "map",
    "read",
    "write",
    "execute_sql",
    "create_table",
    "enqueue_job",
    "database",
    "repository",
    "activate_tracking",
    "public_projection",
    "recommendation_input",
    "provider",
    "network",
    "external",
)

EXPECTED_STORY: Final = {
    "id": "ST-1205",
    "epic_id": "EPIC-12",
    "title": "KPI read models",
    "objective": "30 KPIを定義Version付きで計算",
    "depends_on": ["ST-1201", "ST-1203", "ST-1204"],
    "requirement_ids": ["FR-013", "FR-015"],
    "design_refs": [],
    "deliverables": ["SQL/jobs/read models"],
    "acceptance_criteria": ["fixture formulas reproduce"],
    "test_suites": ["TST-030"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_DOCUMENT: Final = {
    "schema_version": "1.0.0",
    "story_id": "ST-1205",
    "classification": (
        "SOURCE_DERIVED_NON_EXECUTABLE_NON_ATTESTING_KPI_READ_MODEL_REFERENCE_PLAN"
    ),
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "non_attesting": True,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "canonical_status": "UNCHANGED",
}
EXPECTED_AUTHORITY: Final = {
    "canonical_story": {
        "path": STORY_PATH.as_posix(),
        "sha256": STORY_SHA256,
        "story_id": "ST-1205",
    },
    "kpi_catalog": {
        "path": KPI_CATALOG_PATH.as_posix(),
        "sha256": KPI_CATALOG_SHA256,
    },
    "integration_precedence": {
        "path": INTEGRATION_PATH.as_posix(),
        "sha256": INTEGRATION_SHA256,
    },
    "authority_kind": "SOURCE_DERIVED_REFERENCE_ONLY",
    "changes_canonical_status": False,
}


def _artifact_rows(artifacts: Sequence[tuple[Path, str]]) -> dict[str, str]:
    return {path.as_posix(): digest for path, digest in artifacts}


def _artifact_uri_rows(
    artifacts: Sequence[tuple[Path, str]],
) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in artifacts
    ]


EXPECTED_PREDECESSORS: Final = {
    "st1201": {
        "story_id": "ST-1201",
        "feature_commit": ST1201_COMMIT,
        "binding": "EXACT_CURRENT_COMMITTED_BYTES",
        "artifacts": _artifact_rows(ST1201_ARTIFACTS),
        "required_semantics": {
            "default_mode": "DISABLED_OD_012",
            "tracking": "DISABLED",
            "persistence": "NOT_EXECUTED",
            "measurement": False,
            "decision": "NOT_READY",
            "read_model_rows": [],
        },
    },
    "st1203": {
        "story_id": "ST-1203",
        "feature_commit": ST1203_COMMIT,
        "binding": "EXACT_CURRENT_COMMITTED_BYTES",
        "artifacts": _artifact_rows(ST1203_ARTIFACTS),
        "required_semantics": {
            "top_rows_only": True,
            "rows_not_guaranteed_complete": True,
            "empty_page_proves_zero": False,
            "supersession": "NOT_DEFINED",
            "provider": "NOT_EXECUTED",
            "persistence": "NOT_EXECUTED",
        },
    },
    "st1204": {
        "story_id": "ST-1204",
        "feature_commit": ST1204_COMMIT,
        "binding": "EXACT_CURRENT_COMMITTED_BYTES",
        "artifacts": _artifact_rows(ST1204_ARTIFACTS),
        "required_semantics": {
            "returned_row_count": 2,
            "provider_row_count": 3,
            "pagination_performed": False,
            "numeric_aggregation_performed": False,
            "metric_values_preserved_as_strings": True,
            "supersession": "NOT_DEFINED",
            "tracking": "DISABLED_OD_012",
            "provider": "NOT_EXECUTED",
            "persistence": "NOT_EXECUTED",
        },
    },
}
EXPECTED_CATALOG_PROJECTION: Final = {
    "source_order": "EXACT_CANONICAL_ORDER",
    "source_fields": list(KPI_FIELDS),
    "definition_count": 30,
    "calculation_count": 0,
    "verified_count": 0,
    "domain_distribution": DOMAIN_DISTRIBUTION,
    "formula_representation": "NON_EXECUTABLE_SOURCE_TEXT",
    "activation_inferred": False,
}
EXPECTED_CALCULATION_BOUNDARY: Final[dict[str, object]] = {
    "calculation_version": None,
    "kpi_mappings": [],
    "source_mappings": [],
    "watermarks": [],
    "period": None,
    "inputs": [],
    "sql": None,
    "tables": [],
    "job_payloads": [],
    "read_model_rows": [],
    "results": [],
    "evidence": [],
    "mapping_count": None,
    "watermark_count": None,
    "input_count": None,
    "table_count": None,
    "job_payload_count": None,
    "read_model_row_count": None,
    "result_count": None,
    "evidence_count": None,
    "empty_means_zero": False,
}
EXPECTED_ACTION_COUNTS: Final = {key: 0 for key in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION_BOUNDARY: Final = {
    "formula_engine": "NOT_EXECUTED",
    "calculation": "NOT_EXECUTED",
    "verification": "NOT_EXECUTED",
    "sql": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "tracking_activation": "NOT_EXECUTED",
    "public_projection": "NOT_EXECUTED",
    "recommendation_input": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "network": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
    "external_actions": [],
}
EXPECTED_VERIFICATION_BOUNDARY: Final = {
    "definitions_projected": 30,
    "definitions_total": 30,
    "calculations_completed": 0,
    "calculations_total": 30,
    "calculations_verified": 0,
    "verified_total": 30,
    "calculation_status": "NOT_EXECUTED",
    "verification_status": "NOT_EXECUTED",
    "TST-030": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "story_acceptance": False,
    "decision": "NOT_READY",
}


class KpiReferencePlanError(RuntimeError):
    """Stable, sanitized contract or generation failure."""


class NoAliasDumper(yaml.SafeDumper):
    """Keep generated YAML explicit and deterministic."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise KpiReferencePlanError(f"ST-1205 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(left_item, right_item)
            for left_item, right_item in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_sha256(value: object) -> str:
    try:
        content = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError, RecursionError:
        _fail("CANONICAL_JSON_INVALID", "canonical.value")
    return _sha256(content)


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _text(root: Path, relative: Path, field: str) -> str:
    try:
        return _read(root, relative, field).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("UTF8_REQUIRED", field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _validate_hashes(root: Path) -> None:
    expected = (
        (CONTRACT_PATH, EXPECTED_CONTRACT_SHA256, "contract"),
        (STORY_PATH, STORY_SHA256, "authority.story"),
        (KPI_CATALOG_PATH, KPI_CATALOG_SHA256, "authority.kpi_catalog"),
        (INTEGRATION_PATH, INTEGRATION_SHA256, "authority.integration"),
        (HELPER_PATH, HELPER_SHA256, "implementation.helper"),
        *((path, digest, "predecessor.st1201") for path, digest in ST1201_ARTIFACTS),
        *((path, digest, "predecessor.st1203") for path, digest in ST1203_ARTIFACTS),
        *((path, digest, "predecessor.st1204") for path, digest in ST1204_ARTIFACTS),
    )
    for relative, digest, field in expected:
        if _sha256(_read(root, relative, field)) != digest:
            _fail("SOURCE_HASH_DRIFT", field)


def _validate_authority(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    _exact(
        _find(stories.get("stories"), "ST-1205", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _require_fragments(
    root: Path,
    relative: Path,
    fragments: Sequence[str],
    field: str,
) -> None:
    source = _text(root, relative, field)
    if any(fragment not in source for fragment in fragments):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", field)


def _validate_st1201(root: Path) -> None:
    _require_fragments(
        root,
        ST1201_ARTIFACTS[1][0],
        (
            "return cls(mode=EventCollectorMode.DISABLED_OD_012, event_allowlist=())",
            "self.tracking_activation is not TrackingActivation.DISABLED",
            "self.persistence is not CollectorExecution.NOT_EXECUTED",
            "measurement_observed: bool",
            "or self.measurement_observed",
            "self.decision is not CollectorDecision.NOT_READY",
            "self.formal_tst_030 is not CollectorExecution.NOT_EXECUTED",
        ),
        "predecessor.st1201.domain",
    )
    _require_fragments(
        root,
        ST1201_ARTIFACTS[3][0],
        (
            "tracking_activation=TrackingActivation.DISABLED",
            "persistence=CollectorExecution.NOT_EXECUTED",
            "measurement_observed=False",
            "decision=CollectorDecision.NOT_READY",
        ),
        "predecessor.st1201.application",
    )


def _validate_st1203(root: Path) -> None:
    _require_fragments(
        root,
        ST1203_ARTIFACTS[1][0],
        (
            "self.top_rows_only is not True",
            "top_rows_only: bool",
            "self.rows_not_guaranteed_complete is not True",
            "EmptyPageMeaning.RECORDED_ZERO_ROWS_ONLY if not self.rows else None",
            "self.supersession is not SearchConsoleBoundaryStatus.NOT_DEFINED",
            "self.provider is not SearchConsoleBoundaryStatus.NOT_EXECUTED",
            "self.persistence is not SearchConsoleBoundaryStatus.NOT_EXECUTED",
            "self.decision is not SearchConsoleBoundaryStatus.NOT_READY",
        ),
        "predecessor.st1203.domain",
    )
    _require_fragments(
        root,
        ST1203_ARTIFACTS[0][0],
        (
            "It does not establish complete retrieval, zero traffic, or zero analytics.",
            "supersession remains `NOT_DEFINED`",
        ),
        "predecessor.st1203.readme",
    )


def _validate_st1204(root: Path) -> None:
    _require_fragments(
        root,
        ST1204_ARTIFACTS[1][0],
        (
            "metric_values: tuple[str, ...]",
            "len(self.rows) != 2",
            "self.provider_row_count != 3",
            "self.row_count_independent_of_pagination is not True",
            "self.tracking is not Ga4BoundaryStatus.DISABLED_OD_012",
            "self.provider_execution is not Ga4BoundaryStatus.NOT_EXECUTED",
            "self.persistence is not Ga4BoundaryStatus.NOT_EXECUTED",
            "self.supersession is not Ga4BoundaryStatus.NOT_DEFINED",
            "self.decision is not Ga4BoundaryStatus.NOT_READY",
        ),
        "predecessor.st1204.domain",
    )
    _require_fragments(
        root,
        ST1204_ARTIFACTS[0][0],
        (
            "Metric values remain ordered provider strings.",
            "It never attempts another page",
            "supersession relationship is asserted.",
        ),
        "predecessor.st1204.readme",
    )


def _catalog(root: Path) -> Mapping[str, Any]:
    catalog = _load_yaml(root, KPI_CATALOG_PATH, "authority.kpi_catalog")
    if tuple(catalog) != ("document", "kpis"):
        _fail("SOURCE_SCHEMA_DRIFT", "authority.kpi_catalog")
    _exact(
        catalog["document"],
        {"id": "RAOS-ANALYTICS-KPI-001", "version": "1.0"},
        "authority.kpi_catalog.document",
    )
    rows = _list(catalog["kpis"], "authority.kpi_catalog.kpis")
    if len(rows) != 30:
        _fail("SOURCE_SEMANTIC_DRIFT", "authority.kpi_catalog.count")
    ids: list[str] = []
    hashes: list[str] = []
    domains: list[str] = []
    for raw_row in rows:
        row = _mapping(raw_row, "authority.kpi_catalog.row")
        if tuple(row) != KPI_FIELDS or any(type(row[key]) is not str for key in row):
            _fail("SOURCE_SCHEMA_DRIFT", "authority.kpi_catalog.row")
        ids.append(cast(str, row["id"]))
        domains.append(cast(str, row["domain"]))
        hashes.append(_canonical_sha256(row))
        if (
            row["design_status"] != "APPROVED_FOR_IMPLEMENTATION"
            or row["implementation_status"] != "NOT_STARTED"
            or row["runtime_verification"] != "NOT_EXECUTED"
        ):
            _fail("SOURCE_SEMANTIC_DRIFT", "authority.kpi_catalog.status")
    _exact(ids, list(KPI_IDS), "authority.kpi_catalog.order")
    _exact(hashes, list(KPI_ROW_HASHES), "authority.kpi_catalog.rows")
    _exact(
        dict(Counter(domains)),
        DOMAIN_DISTRIBUTION,
        "authority.kpi_catalog.domains",
    )
    return catalog


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(contract["predecessors"], EXPECTED_PREDECESSORS, "predecessors")
    _exact(
        contract["catalog_projection"],
        EXPECTED_CATALOG_PROJECTION,
        "catalog_projection",
    )
    _exact(
        contract["calculation_boundary"],
        EXPECTED_CALCULATION_BOUNDARY,
        "calculation_boundary",
    )
    _exact(
        contract["execution_boundary"],
        EXPECTED_EXECUTION_BOUNDARY,
        "execution_boundary",
    )
    _exact(
        contract["verification_boundary"],
        EXPECTED_VERIFICATION_BOUNDARY,
        "verification_boundary",
    )
    _validate_hashes(root)
    _validate_authority(root)
    _catalog(root)
    _validate_st1201(root)
    _validate_st1203(root)
    _validate_st1204(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], catalog: Mapping[str, Any]
) -> dict[str, Any]:
    rows = _list(catalog["kpis"], "catalog.kpis")
    projection = {
        **_mapping(contract["catalog_projection"], "catalog_projection"),
        "catalog_document": catalog["document"],
        "kpi_ids": list(KPI_IDS),
        "definitions": rows,
    }
    plan: dict[str, Any] = {
        "document": contract["document"],
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "inventory_derivation": "EXACT_CANONICAL_KPI_CATALOG_PROJECTION",
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_bindings": contract["predecessors"],
        "catalog_projection": projection,
        "calculation_boundary": contract["calculation_boundary"],
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": contract["verification_boundary"],
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _predecessor_manifest_rows() -> list[dict[str, object]]:
    return [
        {
            "story_id": "ST-1201",
            "feature_commit": ST1201_COMMIT,
            "binding": "EXACT_CURRENT_COMMITTED_BYTES",
            "inputs": _artifact_uri_rows(ST1201_ARTIFACTS),
        },
        {
            "story_id": "ST-1203",
            "feature_commit": ST1203_COMMIT,
            "binding": "EXACT_CURRENT_COMMITTED_BYTES",
            "inputs": _artifact_uri_rows(ST1203_ARTIFACTS),
        },
        {
            "story_id": "ST-1204",
            "feature_commit": ST1204_COMMIT,
            "binding": "EXACT_CURRENT_COMMITTED_BYTES",
            "inputs": _artifact_uri_rows(ST1204_ARTIFACTS),
        },
    ]


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST1205-KPI-READ-MODEL-REFERENCE-PLAN-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1205",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "canonical_story": {
                "uri": f"repo://{STORY_PATH.as_posix()}",
                "sha256": STORY_SHA256,
            },
            "kpi_catalog": {
                "uri": f"repo://{KPI_CATALOG_PATH.as_posix()}",
                "sha256": KPI_CATALOG_SHA256,
            },
            "integration_precedence": {
                "uri": f"repo://{INTEGRATION_PATH.as_posix()}",
                "sha256": INTEGRATION_SHA256,
            },
            "inventory_derivation": "EXACT_CANONICAL_KPI_CATALOG_PROJECTION",
            "predecessors": _predecessor_manifest_rows(),
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "non_attesting": True,
            "decision": "NOT_READY",
            "definition_count": 30,
            "calculation_count": 0,
            "verified_count": 0,
            "calculation_version": None,
            "mapping_count": None,
            "watermark_count": None,
            "input_count": None,
            "table_count": None,
            "job_payload_count": None,
            "read_model_row_count": None,
            "result_count": None,
            "evidence_count": None,
            "empty_means_zero": False,
            "action_count_total": 0,
            "runtime_actions": "NOT_EXECUTED",
            "formal_tst_030": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    catalog = _catalog(root)
    reference_bytes = _json_bytes(reference_plan(contract, catalog))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


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
    except (KpiReferencePlanError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1205 KPI reference plan checked"
        if args.check
        else "ST-1205 KPI reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
