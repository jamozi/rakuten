#!/usr/bin/env python3
"""Build the deterministic, non-attesting ST-1803 local GATE-2 pack."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
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
            "ST1803_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python", file=sys.stderr
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1803_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.recorded_gate2_observation import (  # noqa: E402
    RecordedGate2ObservationAdapter,
)
from raos.application.analytics.gate2_observation import (  # noqa: E402
    RecordedGate2ObservationJob,
)
from raos.domain.analytics.gate2_observation import (  # noqa: E402
    Availability,
    FixtureByteLength,
    ObservationCommand,
    ObservationPeriod,
    PROGRAM,
    Sha256Digest,
)


CONTRACT_PATH: Final = Path("changes/st-1803/contracts/gate2-observation.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1803/fixtures/recorded-synthetic-gate2-observation.v1.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1803/generated/gate2-observation.local-blocked.v1.json"
)
README_PATH: Final = Path("changes/st-1803/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1803/PREFLIGHT.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1803/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1803_gate2_observation.py")
DOMAIN_PATH: Final = Path("python/raos/domain/analytics/gate2_observation.py")
PORT_PATH: Final = Path("python/raos/ports/gate2_observation.py")
APPLICATION_PATH: Final = Path("python/raos/application/analytics/gate2_observation.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_gate2_observation.py")

GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B "
    "scripts/build_st1803_gate2_observation.py"
)
CONTRACT_SHA256: Final = (
    "e85bfb0886be3f51ab99f81c6654efcdb88397cdfc43cc627ac984db2ee84e72"
)
FIXTURE_SHA256: Final = (
    "1a8fa35229d8f12bca5dc94de396175b5e97c359c775c50dd5b07671018f6c2e"
)
INPUT_SHA256: Final = "5dd59db906b6c3fbb234ec725fef375280f2b8234ceb94e339270b5abddb4e62"
SOURCE_HEAD_SHA256: Final = (
    "df9466fc8a3cca55fcd5c1a7b91ac1183663171c9100e350af9a46f59aa407c0"
)

EXPECTED_BINDINGS: Final = {
    "docs/upstream/key_documents/RAOS_01_requirements_purpose_success_v0.1.md": (
        "5890c616fdaaf02022a524c91b0ae91a8bf5c6b297338f8c958be0d49b3b62ea"
    ),
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": (
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
    ),
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml": (
        "f1cad721ade082f588461ff58c415fa21786e30b85c8281e651476514e2560a2"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "changes/st-1802/generated/gate1-decision.local-blocked.v1.json": (
        "338f677505780ea4f2e0f6ae085e0232728d0f2c708556885c0fb6546a3f6d78"
    ),
    "changes/st-1802/generated/runtime-manifest.v1.yaml": (
        "f6f75d503e509fccd5b2502008fcc29434400a2233f9405825469d81b006e785"
    ),
    "scripts/build_st1802_gate1_decision.py": (
        "0ae5aa8399db32e94f47ded65c5b8d91f7ef82e3f483c5d9e740cd61a8070e7e"
    ),
    "changes/st-1205/generated/kpi-read-model.v2.json": (
        "295ebe70efb63e67dba0e8e0c7026120c6d3577078d3991fdc7f7ddff99bceeb"
    ),
    "changes/st-1205/manifest.yaml": (
        "a1ee3011f7253787fe2b447572ba27a02c080d22d7d6b865a0cdf0c0f6167ebf"
    ),
    "python/raos/domain/analytics/kpi_read_model.py": (
        "7cc8ad6e10c61add95f3543605e1b1305762c20a691b4a05f9c070143f3101ac"
    ),
}

_MAX_READ_BYTES = 4 * 1024 * 1024
_STAGE_NAME = ".gate2-observation.local-blocked.v1.json.st1803.next"


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader, node: MappingNode, deep: bool = False
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
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _error(code: str, field: str) -> NoReturn:
    print(f"ST1803_ERROR code={code} field={field}", file=sys.stderr)
    raise SystemExit(1)


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
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _error("SOURCE_CHANGED", str(relative))
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _error("CONTRACT_INVALID", field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _error("CONTRACT_INVALID", field)
    return cast(Mapping[str, object], value)


def load_contract() -> Mapping[str, object]:
    content = _safe_read(CONTRACT_PATH)
    if _sha256(content) != CONTRACT_SHA256:
        _error("CONTRACT_HASH_DRIFT", str(CONTRACT_PATH))
    try:
        for token in yaml.scan(content.decode("utf-8", errors="strict")):
            if isinstance(token, (AliasToken, AnchorToken)):
                _error("CONTRACT_INVALID", "yaml.alias_or_anchor")
        loaded = yaml.load(content, Loader=_StrictLoader)
    except UnicodeDecodeError, yaml.YAMLError:
        _error("CONTRACT_INVALID", str(CONTRACT_PATH))
    contract = _mapping(loaded, "contract")
    document = _mapping(contract.get("document"), "document")
    if (
        document.get("story_id") != "ST-1803"
        or document.get("acceptance_criteria_satisfied") is not False
        or document.get("formal_verification") != "NOT_EXECUTED"
    ):
        _error("CONTRACT_INVALID", "document")
    observation = _mapping(contract.get("observation_contract"), "observation_contract")
    if (
        observation.get("program") != PROGRAM
        or observation.get("missing_is_zero") is not False
        or observation.get("zero_denominator") != "UNAVAILABLE"
        or observation.get("input_history") != "APPEND_ONLY_HASH_CHAIN"
        or observation.get("input_mutability") != "IMMUTABLE"
    ):
        _error("CONTRACT_INVALID", "observation_contract")
    gate = _mapping(contract.get("gate_2_definition"), "gate_2_definition")
    if (
        gate.get("gate_pass_automation") is not False
        or gate.get("recorded_synthetic_fixture_is_actual_observation") is not False
    ):
        _error("CONTRACT_INVALID", "gate_2_definition")
    improvement = _mapping(contract.get("improvement_contract"), "improvement_contract")
    for field in (
        "finance_or_reward_used_for_candidate_selection",
        "affiliate_rate_used_for_candidate_selection",
        "epc_used_for_candidate_selection",
        "rpm_used_for_candidate_selection",
        "profit_used_for_candidate_selection",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "automatic_publication",
    ):
        if improvement.get(field) is not False:
            _error("CONTRACT_INVALID", f"improvement_contract.{field}")
    return contract


def _validate_bindings(contract: Mapping[str, object]) -> list[dict[str, str]]:
    source_bindings = _mapping(contract.get("source_bindings"), "source_bindings")
    dependencies = _mapping(contract.get("dependency_bindings"), "dependency_bindings")
    flattened: dict[str, object] = dict(source_bindings)
    for story in ("ST-1802", "ST-1205"):
        flattened.update(
            _mapping(dependencies.get(story), f"dependency_bindings.{story}")
        )
    if flattened != EXPECTED_BINDINGS:
        _error("BINDING_CONTRACT_DRIFT", "bindings")
    rows: list[dict[str, str]] = []
    for path, expected in EXPECTED_BINDINGS.items():
        observed = _sha256(_safe_read(Path(path)))
        if observed != expected:
            _error("BOUND_SOURCE_HASH_DRIFT", path)
        rows.append({"sha256": observed, "uri": f"repo://{path}"})
    return rows


def _metric_map(report: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = report.get("metrics")
    if type(raw) is not list:
        _error("REPORT_INVALID", "metrics")
    rows: dict[str, Mapping[str, object]] = {}
    for candidate in cast(list[object], raw):
        row = _mapping(candidate, "metrics.row")
        metric_id = row.get("metric_id")
        if type(metric_id) is not str or metric_id in rows:
            _error("REPORT_INVALID", "metrics.metric_id")
        rows[metric_id] = row
    return rows


def _criterion(
    criterion_id: str,
    rule: str,
    *,
    status: str,
    observed_value: str,
    synthetic_threshold_relation: str = "NOT_APPLICABLE",
    references: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "criterion_id": criterion_id,
        "evidence_classification": (
            "RECORDED_SYNTHETIC_ONLY_NON_ATTESTING"
            if status == "INELIGIBLE_NON_ATTESTING"
            else "REQUIRED_EVIDENCE_ABSENT"
        ),
        "observed_value": observed_value,
        "rule": rule,
        "source_references": list(references),
        "status": status,
        "synthetic_threshold_relation": synthetic_threshold_relation,
    }


def _synthetic_criteria(report: Mapping[str, object]) -> list[dict[str, object]]:
    metrics = _metric_map(report)
    metric_rows = (
        (
            "G2-C01-OBSERVATION-DAYS",
            "OBSERVATION_DAYS_AT_LEAST_90",
            "observation_days",
            Decimal("90"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C02-QUALIFIED-SESSIONS",
            "QUALIFIED_ORGANIC_SESSIONS_REFERENCE_5000",
            "qualified_organic_sessions",
            Decimal("5000"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C03-VALID-INDEX",
            "VALID_INDEX_RATE_AT_LEAST_70_PERCENT",
            "indexed_article_rate",
            Decimal("0.70"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C04-IMPRESSION-COVERAGE",
            "INDEXED_ARTICLES_WITH_IMPRESSIONS_AT_LEAST_60_PERCENT",
            "impression_coverage_rate",
            Decimal("0.60"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C05-TOP20",
            "TOP20_ARTICLE_RATE_AT_LEAST_20_PERCENT",
            "top20_article_rate",
            Decimal("0.20"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C06-AFFILIATE-CTR",
            "AFFILIATE_OUTBOUND_CTR_AT_LEAST_5_PERCENT",
            "affiliate_click_rate",
            Decimal("0.05"),
            "MIN_INCLUSIVE",
        ),
        (
            "G2-C07-STALE-EXPOSURE",
            "STALE_EXPOSURE_RATE_STRICTLY_BELOW_2_PERCENT",
            "stale_exposure_rate",
            Decimal("0.02"),
            "MAX_STRICT",
        ),
        (
            "G2-C08-BROKEN-LINK",
            "BROKEN_AFFILIATE_LINK_RATE_STRICTLY_BELOW_0_5_PERCENT",
            "broken_affiliate_link_rate",
            Decimal("0.005"),
            "MAX_STRICT",
        ),
    )
    rows: list[dict[str, object]] = []
    for criterion_id, rule, metric_id, threshold, comparison in metric_rows:
        metric = metrics.get(metric_id)
        relation = "UNAVAILABLE"
        if metric is None or metric.get("availability") != Availability.AVAILABLE.value:
            observed = "UNAVAILABLE"
        else:
            value = metric.get("value")
            observed = value if type(value) is str else "UNAVAILABLE"
            if type(value) is str:
                parsed = Decimal(value)
                meets = (
                    parsed >= threshold
                    if comparison == "MIN_INCLUSIVE"
                    else parsed < threshold
                )
                relation = (
                    "MEETS_PROVISIONAL_THRESHOLD"
                    if meets
                    else "DOES_NOT_MEET_PROVISIONAL_THRESHOLD"
                )
        rows.append(
            _criterion(
                criterion_id,
                rule,
                status="INELIGIBLE_NON_ATTESTING",
                observed_value=observed,
                synthetic_threshold_relation=relation,
                references=(f"repo://{FIXTURE_PATH}",),
            )
        )
    return rows


def build_pack() -> dict[str, object]:
    contract = load_contract()
    bindings = _validate_bindings(contract)
    fixture = _safe_read(FIXTURE_PATH)
    if _sha256(fixture) != FIXTURE_SHA256:
        _error("FIXTURE_HASH_DRIFT", str(FIXTURE_PATH))
    command = ObservationCommand(
        recording_id="five-slot-complete",
        fixture_digest=Sha256Digest(FIXTURE_SHA256),
        fixture_length=FixtureByteLength(len(fixture)),
        contract_digest=Sha256Digest(CONTRACT_SHA256),
        expected_input_digest=Sha256Digest(INPUT_SHA256),
        period=ObservationPeriod(date(2026, 1, 1), date(2026, 4, 1), date(2026, 4, 1)),
        program_id=PROGRAM,
    )
    report = (
        RecordedGate2ObservationJob(exchange=RecordedGate2ObservationAdapter(fixture))
        .observe(command)
        .payload()
    )
    if report.get("source_head_sha256") != SOURCE_HEAD_SHA256:
        _error("REPORT_INVALID", "source_head_sha256")
    criteria = _synthetic_criteria(report)
    criteria.extend(
        (
            _criterion(
                "G2-C09-MAJOR-PAGES-RECOGNIZED",
                "MAJOR_PAGE_GROUP_RECOGNIZED_WITH_SUFFICIENT_HUMAN_JUDGMENT",
                status="UNAVAILABLE",
                observed_value="UNAVAILABLE",
            ),
            _criterion(
                "G2-C10-CRITICAL-COMPLAINTS",
                "CRITICAL_USER_COMPLAINTS_EQUAL_0",
                status="INELIGIBLE_NON_ATTESTING",
                observed_value="0",
                synthetic_threshold_relation="MEETS_PROVISIONAL_THRESHOLD",
                references=(f"repo://{FIXTURE_PATH}",),
            ),
            _criterion(
                "G2-C11-LOW-VALUE-CONSOLIDATION",
                "LOW_VALUE_AND_CANNIBALIZATION_CONSOLIDATION_OPERATIONAL",
                status="UNAVAILABLE",
                observed_value="UNAVAILABLE",
            ),
            _criterion(
                "G2-C12-DIRECT-VISIT-QUALITY",
                "CONTENT_QUALITY_SUPPORTS_DIRECT_VISITS",
                status="UNAVAILABLE",
                observed_value="UNAVAILABLE",
            ),
            _criterion(
                "G2-C13-GATE1-PREREQUISITE",
                "GATE1_ACTUALLY_PASSED",
                status="BLOCKED",
                observed_value="ST1802_BLOCKED_NOT_ELIGIBLE",
                references=(
                    "repo://changes/st-1802/generated/gate1-decision.local-blocked.v1.json",
                ),
            ),
            _criterion(
                "G2-C14-ACTUAL-OBSERVATION",
                "ACTUAL_30_TO_45_ARTICLE_OBSERVATION_PERIOD_PRESENT",
                status="NOT_EXECUTED",
                observed_value="NOT_EXECUTED",
            ),
            _criterion(
                "G2-C15-FORMAL-TST030",
                "FORMAL_TST030_RECONCILIATION_COMPLETE",
                status="NOT_EXECUTED",
                observed_value="NOT_EXECUTED",
            ),
            _criterion(
                "G2-C16-FORMAL-TST032",
                "FORMAL_TST032_GATE_PACK_EXECUTED_IN_STAGING",
                status="NOT_EXECUTED",
                observed_value="NOT_EXECUTED",
            ),
            _criterion(
                "G2-C17-HUMAN-APPROVAL",
                "PRODUCT_OWNER_GATE_APPROVAL_PRESENT",
                status="UNAVAILABLE",
                observed_value="UNAVAILABLE",
            ),
        )
    )
    return {
        "acceptance_criteria_satisfied": False,
        "actual_observations": [],
        "authority": {
            "formal_evidence_acceptance": "NONE",
            "gate_approval": "NONE",
            "publication": "NONE",
            "status_apply": "NONE",
        },
        "classification": "LOCAL_BLOCKED_RECORDED_SYNTHETIC_GATE2_NON_ATTESTING",
        "dependency_state": {
            "ST-1205": "LOCAL_RECORDED_KPI_RUNTIME_BOUND",
            "ST-1802": "BLOCKED_NOT_ELIGIBLE",
        },
        "data_quality": {
            "actual_provider_reconciliation": "NOT_EXECUTED",
            "append_only_hash_chain": "LOCAL_SYNTHETIC_PASS",
            "exact_five_slots": "LOCAL_SYNTHETIC_PASS",
            "exact_program": "LOCAL_SYNTHETIC_PASS",
            "one_exact_period": "LOCAL_SYNTHETIC_PASS",
            "reward_conservation": _mapping(
                report["finance_separation"], "finance_separation"
            )["reward_conservation"],
            "source_and_verification_contract": "LOCAL_SYNTHETIC_PASS",
            "synthetic_is_actual_observation": False,
        },
        "gate_definition": contract["gate_2_definition"],
        "gate_pass_claim": False,
        "generated_by": {
            "command": GENERATION_COMMAND,
            "generator_sha256": _sha256(_safe_read(GENERATOR_PATH)),
            "uri": f"repo://{GENERATOR_PATH}",
        },
        "mandatory_criteria": criteria,
        "overall": "BLOCKED",
        "recorded_synthetic_harness": report,
        "schema": "ST1803_GATE2_PACK_V1",
        "source_bindings": bindings,
        "story_id": "ST-1803",
        "verification": {
            "actual_30_45_article_observation": "NOT_EXECUTED",
            "formal_TST-030": "NOT_EXECUTED",
            "formal_TST-032": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
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
            directory, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
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
        print("ST1803_CHECK_OK")
    else:
        _atomic_write(expected)
        print(f"ST1803_GENERATED path={OUTPUT_PATH} sha256={_sha256(expected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ADAPTER_PATH",
    "APPLICATION_PATH",
    "CONTRACT_PATH",
    "DOMAIN_PATH",
    "FIXTURE_PATH",
    "GENERATOR_PATH",
    "OUTPUT_PATH",
    "PORT_PATH",
    "build_pack",
    "load_contract",
    "main",
    "render_pack",
]
