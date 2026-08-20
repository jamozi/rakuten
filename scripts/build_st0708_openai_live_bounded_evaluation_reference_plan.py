#!/usr/bin/env python3
# ST-0708 owner generator; generated artifacts must not be hand-edited.
"""Build the non-executable ST-0708 live-evaluation reference plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0708/contracts/openai-live-bounded-evaluation-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0708/generated/openai-live-bounded-evaluation-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0708/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0708/README.md")
TEST_PATHS: Final = (
    Path("tests/st0708/conftest.py"),
    Path("tests/st0708/test_contract.py"),
    Path("tests/st0708/test_generation.py"),
    Path("tests/st0708/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (README_PATH, CONTRACT_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
CONTRACT_SHA256: Final = (
    "bcac45e1115c66d0502d8959f4c75a68d7877605b38d45b37fe85558112577a7"
)
MAX_SOURCE_BYTES: Final = base.MAX_DOCUMENT_BYTES

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
SECURITY_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")

AUTHORITY_SHA256: Final[dict[Path, str]] = {
    INTEGRATION_PATH: "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    OPEN_DECISIONS_PATH: "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    SECURITY_PATH: "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    TEST_CATALOG_PATH: "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    STORY_PATH: "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
}
ST0707_SHA256: Final[dict[Path, str]] = {
    Path(
        "changes/st-0707/README.md"
    ): "1e0d9662f30670b2edb132e3f96a17e469a117d5b1ff579672d5c05e7b2a3ba6",
    Path(
        "python/raos/domain/ai/evaluation.py"
    ): "f5eba5617c24227ac09de7ce555a52a9454fe2e5320c8bbcaab8752f6945aff4",
    Path(
        "python/raos/application/ai/evaluation.py"
    ): "c8605b67d66af08940cc9ef416153e55e6ea71a571afe9244d7c4d362852b3c9",
    Path(
        "tests/st0707/conftest.py"
    ): "6bade20471f8724fe2d131e57d806d1467b54d6467d77b1853e99732b3d94b78",
    Path(
        "tests/st0707/test_boundaries.py"
    ): "862fdda6f03248f82380bccb0ca138e151df83e39437462a66eea29dc8545b33",
    Path(
        "tests/st0707/test_evaluation.py"
    ): "3680ff67bf147721d04ab9f50c5d5c10503f7120af70c3a1c2b9ae4a80431340",
    Path(
        "tests/st0707/test_failure_isolation.py"
    ): "c8444fd85609491bac33a151055a84c8be7cb2571c1a2db1b377100198537633",
}
ST0703_SHA256: Final[dict[Path, str]] = {
    Path(
        "changes/st-0703/README.md"
    ): "18b91c6d0edad9546c2bef77d2b0ffb39ae01810d85f8d4945762fcb8972b83c",
    Path(
        "changes/st-0703/contracts/openai-responses-adapter.v1.yaml"
    ): "52f8c0491e1e0c78cf691d65c476276c8a557c8666c963759439b6c62198410c",
    Path(
        "changes/st-0703/generated/recorded-fixture-registry.v1.json"
    ): "ad40d041083766250903d85332d3f3dbc554b7d6cd05b60a45735a8287bfbf92",
    Path(
        "changes/st-0703/manifest.yaml"
    ): "60d8970c85a6fc1084e78e007f54d60543056bad11bdcdc66632cd9f015811b5",
    Path(
        "python/raos/domain/ai/provider.py"
    ): "179f608a54c87037556f3c202b08fc7be3207081e9737466e24b9de84392e991",
    Path(
        "python/raos/ports/ai_provider.py"
    ): "3b4ccb19ba26793251b938954c736fdc8be871d618312d3eea2d6a4eff1a5c62",
    Path(
        "python/raos/adapters/openai_responses.py"
    ): "d1ca262711e73af59923d852fdc299ecc9ba67ae29675fd8e2512ea357d26017",
    Path(
        "python/raos/adapters/recorded_ai.py"
    ): "294394757d1739889f54dbb6cf20a8353275faf233bc3bba7fdd3f932671dc6a",
}
PINNED_INPUTS: Final = {**AUTHORITY_SHA256, **ST0707_SHA256, **ST0703_SHA256}
CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "story",
    "dependencies",
    "open_decision",
    "candidate_selection",
    "dataset_boundary",
    "thresholds",
    "execution_configuration",
    "observations",
    "verification_boundary",
    "activation_boundary",
    "command_surface",
)
ACTION_COUNT_KEYS: Final = (
    "provider_call",
    "network",
    "credential_read",
    "filesystem_write",
    "repository_write",
    "database_write",
    "job_dispatch",
    "event_publish",
    "retry",
    "create",
    "update",
    "delete",
    "approve",
    "release",
    "external",
)


class OpenAiLiveBoundedEvaluationReferenceError(RuntimeError):
    """Stable sanitized ST-0708 build failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise OpenAiLiveBoundedEvaluationReferenceError(code) from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path) -> bytes:
    try:
        path = base._repository_regular_file(root, relative, "st0708")
        content = path.read_bytes()
    except base.StagingDeploymentContractError, OSError:
        _fail("FILE_BOUNDARY_VIOLATION")
    if len(content) > MAX_SOURCE_BYTES:
        _fail("SOURCE_SIZE_LIMIT")
    return content


def _mapping(value: object) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH")
    return cast(Mapping[str, Any], value)


def _rows(value: object) -> list[Mapping[str, Any]]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH")
    return [_mapping(row) for row in cast(list[object], value)]


def _strict_match(actual: object, expected: object) -> None:
    try:
        base._strict_match(actual, expected, "st0708")
    except base.StagingDeploymentContractError:
        _fail("CONTRACT_BOUNDARY_VIOLATION")


def _parse_contract_bytes(content: bytes) -> dict[str, Any]:
    if _sha256(content) != CONTRACT_SHA256:
        _fail("CONTRACT_BYTE_DRIFT")
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("CONTRACT_PARSE_FAILED")
        loaded = yaml.load(text, Loader=base.UniqueKeyLoader)
    except OpenAiLiveBoundedEvaluationReferenceError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("CONTRACT_PARSE_FAILED")
    except base.StagingDeploymentContractError:
        _fail("CONTRACT_PARSE_FAILED")
    return dict(_mapping(loaded))


def _expected_contract() -> dict[str, Any]:
    return _parse_contract_bytes(_read(REPO_ROOT, CONTRACT_PATH))


def _find(rows: object, identity: str) -> Mapping[str, Any]:
    matches = [row for row in _rows(rows) if row.get("id") == identity]
    if len(matches) != 1:
        _fail("SOURCE_RECORD_DRIFT")
    return matches[0]


def validate_contract(contract: Mapping[str, Any]) -> None:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_BOUNDARY_VIOLATION")
    _strict_match(contract, _expected_contract())
    document = _mapping(contract["document"])
    decision = _mapping(contract["open_decision"])
    dataset = _mapping(contract["dataset_boundary"])
    observations = _mapping(contract["observations"])
    activation = _mapping(contract["activation_boundary"])
    counts = _mapping(activation["action_counts"])
    if (
        document.get("executable") is not False
        or document.get("interface_only") is not True
        or document.get("runtime_eligible") is not False
        or document.get("decision") != "NOT_READY"
        or decision.get("safe_default") != "RECORDED_FIXTURE_ONLY"
        or decision.get("resolved") is not False
        or dataset.get("holdout") != "NOT_LOADED"
        or observations.get("status") != "NOT_EXECUTED"
        or observations.get("observations") != []
        or observations.get("findings") != []
        or observations.get("failures") != []
        or activation.get("external_actions") != []
        or tuple(counts) != ACTION_COUNT_KEYS
        or any(type(value) is not int or value != 0 for value in counts.values())
    ):
        _fail("SAFE_BOUNDARY_VIOLATION")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    content = _read(root, CONTRACT_PATH)
    contract = _parse_contract_bytes(content)
    validate_contract(contract)
    return contract


def _load_yaml(root: Path, relative: Path) -> Mapping[str, Any]:
    try:
        path = base._repository_regular_file(root, relative, "st0708.source")
        return _mapping(base.load_yaml(path))
    except base.StagingDeploymentContractError:
        _fail("SOURCE_PARSE_FAILED")


def _verify_inputs(root: Path) -> None:
    for relative, digest in PINNED_INPUTS.items():
        if _sha256(_read(root, relative)) != digest:
            _fail("PINNED_INPUT_DRIFT")
    if _sha256(_read(root, HELPER_PATH)) != HELPER_SHA256:
        _fail("HELPER_DRIFT")


def _verify_authority(root: Path) -> None:
    story = _find(_load_yaml(root, STORY_PATH).get("stories"), "ST-0708")
    required_story = {
        "depends_on": ["ST-0707", "ST-0703"],
        "acceptance_criteria": ["risk-specific thresholds"],
        "test_suites": ["TST-018"],
        "open_decisions": ["OD-015"],
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }
    if any(story.get(key) != value for key, value in required_story.items()):
        _fail("STORY_SEMANTIC_DRIFT")
    decision = _find(_load_yaml(root, OPEN_DECISIONS_PATH).get("items"), "OD-015")
    if (
        decision.get("status") != "EXTERNAL_EVIDENCE_REQUIRED"
        or decision.get("default_behavior") != "Recorded fixtureのみ"
        or decision.get("blocking") is not True
    ):
        _fail("OPEN_DECISION_SEMANTIC_DRIFT")
    suite = _find(_load_yaml(root, TEST_CATALOG_PATH).get("suites"), "TST-018")
    if (
        suite.get("environments") != ["staging"]
        or suite.get("release_blocking") is not True
        or suite.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TEST_SUITE_SEMANTIC_DRIFT")


def _verify_dependencies(root: Path) -> None:
    st0707_domain = _read(root, Path("python/raos/domain/ai/evaluation.py")).decode()
    required_st0707 = (
        'default="BOOTSTRAP_SMOKE_ONLY"',
        'default="NON_AUTHORITATIVE"',
        'default="NOT_LOADED"',
        'default="NOT_READY"',
        "release_eligible: bool = field(init=False, default=False)",
        "production_eligible: bool = field(init=False, default=False)",
    )
    if any(fragment not in st0707_domain for fragment in required_st0707):
        _fail("ST0707_SEMANTIC_DRIFT")
    st0703 = _load_yaml(
        root, Path("changes/st-0703/contracts/openai-responses-adapter.v1.yaml")
    )
    authority = _mapping(st0703.get("implementation_authority"))
    boundary = _mapping(st0703.get("boundary"))
    if (
        authority.get("authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or boundary.get("live_api") != "NOT_USED"
        or boundary.get("credential_or_secret_resolution") != "NOT_USED"
        or boundary.get("live_tst_018") != "NOT_EXECUTED"
        or boundary.get("production_readiness") != "NOT_READY"
    ):
        _fail("ST0703_SEMANTIC_DRIFT")


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    validate_contract(contract)
    _verify_inputs(root)
    _verify_authority(root)
    _verify_dependencies(root)
    return cast(
        dict[str, Any],
        json.loads(json.dumps(contract, ensure_ascii=False, allow_nan=False)),
    )


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError:
        _fail("JSON_RENDER_FAILED")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0708-OPENAI-LIVE-BOUNDED-EVALUATION-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0708",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": (
                "python "
                "scripts/build_st0708_openai_live_bounded_evaluation_reference_plan.py"
            ),
        },
        "provenance": {
            "base_commit": "6e56aa4d328ffb4135e9ad23145a611ab584b519",
            "contract_sha256": CONTRACT_SHA256,
            "authority_inputs": [_artifact(root, path) for path in AUTHORITY_SHA256],
            "dependency_inputs": {
                "ST-0707": [_artifact(root, path) for path in ST0707_SHA256],
                "ST-0703": [_artifact(root, path) for path in ST0703_SHA256],
            },
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": (
                "SOURCE_DERIVED_NONEXECUTABLE_OPENAI_LIVE_BOUNDED_"
                "EVALUATION_REFERENCE_PLAN"
            ),
            "executable": False,
            "interface_only": True,
            "runtime_eligible": False,
            "od_015": "EXTERNAL_EVIDENCE_REQUIRED",
            "safe_default": "RECORDED_FIXTURE_ONLY",
            "holdout": "NOT_LOADED",
            "formal_tst_018": "NOT_EXECUTED",
            "decision": "NOT_READY",
            "story_acceptance": False,
            "release_eligible": False,
            "production_eligible": False,
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract, root))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        try:
            path = base._output_file(root, relative)
            actual = path.read_bytes()
        except base.StagingDeploymentContractError, OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative in GENERATED_PATHS:
        try:
            base._atomic_write(root, relative, outputs[relative])
        except base.StagingDeploymentContractError:
            _fail("OUTPUT_WRITE_FAILED")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=bool(args.check))
    except (
        OpenAiLiveBoundedEvaluationReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        code = exc.code if hasattr(exc, "code") else "BOUNDARY_FAILURE"
        print(f"ERROR code={code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-0708 OpenAI live bounded evaluation reference plan checked"
        if args.check
        else "ST-0708 OpenAI live bounded evaluation reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
