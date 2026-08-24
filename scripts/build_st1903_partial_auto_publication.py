#!/usr/bin/env python3
# ST-1903 owner generator; generated artifacts must not be hand-edited.
"""Build the refusal-only ST-1903 recorded eligibility evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
for _root in (REPO_ROOT, REPO_ROOT / "python"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from raos.adapters.publishing.recorded_partial_auto_publication import (  # noqa: E402
    RecordedPartialAutoPublicationSource,
)
from raos.application.publishing.partial_auto_publication import (  # noqa: E402
    PartialAutoPublicationEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.publishing.partial_auto_publication import (  # noqa: E402
    PARTIAL_AUTO_PUBLICATION_METHOD_VERSION,
    PARTIAL_AUTO_PUBLICATION_PARSER_VERSION,
    PartialAutoPublicationCommand,
    PartialAutoPublicationScope,
    canonical_json_bytes,
    sha256_bytes,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1903/contracts/partial-auto-publication.v1.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1903/fixtures/recorded/partial-auto-publication.synthetic.v1.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1903/generated/partial-auto-publication-report.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1903/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1903_partial_auto_publication.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
BASE_COMMIT: Final = "0aef05373e4ecc45aee2a4fc4f2ca6f4a0dd19cb"
RECORDING_ID: Final = "st1903_recorded_evaluation_v1"
FIXTURE_SHA256: Final = (
    "bc08ab6988c28f2b992049d71202a46dd312a80906c04e6e47651ff9d314b5b4"
)
HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
MAX_READ_BYTES: Final = 4 * 1024 * 1024
GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
OWNED_SOURCE_PATHS: Final = (
    Path("changes/st-1903/PREFLIGHT.md"),
    Path("changes/st-1903/README.md"),
    Path("changes/st-1903/completion/completion.v1.yaml"),
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("docs/execplans/ST-1903.md"),
    Path("docs/worklogs/ST-1903.md"),
    Path("python/raos/domain/publishing/partial_auto_publication.py"),
    Path("python/raos/ports/publishing/partial_auto_publication.py"),
    Path("python/raos/application/publishing/partial_auto_publication.py"),
    Path("python/raos/adapters/publishing/recorded_partial_auto_publication.py"),
    GENERATOR_PATH,
    Path("tests/st1903/__init__.py"),
    Path("tests/st1903/conftest.py"),
    Path("tests/st1903/support.py"),
    Path("tests/st1903/test_adapter.py"),
    Path("tests/st1903/test_application.py"),
    Path("tests/st1903/test_contract_generation.py"),
    Path("tests/st1903/test_domain.py"),
    Path("tests/st1903/test_security_boundaries.py"),
)
SOURCE_ARTIFACT_PATHS: Final = OWNED_SOURCE_PATHS + (HELPER_PATH,)


class PartialAutoPublicationBuildError(RuntimeError):
    """Stable owner failure without rejected input material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1903_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1903_BUILD_FAILED") -> NoReturn:
    raise PartialAutoPublicationBuildError(code) from None


def _repository_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("FILE_BOUNDARY_VIOLATION")
    physical_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(physical_root / relative))
    try:
        candidate.relative_to(physical_root)
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
            or not 1 <= before.st_size <= MAX_READ_BYTES
        ):
            _fail("FILE_BOUNDARY_VIOLATION")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            identity = (before.st_dev, before.st_ino, before.st_size)
            if (opened.st_dev, opened.st_ino, opened.st_size) != identity:
                _fail("FILE_BOUNDARY_VIOLATION")
            remaining = opened.st_size
            chunks: list[bytes] = []
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
            if (after.st_dev, after.st_ino, after.st_size) != identity or (
                named.st_dev,
                named.st_ino,
                named.st_size,
            ) != identity:
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except PartialAutoPublicationBuildError:
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
    if type(content) is not bytes or not content or len(content) > MAX_READ_BYTES:
        _fail("YAML_INVALID")
    try:
        text = content.decode("utf-8", errors="strict")
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in yaml.scan(text)
        ):
            _fail("YAML_COMPLEXITY_FORBIDDEN")
        value = yaml.load(text, Loader=_UniqueSafeLoader)
    except PartialAutoPublicationBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID")
    if type(value) is not dict:
        _fail("YAML_INVALID")
    return cast(dict[str, Any], value)


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


def _hash_binding(root: Path, row: object) -> Path:
    binding = _mapping(row)
    path = Path(_string(binding.get("path")))
    expected = _string(binding.get("sha256"))
    if sha256_bytes(_read(root, path)) != expected:
        _fail("SOURCE_HASH_DRIFT")
    return path


def _canonical_story(root: Path, binding: dict[str, Any]) -> None:
    backlog = _parse_yaml(_read(root, Path(_string(binding.get("path")))))
    story = next(
        (
            _mapping(row)
            for row in _list(backlog.get("stories"))
            if type(row) is dict and row.get("id") == "ST-1903"
        ),
        None,
    )
    expected = {
        "id": "ST-1903",
        "epic_id": "EPIC-19",
        "title": "Approved partial auto-publication",
        "objective": "明示Release条件を満たす低Risk変更のみ自動化",
        "depends_on": ["ST-1805"],
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
    }
    if story != expected:
        _fail("CANONICAL_STORY_DRIFT")


def _tst032(root: Path, binding: dict[str, Any]) -> None:
    catalog = _parse_yaml(_read(root, Path(_string(binding.get("path")))))
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


def _validate_dependency(root: Path, predecessor: dict[str, Any]) -> None:
    if (
        predecessor.get("story_id") != "ST-1805"
        or predecessor.get("binding") != "EXACT_BASE_COMMIT_BYTES"
        or predecessor.get("base_commit") != BASE_COMMIT
    ):
        _fail("PREDECESSOR_INVALID")
    for relative, expected in _mapping(predecessor.get("artifacts")).items():
        if sha256_bytes(_read(root, Path(relative))) != _string(expected):
            _fail("PREDECESSOR_HASH_DRIFT")
    pack = json.loads(
        _read(
            root,
            Path("changes/st-1805/generated/portfolio-decision.local-blocked.v1.json"),
        )
    )
    if type(pack) is not dict:
        _fail("PREDECESSOR_INVALID")
    decision = _mapping(pack.get("decision"), "PREDECESSOR_INVALID")
    completion = _mapping(pack.get("completion_boundary"), "PREDECESSOR_INVALID")
    if (
        pack.get("overall") != "BLOCKED"
        or pack.get("acceptance_criteria_satisfied") is not False
        or decision.get("outcome") != "NO_DECISION"
        or decision.get("authorized") is not False
        or decision.get("human_decision_required") is not True
        or completion.get("local_integration_complete") is not False
    ):
        _fail("PREDECESSOR_BOUNDARY_DRIFT")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = _parse_yaml(_read(root, CONTRACT_PATH))
    document = _mapping(contract.get("document"))
    if document != {
        "schema_version": "1.0.0",
        "story_id": "ST-1903",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_PARTIAL_AUTO_PUBLICATION_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE_MAX_SAFE_DISABLED",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }:
        _fail("CONTRACT_DOCUMENT_INVALID")
    authority = _mapping(contract.get("authority"))
    for row in authority.values():
        if type(row) is dict and "path" in row:
            _hash_binding(root, row)
    story_binding = _mapping(authority.get("canonical_story"))
    _canonical_story(root, story_binding)
    _tst032(root, _mapping(authority.get("test_catalog")))
    _validate_dependency(root, _mapping(contract.get("predecessor")))

    scope = _mapping(contract.get("feature_scope"))
    if (
        scope.get("default") != "DISABLED"
        or scope.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY"]
        or scope.get("executable_environments") != ["ENV-DEV", "ENV-CI"]
        or any(
            scope.get(name) is not False
            for name in (
                "live_enabled_state_exists",
                "activation_state_exists",
                "activation_interface_exists",
                "publication_command_exists",
            )
        )
        or scope.get("disabled_fails_before_port_call") is not True
        or scope.get("separate_human_release_decision_required") is not True
        or scope.get("release_decision_input_currently_rejected") is not True
    ):
        _fail("FEATURE_SCOPE_INVALID")
    low_risk = _mapping(contract.get("low_risk_candidate_contract"))
    if (
        low_risk.get("representable_change_classes")
        != [
            "STALE_VALUE_SUPPRESSION_ONLY",
            "INVALID_AFFILIATE_CTA_DISABLEMENT_ONLY",
        ]
        or low_risk.get("change_count") != 1
        or low_risk.get("safety_contraction_only") is not True
        or low_risk.get("ambiguity_fails_closed") is not True
        or low_risk.get("high_risk_fails_closed") is not True
        or any(
            low_risk.get(name) is not False
            for name in (
                "content_addition",
                "claim_change",
                "recommendation_order_change",
                "product_identity_change",
                "affiliate_destination_change",
                "raw_html",
                "price_or_stock_assertion_addition",
                "personal_data",
                "finance_input",
                "public_write_request",
                "raw_article_or_cms_payload_representable",
            )
        )
    ):
        _fail("LOW_RISK_BOUNDARY_INVALID")
    fixture = _mapping(contract.get("recorded_fixture"))
    fixture_bytes = _read(root, FIXTURE_PATH)
    if (
        fixture.get("path") != FIXTURE_PATH.as_posix()
        or fixture.get("bytes") != len(fixture_bytes)
        or fixture.get("sha256") != sha256_bytes(fixture_bytes)
        or sha256_bytes(fixture_bytes) != FIXTURE_SHA256
        or fixture.get("actual_publication") is not False
        or fixture.get("release_decision") != "ABSENT"
        or fixture.get("formal_TST-032") != "NOT_EXECUTED"
    ):
        _fail("FIXTURE_BINDING_INVALID")
    result = _mapping(contract.get("result_contract"))
    if (
        result.get("positive_publication_outcome_exists") is not False
        or result.get("eligibility_or_publish_authority") != "NONE"
        or result.get("actions") != []
        or result.get("effects") != []
        or result.get("mutations_applied") != []
        or any(
            "ELIGIBLE" in _string(value)
            for value in _list(result.get("closed_outcomes"))
        )
    ):
        _fail("RESULT_BOUNDARY_INVALID")
    mutation = _mapping(contract.get("mutation_boundary"))
    forbidden = (
        "approval",
        "provider_call",
        "network",
        "credentials",
        "database_write",
        "queue_or_event",
        "cms",
        "public_write",
        "editorial_mutation",
        "article_html_mutation",
        "cta_insertion_or_destination_change",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "publication",
        "status_apply",
    )
    if any(mutation.get(name) != "FORBIDDEN" for name in forbidden):
        _fail("MUTATION_BOUNDARY_INVALID")
    owned = tuple(Path(_string(path)) for path in _list(contract.get("owned_sources")))
    if owned != OWNED_SOURCE_PATHS:
        _fail("OWNED_SOURCE_INVENTORY_DRIFT")
    if sha256_bytes(_read(root, HELPER_PATH)) != HELPER_SHA256:
        _fail("OWNER_HELPER_DRIFT")
    return contract


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def build_report(root: Path = REPO_ROOT) -> bytes:
    fixture = _read(root, FIXTURE_PATH)
    command = PartialAutoPublicationCommand(
        recording_id=RECORDING_ID,
        source_sha256=sha256_bytes(fixture),
        source_bytes=len(fixture),
        scope=(
            PartialAutoPublicationScope.RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY
        ),
        parser_version=PARTIAL_AUTO_PUBLICATION_PARSER_VERSION,
    )
    service = PartialAutoPublicationEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedPartialAutoPublicationSource(fixture),
    )
    report = service.evaluate(command)
    return _canonical_output(report.payload())


def validate_report(value: object) -> None:
    report = _mapping(value, "REPORT_INVALID")
    expected_keys = {
        "actions",
        "authority",
        "candidate",
        "command_sha256",
        "criteria",
        "dependency",
        "effects",
        "feature_scope",
        "future_human_release_decision_required",
        "method_version",
        "mutations_applied",
        "outcome",
        "positive_publication_outcome_exists",
        "recording_id",
        "source_sha256",
        "story_id",
    }
    if set(report) != expected_keys:
        _fail("REPORT_SHAPE_INVALID")
    authority = _mapping(report.get("authority"), "REPORT_INVALID")
    dependency = _mapping(report.get("dependency"), "REPORT_INVALID")
    if (
        report.get("story_id") != "ST-1903"
        or report.get("recording_id") != RECORDING_ID
        or report.get("method_version") != PARTIAL_AUTO_PUBLICATION_METHOD_VERSION
        or report.get("feature_scope")
        != "RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY"
        or report.get("outcome") != "REFUSED_DEPENDENCY_BLOCKED"
        or report.get("positive_publication_outcome_exists") is not False
        or report.get("future_human_release_decision_required") is not True
        or report.get("actions") != []
        or report.get("effects") != []
        or report.get("mutations_applied") != []
        or not authority
        or any(value is not False for value in authority.values())
        or dependency.get("overall") != "BLOCKED"
        or dependency.get("outcome") != "NO_DECISION"
        or dependency.get("authorized") is not False
        or dependency.get("human_decision_required") is not True
        or dependency.get("local_integration_complete") is not False
    ):
        _fail("REPORT_AUTHORITY_INVALID")
    criteria = _list(report.get("criteria"), "REPORT_INVALID")
    if len(criteria) != 9 or any(type(row) is not dict for row in criteria):
        _fail("REPORT_CRITERIA_INVALID")


def _manifest_bytes(root: Path, report: bytes) -> bytes:
    sources = []
    for relative in SOURCE_ARTIFACT_PATHS:
        content = _read(root, relative)
        sources.append(
            {
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                "uri": f"repo://{relative.as_posix()}",
            }
        )
    manifest = {
        "boundary": {
            "activation": "DISABLED",
            "actions": [],
            "canonical_status_changed": False,
            "effects": [],
            "formal_TST-032": "NOT_EXECUTED",
            "human_release_decision": "NOT_OBTAINED",
            "publication": "NOT_EXECUTED",
            "publication_authority": "NONE",
            "public_write_authority": "NONE",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "status_apply": "NONE",
            "production": "NOT_EXECUTED",
        },
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_PARTIAL_AUTO_PUBLICATION_V1"
        ),
        "generated_artifacts": [
            {
                "bytes": len(report),
                "sha256": sha256_bytes(report),
                "uri": f"repo://{REPORT_PATH.as_posix()}",
            }
        ],
        "generated_by": {
            "implementation_base": BASE_COMMIT,
            "method_version": PARTIAL_AUTO_PUBLICATION_METHOD_VERSION,
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "parser_version": PARTIAL_AUTO_PUBLICATION_PARSER_VERSION,
        },
        "source_artifacts": sources,
        "story_id": "ST-1903",
    }
    return yaml.safe_dump(
        manifest,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=True,
    ).encode("ascii")


def build_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    load_contract(root)
    report = build_report(root)
    try:
        parsed = json.loads(report)
    except Exception:
        _fail("REPORT_INVALID")
    validate_report(parsed)
    return {
        REPORT_PATH: report,
        MANIFEST_PATH: _manifest_bytes(root, report),
    }


def check_outputs(outputs: Mapping[Path, bytes], root: Path = REPO_ROOT) -> None:
    if set(outputs) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_INVALID")
    for relative, expected in outputs.items():
        path = _repository_path(root, relative)
        try:
            observed = path.lstat()
        except OSError:
            _fail("GENERATED_DRIFT")
        if (
            not stat.S_ISREG(observed.st_mode)
            or stat.S_ISLNK(observed.st_mode)
            or observed.st_nlink != 1
            or stat.S_IMODE(observed.st_mode) != 0o644
            or _read(root, relative) != expected
        ):
            _fail("GENERATED_DRIFT")


def write_outputs(outputs: Mapping[Path, bytes], root: Path = REPO_ROOT) -> None:
    if set(outputs) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_INVALID")
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), outputs[relative])
                for relative in GENERATED_PATHS
            ),
            namespace="st1903-owner",
            maximum_payload_bytes=MAX_READ_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail("GENERATED_INSTALL_FAILED")


def _parse_args(argv: Sequence[str]) -> bool:
    if list(argv) == []:
        return False
    if list(argv) == ["--check"]:
        return True
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    check = _parse_args(sys.argv[1:] if argv is None else argv)
    outputs = build_outputs()
    if check:
        check_outputs(outputs)
        print("ST1903_CHECK_OK")
    else:
        write_outputs(outputs)
        print("ST1903_GENERATE_OK")
    return 0


if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print("ST1903_ERROR code=ISOLATED_MODE_REQUIRED", file=sys.stderr)
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print("ST1903_ERROR code=NO_BYTECODE_MODE_REQUIRED", file=sys.stderr)
        raise SystemExit(1)
    try:
        raise SystemExit(main())
    except PartialAutoPublicationBuildError as error:
        print(f"ST1903_ERROR code={error.code}", file=sys.stderr)
        raise SystemExit(1) from None
