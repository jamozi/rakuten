#!/usr/bin/env python3
"""Validate ST-0204 semantics and build its schema/evidence manifest."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import pydantic
import pydantic_core
import yaml

try:
    from scripts import build_st0201_postgres_service as shared
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.config import RuntimeConfig  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-0204/contracts/runtime-config.v1.yaml")
SCHEMA_PATH: Final = Path("changes/st-0204/generated/runtime-config.v1.schema.json")
MANIFEST_PATH: Final = Path("changes/st-0204/manifest.yaml")
PREDECESSOR_PATH: Final = Path("changes/st-0203/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0204_config_loader.py")
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st0204_config_loader.py"
)
UV_CONFIGURATION_PATH: Final = Path("uv.toml")

EXPECTED_TOOLCHAIN: Final = {
    "python": "3.14.6",
    "pydantic": "2.13.4",
    "pydantic_core": "2.46.4",
    "pyyaml": "6.0.3",
    "uv": "0.12.1",
}

PINNED_CANONICAL_INPUTS: Final = {
    "docs/manifest.json": (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_test_environment_matrix_v1.0.yaml": (
        "3dc59c8c951a39d2079eb82e6a3e5adde3ce1910296abf8e1a3a539107a96b68"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md": (
        "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2"
    ),
}

EXPECTED_PREDECESSOR_SHA256: Final = (
    "89f6ca8bb0261b82998001f0a6a954a2152437cc4e51e2f8671bc67e9b7c0a3c"
)

SOURCE_ARTIFACT_PATHS: Final = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    UV_CONFIGURATION_PATH,
    CONTRACT_PATH,
    Path("changes/st-0204/README.md"),
    Path("docs/execplans/ST-0204.md"),
    Path("docs/worklogs/ST-0204.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0201_postgres_service.py"),
    Path("python/raos/config/__init__.py"),
    Path("python/raos/config/runtime.py"),
    Path("tests/st0204/conftest.py"),
    Path("tests/st0204/test_loader.py"),
    Path("tests/st0204/test_negative_cases.py"),
    Path("tests/st0204/test_privacy.py"),
    Path("tests/st0204/test_contract.py"),
    Path("tests/st0204/test_generation.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("Makefile"),
    Path("README.md"),
    PREDECESSOR_PATH,
)

EXPECTED_CONTRACT: Final = {
    "document": {
        "id": "RAOS-RUNTIME-CONFIG-001",
        "version": "1.0.0",
        "story_id": "ST-0204",
        "status": "LOCAL_AND_CI_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    },
    "story": {
        "dependencies": ["ST-0102", "ST-0103"],
        "objective": "ENVIRONMENT_TYPED_CONFIG_AND_SECRET_REFERENCES",
        "deliverables": [
            "LANGUAGE_NEUTRAL_CONFIG_SCHEMA",
            "REDACTED_DIAGNOSTICS",
            "STRICT_PYTHON_LOADER",
        ],
        "required_suites": ["TST-005", "TST-031"],
        "open_decisions": [],
    },
    "toolchain": EXPECTED_TOOLCHAIN,
    "schema": {
        "uri": f"repo://{SCHEMA_PATH.as_posix()}",
        "generated_from": "repo://python/raos/config/runtime.py",
        "schema_version": 1,
        "strict_types": True,
        "unknown_fields": "REJECT",
        "immutable_runtime_model": True,
        "pattern_end_semantics": "ABSOLUTE_END_ECMA_262_AND_PYTHON",
    },
    "environment_source": {
        "namespace": "RAOS_",
        "allowed_keys": [
            "RAOS_ENVIRONMENT",
            "RAOS_SERVICE_NAME",
            "RAOS_LOG_LEVEL",
            "RAOS_SECRET_REFERENCES",
        ],
        "required_keys": ["RAOS_ENVIRONMENT", "RAOS_SERVICE_NAME"],
        "optional_defaults": {
            "RAOS_LOG_LEVEL": "INFO",
            "RAOS_SECRET_REFERENCES": "{}",
        },
        "canonical_environments": [
            "ENV-DEV",
            "ENV-CI",
            "ENV-INTEGRATION",
            "ENV-STAGING",
            "ENV-RECOVERY",
            "ENV-PRODUCTION",
        ],
        "environment_files": "FORBIDDEN",
        "inherited_user_configuration": "FORBIDDEN",
        "implicit_import_time_load": "FORBIDDEN",
        "os_environment_access": "EXPLICIT_ENTRYPOINT_ONLY",
        "unknown_namespaced_keys": "REJECT_WITHOUT_ECHO",
    },
    "fields": {
        "service_name": {
            "grammar": "LOWER_KEBAB_CASE",
            "minimum_length": 1,
            "maximum_length": 63,
        },
        "log_level": {"values": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
    },
    "secret_references": {
        "input_key": "RAOS_SECRET_REFERENCES",
        "encoding": "STRICT_JSON_OBJECT_OF_STRINGS",
        "duplicate_keys": "REJECT_WITHOUT_ECHO",
        "maximum_input_bytes": 16384,
        "maximum_reference_count": 64,
        "alias_grammar": "LOWER_SNAKE_CASE",
        "maximum_alias_length": 64,
        "scheme": "secret",
        "maximum_reference_length": 512,
        "query_fragment_userinfo": "FORBIDDEN",
        "controls_and_whitespace": "FORBIDDEN",
        "raw_secret_values": "FORBIDDEN",
        "provider_type_exposure": "FORBIDDEN",
        "required_aliases": "CALLER_OWNED",
        "missing_required_alias": "FAIL_CLOSED",
        "value_resolution": "NOT_IMPLEMENTED",
        "provider_adapter": "NOT_IMPLEMENTED",
    },
    "diagnostics": {
        "format": "JSON_SAFE_MAPPING",
        "exact_keys": [
            "schema_version",
            "environment",
            "service_name",
            "log_level",
            "secret_aliases",
            "secret_reference_count",
        ],
        "secret_aliases": "SORTED",
        "secret_reference_values": "NEVER_EMITTED",
        "arbitrary_source_keys_or_values": "NEVER_EMITTED",
        "deterministic": True,
    },
    "error_hygiene": {
        "domain_error": "ConfigurationError",
        "raw_input_in_message": "FORBIDDEN",
        "raw_input_in_repr": "FORBIDDEN",
        "exception_chaining_of_parser_or_validation_error": "FORBIDDEN",
        "stdout_stderr_logging": "FORBIDDEN",
        "model_json_maximum_input_bytes": 32768,
        "model_json_duplicate_members": "REJECT_WITHOUT_ECHO",
        "model_json_mutable_bytearray": "IMMUTABLE_SNAPSHOT",
        "supported_pydantic_entrypoints": [
            "RUNTIME_CONFIG_CONSTRUCTOR",
            "MODEL_VALIDATE",
            "MODEL_VALIDATE_JSON",
        ],
        "low_level_type_adapter": "UNSUPPORTED_BYPASS",
        "base_model_unvalidated_escape_hatches": "UNSUPPORTED_TRUSTED_CODE_BYPASS",
        "security_boundary_subclassing": "FORBIDDEN",
        "existing_model_instances": "REVALIDATE_AND_NORMALIZE",
        "nested_secret_reference_instances": "EXACT_TYPE_ONLY",
    },
    "security": {
        "control_mappings": [
            {
                "id": "SEC-APP-001",
                "relationship": "STRICT_SCHEMA_AND_NEGATIVE_VALIDATION",
            },
            {
                "id": "SEC-APP-010",
                "relationship": "REDACTED_DIAGNOSTICS_AND_ERRORS",
            },
            {
                "id": "SEC-DATA-003",
                "relationship": "REFERENCE_ONLY_NO_SECRET_VALUE_IN_REPO_OR_LOG",
            },
            {
                "id": "SEC-DATA-007",
                "relationship": "DIAGNOSTIC_DATA_MINIMIZATION",
            },
            {
                "id": "SEC-SDLC-006",
                "relationship": "MAINTAINED_WORKTREE_SECRET_SCAN",
            },
        ],
        "classification": "RESTRICTED_REFERENCE_IDENTIFIER",
        "production_credentials": "NOT_USED",
    },
    "verification": {
        "required_suites": ["TST-005", "TST-031"],
        "local_command": (
            "uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0204"
        ),
        "required_behaviors": [
            "ALL_CANONICAL_ENVIRONMENTS",
            "STRICT_UNKNOWN_KEY_REJECTION",
            "REQUIRED_KEY_FAILURE",
            "REQUIRED_SECRET_ALIAS_FAILURE",
            "DUPLICATE_JSON_KEY_REJECTION",
            "RESOURCE_BOUND_REJECTION",
            "SECRET_REFERENCE_GRAMMAR",
            "SCHEMA_ABSOLUTE_END_PARITY",
            "MODEL_JSON_DUPLICATE_MEMBER_REJECTION",
            "IMMUTABLE_TYPED_MODEL",
            "DETERMINISTIC_SCHEMA",
            "DIAGNOSTIC_ALLOWLIST",
            "NO_REFERENCE_LEAK_IN_REPR_ERROR_SERIALIZATION_OR_LOG",
        ],
        "formal_environments": ["CI", "staging"],
        "local_result_can_promote_formal_suite": False,
    },
    "predecessor": {
        "manifest_uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
        "story_id": "ST-0203",
        "sha256": EXPECTED_PREDECESSOR_SHA256,
    },
    "boundary": {
        "environment": "LOCAL_AND_CI_IMPLEMENTATION_CANDIDATE",
        "production_secret_resolution": "NOT_IMPLEMENTED",
        "secret_manager_adapter": "NOT_IMPLEMENTED",
        "workload_identity": "NOT_IMPLEMENTED",
        "rotation_hooks": "NOT_IMPLEMENTED",
        "browser_or_client_config": "NOT_IMPLEMENTED",
        "dotenv_loading": "FORBIDDEN",
        "formal_tst_005": "NOT_EXECUTED",
        "formal_tst_031": "NOT_EXECUTED",
        "security_owner_review": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}


def _assert_digest(root: Path, relative: Path, expected: str, *, label: str) -> None:
    path = shared._repository_regular_file(root, relative, label)
    actual = shared.sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} digest drift: {relative}: {actual}")


def assert_pinned_inputs(root: Path = REPO_ROOT) -> None:
    """Fail closed when a reviewed canonical or predecessor input drifts."""

    for name, digest in PINNED_CANONICAL_INPUTS.items():
        _assert_digest(root, Path(name), digest, label="canonical input")
    _assert_digest(
        root,
        PREDECESSOR_PATH,
        EXPECTED_PREDECESSOR_SHA256,
        label="predecessor manifest",
    )


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load the reviewed semantic contract and reject every drift."""

    assert_pinned_inputs(root)
    path = shared._repository_regular_file(root, CONTRACT_PATH, "ST-0204 contract")
    loaded = shared.load_yaml(path)
    if not isinstance(loaded, dict):
        raise RuntimeError("ST-0204 contract must be a mapping")
    shared._require_exact(loaded, EXPECTED_CONTRACT, "ST-0204 contract")
    return dict(loaded)


def assert_generation_toolchain(root: Path = REPO_ROOT) -> None:
    """Reject generation outside the exact reviewed runtime and uv pin."""

    runtime_versions = (
        (
            "Python",
            ".".join(str(component) for component in sys.version_info[:3]),
            EXPECTED_TOOLCHAIN["python"],
        ),
        ("Pydantic", pydantic.__version__, EXPECTED_TOOLCHAIN["pydantic"]),
        (
            "pydantic-core",
            pydantic_core.__version__,
            EXPECTED_TOOLCHAIN["pydantic_core"],
        ),
        ("PyYAML", yaml.__version__, EXPECTED_TOOLCHAIN["pyyaml"]),
    )
    for label, actual, expected in runtime_versions:
        if type(actual) is not str or actual != expected:
            raise RuntimeError(f"{label} runtime version does not match reviewed pin")

    uv_path = shared._repository_regular_file(
        root,
        UV_CONFIGURATION_PATH,
        "uv configuration",
    )
    try:
        uv_configuration = tomllib.loads(uv_path.read_text(encoding="utf-8"))
    except UnicodeError, tomllib.TOMLDecodeError:
        raise RuntimeError("uv required-version configuration is invalid") from None
    if uv_configuration.get("required-version") != (f"=={EXPECTED_TOOLCHAIN['uv']}"):
        raise RuntimeError("uv required-version does not match reviewed pin")


def render_schema() -> bytes:
    """Render the strict runtime model as deterministic JSON Schema bytes."""

    assert_generation_toolchain()
    schema = RuntimeConfig.model_json_schema(mode="validation")
    schema["$id"] = "urn:raos:runtime-config:v1"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return (
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _artifact_record(root: Path, relative: Path) -> dict[str, Any]:
    path = shared._repository_regular_file(root, relative, "source artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": shared.sha256_bytes(content),
    }


def _generated_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": shared.sha256_bytes(content),
    }


def render_manifest(root: Path = REPO_ROOT) -> bytes:
    """Render a deterministic manifest over all reviewed source artifacts."""

    assert_generation_toolchain(root)
    contract = load_and_validate_contract(root)
    schema = render_schema()
    artifacts = [_artifact_record(root, path) for path in SOURCE_ARTIFACT_PATHS]
    manifest = {
        "document": {
            "id": "RAOS-RUNTIME-CONFIG-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0204",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "toolchain": dict(EXPECTED_TOOLCHAIN),
            "canonical_inputs": [
                {"uri": f"repo://{name}", "sha256": digest}
                for name, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "predecessor_manifest": {
                "uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_SHA256,
                "story_id": "ST-0203",
            },
        },
        "evidence_chain": {"stories": ["ST-0201", "ST-0202", "ST-0203", "ST-0204"]},
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": 1,
        "generated_artifacts": [_generated_record(SCHEMA_PATH, schema)],
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": dict(contract["boundary"]),
    }
    return yaml.dump(
        manifest,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def install_artifact(
    relative: Path,
    content: bytes,
    root: Path = REPO_ROOT,
) -> None:
    """Atomically install one generated file without following symlinks."""

    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError("unsafe ST-0204 generated path")
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("generated-artifact root must exist") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("generated-artifact root must be a real directory")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    temporary_name: str | None = None
    output_descriptor: int | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in relative.parent.parts:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        parent_descriptor = descriptors[-1]
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError("generated target must be a regular non-symlink file")

        for suffix in range(100):
            candidate = f".{relative.name}.st0204-{os.getpid()}-{suffix}"
            try:
                output_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise RuntimeError("cannot allocate a safe generated staging file")

        try:
            view = memoryview(content)
            while view:
                written = os.write(output_descriptor, view)
                if written <= 0:
                    raise RuntimeError("short write while staging ST-0204 artifact")
                view = view[written:]
            os.fsync(output_descriptor)
        finally:
            os.close(output_descriptor)
            output_descriptor = None

        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if output_descriptor is not None:
            os.close(output_descriptor)
        if descriptors:
            parent_descriptor = descriptors[-1]
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except FileNotFoundError:
                    pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def install_generated(root: Path = REPO_ROOT) -> None:
    """Install the schema followed by the manifest using safe replacements."""

    schema = render_schema()
    manifest = render_manifest(root)
    install_artifact(SCHEMA_PATH, schema, root)
    install_artifact(MANIFEST_PATH, manifest, root)


def check_generated(root: Path = REPO_ROOT) -> None:
    """Verify both generated artifacts without writing."""

    expected = {
        SCHEMA_PATH: render_schema(),
        MANIFEST_PATH: render_manifest(root),
    }
    for relative, content in expected.items():
        target = shared._repository_regular_file(root, relative, "ST-0204 output")
        if target.stat().st_mode & 0o022:
            raise RuntimeError("ST-0204 output cannot be group/world writable")
        if target.read_bytes() != content:
            raise RuntimeError(f"generated ST-0204 artifact drift: {relative}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the contract, schema, and manifest without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            install_generated()
            mode = "install"
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_artifacts": 2,
                "mode": mode,
                "status": "PASS",
                "story_id": "ST-0204",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
