#!/usr/bin/env python3
"""Build deterministic refusal-only ST-1901 calibration artifacts."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn, cast

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raos.adapters.recorded_model_judge_calibration import (  # noqa: E402
    load_recorded_model_judge_calibration,
)
from raos.application.ai.model_judge_calibration import (  # noqa: E402
    ModelJudgeCalibrationHarness,
)
from raos.domain.ai.model_judge_calibration import (  # noqa: E402
    TRUSTED_RUNTIME_CONTRACT_SHA256,
)

try:  # noqa: E402
    from scripts import secure_generated_publication as _publication
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import secure_generated_publication as _publication  # type: ignore[import-not-found, no-redef]


CONTRACT_PATH = Path("changes/st-1901/contracts/model-judge-calibration.v1.yaml")
FIXTURE_PATH = Path(
    "changes/st-1901/fixtures/recorded/model-judge-human-labels.synthetic.v1.json"
)
REPORT_PATH = Path(
    "changes/st-1901/generated/model-judge-calibration-evaluation.v1.json"
)
MANIFEST_PATH = Path("changes/st-1901/manifest.yaml")
MAX_SOURCE_BYTES = 4 * 1024 * 1024


class St1901BuildError(RuntimeError):
    pass


def _fail() -> NoReturn:
    raise St1901BuildError("ST1901_MODEL_JUDGE_CALIBRATION_BUILD_FAILED") from None


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail()


def _json_output(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _repository_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail()
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
    except ValueError:
        _fail()
    return candidate


def _read_regular(root: Path, relative: Path) -> bytes:
    path = _repository_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail()
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                _fail()
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail()
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
                _fail()
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except St1901BuildError:
        raise
    except Exception:
        _fail()


def _mapping(value: object, keys: frozenset[str] | None = None) -> dict[str, object]:
    if type(value) is not dict:
        _fail()
    result = cast(dict[str, object], value)
    if keys is not None and frozenset(result) != keys:
        _fail()
    return result


def _list(value: object, *, maximum: int = 1_000) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        _fail()
    return cast(list[object], value)


def _string(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail()
    return value


def _integer(value: object, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _yaml(value: bytes) -> dict[str, object]:
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError:
        _fail()
    return _mapping(parsed)


def _contract(root: Path) -> dict[str, object]:
    payload = _read_regular(root, CONTRACT_PATH)
    if _sha(payload) != TRUSTED_RUNTIME_CONTRACT_SHA256:
        _fail()
    contract = _yaml(payload)
    if frozenset(contract) != frozenset(
        {
            "authority",
            "calibration_contract",
            "canonical_contracts",
            "debt",
            "document",
            "evaluation_contract",
            "execution_boundary",
            "feature_scope",
            "outputs",
            "owned_sources",
            "port_contract",
            "predecessor",
            "recorded_fixture_profile",
        }
    ):
        _fail()
    document = _mapping(contract["document"])
    if document != {
        "schema_version": "1.0.0",
        "story_id": "ST-1901",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_MODEL_JUDGE_CALIBRATION_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "default_enabled": False,
        "production_eligible": False,
        "approval": None,
    }:
        _fail()
    feature = _mapping(contract["feature_scope"])
    if (
        feature.get("default") != "DISABLED"
        or feature.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_CALIBRATION_ONLY"]
        or feature.get("live_enabled_state_exists") is not False
        or feature.get("activation_interface_exists") is not False
        or feature.get("disabled_fails_before_port_call") is not True
    ):
        _fail()
    evaluation = _mapping(contract["evaluation_contract"])
    if (
        evaluation.get("deterministic") is not True
        or evaluation.get("idempotent_by_content_hash") is not True
        or evaluation.get("human_labels_overrideable_by_judge") is not False
        or evaluation.get("accepted_or_release_ready_outcome_exists") is not False
        or evaluation.get("separate_release_decision_required") is not True
    ):
        _fail()
    outputs = _mapping(contract["outputs"])
    if outputs != {
        "recorded_fixture": FIXTURE_PATH.as_posix(),
        "evaluation_report": REPORT_PATH.as_posix(),
        "runtime_manifest": MANIFEST_PATH.as_posix(),
    }:
        _fail()
    return contract


def _declared_file(root: Path, value: object, *, key: str) -> tuple[Path, bytes, str]:
    del key
    binding = _mapping(value)
    if "path" not in binding or "sha256" not in binding:
        _fail()
    relative = Path(_string(binding["path"]))
    expected = _string(binding["sha256"], maximum=64)
    payload = _read_regular(root, relative)
    if _sha(payload) != expected:
        _fail()
    return relative, payload, expected


def _inputs(
    root: Path, contract: dict[str, object]
) -> dict[str, tuple[Path, bytes, str]]:
    result: dict[str, tuple[Path, bytes, str]] = {}
    authority = _mapping(contract["authority"])
    for name in (
        "canonical_story",
        "integration_precedence",
        "security_privacy_design",
        "security_controls",
        "threat_register",
        "test_catalog",
    ):
        result[name] = _declared_file(root, authority[name], key=name)
    predecessor = _mapping(contract["predecessor"])
    artifacts = _mapping(predecessor["artifacts"])
    predecessor_names = {
        "changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml": (
            "predecessor_contract"
        ),
        "changes/st-0707/runtime-manifest.v1.json": "predecessor_manifest",
        "changes/st-0707/generated/evaluation-suite-registry.v1.json": (
            "predecessor_suite"
        ),
    }
    if frozenset(artifacts) != frozenset(predecessor_names):
        _fail()
    for raw_path, name in predecessor_names.items():
        relative = Path(raw_path)
        payload = _read_regular(root, relative)
        expected = _string(artifacts[raw_path], maximum=64)
        if _sha(payload) != expected:
            _fail()
        result[name] = (relative, payload, expected)
    canonical = _mapping(contract["canonical_contracts"])
    for name in (
        "evaluation_catalog",
        "human_review_rubric",
        "judge_output_schema",
        "judge_calibration_schema",
        "judge_calibration_create_schema",
        "atomic_publication_owner",
    ):
        result[name] = _declared_file(root, canonical[name], key=name)
    return result


def _find_by_id(values: object, expected_id: str) -> dict[str, object]:
    found: dict[str, object] | None = None
    for raw in _list(values, maximum=2_000):
        item = _mapping(raw)
        if item.get("id") == expected_id:
            if found is not None:
                _fail()
            found = item
    if found is None:
        _fail()
    return found


def _decimal_micros(value: object) -> int:
    try:
        scaled = Decimal(str(value)) * Decimal(1_000_000)
    except InvalidOperation, ValueError:
        _fail()
    if not scaled.is_finite() or scaled != scaled.to_integral_value():
        _fail()
    return int(scaled)


def _validate_canonical(
    contract: dict[str, object], inputs: dict[str, tuple[Path, bytes, str]]
) -> None:
    backlog = _yaml(inputs["canonical_story"][1])
    story = _find_by_id(backlog.get("stories"), "ST-1901")
    if story != {
        "id": "ST-1901",
        "epic_id": "EPIC-19",
        "title": "Model judge calibrated automation",
        "objective": "Human labelでJudgeを校正し限定利用",
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
        _fail()
    tests = _yaml(inputs["test_catalog"][1])
    tst032 = _find_by_id(tests.get("suites"), "TST-032")
    if (
        tst032.get("name") != "GATE acceptance pack"
        or tst032.get("release_blocking") is not True
        or tst032.get("environments") != ["staging"]
        or tst032.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail()
    catalog = _yaml(inputs["evaluation_catalog"][1])
    calibration = _mapping(catalog.get("judge_calibration"))
    declared = _mapping(contract["calibration_contract"])
    if (
        calibration.get("minimum_double_labeled_cases")
        != declared.get("minimum_double_labeled_cases")
        or _decimal_micros(calibration.get("required_weighted_kappa"))
        != declared.get("required_weighted_kappa_micros")
        or _decimal_micros(calibration.get("maximum_zero_tolerance_false_pass_rate"))
        != declared.get("maximum_critical_false_pass_rate_micros")
        or _decimal_micros(calibration.get("maximum_zero_tolerance_false_fail_rate"))
        != declared.get("maximum_critical_false_fail_rate_micros")
    ):
        _fail()
    rubric = _yaml(inputs["human_review_rubric"][1])
    if (
        rubric.get("purpose")
        != "AI output review and adjudication rubric. This rubric never authorizes AI publication."
        or len(_list(rubric.get("zero_tolerance"), maximum=8)) != 8
    ):
        _fail()
    for name in (
        "judge_output_schema",
        "judge_calibration_schema",
        "judge_calibration_create_schema",
    ):
        try:
            schema = json.loads(inputs[name][1])
            Draft202012Validator.check_schema(schema)
        except Exception:
            _fail()


def _slice(index: int) -> str:
    if index <= 100:
        return "ROUTINE"
    if index <= 140:
        return "EDGE"
    if index <= 180:
        return "ADVERSARIAL"
    return "REGRESSION"


def _shift_score(score: int) -> int:
    return score + 1 if score < 4 else 3


def _render_fixture(
    contract: dict[str, object], inputs: dict[str, tuple[Path, bytes, str]]
) -> bytes:
    declared = _mapping(contract["calibration_contract"])
    profile = _mapping(contract["recorded_fixture_profile"])
    case_count = _integer(profile["case_count"], minimum=1, maximum=1_000)
    cases: list[dict[str, object]] = []
    for index in range(1, case_count + 1):
        score = (index - 1) % 5
        block = (index - 1) // 5
        reviewer_disagreed = block % 8 == 0
        judge_disagreed = block % 10 == 0
        secondary_score = _shift_score(score) if reviewer_disagreed else score
        judge_score = _shift_score(score) if judge_disagreed else score
        human_zero_tolerance = score == 0
        source: dict[str, object] = {
            "adjudicated_score": score,
            "adjudicator_role": (
                "SYNTHETIC_INDEPENDENT_ADJUDICATOR" if reviewer_disagreed else None
            ),
            "candidate_identity_blinded": True,
            "case_id": f"AICASE-ST1901-{index:04d}",
            "human_zero_tolerance": human_zero_tolerance,
            "judge_needs_human_adjudication": judge_disagreed,
            "judge_score": judge_score,
            "judge_zero_tolerance": human_zero_tolerance,
            "primary_score": score,
            "prompt_author_conflict": False,
            "resolution": "ADJUDICATED" if reviewer_disagreed else "AGREED",
            "risk": "CRITICAL" if human_zero_tolerance else "HIGH",
            "secondary_score": secondary_score,
            "slice": _slice(index),
            "split": _string(declared["split"]),
        }
        cases.append(source | {"case_sha256": _sha(_canonical(source))})
    scope = {
        "category_scope": "SYNTHETIC_GENERAL",
        "domain_scope": "RAOS_SYNTHETIC_EDITORIAL",
        "evaluated_task_code": _string(declared["evaluated_task_code"]),
        "grader_version": _string(declared["grader_version"]),
        "judge_prompt_binding_status": "RECORDED_SYNTHETIC_ONLY",
        "judge_route_binding_status": "RECORDED_SYNTHETIC_ONLY",
        "resolved_model_binding_status": "UNAVAILABLE",
        "rubric_sha256": inputs["human_review_rubric"][2],
    }
    privacy = {
        "affiliate_economics_present": False,
        "personal_data_present": False,
        "raw_output_present": False,
        "raw_prompt_present": False,
        "raw_review_body_present": False,
        "raw_source_present": False,
    }
    dataset_without_hash: dict[str, object] = {
        "actual_human_activity": _boolean(profile["actual_human_activity"]),
        "calibration_scope": scope,
        "calibration_scope_sha256": _sha(_canonical(scope)),
        "case_count": case_count,
        "cases": cases,
        "dataset_id": _string(declared["dataset_id"]),
        "dataset_version": _string(declared["dataset_version"]),
        "human_label_authority": _string(profile["human_label_authority"]),
        "privacy": privacy,
        "provenance": _string(declared["provenance"]),
        "release_eligible": _boolean(profile["release_eligible"]),
        "representative_dataset": _boolean(profile["representative_dataset"]),
    }
    dataset = dataset_without_hash | {
        "dataset_sha256": _sha(_canonical(dataset_without_hash))
    }
    document = {
        "actual_human_activity": False,
        "authority": "NONE",
        "id": _string(declared["fixture_id"]),
        "production_eligible": False,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "release_authorized": False,
        "story_id": "ST-1901",
        "version": "1.0.0",
    }
    root: dict[str, object] = {"dataset": dataset, "document": document}
    root["fixture_content_sha256"] = _sha(_canonical(root))
    payload = _json_output(root)

    human_counts = {str(score): 0 for score in range(5)}
    distribution = {
        name: 0 for name in ("ROUTINE", "EDGE", "ADVERSARIAL", "REGRESSION")
    }
    for item in cases:
        human_counts[str(item["adjudicated_score"])] += 1
        distribution[str(item["slice"])] += 1
    if (
        human_counts != _mapping(profile["human_score_counts"])
        or distribution != _mapping(profile["distribution"])
        or sum(item["human_zero_tolerance"] is True for item in cases)
        != profile["critical_positive_cases"]
        or sum(item["human_zero_tolerance"] is False for item in cases)
        != profile["critical_negative_cases"]
        or sum(item["resolution"] == "ADJUDICATED" for item in cases)
        != profile["human_reviewer_disagreement_cases"]
        or sum(item["judge_needs_human_adjudication"] is True for item in cases)
        != profile["judge_human_score_disagreement_cases"]
    ):
        _fail()
    return payload


def _runtime_source_bytes(
    inputs: dict[str, tuple[Path, bytes, str]],
) -> dict[str, bytes]:
    return {
        name: inputs[name][1]
        for name in (
            "predecessor_contract",
            "predecessor_manifest",
            "predecessor_suite",
            "evaluation_catalog",
            "human_review_rubric",
            "judge_output_schema",
            "judge_calibration_schema",
            "judge_calibration_create_schema",
        )
    }


def _render_report(
    fixture: bytes,
    inputs: dict[str, tuple[Path, bytes, str]],
    root: Path,
) -> bytes:
    batch = load_recorded_model_judge_calibration(
        fixture_bytes=fixture,
        runtime_contract_bytes=_read_regular(root, CONTRACT_PATH),
        source_bytes=_runtime_source_bytes(inputs),
    )
    report = ModelJudgeCalibrationHarness().evaluate(batch)
    return report.canonical_bytes() + b"\n"


def _source_hashes(
    root: Path,
    contract: dict[str, object],
    inputs: dict[str, tuple[Path, bytes, str]],
) -> dict[str, str]:
    paths = {item[0] for item in inputs.values()}
    for raw in _list(contract["owned_sources"], maximum=64):
        paths.add(Path(_string(raw)))
    return {
        path.as_posix(): _sha(_read_regular(root, path))
        for path in sorted(paths, key=lambda item: item.as_posix())
    }


def _manifest_bytes(
    *,
    fixture: bytes,
    report: bytes,
    source_hashes: dict[str, str],
) -> bytes:
    report_value = _mapping(json.loads(report))
    value = {
        "document": {
            "authority": "NONE",
            "canonical_implementation_status": "DEFERRED_POST_MVP",
            "id": "RAOS-ST1901-RUNTIME-MANIFEST-001",
            "production_eligible": False,
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "story_id": "ST-1901",
            "version": "1.0.0",
        },
        "evaluation": {
            "case_count": report_value["case_count"],
            "decision_outcome": _mapping(report_value["decision"])["outcome"],
            "local_metric_criteria_met": _mapping(report_value["decision"])[
                "local_metric_criteria_met"
            ],
            "report_sha256": report_value["report_sha256"],
            "separate_release_decision_required": True,
        },
        "formal_status": {
            "actual_human_labeling": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "generated_sha256": {
            FIXTURE_PATH.as_posix(): _sha(fixture),
            REPORT_PATH.as_posix(): _sha(report),
        },
        "source_sha256": source_hashes,
    }
    try:
        return yaml.safe_dump(
            value,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError:
        _fail()


def render_outputs(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> dict[Path, bytes]:
    inputs = _inputs(root, contract)
    _validate_canonical(contract, inputs)
    fixture = _render_fixture(contract, inputs)
    report = _render_report(fixture, inputs, root)
    manifest = _manifest_bytes(
        fixture=fixture,
        report=report,
        source_hashes=_source_hashes(root, contract, inputs),
    )
    return {FIXTURE_PATH: fixture, REPORT_PATH: report, MANIFEST_PATH: manifest}


def _ensure_output_parents(root: Path) -> None:
    for relative in (FIXTURE_PATH.parent, REPORT_PATH.parent):
        current = root
        for part in relative.parts:
            current = current / part
            current.mkdir(mode=0o755, exist_ok=True)
            value = current.lstat()
            if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
                _fail()


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    contract = _contract(root)
    outputs = render_outputs(contract, root)
    if check:
        for relative, expected in outputs.items():
            path = _repository_path(root, relative)
            if (
                _read_regular(root, relative) != expected
                or stat.S_IMODE(path.lstat().st_mode) != 0o644
            ):
                _fail()
        return
    _ensure_output_parents(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st1901",
            maximum_payload_bytes=MAX_SOURCE_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail()


def trust_anchors(root: Path = REPO_ROOT) -> dict[str, str]:
    outputs = render_outputs(_contract(root), root)
    return {
        "runtime_contract_sha256": _sha(_read_regular(root, CONTRACT_PATH)),
        "fixture_sha256": _sha(outputs[FIXTURE_PATH]),
        "report_sha256": _sha(outputs[REPORT_PATH]),
        "manifest_sha256": _sha(outputs[MANIFEST_PATH]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print-trust-anchors", action="store_true")
    arguments, unknown = parser.parse_known_args()
    if unknown:
        print("ST1901_MODEL_JUDGE_CALIBRATION_ARGUMENT_REJECTED", file=sys.stderr)
        return 2
    try:
        if arguments.print_trust_anchors:
            print(json.dumps(trust_anchors(), sort_keys=True))
        else:
            build(check=arguments.check)
    except St1901BuildError as failure:
        print(str(failure))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
