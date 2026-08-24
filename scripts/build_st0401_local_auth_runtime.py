#!/usr/bin/env python3
"""Build the disabled, recorded-only ST-0401 local authentication contract.

The owner consumes only repository files, performs no network or credential
access, and publishes two deterministic JSON artifacts through the shared
foreign-preserving transaction helper.  It does not register an HTTP route or
turn the recorded adapter into an external authentication surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType
from typing import Any, Final, NoReturn, cast


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import secure_generated_publication  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 2 * 1024 * 1024

CONTRACT_PATH: Final = Path("changes/st-0401/contracts/local-auth-runtime.v2.json")
RUNTIME_PATH: Final = Path("changes/st-0401/generated/local-auth-runtime.v2.json")
MANIFEST_PATH: Final = Path(
    "changes/st-0401/generated/local-auth-runtime-manifest.v2.json"
)
GENERATOR_PATH: Final = Path("scripts/build_st0401_local_auth_runtime.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
GENERATED_PATHS: Final = (RUNTIME_PATH, MANIFEST_PATH)

EXPECTED_CONTRACT_SHA256: Final = (
    "6f91b6619b318e954a7f5b1ef996918755ed8cbd412f4cda7050bb17ab0cdaad"
)
EXPECTED_SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
CANONICAL_BINDINGS: Final = MappingProxyType(
    {
        Path(
            "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
        ): "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
        Path(
            "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
        ): "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        Path(
            "docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"
        ): "dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050",
        Path(
            "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
        ): "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        Path(
            "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
        ): "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
        Path(
            "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ): "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
        Path(
            "changes/st-0308/contracts/persistence-runtime.v2.yaml"
        ): "8ee74a13fd1232f86887e988cbeb475421f2ed17c6a73257968e62ecc0dc54c7",
    }
)
OWNED_IMPLEMENTATION_PATHS: Final = (
    Path("python/raos/domain/iam/authentication.py"),
    Path("python/raos/ports/oidc.py"),
    Path("python/raos/application/iam/authentication.py"),
    Path("python/raos/adapters/development_oidc.py"),
    Path("python/raos/adapters/recorded_authentication.py"),
    Path("python/raos/adapters/disabled_admin_auth_http.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    SECURE_HELPER_PATH,
    *OWNED_IMPLEMENTATION_PATHS,
    *CANONICAL_BINDINGS,
)


class LocalAuthRuntimeGenerationError(ValueError):
    """Sanitized generation failure with a closed reason code."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise LocalAuthRuntimeGenerationError(code) from None


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
    ):
        _fail("GENERATION_TOOLCHAIN_DRIFT")


def _validate_relative(relative: Path) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_PATH")


def _validate_directory(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("SOURCE_ANCESTOR_INVALID")


def _validate_regular(metadata: os.stat_result, *, maximum: int) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_nlink != 1
        or metadata.st_size > maximum
    ):
        _fail("SOURCE_IDENTITY_INVALID")


def _read_regular(
    root: Path,
    relative: Path,
    *,
    maximum: int = MAX_SOURCE_BYTES,
) -> bytes:
    _validate_relative(relative)
    if type(maximum) is not int or maximum < 0:
        _fail("SOURCE_LIMIT_INVALID")
    absolute_root = Path(os.path.abspath(root))
    try:
        root_metadata = absolute_root.lstat()
    except OSError:
        _fail("SOURCE_ROOT_INVALID")
    _validate_directory(root_metadata)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        current = os.open(absolute_root, flags | os.O_DIRECTORY)
        descriptors.append(current)
        if os.fstat(current)[:3] != root_metadata[:3]:
            _fail("SOURCE_ROOT_CHANGED")
        for component in relative.parts[:-1]:
            before = os.stat(component, dir_fd=current, follow_symlinks=False)
            _validate_directory(before)
            child = os.open(component, flags | os.O_DIRECTORY, dir_fd=current)
            descriptors.append(child)
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino, opened.st_mode) != (
                before.st_dev,
                before.st_ino,
                before.st_mode,
            ):
                _fail("SOURCE_ANCESTOR_CHANGED")
            current = child
        before_file = os.stat(
            relative.name,
            dir_fd=current,
            follow_symlinks=False,
        )
        _validate_regular(before_file, maximum=maximum)
        descriptor = os.open(
            relative.name,
            flags | os.O_NONBLOCK,
            dir_fd=current,
        )
        descriptors.append(descriptor)
        opened_file = os.fstat(descriptor)
        before_identity = (
            before_file.st_dev,
            before_file.st_ino,
            before_file.st_mode,
            before_file.st_uid,
            before_file.st_gid,
            before_file.st_nlink,
            before_file.st_size,
            before_file.st_mtime_ns,
        )
        opened_identity = (
            opened_file.st_dev,
            opened_file.st_ino,
            opened_file.st_mode,
            opened_file.st_uid,
            opened_file.st_gid,
            opened_file.st_nlink,
            opened_file.st_size,
            opened_file.st_mtime_ns,
        )
        if opened_identity != before_identity:
            _fail("SOURCE_IDENTITY_CHANGED")
        remaining = opened_file.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail("SOURCE_READ_TRUNCATED")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail("SOURCE_READ_GREW")
        if os.fstat(descriptor).st_mtime_ns != opened_file.st_mtime_ns:
            _fail("SOURCE_IDENTITY_CHANGED")
        return b"".join(chunks)
    except LocalAuthRuntimeGenerationError:
        raise
    except OSError:
        _fail("SOURCE_READ_FAILED")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("CONTRACT_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    _fail("CONTRACT_NONFINITE_NUMBER")


def _parse_contract(payload: bytes) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8", errors="strict")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate,
            parse_constant=_reject_constant,
        )
    except UnicodeError, json.JSONDecodeError:
        _fail("CONTRACT_INVALID")
    if type(parsed) is not dict:
        _fail("CONTRACT_INVALID")
    return cast(dict[str, Any], parsed)


def _validate_contract(contract: dict[str, Any]) -> None:
    if set(contract) != {
        "schema_version",
        "story_id",
        "status",
        "dependencies",
        "open_decision",
        "runtime",
        "debt_resolution",
        "authority",
        "verification",
    }:
        _fail("CONTRACT_SHAPE_INVALID")
    if (
        contract["schema_version"] != 2
        or contract["story_id"] != "ST-0401"
        or contract["status"] != "LOCAL_CODE_COMPLETE"
        or contract["dependencies"] != ["ST-0103", "ST-0204"]
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    decision = contract["open_decision"]
    if type(decision) is not dict or decision != {
        "id": "OD-010",
        "status": "HUMAN_DECISION_REQUIRED",
        "safe_default": "LOCAL_FAKE_DEVELOPMENT_ONLY_EXTERNAL_PUBLICATION_FORBIDDEN",
        "provider_selection": "UNSELECTED",
    }:
        _fail("OPEN_DECISION_BOUNDARY_INVALID")
    runtime = contract["runtime"]
    if type(runtime) is not dict or set(runtime) != {
        "environment",
        "provider_adapter",
        "provider_sdk",
        "credential_resolution",
        "external_provider_calls",
        "transport",
        "authorization",
        "session",
        "persistence",
    }:
        _fail("RUNTIME_BOUNDARY_INVALID")
    transport = runtime["transport"]
    persistence = runtime["persistence"]
    if (
        runtime["environment"] != "ENV-DEV"
        or runtime["provider_adapter"] != "RECORDED_FAKE_NO_NETWORK"
        or runtime["provider_sdk"] != "ABSENT"
        or runtime["credential_resolution"] != "ABSENT"
        or runtime["external_provider_calls"] is not False
        or type(transport) is not dict
        or transport["route_registration"] is not False
        or transport["external_dispatch"] != "UNCONDITIONAL_RFC9457_503_REFUSAL"
        or transport["recorded_origin"]
        != "HTTP_EXACT_IPV4_LOOPBACK_WITH_UNPRIVILEGED_PORT"
        or transport["cookie_delivery"] != "UNSELECTED_NOT_DELIVERED"
        or transport["bearer_delivery"] != "UNSELECTED_NOT_DELIVERED"
        or transport["browser_storage"] != "UNSELECTED_NOT_DELIVERED"
        or type(transport["recorded_external_action_count"]) is not int
        or transport["recorded_external_action_count"] != 0
        or type(persistence) is not dict
        or persistence["external_io_inside_transaction"] is not False
        or persistence["migration_or_production_schema_authority"] is not False
        or persistence["unknown_commit"]
        != "STORAGE_COMMIT_UNKNOWN_THEN_READ_ONLY_RESOLUTION"
        or persistence["database"] != "SQLITE_FIXED_FILENAME_CREATED_ONLY_NO_CALLER_SQL"
        or persistence["schema"] != "EXACT_V2_STRICT_FOREIGN_KEYS_APPEND_ONLY_TRIGGERS"
        or persistence["file_identity"]
        != "OWNER_PRIVATE_MODE_0600_PINNED_DEVICE_AND_INODE"
        or persistence["record_integrity"]
        != "FULL_REVISION_HISTORY_AND_LINEAR_COMMAND_SHA256_CHAIN"
        or persistence["canonical_encoding"]
        != "COMPACT_UTF8_SORTED_JSON_AND_RFC3339_UTC_Z"
        or persistence["rotation_recovery_source"]
        != "EXACT_DURABLE_COMMAND_INTENT_AND_RESULT_ONLY"
        or persistence["rollback_detection"]
        != "PROCESS_LIFETIME_COUNT_HEAD_PREFIX_ANCHOR"
        or persistence["cross_restart_trusted_anchor"] != "ABSENT_NOT_CLAIMED"
    ):
        _fail("RUNTIME_BOUNDARY_INVALID")
    authority = contract["authority"]
    if (
        type(authority) is not dict
        or not authority
        or any(type(value) is not bool or value for value in authority.values())
    ):
        _fail("AUTHORITY_BOUNDARY_INVALID")
    verification = contract["verification"]
    if (
        type(verification) is not dict
        or verification.get("local_focused") != "EXECUTABLE"
        or any(
            verification.get(key) != "NOT_EXECUTED"
            for key in (
                "formal_tst_012",
                "formal_tst_022",
                "formal_tst_026",
                "browser",
                "hosted_ci",
                "staging",
                "release",
                "production",
            )
        )
    ):
        _fail("VERIFICATION_BOUNDARY_INVALID")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(document: object) -> bytes:
    try:
        return (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _fail("GENERATION_SERIALIZATION_FAILED")


def _capture_sources(root: Path) -> dict[Path, bytes]:
    if len(set(SOURCE_PATHS)) != len(SOURCE_PATHS):
        _fail("SOURCE_INVENTORY_DUPLICATE")
    return {path: _read_regular(root, path) for path in SOURCE_PATHS}


def _validate_pins(inputs: dict[Path, bytes]) -> None:
    if _digest(inputs[CONTRACT_PATH]) != EXPECTED_CONTRACT_SHA256:
        _fail("CONTRACT_HASH_DRIFT")
    if _digest(inputs[SECURE_HELPER_PATH]) != EXPECTED_SECURE_HELPER_SHA256:
        _fail("SECURE_HELPER_DRIFT")
    for path, expected in CANONICAL_BINDINGS.items():
        if _digest(inputs[path]) != expected:
            _fail("CANONICAL_BINDING_DRIFT")


def expected_artifacts(
    root: Path = REPOSITORY_ROOT,
) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    inputs = _capture_sources(root)
    _validate_pins(inputs)
    contract = _parse_contract(inputs[CONTRACT_PATH])
    _validate_contract(contract)
    source_artifacts = [
        {
            "path": path.as_posix(),
            "sha256": _digest(inputs[path]),
        }
        for path in SOURCE_PATHS
    ]
    runtime = _json_bytes(
        {
            "document": "RAOS_ST0401_LOCAL_AUTH_RUNTIME_V2",
            "contract": contract,
            "contract_sha256": _digest(inputs[CONTRACT_PATH]),
            "generation_authority": "REPOSITORY_LOCAL_ONLY",
            "source_artifacts": source_artifacts,
            "story_id": "ST-0401",
        }
    )
    manifest = _json_bytes(
        {
            "boundary": {
                "authority": contract["authority"],
                "open_decision": contract["open_decision"],
                "verification": contract["verification"],
            },
            "generated_artifacts": [
                {
                    "path": RUNTIME_PATH.as_posix(),
                    "sha256": _digest(runtime),
                }
            ],
            "generation": {
                "owner": GENERATOR_PATH.as_posix(),
                "publication": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
                "python": "CPython 3.14.6",
            },
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": source_artifacts,
            "story_id": "ST-0401",
        }
    )
    return ((RUNTIME_PATH, runtime), (MANIFEST_PATH, manifest))


def _output_path(root: Path, relative: Path) -> Path:
    _validate_relative(relative)
    absolute_root = Path(os.path.abspath(root))
    destination = absolute_root.joinpath(*relative.parts)
    if not destination.is_absolute():
        _fail("OUTPUT_PATH_INVALID")
    return destination


def build(root: Path = REPOSITORY_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for path, expected in artifacts:
            if _read_regular(root, path, maximum=MAX_GENERATED_BYTES) != expected:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    try:
        secure_generated_publication.publish_generated(
            tuple((_output_path(root, path), payload) for path, payload in artifacts),
            namespace="st0401v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-0401 local authentication runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0401 local authentication runtime checked"
        if arguments.check
        else "ST-0401 local authentication runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
