#!/usr/bin/env python3
"""Build deterministic ST-1202 default-disabled recorded runtime artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn

import yaml


ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1202/contracts/public-event-instrumentation-runtime.v2.yaml"
)
GENERATED_PATH: Final = Path(
    "changes/st-1202/generated/public-event-instrumentation-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1202/runtime-manifest.v2.yaml")
GENERATED_PATHS: Final = (GENERATED_PATH, MANIFEST_PATH)

OWNER_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("scripts/build_st1202_public_event_instrumentation.py"),
    Path("packages/web-ui/src/public-event-instrumentation.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("apps/web/src/public-article-page.tsx"),
    Path("changes/st-1202/PREFLIGHT.md"),
    Path("changes/st-1202/README.md"),
    Path("changes/st-1202/README-v2.md"),
    Path("tests/st1202_v2/fixture.ts"),
    Path("tests/st1202_v2/public-event-runtime.test.ts"),
    Path("tests/st1202_v2/public-event-negative.test.ts"),
    Path("tests/st1202_v2/public-event-static.test.ts"),
    Path("tests/st1202_v2/test_generation.py"),
    Path("docs/execplans/ST-1202.md"),
    Path("docs/worklogs/ST-1202.md"),
    Path("changes/st-1202/completion/completion.v2.yaml"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1202",
    "objective": "view/engagement/CTA/RUMを送信",
    "depends_on": ["ST-1002", "ST-1004", "ST-1201"],
    "requirement_ids": ["FR-013"],
    "deliverables": ["client instrumentation"],
    "acceptance_criteria": ["navigation not blocked"],
    "test_suites": ["TST-022", "TST-030"],
}
EXPECTED_EVENT_IDS: Final = (
    "EVT-001",
    "EVT-002",
    "EVT-003",
    "EVT-004",
    "EVT-006",
    "EVT-012",
)
EXPECTED_EVENT_NAMES: Final = (
    "article_view",
    "qualified_decision_engagement",
    "affiliate_cta_impression",
    "affiliate_click",
    "comparison_interaction",
    "web_vital",
)
ENVELOPE_PARAMETERS: Final = frozenset(
    {
        "event_id",
        "event_name",
        "schema_version",
        "occurred_at",
        "received_at",
        "source",
        "site_id",
        "correlation_id",
    }
)
UUID7: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
    re.ASCII,
)
UTC_TIMESTAMP: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z\Z",
    re.ASCII,
)


class St1202BuildError(RuntimeError):
    """Closed owner-generator error."""


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
            raise St1202BuildError("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _fail(code: str) -> NoReturn:
    raise St1202BuildError(code)


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
    current = root.resolve(strict=True)
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
    except St1202BuildError:
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
        "id": "RAOS-ST1202-PUBLIC-EVENT-INSTRUMENTATION-RUNTIME-002",
        "version": "2.0.0",
        "story_id": "ST-1202",
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        "enabled_environments": ["DEV", "CI"],
        "enabled_by_default_outside_local": False,
    }:
        _fail("CONTRACT_DOCUMENT_DRIFT")
    if (
        contract.get("classification")
        != "LOCAL_DEFAULT_DISABLED_PROCESS_LOCAL_RECORDED_PUBLIC_EVENT_INSTRUMENTATION_V2"
    ):
        _fail("CONTRACT_CLASSIFICATION_DRIFT")

    runtime = _mapping(contract.get("recorded_runtime"), "RECORDED_RUNTIME_INVALID")
    if set(runtime) != {
        "schemaVersion",
        "storyId",
        "classification",
        "actualRouteBoundary",
        "recordedFixture",
        "processLocalEvidence",
    }:
        _fail("RECORDED_RUNTIME_SHAPE_INVALID")
    if runtime.get("schemaVersion") != 2 or runtime.get("storyId") != "ST-1202":
        _fail("RECORDED_RUNTIME_IDENTITY_INVALID")

    route = _mapping(runtime.get("actualRouteBoundary"), "ROUTE_BOUNDARY_INVALID")
    if (
        route.get("routePath") != "/articles/synthetic-recorded-policy-seo"
        or route.get("screenId") != "PUB-003"
        or route.get("mode") != "DISABLED_OD_012"
        or route.get("clientInstrumentationInstalled") is not False
        or route.get("clientComponentCount") != 0
        or route.get("identityAvailable") is not False
        or route.get("affiliateCtaAvailable") is not False
        or route.get("eligibleEventIds") != []
        or route.get("blockedEventIds") != list(EXPECTED_EVENT_IDS)
        or route.get("events") != []
        or route.get("effects") != []
        or route.get("trackingEnabled") is not False
        or route.get("measurementObserved") is not False
    ):
        _fail("ROUTE_BOUNDARY_INVALID")
    for key in (
        "browserStorageUsed",
        "cookiesUsed",
        "fingerprintingUsed",
        "networkUsed",
        "beaconUsed",
        "fetchUsed",
        "providerUsed",
    ):
        if route.get(key) is not False:
            _fail("ROUTE_EFFECT_ESCALATION")

    fixture = _mapping(runtime.get("recordedFixture"), "RECORDED_FIXTURE_INVALID")
    if (
        fixture.get("kind") != "SYNTHETIC_ST1202_RECORDED_INSTRUMENTATION_FIXTURE"
        or fixture.get("mode") != "RECORDED_TEST_ONLY"
        or fixture.get("faultEventIds") != []
    ):
        _fail("RECORDED_FIXTURE_INVALID")
    consent = _mapping(fixture.get("consent"), "RECORDED_CONSENT_INVALID")
    if consent != {
        "fixtureKind": "SYNTHETIC_ST1202_RECORDED_FULL_CONSENT_FIXTURE",
        "consentState": "GRANTED",
        "privacyMode": "FULL_CONSENT",
        "authority": "UNRESOLVED_OD_012",
        "trackingActivation": "DISABLED",
    }:
        _fail("RECORDED_CONSENT_INVALID")
    events = [
        _mapping(event, "RECORDED_EVENT_INVALID")
        for event in _sequence(fixture.get("events"), "RECORDED_EVENTS_INVALID")
    ]
    if tuple(event.get("catalogId") for event in events) != EXPECTED_EVENT_IDS:
        _fail("RECORDED_EVENT_ORDER_INVALID")
    if tuple(event.get("eventName") for event in events) != EXPECTED_EVENT_NAMES:
        _fail("RECORDED_EVENT_ORDER_INVALID")
    event_ids: list[str] = []
    for event in events:
        event_id = event.get("eventId")
        if (
            type(event_id) is not str
            or UUID7.fullmatch(event_id) is None
            or event.get("schemaVersion") != "1.0"
            or event.get("source") != "public_web"
            or type(event.get("siteId")) is not str
            or UUID7.fullmatch(event["siteId"]) is None
            or type(event.get("correlationId")) is not str
            or UUID7.fullmatch(event["correlationId"]) is None
            or type(event.get("occurredAt")) is not str
            or UTC_TIMESTAMP.fullmatch(event["occurredAt"]) is None
            or type(event.get("receivedAt")) is not str
            or UTC_TIMESTAMP.fullmatch(event["receivedAt"]) is None
            or event["receivedAt"] < event["occurredAt"]
        ):
            _fail("RECORDED_EVENT_IDENTITY_INVALID")
        event_ids.append(event_id)
    if len(set(event_ids)) != len(event_ids):
        _fail("RECORDED_EVENT_IDENTITY_INVALID")

    evidence = _mapping(
        runtime.get("processLocalEvidence"), "PROCESS_LOCAL_EVIDENCE_INVALID"
    )
    if (
        evidence.get("eventOrder") != list(EXPECTED_EVENT_IDS)
        or evidence.get("idempotency") != "PROCESS_LOCAL_EVENT_ID_AND_CANONICAL_BYTES"
        or evidence.get("failureHandling") != "SWALLOWED_NON_BLOCKING"
        or evidence.get("bodyHistoryExposed") is not False
        or evidence.get("trackingActivation") != "DISABLED"
        or evidence.get("persistence") != "NOT_EXECUTED"
        or evidence.get("measurementObserved") is not False
    ):
        _fail("PROCESS_LOCAL_EVIDENCE_INVALID")

    runtime_boundary = _mapping(
        contract.get("runtime_boundary"), "RUNTIME_BOUNDARY_INVALID"
    )
    prohibited_effects = (
        "identifier_generation",
        "clock",
        "randomness",
        "cookie",
        "browser_storage",
        "fingerprinting",
        "send_beacon",
        "fetch",
        "endpoint",
        "provider",
        "network",
        "database",
        "filesystem_persistence",
        "durable_dedupe",
    )
    if any(runtime_boundary.get(key) != "NONE" for key in prohibited_effects):
        _fail("RUNTIME_EFFECT_ESCALATION")

    navigation = _mapping(
        contract.get("navigation_boundary"), "NAVIGATION_BOUNDARY_INVALID"
    )
    if (
        navigation.get("native_anchor_required") is not True
        or navigation.get("direct_destination_required") is not True
        or navigation.get("collector_awaited") is not False
        or navigation.get("instrumentation_failure_blocks_navigation") is not False
        or navigation.get("raos_redirect_allowed") is not False
        or navigation.get("return_url_allowed") is not False
        or navigation.get("actual_route_cta_rendered") is not False
    ):
        _fail("NAVIGATION_BOUNDARY_INVALID")

    authority = _mapping(contract.get("authority"), "AUTHORITY_INVALID")
    if any(value not in {False, "NOT_EXECUTED"} for value in authority.values()):
        _fail("AUTHORITY_ESCALATION")


def _validate_canonical(root: Path, contract: dict[str, Any]) -> None:
    backlog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
        )
    )
    story = _find(_records(backlog, "stories"), "ST-1202")
    for key, expected in EXPECTED_STORY.items():
        if story.get(key) != expected:
            _fail("CANONICAL_STORY_DRIFT")

    open_decisions = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml")
        )
    )
    decision = _find(_records(open_decisions, "items"), "OD-012")
    if (
        decision.get("status") != "HUMAN_DECISION_REQUIRED"
        or decision.get("blocking") is not True
        or decision.get("default_behavior")
        != "非必須Trackingを無効化しFirst-party最小Eventのみ"
    ):
        _fail("CANONICAL_OD012_DRIFT")

    slices = _parse_yaml(
        _read_regular(
            root,
            Path("docs/canonical/03_analytics/RAOS_09_implementation_slices_v1.0.yaml"),
        )
    )
    selected_slice = _find(_records(slices, "slices"), "AN-SLICE-002")
    if selected_slice.get("depends_on") != ["AN-SLICE-001"] or selected_slice.get(
        "deliverables"
    ) != ["article view", "CTA impression/click", "comparison", "RUM"]:
        _fail("CANONICAL_SLICE_DRIFT")

    catalog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml")
        )
    )
    definitions = _records(catalog, "events")
    fixture = _mapping(
        _mapping(contract.get("recorded_runtime"), "RECORDED_RUNTIME_INVALID").get(
            "recordedFixture"
        ),
        "RECORDED_FIXTURE_INVALID",
    )
    recorded_events = _sequence(fixture.get("events"), "RECORDED_EVENTS_INVALID")
    for recorded_event in recorded_events:
        event = _mapping(recorded_event, "RECORDED_EVENT_INVALID")
        canonical = _find(definitions, str(event.get("catalogId")))
        parameters = [
            _mapping(item, "RECORDED_PARAMETER_INVALID").get("name")
            for item in _sequence(
                event.get("parameters"), "RECORDED_PARAMETERS_INVALID"
            )
        ]
        expected_parameters = [
            name
            for name in _sequence(
                canonical.get("parameters"), "CANONICAL_PARAMETERS_INVALID"
            )
            if name not in ENVELOPE_PARAMETERS
        ]
        if (
            canonical.get("event_name") != event.get("eventName")
            or canonical.get("source") != "public_web"
            or canonical.get("mvp") is not True
            or parameters != expected_parameters
        ):
            _fail("CANONICAL_EVENT_DRIFT")

    controls = _parse_yaml(
        _read_regular(
            root,
            Path(
                "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
            ),
        )
    )
    control = _find(_records(controls, "controls"), "SEC-DATA-007")
    if (
        control.get("title") != "Data minimization"
        or control.get("requirement") != "Event/Logへ不要な個人情報を収集しない"
        or control.get("priority") != "P0"
    ):
        _fail("CANONICAL_SECURITY_DRIFT")

    tests = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml")
        )
    )
    suites = _records(tests, "suites")
    if _find(suites, "TST-022").get("name") != "Browser functional E2E":
        _fail("CANONICAL_TEST_DRIFT")
    if _find(suites, "TST-030").get("name") != "Analytics reconciliation":
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
    if len(bindings) != 21:
        _fail("SOURCE_BINDING_COUNT_INVALID")
    seen: set[str] = set()
    for binding in bindings:
        path = binding["path"]
        if path in seen:
            _fail("SOURCE_BINDING_DUPLICATE")
        seen.add(path)
        if _sha256(_read_regular(root, Path(path))) != binding["sha256"]:
            _fail("SOURCE_BINDING_DRIFT")
    return bindings


def _validate_dependencies(root: Path, contract: dict[str, Any]) -> None:
    dependencies = _mapping(
        contract.get("dependency_bindings"), "DEPENDENCY_BINDINGS_INVALID"
    )
    st1002 = _mapping(dependencies.get("ST-1002"), "ST1002_BINDING_INVALID")
    recorded_binding = _mapping(st1002.get("recorded_view"), "ST1002_BINDING_INVALID")
    article = _parse_json(_read_regular(root, Path(recorded_binding["path"])))
    route = _mapping(article.get("route"), "ST1002_RECORDED_INVALID")
    screen = _mapping(article.get("screen"), "ST1002_RECORDED_INVALID")
    runtime = _mapping(article.get("runtimeBoundary"), "ST1002_RECORDED_INVALID")
    if (
        route.get("path") != st1002.get("route_path")
        or screen.get("id") != st1002.get("screen_id")
        or st1002.get("public_identity_fields_available") is not False
        or runtime.get("affiliateCtaRendered") is not False
    ):
        _fail("ST1002_DEPENDENCY_DRIFT")

    st1004 = _mapping(dependencies.get("ST-1004"), "ST1004_BINDING_INVALID")
    cta_binding = _mapping(st1004.get("recorded_view"), "ST1004_BINDING_INVALID")
    disclosure = _parse_json(_read_regular(root, Path(cta_binding["path"])))
    article_view = _mapping(disclosure.get("articleView"), "ST1004_RECORDED_INVALID")
    cta = _mapping(article_view.get("affiliateCta"), "ST1004_RECORDED_INVALID")
    navigation = _mapping(
        article_view.get("navigationBoundary"), "ST1004_RECORDED_INVALID"
    )
    if (
        cta.get("state") != "UNAVAILABLE_SOURCE"
        or cta.get("rendered") is not False
        or navigation.get("nativeAnchorRequired") is not True
        or navigation.get("directDestinationRequired") is not True
        or navigation.get("instrumentationFailureBlocksNavigation") is not False
    ):
        _fail("ST1004_DEPENDENCY_DRIFT")

    st1201 = _mapping(dependencies.get("ST-1201"), "ST1201_BINDING_INVALID")
    if (
        st1201.get("mode") != "RECORDED_TEST_ONLY"
        or st1201.get("tracking_activation") != "DISABLED"
        or st1201.get("persistence") != "NOT_EXECUTED"
        or st1201.get("public_endpoint_connected") is not False
    ):
        _fail("ST1201_DEPENDENCY_DRIFT")
    domain_binding = _mapping(st1201.get("domain"), "ST1201_BINDING_INVALID")
    domain_source = _read_regular(root, Path(domain_binding["path"])).decode("utf-8")
    for marker in (
        'DISABLED_OD_012 = "DISABLED_OD_012"',
        'RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"',
        'DISABLED = "DISABLED"',
        'UNRESOLVED_OD_012 = "UNRESOLVED_OD_012"',
    ):
        if marker not in domain_source:
            _fail("ST1201_SOURCE_DRIFT")

    click = _mapping(
        dependencies.get("public_click_contract"), "PUBLIC_CLICK_BINDING_INVALID"
    )
    if (
        click.get("operation_id") != "PUB-004"
        or click.get("connected") is not False
        or click.get("mapping_state") != "NON_ISOMORPHIC_UNRESOLVED_NO_MAPPING"
    ):
        _fail("PUBLIC_CLICK_BOUNDARY_DRIFT")
    openapi_binding = _mapping(click.get("contract"), "PUBLIC_CLICK_BINDING_INVALID")
    public_api = _parse_yaml(_read_regular(root, Path(openapi_binding["path"])))
    paths = _mapping(public_api.get("paths"), "PUBLIC_OPENAPI_INVALID")
    event_path = _mapping(paths.get("/api/v1/events/click"), "PUBLIC_OPENAPI_INVALID")
    operation = _mapping(event_path.get("post"), "PUBLIC_OPENAPI_INVALID")
    if operation.get("operationId") != "PUB-004":
        _fail("PUBLIC_CLICK_BOUNDARY_DRIFT")


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
    contract = _parse_yaml(_read_regular(root, CONTRACT_PATH))
    _assert_contract_shape(contract)
    _validate_canonical(root, contract)
    bindings = _validate_bindings(root, contract)
    _validate_dependencies(root, contract)

    recorded = _mapping(contract.get("recorded_runtime"), "RECORDED_RUNTIME_INVALID")
    recorded_bytes = _render_json(recorded)
    sources = [
        _source_entry(root, relative, "OWNER_SOURCE") for relative in OWNER_SOURCE_PATHS
    ]
    owned = {entry["uri"].removeprefix("repo://") for entry in sources}
    for binding in bindings:
        if binding["path"] in owned:
            continue
        role = (
            "CANONICAL_INPUT"
            if binding["path"].startswith("docs/canonical/")
            else "DEPENDENCY_ARTIFACT"
        )
        sources.append(_source_entry(root, Path(binding["path"]), role))

    manifest = {
        "schema_version": 2,
        "story_id": "ST-1202",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_PUBLIC_EVENT_INSTRUMENTATION_RUNTIME_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{GENERATED_PATH.as_posix()}",
                "artifact_role": "DETERMINISTIC_DEFAULT_DISABLED_AND_RECORDED_EVENT_FIXTURE",
                "media_type": "application/json",
                "bytes": len(recorded_bytes),
                "sha256": _sha256(recorded_bytes),
            }
        ],
        "generation": {
            "owner": "repo://scripts/build_st1202_public_event_instrumentation.py",
            "command": ".venv/bin/python scripts/build_st1202_public_event_instrumentation.py",
            "check_command": ".venv/bin/python scripts/build_st1202_public_event_instrumentation.py --check",
            "network": "NONE",
        },
        "runtime_boundary": contract["runtime_boundary"],
        "privacy_boundary": contract["privacy_boundary"],
        "navigation_boundary": contract["navigation_boundary"],
        "security_boundary": contract["security_boundary"],
        "authority": contract["authority"],
    }
    return (
        (GENERATED_PATH, recorded_bytes),
        (MANIFEST_PATH, _render_yaml(manifest)),
    )


def _atomic_write(root: Path, relative: Path, payload: bytes) -> None:
    pure = _relative_path(relative)
    target = root.joinpath(*pure.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        metadata = os.lstat(target)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("OUTPUT_TARGET_INVALID")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
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
            except St1202BuildError:
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
    except St1202BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
