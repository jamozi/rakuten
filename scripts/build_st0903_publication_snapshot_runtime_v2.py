#!/usr/bin/env python3
"""Generate the deterministic ST-0903 V2 snapshot fixture and provenance."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
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

from raos.adapters.recorded_publication_snapshot_v2 import (  # noqa: E402
    build_recorded_publication_snapshot_step,
    load_recorded_publication_snapshot_fixture,
    recorded_publication_snapshot_fixture_document,
)
from raos.domain.publishing.publication_snapshot_v2 import (  # noqa: E402
    PROFILE,
    canonical_json_bytes,
)


CONTRACT_PATH: Final = Path(
    "changes/st-0903/contracts/publication-snapshot-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-0903/generated/publication-snapshot-pass.v2.json"
)
MODULE_PATH: Final = Path(
    "python/raos/adapters/recorded_publication_snapshot_fixture_v2.py"
)
MANIFEST_PATH: Final = Path("changes/st-0903/runtime-manifest.v2.yaml")
FINAL_APPROVAL_FIXTURE_PATH: Final = Path(
    "changes/st-0902/generated/final-approval-pass.v2.json"
)
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
REVIEW_FIXTURE_PATH: Final = Path(
    "changes/st-0901/generated/review-completion-pass.v2.json"
)
SEO_FIXTURE_PATH: Final = Path("changes/st-0807/generated/seo-render-recorded.v2.json")
POLICY_BUNDLE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml"
)
METHODOLOGY_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_recommendation_methodology_v0.1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st0903_publication_snapshot_runtime_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
MAX_GENERATED_BYTES: Final = 16 * 1024 * 1024
SYNTHETIC_MEDIA: Final = b"st0903-recorded-synthetic-media"

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/publishing/publication_snapshot_v2.py"),
    Path("python/raos/ports/publication_snapshot_v2.py"),
    Path("python/raos/application/publishing/publication_snapshot_v2.py"),
    Path("python/raos/adapters/recorded_publication_snapshot_v2.py"),
    Path("changes/st-0903/README-v2.md"),
    Path("changes/st-0903/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0903.md"),
    Path("docs/worklogs/ST-0903.md"),
    Path("tests/st0903_v2/__init__.py"),
    Path("tests/st0903_v2/conftest.py"),
    Path("tests/st0903_v2/test_domain.py"),
    Path("tests/st0903_v2/test_application_adapter.py"),
    Path("tests/st0903_v2/test_generation.py"),
    Path("tests/st0903_v2/test_static_boundary.py"),
)
DEPENDENCY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/08_codex/AGENTS.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"),
    Path("docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"),
    Path(
        "docs/upstream/key_documents/RAOS_06_content_editorial_evidence_design_v0.1.md"
    ),
    Path(
        "contracts/raos-v0.4/contracts/content/schemas/"
        "publication-content-manifest.schema.json"
    ),
    Path(
        "contracts/raos-v0.4/contracts/schemas/common/publication-snapshot.schema.json"
    ),
    POLICY_BUNDLE_PATH,
    METHODOLOGY_PATH,
    FINAL_APPROVAL_FIXTURE_PATH,
    Path("changes/st-0902/runtime-manifest.v2.yaml"),
    Path("python/raos/domain/publishing/final_approval.py"),
    Path("python/raos/adapters/recorded_final_approval.py"),
    POLICY_FIXTURE_PATH,
    REVIEW_FIXTURE_PATH,
    SEO_FIXTURE_PATH,
    Path("changes/st-0807/runtime-manifest.v2.yaml"),
    Path("python/raos/domain/editorial/seo_renderer.py"),
    Path("python/raos/domain/editorial/media_asset.py"),
    Path("python/raos/application/editorial/media_asset.py"),
    Path("python/raos/adapters/recorded_media_asset.py"),
    Path("python/raos/ports/media_asset.py"),
    Path("changes/st-0903/README.md"),
    Path("changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml"),
    Path("changes/st-0903/generated/publication-snapshot-reference-plan.v1.json"),
    Path("changes/st-0903/manifest.yaml"),
    Path("scripts/build_st0903_publication_snapshot_reference_plan.py"),
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
    "fixture",
    "snapshot_boundary",
    "execution_boundary",
    "verification_boundary",
)
_FIXTURE_KEYS: Final = ("fixture_id", "seed")
_BINDING_KEYS: Final = (
    "st0902_final_approval_fixture_uri",
    "st0902_final_approval_fixture_sha256",
    "st0902_runtime_manifest_uri",
    "st0902_runtime_manifest_sha256",
    "st0805_policy_fixture_uri",
    "st0805_policy_fixture_sha256",
    "st0901_review_fixture_uri",
    "st0901_review_fixture_sha256",
    "st0807_seo_fixture_uri",
    "st0807_seo_fixture_sha256",
    "st0807_runtime_manifest_uri",
    "st0807_runtime_manifest_sha256",
    "st0808_domain_uri",
    "st0808_domain_sha256",
    "st0808_application_uri",
    "st0808_application_sha256",
    "st0808_adapter_uri",
    "st0808_adapter_sha256",
    "st0808_port_uri",
    "st0808_port_sha256",
    "methodology_uri",
    "methodology_sha256",
    "policy_bundle_uri",
    "policy_bundle_sha256",
)
_EXPECTED_RUNTIME: Final[dict[str, object]] = {
    "executable": True,
    "provider_mode": "RECORDED_SYNTHETIC_ONLY",
    "process_local_candidate_only": True,
    "repository_write": False,
    "persistence": False,
    "event_emit": False,
    "public_projection_authorized": False,
    "publication_authorized": False,
    "release_authorized": False,
    "production_authorized": False,
}
_EXPECTED_SNAPSHOT_BOUNDARY: Final[dict[str, object]] = {
    "exact_recorded_approved_version_required": True,
    "exact_content_ast_required": True,
    "exact_dependency_hashes_required": True,
    "exact_seo_render_input_required": True,
    "exact_media_validation_input_required": True,
    "self_hash_excluded_from_hash_material": True,
    "deterministic": True,
    "immutable": True,
    "legacy_publication_snapshot_schema_validated": False,
    "legacy_schema_reconciliation_required": True,
    "snapshot_candidate_ready_for_publication": False,
}
_EXPECTED_EXECUTION_BOUNDARY: Final[dict[str, object]] = {
    "network": "FORBIDDEN",
    "credential": "FORBIDDEN",
    "provider": "FORBIDDEN",
    "browser": "FORBIDDEN",
    "database_write": "FORBIDDEN",
    "event_emit": "FORBIDDEN",
    "public_projection": "FORBIDDEN",
    "cms": "FORBIDDEN",
    "media_upload": "FORBIDDEN",
    "plugin_theme": "FORBIDDEN",
    "publication": "FORBIDDEN",
    "staging": "FORBIDDEN",
    "release": "FORBIDDEN",
    "production": "FORBIDDEN",
}
_EXPECTED_VERIFICATION_BOUNDARY: Final[dict[str, object]] = {
    "TST-014": "NOT_EXECUTED",
    "TST-021": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}
_BOUND_FILES: Final = {
    "st0902_final_approval_fixture": FINAL_APPROVAL_FIXTURE_PATH,
    "st0902_runtime_manifest": Path("changes/st-0902/runtime-manifest.v2.yaml"),
    "st0805_policy_fixture": POLICY_FIXTURE_PATH,
    "st0901_review_fixture": REVIEW_FIXTURE_PATH,
    "st0807_seo_fixture": SEO_FIXTURE_PATH,
    "st0807_runtime_manifest": Path("changes/st-0807/runtime-manifest.v2.yaml"),
    "st0808_domain": Path("python/raos/domain/editorial/media_asset.py"),
    "st0808_application": Path("python/raos/application/editorial/media_asset.py"),
    "st0808_adapter": Path("python/raos/adapters/recorded_media_asset.py"),
    "st0808_port": Path("python/raos/ports/media_asset.py"),
    "methodology": METHODOLOGY_PATH,
    "policy_bundle": POLICY_BUNDLE_PATH,
}


class PublicationSnapshotGenerationError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PublicationSnapshotGenerationError(code) from None


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
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            ),
        )
        if type(key) is not str or key in result:
            _fail("CONTRACT_MAPPING_INVALID")
        result[key] = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                value_node, deep=deep
            ),
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


def _mapping(value: object, keys: tuple[str, ...] | None = None) -> dict[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_MAPPING_INVALID")
    result = cast(dict[str, object], value)
    if keys is not None and tuple(result) != keys:
        _fail("CONTRACT_MAPPING_INVALID")
    return result


def _string(value: object, expected: str | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("CONTRACT_VALUE_INVALID")
    if expected is not None and value != expected:
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
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
            yaml.scan(  # pyright: ignore[reportUnknownMemberType]
                payload.decode("utf-8", errors="strict")
            ),
        )
        for token in tokens:
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("CONTRACT_YAML_FEATURE_FORBIDDEN")
        document = yaml.load(payload, Loader=_UniqueLoader)
    except PublicationSnapshotGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    contract = _mapping(document, _ROOT_KEYS)
    if (
        _integer(contract["schema_version"], minimum=2, maximum=2) != 2
        or _string(contract["story_id"], "ST-0903") != "ST-0903"
        or _string(contract["local_status"], "LOCAL_IMPLEMENTATION_COMPLETE")
        != "LOCAL_IMPLEMENTATION_COMPLETE"
        or _string(
            contract["classification"],
            "LOCAL_EXECUTABLE_IMMUTABLE_PUBLICATION_SNAPSHOT_CANDIDATE_V2",
        )
        != "LOCAL_EXECUTABLE_IMMUTABLE_PUBLICATION_SNAPSHOT_CANDIDATE_V2"
        or _string(contract["profile"], PROFILE) != PROFILE
    ):
        _fail("CONTRACT_VALUE_INVALID")
    if _mapping(contract["runtime"]) != _EXPECTED_RUNTIME:
        _fail("AUTHORITY_ESCALATION")
    bindings = _mapping(contract["bindings"], _BINDING_KEYS)
    for name, path in _BOUND_FILES.items():
        _string(bindings[f"{name}_uri"], f"repo://{path.as_posix()}")
        if hashlib.sha256(_read_regular(_safe_path(root, path))).hexdigest() != _sha(
            bindings[f"{name}_sha256"]
        ):
            _fail("DEPENDENCY_HASH_DRIFT")
    fixture = _mapping(contract["fixture"], _FIXTURE_KEYS)
    seed = _mapping(fixture["seed"])
    media = _mapping(seed.get("media"))
    if (
        _integer(seed.get("publication_version"), minimum=1, maximum=1) != 1
        or _integer(media.get("byte_size"), minimum=1, maximum=(1 << 53) - 1)
        != len(SYNTHETIC_MEDIA)
        or _sha(media.get("content_sha256"))
        != hashlib.sha256(SYNTHETIC_MEDIA).hexdigest()
        or _sha(seed.get("policy_bundle_sha256"))
        != _sha(bindings["policy_bundle_sha256"])
        or seed.get("methodology_version_ref") != "RAOS-CONTENT-RECO-001@1.0.0"
        or seed.get("policy_bundle_version_ref") != "RAOS-CONTENT-POLICY-001@0.1"
        or seed.get("disclosure_policy_version_ref") != "POL-CONT-008@0.1"
    ):
        _fail("FIXTURE_SEED_INVALID")
    if _mapping(contract["snapshot_boundary"]) != _EXPECTED_SNAPSHOT_BOUNDARY:
        _fail("SNAPSHOT_BOUNDARY_INVALID")
    if _mapping(contract["execution_boundary"]) != _EXPECTED_EXECUTION_BOUNDARY:
        _fail("EXECUTION_BOUNDARY_INVALID")
    if _mapping(contract["verification_boundary"]) != _EXPECTED_VERIFICATION_BOUNDARY:
        _fail("VERIFICATION_BOUNDARY_INVALID")
    return contract


def _dependency_bytes(root: Path) -> tuple[bytes, bytes, bytes, bytes]:
    values = tuple(
        _read_regular(_safe_path(root, path))
        for path in (
            FINAL_APPROVAL_FIXTURE_PATH,
            POLICY_FIXTURE_PATH,
            REVIEW_FIXTURE_PATH,
            SEO_FIXTURE_PATH,
        )
    )
    return values[0], values[1], values[2], values[3]


def _fixture_bytes(root: Path, contract: Mapping[str, object]) -> bytes:
    fixture = _mapping(contract["fixture"], _FIXTURE_KEYS)
    bindings = _mapping(contract["bindings"], _BINDING_KEYS)
    final_approval, policy, review, seo = _dependency_bytes(root)
    try:
        step = build_recorded_publication_snapshot_step(
            fixture["seed"],
            final_approval_fixture=final_approval,
            policy_fixture=policy,
            review_fixture=review,
            seo_fixture=seo,
        )
        if step.bundle.methodology_sha256.value != _sha(
            bindings["methodology_sha256"]
        ) or step.bundle.policy_bundle_sha256.value != _sha(
            bindings["policy_bundle_sha256"]
        ):
            _fail("DEPENDENCY_BINDING_DRIFT")
        sources = {
            "final_approval_fixture_sha256": hashlib.sha256(final_approval).hexdigest(),
            "policy_fixture_sha256": hashlib.sha256(policy).hexdigest(),
            "review_fixture_sha256": hashlib.sha256(review).hexdigest(),
            "seo_fixture_sha256": hashlib.sha256(seo).hexdigest(),
        }
        document = recorded_publication_snapshot_fixture_document(
            fixture_id=fixture["fixture_id"],
            seed=fixture["seed"],
            sources=sources,
            step=step,
        )
        return canonical_json_bytes(document) + b"\n"
    except PublicationSnapshotGenerationError:
        raise
    except Exception:
        _fail("FIXTURE_BUILD_FAILED")


def _module_bytes(fixture: bytes) -> bytes:
    digest = hashlib.sha256(fixture).hexdigest()
    return (
        '"""Owner-generated ST-0903 V2 recorded fixture bytes."""\n\n'
        "from typing import Final\n\n"
        f"PUBLICATION_SNAPSHOT_PASS_V2_JSON: Final = {fixture!r}\n"
        "PUBLICATION_SNAPSHOT_PASS_V2_SHA256: Final = (\n"
        f'    "{digest}"\n'
        ")\n\n"
        "__all__ = (\n"
        '    "PUBLICATION_SNAPSHOT_PASS_V2_JSON",\n'
        '    "PUBLICATION_SNAPSHOT_PASS_V2_SHA256",\n'
        ")\n"
    ).encode("utf-8")


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
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
            "artifact_role": "GENERATED_RECORDED_FIXTURE",
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
        "story_id": "ST-0903",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_IMMUTABLE_PUBLICATION_SNAPSHOT_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python "
                "scripts/build_st0903_publication_snapshot_runtime_v2.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0903_publication_snapshot_runtime_v2.py --check"
            ),
            "transaction": ("ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK"),
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": hashlib.sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ).hexdigest(),
        },
        "authority": {
            "public_projection_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "formal_tst_014_status": "NOT_EXECUTED",
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
            namespace="st0903-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    root = Path(os.path.abspath(root))
    contract = load_contract(root)
    fixture = _fixture_bytes(root, contract)
    try:
        final_approval, policy, review, seo = _dependency_bytes(root)
        step = load_recorded_publication_snapshot_fixture(
            fixture,
            final_approval_fixture=final_approval,
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
        print("ST-0903 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0903 V2 runtime checked"
        if arguments.check
        else "ST-0903 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
