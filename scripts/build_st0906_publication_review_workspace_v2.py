#!/usr/bin/env python3
"""Build the deterministic ST-0906 recorded publication-review workspace."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
from pathlib import Path
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import secure_generated_publication  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"

CONTRACT_PATH: Final = Path(
    "changes/st-0906/contracts/publication-review-workspace.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-0906/generated/publication-review-workspace-recorded.v2.json"
)
GENERATED_TS_PATH: Final = Path("packages/web-ui/src/publication-review-recorded.v2.ts")
MANIFEST_PATH: Final = Path("changes/st-0906/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0906_publication_review_workspace_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)

CANONICAL_BINDINGS: Final = (
    (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
        "integration",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
        "canonicalDecisions",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        "openDecisions",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md"),
        "0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e",
        "uiDesign",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"),
        "dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050",
        "screenCatalog",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml"),
        "986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2",
        "componentCatalog",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_workflow_catalog_v1.0.yaml"),
        "59983683ec920cf450d0d887ee43f0b9871e500c2025562f9bec5c6bbc6fe87e",
        "workflowCatalog",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv"),
        "690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e",
        "accessibilityChecklist",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
        "securityDesign",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
        "roleMatrix",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        "securityControls",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
        "testCatalog",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
        "storyBacklog",
    ),
)

DEPENDENCY_BINDINGS: Final = (
    (
        Path("changes/st-0901/generated/review-completion-pass.v2.json"),
        "57587322562eae4a2b58bebfc6b917e39fb05f077cf7268deb4056563950a361",
        "st0901ReviewFixture",
    ),
    (
        Path("changes/st-0902/generated/final-approval-pass.v2.json"),
        "93c44f4d303fef41304962bf4235e19491bcb45c555aecb66a87dcd34e6bca07",
        "st0902FinalApprovalFixture",
    ),
    (
        Path("changes/st-0903/generated/publication-snapshot-pass.v2.json"),
        "6f18ed11cbed99c57dac757875ce4ab3e1fab09cc24710c1fd7bce7e5823cd99",
        "st0903SnapshotFixture",
    ),
    (
        Path("changes/st-0904/generated/public-projection-recorded.v2.json"),
        "d73a112ccb1879e0f8e8fc5f6f52e75d1c9c2802d761aede81003f9343fefce1",
        "st0904ProjectionFixture",
    ),
    (
        Path("changes/st-0905/generated/publication-commands-recorded.v2.json"),
        "632e56fd8737db71016042d1d13e90773f2c444bd788d78c79e024473c23a117",
        "st0905CommandFixture",
    ),
    (
        Path("python/raos/domain/publishing/publication_commands_v2.py"),
        "cc2d975f828c9912985d64be306c633f4d7ff0dd0f6028306d85269e6c64f462",
        "st0905CommandDomain",
    ),
    (
        Path("python/raos/application/publishing/publication_commands_v2.py"),
        "28d610a84b42a2942e502ec7f39a39ba36bae8720979c8134943700b53904eb3",
        "st0905CommandApplication",
    ),
    (
        Path("python/raos/ports/publishing/publication_commands_v2.py"),
        "8b4c4d5555185089fae3381ef66868d48b8019b7a9177039fb48fc426d1f19f7",
        "st0905CommandPort",
    ),
    (
        Path("python/raos/adapters/publishing/recorded_publication_commands_v2.py"),
        "5f23520e9f877c51e169ff7c36e8fa3b2358ee4d448f5504d48f3240bce0d4b1",
        "st0905RecordedAdapter",
    ),
    (
        Path("packages/web-ui/src/serializable.ts"),
        "56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d",
        "st1101Serializable",
    ),
    (
        Path("packages/web-ui/src/route-guard.ts"),
        "8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f",
        "st1101RouteGuard",
    ),
    (
        Path("packages/web-ui/src/app-shell.ts"),
        "600c7aa29ddf9572390f7e2eec8710ed726746aa41125fe23abe2f72ba820129",
        "st1101AppShell",
    ),
    (
        Path("packages/web-ui/src/dialog.ts"),
        "494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc",
        "st1101Dialog",
    ),
    (
        Path("packages/web-ui/src/tokens.ts"),
        "548dddcf8410c95daae7e5fb6a27521949ed4512c581b97c92bb0cb2484507ef",
        "st1101Tokens",
    ),
    (SECURE_HELPER_PATH, SECURE_HELPER_SHA256, "securePublicationHelper"),
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("packages/web-ui/src/publication-review-workspace.ts"),
    Path("packages/web-ui/src/publication-review-workspace-v2.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("changes/st-0906/README.md"),
    Path("changes/st-0906/README-v2.md"),
    Path("changes/st-0906/completion/completion.v2.yaml"),
    Path("tests/st0906/publication-review-workspace-v2-model.test.ts"),
    Path("tests/st0906/publication-review-workspace-v2-render.test.ts"),
    Path("tests/st0906/publication-review-workspace-v2-boundaries.test.ts"),
    Path("tests/st0906/publication-review-workspace-v2-negative.test.ts"),
    Path("tests/st0906/publication-review-workspace-v2-generation.test.ts"),
    Path("tests/st0906/test_generation_v2.py"),
)

LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("package.json"),
    Path("package-lock.json"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)

SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *(path for path, _digest, _name in CANONICAL_BINDINGS),
    *(path for path, _digest, _name in DEPENDENCY_BINDINGS),
    *LOCKED_TOOLCHAIN_PATHS,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, GENERATED_TS_PATH, MANIFEST_PATH)
SCREEN_ORDER: Final = (
    "REV-001",
    "REV-002",
    "REV-003",
    "PUBA-001",
    "PUBA-002",
    "PUBA-003",
    "PUBA-004",
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024


class PublicationReviewGenerationError(ValueError):
    """Closed owner-generation error."""

    __slots__ = ()

    def __init__(self, code: str) -> None:
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PublicationReviewGenerationError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


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


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
        or getattr(yaml, "__version__", None) != EXPECTED_PYYAML_VERSION
    ):
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    try:
        observed = distribution_version("PyYAML")
    except PackageNotFoundError:
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    if observed != EXPECTED_PYYAML_VERSION:
        _fail("GENERATION_TOOLCHAIN_DRIFT")


def _read(root: Path, relative: Path, *, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        _fail("SOURCE_PATH_INVALID")
    payload = path.read_bytes()
    if not payload or len(payload) > maximum:
        _fail("SOURCE_SIZE_INVALID")
    return payload


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha(root: Path, relative: Path) -> str:
    return _sha_bytes(_read(root, relative))


def _require_bindings(root: Path) -> None:
    for relative, expected, _name in (*CANONICAL_BINDINGS, *DEPENDENCY_BINDINGS):
        if _sha(root, relative) != expected:
            _fail("SOURCE_HASH_DRIFT")


def _load_contract(root: Path) -> dict[str, Any]:
    payload = _read(root, CONTRACT_PATH)
    try:
        tokens = tuple(yaml.scan(payload))
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("YAML_FEATURE_REJECTED")
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except PublicationReviewGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    expected_keys = (
        "schema_version",
        "story_id",
        "local_status",
        "classification",
        "profile",
        "screen_order",
        "runtime_boundary",
        "projection_boundary",
        "command_boundary",
        "accessibility_boundary",
        "verification_boundary",
    )
    if type(loaded) is not dict or tuple(loaded) != expected_keys:
        _fail("CONTRACT_SHAPE_INVALID")
    contract = cast(dict[str, Any], loaded)
    runtime_boundary = _mapping(contract["runtime_boundary"], "CONTRACT_SHAPE_INVALID")
    projection_boundary = _mapping(
        contract["projection_boundary"], "CONTRACT_SHAPE_INVALID"
    )
    command_boundary = _mapping(contract["command_boundary"], "CONTRACT_SHAPE_INVALID")
    accessibility_boundary = _mapping(
        contract["accessibility_boundary"], "CONTRACT_SHAPE_INVALID"
    )
    verification_boundary = _mapping(
        contract["verification_boundary"], "CONTRACT_SHAPE_INVALID"
    )
    if (
        contract["schema_version"] != 2
        or contract["story_id"] != "ST-0906"
        or contract["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or contract["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_PUBLICATION_REVIEW_WORKSPACE_V2"
        or contract["profile"] != "ST0906_PUBLICATION_REVIEW_RECORDED_LOCAL_V2"
        or tuple(contract["screen_order"]) != SCREEN_ORDER
        or runtime_boundary
        != {
            "environments": ["ENV-DEV", "CI"],
            "source_mode": "RECORDED_SYNTHETIC_ONLY",
            "deterministic_view_model": True,
            "deterministic_html_renderer": True,
            "route_registered": False,
            "routable": False,
            "authentication_established": False,
            "authorization_granted": False,
            "data_fetch": False,
            "network": False,
            "persistence": False,
            "database_write": False,
            "cms_write": False,
            "public_state_change": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
        }
        or projection_boundary
        != {
            "exact_st0901_review_required": True,
            "exact_st0902_final_approval_required": True,
            "exact_st0903_immutable_snapshot_required": True,
            "exact_st0904_public_projection_required": True,
            "exact_st0905_recorded_command_fixture_required": True,
            "public_projection_text_only": True,
            "raw_article_body_allowed": False,
            "raw_source_allowed": False,
            "raw_prompt_allowed": False,
            "finance_allowed": False,
            "credential_allowed": False,
            "arbitrary_html_allowed": False,
            "snapshot_projection_hash_equality_claimed": False,
            "legacy_reconciliation_status": ("NOT_ESTABLISHED_RECONCILIATION_REQUIRED"),
        }
        or command_boundary
        != {
            "ui_dispatch": "DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE",
            "only_future_adapter": (
                "python.raos.adapters.publishing.recorded_publication_commands_v2"
            ),
            "only_future_profile": "ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2",
            "allowed_environments": ["ENV-DEV", "CI"],
            "active_human_required": True,
            "allowed_roles": ["MANAGING_EDITOR", "OPERATOR"],
            "mfa_required": True,
            "step_up_required": True,
            "site_scope_required": True,
            "server_reauthorization_required": True,
            "final_approval_required": True,
            "separation_of_duties_publish_required": True,
            "exact_snapshot_required": True,
            "exact_source_binding_required": True,
            "kill_switch_safe_state_required": True,
            "reason_required": True,
            "idempotency_required": True,
            "audit_required": True,
            "publish_enabled": False,
            "rollback_enabled": False,
            "unpublish_enabled": False,
            "unpublish_decision": "DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION",
        }
        or accessibility_boundary
        != {
            "semantic_html_required": True,
            "one_h1_required": True,
            "skip_link_required": True,
            "landmark_labels_required": True,
            "status_text_required": True,
            "status_code_required": True,
            "color_only_allowed": False,
            "diff_caption_required": True,
            "diff_column_headers_required": True,
            "diff_row_headers_required": True,
            "disabled_action_reason_required": True,
            "visible_focus_required": True,
            "zoom_target_percent": 200,
            "keyboard_model_required": True,
            "motion": "NONE",
            "browser_verified": False,
            "screen_reader_verified": False,
        }
        or verification_boundary
        != {
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "formal_validation": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        }
    ):
        _fail("CONTRACT_CONTENT_INVALID")
    _require_bindings(root)
    return contract


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    _fail("JSON_CONSTANT_INVALID")


def _parse_json(payload: bytes | str) -> dict[str, Any]:
    try:
        loaded = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_constant,
        )
    except PublicationReviewGenerationError:
        raise
    except Exception:
        _fail("JSON_PARSE_FAILED")
    if type(loaded) is not dict:
        _fail("JSON_SHAPE_INVALID")
    return cast(dict[str, Any], loaded)


def _mapping(value: object, code: str = "DEPENDENCY_SHAPE_INVALID") -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return cast(dict[str, Any], value)


def _sequence(value: object, code: str = "DEPENDENCY_SHAPE_INVALID") -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _text(value: object, code: str = "DEPENDENCY_SHAPE_INVALID") -> str:
    if type(value) is not str or not value or len(value) > 4096:
        _fail(code)
    return value


def _integer(value: object, code: str = "DEPENDENCY_SHAPE_INVALID") -> int:
    if type(value) is not int or value < 0:
        _fail(code)
    return value


def _false(value: object, code: str = "DEPENDENCY_AUTHORITY_INVALID") -> bool:
    if value is not False:
        _fail(code)
    return False


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        ).encode("ascii")
        + b"\n"
    )


def _bindings() -> dict[str, dict[str, str]]:
    return {
        "canonical": {name: digest for _path, digest, name in CANONICAL_BINDINGS},
        "dependencies": {name: digest for _path, digest, name in DEPENDENCY_BINDINGS},
    }


def _load_dependencies(root: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        _parse_json(_read(root, path))
        for path in (
            Path("changes/st-0901/generated/review-completion-pass.v2.json"),
            Path("changes/st-0902/generated/final-approval-pass.v2.json"),
            Path("changes/st-0903/generated/publication-snapshot-pass.v2.json"),
            Path("changes/st-0904/generated/public-projection-recorded.v2.json"),
            Path("changes/st-0905/generated/publication-commands-recorded.v2.json"),
        )
    )


def _validate_dependency_headers(
    review: dict[str, Any],
    approval: dict[str, Any],
    snapshot: dict[str, Any],
    projection: dict[str, Any],
    commands: dict[str, Any],
) -> None:
    expected = (
        (
            review,
            "ST0901_REVIEW_COMPLETION_RECORDED_LOCAL_V2",
            "LOCAL_IMPLEMENTATION_COMPLETE",
        ),
        (
            approval,
            "ST0902_FINAL_APPROVAL_RECORDED_LOCAL_V2",
            "LOCAL_IMPLEMENTATION_COMPLETE",
        ),
        (
            snapshot,
            "ST0903_PUBLICATION_SNAPSHOT_RECORDED_LOCAL_V2",
            "LOCAL_IMPLEMENTATION_COMPLETE",
        ),
        (
            projection,
            "ST0904_PUBLIC_PROJECTION_RECORDED_LOCAL_V2",
            "LOCAL_IMPLEMENTATION_COMPLETE",
        ),
        (
            commands,
            "ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2",
            "LOCAL_IMPLEMENTATION_COMPLETE",
        ),
    )
    for value, profile, status in expected:
        if value.get("schema_version") != 2 or value.get("profile") != profile:
            _fail("DEPENDENCY_PROFILE_INVALID")
        if value.get("local_status") != status:
            _fail("DEPENDENCY_STATUS_INVALID")


def _validate_authority(
    review: dict[str, Any],
    approval: dict[str, Any],
    snapshot: dict[str, Any],
    projection: dict[str, Any],
    commands: dict[str, Any],
) -> None:
    review_authority = _mapping(review.get("authority"))
    if review_authority.get("recorded_synthetic_only") is not True:
        _fail("DEPENDENCY_AUTHORITY_INVALID")
    for key in (
        "final_approval_authorized",
        "publication_snapshot_authorized",
        "publication_authorized",
        "release_authorized",
        "production_authorized",
    ):
        _false(review_authority.get(key))

    approval_authority = _mapping(approval.get("authority"))
    if approval_authority.get("recorded_synthetic_only") is not True:
        _fail("DEPENDENCY_AUTHORITY_INVALID")
    for key in (
        "real_final_approval_authorized",
        "publication_snapshot_authorized",
        "publication_authorized",
        "release_authorized",
        "production_authorized",
    ):
        _false(approval_authority.get(key))

    for value, keys in (
        (
            _mapping(snapshot.get("authority")),
            (
                "credential",
                "database_write",
                "event_emit",
                "external_write",
                "media_upload",
                "persistence",
                "production_authorized",
                "public_projection_authorized",
                "publication_authorized",
                "release_authorized",
            ),
        ),
        (
            _mapping(projection.get("authority")),
            (
                "credential",
                "database_write",
                "event_emit",
                "external_write",
                "network",
                "persistence",
                "production_authorized",
                "public_projection_authorized",
                "public_read_served",
                "publication_authorized",
                "release_authorized",
                "route_activated",
            ),
        ),
        (
            _mapping(commands.get("authority")),
            (
                "cms_write",
                "database_write",
                "event_emission",
                "external_write",
                "http_route",
                "live_provider",
                "outbox_write",
                "production_write",
                "public_state_change",
                "publication",
                "release",
                "staging_write",
            ),
        ),
    ):
        for key in keys:
            _false(value.get(key))


def _public_blocks(
    snapshot: dict[str, Any], projection: dict[str, Any]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    snapshot_output = _mapping(snapshot.get("output"))
    snapshot_value = _mapping(snapshot_output.get("snapshot"))
    renderable = _mapping(snapshot_value.get("renderable_content"))
    source_blocks = _sequence(renderable.get("blocks"))

    projection_output = _mapping(projection.get("output"))
    projected = _mapping(projection_output.get("projection"))
    public_article = _mapping(projected.get("article"))
    projected_blocks = _sequence(public_article.get("blocks"))

    if len(source_blocks) != 10 or len(projected_blocks) != 9:
        _fail("BLOCK_COUNT_INVALID")
    first = _mapping(source_blocks[0])
    if first.get("type") != "disclosure_slot":
        _fail("BLOCK_ALIGNMENT_INVALID")

    diff_rows: list[dict[str, object]] = [
        {
            "position": 0,
            "sourceBlockId": _text(first.get("block_id")),
            "sourceType": "disclosure_slot",
            "projectedBlockKey": None,
            "projectedType": "article_disclosure_text",
            "textFragmentCount": 1,
            "state": "PROJECTED_TO_ARTICLE_FIELD",
        }
    ]
    preview_blocks: list[dict[str, object]] = []
    for index, (source_value, projected_value) in enumerate(
        zip(source_blocks[1:], projected_blocks, strict=True), start=1
    ):
        source = _mapping(source_value)
        target = _mapping(projected_value)
        render_payload = _mapping(target.get("render_payload"))
        source_type = _text(source.get("type"))
        if render_payload.get("source_type") != source_type:
            _fail("BLOCK_ALIGNMENT_INVALID")
        texts = _sequence(render_payload.get("text"))
        if not all(type(item) is str and len(item) <= 1000 for item in texts):
            _fail("PUBLIC_TEXT_INVALID")
        if target.get("rendered_html") is not None:
            _fail("RAW_HTML_PRESENT")
        diff_rows.append(
            {
                "position": index,
                "sourceBlockId": _text(source.get("block_id")),
                "sourceType": source_type,
                "projectedBlockKey": _text(target.get("block_key")),
                "projectedType": _text(target.get("block_type")),
                "textFragmentCount": len(texts),
                "state": "RECORDED_TRANSFORMATION",
            }
        )
        preview_blocks.append(
            {
                "position": _integer(target.get("position")),
                "blockKey": _text(target.get("block_key")),
                "blockType": _text(target.get("block_type")),
                "sourceType": source_type,
                "text": texts,
            }
        )
    return diff_rows, preview_blocks


def _command_projection(commands: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    command_values = _mapping(commands.get("commands"))
    result_values = _mapping(commands.get("results"))
    publish_command = _parse_json(_text(command_values.get("publish")))
    rollback_command = _parse_json(_text(command_values.get("rollback")))
    publish_result = _parse_json(_text(result_values.get("publish")))
    rollback_result = _parse_json(_text(result_values.get("rollback")))
    unpublish = _mapping(command_values.get("unpublish"))

    if (
        publish_command.get("action") != "PUBLISH"
        or rollback_command.get("action") != "ROLLBACK"
        or publish_result.get("action") != "PUBLISH"
        or rollback_result.get("action") != "ROLLBACK"
        or unpublish
        != {
            "decision": "DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION",
            "executable": False,
        }
    ):
        _fail("COMMAND_SHAPE_INVALID")
    for result in (publish_result, rollback_result):
        for key in (
            "audit_persisted",
            "event_emitted",
            "outbox_persisted",
            "production_authorized",
            "projection_persisted",
            "public_read_served",
            "publication_authorized",
            "release_authorized",
            "route_activated",
        ):
            _false(result.get(key))

    return (
        {
            "actionCode": "PUBLISH",
            "label": "Publish recorded snapshot",
            "uiAvailability": "DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE",
            "recordedResultState": _text(publish_result.get("execution")),
            "commandSha256": _text(publish_command.get("command_sha256")),
            "resultSha256": _text(publish_result.get("result_sha256")),
            "idempotencyKeySha256": _text(
                publish_command.get("idempotency_key_sha256")
            ),
            "authorizationSha256": _text(publish_command.get("authorization_sha256")),
            "killSwitchStateSha256": _text(
                publish_command.get("kill_switch_state_sha256")
            ),
            "correlationId": _text(publish_command.get("correlation_id")),
            "auditRecordId": _text(publish_command.get("audit_id")),
            "auditSha256": _text(publish_result.get("audit_sha256")),
            "eventSha256": _text(publish_result.get("event_sha256")),
            "outboxSha256": _text(publish_result.get("outbox_sha256")),
            "generation": _integer(publish_result.get("generation")),
            "fromSnapshotId": publish_result.get("from_snapshot_id"),
            "toSnapshotId": _text(publish_result.get("to_snapshot_id")),
            "effectPerformedByUi": False,
            "persisted": False,
            "eventEmitted": False,
        },
        {
            "actionCode": "UNPUBLISH",
            "label": "Unpublish",
            "uiAvailability": "DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION",
            "recordedResultState": "DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION",
            "commandSha256": None,
            "resultSha256": None,
            "idempotencyKeySha256": None,
            "authorizationSha256": None,
            "killSwitchStateSha256": None,
            "correlationId": None,
            "auditRecordId": None,
            "auditSha256": None,
            "eventSha256": None,
            "outboxSha256": None,
            "generation": None,
            "fromSnapshotId": None,
            "toSnapshotId": None,
            "effectPerformedByUi": False,
            "persisted": False,
            "eventEmitted": False,
        },
        {
            "actionCode": "ROLLBACK",
            "label": "Rollback to previous recorded snapshot",
            "uiAvailability": "DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE",
            "recordedResultState": _text(rollback_result.get("execution")),
            "commandSha256": _text(rollback_command.get("command_sha256")),
            "resultSha256": _text(rollback_result.get("result_sha256")),
            "idempotencyKeySha256": _text(
                rollback_command.get("idempotency_key_sha256")
            ),
            "authorizationSha256": _text(rollback_command.get("authorization_sha256")),
            "killSwitchStateSha256": _text(
                rollback_command.get("kill_switch_state_sha256")
            ),
            "correlationId": _text(rollback_command.get("correlation_id")),
            "auditRecordId": _text(rollback_command.get("audit_id")),
            "auditSha256": _text(rollback_result.get("audit_sha256")),
            "eventSha256": _text(rollback_result.get("event_sha256")),
            "outboxSha256": _text(rollback_result.get("outbox_sha256")),
            "generation": _integer(rollback_result.get("generation")),
            "fromSnapshotId": _text(rollback_result.get("from_snapshot_id")),
            "toSnapshotId": _text(rollback_result.get("to_snapshot_id")),
            "effectPerformedByUi": False,
            "persisted": False,
            "eventEmitted": False,
        },
    )


def _build_fixture(root: Path) -> dict[str, object]:
    review, approval, snapshot, projection, commands = _load_dependencies(root)
    _validate_dependency_headers(review, approval, snapshot, projection, commands)
    _validate_authority(review, approval, snapshot, projection, commands)

    review_assignment = _mapping(review.get("assignment"))
    review_decision = _mapping(review.get("decision"))
    approval_value = _mapping(approval.get("approval"))
    approval_actor = _mapping(approval.get("actor"))
    approval_bindings = _mapping(approval.get("bindings"))
    snapshot_output = _mapping(snapshot.get("output"))
    snapshot_result = _mapping(snapshot_output.get("result"))
    snapshot_value = _mapping(snapshot_output.get("snapshot"))
    snapshot_sources = _mapping(snapshot.get("sources"))
    projection_sources = _mapping(projection.get("sources"))
    projection_output = _mapping(projection.get("output"))
    projection_value = _mapping(projection_output.get("projection"))
    projection_article = _mapping(projection_value.get("article"))
    projection_route = _mapping(projection_value.get("route"))
    projection_result = _parse_json(_text(projection_output.get("result")))
    command_sources = _mapping(commands.get("source_hashes"))
    command_states = _mapping(commands.get("states"))

    dependency_hashes = _bindings()["dependencies"]
    if (
        approval_bindings.get("review_fixture_sha256")
        != dependency_hashes["st0901ReviewFixture"]
        or snapshot_sources.get("final_approval_fixture_sha256")
        != dependency_hashes["st0902FinalApprovalFixture"]
        or projection_sources.get("st0903_fixture_sha256")
        != dependency_hashes["st0903SnapshotFixture"]
        or command_sources.get("st0903_fixture_sha256")
        != dependency_hashes["st0903SnapshotFixture"]
        or command_sources.get("st0904_fixture_sha256")
        != dependency_hashes["st0904ProjectionFixture"]
    ):
        _fail("DEPENDENCY_BINDING_INVALID")
    if (
        approval_value.get("approval_id") not in snapshot_value.get("approval_ids", [])
        or approval_bindings.get("article_version_id")
        != snapshot_value.get("article_version_id")
        or snapshot_value.get("publication_id")
        != projection_article.get("publication_id")
        or snapshot_value.get("snapshot_artifact_id")
        not in (None, projection_article.get("publication_snapshot_id"))
        or snapshot.get("seed", {}).get("snapshot_artifact_id")
        != projection_article.get("publication_snapshot_id")
        or snapshot_result.get("snapshot_sha256")
        != projection.get("input", {}).get("snapshot_sha256")
        or projection_article.get("article_id") != snapshot_value.get("article_id")
        or projection_route.get("article_id") != snapshot_value.get("article_id")
    ):
        _fail("CROSS_STORY_IDENTITY_INVALID")

    diff_rows, preview_blocks = _public_blocks(snapshot, projection)
    command_projection = _command_projection(commands)
    publish_command = command_projection[0]
    rollback_command = command_projection[2]
    after_publish = _mapping(command_states.get("after_publish"))
    after_exact_replay = _mapping(command_states.get("after_exact_replay"))
    after_semantic_replay = _mapping(command_states.get("after_semantic_replay"))
    after_rollback = _mapping(command_states.get("after_rollback"))
    if (
        after_publish != after_exact_replay
        or after_publish.get("audit_intents") != 1
        or after_publish.get("event_intents") != 1
        or after_publish.get("outbox_intents") != 1
        or after_semantic_replay.get("audit_intents") != 1
        or after_semantic_replay.get("event_intents") != 1
        or after_semantic_replay.get("outbox_intents") != 1
    ):
        _fail("IDEMPOTENCY_EVIDENCE_INVALID")

    product_cards = _sequence(projection_article.get("product_cards"))
    if product_cards:
        _fail("PRODUCT_ROWS_UNEXPECTED")
    structured_data = _mapping(projection_article.get("structured_data"))
    if structured_data:
        _fail("STRUCTURED_DATA_UNEXPECTED")

    fixture = {
        "schemaVersion": 2,
        "storyId": "ST-0906",
        "classification": "RECORDED_SYNTHETIC_PUBLICATION_REVIEW_WORKSPACE_V2",
        "profile": "ST0906_PUBLICATION_REVIEW_RECORDED_LOCAL_V2",
        "environment": "CI",
        "capturedAt": "2026-08-24T02:03:00Z",
        "bindings": _bindings(),
        "review": {
            "assignmentId": _text(review_assignment.get("assignment_id")),
            "assignmentState": "COMPLETED",
            "reviewDecisionId": _text(review_decision.get("decision_id")),
            "reviewDecision": _text(review_decision.get("decision")),
            "reviewDecidedAt": _text(review_decision.get("decided_at")),
            "checklistVersion": _text(review_decision.get("checklist_version")),
            "checklistSha256": _text(review_decision.get("checklist_sha256")),
            "checklistStatus": _text(review_decision.get("checklist_status")),
            "reviewAuditRecordId": _text(review_decision.get("audit_event_id")),
            "recordedSyntheticOnly": True,
            "finalApprovalAuthorizedByReview": False,
        },
        "finalApproval": {
            "state": "RECORDED_SYNTHETIC_APPROVED",
            "approvalId": _text(approval_value.get("approval_id")),
            "approvedAt": _text(approval_value.get("approved_at")),
            "auditRecordId": _text(approval_value.get("audit_event_id")),
            "articleVersionId": _text(approval_bindings.get("article_version_id")),
            "articleVersionNo": _integer(approval_bindings.get("article_version_no")),
            "articleBodySha256": _text(approval_bindings.get("article_body_sha256")),
            "canonicalAstSha256": _text(approval_bindings.get("canonical_ast_sha256")),
            "gateBundleSha256": _text(
                snapshot_value.get("input_hashes", {}).get(
                    "approval_gate_bundle_sha256"
                )
            ),
            "findingSnapshotSha256": _text(
                approval_bindings.get("policy_finding_snapshot_sha256")
            ),
            "openBlockingFindingIds": _sequence(
                approval_value.get("open_blocking_finding_ids")
            ),
            "actorKind": _text(approval_actor.get("subject_kind")),
            "actorStatus": _text(approval_actor.get("subject_status")),
            "actorRole": _text(approval_actor.get("role")),
            "mfaState": _text(approval_actor.get("mfa_state")),
            "stepUpState": _text(approval_actor.get("step_up_state")),
            "reauthenticatedAt": _text(approval_actor.get("reauthenticated_at")),
            "separationOfDutiesVerifiedRecorded": True,
            "realFinalApprovalAuthorized": False,
            "publicationAuthorized": False,
        },
        "snapshot": {
            "state": "IMMUTABLE_RECORDED_CANDIDATE",
            "publicationId": _text(snapshot_value.get("publication_id")),
            "publicationVersion": _integer(snapshot_value.get("publication_version")),
            "snapshotId": _text(snapshot.get("seed", {}).get("snapshot_artifact_id")),
            "snapshotSha256": _text(snapshot_result.get("snapshot_sha256")),
            "snapshotArtifactSha256": _text(
                snapshot_result.get("snapshot_artifact_sha256")
            ),
            "contentManifestSha256": _text(
                snapshot_result.get("content_manifest_sha256")
            ),
            "inputBundleSha256": _text(snapshot_result.get("input_bundle_sha256")),
            "sourcePacketSha256": _text(
                snapshot_value.get("input_hashes", {}).get(
                    "source_packet_content_sha256"
                )
            ),
            "immutable": snapshot_result.get("immutable") is True,
            "compatibility": _text(snapshot_result.get("compatibility")),
            "readiness": _text(snapshot_result.get("readiness")),
            "persisted": False,
            "publicationAuthorized": False,
        },
        "diff": {
            "fromLabel": "ST-0903 immutable Content AST candidate",
            "toLabel": "ST-0904 closed public projection",
            "fromSha256": _text(snapshot_result.get("snapshot_sha256")),
            "toSha256": _text(projection_result.get("projection_sha256")),
            "bindingIntegrity": "EXACT_RECORDED_BINDINGS_VERIFIED",
            "contentHashEquality": "NOT_ESTABLISHED_RECONCILIATION_REQUIRED",
            "rows": diff_rows,
        },
        "preview": {
            "state": "RECORDED_PUBLIC_READ_SHAPE_NO_ROUTE",
            "articleId": _text(projection_article.get("article_id")),
            "publicationId": _text(projection_article.get("publication_id")),
            "snapshotId": _text(projection_article.get("publication_snapshot_id")),
            "projectionGeneration": _integer(
                projection_article.get("projection_generation")
            ),
            "title": _text(projection_article.get("title")),
            "languageTag": _text(projection_article.get("language_tag")),
            "canonicalPath": _text(projection_article.get("canonical_path")),
            "isIndexable": projection_article.get("is_indexable") is True,
            "disclosureText": _text(projection_article.get("disclosure_text")),
            "freshnessStatus": _text(projection_article.get("freshness_status")),
            "metaDescription": _text(projection_article.get("meta_description")),
            "blocks": preview_blocks,
            "productCardCount": len(product_cards),
            "offerCount": _integer(
                _mapping(projection_value.get("row_counts")).get("public_offer")
            ),
            "routeHttpStatus": _integer(projection_route.get("http_status")),
            "routeActivated": False,
            "publicReadServed": False,
        },
        "auditTimeline": [
            {
                "sequence": 1,
                "kind": "FINAL_APPROVAL",
                "recordId": _text(approval_value.get("audit_event_id")),
                "occurredAt": _text(approval_value.get("approved_at")),
                "correlationId": None,
                "recordSha256": None,
                "state": "PROCESS_LOCAL_IMMUTABLE_REFERENCE_NOT_DURABLE",
                "persisted": False,
                "eventEmitted": False,
            },
            {
                "sequence": 2,
                "kind": "PUBLISH_RECORDED_INTENT",
                "recordId": publish_command["auditRecordId"],
                "occurredAt": "2026-08-24T02:00:00Z",
                "correlationId": publish_command["correlationId"],
                "recordSha256": publish_command["auditSha256"],
                "state": "PROCESS_LOCAL_NOT_PERSISTED_NOT_EMITTED",
                "persisted": False,
                "eventEmitted": False,
            },
            {
                "sequence": 3,
                "kind": "ROLLBACK_RECORDED_INTENT",
                "recordId": rollback_command["auditRecordId"],
                "occurredAt": "2026-08-24T02:02:00Z",
                "correlationId": rollback_command["correlationId"],
                "recordSha256": rollback_command["auditSha256"],
                "state": "PROCESS_LOCAL_NOT_PERSISTED_NOT_EMITTED",
                "persisted": False,
                "eventEmitted": False,
            },
        ],
        "commands": list(command_projection),
        "idempotencyEvidence": {
            "exactReplayByteIdentical": after_publish == after_exact_replay,
            "semanticDoublePublishNoDuplicateIntent": True,
            "afterPublishAuditIntentCount": _integer(
                after_publish.get("audit_intents")
            ),
            "afterPublishEventIntentCount": _integer(
                after_publish.get("event_intents")
            ),
            "afterPublishOutboxIntentCount": _integer(
                after_publish.get("outbox_intents")
            ),
            "afterSemanticReplayAuditIntentCount": _integer(
                after_semantic_replay.get("audit_intents")
            ),
            "afterSemanticReplayEventIntentCount": _integer(
                after_semantic_replay.get("event_intents")
            ),
            "afterSemanticReplayOutboxIntentCount": _integer(
                after_semantic_replay.get("outbox_intents")
            ),
            "afterRollbackGeneration": _integer(after_rollback.get("generation")),
            "afterRollbackState": _text(after_rollback.get("state")),
        },
        "commandBoundary": {
            "uiDispatch": "DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE",
            "onlyFutureAdapter": "python.raos.adapters.publishing.recorded_publication_commands_v2",
            "onlyFutureProfile": "ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2",
            "allowedEnvironments": ["ENV-DEV", "CI"],
            "activeHumanRequired": True,
            "allowedRoles": ["MANAGING_EDITOR", "OPERATOR"],
            "mfaRequired": True,
            "stepUpRequired": True,
            "siteScopeRequired": True,
            "serverReauthorizationRequired": True,
            "finalApprovalRequired": True,
            "separationOfDutiesPublishRequired": True,
            "exactSnapshotRequired": True,
            "exactSourceBindingRequired": True,
            "killSwitchSafeStateRequired": True,
            "reasonRequired": True,
            "idempotencyRequired": True,
            "auditRequired": True,
            "publishEnabled": False,
            "rollbackEnabled": False,
            "unpublishEnabled": False,
        },
        "route": {
            "registered": False,
            "routable": False,
            "renderEnabled": False,
            "navigationEligible": False,
            "status": "DISABLED_AUTH_TRANSPORT_UNRESOLVED_OD_010",
        },
        "authority": {
            "authenticationEstablished": False,
            "authorizationGranted": False,
            "stepUpEstablished": False,
            "backendReauthorizationRequired": True,
            "dataFetchEnabled": False,
            "mutationEnabled": False,
            "networkEnabled": False,
            "persistenceEnabled": False,
            "databaseWriteEnabled": False,
            "cmsWriteEnabled": False,
            "eventEmissionEnabled": False,
            "outboxWriteEnabled": False,
            "publicStateChangeEnabled": False,
            "publicationAuthorized": False,
            "rollbackAuthorized": False,
            "releaseAuthorized": False,
            "productionAuthorized": False,
        },
        "verification": {
            "TST_022": "NOT_EXECUTED",
            "TST_024": "NOT_EXECUTED",
            "browser": "NOT_EXECUTED",
            "screenReader": "NOT_EXECUTED",
            "authentication": "NOT_EXECUTED",
            "authorization": "NOT_EXECUTED",
            "stepUp": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
        "rawPayloadPresent": False,
        "financeDataPresent": False,
        "credentialDataPresent": False,
    }
    return fixture


def _typescript_wrapper(fixture_bytes: bytes) -> bytes:
    fixture_text = fixture_bytes.decode("ascii").rstrip("\n")
    digest = _sha_bytes(fixture_bytes)
    literal = "'" + fixture_text.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return (
        "/* Generated by scripts/build_st0906_publication_review_workspace_v2.py. */\n"
        "/* Do not edit by hand. */\n"
        "export const ST0906_RECORDED_WORKSPACE_V2_SHA256 =\n"
        f"  '{digest}' as const;\n"
        "export const ST0906_RECORDED_WORKSPACE_V2_JSON =\n"
        f"  {literal} as const;\n"
    ).encode("ascii")


def _media_type(path: Path) -> str:
    suffix = path.suffix
    if suffix == ".json":
        return "application/json"
    if suffix in {".yaml", ".yml"}:
        return "application/yaml"
    if suffix == ".py":
        return "text/x-python"
    if suffix == ".ts":
        return "text/typescript"
    if suffix == ".md":
        return "text/markdown"
    return "application/octet-stream"


def _artifact(root: Path, path: Path, role: str) -> dict[str, object]:
    payload = _read(root, path)
    return {
        "uri": f"repo://{path.as_posix()}",
        "artifact_role": role,
        "media_type": _media_type(path),
        "bytes": len(payload),
        "sha256": _sha_bytes(payload),
    }


def _manifest_bytes(root: Path, fixture_bytes: bytes, wrapper_bytes: bytes) -> bytes:
    sources = [_artifact(root, path, "OWNER_SOURCE") for path in OWNED_SOURCE_PATHS]
    sources.extend(
        _artifact(root, path, "CANONICAL_OR_DEPENDENCY_INPUT")
        for path, _digest, _name in (*CANONICAL_BINDINGS, *DEPENDENCY_BINDINGS)
    )
    sources.extend(
        _artifact(root, path, "LOCKED_TOOLCHAIN") for path in LOCKED_TOOLCHAIN_PATHS
    )
    manifest = {
        "schema_version": 2,
        "story_id": "ST-0906",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_PUBLICATION_REVIEW_WORKSPACE_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": 2,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "artifact_role": "GENERATED_RECORDED_WORKSPACE_FIXTURE",
                "media_type": "application/json",
                "bytes": len(fixture_bytes),
                "sha256": _sha_bytes(fixture_bytes),
            },
            {
                "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
                "artifact_role": "GENERATED_TYPESCRIPT_FIXTURE_WRAPPER",
                "media_type": "text/typescript",
                "bytes": len(wrapper_bytes),
                "sha256": _sha_bytes(wrapper_bytes),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python "
                "scripts/build_st0906_publication_review_workspace_v2.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0906_publication_review_workspace_v2.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "secure_publication_helper_sha256": SECURE_HELPER_SHA256,
        },
        "authority": {
            "route_authorized": False,
            "command_dispatch_authorized": False,
            "database_write_authorized": False,
            "cms_write_authorized": False,
            "event_emission_authorized": False,
            "public_state_change_authorized": False,
            "publication_authorized": False,
            "rollback_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
        },
        "verification": {
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "browser": "NOT_EXECUTED",
            "screen_reader": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(
        manifest,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    ).encode("ascii")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    """Return owner-derived relative outputs in commit order."""

    _validate_toolchain()
    _load_contract(root)
    fixture_bytes = _canonical_bytes(_build_fixture(root))
    if len(fixture_bytes) > MAX_GENERATED_BYTES:
        _fail("GENERATED_FIXTURE_TOO_LARGE")
    wrapper_bytes = _typescript_wrapper(fixture_bytes)
    manifest_bytes = _manifest_bytes(root, fixture_bytes, wrapper_bytes)
    if max(map(len, (wrapper_bytes, manifest_bytes))) > MAX_GENERATED_BYTES:
        _fail("GENERATED_ARTIFACT_TOO_LARGE")
    return (
        (FIXTURE_PATH, fixture_bytes),
        (GENERATED_TS_PATH, wrapper_bytes),
        (MANIFEST_PATH, manifest_bytes),
    )


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, expected in artifacts:
            try:
                observed = _read(root, relative, maximum=MAX_GENERATED_BYTES)
            except PublicationReviewGenerationError:
                _fail("GENERATED_ARTIFACT_MISSING_OR_INVALID")
            if observed != expected:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    secure_generated_publication.publish_generated(
        tuple(
            ((root / relative).resolve(), payload) for relative, payload in artifacts
        ),
        namespace="st0906-v2",
        maximum_payload_bytes=MAX_GENERATED_BYTES,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic ST-0906 V2 workspace fixture."
    )
    parser.add_argument("--check", action="store_true")
    try:
        arguments = parser.parse_args(argv)
        build(REPO_ROOT, check=arguments.check)
    except (
        PublicationReviewGenerationError,
        secure_generated_publication.SecurePublicationError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
