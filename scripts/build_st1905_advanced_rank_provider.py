#!/usr/bin/env python3
# ST-1905 owner generator; generated artifacts must not be hand-edited.
"""Build the disabled recorded advanced rank-provider artifacts."""

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
from uuid import UUID

import yaml
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for _import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from raos.adapters.recorded_advanced_rank_provider import (  # noqa: E402
    RecordedAdvancedRankProviderSource,
)
from raos.application.analytics.advanced_rank_provider import (  # noqa: E402
    AdvancedRankProviderEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.analytics.advanced_rank_provider import (  # noqa: E402
    AdvancedRankProviderCommand,
    AdvancedRankProviderScope,
    canonical_json_bytes,
    report_projection,
)
from raos.domain.analytics.keyword_rank import (  # noqa: E402
    KeywordRankPeriod,
    Sha256Digest,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-1905/contracts/advanced-rank-provider.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1905/fixtures/recorded/advanced-rank-provider.v1.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1905/generated/advanced-rank-provider-report.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1905/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1905_advanced_rank_provider.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
BASE_COMMIT: Final = "6739246fa6f13a490d4dbd6333d9721c62f7c413"
RECORDING_ID: Final = "st1905_recorded_provider_v1"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1905/README.md"),
    Path("changes/st-1905/completion/completion.v1.yaml"),
    Path("docs/worklogs/ST-1905.md"),
    Path("python/raos/domain/analytics/advanced_rank_provider.py"),
    Path("python/raos/ports/advanced_rank_provider.py"),
    Path("python/raos/application/analytics/advanced_rank_provider.py"),
    Path("python/raos/adapters/recorded_advanced_rank_provider.py"),
    GENERATOR_PATH,
    HELPER_PATH,
    Path("tests/st1905/__init__.py"),
    Path("tests/st1905/conftest.py"),
    Path("tests/st1905/support.py"),
    Path("tests/st1905/test_contract.py"),
    Path("tests/st1905/test_generation.py"),
    Path("tests/st1905/test_negative_cases.py"),
    Path("tests/st1905/test_provider_service.py"),
)


class AdvancedRankProviderBuildError(RuntimeError):
    """Stable closed generator failure without rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1905_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1905_BUILD_FAILED") -> NoReturn:
    raise AdvancedRankProviderBuildError(code) from None


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
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
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
            expected = (before.st_dev, before.st_ino, before.st_size)
            if (after.st_dev, after.st_ino, after.st_size) != expected or (
                named.st_dev,
                named.st_ino,
                named.st_size,
            ) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except AdvancedRankProviderBuildError:
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
    except AdvancedRankProviderBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID")
    if type(loaded) is not dict:
        _fail("YAML_INVALID")
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
    "test_acceptance_design",
    "test_catalog",
    "security_design",
    "security_controls",
    "threat_register",
)


def _validate_authority(root: Path, contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"))
    if document != {
        "schema_version": "1.0.0",
        "story_id": "ST-1905",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_ADVANCED_RANK_PROVIDER_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }:
        _fail("CONTRACT_BOUNDARY_DRIFT")
    authority = _mapping(contract.get("authority"))
    paths: dict[str, Path] = {}
    for key in _AUTHORITY_KEYS:
        paths[key], _ = _validate_hash_binding(root, authority.get(key))

    story = _find(
        _parse_yaml(_read(root, paths["canonical_story"])).get("stories"),
        "ST-1905",
    )
    if (
        story.get("depends_on") != ["ST-1206"]
        or story.get("test_suites") != ["TST-032"]
        or story.get("mvp") is not False
        or story.get("implementation_status") != "DEFERRED_POST_MVP"
        or story.get("acceptance_criteria") != ["separate release decision required"]
    ):
        _fail("STORY_SEMANTIC_DRIFT")
    decision = _find(
        _parse_yaml(_read(root, paths["open_decisions"])).get("items"),
        "OD-004",
    )
    if (
        decision.get("status") != "HUMAN_DECISION_REQUIRED"
        or decision.get("default_behavior") != "Search Consoleと手動CSVのみ"
    ):
        _fail("OPEN_DECISION_SEMANTIC_DRIFT")
    suite = _find(
        _parse_yaml(_read(root, paths["test_catalog"])).get("suites"),
        "TST-032",
    )
    if (
        suite.get("release_blocking") is not True
        or suite.get("execution_status") != "NOT_EXECUTED"
        or suite.get("environments") != ["staging"]
    ):
        _fail("TEST_SEMANTIC_DRIFT")


def _predecessor_inputs(root: Path, contract: dict[str, Any]) -> list[dict[str, str]]:
    predecessor = _mapping(contract.get("predecessor"))
    if (
        predecessor.get("story_id") != "ST-1206"
        or predecessor.get("binding") != "EXACT_BASE_COMMIT_BYTES"
        or predecessor.get("base_commit") != BASE_COMMIT
    ):
        _fail("PREDECESSOR_BOUNDARY_DRIFT")
    artifacts = _mapping(predecessor.get("artifacts"))
    if len(artifacts) != 8:
        _fail("PREDECESSOR_INVENTORY_DRIFT")
    result: list[dict[str, str]] = []
    for raw_path, raw_digest in artifacts.items():
        relative = _path(raw_path)
        digest = _digest(raw_digest)
        if sha256_bytes(_read(root, relative)) != digest:
            _fail("PREDECESSOR_DIGEST_DRIFT")
        result.append({"uri": f"repo://{relative.as_posix()}", "sha256": digest})
    semantics = _mapping(predecessor.get("required_semantics"))
    if semantics != {
        "default_scope": "DISABLED",
        "recorded_synthetic_evaluation_only": True,
        "live_provider_rows": False,
        "serp_scrape": "FORBIDDEN",
        "persistence": "NOT_EXECUTED",
        "recommendation_input": "DISABLED",
        "formal_TST-030": "NOT_EXECUTED",
        "canonical_status": "DEFERRED_POST_MVP",
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT")
    return result


def _validate_canonical_contracts(root: Path, contract: dict[str, Any]) -> None:
    contracts = _mapping(contract.get("canonical_contracts"))
    _validate_hash_binding(root, contracts.get("keyword_rank_row"))
    dispatch_path, _ = _validate_hash_binding(
        root, contracts.get("provider_dispatch_job")
    )
    dispatch = _mapping(contracts.get("provider_dispatch_job"))
    if (
        dispatch.get("advanced_provider_source_type_present") is not False
        or dispatch.get("dispatch_modified_by_this_story") is not False
    ):
        _fail("DISPATCH_BOUNDARY_DRIFT")
    try:
        schema = json.loads(_read(root, dispatch_path))
        enum = schema["allOf"][1]["properties"]["payload"]["properties"]["source_type"][
            "enum"
        ]
    except Exception:
        _fail("DISPATCH_SCHEMA_INVALID")
    if enum != ["SEARCH_CONSOLE", "GA4", "KEYWORD_RANK_CSV"]:
        _fail("DISPATCH_SCHEMA_DRIFT")


def _validate_safe_boundary(contract: dict[str, Any]) -> None:
    scope = _mapping(contract.get("feature_scope"))
    if (
        scope.get("default") != "DISABLED"
        or scope.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY"]
        or scope.get("live_enabled_state_exists") is not False
        or scope.get("selected_provider_state_exists") is not False
        or scope.get("activation_interface_exists") is not False
        or scope.get("disabled_fails_before_port_call") is not True
        or scope.get("provider_approval_input_rejected") is not True
        or scope.get("release_decision_input_rejected") is not True
    ):
        _fail("FEATURE_BOUNDARY_DRIFT")
    port = _mapping(contract.get("port_contract"))
    if (
        port.get("direction") != "INWARD_PROVIDER_NEUTRAL"
        or port.get("provider_sdk_types") is not False
        or port.get("endpoint_field") is not False
        or port.get("url_field") is not False
        or port.get("credential_field") is not False
        or port.get("raw_query_field") is not False
        or port.get("raw_response_field") is not False
        or port.get("filesystem_path_field") is not False
        or port.get("calls_per_instance") != 1
        or port.get("retry") is not False
        or port.get("replay") is not False
        or port.get("fallback") is not False
    ):
        _fail("PORT_BOUNDARY_DRIFT")
    mutation = _mapping(contract.get("mutation_boundary"))
    for field in (
        "recommendation_order",
        "cta_mutation",
        "article_mutation",
        "publication_snapshot_mutation",
        "publication",
    ):
        if mutation.get(field) != "FORBIDDEN":
            _fail("MUTATION_BOUNDARY_DRIFT")
    execution = _mapping(contract.get("execution_boundary"))
    if (
        execution.get("provider_selection") != "HUMAN_DECISION_REQUIRED"
        or execution.get("provider_approval") != "ABSENT"
        or execution.get("provider_call") != "NOT_EXECUTED"
        or execution.get("credentials") != "NOT_USED"
        or execution.get("network") != "FORBIDDEN"
        or execution.get("serp_scrape") != "FORBIDDEN"
        or execution.get("persistence") != "NOT_EXECUTED"
        or execution.get("release_decision") != "REQUIRED_SEPARATELY"
        or execution.get("release") != "NOT_EXECUTED"
        or execution.get("production") != "NOT_EXECUTED"
        or execution.get("formal_TST-032") != "NOT_EXECUTED"
        or execution.get("story_acceptance") is not False
    ):
        _fail("EXECUTION_BOUNDARY_DRIFT")
    if _mapping(contract.get("debt")).get("introduced") != []:
        _fail("INTRODUCED_DEBT_PRESENT")


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _build_report(root: Path, contract: dict[str, Any]) -> bytes:
    fixture = _mapping(contract.get("recorded_fixture"))
    fixture_path = _path(fixture.get("path"))
    payload = _read(root, fixture_path)
    if (
        fixture_path != FIXTURE_PATH
        or sha256_bytes(payload) != _digest(fixture.get("sha256"))
        or len(payload) != fixture.get("bytes")
        or fixture.get("synthetic") is not True
        or fixture.get("observations") != 6
        or fixture.get("unique_keyword_ids") != 2
        or any(
            fixture.get(field) is not False
            for field in (
                "raw_keyword_text",
                "endpoint",
                "credentials",
                "provider_sdk_payload",
                "personal_data",
                "finance_fields",
                "recommendation_fields",
            )
        )
    ):
        _fail("FIXTURE_BINDING_DRIFT")
    command = AdvancedRankProviderCommand(
        recording_id=RECORDING_ID,
        site_id=UUID("018f3e90-7b00-7000-8000-000000001900"),
        source_sha256=Sha256Digest.of(payload),
        source_bytes=len(payload),
        period=KeywordRankPeriod(
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 4),
        ),
        scope=(AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY),
    )
    report = AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedAdvancedRankProviderSource(payload),
    ).evaluate(command)
    expected = _mapping(
        _mapping(contract.get("deterministic_evaluation")).get("expected")
    )
    metric_counts = {row.metric_type.value: row.count for row in report.metric_counts}
    if (
        report.row_count != expected.get("row_count")
        or report.unique_keyword_count != expected.get("unique_keyword_count")
        or metric_counts != expected.get("metric_counts")
        or report.observation_from.isoformat() != expected.get("observation_from")
        or report.observation_to.isoformat() != expected.get("observation_to")
        or report.command_sha256.value != expected.get("command_sha256")
        or report.normalized_sha256.value != expected.get("normalized_sha256")
        or report.report_sha256.value != expected.get("report_sha256")
        or report.outcome.value != expected.get("outcome")
    ):
        _fail("DETERMINISTIC_REPORT_DRIFT")
    return _canonical_output(
        {
            "document": {
                "authority": "NONE",
                "default_enabled": False,
                "id": "RAOS-ST1905-ADVANCED-RANK-PROVIDER-REPORT-001",
                "production_eligible": False,
                "status": "LOCAL_IMPLEMENTATION_COMPLETE",
                "story_id": "ST-1905",
                "version": "1.0.0",
            },
            "formal_status": {
                "canonical": "DEFERRED_POST_MVP",
                "formal_tst_032": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
            },
            "report": report_projection(report)
            | {"report_sha256": report.report_sha256.value},
        }
    )


def _source_artifacts(root: Path) -> list[dict[str, object]]:
    return [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": sha256_bytes(content),
        }
        for relative in SOURCE_ARTIFACT_PATHS
        for content in (_read(root, relative),)
    ]


def _manifest_bytes(
    root: Path,
    contract: dict[str, Any],
    report_bytes: bytes,
    predecessor_inputs: list[dict[str, str]],
) -> bytes:
    authority = _mapping(contract.get("authority"))
    authority_inputs = [
        {
            "uri": f"repo://{_path(_mapping(authority[key]).get('path')).as_posix()}",
            "sha256": _digest(_mapping(authority[key]).get("sha256")),
        }
        for key in _AUTHORITY_KEYS
    ]
    manifest = {
        "document": {
            "authority": "NONE",
            "canonical_status": "DEFERRED_POST_MVP",
            "id": "RAOS-ST1905-ADVANCED-RANK-PROVIDER-MANIFEST-001",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "story_id": "ST-1905",
            "version": "1.0.0",
        },
        "provenance": {
            "base_commit": BASE_COMMIT,
            "contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "contract_sha256": sha256_bytes(_read(root, CONTRACT_PATH)),
            "authority_inputs": authority_inputs,
            "predecessor_inputs": predecessor_inputs,
        },
        "source_artifact_count": len(SOURCE_ARTIFACT_PATHS),
        "source_artifacts": _source_artifacts(root),
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REPORT_PATH.as_posix()}",
                "bytes": len(report_bytes),
                "sha256": sha256_bytes(report_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY",
            "default_enabled": False,
            "selected_provider_state_exists": False,
            "live_enabled_state_exists": False,
            "activation_interface_exists": False,
            "provider_approval_accepted": False,
            "release_decision_accepted": False,
            "provider_called": False,
            "network_used": False,
            "credential_read": False,
            "serp_scrape": False,
            "persistence_used": False,
            "kpi_mutated": False,
            "recommendation_mutated": False,
            "publication_allowed": False,
            "release_authorized": False,
            "production_eligible": False,
            "formal_tst_032": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
        "debt": {
            "introduced": [],
            "external_or_formal_remaining": _mapping(contract.get("debt")).get(
                "external_or_formal_remaining"
            ),
        },
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
    predecessors = _predecessor_inputs(root, contract)
    _validate_canonical_contracts(root, contract)
    _validate_safe_boundary(contract)
    report = _build_report(root, contract)
    return {
        REPORT_PATH: report,
        MANIFEST_PATH: _manifest_bytes(root, contract, report, predecessors),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        if _read(root, relative) != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")


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
            namespace="st1905",
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
    except AdvancedRankProviderBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1905 advanced rank provider checked"
        if arguments.check
        else "ST-1905 advanced rank provider generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASE_COMMIT",
    "CONTRACT_PATH",
    "AdvancedRankProviderBuildError",
    "FIXTURE_PATH",
    "GENERATED_PATHS",
    "GENERATOR_PATH",
    "HELPER_PATH",
    "MANIFEST_PATH",
    "REPORT_PATH",
    "REPO_ROOT",
    "SOURCE_ARTIFACT_PATHS",
    "build",
    "check_outputs",
    "main",
    "parse_args",
    "render_outputs",
    "sha256_bytes",
]
