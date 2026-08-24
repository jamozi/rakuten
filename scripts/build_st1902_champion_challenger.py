#!/usr/bin/env python3
# ST-1902 owner generator; generated artifacts must not be hand-edited.
"""Build the disabled recorded champion/challenger shadow artifacts."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
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

from raos.adapters.recorded_champion_challenger import (  # noqa: E402
    RecordedChampionChallengerSource,
    TRUSTED_ROUTE_CATALOG_SHA256,
    TRUSTED_ST0708_REPORT_SHA256,
)
from raos.application.ai.champion_challenger import (  # noqa: E402
    ChampionChallengerShadowService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ai.champion_challenger import (  # noqa: E402
    ChampionChallengerScope,
    ShadowRoutingCommand,
    Sha256Digest,
    TARGET_ROUTE_CODE,
    TARGET_TASK_CODE,
    canonical_json_bytes,
    report_projection,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1902/contracts/champion-challenger-shadow.v1.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1902/fixtures/recorded/champion-challenger-shadow.v1.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1902/generated/champion-challenger-shadow-report.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1902/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1902_champion_challenger.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
BASE_COMMIT: Final = "acdcc3719670c110bf6ec94af1762d87ac7fcb74"
RECORDING_ID: Final = "st1902_recorded_shadow_v1"
POLICY_VERSION: Final = "st1902-disabled-shadow.v1"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1902/README.md"),
    Path("changes/st-1902/completion/completion.v1.yaml"),
    Path("docs/worklogs/ST-1902.md"),
    Path("python/raos/domain/ai/champion_challenger.py"),
    Path("python/raos/ports/champion_challenger.py"),
    Path("python/raos/application/ai/champion_challenger.py"),
    Path("python/raos/adapters/recorded_champion_challenger.py"),
    GENERATOR_PATH,
    HELPER_PATH,
    Path("tests/st1902/__init__.py"),
    Path("tests/st1902/conftest.py"),
    Path("tests/st1902/support.py"),
    Path("tests/st1902/test_contract.py"),
    Path("tests/st1902/test_generation.py"),
    Path("tests/st1902/test_negative_cases.py"),
    Path("tests/st1902/test_shadow_service.py"),
)


class ChampionChallengerBuildError(RuntimeError):
    """Stable closed generator failure without rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1902_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1902_BUILD_FAILED") -> NoReturn:
    raise ChampionChallengerBuildError(code) from None


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
            if (after.st_dev, after.st_ino, after.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ) or (named.st_dev, named.st_ino, named.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except ChampionChallengerBuildError:
        raise
    except Exception:
        _fail("FILE_BOUNDARY_VIOLATION")


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader, node: MappingNode, deep: bool = False
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
    except ChampionChallengerBuildError:
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
    root: Path, binding: object, code: str = "AUTHORITY_DIGEST_DRIFT"
) -> tuple[Path, str]:
    row = _mapping(binding)
    if frozenset(row).isdisjoint({"path", "sha256"}):
        _fail("CONTRACT_INVALID")
    relative = _path(row.get("path"))
    digest = _digest(row.get("sha256"))
    if sha256_bytes(_read(root, relative)) != digest:
        _fail(code)
    return relative, digest


def _validate_authority(root: Path, contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"))
    if document != {
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
    }:
        _fail("CONTRACT_BOUNDARY_DRIFT")

    authority = _mapping(contract.get("authority"))
    authority_paths: dict[str, Path] = {}
    for key in (
        "integration_precedence",
        "canonical_decisions",
        "open_decisions",
        "canonical_story",
        "ai_design",
        "test_acceptance_design",
        "test_catalog",
        "security_design",
        "security_controls",
        "threat_register",
    ):
        relative, _digest_value = _validate_hash_binding(root, authority.get(key))
        authority_paths[key] = relative

    backlog = _parse_yaml(_read(root, authority_paths["canonical_story"]))
    story = _find(backlog.get("stories"), "ST-1902")
    if (
        story.get("depends_on") != ["ST-0708"]
        or story.get("test_suites") != ["TST-032"]
        or story.get("mvp") is not False
        or story.get("implementation_status") != "DEFERRED_POST_MVP"
    ):
        _fail("STORY_SEMANTIC_DRIFT")

    try:
        ai_design = _read(root, authority_paths["ai_design"]).decode(
            "utf-8", errors="strict"
        )
    except UnicodeError:
        _fail("DECISION_SEMANTIC_DRIFT")
    if any(
        snippet not in ai_design
        for snippet in (
            "AI-ADR-028 | Champion/challenger shadow/canary | ACCEPTED | "
            "No immediate champion replacement.",
            "AI-ADR-029 | Route change is a versioned product change | ACCEPTED | "
            "Bind prompt/model/schema/policy/code hashes.",
            "AI-ADR-033 | Automatic route pause, not automatic re-enable | "
            "ACCEPTED | Safety telemetry may stop traffic only.",
        )
    ):
        _fail("DECISION_SEMANTIC_DRIFT")

    tests = _parse_yaml(_read(root, authority_paths["test_catalog"]))
    tst032 = _find(tests.get("suites"), "TST-032")
    if (
        tst032.get("release_blocking") is not True
        or tst032.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TEST_SEMANTIC_DRIFT")


def _predecessor_inputs(root: Path, contract: dict[str, Any]) -> list[dict[str, str]]:
    predecessor = _mapping(contract.get("predecessor"))
    if (
        predecessor.get("story_id") != "ST-0708"
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
        "report_outcome": "REFUSED_INCOMPLETE_EVIDENCE",
        "decision_kind": "PROPOSAL",
        "authority": "NONE",
        "route_mutated": False,
        "activated": False,
        "released": False,
        "production_written": False,
        "formal_TST-018": "NOT_EXECUTED",
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT")
    return result


def _validate_safe_boundary(root: Path, contract: dict[str, Any]) -> None:
    route = _mapping(contract.get("route_binding"))
    catalog, catalog_digest = _validate_hash_binding(root, route.get("catalog"))
    del catalog
    if (
        catalog_digest != TRUSTED_ROUTE_CATALOG_SHA256
        or route.get("task_code") != TARGET_TASK_CODE
        or route.get("route_code") != TARGET_ROUTE_CODE
        or route.get("risk") != "CRITICAL"
        or route.get("route_catalog_canary_max_percent") != 5
        or route.get("critical_effective_canary_max_percent") != 1
        or route.get("configured_canary_allocation_percent") != 0
        or route.get("release_decision") != "ABSENT"
        or route.get("activation_interface_exists") is not False
    ):
        _fail("ROUTE_BOUNDARY_DRIFT")
    scope = _mapping(contract.get("feature_scope"))
    if (
        scope.get("default") != "DISABLED"
        or scope.get("closed_states") != ["DISABLED", "RECORDED_SYNTHETIC_SHADOW_ONLY"]
        or scope.get("live_enabled_state_exists") is not False
        or scope.get("canary_state_exists") is not False
        or scope.get("activation_interface_exists") is not False
        or scope.get("canary_allocation_nonzero_rejected") is not True
        or scope.get("release_decision_input_rejected") is not True
    ):
        _fail("FEATURE_BOUNDARY_DRIFT")
    mutation = _mapping(contract.get("mutation_boundary"))
    for field in (
        "route_mutation",
        "editorial_selection",
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
        execution.get("provider") != "NOT_EXECUTED"
        or execution.get("credentials") != "NOT_USED"
        or execution.get("network") != "FORBIDDEN"
        or execution.get("persistence") != "NOT_EXECUTED"
        or execution.get("canary") != "RELEASE_DECISION_REQUIRED"
        or execution.get("release") != "NOT_EXECUTED"
        or execution.get("production") != "NOT_EXECUTED"
        or execution.get("formal_TST-032") != "NOT_EXECUTED"
        or execution.get("story_acceptance") is not False
    ):
        _fail("EXECUTION_BOUNDARY_DRIFT")
    debt = _mapping(contract.get("debt"))
    if debt.get("introduced") != []:
        _fail("INTRODUCED_DEBT_PRESENT")


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _build_report(root: Path, contract: dict[str, Any]) -> bytes:
    fixture = _mapping(contract.get("recorded_fixture"))
    fixture_path = _path(fixture.get("path"))
    if fixture_path != FIXTURE_PATH:
        _fail("FIXTURE_PATH_DRIFT")
    payload = _read(root, fixture_path)
    if (
        sha256_bytes(payload) != _digest(fixture.get("sha256"))
        or len(payload) != fixture.get("bytes")
        or fixture.get("observations") != 4
        or fixture.get("human_labels") is not False
        or fixture.get("raw_content") is not False
        or fixture.get("personal_data") is not False
        or fixture.get("finance_fields") is not False
    ):
        _fail("FIXTURE_BINDING_DRIFT")
    command = ShadowRoutingCommand(
        recording_id=RECORDING_ID,
        task_code=TARGET_TASK_CODE,
        route_code=TARGET_ROUTE_CODE,
        source_sha256=Sha256Digest.of(payload),
        source_bytes=len(payload),
        policy_version=POLICY_VERSION,
        scope=ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY,
    )
    report = ChampionChallengerShadowService(
        environment=RuntimeEnvironment.CI,
        source=RecordedChampionChallengerSource(payload),
    ).evaluate(command)
    expected = _mapping(
        _mapping(contract.get("deterministic_evaluation")).get("expected")
    )
    if (
        report.cohort_size != expected.get("cohort_size")
        or report.champion_wins != expected.get("champion_wins")
        or report.challenger_wins != expected.get("challenger_wins")
        or report.ties != expected.get("ties")
        or report.champion_mean_score_micros
        != expected.get("champion_mean_score_micros")
        or report.challenger_mean_score_micros
        != expected.get("challenger_mean_score_micros")
        or report.challenger_delta_micros != expected.get("challenger_delta_micros")
        or report.outcome.value != expected.get("outcome")
        or report.challenger_state.value != expected.get("challenger_state")
        or report.st0708_report_sha256.value != TRUSTED_ST0708_REPORT_SHA256
    ):
        _fail("DETERMINISTIC_REPORT_DRIFT")
    return _canonical_output(
        {
            "document": {
                "authority": "NONE",
                "default_enabled": False,
                "id": "RAOS-ST1902-CHAMPION-CHALLENGER-SHADOW-REPORT-001",
                "production_eligible": False,
                "status": "LOCAL_IMPLEMENTATION_COMPLETE",
                "story_id": "ST-1902",
                "version": "1.0.0",
            },
            "formal_status": {
                "canonical": "DEFERRED_POST_MVP",
                "formal_tst_032": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
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
    authority_inputs: list[dict[str, str]] = []
    for key in (
        "integration_precedence",
        "canonical_decisions",
        "open_decisions",
        "canonical_story",
        "ai_design",
        "test_acceptance_design",
        "test_catalog",
        "security_design",
        "security_controls",
        "threat_register",
    ):
        row = _mapping(authority.get(key))
        authority_inputs.append(
            {
                "uri": f"repo://{_path(row.get('path')).as_posix()}",
                "sha256": _digest(row.get("sha256")),
            }
        )
    manifest = {
        "document": {
            "authority": "NONE",
            "canonical_status": "DEFERRED_POST_MVP",
            "id": "RAOS-ST1902-CHAMPION-CHALLENGER-MANIFEST-001",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "story_id": "ST-1902",
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
            "classification": "RECORDED_SYNTHETIC_NONAUTHORITATIVE_SHADOW_ONLY",
            "default_enabled": False,
            "canary_allocation_percent": 0,
            "canary_reachable": False,
            "activation_interface_exists": False,
            "provider_called": False,
            "network_used": False,
            "credential_read": False,
            "persistence_used": False,
            "route_mutated": False,
            "editorial_mutated": False,
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
    _validate_safe_boundary(root, contract)
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
            namespace="st1902",
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
    except ChampionChallengerBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1902 champion/challenger shadow checked"
        if arguments.check
        else "ST-1902 champion/challenger shadow generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASE_COMMIT",
    "CONTRACT_PATH",
    "ChampionChallengerBuildError",
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
