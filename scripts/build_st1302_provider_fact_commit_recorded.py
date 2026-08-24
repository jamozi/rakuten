#!/usr/bin/env python3
"""Build the executable-local, never-external ST-1302 recorded projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_provider_fact_commit import (  # noqa: E402
    RecordedProviderFactCommitAdapter,
    load_recorded_provider_fact_commit_fixture,
)
from raos.application.finance.provider_fact_commit import (  # noqa: E402
    ProviderFactCommitService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1302/contracts/provider-fact-commit-recorded.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1302/fixtures/provider-fact-commit-recorded.synthetic.v1.json"
)
PLAN_PATH: Final = Path(
    "changes/st-1302/generated/provider-fact-commit-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1302/manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1302_provider_fact_commit_recorded.py")
README_PATH: Final = Path("changes/st-1302/README.md")
COMPLETION_PATH: Final = Path("changes/st-1302/LOCAL_COMPLETION.md")
RUNTIME_PATHS: Final = (
    Path("python/raos/domain/finance/provider_fact_commit.py"),
    Path("python/raos/ports/provider_fact_commit.py"),
    Path("python/raos/application/finance/provider_fact_commit.py"),
    Path("python/raos/adapters/recorded_provider_fact_commit.py"),
)
TEST_PATHS: Final = (
    Path("tests/st1302/test_provider_fact_commit.py"),
    Path("tests/st1302/test_provider_fact_commit_negative.py"),
    Path("tests/st1302/test_recorded_generation.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    README_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *RUNTIME_PATHS,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1302_provider_fact_commit_recorded.py"
)

SOURCE_BINDINGS: Final = (
    (
        "canonical_story",
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "analytics_design",
        Path(
            "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md"
        ),
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    ),
    (
        "attribution_policy",
        Path("docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"),
        "29624996381ff0709c6499edcdca1109eb713ce56ad8b981df02153e11fc8b0c",
    ),
    (
        "open_decisions",
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "role_permission_matrix",
        Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
    (
        "finance_data_contract",
        Path("changes/st-0305/contracts/publication-analytics-finance.v1.yaml"),
        "2947fe100633a2611b9287c6530856b9679365bb10d4af4728a5148ed970377f",
    ),
    (
        "canonical_row_schema",
        Path(
            "contracts/raos-v0.4/contracts/schemas/imports/revenue-canonical-row.schema.json"
        ),
        "02bc3d854a7420a74a8b302342a9ad0e23cfe4529565716a185c333b43ebbff8",
    ),
    (
        "commit_job_schema",
        Path(
            "contracts/raos-v0.4/contracts/schemas/jobs/finance-commit-revenue-import-v1.schema.json"
        ),
        "9e0b860aacd151888e67e76a64ad94e8c3dd33072de42f570b8b233e1a9dce0d",
    ),
    (
        "job_catalog",
        Path("contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"),
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        "committed_event_schema",
        Path(
            "contracts/raos-v0.4/contracts/schemas/events/jp-raos-finance-revenue-import-committed-v1.schema.json"
        ),
        "b5c6ad9f2ca522b87e7c630a941817a84a2c8e2ce2604bb9767e976079d71f21",
    ),
    (
        "status_event_schema",
        Path(
            "contracts/raos-v0.4/contracts/schemas/events/jp-raos-finance-commission-status-changed-v1.schema.json"
        ),
        "7fc5e7c5949b5e4588ad7970bfc54d42fd27f898e035a56116b3726a0602865b",
    ),
    (
        "st1301_domain",
        Path("python/raos/domain/finance/revenue_import.py"),
        "9698846ff18dfa7fb81b338f126fe70e28f96151ed8283eac8cb5da7132265eb",
    ),
    (
        "v1_reference_contract",
        Path("changes/st-1302/contracts/provider-fact-commit-reference-plan.v1.yaml"),
        "6f4848b121ecdd31b63fda9b41488b2e690d839bb7d4806de1e09039a7418a10",
    ),
    (
        "recorded_fixture",
        FIXTURE_PATH,
        "1839d9bdc4a5dfae3008e0f285bc36f45e48ef6b95b2dfd15ad7c4984cba3cb2",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "source_bindings",
    "open_decision_boundary",
    "preview_binding",
    "commit_boundary",
    "authorization_boundary",
    "vocabulary_boundary",
    "authority_boundary",
    "verification_boundary",
)
EXPECTED_DOCUMENT: Final = {
    "schema_version": "2.0.0",
    "story_id": "ST-1302",
    "classification": "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_PROVIDER_FACT_COMMIT",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "local_executable": True,
    "environments": ["ENV-DEV", "ENV-CI"],
    "authority": "RECORDED_SYNTHETIC_ONLY",
    "canonical_status": "UNCHANGED",
    "story_acceptance_claimed": False,
    "formal_validation_claimed": False,
    "production_eligible": False,
}
EXPECTED_OPEN_DECISION: Final = {
    "id": "OD-003",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "blocking": True,
    "safe_default": "SYNTHETIC_FIXTURE_ONLY_REAL_ATTRIBUTION_UNVERIFIED",
    "resolved": False,
}
EXPECTED_PREVIEW_BINDING: Final = {
    "algorithm": "RAOS_ST1302_LOCAL_PREVIEW_BINDING_SHA256_V1",
    "required": True,
    "binds": [
        "source_sha256",
        "ST-1301 command fingerprint",
        "accepted row number and row hash",
        "hashed synthetic provider event key",
        "source event type and event timestamp",
        "generated and confirmed Decimal JPY",
        "confirmed missingness",
        "status summaries",
        "observed period",
    ],
    "canonical_preview_hash_equivalence": "NOT_ASSERTED",
    "canonical_contract_inconsistency": "UNRESOLVED",
    "canonical_contract_changed": False,
}
EXPECTED_COMMIT_BOUNDARY: Final = {
    "profile": "RAOS_ST1302_RECORDED_SYNTHETIC_V1",
    "provider_code": "RAKUTEN_AFFILIATE",
    "currency": "JPY",
    "exact_amount_type": "INTEGRAL_DECIMAL_JPY",
    "source_duplicate_policy": "REJECT",
    "idempotency_policy": "SAME_KEY_SAME_REQUEST_REPLAY_DIFFERENT_REQUEST_REJECT",
    "atomicity": "PROCESS_LOCAL_ATOMIC_SWAP",
    "artifacts": [
        "immutable provider facts",
        "immutable source-vocabulary commission events",
        "immutable audit record",
        "immutable outbox-like local records",
    ],
    "database_write": "NOT_EXECUTED",
    "provider_call": "NOT_EXECUTED",
    "network": "NOT_EXECUTED",
}
EXPECTED_AUTHORIZATION: Final = {
    "subject": "ACTIVE_HUMAN_RECORDED_SYNTHETIC",
    "roles": ["PRODUCT_OWNER", "ANALYST"],
    "mfa": "REQUIRED_RECORDED_SYNTHETIC",
    "step_up": "REQUIRED_RECORDED_SYNTHETIC",
    "max_step_up_age_seconds": 300,
    "site_scope": "REQUIRED",
    "dry_run_preparer_committer_separation": "REQUIRED_LOCAL_SAFE_HARDENING",
    "real_authorization_asserted": False,
}
EXPECTED_VOCABULARY: Final = {
    "source_event": ["GENERATED", "CONFIRMED", "CANCELLED", "ADJUSTED"],
    "provider_fact_status": ["GENERATED", "CONFIRMED", "CANCELLED", "ADJUSTED"],
    "canonical_commission_event": [
        "GENERATED",
        "CONFIRMED",
        "CANCELLED",
        "AMOUNT_CHANGED",
        "CORRECTED",
    ],
    "mapping_defined": False,
    "emitted_canonical_commission_event_type": None,
    "mapping_state": "UNVERIFIED_PRESERVED_UNMAPPED",
}
EXPECTED_AUTHORITY: Final = {
    "recorded_synthetic_only": True,
    "database_write_authorized": False,
    "provider_call_authorized": False,
    "network_authorized": False,
    "publication_authorized": False,
    "live_authorized": False,
    "staging_authorized": False,
    "release_authorized": False,
    "production_authorized": False,
}
EXPECTED_VERIFICATION: Final = {
    "local_unit_and_adversarial_tests": "CANDIDATE",
    "owner_generator_check": "CANDIDATE",
    "TST-008": "NOT_EXECUTED",
    "TST-030": "NOT_EXECUTED",
    "real_provider_mapping": "NOT_EXECUTED",
    "database_integration": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


class ProviderFactRecordedBuildError(RuntimeError):
    """Stable sanitized owner-generation failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise ProviderFactRecordedBuildError(
        f"ST-1302 recorded build failed: {code} field={field}"
    )


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


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


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = cast(bytes, physical.read_bytes())
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if not content or len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_INVALID", field)
    return content


def _source_binding_map() -> dict[str, dict[str, str]]:
    return {
        name: {"path": path.as_posix(), "sha256": digest}
        for name, path, digest in SOURCE_BINDINGS
    }


def _load_yaml(root: Path) -> Mapping[str, Any]:
    _read(root, CONTRACT_PATH, "contract")
    try:
        value = base.load_yaml(root / CONTRACT_PATH)
    except Exception:
        _fail("CONTRACT_INVALID", "contract")
    return _mapping(value, "contract")


def _validate_source_semantics(root: Path) -> None:
    for _name, path, digest in SOURCE_BINDINGS:
        if _sha256(_read(root, path, "source_binding")) != digest:
            _fail("INPUT_HASH_DRIFT", "source_binding")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_HASH_DRIFT", "helper")

    story_source = cast(
        Mapping[str, Any], yaml.safe_load(_read(root, SOURCE_BINDINGS[0][1], "story"))
    )
    stories = cast(list[Mapping[str, Any]], story_source.get("stories"))
    story = [item for item in stories if item.get("id") == "ST-1302"]
    if len(story) != 1 or story[0].get("acceptance_criteria") != [
        "generated/confirmed/cancelled separate"
    ]:
        _fail("STORY_SEMANTIC_DRIFT", "story")

    decisions = cast(
        Mapping[str, Any],
        yaml.safe_load(_read(root, SOURCE_BINDINGS[3][1], "open_decisions")),
    )
    od003 = [
        item
        for item in cast(list[Mapping[str, Any]], decisions.get("items"))
        if item.get("id") == "OD-003"
    ]
    if (
        len(od003) != 1
        or od003[0].get("status") != "EXTERNAL_EVIDENCE_REQUIRED"
        or od003[0].get("blocking") is not True
    ):
        _fail("OPEN_DECISION_DRIFT", "OD-003")

    row_schema = cast(
        Mapping[str, Any],
        json.loads(_read(root, SOURCE_BINDINGS[6][1], "row_schema")),
    )
    properties = cast(Mapping[str, Any], row_schema.get("properties"))
    if cast(Mapping[str, Any], properties.get("event_type")).get(
        "enum"
    ) != EXPECTED_VOCABULARY["source_event"] or properties.get("currency") != {
        "const": "JPY"
    }:
        _fail("ROW_SCHEMA_DRIFT", "row_schema")

    job_schema = cast(
        Mapping[str, Any],
        json.loads(_read(root, SOURCE_BINDINGS[7][1], "job_schema")),
    )
    all_of = cast(list[Mapping[str, Any]], job_schema.get("allOf"))
    payload = cast(
        Mapping[str, Any],
        cast(Mapping[str, Any], all_of[1].get("properties")).get("payload"),
    )
    payload_fields = cast(Mapping[str, Any], payload.get("properties"))
    catalog = cast(
        Mapping[str, Any],
        yaml.safe_load(_read(root, SOURCE_BINDINGS[8][1], "job_catalog")),
    )
    jobs = cast(list[Mapping[str, Any]], catalog.get("jobs"))
    commit_jobs = [
        item
        for item in jobs
        if item.get("job_type") == "finance.commit_revenue_import.v1"
    ]
    if (
        len(commit_jobs) != 1
        or commit_jobs[0].get("idempotency_basis")
        != ["revenue_import_id", "source_sha256", "preview_hash"]
        or "preview_hash" in payload_fields
    ):
        _fail("PREVIEW_INCONSISTENCY_DRIFT", "preview_binding")

    matrix = cast(
        Mapping[str, Any],
        yaml.safe_load(_read(root, SOURCE_BINDINGS[4][1], "rbac")),
    )
    permissions = cast(list[Mapping[str, Any]], matrix.get("permissions"))
    commit_permissions = [
        item for item in permissions if item.get("action") == "commit_revenue_import"
    ]
    if (
        len(commit_permissions) != 1
        or commit_permissions[0].get("allowed_roles") != ["PRODUCT_OWNER", "ANALYST"]
        or commit_permissions[0].get("mfa_required") is not True
        or commit_permissions[0].get("step_up_required") is not True
    ):
        _fail("RBAC_DRIFT", "authorization")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    expected = (
        ("document", EXPECTED_DOCUMENT),
        ("source_bindings", _source_binding_map()),
        ("open_decision_boundary", EXPECTED_OPEN_DECISION),
        ("preview_binding", EXPECTED_PREVIEW_BINDING),
        ("commit_boundary", EXPECTED_COMMIT_BOUNDARY),
        ("authorization_boundary", EXPECTED_AUTHORIZATION),
        ("vocabulary_boundary", EXPECTED_VOCABULARY),
        ("authority_boundary", EXPECTED_AUTHORITY),
        ("verification_boundary", EXPECTED_VERIFICATION),
    )
    for key, value in expected:
        _exact(contract.get(key), value, key)
    _validate_source_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root), root)


def _recorded_result(root: Path) -> dict[str, object]:
    scenario = load_recorded_provider_fact_commit_fixture(
        (root / FIXTURE_PATH).resolve()
    )
    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
    )
    service = ProviderFactCommitService(
        environment=RuntimeEnvironment.CI,
        authorization_source=adapter,
        store=adapter,
    )
    result = service.execute(request=scenario.request, bundle=scenario.bundle)
    replay = service.execute(request=scenario.request, bundle=scenario.bundle)
    snapshot = adapter.snapshot()
    if (
        result.canonical_bytes() != replay.canonical_bytes()
        or snapshot.source_count != 1
    ):
        _fail("RECORDED_REPLAY_DRIFT", "recorded_result")
    return {
        "scenario_id": scenario.scenario_id,
        "fixture_sha256": scenario.fixture_sha256.value,
        "source_sha256": scenario.request.expected_source_sha256.value,
        "local_preview_binding_sha256": (
            scenario.bundle.local_preview_binding_sha256.value
        ),
        "result_sha256": result.result_sha256.value,
        "execution": result.execution.value,
        "commit_state": result.commit_state.value,
        "mapping": result.mapping.value,
        "accepted_count": len(result.facts),
        "provider_fact_count": len(result.facts),
        "commission_event_count": len(result.commission_events),
        "audit_count": snapshot.audit_count,
        "outbox_count": len(result.outbox),
        "generated_commission_jpy": (
            scenario.bundle.generated_commission_jpy.canonical_text
        ),
        "confirmed_commission_jpy": (
            None
            if scenario.bundle.confirmed_commission_jpy is None
            else scenario.bundle.confirmed_commission_jpy.canonical_text
        ),
        "confirmed_missing_count": scenario.bundle.confirmed_missing_count,
        "currency": "JPY",
        "period_from": scenario.request.expected_period_from.isoformat(),
        "period_to": scenario.request.expected_period_to.isoformat(),
        "status_summaries": [
            item.binding_payload() for item in result.status_summaries
        ],
        "canonical_commission_event_types": [
            item.canonical_event_type for item in result.commission_events
        ],
        "idempotent_replay": True,
        "process_local_source_count": snapshot.source_count,
    }


def projection(root: Path = REPO_ROOT) -> dict[str, object]:
    contract = load_contract(root)
    return {
        "document": dict(cast(Mapping[str, object], contract["document"])),
        "provenance": {
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "recorded_fixture": f"repo://{FIXTURE_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
            "source_bindings": [
                {
                    "name": name,
                    "uri": f"repo://{path.as_posix()}",
                    "sha256": digest,
                }
                for name, path, digest in SOURCE_BINDINGS
            ],
        },
        "open_decision_boundary": EXPECTED_OPEN_DECISION,
        "preview_binding": EXPECTED_PREVIEW_BINDING,
        "commit_boundary": EXPECTED_COMMIT_BOUNDARY,
        "authorization_boundary": EXPECTED_AUTHORIZATION,
        "vocabulary_boundary": EXPECTED_VOCABULARY,
        "recorded_result": _recorded_result(root),
        "authority_boundary": EXPECTED_AUTHORITY,
        "verification_boundary": EXPECTED_VERIFICATION,
    }


def _json_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except Exception:
        _fail("JSON_SERIALIZATION_FAILED", "output")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "source_artifact")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, plan_bytes: bytes) -> bytes:
    manifest = {
        "schema_version": "2.0.0",
        "story_id": "ST-1302",
        "classification": EXPECTED_DOCUMENT["classification"],
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "local_executable": True,
        "external_authority": False,
        "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifacts": [
            {
                "uri": f"repo://{PLAN_PATH.as_posix()}",
                "bytes": len(plan_bytes),
                "sha256": _sha256(plan_bytes),
            }
        ],
        "provenance": {
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "source_bindings": [
                {"uri": f"repo://{path.as_posix()}", "sha256": digest}
                for _name, path, digest in SOURCE_BINDINGS
            ],
        },
        "boundary": {
            "OD-003": "EXTERNAL_EVIDENCE_REQUIRED",
            "canonical_preview_hash_equivalence": "NOT_ASSERTED",
            "canonical_mapping_defined": False,
            "TST-008": "NOT_EXECUTED",
            "TST-030": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "provider": "NOT_EXECUTED",
            "network": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    plan_bytes = _json_bytes(projection(root))
    return {
        PLAN_PATH: plan_bytes,
        MANIFEST_PATH: _manifest_bytes(root, plan_bytes),
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


def main_for_root(root: Path, argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(root, check=args.check)
    except (ProviderFactRecordedBuildError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1302 recorded provider-fact projection checked"
        if args.check
        else "ST-1302 recorded provider-fact projection generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
