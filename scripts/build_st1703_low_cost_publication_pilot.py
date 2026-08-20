#!/usr/bin/env python3
"""Build the non-executable ST-1703 low-cost publication pilot projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PILOT_ROOT: Final = Path("changes/st-1703/low-cost-publication-pilot")
CONTRACT_PATH: Final = PILOT_ROOT / "low-cost-publication-pilot.v1.yaml"
HANDOFF_PATH: Final = (
    PILOT_ROOT / "DESIGN_HANDOFF_V1_ST1703_LOW_COST_PUBLICATION_PILOT_V1.yaml"
)
APPROVAL_PATH: Final = (
    PILOT_ROOT / "DESIGN-HANDOFF-APPROVAL-ST1703-LOW-COST-PUBLICATION-PILOT-v1.yaml"
)
V2_HANDOFF_PATH: Final = (
    PILOT_ROOT
    / "DESIGN_HANDOFF_V1_ST1703_LOW_COST_PUBLICATION_PILOT_RECONCILIATION_V2.yaml"
)
V2_APPROVAL_PATH: Final = (
    PILOT_ROOT
    / "DESIGN-HANDOFF-APPROVAL-ST1703-LOW-COST-PUBLICATION-PILOT-RECONCILIATION-v2.yaml"
)
V3_HANDOFF_PATH: Final = Path(
    "changes/st-1703/origin-main-integration/"
    "DESIGN_HANDOFF_V1_ST1703_ORIGIN_MAIN_INTEGRATION_V3.yaml"
)
V3_APPROVAL_PATH: Final = Path(
    "changes/st-1703/origin-main-integration/"
    "DESIGN-HANDOFF-APPROVAL-ST1703-ORIGIN-MAIN-INTEGRATION-V3.yaml"
)
OUTPUT_PATH: Final = PILOT_ROOT / "generated/low-cost-publication-pilot.v1.json"
MANIFEST_PATH: Final = PILOT_ROOT / "manifest.yaml"
README_PATH: Final = PILOT_ROOT / "README.md"
GENERATOR_PATH: Final = Path("scripts/build_st1703_low_cost_publication_pilot.py")
TEST_PATHS: Final = (
    Path("tests/st1703_low_cost/conftest.py"),
    Path("tests/st1703_low_cost/test_contract.py"),
    Path("tests/st1703_low_cost/test_generation.py"),
    Path("tests/st1703_low_cost/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (
    HANDOFF_PATH,
    APPROVAL_PATH,
    V2_HANDOFF_PATH,
    V2_APPROVAL_PATH,
    V3_HANDOFF_PATH,
    V3_APPROVAL_PATH,
    CONTRACT_PATH,
    README_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (OUTPUT_PATH, MANIFEST_PATH)
HANDOFF_BYTES: Final = 13776
HANDOFF_SHA256: Final = (
    "4730d8de3eb11cccd76081a34da4d55b2e7070467d53b7bdacd3fb95baa976a6"
)
PROPOSAL_BYTES: Final = 342
PROPOSAL_SHA256: Final = (
    "131534a5c035096a3e18abbc1e82f9937b50cd7d3c84e4a3fc413d52e57b6a5b"
)
OWNER_RESPONSE_BYTES: Final = 6
OWNER_RESPONSE_SHA256: Final = (
    "5d103c64a39b8ac1e10c8a7038fa6d780ed1d1b205e071e2b52236f9540f59a6"
)
CONTRACT_BYTES: Final = 7525
CONTRACT_SHA256: Final = (
    "2bc2329f760e1a7960196fec9960e2573ed2add653e6349150dffaddf60a90f3"
)
CONTRACT_SEMANTIC_SHA256: Final = (
    "9f32b45feb0cb8ddad4c8f54078309b8eb57357e0edce9904d0eca275f723a11"
)
APPROVAL_BYTES: Final = 2592
APPROVAL_SHA256: Final = (
    "60a442e87ba9d965e9c49609307bb4f004bd11f9a4b9f92d5e7bd635b2fca620"
)
APPROVAL_SEMANTIC_SHA256: Final = (
    "a228d177bf2539c0f9cf1d949d64131c11659a0db17a536b374b6812fcbbc466"
)
V2_HANDOFF_BYTES: Final = 28414
V2_HANDOFF_SHA256: Final = (
    "ff75d76479a6ebf85061e54529c0896cd1a203d8f1ab0d01655ecc18dc91a6db"
)
V2_HANDOFF_SEMANTIC_SHA256: Final = (
    "3b3f04d729b249d0a45ac7be19a227dbf689f4b928982fb8574fa6ae7c4aaada"
)
V2_APPROVAL_BYTES: Final = 3756
V2_APPROVAL_SHA256: Final = (
    "cc1dd13e123bde10372a3f4576a851d555e20e7eac6071f3ed33ce5be6c77410"
)
V2_APPROVAL_SEMANTIC_SHA256: Final = (
    "b75d2c76fd4c6d5b37d388731a41b6f8156226b8eabb096672b475874aa09062"
)
V3_HANDOFF_BYTES: Final = 46856
V3_HANDOFF_SHA256: Final = (
    "94e21a08ca051cf66c4c635c9e018b9db313ac649fd2b0c2461d16712a80daba"
)
V3_HANDOFF_SEMANTIC_SHA256: Final = (
    "c8edbbb8891cf15bbbe138a6ab9597233a3d1e477d17eb4fe930632bb0f4a58d"
)
V3_APPROVAL_BYTES: Final = 3883
V3_APPROVAL_SHA256: Final = (
    "27ae35a552c4319a015037f363c08ba617482381fdc1f1cc9802476785e69216"
)
V3_APPROVAL_SEMANTIC_SHA256: Final = (
    "3f6e645dfcaed03df4bf4c42b1074eed99643a89b0f8809ee582d2175a4b34ae"
)
APPROVED_BASE_COMMIT: Final = "0d6286ad19fe3a30599359a33b2409b64ae00f1f"
APPROVED_BASE_TREE: Final = "3b84020ed4c3aa232e2755ebf9e4607fa02a44e1"
CURRENT_TARGET_COMMIT: Final = "6c014bee7004a9f1dfa726686b91f436fc9cd2f7"
CURRENT_TARGET_TREE: Final = "9a1824f948b0bceb416417bfedaf101f1a452ebf"
V3_TARGET_BRANCH: Final = "codex/st-1703-origin-main-integration"
V3_TARGET_COMMIT: Final = "acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d"
V3_TARGET_TREE: Final = "85620e53419b65e3053e4454c6c1cb522de4459b"
V1_SOURCE_COMMIT: Final = "e554148349b93c8d790e7d38da467569c5badafc"
V1_SOURCE_TREE: Final = "8031b0854a35b643b6bd13c877f9eae525f054f1"
V3_SOURCE_COMMIT: Final = "ca5ff2e419ffc07239b4c551146dd66b01489cc3"
V3_SOURCE_TREE: Final = "53071f15d7dffc859e8e83e48531114069a0fb25"
V3_RANGE_PARENT: Final = "290cb2e71b9b310e59500c5643fef4296c877f3f"
V3_MERGE_BASE: Final = "317561ba2f56e9e9c55d65f24df13db3dc3fa77d"
V3_RANGE_PATCH_BYTES: Final = 1153555
V3_RANGE_PATCH_SHA256: Final = (
    "46b5235bd50ec0db8d37ddadbc9924c22db55d7c1c5db2f4293f38b3579cd68e"
)
V3_RANGE_INVENTORY_BYTES: Final = 16790
V3_RANGE_INVENTORY_SHA256: Final = (
    "e3e642125a01e964f1849b181a727a184ae164196e7a96e8bc4247b527ebed3f"
)
WAVE3_HANDOFF_SHA256: Final = (
    "46f43208309e139c062995adf7bae0cd522a564bd17d77d7966e76f8f51277be"
)
WAVE3_APPROVAL_SHA256: Final = (
    "e46de3b040bcb04276ff1cc0246857c10b763888e27a5eb4577f84e424103660"
)
HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES: Final = 5156
HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256: Final = (
    "ac5f80152c846df3be09b90a28a0bd5ca93f2e165807b9fcb50ca7eb569c908c"
)
CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES: Final = 5656
CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256: Final = (
    "8cf00ace6e2988c3bfb7969f13cfec0786137077c1319be4b043c4b762b5fba9"
)
V3_TARGET_WAVE3_RUNTIME_MANIFEST_BYTES: Final = 5656
V3_TARGET_WAVE3_RUNTIME_MANIFEST_SHA256: Final = (
    "b9ccd47c40b9bc9a7595f9e9de2d807232e2b084851b2057007d37b8c98b3c6e"
)
ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES: Final = 5776
ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256: Final = (
    "2d9c599c03bcd479137729ae2cd570ff7b60337511f543821aa5df959873a5d1"
)
STANDING_DEVELOPMENT_AUTHORITY_PATH: Final = Path("AGENTS.md")
STANDING_DEVELOPMENT_AUTHORITY_BYTES: Final = 54428
STANDING_DEVELOPMENT_AUTHORITY_SHA256: Final = (
    "a302eac0ebd61e352c94f9e07e715b41545bc29c1eae6c73f6115cf6ff3f2127"
)
PROJECTION_BYTES: Final = 9380
PROJECTION_SHA256: Final = (
    "34194a4dd874c0b2194733514aa6421131a51a0e2c843e517e207b9d46f96317"
)
SUPERSEDED_V1_MANIFEST_BYTES: Final = 6214
SUPERSEDED_V1_MANIFEST_SHA256: Final = (
    "dd983347c4cbfb9c541df23f15d28f5ddd6e76441452ff353a2e2808207f6746"
)
WAVE3_RUNTIME_MANIFEST_PATH: Final = Path(
    "changes/st-1703/wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json"
)
BASE_AUTHORITY_INPUTS: Final = (
    (
        Path("docs/canonical/00_master/RAOS_MASTER_README_v1.0.md"),
        2275,
        "a0b27b491ee120767a59dd0c7822ab10e30cf17738960a919116623415ff8e40",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        7943,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
        3955,
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        4956,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md"),
        8046,
        "0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv"),
        4051,
        "690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
        7929,
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        24993,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        11395,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
        6609,
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        71458,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        Path(
            "docs/upstream/key_documents/RAOS_06_content_editorial_evidence_design_v0.1.md"
        ),
        78224,
        "a40b9859122b330f9db7246f58e7e45f8024f64fde8b07a41ab234ed11cae682",
    ),
    (
        Path(
            "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3.yaml"
        ),
        29041,
        WAVE3_HANDOFF_SHA256,
    ),
    (
        Path(
            "changes/st-1703/DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3-v1.yaml"
        ),
        1991,
        WAVE3_APPROVAL_SHA256,
    ),
)
FROZEN_V1_HANDOFF_AUTHORITY_INPUTS: Final = (
    *BASE_AUTHORITY_INPUTS,
    (
        WAVE3_RUNTIME_MANIFEST_PATH,
        HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES,
        HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
    ),
)
AUTHORITY_INPUTS: Final = (
    *BASE_AUTHORITY_INPUTS,
    (
        WAVE3_RUNTIME_MANIFEST_PATH,
        CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
        CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
    ),
)
V2_AUTHORITY_INPUTS: Final = (
    BASE_AUTHORITY_INPUTS[0],
    BASE_AUTHORITY_INPUTS[1],
    BASE_AUTHORITY_INPUTS[2],
    BASE_AUTHORITY_INPUTS[3],
    BASE_AUTHORITY_INPUTS[8],
    BASE_AUTHORITY_INPUTS[10],
    BASE_AUTHORITY_INPUTS[12],
    BASE_AUTHORITY_INPUTS[13],
    (
        Path("changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml"),
        12670,
        "aca2af51e2571a62215c600357fb8f0ee246e8891e60d6e5afbe40d8235ee681",
    ),
    (
        Path(
            "changes/st-1703/"
            "DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_"
            "WAVE_3A_OPAQUE_DISCUSSION_EXTENSIONS.yaml"
        ),
        12741,
        "1c0d50faedd3c76d18101afb1032d82da21a6daf0a01e9c687371d20519926aa",
    ),
    (
        Path(
            "changes/st-1703/"
            "DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-"
            "WAVE-3A-OPAQUE-DISCUSSION-EXTENSIONS-v1.yaml"
        ),
        1852,
        "c1002959dda0de0ba0c0535697a814fa3221fcb05c7947f543452ef99232afb0",
    ),
    AUTHORITY_INPUTS[-1],
)
V3_AUTHORITY_INPUTS: Final = (
    *V2_AUTHORITY_INPUTS[:-1],
    (
        WAVE3_RUNTIME_MANIFEST_PATH,
        V3_TARGET_WAVE3_RUNTIME_MANIFEST_BYTES,
        V3_TARGET_WAVE3_RUNTIME_MANIFEST_SHA256,
    ),
)
ACTIVE_CURRENT_AUTHORITY_INPUTS: Final = (
    *BASE_AUTHORITY_INPUTS,
    (
        STANDING_DEVELOPMENT_AUTHORITY_PATH,
        STANDING_DEVELOPMENT_AUTHORITY_BYTES,
        STANDING_DEVELOPMENT_AUTHORITY_SHA256,
    ),
    (
        WAVE3_RUNTIME_MANIFEST_PATH,
        ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
        ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
    ),
)
MAX_INPUT_BYTES: Final = 256_000


class PilotContractError(RuntimeError):
    """Closed, sanitized failure from the local pilot generator."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise PilotContractError(code)


class _StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses aliases and duplicate keys."""


def _construct_mapping(
    loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            _fail("UNSAFE_YAML")
        if duplicate:
            _fail("UNSAFE_YAML")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _real_repository_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError:
        _fail("ROOT_INVALID")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("ROOT_INVALID")
    return resolved


def _validate_relative_path(relative: Path, code: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail(code)


def _repository_regular_path(root: Path, relative: Path) -> Path:
    _validate_relative_path(relative, "UNSAFE_PATH")
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _fail("INPUT_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_PATH")
    candidate = current / relative.name
    try:
        metadata = candidate.lstat()
    except OSError:
        _fail("INPUT_INVALID")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_PATH")
    return candidate


def _read_regular_file(root: Path, relative: Path) -> bytes:
    candidate = _repository_regular_path(root, relative)
    try:
        content = candidate.read_bytes()
    except OSError:
        _fail("INPUT_INVALID")
    if not content or len(content) > MAX_INPUT_BYTES:
        _fail("INPUT_INVALID")
    return content


def load_yaml(root: Path, relative: Path) -> dict[str, Any]:
    content = _read_regular_file(root, relative)
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("UNSAFE_YAML")
        document = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError, UnicodeError, PilotContractError:
        _fail("UNSAFE_YAML")
    if type(document) is not dict:
        _fail("CONTRACT_INVALID")
    return document


def validate_contract(document: Mapping[str, Any]) -> None:
    """Validate the complete exact approved semantic tree."""
    if tuple(document) != (
        "document",
        "authority",
        "bindings",
        "pilot",
        "spend_boundary",
        "quality_and_ux_requirements",
        "planned_checkpoints",
        "inherited_blockers",
        "evidence_boundary",
        "action_boundary",
        "effect_boundary",
        "evidence_records",
    ):
        _fail("CONTRACT_INVALID")
    if document["document"] != {
        "schema": "RAOS_LOW_COST_PUBLICATION_PILOT_V1",
        "id": "RAOS-ST1703-LOW-COST-PUBLICATION-PILOT-001",
        "version": "1.0.0",
        "story_id": "ST-1703",
        "classification": "SOURCE_DERIVED_NON_EXECUTABLE_NON_ATTESTING_PLAN",
        "design_status": "OWNER_APPROVED_FOR_REPOSITORY_LOCAL_IMPLEMENTATION",
        "implementation_status": "LOCAL_GOVERNANCE_SLICE_ONLY",
        "formal_verification": "NOT_EXECUTED",
        "production_readiness": "NOT_READY",
    }:
        _fail("CONTRACT_INVALID")
    authority = document.get("authority")
    if type(authority) is not dict:
        _fail("CONTRACT_INVALID")
    proposal = authority.get("approved_proposal")
    response = authority.get("owner_response")
    if type(proposal) is not dict or type(response) is not dict:
        _fail("AUTHORITY_INVALID")
    proposal_text = proposal.get("text")
    response_text = response.get("text")
    if type(proposal_text) is not str or type(response_text) is not str:
        _fail("AUTHORITY_INVALID")
    proposal_bytes = proposal_text.encode("utf-8")
    response_bytes = response_text.encode("utf-8")
    if (len(proposal_bytes), sha256_bytes(proposal_bytes)) != (
        PROPOSAL_BYTES,
        PROPOSAL_SHA256,
    ):
        _fail("AUTHORITY_INVALID")
    if (len(response_bytes), sha256_bytes(response_bytes)) != (
        OWNER_RESPONSE_BYTES,
        OWNER_RESPONSE_SHA256,
    ):
        _fail("AUTHORITY_INVALID")
    if (
        proposal.get("utf8_bytes") != PROPOSAL_BYTES
        or proposal.get("sha256") != PROPOSAL_SHA256
    ):
        _fail("AUTHORITY_INVALID")
    if (
        response.get("utf8_bytes") != OWNER_RESPONSE_BYTES
        or response.get("sha256") != OWNER_RESPONSE_SHA256
    ):
        _fail("AUTHORITY_INVALID")
    if document.get("action_boundary") != {
        "external_actions": [],
        "provider_calls": [],
        "purchases": [],
        "credential_operations": [],
        "domain_operations": [],
        "draft_operations": [],
        "publication_operations": [],
        "staging_operations": [],
        "release_operations": [],
        "production_operations": [],
    }:
        _fail("ACTION_BOUNDARY_INVALID")
    if (
        any(document.get("effect_boundary", {}).values())
        or document.get("evidence_records") != []
    ):
        _fail("EVIDENCE_OR_EFFECT_INVALID")
    try:
        semantic_bytes = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("CONTRACT_INVALID")
    if sha256_bytes(semantic_bytes) != CONTRACT_SEMANTIC_SHA256:
        _fail("CONTRACT_INVALID")


def render_projection(document: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            document, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False
        )
    except TypeError, ValueError, UnicodeError:
        _fail("SERIALIZATION_INVALID")
    return (rendered + "\n").encode("utf-8")


def _semantic_sha256(document: Mapping[str, Any]) -> str:
    try:
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("SERIALIZATION_INVALID")
    return sha256_bytes(content)


def _validate_handoff(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("design_handoff",):
        _fail("HANDOFF_INVALID")
    handoff = document["design_handoff"]
    if type(handoff) is not dict or tuple(handoff) != (
        "schema",
        "approval_status",
        "approved_story",
        "title",
        "approved_scope",
        "source_design_refs",
        "decision",
        "rationale",
        "rejected_alternatives",
        "constraints",
        "security_and_approval_gates",
        "acceptance_criteria",
        "required_test_evidence",
        "open_decisions",
    ):
        _fail("HANDOFF_INVALID")
    if (
        handoff["schema"] != "DESIGN_HANDOFF_V1"
        or handoff["approval_status"] != "APPROVED_FOR_IMPLEMENTATION"
        or handoff["approved_story"] != "ST-1703"
        or handoff["open_decisions"] != []
    ):
        _fail("HANDOFF_INVALID")
    refs = handoff["source_design_refs"]
    if type(refs) is not list or len(refs) != len(FROZEN_V1_HANDOFF_AUTHORITY_INPUTS):
        _fail("HANDOFF_INVALID")
    observed: list[tuple[str, int, str]] = []
    for row in refs:
        if type(row) is not dict or tuple(row) != (
            "uri",
            "bytes",
            "sha256",
            "authority",
        ):
            _fail("HANDOFF_INVALID")
        observed.append((row["uri"], row["bytes"], row["sha256"]))
    expected = [
        (f"repo://{path.as_posix()}", byte_count, digest)
        for path, byte_count, digest in FROZEN_V1_HANDOFF_AUTHORITY_INPUTS
    ]
    if observed != expected:
        _fail("HANDOFF_INVALID")


def _validate_approval(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("DESIGN_HANDOFF_APPROVAL_V1",):
        _fail("APPROVAL_INVALID")
    if _semantic_sha256(document) != APPROVAL_SEMANTIC_SHA256:
        _fail("APPROVAL_INVALID")
    approval = document["DESIGN_HANDOFF_APPROVAL_V1"]
    if type(approval) is not dict:
        _fail("APPROVAL_INVALID")
    if (
        approval.get("story_id") != "ST-1703"
        or approval.get("handoff_bytes") != HANDOFF_BYTES
        or approval.get("handoff_sha256") != HANDOFF_SHA256
        or approval.get("status") != "APPROVED_FOR_IMPLEMENTATION"
        or approval.get("open_decisions") != []
    ):
        _fail("APPROVAL_INVALID")
    if approval.get("exact_proposal") != {
        "text": (
            "30日パイロットでは、WordPress.com Personalを唯一の公開基盤、"
            "Codex＋Gitを記事作成・品質管理基盤とする。OpenAI API、AWS、"
            "Cloudflare Pages、独自Admin/API/Workerは保留。既存ChatGPT契約を"
            "除く外部費上限は月2,000円。CodexはDraft作成と検証のみで、公開は"
            "人手に限定する。"
        ),
        "utf8_bytes": PROPOSAL_BYTES,
        "sha256": PROPOSAL_SHA256,
    }:
        _fail("APPROVAL_INVALID")
    if approval.get("exact_owner_response") != {
        "text": "承認",
        "utf8_bytes": OWNER_RESPONSE_BYTES,
        "sha256": OWNER_RESPONSE_SHA256,
    }:
        _fail("APPROVAL_INVALID")
    if approval.get("exact_base") != {
        "commit": APPROVED_BASE_COMMIT,
        "tree": APPROVED_BASE_TREE,
    }:
        _fail("APPROVAL_INVALID")
    if approval.get("wave3_bindings") != {
        "handoff_sha256": WAVE3_HANDOFF_SHA256,
        "approval_sha256": WAVE3_APPROVAL_SHA256,
        "runtime_manifest_sha256": HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
    }:
        _fail("APPROVAL_INVALID")


def _validate_v2_handoff(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("design_handoff",):
        _fail("V2_HANDOFF_INVALID")
    if _semantic_sha256(document) != V2_HANDOFF_SEMANTIC_SHA256:
        _fail("V2_HANDOFF_INVALID")
    handoff = document["design_handoff"]
    if type(handoff) is not dict:
        _fail("V2_HANDOFF_INVALID")
    decision = handoff.get("decision")
    if type(decision) is not dict:
        _fail("V2_HANDOFF_INVALID")
    if (
        handoff.get("schema") != "DESIGN_HANDOFF_V1"
        or handoff.get("approved_story") != "ST-1703"
        or handoff.get("title") != "ST1703_LOW_COST_PUBLICATION_PILOT_RECONCILIATION_V2"
        or handoff.get("open_decisions") != []
        or decision.get("semantic_delta_from_approved_v1") != "NONE"
        or decision.get("implementation_authority")
        != "NONE_PENDING_EXACT_HANDOFF_SHA256_APPROVAL"
    ):
        _fail("V2_HANDOFF_INVALID")
    rule = decision.get("historical_and_current_manifest_rule")
    target = decision.get("target_repository_state")
    source = decision.get("v1_source_identity")
    if type(rule) is not dict or type(target) is not dict or type(source) is not dict:
        _fail("V2_HANDOFF_INVALID")
    if (
        rule.get("v1_historical_sha256") != HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256
        or rule.get("v1_historical_bytes") != HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES
        or rule.get("current_target_sha256") != CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256
        or rule.get("current_target_bytes") != CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES
        or rule.get("git_object_as_missing_filesystem_authority_input") != "FORBIDDEN"
        or target.get("exact_target_commit") != CURRENT_TARGET_COMMIT
        or target.get("exact_target_tree") != CURRENT_TARGET_TREE
        or source.get("exact_commit") != V1_SOURCE_COMMIT
        or source.get("exact_tree") != V1_SOURCE_TREE
    ):
        _fail("V2_HANDOFF_INVALID")


def _validate_v2_approval(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("DESIGN_HANDOFF_APPROVAL_V1",):
        _fail("V2_APPROVAL_INVALID")
    if _semantic_sha256(document) != V2_APPROVAL_SEMANTIC_SHA256:
        _fail("V2_APPROVAL_INVALID")
    approval = document["DESIGN_HANDOFF_APPROVAL_V1"]
    if type(approval) is not dict:
        _fail("V2_APPROVAL_INVALID")
    if (
        approval.get("story_id") != "ST-1703"
        or approval.get("slice_id")
        != "ST1703_LOW_COST_PUBLICATION_PILOT_RECONCILIATION_V2"
        or approval.get("handoff_bytes") != V2_HANDOFF_BYTES
        or approval.get("handoff_sha256") != V2_HANDOFF_SHA256
        or approval.get("status") != "APPROVED_FOR_IMPLEMENTATION"
        or approval.get("semantic_delta_from_approved_v1") != "NONE"
        or approval.get("open_decisions") != []
    ):
        _fail("V2_APPROVAL_INVALID")
    if approval.get("exact_target") != {
        "commit": CURRENT_TARGET_COMMIT,
        "tree": CURRENT_TARGET_TREE,
    }:
        _fail("V2_APPROVAL_INVALID")
    source = approval.get("exact_v1_source")
    current = approval.get("current_wave3_runtime_manifest")
    historical = approval.get("historical_v1_runtime_manifest_binding")
    if (
        type(source) is not dict
        or type(current) is not dict
        or type(historical) is not dict
    ):
        _fail("V2_APPROVAL_INVALID")
    if (
        source.get("commit") != V1_SOURCE_COMMIT
        or source.get("tree") != V1_SOURCE_TREE
        or current.get("bytes") != CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES
        or current.get("sha256") != CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256
        or historical.get("bytes") != HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES
        or historical.get("sha256") != HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256
        or historical.get("git_object_as_current_filesystem_substitute") != "FORBIDDEN"
    ):
        _fail("V2_APPROVAL_INVALID")


def _validate_v3_handoff(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("design_handoff",):
        _fail("V3_HANDOFF_INVALID")
    if _semantic_sha256(document) != V3_HANDOFF_SEMANTIC_SHA256:
        _fail("V3_HANDOFF_INVALID")
    handoff = document["design_handoff"]
    if type(handoff) is not dict:
        _fail("V3_HANDOFF_INVALID")
    decision = handoff.get("decision")
    if type(decision) is not dict:
        _fail("V3_HANDOFF_INVALID")
    if (
        handoff.get("schema") != "DESIGN_HANDOFF_V1"
        or handoff.get("approval_status")
        != "PROPOSED_REQUIRES_REPOSITORY_OWNER_EXACT_SHA256_APPROVAL"
        or handoff.get("approved_story") != "ST-1703"
        or handoff.get("title") != "ST1703_ORIGIN_MAIN_INTEGRATION_V3"
        or handoff.get("open_decisions") != []
        or decision.get("integration_kind")
        != "EXACT_RANGE_IMPORT_WITH_TARGET_SPECIFIC_MECHANICAL_REBIND"
        or decision.get("implementation_authority")
        != "NONE_PENDING_EXACT_HANDOFF_SHA256_APPROVAL"
    ):
        _fail("V3_HANDOFF_INVALID")
    target = decision.get("exact_target")
    source = decision.get("exact_source")
    exact_range = decision.get("exact_range")
    reconciliation = decision.get("low_cost_v3_reconciliation")
    file_cut = decision.get("post_approval_file_cut")
    if (
        type(target) is not dict
        or type(source) is not dict
        or type(exact_range) is not dict
        or type(reconciliation) is not dict
        or type(file_cut) is not dict
    ):
        _fail("V3_HANDOFF_INVALID")
    inventory = exact_range.get("canonical_inventory_serialization")
    if type(inventory) is not dict:
        _fail("V3_HANDOFF_INVALID")
    if (
        target.get("branch") != V3_TARGET_BRANCH
        or target.get("commit") != V3_TARGET_COMMIT
        or target.get("tree") != V3_TARGET_TREE
        or target.get("later_origin_main_move")
        != "STOP_NEW_HANDOFF_AND_APPROVAL_REQUIRED"
        or source.get("commit") != V3_SOURCE_COMMIT
        or source.get("tree") != V3_SOURCE_TREE
        or source.get("range_parent") != V3_RANGE_PARENT
        or source.get("merge_base_with_target") != V3_MERGE_BASE
        or exact_range.get("commit_count") != 9
        or exact_range.get("final_path_count") != 73
        or exact_range.get("full_index_binary_no_renames_patch_bytes")
        != V3_RANGE_PATCH_BYTES
        or exact_range.get("full_index_binary_no_renames_patch_sha256")
        != V3_RANGE_PATCH_SHA256
        or inventory.get("bytes") != V3_RANGE_INVENTORY_BYTES
        or inventory.get("sha256") != V3_RANGE_INVENTORY_SHA256
        or reconciliation.get("V1_semantic_delta") != "NONE"
        or reconciliation.get("V2_semantic_delta") != "NONE"
        or reconciliation.get("current_target_commit") != V3_TARGET_COMMIT
        or reconciliation.get("current_target_tree") != V3_TARGET_TREE
        or reconciliation.get("future_current_runtime_manifest_bytes")
        != V3_TARGET_WAVE3_RUNTIME_MANIFEST_BYTES
        or reconciliation.get("future_current_runtime_manifest_sha256")
        != V3_TARGET_WAVE3_RUNTIME_MANIFEST_SHA256
        or file_cut.get("exact_mutable_imported_path_count") != 8
        or file_cut.get("imported_byte_identical_final_path_count") != 65
        or file_cut.get("all_other_paths") != "PROTECTED"
    ):
        _fail("V3_HANDOFF_INVALID")


def _validate_v3_approval(document: Mapping[str, Any]) -> None:
    if tuple(document) != ("DESIGN_HANDOFF_APPROVAL_V1",):
        _fail("V3_APPROVAL_INVALID")
    if _semantic_sha256(document) != V3_APPROVAL_SEMANTIC_SHA256:
        _fail("V3_APPROVAL_INVALID")
    approval = document["DESIGN_HANDOFF_APPROVAL_V1"]
    if type(approval) is not dict:
        _fail("V3_APPROVAL_INVALID")
    if (
        approval.get("story_id") != "ST-1703"
        or approval.get("slice_id") != "ST1703_ORIGIN_MAIN_INTEGRATION_V3"
        or approval.get("handoff_uri") != f"repo://{V3_HANDOFF_PATH.as_posix()}"
        or approval.get("handoff_bytes") != V3_HANDOFF_BYTES
        or approval.get("handoff_sha256") != V3_HANDOFF_SHA256
        or approval.get("status") != "APPROVED_FOR_IMPLEMENTATION"
        or approval.get("implementation_authority")
        != "EXACT_CLOSED_REPOSITORY_LOCAL_V3_SLICE_ONLY"
        or approval.get("open_decisions") != []
    ):
        _fail("V3_APPROVAL_INVALID")
    target = approval.get("exact_target")
    source = approval.get("exact_source")
    exact_range = approval.get("exact_range")
    file_cut = approval.get("authorized_file_cut")
    historical = approval.get("historical_authority")
    boundaries = approval.get("boundaries")
    if (
        type(target) is not dict
        or type(source) is not dict
        or type(exact_range) is not dict
        or type(file_cut) is not dict
        or type(historical) is not dict
        or type(boundaries) is not dict
    ):
        _fail("V3_APPROVAL_INVALID")
    if (
        target.get("branch") != V3_TARGET_BRANCH
        or target.get("commit") != V3_TARGET_COMMIT
        or target.get("tree") != V3_TARGET_TREE
        or source.get("commit") != V3_SOURCE_COMMIT
        or source.get("tree") != V3_SOURCE_TREE
        or source.get("range_parent") != V3_RANGE_PARENT
        or source.get("merge_base") != V3_MERGE_BASE
        or exact_range.get("commit_count") != 9
        or exact_range.get("final_path_count") != 73
        or exact_range.get("patch_bytes") != V3_RANGE_PATCH_BYTES
        or exact_range.get("patch_sha256") != V3_RANGE_PATCH_SHA256
        or exact_range.get("inventory_bytes") != V3_RANGE_INVENTORY_BYTES
        or exact_range.get("inventory_sha256") != V3_RANGE_INVENTORY_SHA256
        or file_cut.get("exact_imported_path_count") != 73
        or file_cut.get("exact_mutable_imported_path_count") != 8
        or file_cut.get("exact_byte_identical_imported_path_count") != 65
        or file_cut.get("all_other_paths") != "PROTECTED"
        or historical.get("V1_semantic_delta") != "NONE"
        or historical.get("V2_semantic_delta") != "NONE"
        or historical.get("wave3a_nonexistent_commit_references")
        != "UNRESOLVED_NO_AUTHORITY"
        or historical.get("object_drift_separate_exact_hash_bound_approval")
        != "ABSENT_NO_RETROACTIVE_AUTHORITY"
        or boundaries.get("local_commit")
        != "NOT_AUTHORIZED_REQUIRES_EXACT_REVIEWED_DIFF_OWNER_AUTHORITY"
        or boundaries.get("push")
        != "NOT_AUTHORIZED_REQUIRES_SEPARATE_EXTERNAL_WRITE_AUTHORITY"
        or boundaries.get("pull_request")
        != "NOT_AUTHORIZED_REQUIRES_SEPARATE_EXTERNAL_WRITE_AUTHORITY"
        or boundaries.get("publication") != "NOT_AUTHORIZED"
        or boundaries.get("production") != "NOT_AUTHORIZED"
    ):
        _fail("V3_APPROVAL_INVALID")


def _validate_authority_inputs(
    root: Path, inputs: Sequence[tuple[Path, int, str]]
) -> None:
    for relative, byte_count, digest in inputs:
        content = _read_regular_file(root, relative)
        if (len(content), sha256_bytes(content)) != (byte_count, digest):
            _fail("AUTHORITY_INPUT_DRIFT")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read_regular_file(root, relative)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract_bytes = _read_regular_file(root, CONTRACT_PATH)
    if (len(contract_bytes), sha256_bytes(contract_bytes)) != (
        CONTRACT_BYTES,
        CONTRACT_SHA256,
    ):
        _fail("CONTRACT_SOURCE_DRIFT")
    document = load_yaml(root, CONTRACT_PATH)
    validate_contract(document)
    handoff = _read_regular_file(root, HANDOFF_PATH)
    if (len(handoff), sha256_bytes(handoff)) != (HANDOFF_BYTES, HANDOFF_SHA256):
        _fail("HANDOFF_INVALID")
    _validate_handoff(load_yaml(root, HANDOFF_PATH))
    approval_bytes = _read_regular_file(root, APPROVAL_PATH)
    if (len(approval_bytes), sha256_bytes(approval_bytes)) != (
        APPROVAL_BYTES,
        APPROVAL_SHA256,
    ):
        _fail("APPROVAL_INVALID")
    _validate_approval(load_yaml(root, APPROVAL_PATH))
    v2_handoff = _read_regular_file(root, V2_HANDOFF_PATH)
    if (len(v2_handoff), sha256_bytes(v2_handoff)) != (
        V2_HANDOFF_BYTES,
        V2_HANDOFF_SHA256,
    ):
        _fail("V2_HANDOFF_INVALID")
    _validate_v2_handoff(load_yaml(root, V2_HANDOFF_PATH))
    v2_approval = _read_regular_file(root, V2_APPROVAL_PATH)
    if (len(v2_approval), sha256_bytes(v2_approval)) != (
        V2_APPROVAL_BYTES,
        V2_APPROVAL_SHA256,
    ):
        _fail("V2_APPROVAL_INVALID")
    _validate_v2_approval(load_yaml(root, V2_APPROVAL_PATH))
    v3_handoff = _read_regular_file(root, V3_HANDOFF_PATH)
    if (len(v3_handoff), sha256_bytes(v3_handoff)) != (
        V3_HANDOFF_BYTES,
        V3_HANDOFF_SHA256,
    ):
        _fail("V3_HANDOFF_INVALID")
    _validate_v3_handoff(load_yaml(root, V3_HANDOFF_PATH))
    v3_approval = _read_regular_file(root, V3_APPROVAL_PATH)
    if (len(v3_approval), sha256_bytes(v3_approval)) != (
        V3_APPROVAL_BYTES,
        V3_APPROVAL_SHA256,
    ):
        _fail("V3_APPROVAL_INVALID")
    _validate_v3_approval(load_yaml(root, V3_APPROVAL_PATH))
    _validate_authority_inputs(root, BASE_AUTHORITY_INPUTS)
    _validate_authority_inputs(root, V2_AUTHORITY_INPUTS[:-1])
    _validate_authority_inputs(root, V3_AUTHORITY_INPUTS[:-1])
    _validate_authority_inputs(root, ACTIVE_CURRENT_AUTHORITY_INPUTS)
    projection = render_projection(document)
    if (len(projection), sha256_bytes(projection)) != (
        PROJECTION_BYTES,
        PROJECTION_SHA256,
    ):
        _fail("PROJECTION_DRIFT")
    source_artifacts = [_artifact_row(root, path) for path in SOURCE_PATHS]
    generator_row = next(
        row
        for row in source_artifacts
        if row["uri"] == f"repo://{GENERATOR_PATH.as_posix()}"
    )
    manifest = {
        "document": {
            "schema": "RAOS_LOW_COST_PUBLICATION_PILOT_MANIFEST_V1",
            "id": "RAOS-ST1703-LOW-COST-PUBLICATION-PILOT-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1703",
        },
        "provenance": {
            "source_contract": {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "bytes": CONTRACT_BYTES,
                "sha256": CONTRACT_SHA256,
                "semantic_sha256": CONTRACT_SEMANTIC_SHA256,
            },
            "implementation_authority": {
                "handoff": {
                    "uri": f"repo://{HANDOFF_PATH.as_posix()}",
                    "bytes": HANDOFF_BYTES,
                    "sha256": HANDOFF_SHA256,
                },
                "approval": {
                    "uri": f"repo://{APPROVAL_PATH.as_posix()}",
                    "bytes": APPROVAL_BYTES,
                    "sha256": APPROVAL_SHA256,
                },
                "approved_base_commit": APPROVED_BASE_COMMIT,
                "approved_base_tree": APPROVED_BASE_TREE,
            },
            "reconciliation_v2": {
                "classification": "REPOSITORY_LOCAL_PROVENANCE_RECONCILIATION_ONLY",
                "semantic_delta_from_approved_v1": "NONE",
                "authority": {
                    "handoff": {
                        "uri": f"repo://{V2_HANDOFF_PATH.as_posix()}",
                        "bytes": V2_HANDOFF_BYTES,
                        "sha256": V2_HANDOFF_SHA256,
                    },
                    "approval": {
                        "uri": f"repo://{V2_APPROVAL_PATH.as_posix()}",
                        "bytes": V2_APPROVAL_BYTES,
                        "sha256": V2_APPROVAL_SHA256,
                    },
                    "target_commit": CURRENT_TARGET_COMMIT,
                    "target_tree": CURRENT_TARGET_TREE,
                    "v1_source_commit": V1_SOURCE_COMMIT,
                    "v1_source_tree": V1_SOURCE_TREE,
                },
                "historical_v1_runtime_manifest_binding": {
                    "uri": f"repo://{WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
                    "bytes": HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES,
                    "sha256": HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
                    "validation_source": "EXACT_FROZEN_V1_AUTHORITY_BYTES",
                    "silent_repin": "FORBIDDEN",
                    "git_object_as_current_filesystem_substitute": "FORBIDDEN",
                },
                "current_wave3_runtime_manifest": {
                    "uri": f"repo://{WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
                    "bytes": CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
                    "sha256": CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
                    "validation_source": "EXACT_REGULAR_FILESYSTEM_FILE",
                    "authority": "COMMITTED_RUNTIME_METADATA_ONLY",
                    "formal_evidence": False,
                },
                "superseded_v1_generated_manifest": {
                    "uri": f"repo://{MANIFEST_PATH.as_posix()}",
                    "bytes": SUPERSEDED_V1_MANIFEST_BYTES,
                    "sha256": SUPERSEDED_V1_MANIFEST_SHA256,
                    "classification": "HISTORICAL_GENERATED_OUTPUT_NOT_FORMAL_EVIDENCE",
                },
                "preserved_authority_gaps": {
                    "wave3a_invalid_embedded_commit_references": "UNRESOLVED",
                    "object_drift_exact_hash_bound_approval": "ABSENT",
                    "authority_inference_or_retroactive_repair": "FORBIDDEN",
                },
                "authority_inputs": [
                    {
                        "uri": f"repo://{path.as_posix()}",
                        "bytes": byte_count,
                        "sha256": digest,
                    }
                    for path, byte_count, digest in V2_AUTHORITY_INPUTS
                ],
            },
            "reconciliation_v3": {
                "classification": "REPOSITORY_LOCAL_PROVENANCE_RECONCILIATION_ONLY",
                "semantic_delta_from_approved_v1": "NONE",
                "semantic_delta_from_approved_v2": "NONE",
                "authority": {
                    "handoff": {
                        "uri": f"repo://{V3_HANDOFF_PATH.as_posix()}",
                        "bytes": V3_HANDOFF_BYTES,
                        "sha256": V3_HANDOFF_SHA256,
                    },
                    "approval": {
                        "uri": f"repo://{V3_APPROVAL_PATH.as_posix()}",
                        "bytes": V3_APPROVAL_BYTES,
                        "sha256": V3_APPROVAL_SHA256,
                    },
                    "target_branch": V3_TARGET_BRANCH,
                    "target_commit": V3_TARGET_COMMIT,
                    "target_tree": V3_TARGET_TREE,
                    "source_commit": V3_SOURCE_COMMIT,
                    "source_tree": V3_SOURCE_TREE,
                    "range_parent": V3_RANGE_PARENT,
                    "merge_base": V3_MERGE_BASE,
                    "range_patch_bytes": V3_RANGE_PATCH_BYTES,
                    "range_patch_sha256": V3_RANGE_PATCH_SHA256,
                    "range_inventory_bytes": V3_RANGE_INVENTORY_BYTES,
                    "range_inventory_sha256": V3_RANGE_INVENTORY_SHA256,
                },
                "historical_runtime_manifest_bindings": {
                    "v1": {
                        "bytes": HISTORICAL_WAVE3_RUNTIME_MANIFEST_BYTES,
                        "sha256": HISTORICAL_WAVE3_RUNTIME_MANIFEST_SHA256,
                    },
                    "v2": {
                        "bytes": CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
                        "sha256": CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
                    },
                    "silent_repin": "FORBIDDEN",
                    "git_object_as_current_filesystem_substitute": "FORBIDDEN",
                },
                "v3_target_runtime_manifest": {
                    "uri": f"repo://{WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
                    "bytes": V3_TARGET_WAVE3_RUNTIME_MANIFEST_BYTES,
                    "sha256": V3_TARGET_WAVE3_RUNTIME_MANIFEST_SHA256,
                    "validation_source": "IMMUTABLE_V3_HANDOFF_AND_APPROVAL",
                    "authority": "HISTORICAL_COMMITTED_RUNTIME_METADATA_ONLY",
                    "formal_evidence": False,
                },
                "generated_projection": {
                    "uri": f"repo://{OUTPUT_PATH.as_posix()}",
                    "bytes": PROJECTION_BYTES,
                    "sha256": PROJECTION_SHA256,
                    "mutation": "FORBIDDEN",
                },
                "low_cost_manifest": {
                    "generation_only": True,
                    "attestation_or_authority_inflation": "FORBIDDEN",
                },
                "preserved_authority_gaps": {
                    "wave3a_invalid_embedded_commit_references": "UNRESOLVED",
                    "object_drift_exact_hash_bound_approval": "ABSENT",
                    "authority_inference_or_retroactive_repair": "FORBIDDEN",
                },
                "external_authority": "NONE",
                "local_commit_authority": "NOT_AUTHORIZED_REQUIRES_EXACT_OWNER_AUTHORITY",
                "authority_inputs": [
                    {
                        "uri": f"repo://{path.as_posix()}",
                        "bytes": byte_count,
                        "sha256": digest,
                    }
                    for path, byte_count, digest in V3_AUTHORITY_INPUTS
                ],
            },
            "current_development_rebinding": {
                "classification": "REVERSIBLE_REPOSITORY_DEVELOPMENT_ONLY",
                "authority_source": {
                    "uri": f"repo://{STANDING_DEVELOPMENT_AUTHORITY_PATH.as_posix()}",
                    "bytes": STANDING_DEVELOPMENT_AUTHORITY_BYTES,
                    "sha256": STANDING_DEVELOPMENT_AUTHORITY_SHA256,
                    "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
                },
                "current_wave3_runtime_manifest": {
                    "uri": f"repo://{WAVE3_RUNTIME_MANIFEST_PATH.as_posix()}",
                    "bytes": ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_BYTES,
                    "sha256": ACTIVE_CURRENT_WAVE3_RUNTIME_MANIFEST_SHA256,
                    "validation_source": "EXACT_REGULAR_FILESYSTEM_FILE",
                    "authority": "CURRENT_RUNTIME_METADATA_ONLY",
                    "formal_evidence": False,
                },
                "repository_git_authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
                "external_authority": "NONE",
                "live_prepare_authority": "NONE",
                "provider_authority": "NONE",
                "credential_authority": "NONE",
                "publication_authority": "NONE",
                "release_authority": "NONE",
                "production_authority": "NONE",
                "authority_inputs": [
                    {
                        "uri": f"repo://{path.as_posix()}",
                        "bytes": byte_count,
                        "sha256": digest,
                    }
                    for path, byte_count, digest in ACTIVE_CURRENT_AUTHORITY_INPUTS
                ],
            },
            "authority_inputs": [
                {
                    "uri": f"repo://{path.as_posix()}",
                    "bytes": byte_count,
                    "sha256": digest,
                }
                for path, byte_count, digest in ACTIVE_CURRENT_AUTHORITY_INPUTS
            ],
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": (
                "/home/minami/rakuten/.venv/bin/python "
                "scripts/build_st1703_low_cost_publication_pilot.py"
            ),
            "helper_integrity": generator_row,
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{OUTPUT_PATH.as_posix()}",
                "bytes": len(projection),
                "sha256": sha256_bytes(projection),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "DETERMINISTIC_BYTE_FOR_BYTE_REGENERATION_VIA_CHECK",
        },
        "boundary": {
            "classification": "SOURCE_DERIVED_NON_EXECUTABLE_NON_ATTESTING_PLAN",
            "external_actions": [],
            "effects": [],
            "evidence": [],
            "formal_tst": "NOT_EXECUTED",
            "production_readiness": "NOT_READY",
        },
    }
    manifest_bytes = yaml.dump(
        manifest,
        Dumper=_NoAliasDumper,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).encode("utf-8")
    return {OUTPUT_PATH: projection, MANIFEST_PATH: manifest_bytes}


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    _validate_relative_path(relative, "UNSAFE_OUTPUT_PATH")
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("OUTPUT_DRIFT")
            try:
                current.mkdir(mode=0o755)
                _fsync_directory(current.parent)
                metadata = current.lstat()
            except OSError:
                _fail("OUTPUT_WRITE_FAILED")
        except OSError:
            _fail("UNSAFE_OUTPUT_PATH")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_OUTPUT_PATH")
    return current


def _output_path(root: Path, relative: Path, *, create_parent: bool) -> Path:
    parent = _safe_output_parent(root, relative, create=create_parent)
    candidate = parent / relative.name
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return candidate
    except OSError:
        _fail("UNSAFE_OUTPUT_PATH")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_OUTPUT_PATH")
    return candidate


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        _fail("OUTPUT_WRITE_FAILED")


def _stage_file(parent: Path, name: str, content: bytes, mode: int = 0o644) -> Path:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.st1703-low-cost-", dir=parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, mode & 0o777)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        _fail("OUTPUT_WRITE_FAILED")


def install_outputs(outputs: Mapping[Path, bytes], root: Path = REPO_ROOT) -> None:
    """Stage the two generated files, publish them, and roll back as a pair."""
    if tuple(outputs) != GENERATED_PATHS or set(outputs) != set(GENERATED_PATHS):
        _fail("OUTPUT_INVENTORY_DRIFT")
    staged: dict[Path, Path] = {}
    previous: dict[Path, tuple[bytes, int] | None] = {}
    installed: list[Path] = []
    try:
        for relative in GENERATED_PATHS:
            content = outputs[relative]
            if (
                type(content) is not bytes
                or not content
                or len(content) > MAX_INPUT_BYTES
            ):
                _fail("OUTPUT_CONTENT_INVALID")
            target = _output_path(root, relative, create_parent=True)
            if target.exists():
                metadata = target.stat()
                if metadata.st_size > MAX_INPUT_BYTES:
                    _fail("OUTPUT_CONTENT_INVALID")
                old_content = target.read_bytes()
                if len(old_content) != metadata.st_size:
                    _fail("OUTPUT_CONTENT_INVALID")
                previous[relative] = (
                    old_content,
                    stat.S_IMODE(metadata.st_mode),
                )
            else:
                previous[relative] = None
            staged[relative] = _stage_file(target.parent, target.name, content)
        for relative in GENERATED_PATHS:
            target = _output_path(root, relative, create_parent=False)
            temporary = staged[relative]
            os.replace(temporary, target)
            staged.pop(relative)
            installed.append(relative)
            _fsync_directory(target.parent)
    except PilotContractError as install_error:
        rollback_errors = _rollback_outputs(root, previous, installed)
        if rollback_errors:
            raise PilotContractError("OUTPUT_ROLLBACK_INCOMPLETE") from install_error
        raise
    except BaseException as install_error:
        rollback_errors = _rollback_outputs(root, previous, installed)
        if rollback_errors:
            raise PilotContractError("OUTPUT_ROLLBACK_INCOMPLETE") from install_error
        raise PilotContractError("OUTPUT_WRITE_FAILED") from install_error
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _rollback_outputs(
    root: Path,
    previous: Mapping[Path, tuple[bytes, int] | None],
    installed: Sequence[Path],
) -> list[BaseException]:
    errors: list[BaseException] = []
    for relative in reversed(installed):
        try:
            target = _output_path(root, relative, create_parent=False)
            old = previous[relative]
            if old is None:
                target.unlink(missing_ok=True)
                _fsync_directory(target.parent)
            else:
                old_content, old_mode = old
                replacement = _stage_file(
                    target.parent, target.name, old_content, mode=old_mode
                )
                try:
                    os.replace(replacement, target)
                finally:
                    replacement.unlink(missing_ok=True)
                _fsync_directory(target.parent)
        except BaseException as error:
            errors.append(error)
    return errors


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        if tuple(outputs) != GENERATED_PATHS:
            _fail("OUTPUT_INVENTORY_DRIFT")
        for relative in GENERATED_PATHS:
            candidate = _output_path(root, relative, create_parent=False)
            if not candidate.exists():
                _fail("OUTPUT_DRIFT")
            if candidate.read_bytes() != outputs[relative]:
                _fail("OUTPUT_DRIFT")
        return
    install_outputs(outputs, root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(check=arguments.check)
    except PilotContractError as error:
        print(error.code, file=sys.stderr)
        return 1
    except Exception:
        print("UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
