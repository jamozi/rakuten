"""Explicit offline runner for the ST-1505 local admission simulator."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken

from raos.adapters.disabled_deployment_identity import (
    DisabledDeploymentIdentityActivation,
)
from raos.adapters.recorded_staging_admission import (
    RecordedStagingAdmissionJournal,
)
from raos.application.ops.staging_admission import (
    LocalStagingAdmissionRun,
    LocalStagingAdmissionRunReceipt,
    LocalStagingAdmissionService,
)
from raos.domain.ops.staging_admission import (
    LocalStagingAdmissionSpec,
    StagingAdmissionError,
    canonical_bytes,
)


_CONTRACT_RELATIVE_PATH = Path(
    "changes/st-1505/contracts/local-staging-admission-runtime.v2.yaml"
)
_MAX_CONTRACT_BYTES = 262_144


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
    raise StagingAdmissionError(code, field)


def _read_closed_yaml(path: Path) -> Mapping[str, object]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("CONTRACT_READ_FAILED", "contract")
    if not raw or len(raw) > _MAX_CONTRACT_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        _fail("CONTRACT_BYTES_INVALID", "contract")
    try:
        text = raw.decode("utf-8", errors="strict")
        scan = cast(Callable[[str], Sequence[object]], getattr(yaml, "scan"))
        for token in scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_EXTENSION_FORBIDDEN", "contract")
        document = cast(object, yaml.load(text, Loader=_ClosedLoader))
    except StagingAdmissionError:
        raise
    except UnicodeDecodeError, yaml.YAMLError:
        _fail("CONTRACT_PARSE_FAILED", "contract")
    if type(document) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    raw_document = cast(dict[object, object], document)
    if any(type(key) is not str for key in raw_document):
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    return cast(Mapping[str, object], document)


def _repository_path(repository_root: Path, uri: object) -> Path:
    if type(uri) is not str or not uri.startswith("repo://"):
        _fail("REPOSITORY_URI_INVALID", "binding.uri")
    relative = PurePosixPath(uri.removeprefix("repo://"))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        _fail("REPOSITORY_URI_INVALID", "binding.uri")
    candidate = repository_root.joinpath(*relative.parts)
    cursor = repository_root
    try:
        root_metadata = repository_root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(
            root_metadata.st_mode
        ):
            _fail("REPOSITORY_ROOT_INVALID", "repository_root")
        for part in relative.parts:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                _fail("REPOSITORY_PATH_INVALID", "binding.path")
        if not stat.S_ISREG(candidate.lstat().st_mode):
            _fail("REPOSITORY_PATH_INVALID", "binding.path")
    except StagingAdmissionError:
        raise
    except OSError:
        _fail("REPOSITORY_PATH_INVALID", "binding.path")
    return candidate


def _verify_binding(repository_root: Path, *, uri: object, digest: object) -> None:
    if type(digest) is not str or len(digest) != 64:
        _fail("BINDING_DIGEST_INVALID", "binding.sha256")
    path = _repository_path(repository_root, uri)
    try:
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("BINDING_READ_FAILED", "binding")
    if observed != digest:
        _fail("BINDING_DIGEST_MISMATCH", "binding")


def _validate_repository_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    normalized = Path(os.path.abspath(value))
    if value != normalized:
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    cursor = Path(normalized.anchor)
    try:
        for part in normalized.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    except StagingAdmissionError:
        raise
    except OSError:
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    return normalized


def load_local_staging_admission_spec(
    repository_root: object,
) -> LocalStagingAdmissionSpec:
    """Load the fixed contract and verify every predecessor source byte."""

    normalized = _validate_repository_root(repository_root)
    contract_path = _repository_path(
        normalized, f"repo://{_CONTRACT_RELATIVE_PATH.as_posix()}"
    )
    document = _read_closed_yaml(contract_path)
    predecessors = document.get("predecessor_bindings")
    if type(predecessors) is not dict:
        _fail("PREDECESSOR_BINDING_INVALID", "predecessors")
    for raw in cast(dict[object, object], predecessors).values():
        if type(raw) is not dict:
            _fail("PREDECESSOR_BINDING_INVALID", "predecessor")
        row = cast(dict[object, object], raw)
        _verify_binding(
            normalized,
            uri=row.get("contract_uri"),
            digest=row.get("contract_sha256"),
        )
        _verify_binding(
            normalized,
            uri=row.get("reference_plan_uri"),
            digest=row.get("reference_plan_sha256"),
        )
    identity = document.get("identity_boundary")
    if type(identity) is not dict:
        _fail("IDENTITY_BINDING_INVALID", "identity")
    identity_row = cast(dict[object, object], identity)
    for uri_field, digest_field in (
        ("source_manifest_uri", "source_manifest_sha256"),
        ("source_activation_port_uri", "source_activation_port_sha256"),
        ("evaluation_fixture_uri", "evaluation_fixture_sha256"),
    ):
        _verify_binding(
            normalized,
            uri=identity_row.get(uri_field),
            digest=identity_row.get(digest_field),
        )
    return LocalStagingAdmissionSpec.from_document(document)


def execute_local_staging_admission(
    *,
    repository_root: Path,
    private_root: Path,
    run_id: str,
    idempotency_key: str,
    simulate_commit_ambiguity_once: bool = False,
) -> LocalStagingAdmissionRunReceipt:
    """Run the simulator without any external action or selected target."""

    spec = load_local_staging_admission_spec(repository_root)
    journal = RecordedStagingAdmissionJournal(
        private_root=private_root,
        simulate_commit_ambiguity_once=simulate_commit_ambiguity_once,
    )
    service = LocalStagingAdmissionService(
        spec=spec,
        activation=DisabledDeploymentIdentityActivation(),
        journal=journal,
    )
    return service.execute(
        LocalStagingAdmissionRun(
            run_id=run_id,
            idempotency_key=idempotency_key,
        )
    )


def _receipt_document(receipt: LocalStagingAdmissionRunReceipt) -> dict[str, object]:
    return {
        "schema": "RAOS_LOCAL_STAGING_ADMISSION_RUN_RECEIPT_V2",
        "result": receipt.result_document,
        "persistence": {
            "run_id": receipt.persistence.run_id,
            "idempotency_key_sha256": receipt.persistence.idempotency_key_sha256,
            "request_sha256": receipt.persistence.request_sha256,
            "result_sha256": receipt.persistence.result_sha256,
            "sequence": receipt.persistence.sequence,
            "previous_entry_sha256": receipt.persistence.previous_entry_sha256,
            "entry_sha256": receipt.persistence.entry_sha256,
            "replayed": receipt.persistence.replayed,
            "recovered_after_commit_ambiguity": receipt.recovered_after_commit_ambiguity,
        },
        "external_actions": 0,
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }


def _default_repository_root() -> Path:
    return Path(__file__).absolute().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the ST-1505 offline recorded local admission simulator."
    )
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument(
        "--simulate-commit-ambiguity-once",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    arguments = parser.parse_args(argv)
    receipt = execute_local_staging_admission(
        repository_root=_default_repository_root(),
        private_root=arguments.private_root,
        run_id=arguments.run_id,
        idempotency_key=arguments.idempotency_key,
        simulate_commit_ambiguity_once=arguments.simulate_commit_ambiguity_once,
    )
    print(canonical_bytes(_receipt_document(receipt)).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "execute_local_staging_admission",
    "load_local_staging_admission_spec",
    "main",
]
