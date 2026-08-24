#!/usr/bin/env python3
# ST-1906 owner generator; generated artifacts must not be hand-edited.
"""Build the disabled recorded aggregate causal-attribution artifacts."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for _import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from raos.adapters.recorded_causal_attribution import (  # noqa: E402
    RecordedCausalAttributionSource,
)
from raos.application.analytics.causal_attribution import (  # noqa: E402
    CausalAttributionEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.analytics.causal_attribution import (  # noqa: E402
    CAUSAL_METHOD_VERSION,
    CausalAttributionCommand,
    CausalAttributionScope,
    CausalAvailability,
    PrivacyReviewEvidence,
    PrivacyReviewStatus,
    canonical_json_bytes,
    digest_bytes,
)
from raos.domain.finance.attribution import (  # noqa: E402
    ContractArticle,
    MeasurementAttributionContract,
    MeasurementPeriod,
)
from raos.domain.ops.object_intake import Sha256Digest  # noqa: E402
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1906/contracts/advanced-causal-attribution.v1.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1906/fixtures/recorded/causal-attribution.synthetic.v1.json"
)
REPORT_PATH: Final = Path("changes/st-1906/generated/causal-attribution-report.v1.json")
MANIFEST_PATH: Final = Path("changes/st-1906/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1906_advanced_causal_attribution.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
BASE_COMMIT: Final = "6b89b412ea061af36544cce817ecede4cce7d457"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1906/README.md"),
    Path("changes/st-1906/completion/completion.v1.yaml"),
    Path("docs/worklogs/ST-1906.md"),
    Path("python/raos/domain/analytics/causal_attribution.py"),
    Path("python/raos/ports/causal_attribution.py"),
    Path("python/raos/application/analytics/causal_attribution.py"),
    Path("python/raos/adapters/recorded_causal_attribution.py"),
    GENERATOR_PATH,
    HELPER_PATH,
    Path("tests/st1906/__init__.py"),
    Path("tests/st1906/conftest.py"),
    Path("tests/st1906/support.py"),
    Path("tests/st1906/test_contract.py"),
    Path("tests/st1906/test_generation.py"),
    Path("tests/st1906/test_causal_service.py"),
    Path("tests/st1906/test_unavailable_cases.py"),
    Path("tests/st1906/test_negative_cases.py"),
)

EXPECTED_DOCUMENT: Final = {
    "schema_version": "1.0.0",
    "story_id": "ST-1906",
    "classification": (
        "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_AGGREGATE_CAUSAL_ATTRIBUTION_V1"
    ),
    "status": "LOCAL_IMPLEMENTATION_COMPLETE",
    "mvp": False,
    "canonical_implementation_status": "DEFERRED_POST_MVP",
    "canonical_status_changed": False,
    "formal_validation": "NOT_EXECUTED",
    "authority": "NONE",
    "production_eligible": False,
}


class CausalAttributionBuildError(RuntimeError):
    """Closed owner-generation failure without source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1906_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1906_BUILD_FAILED") -> NoReturn:
    raise CausalAttributionBuildError(code) from None


def sha256_bytes(content: bytes) -> str:
    if type(content) is not bytes:
        _fail("HASH_INPUT_INVALID")
    return hashlib.sha256(content).hexdigest()


def _repository_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("FILE_BOUNDARY_VIOLATION")
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
    except ValueError:
        _fail("FILE_BOUNDARY_VIOLATION")
    return candidate


def _read(root: Path, relative: Path) -> bytes:
    path = _repository_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail("FILE_BOUNDARY_VIOLATION")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            expected = (before.st_dev, before.st_ino, before.st_size)
            if (opened.st_dev, opened.st_ino, opened.st_size) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail("FILE_BOUNDARY_VIOLATION")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("FILE_BOUNDARY_VIOLATION")
            after = os.fstat(descriptor)
            named = path.lstat()
            if (after.st_dev, after.st_ino, after.st_size) != expected or (
                named.st_dev,
                named.st_ino,
                named.st_size,
            ) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except CausalAttributionBuildError:
        raise
    except Exception:
        _fail("FILE_BOUNDARY_VIOLATION")


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            _fail("YAML_DUPLICATE_OR_NONSTRING_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _parse_yaml(content: bytes) -> dict[str, Any]:
    if type(content) is not bytes or not content or len(content) > MAX_SOURCE_BYTES:
        _fail("YAML_INVALID")
    try:
        text = content.decode("utf-8", errors="strict")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_COMPLEXITY_FORBIDDEN")
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except CausalAttributionBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID")
    if type(loaded) is not dict:
        _fail("YAML_INVALID")
    return cast(dict[str, Any], loaded)


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _fail("JSON_INVALID")
        result[key] = value
    return result


def _reject_json_number(value: str) -> NoReturn:
    del value
    _fail("JSON_INVALID")


def _parse_json(content: bytes) -> dict[str, Any]:
    if type(content) is not bytes or not content or len(content) > MAX_SOURCE_BYTES:
        _fail("JSON_INVALID")
    try:
        loaded = json.loads(
            content,
            object_pairs_hook=_pairs,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except CausalAttributionBuildError:
        raise
    except Exception:
        _fail("JSON_INVALID")
    if type(loaded) is not dict or canonical_json_bytes(loaded) + b"\n" != content:
        _fail("JSON_INVALID")
    return cast(dict[str, Any], loaded)


def _mapping(value: object, code: str = "CONTRACT_INVALID") -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail(code)
    return cast(dict[str, Any], value)


def _rows(value: object, code: str = "AUTHORITY_SEMANTIC_DRIFT") -> list[Any]:
    if type(value) is not list or len(value) > 10_000:
        _fail(code)
    return value


def _find(rows: object, record_id: str) -> dict[str, Any]:
    matches = [
        _mapping(row, "AUTHORITY_SEMANTIC_DRIFT")
        for row in _rows(rows)
        if isinstance(row, Mapping) and row.get("id") == record_id
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_SEMANTIC_DRIFT")
    return matches[0]


def _digest(value: object) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        _fail("CONTRACT_DIGEST_INVALID")
    return value


def _path(value: object) -> Path:
    if type(value) is not str or not value or "\\" in value:
        _fail("CONTRACT_PATH_INVALID")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail("CONTRACT_PATH_INVALID")
    return path


def _validate_hash_binding(
    root: Path,
    binding: object,
    code: str = "AUTHORITY_DIGEST_DRIFT",
) -> tuple[Path, str]:
    row = _mapping(binding)
    if not {"path", "sha256"}.issubset(row):
        _fail("CONTRACT_INVALID")
    relative = _path(row.get("path"))
    digest = _digest(row.get("sha256"))
    if sha256_bytes(_read(root, relative)) != digest:
        _fail(code)
    return relative, digest


_AUTHORITY_KEYS: Final = (
    "integration_precedence",
    "canonical_decisions",
    "open_decisions",
    "canonical_story",
    "analytics_design",
    "attribution_policy",
    "test_acceptance_design",
    "test_catalog",
    "security_design",
    "data_classification",
    "security_controls",
    "threat_register",
)


def _validate_authority(root: Path, contract: dict[str, Any]) -> None:
    if _mapping(contract.get("document")) != EXPECTED_DOCUMENT:
        _fail("CONTRACT_BOUNDARY_DRIFT")
    authority = _mapping(contract.get("authority"))
    paths: dict[str, Path] = {}
    for key in _AUTHORITY_KEYS:
        paths[key], _ = _validate_hash_binding(root, authority.get(key))

    story = _find(
        _parse_yaml(_read(root, paths["canonical_story"])).get("stories"),
        "ST-1906",
    )
    if (
        story.get("depends_on") != ["ST-1303"]
        or story.get("test_suites") != ["TST-032"]
        or story.get("mvp") is not False
        or story.get("implementation_status") != "DEFERRED_POST_MVP"
        or story.get("acceptance_criteria") != ["separate release decision required"]
    ):
        _fail("STORY_SEMANTIC_DRIFT")

    open_decisions = _parse_yaml(_read(root, paths["open_decisions"]))
    privacy = _find(open_decisions.get("items"), "OD-012")
    retention = _find(open_decisions.get("items"), "OD-014")
    if (
        privacy.get("status") != "HUMAN_DECISION_REQUIRED"
        or privacy.get("blocking") is not True
        or retention.get("status") != "HUMAN_DECISION_REQUIRED"
        or retention.get("blocking") is not True
        or authority["open_decisions"].get("resolved_by_this_story") is not False
    ):
        _fail("OPEN_DECISION_SEMANTIC_DRIFT")

    suite = _find(
        _parse_yaml(_read(root, paths["test_catalog"])).get("suites"),
        "TST-032",
    )
    if (
        suite.get("environments") != ["staging"]
        or suite.get("execution_status") != "NOT_EXECUTED"
        or suite.get("release_blocking") is not True
    ):
        _fail("TEST_BOUNDARY_DRIFT")

    controls = {
        row.get("id")
        for row in _rows(
            _parse_yaml(_read(root, paths["security_controls"])).get("controls")
        )
        if isinstance(row, Mapping)
    }
    expected_controls = set(authority["security_controls"].get("controls", []))
    threats = {
        row.get("id")
        for row in _rows(
            _parse_yaml(_read(root, paths["threat_register"])).get("threats")
        )
        if isinstance(row, Mapping)
    }
    expected_threats = set(authority["threat_register"].get("threats", []))
    if (
        expected_controls
        != {
            "SEC-GOV-006",
            "SEC-APP-001",
            "SEC-DATA-003",
            "SEC-DATA-004",
            "SEC-DATA-007",
            "SEC-DATA-008",
            "SEC-SDLC-006",
            "SEC-SDLC-009",
        }
        or not expected_controls.issubset(controls)
        or expected_threats != {"THR-010", "THR-014", "THR-019", "THR-020", "THR-025"}
        or not expected_threats.issubset(threats)
    ):
        _fail("SECURITY_BOUNDARY_DRIFT")


def _validate_predecessor(root: Path, contract: dict[str, Any]) -> None:
    predecessor = _mapping(contract.get("predecessor"))
    if (
        predecessor.get("story_id") != "ST-1303"
        or predecessor.get("binding") != "EXACT_BASE_COMMIT_BYTES"
        or predecessor.get("base_commit") != BASE_COMMIT
    ):
        _fail("PREDECESSOR_BOUNDARY_DRIFT")
    artifacts = _mapping(predecessor.get("artifacts"))
    if len(artifacts) != 8:
        _fail("PREDECESSOR_BOUNDARY_DRIFT")
    for raw_path, raw_digest in artifacts.items():
        relative = _path(raw_path)
        expected = _digest(raw_digest)
        if sha256_bytes(_read(root, relative)) != expected:
            _fail("PREDECESSOR_DIGEST_DRIFT")
    semantics = _mapping(predecessor.get("required_semantics"))
    if semantics != {
        "five_slot_contract": True,
        "fixed_program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE",
        "period_duration_days": 14,
        "provider_fact_immutable": True,
        "direct_estimated_unattributed_separate": True,
        "unavailable_not_zero": True,
        "arbitrary_total_allocation": False,
        "finance_to_recommendation": False,
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT")


def _validate_safe_boundary(contract: dict[str, Any]) -> None:
    feature = _mapping(contract.get("feature_scope"))
    if (
        feature.get("default") != "DISABLED"
        or feature.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY"]
        or feature.get("live_enabled_state_exists") is not False
        or feature.get("activation_interface_exists") is not False
        or feature.get("disabled_fails_before_port_call") is not True
        or feature.get("executable_environments") != ["ENV-DEV", "ENV-CI"]
        or feature.get("provider_neutral") is not True
        or feature.get("caller_bytes_only") is not True
    ):
        _fail("FEATURE_BOUNDARY_DRIFT")

    privacy = _mapping(contract.get("privacy_gate"))
    if (
        privacy.get("required_for_available_result") is not True
        or privacy.get("accepted_status") != "RECORDED_SYNTHETIC_SCOPE_REVIEWED"
        or privacy.get("accepted_scope")
        != "AGGREGATE_NON_PERSONAL_RECORDED_SYNTHETIC_ONLY"
        or any(
            privacy.get(key) is not False
            for key in (
                "personal_data",
                "persistent_identifier",
                "raw_ip",
                "full_user_agent",
                "free_text",
                "tracking_activation",
                "live_privacy_approval_claimed",
                "retention_policy_activated",
            )
        )
        or privacy.get("not_reviewed_result") != "UNAVAILABLE"
    ):
        _fail("PRIVACY_BOUNDARY_DRIFT")

    signal = _mapping(contract.get("signal_contract"))
    if (
        signal.get("design") != "RANDOMIZED_AGGREGATE_TWO_ARM"
        or signal.get("outcome") != "AFFILIATE_CLICK"
        or signal.get("exact_article_cells") != 5
        or signal.get("minimum_exposures_per_arm_per_cell") != 500
        or signal.get("minimum_outcomes_per_arm_per_cell") != 20
        or any(
            signal.get(key) is not True
            for key in (
                "assignment_verification_required",
                "equal_arm_exposures_required",
                "measurement_verification_required",
                "mature_cohort_required",
                "same_program_required",
                "same_period_required",
                "exact_packet_binding_required",
                "preregistration_hash_required",
            )
        )
        or signal.get("personal_unit_rows") is not False
        or signal.get("observational_identity_linkage") is not False
    ):
        _fail("SIGNAL_BOUNDARY_DRIFT")

    method = _mapping(contract.get("method"))
    if (
        method.get("version") != CAUSAL_METHOD_VERSION
        or method.get("estimand") != "POOLED_RISK_DIFFERENCE"
        or method.get("confidence_bps") != 9500
        or method.get("zero_crossing_result") != "UNAVAILABLE"
        or method.get("claim") != "ANALYSIS_CANDIDATE_ONLY"
        or any(
            method.get(key) is not False
            for key in (
                "provider_fact",
                "provider_reward_allocation",
                "arbitrary_attribution",
            )
        )
    ):
        _fail("METHOD_BOUNDARY_DRIFT")

    mutation = _mapping(contract.get("mutation_boundary"))
    if (
        mutation.get("authority") != "NONE"
        or mutation.get("network") != "FORBIDDEN"
        or mutation.get("tracking_activation") != "DISABLED"
        or mutation.get("publication") != "FORBIDDEN"
        or mutation.get("release") != "NOT_EXECUTED"
        or mutation.get("production") != "NOT_EXECUTED"
        or mutation.get("finance_values_represented") is not False
        or mutation.get("causal_result_automatic_editorial_use") is not False
        or mutation.get("causal_result_automatic_recommendation_use") is not False
        or any(
            mutation.get(key) != "FORBIDDEN"
            for key in (
                "editorial_mutation",
                "article_html_mutation",
                "cta_mutation",
                "product_selection_mutation",
                "recommendation_order_mutation",
                "publication_snapshot_mutation",
            )
        )
    ):
        _fail("MUTATION_BOUNDARY_DRIFT")
    debt = _mapping(contract.get("debt"))
    if debt.get("introduced") != []:
        _fail("DEBT_BOUNDARY_DRIFT")


def _fixture_command(root: Path) -> tuple[bytes, CausalAttributionCommand]:
    payload = _read(root, FIXTURE_PATH)
    fixture = _parse_json(payload)
    document = _mapping(fixture.get("document"), "FIXTURE_INVALID")
    contract_row = _mapping(document.get("contract"), "FIXTURE_INVALID")
    try:
        articles = tuple(
            ContractArticle(
                slot=item["slot"],
                article_id=item["article_id"],
                slug=item["slug"],
                packet_sha256=Sha256Digest(item["packet_sha256"]),
                intent_classification=item["intent_classification"],
            )
            for raw in _rows(contract_row.get("articles"), "FIXTURE_INVALID")
            for item in (_mapping(raw, "FIXTURE_INVALID"),)
        )
        measurement_contract = MeasurementAttributionContract(
            articles=articles,
            source_contract_sha256=Sha256Digest(contract_row["source_contract_sha256"]),
            program=contract_row["program"],
            schema_version=contract_row["schema_version"],
        )
        period_row = _mapping(document.get("period"), "FIXTURE_INVALID")
        period = MeasurementPeriod(
            start_date=date.fromisoformat(period_row["start_date"]),
            end_exclusive_date=date.fromisoformat(period_row["end_exclusive_date"]),
        )
        privacy_row = _mapping(document.get("privacy_review"), "FIXTURE_INVALID")
        privacy = PrivacyReviewEvidence(
            status=PrivacyReviewStatus(privacy_row["status"]),
            review_sha256=Sha256Digest(privacy_row["review_sha256"]),
            scope=privacy_row["scope"],
            synthetic=privacy_row["synthetic"],
            aggregate_only=privacy_row["aggregate_only"],
            personal_data=privacy_row["personal_data"],
            persistent_identifier=privacy_row["persistent_identifier"],
            raw_ip=privacy_row["raw_ip"],
            full_user_agent=privacy_row["full_user_agent"],
            free_text=privacy_row["free_text"],
            tracking_activation=privacy_row["tracking_activation"],
        )
        command = CausalAttributionCommand(
            recording_id=document["recording_id"],
            experiment_id=document["experiment_id"],
            source_sha256=digest_bytes(payload),
            source_bytes=len(payload),
            contract=measurement_contract,
            program=document["program"],
            period=period,
            privacy_review=privacy,
            preregistration_sha256=Sha256Digest(document["preregistration_sha256"]),
            scope=(CausalAttributionScope.RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY),
        )
    except Exception:
        _fail("FIXTURE_INVALID")
    return payload, command


def _build_report(root: Path) -> bytes:
    payload, command = _fixture_command(root)
    first = CausalAttributionEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedCausalAttributionSource(payload),
    ).evaluate(command)
    second = CausalAttributionEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedCausalAttributionSource(payload),
    ).evaluate(command)
    if (
        first != second
        or first.availability is not CausalAvailability.AVAILABLE
        or first.estimate is None
        or first.estimate.confidence_lower_micros <= 0
    ):
        _fail("DETERMINISTIC_EVALUATION_FAILED")
    projection = {
        "document": {
            "authority": "NONE",
            "canonical_status": "DEFERRED_POST_MVP",
            "classification": (
                "RECORDED_SYNTHETIC_AGGREGATE_CAUSAL_ANALYSIS_CANDIDATE"
            ),
            "formal_TST-032": "NOT_EXECUTED",
            "production_eligible": False,
            "schema_version": "1.0.0",
            "story_id": "ST-1906",
        },
        "evaluation": first.payload(),
        "source": {
            "bytes": len(payload),
            "fixture_profile": "RAOS_ST1906_SYNTHETIC_CAUSAL_AGGREGATE_V1",
            "path": FIXTURE_PATH.as_posix(),
            "sha256": sha256_bytes(payload),
            "synthetic": True,
        },
    }
    return (
        json.dumps(
            projection,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _source_record(root: Path, relative: Path) -> dict[str, object]:
    payload = _read(root, relative)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def _manifest_bytes(
    root: Path,
    contract: dict[str, Any],
    report: bytes,
) -> bytes:
    authority = _mapping(contract.get("authority"))
    predecessor = _mapping(contract.get("predecessor"))
    manifest = {
        "document": {
            "id": "RAOS-ST1906-ADVANCED-CAUSAL-ATTRIBUTION-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1906",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "canonical_status": "DEFERRED_POST_MVP",
            "authority": "NONE",
            "production_eligible": False,
        },
        "provenance": {
            "base_commit": BASE_COMMIT,
            "contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "contract_sha256": sha256_bytes(_read(root, CONTRACT_PATH)),
            "authority_inputs": [
                {
                    "uri": f"repo://{_path(authority[key]['path']).as_posix()}",
                    "sha256": _digest(authority[key]["sha256"]),
                }
                for key in _AUTHORITY_KEYS
            ],
            "predecessor_inputs": [
                {
                    "uri": f"repo://{_path(path).as_posix()}",
                    "sha256": _digest(digest),
                }
                for path, digest in _mapping(predecessor["artifacts"]).items()
            ],
        },
        "source_artifact_count": len(SOURCE_ARTIFACT_PATHS),
        "source_artifacts": [
            _source_record(root, relative) for relative in SOURCE_ARTIFACT_PATHS
        ],
        "generated_artifacts": [
            {
                "uri": f"repo://{REPORT_PATH.as_posix()}",
                "bytes": len(report),
                "sha256": sha256_bytes(report),
            }
        ],
        "boundary": {
            "default_scope": "DISABLED",
            "executable_environments": ["ENV-DEV", "ENV-CI"],
            "personal_data": False,
            "tracking_activation": False,
            "finance_values_represented": False,
            "provider_total_allocation": False,
            "editorial_mutation": False,
            "recommendation_order_mutation": False,
            "publication": False,
            "release": False,
            "production": False,
        },
        "verification": {
            "focused_local": "CANDIDATE",
            "formal_TST-032": "NOT_EXECUTED",
            "live_privacy_review": "NOT_EXECUTED",
            "real_signal_calibration": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
        },
        "debt": _mapping(contract.get("debt")),
    }
    try:
        return yaml.safe_dump(
            manifest,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8", errors="strict")
    except Exception:
        _fail("MANIFEST_RENDER_FAILED")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = _parse_yaml(_read(root, CONTRACT_PATH))
    _validate_authority(root, contract)
    _validate_predecessor(root, contract)
    _validate_safe_boundary(contract)
    report = _build_report(root)
    return {
        REPORT_PATH: report,
        MANIFEST_PATH: _manifest_bytes(root, contract, report),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        path = _repository_path(root, relative)
        if _read(root, relative) != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT")


def _ensure_output_parent(root: Path) -> None:
    parent = _repository_path(root, REPORT_PATH).parent
    try:
        parent.mkdir(mode=0o755, parents=False, exist_ok=True)
        metadata = parent.lstat()
    except Exception:
        _fail("OUTPUT_WRITE_FAILED")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("OUTPUT_WRITE_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    _ensure_output_parent(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st1906",
            maximum_payload_bytes=MAX_SOURCE_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail("OUTPUT_WRITE_FAILED")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        build(check=bool(arguments.check))
    except CausalAttributionBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1906 advanced causal attribution checked"
        if arguments.check
        else "ST-1906 advanced causal attribution generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "BASE_COMMIT",
    "CONTRACT_PATH",
    "FIXTURE_PATH",
    "GENERATED_PATHS",
    "GENERATOR_PATH",
    "HELPER_PATH",
    "MANIFEST_PATH",
    "REPORT_PATH",
    "REPO_ROOT",
    "SOURCE_ARTIFACT_PATHS",
    "CausalAttributionBuildError",
    "build",
    "check_outputs",
    "main",
    "parse_args",
    "render_outputs",
    "sha256_bytes",
)
