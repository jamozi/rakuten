"""Explicit offline runner for the ST-1506 synthetic canary simulator."""

from __future__ import annotations

import argparse
import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken

from raos.adapters.disabled_production_activation import DisabledProductionActivation
from raos.adapters.recorded_production_canary import (
    CommitFault,
    RecordedProductionCanaryJournal,
)
from raos.application.ops.production_canary import (
    LocalProductionCanaryRun,
    LocalProductionCanaryRunReceipt,
    LocalProductionCanaryService,
)
from raos.domain.ops.production_canary import (
    CanaryCommandKind,
    ProductionCanaryError,
    ProductionCanarySpec,
    ReleasePhase,
    SyntheticObservation,
    canonical_bytes,
    canonical_sha256,
)


_CONTRACT_RELATIVE_PATH = Path(
    "changes/st-1506/contracts/local-production-canary-runtime.v2.yaml"
)
_MAX_DOCUMENT_BYTES = 262_144


class _ClosedLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _ClosedLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    output: dict[object, object] = {}
    construct = cast(
        Callable[[object, bool], object], getattr(loader, "construct_object")
    )
    for key_node, value_node in node.value:
        key = construct(cast(object, key_node), deep)
        try:
            duplicate = key in output
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate mapping key",
                key_node.start_mark,
            )
        output[key] = construct(cast(object, value_node), deep)
    return output


_ClosedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _fail(code: str, field: str) -> NoReturn:
    raise ProductionCanaryError(code, field) from None


def _read_closed_yaml(path: Path) -> Mapping[str, object]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("CONTRACT_READ_FAILED", "contract")
    if (
        not raw
        or len(raw) > _MAX_DOCUMENT_BYTES
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\x00" in raw
    ):
        _fail("CONTRACT_BYTES_INVALID", "contract")
    try:
        text = raw.decode("utf-8", errors="strict")
        scan = cast(Callable[[str], Sequence[object]], getattr(yaml, "scan"))
        for token in scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_EXTENSION_FORBIDDEN", "contract")
        document = cast(object, yaml.load(text, Loader=_ClosedLoader))
    except ProductionCanaryError:
        raise
    except UnicodeDecodeError, yaml.YAMLError:
        _fail("CONTRACT_PARSE_FAILED", "contract")
    if type(document) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    raw_document = cast(dict[object, object], document)
    if any(type(key) is not str for key in raw_document):
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    return cast(Mapping[str, object], document)


def _closed_json_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in output:
            _fail("JSON_SHAPE_INVALID", "binding")
        output[key] = value
    return output


def _read_closed_json(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("BINDING_READ_FAILED", "binding")
    if not raw or len(raw) > _MAX_DOCUMENT_BYTES or b"\x00" in raw:
        _fail("BINDING_BYTES_INVALID", "binding")
    try:
        value = cast(
            object,
            json.loads(
                raw,
                object_pairs_hook=_closed_json_pairs,
                parse_constant=lambda _value: _fail("JSON_VALUE_INVALID", "binding"),
            ),
        )
    except ProductionCanaryError:
        raise
    except json.JSONDecodeError, UnicodeDecodeError:
        _fail("JSON_PARSE_FAILED", "binding")
    if type(value) is not dict:
        _fail("JSON_SHAPE_INVALID", "binding")
    return cast(dict[str, object], value)


def _validate_repository_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    normalized = Path(os.path.abspath(value))
    if value != normalized:
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    cursor = Path(normalized.anchor)
    try:
        for part in normalized.parts[1:]:
            cursor /= part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    except ProductionCanaryError:
        raise
    except OSError:
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    return normalized


def _repository_path(root: Path, uri: object) -> Path:
    if type(uri) is not str or not uri.startswith("repo://"):
        _fail("REPOSITORY_URI_INVALID", "binding")
    relative = PurePosixPath(uri.removeprefix("repo://"))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("REPOSITORY_URI_INVALID", "binding")
    cursor = root
    try:
        for part in relative.parts:
            cursor /= part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                _fail("REPOSITORY_PATH_INVALID", "binding")
        if not stat.S_ISREG(cursor.lstat().st_mode):
            _fail("REPOSITORY_PATH_INVALID", "binding")
    except ProductionCanaryError:
        raise
    except OSError:
        _fail("REPOSITORY_PATH_INVALID", "binding")
    return cursor


def _verify_binding(root: Path, *, uri: object, digest: object) -> Path:
    if type(digest) is not str or len(digest) != 64:
        _fail("BINDING_DIGEST_INVALID", "binding")
    return _repository_path(root, uri)


def _verify_semantic_binding(path: Path, expected: object) -> None:
    if type(expected) is not str or len(expected) != 64:
        _fail("BINDING_DIGEST_INVALID", "binding")
    if path.suffix in {".yaml", ".yml"}:
        _read_closed_yaml(path)
    elif path.suffix == ".json":
        _read_closed_json(path)
    else:
        _fail("BINDING_SEMANTIC_TYPE_INVALID", "binding")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail("CONTRACT_SHAPE_INVALID", field)
    return cast(Mapping[str, object], value)


def load_local_production_canary_spec(
    repository_root: object,
) -> ProductionCanarySpec:
    """Load the exact V2 contract and bind every predecessor artifact."""

    root = _validate_repository_root(repository_root)
    contract_path = _repository_path(
        root, f"repo://{_CONTRACT_RELATIVE_PATH.as_posix()}"
    )
    document = _read_closed_yaml(contract_path)
    spec = ProductionCanarySpec.from_document(document)
    predecessors = _mapping(document.get("predecessor_bindings"), "predecessors")
    for story, raw in predecessors.items():
        row = _mapping(raw, "predecessor")
        if row.get("story_id") != story:
            _fail("PREDECESSOR_BINDING_INVALID", "predecessor")
        for prefix in (
            "design_handoff",
            "contract",
            "reference_plan",
            "manifest",
        ):
            path = _verify_binding(
                root,
                uri=row.get(f"{prefix}_uri"),
                digest=row.get(f"{prefix}_sha256"),
            )
            _verify_semantic_binding(path, row.get(f"{prefix}_semantic_sha256"))
        _verify_binding(
            root,
            uri=row.get("owner_generator_uri"),
            digest=row.get("owner_generator_sha256"),
        )
    compatibility = _mapping(document.get("v1_compatibility_binding"), "compatibility")
    compatibility_path = _verify_binding(
        root,
        uri=compatibility.get("contract_uri"),
        digest=compatibility.get("contract_sha256"),
    )
    _verify_semantic_binding(
        compatibility_path, compatibility.get("contract_semantic_sha256")
    )
    staging = _mapping(predecessors.get("ST-1505"), "staging")
    for uri_field, digest_field in (
        ("manifest_uri", "manifest_sha256"),
        ("pipeline_uri", "pipeline_sha256"),
        ("result_uri", "result_sha256"),
    ):
        _verify_binding(
            root,
            uri=staging.get(uri_field),
            digest=staging.get(digest_field),
        )
    staging_contract_path = _repository_path(root, staging.get("contract_uri"))
    staging_contract = _read_closed_yaml(staging_contract_path)
    artifact = _mapping(staging_contract.get("artifact"), "staging.artifact")
    sbom = _mapping(artifact.get("sbom"), "staging.sbom")
    provenance = _mapping(artifact.get("provenance"), "staging.provenance")
    if (
        artifact.get("payload_sha256") != staging.get("artifact_payload_sha256")
        or canonical_sha256(dict(sbom)) != staging.get("sbom_sha256")
        or canonical_sha256(dict(provenance)) != staging.get("provenance_sha256")
    ):
        _fail("STAGING_ARTIFACT_MISMATCH", "staging")
    result_path = _repository_path(root, staging.get("result_uri"))
    result = _read_closed_json(result_path)
    if (
        result.get("result_sha256") != staging.get("admitted_result_sha256")
        or result.get("contract_sha256") != staging.get("contract_semantic_sha256")
        or result.get("status") != staging.get("required_status")
        or result.get("classification") != staging.get("required_classification")
        or any(
            type(value) is not int or value != 0
            for value in _mapping(
                result.get("action_counts"), "staging.actions"
            ).values()
        )
    ):
        _fail("STAGING_RESULT_MISMATCH", "staging")
    without_result_digest = dict(result)
    embedded = without_result_digest.pop("result_sha256", None)
    if embedded != canonical_sha256(without_result_digest):
        _fail("STAGING_RESULT_MISMATCH", "staging")
    return spec


def recorded_observations(
    repository_root: object,
    spec: ProductionCanarySpec,
) -> tuple[SyntheticObservation, ...]:
    if type(spec) is not ProductionCanarySpec:
        _fail("SPEC_INVALID", "spec")
    root = _validate_repository_root(repository_root)
    contract_path = _repository_path(
        root, f"repo://{_CONTRACT_RELATIVE_PATH.as_posix()}"
    )
    document = _read_closed_yaml(contract_path)
    if ProductionCanarySpec.from_document(document) != spec:
        _fail("SPEC_BINDING_MISMATCH", "spec")
    rows = document.get("recorded_scenarios")
    if type(rows) is not list:
        _fail("SCENARIO_INVALID", "scenario")
    output: list[SyntheticObservation] = []
    for raw in cast(list[object], rows):
        row = _mapping(raw, "scenario")
        try:
            output.append(
                SyntheticObservation(
                    scenario_id=cast(str, row.get("scenario_id")),
                    source="SYNTHETIC_RECORDED_FIXTURE_ONLY",
                    cohort_id=spec.cohort_id,
                    release_phase=ReleasePhase(cast(str, row.get("release_phase"))),
                    contract_sha256=spec.semantic_sha256,
                    artifact_sha256=spec.artifact_sha256,
                    staging_result_sha256=spec.staging_result_sha256,
                    observed_at_epoch_seconds=cast(
                        int, row.get("observed_at_epoch_seconds")
                    ),
                    evaluated_at_epoch_seconds=cast(
                        int, row.get("evaluated_at_epoch_seconds")
                    ),
                    sample_count=cast(int, row.get("sample_count")),
                    window_seconds=cast(int, row.get("window_seconds")),
                    error_rate_ppm=cast(int, row.get("error_rate_ppm")),
                    latency_p95_milliseconds=cast(
                        int, row.get("latency_p95_milliseconds")
                    ),
                    health_failure_count=cast(int, row.get("health_failure_count")),
                    critical_alert_count=cast(int, row.get("critical_alert_count")),
                    kill_switch_triggered=cast(bool, row.get("kill_switch_triggered")),
                    external_action_count=0,
                )
            )
        except TypeError, ValueError:
            _fail("SCENARIO_INVALID", "scenario")
    return tuple(output)


def execute_local_production_canary_step(
    *,
    repository_root: Path,
    private_root: Path,
    run_id: str,
    idempotency_key: str,
    command: CanaryCommandKind,
    observation: SyntheticObservation | None,
    commit_fault_once: CommitFault = CommitFault.NONE,
) -> LocalProductionCanaryRunReceipt:
    spec = load_local_production_canary_spec(repository_root)
    journal = RecordedProductionCanaryJournal(
        private_root=private_root,
        commit_fault_once=commit_fault_once,
    )
    service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=journal,
    )
    return service.execute(
        LocalProductionCanaryRun(
            run_id=run_id,
            idempotency_key=idempotency_key,
            command=command,
            observation=observation,
        )
    )


def _receipt_document(receipt: LocalProductionCanaryRunReceipt) -> dict[str, object]:
    return {
        "schema": "RAOS_LOCAL_PRODUCTION_CANARY_RUN_RECEIPT_V2",
        "result": receipt.result_document,
        "persistence": {
            "run_id": receipt.persistence.run_id,
            "current_version": receipt.persistence.current_version,
            "request_sha256": receipt.persistence.request_sha256,
            "result_sha256": receipt.persistence.result_sha256,
            "sequence": receipt.persistence.sequence,
            "previous_entry_sha256": receipt.persistence.previous_entry_sha256,
            "entry_sha256": receipt.persistence.entry_sha256,
            "replayed": receipt.persistence.replayed,
            "recovered_after_commit_ambiguity": receipt.recovered_after_commit_ambiguity,
        },
        "external_actions": 0,
        "formal_tst_032": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }


def _default_repository_root() -> Path:
    return Path(__file__).absolute().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one ST-1506 offline synthetic canary step."
    )
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument(
        "--command",
        required=True,
        choices=[item.value for item in CanaryCommandKind],
    )
    parser.add_argument("--scenario", type=int)
    arguments = parser.parse_args(argv)
    root = _default_repository_root()
    spec = load_local_production_canary_spec(root)
    observations = recorded_observations(root, spec)
    observation: SyntheticObservation | None = None
    scenario = cast(int | None, arguments.scenario)
    if scenario is not None:
        if scenario < 0 or scenario >= len(observations):
            parser.error("scenario index out of range")
        observation = observations[scenario]
    receipt = execute_local_production_canary_step(
        repository_root=root,
        private_root=arguments.private_root,
        run_id=arguments.run_id,
        idempotency_key=arguments.idempotency_key,
        command=CanaryCommandKind(arguments.command),
        observation=observation,
    )
    print(canonical_bytes(_receipt_document(receipt)).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "execute_local_production_canary_step",
    "load_local_production_canary_spec",
    "main",
    "recorded_observations",
]
