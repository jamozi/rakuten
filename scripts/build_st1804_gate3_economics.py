#!/usr/bin/env python3
"""Build the deterministic, non-attesting ST-1804 local GATE-3 pack."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print(
            "ST1804_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1804_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.recorded_gate3_economics import (  # noqa: E402
    RecordedGate3EconomicsAdapter,
)
from raos.application.analytics.gate3_economics import (  # noqa: E402
    RecordedGate3EconomicsJob,
)
from raos.domain.analytics.gate3_economics import (  # noqa: E402
    FINANCE_EDITORIAL_INPUTS_FORBIDDEN,
    FixtureByteLength,
    Gate3Command,
    PROGRAM,
    Sha256Digest,
)


CONTRACT_PATH: Final = Path("changes/st-1804/contracts/gate3-economics.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1804/fixtures/recorded-synthetic-gate3-economics.v1.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1804/generated/gate3-economics.local-blocked.v1.json"
)
README_PATH: Final = Path("changes/st-1804/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1804/PREFLIGHT.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1804/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1804_gate3_economics.py")
DOMAIN_PATH: Final = Path("python/raos/domain/analytics/gate3_economics.py")
PORT_PATH: Final = Path("python/raos/ports/gate3_economics.py")
APPLICATION_PATH: Final = Path("python/raos/application/analytics/gate3_economics.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_gate3_economics.py")

ST1803_OUTPUT_PATH: Final = Path(
    "changes/st-1803/generated/gate2-observation.local-blocked.v1.json"
)
ST1305_OUTPUT_PATH: Final = Path(
    "changes/st-1305/generated/finance-reconciliation-recorded.v2.json"
)

GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B "
    "scripts/build_st1804_gate3_economics.py"
)
CONTRACT_SHA256: Final = (
    "46075d28770e5128b184c3a2ca8089d92ee066fbafe0d29322cdd6ccb293bd9b"
)
FIXTURE_SHA256: Final = (
    "a31852950e1ffa602cfd272945e08874597c7143ccd0dd0f4c1a44a1cf9a297a"
)
INPUT_SHA256: Final = "a532e84c3be3d656978a8168047a8e4df94c872fd78d703137f399c77e0199b2"
SOURCE_HEAD_SHA256: Final = (
    "cf99243c2652e523afe8664ce0608d19260e8d218557f641768a6a769862ca17"
)

EXPECTED_BINDINGS: Final = {
    "docs/upstream/key_documents/RAOS_01_requirements_purpose_success_v0.1.md": (
        "5890c616fdaaf02022a524c91b0ae91a8bf5c6b297338f8c958be0d49b3b62ea"
    ),
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": (
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
    ),
    "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml": (
        "29624996381ff0709c6499edcdca1109eb713ce56ad8b981df02153e11fc8b0c"
    ),
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml": (
        "f1cad721ade082f588461ff58c415fa21786e30b85c8281e651476514e2560a2"
    ),
    "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml": (
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "changes/st-1803/contracts/gate2-observation.v1.yaml": (
        "4e494e2e974f2aa7b6e0d623f0bc038d7be3a65d8108e3edaf86c2c5b30e8714"
    ),
    "changes/st-1803/fixtures/recorded-synthetic-gate2-observation.v1.json": (
        "3e61f2cd73c6fcb46010a5573bfa6c0ed770b3e47964112f8e430bc2b43d28ce"
    ),
    "changes/st-1803/generated/gate2-observation.local-blocked.v1.json": (
        "9b4574559aafb7fa5db85a8ba86122bcd20c2eff798be935717382b54223d1c3"
    ),
    "scripts/build_st1803_gate2_observation.py": (
        "afcd368a4e4cf4badce2bb05cecc02b801b6b0606dbdaff5bf0cde64b5cd42dc"
    ),
    "changes/st-1305/contracts/finance-reconciliation-runtime.v2.yaml": (
        "3a654c9ebd8184a8f23d563dbed789cd1743a1a34437dcd0423963d58ba7242d"
    ),
    "changes/st-1305/fixtures/finance-reconciliation-recorded.synthetic.v2.json": (
        "59b666012081afc238b331dc481a48bf9ba91c54ee00756f0a0a7687b98deb09"
    ),
    "changes/st-1305/generated/finance-reconciliation-recorded.v2.json": (
        "565f9999a0a8b990399d439b7f8651819e1e9fcb96fbae96ecfb739ebdb8de0c"
    ),
    "changes/st-1305/manifest.yaml": (
        "e6e191060b4ce0e36d3416efdc0c2ca8615e626762dc3dc01a2354fe70a57974"
    ),
    "scripts/build_st1305_finance_reconciliation.py": (
        "215f8aac3529ce713a08af2195de8295fa62b884d3003245a89b818189df5502"
    ),
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json": (
        "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8"
    ),
}

_MAX_READ_BYTES = 4 * 1024 * 1024
_STAGE_NAME = ".gate3-economics.local-blocked.v1.json.st1804.next"


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "duplicate key",
                    key_node.start_mark,
                )
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from exc
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _error(code: str, field: str) -> NoReturn:
    print(f"ST1804_ERROR code={code} field={field}", file=sys.stderr)
    raise SystemExit(1)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_read(relative: Path, *, maximum: int = _MAX_READ_BYTES) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        _error("PATH_INVALID", str(relative))
    current = REPO_ROOT
    for component in relative.parts[:-1]:
        current /= component
        try:
            observed = os.lstat(current)
        except OSError:
            _error("SOURCE_UNAVAILABLE", str(relative))
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            _error("SOURCE_PATH_UNSAFE", str(relative))
    target = REPO_ROOT / relative
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        _error("SOURCE_UNAVAILABLE", str(relative))
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= maximum
        ):
            _error("SOURCE_FILE_UNSAFE", str(relative))
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                _error("SOURCE_SHORT_READ", str(relative))
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _error("SOURCE_CHANGED", str(relative))
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _error("SOURCE_CHANGED", str(relative))
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict or any(
        type(key) is not str for key in cast(dict[object, object], value)
    ):
        _error("DOCUMENT_INVALID", field)
    return cast(Mapping[str, object], value)


def _strict_yaml(content: bytes, field: str) -> Mapping[str, object]:
    try:
        text = content.decode("utf-8", errors="strict")
        tokens = tuple(yaml.scan(text))
        if any(isinstance(token, (AnchorToken, AliasToken)) for token in tokens):
            _error("YAML_REFERENCE_FORBIDDEN", field)
        document = yaml.load(text, Loader=_StrictLoader)
    except UnicodeDecodeError, yaml.YAMLError:
        _error("YAML_INVALID", field)
    return _mapping(document, field)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            _error("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _strict_json(content: bytes, field: str) -> Mapping[str, object]:
    try:
        document = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _error("JSON_NUMBER_INVALID", field),
            parse_float=lambda _: _error("JSON_NUMBER_INVALID", field),
        )
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        _error("JSON_INVALID", field)
    return _mapping(document, field)


def _flatten_bindings(contract: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path, digest in _mapping(
        contract.get("source_bindings"), "source_bindings"
    ).items():
        if type(digest) is not str:
            _error("BINDING_INVALID", path)
        result[path] = digest
    for story, entries in _mapping(
        contract.get("dependency_bindings"), "dependency_bindings"
    ).items():
        for path, digest in _mapping(entries, f"dependency_bindings.{story}").items():
            if type(digest) is not str:
                _error("BINDING_INVALID", path)
            result[path] = digest
    return result


def load_contract() -> Mapping[str, object]:
    content = _safe_read(CONTRACT_PATH)
    if _sha256(content) != CONTRACT_SHA256:
        _error("CONTRACT_HASH_DRIFT", str(CONTRACT_PATH))
    contract = _strict_yaml(content, str(CONTRACT_PATH))
    document = _mapping(contract.get("document"), "document")
    if (
        document.get("story_id") != "ST-1804"
        or document.get("version") != "1.0.0"
        or document.get("acceptance_criteria_satisfied") is not False
        or document.get("formal_verification") != "NOT_EXECUTED"
    ):
        _error("CONTRACT_DOCUMENT_INVALID", "document")
    bindings = _flatten_bindings(contract)
    if bindings != EXPECTED_BINDINGS:
        _error("BINDING_SET_DRIFT", "source_bindings")
    for path, expected in bindings.items():
        if _sha256(_safe_read(Path(path))) != expected:
            _error("DEPENDENCY_HASH_DRIFT", path)
    return contract


def _load_story() -> Mapping[str, object]:
    backlog = _strict_yaml(
        _safe_read(Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")),
        "canonical_story",
    )
    stories = backlog.get("stories")
    if type(stories) is not list:
        _error("STORY_CATALOG_INVALID", "stories")
    for item in cast(list[object], stories):
        row = _mapping(item, "story")
        if row.get("id") == "ST-1804":
            if (
                row.get("objective") != "確定成果/費用/利益を評価"
                or row.get("depends_on") != ["ST-1803", "ST-1305"]
                or row.get("deliverables") != ["GATE-3 pack"]
                or row.get("acceptance_criteria")
                != ["confirmed basis and no false attribution"]
                or row.get("test_suites") != ["TST-030", "TST-032"]
            ):
                _error("STORY_DRIFT", "ST-1804")
            return row
    _error("STORY_MISSING", "ST-1804")


def _validate_dependencies() -> tuple[Mapping[str, object], Mapping[str, object]]:
    gate2 = _strict_json(_safe_read(ST1803_OUTPUT_PATH), "ST-1803")
    if (
        gate2.get("schema") != "ST1803_GATE2_PACK_V1"
        or gate2.get("overall") != "BLOCKED"
        or gate2.get("gate_pass_claim") is not False
        or gate2.get("actual_observations") != []
    ):
        _error("ST1803_BOUNDARY_DRIFT", "ST-1803")
    harness = _mapping(gate2.get("recorded_synthetic_harness"), "ST-1803.harness")
    if harness.get("synthetic") is not True or harness.get("program") != PROGRAM:
        _error("ST1803_HARNESS_DRIFT", "ST-1803.harness")

    finance = _strict_json(_safe_read(ST1305_OUTPUT_PATH), "ST-1305")
    document = _mapping(finance.get("document"), "ST-1305.document")
    report = _mapping(finance.get("recorded_report"), "ST-1305.recorded_report")
    if (
        document.get("story_id") != "ST-1305"
        or document.get("authority") != "RECORDED_SYNTHETIC_ONLY"
        or report.get("availability") != "PARTIAL"
    ):
        _error("ST1305_BOUNDARY_DRIFT", "ST-1305")
    policy = _mapping(
        report.get("recommendation_input_policy"),
        "ST-1305.recommendation_input_policy",
    )
    if (
        policy.get("all_finance_values_excluded") is not True
        or tuple(cast(list[object], policy.get("excluded")))
        != FINANCE_EDITORIAL_INPUTS_FORBIDDEN
        or any(
            policy.get(key) is not False
            for key in (
                "finance_may_change_article_html",
                "finance_may_change_cta",
                "finance_may_change_product_selection",
                "finance_may_change_publication_snapshot",
                "finance_may_change_recommendation_order",
            )
        )
    ):
        _error("ST1305_EDITORIAL_BOUNDARY_DRIFT", "ST-1305")
    learning = _mapping(report.get("learning_report"), "ST-1305.learning_report")
    if learning.get("output_kind") != "REVIEW_CANDIDATES_ONLY":
        _error("ST1305_LEARNING_BOUNDARY_DRIFT", "ST-1305")
    return gate2, finance


def _source_artifact(path: Path) -> dict[str, object]:
    content = _safe_read(path)
    return {
        "bytes": len(content),
        "sha256": _sha256(content),
        "uri": f"repo://{path}",
    }


def build_pack() -> dict[str, object]:
    contract = load_contract()
    _load_story()
    gate2, finance = _validate_dependencies()
    fixture = _safe_read(FIXTURE_PATH, maximum=1024 * 1024)
    if _sha256(fixture) != FIXTURE_SHA256:
        _error("FIXTURE_HASH_DRIFT", str(FIXTURE_PATH))
    command = Gate3Command(
        recording_id="three-month-synthetic-threshold-vector",
        fixture_digest=Sha256Digest(FIXTURE_SHA256),
        fixture_length=FixtureByteLength(len(fixture)),
        contract_digest=Sha256Digest(CONTRACT_SHA256),
        expected_input_digest=Sha256Digest(INPUT_SHA256),
        program_id=PROGRAM,
    )
    report = RecordedGate3EconomicsJob(
        exchange=RecordedGate3EconomicsAdapter(fixture)
    ).evaluate(command)
    if report.source_head_sha256.value != SOURCE_HEAD_SHA256:
        _error("SOURCE_HEAD_DRIFT", "fixture.entries")

    gate2_harness = _mapping(gate2.get("recorded_synthetic_harness"), "ST-1803.harness")
    gate2_period = _mapping(gate2_harness.get("period"), "ST-1803.period")
    measurement = _mapping(
        finance.get("measurement_boundary"), "ST-1305.measurement_boundary"
    )
    finance_period = _mapping(measurement.get("period"), "ST-1305.period")
    finance_report = _mapping(finance.get("recorded_report"), "ST-1305.recorded_report")
    learning = _mapping(
        finance_report.get("learning_report"), "ST-1305.learning_report"
    )
    candidates = learning.get("candidates")
    if type(candidates) is not list:
        _error("ST1305_LEARNING_BOUNDARY_DRIFT", "candidates")

    source_paths = (
        CONTRACT_PATH,
        FIXTURE_PATH,
        PREFLIGHT_PATH,
        README_PATH,
        DOMAIN_PATH,
        PORT_PATH,
        APPLICATION_PATH,
        ADAPTER_PATH,
        GENERATOR_PATH,
    )
    synthetic_report = report.payload()
    criteria = list(cast(list[object], synthetic_report["criteria"]))
    criteria.extend(
        [
            {
                "criterion_id": "G3-X01",
                "description": "actual 30-45 article observation present",
                "status": "NOT_EXECUTED",
            },
            {
                "criterion_id": "G3-X02",
                "description": "real provider report reconciled",
                "status": "NOT_EXECUTED_OD_003",
            },
            {
                "criterion_id": "G3-X03",
                "description": "approved labor basis present",
                "status": "UNAVAILABLE_OD_005",
            },
            {
                "criterion_id": "G3-X04",
                "description": "formal TST-030 complete",
                "status": "NOT_EXECUTED",
            },
            {
                "criterion_id": "G3-X05",
                "description": "formal TST-032 staging pack complete",
                "status": "NOT_EXECUTED",
            },
            {
                "criterion_id": "G3-X06",
                "description": "Product Owner Gate approval present",
                "status": "UNAVAILABLE",
            },
        ]
    )
    return {
        "acceptance_criteria_satisfied": False,
        "actual_observations": [],
        "authority": {
            "editorial_mutation": "NONE",
            "formal_evidence_acceptance": "NONE",
            "gate_approval": "NONE",
            "publication": "NONE",
            "scale": "NONE",
            "status_apply": "NONE",
        },
        "classification": "LOCAL_BLOCKED_RECORDED_SYNTHETIC_GATE3_NON_ATTESTING",
        "completion_boundary": {
            "canonical_status_changed": False,
            "formal_or_live_evidence_claimed": False,
            "local_code_complete": True,
            "local_integration_complete": False,
        },
        "confirmed_basis": {
            "actual_confirmed_profit_eligible": False,
            "direct_estimated_unattributed_separate": True,
            "provider_report_status": "SYNTHETIC_ONLY_REAL_REPORT_UNAVAILABLE_OD_003",
            "reconciliation_availability": finance_report["availability"],
            "unattributed_reward_allocated_to_articles": False,
        },
        "dependency_alignment": {
            "actual_gate_input_eligible": False,
            "period_alignment": "MISMATCH_RECORDED_SYNTHETIC_DEPENDENCIES",
            "program_alignment": (
                "MATCHED_FIXED_PROGRAM"
                if gate2_harness.get("program") == measurement.get("program") == PROGRAM
                else "MISMATCH"
            ),
            "ST-1803": {
                "overall": gate2["overall"],
                "period": dict(gate2_period),
                "synthetic": True,
            },
            "ST-1305": {
                "period": dict(finance_period),
                "reconciliation_availability": finance_report["availability"],
                "result_sha256": finance_report["result_sha256"],
                "synthetic": True,
            },
        },
        "gate_definition": contract["gate_3_definition"],
        "gate_pass_claim": False,
        "generated_by": {
            "command": GENERATION_COMMAND,
            "generator_sha256": _sha256(_safe_read(GENERATOR_PATH)),
            "uri": f"repo://{GENERATOR_PATH}",
        },
        "learning_boundary": {
            "candidate_count": len(candidates),
            "candidate_output_kind": learning["output_kind"],
            "finance_signals_excluded": learning["finance_signals_excluded"],
            "finance_used_for_product_or_recommendation_ranking": False,
            "modifications_applied": [],
            "source_result_sha256": finance_report["result_sha256"],
        },
        "mandatory_criteria": criteria,
        "overall": "BLOCKED",
        "provenance": {
            "dependency_bindings": _flatten_bindings(contract),
            "fixture_sha256": FIXTURE_SHA256,
            "source_artifacts": [_source_artifact(path) for path in source_paths],
        },
        "recorded_synthetic_evaluation": synthetic_report,
        "scale_authority": "NONE",
        "schema": "ST1804_GATE3_PACK_V1",
        "story_id": "ST-1804",
        "verification": {
            "actual_30_45_article_pilot": "NOT_EXECUTED",
            "actual_gate2_observation": "NOT_EXECUTED",
            "actual_gate3_observation": "NOT_EXECUTED",
            "formal_TST-030": "NOT_EXECUTED",
            "formal_TST-032": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
    }


def render_pack() -> bytes:
    return (
        json.dumps(
            build_pack(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(content: bytes) -> None:
    directory = REPO_ROOT / OUTPUT_PATH.parent
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError:
        _error("OUTPUT_DIRECTORY_UNSAFE", str(OUTPUT_PATH.parent))
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        try:
            staged = os.stat(_STAGE_NAME, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            _error("OUTPUT_STAGE_UNSAFE", _STAGE_NAME)
        else:
            if not stat.S_ISREG(staged.st_mode) or staged.st_uid != os.geteuid():
                _error("OUTPUT_STAGE_UNSAFE", _STAGE_NAME)
            os.unlink(_STAGE_NAME, dir_fd=directory_fd)
        try:
            stage_fd = os.open(
                _STAGE_NAME,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        except OSError:
            _error("OUTPUT_STAGE_CREATE_FAILED", _STAGE_NAME)
        try:
            offset = 0
            while offset < len(content):
                written = os.write(stage_fd, content[offset:])
                if written <= 0:
                    _error("OUTPUT_STAGE_WRITE_FAILED", _STAGE_NAME)
                offset += written
            os.fsync(stage_fd)
            os.fchmod(stage_fd, 0o644)
            os.fsync(stage_fd)
        finally:
            os.close(stage_fd)
        os.replace(
            _STAGE_NAME,
            OUTPUT_PATH.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _check(expected: bytes) -> None:
    try:
        observed = _safe_read(OUTPUT_PATH)
    except SystemExit:
        _error("GENERATED_OUTPUT_MISSING", str(OUTPUT_PATH))
    if observed != expected:
        _error("GENERATED_OUTPUT_DRIFT", str(OUTPUT_PATH))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render_pack()
    if args.check:
        _check(expected)
        print("ST1804_CHECK_OK")
    else:
        _atomic_write(expected)
        print(f"ST1804_GENERATED path={OUTPUT_PATH} sha256={_sha256(expected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ADAPTER_PATH",
    "APPLICATION_PATH",
    "COMPLETION_PATH",
    "CONTRACT_PATH",
    "DOMAIN_PATH",
    "FIXTURE_PATH",
    "GENERATOR_PATH",
    "OUTPUT_PATH",
    "PORT_PATH",
    "PREFLIGHT_PATH",
    "README_PATH",
    "build_pack",
    "load_contract",
    "main",
    "render_pack",
]
