#!/usr/bin/env python3
"""Generate the deterministic ST-0905 V2 local command fixture and manifest."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.publishing.recorded_publication_command_fixture_v2 import (  # noqa: E402
    build_recorded_publication_command_fixture_bytes_v2,
    load_recorded_publication_command_fixture_v2,
)
from raos.domain.publishing.publication_commands_v2 import PROFILE  # noqa: E402


class PublicationCommandGenerationError(RuntimeError):
    pass


def _fail(code: str) -> NoReturn:
    raise PublicationCommandGenerationError(code) from None


CONTRACT_PATH: Final = Path(
    "changes/st-0905/contracts/publication-commands-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-0905/generated/publication-commands-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-0905/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0905_publication_commands_runtime_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
ST0903_FIXTURE_PATH: Final = Path(
    "changes/st-0903/generated/publication-snapshot-pass.v2.json"
)
ST0904_FIXTURE_PATH: Final = Path(
    "changes/st-0904/generated/public-projection-recorded.v2.json"
)
FINAL_APPROVAL_FIXTURE_PATH: Final = Path(
    "changes/st-0902/generated/final-approval-pass.v2.json"
)
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
REVIEW_FIXTURE_PATH: Final = Path(
    "changes/st-0901/generated/review-completion-pass.v2.json"
)
SEO_FIXTURE_PATH: Final = Path("changes/st-0807/generated/seo-render-recorded.v2.json")
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 16 * 1024 * 1024

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/publishing/publication_commands_v2.py"),
    Path("python/raos/ports/publishing/publication_commands_v2.py"),
    Path("python/raos/application/publishing/publication_commands_v2.py"),
    Path("python/raos/adapters/publishing/recorded_publication_commands_v2.py"),
    Path("python/raos/adapters/publishing/recorded_publication_command_fixture_v2.py"),
    Path("changes/st-0905/README-v2.md"),
    Path("changes/st-0905/completion/completion.v2.yaml"),
    Path("tests/st0905/test_runtime_v2.py"),
    Path("tests/st0905/test_runtime_hostile_v2.py"),
    Path("tests/st0905/test_runtime_generation_v2.py"),
)

BINDING_PATHS: Final = {
    "st0903_fixture": ST0903_FIXTURE_PATH,
    "st0903_manifest": Path("changes/st-0903/runtime-manifest.v2.yaml"),
    "st0904_fixture": ST0904_FIXTURE_PATH,
    "st0904_manifest": Path("changes/st-0904/runtime-manifest.v2.yaml"),
    "final_approval_fixture": FINAL_APPROVAL_FIXTURE_PATH,
    "policy_fixture": POLICY_FIXTURE_PATH,
    "review_fixture": REVIEW_FIXTURE_PATH,
    "seo_fixture": SEO_FIXTURE_PATH,
    "step_up_domain": Path("python/raos/domain/iam/step_up.py"),
    "step_up_application": Path("python/raos/application/iam/step_up.py"),
    "step_up_port": Path("python/raos/ports/step_up.py"),
    "step_up_adapter": Path("python/raos/adapters/development_step_up.py"),
    "role_matrix": Path(
        "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"
    ),
    "security_controls": Path(
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    ),
    "admin_openapi": Path("contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml"),
    "publish_job": Path(
        "contracts/raos-v0.4/contracts/schemas/jobs/"
        "publishing-publish-snapshot-v1.schema.json"
    ),
    "rollback_job": Path(
        "contracts/raos-v0.4/contracts/schemas/jobs/publishing-rollback-v1.schema.json"
    ),
    "unpublish_job": Path(
        "contracts/raos-v0.4/contracts/schemas/jobs/publishing-unpublish-v1.schema.json"
    ),
    "published_event": Path(
        "contracts/raos-v0.4/contracts/schemas/events/"
        "jp-raos-publishing-article-published-v1.schema.json"
    ),
    "rolled_back_event": Path(
        "contracts/raos-v0.4/contracts/schemas/events/"
        "jp-raos-publishing-article-rolled-back-v1.schema.json"
    ),
    "unpublished_event": Path(
        "contracts/raos-v0.4/contracts/schemas/events/"
        "jp-raos-publishing-article-unpublished-v1.schema.json"
    ),
}

DEPENDENCY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/08_codex/AGENTS.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"),
    Path("changes/st-0905/README.md"),
    Path("changes/st-0905/contracts/publication-commands-reference-plan.v1.yaml"),
    Path("changes/st-0905/generated/publication-commands-reference-plan.v1.json"),
    Path("changes/st-0905/manifest.yaml"),
    Path("scripts/build_st0905_publication_commands_reference_plan.py"),
    SECURE_HELPER_PATH,
    *BINDING_PATHS.values(),
)

GENERATED_PATHS: Final = (FIXTURE_PATH, MANIFEST_PATH)

_EXPECTED_RUNTIME: Final = {
    "executable": True,
    "environments": ["ENV-DEV", "CI"],
    "process_local_only": True,
    "provider_mode": "RECORDED_SYNTHETIC_ONLY",
    "immutable_st0903_input_only": True,
    "immutable_st0904_projection_only": True,
    "persistence": False,
    "database_write": False,
    "network": False,
    "http_route": False,
    "cms_write": False,
    "queue_write": False,
    "event_emit": False,
    "outbox_write": False,
    "public_state_change": False,
    "publication_authorized": False,
    "release_authorized": False,
    "production_authorized": False,
}

_EXPECTED_COMMAND: Final = {
    "publish": "PROCESS_LOCAL_RECORDED_TRANSACTION",
    "rollback": "PROCESS_LOCAL_RECORDED_TRANSACTION",
    "unpublish": "DENY_NO_CANONICAL_ROLE_ACTION",
    "active_human_required": True,
    "allowed_roles": ["MANAGING_EDITOR", "OPERATOR"],
    "mfa_required": True,
    "step_up_required": True,
    "final_approval_required": True,
    "exact_snapshot_identity_required": True,
    "exact_source_hash_required": True,
    "kill_switch_safe_state_required": True,
    "separation_of_duties_publish": True,
}

_EXPECTED_TRANSACTION: Final = {
    "same_request_replay": "BYTE_IDENTICAL_RESULT",
    "same_key_different_request": "IDEMPOTENCY_CONFLICT",
    "double_publish": "NO_DUPLICATE_PROJECTION_EVENT_AUDIT_OUTBOX",
    "rollback_target": "KNOWN_STRICTLY_PREVIOUS_IMMUTABLE_SNAPSHOT_ONLY",
    "copy_stage_swap_atomicity": True,
    "partial_failure": "NO_STATE_CHANGE",
}

_EXPECTED_EXECUTION: Final = {
    name: "FORBIDDEN"
    for name in (
        "network",
        "credential",
        "browser",
        "database",
        "cms",
        "http_route",
        "queue",
        "provider",
        "public_state",
        "publication",
        "staging",
        "release",
        "production",
    )
}

_EXPECTED_VERIFICATION: Final = {
    "TST-012": "NOT_EXECUTED",
    "TST-013": "NOT_EXECUTED",
    "TST-021": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    node_pairs = cast(list[tuple[yaml.Node, yaml.Node]], node.value)
    loader_api = cast(Any, loader)
    construct = cast(Callable[[yaml.Node, bool], object], loader_api.construct_object)
    for key_node, value_node in node_pairs:
        key = construct(key_node, deep)
        if key in result:
            _fail("DUPLICATE_YAML_KEY")
        value = construct(value_node, deep)
        result[key] = value
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _safe_path(root: Path, relative: object) -> Path:
    if (
        not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("PATH_INVALID")
    candidate = root.joinpath(relative)
    try:
        candidate.relative_to(root)
    except ValueError:
        _fail("PATH_INVALID")
    return candidate


def _read_regular(path: Path) -> bytes:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_SOURCE_BYTES
        ):
            _fail("SOURCE_INVALID")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError:
        _fail("SOURCE_INVALID")
    if len(payload) != before.st_size or (
        before.st_dev,
        before.st_ino,
        before.st_mtime_ns,
        before.st_size,
    ) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size):
        _fail("SOURCE_CHANGED")
    return payload


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID")
    candidate = cast(dict[object, object], value)
    if any(type(key) is not str for key in candidate):
        _fail("CONTRACT_SHAPE_INVALID")
    return {cast(str, key): item for key, item in candidate.items()}


def load_contract(root: Path = REPO_ROOT) -> dict[str, object]:
    root = Path(os.path.abspath(root))
    payload = _read_regular(_safe_path(root, CONTRACT_PATH))
    try:
        yaml_api = cast(Any, yaml)
        scan = cast(Callable[[bytes], Iterable[object]], yaml_api.scan)
        tokens = tuple(scan(payload))
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("YAML_FEATURE_FORBIDDEN")
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except PublicationCommandGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    contract = _mapping(loaded)
    if frozenset(contract) != frozenset(
        {
            "schema_version",
            "story_id",
            "local_status",
            "classification",
            "profile",
            "runtime",
            "bindings",
            "command_boundary",
            "transaction_boundary",
            "execution_boundary",
            "verification_boundary",
        }
    ):
        _fail("CONTRACT_SHAPE_INVALID")
    if (
        contract["schema_version"] != 2
        or contract["story_id"] != "ST-0905"
        or contract["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or contract["classification"] != "LOCAL_RECORDED_PUBLICATION_COMMAND_RUNTIME_V2"
        or contract["profile"] != PROFILE
        or _mapping(contract["runtime"]) != _EXPECTED_RUNTIME
        or _mapping(contract["command_boundary"]) != _EXPECTED_COMMAND
        or _mapping(contract["transaction_boundary"]) != _EXPECTED_TRANSACTION
        or _mapping(contract["execution_boundary"]) != _EXPECTED_EXECUTION
        or _mapping(contract["verification_boundary"]) != _EXPECTED_VERIFICATION
    ):
        _fail("CONTRACT_VALUE_INVALID")
    bindings = _mapping(contract["bindings"])
    if frozenset(bindings) != frozenset(
        key for name in BINDING_PATHS for key in (f"{name}_uri", f"{name}_sha256")
    ):
        _fail("BINDING_SHAPE_INVALID")
    for name, relative in BINDING_PATHS.items():
        if bindings[f"{name}_uri"] != f"repo://{relative.as_posix()}":
            _fail("BINDING_URI_INVALID")
        digest = bindings[f"{name}_sha256"]
        if type(digest) is not str or len(digest) != 64:
            _fail("BINDING_SHAPE_INVALID")
    return contract


def _dependency_bytes(root: Path) -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    values = tuple(
        _read_regular(_safe_path(root, path))
        for path in (
            ST0903_FIXTURE_PATH,
            ST0904_FIXTURE_PATH,
            FINAL_APPROVAL_FIXTURE_PATH,
            POLICY_FIXTURE_PATH,
            REVIEW_FIXTURE_PATH,
            SEO_FIXTURE_PATH,
        )
    )
    return cast(tuple[bytes, bytes, bytes, bytes, bytes, bytes], values)


def _fixture_bytes(root: Path) -> bytes:
    snapshot, projection, approval, policy, review, seo = _dependency_bytes(root)
    return build_recorded_publication_command_fixture_bytes_v2(
        st0903_fixture=snapshot,
        st0904_fixture=projection,
        final_approval_fixture=approval,
        policy_fixture=policy,
        review_fixture=review,
        seo_fixture=seo,
    )


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".yaml": "application/yaml",
    }.get(path.suffix, "application/octet-stream")


def _artifact(root: Path, path: Path, role: str) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, path))
    return {
        "uri": f"repo://{path.as_posix()}",
        "artifact_role": role,
        "media_type": _media_type(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _manifest_bytes(root: Path, fixture: bytes) -> bytes:
    sources = [
        *(_artifact(root, path, "OWNER_SOURCE") for path in SOURCE_PATHS),
        *(
            _artifact(root, path, "CANONICAL_OR_DEPENDENCY_INPUT")
            for path in DEPENDENCY_PATHS
        ),
    ]
    document = {
        "schema_version": 2,
        "story_id": "ST-0905",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_PUBLICATION_COMMAND_RUNTIME_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "artifact_role": "GENERATED_RECORDED_PUBLICATION_COMMAND_FIXTURE",
                "media_type": "application/json",
                "bytes": len(fixture),
                "sha256": hashlib.sha256(fixture).hexdigest(),
            }
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python "
                "scripts/build_st0905_publication_commands_runtime_v2.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0905_publication_commands_runtime_v2.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": hashlib.sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ).hexdigest(),
        },
        "authority": {
            "database_write_authorized": False,
            "event_emission_authorized": False,
            "http_route_authorized": False,
            "outbox_write_authorized": False,
            "public_state_change_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_012_status": "NOT_EXECUTED",
            "formal_tst_013_status": "NOT_EXECUTED",
            "formal_tst_021_status": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    root = Path(os.path.abspath(root))
    load_contract(root)
    fixture = _fixture_bytes(root)
    snapshot, projection, approval, policy, review, seo = _dependency_bytes(root)
    try:
        load_recorded_publication_command_fixture_v2(
            fixture,
            st0903_fixture=snapshot,
            st0904_fixture=projection,
            final_approval_fixture=approval,
            policy_fixture=policy,
            review_fixture=review,
            seo_fixture=seo,
        )
    except Exception:
        _fail("GENERATED_FIXTURE_VALIDATION_FAILED")
    return {
        FIXTURE_PATH: fixture,
        MANIFEST_PATH: _manifest_bytes(root, fixture),
    }


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    root = Path(os.path.abspath(root))
    outputs = render_outputs(root)
    if check:
        for relative, payload in outputs.items():
            if _read_regular(_safe_path(root, relative)) != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    try:
        secure_generated_publication.publish_generated(
            tuple(
                (_safe_path(root, path), payload) for path, payload in outputs.items()
            ),
            namespace="st0905-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    arguments, unknown = parser.parse_known_args(argv)
    if unknown:
        return 2
    try:
        build(check=arguments.check)
    except Exception:
        print("ST-0905 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0905 V2 runtime checked"
        if arguments.check
        else "ST-0905 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
