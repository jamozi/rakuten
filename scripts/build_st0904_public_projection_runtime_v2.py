#!/usr/bin/env python3
"""Generate the deterministic ST-0904 V2 projection fixture and provenance."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken, Token


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.recorded_public_projection_v2 import (  # noqa: E402
    build_recorded_public_projection_step,
    load_recorded_public_projection_fixture,
    recorded_public_projection_fixture_document,
)
from raos.adapters.recorded_publication_snapshot_v2 import (  # noqa: E402
    load_recorded_publication_snapshot_fixture,
)
from raos.domain.publishing.public_projection_v2 import (  # noqa: E402
    PROFILE,
)
from raos.domain.publishing.publication_snapshot_v2 import (  # noqa: E402
    canonical_json_bytes,
)


CONTRACT_PATH: Final = Path(
    "changes/st-0904/contracts/public-projection-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-0904/generated/public-projection-recorded.v2.json"
)
MODULE_PATH: Final = Path("python/raos/generated/public_projection_pass_v2.py")
MANIFEST_PATH: Final = Path("changes/st-0904/runtime-manifest.v2.yaml")
ST0903_FIXTURE_PATH: Final = Path(
    "changes/st-0903/generated/publication-snapshot-pass.v2.json"
)
FINAL_APPROVAL_FIXTURE_PATH: Final = Path(
    "changes/st-0902/generated/final-approval-pass.v2.json"
)
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
REVIEW_FIXTURE_PATH: Final = Path(
    "changes/st-0901/generated/review-completion-pass.v2.json"
)
SEO_FIXTURE_PATH: Final = Path("changes/st-0807/generated/seo-render-recorded.v2.json")
GENERATOR_PATH: Final = Path("scripts/build_st0904_public_projection_runtime_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
MAX_GENERATED_BYTES: Final = 16 * 1024 * 1024

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/publishing/public_projection_v2.py"),
    Path("python/raos/ports/public_projection_v2.py"),
    Path("python/raos/application/publishing/public_projection_v2.py"),
    Path("python/raos/adapters/recorded_public_projection_v2.py"),
    Path("changes/st-0904/README-v2.md"),
    Path("changes/st-0904/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0904.md"),
    Path("docs/worklogs/ST-0904.md"),
    Path("tests/st0904_v2/__init__.py"),
    Path("tests/st0904_v2/conftest.py"),
    Path("tests/st0904_v2/test_domain.py"),
    Path("tests/st0904_v2/test_application_adapter.py"),
    Path("tests/st0904_v2/test_generation.py"),
    Path("tests/st0904_v2/test_static_boundary.py"),
)
DEPENDENCY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/08_codex/AGENTS.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"),
    Path("docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"),
    Path("contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml"),
    Path(
        "contracts/raos-v0.4/contracts/schemas/common/publication-snapshot.schema.json"
    ),
    ST0903_FIXTURE_PATH,
    Path("changes/st-0903/runtime-manifest.v2.yaml"),
    Path("python/raos/domain/publishing/publication_snapshot_v2.py"),
    Path("python/raos/ports/publication_snapshot_v2.py"),
    Path("python/raos/application/publishing/publication_snapshot_v2.py"),
    Path("python/raos/adapters/recorded_publication_snapshot_v2.py"),
    FINAL_APPROVAL_FIXTURE_PATH,
    POLICY_FIXTURE_PATH,
    REVIEW_FIXTURE_PATH,
    SEO_FIXTURE_PATH,
    Path("changes/st-0306/contracts/database-roles-grants.v1.yaml"),
    Path("changes/st-0306/generated/database-roles-grants.v1.json"),
    Path("changes/st-0904/README.md"),
    Path("changes/st-0904/contracts/public-projection-reference-plan.v1.yaml"),
    Path("changes/st-0904/generated/public-projection-reference-plan.v1.json"),
    Path("changes/st-0904/manifest.yaml"),
    Path("scripts/build_st0904_public_projection_reference_plan.py"),
    SECURE_HELPER_PATH,
)

_ROOT_KEYS: Final = (
    "schema_version",
    "story_id",
    "local_status",
    "classification",
    "profile",
    "runtime",
    "bindings",
    "projection_boundary",
    "compatibility_boundary",
    "security_boundary",
    "execution_boundary",
    "verification_boundary",
)
_BINDING_PATHS: Final = {
    "st0903_fixture": ST0903_FIXTURE_PATH,
    "st0903_runtime_manifest": Path("changes/st-0903/runtime-manifest.v2.yaml"),
    "st0902_final_approval_fixture": FINAL_APPROVAL_FIXTURE_PATH,
    "st0805_policy_fixture": POLICY_FIXTURE_PATH,
    "st0901_review_fixture": REVIEW_FIXTURE_PATH,
    "st0807_seo_fixture": SEO_FIXTURE_PATH,
    "st0306_role_contract": Path(
        "changes/st-0306/contracts/database-roles-grants.v1.yaml"
    ),
    "st0306_role_projection": Path(
        "changes/st-0306/generated/database-roles-grants.v1.json"
    ),
    "public_openapi": Path("contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml"),
    "legacy_snapshot_schema": Path(
        "contracts/raos-v0.4/contracts/schemas/common/publication-snapshot.schema.json"
    ),
}
_EXPECTED_RUNTIME: Final[dict[str, object]] = {
    "executable": True,
    "provider_mode": "RECORDED_SYNTHETIC_ONLY",
    "process_local_candidate_only": True,
    "repository_write": False,
    "persistence": False,
    "database_write": False,
    "event_emit": False,
    "route_activation": False,
    "public_read_served": False,
    "public_projection_authorized": False,
    "publication_authorized": False,
    "release_authorized": False,
    "production_authorized": False,
}
_EXPECTED_PROJECTION_BOUNDARY: Final[dict[str, object]] = {
    "exact_st0903_request_result_pair_required": True,
    "exact_dependency_hashes_required": True,
    "public_article_allowlist_closed": True,
    "public_block_allowlist_closed": True,
    "public_route_allowlist_closed": True,
    "prohibited_internal_fields_rejected": True,
    "raw_html_emitted": False,
    "structured_data_emitted": False,
    "product_cards_emitted": False,
    "offers_emitted": False,
    "noindex_route_only": True,
    "deterministic_projection_generation": 1,
    "projection_persisted": False,
    "route_activated": False,
    "public_read_served": False,
    "disclosure_text_mode": "RECORDED_SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_COPY",
    "published_at_mode": "ST0903_CREATED_AT_LOCAL_ONLY_NOT_PUBLICATION_FACT",
    "freshness_mode": "UNKNOWN_SAFE_DEFAULT",
}
_EXPECTED_COMPATIBILITY: Final[dict[str, object]] = {
    "legacy_publication_snapshot_schema_validated": False,
    "legacy_schema_reconciliation_required": True,
    "heading_level_resolution": "NULL_COMMON_SUBSET_NO_HEADING_ROWS",
    "badges_resolution": "NO_PRODUCT_ROWS_SOURCE_UNAVAILABLE",
    "destination_host_resolution": "NO_OFFER_ROWS_SOURCE_UNAVAILABLE",
    "projection_generation_resolution": "ONE_COMMON_VALID_SUBSET_LOCAL_ONLY",
    "unresolved_production_values_invented": False,
}
_EXPECTED_SECURITY: Final[dict[str, object]] = {
    "public_role": "raos_public_ro",
    "public_role_schema_usage": ["readmodel"],
    "public_role_table_privileges": ["SELECT"],
    "public_role_other_domain_privileges": "NONE",
    "projection_role": "raos_projection_rw",
    "finance_evidence_ai_raw_fields_forbidden": True,
    "controls": ["SEC-DATA-004", "SEC-DATA-006"],
}
_EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "network": "FORBIDDEN",
    "credential": "FORBIDDEN",
    "provider": "FORBIDDEN",
    "browser": "FORBIDDEN",
    "database_write": "FORBIDDEN",
    "job": "FORBIDDEN",
    "event_emit": "FORBIDDEN",
    "api_activation": "FORBIDDEN",
    "public_serve": "FORBIDDEN",
    "cms": "FORBIDDEN",
    "publication": "FORBIDDEN",
    "staging": "FORBIDDEN",
    "release": "FORBIDDEN",
    "production": "FORBIDDEN",
}
_EXPECTED_VERIFICATION: Final[dict[str, object]] = {
    "TST-011": "NOT_EXECUTED",
    "TST-021": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


class PublicProjectionGenerationError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PublicProjectionGenerationError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = cast(
            object,
            loader.construct_object(key_node, deep=deep),  # pyright: ignore[reportUnknownMemberType]
        )
        if type(key) is not str or key in result:
            _fail("CONTRACT_MAPPING_INVALID")
        result[key] = cast(
            object,
            loader.construct_object(value_node, deep=deep),  # pyright: ignore[reportUnknownMemberType]
        )
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _safe_path(root: Path, relative: Path) -> Path:
    if (
        not root.is_absolute()
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
        metadata = path.lstat()
    except OSError:
        _fail("SOURCE_MISSING")
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > 64 * 1024 * 1024
    ):
        _fail("SOURCE_INVALID")
    try:
        payload = path.read_bytes()
    except OSError:
        _fail("SOURCE_INVALID")
    if len(payload) != metadata.st_size:
        _fail("SOURCE_INVALID")
    return payload


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_MAPPING_INVALID")
    return cast(dict[str, object], value)


def _string(value: object, expected: str | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("CONTRACT_VALUE_INVALID")
    if expected is not None and value != expected:
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _sha(value: object) -> str:
    observed = _string(value)
    if len(observed) != 64 or any(
        character not in "0123456789abcdef" for character in observed
    ):
        _fail("CONTRACT_VALUE_INVALID")
    return observed


def load_contract(root: Path) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, CONTRACT_PATH))
    if len(payload) > 256 * 1024:
        _fail("CONTRACT_TOO_LARGE")
    try:
        tokens = cast(
            Iterable[Token],
            yaml.scan(payload.decode("utf-8", errors="strict")),  # pyright: ignore[reportUnknownMemberType]
        )
        for token in tokens:
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("CONTRACT_YAML_FEATURE_FORBIDDEN")
        document = yaml.load(payload, Loader=_UniqueLoader)
    except PublicProjectionGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    contract = _mapping(document)
    if tuple(contract) != _ROOT_KEYS:
        _fail("CONTRACT_MAPPING_INVALID")
    if (
        contract["schema_version"] != 2
        or _string(contract["story_id"], "ST-0904") != "ST-0904"
        or _string(contract["local_status"], "LOCAL_IMPLEMENTATION_COMPLETE")
        != "LOCAL_IMPLEMENTATION_COMPLETE"
        or _string(
            contract["classification"],
            "LOCAL_EXECUTABLE_PUBLIC_READ_SHAPE_CANDIDATE_V2",
        )
        != "LOCAL_EXECUTABLE_PUBLIC_READ_SHAPE_CANDIDATE_V2"
        or _string(contract["profile"], PROFILE) != PROFILE
    ):
        _fail("CONTRACT_VALUE_INVALID")
    if _mapping(contract["runtime"]) != _EXPECTED_RUNTIME:
        _fail("AUTHORITY_ESCALATION")
    bindings = _mapping(contract["bindings"])
    if frozenset(bindings) != frozenset(
        key for name in _BINDING_PATHS for key in (f"{name}_uri", f"{name}_sha256")
    ):
        _fail("CONTRACT_MAPPING_INVALID")
    for name, path in _BINDING_PATHS.items():
        _string(bindings[f"{name}_uri"], f"repo://{path.as_posix()}")
        observed = hashlib.sha256(_read_regular(_safe_path(root, path))).hexdigest()
        if observed != _sha(bindings[f"{name}_sha256"]):
            _fail("DEPENDENCY_HASH_DRIFT")
    if _mapping(contract["projection_boundary"]) != _EXPECTED_PROJECTION_BOUNDARY:
        _fail("PROJECTION_BOUNDARY_INVALID")
    if _mapping(contract["compatibility_boundary"]) != _EXPECTED_COMPATIBILITY:
        _fail("COMPATIBILITY_BOUNDARY_INVALID")
    if _mapping(contract["security_boundary"]) != _EXPECTED_SECURITY:
        _fail("SECURITY_BOUNDARY_INVALID")
    if _mapping(contract["execution_boundary"]) != _EXPECTED_EXECUTION:
        _fail("EXECUTION_BOUNDARY_INVALID")
    if _mapping(contract["verification_boundary"]) != _EXPECTED_VERIFICATION:
        _fail("VERIFICATION_BOUNDARY_INVALID")

    role = yaml.safe_load(
        _read_regular(_safe_path(root, _BINDING_PATHS["st0306_role_contract"]))
    )
    role_document = _mapping(cast(object, role))
    public_boundary = _mapping(role_document.get("public_boundary"))
    if public_boundary != {
        "schema_usage": ["readmodel"],
        "table_privileges": ["SELECT"],
        "function_execute": [],
        "all_other_domain_schema_privileges": "NONE",
        "all_other_domain_object_privileges": "NONE",
        "database_owner": False,
        "database_connect_and_temporary": (
            "PREDECESSOR_POSTGRESQL_PUBLIC_BASELINE_UNCHANGED"
        ),
    }:
        _fail("PUBLIC_ROLE_BOUNDARY_DRIFT")
    return contract


def _dependency_bytes(root: Path) -> tuple[bytes, bytes, bytes, bytes, bytes]:
    values = tuple(
        _read_regular(_safe_path(root, path))
        for path in (
            ST0903_FIXTURE_PATH,
            FINAL_APPROVAL_FIXTURE_PATH,
            POLICY_FIXTURE_PATH,
            REVIEW_FIXTURE_PATH,
            SEO_FIXTURE_PATH,
        )
    )
    return values[0], values[1], values[2], values[3], values[4]


def _fixture_bytes(root: Path) -> bytes:
    snapshot, approval, policy, review, seo = _dependency_bytes(root)
    try:
        snapshot_step = load_recorded_publication_snapshot_fixture(
            snapshot,
            final_approval_fixture=approval,
            policy_fixture=policy,
            review_fixture=review,
            seo_fixture=seo,
        )
        step = build_recorded_public_projection_step(
            snapshot_step,
            source_fixture_sha256=hashlib.sha256(snapshot).hexdigest(),
        )
        sources = {
            "final_approval_fixture_sha256": hashlib.sha256(approval).hexdigest(),
            "policy_fixture_sha256": hashlib.sha256(policy).hexdigest(),
            "review_fixture_sha256": hashlib.sha256(review).hexdigest(),
            "seo_fixture_sha256": hashlib.sha256(seo).hexdigest(),
            "st0903_fixture_sha256": hashlib.sha256(snapshot).hexdigest(),
        }
        document = recorded_public_projection_fixture_document(
            sources=sources,
            step=step,
        )
        return canonical_json_bytes(document) + b"\n"
    except PublicProjectionGenerationError:
        raise
    except Exception:
        _fail("FIXTURE_BUILD_FAILED")


def _module_bytes(fixture: bytes) -> bytes:
    digest = hashlib.sha256(fixture).hexdigest()
    return (
        '"""Owner-generated ST-0904 V2 recorded fixture bytes."""\n\n'
        "from typing import Final\n\n"
        f"PUBLIC_PROJECTION_PASS_V2_JSON: Final = {fixture!r}\n"
        "PUBLIC_PROJECTION_PASS_V2_SHA256: Final = (\n"
        f'    "{digest}"\n'
        ")\n\n"
        "__all__ = (\n"
        '    "PUBLIC_PROJECTION_PASS_V2_JSON",\n'
        '    "PUBLIC_PROJECTION_PASS_V2_SHA256",\n'
        ")\n"
    ).encode("utf-8")


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


def _manifest_bytes(root: Path, fixture: bytes, module: bytes) -> bytes:
    sources = [
        *(_artifact(root, path, "OWNER_SOURCE") for path in SOURCE_PATHS),
        *(
            _artifact(root, path, "CANONICAL_OR_DEPENDENCY_INPUT")
            for path in DEPENDENCY_PATHS
        ),
    ]
    generated = [
        {
            "uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "artifact_role": "GENERATED_RECORDED_PUBLIC_PROJECTION_FIXTURE",
            "media_type": "application/json",
            "bytes": len(fixture),
            "sha256": hashlib.sha256(fixture).hexdigest(),
        },
        {
            "uri": f"repo://{MODULE_PATH.as_posix()}",
            "artifact_role": "GENERATED_RUNTIME_MODULE",
            "media_type": "text/x-python",
            "bytes": len(module),
            "sha256": hashlib.sha256(module).hexdigest(),
        },
    ]
    document = {
        "schema_version": 2,
        "story_id": "ST-0904",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_PUBLIC_PROJECTION_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python scripts/build_st0904_public_projection_runtime_v2.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0904_public_projection_runtime_v2.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": hashlib.sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ).hexdigest(),
        },
        "authority": {
            "database_write_authorized": False,
            "public_projection_authorized": False,
            "route_activation_authorized": False,
            "public_read_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_011_status": "NOT_EXECUTED",
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


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st0904-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    root = Path(os.path.abspath(root))
    load_contract(root)
    fixture = _fixture_bytes(root)
    try:
        snapshot, approval, policy, review, seo = _dependency_bytes(root)
        step = load_recorded_public_projection_fixture(
            fixture,
            st0903_fixture=snapshot,
            final_approval_fixture=approval,
            policy_fixture=policy,
            review_fixture=review,
            seo_fixture=seo,
        )
        step.require_valid()
    except Exception:
        _fail("GENERATED_FIXTURE_VALIDATION_FAILED")
    module = _module_bytes(fixture)
    manifest = _manifest_bytes(root, fixture, module)
    expected = (
        (FIXTURE_PATH, fixture),
        (MODULE_PATH, module),
        (MANIFEST_PATH, manifest),
    )
    if check:
        for path, payload in expected:
            if _read_regular(_safe_path(root, path)) != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _replace_generated(
        tuple((_safe_path(root, path), payload) for path, payload in expected)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-0904 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0904 V2 runtime checked"
        if arguments.check
        else "ST-0904 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
