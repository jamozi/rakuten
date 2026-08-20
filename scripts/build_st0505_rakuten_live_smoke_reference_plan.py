#!/usr/bin/env python3
"""Build the non-executable ST-0505 Rakuten live-smoke reference plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0505/contracts/rakuten-live-smoke-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0505/generated/rakuten-live-smoke-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0505/manifest.yaml")
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-0505/"
    "DESIGN_HANDOFF_V1_ST0505_RAKUTEN_LIVE_SMOKE_CREDENTIAL_INTAKE_V1.yaml"
)
DESIGN_HANDOFF_BYTES: Final = 13180
DESIGN_HANDOFF_SHA256: Final = (
    "0292b38edcbf8b8639523c618bb19c3e696708d733fcfaac93006670cf361e30"
)
GENERATOR_PATH: Final = Path(
    "scripts/build_st0505_rakuten_live_smoke_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0505/README.md")
CREDENTIAL_SCRIPT_PATH: Final = Path("scripts/rakuten_live_smoke_credentials.py")
CREDENTIAL_LAUNCHER_PATH: Final = Path(
    "scripts/rakuten_live_smoke_credentials_python.sh"
)
TEST_PATHS: Final = (
    Path("tests/st0505/conftest.py"),
    Path("tests/st0505/test_contract.py"),
    Path("tests/st0505/test_generation.py"),
    Path("tests/st0505/test_negative_cases.py"),
    Path("tests/st0505/test_rakuten_live_smoke_credentials.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    README_PATH,
    GENERATOR_PATH,
    CREDENTIAL_SCRIPT_PATH,
    CREDENTIAL_LAUNCHER_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0505_rakuten_live_smoke_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")

EXPECTED_SOURCES: Final = (
    (
        "integration",
        INTEGRATION_PATH.as_posix(),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "open_decisions",
        OPEN_DECISIONS_PATH.as_posix(),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH.as_posix(),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
PREDECESSOR_COMMIT: Final = "3b63ea8b35b25f1c38c53a7fb5e8c0b596ddd0ab"
EXPECTED_PREDECESSOR_ARTIFACTS: Final = (
    (
        Path("changes/st-0502/README.md"),
        "d242024ecb824c36fe45d63709a34af7138f6101deb5c36782f78f8836c7b731",
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search.py"),
        "4ea7f33ecee122f7e1e57590c2a972ffe7fb9aa493575a547e3354d0f01570c2",
    ),
    (
        Path("python/raos/ports/rakuten_item_search.py"),
        "63983941eeb4a485a3d169073f44c0e4241bdcad452d124cfce1dd07cf2d29fe",
    ),
    (
        Path("python/raos/application/catalog/rakuten_item_search.py"),
        "454c46f66ad473a81395bc08330e7b62635e78c0d1763424227d2f7ebd84688c",
    ),
    (
        Path("python/raos/adapters/recorded_rakuten_item_search.py"),
        "ffdde9dda64800369ac1d90357a6b9300ff104447547bf8c4bb9bf28e89e7dd7",
    ),
    (
        Path("tests/st0502/conftest.py"),
        "31285176cd193385818f830c15b3a520195f8e5fe819e541fd916aad6bf66718",
    ),
    (
        Path("tests/st0502/test_boundaries.py"),
        "d67b995da35bf31b5fb576ca291a9c16e34ccfa4a672377b83121b576ef8eb78",
    ),
    (
        Path("tests/st0502/test_failure_isolation.py"),
        "964139bc7e81e41d2dab066599cfa434ee186c465f417e51db97c930f0ea5d52",
    ),
    (
        Path("tests/st0502/test_rakuten_item_search.py"),
        "5d6d8767ea11124dc378cc52f18006fbb4eb9cdba3fbfe4bb7d06526ebddd42a",
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search_live_request_v1.py"),
        "acd53bc3b12925e09859833ed9fc817e52a14872ae946336cc3dd039e990849e",
    ),
    (
        Path("tests/st0502/test_rakuten_item_search_live_request_v1.py"),
        "710ee36b2cc88d2f14c5a3e726b2fe50d1bd9fbc2bdd9bdb1a05c099bbf4c696",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessor",
    "open_decision",
    "local_credential_intake",
    "live_smoke_definition",
    "observation_defaults",
    "rate_quota_cost_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_binding",
    "open_decision",
    "local_credential_intake",
    "test_suite",
    "live_smoke_definition",
    "observation_boundary",
    "rate_quota_cost_boundary",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "live_call",
    "network",
    "credential_read",
    "retry",
    "paginate",
    "create",
    "update",
    "delete",
    "store",
    "persist",
    "external",
)
LIVE_POLICY_ALLOWED_IMPORTS: Final = frozenset(
    {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "raos",
        "typing",
    }
)
LIVE_POLICY_ALLOWED_IMPORT_BINDINGS: Final[
    frozenset[tuple[str, str, str, str | None, int]]
] = frozenset(
    {
        ("from", "__future__", "annotations", None, 0),
        ("from", "dataclasses", "dataclass", None, 0),
        ("from", "enum", "Enum", None, 0),
        ("import", "", "hashlib", None, 0),
        ("import", "", "json", None, 0),
        ("from", "typing", "NoReturn", None, 0),
        ("from", "typing", "SupportsIndex", None, 0),
        (
            "from",
            "raos.domain.catalog.rakuten_item_search",
            "fail_item_search",
            None,
            0,
        ),
    }
)
LIVE_POLICY_ALLOWED_NAME_CALLS: Final = frozenset(
    {
        "TypeError",
        "_bounded_text",
        "_exact_int",
        "any",
        "dataclass",
        "dict",
        "fail_item_search",
        "len",
        "ord",
        "sorted",
        "tuple",
        "type",
    }
)
LIVE_POLICY_ALLOWED_ATTRIBUTE_CALLS: Final = frozenset(
    {
        "dumps",
        "encode",
        "hexdigest",
        "items",
        "partition",
        "sha256",
        "strip",
        "update",
    }
)
LIVE_POLICY_EXPECTED_TOP_LEVEL_FUNCTIONS: Final = frozenset(
    {"_bounded_text", "_exact_int"}
)
LIVE_POLICY_EXPECTED_CLASS_METHODS: Final[Mapping[str, frozenset[str]]] = {
    "LiveItemSearchSortV1": frozenset(),
    "LiveItemSearchElementV1": frozenset(),
    "ProviderTextTrustV1": frozenset(),
    "_RedactedValue": frozenset({"__reduce_ex__", "__repr__", "__str__"}),
    "RakutenItemSearchLiveRequestV1": frozenset(
        {
            "__post_init__",
            "canonical_json",
            "canonical_parameters",
            "fingerprint",
            "pagination_followup_limit",
            "provider_derived_recommendation_inputs",
            "provider_text_trust",
            "retry_limit",
        }
    ),
}
LIVE_POLICY_EXPECTED_DEFINITION_AST_SHA256: Final[Mapping[str, str]] = {
    "_bounded_text": (
        "2bfc582b76f363ce8ff4714ca2d95466fd49a6b6ff262b65b3fb0c738aa66a0e"
    ),
    "_exact_int": ("5bc0641d1a1a36488cc7bef4b27e3a84af68f42f69bfe7739b4c697c46b9d104"),
    "_RedactedValue.__repr__": (
        "42234706298cad84560a330232331303f10bca79d121b21047b8527c013342fe"
    ),
    "_RedactedValue.__str__": (
        "e83938cb60d4af60cce2aa0e50cd7c8c467446c90dfc03096f6b70dd8f351b5a"
    ),
    "_RedactedValue.__reduce_ex__": (
        "ab186dc206a94c78126c33f97a540e5d05b07661f3b6210ed8995ba6ac6a929f"
    ),
    "RakutenItemSearchLiveRequestV1.__post_init__": (
        "73ad229594810c26c3ec528b4763f3e1e380ecf48e974f446e84a794847858cc"
    ),
    "RakutenItemSearchLiveRequestV1.canonical_parameters": (
        "2280325aa2398f58b2b2aba39f35db9572e4cef2b1672c1ecbf945200f086a8f"
    ),
    "RakutenItemSearchLiveRequestV1.canonical_json": (
        "fdd0e5ed07d41d0cf3ac31058c9bfe7e71b4fec41cb102caf9c05238a124d853"
    ),
    "RakutenItemSearchLiveRequestV1.fingerprint": (
        "8b47f804f96e82d6ce401addeb12d1ad67dd2e7f0fb767777e48dd56815a229d"
    ),
    "RakutenItemSearchLiveRequestV1.retry_limit": (
        "d076b89c1eb6963ffb44acd1368485899aa98b7d50e6aaad5ac8d11ac6559e8c"
    ),
    "RakutenItemSearchLiveRequestV1.pagination_followup_limit": (
        "169ee0a7d161698acdcde71b55c20370a9e59cd2347d92ba0db3693e4991bd74"
    ),
    "RakutenItemSearchLiveRequestV1.provider_text_trust": (
        "6174281582ea9147c68f877d4750c0f78fc65c99b2738bdd8f4850742cc2b71e"
    ),
    "RakutenItemSearchLiveRequestV1.provider_derived_recommendation_inputs": (
        "a7d21ee1bf2ad262ebbf723c3f6a4988ad18108225299830cd0a7325ceb5f590"
    ),
}
LIVE_POLICY_EXPECTED_MODULE_AST_SHA256: Final = (
    "b24db041cee99db89a1c951973f0a9fe6a5c3ae7e88729fef6ca21d95b04afcb"
)
LIVE_POLICY_FORBIDDEN_IMPORTS: Final = frozenset(
    {
        "builtins",
        "boto3",
        "botocore",
        "http",
        "httpx",
        "importlib",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "sys",
        "urllib",
    }
)
LIVE_POLICY_FORBIDDEN_CALLS: Final = frozenset(
    {
        "commit",
        "execute",
        "getenv",
        "open",
        "persist",
        "publish",
        "request",
        "save",
        "send",
        "store",
        "unlink",
        "upload",
        "urlopen",
        "write",
    }
)
LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES: Final = frozenset(
    {
        "__builtins__",
        "__dict__",
        "__getattribute__",
        "__globals__",
        "__import__",
        "__mro__",
        "__subclasses__",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "hasattr",
        "import_module",
        "locals",
        "modules",
        "setattr",
        "vars",
    }
)
LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS: Final = (
    "affiliate_rate",
    "credential",
    "endpoint",
    "http",
    "network",
    "persistence",
    "review_average",
    "review_count",
    "secret",
    "storage",
)


class RakutenLiveSmokeReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise RakutenLiveSmokeReferenceError(f"ST-0505 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(a, b) for a, b in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _ast_sha256(node: ast.AST) -> str:
    material = ast.dump(
        node,
        annotate_fields=True,
        include_attributes=False,
    ).encode("utf-8")
    return _sha256(material)


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_predecessor_artifacts() -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in EXPECTED_PREDECESSOR_ARTIFACTS
    ]


def _validate_hashes(root: Path) -> None:
    for _role, source_path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(source_path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for predecessor_path, digest in EXPECTED_PREDECESSOR_ARTIFACTS:
        if _sha256(_read(root, predecessor_path, "predecessor.artifact")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.artifact")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")
    handoff = _read(root, DESIGN_HANDOFF_PATH, "credential_intake.design_handoff")
    if (
        len(handoff) != DESIGN_HANDOFF_BYTES
        or _sha256(handoff) != DESIGN_HANDOFF_SHA256
    ):
        _fail("DESIGN_HANDOFF_DRIFT", "credential_intake.design_handoff")


EXPECTED_STORY: Final = {
    "id": "ST-0505",
    "epic_id": "EPIC-05",
    "title": "Rakuten live bounded smoke",
    "objective": "実Credentialで低影響検証",
    "depends_on": ["ST-0502"],
    "requirement_ids": ["FR-002"],
    "design_refs": [],
    "deliverables": ["live smoke report"],
    "acceptance_criteria": ["auth/schema/rate observed"],
    "test_suites": ["TST-016"],
    "priority": "P0",
    "mvp": True,
    "size": "S",
    "open_decisions": ["OD-015"],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_OPEN_DECISION_ROW: Final = {
    "id": "OD-015",
    "topic": "production_provider_credentials",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "required_by": "Live adapter test",
    "owner": "Operations Owner",
    "decision_needed": "楽天、OpenAI、Google、AWSの専用Account/権限/Secretを設定",
    "default_behavior": "Recorded fixtureのみ",
    "blocking": True,
}
EXPECTED_TEST_SUITE: Final = {
    "id": "TST-016",
    "name": "Rakuten adapter live smoke",
    "layer": "adapter",
    "purpose": "公式Sandbox/低影響Liveでauth/rate/schema",
    "candidate_tools": ["live credential"],
    "release_blocking": True,
    "environments": ["staging"],
    "owner": "Operations",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    _exact(_find(stories.get("stories"), "ST-0505", "story"), EXPECTED_STORY, "story")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decision")
    _exact(
        _find(decisions.get("items"), "OD-015", "open_decision"),
        EXPECTED_OPEN_DECISION_ROW,
        "open_decision",
    )
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_suite")
    _exact(
        _find(suites.get("suites"), "TST-016", "test_suite"),
        EXPECTED_TEST_SUITE,
        "test_suite",
    )


def _validate_predecessor_semantics(root: Path) -> None:
    readme = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[0][0], "predecessor.readme"
    ).decode("utf-8", errors="strict")
    required_readme = (
        "RECORDED_TEST_ONLY",
        "live_eligible: false",
        "health `NOT_EXECUTED`",
        "executes once",
        "never sleeps",
        "retries",
        "follows another page",
        "storage and\n  persistence are both `NOT_EXECUTED`",
        "URI is `None`",
        "filesystem, network, SDK, credential, or external-action",
    )
    if any(fragment not in readme for fragment in required_readme):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.readme")

    domain = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[1][0], "predecessor.domain"
    ).decode("utf-8", errors="strict")
    required_domain = (
        'RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"',
        'NOT_EXECUTED = "NOT_EXECUTED"',
        'CONTRACT_TEST = "CONTRACT_TEST"',
        'ITEM_SEARCH = "ITEM_SEARCH"',
        "self.purpose is not ItemSearchPurpose.CONTRACT_TEST",
        "self.live_eligible is not False",
        "self.uri is not None",
        "self.storage_status is not StorageExecutionStatus.NOT_EXECUTED",
        "self.persistence_status is not PersistenceExecutionStatus.NOT_EXECUTED",
        "self.page != 1",
    )
    if any(fragment not in domain for fragment in required_domain):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.domain")

    port = _read(root, EXPECTED_PREDECESSOR_ARTIFACTS[2][0], "predecessor.port").decode(
        "utf-8", errors="strict"
    )
    if any(
        fragment in port
        for fragment in (
            "endpoint_url",
            "credential",
            "def save(",
            "def delete(",
            "def list(",
        )
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.port")

    application = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[3][0], "predecessor.application"
    ).decode("utf-8", errors="strict")
    required_application = (
        "command.request.page != 1",
        "raw = self._provider.execute(command)",
        "storage_status=StorageExecutionStatus.NOT_EXECUTED",
        "persistence_status=PersistenceExecutionStatus.NOT_EXECUTED",
        "live_eligible=False",
    )
    if any(fragment not in application for fragment in required_application):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.application")

    live_policy = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[9][0], "predecessor.live_policy"
    ).decode("utf-8", errors="strict")
    required_live_policy = (
        '"""Pure non-executable live-safe Item Search request policy for ST-0502."""',
        "class RakutenItemSearchLiveRequestV1(_RedactedValue):",
        'self.api_version != "2026-07-01"',
        "_exact_int(self.hits, minimum=1, maximum=30)",
        "type(self.page) is not int or self.page != 1",
        "def retry_limit(self) -> int:\n        return 0",
        "def pagination_followup_limit(self) -> int:\n        return 0",
        "return ProviderTextTrustV1.UNTRUSTED_DATA",
        "if self.has_review_only:\n            fail_item_search()",
    )
    if any(fragment not in live_policy for fragment in required_live_policy):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    if any(
        forbidden in live_policy
        for forbidden in ("reviewAverage", "reviewCount", "affiliateRate")
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    live_policy_tree: ast.Module | None = None
    try:
        live_policy_tree = ast.parse(live_policy)
    except SyntaxError:
        pass
    if live_policy_tree is None:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    if _ast_sha256(live_policy_tree) != LIVE_POLICY_EXPECTED_MODULE_AST_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    top_level_definitions = [
        node
        for node in live_policy_tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    ]
    top_level_definition_names = [node.name for node in top_level_definitions]
    class_definitions = [
        node for node in live_policy_tree.body if isinstance(node, ast.ClassDef)
    ]
    class_definition_names = [node.name for node in class_definitions]
    if (
        len(top_level_definition_names) != len(set(top_level_definition_names))
        or frozenset(top_level_definition_names)
        != LIVE_POLICY_EXPECTED_TOP_LEVEL_FUNCTIONS
        or len(class_definition_names) != len(set(class_definition_names))
        or frozenset(class_definition_names)
        != frozenset(LIVE_POLICY_EXPECTED_CLASS_METHODS)
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    definition_nodes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        node.name: node for node in top_level_definitions
    }
    observed_class_methods: dict[str, frozenset[str]] = {}
    for class_definition in class_definitions:
        methods = [
            node
            for node in class_definition.body
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        ]
        method_names = [node.name for node in methods]
        if len(method_names) != len(set(method_names)):
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
        observed_class_methods[class_definition.name] = frozenset(method_names)
        definition_nodes.update(
            {f"{class_definition.name}.{method.name}": method for method in methods}
        )
    observed_definition_fingerprints = {
        name: _ast_sha256(definition) for name, definition in definition_nodes.items()
    }
    if (
        observed_class_methods != LIVE_POLICY_EXPECTED_CLASS_METHODS
        or observed_definition_fingerprints
        != LIVE_POLICY_EXPECTED_DEFINITION_AST_SHA256
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    imports: set[str] = set()
    import_bindings: set[tuple[str, str, str, str | None, int]] = set()
    calls: set[str] = set()
    name_calls: set[str] = set()
    attribute_calls: set[str] = set()
    identifiers: set[str] = set()
    string_values: set[str] = set()
    has_indirect_call = False
    for node in ast.walk(live_policy_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.partition(".")[0])
                import_bindings.add(("import", "", alias.name, alias.asname, 0))
                identifiers.add(alias.name)
                if alias.asname:
                    identifiers.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(module.partition(".")[0])
            for alias in node.names:
                import_bindings.add(
                    ("from", module, alias.name, alias.asname, node.level)
                )
                identifiers.add(alias.name)
                if alias.asname:
                    identifiers.add(alias.asname)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
                attribute_calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
                name_calls.add(node.func.id)
            else:
                has_indirect_call = True
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            string_values.add(node.value)
    if (
        not imports.issubset(LIVE_POLICY_ALLOWED_IMPORTS)
        or import_bindings != LIVE_POLICY_ALLOWED_IMPORT_BINDINGS
        or not imports.isdisjoint(LIVE_POLICY_FORBIDDEN_IMPORTS)
        or not name_calls.issubset(LIVE_POLICY_ALLOWED_NAME_CALLS)
        or not attribute_calls.issubset(LIVE_POLICY_ALLOWED_ATTRIBUTE_CALLS)
        or not calls.isdisjoint(LIVE_POLICY_FORBIDDEN_CALLS)
        or not identifiers.isdisjoint(LIVE_POLICY_FORBIDDEN_CALLS)
        or not identifiers.isdisjoint(LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES)
        or not string_values.isdisjoint(LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES)
        or not string_values.isdisjoint(LIVE_POLICY_FORBIDDEN_IMPORTS)
        or has_indirect_call
        or any(
            part in identifier.lower()
            for identifier in identifiers
            for part in LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS
        )
        or any(
            part in value.lower()
            for value in string_values
            for part in LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS
        )
        or '"has_review_only":' in live_policy
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")

    live_policy_test = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[10][0], "predecessor.live_policy_test"
    ).decode("utf-8", errors="strict")
    required_live_policy_test = (
        "assert request.retry_limit == request.pagination_followup_limit == 0",
        "assert request.provider_text_trust is ProviderTextTrustV1.UNTRUSTED_DATA",
        'assert b"reviewCount" not in request.canonical_json',
        'assert b"reviewAverage" not in request.canonical_json',
        'assert b"affiliateRate" not in request.canonical_json',
        'assert "has_review_only" not in request.canonical_parameters',
        "test_module_has_no_network_environment_filesystem_or_action_surface",
    )
    if any(fragment not in live_policy_test for fragment in required_live_policy_test):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy_test")


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0505-RAKUTEN-LIVE-SMOKE-REFERENCE-PLAN-001",
    "version": "1.2.1",
    "story_id": "ST-0505",
    "classification": "SOURCE_DERIVED_NONEXECUTABLE_RAKUTEN_LIVE_SMOKE_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS: Final[dict[str, object]] = {
    "policy_name": "RakutenItemSearchLiveRequestV1",
    "policy_version": "V1",
    "provider_api_version": "2026-07-01",
    "non_executable": True,
    "requested_page": 1,
    "hits_minimum": 1,
    "hits_maximum": 30,
    "retry_limit": 0,
    "pagination_followup_limit": 0,
    "review_derived_request_inputs": "EXCLUDED",
    "affiliate_rate_request_inputs": "EXCLUDED",
    "provider_text_trust": "UNTRUSTED_DATA",
}
EXPECTED_PREDECESSOR_SEMANTICS: Final[dict[str, object]] = {
    "provider": "RAKUTEN_ICHIBA",
    "operation": "ITEM_SEARCH",
    "purpose": "CONTRACT_TEST",
    "mode": "RECORDED_TEST_ONLY",
    "live_eligible": False,
    "health": "NOT_EXECUTED",
    "requested_page": 1,
    "page_fetch_count": 1,
    "retry_count": 0,
    "pagination_count": 0,
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "receipt_uri": None,
    "endpoint_url": None,
    "account": None,
    "credential_access": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "provider_sdk": "ABSENT",
    "filesystem": "ABSENT",
    "repository": "ABSENT",
    "external_actions": [],
    "live_request_policy": EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS,
}
EXPECTED_PREDECESSOR: Final = {
    "story_id": "ST-0502",
    "commit": PREDECESSOR_COMMIT,
    "status": "RECORDED_ONE_PAGE_CONTRACT_TEST_ONLY",
    "connection_status": "INTERFACE_AVAILABLE_NOT_CONNECTED",
    "artifacts": _expected_predecessor_artifacts(),
    "semantics": EXPECTED_PREDECESSOR_SEMANTICS,
}
EXPECTED_OPEN_DECISION: Final = {
    "id": "OD-015",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "blocking": True,
    "safe_default": "RECORDED_FIXTURE_ONLY",
    "resolved": False,
    "live_credentials_available": False,
    "live_execution_authorized": False,
}
EXPECTED_CREDENTIAL_INTAKE: Final[dict[str, object]] = {
    "status": "LOCAL_CREDENTIAL_INTAKE_AVAILABLE",
    "version": "V1",
    "design_handoff": {
        "uri": f"repo://{DESIGN_HANDOFF_PATH.as_posix()}",
        "bytes": DESIGN_HANDOFF_BYTES,
        "sha256": DESIGN_HANDOFF_SHA256,
    },
    "commands": {
        "setup": (
            "/home/minami/rakuten/scripts/"
            "rakuten_live_smoke_credentials_python.sh setup"
        ),
        "check": (
            "/home/minami/rakuten/scripts/"
            "rakuten_live_smoke_credentials_python.sh check"
        ),
    },
    "launcher_boundary": {
        "python_flags": ["-I", "-S"],
        "isolated_mode": "REQUIRED",
        "site_import": "DISABLED",
        "executable_pth_hooks": "DISABLED",
        "dependency_surface": "PYTHON_STANDARD_LIBRARY_ONLY",
    },
    "repository_root": "/home/minami/rakuten",
    "store_root": ".secrets/rakuten-live-smoke",
    "staging_root": ".secrets/.rakuten-live-smoke.preparing",
    "committing_marker": ".secrets/.rakuten-live-smoke.committing",
    "ready_marker": ".secrets/.rakuten-live-smoke.ready",
    "validating_marker": ".secrets/.rakuten-live-smoke.validating",
    "committed_marker": ".secrets/.rakuten-live-smoke.committed",
    "aliases": [
        {
            "logical_name": "application_id",
            "alias": "rakuten_web_service_application_id",
        },
        {
            "logical_name": "access_key",
            "alias": "rakuten_web_service_access_key",
        },
    ],
    "excluded_aliases": ["rakuten_affiliate_id"],
    "provider_contract_context": {
        "official_documentation": (
            "https://webservice.rakuten.co.jp/documentation/ichiba-item-search"
        ),
        "retrieved_at": "2026-08-21",
        "api_version": "2026-07-01",
        "application_id_required": True,
        "access_key_required": True,
        "affiliate_id_optional": True,
        "future_access_key_transport": "DEDICATED_HTTP_HEADER_ONLY",
        "access_key_query_parameter": "FORBIDDEN_BY_RAOS",
    },
    "input_boundary": {
        "source": "/dev/tty",
        "echo": "DISABLED",
        "echonl": "DISABLED",
        "argv_values": "FORBIDDEN",
        "environment_values": "FORBIDDEN",
        "stdin_values": "FORBIDDEN",
        "chat_values": "FORBIDDEN",
        "both_values_before_durable_write": True,
        "process_disclosure_before_input": "DISABLED_REQUIRED_LINUX",
        "child_process_after_input": "FORBIDDEN",
        "mutable_buffer_wipe": "BEST_EFFORT",
    },
    "filesystem_boundary": {
        "secret_parent_mode": "0700",
        "store_mode": "0700",
        "alias_mode": "0600",
        "owner": "CURRENT_EFFECTIVE_UID_ONLY",
        "exact_inventory_only": True,
        "regular_files_only": True,
        "link_count": 1,
        "symlinks": "FORBIDDEN",
        "hardlinks": "FORBIDDEN",
        "special_files": "FORBIDDEN",
        "exclusive_create": True,
        "close_on_exec": True,
        "file_and_parent_fsync": True,
        "prepublish_file_stage_parent_fsync": "REQUIRED",
        "publish": "RENAMEAT2_RENAME_NOREPLACE",
        "publish_inode_binding": "RETAINED_DIRECTORY_FD_BEFORE_AND_AFTER_RENAME",
        "postpublish_parent_fsync": "REQUIRED",
        "readiness_intermediate": "COMMITTING_TO_READY_RENAME_NOREPLACE",
        "validating_state": "INVALID_UNTIL_FINAL_METADATA_INSPECTION_PASSES",
        "readiness_commit": ("VALIDATING_TO_COMMITTED_RENAME_NOREPLACE_LAST_OPERATION"),
        "external_ready_shape": (
            "FINAL_STORE_PLUS_READY_PLUS_COMMITTED_WITH_NO_ACTIVE_MARKERS"
        ),
        "overwrite": "FORBIDDEN",
        "rotation": "OUTSIDE_V1",
        "rollback": "NO_AUTOMATIC_ROLLBACK_OR_REPAIR",
        "failure_residue": "OWNER_ONLY_FAIL_CLOSED",
        "crash_residue": "FAIL_CLOSED_NO_AUTOMATIC_DELETE_OR_REPAIR",
        "same_euid_concurrent_mutator": "FORBIDDEN_DURING_SETUP_OR_CHECK",
    },
    "check_boundary": {
        "metadata_only": True,
        "secret_file_open": "FORBIDDEN",
        "secret_content_read": "FORBIDDEN",
        "active_markers": [
            ".rakuten-live-smoke.preparing",
            ".rakuten-live-smoke.committing",
            ".rakuten-live-smoke.validating",
        ],
        "any_active_marker_present": "INVALID",
        "ready_markers_required_with_final_store": [
            ".rakuten-live-smoke.ready",
            ".rakuten-live-smoke.committed",
        ],
        "statuses": ["ABSENT", "READY", "INVALID_WITH_FIXED_REASON_CODE"],
        "ready_meaning": (
            "METADATA_STRUCTURE_ONLY_NOT_CREDENTIAL_VALIDITY_OR_LIVE_AUTHORITY"
        ),
    },
    "runtime_boundary": {
        "credential_reader": "ABSENT",
        "provider_adapter": "ABSENT",
        "endpoint": "ABSENT",
        "account": "ABSENT",
        "network": "FORBIDDEN",
        "provider_call": "FORBIDDEN",
        "live_smoke_connection": "NOT_CONNECTED",
    },
    "execution_evidence": {
        "credential_values_received": False,
        "real_store_setup": "NOT_EXECUTED",
        "real_store_check": "NOT_EXECUTED",
        "provider_call": "NOT_EXECUTED",
    },
}
EXPECTED_SMOKE: Final[dict[str, object]] = {
    "status": "NOT_CONFIGURED",
    "runnable": False,
    "runner": None,
    "command": None,
    "selected_environment": None,
    "selected_account": None,
    "selected_endpoint": None,
    "credential_selection": "ABSENT",
    "request": None,
    "response": None,
    "report": None,
    "retry_policy": None,
    "pagination_policy": None,
    "artifacts": [],
}
EXPECTED_OBSERVATIONS: Final[dict[str, object]] = {
    "status": "NOT_EXECUTED",
    "started_at": None,
    "finished_at": None,
    "auth_observation": None,
    "schema_observation": None,
    "rate_observation": None,
    "provider_request_id": None,
    "http_status": None,
    "latency": None,
    "observations": [],
    "errors": [],
    "evidence": [],
    "empty_interpretation": "NO_LIVE_EXECUTION_EVIDENCE_NOT_ZERO_ERRORS_OR_SUCCESS",
}
EXPECTED_RATE_QUOTA_COST: Final[dict[str, object]] = {
    "rate_limit": None,
    "rate_remaining": None,
    "rate_reset": None,
    "quota_limit": None,
    "quota_remaining": None,
    "cost": None,
    "currency": None,
    "capacity": None,
    "values": [],
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "enabled": False,
    "status": "DISABLED",
    "live_smoke": "NOT_EXECUTED",
    "network": "FORBIDDEN",
    "credential": "LIVE_RUNTIME_FORBIDDEN_LOCAL_INTAKE_INTERFACE_ONLY",
    "provider": "FORBIDDEN",
    "sdk": "ABSENT",
    "filesystem": "FIXED_LOCAL_SECRET_STORE_SETUP_ONLY_NOT_EXECUTED",
    "repository": "TRACKED_CREDENTIAL_STORAGE_FORBIDDEN",
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "external_actions": [],
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "formal_tst_016": "NOT_EXECUTED",
    "live_auth": "NOT_EXECUTED",
    "live_schema": "NOT_EXECUTED",
    "live_rate": "NOT_EXECUTED",
    "provider_runtime": "NOT_EXECUTED",
    "network": "NOT_EXECUTED",
    "credentials": "VALUES_NOT_RECEIVED_OR_READ",
    "credential_intake_interface": "LOCAL_IMPLEMENTATION_AVAILABLE",
    "real_credential_store": "NOT_EXECUTED",
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "decision": "NOT_READY",
    "approval": None,
    "story_acceptance": False,
    "production_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_OPEN_DECISION_AND_TEST_CATALOG",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["predecessor"], EXPECTED_PREDECESSOR, "predecessor")
    _exact(contract["open_decision"], EXPECTED_OPEN_DECISION, "open_decision")
    _exact(
        contract["local_credential_intake"],
        EXPECTED_CREDENTIAL_INTAKE,
        "local_credential_intake",
    )
    _exact(contract["live_smoke_definition"], EXPECTED_SMOKE, "live_smoke_definition")
    _exact(contract["observation_defaults"], EXPECTED_OBSERVATIONS, "observations")
    _exact(
        contract["rate_quota_cost_defaults"],
        EXPECTED_RATE_QUOTA_COST,
        "rate_quota_cost",
    )
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution")
    _exact(contract["verification_boundary"], EXPECTED_VERIFICATION, "verification")
    _validate_hashes(root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(contract: Mapping[str, Any]) -> dict[str, Any]:
    verification = _mapping(contract["verification_boundary"], "verification")
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_binding": contract["predecessor"],
        "open_decision": contract["open_decision"],
        "local_credential_intake": contract["local_credential_intake"],
        "test_suite": {
            **EXPECTED_TEST_SUITE,
            "formal_execution": "NOT_EXECUTED",
            "evidence": None,
        },
        "live_smoke_definition": contract["live_smoke_definition"],
        "observation_boundary": contract["observation_defaults"],
        "rate_quota_cost_boundary": contract["rate_quota_cost_defaults"],
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": {
            "projection_only": True,
            "predecessor_connection": "NOT_EXECUTED",
            **dict(verification),
        },
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0505-RAKUTEN-LIVE-SMOKE-MANIFEST-001",
            "version": "1.2.1",
            "story_id": "ST-0505",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "predecessor_commit": PREDECESSOR_COMMIT,
            "predecessor_inputs": _expected_predecessor_artifacts(),
            "credential_intake_design_handoff": {
                "uri": f"repo://{DESIGN_HANDOFF_PATH.as_posix()}",
                "bytes": DESIGN_HANDOFF_BYTES,
                "sha256": DESIGN_HANDOFF_SHA256,
            },
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "interface_only": True,
            "od_015": "EXTERNAL_EVIDENCE_REQUIRED",
            "safe_default": "RECORDED_FIXTURE_ONLY",
            "credential_intake_interface": "LOCAL_IMPLEMENTATION_AVAILABLE",
            "credential_values": "NOT_RECEIVED_OR_READ",
            "real_credential_store": "NOT_EXECUTED",
            "live_smoke": "NOT_EXECUTED",
            "network": "NOT_EXECUTED",
            "credentials": "LIVE_RUNTIME_NOT_EXECUTED",
            "provider_runtime": "NOT_EXECUTED",
            "storage": "NOT_EXECUTED",
            "persistence": "NOT_EXECUTED",
            "formal_tst_016": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except (RakutenLiveSmokeReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0505 Rakuten live-smoke reference plan checked"
        if args.check
        else "ST-0505 Rakuten live-smoke reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
