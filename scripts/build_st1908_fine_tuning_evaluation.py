#!/usr/bin/env python3
# ST-1908 owner generator; generated artifacts must not be hand-edited.
"""Build the disabled recorded fine-tuning evaluation evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
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

from raos.adapters.recorded_fine_tuning_evaluation import (  # noqa: E402
    RecordedFineTuningEvidenceSource,
)
from raos.application.ai.fine_tuning_evaluation import (  # noqa: E402
    FineTuningEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ai.fine_tuning_evaluation import (  # noqa: E402
    FINE_TUNING_METHOD_VERSION,
    FINE_TUNING_PARSER_VERSION,
    FineTuningEvaluationCommand,
    FineTuningScope,
    canonical_json_bytes,
    report_projection,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-1908/contracts/fine-tuning-evaluation.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1908/fixtures/recorded/fine-tuning-candidate.synthetic.v1.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1908/generated/fine-tuning-evaluation-report.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1908/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1908_fine_tuning_evaluation.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
RECORDING_ID: Final = "st1908_recorded_evaluation_v1"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1908/README.md"),
    Path("changes/st-1908/completion/completion.v1.yaml"),
    Path("docs/execplans/ST-1908.md"),
    Path("docs/worklogs/ST-1908.md"),
    Path("python/raos/domain/ai/fine_tuning_evaluation.py"),
    Path("python/raos/ports/fine_tuning_evaluation.py"),
    Path("python/raos/application/ai/fine_tuning_evaluation.py"),
    Path("python/raos/adapters/recorded_fine_tuning_evaluation.py"),
    GENERATOR_PATH,
    Path("tests/st1908/__init__.py"),
    Path("tests/st1908/conftest.py"),
    Path("tests/st1908/support.py"),
    Path("tests/st1908/test_contract.py"),
    Path("tests/st1908/test_evaluator.py"),
    Path("tests/st1908/test_generation.py"),
    Path("tests/st1908/test_negative_cases.py"),
    Path("tests/st1908/test_security_boundaries.py"),
)
SOURCE_ARTIFACT_PATHS: Final = OWNED_SOURCE_PATHS + (HELPER_PATH,)


class FineTuningBuildError(RuntimeError):
    """Stable generator failure without rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1908_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1908_BUILD_FAILED") -> NoReturn:
    raise FineTuningBuildError(code) from None


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
    except FineTuningBuildError:
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
    except FineTuningBuildError:
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


def _list(value: object, code: str = "CONTRACT_INVALID") -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _string(value: object, code: str = "CONTRACT_INVALID") -> str:
    if type(value) is not str or not value:
        _fail(code)
    return value


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _validate_hash_binding(root: Path, row: object) -> Path:
    binding = _mapping(row)
    relative = Path(_string(binding.get("path")))
    if sha256_bytes(_read(root, relative)) != _string(binding.get("sha256")):
        _fail("SOURCE_HASH_DRIFT")
    return relative


def _validate_contract(root: Path, contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"))
    expected_document = {
        "schema_version": "1.0.0",
        "story_id": "ST-1908",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_FINE_TUNING_EVALUATION_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }
    if document != expected_document:
        _fail("CONTRACT_DOCUMENT_INVALID")

    authority = _mapping(contract.get("authority"))
    for row in authority.values():
        if type(row) is dict and "path" in row:
            _validate_hash_binding(root, row)
    story_binding = _mapping(authority.get("canonical_story"))
    backlog = _parse_yaml(_read(root, Path(_string(story_binding.get("path")))))
    stories = _list(backlog.get("stories"))
    story = next(
        (
            _mapping(row)
            for row in stories
            if type(row) is dict and row.get("id") == "ST-1908"
        ),
        None,
    )
    if story is None or story != {
        "id": "ST-1908",
        "epic_id": "EPIC-19",
        "title": "Fine-tuning evaluation",
        "objective": "Dataset権利と費用対効果を満たす場合のみ検討",
        "depends_on": ["ST-0707"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["post-MVP design revision and implementation"],
        "acceptance_criteria": ["separate release decision required"],
        "test_suites": ["TST-032"],
        "priority": "P2",
        "mvp": False,
        "size": "M",
        "open_decisions": [],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "DEFERRED_POST_MVP",
        "verification_status": "NOT_EXECUTED",
    }:
        _fail("CANONICAL_STORY_DRIFT")
    test_binding = _mapping(authority.get("test_catalog"))
    catalog = _parse_yaml(_read(root, Path(_string(test_binding.get("path")))))
    suite = next(
        (
            _mapping(row)
            for row in _list(catalog.get("suites"))
            if type(row) is dict and row.get("id") == "TST-032"
        ),
        None,
    )
    if (
        suite is None
        or suite.get("release_blocking") is not True
        or suite.get("environments") != ["staging"]
        or suite.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TST032_CONTRACT_DRIFT")

    predecessor = _mapping(contract.get("predecessor"))
    if (
        predecessor.get("story_id") != "ST-0707"
        or predecessor.get("binding") != "OWNER_SEMANTIC_VERSION"
        or predecessor.get("owner_id") != "build_st0707_evaluation_harness_runtime"
        or predecessor.get("owner_version") != 2
    ):
        _fail("PREDECESSOR_INVALID")
    canonical = _mapping(contract.get("canonical_contracts"))
    for row in canonical.values():
        _validate_hash_binding(root, row)
    fixture = _mapping(contract.get("recorded_fixture"))
    fixture_path = Path(_string(fixture.get("path")))
    fixture_bytes = _read(root, fixture_path)
    if (
        fixture_path != FIXTURE_PATH
        or fixture.get("bytes") != len(fixture_bytes)
        or fixture.get("sha256") != sha256_bytes(fixture_bytes)
    ):
        _fail("FIXTURE_HASH_DRIFT")

    scope = _mapping(contract.get("feature_scope"))
    if (
        scope.get("default") != "DISABLED"
        or scope.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_EVALUATION_ONLY"]
        or scope.get("executable_environments") != ["ENV-DEV", "ENV-CI"]
        or any(
            scope.get(field) is not False
            for field in (
                "live_enabled_state_exists",
                "training_state_exists",
                "activation_interface_exists",
            )
        )
    ):
        _fail("FEATURE_SCOPE_INVALID")
    result = _mapping(contract.get("result_contract"))
    if (
        result.get("consideration_candidate_outcome_exists") is not False
        or result.get("missing_or_unverified_metrics") is not None
        or result.get("missing_or_unverified_cost") is not None
        or result.get("authority") != "NONE"
    ):
        _fail("RESULT_BOUNDARY_INVALID")
    mutation = _mapping(contract.get("mutation_boundary"))
    if any(
        mutation.get(field) != "FORBIDDEN"
        for field in (
            "provider_call",
            "training_job",
            "network",
            "credentials",
            "dataset_write",
            "prompt_mutation",
            "route_or_model_mutation",
            "editorial_mutation",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
            "publication",
        )
    ):
        _fail("MUTATION_BOUNDARY_INVALID")
    owned = tuple(Path(_string(path)) for path in _list(contract.get("owned_sources")))
    if owned != OWNED_SOURCE_PATHS:
        _fail("OWNED_SOURCE_INVENTORY_DRIFT")


def _build_report(root: Path) -> bytes:
    fixture = _read(root, FIXTURE_PATH)
    command = FineTuningEvaluationCommand(
        recording_id=RECORDING_ID,
        source_sha256=sha256_bytes(fixture),
        source_bytes=fixture,
        scope=FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
        method_version=FINE_TUNING_METHOD_VERSION,
        parser_version=FINE_TUNING_PARSER_VERSION,
    )
    source = RecordedFineTuningEvidenceSource(fixture)
    service = FineTuningEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    report = service.evaluate(command)
    return _canonical_output(report_projection(report))


def _manifest_bytes(
    root: Path,
    contract: dict[str, Any],
    report: bytes,
) -> bytes:
    source_rows = [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": sha256_bytes(content),
        }
        for relative in SOURCE_ARTIFACT_PATHS
        for content in (_read(root, relative),)
    ]
    fixture = _read(root, FIXTURE_PATH)
    parsed_report = cast(dict[str, Any], json.loads(report))
    contract_bytes = _read(root, CONTRACT_PATH)
    manifest = {
        "document": {
            "id": "RAOS-ST1908-FINE-TUNING-EVALUATION-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1908",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "canonical_status": "DEFERRED_POST_MVP",
            "authority": "NONE",
            "production_eligible": False,
        },
        "provenance": {
            "generator_owner": "build_st1908_fine_tuning_evaluation",
            "generator_version": 2,
            "contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "contract_sha256": sha256_bytes(contract_bytes),
            "fixture_uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "fixture_sha256": sha256_bytes(fixture),
            "report_sha256": sha256_bytes(report),
            "evaluation_report_sha256": parsed_report["report"]["report_sha256"],
        },
        "source_artifact_count": len(source_rows),
        "source_artifacts": source_rows,
        "generated_artifacts": [
            {
                "uri": f"repo://{REPORT_PATH.as_posix()}",
                "bytes": len(report),
                "sha256": sha256_bytes(report),
            }
        ],
        "boundary": {
            "default_enabled": False,
            "recorded_synthetic_only": True,
            "raw_training_examples": False,
            "actual_training_executed": False,
            "live_enabled_state_exists": False,
            "activation_interface_exists": False,
            "provider_called": False,
            "network_used": False,
            "credential_read": False,
            "persistence_used": False,
            "model_or_route_mutated": False,
            "editorial_mutated": False,
            "recommendation_mutated": False,
            "publication_snapshot_mutated": False,
            "publication_allowed": False,
            "release_authorized": False,
            "production_eligible": False,
        },
        "formal_status": {
            "formal_TST-032": "NOT_EXECUTED",
            "legal_dataset_rights_review": "NOT_EXECUTED",
            "actual_fine_tuning": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
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
    _validate_contract(root, contract)
    report = _build_report(root)
    return {
        REPORT_PATH: report,
        MANIFEST_PATH: _manifest_bytes(root, contract, report),
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
            namespace="st1908",
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
    except FineTuningBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1908 fine-tuning evaluation checked"
        if arguments.check
        else "ST-1908 fine-tuning evaluation generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "CONTRACT_PATH",
    "FIXTURE_PATH",
    "FineTuningBuildError",
    "GENERATED_PATHS",
    "GENERATOR_PATH",
    "HELPER_PATH",
    "MANIFEST_PATH",
    "OWNED_SOURCE_PATHS",
    "REPORT_PATH",
    "REPO_ROOT",
    "SOURCE_ARTIFACT_PATHS",
    "build",
    "check_outputs",
    "main",
    "parse_args",
    "render_outputs",
    "sha256_bytes",
)
