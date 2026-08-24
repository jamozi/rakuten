#!/usr/bin/env python3
"""Build the deterministic recorded/synthetic ST-1303 attribution projection."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_attribution import (  # noqa: E402
    RecordedAttributionAdapter,
    load_recorded_attribution_fixture,
)
from raos.application.finance.attribution import AttributionService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.finance.attribution import (  # noqa: E402
    ARTICLE_METRICS,
    CONTRACT_VERSION,
    DIRECT_CONFIDENCE_BPS,
    ESTIMATED_CONFIDENCE_BPS,
    METHOD_VERSION,
    PERIOD_DURATION_DAYS,
    PROGRAM,
    RECOMMENDATION_INPUTS_EXCLUDED,
    ContractArticle,
    MeasurementAttributionContract,
)
from raos.domain.ops.object_intake import Sha256Digest  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1303/contracts/attribution-engine-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1303/generated/attribution-engine-recorded.v2.json"
)
GENERATOR_PATH: Final = Path("scripts/build_st1303_attribution_engine.py")
README_PATH: Final = Path("changes/st-1303/README-v2.md")
PREFLIGHT_PATH: Final = Path("changes/st-1303/PREFLIGHT-v2.md")
COMPLETION_PATH: Final = Path("changes/st-1303/LOCAL_COMPLETION-v2.md")
ST1704_CONTRACT_PATH: Final = Path(
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
)
RUNTIME_PATHS: Final = (
    Path("python/raos/domain/finance/attribution.py"),
    Path("python/raos/ports/attribution.py"),
    Path("python/raos/application/finance/attribution.py"),
    Path("python/raos/adapters/recorded_attribution.py"),
)
TEST_PATHS: Final = (
    Path("tests/st1303_v2/__init__.py"),
    Path("tests/st1303_v2/conftest.py"),
    Path("tests/st1303_v2/test_attribution_runtime.py"),
    Path("tests/st1303_v2/test_attribution_negative.py"),
    Path("tests/st1303_v2/test_generation.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    README_PATH,
    PREFLIGHT_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *RUNTIME_PATHS,
    *TEST_PATHS,
)
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1303_attribution_engine.py"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

SOURCE_BINDINGS: Final = {
    "canonical_story": {
        "path": "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "sha256": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    },
    "analytics_design": {
        "path": "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md",
        "sha256": "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    },
    "attribution_policy": {
        "path": "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml",
        "sha256": "29624996381ff0709c6499edcdca1109eb713ce56ad8b981df02153e11fc8b0c",
    },
    "open_decisions": {
        "path": "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "sha256": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    },
    "test_catalog": {
        "path": "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "sha256": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    },
    "security_design": {
        "path": "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        "sha256": "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    },
    "threat_register": {
        "path": "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml",
        "sha256": "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    },
    "st1202_runtime": {
        "path": "changes/st-1202/runtime-manifest.v2.yaml",
        "sha256": "a561ba3ec7e7851d0cbdbfb357bf388801b36ae8a28e7f46969ba201079b761f",
    },
    "st1302_runtime": {
        "path": "changes/st-1302/manifest.v2.yaml",
        "sha256": "1c1ee418d69bf199730e9354f9197f166de96d2629dd22298dd058d1bf7b2790",
    },
    "five_slot_measurement": {
        "path": ST1704_CONTRACT_PATH.as_posix(),
        "sha256": "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8",
    },
}

EXPECTED_DOCUMENT: Final = {
    "schema_version": "2.0.0",
    "story_id": "ST-1303",
    "classification": "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_ATTRIBUTION_ENGINE",
    "status": "LOCAL_CODE_COMPLETE",
    "executable_environments": ["ENV-DEV", "ENV-CI"],
    "authority": "RECORDED_SYNTHETIC_ONLY",
    "canonical_status": "UNCHANGED",
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
EXPECTED_METHOD: Final = {
    "method_version": METHOD_VERSION,
    "direct": "VERIFIED_HASHED_PROVIDER_KEY_AND_EXACT_ARTICLE_BINDING_ONLY",
    "estimated": "SAME_PROGRAM_PERIOD_VERIFIED_MATURE_ELIGIBLE_CLICK_WEIGHT",
    "integer_allocation": "LARGEST_REMAINDER_SLOT_ASCENDING_TIE_BREAK",
    "direct_confidence_bps": DIRECT_CONFIDENCE_BPS,
    "estimated_confidence_bps": ESTIMATED_CONFIDENCE_BPS,
    "unattributed_confidence_bps": 0,
    "input_hash_required": True,
    "closed_reason_required": True,
    "exact_total_conservation": True,
    "arbitrary_provider_total_allocation": False,
    "unattributed_reward_article_allocation": False,
    "measurement_fact_consistency_required": True,
}
EXPECTED_AUTHORITY: Final = {
    "provider_call": False,
    "network": False,
    "persistence": False,
    "publication": False,
    "editorial_mutation": False,
    "article_html_mutation": False,
    "cta_mutation": False,
    "product_selection_mutation": False,
    "recommendation_order_mutation": False,
    "publication_snapshot_mutation": False,
    "staging": False,
    "release": False,
    "production": False,
    "recommendation_inputs_excluded": list(RECOMMENDATION_INPUTS_EXCLUDED),
    "all_finance_values_excluded_from_improvement_candidates": True,
}
EXPECTED_VERIFICATION: Final = {
    "local_unit_property_adversarial": "CANDIDATE",
    "owner_generator_check": "CANDIDATE",
    "TST-007": "NOT_EXECUTED",
    "TST-030": "NOT_EXECUTED",
    "real_provider_mapping": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}
CONTRACT_KEYS: Final = (
    "document",
    "source_bindings",
    "open_decision_boundary",
    "measurement_contract",
    "method_boundary",
    "authority_boundary",
    "verification_boundary",
)


class AttributionBuildError(RuntimeError):
    """Sanitized deterministic owner-generation failure."""


class UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _unique_mapping(
    loader: UniqueSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except Exception:
            _fail("YAML_KEY_INVALID", "contract")
        if duplicate:
            _fail("YAML_DUPLICATE_KEY", "contract")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _fail(code: str, field: str) -> NoReturn:
    raise AttributionBuildError(f"ST-1303 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _physical_path(root: Path, relative: Path, field: str) -> Path:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("PATH_INVALID", field)
    try:
        root = root.resolve(strict=True)
    except OSError:
        _fail("ROOT_INVALID", field)
    current = root
    for part in relative.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            _fail("FILE_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode):
            _fail("SYMLINK_FORBIDDEN", field)
    return current


def _read(root: Path, relative: Path, field: str) -> bytes:
    path = _physical_path(root, relative, field)
    try:
        metadata = path.stat()
        payload = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not payload
        or len(payload) != metadata.st_size
        or len(payload) > MAX_SOURCE_BYTES
    ):
        _fail("FILE_INVALID", field)
    return payload


def _load_yaml(root: Path) -> Mapping[str, Any]:
    payload = _read(root, CONTRACT_PATH, "contract")
    try:
        value = yaml.load(payload, Loader=UniqueSafeLoader)
    except AttributionBuildError:
        raise
    except Exception:
        _fail("CONTRACT_INVALID", "contract")
    return _mapping(value, "contract")


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail("JSON_DUPLICATE_KEY", field)
            result[key] = value
        return result

    try:
        value = json.loads(_read(root, relative, field), object_pairs_hook=pairs)
    except AttributionBuildError:
        raise
    except Exception:
        _fail("JSON_INVALID", field)
    return _mapping(value, field)


def _validate_bindings(root: Path, source: object) -> None:
    if source != SOURCE_BINDINGS:
        _fail("SOURCE_BINDING_SCHEMA_DRIFT", "source_bindings")
    for name, binding in SOURCE_BINDINGS.items():
        path = Path(binding["path"])
        if _sha256(_read(root, path, name)) != binding["sha256"]:
            _fail("INPUT_HASH_DRIFT", name)


def _validate_canonical_semantics(root: Path) -> None:
    backlog = cast(
        Mapping[str, Any],
        yaml.safe_load(
            _read(
                root,
                Path(SOURCE_BINDINGS["canonical_story"]["path"]),
                "canonical_story",
            )
        ),
    )
    stories = cast(list[Mapping[str, Any]], backlog.get("stories"))
    selected = [item for item in stories if item.get("id") == "ST-1303"]
    if (
        len(selected) != 1
        or selected[0].get("depends_on") != ["ST-1202", "ST-1302"]
        or selected[0].get("requirement_ids") != ["FR-013"]
        or selected[0].get("acceptance_criteria")
        != ["totals conserved", "confidence required"]
        or selected[0].get("test_suites") != ["TST-007", "TST-030"]
        or selected[0].get("open_decisions") != ["OD-003"]
    ):
        _fail("STORY_SEMANTIC_DRIFT", "ST-1303")

    policy = cast(
        Mapping[str, Any],
        yaml.safe_load(
            _read(
                root,
                Path(SOURCE_BINDINGS["attribution_policy"]["path"]),
                "attribution_policy",
            )
        ),
    )
    classes = cast(list[Mapping[str, Any]], policy.get("classes"))
    if [item.get("code") for item in classes] != [
        "PROVIDER_FACT",
        "DIRECT",
        "ESTIMATED",
        "UNATTRIBUTED",
    ] or cast(Mapping[str, Any], policy.get("mvp_estimation")).get("status") != (
        "PROVISIONAL_PENDING_REAL_REPORT_SAMPLE"
    ):
        _fail("ATTRIBUTION_POLICY_DRIFT", "attribution_policy")

    decisions = cast(
        Mapping[str, Any],
        yaml.safe_load(
            _read(
                root,
                Path(SOURCE_BINDINGS["open_decisions"]["path"]),
                "open_decisions",
            )
        ),
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


def _measurement_contract(
    source: Mapping[str, Any], root: Path
) -> MeasurementAttributionContract:
    expected_keys = (
        "schema_version",
        "source_contract_sha256",
        "program",
        "period_duration_days",
        "articles",
        "article_metrics",
        "program_metrics",
        "value_states",
        "zero_is_observed_only_when_explicit",
    )
    if tuple(source) != expected_keys:
        _fail("MEASUREMENT_CONTRACT_SCHEMA_DRIFT", "measurement_contract")
    upstream = _load_json(root, ST1704_CONTRACT_PATH, "five_slot_measurement")
    upstream_articles = cast(list[Mapping[str, Any]], upstream.get("articles"))
    expected_articles = [
        {
            "slot": item["slot"],
            "article_id": item["article_id"],
            "slug": item["slug"],
            "packet_sha256": item["packet_sha256"],
            "intent_classification": item["intent_classification"],
        }
        for item in upstream_articles
    ]
    if (
        source["schema_version"] != CONTRACT_VERSION
        or source["source_contract_sha256"]
        != SOURCE_BINDINGS["five_slot_measurement"]["sha256"]
        or source["program"] != PROGRAM
        or source["period_duration_days"] != PERIOD_DURATION_DAYS
        or source["articles"] != expected_articles
        or source["article_metrics"] != list(ARTICLE_METRICS)
        or source["program_metrics"] != ["unattributed_confirmed_reward_jpy"]
        or source["value_states"]
        != [
            "NOT_OBSERVED",
            "UNAVAILABLE",
            "UNVERIFIED",
            "OBSERVED_ZERO",
            "OBSERVED_VALUE",
        ]
        or source["zero_is_observed_only_when_explicit"] is not True
        or upstream.get("program") != PROGRAM
        or upstream.get("period_duration_days") != PERIOD_DURATION_DAYS
        or cast(Mapping[str, Any], upstream.get("metric_contract")).get(
            "article_metrics"
        )
        != list(ARTICLE_METRICS)
        or cast(Mapping[str, Any], upstream.get("metric_contract")).get("states")
        != source["value_states"]
        or cast(Mapping[str, Any], upstream.get("guardrails")).get(
            "recommendation_inputs_excluded"
        )
        != ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"]
    ):
        _fail("MEASUREMENT_CONTRACT_DRIFT", "measurement_contract")
    try:
        return MeasurementAttributionContract(
            articles=tuple(
                ContractArticle(
                    slot=item["slot"],
                    article_id=item["article_id"],
                    slug=item["slug"],
                    packet_sha256=Sha256Digest(item["packet_sha256"]),
                    intent_classification=item["intent_classification"],
                )
                for item in expected_articles
            ),
            source_contract_sha256=Sha256Digest(
                cast(str, source["source_contract_sha256"])
            ),
            program=cast(str, source["program"]),
            schema_version=cast(str, source["schema_version"]),
        )
    except Exception:
        _fail("MEASUREMENT_CONTRACT_INVALID", "measurement_contract")


def load_contract(
    root: Path = REPO_ROOT,
) -> tuple[Mapping[str, Any], MeasurementAttributionContract]:
    contract = _load_yaml(root)
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    if contract["document"] != EXPECTED_DOCUMENT:
        _fail("DOCUMENT_DRIFT", "document")
    _validate_bindings(root, contract["source_bindings"])
    if contract["open_decision_boundary"] != EXPECTED_OPEN_DECISION:
        _fail("OPEN_DECISION_BOUNDARY_DRIFT", "open_decision_boundary")
    measurement = _measurement_contract(
        _mapping(contract["measurement_contract"], "measurement_contract"), root
    )
    if contract["method_boundary"] != EXPECTED_METHOD:
        _fail("METHOD_BOUNDARY_DRIFT", "method_boundary")
    if contract["authority_boundary"] != EXPECTED_AUTHORITY:
        _fail("AUTHORITY_BOUNDARY_DRIFT", "authority_boundary")
    if contract["verification_boundary"] != EXPECTED_VERIFICATION:
        _fail("VERIFICATION_BOUNDARY_DRIFT", "verification_boundary")
    _validate_canonical_semantics(root)
    return contract, measurement


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    payload = _read(root, relative, "source_artifact")
    return {
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "uri": f"repo://{relative.as_posix()}",
    }


def projection(root: Path = REPO_ROOT) -> dict[str, object]:
    contract, measurement_contract = load_contract(root)
    scenario = load_recorded_attribution_fixture(
        (root / FIXTURE_PATH).resolve(), contract=measurement_contract
    )
    adapter = RecordedAttributionAdapter()
    service = AttributionService(
        environment=RuntimeEnvironment.CI,
        runner=adapter,
    )
    first = service.execute(scenario.request)
    replay = service.execute(scenario.request)
    snapshot = adapter.snapshot()
    if (
        first != replay
        or first.canonical_bytes() != replay.canonical_bytes()
        or snapshot.run_count != 1
        or snapshot.replay_count != 1
        or first.totals.difference_jpy.canonical_text != "0"
    ):
        _fail("RECORDED_REPLAY_DRIFT", "recorded_result")
    return {
        "document": dict(cast(Mapping[str, object], contract["document"])),
        "provenance": {
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
            "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
            "source_bindings": [
                {
                    "name": name,
                    "sha256": binding["sha256"],
                    "uri": f"repo://{binding['path']}",
                }
                for name, binding in SOURCE_BINDINGS.items()
            ],
        },
        "open_decision_boundary": EXPECTED_OPEN_DECISION,
        "measurement_contract": {
            "contract_sha256": measurement_contract.sha256.value,
            "period_duration_days": PERIOD_DURATION_DAYS,
            "program": PROGRAM,
            "slot_count": len(measurement_contract.articles),
            "slots": [item.payload() for item in measurement_contract.articles],
        },
        "method_boundary": EXPECTED_METHOD,
        "recorded_result": {
            "allocations": [item.payload() for item in first.allocations],
            "authority": first.authority.payload(),
            "availability": first.availability.value,
            "fixture_sha256": scenario.fixture_sha256.value,
            "idempotent_replay": True,
            "input_sha256": first.input_sha256.value,
            "measurement_evaluation": first.measurement_evaluation.payload(),
            "method_version": first.method_version,
            "replay_count": snapshot.replay_count,
            "result_sha256": first.result_sha256.value,
            "run_count": snapshot.run_count,
            "scenario_id": scenario.scenario_id,
            "totals": first.totals.payload(),
        },
        "authority_boundary": EXPECTED_AUTHORITY,
        "verification_boundary": EXPECTED_VERIFICATION,
        "completion_boundary": {
            "local_code_complete": True,
            "local_integration_complete": False,
            "canonical_status_changed": False,
            "formal_or_live_evidence_claimed": False,
        },
    }


def render_output(root: Path = REPO_ROOT) -> bytes:
    try:
        return (
            json.dumps(
                projection(root),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except AttributionBuildError:
        raise
    except Exception:
        _fail("OUTPUT_SERIALIZATION_FAILED", "output")


def _output_path(root: Path) -> Path:
    relative_parent = OUTPUT_PATH.parent
    parent = _physical_path(root, relative_parent, "output_parent")
    if not parent.is_dir():
        _fail("OUTPUT_PARENT_INVALID", "output")
    output = parent / OUTPUT_PATH.name
    if output.exists() or output.is_symlink():
        try:
            metadata = os.lstat(output)
        except OSError:
            _fail("OUTPUT_INVALID", "output")
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            _fail("OUTPUT_INVALID", "output")
    return output


def _atomic_write(root: Path, payload: bytes) -> None:
    output = _output_path(root)
    descriptor = -1
    stage: Path | None = None
    try:
        descriptor, raw_stage = tempfile.mkstemp(
            prefix=f".{OUTPUT_PATH.name}.", suffix=".stage", dir=output.parent
        )
        stage = Path(raw_stage)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(stage, 0o644)
        os.replace(stage, output)
        stage = None
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except AttributionBuildError:
        raise
    except OSError:
        _fail("ATOMIC_WRITE_FAILED", "output")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if stage is not None:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    expected = render_output(root)
    if check:
        output = _output_path(root)
        try:
            actual = output.read_bytes()
            mode = stat.S_IMODE(output.stat().st_mode)
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected:
            _fail("GENERATED_OUTPUT_DRIFT", "output")
        if mode != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT", "output")
        return
    _atomic_write(root, expected)


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
    except AttributionBuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        "ST-1303 attribution projection checked"
        if args.check
        else "ST-1303 attribution projection generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
