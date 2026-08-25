#!/usr/bin/env python3
"""Build the disabled recorded ST-0706 durable AI job queue artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import re
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0706/contracts/durable-ai-job-queue.v2.yaml")
PLAN_PATH: Final = Path("changes/st-0706/generated/durable-ai-job-queue.v2.json")
MANIFEST_PATH: Final = Path("changes/st-0706/manifest.yaml")
GENERATED_PATHS: Final = (PLAN_PATH, MANIFEST_PATH)
EXPECTED_CONTRACT_SHA256: Final = (
    "a8abc40d249529601d5026ed4c8a6cda6478a0465500003166e216e04ed47b30"
)
EXPECTED_POLICY_SHA256: Final = (
    "f4d7c6bacfbbc8c104d2e4cbd1700d87d946191b789c7967183a1c4b9186d5a8"
)
HARDENED_WRITER_PATH: Final = Path("scripts/secure_generated_publication.py")
HARDENED_WRITER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file "
    "--no-python-downloads python scripts/build_st0706_durable_ai_job_queue.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
MAXIMUM_CONTRACT_BYTES: Final = 262_144
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z")

PINNED_SOURCE_BINDINGS: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/upstream/key_documents/RAOS_01_requirements_catalog_v0.1.yaml": (
        "bd4398da2aa73008b7332d2403e7a2e290b7bf1dd77df7bd7e7fd44bb3620827"
    ),
    "docs/upstream/key_documents/RAOS_05_ai_agent_prompt_routing_evaluation_design_v0.1.md": (
        "475e4b6b4490110fd9f94a07aaf4cf979bea99d59b7ef8b95ba0fdbe61219476"
    ),
    "docs/upstream/key_documents/RAOS_05_ai_task_catalog_v0.1.yaml": (
        "8b5a0d820f0a6180dd0bbbd050553114c22efe499a553d72bbdb24ffc8483c04"
    ),
    "changes/st-0303/contracts/iam-ops-schema.v1.yaml": (
        "6f04e1f773c4234587d3ace990d16ece8314e3186ce4338547f8684fdd225f01"
    ),
    "python/raos/domain/ai/routing.py": (
        "884ce44d875339d9cd7f88e896d5779b2eac3154a5af39d3238748acc144924e"
    ),
    "changes/st-0705/contracts/ai-output-validation-runtime.v1.yaml": (
        "25e8696211025ee2581b0318ca2758dbcd4dccccd37447be1e8ad84667dbb02d"
    ),
    "changes/st-0004/contracts/ai/RAOS_05_failure_taxonomy_v0.1.yaml": (
        "55db49d67678a1d8052fd4da9035ebfe2516913659c528bccd9f1a0313b38504"
    ),
    "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-requested-v1.schema.json": (
        "9937ac30df245d120ccf06aaaf406a8b29cdc9773307e9c9c61d9fc025abd42c"
    ),
    "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-succeeded-v1.schema.json": (
        "670dbd4036129bb41284eafa6fb8809b260593f9aab4bc270384509d41d2057a"
    ),
    "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-failed-v1.schema.json": (
        "5cb07491fe735a9e1724b7539f50763928a32befb96627d642c1ad30e39fa2c7"
    ),
    "python/raos/domain/ai/job_orchestration.py": (
        "5ef0e0d90f5bb07257d4a9d27829647dd07ced443310f9ba5bc6fed8fc7d97c2"
    ),
}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0706/README.md"),
    Path("changes/st-0706/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("scripts/build_st0706_durable_ai_job_queue.py"),
    HARDENED_WRITER_PATH,
    Path("python/raos/domain/ai/job_orchestration.py"),
    Path("python/raos/ports/ai_job_orchestration.py"),
    Path("python/raos/application/ai/job_orchestration.py"),
    Path("python/raos/adapters/recorded_ai_job_orchestration.py"),
    Path("python/raos/domain/ai/durable_job_queue_v2.py"),
    Path("python/raos/ports/durable_ai_job_queue_v2.py"),
    Path("python/raos/application/ai/durable_job_queue_v2.py"),
    Path("python/raos/adapters/recorded_durable_ai_job_queue_v2.py"),
    Path("tests/st0706/conftest.py"),
    Path("tests/st0706/test_boundaries.py"),
    Path("tests/st0706/test_failure_isolation.py"),
    Path("tests/st0706/test_orchestration.py"),
    Path("tests/st0706/test_durable_queue_v2.py"),
    Path("tests/st0706/test_durable_queue_v2_negative.py"),
    Path("tests/st0706/test_durable_queue_v2_boundaries.py"),
    Path("tests/st0706/test_durable_queue_v2_generation.py"),
)


class DurableQueueBuildError(RuntimeError):
    """Closed generator failure with no source or parser material."""

    __slots__ = ("code", "field")

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise DurableQueueBuildError(code, field) from None


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    construct = cast(
        Callable[[object, bool], object], getattr(loader, "construct_object")
    )
    for key_node, value_node in node.value:
        key = construct(cast(object, key_node), deep)
        try:
            duplicate = key in mapping
        except TypeError:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from None
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate key",
                key_node.start_mark,
            ) from None
        mapping[key] = construct(cast(object, value_node), deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _regular_file(path: Path, field: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("SOURCE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_NOT_REGULAR", field)
    return path


def _read_bytes(root: Path, relative: Path, field: str) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_SOURCE_PATH", field)
    path = _regular_file(root / relative, field)
    try:
        return path.read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE", field)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_sha256(value: object) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    )


def _exact_mapping(
    value: object, *, keys: frozenset[str], field: str
) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", field)
    raw = cast(dict[object, object], value)
    if frozenset(raw) != keys or not all(type(key) is str for key in raw):
        _fail("CONTRACT_SHAPE_INVALID", field)
    return cast(Mapping[str, object], raw)


def _typed_mapping(value: object, *, code: str, field: str) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(code, field)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail(code, field)
    return cast(Mapping[str, object], raw)


def _load_contract(root: Path) -> Mapping[str, object]:
    raw = _read_bytes(root, CONTRACT_PATH, "contract")
    if not raw or len(raw) > MAXIMUM_CONTRACT_BYTES:
        _fail("CONTRACT_SIZE_INVALID", "contract")
    if _sha256(raw) != EXPECTED_CONTRACT_SHA256:
        _fail("CONTRACT_HASH_DRIFT", "contract")
    try:
        text = raw.decode("utf-8", errors="strict")
        scan = cast(Callable[[str], Sequence[object]], getattr(yaml, "scan"))
        tokens = tuple(scan(text))
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("CONTRACT_YAML_FEATURE_FORBIDDEN", "contract")
        loaded = cast(object, yaml.load(text, Loader=UniqueKeyLoader))
    except DurableQueueBuildError:
        raise
    except UnicodeDecodeError, yaml.YAMLError, RecursionError:
        _fail("CONTRACT_PARSE_FAILED", "contract")
    return _exact_mapping(
        loaded,
        keys=frozenset(
            {
                "document",
                "authority",
                "source_bindings",
                "recorded_policy",
                "state_machine",
                "durability_boundary",
                "outbox_boundary",
                "security_controls",
                "safe_defaults",
                "verification_boundary",
            }
        ),
        field="contract",
    )


def _validate_contract(root: Path, contract: Mapping[str, object]) -> None:
    document = _exact_mapping(
        contract["document"],
        keys=frozenset(
            {
                "id",
                "version",
                "story_id",
                "status",
                "classification",
                "enabled_by_default",
                "authority",
                "production_eligible",
                "publication_authorized",
            }
        ),
        field="document",
    )
    expected_document = {
        "id": "RAOS-ST0706-DURABLE-AI-JOB-QUEUE-002",
        "version": "2.0.0",
        "story_id": "ST-0706",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "RECORDED_SYNTHETIC_DURABLE_STATE_CONTRACT",
        "enabled_by_default": False,
        "authority": "NONE",
        "production_eligible": False,
        "publication_authorized": False,
    }
    if dict(document) != expected_document:
        _fail("CONTRACT_VALUE_INVALID", "document")
    authority = _typed_mapping(
        contract["authority"], code="GENERIC_OWNER_INVALID", field="authority"
    )
    policy = _typed_mapping(
        contract["recorded_policy"],
        code="CONTRACT_VALUE_INVALID",
        field="recorded_policy",
    )
    durability = _typed_mapping(
        contract["durability_boundary"],
        code="DURABILITY_BOUNDARY_INVALID",
        field="durability_boundary",
    )
    outbox = _typed_mapping(
        contract["outbox_boundary"],
        code="OUTBOX_BOUNDARY_INVALID",
        field="outbox_boundary",
    )
    safe_defaults = _typed_mapping(
        contract["safe_defaults"],
        code="SAFE_DEFAULT_INVALID",
        field="safe_defaults",
    )
    if authority.get("generic_runtime_owner") != "ST-1404":
        _fail("GENERIC_OWNER_INVALID", "authority")
    policy_values = dict(policy)
    policy_sha256 = policy_values.pop("policy_sha256", None)
    if policy_values != {
        "policy_id": "st-0706.recorded-durable-ai-job-queue.v2",
        "state_schema_version": 2,
        "allowed_environments": ["ENV-DEV", "ENV-CI"],
        "queue_capacity": 32,
        "maximum_state_bytes": 1048576,
        "maximum_outbox_intents": 128,
        "maximum_completion_receipts_per_job": 3,
        "maximum_attempts_cap": 3,
        "lease_duration_seconds": 30,
        "retry_backoff_seconds_after_attempt": [7, 31],
        "retry_backoff_strictly_increasing": True,
        "maximum_cumulative_retry_backoff_seconds": 38,
        "clock_source": "CALLER_SUPPLIED_EXPLICIT_UTC",
        "retryable_provider_failure_classes": [
            "RATE_LIMIT",
            "TRANSIENT_ERROR",
            "TIMEOUT",
            "MODEL_UNAVAILABLE",
        ],
        "lease_expiry_disposition": "QUARANTINED",
        "unknown_cost_disposition": "QUARANTINED",
        "cost_overrun_disposition": "QUARANTINED",
        "automatic_redrive": False,
        "automatic_loop": False,
        "sleep": False,
        "jitter_runtime_selection": False,
        "note": "Delays are exact recorded fixture data, not Production policy or OD-009 resolution.",
    } or not (
        policy_sha256 == EXPECTED_POLICY_SHA256
        and _canonical_json_sha256(policy_values) == EXPECTED_POLICY_SHA256
    ):
        _fail("CONTRACT_VALUE_INVALID", "recorded_policy")
    if durability.get("storage") != "CALLER_OWNED_CAS_ATOMIC_PORT":
        _fail("DURABILITY_BOUNDARY_INVALID", "durability_boundary")
    if outbox.get("dispatch") != "NOT_IMPLEMENTED":
        _fail("OUTBOX_BOUNDARY_INVALID", "outbox_boundary")
    if safe_defaults.get("activation") != "DISABLED":
        _fail("SAFE_DEFAULT_INVALID", "safe_defaults")
    bindings_value = contract["source_bindings"]
    if type(bindings_value) is not list:
        _fail("SOURCE_BINDING_INVENTORY_INVALID", "source_bindings")
    bindings = cast(list[object], bindings_value)
    if len(bindings) != len(PINNED_SOURCE_BINDINGS):
        _fail("SOURCE_BINDING_INVENTORY_INVALID", "source_bindings")
    observed: dict[str, str] = {}
    for index, value in enumerate(bindings):
        if type(value) is not dict:
            _fail("SOURCE_BINDING_SHAPE_INVALID", f"source_bindings[{index}]")
        raw_binding = cast(dict[object, object], value)
        if set(raw_binding) != {
            "path",
            "sha256",
            "owner",
            "role",
        } or not all(type(key) is str for key in raw_binding):
            _fail("SOURCE_BINDING_SHAPE_INVALID", f"source_bindings[{index}]")
        binding = cast(Mapping[str, object], raw_binding)
        path = binding["path"]
        digest = binding["sha256"]
        if (
            type(path) is not str
            or type(digest) is not str
            or SHA256_PATTERN.fullmatch(digest) is None
        ):
            _fail("SOURCE_BINDING_VALUE_INVALID", f"source_bindings[{index}]")
        if path in observed:
            _fail("SOURCE_BINDING_DUPLICATE", f"source_bindings[{index}]")
        observed[path] = digest
    if observed != PINNED_SOURCE_BINDINGS:
        _fail("SOURCE_BINDING_DRIFT", "source_bindings")
    for path, expected in PINNED_SOURCE_BINDINGS.items():
        if _sha256(_read_bytes(root, Path(path), "source_binding")) != expected:
            _fail("PINNED_SOURCE_HASH_MISMATCH", "source_binding")
    _validate_runtime_contract_binding(root)


def _validate_runtime_contract_binding(root: Path) -> None:
    path = Path("python/raos/domain/ai/durable_job_queue_v2.py")
    raw = _read_bytes(root, path, "runtime_contract_binding")
    try:
        tree = ast.parse(raw.decode("utf-8", errors="strict"), filename=path.as_posix())
    except UnicodeDecodeError, SyntaxError:
        _fail("RUNTIME_PARSE_FAILED", "runtime_contract_binding")
    values: dict[str, list[object]] = {
        "CONTRACT_SHA256": [],
        "POLICY_SHA256": [],
    }
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {
            target.id
            for target in node.targets
            if isinstance(target, ast.Name) and target.id in values
        }
        for name in names:
            try:
                values[name].append(ast.literal_eval(node.value))
            except ValueError, TypeError:
                _fail("RUNTIME_CONTRACT_BINDING_INVALID", "runtime_contract_binding")
    if values != {
        "CONTRACT_SHA256": [EXPECTED_CONTRACT_SHA256],
        "POLICY_SHA256": [EXPECTED_POLICY_SHA256],
    }:
        _fail("RUNTIME_CONTRACT_BINDING_INVALID", "runtime_contract_binding")


def _source_hashes(root: Path) -> dict[str, str]:
    if len(set(SOURCE_ARTIFACT_PATHS)) != len(SOURCE_ARTIFACT_PATHS):
        _fail("SOURCE_INVENTORY_DUPLICATE", "source_artifacts")
    return {
        path.as_posix(): _sha256(_read_bytes(root, path, "source_artifacts"))
        for path in SOURCE_ARTIFACT_PATHS
    }


def _plan_bytes(
    contract: Mapping[str, object], source_hashes: Mapping[str, str]
) -> bytes:
    _typed_mapping(
        contract["document"], code="CONTRACT_SHAPE_INVALID", field="document"
    )
    policy = _typed_mapping(
        contract["recorded_policy"],
        code="CONTRACT_SHAPE_INVALID",
        field="recorded_policy",
    )
    plan: dict[str, object] = {
        "document_id": "RAOS-ST0706-DURABLE-AI-JOB-QUEUE-PLAN-002",
        "version": "2.0.0",
        "story_id": "ST-0706",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "authority": "NONE",
        "enabled": False,
        "executable": False,
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "policy": dict(policy),
        "state_machine": contract["state_machine"],
        "durability_boundary": contract["durability_boundary"],
        "outbox_boundary": contract["outbox_boundary"],
        "safe_defaults": contract["safe_defaults"],
        "source_bindings": contract["source_bindings"],
        "owner_source_sha256": dict(source_hashes),
        "generation": {
            "command": GENERATION_COMMAND,
            "check_command": CHECK_COMMAND,
            "generated_paths": [path.as_posix() for path in GENERATED_PATHS],
        },
        "formal_and_external": contract["verification_boundary"],
    }
    return (
        json.dumps(
            plan,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8", errors="strict")


def _manifest_bytes(source_hashes: Mapping[str, str], plan_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0706-DURABLE-AI-JOB-QUEUE-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-0706",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "authority": "NONE",
            "production_eligible": False,
        },
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "source_sha256": dict(source_hashes),
        "generated_sha256": {PLAN_PATH.as_posix(): _sha256(plan_bytes)},
        "generation": {
            "command": GENERATION_COMMAND,
            "check_command": CHECK_COMMAND,
        },
        "bounds": {
            "generic_runtime_owner": "ST-1404",
            "persistence": "CALLER_OWNED_CAS_ATOMIC_PORT",
            "adapter": "RECORDED_BYTES_AND_REVISION_ONLY",
            "provider": False,
            "network": False,
            "credentials": False,
            "event_dispatch": False,
            "publication": False,
            "staging": False,
            "release": False,
            "production": False,
        },
        "formal_tst_013": "NOT_EXECUTED",
        "formal_tst_017": "NOT_EXECUTED",
    }
    return yaml.safe_dump(
        manifest,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8", errors="strict")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = _load_contract(root)
    _validate_contract(root, contract)
    source_hashes = _source_hashes(root)
    plan = _plan_bytes(contract, source_hashes)
    return {PLAN_PATH: plan, MANIFEST_PATH: _manifest_bytes(source_hashes, plan)}


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    pure = PurePosixPath(relative.as_posix())
    if (
        relative.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != relative.as_posix()
    ):
        _fail("UNSAFE_OUTPUT_PATH", "output")
    current = root.resolve(strict=True)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            try:
                current.mkdir(mode=0o755)
                metadata = current.lstat()
            except OSError:
                _fail("OUTPUT_DIRECTORY_FAILED", "output")
        except OSError:
            _fail("OUTPUT_DIRECTORY_FAILED", "output")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
    return current


def _hardened_writer_module(root: Path) -> Any:
    raw = _read_bytes(root, HARDENED_WRITER_PATH, "hardened_writer")
    if _sha256(raw) != HARDENED_WRITER_SHA256:
        _fail("HARDENED_WRITER_HASH_MISMATCH", "hardened_writer")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        module = importlib.import_module("scripts.secure_generated_publication")
        module_file = module.__file__
        if type(module_file) is not str:
            _fail("HARDENED_WRITER_UNAVAILABLE", "hardened_writer")
        module_path = Path(module_file).resolve(strict=True)
    except ImportError, AttributeError, OSError, TypeError:
        _fail("HARDENED_WRITER_UNAVAILABLE", "hardened_writer")
    if module_path != (root / HARDENED_WRITER_PATH).resolve(strict=True):
        _fail("HARDENED_WRITER_ORIGIN_MISMATCH", "hardened_writer")
    return module


def _replace_generated(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    writer = _hardened_writer_module(root)
    replacement = getattr(writer, "publish_generated", None)
    if not callable(replacement):
        _fail("HARDENED_WRITER_UNAVAILABLE", "hardened_writer")
    try:
        replacement(
            artifacts,
            namespace="st0706-v2",
            maximum_payload_bytes=4 * 1024 * 1024,
        )
    except BaseException as failure:
        writer_failure = getattr(writer, "SecurePublicationError", None)
        if isinstance(writer_failure, type) and isinstance(failure, writer_failure):
            _fail("OUTPUT_TRANSACTION_FAILED", "output")
        raise


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = _safe_output_parent(root, relative, create=False) / relative.name
        _regular_file(path, "generated_output")
        try:
            actual = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative] or mode != 0o644:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    artifacts = tuple(
        (
            _safe_output_parent(root, relative, create=False) / relative.name,
            outputs[relative],
        )
        for relative in GENERATED_PATHS
    )
    _replace_generated(root, artifacts)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build disabled recorded ST-0706 durable queue artifacts."
    )
    parser.add_argument(
        "--check", action="store_true", help="verify generated bytes without writes"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except DurableQueueBuildError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    print(
        "ST-0706 durable queue check passed"
        if args.check
        else "ST-0706 durable queue artifacts generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
