#!/usr/bin/env python3
"""Build deterministic local-only ST-1001 public-shell artifacts."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
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
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

CONTRACT_PATH: Final = Path(
    "changes/st-1001/contracts/public-app-shell-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1001/generated/public-app-shell-recorded.v2.json"
)
GENERATED_TS_PATH: Final = Path("apps/web/src/public-policy-content.generated.ts")
MANIFEST_PATH: Final = Path("changes/st-1001/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1001_public_app_shell.py")
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
    Path(
        "changes/st-0807/contracts/seo-render-runtime.v2.yaml"
    ): "9336feeddbc0d095708d60e9718c1636c9c16068db36fffab651222fdd279b5c",
    Path(
        "changes/st-0807/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"
    ): "3e0ee50841acb2e485269f1805c15c6eab82faf04e23e40209b59372a77e0c07",
    Path(
        "packages/web-ui/src/public-shell.ts"
    ): "33020159073f230088849066e14cf26ae1e283c976f4ff4506abc987885b8333",
    SECURE_HELPER_PATH: "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e",
}

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path(".prettierignore"),
    Path("eslint.config.mjs"),
    Path("apps/web/package.json"),
    Path("apps/web/next-env.d.ts"),
    Path("apps/web/next.config.ts"),
    Path("apps/web/tsconfig.json"),
    Path("apps/web/app/globals.css"),
    Path("apps/web/app/layout.tsx"),
    Path("apps/web/app/editorial-policy/page.tsx"),
    Path("apps/web/app/affiliate-disclosure/page.tsx"),
    Path("apps/web/app/privacy/page.tsx"),
    Path("apps/web/app/about/page.tsx"),
    Path("apps/web/src/public-policy.ts"),
    Path("apps/web/src/public-shell.tsx"),
    Path("scripts/check_st1001_public_shell_browser.mjs"),
    Path("tests/st1001_v2/public-policy-model.test.ts"),
    Path("tests/st1001_v2/public-shell-static.test.ts"),
    Path("tests/st1001_v2/public-shell-accessibility.test.ts"),
    Path("tests/st1001_v2/public-shell-generated-contract.test.ts"),
    Path("tests/st1001_v2/test_generation.py"),
    Path("changes/st-1001/README-v2.md"),
    Path("changes/st-1001/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-1001.md"),
    Path("docs/worklogs/ST-1001.md"),
)

TOOLCHAIN_PATHS: Final = (Path("package.json"), Path("package-lock.json"))
SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *CANONICAL_HASHES,
    *DEPENDENCY_HASHES,
    *TOOLCHAIN_PATHS,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, GENERATED_TS_PATH, MANIFEST_PATH)

EXPECTED_PAGE_RECORDS: Final = (
    ("PUB-004", "/editorial-policy", "編集方針", "比較・推薦・根拠・AI利用方針を説明"),
    (
        "PUB-005",
        "/affiliate-disclosure",
        "広告・Affiliate開示",
        "広告関係と送客先を説明",
    ),
    (
        "PUB-006",
        "/privacy",
        "Privacy Policy",
        "取得データ、目的、保持、問い合わせを説明",
    ),
    (
        "PUB-007",
        "/about",
        "運営者・問い合わせ",
        "運営主体と連絡経路を表示",
    ),
)
ALLOWED_SECTION_STATES: Final = frozenset(
    {
        "CANONICAL_PRINCIPLE",
        "SAFE_DEFAULT",
        "OWNER_DECISION_REQUIRED",
        "LEGAL_REVIEW_REQUIRED",
    }
)


class PublicShellBuildError(RuntimeError):
    """Closed owner-generator refusal."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PublicShellBuildError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


class _IndentedSafeDumper(yaml.SafeDumper):
    """Emit sequence indentation compatible with the repository formatter."""

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
    except ValueError:
        _fail("SOURCE_PATH_INVALID")
    try:
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
            if (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ):
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
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) or (
                named.st_dev,
                named.st_ino,
                named.st_size,
                named.st_mtime_ns,
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ):
                _fail("SOURCE_IDENTITY_CHANGED")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except PublicShellBuildError:
        raise
    except OSError, ValueError:
        _fail("SOURCE_READ_FAILED")


def _parse_json(payload: bytes) -> dict[str, object]:
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=unique_pairs
        )
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        _fail("JSON_INVALID")
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail("JSON_INVALID")
    return cast(dict[str, object], value)


def _parse_yaml(
    payload: bytes, *, allow_trusted_anchors: bool = False
) -> dict[str, object]:
    try:
        text = payload.decode("utf-8", errors="strict")
        if not allow_trusted_anchors and any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in yaml.scan(text)
        ):
            _fail("YAML_FEATURE_FORBIDDEN")
        loader = _UniqueLoader(text)
        try:
            value = loader.get_single_data()
        finally:
            cast(Callable[[], None], loader.dispose)()
    except PublicShellBuildError:
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


def _string(value: object, code: str, *, maximum: int = 600) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
    ):
        _fail(code)
    return value


def _exact_keys(value: dict[str, object], expected: set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _canonical_bytes(value: object) -> bytes:
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
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail("SERIALIZATION_FAILED")


def _camel_mapping(value: dict[str, object]) -> dict[str, object]:
    def camel(key: str) -> str:
        first, *rest = key.split("_")
        return first + "".join(part[:1].upper() + part[1:] for part in rest)

    return {camel(key): item for key, item in value.items()}


def _validate_canonical_bindings(root: Path, contract: dict[str, object]) -> None:
    records = _sequence(contract["canonical_bindings"], "CANONICAL_BINDINGS_INVALID")
    expected = [(path.as_posix(), digest) for path, digest in CANONICAL_HASHES.items()]
    actual: list[tuple[str, str]] = []
    for raw in records:
        record = _mapping(raw, "CANONICAL_BINDINGS_INVALID")
        _exact_keys(record, {"path", "sha256"}, "CANONICAL_BINDINGS_INVALID")
        bound_path = _string(record["path"], "CANONICAL_BINDINGS_INVALID")
        digest = _string(record["sha256"], "CANONICAL_BINDINGS_INVALID")
        actual.append((bound_path, digest))
    if actual != expected:
        _fail("CANONICAL_BINDINGS_INVALID")
    for path, digest in CANONICAL_HASHES.items():
        if _sha(_read_regular(root, path)) != digest:
            _fail("CANONICAL_BINDING_DRIFT")


def _validate_dependency_bindings(root: Path, contract: dict[str, object]) -> None:
    dependencies = _mapping(
        contract["dependency_bindings"], "DEPENDENCY_BINDINGS_INVALID"
    )
    _exact_keys(dependencies, {"ST-0103", "ST-0807"}, "DEPENDENCY_BINDINGS_INVALID")
    st0103 = _mapping(dependencies["ST-0103"], "DEPENDENCY_BINDINGS_INVALID")
    if st0103 != {
        "node": "24.18.1",
        "npm": "11.16.0",
        "next": "16.2.12",
        "react": "19.2.8",
        "react_dom": "19.2.8",
        "typescript": "6.0.3",
    }:
        _fail("DEPENDENCY_BINDINGS_INVALID")
    for path, digest in DEPENDENCY_HASHES.items():
        if _sha(_read_regular(root, path)) != digest:
            _fail("DEPENDENCY_BINDING_DRIFT")

    root_manifest = _parse_json(_read_regular(root, Path("package.json")))
    app_manifest = _parse_json(_read_regular(root, Path("apps/web/package.json")))
    lock = _parse_json(_read_regular(root, Path("package-lock.json")))
    if root_manifest.get("packageManager") != "npm@11.16.0":
        _fail("NODE_TOOLCHAIN_INVALID")
    dependencies_raw = _mapping(
        app_manifest.get("dependencies"), "NODE_TOOLCHAIN_INVALID"
    )
    if dependencies_raw != {
        "next": "16.2.12",
        "react": "19.2.8",
        "react-dom": "19.2.8",
    }:
        _fail("NODE_TOOLCHAIN_INVALID")
    if "devDependencies" in app_manifest:
        _fail("NODE_TOOLCHAIN_INVALID")
    packages = _mapping(lock.get("packages"), "NODE_TOOLCHAIN_INVALID")
    locked_app = _mapping(packages.get("apps/web"), "NODE_TOOLCHAIN_INVALID")
    if "devDependencies" in locked_app:
        _fail("NODE_TOOLCHAIN_INVALID")
    axe_core = _mapping(packages.get("node_modules/axe-core"), "NODE_TOOLCHAIN_INVALID")
    if axe_core.get("version") != "4.12.1" or axe_core.get("dev") is not True:
        _fail("NODE_TOOLCHAIN_INVALID")


def _validate_catalog_records(root: Path) -> None:
    backlog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
        ),
        allow_trusted_anchors=True,
    )
    stories = _sequence(backlog.get("stories"), "STORY_CATALOG_INVALID")
    selected = [
        _mapping(item, "STORY_CATALOG_INVALID")
        for item in stories
        if _mapping(item, "STORY_CATALOG_INVALID").get("id") == "ST-1001"
    ]
    if len(selected) != 1:
        _fail("STORY_CATALOG_INVALID")
    story = selected[0]
    if (
        story.get("title") != "Public app shell and policy pages"
        or story.get("objective") != "Header/Footer/Policy/Disclosureを実装"
        or story.get("depends_on") != ["ST-0103", "ST-0807"]
        or story.get("deliverables") != ["public routes"]
        or story.get("acceptance_criteria") != ["SSR/metadata/a11y"]
        or story.get("test_suites") != ["TST-022", "TST-023"]
        or story.get("open_decisions") != ["OD-002", "OD-012"]
    ):
        _fail("STORY_CATALOG_INVALID")

    screens = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml")
        ),
        allow_trusted_anchors=True,
    )
    screen_records = _sequence(screens.get("screens"), "SCREEN_CATALOG_INVALID")
    selected_screens = [
        _mapping(item, "SCREEN_CATALOG_INVALID")
        for item in screen_records
        if _mapping(item, "SCREEN_CATALOG_INVALID").get("id")
        in {record[0] for record in EXPECTED_PAGE_RECORDS}
    ]
    if [
        (item.get("id"), item.get("route"), item.get("name"), item.get("purpose"))
        for item in selected_screens
    ] != list(EXPECTED_PAGE_RECORDS):
        _fail("SCREEN_CATALOG_INVALID")

    components = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml")
        ),
        allow_trusted_anchors=True,
    )
    component_records = _sequence(
        components.get("components"), "COMPONENT_CATALOG_INVALID"
    )
    selected_components = [
        _mapping(item, "COMPONENT_CATALOG_INVALID")
        for item in component_records
        if _mapping(item, "COMPONENT_CATALOG_INVALID").get("id")
        in {"UI-C002", "UI-C003", "UI-C004"}
    ]
    if [
        (
            item.get("id"),
            item.get("name"),
            item.get("keyboard_required"),
            item.get("screen_reader_required"),
        )
        for item in selected_components
    ] != [
        ("UI-C002", "PublicHeader", True, True),
        ("UI-C003", "PublicFooter", True, True),
        ("UI-C004", "Breadcrumbs", True, True),
    ]:
        _fail("COMPONENT_CATALOG_INVALID")


def _validate_pages(contract: dict[str, object]) -> None:
    pages = _sequence(contract["pages"], "PAGE_CONTRACT_INVALID")
    if len(pages) != len(EXPECTED_PAGE_RECORDS):
        _fail("PAGE_CONTRACT_INVALID")
    seen_sections: set[str] = set()
    for raw, expected in zip(pages, EXPECTED_PAGE_RECORDS, strict=True):
        page = _mapping(raw, "PAGE_CONTRACT_INVALID")
        _exact_keys(
            page,
            {
                "screen_id",
                "route",
                "title",
                "purpose",
                "description",
                "lead",
                "sections",
            },
            "PAGE_CONTRACT_INVALID",
        )
        if (
            tuple(page[key] for key in ("screen_id", "route", "title", "purpose"))
            != expected
        ):
            _fail("PAGE_CONTRACT_INVALID")
        _string(page["description"], "PAGE_CONTRACT_INVALID")
        _string(page["lead"], "PAGE_CONTRACT_INVALID")
        sections = _sequence(page["sections"], "PAGE_CONTRACT_INVALID")
        if len(sections) < 2:
            _fail("PAGE_CONTRACT_INVALID")
        local_ids: set[str] = set()
        for raw_section in sections:
            section = _mapping(raw_section, "PAGE_CONTRACT_INVALID")
            _exact_keys(
                section,
                {"id", "heading", "body", "state", "source_ref"},
                "PAGE_CONTRACT_INVALID",
            )
            section_id = _string(section["id"], "PAGE_CONTRACT_INVALID", maximum=80)
            if (
                not section_id.replace("-", "").isalnum()
                or not section_id[0].islower()
                or section_id in local_ids
                or section_id in seen_sections
            ):
                _fail("PAGE_CONTRACT_INVALID")
            local_ids.add(section_id)
            seen_sections.add(section_id)
            heading = _string(section["heading"], "PAGE_CONTRACT_INVALID")
            body = _string(section["body"], "PAGE_CONTRACT_INVALID")
            state = _string(section["state"], "PAGE_CONTRACT_INVALID")
            source_ref = _string(section["source_ref"], "PAGE_CONTRACT_INVALID")
            if (
                state not in ALLOWED_SECTION_STATES
                or not source_ref.startswith("docs/canonical/")
                or any(marker in heading + body for marker in ("<", ">", "://"))
                or "javascript:" in (heading + body).lower()
            ):
                _fail("PAGE_CONTRACT_INVALID")

    privacy = _mapping(pages[2], "PAGE_CONTRACT_INVALID")
    privacy_sections = _sequence(privacy["sections"], "PAGE_CONTRACT_INVALID")
    if (
        _mapping(privacy_sections[0], "PAGE_CONTRACT_INVALID").get("state")
        != "SAFE_DEFAULT"
    ):
        _fail("PAGE_CONTRACT_INVALID")
    affiliate = _mapping(pages[1], "PAGE_CONTRACT_INVALID")
    affiliate_sections = _sequence(affiliate["sections"], "PAGE_CONTRACT_INVALID")
    if (
        _mapping(affiliate_sections[-1], "PAGE_CONTRACT_INVALID").get("state")
        != "LEGAL_REVIEW_REQUIRED"
    ):
        _fail("PAGE_CONTRACT_INVALID")


def _validate_contract(root: Path) -> dict[str, object]:
    contract = _parse_yaml(_read_regular(root, CONTRACT_PATH))
    _exact_keys(
        contract,
        {
            "document",
            "classification",
            "canonical_bindings",
            "dependency_bindings",
            "runtime_boundary",
            "identity_boundary",
            "privacy_boundary",
            "metadata_policy",
            "shell",
            "pages",
            "security_headers",
            "authority",
        },
        "CONTRACT_SHAPE_INVALID",
    )
    document = _mapping(contract["document"], "CONTRACT_SHAPE_INVALID")
    if (
        document
        != {
            "id": "RAOS-ST1001-PUBLIC-APP-SHELL-RUNTIME-002",
            "version": "2.0.0",
            "story_id": "ST-1001",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
            "enabled_environments": ["DEV", "CI"],
            "enabled_by_default_outside_local": False,
        }
        or contract["classification"] != "LOCAL_ONLY_UNBRANDED_SSR_POLICY_PREVIEW_V2"
    ):
        _fail("CONTRACT_SHAPE_INVALID")
    _validate_canonical_bindings(root, contract)
    _validate_dependency_bindings(root, contract)
    _validate_catalog_records(root)
    _validate_pages(contract)

    runtime = _mapping(contract["runtime_boundary"], "RUNTIME_BOUNDARY_INVALID")
    if (
        runtime.get("rendering") != "FORCE_DYNAMIC_SERVER_RENDERING"
        or runtime.get("data_source") != "VERSIONED_RECORDED_POLICY_CONTENT"
        or runtime.get("outbound_io") != "NONE"
        or runtime.get("browser_storage") != "NONE"
        or runtime.get("cookie_write") != "NONE"
        or runtime.get("tracking") != "DISABLED_OD_012"
        or runtime.get("analytics") != "DISABLED_OD_012"
        or runtime.get("client_component_count") != 0
        or runtime.get("raw_html_allowed") is not False
        or runtime.get("arbitrary_url_allowed") is not False
        or runtime.get("javascript_required_for_reading") is not False
        or runtime.get("route_count") != 4
    ):
        _fail("RUNTIME_BOUNDARY_INVALID")
    identity = _mapping(contract["identity_boundary"], "IDENTITY_BOUNDARY_INVALID")
    if identity != {
        "decision_id": "OD-002",
        "site_name": None,
        "domain": None,
        "operator": None,
        "contact": None,
        "metadata_base": None,
        "state": "HUMAN_DECISION_REQUIRED",
        "external_publication_allowed": False,
    }:
        _fail("IDENTITY_BOUNDARY_INVALID")
    privacy = _mapping(contract["privacy_boundary"], "PRIVACY_BOUNDARY_INVALID")
    if privacy != {
        "decision_id": "OD-012",
        "nonessential_tracking_enabled": False,
        "consent_mode_selected": False,
        "cookie_policy_approved": False,
        "privacy_copy_approved": False,
        "retention_approved": False,
        "first_party_event_emitted": False,
    }:
        _fail("PRIVACY_BOUNDARY_INVALID")
    metadata = _mapping(contract["metadata_policy"], "METADATA_BOUNDARY_INVALID")
    if (
        metadata.get("canonical_url") is not None
        or metadata.get("open_graph") is not None
        or metadata.get("twitter") is not None
        or metadata.get("response_header")
        != "noindex, nofollow, noarchive, nosnippet, noimageindex"
        or _mapping(metadata.get("robots"), "METADATA_BOUNDARY_INVALID")
        != {
            "index": False,
            "follow": False,
            "noarchive": True,
            "nosnippet": True,
            "noimageindex": True,
            "nocache": True,
        }
    ):
        _fail("METADATA_BOUNDARY_INVALID")
    headers = _mapping(contract["security_headers"], "SECURITY_BOUNDARY_INVALID")
    csp = headers.get("content_security_policy")
    if (
        type(csp) is not str
        or "script-src 'none'" not in csp
        or "frame-ancestors 'none'" not in csp
    ):
        _fail("SECURITY_BOUNDARY_INVALID")
    authority = _mapping(contract["authority"], "AUTHORITY_BOUNDARY_INVALID")
    if any(
        (type(value) is bool and value is not False)
        or (type(value) is str and value != "NOT_EXECUTED")
        or type(value) not in {bool, str}
        for value in authority.values()
    ):
        _fail("AUTHORITY_BOUNDARY_INVALID")
    return contract


def _fixture(contract: dict[str, object]) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    for raw_page in _sequence(contract["pages"], "PAGE_CONTRACT_INVALID"):
        page = _mapping(raw_page, "PAGE_CONTRACT_INVALID")
        sections = [
            _camel_mapping(_mapping(raw, "PAGE_CONTRACT_INVALID"))
            for raw in _sequence(page["sections"], "PAGE_CONTRACT_INVALID")
        ]
        pages.append(
            {
                "screenId": page["screen_id"],
                "route": page["route"],
                "title": page["title"],
                "purpose": page["purpose"],
                "description": page["description"],
                "lead": page["lead"],
                "sections": sections,
            }
        )
    return {
        "schemaVersion": 2,
        "storyId": "ST-1001",
        "classification": contract["classification"],
        "runtimeBoundary": _camel_mapping(
            _mapping(contract["runtime_boundary"], "RUNTIME_BOUNDARY_INVALID")
        ),
        "identityBoundary": _camel_mapping(
            _mapping(contract["identity_boundary"], "IDENTITY_BOUNDARY_INVALID")
        ),
        "privacyBoundary": _camel_mapping(
            _mapping(contract["privacy_boundary"], "PRIVACY_BOUNDARY_INVALID")
        ),
        "metadataPolicy": _camel_mapping(
            _mapping(contract["metadata_policy"], "METADATA_BOUNDARY_INVALID")
        ),
        "shell": _camel_mapping(_mapping(contract["shell"], "SHELL_BOUNDARY_INVALID")),
        "pages": pages,
        "securityHeaders": _camel_mapping(
            _mapping(contract["security_headers"], "SECURITY_BOUNDARY_INVALID")
        ),
        "authority": dict(
            _mapping(contract["authority"], "AUTHORITY_BOUNDARY_INVALID")
        ),
    }


def _typescript_bytes(fixture: bytes) -> bytes:
    parsed = _parse_json(fixture)
    try:
        compact = json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except TypeError, ValueError, RecursionError:
        _fail("SERIALIZATION_FAILED")
    literal = compact.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "/* Generated by scripts/build_st1001_public_app_shell.py. Do not edit. */\n"
        "import type { PublicPolicyContentSource } from './public-policy.ts';\n\n"
        "export const PUBLIC_POLICY_CONTENT_SOURCE = JSON.parse(\n"
        f"  '{literal}',\n"
        ") as PublicPolicyContentSource;\n"
    ).encode("utf-8")


def _source_role(path: Path) -> str:
    if path in OWNED_SOURCE_PATHS:
        return "OWNER_SOURCE"
    if path in CANONICAL_HASHES:
        return "CANONICAL_INPUT"
    if path in DEPENDENCY_HASHES:
        return "DEPENDENCY_CONTRACT"
    return "LOCKED_TOOLCHAIN"


def _manifest_bytes(root: Path, fixture: bytes, generated_ts: bytes) -> bytes:
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
        "story_id": "ST-1001",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_RECORDED_PUBLIC_APP_SHELL_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "artifact_role": "RECORDED_LOCAL_POLICY_PROJECTION",
                "media_type": "application/json",
                "bytes": len(fixture),
                "sha256": _sha(fixture),
            },
            {
                "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
                "artifact_role": "IMMUTABLE_TYPESCRIPT_CONTENT_SOURCE",
                "media_type": "text/typescript",
                "bytes": len(generated_ts),
                "sha256": _sha(generated_ts),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st1001_public_app_shell.py",
            "check_command": ".venv/bin/python scripts/build_st1001_public_app_shell.py --check",
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "python_implementation": "CPython",
            "python_version": "3.14.6",
            "pyyaml_version": "6.0.3",
        },
        "authority": {
            "domain_approved": False,
            "operator_approved": False,
            "consent_approved": False,
            "legal_copy_approved": False,
            "external_publication_authorized": False,
            "staging_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
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
    fixture = _canonical_bytes(_fixture(contract))
    generated_ts = _typescript_bytes(fixture)
    manifest = _manifest_bytes(root, fixture, generated_ts)
    return (
        (FIXTURE_PATH, fixture),
        (GENERATED_TS_PATH, generated_ts),
        (MANIFEST_PATH, manifest),
    )


def _publish(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            tuple((_safe_path(root, path), payload) for path, payload in artifacts),
            namespace="st1001",
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
        print("ST-1001 public app shell generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1001 public app shell checked"
        if arguments.check
        else "ST-1001 public app shell generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
