#!/usr/bin/env python3
"""Build the deterministic recorded ST-1102 article workspace projection."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for search_path in (REPO_ROOT, PYTHON_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.recorded_ai_draft_integration_v2 import (  # noqa: E402
    load_recorded_ai_draft_fixture_v2,
)
from raos.domain.editorial.ai_draft_integration_v2 import (  # noqa: E402
    BoundContentAstV2,
    DraftCoverageDecisionV2,
    build_content_ast_diff_v2,
    bind_coverage_v2,
)
from raos.domain.editorial.content_ast import (  # noqa: E402
    load_content_ast,
)
from raos.domain.evidence.claim_evidence import CoverageStatus  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"

CONTRACT_PATH: Final = Path("changes/st-1102/contracts/article-workspace.v2.yaml")
FIXTURE_PATH: Final = Path("changes/st-1102/article-workspace-recorded.v2.json")
GENERATED_TS_PATH: Final = Path("packages/web-ui/src/article-workspace-recorded.v2.ts")
MANIFEST_PATH: Final = Path("changes/st-1102/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1102_article_workspace_v2.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "ed5d7725e764f2ff0da5342b0dde28d347ba53dfd5066d34b6ea8465526ce52f"
)

ST0806_PLAN_PATH: Final = Path("changes/st-0806/generated/ai-draft-integration.v2.json")
ST0806_FIXTURE_PATH: Final = Path(
    "changes/st-0806/generated/ai-draft-integration-fixture.v2.json"
)
CONTENT_FIXTURE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
)
ST0806_FIXTURE_SHA256: Final = (
    "656e434ab1b8c6b7af3a0c4bc75dcd880ef487744a50bc870ca0ab70ad9361c6"
)
ST0806_PLAN_SHA256: Final = (
    "d2f81925a2abd77177de3f8233286e521f158081bd421e7d1d9529631873a4d9"
)

ARTICLE_ID: Final = "018f3e90-7b00-7000-8000-000000000806"
ARTICLE_VERSION_ID: Final = "018f3e90-7b00-7000-8000-000000000807"
SOURCE_PACKET_VERSION_ID: Final = "018f3e90-7b00-7000-8000-000000000808"
ARTICLE_TITLE: Final = "Synthetic AI draft integration article V2"
EVALUATED_AT: Final = "2026-08-24T02:00:00Z"

SCREEN_ORDER: Final = (
    "EDT-002",
    "EDT-003",
    "EDT-005",
    "EDT-006",
    "EDT-007",
    "EDT-009",
)
PROJECTION_ORDER: Final = ("AST", "AI_DIFF", "CLAIMS", "COMPARISON", "SEO")

GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file "
    "--no-python-downloads python scripts/build_st1102_article_workspace_v2.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
MAX_CONTRACT_BYTES: Final = 262_144
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

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
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        "securityCatalog",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"),
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
        "roleMatrix",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
        "testDesign",
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
    (
        Path("contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml"),
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
        "adminOpenApi",
    ),
    (
        Path("contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json"),
        "a9e9f927d1646bb56f5124c70e5cc8a34e5e3b0de57d4fd1ac6633da1cfb2bac",
        "contentAstSchema",
    ),
)

DEPENDENCY_BINDINGS: Final = (
    (
        Path("changes/st-0806/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
        "55347f6ce7d85dfc2b92ebeb41e8c51bfbb4ee83398a490e7022946b634d1556",
        "st0806Completion",
    ),
    (ST0806_PLAN_PATH, ST0806_PLAN_SHA256, "st0806Plan"),
    (ST0806_FIXTURE_PATH, ST0806_FIXTURE_SHA256, "st0806Fixture"),
    (
        Path("changes/st-0806/contracts/ai-draft-integration.v2.yaml"),
        "42715fc526bcb4eddccbd836084769f7ef8886b7767ad806f33accdff4843bdd",
        "st0806Contract",
    ),
    (
        Path("python/raos/domain/editorial/ai_draft_integration_v2.py"),
        "a033b7baac023179ea5cd245f399986e9969f2f1c611d6f4faf7cf98363e81b7",
        "st0806Domain",
    ),
    (
        Path("python/raos/adapters/recorded_ai_draft_integration_v2.py"),
        "5f43a7e69eb6430ba2fa190635d0e4d1bc16e01f66e3b3043625277ffedda85c",
        "st0806Adapter",
    ),
    (
        CONTENT_FIXTURE_PATH,
        "8467c824215c548479f1ccba5877797910c3a4abec736af37627605059422489",
        "st0806BeforeAstFixture",
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
        Path("packages/web-ui/src/data-table.ts"),
        "bb999786019d1c01ece36929124359af00c5362134c4ee4faf50ce496d3689f4",
        "st1101DataTable",
    ),
    (
        Path("packages/web-ui/src/dialog.ts"),
        "494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc",
        "st1101Dialog",
    ),
    (
        Path("packages/web-ui/src/article-workspace.ts"),
        "01d2f680ddfb5a64fa9d84db1c10e1ae9cd3de490520e67f135f3be63260db89",
        "st1102HistoricalV1",
    ),
    (SECURE_HELPER_PATH, SECURE_HELPER_SHA256, "securePublicationHelper"),
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("packages/web-ui/src/article-workspace-v2.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("changes/st-1102/README.md"),
    Path("changes/st-1102/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-1102.md"),
    Path("docs/worklogs/ST-1102.md"),
    Path("tests/st1102/article-workspace-v2-model.test.ts"),
    Path("tests/st1102/article-workspace-v2-concurrency.test.ts"),
    Path("tests/st1102/article-workspace-v2-accessibility.test.ts"),
    Path("tests/st1102/article-workspace-v2-negative.test.ts"),
    Path("tests/st1102/article-workspace-v2-generation.test.ts"),
    Path("tests/st1102/test_generation_v2.py"),
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


class ArticleWorkspaceBuildError(RuntimeError):
    __slots__ = ("code", "field")

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise ArticleWorkspaceBuildError(code, field) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
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
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _check_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
    ):
        _fail("PYTHON_TOOLCHAIN_MISMATCH", "toolchain")
    try:
        yaml_version = distribution_version("PyYAML")
    except PackageNotFoundError:
        _fail("PYYAML_UNAVAILABLE", "toolchain")
    if yaml_version != EXPECTED_PYYAML_VERSION:
        _fail("PYYAML_VERSION_MISMATCH", "toolchain")


def _read(root: Path, relative: Path, field: str) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_PATH", field)
    path = root / relative
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE", field)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or len(value) > MAX_SOURCE_BYTES
    ):
        _fail("SOURCE_INVALID", field)
    return value


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            _fail("JSON_DUPLICATE_KEY", "recorded_fixture")
        value[key] = item
    return value


def _load_json_bytes(payload: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_json_pairs)
    except ArticleWorkspaceBuildError:
        raise
    except Exception:
        _fail("JSON_PARSE_FAILED", field)
    if type(value) is not dict:
        _fail("JSON_SHAPE_INVALID", field)
    return cast(dict[str, Any], value)


def _load_contract(root: Path) -> dict[str, Any]:
    raw = _read(root, CONTRACT_PATH, "contract")
    if (
        not raw
        or len(raw) > MAX_CONTRACT_BYTES
        or _sha256(raw) != EXPECTED_CONTRACT_SHA256
    ):
        _fail("CONTRACT_HASH_DRIFT", "contract")
    try:
        text = raw.decode("utf-8", errors="strict")
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in yaml.scan(text)
        ):
            _fail("CONTRACT_YAML_FEATURE_FORBIDDEN", "contract")
        loaded = yaml.load(text, Loader=_UniqueLoader)
    except ArticleWorkspaceBuildError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED", "contract")
    expected_keys = {
        "schema_version",
        "story_id",
        "local_status",
        "classification",
        "enabled_by_default",
        "authority",
        "production_eligible",
        "publication_authorized",
        "screen_order",
        "dependency_boundary",
        "projection_boundary",
        "concurrency_boundary",
        "unsaved_guard_boundary",
        "accessibility_boundary",
        "security_controls",
        "prohibited_surfaces",
        "authority_boundary",
        "verification_boundary",
    }
    if type(loaded) is not dict or set(loaded) != expected_keys:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    contract = cast(dict[str, Any], loaded)
    if (
        contract["schema_version"] != 2
        or contract["story_id"] != "ST-1102"
        or contract["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or contract["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_ARTICLE_WORKSPACE_V2"
        or contract["enabled_by_default"] is not False
        or contract["authority"] != "NONE"
        or contract["production_eligible"] is not False
        or contract["publication_authorized"] is not False
        or contract["screen_order"] != list(SCREEN_ORDER)
    ):
        _fail("CONTRACT_POLICY_DRIFT", "contract")
    authority = contract["authority_boundary"]
    if type(authority) is not dict or any(
        value is not False for value in authority.values()
    ):
        _fail("CONTRACT_AUTHORITY_DRIFT", "contract")
    verification = contract["verification_boundary"]
    if (
        type(verification) is not dict
        or verification.get("TST-022") != "NOT_EXECUTED"
        or verification.get("TST-024") != "NOT_EXECUTED"
        or verification.get("production") != "NOT_EXECUTED"
    ):
        _fail("CONTRACT_VERIFICATION_DRIFT", "contract")
    return contract


def _verify_bindings(root: Path) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {"canonical": {}, "dependencies": {}}
    for group, bindings in (
        ("canonical", CANONICAL_BINDINGS),
        ("dependencies", DEPENDENCY_BINDINGS),
    ):
        for path, expected, name in bindings:
            observed = _sha256(_read(root, path, f"binding.{name}"))
            if observed != expected:
                _fail("SOURCE_BINDING_DRIFT", f"binding.{name}")
            output[group][name] = observed
    if (
        _sha256(_read(root, SECURE_HELPER_PATH, "hardened_writer"))
        != SECURE_HELPER_SHA256
    ):
        _fail("HARDENED_WRITER_HASH_MISMATCH", "hardened_writer")
    return output


def _reconstruct_before_ast(root: Path) -> BoundContentAstV2:
    payload = _load_json_bytes(
        _read(root, CONTENT_FIXTURE_PATH, "before_ast"), "before_ast"
    )
    payload["article_id"] = ARTICLE_ID
    payload["article_version_id"] = ARTICLE_VERSION_ID
    payload["source_packet_version_ref"] = SOURCE_PACKET_VERSION_ID
    payload["title"] = ARTICLE_TITLE
    try:
        content = load_content_ast(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return BoundContentAstV2.from_content_ast(content)
    except Exception:
        _fail("BEFORE_AST_INVALID", "before_ast")


def _strict_list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    return value


def _strict_mapping(value: object, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    return cast(dict[str, Any], value)


def _strict_string(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    return value


def _strict_document_string(value: object, field: str) -> str:
    if type(value) is not str or not value:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    return value


def _string_list(value: object, field: str) -> list[str]:
    items = _strict_list(value, field)
    if any(type(item) is not str for item in items):
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", field)
    return cast(list[str], items)


def _block_projection(block: Mapping[str, object]) -> dict[str, object]:
    block_id = _strict_string(block.get("block_id"), "ast.block_id")
    block_type = _strict_string(block.get("type"), "ast.block_type")
    claim_ids = _string_list(block.get("claim_ids", []), "ast.claim_ids")
    rationale_claim_ids = _string_list(
        block.get("rationale_claim_ids", []), "ast.rationale_claim_ids"
    )
    axis_refs = _string_list(
        block.get("comparison_axis_refs", []), "ast.comparison_axis_refs"
    )
    product_refs = _string_list(
        block.get("product_selection_refs", []), "ast.product_selection_refs"
    )
    recommendation_refs = _string_list(
        block.get("recommendation_refs", []), "ast.recommendation_refs"
    )
    show_unknown = block.get("show_unknown_values")
    if show_unknown is not None and type(show_unknown) is not bool:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", "ast.show_unknown_values")
    display_mode = block.get("display_mode")
    if display_mode is not None and type(display_mode) is not str:
        _fail("RECORDED_FIXTURE_SHAPE_INVALID", "ast.display_mode")
    return {
        "blockId": block_id,
        "type": block_type,
        "claimIds": claim_ids,
        "rationaleClaimIds": rationale_claim_ids,
        "comparisonAxisRefs": axis_refs,
        "productSelectionRefs": product_refs,
        "recommendationRefs": recommendation_refs,
        "showUnknownValues": show_unknown,
        "displayMode": display_mode,
    }


def _ast_projection(bound: BoundContentAstV2) -> dict[str, object]:
    value = _load_json_bytes(bound.canonical_bytes, "content_ast")
    blocks = _strict_list(value.get("blocks"), "content_ast.blocks")
    projected = [
        _block_projection(_strict_mapping(block, "content_ast.block"))
        for block in blocks
    ]
    return {
        "sha256": bound.sha256,
        "schemaVersion": _strict_string(
            value.get("schema_version"), "ast.schema_version"
        ),
        "locale": _strict_string(value.get("locale"), "ast.locale"),
        "articleType": _strict_string(value.get("article_type"), "ast.article_type"),
        "blockCount": len(projected),
        "blocks": projected,
    }


def _claims_projection(snapshot_value: Mapping[str, object]) -> dict[str, object]:
    claims = _strict_list(snapshot_value.get("claims"), "claims")
    links = _strict_list(snapshot_value.get("links"), "links")
    facts = _strict_list(snapshot_value.get("facts"), "facts")
    snapshots = _strict_list(snapshot_value.get("snapshots"), "snapshots")
    identities = _strict_list(snapshot_value.get("identities"), "identities")
    conflicts = _strict_list(snapshot_value.get("conflicts"), "conflicts")

    fact_by_id = {
        _strict_string(
            _strict_mapping(item, "facts.item").get("fact_id"), "facts.fact_id"
        ): _strict_mapping(item, "facts.item")
        for item in facts
    }
    snapshot_by_id = {
        _strict_string(
            _strict_mapping(item, "snapshots.item").get("source_snapshot_id"),
            "snapshots.source_snapshot_id",
        ): _strict_mapping(item, "snapshots.item")
        for item in snapshots
    }
    identity_by_fact = {
        _strict_string(
            _strict_mapping(item, "identities.item").get("fact_id"),
            "identities.fact_id",
        ): _strict_mapping(item, "identities.item")
        for item in identities
    }

    rows: list[dict[str, object]] = []
    for raw_claim in claims:
        claim = _strict_mapping(raw_claim, "claims.item")
        claim_id = _strict_string(claim.get("claim_id"), "claims.claim_id")
        linked_fact_ids = sorted(
            _strict_string(
                _strict_mapping(link, "links.item").get("fact_id"), "links.fact_id"
            )
            for link in links
            if _strict_mapping(link, "links.item").get("claim_id") == claim_id
        )
        source_rows: list[dict[str, object]] = []
        identity_statuses: list[str] = []
        for fact_id in linked_fact_ids:
            fact = fact_by_id.get(fact_id)
            if fact is None:
                _fail("RECORDED_FIXTURE_SHAPE_INVALID", "claims.fact_binding")
            snapshot_id = _strict_string(
                fact.get("source_snapshot_id"), "claims.source_snapshot_id"
            )
            source = snapshot_by_id.get(snapshot_id)
            identity = identity_by_fact.get(fact_id)
            if source is None or identity is None:
                _fail("RECORDED_FIXTURE_SHAPE_INVALID", "claims.evidence_binding")
            source_rows.append(
                {
                    "sourceSnapshotId": snapshot_id,
                    "acquiredAt": _strict_string(
                        source.get("acquired_at"), "source.acquired_at"
                    ),
                    "expiresAt": _strict_string(
                        source.get("expires_at"), "source.expires_at"
                    ),
                    "validationStatus": _strict_string(
                        source.get("validation_status"), "source.validation_status"
                    ),
                }
            )
            identity_statuses.append(
                _strict_string(identity.get("status"), "identity.status")
            )
        conflict_count = sum(
            1
            for item in conflicts
            if claim_id
            in {
                value
                for value in _strict_mapping(item, "conflicts.item").values()
                if type(value) is str
            }
        )
        criticality = claim.get("criticality")
        affects_purchase = claim.get("affects_purchase_decision")
        if type(criticality) is not int or type(affects_purchase) is not bool:
            _fail("RECORDED_FIXTURE_SHAPE_INVALID", "claims.classification")
        rows.append(
            {
                "claimId": claim_id,
                "claimType": _strict_string(
                    claim.get("claim_type"), "claims.claim_type"
                ),
                "criticality": criticality,
                "affectsPurchaseDecision": affects_purchase,
                "evidenceFactIds": linked_fact_ids,
                "sources": source_rows,
                "identityStatuses": sorted(identity_statuses),
                "conflictCount": conflict_count,
                "coverage": "EVIDENCED" if linked_fact_ids else "UNKNOWN",
            }
        )
    return {
        "caption": "Recorded synthetic Claim and Evidence coverage",
        "columns": [
            {"id": "claim", "label": "Claim ID", "scope": "col"},
            {"id": "criticality", "label": "Criticality", "scope": "col"},
            {"id": "evidence", "label": "Evidence", "scope": "col"},
            {"id": "freshness", "label": "Freshness", "scope": "col"},
            {"id": "conflict", "label": "Conflict", "scope": "col"},
        ],
        "rowHeaderColumn": "claim",
        "rows": rows,
        "claimTextPresent": False,
    }


def _comparison_projection(after_value: Mapping[str, object]) -> dict[str, object]:
    blocks = [
        _strict_mapping(item, "comparison.block")
        for item in _strict_list(after_value.get("blocks"), "comparison.blocks")
    ]
    comparison_blocks = [
        item for item in blocks if item.get("type") == "comparison_table"
    ]
    recommendation_blocks = [
        item for item in blocks if item.get("type") == "recommendation_group"
    ]
    if len(comparison_blocks) != 1 or not recommendation_blocks:
        _fail("COMPARISON_PROJECTION_INVALID", "comparison")
    table = comparison_blocks[0]
    show_unknown = table.get("show_unknown_values")
    strict_order_values = [item.get("strict_order") for item in recommendation_blocks]
    if show_unknown is not True or any(
        type(value) is not bool for value in strict_order_values
    ):
        _fail("COMPARISON_PROJECTION_INVALID", "comparison")
    return {
        "comparisonTableRef": _strict_string(
            table.get("comparison_table_ref"), "comparison.comparison_table_ref"
        ),
        "axisRefs": _string_list(
            table.get("comparison_axis_refs"), "comparison.comparison_axis_refs"
        ),
        "productSelectionRefs": _string_list(
            table.get("product_selection_refs"), "comparison.product_selection_refs"
        ),
        "displayMode": _strict_string(
            table.get("display_mode"), "comparison.display_mode"
        ),
        "showUnknownValues": True,
        "recommendationGroups": [
            {
                "groupId": _strict_string(item.get("group_id"), "comparison.group_id"),
                "recommendationRefs": _string_list(
                    item.get("recommendation_refs"), "comparison.recommendation_refs"
                ),
                "rationaleClaimIds": _string_list(
                    item.get("rationale_claim_ids"), "comparison.rationale_claim_ids"
                ),
                "strictOrder": cast(bool, item.get("strict_order")),
            }
            for item in recommendation_blocks
        ],
        "financeOrAffiliateEconomicsPresent": False,
        "recommendationOrderMutationAuthorized": False,
    }


def _projection(
    *,
    status: str,
    source_story_ids: list[str],
    component_ids: list[str],
    payload: object,
) -> dict[str, object]:
    return {
        "status": status,
        "sourceStoryIds": source_story_ids,
        "componentIds": component_ids,
        "payload": payload,
        "statusCue": {
            "code": status,
            "text": status.replace("_", " ").title(),
            "icon": "circle-check"
            if status == "AVAILABLE_RECORDED"
            else "circle-alert",
            "colorOnly": False,
        },
    }


def _recorded_projection(root: Path) -> dict[str, object]:
    plan_bytes = _read(root, ST0806_PLAN_PATH, "st0806.plan")
    fixture_bytes = _read(root, ST0806_FIXTURE_PATH, "st0806.fixture")
    if (
        _sha256(plan_bytes) != ST0806_PLAN_SHA256
        or _sha256(fixture_bytes) != ST0806_FIXTURE_SHA256
    ):
        _fail("ST0806_ARTIFACT_DRIFT", "st0806")
    plan = _load_json_bytes(plan_bytes, "st0806.plan")
    if (
        plan.get("story_id") != "ST-0806"
        or plan.get("status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or plan.get("enabled") is not False
        or plan.get("authority") != "NONE"
        or plan.get("generated_fixture_sha256") != ST0806_FIXTURE_SHA256
    ):
        _fail("ST0806_PLAN_INVALID", "st0806.plan")
    try:
        material = load_recorded_ai_draft_fixture_v2(fixture_bytes)
    except Exception:
        _fail("ST0806_FIXTURE_INVALID", "st0806.fixture")
    before = _reconstruct_before_ast(root)
    after = material.after_ast
    diff = build_content_ast_diff_v2(before, after)
    decision, coverage_status, coverage, report_sha256, receipt_sequence = (
        bind_coverage_v2(
            material=material,
            after_ast=after,
        )
    )
    if (
        decision is not DraftCoverageDecisionV2.AVAILABLE
        or coverage_status is not CoverageStatus.PASS
        or coverage is None
        or report_sha256 is None
        or receipt_sequence is None
        or not diff.changed
    ):
        _fail("ST0806_PROPOSAL_NOT_AVAILABLE", "st0806.fixture")

    raw_fixture = _load_json_bytes(fixture_bytes, "st0806.fixture")
    after_value = _load_json_bytes(after.canonical_bytes, "st0806.after_ast")
    snapshot_text = _strict_document_string(
        raw_fixture.get("claim_evidence_snapshot_utf8"), "st0806.claim_snapshot"
    )
    snapshot_value = _load_json_bytes(
        snapshot_text.encode("utf-8", errors="strict"), "st0806.claim_snapshot"
    )
    if (
        after_value.get("article_id") != ARTICLE_ID
        or after_value.get("article_version_id") != ARTICLE_VERSION_ID
        or after_value.get("source_packet_version_ref") != SOURCE_PACKET_VERSION_ID
        or after_value.get("title") != ARTICLE_TITLE
    ):
        _fail("ST0806_ARTICLE_BINDING_INVALID", "st0806.after_ast")

    baseline_etag = f'"sha256:{before.sha256}"'
    projections = {
        "AST": _projection(
            status="AVAILABLE_RECORDED",
            source_story_ids=["ST-0806"],
            component_ids=["UI-C022"],
            payload={
                "active": _ast_projection(before),
                "proposed": _ast_projection(after),
                "proposalApplied": False,
                "humanEditable": True,
            },
        ),
        "AI_DIFF": _projection(
            status="AVAILABLE_RECORDED",
            source_story_ids=["ST-0806"],
            component_ids=["UI-C015"],
            payload={
                "beforeAstSha256": before.sha256,
                "afterAstSha256": after.sha256,
                "diffSha256": diff.diff_sha256,
                "operations": [
                    {
                        "ordinal": item.ordinal,
                        "kind": item.kind.value,
                        "jsonPointer": item.json_pointer,
                        "beforeValueSha256": item.before_value_sha256,
                        "afterValueSha256": item.after_value_sha256,
                    }
                    for item in diff.operations
                ],
                "valuesExposed": False,
                "adoptionAuthorized": False,
                "adoptionPerformed": False,
            },
        ),
        "CLAIMS": _projection(
            status="AVAILABLE_RECORDED",
            source_story_ids=["ST-0806", "ST-0605"],
            component_ids=["UI-C021"],
            payload={
                **_claims_projection(snapshot_value),
                "coverage": {
                    "status": coverage_status.value,
                    "reportSha256": report_sha256,
                    "receiptSequence": receipt_sequence,
                    "bindingSha256": coverage.binding_sha256,
                    "major": {
                        "evidenced": coverage.major_evidenced,
                        "total": coverage.major_total,
                    },
                    "allVerifiable": {
                        "evidenced": coverage.all_verifiable_evidenced,
                        "total": coverage.all_verifiable_total,
                    },
                },
            },
        ),
        "COMPARISON": _projection(
            status="AVAILABLE_RECORDED",
            source_story_ids=["ST-0806"],
            component_ids=["UI-C023", "UI-C036"],
            payload=_comparison_projection(after_value),
        ),
        "SEO": _projection(
            status="PARTIAL_RECORDED",
            source_story_ids=["ST-0806"],
            component_ids=[],
            payload={
                "title": ARTICLE_TITLE,
                "titleSource": "TYPED_AST",
                "seoMetadataRef": _strict_string(
                    after_value.get("seo_metadata_ref"), "seo.seo_metadata_ref"
                ),
                "canonical": None,
                "robots": None,
                "jsonLd": None,
                "resolvedMetadataStatus": "UNAVAILABLE_DEPENDENCY",
                "missingOwner": "ST-0807_NOT_DECLARED_DEPENDENCY",
            },
        ),
    }
    if tuple(projections) != PROJECTION_ORDER:
        _fail("PROJECTION_ORDER_INVALID", "projection")
    return {
        "article": {
            "articleId": ARTICLE_ID,
            "versionId": ARTICLE_VERSION_ID,
            "sourcePacketVersionId": SOURCE_PACKET_VERSION_ID,
            "articleType": _strict_string(
                after_value.get("article_type"), "article.type"
            ),
            "title": ARTICLE_TITLE,
            "versionState": "DRAFT",
            "baselineAstSha256": before.sha256,
            "proposalAstSha256": after.sha256,
            "recordedEtag": baseline_etag,
            "proposalDisposition": "HUMAN_EDITABLE_PROPOSAL_ONLY",
            "proposalApplied": False,
            "publicationAuthorized": False,
        },
        "header": {
            "article": {"status": "AVAILABLE_RECORDED", "value": ARTICLE_ID},
            "version": {"status": "AVAILABLE_RECORDED", "value": ARTICLE_VERSION_ID},
            "state": {"status": "AVAILABLE_RECORDED", "value": "DRAFT"},
            "owner": {"status": "UNAVAILABLE_DEPENDENCY", "value": None},
            "quality": {"status": "AVAILABLE_RECORDED", "value": coverage_status.value},
            "freshness": {"status": "UNAVAILABLE_DEPENDENCY", "value": None},
            "etag": {"status": "AVAILABLE_RECORDED", "value": baseline_etag},
        },
        "projections": projections,
    }


def _fixture_bytes(
    contract: Mapping[str, object],
    bindings: Mapping[str, object],
    recorded: Mapping[str, object],
) -> bytes:
    value = {
        "schemaVersion": 2,
        "storyId": "ST-1102",
        "classification": "LOCAL_EXECUTABLE_RECORDED_ARTICLE_WORKSPACE_V2",
        "localStatus": "LOCAL_IMPLEMENTATION_COMPLETE",
        "canonicalStatus": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
        "evaluatedAt": EVALUATED_AT,
        "screenOrder": list(SCREEN_ORDER),
        "bindings": bindings,
        **dict(recorded),
        "security": {
            "controls": contract["security_controls"],
            "prohibitedSurfaces": contract["prohibited_surfaces"],
            "rawPromptPresent": False,
            "rawSourcePresent": False,
            "reviewBodyPresent": False,
            "rawHtmlPresent": False,
            "arbitraryUrlPresent": False,
            "financeOrAffiliateEconomicsPresent": False,
            "credentialPresent": False,
            "personalDataPresent": False,
            "publicProjectionPresent": False,
        },
        "authority": contract["authority_boundary"],
        "verification": contract["verification_boundary"],
    }
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8", errors="strict")


def _generated_ts_bytes(fixture: bytes) -> bytes:
    encoded = json.dumps(fixture.decode("utf-8", errors="strict"), ensure_ascii=True)
    return (
        "// Generated by scripts/build_st1102_article_workspace_v2.py.\n"
        "// Do not edit by hand.\n"
        "export const ST1102_RECORDED_WORKSPACE_V2_SHA256 =\n"
        f"  '{_sha256(fixture)}' as const;\n"
        "// prettier-ignore\n"
        f"export const ST1102_RECORDED_WORKSPACE_V2_JSON = {encoded} as const;\n"
    ).encode("utf-8")


def _source_hashes(root: Path) -> dict[str, str]:
    if len(SOURCE_PATHS) != len(set(SOURCE_PATHS)):
        _fail("SOURCE_INVENTORY_DUPLICATE", "source")
    return {
        path.as_posix(): _sha256(_read(root, path, "source")) for path in SOURCE_PATHS
    }


def _manifest_bytes(
    source_hashes: Mapping[str, str], fixture: bytes, generated_ts: bytes
) -> bytes:
    value = {
        "document": {
            "id": "RAOS-ST1102-ARTICLE-WORKSPACE-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-1102",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "authority": "NONE",
            "production_eligible": False,
        },
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "hardened_writer_sha256": SECURE_HELPER_SHA256,
        "source_sha256": dict(source_hashes),
        "generated_sha256": {
            FIXTURE_PATH.as_posix(): _sha256(fixture),
            GENERATED_TS_PATH.as_posix(): _sha256(generated_ts),
        },
        "generation": {"command": GENERATION_COMMAND, "check_command": CHECK_COMMAND},
        "bounds": {
            "mode": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
            "routes_registered": False,
            "rendering": False,
            "authentication": False,
            "authorization": False,
            "mutation": False,
            "navigation_effect": False,
            "dispatch": False,
            "persistence": False,
            "provider": False,
            "network": False,
            "publication": False,
            "release": False,
            "production": False,
        },
        "formal_TST_022": "NOT_EXECUTED",
        "formal_TST_024": "NOT_EXECUTED",
    }
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8", errors="strict")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    _check_toolchain()
    contract = _load_contract(root)
    bindings = _verify_bindings(root)
    recorded = _recorded_projection(root)
    fixture = _fixture_bytes(contract, bindings, recorded)
    generated_ts = _generated_ts_bytes(fixture)
    sources = _source_hashes(root)
    return {
        FIXTURE_PATH: fixture,
        GENERATED_TS_PATH: generated_ts,
        MANIFEST_PATH: _manifest_bytes(sources, fixture, generated_ts),
    }


def _output(root: Path, relative: Path, *, create_parent: bool) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_OUTPUT_PATH", "output")
    parent = root / relative.parent
    try:
        if create_parent and not parent.exists():
            parent.mkdir(mode=0o755)
        metadata = parent.lstat()
    except OSError:
        _fail("OUTPUT_PARENT_INVALID", "output")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("OUTPUT_PARENT_INVALID", "output")
    destination = parent / relative.name
    if not destination.is_absolute():
        _fail("UNSAFE_OUTPUT_PATH", "output")
    return destination


def _replace_generated(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    helper_origin = Path(secure_generated_publication.__file__).resolve(strict=True)
    expected_origin = (root / SECURE_HELPER_PATH).resolve(strict=True)
    if helper_origin != expected_origin:
        _fail("HARDENED_WRITER_ORIGIN_MISMATCH", "hardened_writer")
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st1102-v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except BaseException as failure:
        if isinstance(failure, secure_generated_publication.SecurePublicationError):
            _fail("OUTPUT_TRANSACTION_FAILED", "output")
        raise


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if set(outputs) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    if check:
        for relative in GENERATED_PATHS:
            path = _output(root, relative, create_parent=False)
            try:
                metadata = path.lstat()
                actual = path.read_bytes()
            except OSError:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o644
                or actual != outputs[relative]
            ):
                _fail("GENERATED_OUTPUT_DRIFT", "output")
        return
    artifacts = tuple(
        (_output(root, relative, create_parent=True), outputs[relative])
        for relative in GENERATED_PATHS
    )
    _replace_generated(root, artifacts)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ST-1102 V2 artifacts")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except ArticleWorkspaceBuildError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    print("ST-1102 V2 check passed" if args.check else "ST-1102 V2 artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
