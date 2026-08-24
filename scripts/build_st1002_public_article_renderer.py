#!/usr/bin/env python3
"""Build deterministic recorded-only ST-1002 article-renderer artifacts."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Callable, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import secure_generated_publication  # noqa: E402


EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

CONTRACT_PATH: Final = Path(
    "changes/st-1002/contracts/public-article-renderer-runtime.v2.yaml"
)
SOURCE_FIXTURE_PATH: Final = Path(
    "changes/st-0904/generated/public-projection-recorded.v2.json"
)
GENERATED_SOURCE_PATH: Final = Path("packages/web-ui/src/public-article-recorded.v2.ts")
RENDERED_FIXTURE_PATH: Final = Path(
    "changes/st-1002/generated/public-article-renderer-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1002/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1002_public_article_renderer.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")

CANONICAL_HASHES: Final = {
    Path(
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
    ): "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    Path(
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
    ): "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    Path(
        "docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md"
    ): "0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e",
    Path(
        "docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"
    ): "dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050",
    Path(
        "docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml"
    ): "986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2",
    Path(
        "docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv"
    ): "690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e",
    Path(
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    ): "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    Path(
        "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"
    ): "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    Path(
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    ): "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    Path(
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    ): "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
}

DEPENDENCY_HASHES: Final = {
    SOURCE_FIXTURE_PATH: "d73a112ccb1879e0f8e8fc5f6f52e75d1c9c2802d761aede81003f9343fefce1",
    Path(
        "changes/st-0904/runtime-manifest.v2.yaml"
    ): "463887fc57ccc2aeda2a1707eef302962c730bf1c19f6f59bfb986bf3523be9f",
    Path(
        "changes/st-0904/contracts/public-projection-runtime.v2.yaml"
    ): "210961b25d78bc3f9f7994855eea425a813b9e978d52709fa26618f2653a5463",
    Path(
        "changes/st-1001/contracts/public-app-shell-runtime.v2.yaml"
    ): "e916db42258a52ab30139349fd13f0d64742f21464882ef10bc282276201f459",
    Path(
        "changes/st-1001/generated/public-app-shell-recorded.v2.json"
    ): "b773e2d507d47df856bb8e72c25811c83dd44bcdfcec004ee9b659446cda823e",
    Path(
        "contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml"
    ): "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797",
    SECURE_HELPER_PATH: "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e",
}

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("packages/web-ui/src/public-article-renderer.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("apps/web/app/articles/[slug]/page.tsx"),
    Path("apps/web/app/articles/[slug]/article.module.css"),
    Path("apps/web/src/public-article-page.tsx"),
    Path("apps/web/proxy.ts"),
    Path("scripts/check_st1002_public_article_browser.mjs"),
    Path("tests/st1002/public-article-renderer-boundaries.test.ts"),
    Path("tests/st1002_v2/public-article-model.test.ts"),
    Path("tests/st1002_v2/public-article-negative.test.ts"),
    Path("tests/st1002_v2/public-article-static.test.ts"),
    Path("tests/st1002_v2/public-article-generated-contract.test.ts"),
    Path("tests/st1002_v2/public-article-accessibility.test.ts"),
    Path("tests/st1002_v2/test_generation.py"),
    Path("changes/st-1002/README-v2.md"),
    Path("changes/st-1002/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-1002.md"),
    Path("docs/worklogs/ST-1002.md"),
)
SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *CANONICAL_HASHES,
    *DEPENDENCY_HASHES,
    Path("package.json"),
    Path("package-lock.json"),
    Path("apps/web/package.json"),
)
GENERATED_PATHS: Final = (
    GENERATED_SOURCE_PATH,
    RENDERED_FIXTURE_PATH,
    MANIFEST_PATH,
)

SOURCE_PROFILE: Final = "ST0904_PUBLIC_PROJECTION_RECORDED_LOCAL_V2"
SOURCE_PROJECTION_SHA256: Final = (
    "4c5d4c8e2f2465d53d2ead84cd20e9ea9328b353854d0b365bcde63211ef1980"
)
EXPECTED_SLUG: Final = "synthetic-recorded-policy-seo"
SOURCE_PATH: Final = f"/{EXPECTED_SLUG}/"
LOCAL_PATH: Final = f"/articles/{EXPECTED_SLUG}"
SAFE_BLOCK_TYPES: Final = frozenset(
    {
        "paragraph",
        "summary",
        "suitable_unsuitable",
        "source_note",
        "selection_criteria",
        "comparison_table",
        "warning",
    }
)
SOURCE_TYPE_ORDER: Final = (
    "lead",
    "decision_summary",
    "intended_reader",
    "methodology",
    "selection_criteria",
    "comparison_table",
    "recommendation_group",
    "caution",
    "source_summary",
)
SOURCE_BLOCK_TYPE: Final = {
    "lead": "paragraph",
    "decision_summary": "summary",
    "intended_reader": "suitable_unsuitable",
    "methodology": "source_note",
    "selection_criteria": "selection_criteria",
    "comparison_table": "comparison_table",
    "recommendation_group": "summary",
    "caution": "warning",
    "source_summary": "source_note",
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SAFE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
ACTIVE_TEXT = re.compile(
    r"(?:<\s*[a-z!/]|(?:https?|ftp|file|javascript|data|vbscript):|//|\bon[a-z]+\s*=)",
    re.IGNORECASE,
)
PROHIBITED_KEY_PARTS: Final = (
    "approvalid",
    "articleid",
    "publicationid",
    "snapshotid",
    "claim",
    "evidence",
    "finance",
    "commission",
    "revenue",
    "profit",
    "epc",
    "rpm",
    "rawprompt",
    "reviewbody",
    "sourcepacket",
    "credential",
    "secret",
    "token",
    "password",
    "affiliateurl",
)


class PublicArticleBuildError(RuntimeError):
    """Closed owner-generator refusal."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PublicArticleBuildError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


class _IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, indentless=False)


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            _fail("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_compact(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail("SERIALIZATION_FAILED")


def _canonical_pretty(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail("SERIALIZATION_FAILED")


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
    ):
        _fail("PYTHON_TOOLCHAIN_INVALID")
    try:
        installed = distribution_version("PyYAML")
    except PackageNotFoundError:
        _fail("PYYAML_TOOLCHAIN_INVALID")
    if installed != EXPECTED_PYYAML_VERSION:
        _fail("PYYAML_TOOLCHAIN_INVALID")


def _safe_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("SOURCE_PATH_INVALID")
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
        root_stat = absolute_root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            _fail("SOURCE_ROOT_INVALID")
        cursor = absolute_root
        for part in relative.parts[:-1]:
            cursor /= part
            current = cursor.lstat()
            if not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode):
                _fail("SOURCE_PARENT_INVALID")
    except FileNotFoundError:
        _fail("SOURCE_PATH_MISSING")
    except ValueError:
        _fail("SOURCE_PATH_INVALID")
    return candidate


def _read_regular(root: Path, relative: Path) -> bytes:
    path = _safe_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail("SOURCE_LEAF_INVALID")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            if (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ) != identity:
                _fail("SOURCE_IDENTITY_CHANGED")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail("SOURCE_READ_TRUNCATED")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("SOURCE_READ_GREW")
            after = os.fstat(descriptor)
            named = path.lstat()
            if (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) != identity or (
                named.st_dev,
                named.st_ino,
                named.st_size,
                named.st_mtime_ns,
            ) != identity:
                _fail("SOURCE_IDENTITY_CHANGED")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except PublicArticleBuildError:
        raise
    except OSError, ValueError:
        _fail("SOURCE_READ_FAILED")


def _parse_json(payload: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                _fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: _fail("JSON_INVALID"),
        )
    except PublicArticleBuildError:
        raise
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        _fail("JSON_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("JSON_INVALID")
    return cast(dict[str, object], value)


def _parse_yaml(payload: bytes, *, trusted: bool = False) -> dict[str, object]:
    try:
        text = payload.decode("utf-8", errors="strict")
        if not trusted and any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in yaml.scan(text)
        ):
            _fail("YAML_FEATURE_FORBIDDEN")
        loader = _UniqueLoader(text)
        try:
            value = loader.get_single_data()
        finally:
            cast(Callable[[], None], loader.dispose)()
    except PublicArticleBuildError:
        raise
    except UnicodeDecodeError, yaml.YAMLError, RecursionError, TypeError:
        _fail("YAML_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("YAML_INVALID")
    return cast(dict[str, object], value)


def _mapping(value: object, code: str) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail(code)
    return cast(dict[str, object], value)


def _sequence(value: object, code: str) -> list[object]:
    if type(value) is not list:
        _fail(code)
    return cast(list[object], value)


def _text(value: object, code: str, *, maximum: int = 1000) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        _fail(code)
    return value


def _exact(value: dict[str, object], keys: set[str], code: str) -> None:
    if set(value) != keys:
        _fail(code)


def _validate_source_bindings(root: Path, contract: dict[str, object]) -> None:
    records = _sequence(contract.get("canonical_bindings"), "CANONICAL_BINDING_INVALID")
    expected = [(path.as_posix(), digest) for path, digest in CANONICAL_HASHES.items()]
    actual: list[tuple[str, str]] = []
    for raw in records:
        record = _mapping(raw, "CANONICAL_BINDING_INVALID")
        _exact(record, {"path", "sha256"}, "CANONICAL_BINDING_INVALID")
        actual.append(
            (
                _text(record.get("path"), "CANONICAL_BINDING_INVALID"),
                _text(record.get("sha256"), "CANONICAL_BINDING_INVALID"),
            )
        )
    if actual != expected:
        _fail("CANONICAL_BINDING_INVALID")
    for path, digest in {**CANONICAL_HASHES, **DEPENDENCY_HASHES}.items():
        if _sha(_read_regular(root, path)) != digest:
            _fail("DEPENDENCY_BINDING_DRIFT")


def _validate_catalogs(root: Path) -> None:
    backlog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
        ),
        trusted=True,
    )
    stories = _sequence(backlog.get("stories"), "STORY_CATALOG_INVALID")
    selected = [
        _mapping(item, "STORY_CATALOG_INVALID")
        for item in stories
        if _mapping(item, "STORY_CATALOG_INVALID").get("id") == "ST-1002"
    ]
    if len(selected) != 1:
        _fail("STORY_CATALOG_INVALID")
    story = selected[0]
    if (
        story.get("title") != "Public article renderer"
        or story.get("objective") != "Publication SnapshotからASTを描画"
        or story.get("depends_on") != ["ST-0904", "ST-1001"]
        or story.get("deliverables") != ["article route/components"]
        or story.get("acceptance_criteria") != ["hash-bound", "no internal fields"]
        or story.get("test_suites") != ["TST-021", "TST-022", "TST-023"]
        or story.get("open_decisions") != []
    ):
        _fail("STORY_CATALOG_INVALID")

    screens = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml")
        ),
        trusted=True,
    )
    records = _sequence(screens.get("screens"), "SCREEN_CATALOG_INVALID")
    chosen = [
        _mapping(item, "SCREEN_CATALOG_INVALID")
        for item in records
        if _mapping(item, "SCREEN_CATALOG_INVALID").get("id") == "PUB-003"
    ]
    if len(chosen) != 1 or (
        chosen[0].get("name"),
        chosen[0].get("route"),
        chosen[0].get("purpose"),
    ) != ("記事詳細", "/articles/{slug}", "承認済みPublication Snapshotを表示"):
        _fail("SCREEN_CATALOG_INVALID")

    suites = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml")
        ),
        trusted=True,
    )
    suite_records = _sequence(suites.get("suites"), "TEST_CATALOG_INVALID")
    selected_ids = [
        _mapping(item, "TEST_CATALOG_INVALID").get("id")
        for item in suite_records
        if _mapping(item, "TEST_CATALOG_INVALID").get("id")
        in {"TST-021", "TST-022", "TST-023"}
    ]
    if selected_ids != ["TST-021", "TST-022", "TST-023"]:
        _fail("TEST_CATALOG_INVALID")


def _validate_contract(root: Path) -> dict[str, object]:
    contract = _parse_yaml(_read_regular(root, CONTRACT_PATH))
    document = _mapping(contract.get("document"), "CONTRACT_INVALID")
    if (
        document.get("id") != "RAOS-ST1002-PUBLIC-ARTICLE-RENDERER-RUNTIME-002"
        or document.get("version") != "2.0.0"
        or document.get("story_id") != "ST-1002"
        or document.get("status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document.get("authority") != "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY"
        or document.get("enabled_environments") != ["DEV", "CI"]
        or document.get("enabled_by_default_outside_local") is not False
        or contract.get("classification")
        != "LOCAL_RECORDED_NOINDEX_SSR_ARTICLE_PREVIEW_V2"
    ):
        _fail("CONTRACT_INVALID")
    _validate_source_bindings(root, contract)
    _validate_catalogs(root)

    route = _mapping(contract.get("route"), "ROUTE_CONTRACT_INVALID")
    if route != {
        "screen_id": "PUB-003",
        "template": "/articles/{slug}",
        "slug": EXPECTED_SLUG,
        "local_path": LOCAL_PATH,
        "exact_slug_only": True,
        "unknown_or_malformed_status": 404,
        "unknown_value_reflected": False,
        "local_route_registered": True,
        "source_projection_route_activated": False,
    }:
        _fail("ROUTE_CONTRACT_INVALID")

    dependency = _mapping(contract.get("dependency_bindings"), "DEPENDENCY_INVALID")
    st0904 = _mapping(dependency.get("ST-0904"), "DEPENDENCY_INVALID")
    if (
        st0904.get("fixture") != SOURCE_FIXTURE_PATH.as_posix()
        or st0904.get("fixture_sha256") != DEPENDENCY_HASHES[SOURCE_FIXTURE_PATH]
        or st0904.get("profile") != SOURCE_PROFILE
        or st0904.get("projection_sha256") != SOURCE_PROJECTION_SHA256
        or st0904.get("source_route_path") != SOURCE_PATH
        or st0904.get("source_route_activated") is not False
        or st0904.get("public_read_served") is not False
    ):
        _fail("DEPENDENCY_INVALID")

    mapping = _mapping(contract.get("render_mapping"), "MAPPING_INVALID")
    source_types = _mapping(mapping.get("source_types"), "MAPPING_INVALID")
    if tuple(source_types) != SOURCE_TYPE_ORDER:
        _fail("MAPPING_INVALID")
    for source_type, record_raw in source_types.items():
        record = _mapping(record_raw, "MAPPING_INVALID")
        if set(record) != {"view_kind", "heading"}:
            _fail("MAPPING_INVALID")
        _text(record.get("view_kind"), "MAPPING_INVALID")
        heading = record.get("heading")
        if heading is not None:
            _text(heading, "MAPPING_INVALID", maximum=80)
    for key in (
        "raw_html_allowed",
        "product_cards_rendered",
        "offers_rendered",
        "affiliate_cta_rendered",
        "comparison_rendered",
        "structured_data_rendered",
        "canonical_url_rendered",
        "internal_identifiers_rendered",
    ):
        if mapping.get(key) is not False:
            _fail("MAPPING_INVALID")
    if (
        mapping.get("client_component_count") != 0
        or mapping.get("javascript_required_for_reading") is not False
        or mapping.get("empty_blocks_omitted") is not True
    ):
        _fail("MAPPING_INVALID")

    metadata = _mapping(contract.get("metadata_policy"), "METADATA_INVALID")
    robots = _mapping(metadata.get("robots"), "METADATA_INVALID")
    if (
        metadata.get("canonical_url") is not None
        or metadata.get("open_graph") is not None
        or metadata.get("twitter") is not None
        or metadata.get("source_title_only") is not True
        or metadata.get("source_description_only") is not True
        or robots
        != {
            "index": False,
            "follow": False,
            "noarchive": True,
            "nosnippet": True,
            "noimageindex": True,
            "nocache": True,
        }
        or metadata.get("response_header")
        != "noindex, nofollow, noarchive, nosnippet, noimageindex"
    ):
        _fail("METADATA_INVALID")
    authority = _mapping(contract.get("authority"), "AUTHORITY_INVALID")
    if any(
        (type(value) is bool and value is not False)
        or (type(value) is str and value != "NOT_EXECUTED")
        or type(value) not in {bool, str}
        for value in authority.values()
    ):
        _fail("AUTHORITY_INVALID")
    return contract


def _safe_public_text(value: object, code: str, *, maximum: int = 1000) -> str:
    result = _text(value, code, maximum=maximum)
    if ACTIVE_TEXT.search(result):
        _fail(code)
    return result


def _validate_projected_output_tree(value: object) -> None:
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        if "\x00" in value:
            _fail("PUBLIC_OUTPUT_INVALID")
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _validate_projected_output_tree(item)
        return
    if type(value) is not dict:
        _fail("PUBLIC_OUTPUT_INVALID")
    for key, item in cast(dict[object, object], value).items():
        if type(key) is not str:
            _fail("PUBLIC_OUTPUT_INVALID")
        normalized = re.sub(r"[\s_-]+", "", key).lower()
        if any(part in normalized for part in PROHIBITED_KEY_PARTS):
            _fail("PUBLIC_OUTPUT_INTERNAL_FIELD")
        _validate_projected_output_tree(item)


def _recorded_source(root: Path, contract: dict[str, object]) -> dict[str, object]:
    payload = _read_regular(root, SOURCE_FIXTURE_PATH)
    if _sha(payload) != DEPENDENCY_HASHES[SOURCE_FIXTURE_PATH]:
        _fail("SOURCE_FIXTURE_HASH_MISMATCH")
    fixture = _parse_json(payload)
    if (
        fixture.get("story_id") != "ST-0904"
        or fixture.get("schema_version") != 2
        or fixture.get("profile") != SOURCE_PROFILE
        or fixture.get("local_status") != "LOCAL_IMPLEMENTATION_COMPLETE"
    ):
        _fail("SOURCE_FIXTURE_INVALID")
    authority = _mapping(fixture.get("authority"), "SOURCE_FIXTURE_INVALID")
    if any(
        (type(value) is bool and value is not False)
        or (type(value) is str and value != "NOT_EXECUTED")
        or type(value) not in {bool, str}
        for value in authority.values()
    ):
        _fail("SOURCE_AUTHORITY_INVALID")

    output = _mapping(fixture.get("output"), "SOURCE_FIXTURE_INVALID")
    projection = _mapping(output.get("projection"), "SOURCE_FIXTURE_INVALID")
    result_text = _text(output.get("result"), "SOURCE_FIXTURE_INVALID", maximum=20_000)
    result = _parse_json(result_text.encode("ascii"))
    if (
        result.get("profile") != SOURCE_PROFILE
        or result.get("projection_sha256") != SOURCE_PROJECTION_SHA256
        or result.get("route_activated") is not False
        or result.get("public_read_served") is not False
        or result.get("public_projection_authorized") is not False
        or result.get("publication_authorized") is not False
        or result.get("release_authorized") is not False
        or result.get("production_authorized") is not False
        or _sha(_canonical_compact(projection)) != SOURCE_PROJECTION_SHA256
    ):
        _fail("SOURCE_PROJECTION_HASH_MISMATCH")

    _exact(
        projection,
        {"article", "projection_generation", "route", "row_counts"},
        "SOURCE_PROJECTION_INVALID",
    )
    article = _mapping(projection.get("article"), "SOURCE_ARTICLE_INVALID")
    route = _mapping(projection.get("route"), "SOURCE_ROUTE_INVALID")
    counts = _mapping(projection.get("row_counts"), "SOURCE_ROUTE_INVALID")
    if (
        projection.get("projection_generation") != 1
        or route.get("path") != SOURCE_PATH
        or route.get("route_type") != "ARTICLE"
        or route.get("http_status") != 200
        or route.get("redirect_path") is not None
        or route.get("is_indexable") is not False
        or route.get("projection_generation") != 1
        or counts
        != {
            "public_article": 1,
            "public_article_block": 9,
            "public_offer": 0,
            "public_product_card": 0,
            "public_route": 1,
        }
    ):
        _fail("SOURCE_ROUTE_INVALID")
    if (
        article.get("canonical_path") != SOURCE_PATH
        or article.get("language_tag") != "ja-JP"
        or article.get("freshness_status") != "UNKNOWN"
        or article.get("is_indexable") is not False
        or article.get("projection_generation") != 1
        or article.get("product_cards") != []
        or article.get("structured_data") != {}
        or article.get("excerpt") is not None
        or article.get("updated_public_at") is not None
    ):
        _fail("SOURCE_ARTICLE_INVALID")

    title = _safe_public_text(
        article.get("title"), "SOURCE_ARTICLE_INVALID", maximum=160
    )
    meta_title = _safe_public_text(
        article.get("meta_title"), "SOURCE_ARTICLE_INVALID", maximum=160
    )
    description = _safe_public_text(
        article.get("meta_description"), "SOURCE_ARTICLE_INVALID", maximum=320
    )
    disclosure = _safe_public_text(
        article.get("disclosure_text"), "SOURCE_ARTICLE_INVALID", maximum=320
    )
    blocks_raw = _sequence(article.get("blocks"), "SOURCE_BLOCK_INVALID")
    if len(blocks_raw) != len(SOURCE_TYPE_ORDER):
        _fail("SOURCE_BLOCK_INVALID")
    mappings = _mapping(
        _mapping(contract.get("render_mapping"), "MAPPING_INVALID").get("source_types"),
        "MAPPING_INVALID",
    )
    blocks: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for position, (raw, expected_source_type) in enumerate(
        zip(blocks_raw, SOURCE_TYPE_ORDER, strict=True)
    ):
        block = _mapping(raw, "SOURCE_BLOCK_INVALID")
        _exact(
            block,
            {
                "block_key",
                "block_type",
                "heading_level",
                "heading_text",
                "position",
                "render_payload",
                "rendered_html",
            },
            "SOURCE_BLOCK_INVALID",
        )
        block_key = _safe_public_text(
            block.get("block_key"), "SOURCE_BLOCK_INVALID", maximum=80
        )
        block_type = _safe_public_text(
            block.get("block_type"), "SOURCE_BLOCK_INVALID", maximum=40
        )
        payload_record = _mapping(block.get("render_payload"), "SOURCE_BLOCK_INVALID")
        _exact(payload_record, {"source_type", "text"}, "SOURCE_BLOCK_INVALID")
        source_type = _safe_public_text(
            payload_record.get("source_type"), "SOURCE_BLOCK_INVALID", maximum=60
        )
        text_items = [
            _safe_public_text(item, "SOURCE_BLOCK_INVALID")
            for item in _sequence(payload_record.get("text"), "SOURCE_BLOCK_INVALID")
        ]
        if (
            block_key in seen_keys
            or block.get("position") != position
            or block_type not in SAFE_BLOCK_TYPES
            or source_type != expected_source_type
            or block_type != SOURCE_BLOCK_TYPE[source_type]
            or block.get("heading_level") is not None
            or block.get("heading_text") is not None
            or block.get("rendered_html") is not None
        ):
            _fail("SOURCE_BLOCK_INVALID")
        seen_keys.add(block_key)
        view = _mapping(mappings.get(source_type), "MAPPING_INVALID")
        if source_type in {"comparison_table", "source_summary"} and text_items:
            _fail("DOWNSTREAM_SURFACE_PRESENT")
        blocks.append(
            {
                "blockKey": block_key,
                "blockType": block_type,
                "position": position,
                "sourceType": source_type,
                "text": text_items,
                "viewKind": view["view_kind"],
                "heading": view["heading"],
            }
        )

    preview = _mapping(contract.get("preview_copy"), "PREVIEW_COPY_INVALID")
    source = {
        "schemaVersion": 2,
        "storyId": "ST-1002",
        "classification": "EXACT_ST0904_V2_RECORDED_PUBLIC_ARTICLE_SOURCE",
        "sourceBinding": {
            "fixtureUri": f"repo://{SOURCE_FIXTURE_PATH.as_posix()}",
            "fixtureSha256": DEPENDENCY_HASHES[SOURCE_FIXTURE_PATH],
            "projectionSha256": SOURCE_PROJECTION_SHA256,
            "profile": SOURCE_PROFILE,
            "fixtureHashVerifiedByOwner": True,
            "projectionHashVerifiedByOwner": True,
        },
        "route": {
            "screenId": "PUB-003",
            "template": "/articles/{slug}",
            "slug": EXPECTED_SLUG,
            "path": LOCAL_PATH,
            "sourcePath": SOURCE_PATH,
            "exactSlugOnly": True,
            "sourceRouteActivated": False,
        },
        "article": {
            "title": title,
            "metaTitle": meta_title,
            "metaDescription": description,
            "disclosureText": disclosure,
            "languageTag": "ja-JP",
            "freshnessStatus": "UNKNOWN",
            "isIndexable": False,
            "blocks": blocks,
        },
        "presentation": {
            "eyebrow": _safe_public_text(
                preview.get("eyebrow"), "PREVIEW_COPY_INVALID", maximum=80
            ),
            "previewLabel": _safe_public_text(
                preview.get("label"), "PREVIEW_COPY_INVALID", maximum=100
            ),
            "previewMessage": _safe_public_text(
                preview.get("message"), "PREVIEW_COPY_INVALID", maximum=400
            ),
            "freshnessUnknown": _safe_public_text(
                preview.get("freshness_unknown"),
                "PREVIEW_COPY_INVALID",
                maximum=100,
            ),
            "breadcrumbRoot": _safe_public_text(
                preview.get("breadcrumb_root"),
                "PREVIEW_COPY_INVALID",
                maximum=80,
            ),
            "skipLink": _safe_public_text(
                preview.get("skip_link"), "PREVIEW_COPY_INVALID", maximum=80
            ),
        },
    }
    _validate_projected_output_tree(source)
    return source


def _view_fixture(
    source: dict[str, object], contract: dict[str, object]
) -> dict[str, object]:
    route = _mapping(source["route"], "SOURCE_ROUTE_INVALID")
    article = _mapping(source["article"], "SOURCE_ARTICLE_INVALID")
    presentation = _mapping(source["presentation"], "PREVIEW_COPY_INVALID")
    sections: list[dict[str, object]] = []
    lead: list[str] = []
    omitted: list[dict[str, object]] = []
    for raw in _sequence(article["blocks"], "SOURCE_BLOCK_INVALID"):
        block = _mapping(raw, "SOURCE_BLOCK_INVALID")
        text = cast(list[str], block["text"])
        if block["viewKind"] == "LEAD":
            lead.extend(text)
        elif str(block["viewKind"]).startswith("OMITTED_"):
            omitted.append(
                {
                    "blockKey": block["blockKey"],
                    "reason": block["viewKind"],
                }
            )
        else:
            sections.append(
                {
                    "blockKey": block["blockKey"],
                    "kind": block["viewKind"],
                    "heading": block["heading"],
                    "items": text,
                }
            )
    metadata = _mapping(contract["metadata_policy"], "METADATA_INVALID")
    runtime = _mapping(contract["runtime_boundary"], "RUNTIME_INVALID")
    authority = _mapping(contract["authority"], "AUTHORITY_INVALID")
    fixture = {
        "schemaVersion": 2,
        "storyId": "ST-1002",
        "classification": contract["classification"],
        "screen": {
            "id": "PUB-003",
            "name": "記事詳細",
            "routeTemplate": "/articles/{slug}",
        },
        "route": {
            "slug": route["slug"],
            "path": route["path"],
            "localRouteRegistered": True,
            "sourceRouteActivated": False,
            "exactSlugOnly": True,
        },
        "metadata": {
            "title": article["metaTitle"],
            "description": article["metaDescription"],
            "canonical": None,
            "openGraph": None,
            "twitter": None,
            "robots": metadata["robots"],
        },
        "article": {
            "languageTag": article["languageTag"],
            "eyebrow": presentation["eyebrow"],
            "title": article["title"],
            "disclosureText": article["disclosureText"],
            "previewLabel": presentation["previewLabel"],
            "previewMessage": presentation["previewMessage"],
            "freshnessStatus": article["freshnessStatus"],
            "freshnessText": presentation["freshnessUnknown"],
            "breadcrumbRoot": presentation["breadcrumbRoot"],
            "skipLink": presentation["skipLink"],
            "lead": lead,
            "sections": sections,
            "omittedBlocks": omitted,
        },
        "sourceBinding": source["sourceBinding"],
        "runtimeBoundary": {
            "framework": runtime["framework"],
            "rendering": runtime["rendering"],
            "dataSource": runtime["data_source"],
            "remotePublicReadModel": runtime["remote_public_read_model"],
            "api": runtime["api"],
            "database": runtime["database"],
            "provider": runtime["provider"],
            "outboundIo": runtime["outbound_io"],
            "browserStorage": runtime["browser_storage"],
            "cookieWrite": runtime["cookie_write"],
            "tracking": runtime["tracking"],
            "analytics": runtime["analytics"],
            "clientComponentCount": 0,
            "rawHtmlAllowed": False,
            "javascriptRequiredForReading": False,
            "productCardsRendered": False,
            "offersRendered": False,
            "affiliateCtaRendered": False,
            "comparisonRendered": False,
            "structuredDataRendered": False,
            "canonicalUrlRendered": False,
            "internalIdentifiersRendered": False,
        },
        "authority": authority,
        "actions": [],
    }
    _validate_projected_output_tree(fixture)
    return fixture


def _typescript_source(source: dict[str, object]) -> bytes:
    compact = _canonical_compact(source).decode("ascii")
    literal = compact.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "/* Generated by scripts/build_st1002_public_article_renderer.py. Do not edit. */\n"
        "export const ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2: unknown = JSON.parse(\n"
        f"  '{literal}',\n"
        ");\n"
    ).encode("utf-8")


def _source_role(path: Path) -> str:
    if path in OWNED_SOURCE_PATHS:
        return "OWNER_SOURCE"
    if path in CANONICAL_HASHES:
        return "CANONICAL_INPUT"
    if path in DEPENDENCY_HASHES:
        return "DEPENDENCY_ARTIFACT"
    return "LOCKED_TOOLCHAIN"


def _manifest_bytes(
    root: Path, generated_source: bytes, rendered_fixture: bytes
) -> bytes:
    sources: list[dict[str, object]] = []
    for path in SOURCE_PATHS:
        payload = _read_regular(root, path)
        sources.append(
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(payload),
                "sha256": _sha(payload),
                "role": _source_role(path),
            }
        )
    manifest = {
        "schema_version": 2,
        "story_id": "ST-1002",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_RECORDED_PUBLIC_ARTICLE_RENDERER_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{GENERATED_SOURCE_PATH.as_posix()}",
                "artifact_role": "EXACT_RECORDED_TYPESCRIPT_SOURCE",
                "media_type": "text/typescript",
                "bytes": len(generated_source),
                "sha256": _sha(generated_source),
            },
            {
                "uri": f"repo://{RENDERED_FIXTURE_PATH.as_posix()}",
                "artifact_role": "DETERMINISTIC_RENDERER_VIEW_FIXTURE",
                "media_type": "application/json",
                "bytes": len(rendered_fixture),
                "sha256": _sha(rendered_fixture),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st1002_public_article_renderer.py",
            "check_command": (
                ".venv/bin/python scripts/build_st1002_public_article_renderer.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "python_implementation": "CPython",
            "python_version": "3.14.6",
            "pyyaml_version": "6.0.3",
        },
        "authority": {
            "source_route_activated": False,
            "public_read_served": False,
            "publication_authorized": False,
            "staging_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "TST-021": "NOT_EXECUTED",
            "TST-022": "NOT_EXECUTED",
            "TST-023": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=_IndentedSafeDumper,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    ).encode("utf-8")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    contract = _validate_contract(root)
    source = _recorded_source(root, contract)
    generated_source = _typescript_source(source)
    rendered_fixture = _canonical_pretty(_view_fixture(source, contract))
    manifest = _manifest_bytes(root, generated_source, rendered_fixture)
    return (
        (GENERATED_SOURCE_PATH, generated_source),
        (RENDERED_FIXTURE_PATH, rendered_fixture),
        (MANIFEST_PATH, manifest),
    )


def _publish(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            tuple((_safe_path(root, path), payload) for path, payload in artifacts),
            namespace="st1002",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, expected in artifacts:
            if _read_regular(root, relative) != expected:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _publish(root, artifacts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-1002 public article renderer generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1002 public article renderer checked"
        if arguments.check
        else "ST-1002 public article renderer generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
