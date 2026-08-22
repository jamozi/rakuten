#!/usr/bin/env python3
"""Build ST-1701 business inputs and the fail-closed Gold preapproval report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st0006_decision_gates as predecessor  # noqa: E402
from scripts import build_st1506_production_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml"
)
DECISION_PACKAGE_PATH: Final = Path(
    "changes/st-1701/contracts/mvp-business-decision-package.v1.yaml"
)
REFERENCE_PATH: Final = Path(
    "changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json"
)
DECISION_READ_MODEL_PATH: Final = Path(
    "changes/st-1701/generated/mvp-business-decision-package.v1.json"
)
CANONICAL_REVISION_REQUEST_PATH: Final = Path(
    "changes/st-1701/generated/canonical-revision-request.v1.md"
)
MANIFEST_PATH: Final = Path("changes/st-1701/manifest.yaml")
README_PATH: Final = Path("changes/st-1701/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st1701_business_inputs.py")
HANDOFF_PATH: Final = Path(
    "changes/st-1701/DESIGN_HANDOFF_V1_ST1701_MVP_DECISION_PACKAGE_v1.yaml"
)
HANDOFF_APPROVAL_PATH: Final = Path("changes/st-1701/DESIGN-HANDOFF-APPROVAL-v1.yaml")
FINAL_PACKAGE_APPROVAL_PATH: Final = Path(
    "changes/st-1701/MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml"
)
GOLD_HANDOFF_PATH: Final = Path(
    "changes/st-1701/DESIGN_HANDOFF_V1_ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_v1.yaml"
)
GOLD_HANDOFF_APPROVAL_PATH: Final = Path(
    "changes/st-1701/DESIGN-HANDOFF-APPROVAL-GOLD-EVIDENCE-v1.yaml"
)
GOLD_LEDGER_PATH: Final = Path("changes/st-1701/evidence/gold-evidence-ledger.v1.yaml")
GOLD_EVIDENCE_APPROVAL_PATH: Final = Path(
    "changes/st-1701/evidence/GOLD-EVIDENCE-APPROVAL-v1.yaml"
)
GOLD_VALIDATION_PATH: Final = Path(
    "changes/st-1701/generated/gold-evidence-validation.v1.json"
)
GOLD_POSTAPPROVAL_PATHS: Final = (
    Path("changes/st-1701/generated/gold-evidence-summary.v1.json"),
    Path("changes/st-1701/generated/st1701-resolution-record-candidates.v1.yaml"),
    Path("changes/st-1701/generated/open-decisions-revision-candidate.v1.yaml"),
    Path("changes/st-1701/generated/canonical-revision-bundle-manifest.v1.yaml"),
    Path("changes/st-1701/CANONICAL-REVISION-BUNDLE-APPROVAL-v1.yaml"),
)
TEST_PATHS: Final = (
    Path("tests/st1701/conftest.py"),
    Path("tests/st1701/test_contract.py"),
    Path("tests/st1701/test_generation.py"),
    Path("tests/st1701/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    DECISION_PACKAGE_PATH,
    FINAL_PACKAGE_APPROVAL_PATH,
    GOLD_HANDOFF_PATH,
    GOLD_HANDOFF_APPROVAL_PATH,
    README_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_CONTENT_PATHS: Final = (
    REFERENCE_PATH,
    DECISION_READ_MODEL_PATH,
    CANONICAL_REVISION_REQUEST_PATH,
    GOLD_VALIDATION_PATH,
)
GENERATED_PATHS: Final = (*GENERATED_CONTENT_PATHS, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
DECISION_PACKAGE_URI: Final = f"repo://{DECISION_PACKAGE_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1701_business_inputs.py"
)

POLICY_PATH: Final = Path("changes/st-0006/contracts/decision-gate-policy.v1.yaml")
REPORT_PATH: Final = Path("changes/st-0006/gate-blocker-report.v1.yaml")
PREDECESSOR_GENERATOR_PATH: Final = Path("scripts/build_st0006_decision_gates.py")

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_binding",
    "scope",
    "decisions",
    "business_inputs",
    "safe_defaults",
    "activation",
    "gates",
    "action_boundary",
    "evidence_boundary",
    "downstream_boundary",
)
DECISION_PACKAGE_TOP_LEVEL_KEYS: Final = (
    "document",
    "implementation_authority",
    "final_package_approval",
    "authority_model",
    "record_status_model",
    "canonical_truth_boundary",
    "scoped_decisions",
    "informational_cross_story_owner_inputs",
    "implementation_boundary",
    "evidence_boundary",
    "action_boundary",
)
SCOPED_IDS: Final = (
    "OD-001",
    "OD-002",
    "OD-005",
    "OD-006",
    "OD-007",
    "OD-008",
    "OD-009",
)
INFORMATIONAL_IDS: Final = (
    "OD-003",
    "OD-004",
    "OD-010",
    "OD-011",
    "OD-012",
    "OD-013",
    "OD-014",
    "OD-015",
)
RECORD_STATUSES: Final = (
    "OWNER_APPROVED",
    "PARTIAL",
    "EVIDENCE_PENDING",
    "EXECUTION_PENDING",
)
FORBIDDEN_RECORD_STATUSES: Final = (
    "RESOLVED",
    "VALIDATED",
    "ACTIVE",
    "RELEASED",
    "PRODUCTION_READY",
)
BLOCKED_TARGETS: Final = (
    "GATE-0",
    "GATE-1",
    "GATE-2",
    "GATE-3",
    "GATE-4",
    "PRODUCTION_RELEASE",
)
GATE_IDS: Final = BLOCKED_TARGETS[:5]
ACTION_NAMES: Final = (
    "decision",
    "approval",
    "research",
    "external",
    "publication",
    "staging",
    "release",
    "production",
)
DECISION_ACTION_NAMES: Final = (
    "external",
    "browser",
    "provider",
    "account",
    "domain",
    "publication",
    "staging",
    "release",
    "production",
)
OD006_REQUIRED_FIELDS: Final = (
    "brand",
    "manufacturer_model",
    "size",
    "capacity",
    "external_dimensions",
    "color_or_variant",
    "set_count",
)
SYNTHETIC_JAN_PATTERN: Final = re.compile(r"^(?:[0-9]{8}|[0-9]{13})$")

GOLD_REQUIRED_CASE_TAGS: Final = (
    "exact_duplicates",
    "color_or_variant_differences",
    "size_or_capacity_differences",
    "missing_jan",
    "bundles_and_set_count",
    "conflicting_fields",
)
GOLD_CONTRACT_MAPPING_GAPS: Final = (
    "ledger.schema literal",
    "snapshot_id listing_id family_id and shop_id types and formats",
    "candidate qualification_status and reason_codes closed values",
    "required_case_coverage and domain_editor_review nested schemas",
    (
        "source_reasoning expected_relationship_basis and "
        "variant_or_bundle_distinctions shapes"
    ),
    "observation canonical JSON hashing profile",
    "derived expected-pair row structure and ordering",
    "manufacturer host registry and redirect-chain proof",
    "Domain Editor approval record field layout",
    "postapproval Gold summary resolution revision and bundle schemas",
    (
        "per-result URL and outcome evidence for first-three qualifying "
        "results and first-eligible tuple proof"
    ),
)

HANDOFF_SHA256: Final = (
    "f5e8f70b74fd26c68b0dfd8a47dd35fc59b1651e9e553dad738d90b00acd1790"
)
HANDOFF_BYTES: Final = 20695
HANDOFF_APPROVAL_SHA256: Final = (
    "8a9029410bdad475eca2da7d0ab0f87cf0d3e1a8019e6102522d7cb18ac3dbd0"
)
HANDOFF_APPROVAL_BYTES: Final = 1478
APPROVED_DECISION_PACKAGE_SHA256: Final = (
    "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f"
)
APPROVED_DECISION_PACKAGE_BYTES: Final = 10678
FINAL_PACKAGE_APPROVAL_SHA256: Final = (
    "749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34"
)
FINAL_PACKAGE_APPROVAL_BYTES: Final = 2098
GOLD_HANDOFF_SHA256: Final = (
    "c45bea63891448be4af4d696d7d164ea37f246b76f5acce91de791638f49c17f"
)
GOLD_HANDOFF_BYTES: Final = 26483
GOLD_HANDOFF_APPROVAL_SHA256: Final = (
    "288e96b9e4814e1a3d9409addcee2bf1b5bdf12ab9e0a8e756ec66846f057197"
)
GOLD_HANDOFF_APPROVAL_BYTES: Final = 1876
FINAL_PACKAGE_APPROVAL_STATUS: Final = (
    "APPROVED_AS_NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE"
)
FINAL_PACKAGE_APPROVAL_AUTHORITY: Final = (
    "OWNER_APPROVED_CANONICAL_REVISION_EVIDENCE_CANDIDATE_ONLY"
)
CANONICAL_REVISION_REQUEST_STATUS: Final = "OWNER_APPROVED_EVIDENCE_CANDIDATE_NOT_READY"

EXPECTED_SOURCE_ROWS: Final = (
    (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        7943,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        3955,
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        4956,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        24993,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        11395,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        71458,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        10741,
        "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b",
    ),
)
EXPECTED_PREDECESSOR_ROWS: Final = (
    (
        PREDECESSOR_GENERATOR_PATH.as_posix(),
        66037,
        "0f6ad788aa90660775cb7852f7bb2ab7d8712d62bbf17dcaa651fe0fb8f6e06f",
    ),
    (
        POLICY_PATH.as_posix(),
        1064,
        "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989",
    ),
    (
        REPORT_PATH.as_posix(),
        9999,
        "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15",
    ),
)
EXPECTED_GOLD_SOURCE_ROWS: Final = (
    (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        7943,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        4956,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        71458,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        11395,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        24993,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "changes/st-0006/contracts/decision-gate-policy.v1.yaml",
        1064,
        "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989",
    ),
    (
        "changes/st-0006/gate-blocker-report.v1.yaml",
        9999,
        "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15",
    ),
    (
        "changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml",
        8680,
        "d07a2f3902dcd23f7ef9d46ecd3ab68162bcc28f2b3ad849bbe0e27891f502aa",
    ),
    (
        "changes/st-1701/contracts/mvp-business-decision-package.v1.yaml",
        10678,
        "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f",
    ),
    (
        "changes/st-1701/MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml",
        2098,
        "749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34",
    ),
    (
        "changes/st-1701/generated/canonical-revision-request.v1.md",
        4268,
        "6f6425ef97b53ca9a406b98ff5e9b2a64762adc5badc4569cc539afc53da7d04",
    ),
    (
        "changes/st-1701/README.md",
        10769,
        "da33c6c0720d83477de3e73dc794863f33d2f7bf0304f55a9b23eeb23100525e",
    ),
    (
        "scripts/build_st1701_business_inputs.py",
        64297,
        "cc89aabbebe241cd81d0f1247ef467b6f48e640ec6a3e8c8c3c4e570899a048b",
    ),
)
IMPLEMENTATION_DEPENDENCIES: Final = {
    "scripts/build_st1506_production_deployment.py": (
        "a57808e2c44feb51ebb4bcc1127c3aa0a64ef77d45d5c570207f66750b04d304"
    )
}
STANDING_DEVELOPMENT_AUTHORITY_PATH: Final = Path("AGENTS.md")
STANDING_DEVELOPMENT_AUTHORITY_BYTES: Final = 54_428
STANDING_DEVELOPMENT_AUTHORITY_SHA256: Final = (
    "a302eac0ebd61e352c94f9e07e715b41545bc29c1eae6c73f6115cf6ff3f2127"
)
CURRENT_DEVELOPMENT_SOURCE_OVERRIDES: Final = {
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        11_132,
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234",
    ),
}

EXPECTED_APPROVAL_DOCUMENT: Final = {
    "DESIGN_HANDOFF_APPROVAL_V1": {
        "story_id": "ST-1701",
        "handoff_uri": f"repo://{HANDOFF_PATH.as_posix()}",
        "handoff_sha256": HANDOFF_SHA256,
        "status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_authority": "ST1701_MVP_DECISION_PACKAGE_V1_ONLY",
        "approved_by": "repository_owner:jamozi",
        "approved_at": "2026-08-11T15:10:05Z",
        "approval_source": (
            "Exact handoff SHA-256 followed by explicit repository-owner approval "
            "in the connected Codex conversation."
        ),
        "approved_sha256_statement": f"ST-1701 handoff {HANDOFF_SHA256}",
        "canonical_reconciliation": "PASS_PROPOSAL_ONLY_NO_CANONICAL_MUTATION",
        "open_decisions": [],
        "boundaries": {
            "semantic_story_changes": ["ST-1701"],
            "canonical_files": "UNCHANGED",
            "st0006_blocker_state": "UNCHANGED",
            "existing_unresolved_registry": "PRESERVED_ACTIVE",
            "canonical_resolution_authority": "NONE",
            "cross_story_owner_inputs": (
                "INFORMATION_ONLY_NO_IMPLEMENTATION_OR_STATUS_EFFECT"
            ),
            "st1702_runtime_category_config": "NOT_AUTHORIZED",
            "st1702_golden_products": "NOT_AUTHORIZED",
            "od006_gold_evidence": "NOT_OBTAINED",
            "final_package_exact_owner_approval": "REQUIRED_AFTER_IMPLEMENTATION",
            "formal_tst_032": "NOT_EXECUTED",
            "external_account_or_domain_action": "NOT_AUTHORIZED",
            "live_provider_or_browser_action": "NOT_AUTHORIZED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
}

EXPECTED_FINAL_PACKAGE_APPROVAL_DOCUMENT: Final = {
    "MVP_BUSINESS_DECISION_PACKAGE_APPROVAL_V1": {
        "story_id": "ST-1701",
        "source_package_uri": DECISION_PACKAGE_URI,
        "source_package_sha256": APPROVED_DECISION_PACKAGE_SHA256,
        "source_package_bytes": APPROVED_DECISION_PACKAGE_BYTES,
        "status": FINAL_PACKAGE_APPROVAL_STATUS,
        "authority": FINAL_PACKAGE_APPROVAL_AUTHORITY,
        "approved_by": "repository_owner:jamozi",
        "approved_at": "2026-08-11T15:59:01Z",
        "approval_source": (
            "Exact source-package SHA-256 followed by explicit repository-owner "
            "approval in the connected Codex conversation."
        ),
        "approved_sha256_statement": (
            f"ST-1701 final package {APPROVED_DECISION_PACKAGE_SHA256}"
        ),
        "implementation_handoff": {
            "uri": f"repo://{HANDOFF_PATH.as_posix()}",
            "sha256": HANDOFF_SHA256,
        },
        "implementation_handoff_approval": {
            "uri": f"repo://{HANDOFF_APPROVAL_PATH.as_posix()}",
            "sha256": HANDOFF_APPROVAL_SHA256,
        },
        "open_decisions": [],
        "effective_boundary": {
            "source_package_internal_pending_field": (
                "PRESERVED_IMMUTABLE_PROPOSAL_STATE"
            ),
            "detached_exact_hash_approval": "EFFECTIVE",
            "canonical_revision_request": CANONICAL_REVISION_REQUEST_STATUS,
            "canonical_mutation_authority": "NONE",
            "canonical_open_decision_status": "UNCHANGED",
            "st0006_blocker_state": "UNCHANGED",
            "gate_state": "BLOCKED",
            "st1701_acceptance": "NOT_ACHIEVED",
            "st1702_ready": False,
        },
        "remaining_prerequisites": {
            "od005_alternate_reviewer_or_approved_exception": "NOT_SATISFIED",
            "od006_gold_evidence": "NOT_OBTAINED",
            "od006_domain_editor_acceptance": "NOT_OBTAINED",
            "formal_tst_032": "NOT_EXECUTED",
            "canonical_revision_approval_and_import": "NOT_EXECUTED",
        },
        "external_and_release_boundary": {
            "domain_purchase_or_control": "NOT_EXECUTED",
            "account_or_credential_setup": "NOT_EXECUTED",
            "browser_or_provider_action": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
}

EXPECTED_GOLD_HANDOFF_APPROVAL_DOCUMENT: Final = {
    "DESIGN_HANDOFF_APPROVAL_V1": {
        "story_id": "ST-1701",
        "handoff_uri": f"repo://{GOLD_HANDOFF_PATH.as_posix()}",
        "handoff_bytes": GOLD_HANDOFF_BYTES,
        "handoff_sha256": GOLD_HANDOFF_SHA256,
        "status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_authority": ("ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_V1_ONLY"),
        "approved_by": "repository_owner:jamozi",
        "approved_at": "2026-08-11T17:54:14Z",
        "approval_source": (
            "Exact handoff SHA-256 followed by explicit repository-owner approval "
            "in the connected Codex conversation."
        ),
        "owner_approval_statement": (
            f"ST-1701 Gold Evidence handoff {GOLD_HANDOFF_SHA256} を承認します"
        ),
        "approved_sha256_statement": (
            f"ST-1701 Gold Evidence handoff {GOLD_HANDOFF_SHA256}"
        ),
        "canonical_reconciliation": "PASS_PROPOSAL_ONLY_NO_CANONICAL_MUTATION",
        "open_decisions": [],
        "boundaries": {
            "semantic_story_changes": ["ST-1701"],
            "bounded_public_page_desk_research": ("AUTHORIZED_WITHIN_HANDOFF_LIMITS"),
            "field_level_gold_evidence_ledger": (
                "AUTHORIZED_PENDING_DOMAIN_EDITOR_REVIEW"
            ),
            "preapproval_generated_output": "GOLD_EVIDENCE_VALIDATION_V1_ONLY",
            "domain_editor_approval": ("REQUIRED_SEPARATE_EXACT_LEDGER_HASH_APPROVAL"),
            "resolution_candidates_before_domain_editor_approval": "FORBIDDEN",
            "canonical_revision_bundle_before_domain_editor_approval": "FORBIDDEN",
            "canonical_files": "UNCHANGED",
            "status_overlays": "UNCHANGED",
            "st0006_generated_truth": "UNCHANGED",
            "canonical_mutation_authority": "NONE",
            "st1607": "NOT_AUTHORIZED",
            "st1702_runtime_category_config": "NOT_AUTHORIZED",
            "st1702_golden_products": "NOT_AUTHORIZED",
            "formal_tst_032": "NOT_EXECUTED",
            "browser_login_api_or_credential_use": "NOT_AUTHORIZED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
}

EXPECTED_DECISION_DOCUMENT: Final = {
    "id": "RAOS-MVP-BUSINESS-DECISION-PACKAGE-001",
    "version": "1.0.0",
    "story_id": "ST-1701",
    "status": "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL",
    "classification": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
    "executable": False,
    "canonical_resolution_authority": "NONE",
}
EXPECTED_IMPLEMENTATION_AUTHORITY: Final = {
    "mode": "STRICT_STORY",
    "approved_story": "ST-1701",
    "handoff": {
        "uri": f"repo://{HANDOFF_PATH.as_posix()}",
        "bytes": HANDOFF_BYTES,
        "sha256": HANDOFF_SHA256,
    },
    "approval": {
        "uri": f"repo://{HANDOFF_APPROVAL_PATH.as_posix()}",
        "bytes": HANDOFF_APPROVAL_BYTES,
        "sha256": HANDOFF_APPROVAL_SHA256,
        "status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_authority": "ST1701_MVP_DECISION_PACKAGE_V1_ONLY",
        "canonical_reconciliation": "PASS_PROPOSAL_ONLY_NO_CANONICAL_MUTATION",
    },
    "open_decisions": [],
}
EXPECTED_FINAL_PACKAGE_APPROVAL: Final = {
    "required": True,
    "status": "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL",
    "approved_source_contract_sha256": None,
    "canonical_revision_evidence_authority": "NONE",
}
EXPECTED_CANONICAL_TRUTH_BOUNDARY: Final = {
    "canonical_open_decisions_document_status": "ACTIVE_UNCHANGED",
    "existing_unresolved_registry": "PRESERVED_ACTIVE",
    "scoped_unresolved_count": 7,
    "global_decision_count": 15,
    "global_unresolved_blocker_count": 14,
    "global_blocked_target_count": 6,
    "activation": "BLOCKED_UNRESOLVED_INPUTS",
    "gate_state": "BLOCKED",
    "st1701_acceptance": "NOT_ACHIEVED",
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_DECISION_EVIDENCE_BOUNDARY: Final = {
    "local_generation_and_tests": "IMPLEMENTATION_ONLY_NOT_FORMAL_VALIDATION",
    "exact_final_package_owner_approval": "PENDING",
    "od006_external_gold_evidence": "NOT_OBTAINED",
    "formal_tst_032": "NOT_EXECUTED",
    "live_evidence": "NOT_OBTAINED",
    "staging": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}
EXPECTED_DECISION_ACTION_BOUNDARY: Final = {
    "runtime_category_config": "NOT_CREATED",
    "golden_products": "NOT_CREATED",
    "external_actions": "NOT_AUTHORIZED",
    "browser_actions": "NOT_AUTHORIZED",
    "provider_actions": "NOT_AUTHORIZED",
    "account_or_credential_setup": "NOT_AUTHORIZED",
    "domain_purchase": "NOT_AUTHORIZED",
    "publication": "NOT_AUTHORIZED",
    "staging": "NOT_AUTHORIZED",
    "release": "NOT_AUTHORIZED",
    "production": "NOT_AUTHORIZED",
    "action_counts": {name: 0 for name in DECISION_ACTION_NAMES},
}

SCOPED_PENDING_CONDITIONS: Final = (
    {
        "id": "OD-002",
        "record_status": "EXECUTION_PENDING",
        "condition": (
            "domain purchase is NOT_EXECUTED, domain-control evidence is "
            "NOT_OBTAINED, and public activation remains FORBIDDEN"
        ),
    },
    {
        "id": "OD-005",
        "record_status": "PARTIAL",
        "condition": (
            "alternate_reviewer is absent; publication remains blocked unless "
            "a separately approved policy explicitly permits an exception"
        ),
    },
    {
        "id": "OD-006",
        "record_status": "EVIDENCE_PENDING",
        "condition": "closed external Gold Evidence has not been obtained",
    },
    {
        "id": "OD-006",
        "record_status": "EVIDENCE_PENDING",
        "condition": (
            "evidence requires at least 30 listings, 10 product families, and 5 shops"
        ),
    },
    {
        "id": "OD-006",
        "record_status": "EVIDENCE_PENDING",
        "condition": (
            "required cases are exact_duplicates, color_or_variant_differences, "
            "size_or_capacity_differences, missing_jan, bundles_and_set_count, "
            "and conflicting_fields"
        ),
    },
    {
        "id": "OD-006",
        "record_status": "EVIDENCE_PENDING",
        "condition": (
            "maximum false automatic merges is 0 and Domain Editor review "
            "remains required"
        ),
    },
    {
        "id": "OD-006",
        "record_status": "EVIDENCE_PENDING",
        "condition": "raw source links and observations are required",
    },
)
INFORMATIONAL_PENDING_CONDITIONS: Final = (
    {
        "id": "OD-003",
        "record_status": "EVIDENCE_PENDING",
        "condition": "Rakuten account and report sample are not prepared",
    },
    {
        "id": "OD-010",
        "record_status": "EXECUTION_PENDING",
        "condition": "Amazon Cognito account setup and activation are unexecuted",
    },
    {
        "id": "OD-011",
        "record_status": "PARTIAL",
        "condition": "alternate notification owner is absent",
    },
    {
        "id": "OD-012",
        "record_status": "PARTIAL",
        "condition": "exact public privacy text is not approved",
    },
    {
        "id": "OD-014",
        "record_status": "PARTIAL",
        "condition": "professional confirmation before Production is required",
    },
    {
        "id": "OD-015",
        "record_status": "EXECUTION_PENDING",
        "condition": "account and credential setup is NOT_EXECUTED",
    },
)

EXPECTED_BUSINESS_INPUTS: Final[dict[str, object]] = {
    "initial_category": None,
    "brand_name": None,
    "domain_name": None,
    "operator_identity": None,
    "primary_reviewer": None,
    "alternate_reviewer": None,
    "labor_hourly_cost": None,
    "product_identity_rules": None,
    "freshness_sla": None,
    "legal_review_boundary": None,
    "monthly_budget": None,
    "budget_currency": None,
    "automatic_stop_threshold": None,
    "resolution_payload": None,
    "approval_payload": None,
    "evidence_payload": None,
    "research_payload": None,
}
EXPECTED_SAFE_DEFAULTS: Final[dict[str, object]] = {
    "selected_values": "FORBIDDEN",
    "safe_defaults_are_resolutions": False,
    "synthetic_fixtures_only": True,
    "category_specific_implementation": "BLOCKED",
    "external_publication": "BLOCKED",
    "labor_cost_basis": "UNKNOWN",
    "human_review": "REQUIRED_UNCONFIGURED",
    "automatic_product_identity_merge": "DISABLED",
    "stale_content_visibility": "HIDDEN",
    "legal_judgment_by_ai_or_developer": "FORBIDDEN",
    "production": "DISABLED",
}
EXPECTED_ACTION_BOUNDARY: Final[dict[str, object]] = {
    "external_actions": "FORBIDDEN",
    "external_publication": "FORBIDDEN",
    "staging": "FORBIDDEN",
    "release": "FORBIDDEN",
    "production": "FORBIDDEN",
    "action_counts": {name: 0 for name in ACTION_NAMES},
}
EXPECTED_EVIDENCE_BOUNDARY: Final[dict[str, object]] = {
    "formal_tst_032": "NOT_EXECUTED",
    "human_approvals": "NOT_OBTAINED",
    "external_evidence": "NOT_OBTAINED",
    "canonical_status": "UNCHANGED",
    "st_1701_acceptance_achieved": False,
    "local_evidence": "IMPLEMENTATION_ONLY_NOT_FORMAL_VALIDATION",
}
EXPECTED_DOWNSTREAM_BOUNDARY: Final[dict[str, object]] = {
    "st_1702_ready": False,
    "readiness_status": "BLOCKED_BY_ST_1701_ACCEPTANCE",
    "publication_ready": False,
    "release_ready": False,
    "production_ready": False,
}


class BusinessInputsError(RuntimeError):
    """Sanitized ST-1701 owner failure."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"ST1701_ERROR code={code} field={field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise BusinessInputsError(code, field) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_TYPE", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_TYPE", field)
    return value


def _exact_mapping(
    value: object, expected: Mapping[str, object], field: str
) -> Mapping[str, Any]:
    observed = _mapping(value, field)
    if tuple(observed.keys()) != tuple(expected.keys()) or observed != expected:
        _fail("CONTRACT_SECTION_DRIFT", field)
    return observed


def _exact_tree(value: object, expected: object, field: str) -> None:
    """Require exact ordered mappings, exact lists, and exact scalar types."""

    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        if tuple(observed.keys()) != tuple(expected.keys()):
            _fail("CONTRACT_SECTION_DRIFT", field)
        for key, expected_value in expected.items():
            _exact_tree(observed[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        observed_list = _list(value, field)
        expected_list = _list(expected, field)
        if len(observed_list) != len(expected_list):
            _fail("CONTRACT_SECTION_DRIFT", field)
        for index, expected_value in enumerate(expected_list):
            _exact_tree(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        _fail("CONTRACT_SECTION_DRIFT", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def evaluate_od006_synthetic_pair(
    left: Mapping[str, object], right: Mapping[str, object]
) -> str:
    """Exercise the approved OD-006 exact-match rule on synthetic fixtures only."""

    for field in OD006_REQUIRED_FIELDS:
        left_value = left.get(field)
        right_value = right.get(field)
        if left_value is None or right_value is None:
            return "HUMAN_REVIEW"
        if left_value == "" or right_value == "":
            return "HUMAN_REVIEW"
        if field == "set_count" and (
            type(left_value) is not int
            or type(right_value) is not int
            or left_value <= 0
            or right_value <= 0
        ):
            return "HUMAN_REVIEW"
        if field != "set_count" and (
            type(left_value) is not str or type(right_value) is not str
        ):
            return "HUMAN_REVIEW"
        if type(left_value) is not type(right_value) or left_value != right_value:
            return "HUMAN_REVIEW"

    left_jan = left.get("jan")
    right_jan = right.get("jan")
    if left_jan is None and right_jan is None:
        return "EXACT_MATCH_ONLY"
    if type(left_jan) is not str or type(right_jan) is not str:
        return "HUMAN_REVIEW"
    if (
        not _valid_synthetic_jan(left_jan)
        or not _valid_synthetic_jan(right_jan)
        or left_jan != right_jan
    ):
        return "HUMAN_REVIEW"
    return "EXACT_MATCH_ONLY"


def evaluate_od006_gold_pair(
    left: Mapping[str, object], right: Mapping[str, object]
) -> str:
    """Project the approved exact identity rule into Gold report vocabulary."""

    if evaluate_od006_synthetic_pair(left, right) == "EXACT_MATCH_ONLY":
        return "AUTOMATIC_MERGE"
    return "HUMAN_REVIEW"


def gold_unordered_pair_count(listing_count: int) -> int:
    """Return the exact unordered-pair population for a closed listing count."""

    if type(listing_count) is not int or listing_count < 0:
        _fail("INVALID_COUNT", "gold.pair_population.listing_count")
    return listing_count * (listing_count - 1) // 2


def _valid_synthetic_jan(value: str) -> bool:
    """Validate the standard JAN/EAN-8 or JAN/EAN-13 check digit."""

    if SYNTHETIC_JAN_PATTERN.fullmatch(value) is None:
        return False
    digits = [ord(character) - ord("0") for character in value]
    weighted_sum = sum(
        digit * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(digits[:-1]))
    )
    expected_check_digit = (10 - (weighted_sum % 10)) % 10
    return digits[-1] == expected_check_digit


def _read(root: Path, relative: Path, field: str) -> bytes:
    path = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        return path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)


def _repository_path_state(root: Path, relative: Path, field: str) -> str:
    """Return ABSENT or REGULAR without following any repository symlink."""

    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)
    current = base._real_repository_root(root)  # noqa: SLF001
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return "ABSENT"
        except OSError:
            _fail("FILE_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_ANCESTOR", field)
    target = current / relative.name
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return "ABSENT"
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_FILE_TYPE", field)
    return "REGULAR"


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _verify_rows(
    root: Path,
    rows: object,
    expected: Sequence[tuple[str, int, str]],
    field: str,
) -> None:
    observed_rows = _list(rows, field)
    if len(observed_rows) != len(expected):
        _fail("INVENTORY_DRIFT", field)
    for index, (raw, expected_row) in enumerate(
        zip(observed_rows, expected, strict=True)
    ):
        row = _mapping(raw, f"{field}[{index}]")
        if tuple(row.keys()) != ("uri", "bytes", "sha256"):
            _fail("INVENTORY_SCHEMA_DRIFT", f"{field}[{index}]")
        relative, size, digest = expected_row
        if row != {"uri": f"repo://{relative}", "bytes": size, "sha256": digest}:
            _fail("INVENTORY_DRIFT", f"{field}[{index}]")
        content = _read(root, Path(relative), f"{field}.input")
        current_override = CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.get(relative)
        if current_override is None:
            if len(content) != size or _sha256(content) != digest:
                _fail("INPUT_HASH_DRIFT", field)
            continue
        current_size, current_digest = current_override
        if len(content) != current_size or _sha256(content) != current_digest:
            _fail("CURRENT_DEVELOPMENT_SOURCE_DRIFT", field)


def _validate_current_development_authority(root: Path) -> None:
    content = _read(
        root,
        STANDING_DEVELOPMENT_AUTHORITY_PATH,
        "current_development.authority_source",
    )
    if (
        len(content) != STANDING_DEVELOPMENT_AUTHORITY_BYTES
        or _sha256(content) != STANDING_DEVELOPMENT_AUTHORITY_SHA256
    ):
        _fail(
            "CURRENT_DEVELOPMENT_AUTHORITY_DRIFT",
            "current_development.authority_source",
        )


def _validate_implementation_dependencies(root: Path) -> None:
    for relative, digest in IMPLEMENTATION_DEPENDENCIES.items():
        if _sha256(_read(root, Path(relative), "implementation.input")) != digest:
            _fail("IMPLEMENTATION_DEPENDENCY_DRIFT", "implementation")


def _validate_predecessor(
    contract: Mapping[str, Any], root: Path
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    binding = _mapping(contract["predecessor_binding"], "predecessor_binding")
    if tuple(binding.keys()) != (
        "story_id",
        "owner_check",
        "generator",
        "policy",
        "report",
        "required_semantics",
    ):
        _fail("PREDECESSOR_SCHEMA_DRIFT", "predecessor_binding")
    if binding["story_id"] != "ST-0006":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.story_id")
    if binding["owner_check"] != "scripts.build_st0006_decision_gates.check_generated":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.owner_check")
    for key, expected in zip(
        ("generator", "policy", "report"), EXPECTED_PREDECESSOR_ROWS, strict=True
    ):
        relative, size, digest = expected
        _exact_mapping(
            binding[key],
            {"uri": f"repo://{relative}", "bytes": size, "sha256": digest},
            f"predecessor.{key}",
        )
        content = _read(root, Path(relative), f"predecessor.{key}")
        if len(content) != size or _sha256(content) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", f"predecessor.{key}")
    _exact_mapping(
        binding["required_semantics"],
        {
            "overall_open_decision_check": "BLOCKED",
            "global_decision_count": 15,
            "global_unresolved_blocker_count": 14,
            "global_blocked_target_count": 6,
            "target_mapping": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
            "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
            "safe_default_interpretation": "SAFE_FALLBACK_NOT_RESOLUTION",
            "clear_does_not_imply_gate_pass": True,
        },
        "predecessor.required_semantics",
    )
    policy = _load_yaml(root, POLICY_PATH, "predecessor.policy")
    report = _load_yaml(root, REPORT_PATH, "predecessor.report")
    policy_mapping = _mapping(policy.get("mapping"), "policy.mapping")
    if policy_mapping != {
        "targets": list(BLOCKED_TARGETS),
        "active_blocker": "blocking=true AND status!=RESOLVED",
        "target_policy": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
        "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
        "default_behavior_interpretation": "SAFE_FALLBACK_NOT_RESOLUTION",
        "clear_means_gate_pass": False,
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "policy.mapping")
    if _mapping(report.get("counts"), "report.counts") != {
        "decisions": 15,
        "resolved": 0,
        "unresolved": 15,
        "blocking": 14,
        "unresolved_blocking": 14,
        "unresolved_nonblocking": 1,
        "blocked_targets": 6,
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "report.counts")
    if report.get("overall_open_decision_check") != "BLOCKED":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "report.status")
    decisions = [
        _mapping(row, "report.decisions")
        for row in _list(report.get("decisions"), "report.decisions")
    ]
    if root.resolve() == REPO_ROOT.resolve():
        try:
            predecessor.check_generated()
        except Exception:
            _fail("PREDECESSOR_OWNER_CHECK_FAILED", "predecessor")
    return report, decisions


def _expected_decisions(
    report_decisions: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    by_id = {str(row["id"]): row for row in report_decisions}
    if (
        tuple(identifier for identifier in by_id if identifier in SCOPED_IDS)
        != SCOPED_IDS
    ):
        _fail("SCOPED_ORDER_DRIFT", "decisions")
    expected: list[dict[str, object]] = []
    for identifier in SCOPED_IDS:
        source = by_id.get(identifier)
        if source is None:
            _fail("SCOPED_INVENTORY_DRIFT", "decisions")
        expected.append(
            {
                "id": identifier,
                "topic": source["topic"],
                "source_status": source["source_status"],
                "required_by": source["required_by"],
                "owner": source["owner"],
                "decision_needed": source["decision_needed"],
                "default_behavior": source["default_behavior"],
                "blocking": True,
                "resolution_state": "UNRESOLVED",
                "active_blocker": True,
                "blocked_targets": list(BLOCKED_TARGETS),
                "safe_default_is_resolution": False,
                "selected_value": None,
                "resolution_payload": "FORBIDDEN_IN_V1",
            }
        )
    if expected[3]["source_status"] != "EXTERNAL_EVIDENCE_REQUIRED":
        _fail("SCOPED_STATUS_DRIFT", "decisions.OD-006")
    if any(
        row["source_status"] != "HUMAN_DECISION_REQUIRED"
        for index, row in enumerate(expected)
        if index != 3
    ):
        _fail("SCOPED_STATUS_DRIFT", "decisions")
    return expected


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact_mapping(
        contract["document"],
        {
            "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "classification": ("SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY"),
            "executable": False,
            "canonical_acceptance_achieved": False,
        },
        "document",
    )
    _verify_rows(root, contract["sources"], EXPECTED_SOURCE_ROWS, "sources")
    _validate_current_development_authority(root)
    _validate_implementation_dependencies(root)
    _report, report_decisions = _validate_predecessor(contract, root)
    _exact_mapping(
        contract["scope"],
        {
            "decision_ids": list(SCOPED_IDS),
            "decision_count": 7,
            "resolved_count": 0,
            "unresolved_count": 7,
            "active_blocker_count": 7,
            "inventory_kind": "EXACT_ORDERED_ST0006_SUBSET",
            "source_facts_interpretation": "OPAQUE_NO_DERIVATION",
            "global_counts_preserved": True,
        },
        "scope",
    )
    decisions = _list(contract["decisions"], "decisions")
    if decisions != _expected_decisions(report_decisions):
        _fail("DECISION_PROJECTION_DRIFT", "decisions")
    _exact_mapping(
        contract["business_inputs"], EXPECTED_BUSINESS_INPUTS, "business_inputs"
    )
    _exact_mapping(contract["safe_defaults"], EXPECTED_SAFE_DEFAULTS, "safe_defaults")
    _exact_mapping(
        contract["activation"],
        {"enabled": False, "status": "BLOCKED_UNRESOLVED_INPUTS"},
        "activation",
    )
    expected_gates = [
        {"gate_id": gate, "status": "BLOCKED", "blocker_count": 7} for gate in GATE_IDS
    ]
    if _list(contract["gates"], "gates") != expected_gates:
        _fail("GATE_BOUNDARY_DRIFT", "gates")
    action_boundary = _exact_mapping(
        contract["action_boundary"], EXPECTED_ACTION_BOUNDARY, "action_boundary"
    )
    for key, value in _mapping(
        action_boundary["action_counts"], "action_counts"
    ).items():
        if type(value) is not int or value != 0:
            _fail("NONZERO_ACTION", f"action_counts.{key}")
    _exact_mapping(
        contract["evidence_boundary"],
        EXPECTED_EVIDENCE_BOUNDARY,
        "evidence_boundary",
    )
    _exact_mapping(
        contract["downstream_boundary"],
        EXPECTED_DOWNSTREAM_BOUNDARY,
        "downstream_boundary",
    )
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def _authority_documents(
    root: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    handoff_bytes = _read(root, HANDOFF_PATH, "authority.handoff")
    if len(handoff_bytes) != HANDOFF_BYTES or _sha256(handoff_bytes) != HANDOFF_SHA256:
        _fail("AUTHORITY_HASH_DRIFT", "authority.handoff")
    approval_bytes = _read(root, HANDOFF_APPROVAL_PATH, "authority.approval")
    if (
        len(approval_bytes) != HANDOFF_APPROVAL_BYTES
        or _sha256(approval_bytes) != HANDOFF_APPROVAL_SHA256
    ):
        _fail("AUTHORITY_HASH_DRIFT", "authority.approval")

    handoff_wrapper = _load_yaml(root, HANDOFF_PATH, "authority.handoff")
    if tuple(handoff_wrapper.keys()) != ("DESIGN_HANDOFF_V1",):
        _fail("AUTHORITY_SCHEMA_DRIFT", "authority.handoff")
    handoff = _mapping(handoff_wrapper["DESIGN_HANDOFF_V1"], "authority.handoff")
    if tuple(handoff.keys()) != (
        "document_version",
        "proposal_status",
        "approved_story",
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
        "approval",
    ):
        _fail("AUTHORITY_SCHEMA_DRIFT", "authority.handoff")
    if (
        handoff["document_version"] != 1
        or handoff["approved_story"] != "ST-1701"
        or handoff["open_decisions"] != []
    ):
        _fail("AUTHORITY_SEMANTIC_DRIFT", "authority.handoff")
    decision = _mapping(handoff["decision"], "authority.handoff.decision")
    if tuple(decision.keys()) != (
        "authority_model",
        "record_status_model",
        "scoped_decisions",
        "informational_cross_story_owner_inputs",
        "implementation_artifacts",
        "suitcase_candidate_boundary",
        "canonical_revision_request",
    ):
        _fail("AUTHORITY_SCHEMA_DRIFT", "authority.handoff.decision")

    approval_wrapper = _load_yaml(root, HANDOFF_APPROVAL_PATH, "authority.approval")
    _exact_tree(approval_wrapper, EXPECTED_APPROVAL_DOCUMENT, "authority.approval")
    approval = _mapping(
        approval_wrapper["DESIGN_HANDOFF_APPROVAL_V1"], "authority.approval"
    )
    if approval["open_decisions"] != []:
        _fail("AUTHORITY_SEMANTIC_DRIFT", "authority.approval.open_decisions")
    return handoff, approval


def _gold_authority_documents(
    root: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Validate the exact Gold handoff and its detached implementation approval."""

    # The Gold slice is additive: its authority never replaces the approved MVP
    # package authority or detached final-package approval.
    _authority_documents(root)
    _final_package_approval_document(root)

    handoff_bytes = _read(root, GOLD_HANDOFF_PATH, "gold_authority.handoff")
    if (
        len(handoff_bytes) != GOLD_HANDOFF_BYTES
        or _sha256(handoff_bytes) != GOLD_HANDOFF_SHA256
    ):
        _fail("AUTHORITY_HASH_DRIFT", "gold_authority.handoff")
    approval_bytes = _read(root, GOLD_HANDOFF_APPROVAL_PATH, "gold_authority.approval")
    if (
        len(approval_bytes) != GOLD_HANDOFF_APPROVAL_BYTES
        or _sha256(approval_bytes) != GOLD_HANDOFF_APPROVAL_SHA256
    ):
        _fail("AUTHORITY_HASH_DRIFT", "gold_authority.approval")

    handoff_wrapper = _load_yaml(root, GOLD_HANDOFF_PATH, "gold_authority.handoff")
    if tuple(handoff_wrapper.keys()) != ("DESIGN_HANDOFF_V1",):
        _fail("AUTHORITY_SCHEMA_DRIFT", "gold_authority.handoff")
    handoff = _mapping(handoff_wrapper["DESIGN_HANDOFF_V1"], "gold_authority.handoff")
    if tuple(handoff.keys()) != (
        "document_version",
        "proposal_status",
        "approved_story",
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
        _fail("AUTHORITY_SCHEMA_DRIFT", "gold_authority.handoff")
    if (
        handoff["document_version"] != 1
        or handoff["proposal_status"] != "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL"
        or handoff["approved_story"] != "ST-1701"
        or handoff["open_decisions"] != []
    ):
        _fail("AUTHORITY_SEMANTIC_DRIFT", "gold_authority.handoff")
    expected_source_refs = [
        {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
        for path, size, digest in EXPECTED_GOLD_SOURCE_ROWS
    ]
    _exact_tree(
        handoff["source_design_refs"],
        expected_source_refs,
        "gold_authority.handoff.source_design_refs",
    )
    # README and generator are deliberate preimplementation anchors. Every
    # earlier row is immutable authority/predecessor input and stays live-bound.
    for path, size, digest in EXPECTED_GOLD_SOURCE_ROWS[:-2]:
        content = _read(root, Path(path), "gold_authority.predecessor")
        if len(content) != size or _sha256(content) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "gold_authority.predecessor")
    decision = _mapping(handoff["decision"], "gold_authority.handoff.decision")
    if tuple(decision.keys()) != (
        "authority_model",
        "od005_single_reviewer_policy",
        "od006_collection_policy",
        "ledger_contract",
        "identity_policy",
        "pair_evaluation",
        "domain_editor_approval",
        "generator_contract",
        "resolution_candidate_contract",
        "canonical_revision_bundle",
    ):
        _fail("AUTHORITY_SCHEMA_DRIFT", "gold_authority.handoff.decision")

    approval_wrapper = _load_yaml(
        root, GOLD_HANDOFF_APPROVAL_PATH, "gold_authority.approval"
    )
    _exact_tree(
        approval_wrapper,
        EXPECTED_GOLD_HANDOFF_APPROVAL_DOCUMENT,
        "gold_authority.approval",
    )
    approval = _mapping(
        approval_wrapper["DESIGN_HANDOFF_APPROVAL_V1"],
        "gold_authority.approval",
    )
    if approval["open_decisions"] != []:
        _fail("AUTHORITY_SEMANTIC_DRIFT", "gold_authority.approval.open_decisions")
    return handoff, approval


def load_gold_authority(
    root: Path = REPO_ROOT,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load only the exact additive Gold implementation authority."""

    return _gold_authority_documents(root)


def validate_final_package_approval(
    document: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    """Validate the detached exact-hash approval and its immutable source."""

    _authority_documents(root)
    _exact_tree(
        document,
        EXPECTED_FINAL_PACKAGE_APPROVAL_DOCUMENT,
        "authority.final_package_approval",
    )
    source_bytes = _read(
        root,
        DECISION_PACKAGE_PATH,
        "authority.final_package_approval.source_package",
    )
    if (
        len(source_bytes) != APPROVED_DECISION_PACKAGE_BYTES
        or _sha256(source_bytes) != APPROVED_DECISION_PACKAGE_SHA256
    ):
        _fail(
            "APPROVED_SOURCE_DRIFT",
            "authority.final_package_approval.source_package",
        )
    approval = _mapping(
        document["MVP_BUSINESS_DECISION_PACKAGE_APPROVAL_V1"],
        "authority.final_package_approval",
    )
    if approval["open_decisions"] != []:
        _fail(
            "AUTHORITY_SEMANTIC_DRIFT",
            "authority.final_package_approval.open_decisions",
        )
    return approval


def _final_package_approval_document(root: Path) -> Mapping[str, Any]:
    approval_bytes = _read(
        root, FINAL_PACKAGE_APPROVAL_PATH, "authority.final_package_approval"
    )
    if (
        len(approval_bytes) != FINAL_PACKAGE_APPROVAL_BYTES
        or _sha256(approval_bytes) != FINAL_PACKAGE_APPROVAL_SHA256
    ):
        _fail("AUTHORITY_HASH_DRIFT", "authority.final_package_approval")
    return validate_final_package_approval(
        _load_yaml(
            root,
            FINAL_PACKAGE_APPROVAL_PATH,
            "authority.final_package_approval",
        ),
        root,
    )


def load_final_package_approval(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    """Load the detached approval only after validating every bound authority."""

    return _final_package_approval_document(root)


def _effective_final_package_approval(
    root: Path, provided: Mapping[str, Any] | None
) -> Mapping[str, Any]:
    loaded = load_final_package_approval(root)
    if provided is not None:
        _exact_tree(
            provided,
            loaded,
            "authority.final_package_approval.provided",
        )
    return loaded


def _expected_implementation_boundary(
    handoff: Mapping[str, Any],
) -> dict[str, object]:
    decision = _mapping(handoff["decision"], "authority.handoff.decision")
    return {
        "existing_unresolved_registry": {
            "source_uri": SOURCE_URI,
            "source_sha256": (
                "d07a2f3902dcd23f7ef9d46ecd3ab68162bcc28f2b3ad849bbe0e27891f502aa"
            ),
            "generated_uri": f"repo://{REFERENCE_PATH.as_posix()}",
            "generated_sha256": (
                "22394f5b37d3fe90cc5c31aff47be0d0f31f061398bbd9d90b4030bcb050c33b"
            ),
            "preserve": True,
            "canonical_counts_and_blockers_unchanged": True,
        },
        "suitcase_candidate_boundary": decision["suitcase_candidate_boundary"],
        "canonical_revision_request": decision["canonical_revision_request"],
    }


def validate_decision_package(
    contract: Mapping[str, Any],
    root: Path = REPO_ROOT,
    *,
    handoff: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != DECISION_PACKAGE_TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "decision_package")
    approved_handoff = handoff
    if approved_handoff is None:
        approved_handoff, _approval = _authority_documents(root)
    decision = _mapping(approved_handoff["decision"], "authority.handoff.decision")

    _exact_tree(contract["document"], EXPECTED_DECISION_DOCUMENT, "package.document")
    _exact_tree(
        contract["implementation_authority"],
        EXPECTED_IMPLEMENTATION_AUTHORITY,
        "package.implementation_authority",
    )
    _exact_tree(
        contract["final_package_approval"],
        EXPECTED_FINAL_PACKAGE_APPROVAL,
        "package.final_package_approval",
    )
    _exact_tree(
        contract["authority_model"],
        decision["authority_model"],
        "package.authority_model",
    )
    _exact_tree(
        contract["record_status_model"],
        decision["record_status_model"],
        "package.record_status_model",
    )
    _exact_tree(
        contract["canonical_truth_boundary"],
        EXPECTED_CANONICAL_TRUTH_BOUNDARY,
        "package.canonical_truth_boundary",
    )
    _exact_tree(
        contract["scoped_decisions"],
        decision["scoped_decisions"],
        "package.scoped_decisions",
    )
    _exact_tree(
        contract["informational_cross_story_owner_inputs"],
        decision["informational_cross_story_owner_inputs"],
        "package.informational_cross_story_owner_inputs",
    )
    _exact_tree(
        contract["implementation_boundary"],
        _expected_implementation_boundary(approved_handoff),
        "package.implementation_boundary",
    )
    _exact_tree(
        contract["evidence_boundary"],
        EXPECTED_DECISION_EVIDENCE_BOUNDARY,
        "package.evidence_boundary",
    )
    _exact_tree(
        contract["action_boundary"],
        EXPECTED_DECISION_ACTION_BOUNDARY,
        "package.action_boundary",
    )

    scoped = _list(contract["scoped_decisions"], "package.scoped_decisions")
    if tuple(_mapping(row, "package.scoped_decisions")["id"] for row in scoped) != (
        SCOPED_IDS
    ):
        _fail("SCOPED_ORDER_DRIFT", "package.scoped_decisions")
    informational = _mapping(
        contract["informational_cross_story_owner_inputs"],
        "package.informational_cross_story_owner_inputs",
    )
    informational_rows = _list(
        informational["rows"], "package.informational_cross_story_owner_inputs.rows"
    )
    if tuple(
        _mapping(row, "package.informational")["id"] for row in informational_rows
    ) != (INFORMATIONAL_IDS):
        _fail("INFORMATIONAL_ORDER_DRIFT", "package.informational")
    observed_statuses = {
        str(_mapping(row, "package.row")["record_status"])
        for row in (*scoped, *informational_rows)
    }
    if not observed_statuses <= set(RECORD_STATUSES):
        _fail("RECORD_STATUS_DRIFT", "package.record_status")
    if observed_statuses & set(FORBIDDEN_RECORD_STATUSES):
        _fail("FORBIDDEN_STATUS", "package.record_status")
    action_counts = _mapping(
        _mapping(contract["action_boundary"], "package.action_boundary")[
            "action_counts"
        ],
        "package.action_boundary.action_counts",
    )
    if any(type(value) is not int or value != 0 for value in action_counts.values()):
        _fail("NONZERO_ACTION", "package.action_boundary.action_counts")
    return contract


def load_decision_package(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    handoff, _approval = _authority_documents(root)
    _final_package_approval_document(root)
    return validate_decision_package(
        _load_yaml(root, DECISION_PACKAGE_PATH, "decision_package"),
        root,
        handoff=handoff,
    )


def _bound_decision_package(
    provided: Mapping[str, Any], root: Path
) -> Mapping[str, Any]:
    loaded = load_decision_package(root)
    _exact_tree(provided, loaded, "projection.decision_package")
    return loaded


def _bound_unresolved_contract(
    provided: Mapping[str, Any], root: Path
) -> Mapping[str, Any]:
    loaded = load_contract(root)
    _exact_tree(provided, loaded, "projection.unresolved_contract")
    return loaded


def reference_document(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, object]:
    contract = _bound_unresolved_contract(contract, root)
    return {
        "document": {
            "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-REGISTRY-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "classification": ("SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY"),
            "authority": "NON_AUTHORITATIVE",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "executable": False,
            "canonical_acceptance_achieved": False,
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "predecessor_binding": contract["predecessor_binding"],
        "registry": {
            **dict(_mapping(contract["scope"], "scope")),
            "global_decision_count": 15,
            "global_unresolved_blocker_count": 14,
            "global_blocked_target_count": 6,
            "blocked_targets": list(BLOCKED_TARGETS),
            "decisions": contract["decisions"],
        },
        "business_inputs": contract["business_inputs"],
        "safe_defaults": contract["safe_defaults"],
        "activation": contract["activation"],
        "gates": contract["gates"],
        "action_boundary": contract["action_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "downstream_boundary": contract["downstream_boundary"],
        "prohibited_interpretations": [
            "SAFE_DEFAULT_IS_NOT_A_DECISION",
            "UNRESOLVED_REGISTRY_IS_NOT_APPROVAL",
            "LOCAL_TESTS_ARE_NOT_FORMAL_TST_032",
            "ZERO_ACTIONS_ARE_NOT_ST_1701_ACCEPTANCE",
            "SCOPED_SEVEN_DO_NOT_CLEAR_OTHER_GLOBAL_BLOCKERS",
            "NO_CATEGORY_PUBLICATION_RELEASE_OR_PRODUCTION_VALUE_MAY_BE_INFERRED",
        ],
    }


def decision_read_model(
    package: Mapping[str, Any],
    unresolved_contract: Mapping[str, Any],
    root: Path = REPO_ROOT,
    *,
    final_approval: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    package = _bound_decision_package(package, root)
    unresolved_contract = _bound_unresolved_contract(unresolved_contract, root)
    effective_approval = _effective_final_package_approval(root, final_approval)
    unresolved_rows = {
        str(_mapping(row, "unresolved.decisions")["id"]): _mapping(
            row, "unresolved.decisions"
        )
        for row in _list(unresolved_contract["decisions"], "unresolved.decisions")
    }
    scoped_rows: list[dict[str, object]] = []
    for candidate_value in _list(
        package["scoped_decisions"], "package.scoped_decisions"
    ):
        candidate = _mapping(candidate_value, "package.scoped_decisions")
        identifier = str(candidate["id"])
        canonical = unresolved_rows.get(identifier)
        if canonical is None:
            _fail("SCOPED_INVENTORY_DRIFT", "package.scoped_decisions")
        scoped_rows.append(
            {
                "id": identifier,
                "canonical_truth": {
                    "source_status": canonical["source_status"],
                    "resolution_state": canonical["resolution_state"],
                    "active_blocker": canonical["active_blocker"],
                    "selected_value": canonical["selected_value"],
                    "blocked_targets": canonical["blocked_targets"],
                },
                "owner_decision_candidate": candidate,
            }
        )

    package_bytes = _read(root, DECISION_PACKAGE_PATH, "decision_package")
    return {
        "document": {
            "id": "RAOS-MVP-BUSINESS-DECISION-PACKAGE-READ-MODEL-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "classification": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
            "authority": FINAL_PACKAGE_APPROVAL_AUTHORITY,
            "status": CANONICAL_REVISION_REQUEST_STATUS,
            "executable": False,
            "canonical_resolution_authority": "NONE",
            "source_contract": DECISION_PACKAGE_URI,
            "source_contract_sha256": _sha256(package_bytes),
            "source_contract_internal_status": _mapping(
                package["document"], "package.document"
            )["status"],
            "approved_handoff": f"repo://{HANDOFF_PATH.as_posix()}",
            "approved_handoff_sha256": HANDOFF_SHA256,
            "handoff_approval": f"repo://{HANDOFF_APPROVAL_PATH.as_posix()}",
            "handoff_approval_sha256": HANDOFF_APPROVAL_SHA256,
            "detached_final_package_approval": (
                f"repo://{FINAL_PACKAGE_APPROVAL_PATH.as_posix()}"
            ),
            "detached_final_package_approval_sha256": (FINAL_PACKAGE_APPROVAL_SHA256),
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "serialization": "UTF8_JSON_INDENT_2_TRAILING_NEWLINE",
        },
        "final_package_approval": {
            "source_package_internal": package["final_package_approval"],
            "detached_effective": {
                "uri": f"repo://{FINAL_PACKAGE_APPROVAL_PATH.as_posix()}",
                "bytes": FINAL_PACKAGE_APPROVAL_BYTES,
                "sha256": FINAL_PACKAGE_APPROVAL_SHA256,
                "status": effective_approval["status"],
                "authority": effective_approval["authority"],
                "approved_by": effective_approval["approved_by"],
                "approved_at": effective_approval["approved_at"],
                "source_package_uri": effective_approval["source_package_uri"],
                "source_package_bytes": effective_approval["source_package_bytes"],
                "source_package_sha256": effective_approval["source_package_sha256"],
            },
            "effective_boundary": effective_approval["effective_boundary"],
            "remaining_prerequisites": effective_approval["remaining_prerequisites"],
            "external_and_release_boundary": effective_approval[
                "external_and_release_boundary"
            ],
        },
        "authority_model": package["authority_model"],
        "canonical_truth_boundary": package["canonical_truth_boundary"],
        "record_status_model": package["record_status_model"],
        "scoped_decisions": scoped_rows,
        "informational_cross_story_owner_inputs": package[
            "informational_cross_story_owner_inputs"
        ],
        "pending_conditions": {
            "scoped": [dict(row) for row in SCOPED_PENDING_CONDITIONS],
            "informational_no_status_effect": [
                dict(row) for row in INFORMATIONAL_PENDING_CONDITIONS
            ],
        },
        "implementation_boundary": package["implementation_boundary"],
        "evidence_boundary": {
            "source_package_internal": package["evidence_boundary"],
            "effective_final_package_owner_approval": {
                "status": effective_approval["status"],
                "authority": effective_approval["authority"],
                "approval_sha256": FINAL_PACKAGE_APPROVAL_SHA256,
            },
            "canonical_revision_request_readiness": "NOT_READY",
            "remaining_prerequisites": effective_approval["remaining_prerequisites"],
        },
        "action_boundary": package["action_boundary"],
        "downstream_truth": unresolved_contract["downstream_boundary"],
        "prohibited_effects": [
            "NO_CANONICAL_FILE_MUTATION",
            "NO_CANONICAL_DECISION_STATUS_CHANGE",
            "NO_GATE_OR_STATUS_PROMOTION",
            "NO_ST1702_RUNTIME_CATEGORY_CONFIGURATION",
            "NO_ST1702_GOLDEN_PRODUCTS",
            "NO_EXTERNAL_OR_LIVE_ACTION",
        ],
    }


def _pending_condition_lines(
    package: Mapping[str, Any],
    conditions: Sequence[Mapping[str, str]],
    *,
    informational: bool,
) -> list[str]:
    if informational:
        inventory = _mapping(
            package["informational_cross_story_owner_inputs"],
            "package.informational_cross_story_owner_inputs",
        )
        rows = _list(inventory["rows"], "package.informational.rows")
    else:
        rows = _list(package["scoped_decisions"], "package.scoped_decisions")
    by_id = {
        str(_mapping(row, "package.pending.row")["id"]): _mapping(
            row, "package.pending.row"
        )
        for row in rows
    }
    lines: list[str] = []
    for condition in conditions:
        identifier = condition["id"]
        row = by_id.get(identifier)
        if row is None or row.get("record_status") != condition["record_status"]:
            _fail("PENDING_CONDITION_DRIFT", "canonical_revision_request")
        lines.append(
            f"- `{identifier}` / `{condition['record_status']}`: "
            f"{condition['condition']}."
        )
    return lines


def canonical_revision_request_bytes(
    package: Mapping[str, Any],
    root: Path = REPO_ROOT,
    *,
    final_approval: Mapping[str, Any] | None = None,
) -> bytes:
    package = _bound_decision_package(package, root)
    effective_approval = _effective_final_package_approval(root, final_approval)
    package_sha256 = _sha256(
        _read(root, DECISION_PACKAGE_PATH, "canonical_revision_request.source")
    )
    scoped = _list(package["scoped_decisions"], "package.scoped_decisions")
    candidate_lines = [
        f"- `{row['id']}`: `{row['record_status']}`"
        for value in scoped
        for row in (_mapping(value, "package.scoped_decisions"),)
    ]
    scoped_pending = _pending_condition_lines(
        package, SCOPED_PENDING_CONDITIONS, informational=False
    )
    informational_pending = _pending_condition_lines(
        package, INFORMATIONAL_PENDING_CONDITIONS, informational=True
    )
    lines = [
        "# ST-1701 canonical-revision request proposal",
        "",
        f"Authority: `{effective_approval['authority']}`",
        "Readiness: `NOT_READY`",
        "Canonical mutation or status-change authority: `NONE`",
        "",
        "This deterministic request is generated from the exact-hash, "
        "owner-approved, non-authoritative decision candidate. Its authority is "
        "limited to canonical-revision evidence candidacy. It does not change a "
        "canonical file, decision status, Gate, Story status, or downstream "
        "readiness.",
        "",
        "## Exact bindings",
        "",
        f"- Source package: `{DECISION_PACKAGE_URI}`",
        f"- Source package SHA-256: `{package_sha256}`",
        f"- Approved implementation handoff SHA-256: `{HANDOFF_SHA256}`",
        f"- Handoff approval SHA-256: `{HANDOFF_APPROVAL_SHA256}`",
        "- Detached final-package approval: "
        f"`repo://{FINAL_PACKAGE_APPROVAL_PATH.as_posix()}`",
        f"- Detached final-package approval SHA-256: `{FINAL_PACKAGE_APPROVAL_SHA256}`",
        f"- Detached approval status: `{effective_approval['status']}`",
        f"- Detached approval authority: `{effective_approval['authority']}`",
        f"- Generated by: `{GENERATOR_URI}`",
        f"- Generation command: `{GENERATION_COMMAND}`",
        "- Source-package internal approval field: "
        "`PENDING_EXACT_REPOSITORY_OWNER_APPROVAL` (preserved immutable proposal "
        "state)",
        "- Final source-package owner approval: `EFFECTIVE_DETACHED_EXACT_HASH`",
        "",
        "## Scoped owner-candidate inventory",
        "",
        *candidate_lines,
        "",
        "Canonical truth remains seven scoped unresolved rows, fourteen global "
        "unresolved blockers, six blocked targets, and "
        "`BLOCKED_UNRESOLVED_INPUTS`.",
        "",
        "## Scoped pending conditions",
        "",
        *scoped_pending,
        "",
        "## Informational cross-Story pending conditions",
        "",
        "These rows have no ST-1701 implementation, activation, status, or "
        "revision-readiness effect.",
        "",
        *informational_pending,
        "",
        "## Remaining prerequisites before canonical revision",
        "",
        "- OD-005 requires an alternate reviewer or a separately approved exception.",
        "- The Domain Editor accepts the closed OD-006 Gold Evidence with zero "
        "false automatic merges.",
        "- Formal TST-032 remains `NOT_EXECUTED`.",
        "- Canonical-revision approval and import remain separately `NOT_EXECUTED`.",
        "- External execution remains separate from decision-resolution evidence.",
        "",
        "## Prohibited effects",
        "",
        "- No canonical edit or canonical decision-status change.",
        "- No Gate, TST-032, Story, staging, publication, release, or Production "
        "promotion.",
        "- No ST-1702 runtime category configuration or golden-product dataset.",
        "- No browser, provider, account, credential, domain, or other external "
        "action.",
        "",
    ]
    return "\n".join(lines).encode()


def _require_gold_preapproval_artifacts_absent(root: Path) -> None:
    if _repository_path_state(root, GOLD_LEDGER_PATH, "gold.ledger") == "REGULAR":
        _fail("GOLD_LEDGER_ACCEPTANCE_UNAVAILABLE", "gold.ledger")
    if (
        _repository_path_state(
            root, GOLD_EVIDENCE_APPROVAL_PATH, "gold.domain_editor_approval"
        )
        == "REGULAR"
    ):
        _fail(
            "GOLD_APPROVAL_ACCEPTANCE_UNAVAILABLE",
            "gold.domain_editor_approval",
        )
    for relative in GOLD_POSTAPPROVAL_PATHS:
        if (
            _repository_path_state(root, relative, "gold.postapproval_artifact")
            == "REGULAR"
        ):
            _fail(
                "GOLD_POSTAPPROVAL_ARTIFACT_FORBIDDEN",
                "gold.postapproval_artifact",
            )


def gold_evidence_validation_document(
    root: Path = REPO_ROOT,
) -> dict[str, object]:
    """Render the sole preapproval Gold result without accepting a ledger."""

    handoff, approval = _gold_authority_documents(root)
    _require_gold_preapproval_artifacts_absent(root)
    decision = _mapping(handoff["decision"], "gold_authority.handoff.decision")
    collection_policy = _mapping(
        decision["od006_collection_policy"],
        "gold_authority.handoff.decision.od006_collection_policy",
    )
    candidate_pool = _mapping(
        collection_policy["candidate_pool"],
        "gold_authority.handoff.decision.candidate_pool",
    )
    closed_counts = _mapping(
        collection_policy["closed_counts"],
        "gold_authority.handoff.decision.closed_counts",
    )
    price_mix = _mapping(
        collection_policy["price_mix"],
        "gold_authority.handoff.decision.price_mix",
    )
    identity_policy = _mapping(
        decision["identity_policy"],
        "gold_authority.handoff.decision.identity_policy",
    )
    pair_evaluation = _mapping(
        decision["pair_evaluation"],
        "gold_authority.handoff.decision.pair_evaluation",
    )
    pair_acceptance = _mapping(
        pair_evaluation["acceptance"],
        "gold_authority.handoff.decision.pair_evaluation.acceptance",
    )
    authority_model = _mapping(
        decision["authority_model"],
        "gold_authority.handoff.decision.authority_model",
    )
    required_case_tags = _list(
        collection_policy["required_case_tags"], "gold.required_case_tags"
    )
    listing_count = closed_counts["listing_count"]
    if type(listing_count) is not int:
        _fail("INVALID_COUNT", "gold.closed_counts.listing_count")
    if gold_unordered_pair_count(30) != 435:
        _fail("PAIR_POPULATION_DRIFT", "gold.pair_population")
    if tuple(required_case_tags) != GOLD_REQUIRED_CASE_TAGS:
        _fail("REQUIRED_CASE_DRIFT", "gold.required_case_tags")

    return {
        "schema": "GOLD_EVIDENCE_VALIDATION_V1",
        "story_id": "ST-1701",
        "status": "EVIDENCE_INSUFFICIENT",
        "stop_code": "STOP_EVIDENCE_INSUFFICIENT",
        "authority": "PROPOSAL_ONLY_NON_CANONICAL",
        "authority_binding": {
            "handoff": {
                "uri": f"repo://{GOLD_HANDOFF_PATH.as_posix()}",
                "bytes": GOLD_HANDOFF_BYTES,
                "sha256": GOLD_HANDOFF_SHA256,
            },
            "detached_approval": {
                "uri": f"repo://{GOLD_HANDOFF_APPROVAL_PATH.as_posix()}",
                "bytes": GOLD_HANDOFF_APPROVAL_BYTES,
                "sha256": GOLD_HANDOFF_APPROVAL_SHA256,
                "status": approval["status"],
                "implementation_authority": approval["implementation_authority"],
                "open_decisions": approval["open_decisions"],
            },
        },
        "collection_feasibility": {
            "category_id": collection_policy["category_id"],
            "collection_mode": collection_policy["collection_mode"],
            "ranking_source": collection_policy["ranking_source"],
            "ranking_url": "https://ranking.rakuten.co.jp/daily/301577/",
            "ranking_observed_at": "2026-08-12T02:30:56+09:00",
            "snapshot_update_date": "2026-08-11",
            "snapshot_aggregate_date": "2026-08-10",
            "required_first_bound": candidate_pool["first_bound"],
            "accessible_contiguous_rank_positions": {"first": 1, "last": 20},
            "unavailable_required_same_snapshot_positions": {
                "first": 21,
                "last": 50,
            },
            "same_snapshot_top_50_route_found": False,
            "top_100_expansion_reached": False,
            "candidate_bound_exhaustion_claimed": False,
            "stale_snapshot_mixing_refused": True,
            "ranking_entries_are_family_seeds_not_observations": (
                candidate_pool["ranking_entries_are_family_seeds_not_all_observations"]
            ),
            "out_of_pool_manual_substitution": candidate_pool[
                "out_of_pool_manual_substitution"
            ],
            "page_bodies_archived": False,
        },
        "closed_evidence_contract": {
            "ledger_uri": f"repo://{GOLD_LEDGER_PATH.as_posix()}",
            "complete_ledger_acceptance_enabled": False,
            "closed_counts": dict(closed_counts),
            "required_case_tags": list(GOLD_REQUIRED_CASE_TAGS),
            "price_mix": {
                "low_family_count": price_mix["low_family_count"],
                "mid_family_count": price_mix["mid_family_count"],
                "high_family_count": price_mix["high_family_count"],
            },
            "required_exact_identity_fields": list(
                _list(
                    identity_policy["required_exact_fields"],
                    "gold.identity.required_exact_fields",
                )
            ),
            "jan_policy": identity_policy["jan_policy"],
            "pair_population": pair_evaluation["pair_population"],
            "derived_unordered_pair_count": gold_unordered_pair_count(listing_count),
            "pair_result_values": pair_evaluation["result_values"],
            "maximum_false_automatic_merges": pair_acceptance[
                "maximum_false_automatic_merges"
            ],
            "pair_metrics_emitted": False,
        },
        "ledger_boundary": {
            "ledger_present": False,
            "domain_editor_approval_uri": (
                f"repo://{GOLD_EVIDENCE_APPROVAL_PATH.as_posix()}"
            ),
            "domain_editor_approval_present": False,
            "preapproval_result_uri": f"repo://{GOLD_VALIDATION_PATH.as_posix()}",
            "gold_summary_generated": False,
            "resolution_candidates_generated": False,
            "open_decisions_revision_candidate_generated": False,
            "gold_canonical_revision_request_generated": False,
            "canonical_revision_bundle_manifest_generated": False,
            "canonical_revision_bundle_approval_present": False,
            "existing_predecessor_canonical_revision_request_preserved": True,
        },
        "required_handoff_addendum": list(GOLD_CONTRACT_MAPPING_GAPS),
        "non_promotion_boundary": {
            "evidence_authority": "NONE",
            "maximum_evidence_authority_after_valid_domain_editor_approval": (
                authority_model["evidence_authority"]
            ),
            "canonical_mutation_authority": authority_model[
                "canonical_mutation_authority"
            ],
            "canonical_open_decision_status": authority_model[
                "canonical_open_decision_status"
            ],
            "canonical_scoped_unresolved_count": 7,
            "global_unresolved_blocker_count": 14,
            "st0006_blocker_state": authority_model["st0006_blocker_state"],
            "gate_state": authority_model["gate_state"],
            "st1701_acceptance": authority_model["st1701_acceptance"],
            "tst_032": authority_model["tst_032"],
            "st1607": authority_model["st1607"],
            "st1702_ready": False,
            "status_overlays": "UNCHANGED",
            "staging": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(
    root: Path,
    generated_content: Mapping[Path, bytes],
    handoff: Mapping[str, Any],
    package: Mapping[str, Any],
    final_approval: Mapping[str, Any],
    gold_handoff: Mapping[str, Any],
    gold_approval: Mapping[str, Any],
    gold_validation: Mapping[str, object],
) -> bytes:
    scoped = [
        _mapping(row, "package.scoped_decisions")
        for row in _list(package["scoped_decisions"], "package.scoped_decisions")
    ]
    status_counts = {
        status: sum(row["record_status"] == status for row in scoped)
        for status in RECORD_STATUSES
    }
    document = {
        "document": {
            "id": "RAOS-ST1701-MVP-BUSINESS-INPUTS-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "source_contracts": [SOURCE_URI, DECISION_PACKAGE_URI],
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "implementation_authority": {
                "handoff": {
                    "uri": f"repo://{HANDOFF_PATH.as_posix()}",
                    "bytes": HANDOFF_BYTES,
                    "sha256": HANDOFF_SHA256,
                },
                "approval": {
                    "uri": f"repo://{HANDOFF_APPROVAL_PATH.as_posix()}",
                    "bytes": HANDOFF_APPROVAL_BYTES,
                    "sha256": HANDOFF_APPROVAL_SHA256,
                    "status": "APPROVED_FOR_IMPLEMENTATION",
                    "implementation_authority": ("ST1701_MVP_DECISION_PACKAGE_V1_ONLY"),
                },
            },
            "gold_evidence_implementation_authority": {
                "handoff": {
                    "uri": f"repo://{GOLD_HANDOFF_PATH.as_posix()}",
                    "bytes": GOLD_HANDOFF_BYTES,
                    "sha256": GOLD_HANDOFF_SHA256,
                },
                "approval": {
                    "uri": f"repo://{GOLD_HANDOFF_APPROVAL_PATH.as_posix()}",
                    "bytes": GOLD_HANDOFF_APPROVAL_BYTES,
                    "sha256": GOLD_HANDOFF_APPROVAL_SHA256,
                    "status": gold_approval["status"],
                    "implementation_authority": gold_approval[
                        "implementation_authority"
                    ],
                    "open_decisions": gold_approval["open_decisions"],
                    "self_approval_binding": "NOT_PRESENT_NO_CIRCULAR_APPROVAL",
                },
                "preapproval_generated_output": "GOLD_EVIDENCE_VALIDATION_V1_ONLY",
            },
            "final_package_approval": {
                "uri": f"repo://{FINAL_PACKAGE_APPROVAL_PATH.as_posix()}",
                "bytes": FINAL_PACKAGE_APPROVAL_BYTES,
                "sha256": FINAL_PACKAGE_APPROVAL_SHA256,
                "status": final_approval["status"],
                "authority": final_approval["authority"],
                "source_package": {
                    "uri": final_approval["source_package_uri"],
                    "bytes": final_approval["source_package_bytes"],
                    "sha256": final_approval["source_package_sha256"],
                },
                "implementation_handoff": final_approval["implementation_handoff"],
                "implementation_handoff_approval": final_approval[
                    "implementation_handoff_approval"
                ],
                "open_decisions": final_approval["open_decisions"],
                "self_approval_binding": "NOT_PRESENT_NO_CIRCULAR_APPROVAL",
            },
            "approved_preimplementation_inputs": list(
                _list(handoff["source_design_refs"], "authority.source_design_refs")
            ),
            "gold_evidence_approved_preimplementation_inputs": list(
                _list(
                    gold_handoff["source_design_refs"],
                    "gold_authority.source_design_refs",
                )
            ),
            "authority_inputs": [
                {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
                for path, size, digest in EXPECTED_SOURCE_ROWS
            ],
            "predecessor_inputs": [
                {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
                for path, size, digest in EXPECTED_PREDECESSOR_ROWS
            ],
            "implementation_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in IMPLEMENTATION_DEPENDENCIES.items()
            ],
            "current_development_rebinding": {
                "classification": "REVERSIBLE_REPOSITORY_DEVELOPMENT_ONLY",
                "authority_source": {
                    "uri": f"repo://{STANDING_DEVELOPMENT_AUTHORITY_PATH.as_posix()}",
                    "bytes": STANDING_DEVELOPMENT_AUTHORITY_BYTES,
                    "sha256": STANDING_DEVELOPMENT_AUTHORITY_SHA256,
                    "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
                },
                "current_authority_inputs": [
                    {
                        "uri": f"repo://{path}",
                        "bytes": binding[0],
                        "sha256": binding[1],
                    }
                    for path, binding in CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.items()
                ],
                "current_implementation_inputs": [
                    {
                        "uri": f"repo://{path}",
                        "bytes": len(
                            _read(
                                root, Path(path), "current_development.implementation"
                            )
                        ),
                        "sha256": digest,
                    }
                    for path, digest in IMPLEMENTATION_DEPENDENCIES.items()
                ],
                "historical_source_and_authority_rows_preserved": True,
                "semantic_delta_from_business_inputs": "NONE",
                "formal_evidence": False,
                "repository_git_authority": ("ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"),
                "external_authority": "NONE",
                "live_provider_authority": "NONE",
                "credential_authority": "NONE",
                "staging_authority": "NONE",
                "publication_authority": "NONE",
                "release_authority": "NONE",
                "production_authority": "NONE",
            },
            "source_contracts": [
                {
                    "uri": SOURCE_URI,
                    "bytes": len(_read(root, CONTRACT_PATH, "manifest.contract")),
                    "sha256": _sha256(_read(root, CONTRACT_PATH, "manifest.contract")),
                },
                {
                    "uri": DECISION_PACKAGE_URI,
                    "bytes": len(
                        _read(root, DECISION_PACKAGE_PATH, "manifest.decision_package")
                    ),
                    "sha256": _sha256(
                        _read(root, DECISION_PACKAGE_PATH, "manifest.decision_package")
                    ),
                },
            ],
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": len(GENERATED_CONTENT_PATHS),
        "generated_artifacts": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(generated_content[path]),
                "sha256": _sha256(generated_content[path]),
            }
            for path in GENERATED_CONTENT_PATHS
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "package_authority": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
            "source_package_internal_final_approval": (
                "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL"
            ),
            "final_package_approval": final_approval["status"],
            "final_package_approval_authority": final_approval["authority"],
            "canonical_authority": "UNCHANGED",
            "canonical_open_decision_status": "UNCHANGED",
            "st0006_blocker_state": "UNCHANGED",
            "scoped_decision_count": 7,
            "scoped_record_status_counts": status_counts,
            "canonical_scoped_unresolved_count": 7,
            "global_unresolved_blocker_count": 14,
            "activation": "BLOCKED_UNRESOLVED_INPUTS",
            "gate_state": "BLOCKED",
            "formal_tst_032": "NOT_EXECUTED",
            "st_1701_acceptance_achieved": False,
            "st_1702_ready": False,
            "publication_ready": False,
            "release_ready": False,
            "production_ready": False,
            "effective_canonical_status": "UNCHANGED",
            "informational_cross_story_effect": (
                "INFORMATION_ONLY_NO_IMPLEMENTATION_OR_STATUS_EFFECT"
            ),
            "canonical_revision_request_status": CANONICAL_REVISION_REQUEST_STATUS,
            "canonical_revision_request_authority": final_approval["authority"],
            "canonical_revision_request_readiness": "NOT_READY",
            "gold_evidence_validation_status": gold_validation["status"],
            "gold_evidence_stop_code": gold_validation["stop_code"],
            "gold_evidence_ledger_present": False,
            "gold_domain_editor_approval_present": False,
            "gold_complete_ledger_acceptance_enabled": False,
            "gold_resolution_candidates_generated": False,
            "gold_open_decisions_revision_candidate_generated": False,
            "gold_canonical_revision_request_generated": False,
            "gold_canonical_revision_bundle_manifest_generated": False,
            "gold_canonical_revision_bundle_approval_present": False,
            "gold_candidate_bound_exhaustion_claimed": False,
            "gold_postapproval_generation_enabled": False,
            "canonical_mutation_authority": "NONE",
            "status_overlays": "UNCHANGED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    handoff, _approval = _authority_documents(root)
    final_approval = _final_package_approval_document(root)
    gold_handoff, gold_approval = _gold_authority_documents(root)
    contract = load_contract(root)
    package = validate_decision_package(
        _load_yaml(root, DECISION_PACKAGE_PATH, "decision_package"),
        root,
        handoff=handoff,
    )
    reference_bytes = _json_bytes(reference_document(contract, root))
    if _sha256(reference_bytes) != (
        "22394f5b37d3fe90cc5c31aff47be0d0f31f061398bbd9d90b4030bcb050c33b"
    ):
        _fail("UNRESOLVED_REGISTRY_DRIFT", "unresolved_registry")
    decision_bytes = _json_bytes(
        decision_read_model(
            package,
            contract,
            root,
            final_approval=final_approval,
        )
    )
    revision_request_bytes = canonical_revision_request_bytes(
        package, root, final_approval=final_approval
    )
    gold_validation = gold_evidence_validation_document(root)
    gold_validation_bytes = _json_bytes(gold_validation)
    generated_content = {
        REFERENCE_PATH: reference_bytes,
        DECISION_READ_MODEL_PATH: decision_bytes,
        CANONICAL_REVISION_REQUEST_PATH: revision_request_bytes,
        GOLD_VALIDATION_PATH: gold_validation_bytes,
    }
    return {
        **generated_content,
        MANIFEST_PATH: _manifest_bytes(
            root,
            generated_content,
            handoff,
            package,
            final_approval,
            gold_handoff,
            gold_approval,
            gold_validation,
        ),
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
    except (BusinessInputsError, base.ProductionDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1701 business-input and Gold preapproval artifacts checked"
        if args.check
        else "ST-1701 business-input and Gold preapproval artifacts generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
