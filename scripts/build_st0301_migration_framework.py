#!/usr/bin/env python3
"""Validate ST-0301 and build its catalog index and evidence manifest."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import stat
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts import build_st0201_postgres_service as shared
except ModuleNotFoundError:
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.migrations.catalog import (  # noqa: E402
    ALEMBIC_RUNTIME_SPECS,
    ANCHOR_REVISION,
    CHECKPOINT_SPECS,
    FORWARD_PLAN,
    GUARDED_REVERSE_PLAN,
    HEAD_REVISION,
    REVISION_SPECS,
)
from raos.migrations.runner import verify_repository  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-0301/contracts/migration-framework.v1.yaml")
CATALOG_PATH: Final = Path("changes/st-0301/generated/migration-catalog.v1.json")
MANIFEST_PATH: Final = Path("changes/st-0301/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0301_migration_framework.py")
PREDECESSOR_PATH: Final = Path("changes/st-0204/manifest.yaml")
GENERATED_PATHS: Final = (CATALOG_PATH, MANIFEST_PATH)
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python "
    "scripts/build_st0301_migration_framework.py"
)

EXPECTED_TOOLCHAIN: Final = {
    "python": "3.14.6",
    "uv": "0.12.1",
    "alembic": "1.18.5",
    "sqlalchemy": "2.0.51",
    "psycopg": "3.3.4",
    "pyyaml": "6.0.3",
}

PINNED_CANONICAL_INPUTS: Final = {
    "docs/manifest.json": "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
    "docs/canonical/05_test/RAOS_11_test_environment_matrix_v1.0.yaml": "3dc59c8c951a39d2079eb82e6a3e5adde3ce1910296abf8e1a3a539107a96b68",
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md": "d05d1d4ebe3f3904e58c104e0b1836bc897377dbf27f9019f57c3fc6440bd137",
    "docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md": "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2",
    "docs/canonical/08_codex/PLANS.md": "e8ff1bd1ac181380e9bff2bcbd27aeddcadf0858692bc666b08cb8f9c4d7f84a",
    "docs/canonical/08_codex/prompts/02_database_migration.md": "753a5301ad3aac43dd1954e6e9f7ecc777aaf5c21979a6037f33ae5da72ee160",
}

DEPENDENCY_MANIFESTS: Final = {
    "ST-0201": (
        Path("changes/st-0201/manifest.yaml"),
        "fce4b7f18cec09425264a1058bda59759e081be0c04826ffa3eae433a68fcda3",
    ),
    "ST-0002": (
        Path("changes/st-0002/manifest.yaml"),
        "ec687f51795c4f97d4e4b08db38ce4bec7c94da0e337c7e9a1bff2a9b2cb0f1e",
    ),
    "ST-0003": (
        Path("changes/st-0003/manifest.yaml"),
        "142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482",
    ),
    "ST-0004": (
        Path("changes/st-0004/manifest.yaml"),
        "5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458",
    ),
}
EXPECTED_PREDECESSOR_SHA256: Final = (
    "2c26f24dce1a1eda9a79bd0d339478b208dde77ecc76e9dfd71c918ad9fab3be"
)
SUCCESSOR_CONTRACT_PATH: Final = Path(
    "changes/st-0302/contracts/foundation-schema.v1.yaml"
)

SOURCE_ARTIFACT_PATHS: Final = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
    CONTRACT_PATH,
    Path("changes/st-0301/README.md"),
    Path("docs/execplans/ST-0301.md"),
    Path("docs/worklogs/ST-0301.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0201_postgres_service.py"),
    Path("migrations/FRAMEWORK.md"),
    Path("migrations/env.py"),
    Path("migrations/script.py.mako"),
    *(item.relative_path for item in REVISION_SPECS),
    Path("python/raos/__init__.py"),
    Path("python/raos/migrations/__init__.py"),
    Path("python/raos/migrations/__main__.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/cli.py"),
    Path("python/raos/migrations/runner.py"),
    Path("tests/st0301/conftest.py"),
    Path("tests/st0301/test_catalog.py"),
    Path("tests/st0301/test_cli.py"),
    Path("tests/st0301/test_contract.py"),
    Path("tests/st0301/test_generation.py"),
    Path("tests/st0301/test_postgresql.py"),
    Path("tests/st0301/test_runner.py"),
    Path("tests/st0102/test_toolchain_contract.py"),
    Path("tests/st0102/test_lock_contract.py"),
    Path("tests/st0102/test_commands_and_docs.py"),
    Path("scripts/validate_ci_hydration.py"),
    Path("tests/st0106/test_hydration_validator.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("Makefile"),
    Path("README.md"),
    *(item.relative_path for item in CHECKPOINT_SPECS),
    *(path for path, _ in DEPENDENCY_MANIFESTS.values()),
    PREDECESSOR_PATH,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be a mapping")
    return value


def assert_generation_toolchain(root: Path = REPO_ROOT) -> None:
    observed = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "alembic": importlib.metadata.version("alembic"),
        "sqlalchemy": importlib.metadata.version("SQLAlchemy"),
        "psycopg": importlib.metadata.version("psycopg"),
        "pyyaml": yaml.__version__,
    }
    _require(
        observed
        == {key: value for key, value in EXPECTED_TOOLCHAIN.items() if key != "uv"},
        "generation toolchain does not match reviewed pins",
    )
    uv = tomllib.loads(
        shared._repository_regular_file(
            root, Path("uv.toml"), "uv configuration"
        ).read_text(encoding="utf-8")
    )
    _require(
        uv.get("required-version") == "==0.12.1",
        "uv required-version does not match reviewed pin",
    )
    project = tomllib.loads(
        shared._repository_regular_file(
            root, Path("pyproject.toml"), "Python project"
        ).read_text(encoding="utf-8")
    )
    dependencies = set(project["project"]["dependencies"])
    _require(
        {"alembic==1.18.5", "sqlalchemy==2.0.51", "psycopg[binary]==3.3.4"}
        <= dependencies,
        "migration dependencies do not match reviewed pins",
    )


def _checkpoint_contract(item: Any) -> dict[str, object]:
    return {
        "revision": item.revision,
        "story_id": item.story_id,
        "phase": item.phase,
        "direction": item.direction.value,
        "repeatable": item.repeatable,
        "path": item.relative_path.as_posix(),
        "sha256": item.sha256,
    }


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = dict(
        _mapping(
            shared.load_yaml(
                shared._repository_regular_file(root, CONTRACT_PATH, "ST-0301 contract")
            ),
            "ST-0301 contract",
        )
    )
    _require(
        set(contract)
        == {
            "document",
            "story",
            "toolchain",
            "database",
            "revision_chain",
            "locking",
            "timeouts",
            "transactions",
            "history",
            "checkpoint_catalog",
            "cli",
            "error_hygiene",
            "security",
            "verification",
            "boundary",
        },
        "ST-0301 contract top-level keys differ",
    )
    _require(
        contract["document"]
        == {
            "id": "RAOS-MIGRATION-FRAMEWORK-001",
            "version": "1.0.0",
            "story_id": "ST-0301",
            "status": "LOCAL_AND_CI_CANDIDATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "ST-0301 document differs",
    )
    _require(contract["toolchain"] == EXPECTED_TOOLCHAIN, "ST-0301 toolchain differs")
    database = _mapping(contract["database"], "database")
    _require(
        database["exact_server_version_num"] == REVISION_SPECS[0].server_version_num,
        "ST-0301 database server version differs",
    )
    story = _mapping(contract["story"], "story")
    _require(
        story["dependencies"] == ["ST-0201", "ST-0002", "ST-0003", "ST-0004"],
        "ST-0301 dependencies differ",
    )
    _require(
        story["required_suites"] == ["TST-008", "TST-009"], "ST-0301 suites differ"
    )
    _require(story["open_decisions"] == [], "ST-0301 has an unresolved decision")
    revisions = _mapping(contract["revision_chain"], "revision chain")
    _require(
        revisions["anchor"] == ANCHOR_REVISION == revisions["head"],
        "ST-0301 revision head differs",
    )
    root_revision = REVISION_SPECS[0]
    expected_revisions = [
        {
            "revision": root_revision.revision,
            "down_revision": root_revision.down_revision,
            "story_id": root_revision.story_id,
            "name": "INSTALL_APPEND_ONLY_HISTORY_ANCHOR",
            "path": root_revision.relative_path.as_posix(),
            "source_sha256": root_revision.sha256,
            "runner_version": root_revision.runner_version,
            "server_version_num": root_revision.server_version_num,
            "transaction": "ALEMBIC_PER_REVISION",
            "downgrade": "FORBIDDEN_HISTORY_ANCHOR_RETAINED",
        }
    ]
    _require(
        revisions["revisions"] == expected_revisions, "ST-0301 revision catalog differs"
    )
    history = _mapping(contract["history"], "history")
    _require(
        history["revision_runtime_metadata"] == "IMMUTABLE_CATALOG_BOUND_PER_REVISION",
        "ST-0301 history runtime metadata binding differs",
    )
    _require(
        history["fields"]
        == [
            "event_id",
            "attempt_id",
            "revision_id",
            "story_id",
            "direction",
            "status",
            "source_sha256",
            "runner_version",
            "server_version_num",
            "error_code",
            "occurred_at",
            "transaction_id",
        ],
        "ST-0301 history fields differ",
    )
    _require(
        history["event_statuses"] == ["STARTED", "SUCCEEDED", "FAILED"]
        and history["directions"] == ["UPGRADE", "DOWNGRADE"],
        "ST-0301 history event vocabulary differs",
    )
    _require(
        history["transaction_rules"]
        == {
            "started": "SEPARATE_COMMIT_WHEN_HISTORY_EXISTS",
            "succeeded": "ON_VERSION_APPLY_IN_REVISION_TRANSACTION",
            "failed": ("APPEND_AFTER_REVISION_ROLLBACK_IF_LOCKED_SESSION_PRESERVED"),
            "interrupted": (
                "NEXT_LOCK_HOLDER_APPENDS_FAILED_INTERRUPTED_BEFORE_TERMINAL"
            ),
            "root_bootstrap_exception": (
                "SUCCEEDED_ONLY_BECAUSE_HISTORY_TABLE_DID_NOT_EXIST"
            ),
        },
        "ST-0301 history transaction rules differ",
    )
    checkpoints = _mapping(contract["checkpoint_catalog"], "checkpoint catalog")
    _require(
        checkpoints["execution"] == "DISABLED_UNTIL_OWNING_MIGRATION_WAVE_TRANSLATION",
        "checkpoint execution must remain disabled",
    )
    _require(
        checkpoints["entries"]
        == [_checkpoint_contract(item) for item in CHECKPOINT_SPECS],
        "checkpoint entries differ",
    )
    _require(tuple(checkpoints["forward_plan"]) == FORWARD_PLAN, "forward plan differs")
    _require(
        tuple(checkpoints["guarded_reverse_plan"]) == GUARDED_REVERSE_PLAN,
        "reverse plan differs",
    )
    boundary = _mapping(contract["boundary"], "boundary")
    _require(
        boundary["effective_canonical_status"] == "UNCHANGED",
        "canonical status promotion is forbidden",
    )
    _require(
        boundary["formal_tst_008"] == boundary["formal_tst_009"] == "NOT_EXECUTED",
        "formal suites cannot be promoted locally",
    )
    _require(
        boundary["checkpoint_execution"] == "DISABLED",
        "checkpoint execution boundary differs",
    )
    return contract


def _verify_pinned_inputs(root: Path) -> None:
    for relative, expected in PINNED_CANONICAL_INPUTS.items():
        path = shared._repository_regular_file(root, Path(relative), "canonical input")
        _require(shared.sha256_file(path) == expected, "canonical input digest differs")
    for story, (relative, expected) in DEPENDENCY_MANIFESTS.items():
        path = shared._repository_regular_file(root, relative, "dependency manifest")
        _require(
            shared.sha256_file(path) == expected,
            f"{story} dependency manifest digest differs",
        )
    predecessor = shared._repository_regular_file(
        root, PREDECESSOR_PATH, "predecessor manifest"
    )
    _require(
        shared.sha256_file(predecessor) == EXPECTED_PREDECESSOR_SHA256,
        "ST-0204 predecessor manifest digest differs",
    )


def render_catalog(root: Path = REPO_ROOT) -> bytes:
    assert_generation_toolchain(root)
    contract = load_and_validate_contract(root)
    _verify_pinned_inputs(root)
    verification = verify_repository(root)
    document = {
        "document": {
            "id": "RAOS-MIGRATION-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0301",
            "formal_verification": "NOT_EXECUTED",
        },
        "catalog_sha256": verification.catalog_sha256,
        "runtime_sources": [
            {
                "path": item.relative_path.as_posix(),
                "sha256": item.sha256,
            }
            for item in ALEMBIC_RUNTIME_SPECS
        ],
        "revision_graph": {
            "base": None,
            "anchor": ANCHOR_REVISION,
            "head": HEAD_REVISION,
            "linear_single_head": True,
            "revisions": [
                {
                    "revision": item.revision,
                    "down_revision": item.down_revision,
                    "story_id": item.story_id,
                    "path": item.relative_path.as_posix(),
                    "sha256": item.sha256,
                    "runner_version": item.runner_version,
                    "server_version_num": item.server_version_num,
                }
                for item in REVISION_SPECS
            ],
        },
        "deferred_checkpoints": {
            "execution": "DISABLED",
            "verification_order": [item.revision for item in CHECKPOINT_SPECS],
            "forward_plan": list(FORWARD_PLAN),
            "guarded_reverse_plan": list(GUARDED_REVERSE_PLAN),
            "entries": [_checkpoint_contract(item) for item in CHECKPOINT_SPECS],
        },
        "boundary": dict(contract["boundary"]),
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _artifact_record(root: Path, relative: Path) -> dict[str, object]:
    content = shared._repository_regular_file(
        root, relative, "source artifact"
    ).read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": shared.sha256_bytes(content),
    }


def render_manifest(root: Path = REPO_ROOT) -> bytes:
    assert_generation_toolchain(root)
    contract = load_and_validate_contract(root)
    _verify_pinned_inputs(root)
    catalog_content = render_catalog(root)
    artifacts = [_artifact_record(root, relative) for relative in SOURCE_ARTIFACT_PATHS]
    manifest = {
        "document": {
            "id": "RAOS-MIGRATION-FRAMEWORK-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0301",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "toolchain": dict(EXPECTED_TOOLCHAIN),
            "canonical_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "dependency_manifests": [
                {
                    "story_id": story,
                    "uri": f"repo://{path.as_posix()}",
                    "sha256": digest,
                }
                for story, (path, digest) in DEPENDENCY_MANIFESTS.items()
            ],
            "predecessor_manifest": {
                "story_id": "ST-0204",
                "uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_SHA256,
            },
        },
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{CATALOG_PATH.as_posix()}",
                "bytes": len(catalog_content),
                "sha256": shared.sha256_bytes(catalog_content),
            }
        ],
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
    ).encode()


def _install(relative: Path, content: bytes, root: Path) -> None:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError("unsafe generated path")
    root_metadata = root.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("generated root must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    descriptor = -1
    temporary_name = f".{relative.name}.st0301-{os.getpid()}"
    temporary_descriptor: int | None = None
    try:
        descriptor = os.open(root, directory_flags)
        descriptors.append(descriptor)
        for part in relative.parent.parts:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(part, directory_flags, dir_fd=descriptor)
            descriptor = child
            descriptors.append(descriptor)
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError("generated target must be a regular non-symlink file")
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=descriptor,
        )
        view = memoryview(content)
        while view:
            written = os.write(temporary_descriptor, view)
            if written <= 0:
                raise RuntimeError("generated artifact short write")
            view = view[written:]
        os.fsync(temporary_descriptor)
        os.close(temporary_descriptor)
        temporary_descriptor = None
        os.replace(
            temporary_name, relative.name, src_dir_fd=descriptor, dst_dir_fd=descriptor
        )
        temporary_name = ""
        os.fsync(descriptor)
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name and descriptors:
            try:
                os.unlink(temporary_name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass


def install_generated(root: Path = REPO_ROOT) -> None:
    catalog_content = render_catalog(root)
    manifest_content = render_manifest(root)
    _install(CATALOG_PATH, catalog_content, root)
    _install(MANIFEST_PATH, manifest_content, root)


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = {
        CATALOG_PATH: render_catalog(root),
        MANIFEST_PATH: render_manifest(root),
    }
    for relative, content in expected.items():
        path = shared._repository_regular_file(root, relative, "generated artifact")
        _require(
            path.stat().st_mode & 0o022 == 0,
            "generated artifact is writable by group or world",
        )
        _require(path.read_bytes() == content, "generated artifact drift")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    if (REPO_ROOT / SUCCESSOR_CONTRACT_PATH).is_file():
        try:
            from scripts import build_st0302_foundation as successor
        except ModuleNotFoundError:
            import build_st0302_foundation as successor  # type: ignore[no-redef]

        return successor.main(argv)
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
                "story_id": "ST-0301",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
