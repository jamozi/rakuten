#!/usr/bin/env python3
"""Build the content-addressed ST-0807 recorded SEO render evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn, Protocol, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node
from yaml.tokens import AliasToken, AnchorToken, TagToken, Token


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_policy_engine import (  # noqa: E402
    load_recorded_policy_fixture,
)
from raos.domain.editorial.article_lifecycle import (  # noqa: E402
    ArticleVersionState,
    SourcePacketVerification,
)
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    PolicyEvaluationStatusV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.editorial.seo_renderer import (  # noqa: E402
    CONTENT_TEST_MATRIX_SHA256,
    SEO_METADATA_SCHEMA_ID,
    SEO_METADATA_SCHEMA_SHA256,
    SEO_POLICY_ID,
    SEO_POLICY_SHA256,
    SEO_POLICY_VERSION,
    STRUCTURED_DATA_MANIFEST_SCHEMA_ID,
    STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256,
    ArticleSchemaType,
    AuthorKind,
    AuthorProjection,
    BoundEvidence,
    BreadcrumbProjection,
    ChangeAssessment,
    ChangeClassification,
    ContractBindings,
    DisabledSchemaType,
    EligibilityReason,
    ExternalAssessment,
    ExternalAssessmentState,
    ExternalCheck,
    IndexState,
    LocalValidationResult,
    OriginMode,
    OriginSource,
    ReferenceId,
    RenderMode,
    RenderStatus,
    RobotsDirective,
    RouteBinding,
    SeoMetadataCandidate,
    SeoRenderRequest,
    SeoRenderResult,
    Sha256Digest,
    UtcInstant,
    VisibleArticleProjection,
    render_seo,
)
from scripts import secure_generated_publication as secure_publication  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-0807/contracts/seo-render-runtime.v2.yaml")
RESULT_PATH: Final = Path("changes/st-0807/generated/seo-render-recorded.v2.json")
MANIFEST_PATH: Final = Path("changes/st-0807/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0807_seo_render_runtime.py")
GENERATED_PATHS: Final = (RESULT_PATH, MANIFEST_PATH)
POLICY_FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
EXPECTED_CONTRACT_SHA256: Final = (
    "52214c70766473ecf7c09b2df98c8830c2506c09e442e03c835a5c0e7d9b39fc"
)
HARDENED_WRITER_PATH: Final = Path("scripts/secure_generated_publication.py")
HARDENED_WRITER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
V1_RENDERER_SHA256: Final = (
    "8dd849cbb3c99f7c9302c908fe1efdd9567799010ae97b10c3d9bfe57d1287de"
)
ST0805_FIXTURE_SHA256: Final = (
    "75797ab838b37b482ecfd30312101e4103dc7301a4ee57e0f6ce544a845300b9"
)
ST0805_MANIFEST_SHA256: Final = (
    "f10516b1d26e6dc448ade04873880211244e82d1c0f7175b5c57ce2c95f411ce"
)
EXPECTED_UV_VERSION: Final = "0.12.1"
PINNED_UV_PATH: Final = Path("/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv")
GENERATION_COMMAND: Final = (
    f"{PINNED_UV_PATH} run "
    "--locked --offline --no-cache --no-sync --no-env-file "
    "--no-python-downloads python scripts/build_st0807_seo_render_runtime.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
MAXIMUM_CONTRACT_BYTES: Final = 256 * 1024
MAXIMUM_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAXIMUM_OUTPUT_BYTES: Final = 8 * 1024 * 1024
EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SAFE_PATH: Final = re.compile(r"[A-Za-z0-9.][A-Za-z0-9._/-]{0,511}\Z", re.ASCII)

_TOP_LEVEL_KEYS: Final = (
    "document",
    "classification",
    "source_bindings",
    "dependency_boundary",
    "recorded_render",
    "external_assessments",
    "structured_data_boundary",
    "security_controls",
    "authority",
    "execution_boundary",
    "verification_boundary",
)
_EXPECTED_EXTERNAL_NOT_EVALUATED: Final = tuple(
    item.value
    for item in ExternalCheck
    if item is not ExternalCheck.ST_0805_POLICY_ELIGIBILITY
)
_EXPECTED_SECURITY_CONTROLS: Final = (
    "SEC-APP-001",
    "SEC-APP-002",
    "SEC-APP-004",
    "SEC-APP-006",
    "SEC-DATA-003",
    "SEC-DATA-004",
    "SEC-DATA-006",
    "SEC-SDLC-002",
    "SEC-SDLC-006",
    "SEC-SDLC-009",
    "SEC-SDLC-012",
)
_EXPECTED_DISABLED_TYPES: Final = tuple(item.value for item in DisabledSchemaType)
_EXPECTED_ALLOWED_TYPES: Final = (
    "Article",
    "BlogPosting",
    "BreadcrumbList",
    "Organization",
    "WebSite",
)
_EXPECTED_SOURCE_BINDING_PATHS: Final = frozenset(
    {
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "contracts/raos-v0.4/contracts/content/"
        "RAOS_06_seo_metadata_structured_data_policy_v0.1.yaml",
        "contracts/raos-v0.4/contracts/content/schemas/seo-metadata.schema.json",
        "contracts/raos-v0.4/contracts/content/schemas/"
        "structured-data-manifest.schema.json",
        "contracts/raos-v0.4/contracts/content/RAOS_06_content_test_matrix_v0.1.csv",
        "python/raos/domain/editorial/seo_renderer.py",
        "python/raos/domain/editorial/article_lifecycle.py",
        "python/raos/domain/editorial/content_ast.py",
        "python/raos/domain/editorial/policy_engine_v2.py",
        "python/raos/adapters/recorded_policy_engine.py",
        "changes/st-0805/generated/policy-pass.v2.json",
        "changes/st-0805/runtime-manifest.v2.yaml",
    }
)

SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0807/README.md"),
    Path("changes/st-0807/README-v2.md"),
    Path("changes/st-0807/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-0807.md"),
    Path("docs/worklogs/ST-0807.md"),
    GENERATOR_PATH,
    HARDENED_WRITER_PATH,
    Path("python/raos/domain/editorial/seo_renderer.py"),
    Path("tests/st0807/conftest.py"),
    Path("tests/st0807/test_contracts.py"),
    Path("tests/st0807/test_renderer.py"),
    Path("tests/st0807/test_boundaries.py"),
    Path("tests/st0807/test_negative_cases.py"),
    Path("tests/st0807_v2/__init__.py"),
    Path("tests/st0807_v2/conftest.py"),
    Path("tests/st0807_v2/test_recorded_runtime.py"),
    Path("tests/st0807_v2/test_generation.py"),
    Path("tests/st0807_v2/test_boundaries.py"),
    POLICY_FIXTURE_PATH,
    Path("changes/st-0805/runtime-manifest.v2.yaml"),
    Path("python/raos/domain/editorial/article_lifecycle.py"),
    Path("python/raos/domain/editorial/content_ast.py"),
    Path("python/raos/domain/editorial/policy_engine_v2.py"),
    Path("python/raos/adapters/recorded_policy_engine.py"),
    Path(
        "contracts/raos-v0.4/contracts/content/"
        "RAOS_06_seo_metadata_structured_data_policy_v0.1.yaml"
    ),
    Path("contracts/raos-v0.4/contracts/content/schemas/seo-metadata.schema.json"),
    Path(
        "contracts/raos-v0.4/contracts/content/schemas/"
        "structured-data-manifest.schema.json"
    ),
    Path("contracts/raos-v0.4/contracts/content/RAOS_06_content_test_matrix_v0.1.csv"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.toml"),
    Path("uv.lock"),
)


class SeoRuntimeBuildError(RuntimeError):
    """Closed generator failure without source or rejected value material."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise SeoRuntimeBuildError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


class _YamlConstructor(Protocol):
    def construct_object(self, node: Node, deep: bool = False) -> Any: ...


def _construct_mapping(
    loader: _UniqueLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    pairs = cast(list[tuple[Node, Node]], node.value)
    constructor = cast(_YamlConstructor, loader)
    for key_node, value_node in pairs:
        key = constructor.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
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
        result[key] = constructor.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _directory_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
    )


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _read_regular(
    root: object,
    relative: object,
    *,
    maximum_bytes: int = MAXIMUM_SOURCE_BYTES,
) -> bytes:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or _SAFE_PATH.fullmatch(relative.as_posix()) is None
        or type(maximum_bytes) is not int
        or maximum_bytes <= 0
    ):
        _fail("SOURCE_PATH_INVALID")
    root_path = root
    relative_path = relative
    if not root_path.is_absolute():
        _fail("SOURCE_PATH_INVALID")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    directory_bindings: list[tuple[int, str, int, tuple[int, ...]]] = []
    file_descriptor: int | None = None
    try:
        root_before = root_path.lstat()
        if not stat.S_ISDIR(root_before.st_mode) or stat.S_ISLNK(root_before.st_mode):
            _fail("SOURCE_ROOT_INVALID")
        current = os.open(root_path, directory_flags)
        descriptors.append(current)
        root_identity = _directory_identity(root_before)
        if _directory_identity(os.fstat(current)) != root_identity:
            _fail("SOURCE_ROOT_CHANGED")
        for part in relative_path.parts[:-1]:
            before = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
                _fail("SOURCE_PARENT_INVALID")
            child = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(child)
            identity = _directory_identity(before)
            if _directory_identity(os.fstat(child)) != identity:
                _fail("SOURCE_PARENT_CHANGED")
            directory_bindings.append((current, part, child, identity))
            current = child
        name = relative_path.parts[-1]
        before = os.stat(name, dir_fd=current, follow_symlinks=False)
        file_descriptor = os.open(name, file_flags, dir_fd=current)
        opened = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _file_identity(before) != _file_identity(opened)
            or opened.st_nlink != 1
            or opened.st_size <= 0
            or opened.st_size > maximum_bytes
        ):
            _fail("SOURCE_FILE_INVALID")
        chunks: list[bytes] = []
        observed_size = 0
        while True:
            chunk = os.read(file_descriptor, 65_536)
            if not chunk:
                break
            observed_size += len(chunk)
            if observed_size > maximum_bytes:
                _fail("SOURCE_FILE_INVALID")
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(file_descriptor)
        named_after = os.stat(name, dir_fd=current, follow_symlinks=False)
        if (
            _file_identity(after) != _file_identity(opened)
            or _file_identity(named_after) != _file_identity(opened)
            or len(payload) != opened.st_size
        ):
            _fail("SOURCE_FILE_CHANGED")
        if (
            _directory_identity(root_path.lstat()) != root_identity
            or _directory_identity(os.fstat(descriptors[0])) != root_identity
        ):
            _fail("SOURCE_ROOT_CHANGED")
        for parent, part, child, identity in directory_bindings:
            if (
                _directory_identity(os.stat(part, dir_fd=parent, follow_symlinks=False))
                != identity
                or _directory_identity(os.fstat(child)) != identity
            ):
                _fail("SOURCE_PARENT_CHANGED")
    except SeoRuntimeBuildError:
        raise
    except OSError:
        _fail("SOURCE_FILE_UNAVAILABLE")
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return payload


def _require_toolchain(root: Path) -> None:
    """Tool versions are verified once by setup/final."""

    _ = root


def _mapping(value: object, keys: Sequence[str]) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(dict[str, object], value)
    if tuple(result) != tuple(keys):
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _list(value: object, *, maximum: int = 128) -> list[object]:
    if type(value) is not list:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(list[object], value)
    if not 0 <= len(result) <= maximum:
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _text(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail("CONTRACT_VALUE_INVALID")
    return value


def _instant(value: object) -> datetime:
    text = _text(value, maximum=32)
    if not text.endswith("Z"):
        _fail("CONTRACT_VALUE_INVALID")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _fail("CONTRACT_VALUE_INVALID")
    if (
        parsed.tzinfo is not timezone.utc
        or parsed.fold != 0
        or parsed.isoformat().replace("+00:00", "Z") != text
    ):
        _fail("CONTRACT_VALUE_INVALID")
    return parsed


def _load_contract(root: Path) -> Mapping[str, object]:
    raw = _read_regular(
        root,
        CONTRACT_PATH,
        maximum_bytes=MAXIMUM_CONTRACT_BYTES,
    )
    if _sha256(raw) != EXPECTED_CONTRACT_SHA256:
        _fail("CONTRACT_HASH_DRIFT")
    try:
        text = raw.decode("utf-8", errors="strict")
        yaml_module = cast(Any, yaml)
        scan = cast(Callable[[str], Iterable[Token]], yaml_module.scan)
        tokens = scan(text)
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("CONTRACT_YAML_FEATURE_FORBIDDEN")
        loaded = cast(object, yaml.load(text, Loader=_UniqueLoader))
    except SeoRuntimeBuildError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    contract = _mapping(loaded, _TOP_LEVEL_KEYS)
    _validate_contract(contract, root=root)
    return contract


def _validate_contract(contract: Mapping[str, object], *, root: Path) -> None:
    document = _mapping(
        contract["document"],
        (
            "id",
            "version",
            "story_id",
            "status",
            "authority",
            "enabled_by_default",
            "production_eligible",
        ),
    )
    if (
        document["id"] != "RAOS-ST0807-SEO-RENDER-RUNTIME-002"
        or document["version"] != "2.0.0"
        or document["story_id"] != "ST-0807"
        or document["status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document["authority"] != "NONE"
        or _boolean(document["enabled_by_default"]) is not False
        or _boolean(document["production_eligible"]) is not False
        or contract["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_SYNTHETIC_SEO_RENDER_V2"
    ):
        _fail("CONTRACT_DOCUMENT_INVALID")

    bindings = _list(contract["source_bindings"], maximum=64)
    if not bindings:
        _fail("SOURCE_BINDING_INVALID")
    seen: set[str] = set()
    for row in bindings:
        binding = _mapping(row, ("path", "sha256", "owner", "role"))
        path_text = _text(binding["path"])
        digest = _text(binding["sha256"], maximum=64)
        _text(binding["owner"], maximum=64)
        _text(binding["role"], maximum=96)
        if (
            path_text in seen
            or _SHA256.fullmatch(digest) is None
        ):
            _fail("SOURCE_BINDING_INVALID")
        seen.add(path_text)
    if frozenset(seen) != _EXPECTED_SOURCE_BINDING_PATHS:
        _fail("SOURCE_BINDING_INVALID")

    dependencies = _mapping(contract["dependency_boundary"], ("ST-0802", "ST-0805"))
    st0802 = _mapping(
        dependencies["ST-0802"],
        (
            "required_article_version_id",
            "required_state",
            "source_packet_verification",
            "persistence_claimed",
            "publication_claimed",
        ),
    )
    st0805 = _mapping(
        dependencies["ST-0805"],
        (
            "required_status",
            "required_local_eligibility",
            "report_recomputed",
            "receipt_required",
            "waiver_or_finding_applied",
        ),
    )
    if (
        st0802["required_article_version_id"] != "018f3e90-7b00-7000-8000-000000000806"
        or st0802["required_state"] != "DRAFT"
        or st0802["source_packet_verification"] != "NOT_VERIFIED"
        or any(
            _boolean(st0802[key]) is not False
            for key in ("persistence_claimed", "publication_claimed")
        )
        or st0805["required_status"] != "LOCAL_EVALUATED"
        or _boolean(st0805["required_local_eligibility"]) is not True
        or _boolean(st0805["report_recomputed"]) is not True
        or _boolean(st0805["receipt_required"]) is not False
        or _boolean(st0805["waiver_or_finding_applied"]) is not False
    ):
        _fail("DEPENDENCY_BOUNDARY_INVALID")

    render = _mapping(
        contract["recorded_render"],
        (
            "profile",
            "renderer_article_version_ref",
            "seo_metadata_ref",
            "structured_data_manifest_ref",
            "slug",
            "title",
            "meta_description",
            "author_kind",
            "author_name",
            "current_route_ref",
            "current_route",
            "home_route_ref",
            "created_at",
            "validated_at",
            "date_semantics",
            "article_schema_type",
            "mode",
            "origin_mode",
            "caller_origin",
            "site_projection",
        ),
    )
    if dict(render) != {
        "profile": "ST0807_LOCAL_RENDER_V1",
        "renderer_article_version_ref": "018F3E90-7B00-7000-8000-000000000806",
        "seo_metadata_ref": "SEO-METADATA-ST0807-V2",
        "structured_data_manifest_ref": "STRUCTURED-DATA-ST0807-V2",
        "slug": "synthetic-recorded-policy-seo",
        "title": "ST-0805 recorded policy draft",
        "meta_description": (
            "合成済みの編集候補から、公開権限を持たないSEO情報を決定的に生成します。"
        ),
        "author_kind": "Organization",
        "author_name": "RAOS 合成編集部",
        "current_route_ref": "ROUTE-ST0807-V2",
        "current_route": "/guides/synthetic-recorded-policy-seo",
        "home_route_ref": "ROUTE-HOME-ST0807-V2",
        "created_at": "2026-08-24T00:00:00Z",
        "validated_at": "2026-08-24T00:00:00Z",
        "date_semantics": "SYNTHETIC_PREVIEW_INPUT_NOT_PUBLICATION_FACT",
        "article_schema_type": "Article",
        "mode": "PREVIEW",
        "origin_mode": "ROUTE_ONLY",
        "caller_origin": None,
        "site_projection": None,
    }:
        _fail("RECORDED_RENDER_INVALID")

    assessments = _mapping(
        contract["external_assessments"],
        (
            "evaluated",
            "not_evaluated",
            "missing_or_unverified_to_pass",
            "browser_or_live_execution_claimed",
        ),
    )
    evaluated = tuple(_text(item) for item in _list(assessments["evaluated"]))
    not_evaluated = tuple(_text(item) for item in _list(assessments["not_evaluated"]))
    if (
        evaluated != (ExternalCheck.ST_0805_POLICY_ELIGIBILITY.value,)
        or not_evaluated != _EXPECTED_EXTERNAL_NOT_EVALUATED
        or _boolean(assessments["missing_or_unverified_to_pass"]) is not False
        or _boolean(assessments["browser_or_live_execution_claimed"]) is not False
    ):
        _fail("ASSESSMENT_BOUNDARY_INVALID")

    structured = _mapping(
        contract["structured_data_boundary"],
        (
            "allowed_top_level_types",
            "prohibited_recursive_types",
            "visible_content_match_required",
            "arbitrary_html",
            "llm_generated_jsonld",
        ),
    )
    if (
        tuple(_text(item) for item in _list(structured["allowed_top_level_types"]))
        != _EXPECTED_ALLOWED_TYPES
        or tuple(
            _text(item) for item in _list(structured["prohibited_recursive_types"])
        )
        != _EXPECTED_DISABLED_TYPES
        or _boolean(structured["visible_content_match_required"]) is not True
        or _boolean(structured["arbitrary_html"]) is not False
        or _boolean(structured["llm_generated_jsonld"]) is not False
    ):
        _fail("STRUCTURED_DATA_BOUNDARY_INVALID")

    controls = tuple(_text(item) for item in _list(contract["security_controls"]))
    if controls != _EXPECTED_SECURITY_CONTROLS:
        _fail("SECURITY_CONTROL_BOUNDARY_INVALID")
    authority = _mapping(
        contract["authority"],
        (
            "approval_authorized",
            "article_mutation_authorized",
            "policy_apply_authorized",
            "domain_approved",
            "publication_authorized",
            "release_authorized",
            "production_authorized",
            "production_eligible",
        ),
    )
    if any(_boolean(value) is not False for value in authority.values()):
        _fail("AUTHORITY_BOUNDARY_INVALID")
    execution = _mapping(
        contract["execution_boundary"],
        (
            "activation",
            "provider_mode",
            "repository_runtime_read",
            "filesystem_runtime_read",
            "network",
            "credentials",
            "database",
            "browser",
            "staging",
            "publication",
            "release",
            "production",
        ),
    )
    if (
        execution["activation"] != "DISABLED"
        or execution["provider_mode"] != "RECORDED_SYNTHETIC_ONLY"
        or any(
            _boolean(value) is not False
            for key, value in execution.items()
            if key not in {"activation", "provider_mode"}
        )
    ):
        _fail("EXECUTION_BOUNDARY_INVALID")
    verification = _mapping(
        contract["verification_boundary"],
        (
            "TST-020",
            "TST-022",
            "formal_validation",
            "browser",
            "hosted_ci",
            "live",
            "staging",
            "release",
            "publication",
            "production",
        ),
    )
    if any(value != "NOT_EXECUTED" for value in verification.values()):
        _fail("VERIFICATION_BOUNDARY_INVALID")


def _contracts() -> ContractBindings:
    return ContractBindings(
        seo_policy_id=SEO_POLICY_ID,
        seo_policy_version=SEO_POLICY_VERSION,
        seo_policy_sha256=Sha256Digest(SEO_POLICY_SHA256),
        seo_metadata_schema_id=SEO_METADATA_SCHEMA_ID,
        seo_metadata_schema_sha256=Sha256Digest(SEO_METADATA_SCHEMA_SHA256),
        structured_data_manifest_schema_id=STRUCTURED_DATA_MANIFEST_SCHEMA_ID,
        structured_data_manifest_schema_sha256=Sha256Digest(
            STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256
        ),
        content_test_matrix_sha256=Sha256Digest(CONTENT_TEST_MATRIX_SHA256),
    )


def _build_request(
    contract: Mapping[str, object],
    *,
    policy_report_sha256: str,
    visible_content_sha256: str,
) -> SeoRenderRequest:
    material = _mapping(
        contract["recorded_render"],
        (
            "profile",
            "renderer_article_version_ref",
            "seo_metadata_ref",
            "structured_data_manifest_ref",
            "slug",
            "title",
            "meta_description",
            "author_kind",
            "author_name",
            "current_route_ref",
            "current_route",
            "home_route_ref",
            "created_at",
            "validated_at",
            "date_semantics",
            "article_schema_type",
            "mode",
            "origin_mode",
            "caller_origin",
            "site_projection",
        ),
    )
    article_ref = ReferenceId(_text(material["renderer_article_version_ref"]))
    route_ref = ReferenceId(_text(material["current_route_ref"]))
    home_ref = ReferenceId(_text(material["home_route_ref"]))
    created = UtcInstant(_instant(material["created_at"]))
    title = _text(material["title"])
    metadata = SeoMetadataCandidate(
        seo_metadata_id=ReferenceId(_text(material["seo_metadata_ref"])),
        article_version_id=article_ref,
        slug=_text(material["slug"]),
        title=title,
        meta_description=_text(material["meta_description"]),
        canonical_route_ref=route_ref,
        index_state=IndexState.NOINDEX,
        robots=(RobotsDirective.NOINDEX, RobotsDirective.NOFOLLOW),
        breadcrumb_refs=(home_ref, route_ref),
        sitemap_inclusion=False,
        substantive_updated_at=created,
        structured_data_manifest_ref=ReferenceId(
            _text(material["structured_data_manifest_ref"])
        ),
    )
    route = RouteBinding(
        article_version_id=article_ref,
        current_route_ref=route_ref,
        current_route=_text(material["current_route"]),
        canonical_route_ref=route_ref,
        canonical_route=_text(material["current_route"]),
    )
    visible = VisibleArticleProjection(
        article_version_id=article_ref,
        title=title,
        h1=title,
        author=AuthorProjection(
            AuthorKind.ORGANIZATION,
            _text(material["author_name"]),
        ),
        date_published=created,
        date_modified=created,
        visible_content_hash=Sha256Digest(visible_content_sha256),
        visible_content_profile=ReferenceId("ST0807-RECORDED-VISIBLE-AST-V2"),
        visible_content_source_sha256=Sha256Digest(visible_content_sha256),
    )
    assessments = tuple(
        ExternalAssessment(
            article_version_id=article_ref,
            check=check,
            state=(
                ExternalAssessmentState.PASS
                if check is ExternalCheck.ST_0805_POLICY_ELIGIBILITY
                else ExternalAssessmentState.NOT_EVALUATED
            ),
            assessor_ref=(
                ReferenceId("ASSESSOR-ST0805-POLICY-ENGINE-V2")
                if check is ExternalCheck.ST_0805_POLICY_ELIGIBILITY
                else ReferenceId(f"ASSESSOR-{check.value}-NOT-EVALUATED")
            ),
            evidence=(
                BoundEvidence(
                    ReferenceId("EVIDENCE-ST0805-POLICY-REPORT-V2"),
                    Sha256Digest(policy_report_sha256),
                )
                if check is ExternalCheck.ST_0805_POLICY_ELIGIBILITY
                else None
            ),
        )
        for check in ExternalCheck
    )
    return SeoRenderRequest(
        contracts=_contracts(),
        metadata=metadata,
        route=route,
        visible=visible,
        breadcrumbs=(
            BreadcrumbProjection(article_ref, home_ref, 1, "ホーム", "/"),
            BreadcrumbProjection(
                article_ref,
                route_ref,
                2,
                title,
                route.current_route,
            ),
        ),
        site_projection=None,
        article_schema_type=ArticleSchemaType.ARTICLE,
        mode=RenderMode.PREVIEW,
        origin_mode=OriginMode.ROUTE_ONLY,
        caller_origin=None,
        change=ChangeAssessment(
            article_ref,
            ChangeClassification.INITIAL_PUBLICATION,
            None,
        ),
        external_assessments=assessments,
        validated_at=UtcInstant(_instant(material["validated_at"])),
    )


def _assert_safe_result(result: SeoRenderResult) -> None:
    if (
        type(result) is not SeoRenderResult
        or result.status is not RenderStatus.RENDERED_LOCAL
        or result.input_findings
        or result.raw_metadata_candidate is None
        or result.rendered_metadata is None
        or result.rendered_metadata.canonical_url is not None
        or result.rendered_metadata.index_state is not IndexState.NOINDEX
        or result.rendered_metadata.sitemap_inclusion is not False
        or result.structured_data_manifest is None
        or result.structured_data_manifest.validation_result
        is not LocalValidationResult.PASS
        or result.structured_data_manifest.enabled_types != ("Article",)
        or result.structured_data_manifest.disabled_types != tuple(DisabledSchemaType)
        or result.conditional_local_eligibility is not False
        or result.eligibility_reasons
        != (
            EligibilityReason.ROUTE_ONLY_ORIGIN_UNAVAILABLE,
            EligibilityReason.PREVIEW_NOINDEX,
            EligibilityReason.EXTERNAL_ASSESSMENT_NOT_EVALUATED,
        )
        or result.origin_source is not OriginSource.NONE
        or any(
            value is not False
            for value in (
                result.domain_approved,
                result.production_domain_selected,
                result.approval_authorized,
                result.publication_authorized,
                result.release_authorized,
                result.production_authorized,
                result.production_eligible,
                result.formal_evidence,
                result.browser_executed,
                result.staging_executed,
                result.tst_020_executed,
                result.tst_022_executed,
            )
        )
    ):
        _fail("RENDER_RESULT_UNSAFE")
    if result.jsonld_json is None:
        _fail("RENDER_RESULT_UNSAFE")
    try:
        decoded = cast(object, json.loads(result.jsonld_json))
    except Exception:
        _fail("RENDER_RESULT_UNSAFE")
    if type(decoded) is not dict:
        _fail("RENDER_RESULT_UNSAFE")
    jsonld = cast(dict[str, object], decoded)
    graph_value = jsonld.get("@graph")
    graph = cast(list[object], graph_value) if type(graph_value) is list else []
    article = (
        cast(dict[str, object], graph[0]) if graph and type(graph[0]) is dict else {}
    )
    if (
        tuple(jsonld) != ("@context", "@graph")
        or jsonld.get("@context") != "https://schema.org"
        or len(graph) != 1
        or not article
        or article.get("@type") != "Article"
        or any(
            prohibited in result.jsonld_json
            for prohibited in (
                '"Product"',
                '"Offer"',
                '"Review"',
                '"AggregateRating"',
                '"FAQPage"',
            )
        )
    ):
        _fail("RENDER_RESULT_UNSAFE")


def _result_document(root: Path, contract: Mapping[str, object]) -> dict[str, object]:
    fixture_bytes = _read_regular(root, POLICY_FIXTURE_PATH)
    if _sha256(fixture_bytes) != ST0805_FIXTURE_SHA256:
        _fail("ST0805_FIXTURE_HASH_DRIFT")
    try:
        envelope = load_recorded_policy_fixture(fixture_bytes)
        policy_report = evaluate_editorial_policy_v2(envelope)
        policy_report.require_valid()
    except Exception:
        _fail("ST0805_POLICY_INVALID")
    draft = envelope.draft.snapshot
    dependency = _mapping(contract["dependency_boundary"], ("ST-0802", "ST-0805"))
    expected_st0802 = _mapping(
        dependency["ST-0802"],
        (
            "required_article_version_id",
            "required_state",
            "source_packet_verification",
            "persistence_claimed",
            "publication_claimed",
        ),
    )
    if (
        str(draft.version_id) != expected_st0802["required_article_version_id"]
        or draft.state is not ArticleVersionState.DRAFT
        or draft.source_packet_verification is not SourcePacketVerification.NOT_VERIFIED
        or policy_report.status is not PolicyEvaluationStatusV2.LOCAL_EVALUATED
        or policy_report.local_eligibility is not True
        or policy_report.findings
        or policy_report.article_version_id is None
        or policy_report.article_version_id.value != draft.version_id
        or policy_report.canonical_ast_sha256 is None
        or policy_report.canonical_ast_sha256.value != draft.body_sha256.value
        or policy_report.publication_authorized is not False
        or policy_report.approval_authorized is not False
        or policy_report.production_eligible is not False
        or draft.published_at is not None
    ):
        _fail("DEPENDENCY_RESULT_INVALID")
    recorded = _mapping(
        contract["recorded_render"],
        (
            "profile",
            "renderer_article_version_ref",
            "seo_metadata_ref",
            "structured_data_manifest_ref",
            "slug",
            "title",
            "meta_description",
            "author_kind",
            "author_name",
            "current_route_ref",
            "current_route",
            "home_route_ref",
            "created_at",
            "validated_at",
            "date_semantics",
            "article_schema_type",
            "mode",
            "origin_mode",
            "caller_origin",
            "site_projection",
        ),
    )
    if (
        _text(recorded["renderer_article_version_ref"]).casefold()
        != str(draft.version_id)
        or _text(recorded["title"]) != draft.title
        or _instant(recorded["created_at"]) != draft.created_at.value
        or _instant(recorded["validated_at"]) != draft.updated_at.value
        or recorded["date_semantics"] != "SYNTHETIC_PREVIEW_INPUT_NOT_PUBLICATION_FACT"
    ):
        _fail("DEPENDENCY_RESULT_INVALID")
    request = _build_request(
        contract,
        policy_report_sha256=policy_report.report_sha256.value,
        visible_content_sha256=policy_report.canonical_ast_sha256.value,
    )
    result = render_seo(request)
    _assert_safe_result(result)
    try:
        local_result = json.loads(result.local_result_json)
    except Exception:
        _fail("RENDER_RESULT_INVALID")
    return {
        "schema_version": 2,
        "document_id": "RAOS-ST0807-SEO-RENDER-RECORDED-002",
        "story_id": "ST-0807",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "RECORDED_SYNTHETIC_ROUTE_ONLY_PREVIEW",
        "render_date_semantics": recorded["date_semantics"],
        "dependency": {
            "st0802_article_id": str(draft.article_id),
            "st0802_article_version_id": str(draft.version_id),
            "st0802_state": draft.state.value,
            "st0802_published_at": None,
            "st0802_body_sha256": draft.body_sha256.value,
            "st0805_fixture_sha256": ST0805_FIXTURE_SHA256,
            "st0805_evaluation_input_sha256": (
                policy_report.evaluation_input_sha256.value
                if policy_report.evaluation_input_sha256 is not None
                else None
            ),
            "st0805_report_sha256": policy_report.report_sha256.value,
            "st0805_status": policy_report.status.value,
            "st0805_local_eligibility": policy_report.local_eligibility,
        },
        "render": local_result,
        "render_local_result_sha256": result.local_result_digest,
        "jsonld_sha256": (
            result.structured_data_manifest.jsonld_sha256.value
            if result.structured_data_manifest is not None
            else None
        ),
        "authority": {
            "approval_authorized": False,
            "domain_approved": False,
            "policy_apply_authorized": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "production_eligible": False,
        },
        "verification": {
            "TST-020": "NOT_EXECUTED",
            "TST-022": "NOT_EXECUTED",
            "browser": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }


def _json_bytes(value: object) -> bytes:
    try:
        result = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except Exception:
        _fail("OUTPUT_SERIALIZATION_FAILED")
    if not result or len(result) > MAXIMUM_OUTPUT_BYTES:
        _fail("OUTPUT_SIZE_INVALID")
    return result


def _manifest_bytes(root: Path, result_bytes: bytes) -> bytes:
    source_sha256 = {
        path.as_posix(): _sha256(_read_regular(root, path)) for path in SOURCE_PATHS
    }
    manifest: dict[str, object] = {
        "document": {
            "id": "RAOS-ST0807-SEO-RENDER-RUNTIME-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-0807",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "authority": "NONE",
            "production_eligible": False,
        },
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "v1_renderer_sha256": V1_RENDERER_SHA256,
        "st0805_fixture_sha256": ST0805_FIXTURE_SHA256,
        "st0805_manifest_sha256": ST0805_MANIFEST_SHA256,
        "hardened_writer_sha256": HARDENED_WRITER_SHA256,
        "source_sha256": source_sha256,
        "generated_sha256": {RESULT_PATH.as_posix(): _sha256(result_bytes)},
        "generation": {
            "command": GENERATION_COMMAND,
            "check_command": CHECK_COMMAND,
        },
        "toolchain": {
            "uv_version": EXPECTED_UV_VERSION,
            "python_implementation": EXPECTED_PYTHON_IMPLEMENTATION,
            "python_version": ".".join(str(item) for item in EXPECTED_PYTHON_VERSION),
            "pyyaml_version": EXPECTED_PYYAML_VERSION,
        },
        "bounds": {
            "activation": "DISABLED",
            "provider_mode": "RECORDED_SYNTHETIC_ONLY",
            "origin_mode": "ROUTE_ONLY",
            "render_mode": "PREVIEW",
            "network": False,
            "credentials": False,
            "database": False,
            "browser": False,
            "publication": False,
            "release": False,
            "production": False,
        },
        "formal_TST_020": "NOT_EXECUTED",
        "formal_TST_022": "NOT_EXECUTED",
    }
    try:
        encoded = yaml.safe_dump(
            manifest,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8", errors="strict")
    except Exception:
        _fail("MANIFEST_SERIALIZATION_FAILED")
    if not encoded or len(encoded) > MAXIMUM_OUTPUT_BYTES:
        _fail("OUTPUT_SIZE_INVALID")
    return encoded


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_publication.publish_generated(
            artifacts,
            namespace="st0807-seo-v2",
            maximum_payload_bytes=MAXIMUM_OUTPUT_BYTES,
        )
    except secure_publication.SecurePublicationError:
        _fail("SECURE_PUBLICATION_FAILED")


def _check_generated(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    for path, expected in artifacts:
        relative = path.relative_to(root)
        observed = _read_regular(
            root,
            relative,
            maximum_bytes=MAXIMUM_OUTPUT_BYTES,
        )
        if observed != expected:
            _fail("GENERATED_DRIFT")


def build(root: object = REPO_ROOT, *, check: bool = False) -> None:
    if not isinstance(root, Path) or not root.is_absolute() or type(check) is not bool:
        _fail("BUILD_INPUT_INVALID")
    root_path = root
    _require_toolchain(root_path)
    contract = _load_contract(root_path)
    result_bytes = _json_bytes(_result_document(root_path, contract))
    manifest_bytes = _manifest_bytes(root_path, result_bytes)
    artifacts = (
        (root_path / RESULT_PATH, result_bytes),
        (root_path / MANIFEST_PATH, manifest_bytes),
    )
    if check:
        _check_generated(root_path, artifacts)
    else:
        _replace_generated(artifacts)


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic ST-0807 local recorded artifacts."
    )
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(REPO_ROOT, check=arguments.check)
    except SeoRuntimeBuildError as error:
        print(error.code, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
