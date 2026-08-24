#!/usr/bin/env python3
"""Build deterministic ST-1006 V2 performance/image-safety artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn

import yaml


ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1006/contracts/public-performance-runtime.v2.yaml"
)
GENERATED_PATH: Final = Path(
    "changes/st-1006/generated/public-performance-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1006/runtime-manifest.v2.yaml")
GENERATED_PATHS: Final = (GENERATED_PATH, MANIFEST_PATH)

CANONICAL_SOURCE_PATHS: Final = (
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md"),
    Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"),
    Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
)
DEPENDENCY_SOURCE_PATHS: Final = (
    Path("changes/st-1002/contracts/public-article-renderer-runtime.v2.yaml"),
    Path("changes/st-1002/generated/public-article-renderer-recorded.v2.json"),
    Path("changes/st-1002/runtime-manifest.v2.yaml"),
)
OWNER_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("scripts/build_st1006_public_performance_runtime.py"),
    Path("packages/web-ui/src/public-performance-runtime-v2.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("changes/st-1006/PREFLIGHT-v2.md"),
    Path("changes/st-1006/README-v2.md"),
    Path("changes/st-1006/completion/completion.v2.yaml"),
    Path("tests/st1006_v2/public-performance-runtime.test.ts"),
    Path("tests/st1006_v2/public-performance-image.test.ts"),
    Path("tests/st1006_v2/public-performance-rum-negative.test.ts"),
    Path("tests/st1006_v2/public-performance-static.test.ts"),
    Path("tests/st1006_v2/test_generation.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1006",
    "objective": "CWV instrumentation/cache/image最適化",
    "depends_on": ["ST-1002"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["RUM hooks", "budgets"],
    "acceptance_criteria": ["lab target and no CLS from CTA"],
    "test_suites": ["TST-027"],
}
EXPECTED_EVT_012: Final = {
    "id": "EVT-012",
    "event_name": "web_vital",
    "source": "public_web",
    "purpose": "RUM性能",
    "ga4_mapping": "custom metric",
    "mvp": True,
    "parameters": [
        "article_id",
        "snapshot_id",
        "metric_name",
        "metric_value",
        "rating",
        "navigation_type",
    ],
    "prohibited_parameters": [
        "email",
        "phone",
        "raw_ip",
        "full_user_agent",
        "raw_search_query",
        "article_body",
        "source_packet_text",
        "affiliate_url_query_secret",
    ],
    "implementation_status": "NOT_STARTED",
    "runtime_verification": "NOT_EXECUTED",
}


class St1006BuildError(RuntimeError):
    """Closed, non-reflecting ST-1006 owner-generator failure."""


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
            raise St1006BuildError("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _fail(code: str) -> NoReturn:
    raise St1006BuildError(code)


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
        current /= part
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
    except St1006BuildError:
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


def _number(value: Any, code: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        _fail(code)
    return float(value)


def _nearest_rank_75(values: list[Any], *, maximum: float) -> float:
    if not values or len(values) > 100:
        _fail("PERFORMANCE_SAMPLE_INVALID")
    samples = [_number(value, "PERFORMANCE_SAMPLE_INVALID") for value in values]
    if any(value < 0 or value > maximum for value in samples):
        _fail("PERFORMANCE_SAMPLE_INVALID")
    samples.sort()
    return samples[math.ceil(len(samples) * 0.75) - 1]


def _normalize_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _assert_exact_keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _assert_contract_shape(contract: dict[str, Any]) -> None:
    document = _mapping(contract.get("document"), "CONTRACT_DOCUMENT_INVALID")
    if document != {
        "id": "RAOS-ST1006-PUBLIC-PERFORMANCE-RUNTIME-002",
        "version": "2.0.0",
        "story_id": "ST-1006",
        "status": "LOCAL_CODE_COMPLETE",
        "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        "enabled_environments": ["DEV", "CI"],
        "enabled_by_default_outside_local": False,
    }:
        _fail("CONTRACT_DOCUMENT_DRIFT")
    if contract.get("classification") != "LOCAL_RECORDED_PERFORMANCE_IMAGE_SAFETY_V2":
        _fail("CONTRACT_CLASSIFICATION_DRIFT")

    canonical = _sequence(
        contract.get("canonical_sources"), "CANONICAL_SOURCES_INVALID"
    )
    if canonical != [path.as_posix() for path in CANONICAL_SOURCE_PATHS]:
        _fail("CANONICAL_SOURCES_DRIFT")
    dependencies = _mapping(contract.get("dependency_sources"), "DEPENDENCIES_INVALID")
    if dependencies != {
        "ST-1002": [path.as_posix() for path in DEPENDENCY_SOURCE_PATHS]
    }:
        _fail("DEPENDENCY_SOURCES_DRIFT")

    route = _mapping(contract.get("route_boundary"), "ROUTE_BOUNDARY_INVALID")
    if route != {
        "screen_id": "PUB-003",
        "route_template": "/articles/{slug}",
        "exact_local_path": "/articles/synthetic-recorded-policy-seo",
        "local_route_registered": True,
        "source_projection_route_activated": False,
        "public_read_served": False,
        "current_route_image_count": 0,
        "current_route_affiliate_cta_rendered": False,
        "current_cache_control": "no-store",
    }:
        _fail("ROUTE_BOUNDARY_DRIFT")

    performance = _mapping(
        contract.get("performance_policy"), "PERFORMANCE_POLICY_INVALID"
    )
    if (
        performance.get("percentile_method") != "NEAREST_RANK"
        or performance.get("percentile") != 75
        or performance.get("field_window") != "ROLLING_28_DAYS"
        or performance.get("field_assessment") != "NOT_EXECUTED"
        or performance.get("browser_lab_assessment") != "NOT_EXECUTED"
        or performance.get("formal_tst_027") != "NOT_EXECUTED"
    ):
        _fail("PERFORMANCE_POLICY_DRIFT")
    targets = _sequence(performance.get("targets"), "PERFORMANCE_TARGETS_INVALID")
    if targets != [
        {"metric": "LCP", "threshold": 2500, "unit": "MILLISECONDS"},
        {"metric": "INP", "threshold": 200, "unit": "MILLISECONDS"},
        {"metric": "CLS", "threshold": 0.1, "unit": "SCORE"},
    ]:
        _fail("PERFORMANCE_TARGETS_DRIFT")
    fixture = _mapping(
        performance.get("recorded_fixture"), "PERFORMANCE_FIXTURE_INVALID"
    )
    if (
        fixture.get("provenance") != "RECORDED_SYNTHETIC_ONLY"
        or fixture.get("formal_evidence") is not False
        or fixture.get("browser_observed") is not False
        or fixture.get("expected_state") != "RECORDED_SYNTHETIC_PASS"
    ):
        _fail("PERFORMANCE_FIXTURE_DRIFT")

    image = _mapping(contract.get("image_policy"), "IMAGE_POLICY_INVALID")
    expected_image_policy = {
        "profile": "VERIFIED_SOURCE_REQUIRED_RESERVED_RESPONSIVE_IMAGE_V1",
        "dimensions_required": True,
        "responsive_widths_required": True,
        "sizes_required": True,
        "reserve_layout_space": True,
        "upscale_allowed": False,
        "cropping_allowed": False,
        "decoding": "async",
        "above_fold_loading": "eager",
        "above_fold_fetch_priority": "high",
        "below_fold_loading": "lazy",
        "below_fold_fetch_priority": "auto",
        "maximum_dimension_px": 8192,
        "maximum_responsive_candidates": 8,
        "recorded_fixture": image.get("recorded_fixture"),
    }
    if image != expected_image_policy:
        _fail("IMAGE_POLICY_DRIFT")
    image_fixture = _mapping(image.get("recorded_fixture"), "IMAGE_FIXTURE_INVALID")
    if image_fixture != {
        "asset_id": "st1006-synthetic-image-001",
        "source_state": "RECORDED_SYNTHETIC_ONLY",
        "placement": "BELOW_FOLD",
        "intrinsic_width": 640,
        "intrinsic_height": 360,
        "responsive_widths": [320, 640],
        "expected_sizes": "(max-width: 640px) 100vw, 640px",
        "expected_loading": "lazy",
        "expected_fetch_priority": "auto",
        "expected_state": "RECORDED_SYNTHETIC_PASS",
    }:
        _fail("IMAGE_FIXTURE_DRIFT")

    cta = _mapping(contract.get("cta_layout_policy"), "CTA_LAYOUT_POLICY_INVALID")
    if (
        cta.get("layout_shift_allowed") is not False
        or cta.get("reservation_required") is not True
    ):
        _fail("CTA_LAYOUT_POLICY_DRIFT")
    cta_fixture = _mapping(cta.get("recorded_fixture"), "CTA_LAYOUT_FIXTURE_INVALID")
    if (
        cta_fixture.get("provenance") != "RECORDED_SYNTHETIC_ONLY"
        or cta_fixture.get("expected_layout_shift_score") != 0
        or cta_fixture.get("expected_state") != "RECORDED_SYNTHETIC_PASS"
    ):
        _fail("CTA_LAYOUT_FIXTURE_DRIFT")

    rum = _mapping(contract.get("rum_hook_policy"), "RUM_HOOK_POLICY_INVALID")
    if rum != {
        "event_catalog_id": "EVT-012",
        "event_name": "web_vital",
        "source": "public_web",
        "privacy_decision_id": "OD-012",
        "privacy_decision_status": "HUMAN_DECISION_REQUIRED",
        "safe_default": "NONESSENTIAL_TRACKING_DISABLED",
        "mode": "DISABLED_OD_012",
        "enabled": False,
        "capture_behavior": "DROP_WITHOUT_INSPECTION",
        "buffer_capacity": 0,
        "transport": None,
        "provider": None,
        "collector_connected": False,
        "cookies_used": False,
        "storage_used": False,
        "consent_inferred": False,
        "captured_events": [],
    }:
        _fail("RUM_HOOK_POLICY_DRIFT")

    authority = _mapping(contract.get("authority"), "AUTHORITY_INVALID")
    if any(value not in {False, "NOT_EXECUTED"} for value in authority.values()):
        _fail("AUTHORITY_ESCALATION")
    serialized = json.dumps(contract, ensure_ascii=False)
    if "https://" in serialized or "http://" in serialized:
        _fail("EXTERNAL_URL_PROHIBITED")


def _validate_canonical(root: Path) -> None:
    backlog = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
        )
    )
    story = _find(_records(backlog, "stories"), "ST-1006")
    for key, expected in EXPECTED_STORY.items():
        if story.get(key) != expected:
            _fail("CANONICAL_STORY_DRIFT")

    screens = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml")
        )
    )
    screen = _find(_records(screens, "screens"), "PUB-003")
    if (
        screen.get("route") != "/articles/{slug}"
        or screen.get("area") != "public"
        or screen.get("critical_action") is not False
    ):
        _fail("CANONICAL_SCREEN_DRIFT")

    events = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml")
        )
    )
    if _find(_records(events, "events"), "EVT-012") != EXPECTED_EVT_012:
        _fail("CANONICAL_EVENT_DRIFT")

    decisions = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml")
        )
    )
    decision = _find(_records(decisions, "items"), "OD-012")
    if (
        decision.get("status") != "HUMAN_DECISION_REQUIRED"
        or decision.get("default_behavior")
        != "非必須Trackingを無効化しFirst-party最小Eventのみ"
        or decision.get("blocking") is not True
    ):
        _fail("CANONICAL_PRIVACY_DECISION_DRIFT")

    security = _parse_yaml(
        _read_regular(
            root,
            Path(
                "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
            ),
        )
    )
    control = _find(_records(security, "controls"), "SEC-DATA-007")
    if (
        control.get("requirement") != "Event/Logへ不要な個人情報を収集しない"
        or control.get("verification") != "schema/privacy review"
        or control.get("priority") != "P0"
    ):
        _fail("CANONICAL_SECURITY_CONTROL_DRIFT")

    suites = _parse_yaml(
        _read_regular(
            root, Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml")
        )
    )
    suite = _find(_records(suites, "suites"), "TST-027")
    if (
        suite.get("layer") != "performance"
        or suite.get("release_blocking") is not True
        or suite.get("environments") != ["staging"]
        or suite.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("CANONICAL_TEST_SUITE_DRIFT")

    ui_design = _read_regular(
        root, Path("docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md")
    ).decode("utf-8")
    for required in (
        "LCP 2.5秒以下、INP 200ms以下、CLS 0.1以下を75 percentile",
        "Imageは寸法を予約し、Affiliate/Analytics ScriptがLayout Shiftを起こさない",
        "Real User Monitoringを実装・観測するまでは達成済みとしない",
    ):
        if required not in ui_design:
            _fail("CANONICAL_UI_PERFORMANCE_DRIFT")


def _validate_dependency(root: Path) -> None:
    contract = _parse_yaml(_read_regular(root, DEPENDENCY_SOURCE_PATHS[0]))
    document = _mapping(contract.get("document"), "DEPENDENCY_CONTRACT_INVALID")
    route = _mapping(contract.get("route"), "DEPENDENCY_ROUTE_INVALID")
    render = _mapping(contract.get("render_mapping"), "DEPENDENCY_RENDER_INVALID")
    runtime = _mapping(contract.get("runtime_boundary"), "DEPENDENCY_RUNTIME_INVALID")
    if (
        document.get("story_id") != "ST-1002"
        or document.get("status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or route.get("local_path") != "/articles/synthetic-recorded-policy-seo"
        or route.get("local_route_registered") is not True
        or route.get("source_projection_route_activated") is not False
        or render.get("affiliate_cta_rendered") is not False
        or render.get("product_cards_rendered") is not False
        or runtime.get("rendering") != "FORCE_DYNAMIC_SERVER_RENDERING"
    ):
        _fail("DEPENDENCY_CONTRACT_DRIFT")
    recorded = _parse_json(_read_regular(root, DEPENDENCY_SOURCE_PATHS[1]))
    recorded_route = _mapping(recorded.get("route"), "DEPENDENCY_RECORDED_INVALID")
    if recorded_route.get("path") != "/articles/synthetic-recorded-policy-seo":
        _fail("DEPENDENCY_RECORDED_DRIFT")


def _build_performance_assessment(policy: dict[str, Any]) -> dict[str, Any]:
    targets = [
        _mapping(item, "PERFORMANCE_TARGET_INVALID")
        for item in _sequence(policy.get("targets"), "PERFORMANCE_TARGETS_INVALID")
    ]
    fixture = _mapping(policy.get("recorded_fixture"), "PERFORMANCE_FIXTURE_INVALID")
    samples = _mapping(fixture.get("samples"), "PERFORMANCE_SAMPLES_INVALID")
    expected_values = _mapping(
        fixture.get("expected_percentile_values"), "PERFORMANCE_EXPECTED_INVALID"
    )
    results: list[dict[str, Any]] = []
    for target in targets:
        metric = target.get("metric")
        if metric not in {"LCP", "INP", "CLS"}:
            _fail("PERFORMANCE_METRIC_INVALID")
        maximum = 100.0 if metric == "CLS" else 600_000.0
        observed = _nearest_rank_75(
            _sequence(samples.get(metric), "PERFORMANCE_SAMPLE_INVALID"),
            maximum=maximum,
        )
        expected = _number(expected_values.get(metric), "PERFORMANCE_EXPECTED_INVALID")
        if observed != expected:
            _fail("PERFORMANCE_EXPECTED_DRIFT")
        threshold = _number(target.get("threshold"), "PERFORMANCE_TARGET_INVALID")
        state = (
            "RECORDED_SYNTHETIC_PASS"
            if observed <= threshold
            else "RECORDED_SYNTHETIC_FAIL"
        )
        results.append(
            {
                "metric": metric,
                "percentile": 75,
                "percentileMethod": "NEAREST_RANK",
                "threshold": _normalize_number(threshold),
                "unit": target.get("unit"),
                "recordedSyntheticValue": _normalize_number(observed),
                "state": state,
                "formalEvidence": False,
                "browserObserved": False,
                "fieldMeasurement": False,
            }
        )
    overall = (
        "RECORDED_SYNTHETIC_PASS"
        if all(result["state"] == "RECORDED_SYNTHETIC_PASS" for result in results)
        else "RECORDED_SYNTHETIC_FAIL"
    )
    if overall != fixture.get("expected_state"):
        _fail("PERFORMANCE_STATE_DRIFT")
    return {
        "provenance": "RECORDED_SYNTHETIC_ONLY",
        "fieldWindow": "ROLLING_28_DAYS",
        "results": results,
        "state": overall,
        "formalEvidence": False,
        "browserObserved": False,
        "fieldMeasurement": False,
    }


def _positive_integer(value: Any, code: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(code)
    return value


def _build_image_presentation(policy: dict[str, Any]) -> dict[str, Any]:
    fixture = _mapping(policy.get("recorded_fixture"), "IMAGE_FIXTURE_INVALID")
    width = _positive_integer(
        fixture.get("intrinsic_width"), "IMAGE_DIMENSIONS_INVALID"
    )
    height = _positive_integer(
        fixture.get("intrinsic_height"), "IMAGE_DIMENSIONS_INVALID"
    )
    maximum_dimension = _positive_integer(
        policy.get("maximum_dimension_px"), "IMAGE_POLICY_INVALID"
    )
    maximum_candidates = _positive_integer(
        policy.get("maximum_responsive_candidates"), "IMAGE_POLICY_INVALID"
    )
    if width > maximum_dimension or height > maximum_dimension:
        _fail("IMAGE_DIMENSIONS_INVALID")
    responsive = [
        _positive_integer(item, "IMAGE_RESPONSIVE_WIDTH_INVALID")
        for item in _sequence(
            fixture.get("responsive_widths"), "IMAGE_RESPONSIVE_WIDTH_INVALID"
        )
    ]
    if (
        len(responsive) > maximum_candidates
        or responsive != sorted(set(responsive))
        or responsive[-1] != width
        or any(item > width for item in responsive)
    ):
        _fail("IMAGE_RESPONSIVE_WIDTH_INVALID")
    sizes = f"(max-width: {width}px) 100vw, {width}px"
    placement = fixture.get("placement")
    if placement == "ABOVE_FOLD":
        loading = policy.get("above_fold_loading")
        priority = policy.get("above_fold_fetch_priority")
    elif placement == "BELOW_FOLD":
        loading = policy.get("below_fold_loading")
        priority = policy.get("below_fold_fetch_priority")
    else:
        _fail("IMAGE_PLACEMENT_INVALID")
    if (
        sizes != fixture.get("expected_sizes")
        or loading != fixture.get("expected_loading")
        or priority != fixture.get("expected_fetch_priority")
        or fixture.get("expected_state") != "RECORDED_SYNTHETIC_PASS"
    ):
        _fail("IMAGE_EXPECTED_DRIFT")
    return {
        "assetId": fixture.get("asset_id"),
        "sourceState": fixture.get("source_state"),
        "placement": placement,
        "renderable": False,
        "src": None,
        "srcSet": None,
        "width": width,
        "height": height,
        "aspectRatio": f"{width} / {height}",
        "responsiveWidths": responsive,
        "sizes": sizes,
        "loading": loading,
        "decoding": policy.get("decoding"),
        "fetchPriority": priority,
        "layoutSpaceReserved": True,
        "upscaleAllowed": False,
        "croppingAllowed": False,
        "state": "RECORDED_SYNTHETIC_PASS",
        "formalEvidence": False,
    }


def _rect(value: Any) -> dict[str, float]:
    rect = _mapping(value, "CTA_LAYOUT_RECT_INVALID")
    _assert_exact_keys(rect, {"x", "y", "width", "height"}, "CTA_LAYOUT_RECT_INVALID")
    result = {
        key: _number(rect.get(key), "CTA_LAYOUT_RECT_INVALID")
        for key in ("x", "y", "width", "height")
    }
    if (
        abs(result["x"]) > 1_000_000
        or abs(result["y"]) > 1_000_000
        or result["width"] <= 0
        or result["height"] <= 0
        or result["width"] > 8192
        or result["height"] > 8192
    ):
        _fail("CTA_LAYOUT_RECT_INVALID")
    return result


def _build_cta_assessment(policy: dict[str, Any]) -> dict[str, Any]:
    fixture = _mapping(policy.get("recorded_fixture"), "CTA_LAYOUT_FIXTURE_INVALID")
    before = _rect(fixture.get("before"))
    after = _rect(fixture.get("after"))
    stable = before == after
    score: int | None = 0 if stable else None
    state = "RECORDED_SYNTHETIC_PASS" if stable else "RECORDED_SYNTHETIC_FAIL"
    if score != fixture.get("expected_layout_shift_score") or state != fixture.get(
        "expected_state"
    ):
        _fail("CTA_LAYOUT_EXPECTED_DRIFT")
    return {
        "provenance": "RECORDED_SYNTHETIC_ONLY",
        "stableReservation": stable,
        "recordedLayoutShiftScore": score,
        "state": state,
        "browserObserved": False,
        "formalEvidence": False,
    }


def _camel_authority(authority: dict[str, Any]) -> dict[str, Any]:
    return {
        "approvalAuthorized": authority["approval_authorized"],
        "trackingAuthorized": authority["tracking_authorized"],
        "publicationAuthorized": authority["publication_authorized"],
        "stagingAuthorized": authority["staging_authorized"],
        "releaseAuthorized": authority["release_authorized"],
        "productionAuthorized": authority["production_authorized"],
        "externalWrite": authority["external_write"],
        "network": authority["network"],
        "persistence": authority["persistence"],
        "live": authority["live"],
        "browserLab": authority["browser_lab"],
        "fieldRum": authority["field_rum"],
        "formalTst027": authority["TST-027"],
        "staging": authority["staging"],
        "publication": authority["publication"],
        "release": authority["release"],
        "production": authority["production"],
    }


def _build_runtime(contract: dict[str, Any]) -> dict[str, Any]:
    route = _mapping(contract["route_boundary"], "ROUTE_BOUNDARY_INVALID")
    performance = _mapping(contract["performance_policy"], "PERFORMANCE_POLICY_INVALID")
    image = _mapping(contract["image_policy"], "IMAGE_POLICY_INVALID")
    cta = _mapping(contract["cta_layout_policy"], "CTA_LAYOUT_POLICY_INVALID")
    rum = _mapping(contract["rum_hook_policy"], "RUM_HOOK_POLICY_INVALID")
    authority = _mapping(contract["authority"], "AUTHORITY_INVALID")
    return {
        "schemaVersion": 2,
        "storyId": "ST-1006",
        "classification": contract["classification"],
        "routeBoundary": {
            "screenId": route["screen_id"],
            "routeTemplate": route["route_template"],
            "exactLocalPath": route["exact_local_path"],
            "localRouteRegistered": route["local_route_registered"],
            "sourceProjectionRouteActivated": route[
                "source_projection_route_activated"
            ],
            "publicReadServed": route["public_read_served"],
            "currentRouteImageCount": route["current_route_image_count"],
            "currentRouteAffiliateCtaRendered": route[
                "current_route_affiliate_cta_rendered"
            ],
        },
        "performanceBudgets": {
            "targets": [
                {
                    "metric": target["metric"],
                    "percentile": 75,
                    "operator": "<=",
                    "threshold": target["threshold"],
                    "unit": target["unit"],
                    "fieldWindow": "ROLLING_28_DAYS",
                }
                for item in performance["targets"]
                for target in [_mapping(item, "PERFORMANCE_TARGET_INVALID")]
            ],
            "recordedSyntheticAssessment": _build_performance_assessment(performance),
            "fieldAssessment": performance["field_assessment"],
            "browserLabAssessment": performance["browser_lab_assessment"],
            "formalTst027": performance["formal_tst_027"],
        },
        "imagePolicy": {
            "profile": image["profile"],
            "dimensionsRequired": image["dimensions_required"],
            "responsiveWidthsRequired": image["responsive_widths_required"],
            "sizesRequired": image["sizes_required"],
            "reserveLayoutSpace": image["reserve_layout_space"],
            "upscaleAllowed": image["upscale_allowed"],
            "croppingAllowed": image["cropping_allowed"],
            "maximumDimensionPx": image["maximum_dimension_px"],
            "maximumResponsiveCandidates": image["maximum_responsive_candidates"],
            "recordedSyntheticPresentation": _build_image_presentation(image),
            "currentRouteImageApplied": False,
        },
        "ctaLayoutPolicy": {
            "layoutShiftAllowed": cta["layout_shift_allowed"],
            "reservationRequired": cta["reservation_required"],
            "recordedSyntheticAssessment": _build_cta_assessment(cta),
            "currentRouteCtaApplied": False,
        },
        "rumHook": {
            "eventCatalogId": rum["event_catalog_id"],
            "eventName": rum["event_name"],
            "source": rum["source"],
            "privacyDecisionId": rum["privacy_decision_id"],
            "privacyDecisionStatus": rum["privacy_decision_status"],
            "safeDefault": rum["safe_default"],
            "mode": rum["mode"],
            "enabled": rum["enabled"],
            "captureBehavior": rum["capture_behavior"],
            "bufferCapacity": rum["buffer_capacity"],
            "transport": rum["transport"],
            "provider": rum["provider"],
            "collectorConnected": rum["collector_connected"],
            "cookiesUsed": rum["cookies_used"],
            "storageUsed": rum["storage_used"],
            "consentInferred": rum["consent_inferred"],
            "capturedEvents": rum["captured_events"],
        },
        "cacheBoundary": {
            "currentRouteCacheControl": route["current_cache_control"],
            "currentRouteCacheMutationApplied": False,
            "publicCacheStrategySelected": False,
        },
        "authority": _camel_authority(authority),
    }


def _binding(root: Path, relative: Path) -> dict[str, str]:
    return {
        "path": relative.as_posix(),
        "sha256": _sha256(_read_regular(root, relative)),
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _yaml_bytes(value: Any) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    ).encode("utf-8")


def expected_artifacts(root: Path = ROOT) -> tuple[tuple[Path, bytes], ...]:
    contract = _parse_yaml(_read_regular(root, CONTRACT_PATH))
    _assert_contract_shape(contract)
    _validate_canonical(root)
    _validate_dependency(root)
    runtime_payload = _json_bytes(_build_runtime(contract))
    manifest = {
        "document": {
            "id": "RAOS-ST1006-PUBLIC-PERFORMANCE-RUNTIME-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-1006",
            "status": "LOCAL_CODE_COMPLETE",
            "authority": "LOCAL_REVERSIBLE_DEVELOPMENT_ONLY",
        },
        "classification": "LOCAL_RECORDED_PERFORMANCE_IMAGE_SAFETY_V2",
        "generated_by": "scripts/build_st1006_public_performance_runtime.py",
        "source_bindings": [_binding(root, path) for path in OWNER_SOURCE_PATHS],
        "canonical_bindings": [_binding(root, path) for path in CANONICAL_SOURCE_PATHS],
        "dependency_bindings": {
            "ST-1002": [_binding(root, path) for path in DEPENDENCY_SOURCE_PATHS]
        },
        "generated_outputs": [
            {"path": GENERATED_PATH.as_posix(), "sha256": _sha256(runtime_payload)}
        ],
        "authority": _mapping(contract["authority"], "AUTHORITY_INVALID"),
    }
    return ((GENERATED_PATH, runtime_payload), (MANIFEST_PATH, _yaml_bytes(manifest)))


def _write_atomic(root: Path, relative: Path, payload: bytes) -> None:
    pure = _relative_path(relative)
    parent = root.joinpath(*pure.parts[:-1])
    parent.mkdir(parents=True, exist_ok=True)
    if parent.resolve(strict=True) != parent.absolute():
        _fail("OUTPUT_PARENT_INVALID")
    destination = parent / pure.parts[-1]
    if destination.exists() or destination.is_symlink():
        metadata = os.lstat(destination)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("OUTPUT_LEAF_INVALID")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def build(root: Path = ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, expected in artifacts:
            if _read_regular(root, relative) != expected:
                _fail("GENERATED_OUTPUT_DRIFT")
        return
    for relative, payload in artifacts:
        _write_atomic(root, relative, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic ST-1006 V2 local artifacts."
    )
    parser.add_argument("--check", action="store_true", help="verify without writing")
    try:
        arguments = parser.parse_args(argv)
        build(ROOT, check=arguments.check)
    except St1006BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
