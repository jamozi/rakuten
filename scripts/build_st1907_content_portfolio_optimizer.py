#!/usr/bin/env python3
# ST-1907 owner generator; generated artifacts must not be hand-edited.
"""Build the disabled recorded-synthetic content portfolio optimizer pack."""

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

from raos.adapters.recorded_content_portfolio_optimizer import (  # noqa: E402
    RecordedContentPortfolioOptimizerSource,
)
from raos.application.portfolio.content_optimizer import (  # noqa: E402
    ContentPortfolioOptimizerService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.portfolio.content_optimizer import (  # noqa: E402
    FIXTURE_PROFILE,
    METHOD_VERSION,
    PARSER_VERSION,
    OptimizerAvailability,
    OptimizerUnavailableReason,
    ObservationPeriod,
    PortfolioOptimizerCommand,
    PortfolioOptimizerScope,
    ProposalState,
    Sha256Digest,
    digest_bytes,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


BASE_COMMIT: Final = "3d454db83f59e2854c0680a26dd0a7351cfe47ab"
CONTRACT_PATH: Final = Path(
    "changes/st-1907/contracts/content-portfolio-optimizer.v1.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1907/fixtures/recorded/"
    "content-portfolio-optimizer.blocked.synthetic.v1.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1907/generated/content-portfolio-optimizer-report.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1907/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1907_content_portfolio_optimizer.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
MAX_ARTIFACT_BYTES: Final = 4 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1907/PREFLIGHT.md"),
    Path("changes/st-1907/README.md"),
    Path("changes/st-1907/completion/completion.v1.yaml"),
    Path("docs/execplans/ST-1907.md"),
    Path("docs/worklogs/ST-1907.md"),
    Path("python/raos/domain/portfolio/content_optimizer.py"),
    Path("python/raos/ports/content_portfolio_optimizer.py"),
    Path("python/raos/application/portfolio/content_optimizer.py"),
    Path("python/raos/adapters/recorded_content_portfolio_optimizer.py"),
    GENERATOR_PATH,
    HELPER_PATH,
    Path("tests/st1907/__init__.py"),
    Path("tests/st1907/conftest.py"),
    Path("tests/st1907/support.py"),
    Path("tests/st1907/test_contract.py"),
    Path("tests/st1907/test_generation.py"),
    Path("tests/st1907/test_optimizer_service.py"),
    Path("tests/st1907/test_security_boundaries.py"),
    Path("tests/st1907/test_unavailable_cases.py"),
    Path("tests/st1907/test_hostile_boundaries.py"),
)

_AUTHORITY_KEYS: Final = (
    "integration_precedence",
    "canonical_decisions",
    "open_decisions",
    "canonical_story",
    "backlog_design",
    "upstream_requirements",
    "upstream_architecture",
    "analytics_design",
    "kpi_catalog",
    "test_acceptance_design",
    "test_catalog",
    "security_design",
    "data_classification",
    "roles",
    "security_controls",
    "threat_register",
)
_EXPECTED_CONTROLS: Final = (
    "SEC-GOV-005",
    "SEC-GOV-006",
    "SEC-APP-001",
    "SEC-DATA-003",
    "SEC-DATA-004",
    "SEC-DATA-005",
    "SEC-DATA-006",
    "SEC-DATA-007",
    "SEC-SDLC-006",
    "SEC-SDLC-009",
    "SEC-SDLC-011",
    "SEC-SDLC-012",
)
_EXPECTED_THREATS: Final = (
    "THR-010",
    "THR-014",
    "THR-015",
    "THR-017",
    "THR-018",
    "THR-019",
    "THR-020",
    "THR-024",
    "THR-025",
)
_EXPECTED_DEPENDENCY_HASHES: Final = {
    "changes/st-1805/contracts/portfolio-decision.v1.yaml": (
        "dd6c742d295f5bc7baa036aa6cca0a42e84b7a3168f0302aec8e40e46a87f4b9"
    ),
    "changes/st-1805/fixtures/recorded-synthetic-portfolio-decision.v1.json": (
        "c2b06e525c3d5c8e86997cbd67285eedad85c9b90fd12f95f162d6a6c6fc910e"
    ),
    "changes/st-1805/generated/portfolio-decision.local-blocked.v1.json": (
        "1288a29454435293fc47ff556215c5afee6e58fad8b995b13e4aca81d2535e22"
    ),
    "scripts/build_st1805_portfolio_decision.py": (
        "79ed861e82efd80b10e884028fd99b122ac3b1713b66d63203c671162fdbb23e"
    ),
}
_ST1805_REPORT_PATH: Final = Path(
    "changes/st-1805/generated/portfolio-decision.local-blocked.v1.json"
)
_MEASUREMENT_PATH: Final = Path(
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
)
_MEASUREMENT_SHA256: Final = (
    "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8"
)
_SIGNAL_POLICY_PATH: Final = Path(
    "changes/st-1305/contracts/finance-reconciliation-runtime.v2.yaml"
)
_SIGNAL_POLICY_SHA256: Final = (
    "b21ffd229a771cb10fea9084afea33c2ad1de780112a69b2d6a1eadfe84fcab7"
)


class ContentPortfolioOptimizerBuildError(RuntimeError):
    """Closed owner-generation failure without source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1907_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1907_BUILD_FAILED") -> NoReturn:
    raise ContentPortfolioOptimizerBuildError(code) from None


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
            or not 1 <= before.st_size <= MAX_ARTIFACT_BYTES
        ):
            _fail("FILE_BOUNDARY_VIOLATION")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            expected = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            observed = (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            )
            if observed != expected:
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
            if (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) != expected or (
                named.st_dev,
                named.st_ino,
                named.st_size,
                named.st_mtime_ns,
                named.st_ctime_ns,
            ) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except ContentPortfolioOptimizerBuildError:
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
    if type(content) is not bytes or not content or len(content) > MAX_ARTIFACT_BYTES:
        _fail("YAML_INVALID")
    try:
        text = content.decode("utf-8", errors="strict")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_COMPLEXITY_FORBIDDEN")
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except ContentPortfolioOptimizerBuildError:
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
    if type(content) is not bytes or not content or len(content) > MAX_ARTIFACT_BYTES:
        _fail("JSON_INVALID")
    try:
        loaded = json.loads(
            content,
            object_pairs_hook=_pairs,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except ContentPortfolioOptimizerBuildError:
        raise
    except Exception:
        _fail("JSON_INVALID")
    if type(loaded) is not dict:
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


def _validate_binding(
    root: Path,
    value: object,
    *,
    code: str = "AUTHORITY_DIGEST_DRIFT",
) -> tuple[Path, str]:
    row = _mapping(value)
    relative = _path(row.get("path"))
    expected = _digest(row.get("sha256"))
    if sha256_bytes(_read(root, relative)) != expected:
        _fail(code)
    return relative, expected


def _validate_authority(root: Path, contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"))
    if document != {
        "schema_version": "1.0.0",
        "story_id": "ST-1907",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_SYNTHETIC_HUMAN_PROPOSAL_OPTIMIZER_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "implementation_mode": "STRICT_STORY",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
        "base_commit": BASE_COMMIT,
    }:
        _fail("CONTRACT_BOUNDARY_DRIFT")

    authority = _mapping(contract.get("authority"))
    if tuple(authority) != _AUTHORITY_KEYS:
        _fail("AUTHORITY_INVENTORY_DRIFT")
    paths: dict[str, Path] = {}
    for key in _AUTHORITY_KEYS:
        paths[key], _ = _validate_binding(root, authority.get(key))

    story = _find(
        _parse_yaml(_read(root, paths["canonical_story"])).get("stories"),
        "ST-1907",
    )
    if (
        story.get("depends_on") != ["ST-1805"]
        or story.get("test_suites") != ["TST-032"]
        or story.get("mvp") is not False
        or story.get("implementation_status") != "DEFERRED_POST_MVP"
        or story.get("acceptance_criteria") != ["separate release decision required"]
    ):
        _fail("STORY_SEMANTIC_DRIFT")

    suite = _find(
        _parse_yaml(_read(root, paths["test_catalog"])).get("suites"),
        "TST-032",
    )
    if (
        suite.get("environments") != ["staging"]
        or suite.get("owner") != "Product Owner"
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
    threats = {
        row.get("id")
        for row in _rows(
            _parse_yaml(_read(root, paths["threat_register"])).get("threats")
        )
        if isinstance(row, Mapping)
    }
    if (
        tuple(authority["security_controls"].get("controls", [])) != _EXPECTED_CONTROLS
        or not set(_EXPECTED_CONTROLS).issubset(controls)
        or tuple(authority["threat_register"].get("threats", [])) != _EXPECTED_THREATS
        or not set(_EXPECTED_THREATS).issubset(threats)
        or authority["open_decisions"].get("resolved_by_this_story") is not False
    ):
        _fail("SECURITY_BOUNDARY_DRIFT")


def _validate_dependency(root: Path, contract: dict[str, Any]) -> None:
    dependency = _mapping(contract.get("dependency"))
    if (
        dependency.get("story_id") != "ST-1805"
        or dependency.get("current_readiness") != "BLOCKED_NO_DECISION"
        or dependency.get("blocked_or_no_decision_result") != "UNAVAILABLE"
        or dependency.get("blocked_or_no_decision_proposals") != []
        or dependency.get("dependency_status_changed_by_this_story") is not False
    ):
        _fail("DEPENDENCY_BOUNDARY_DRIFT")
    exact = _mapping(dependency.get("exact_sources"))
    if exact != _EXPECTED_DEPENDENCY_HASHES:
        _fail("DEPENDENCY_INVENTORY_DRIFT")
    for path, expected in exact.items():
        if sha256_bytes(_read(root, _path(path))) != _digest(expected):
            _fail("DEPENDENCY_DIGEST_DRIFT")

    current = _mapping(dependency.get("current_pack"))
    if (
        current.get("path") != _ST1805_REPORT_PATH.as_posix()
        or current.get("sha256")
        != _EXPECTED_DEPENDENCY_HASHES[_ST1805_REPORT_PATH.as_posix()]
        or current.get("overall") != "BLOCKED"
        or current.get("outcome") != "NO_DECISION"
        or current.get("authorized") is not False
        or current.get("acceptance_criteria_satisfied") is not False
        or current.get("actual_observation_count") != 0
        or current.get("human_decision_present") is not False
        or current.get("local_integration_complete") is not False
    ):
        _fail("DEPENDENCY_CONTRACT_DRIFT")

    report = _parse_json(_read(root, _ST1805_REPORT_PATH))
    decision = _mapping(report.get("decision"), "DEPENDENCY_SEMANTIC_DRIFT")
    completion = _mapping(
        report.get("completion_boundary"), "DEPENDENCY_SEMANTIC_DRIFT"
    )
    if (
        report.get("overall") != "BLOCKED"
        or report.get("acceptance_criteria_satisfied") is not False
        or report.get("actual_observations") != []
        or decision.get("outcome") != "NO_DECISION"
        or decision.get("authorized") is not False
        or decision.get("human_decision_required") is not True
        or decision.get("mutations_applied") != []
        or completion.get("local_integration_complete") is not False
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT")


def _validate_measurement_and_signal_policy(
    root: Path, contract: dict[str, Any]
) -> None:
    policy = _mapping(contract.get("measurement_and_signal_policy"))
    measurement_path, measurement_sha = _validate_binding(
        root, policy.get("measurement_contract"), code="MEASUREMENT_DIGEST_DRIFT"
    )
    signal_path, signal_sha = _validate_binding(
        root, policy.get("signal_policy"), code="SIGNAL_POLICY_DIGEST_DRIFT"
    )
    if (
        measurement_path != _MEASUREMENT_PATH
        or measurement_sha != _MEASUREMENT_SHA256
        or signal_path != _SIGNAL_POLICY_PATH
        or signal_sha != _SIGNAL_POLICY_SHA256
        or policy.get("program") != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or policy.get("period_duration_days") != 14
        or any(
            policy.get(field) is not True
            for field in (
                "same_program_required",
                "same_period_required",
                "verified_input_required",
                "mature_cohort_required",
                "positive_denominator_required",
            )
        )
        or policy.get("missing_as_zero") is not False
        or policy.get("finance_signal_allowed") is not False
        or policy.get("personal_data_allowed") is not False
    ):
        _fail("MEASUREMENT_POLICY_BOUNDARY_DRIFT")

    measurement = _parse_json(_read(root, measurement_path))
    guardrails = _mapping(measurement.get("guardrails"), "MEASUREMENT_SEMANTIC_DRIFT")
    if (
        measurement.get("program") != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or measurement.get("period_duration_days") != 14
        or guardrails.get("recommendation_order_mutation") is not False
        or guardrails.get("article_html_mutation") is not False
        or guardrails.get("cta_mutation") is not False
        or guardrails.get("product_selection_mutation") is not False
        or guardrails.get("publication_snapshot_mutation") is not False
        or guardrails.get("live_provider_calls") is not False
        or guardrails.get("network_requests") is not False
        or guardrails.get("recommendation_inputs_excluded")
        != ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"]
    ):
        _fail("MEASUREMENT_SEMANTIC_DRIFT")

    signal_contract = _parse_yaml(_read(root, signal_path))
    report_contract = _mapping(
        signal_contract.get("report_contract"), "SIGNAL_POLICY_SEMANTIC_DRIFT"
    )
    metric_contract = _mapping(
        signal_contract.get("metric_contract"), "SIGNAL_POLICY_SEMANTIC_DRIFT"
    )
    learning = _mapping(
        signal_contract.get("learning_contract"), "SIGNAL_POLICY_SEMANTIC_DRIFT"
    )
    boundary = _mapping(
        signal_contract.get("authority_boundary"),
        "SIGNAL_POLICY_SEMANTIC_DRIFT",
    )
    if (
        report_contract.get("program") != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or report_contract.get("period_duration_days") != 14
        or report_contract.get("same_program_required") is not True
        or report_contract.get("same_period_required") is not True
        or report_contract.get("verified_input_required") is not True
        or report_contract.get("mature_cohort_required") is not True
        or report_contract.get("missing_as_zero") is not False
        or metric_contract.get("same_program_period_verified_mature_only") is not True
        or metric_contract.get("missing_unverified_zero_denominator_immature_mismatch")
        != "UNAVAILABLE"
        or learning.get("output_kind") != "REVIEW_CANDIDATES_ONLY"
        or learning.get("reward_or_profit_priority") is not False
        or any(
            learning.get(field) is not False
            for field in (
                "article_html_mutation",
                "cta_mutation",
                "product_selection_mutation",
                "recommendation_order_mutation",
                "publication_snapshot_mutation",
            )
        )
        or any(
            boundary.get(field) is not False
            for field in (
                "provider_call",
                "network",
                "credential_access",
                "persistence",
                "public_projection",
                "publication",
                "editorial_mutation",
                "recommendation_order_mutation",
                "approval",
                "staging",
                "release",
                "production",
            )
        )
    ):
        _fail("SIGNAL_POLICY_SEMANTIC_DRIFT")


def _validate_safe_boundary(contract: dict[str, Any]) -> None:
    feature = _mapping(contract.get("feature_scope"))
    proposal = _mapping(contract.get("proposal_contract"))
    mutation = _mapping(contract.get("mutation_boundary"))
    verification = _mapping(contract.get("verification_boundary"))
    if (
        feature.get("default") != "DISABLED"
        or feature.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY"]
        or feature.get("executable_environments") != ["ENV-DEV", "ENV-CI"]
        or any(
            feature.get(field) is not False
            for field in ("live_enabled_state_exists", "activation_interface_exists")
        )
        or any(
            feature.get(field) is not True
            for field in (
                "disabled_fails_before_port_call",
                "provider_neutral",
                "caller_bytes_only",
                "one_shot",
                "recorded_synthetic_only",
            )
        )
    ):
        _fail("FEATURE_BOUNDARY_DRIFT")
    if (
        proposal.get("output_kind") != "HUMAN_REVIEW_METADATA_ONLY"
        or proposal.get("actions") != ["STRENGTHEN", "CONSOLIDATE", "WITHDRAW"]
        or proposal.get("input_is_preclassified") is not True
        or proposal.get("thresholds_selected_by_this_story") is not False
        or proposal.get("proposal_order_is_recommendation_order") is not False
        or proposal.get("actionable") is not False
        or proposal.get("human_review_required") is not True
        or proposal.get("automatic_apply") is not False
        or proposal.get("status_APPLY_exists") is not False
        or proposal.get("mutations_applied") != []
    ):
        _fail("PROPOSAL_BOUNDARY_DRIFT")
    false_fields = (
        "activation",
        "approval",
        "proposal_apply",
        "status_apply",
        "provider_call",
        "network",
        "credential_access",
        "persistence",
        "editorial_mutation",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "public_projection",
        "publication",
        "staging",
        "release",
        "production",
        "finance_values_represented",
    )
    if (
        mutation.get("authority") != "NONE"
        or any(mutation.get(field) is not False for field in false_fields)
        or verification.get("formal_TST-032") != "NOT_EXECUTED"
        or verification.get("story_acceptance") is not False
    ):
        _fail("MUTATION_BOUNDARY_DRIFT")


def _validate_fixture(
    root: Path, contract: dict[str, Any]
) -> tuple[bytes, dict[str, Any]]:
    fixture = _mapping(contract.get("recorded_fixture"))
    if fixture.get("path") != FIXTURE_PATH.as_posix():
        _fail("FIXTURE_CONTRACT_DRIFT")
    payload = _read(root, FIXTURE_PATH)
    if (
        sha256_bytes(payload) != _digest(fixture.get("sha256"))
        or len(payload) != fixture.get("bytes")
        or fixture.get("synthetic") is not True
        or fixture.get("current_availability") != "UNAVAILABLE"
        or fixture.get("current_reason") != "DEPENDENCY_BLOCKED_NO_DECISION"
        or fixture.get("current_proposals") != []
    ):
        _fail("FIXTURE_CONTRACT_DRIFT")
    parsed = _parse_json(payload)
    if (
        json.dumps(
            parsed,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
        != payload
    ):
        _fail("FIXTURE_CANONICALIZATION_DRIFT")
    return payload, parsed


def _period(value: object) -> ObservationPeriod:
    row = _mapping(value, "FIXTURE_INVALID")
    try:
        start = date.fromisoformat(str(row.get("start_date")))
        end = date.fromisoformat(str(row.get("end_exclusive_date")))
        period = ObservationPeriod(start_date=start, end_exclusive_date=end)
    except Exception:
        _fail("FIXTURE_INVALID")
    if row.get("duration_days") != 14:
        _fail("FIXTURE_INVALID")
    return period


def _command(
    root: Path,
    contract: dict[str, Any],
    payload: bytes,
    parsed: dict[str, Any],
) -> PortfolioOptimizerCommand:
    document = _mapping(parsed.get("document"), "FIXTURE_INVALID")
    dependency = _mapping(document.get("dependency"), "FIXTURE_INVALID")
    try:
        command = PortfolioOptimizerCommand(
            recording_id=document["recording_id"],
            source_sha256=digest_bytes(payload),
            source_bytes=len(payload),
            contract_sha256=digest_bytes(_read(root, CONTRACT_PATH)),
            expected_dependency_pack_sha256=Sha256Digest(dependency["pack_sha256"]),
            measurement_contract_sha256=Sha256Digest(
                document["measurement_contract_sha256"]
            ),
            signal_policy_sha256=Sha256Digest(document["signal_policy_sha256"]),
            program=document["program"],
            period=_period(document["period"]),
            scope=(PortfolioOptimizerScope.RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY),
        )
    except Exception:
        _fail("FIXTURE_INVALID")
    if (
        document.get("synthetic") is not True
        or document.get("fixture_profile") != FIXTURE_PROFILE
        or document.get("method_version") != METHOD_VERSION
        or document.get("parser_version") != PARSER_VERSION
        or command.measurement_contract_sha256.value != _MEASUREMENT_SHA256
        or command.signal_policy_sha256.value != _SIGNAL_POLICY_SHA256
    ):
        _fail("FIXTURE_SEMANTIC_DRIFT")
    del contract
    return command


def _build_report(root: Path, contract: dict[str, Any]) -> bytes:
    payload, parsed = _validate_fixture(root, contract)
    command = _command(root, contract, payload, parsed)
    first = ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=RecordedContentPortfolioOptimizerSource(payload),
    ).evaluate(command)
    second = ContentPortfolioOptimizerService(
        environment=RuntimeEnvironment.CI,
        source=RecordedContentPortfolioOptimizerSource(payload),
    ).evaluate(command)
    if (
        first != second
        or first.availability is not OptimizerAvailability.UNAVAILABLE
        or first.unavailable_reason
        is not OptimizerUnavailableReason.DEPENDENCY_BLOCKED_NO_DECISION
        or first.proposal_state is not ProposalState.NO_PROPOSALS
        or first.proposals
        or any(first.authority.payload().values())
    ):
        _fail("CURRENT_DEPENDENCY_FAIL_CLOSED_DRIFT")
    projection = {
        "document": {
            "authority": "NONE",
            "canonical_status": "DEFERRED_POST_MVP",
            "classification": (
                "RECORDED_SYNTHETIC_BLOCKED_HUMAN_PROPOSAL_OPTIMIZER_REPORT"
            ),
            "formal_TST-032": "NOT_EXECUTED",
            "production_eligible": False,
            "schema_version": "1.0.0",
            "story_id": "ST-1907",
        },
        "evaluation": first.payload(),
        "source": {
            "bytes": len(payload),
            "fixture_profile": FIXTURE_PROFILE,
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
    dependency = _mapping(contract.get("dependency"))
    exact_dependencies = _mapping(dependency.get("exact_sources"))
    manifest = {
        "document": {
            "id": "RAOS-ST1907-CONTENT-PORTFOLIO-OPTIMIZER-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1907",
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
            "dependency_inputs": [
                {"uri": f"repo://{_path(path).as_posix()}", "sha256": digest}
                for path, digest in exact_dependencies.items()
            ],
            "measurement_input": {
                "uri": f"repo://{_MEASUREMENT_PATH.as_posix()}",
                "sha256": _MEASUREMENT_SHA256,
            },
            "signal_policy_input": {
                "uri": f"repo://{_SIGNAL_POLICY_PATH.as_posix()}",
                "sha256": _SIGNAL_POLICY_SHA256,
            },
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
            "current_dependency": "BLOCKED_NO_DECISION",
            "current_availability": "UNAVAILABLE",
            "current_proposals": 0,
            "human_proposal_only": True,
            "automatic_apply": False,
            "finance_values_represented": False,
            "personal_data": False,
            "provider_call": False,
            "network": False,
            "credential_access": False,
            "persistence": False,
            "editorial_mutation": False,
            "recommendation_order_mutation": False,
            "publication": False,
            "staging": False,
            "release": False,
            "production": False,
        },
        "verification": {
            "focused_local": "CANDIDATE",
            "formal_TST-032": "NOT_EXECUTED",
            "real_observations": "NOT_EXECUTED",
            "human_portfolio_decision": "NOT_EXECUTED",
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
    _validate_dependency(root, contract)
    _validate_measurement_and_signal_policy(root, contract)
    _validate_safe_boundary(contract)
    report = _build_report(root, contract)
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


def _ensure_output_parents(root: Path) -> None:
    for parent in {path.parent for path in GENERATED_PATHS}:
        target = _repository_path(root, parent)
        try:
            target.mkdir(mode=0o755, parents=False, exist_ok=True)
            metadata = target.lstat()
        except Exception:
            _fail("OUTPUT_WRITE_FAILED")
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail("OUTPUT_WRITE_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    _ensure_output_parents(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st1907",
            maximum_payload_bytes=MAX_ARTIFACT_BYTES,
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
    except ContentPortfolioOptimizerBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1907 content portfolio optimizer checked"
        if arguments.check
        else "ST-1907 content portfolio optimizer generated"
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
    "ContentPortfolioOptimizerBuildError",
    "build",
    "check_outputs",
    "main",
    "parse_args",
    "render_outputs",
    "sha256_bytes",
)
