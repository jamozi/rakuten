#!/usr/bin/env python3
"""Build the deterministic local ST-1004 disclosure/affiliate V2 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn
from urllib.parse import urlsplit

import yaml


ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1004/contracts/disclosure-affiliate-runtime.v2.yaml"
)
GENERATED_PATH: Final = Path(
    "changes/st-1004/generated/disclosure-affiliate-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1004/runtime-manifest.v2.yaml")
GENERATED_PATHS: Final = (GENERATED_PATH, MANIFEST_PATH)

OWNER_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("scripts/build_st1004_disclosure_affiliate_runtime.py"),
    Path("packages/web-ui/src/disclosure-affiliate-cta.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("apps/web/src/public-article-page.tsx"),
    Path("apps/web/app/articles/[slug]/article.module.css"),
    Path("changes/st-1004/PREFLIGHT.md"),
    Path("changes/st-1004/README.md"),
    Path("tests/st1004_v2/disclosure-affiliate-runtime.test.ts"),
    Path("tests/st1004_v2/disclosure-affiliate-negative.test.ts"),
    Path("tests/st1004_v2/disclosure-affiliate-static.test.ts"),
    Path("tests/st1004_v2/check-browser.mjs"),
    Path("tests/st1004_v2/test_generation.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1004",
    "objective": "固定開示と正規URL直接遷移",
    "depends_on": ["ST-1002", "ST-0503"],
    "requirement_ids": ["FR-011"],
    "deliverables": ["disclosure renderer", "CTA"],
    "acceptance_criteria": ["rel sponsored", "destination clear", "beacon independent"],
    "test_suites": ["TST-020", "TST-022", "TST-026"],
}
EXPECTED_COMPONENTS: Final = {
    "UI-C031": ("DisclosureBanner", "広告・Affiliate開示"),
    "UI-C034": ("AffiliateCTA", "楽天遷移を明示しSponsored属性"),
}
EXPECTED_SYNTHETIC_HREF: Final = "https://example.invalid/rakuten-marketplace/item"


class St1004BuildError(RuntimeError):
    """Closed, non-reflecting owner-generator failure."""


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise St1004BuildError("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _fail(code: str) -> NoReturn:
    raise St1004BuildError(code)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative_path(relative: Path) -> PurePosixPath:
    if relative.is_absolute():
        _fail("SOURCE_PATH_INVALID")
    pure = PurePosixPath(relative.as_posix())
    if not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("SOURCE_PATH_INVALID")
    return pure


def _read_regular(root: Path, relative: Path, *, maximum: int = 4_000_000) -> bytes:
    pure = _relative_path(relative)
    root_real = root.resolve(strict=True)
    current = root_real
    for part in pure.parts[:-1]:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError:
            _fail("SOURCE_PARENT_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("SOURCE_PARENT_INVALID")
    leaf = current / pure.parts[-1]
    try:
        metadata = os.lstat(leaf)
    except OSError:
        _fail("SOURCE_LEAF_INVALID")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_LEAF_INVALID")
    if metadata.st_size > maximum:
        _fail("SOURCE_TOO_LARGE")
    try:
        payload = leaf.read_bytes()
    except OSError:
        _fail("SOURCE_READ_FAILED")
    if len(payload) != metadata.st_size:
        _fail("SOURCE_CHANGED_DURING_READ")
    return payload


def _parse_yaml(payload: bytes) -> dict[str, Any]:
    try:
        value = yaml.load(payload.decode("utf-8"), Loader=_UniqueSafeLoader)
    except St1004BuildError:
        raise
    except UnicodeDecodeError, yaml.YAMLError:
        _fail("YAML_INVALID")
    if type(value) is not dict:
        _fail("YAML_ROOT_INVALID")
    return value


def _parse_json(payload: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique)
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    if type(value) is not dict:
        _fail("JSON_ROOT_INVALID")
    return value


def _mapping(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail(code)
    return value


def _sequence(value: Any, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _records(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [
        _mapping(item, "CANONICAL_RECORD_INVALID")
        for item in _sequence(document.get(key), "CANONICAL_COLLECTION_INVALID")
    ]


def _find(records: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("id") == identifier]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING")
    return matches[0]


def _assert_contract_shape(contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"), "CONTRACT_DOCUMENT_INVALID")
    if document != {
        "id": "RAOS-ST1004-DISCLOSURE-AFFILIATE-RUNTIME-002",
        "version": "2.0.0",
        "story_id": "ST-1004",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        "enabled_environments": ["DEV", "CI"],
        "enabled_by_default_outside_local": False,
    }:
        _fail("CONTRACT_DOCUMENT_DRIFT")
    if (
        contract.get("classification")
        != "LOCAL_RECORDED_DISCLOSURE_WITH_UNAVAILABLE_AFFILIATE_SOURCE_V2"
    ):
        _fail("CONTRACT_CLASSIFICATION_DRIFT")

    runtime = _mapping(contract.get("recorded_runtime"), "RECORDED_RUNTIME_INVALID")
    if set(runtime) != {
        "schemaVersion",
        "storyId",
        "classification",
        "articleView",
        "syntheticCtaFixture",
        "receiptPort",
    }:
        _fail("RECORDED_RUNTIME_SHAPE_INVALID")
    if runtime.get("schemaVersion") != 2 or runtime.get("storyId") != "ST-1004":
        _fail("RECORDED_RUNTIME_IDENTITY_INVALID")

    article = _mapping(runtime.get("articleView"), "ARTICLE_VIEW_INVALID")
    if article.get("componentOrder") != ["UI-C031", "UI-C034"]:
        _fail("COMPONENT_ORDER_INVALID")
    disclosure = _mapping(article.get("disclosure"), "DISCLOSURE_INVALID")
    if (
        disclosure.get("componentId") != "UI-C031"
        or disclosure.get("rendered") is not True
        or disclosure.get("required") is not True
        or disclosure.get("editorRemovable") is not False
        or disclosure.get("headingCount") != 1
        or disclosure.get("placement") != "AFTER_H1_BEFORE_LEAD_AND_ARTICLE_BODY"
        or disclosure.get("precedesArticleBody") is not True
        or disclosure.get("firstViewRequired") is not True
        or disclosure.get("copy") != "この記事にはアフィリエイト広告が含まれます。"
    ):
        _fail("DISCLOSURE_CONTRACT_INVALID")

    cta = _mapping(article.get("affiliateCta"), "AFFILIATE_CTA_INVALID")
    source = _mapping(cta.get("source"), "AFFILIATE_SOURCE_INVALID")
    gates = _mapping(cta.get("gates"), "AFFILIATE_GATES_INVALID")
    if (
        cta.get("componentId") != "UI-C034"
        or cta.get("state") != "UNAVAILABLE_SOURCE"
        or cta.get("rendered") is not False
        or cta.get("enabled") is not False
        or cta.get("anchor") is not None
        or source.get("affiliateUrl") is not None
        or cta.get("fixedCopy") != "楽天市場で写真・価格・在庫を見る"
        or cta.get("requiredRel") != "sponsored nofollow"
        or cta.get("requiredDestinationLabel") != "楽天市場"
        or any(
            value not in {"UNAVAILABLE_SOURCE", "NOT_EVALUATED"}
            for value in gates.values()
        )
    ):
        _fail("AFFILIATE_UNAVAILABLE_CONTRACT_INVALID")

    navigation = _mapping(
        article.get("navigationBoundary"), "NAVIGATION_BOUNDARY_INVALID"
    )
    if (
        navigation.get("nativeAnchorRequired") is not True
        or navigation.get("directDestinationRequired") is not True
        or navigation.get("beaconRequiredForNavigation") is not False
        or navigation.get("instrumentationFailureBlocksNavigation") is not False
        or any(
            navigation.get(key) is not False
            for key in (
                "raosRedirectAllowed",
                "cloakingAllowed",
                "urlMutationAllowed",
                "returnUrlAllowed",
                "clientHandlerAllowed",
            )
        )
    ):
        _fail("NAVIGATION_BOUNDARY_INVALID")

    synthetic = _mapping(runtime.get("syntheticCtaFixture"), "SYNTHETIC_CTA_INVALID")
    parsed = urlsplit(str(synthetic.get("href")))
    if (
        synthetic.get("state") != "SYNTHETIC_RENDER_TEST_ONLY"
        or synthetic.get("href") != EXPECTED_SYNTHETIC_HREF
        or parsed.scheme != "https"
        or parsed.hostname != "example.invalid"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or synthetic.get("rel") != "sponsored nofollow"
        or synthetic.get("copy") != "楽天市場で写真・価格・在庫を見る"
        or synthetic.get("destinationLabel") != "楽天市場"
        or synthetic.get("target") is not None
        or synthetic.get("minimumTargetBlockSizePx") != 44
        or synthetic.get("minimumTargetInlineSizePx") != 44
        or synthetic.get("beaconRequiredForNavigation") is not False
        or synthetic.get("instrumentationFailureBlocksNavigation") is not False
        or synthetic.get("raosRedirect") is not False
        or synthetic.get("cloaking") is not False
        or synthetic.get("urlMutation") is not False
        or synthetic.get("routeRendered") is not False
    ):
        _fail("SYNTHETIC_CTA_CONTRACT_INVALID")

    port = _mapping(runtime.get("receiptPort"), "RECEIPT_PORT_INVALID")
    if (
        port.get("profile") != "CLOSED_VERIFIED_AFFILIATE_DESTINATION_RECEIPT_PORT_V1"
        or port.get("connected") is not False
        or port.get("acceptsArbitraryUrl") is not False
        or port.get("acceptsReturnUrl") is not False
        or port.get("liveReceiptAcceptedByThisSlice") is not False
    ):
        _fail("RECEIPT_PORT_INVALID")

    authority = _mapping(contract.get("authority"), "AUTHORITY_INVALID")
    if any(value not in {False, "NOT_EXECUTED"} for value in authority.values()):
        _fail("AUTHORITY_ESCALATION")


def _validate_canonical(root: Path) -> None:
    backlog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
        )
    )
    story = _find(_records(backlog, "stories"), "ST-1004")
    for key, expected in EXPECTED_STORY.items():
        if story.get(key) != expected:
            _fail("CANONICAL_STORY_DRIFT")

    components_document = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml")
        )
    )
    components = _records(components_document, "components")
    for identifier, (name, purpose) in EXPECTED_COMPONENTS.items():
        component = _find(components, identifier)
        if (
            component.get("name") != name
            or component.get("purpose") != purpose
            or component.get("area") != "public"
            or component.get("keyboard_required") is not True
            or component.get("screen_reader_required") is not True
        ):
            _fail("CANONICAL_COMPONENT_DRIFT")

    security = _parse_yaml(
        _read_regular(
            root,
            Path(
                "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
            ),
        )
    )
    control = _find(_records(security, "controls"), "SEC-APP-006")
    if (
        control.get("title") != "Open redirect defense"
        or control.get("requirement") != "任意return URL/affiliate redirectを禁止"
        or control.get("priority") != "P0"
    ):
        _fail("CANONICAL_SECURITY_DRIFT")

    tests = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml")
        )
    )
    suites = _records(tests, "suites")
    suite_names = {
        "TST-020": "Content AST and policy",
        "TST-022": "Browser functional E2E",
        "TST-026": "Security verification",
    }
    for identifier, name in suite_names.items():
        suite = _find(suites, identifier)
        if suite.get("name") != name or suite.get("release_blocking") is not True:
            _fail("CANONICAL_TEST_DRIFT")


def _walk_bindings(value: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if type(value) is dict:
        if set(value) == {"path", "sha256"}:
            path = value.get("path")
            sha256 = value.get("sha256")
            if type(path) is not str or type(sha256) is not str:
                _fail("SOURCE_BINDING_INVALID")
            results.append({"path": path, "sha256": sha256})
        else:
            for child in value.values():
                results.extend(_walk_bindings(child))
    elif type(value) is list:
        for child in value:
            results.extend(_walk_bindings(child))
    return results


def _validate_bindings(root: Path, contract: dict[str, Any]) -> list[dict[str, str]]:
    bindings = _walk_bindings(contract.get("canonical_bindings"))
    bindings.extend(_walk_bindings(contract.get("dependency_bindings")))
    if len(bindings) != 16:
        _fail("SOURCE_BINDING_COUNT_INVALID")
    seen: set[str] = set()
    for binding in bindings:
        path = binding["path"]
        if path in seen:
            _fail("SOURCE_BINDING_DUPLICATE")
        seen.add(path)
        payload = _read_regular(root, Path(path))
        protected = path.startswith(("docs/canonical/", "contracts/"))
        if protected and _sha256(payload) != binding["sha256"]:
            _fail("SOURCE_BINDING_DRIFT")
    return bindings


def _validate_dependencies(root: Path, contract: dict[str, Any]) -> None:
    dependencies = _mapping(
        contract.get("dependency_bindings"), "DEPENDENCY_BINDINGS_INVALID"
    )
    st1002 = _mapping(dependencies.get("ST-1002"), "ST1002_BINDING_INVALID")
    recorded_binding = _mapping(st1002.get("recorded_view"), "ST1002_BINDING_INVALID")
    recorded = _parse_json(_read_regular(root, Path(recorded_binding["path"])))
    route = _mapping(recorded.get("route"), "ST1002_VIEW_INVALID")
    article = _mapping(recorded.get("article"), "ST1002_VIEW_INVALID")
    runtime = _mapping(recorded.get("runtimeBoundary"), "ST1002_VIEW_INVALID")
    if (
        route.get("slug") != st1002.get("exact_slug")
        or route.get("path") != st1002.get("exact_path")
        or article.get("disclosureText") != st1002.get("recorded_disclosure_copy")
        or runtime.get("affiliateCtaRendered") is not False
        or runtime.get("offersRendered") is not False
    ):
        _fail("ST1002_VIEW_DRIFT")

    st0503 = _mapping(dependencies.get("ST-0503"), "ST0503_BINDING_INVALID")
    if (
        st0503.get("profile") != "RECORDED_LOSSLESS_STRUCTURAL_V1"
        or st0503.get("affiliate_url") is not None
        or st0503.get("url_source_state") != "UNAVAILABLE_SOURCE"
    ):
        _fail("ST0503_CONTRACT_DRIFT")
    source_binding = _mapping(
        st0503.get("normalization_source"), "ST0503_BINDING_INVALID"
    )
    source = _read_regular(root, Path(source_binding["path"])).decode("utf-8")
    if "affiliate_url: None" not in source or "affiliate_url=None" not in source:
        _fail("ST0503_SOURCE_DRIFT")


def _validate_url_surface(recorded: dict[str, Any]) -> None:
    found: list[str] = []

    def walk(value: Any) -> None:
        if type(value) is str and "://" in value:
            found.append(value)
        elif type(value) is list:
            for child in value:
                walk(child)
        elif type(value) is dict:
            for child in value.values():
                walk(child)

    walk(recorded)
    if found != [EXPECTED_SYNTHETIC_HREF]:
        _fail("URL_SURFACE_INVALID")


def _render_json(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _render_yaml(value: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).encode("utf-8")


def _source_entry(root: Path, relative: Path, role: str) -> dict[str, Any]:
    payload = _read_regular(root, relative)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "role": role,
    }


def expected_artifacts(root: Path = ROOT) -> tuple[tuple[Path, bytes], ...]:
    contract_bytes = _read_regular(root, CONTRACT_PATH)
    contract = _parse_yaml(contract_bytes)
    _assert_contract_shape(contract)
    _validate_canonical(root)
    bindings = _validate_bindings(root, contract)
    _validate_dependencies(root, contract)

    recorded = _mapping(contract.get("recorded_runtime"), "RECORDED_RUNTIME_INVALID")
    _validate_url_surface(recorded)
    recorded_bytes = _render_json(recorded)

    source_artifacts = [
        _source_entry(root, relative, "OWNER_SOURCE") for relative in OWNER_SOURCE_PATHS
    ]
    bound_paths = {entry["uri"].removeprefix("repo://") for entry in source_artifacts}
    for binding in bindings:
        if binding["path"] in bound_paths:
            continue
        role = (
            "CANONICAL_INPUT"
            if binding["path"].startswith("docs/canonical/")
            else "DEPENDENCY_ARTIFACT"
        )
        source_artifacts.append(_source_entry(root, Path(binding["path"]), role))

    manifest = {
        "schema_version": 2,
        "story_id": "ST-1004",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_DISCLOSURE_AFFILIATE_RUNTIME_MANIFEST_V2",
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifacts": [
            {
                "uri": f"repo://{GENERATED_PATH.as_posix()}",
                "artifact_role": "DETERMINISTIC_RECORDED_DISCLOSURE_AFFILIATE_VIEW",
                "media_type": "application/json",
                "bytes": len(recorded_bytes),
                "sha256": _sha256(recorded_bytes),
            }
        ],
        "generation": {
            "owner": "repo://scripts/build_st1004_disclosure_affiliate_runtime.py",
            "command": ".venv/bin/python scripts/build_st1004_disclosure_affiliate_runtime.py",
            "check_command": ".venv/bin/python scripts/build_st1004_disclosure_affiliate_runtime.py --check",
            "network": "NONE",
        },
        "runtime_boundary": contract["runtime_boundary"],
        "security_boundary": contract["security_boundary"],
        "accessibility_boundary": contract["accessibility_boundary"],
        "authority": contract["authority"],
    }
    return (
        (GENERATED_PATH, recorded_bytes),
        (MANIFEST_PATH, _render_yaml(manifest)),
    )


def _atomic_write(root: Path, relative: Path, payload: bytes) -> None:
    pure = _relative_path(relative)
    target = root.joinpath(*pure.parts)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        metadata = os.lstat(target)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("OUTPUT_TARGET_INVALID")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def build(root: Path = ROOT, *, check: bool) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, expected in artifacts:
            try:
                actual = _read_regular(root, relative)
            except St1004BuildError:
                _fail("GENERATED_ARTIFACT_DRIFT")
            if actual != expected:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    for relative, payload in artifacts:
        _atomic_write(root, relative, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    try:
        try:
            arguments = parser.parse_args(argv)
        except SystemExit as error:
            return error.code if isinstance(error.code, int) else 2
        build(check=arguments.check)
    except St1004BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
