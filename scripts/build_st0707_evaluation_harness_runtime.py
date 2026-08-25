#!/usr/bin/env python3
"""Build deterministic ST-0707 recorded evaluation artifacts."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import NoReturn, Protocol, cast

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

try:
    from scripts import secure_generated_publication as _publication
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import secure_generated_publication as _publication  # type: ignore[import-not-found, no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("changes/st-0707/contracts/evaluation-harness-runtime.v1.yaml")
REGISTRY_PATH = Path("changes/st-0707/generated/evaluation-suite-registry.v1.json")
DATASET_PATH = Path("changes/st-0707/generated/locked-synthetic-holdout.v1.json")
RUNTIME_MANIFEST_PATH = Path("changes/st-0707/runtime-manifest.v1.json")
MAX_SOURCE_BYTES = 4 * 1024 * 1024
METRIC_SCALE = 1_000_000


class St0707BuildError(RuntimeError):
    pass


class _JsonSchemaValidator(Protocol):
    def iter_errors(self, instance: object) -> Iterator[object]: ...


def _fail() -> NoReturn:
    raise St0707BuildError("ST0707_EVALUATION_HARNESS_BUILD_FAILED") from None


def _canonical(value: dict[str, object]) -> bytes:
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


def _json_output(value: dict[str, object]) -> bytes:
    return _canonical(value) + b"\n"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _repository_path(root: object, relative: object) -> Path:
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
    except St0707BuildError:
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


def _string(value: object, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail()
    return value


def _integer(value: object, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _list(value: object, maximum: int = 256) -> list[object]:
    if type(value) is not list:
        _fail()
    items = cast(list[object], value)
    if len(items) > maximum:
        _fail()
    return items


def _contract(root: Path) -> dict[str, object]:
    payload = _read_regular(root, CONTRACT_PATH)
    try:
        parsed = yaml.safe_load(payload)
    except yaml.YAMLError:
        _fail()
    contract = _mapping(parsed)
    if frozenset(contract) != frozenset(
        {
            "canonical_sources",
            "dataset_fixture",
            "document",
            "outputs",
            "owned_sources",
            "runtime_policy",
            "st0705_bindings",
            "suite",
        }
    ):
        _fail()
    document = _mapping(contract["document"])
    if document != {
        "id": "RAOS-ST0707-EVALUATION-HARNESS-RUNTIME-001",
        "version": "1.0.0",
        "story_id": "ST-0707",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "authority": "NONE",
        "default_enabled": False,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "live_provider_allowed": False,
        "credentials_allowed": False,
        "persistence_allowed": False,
        "activation_allowed": False,
        "release_authorized": False,
        "production_eligible": False,
    }:
        _fail()
    outputs = _mapping(contract["outputs"])
    if outputs != {
        "suite_registry": REGISTRY_PATH.as_posix(),
        "locked_dataset": DATASET_PATH.as_posix(),
        "runtime_manifest": RUNTIME_MANIFEST_PATH.as_posix(),
    }:
        _fail()
    runtime_policy = _mapping(contract["runtime_policy"])
    if (
        runtime_policy.get("maximum_artifact_bytes") != MAX_SOURCE_BYTES
        or runtime_policy.get("maximum_cases") != 256
        or runtime_policy.get("metric_scale") != METRIC_SCALE
        or runtime_policy.get("decision_kind") != "PROPOSAL"
        or runtime_policy.get("unavailable_is_pass") is not False
        or runtime_policy.get("zero_tolerance_waiver_allowed") is not False
        or runtime_policy.get("synthetic_release_eligible") is not False
    ):
        _fail()
    return contract


def _declared_file(root: Path, binding: dict[str, object]) -> tuple[Path, bytes, str]:
    if frozenset(binding) != frozenset({"path", "sha256"}):
        _fail()
    relative = Path(_string(binding["path"]))
    expected = _string(binding["sha256"], 64)
    payload = _read_regular(root, relative)
    if _sha(payload) != expected:
        _fail()
    return relative, payload, expected


def _canonical_inputs(
    root: Path, contract: dict[str, object]
) -> dict[str, tuple[Path, bytes, str]]:
    result: dict[str, tuple[Path, bytes, str]] = {}
    canonical = _mapping(contract["canonical_sources"])
    for name, raw in canonical.items():
        result[name] = _declared_file(root, _mapping(raw))
    st0705 = _mapping(contract["st0705_bindings"])
    for name in (
        "atomic_publication_owner",
        "runtime_contract",
        "profile_registry",
        "recorded_fixture",
        "runtime_manifest",
        "task_schema",
    ):
        result[f"st0705_{name}"] = _declared_file(root, _mapping(st0705[name]))
    return result


def _catalog_suite(
    contract: dict[str, object], catalog_bytes: bytes
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    try:
        catalog = _mapping(yaml.safe_load(catalog_bytes))
    except yaml.YAMLError:
        _fail()
    metrics: dict[str, dict[str, object]] = {}
    for raw in _list(catalog.get("metrics"), 128):
        metric = _mapping(raw)
        code = _string(metric.get("code"))
        if code in metrics:
            _fail()
        metrics[code] = metric
    suite_contract = _mapping(contract["suite"])
    expected_code = _string(suite_contract["suite_code"])
    selected: dict[str, object] | None = None
    for raw in _list(catalog.get("suites"), 128):
        candidate = _mapping(raw)
        if candidate.get("suite_code") == expected_code:
            if selected is not None:
                _fail()
            selected = candidate
    if selected is None:
        _fail()
    if (
        selected.get("task_code") != suite_contract.get("task_code")
        or selected.get("risk_level") != suite_contract.get("risk_level")
        or selected.get("minimum_adjudicated_cases")
        != suite_contract.get("minimum_adjudicated_cases")
        or selected.get("required_splits") != suite_contract.get("required_splits")
    ):
        _fail()
    return selected, metrics


def _threshold_micros(value: object) -> int:
    if type(value) not in {int, float}:
        _fail()
    try:
        scaled = Decimal(str(value)) * Decimal(METRIC_SCALE)
    except Exception:
        _fail()
    integral = scaled.to_integral_value()
    if scaled != integral or not 0 <= integral <= METRIC_SCALE * 10:
        _fail()
    return int(integral)


def _render_registry(
    contract: dict[str, object],
    inputs: dict[str, tuple[Path, bytes, str]],
) -> bytes:
    selected, metric_catalog = _catalog_suite(contract, inputs["evaluation_catalog"][1])
    raw_thresholds = _mapping(selected.get("thresholds"))
    thresholds: list[dict[str, object]] = []
    for code in sorted(raw_thresholds):
        definition = metric_catalog.get(code)
        if definition is None:
            _fail()
        raw = _mapping(raw_thresholds[code], frozenset({"operator", "value"}))
        thresholds.append(
            {
                "code": code,
                "direction": _string(definition.get("direction")),
                "kind": _string(definition.get("kind")),
                "operator": _string(raw["operator"]),
                "threshold_micros": _threshold_micros(raw["value"]),
                "unit": _string(definition.get("unit")),
            }
        )
    zero_tolerance = tuple(
        _string(item, 160) for item in _list(selected.get("zero_tolerance_failures"), 8)
    )
    if len(zero_tolerance) != 8 or len(set(zero_tolerance)) != 8:
        _fail()
    st0705 = _mapping(contract["st0705_bindings"])
    source: dict[str, object] = {
        "bindings": {
            "evaluation_catalog_sha256": inputs["evaluation_catalog"][2],
            "profile_registry_sha256": inputs["st0705_profile_registry"][2],
            "st0705_runtime_contract_sha256": inputs["st0705_runtime_contract"][2],
            "st0705_runtime_manifest_sha256": inputs["st0705_runtime_manifest"][2],
        },
        "document": {
            "authority": "NONE",
            "id": "RAOS-ST0707-EVALUATION-SUITE-REGISTRY-001",
            "live_provider": False,
            "production_eligible": False,
            "provider_mode": "RECORDED_SYNTHETIC_ONLY",
            "release_authorized": False,
            "story_id": "ST-0707",
            "version": "1.0.0",
        },
        "suite": {
            "minimum_adjudicated_cases": _integer(
                selected["minimum_adjudicated_cases"], 10_000
            ),
            "required_splits": [
                _string(item) for item in _list(selected["required_splits"], 5)
            ],
            "risk_level": _string(selected["risk_level"]),
            "suite_code": _string(selected["suite_code"]),
            "task_code": _string(st0705["task_code"]),
            "thresholds": thresholds,
            "zero_tolerance_classes": list(zero_tolerance),
        },
    }
    source["registry_sha256"] = _sha(_canonical(source))
    return _json_output(source)


def _strict_fixture(value: bytes) -> dict[str, object]:
    try:
        root = json.loads(value)
    except json.JSONDecodeError:
        _fail()
    return _mapping(root)


def _render_dataset(
    contract: dict[str, object],
    inputs: dict[str, tuple[Path, bytes, str]],
) -> bytes:
    fixture = _strict_fixture(inputs["st0705_recorded_fixture"][1])
    expected = _mapping(fixture.get("expected_report"))
    dataset_fixture = _mapping(contract["dataset_fixture"])
    case_fixture = _mapping(dataset_fixture["case"])
    st0705 = _mapping(contract["st0705_bindings"])
    evaluation_case = {
        "case_id": _string(case_fixture["case_id"]),
        "task_code": _string(st0705["task_code"]),
        "dataset_version": _string(dataset_fixture["version"]),
        "split": _string(case_fixture["split"]),
        "category": _string(case_fixture["category"]),
        "risk_level": _string(case_fixture["risk_level"]),
        "input_fixture": _string(case_fixture["input_fixture"], 500),
        "expected_disposition": _string(case_fixture["expected_disposition"]),
        "expected_invariants": [
            _string(item, 500)
            for item in _list(case_fixture["expected_invariants"], 32)
        ],
        "metrics": [_string(item, 100) for item in _list(case_fixture["metrics"], 64)],
        "tags": [_string(item, 100) for item in _list(case_fixture["tags"], 32)],
        "gold_artifact": case_fixture["gold_artifact"],
        "notes": _string(case_fixture["notes"], 2000),
    }
    try:
        evaluation_case_schema = json.loads(inputs["evaluation_case_schema"][1])
        Draft202012Validator.check_schema(evaluation_case_schema)
        validator = cast(
            _JsonSchemaValidator, Draft202012Validator(evaluation_case_schema)
        )
        errors = tuple(validator.iter_errors(evaluation_case))
    except Exception:
        _fail()
    if errors:
        _fail()
    bindings = {
        "case_id": evaluation_case["case_id"],
        "category": evaluation_case["category"],
        "evaluation_case_sha256": _sha(_canonical(evaluation_case)),
        "output_sha256": _string(st0705["output_sha256"], 64),
        "profile_sha256": _string(st0705["profile_sha256"], 64),
        "provenance": _string(dataset_fixture["provenance"]),
        "provider_exchange_sha256": _string(st0705["provider_exchange_sha256"], 64),
        "split": evaluation_case["split"],
        "st0705_report_sha256": _string(st0705["validation_report_sha256"], 64),
        "validation_manifest_sha256": _string(st0705["validation_manifest_sha256"], 64),
    }
    if (
        expected.get("report_sha256") != bindings["st0705_report_sha256"]
        or expected.get("profile_sha256") != bindings["profile_sha256"]
        or expected.get("manifest_sha256") != bindings["validation_manifest_sha256"]
        or expected.get("output_sha256") != bindings["output_sha256"]
        or expected.get("provider_exchange_sha256")
        != bindings["provider_exchange_sha256"]
        or expected.get("status") != "LOCAL_VALIDATED"
    ):
        _fail()
    case_projection = bindings | {"case_sha256": _sha(_canonical(bindings))}
    case = case_projection | {"evaluation_case": evaluation_case}
    holdout_document: dict[str, object] = {
        "case_sha256": [case_projection["case_sha256"]],
        "dataset_id": _string(dataset_fixture["dataset_id"]),
        "split": "HOLDOUT",
        "version": _string(dataset_fixture["version"]),
    }
    dataset = {
        "canonical_dataset": _boolean(dataset_fixture["canonical_dataset"]),
        "cases": [case],
        "dataset_id": holdout_document["dataset_id"],
        "holdout_sha256": _sha(_canonical(holdout_document)),
        "human_label_status": _string(dataset_fixture["human_label_status"]),
        "human_labeled": _boolean(dataset_fixture["human_labeled"]),
        "label_provenance": _list(dataset_fixture["label_provenance"], 0),
        "locked_at": _string(dataset_fixture["locked_at"]),
        "provenance": _string(dataset_fixture["provenance"]),
        "release_eligible": _boolean(dataset_fixture["release_eligible"]),
        "representative_dataset": _boolean(dataset_fixture["representative_dataset"]),
        "source_kind": _string(dataset_fixture["source_kind"]),
        "status": _string(dataset_fixture["status"]),
        "version": holdout_document["version"],
    }
    dataset_hash_material = dataset | {"cases": [case_projection]}
    dataset["dataset_sha256"] = _sha(_canonical(dataset_hash_material))
    return _json_output(
        {
            "dataset": dataset,
            "document": {
                "authority": "NONE",
                "id": "RAOS-ST0707-LOCKED-SYNTHETIC-HOLDOUT-001",
                "live_provider": False,
                "production_eligible": False,
                "release_authorized": False,
                "story_id": "ST-0707",
                "version": "1.0.0",
            },
        }
    )


def _source_hashes(
    root: Path,
    contract: dict[str, object],
    inputs: dict[str, tuple[Path, bytes, str]],
) -> dict[str, str]:
    paths: set[Path] = {item[0] for item in inputs.values()}
    for raw in _list(contract["owned_sources"], 64):
        paths.add(Path(_string(raw, 512)))
    result: dict[str, str] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        result[path.as_posix()] = _sha(_read_regular(root, path))
    return result


def render_outputs(
    contract: dict[str, object], root: Path = REPO_ROOT
) -> dict[Path, bytes]:
    inputs = _canonical_inputs(root, contract)
    registry = _render_registry(contract, inputs)
    dataset = _render_dataset(contract, inputs)
    manifest = _json_output(
        {
            "document": {
                "authority": "NONE",
                "id": "RAOS-ST0707-RUNTIME-MANIFEST-001",
                "production_eligible": False,
                "status": "LOCAL_IMPLEMENTATION_COMPLETE",
                "story_id": "ST-0707",
                "version": "1.0.0",
            },
            "formal_status": {
                "formal_tst_018": "NOT_EXECUTED",
                "formal_tst_019": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
            },
            "generated_sha256": {
                REGISTRY_PATH.as_posix(): _sha(registry),
                DATASET_PATH.as_posix(): _sha(dataset),
            },
            "source_sha256": _source_hashes(root, contract, inputs),
        }
    )
    return {
        REGISTRY_PATH: registry,
        DATASET_PATH: dataset,
        RUNTIME_MANIFEST_PATH: manifest,
    }


def _ensure_output_parents(root: Path) -> None:
    generated = _repository_path(root, REGISTRY_PATH).parent
    generated.mkdir(mode=0o755, parents=False, exist_ok=True)
    value = generated.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        _fail()


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    contract = _contract(root)
    outputs = render_outputs(contract, root)
    if check:
        for relative, expected in outputs.items():
            if _read_regular(root, relative) != expected:
                _fail()
        return
    _ensure_output_parents(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st0707",
            maximum_payload_bytes=MAX_SOURCE_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail()


def trust_anchors(root: Path = REPO_ROOT) -> dict[str, str]:
    contract = _contract(root)
    outputs = render_outputs(contract, root)
    return {
        "runtime_contract_sha256": _sha(_read_regular(root, CONTRACT_PATH)),
        "suite_registry_sha256": _sha(outputs[REGISTRY_PATH]),
        "dataset_sha256": _sha(outputs[DATASET_PATH]),
        "runtime_manifest_sha256": _sha(outputs[RUNTIME_MANIFEST_PATH]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print-trust-anchors", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.print_trust_anchors:
            print(json.dumps(trust_anchors(), sort_keys=True))
        else:
            build(check=arguments.check)
    except St0707BuildError as failure:
        print(str(failure))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
