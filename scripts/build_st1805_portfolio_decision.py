#!/usr/bin/env python3
"""Build the deterministic, non-attesting ST-1805 portfolio decision pack."""

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
            "ST1805_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1805_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.recorded_scale_decision import (  # noqa: E402
    RecordedPortfolioDecisionAdapter,
)
from raos.application.portfolio.scale_decision import (  # noqa: E402
    RecordedPortfolioDecisionJob,
)
from raos.domain.portfolio.scale_decision import (  # noqa: E402
    FixtureByteLength,
    PROGRAM,
    PortfolioDecisionCommand,
    Sha256Digest,
)


CONTRACT_PATH: Final = Path("changes/st-1805/contracts/portfolio-decision.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1805/fixtures/recorded-synthetic-portfolio-decision.v1.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1805/generated/portfolio-decision.local-blocked.v1.json"
)
README_PATH: Final = Path("changes/st-1805/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1805/PREFLIGHT.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1805/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1805_portfolio_decision.py")
DOMAIN_PATH: Final = Path("python/raos/domain/portfolio/scale_decision.py")
PORT_PATH: Final = Path("python/raos/ports/scale_decision.py")
APPLICATION_PATH: Final = Path("python/raos/application/portfolio/scale_decision.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_scale_decision.py")
ST1804_OUTPUT_PATH: Final = Path(
    "changes/st-1804/generated/gate3-economics.local-blocked.v1.json"
)

SOURCE_PATHS: Final = (
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

GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B "
    "scripts/build_st1805_portfolio_decision.py"
)
CONTRACT_SHA256: Final = (
    "dd6c742d295f5bc7baa036aa6cca0a42e84b7a3168f0302aec8e40e46a87f4b9"
)
FIXTURE_SHA256: Final = (
    "c2b06e525c3d5c8e86997cbd67285eedad85c9b90fd12f95f162d6a6c6fc910e"
)
INPUT_SHA256: Final = "2f2765267d23c7e9f0c0b2e401570fa731dd2bacc79a4e82eccb92485135c26e"
ST1804_OUTPUT_SHA256: Final = (
    "1be17ed3769bf4804ee96b38d03e610b08640ec6805f97dd510d32e89a78c49d"
)

EXPECTED_BINDINGS: Final = {
    "docs/upstream/key_documents/RAOS_01_requirements_purpose_success_v0.1.md": (
        "5890c616fdaaf02022a524c91b0ae91a8bf5c6b297338f8c958be0d49b3b62ea"
    ),
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": (
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
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
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "changes/st-1804/contracts/gate3-economics.v1.yaml": (
        "41387e716a71c93ae288da70469eb8ca2d1a07b28a1a5fcd63b8dbb2d5acd32a"
    ),
    "changes/st-1804/fixtures/recorded-synthetic-gate3-economics.v1.json": (
        "ab603a329a5c7e2d44576be31119f6702ba353882b3f1e798bd3367db0bae5a4"
    ),
    "changes/st-1804/generated/gate3-economics.local-blocked.v1.json": (
        ST1804_OUTPUT_SHA256
    ),
    "scripts/build_st1804_gate3_economics.py": (
        "f65dee559a3105fe81a1996d2bad8b9498906fff441539745fc620a5a2926771"
    ),
}

_MAX_READ_BYTES = 4 * 1024 * 1024
_STAGE_NAME = ".portfolio-decision.local-blocked.v1.json.st1805.next"


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
    print(f"ST1805_ERROR code={code} field={field}", file=sys.stderr)
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
        rendered = content.decode("utf-8", errors="strict")
        if any(
            isinstance(token, (AnchorToken, AliasToken))
            for token in yaml.scan(rendered)
        ):
            _error("YAML_REFERENCE_FORBIDDEN", field)
        document = yaml.load(rendered, Loader=_StrictLoader)
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
        document.get("story_id") != "ST-1805"
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
    decision = _mapping(contract.get("decision_contract"), "decision_contract")
    if (
        decision.get("outputs")
        != {"overall": "BLOCKED", "outcome": "NO_DECISION", "authorized": False}
        or decision.get("product_owner_decision_required") is not True
        or decision.get("automation_may_choose_scale_hold_pivot") is not False
        or decision.get("automation_may_change_category_limit") is not False
        or decision.get("automation_may_apply_mutation") is not False
    ):
        _error("AUTHORITY_BOUNDARY_DRIFT", "decision_contract")
    return contract


def _load_story() -> None:
    backlog = _strict_yaml(
        _safe_read(Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")),
        "canonical_story",
    )
    stories = backlog.get("stories")
    if type(stories) is not list:
        _error("STORY_CATALOG_INVALID", "stories")
    for item in cast(list[object], stories):
        story = _mapping(item, "story")
        if story.get("id") == "ST-1805":
            if (
                story.get("objective") != "次カテゴリ・継続・撤退を判断"
                or story.get("depends_on") != ["ST-1804"]
                or story.get("deliverables") != ["portfolio decision"]
                or story.get("acceptance_criteria")
                != ["quality/economics/risk evidence"]
                or story.get("test_suites") != ["TST-032"]
            ):
                _error("STORY_DRIFT", "ST-1805")
            return
    _error("STORY_MISSING", "ST-1805")


def _validate_dependency() -> Mapping[str, object]:
    dependency = _strict_json(_safe_read(ST1804_OUTPUT_PATH), "ST-1804")
    if (
        dependency.get("schema") != "ST1804_GATE3_PACK_V1"
        or dependency.get("overall") != "BLOCKED"
        or dependency.get("gate_pass_claim") is not False
        or dependency.get("acceptance_criteria_satisfied") is not False
        or dependency.get("actual_observations") != []
        or dependency.get("scale_authority") != "NONE"
    ):
        _error("ST1804_BOUNDARY_DRIFT", "ST-1804")
    authority = _mapping(dependency.get("authority"), "ST-1804.authority")
    if any(authority.get(key) != "NONE" for key in authority):
        _error("ST1804_AUTHORITY_DRIFT", "ST-1804.authority")
    learning = _mapping(
        dependency.get("learning_boundary"), "ST-1804.learning_boundary"
    )
    if (
        learning.get("finance_used_for_product_or_recommendation_ranking") is not False
        or learning.get("modifications_applied") != []
    ):
        _error("ST1804_EDITORIAL_BOUNDARY_DRIFT", "ST-1804.learning_boundary")
    return dependency


def _source_artifact(path: Path) -> dict[str, object]:
    content = _safe_read(path)
    return {
        "bytes": len(content),
        "sha256": _sha256(content),
        "uri": f"repo://{path}",
    }


_PACK_KEYS: Final = {
    "acceptance_criteria_satisfied",
    "actual_observations",
    "authority",
    "classification",
    "completion_boundary",
    "decision",
    "dependency_state",
    "evidence",
    "finance_editorial_boundary",
    "generated_by",
    "mandatory_criteria",
    "overall",
    "provenance",
    "recorded_synthetic_evaluation",
    "schema",
    "story_id",
    "verification",
}


def validate_pack(pack: Mapping[str, object]) -> None:
    if set(pack) != _PACK_KEYS:
        _error("UNKNOWN_OR_MISSING_FIELD", "pack")
    decision = _mapping(pack.get("decision"), "decision")
    if set(decision) != {
        "authorized",
        "category_limit_change",
        "human_decision_required",
        "mutations_applied",
        "outcome",
        "scale_limit_change",
    }:
        _error("UNKNOWN_OR_MISSING_FIELD", "decision")
    authority = _mapping(pack.get("authority"), "authority")
    if (
        pack.get("overall") != "BLOCKED"
        or pack.get("acceptance_criteria_satisfied") is not False
        or pack.get("actual_observations") != []
        or decision
        != {
            "authorized": False,
            "category_limit_change": None,
            "human_decision_required": True,
            "mutations_applied": [],
            "outcome": "NO_DECISION",
            "scale_limit_change": None,
        }
        or any(authority.get(key) != "NONE" for key in authority)
    ):
        _error("AUTHORITY_ESCALATION", "decision")
    criteria = pack.get("mandatory_criteria")
    if (
        type(criteria) is not list
        or len(criteria) != 5
        or any(
            type(row) is not dict
            or cast(dict[object, object], row).get("status") != "NOT_ELIGIBLE"
            for row in criteria
        )
    ):
        _error("EVIDENCE_PROMOTION", "mandatory_criteria")
    boundary = _mapping(
        pack.get("finance_editorial_boundary"), "finance_editorial_boundary"
    )
    if any(value is not False for value in boundary.values()):
        _error("EDITORIAL_BOUNDARY_ESCALATION", "finance_editorial_boundary")


def build_pack() -> dict[str, object]:
    contract = load_contract()
    _load_story()
    dependency = _validate_dependency()
    fixture = _safe_read(FIXTURE_PATH, maximum=1024 * 1024)
    if _sha256(fixture) != FIXTURE_SHA256:
        _error("FIXTURE_HASH_DRIFT", str(FIXTURE_PATH))
    command = PortfolioDecisionCommand(
        recording_id="blocked-synthetic-no-decision",
        fixture_digest=Sha256Digest(FIXTURE_SHA256),
        fixture_length=FixtureByteLength(len(fixture)),
        contract_digest=Sha256Digest(CONTRACT_SHA256),
        expected_input_digest=Sha256Digest(INPUT_SHA256),
        expected_source_pack_digest=Sha256Digest(ST1804_OUTPUT_SHA256),
        program_id=PROGRAM,
    )
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture)
    ).evaluate(command)
    evaluation = report.payload()
    pack = {
        "acceptance_criteria_satisfied": False,
        "actual_observations": [],
        "authority": evaluation["authority"],
        "classification": ("LOCAL_BLOCKED_RECORDED_SYNTHETIC_PORTFOLIO_NO_DECISION"),
        "completion_boundary": {
            "canonical_status_changed": False,
            "formal_or_live_evidence_claimed": False,
            "local_code_complete": True,
            "local_integration_complete": False,
        },
        "decision": evaluation["decision"],
        "dependency_state": {
            "ST-1804": {
                "acceptance_criteria_satisfied": dependency[
                    "acceptance_criteria_satisfied"
                ],
                "actual_observation_count": 0,
                "gate_pass_claim": dependency["gate_pass_claim"],
                "overall": dependency["overall"],
                "pack_sha256": ST1804_OUTPUT_SHA256,
                "scale_authority": dependency["scale_authority"],
                "schema": dependency["schema"],
                "synthetic": True,
            },
            "qualifies_for_business_decision": False,
        },
        "evidence": evaluation["evidence"],
        "finance_editorial_boundary": evaluation["finance_editorial_boundary"],
        "generated_by": {
            "command": GENERATION_COMMAND,
            "generator_sha256": _sha256(_safe_read(GENERATOR_PATH)),
            "uri": f"repo://{GENERATOR_PATH}",
        },
        "mandatory_criteria": evaluation["criteria"],
        "overall": evaluation["overall"],
        "provenance": {
            "dependency_bindings": _flatten_bindings(contract),
            "fixture_sha256": FIXTURE_SHA256,
            "input_sha256": INPUT_SHA256,
            "source_artifacts": [_source_artifact(path) for path in SOURCE_PATHS],
        },
        "recorded_synthetic_evaluation": evaluation,
        "schema": "ST1805_PORTFOLIO_DECISION_PACK_V1",
        "story_id": "ST-1805",
        "verification": {
            "actual_30_45_article_pilot": "NOT_EXECUTED",
            "actual_gate3_economics": "NOT_EXECUTED",
            "formal_risk_evidence": "NOT_EXECUTED",
            "formal_TST-032": "NOT_EXECUTED",
            "human_portfolio_decision": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
    }
    validate_pack(pack)
    return pack


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
        print("ST1805_CHECK_OK")
    else:
        _atomic_write(expected)
        print(f"ST1805_GENERATED path={OUTPUT_PATH} sha256={_sha256(expected)}")
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
    "SOURCE_PATHS",
    "ST1804_OUTPUT_PATH",
    "build_pack",
    "load_contract",
    "main",
    "render_pack",
    "validate_pack",
]
