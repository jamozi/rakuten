#!/usr/bin/env python3
"""Build the repository-inert ST-1504 GitHub OIDC offline harness."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-1504/contracts/github-oidc-deployment.v1.yaml")
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json"
)
CLAIMS_FIXTURE_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc.claims.recorded.v1.json"
)
TRUST_POLICY_FIXTURE_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc.trust-policy.recorded.v1.json"
)
EVALUATION_FIXTURE_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc.evaluation.recorded.v1.json"
)
WORKFLOW_FIXTURE_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc-deploy.disabled.workflow.yml"
)
MANIFEST_PATH: Final = Path("changes/st-1504/manifest.yaml")
GENERATED_NON_MANIFEST_PATHS: Final = (
    REFERENCE_PLAN_PATH,
    CLAIMS_FIXTURE_PATH,
    TRUST_POLICY_FIXTURE_PATH,
    EVALUATION_FIXTURE_PATH,
    WORKFLOW_FIXTURE_PATH,
)
GENERATED_PATHS: Final = (*GENERATED_NON_MANIFEST_PATHS, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1504_github_oidc.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1504_github_oidc.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"

AUTHORITY_SOURCES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md": (
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3"
    ),
    "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml": (
        "2cdc9afb4b9a1fc7cb44b78dc5198bc443a219ca895713b75220f8625aea6305"
    ),
    "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md": (
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "docs/canonical/04_security/RAOS_10_implementation_slices_v1.0.yaml": (
        "3db3aeeb3cfd0cbb4ab91e3490956cae17d60e43950e48fdf50c1609019e1b22"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234"
    ),
    "AGENTS.md": ("a302eac0ebd61e352c94f9e07e715b41545bc29c1eae6c73f6115cf6ff3f2127"),
    "changes/st-1504/"
    "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml": (
        "36ac3095033f8ad7c91deac77f6a6689d354dc63dd46f03350e0bf68b3ccca04"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-0107/contracts/pr-governance.v1.yaml": (
        "b387255fa65577051203b0fb1f935d5340c0d00f1285fd25557a38776fb07d92"
    ),
    "changes/st-0107/ruleset-policy.v1.json": (
        "e999838c2f592e3795aa79222bcfbc8cedf4b59bad06024f0328ebd65b3e11f5"
    ),
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "5f13094d18dfbece65ccf36a68928fc9d602d316068aa5f1b538f14d90136e1e"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "bb5a6bb86ab13cf465a980eccea75bc3742eb818af142dc74ba6cea90aef6a72"
    ),
    "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json": (
        "696c1e06b4dbb93c952a32e181d145ce8cdf6980b3434fee7e4795296f887f44"
    ),
    "infra/terraform/foundation/versions.tf": (
        "87d23505f127e84430a32ac458b67b46b6614f3d2f976c2539fe3163b4eecab7"
    ),
    "infra/terraform/foundation/variables.tf": (
        "ce13d5d7eb4ed483c5afd170e1ec74738aa73455e5b4036e861cf5786ff6e76e"
    ),
    "infra/terraform/foundation/locals.tf": (
        "a113d24697b1f00c6f3fe32459280672d271dd5a1757364e8e2aac97db1c3b3c"
    ),
    "infra/terraform/foundation/checks.tf": (
        "e4d826ee2881a74f2cc1c49f80ef817d090fb9c0f86040a30f37c231af663787"
    ),
    "infra/terraform/foundation/outputs.tf": (
        "dac1835d490dc50355a9d4510d6ee8991f2a945ad1bfc1ee395e8c2134431d72"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    Path("changes/st-1504/IMPLEMENTATION_RECORD_V2_ST1504_OFFLINE_OIDC.yaml"),
    Path("changes/st-1504/LOCAL_COMPLETION_EVIDENCE_V2.md"),
    Path("changes/st-1504/README.md"),
    Path("scripts/build_st1504_github_oidc.py"),
    Path("python/raos/domain/deployment_identity.py"),
    Path("python/raos/ports/deployment_identity.py"),
    Path("python/raos/adapters/disabled_deployment_identity.py"),
    Path("tests/st1504/conftest.py"),
    Path("tests/st1504/test_contract.py"),
    Path("tests/st1504/test_generation.py"),
    Path("tests/st1504/test_negative_cases.py"),
    Path("tests/st1504/test_offline_runtime.py"),
    Path("tests/st1504/test_offline_runtime_negative.py"),
)

EXPECTED_HANDOFF_SEMANTIC_SHA256: Final = (
    "e26a0bbedb909530587462881a96e8b85b7bfdb93aedc57e281eda9d4d043282"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256: Final = (
    "f0a8a5ca57f34f8b983aa547f8b5f036ee91e0cc9acb63813da64e62a317d2db"
)
EXPECTED_PR_GOVERNANCE_CONTRACT_SEMANTIC_SHA256: Final = (
    "141dce557ae5b16c1ef54490ed1c41ce083c33cf27c5e9b66a38de4827dd6dfb"
)
EXPECTED_PR_GOVERNANCE_DESIRED_STATE_SEMANTIC_SHA256: Final = (
    "bcfc8440e5e508648607dc22f8deacca4dc14021404c050457077ce451934c33"
)
EXPECTED_PREDECESSOR_HANDOFF_SEMANTIC_SHA256: Final = (
    "e20e03d89693bc8ad7adfffcc515eb656ec11375c2a304aa58ab0e30b8fe4722"
)
EXPECTED_PREDECESSOR_CONTRACT_SEMANTIC_SHA256: Final = (
    "9e88addbfe93c6d6754111d508ba1d7461a703c2aa6b329fa319b6566d9a55e1"
)
EXPECTED_PREDECESSOR_PLAN_SEMANTIC_SHA256: Final = (
    "1deb0efe9ff2d99ccc27ad6f50d1a07c6ed13b6c45cdd6914a7fdcd1a0edbf20"
)
EXPECTED_PREDECESSOR_TOOLCHAIN_LOCK_SEMANTIC_SHA256: Final = (
    "db631e5421d5eea0534737b1df03425ccb873cfe981ad96409d3c90aeef4de1a"
)
EXPECTED_HANDOFF_SOURCE_DESIGN_REFS: Final = (
    "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    "repo://docs/canonical/01_integration/"
    "RAOS_07_canonical_decisions_v1.0.yaml#INT-DEC-007",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-009",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-011",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-015",
    "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-0107",
    "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-1504",
    "repo://changes/st-0107/contracts/pr-governance.v1.yaml",
    "repo://changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "repo://docs/upstream/key_documents/"
    "RAOS_02_system_architecture_v0.1.md#RAOS-ARCH-001",
    "repo://docs/upstream/key_documents/"
    "RAOS_02_architecture_catalog_v0.1.yaml#RAOS-ARCH-001",
    "repo://docs/canonical/06_ops/"
    "RAOS_12_operations_reliability_design_v1.0.md#RAOS-OPS-001",
    "repo://docs/canonical/04_security/"
    "RAOS_10_security_privacy_design_v1.0.md#RAOS-SEC-001",
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-026",
    "repo://AGENTS.md#project-tools-contract",
)

EXPECTED_STORY: Final = {
    "id": "ST-1504",
    "epic_id": "EPIC-15",
    "title": "GitHub OIDC deployment",
    "objective": "short-lived deploy identityとenvironment approval",
    "depends_on": ["ST-0107", "ST-1501"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["workflow/IAM trust"],
    "acceptance_criteria": ["fork PR no credential", "production approval"],
    "test_suites": ["TST-026"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_INT_DEC_007: Final = {
    "id": "INT-DEC-007",
    "title": "Reference Cloud",
    "status": "RESOLVED",
    "decision": (
        "AWS東京リージョンをReference ArchitectureとするがCoreをAWS固有Domain Modelへ密結合させない"
    ),
    "implementation_effect": "TerraformとAdapter境界を用意。実AWS Accountは未設定",
}
EXPECTED_OPEN_DECISIONS: Final = {
    "OD-009": {
        "id": "OD-009",
        "topic": "budget_and_acceptable_loss",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Cloud/LLM release",
        "owner": "Business Owner",
        "decision_needed": "AWS、LLM、外部Providerの月次上限と自動停止閾値を設定",
        "default_behavior": "低い開発用上限、Production無効",
        "blocking": True,
    },
    "OD-011": {
        "id": "OD-011",
        "topic": "notification_channels",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Incident operations",
        "owner": "Operations Owner",
        "decision_needed": "Critical/High通知先とEscalation連絡先を設定",
        "default_behavior": "Local logのみ。Production不可",
        "blocking": True,
    },
    "OD-013": {
        "id": "OD-013",
        "topic": "production_region_and_data_residency",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Terraform production",
        "owner": "Security/Business Owner",
        "decision_needed": "AWS Region、Backup Region、越境移転の扱いを承認",
        "default_behavior": "Referenceはap-northeast-1、Production apply禁止",
        "blocking": True,
    },
    "OD-015": {
        "id": "OD-015",
        "topic": "production_provider_credentials",
        "status": "EXTERNAL_EVIDENCE_REQUIRED",
        "required_by": "Live adapter test",
        "owner": "Operations Owner",
        "decision_needed": "楽天、OpenAI、Google、AWSの専用Account/権限/Secretを設定",
        "default_behavior": "Recorded fixtureのみ",
        "blocking": True,
    },
}
EXPECTED_TST_026: Final = {
    "id": "TST-026",
    "name": "Security verification",
    "layer": "security",
    "purpose": "ASVS control、SAST/SCA/DAST、manual abuse",
    "candidate_tools": ["security tools", "manual"],
    "release_blocking": True,
    "environments": ["CI", "staging"],
    "owner": "Security",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-004": "Role/Scope/Siteで最小権限",
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-IAM-010": "長期AWS keyをActions secretに置かない",
    "SEC-SDLC-001": "Rulesetとrequired review/checks",
    "SEC-SDLC-002": "Security、migration、contractsへowner review",
    "SEC-SDLC-004": "Dependency/container vulnerability scan",
    "SEC-SDLC-006": "History/PR/artifactをscan",
    "SEC-SDLC-007": "Release artifactのSBOM生成",
    "SEC-SDLC-008": "Build provenance/attestationを生成",
    "SEC-SDLC-012": "Production deployはHuman approval",
    "SEC-OPS-001": "Auth failure、privilege、secret、WAF、kill switchを監視",
    "SEC-OPS-003": "SEVとresponse ownerを定義",
    "SEC-OPS-004": "Artifact、log、timelineを保全",
}
EXPECTED_THREATS: Final = {
    "THR-007": {
        "id": "THR-007",
        "threat": "Dependency compromise",
        "scenario": "Package/Action汚染",
        "impact": "Build/Production侵害",
        "controls": "pin、SCA、SBOM、provenance",
        "residual_risk": "TO_BE_ASSESSED_AFTER_IMPLEMENTATION",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    "THR-008": {
        "id": "THR-008",
        "threat": "CI credential abuse",
        "scenario": "PRからCloud credential取得",
        "impact": "Infrastructure侵害",
        "controls": "OIDC trust condition、environment approval",
        "residual_risk": "TO_BE_ASSESSED_AFTER_IMPLEMENTATION",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_SLICE: Final = {
    "id": "SEC-SLICE-009",
    "name": "Supply chain and deployment",
    "depends_on": ["SEC-SLICE-001", "SEC-SLICE-007"],
    "deliverables": ["SBOM", "provenance", "OIDC deploy", "environment approval"],
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}

REQUIRED_CLAIM_BINDINGS: Final = (
    "repository_identity",
    "trusted_ref",
    "workflow_identity",
    "environment",
    "audience",
    "subject",
)
EXPECTED_REQUIRED_CHECKS: Final = (
    "Static",
    "Unit",
    "Contracts",
    "Database",
    "Storage",
    "Secrets",
    "Validate status overlay",
)
FOUNDATION_NATIVE_COMMANDS: Final = (
    "init",
    "plan",
    "apply",
    "destroy",
    "import",
    "refresh",
)
NATIVE_OPERATIONS: Final = (
    "github_api_mutation",
    "github_ruleset_mutation",
    "github_workflow_mutation",
    "github_environment_mutation",
    "target_provider_api_call",
    "target_identity_policy_apply",
    "target_federation_exchange",
    "credential_issue",
    "deploy",
    "iac_plan",
    "iac_apply",
)
ELIGIBLE_PROFILE_KINDS: Final = (
    "AWS",
    "OTHER_CLOUD",
    "OWNER_MANAGED_INFRASTRUCTURE",
)
DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES: Final = (
    (
        "exact_repository_ref_workflow_and_subject_binding",
        "EXACT_REPOSITORY_REF_WORKFLOW_ENVIRONMENT_AUDIENCE_AND_SUBJECT_WITH_"
        "NO_WILDCARD_OR_UNTRUSTED_CALLER",
    ),
    (
        "short_lived_federation_without_static_cloud_secrets",
        "SHORT_LIVED_FEDERATION_WITHOUT_STATIC_CLOUD_SECRET_HUMAN_CREDENTIAL_"
        "OR_AMBIENT_AUTHORITY",
    ),
    (
        "target_environment_and_audience_binding",
        "EXACT_TARGET_ENVIRONMENT_AUDIENCE_PROVIDER_AND_RELEASE_BOUNDARY_WITH_"
        "FAIL_CLOSED_ISSUANCE",
    ),
    (
        "least_privilege_session_scope_and_duration_limits",
        "LEAST_PRIVILEGE_SCOPE_BOUNDED_DURATION_NO_ROLE_CHAINING_AND_NO_"
        "PRIVILEGE_ESCALATION",
    ),
    (
        "protected_environment_human_approval",
        "DISTINCT_HUMAN_APPROVAL_PROTECTED_ENVIRONMENT_EXACT_ALLOWED_REFS_AND_"
        "NO_BYPASS",
    ),
    (
        "provenance_audit_revocation_and_rollback",
        "SIGNED_PROVENANCE_IMMUTABLE_AUDIT_REVOCATION_RUNBOOK_ALERT_OWNERSHIP_"
        "AND_TESTED_ROLLBACK",
    ),
    (
        "provider_account_project_tenant_and_environment_isolation",
        "DEVELOPMENT_PRODUCTION_ACCOUNT_PROJECT_TENANT_ENVIRONMENT_AND_REGION_"
        "RESIDENCY_ISOLATION",
    ),
    (
        "equivalent_security_operations_and_release_evidence",
        "IDENTICAL_SECURITY_OPERATIONS_RELEASE_PROVENANCE_AUDIT_REVOCATION_"
        "ROLLBACK_ISOLATION_AND_RESIDENCY_EVIDENCE",
    ),
)
ACTION_NAMES: Final = ("create", "update", "delete")
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
FIXTURE_ID: Final = "st1504-fixture-repository-inert-v1"
POLICY_ID: Final = "st1504-policy-repository-inert-v1"
RECORDED_CLAIM_KEYS: Final = (
    "iss",
    "aud",
    "sub",
    "repository",
    "repository_id",
    "repository_owner_id",
    "ref",
    "ref_type",
    "workflow",
    "workflow_ref",
    "workflow_sha",
    "job_workflow_ref",
    "environment",
    "event_name",
    "repository_visibility",
    "actor_id",
    "run_id",
    "run_attempt",
    "base_ref",
    "head_ref",
)
RECORDED_CLAIMS: Final = {
    "iss": "https://token.actions.githubusercontent.invalid",
    "aud": "raos-deployment-fixture.invalid",
    "sub": (
        "repo:raos-fixture/not-a-real-repository:"
        "environment:production-fixture-disabled"
    ),
    "repository": "raos-fixture/not-a-real-repository",
    "repository_id": "100000001",
    "repository_owner_id": "100000002",
    "ref": "refs/heads/fixture-deploy",
    "ref_type": "branch",
    "workflow": "ST-1504 disabled deployment fixture",
    "workflow_ref": (
        "raos-fixture/not-a-real-repository/infra/terraform/"
        "deployment-identity/github-oidc-deploy.disabled.workflow.yml@"
        "refs/heads/fixture-deploy"
    ),
    "workflow_sha": "1111111111111111111111111111111111111111",
    "job_workflow_ref": "",
    "environment": "production-fixture-disabled",
    "event_name": "workflow_dispatch",
    "repository_visibility": "private",
    "actor_id": "100000003",
    "run_id": "100000004",
    "run_attempt": "1",
    "base_ref": "",
    "head_ref": "",
}


def _aws_reference_mappings() -> list[dict[str, str]]:
    return [
        {"reference_name": reference_name, "capability_id": capability_id}
        for reference_name, capability_id in (
            (
                "AWS IAM OIDC provider",
                "short_lived_federation_without_static_cloud_secrets",
            ),
            (
                "AWS IAM role",
                "least_privilege_session_scope_and_duration_limits",
            ),
            (
                "AWS account",
                "provider_account_project_tenant_and_environment_isolation",
            ),
            (
                "AWS region",
                "provider_account_project_tenant_and_environment_isolation",
            ),
            ("AWS audience", "target_environment_and_audience_binding"),
        )
    ]


def _binding_policy() -> dict[str, object]:
    unset = {"selected": None, "default": None, "fallback": None}
    return {
        name: copy.deepcopy(unset)
        for name in (
            "target_provider",
            "target_profile",
            "account_project_or_tenant",
            "region",
            "audience",
            "target_identity_or_role",
            "identity_plugin_or_adapter",
        )
    } | {
        "implicit_binding": "FORBIDDEN",
        "name_or_reference_only_eligibility": "FORBIDDEN",
    }


def _capability_mapping_requirements() -> list[dict[str, object]]:
    return [
        {
            "capability_id": capability_id,
            "required_outcome": required_outcome,
            "selected_mapping": None,
            "evidence_refs": [],
            "mapping_status": "REQUIRED_NOT_CONFIGURED",
        }
        for capability_id, required_outcome in DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES
    ]


def _selected_bindings() -> dict[str, object]:
    return {
        "oidc_issuer_url": None,
        "oidc_subject": None,
        "github_organization": None,
        "github_repository": None,
        "github_repository_numeric_id": None,
        "default_branch_ref": None,
        "deploy_ref": None,
        "workflow_ref": None,
        "workflow_sha": None,
        "workflow_file_path": None,
        "deploy_job_id": None,
        "github_environment_name": None,
        "github_environment_reviewer_ids": [],
        "github_environment_allowed_refs": [],
        "reusable_workflow_callers": [],
        "target_provider_name": None,
        "target_profile_id": None,
        "target_profile_kind": None,
        "target_account_project_or_tenant": None,
        "target_region": None,
        "target_audience": None,
        "target_identity_role_reference": None,
        "target_federation_endpoint_reference": None,
        "session_duration_seconds": None,
        "session_name": None,
        "session_tags": [],
        "federation_trust_material": None,
        "permission_policy_payload": None,
        "environment_protection_payload": None,
        "workflow_permissions_payload": None,
        "workflow_trigger_events": [],
        "external_action_references": [],
        "identity_plugin_or_adapter": None,
        "provider_plugins": [],
    }


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-GITHUB-OIDC-DEPLOYMENT-001",
        "version": "2.0.0",
        "story_id": "ST-1504",
        "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_bindings": {
        "pr_governance": {
            "story_id": "ST-0107",
            "contract_uri": "repo://changes/st-0107/contracts/pr-governance.v1.yaml",
            "contract_sha256": PREDECESSOR_SOURCES[
                "changes/st-0107/contracts/pr-governance.v1.yaml"
            ],
            "desired_state_uri": "repo://changes/st-0107/ruleset-policy.v1.json",
            "desired_state_sha256": PREDECESSOR_SOURCES[
                "changes/st-0107/ruleset-policy.v1.json"
            ],
            "required_artifact_kind": "DESIRED_STATE_NOT_API_PAYLOAD",
            "required_target": "branch",
            "required_include": ["~DEFAULT_BRANCH"],
            "required_desired_enforcement": "active",
            "required_local_application_status": "NOT_EXECUTED",
            "required_remote_mutation": "FORBIDDEN",
            "required_bypass_actors": [],
            "required_protected_pr_controls": {
                "prohibit_deletion": True,
                "prohibit_force_push": True,
                "require_linear_history": True,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        },
        "terraform_foundation": {
            "story_id": "ST-1501",
            "design_handoff_uri": (
                "repo://changes/st-1501/"
                "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
            ),
            "design_handoff_sha256": PREDECESSOR_SOURCES[
                "changes/st-1501/"
                "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
            ],
            "contract_uri": (
                "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
            ),
            "contract_sha256": PREDECESSOR_SOURCES[
                "changes/st-1501/contracts/terraform-foundation.v1.yaml"
            ],
            "reference_plan_uri": (
                "repo://infra/terraform/foundation/"
                "terraform-foundation.reference-plan.v1.json"
            ),
            "reference_plan_sha256": PREDECESSOR_SOURCES[
                "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
            ],
            "validation_toolchain_lock_uri": (
                "repo://infra/terraform/foundation/"
                "terraform-validation-toolchain.lock.v1.json"
            ),
            "validation_toolchain_lock_sha256": PREDECESSOR_SOURCES[
                "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"
            ],
            "required_contract_status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "required_provider_policy": (
                "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
            ),
            "required_terraform_cli_version": "1.15.9",
            "required_hcl_module": (
                "PROVIDER_NEUTRAL_VALIDATION_ONLY_FOUNDATION_ADMISSION_MODULE"
            ),
            "required_hcl_default_disabled": True,
            "required_provider_count": 0,
            "required_resource_count": 0,
            "required_admission_status": "NOT_EVALUATED",
            "required_eligible": False,
            "required_activation_status": "DISABLED",
            "required_resource_payloads": "FORBIDDEN",
            "required_planned_actions": {action: 0 for action in ACTION_NAMES},
        },
    },
    "ci_source_boundary": {
        "ci_source": "GITHUB_ACTIONS",
        "oidc_source": "GITHUB_ACTIONS_OIDC",
        "external_review_connector": "GITHUB",
        "classification": "APPROVED_FIXED_SOURCE_NOT_TARGET_PROVIDER_SELECTION",
        "target_provider_selected": False,
        "exact_repository_binding": "REQUIRED_NOT_CONFIGURED",
        "exact_ref_binding": "REQUIRED_NOT_CONFIGURED",
        "exact_workflow_binding": "REQUIRED_NOT_CONFIGURED",
        "hosted_execution_evidence": "NOT_EXECUTED",
    },
    "reference_architecture": {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "inherited_from": "INT-DEC-007",
        "architecture_id": "RAOS-ARCH-001",
        "portable_core_required": True,
        "mappings": _aws_reference_mappings(),
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    },
    "provider_neutral_deployment_identity_admission": {
        "classification": (
            "STRICT_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY_CAPABILITY_ADMISSION"
        ),
        "admission_status": "NOT_EVALUATED",
        "eligible": False,
        "selected_profile_id": None,
        "selected_profile_kind": None,
        "selected_provider_name": None,
        "default_profile_id": None,
        "fallback_profile_id": None,
        "concrete_alternate_provider_selected": False,
        "eligible_profile_kinds": list(ELIGIBLE_PROFILE_KINDS),
        "eligibility_condition": (
            "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE"
        ),
        "binding_policy": _binding_policy(),
        "mapping_policy": {
            "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
            "required_capability_count": len(DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES),
            "configured_mapping_count": 0,
            "complete_mapping": False,
            "missing_mapping": "REJECT",
            "unknown_mapping": "REJECT",
            "duplicate_mapping": "REJECT",
            "implicit_mapping": "REJECT",
            "partial_mapping": "REJECT",
            "provider_label_only_mapping": "REJECT",
            "aws_label_only_mapping": "REJECT",
            "source_label_only_mapping": "REJECT",
            "reference_only_mapping": "REJECT",
        },
        "aws_reference_boundary": {
            "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "canonical_story_deliverables": (
                "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
            ),
            "non_aws_owner_managed_profiles": (
                "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
            ),
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "evidence_equivalence_policy": {
            "identical_security_evidence": "REQUIRED",
            "identical_operations_evidence": "REQUIRED",
            "identical_release_evidence": "REQUIRED",
            "identical_provenance_evidence": "REQUIRED",
            "identical_audit_evidence": "REQUIRED",
            "identical_revocation_rollback_evidence": "REQUIRED",
            "identical_identity_session_evidence": "REQUIRED",
            "identical_isolation_residency_evidence": "REQUIRED",
            "provider_label_as_evidence": "FORBIDDEN",
            "aws_label_as_evidence": "FORBIDDEN",
            "github_source_label_as_evidence": "FORBIDDEN",
            "reference_metadata_as_evidence": "FORBIDDEN",
            "local_test_as_live_evidence": "FORBIDDEN",
        },
        "capability_mapping_requirements": _capability_mapping_requirements(),
    },
    "reference_intent": {
        "classification": (
            "REPOSITORY_INERT_PROVIDER_NEUTRAL_OFFLINE_IDENTITY_HARNESS"
        ),
        "source": "GITHUB_ACTIONS_OIDC",
        "destination": "PROVIDER_NEUTRAL_SHORT_LIVED_WORKLOAD_SESSION",
        "github_workload_identity": "REQUIRED_NOT_CONFIGURED",
        "target_federated_session": "REQUIRED_NOT_CONFIGURED",
        "target_provider": "UNSELECTED",
        "github_source_is_target_provider_selection": False,
        "executable_workflow": "REPOSITORY_INERT_DISABLED_FIXTURE_ONLY",
        "target_trust_policy": "RECORDED_OFFLINE_EVALUATOR_FIXTURE_ONLY",
        "provider_sdk_types": "ABSENT",
        "production_deployment": "FORBIDDEN",
    },
    "recorded_fixture_boundary": {
        "classification": ("SYNTHETIC_RECORDED_VALUES_NOT_SELECTED_OR_LIVE_BINDINGS"),
        "fixture_id": FIXTURE_ID,
        "claims_fixture_uri": f"repo://{CLAIMS_FIXTURE_PATH.as_posix()}",
        "trust_policy_fixture_uri": (f"repo://{TRUST_POLICY_FIXTURE_PATH.as_posix()}"),
        "evaluation_fixture_uri": f"repo://{EVALUATION_FIXTURE_PATH.as_posix()}",
        "workflow_fixture_uri": f"repo://{WORKFLOW_FIXTURE_PATH.as_posix()}",
        "workflow_active_path": False,
        "workflow_default_disabled": True,
        "workflow_external_actions": [],
        "workflow_provider_commands": [],
        "claim_keys": list(RECORDED_CLAIM_KEYS),
        "jwt_compact_token": "ABSENT",
        "jwt_header": "ABSENT",
        "jwt_signature": "ABSENT",
        "signature_verification": "NOT_PERFORMED",
        "authentication": "NOT_PERFORMED",
        "credential_material": "ABSENT",
        "selected_binding_effect": "NONE",
    },
    "offline_trust_evaluator": {
        "classification": "POLICY_MATCH_ONLY_NOT_AUTHENTICATION",
        "domain_module_uri": "repo://python/raos/domain/deployment_identity.py",
        "input_mode": "CLOSED_RECORDED_FIXTURES_ONLY",
        "exact_match": "REQUIRED",
        "unknown_fields": "REJECT",
        "wildcards": "REJECT",
        "jwt_parser": "ABSENT",
        "signature_verifier": "ABSENT",
        "authentication_authority": "NONE",
        "credential_issuance_authority": "NONE",
        "network_access": "FORBIDDEN",
        "provider_sdk": "ABSENT",
        "evaluation_status": "EXECUTED_LOCAL_RECORDED_NOT_FORMAL",
        "evaluation_result": "RECORDED_EXACT_CLAIMS_MATCHED",
        "deployment_authority": "NONE",
    },
    "activation_port": {
        "classification": "STRICT_DISABLED_ZERO_ACTION_PORT",
        "port_module_uri": "repo://python/raos/ports/deployment_identity.py",
        "adapter_module_uri": (
            "repo://python/raos/adapters/disabled_deployment_identity.py"
        ),
        "status": "DISABLED",
        "activation_allowed": False,
        "credential_issuance_allowed": False,
        "deployment_allowed": False,
        "planned_actions": {action: 0 for action in ACTION_NAMES},
        "executed_actions": 0,
    },
    "selected_bindings": _selected_bindings(),
    "trust_constraints": {
        "status": "REQUIRED_NOT_CONFIGURED",
        "required_claim_bindings": list(REQUIRED_CLAIM_BINDINGS),
        "exact_repository_identity": "REQUIRED_NOT_CONFIGURED",
        "exact_trusted_ref": "REQUIRED_NOT_CONFIGURED",
        "exact_workflow_identity": "REQUIRED_NOT_CONFIGURED",
        "exact_environment": "REQUIRED_NOT_CONFIGURED",
        "exact_audience": "REQUIRED_NOT_CONFIGURED",
        "exact_subject": "REQUIRED_NOT_CONFIGURED",
        "wildcard_trust": "FORBIDDEN",
        "fork_pull_request": "FORBIDDEN",
        "untrusted_pull_request": "FORBIDDEN",
        "untrusted_ref": "FORBIDDEN",
        "untrusted_environment": "FORBIDDEN",
        "pull_request_target_credential_path": "FORBIDDEN",
        "unbounded_reusable_workflow_caller": "FORBIDDEN",
        "broad_organization_subject": "FORBIDDEN",
        "broad_repository_subject": "FORBIDDEN",
        "broad_ref_subject": "FORBIDDEN",
        "broad_audience": "FORBIDDEN",
    },
    "credential_boundary": {
        "classification": (
            "MATERIAL_FREE_PROVIDER_NEUTRAL_FEDERATION_REQUIREMENTS_ONLY"
        ),
        "long_lived_cloud_key": "FORBIDDEN",
        "static_provider_credential": "FORBIDDEN",
        "repository_secret_cloud_credential": "FORBIDDEN",
        "human_cloud_credential": "FORBIDDEN",
        "fork_pr_credential_issuance": "FORBIDDEN",
        "untrusted_ref_credential_issuance": "FORBIDDEN",
        "untrusted_environment_credential_issuance": "FORBIDDEN",
        "oidc_session": "SHORT_LIVED_REQUIRED_NOT_CONFIGURED",
        "least_privilege": "REQUIRED_NOT_CONFIGURED",
        "session_scope_limit": "REQUIRED_NOT_CONFIGURED",
        "session_duration_limit": "REQUIRED_NOT_CONFIGURED",
        "session_revocation": "REQUIRED_NOT_CONFIGURED",
        "target_account_project_tenant_isolation": "REQUIRED_NOT_CONFIGURED",
        "role_chaining": "FORBIDDEN",
        "privilege_escalation": "FORBIDDEN",
        "cross_environment_identity_reuse": "FORBIDDEN",
        "credential_material": "ABSENT",
        "credential_issuance_capability": "ABSENT",
        "secret_names": [],
        "secret_values": [],
    },
    "workflow_permission_intent": {
        "classification": "REPOSITORY_INERT_DISABLED_WORKFLOW_FIXTURE",
        "actual_workflow": "ACTIVE_WORKFLOW_ABSENT_INERT_FIXTURE_PRESENT",
        "id_token_write_scope": "INERT_DISABLED_FIXTURE_JOB_ONLY",
        "contents_permission": "READ_IN_INERT_DISABLED_FIXTURE_ONLY",
        "write_all": "FORBIDDEN",
        "admin_permissions": "FORBIDDEN",
        "secrets_access": "FORBIDDEN",
        "mutable_external_action_references": "FORBIDDEN",
        "unbounded_reusable_workflow_callers": "FORBIDDEN",
        "pull_request_target_credential_path": "FORBIDDEN",
    },
    "environment_protection_intent": {
        "classification": "PRODUCTION_PROTECTION_INTENT_ONLY",
        "production_environment": "REQUIRED_NOT_CONFIGURED",
        "distinct_human_approval": "REQUIRED_NOT_CONFIGURED",
        "protected_environment": "REQUIRED_NOT_CONFIGURED",
        "exact_allowed_refs": "REQUIRED_NOT_CONFIGURED",
        "target_account_project_tenant_isolation": "REQUIRED_NOT_CONFIGURED",
        "self_approval": "FORBIDDEN",
        "approval_bypass": "FORBIDDEN",
        "deployment_without_approval": "FORBIDDEN",
        "cross_environment_target_reuse": "FORBIDDEN",
    },
    "lifecycle_control_intent": {
        "classification": "PROVIDER_NEUTRAL_AUDIT_REVOCATION_ROLLBACK_INTENT_ONLY",
        "signed_provenance": "REQUIRED_NOT_CONFIGURED",
        "immutable_audit_trail": "REQUIRED_NOT_CONFIGURED",
        "credential_and_trust_revocation": "REQUIRED_NOT_CONFIGURED",
        "rollback_and_kill_switch_runbook": "REQUIRED_NOT_CONFIGURED",
        "alert_owner_and_escalation": "REQUIRED_NOT_CONFIGURED",
        "evidence_retention": "REQUIRED_NOT_CONFIGURED",
        "audit_bypass": "FORBIDDEN",
        "revocation_bypass": "FORBIDDEN",
        "rollback_bypass": "FORBIDDEN",
        "irreversible_promotion": "FORBIDDEN",
    },
    "open_decision_boundary": {
        "OD-009": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "LOW_DEVELOPMENT_CAP_PRODUCTION_DISABLED",
        },
        "OD-011": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "LOCAL_LOG_ONLY_PRODUCTION_UNAVAILABLE",
        },
        "OD-013": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "REFERENCE_REGION_ONLY_PRODUCTION_APPLY_FORBIDDEN",
        },
        "OD-015": {
            "status": "EXTERNAL_EVIDENCE_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": (
                "RECORDED_FIXTURE_ONLY_CREDENTIALS_ABSENT_PROVIDER_CALLS_FORBIDDEN"
            ),
        },
    },
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "credential_issuance": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "operations": {operation: "FORBIDDEN" for operation in NATIVE_OPERATIONS},
        "planned_actions": {action: 0 for action in ACTION_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "SOURCE_DERIVED_REPOSITORY_INERT_PROVIDER_NEUTRAL_OFFLINE_"
            "DEPLOYMENT_IDENTITY_HARNESS"
        ),
        "executable_workflow": "REPOSITORY_INERT_DISABLED_FIXTURE_ONLY",
        "target_trust_policy": "RECORDED_OFFLINE_FIXTURE_ONLY",
        "offline_trust_evaluator": "IMPLEMENTED",
        "local_recorded_evaluation": "EXECUTED_NOT_FORMAL",
        "jwt_authentication": "NOT_IMPLEMENTED_NOT_CLAIMED",
        "signature_verification": "NOT_IMPLEMENTED_NOT_CLAIMED",
        "activation_port": "DISABLED_ZERO_ACTIONS",
        "github_actions_ci_source": (
            "APPROVED_FIXED_SOURCE_NOT_TARGET_PROVIDER_SELECTION"
        ),
        "github_repository": "UNSET",
        "github_environment": "UNSET",
        "target_provider": "UNSET",
        "target_profile": "UNSET",
        "target_account_project_or_tenant": "UNSET",
        "target_region": "UNSET",
        "target_audience": "UNSET",
        "target_identity_role": "UNSET",
        "credentials": "ABSENT",
        "credential_issuance": "NOT_EXECUTED",
        "native_iac_validation": "NOT_EXECUTED",
        "workflow_inspection": "LOCAL_INERT_FIXTURE_ONLY_NOT_FORMAL",
        "provenance_audit_revocation_rollback": (
            "REQUIRED_RECORDED_FIXTURE_ONLY_NOT_FORMAL"
        ),
        "formal_tst_026": "NOT_EXECUTED",
        "hosted_github_target_provider": "NOT_EXECUTED",
        "live_oidc_federation": "NOT_EXECUTED",
        "staging_deployment": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}
TOP_LEVEL_KEYS: Final = {"sources", *EXPECTED_SECTIONS}


class GithubOidcContractError(RuntimeError):
    """A sanitized validation failure that never includes rejected values."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class NoAliasDumper(yaml.SafeDumper):
    """Deterministic YAML dumper without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found duplicate key",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class GithubOidcModel:
    """A fully validated, closed ST-1504 contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def semantic_sha256(document: object) -> str:
    try:
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("SEMANTIC_DOCUMENT_INVALID", "semantic_document")
    return sha256_bytes(content)


def _fail(code: str, field: str) -> NoReturn:
    raise GithubOidcContractError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        type(key) is str for key in value.keys()
    ):
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("CLOSED_SCHEMA_VIOLATION", field)


def _strict_match(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        value = _mapping(actual, field)
        expected_mapping = _mapping(expected, field)
        _exact_keys(value, set(expected_mapping), field)
        for key, expected_value in expected_mapping.items():
            _strict_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(expected, field)
        if not expected_list and value_list:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        if len(value_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_match(value_list[index], expected_value, f"{field}.item")
        return
    if expected is None:
        if actual is not None:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        return
    if type(actual) is not type(expected):
        _fail("TYPE_MISMATCH", field)
    if actual != expected:
        if type(expected) is bool or (type(expected) is int and expected == 0):
            _fail("SAFE_BOUNDARY_VIOLATION", field)
        _fail("FIXED_VALUE_VIOLATION", field)


def _regular_file(path: Path, field: str) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_FILE_TYPE", field)


def _real_repository_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    try:
        return root.resolve(strict=True)
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")


def _repository_regular_file(root: Path, relative: Path, field: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _fail("FILE_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_ANCESTOR", field)
    target = current / relative.name
    _regular_file(target, field)
    return target


def load_yaml(path: Path) -> Any:
    _regular_file(path, "yaml")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "yaml")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("YAML_SIZE_LIMIT", "yaml")
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", "yaml")
        return yaml.load(text, Loader=UniqueKeyLoader)
    except GithubOidcContractError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", "yaml")


def load_json(path: Path) -> Any:
    _regular_file(path, "json")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "json")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("JSON_SIZE_LIMIT", "json")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("JSON_DUPLICATE_KEY", "json")
            result[key] = value
        return result

    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _fail("JSON_INVALID", "json"),
        )
    except GithubOidcContractError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", "json")


def _repo_relative_uri(value: object) -> Path:
    if type(value) is not str or not value.startswith("repo://"):
        _fail("SOURCE_URI_INVALID", "sources")
    raw = value.removeprefix("repo://")
    if not raw or "\\" in raw:
        _fail("SOURCE_URI_INVALID", "sources")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("SOURCE_URI_INVALID", "sources")
    return Path(*pure.parts)


def _validate_sources(contract: Mapping[str, Any], root: Path) -> None:
    rows = _list(contract["sources"], "sources")
    observed: dict[str, str] = {}
    observed_order: list[str] = []
    for raw_row in rows:
        row = _mapping(raw_row, "sources.item")
        _exact_keys(row, {"uri", "sha256"}, "sources.item")
        relative = _repo_relative_uri(row["uri"])
        digest = row["sha256"]
        if type(digest) is not str or SHA256_PATTERN.fullmatch(digest) is None:
            _fail("SOURCE_DIGEST_INVALID", "sources.item.sha256")
        key = relative.as_posix()
        if key in observed:
            _fail("SOURCE_DUPLICATE", "sources")
        observed[key] = digest
        observed_order.append(key)
    if observed != PINNED_SOURCES or tuple(observed_order) != tuple(PINNED_SOURCES):
        _fail("SOURCE_INVENTORY_DRIFT", "sources")
    for source_name, expected_digest in PINNED_SOURCES.items():
        source = _repository_regular_file(root, Path(source_name), "pinned_source")
        if sha256_file(source) != expected_digest:
            _fail("SOURCE_DIGEST_MISMATCH", "pinned_source")


def _find_exact_record(
    document: Mapping[str, Any], collection: str, record_id: str, field: str
) -> Mapping[str, Any]:
    rows = _list(document.get(collection), field)
    matches = [
        _mapping(row, field)
        for row in rows
        if isinstance(row, Mapping) and row.get("id") == record_id
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_MISSING", field)
    return matches[0]


def _load_repo_yaml(root: Path, relative: str, field: str) -> Mapping[str, Any]:
    return _mapping(
        load_yaml(_repository_regular_file(root, Path(relative), field)), field
    )


def _validate_design_handoff(root: Path) -> None:
    handoff = _mapping(
        load_yaml(_repository_regular_file(root, DESIGN_HANDOFF_PATH, "handoff")),
        "handoff",
    )
    _exact_keys(
        handoff,
        {
            "schema",
            "version",
            "record_status",
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
            "open_decision_state",
        },
        "handoff",
    )
    _strict_match(handoff.get("schema"), "DESIGN_HANDOFF_V1", "handoff.schema")
    _strict_match(handoff.get("version"), 1, "handoff.version")
    _strict_match(
        handoff.get("record_status"),
        "RECORDED_DURABLE_OWNER_DECISION",
        "handoff.record_status",
    )
    _strict_match(handoff.get("approved_story"), "ST-1504", "handoff.story")
    _strict_match(
        handoff.get("source_design_refs"),
        list(EXPECTED_HANDOFF_SOURCE_DESIGN_REFS),
        "handoff.source_design_refs",
    )
    _strict_match(
        handoff.get("decision"),
        {
            "deployment_identity_provider_policy": (
                "STRICT_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY_CAPABILITY_ADMISSION"
            ),
            "ci_source_boundary": {
                "ci_source": "GITHUB_ACTIONS",
                "oidc_source": "GITHUB_ACTIONS_OIDC",
                "external_review_connector": "GITHUB",
                "classification": (
                    "APPROVED_FIXED_SOURCE_NOT_TARGET_PROVIDER_SELECTION"
                ),
                "target_provider_selected": False,
            },
            "selected_profile": None,
            "default_profile": None,
            "fallback_profile": None,
            "concrete_alternate_provider_selected": False,
            "eligible_profile_kinds": list(ELIGIBLE_PROFILE_KINDS),
            "eligibility_condition": (
                "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE"
            ),
            "aws_reference_mapping_boundary": {
                "canonical_decision_id": "INT-DEC-007",
                "architecture_id": "RAOS-ARCH-001",
                "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
                "canonical_story_deliverables": (
                    "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
                ),
                "non_aws_owner_managed_profiles": (
                    "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
                ),
                "mappings": _aws_reference_mappings(),
                "default": False,
                "implicit_fallback": False,
                "selected_binding": False,
                "eligibility_shortcut": False,
                "admission_requirement": False,
                "evidence_substitute": False,
            },
            "binding_policy": _binding_policy(),
            "required_capability_ids": [
                capability_id
                for capability_id, _required_outcome in (
                    DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES
                )
            ],
        },
        "handoff.decision",
    )
    _strict_match(
        handoff.get("open_decision_state"),
        EXPECTED_SECTIONS["open_decision_boundary"],
        "handoff.open_decision_state",
    )
    if semantic_sha256(handoff) != EXPECTED_HANDOFF_SEMANTIC_SHA256:
        _fail("HANDOFF_SEMANTIC_DRIFT", "handoff")


def _validate_authority_semantics(root: Path) -> None:
    backlog = _load_repo_yaml(
        root,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    story = _find_exact_record(backlog, "stories", "ST-1504", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1504")

    canonical_decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "canonical_decisions",
    )
    canonical_decision = _find_exact_record(
        canonical_decisions,
        "decisions",
        "INT-DEC-007",
        "canonical_decisions.decisions",
    )
    _strict_match(
        canonical_decision, EXPECTED_INT_DEC_007, "canonical_decisions.INT-DEC-007"
    )

    open_decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        decision = _find_exact_record(
            open_decisions, "items", decision_id, "open_decisions.items"
        )
        _strict_match(decision, expected, f"open_decisions.{decision_id}")

    tests = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    test = _find_exact_record(tests, "suites", "TST-026", "test_catalog.suites")
    _strict_match(test, EXPECTED_TST_026, "test_catalog.TST-026")

    controls = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "security_controls",
    )
    for control_id, requirement in EXPECTED_SECURITY_CONTROLS.items():
        control = _find_exact_record(
            controls, "controls", control_id, "security_controls.controls"
        )
        if (
            control.get("requirement") != requirement
            or control.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or control.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_CONTROL_DRIFT", control_id)

    threats = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml",
        "threat_register",
    )
    for threat_id, expected_threat in EXPECTED_THREATS.items():
        threat = _find_exact_record(
            threats, "threats", threat_id, "threat_register.threats"
        )
        _strict_match(threat, expected_threat, f"threat_register.{threat_id}")

    slices = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_implementation_slices_v1.0.yaml",
        "security_slices",
    )
    security_slice = _find_exact_record(
        slices, "slices", "SEC-SLICE-009", "security_slices.slices"
    )
    _strict_match(security_slice, EXPECTED_SECURITY_SLICE, "SEC-SLICE-009")

    architecture = _load_repo_yaml(
        root,
        "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml",
        "architecture_catalog",
    )
    architecture_document = _mapping(architecture.get("document"), "architecture")
    if architecture_document.get("id") != "RAOS-ARCH-001":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "RAOS-ARCH-001")
    deployment = _mapping(architecture.get("deployment"), "architecture.deployment")
    aws_mapping = _mapping(deployment.get("aws_mapping"), "deployment.aws_mapping")
    if aws_mapping.get("ci_cd") != "GitHub_Actions_OIDC":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.ci_cd")
    if deployment.get("infrastructure_as_code") != "Terraform":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.iac")
    if deployment.get("production_data_in_nonprod") is not False:
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.production_data")

    agents_path = _repository_regular_file(root, Path("AGENTS.md"), "agents_policy")
    try:
        agents_text = agents_path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        _fail("FILE_UNAVAILABLE", "agents_policy")
    if "初期 external review connector には GitHub のみを使用する。" not in agents_text:
        _fail("AUTHORITY_CONNECTOR_POLICY_DRIFT", "agents_policy")
    _validate_design_handoff(root)


def _validate_pr_governance_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-0107/contracts/pr-governance.v1.yaml",
        "pr_governance_contract",
    )
    if semantic_sha256(contract) != EXPECTED_PR_GOVERNANCE_CONTRACT_SEMANTIC_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "pr_governance_contract")
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-PR-GOVERNANCE-001",
            "version": "1.0.0",
            "story_id": "ST-0107",
            "status": "LOCAL_DESIRED_STATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.pr_governance.document",
    )
    policy = _mapping(contract.get("ruleset_policy"), "predecessor.ruleset")
    _strict_match(policy.get("target"), "branch", "predecessor.ruleset.target")
    _strict_match(
        policy.get("include"), ["~DEFAULT_BRANCH"], "predecessor.ruleset.include"
    )
    _strict_match(
        policy.get("desired_enforcement"), "active", "predecessor.ruleset.enforcement"
    )
    _strict_match(
        policy.get("local_application_status"),
        "NOT_EXECUTED",
        "predecessor.ruleset.application",
    )
    _strict_match(policy.get("bypass_actors"), [], "predecessor.ruleset.bypass")
    for field in ("prohibit_deletion", "prohibit_force_push", "require_linear_history"):
        _strict_match(policy.get(field), True, f"predecessor.ruleset.{field}")
    pull_request = _mapping(policy.get("pull_request"), "predecessor.pull_request")
    for field in (
        "dismiss_stale_reviews_on_push",
        "require_code_owner_review",
        "require_last_push_approval",
        "required_review_thread_resolution",
    ):
        _strict_match(
            pull_request.get(field), True, f"predecessor.pull_request.{field}"
        )
    _strict_match(
        pull_request.get("allowed_merge_methods"),
        ["squash"],
        "predecessor.pull_request.merge_methods",
    )
    _strict_match(
        pull_request.get("required_approving_review_count"),
        1,
        "predecessor.pull_request.review_count",
    )
    required_checks = _list(
        policy.get("required_status_checks"), "predecessor.required_status_checks"
    )
    if len(required_checks) != len(EXPECTED_REQUIRED_CHECKS):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "required_status_checks")
    for index, context in enumerate(EXPECTED_REQUIRED_CHECKS):
        _strict_match(
            required_checks[index],
            {
                "context": context,
                "expected_source": "github-actions",
                "integration_id_binding": "REQUIRED_AT_ACTIVATION",
            },
            "predecessor.required_status_checks.item",
        )
    _strict_match(
        policy.get("strict_required_status_checks_policy"),
        True,
        "predecessor.strict_checks",
    )
    _strict_match(
        policy.get("do_not_enforce_on_create"),
        False,
        "predecessor.enforce_on_create",
    )
    owner_categories = _mapping(
        policy.get("required_owner_categories"), "predecessor.owner_categories"
    )
    deployment = _mapping(owner_categories.get("deployment"), "predecessor.deployment")
    if "/infra/" not in _list(deployment.get("patterns"), "predecessor.patterns"):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "deployment.patterns")
    _strict_match(
        deployment.get("roles"),
        ["operations", "security"],
        "predecessor.deployment.roles",
    )

    activation = _mapping(contract.get("activation"), "predecessor.activation")
    _strict_match(
        activation.get("generator_remote_mutation"),
        "FORBIDDEN",
        "predecessor.remote_mutation",
    )
    _strict_match(
        activation.get("live_status"), "NOT_EXECUTED", "predecessor.live_status"
    )
    _strict_match(
        activation.get("formal_tst_001"),
        "NOT_EXECUTED",
        "predecessor.formal_tst_001",
    )
    prerequisites = _list(
        activation.get("prerequisites"), "predecessor.activation.prerequisites"
    )
    if not prerequisites or prerequisites[-1] != (
        "a distinct human reviewer approves the governance change"
    ):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "activation.prerequisites")

    desired_state_path = _repository_regular_file(
        root,
        Path("changes/st-0107/ruleset-policy.v1.json"),
        "pr_governance_desired_state",
    )
    desired_state = _mapping(
        load_json(desired_state_path), "pr_governance_desired_state"
    )
    if (
        semantic_sha256(desired_state)
        != EXPECTED_PR_GOVERNANCE_DESIRED_STATE_SEMANTIC_SHA256
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "pr_governance_desired_state")
    document = _mapping(desired_state.get("document"), "predecessor.desired.document")
    expected_document = {
        "id": "RAOS-GITHUB-RULESET-POLICY-001",
        "version": "1.0.0",
        "story_id": "ST-0107",
        "source_contract": "repo://changes/st-0107/contracts/pr-governance.v1.yaml",
        "generated_by": "repo://scripts/build_st0107_pr_governance.py",
        "generation_command": (
            "uv run --locked --no-sync python scripts/build_st0107_pr_governance.py"
        ),
        "artifact_kind": "DESIRED_STATE_NOT_API_PAYLOAD",
        "github_api_version": "2026-03-10",
        "live_status": "NOT_EXECUTED",
        "formal_tst_001": "NOT_EXECUTED",
    }
    _strict_match(document, expected_document, "predecessor.desired.document")
    expected_desired_state = {
        "document": expected_document,
        "ruleset": copy.deepcopy(policy),
        "activation": copy.deepcopy(activation),
    }
    _strict_match(
        desired_state, expected_desired_state, "predecessor.pr_governance_desired_state"
    )
    expected_desired_state_bytes = (
        json.dumps(
            expected_desired_state, ensure_ascii=False, indent=2, sort_keys=False
        )
        + "\n"
    ).encode("utf-8")
    try:
        actual_desired_state_bytes = desired_state_path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "pr_governance_desired_state")
    if actual_desired_state_bytes != expected_desired_state_bytes:
        _fail("PREDECESSOR_GENERATED_DRIFT", "pr_governance_desired_state")


def _validate_foundation_predecessor(root: Path) -> None:
    handoff = _load_repo_yaml(
        root,
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "foundation_handoff",
    )
    if semantic_sha256(handoff) != EXPECTED_PREDECESSOR_HANDOFF_SEMANTIC_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "foundation_handoff")

    contract = _load_repo_yaml(
        root,
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "foundation_contract",
    )
    if semantic_sha256(contract) != EXPECTED_PREDECESSOR_CONTRACT_SEMANTIC_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "foundation_contract")
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-TERRAFORM-FOUNDATION-001",
            "version": "1.2.0",
            "story_id": "ST-1501",
            "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.foundation.document",
    )
    _strict_match(
        contract.get("reference_architecture"),
        {
            "cloud": "AWS",
            "region": "ap-northeast-1",
            "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "inherited_from": "INT-DEC-007",
            "portable_core_required": True,
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "predecessor.foundation.reference_architecture",
    )
    admission = _mapping(
        contract.get("provider_neutral_foundation_admission"),
        "predecessor.foundation.admission",
    )
    _strict_match(
        admission.get("classification"),
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
        "predecessor.foundation.admission.classification",
    )
    _strict_match(
        admission.get("admission_status"),
        "NOT_EVALUATED",
        "predecessor.foundation.admission.status",
    )
    _strict_match(
        admission.get("eligible"), False, "predecessor.foundation.admission.eligible"
    )
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(
            admission.get(field), None, f"predecessor.foundation.admission.{field}"
        )
    _strict_match(
        admission.get("aws_reference_boundary"),
        {
            "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "canonical_story_deliverables": (
                "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
            ),
            "non_aws_owner_managed_profiles": (
                "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
            ),
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "predecessor.foundation.admission.aws_reference_boundary",
    )
    _strict_match(
        contract.get("selected_configuration"),
        {
            "cloud_provider": None,
            "production_region": None,
            "backup_region": None,
            "development_account_id": None,
            "production_account_id": None,
            "terraform_cli_version": None,
            "provider_plugins": [],
            "state_backend": None,
            "credential_source": None,
            "network_cidrs": [],
            "availability_zones": [],
            "kms_key_reference": None,
            "monthly_budget_jpy": None,
            "resource_definitions": [],
        },
        "predecessor.foundation.selection",
    )
    execution = _mapping(
        contract.get("execution_boundary"), "predecessor.foundation.execution"
    )
    _strict_match(
        execution,
        {
            "activation_enabled": False,
            "activation_status": "DISABLED",
            "native_plan_status": "NOT_EXECUTED",
            "network_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "live_provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "deploy_action": "FORBIDDEN",
            "release_action": "FORBIDDEN",
            "production_action": "FORBIDDEN",
            "commands": {
                command: "FORBIDDEN" for command in FOUNDATION_NATIVE_COMMANDS
            },
            "validation_commands": {
                "version": "OFFLINE_READ_ONLY",
                "format": "OFFLINE_READ_ONLY",
                "validate": "OFFLINE_READ_ONLY",
            },
            "planned_actions": {action: 0 for action in ACTION_NAMES},
        },
        "predecessor.foundation.execution",
    )
    extension = _mapping(contract.get("extension_contract"), "predecessor.extension")
    _strict_match(
        extension,
        {
            "current_resource_payloads": "FORBIDDEN",
            "successor_contract_revision_required": True,
            "native_toolchain_pin_required_before_hcl": True,
            "validation_only_hcl_module_available": True,
            "successor_resource_module_required": True,
            "successors": {
                "ST-1502": "DATA_SERVICES",
                "ST-1503": "COMPUTE_CDN_WAF",
            },
        },
        "predecessor.foundation.extension",
    )
    evidence = _mapping(
        contract.get("evidence_boundary"), "predecessor.foundation.evidence"
    )
    _strict_match(
        evidence,
        {
            "deliverable_classification": (
                "SOURCE_DERIVED_PROVIDER_NEUTRAL_HCL_FOUNDATION"
            ),
            "executable_terraform": ("VALIDATABLE_NO_RESOURCE_NO_PROVIDER_HCL_MODULE"),
            "terraform_cli": "PINNED_VALIDATION_ONLY_1_15_9",
            "provider_plugins": "NONE_REQUIRED_NOT_SELECTED",
            "offline_native_validation_path": "IMPLEMENTED",
            "local_native_validation": "EXECUTED_NOT_FORMAL",
            "remote_state": "NOT_CONFIGURED",
            "provider_account_or_project": "UNSET",
            "credentials": "ABSENT",
            "formal_tst_026": "NOT_EXECUTED",
            "live_staging_release_production": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
        "predecessor.foundation.evidence",
    )

    toolchain = _mapping(
        contract.get("iac_validation_toolchain"),
        "predecessor.foundation.iac_validation_toolchain",
    )
    _strict_match(
        {
            "classification": toolchain.get("classification"),
            "product": toolchain.get("product"),
            "version": toolchain.get("version"),
            "required_version_constraint": toolchain.get("required_version_constraint"),
            "platform": toolchain.get("platform"),
        },
        {
            "classification": "PINNED_VALIDATION_ONLY_NO_INFRASTRUCTURE_AUTHORITY",
            "product": "Terraform",
            "version": "1.15.9",
            "required_version_constraint": "= 1.15.9",
            "platform": "linux_amd64",
        },
        "predecessor.foundation.iac_validation_toolchain.summary",
    )
    validation_boundary = _mapping(
        toolchain.get("validation_boundary"),
        "predecessor.foundation.iac_validation_boundary",
    )
    _strict_match(
        validation_boundary.get("allowed_commands"),
        ["version -json", "fmt -check -recursive", "validate -json"],
        "predecessor.foundation.iac_validation_boundary.allowed_commands",
    )
    for field in (
        "normal_check_network_access",
        "initialization",
        "provider_installation",
        "module_downloads",
        "backend_access",
        "credential_inheritance",
        "repository_writes",
    ):
        _strict_match(
            validation_boundary.get(field),
            "FORBIDDEN",
            f"predecessor.foundation.iac_validation_boundary.{field}",
        )
    _strict_match(
        validation_boundary.get("provider_plugins"),
        [],
        "predecessor.foundation.iac_validation_boundary.provider_plugins",
    )

    hcl_module = _mapping(
        contract.get("hcl_foundation_module"),
        "predecessor.foundation.hcl_foundation_module",
    )
    _strict_match(
        hcl_module.get("classification"),
        "PROVIDER_NEUTRAL_VALIDATION_ONLY_FOUNDATION_ADMISSION_MODULE",
        "predecessor.foundation.hcl_foundation_module.classification",
    )
    _strict_match(
        hcl_module.get("default_disabled"),
        True,
        "predecessor.foundation.hcl_foundation_module.default_disabled",
    )
    for field in (
        "provider_requirements",
        "provider_blocks",
        "backend_blocks",
        "cloud_blocks",
        "module_blocks",
        "data_blocks",
        "resource_blocks",
        "provisioners",
        "selected_bindings",
        "capability_mappings",
    ):
        _strict_match(
            hcl_module.get(field),
            [],
            f"predecessor.foundation.hcl_foundation_module.{field}",
        )
    _strict_match(
        hcl_module.get("planned_actions"),
        {action: 0 for action in ACTION_NAMES},
        "predecessor.foundation.hcl_foundation_module.planned_actions",
    )

    toolchain_lock_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"),
        "foundation_toolchain_lock",
    )
    toolchain_lock = _mapping(
        load_json(toolchain_lock_path), "foundation_toolchain_lock"
    )
    if (
        semantic_sha256(toolchain_lock)
        != EXPECTED_PREDECESSOR_TOOLCHAIN_LOCK_SEMANTIC_SHA256
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "foundation_toolchain_lock")

    plan_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"),
        "foundation_plan",
    )
    plan = _mapping(load_json(plan_path), "foundation_plan")
    if semantic_sha256(plan) != EXPECTED_PREDECESSOR_PLAN_SEMANTIC_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "foundation_plan")
    expected_plan = {
        "document": {
            "id": "RAOS-TERRAFORM-FOUNDATION-REFERENCE-PLAN-001",
            "version": "1.2.0",
            "story_id": "ST-1501",
            "source_contract": (
                "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
            ),
            "generated_by": "repo://scripts/build_st1501_terraform_foundation.py",
            "generation_command": (
                "uv run --locked --no-sync python "
                "scripts/build_st1501_terraform_foundation.py"
            ),
            "artifact_kind": evidence["deliverable_classification"],
            "executable": True,
            "executable_for": ["fmt", "validate"],
            "infrastructure_actions": False,
            "implementation_scope": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        },
        "reference_architecture": copy.deepcopy(contract["reference_architecture"]),
        "provider_neutral_foundation_admission": copy.deepcopy(admission),
        "selected_configuration": copy.deepcopy(contract["selected_configuration"]),
        "iac_validation_toolchain": copy.deepcopy(contract["iac_validation_toolchain"]),
        "hcl_foundation_module": copy.deepcopy(contract["hcl_foundation_module"]),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "native_commands": copy.deepcopy(execution["commands"]),
            "validation_commands": copy.deepcopy(execution["validation_commands"]),
        },
        "future_requirements": {
            "remote_state": copy.deepcopy(contract["state_requirements"]),
            "account_separation": {
                "requirement": contract["account_requirements"][
                    "separate_development_and_production"
                ],
                "development_account_id": contract["account_requirements"][
                    "development_account_id"
                ],
                "production_account_id": contract["account_requirements"][
                    "production_account_id"
                ],
            },
            "production_change_control": copy.deepcopy(
                contract["production_change_requirements"]
            ),
        },
        "extension_contract": copy.deepcopy(extension),
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }
    _strict_match(plan, expected_plan, "predecessor.foundation.plan")
    expected_plan_bytes = (
        json.dumps(expected_plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        actual_plan_bytes = plan_path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "foundation_plan")
    if actual_plan_bytes != expected_plan_bytes:
        _fail("PREDECESSOR_GENERATED_DRIFT", "foundation_plan")


def _validate_predecessor_semantics(root: Path) -> None:
    _validate_pr_governance_predecessor(root)
    _validate_foundation_predecessor(root)


def _validate_capability_inventory(contract: Mapping[str, Any]) -> None:
    admission = _mapping(
        contract["provider_neutral_deployment_identity_admission"],
        "provider_neutral_deployment_identity_admission",
    )
    rows = _list(
        admission["capability_mapping_requirements"],
        "provider_neutral_deployment_identity_admission."
        "capability_mapping_requirements",
    )
    observed: list[str] = []
    for row in rows:
        item = _mapping(
            row,
            "provider_neutral_deployment_identity_admission."
            "capability_mapping_requirements.item",
        )
        capability_id = item.get("capability_id")
        if type(capability_id) is not str:
            _fail("TYPE_MISMATCH", "capability_mapping.capability_id")
        observed.append(capability_id)
    expected = [
        capability_id
        for capability_id, _required_outcome in (
            DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES
        )
    ]
    if len(observed) != len(set(observed)):
        _fail("DUPLICATE_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in expected for capability_id in observed):
        _fail("UNKNOWN_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in observed for capability_id in expected):
        _fail("MISSING_CAPABILITY_MAPPING", "capability_mapping")
    if observed != expected:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "capability_mapping")


def validate_contract(contract: object, root: Path = REPO_ROOT) -> GithubOidcModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    _validate_capability_inventory(value)
    for section, expected in EXPECTED_SECTIONS.items():
        _strict_match(value[section], expected, section)
    if semantic_sha256(value) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
        _fail("CONTRACT_SEMANTIC_DRIFT", "contract")
    return GithubOidcModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> GithubOidcModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: GithubOidcModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: GithubOidcModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-GITHUB-OIDC-REFERENCE-PLAN-001",
            "version": "2.0.0",
            "story_id": "ST-1504",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "harness_execution": "OFFLINE_RECORDED_FIXTURE_ONLY",
        },
        "predecessor_bindings": _section(model, "predecessor_bindings"),
        "ci_source_boundary": _section(model, "ci_source_boundary"),
        "reference_architecture": _section(model, "reference_architecture"),
        "provider_neutral_deployment_identity_admission": _section(
            model, "provider_neutral_deployment_identity_admission"
        ),
        "logical_identity_path": _section(model, "reference_intent"),
        "recorded_fixture_boundary": _section(model, "recorded_fixture_boundary"),
        "offline_trust_evaluator": _section(model, "offline_trust_evaluator"),
        "activation_port": _section(model, "activation_port"),
        "selected_bindings": _section(model, "selected_bindings"),
        "trust_constraints": _section(model, "trust_constraints"),
        "credential_boundary": _section(model, "credential_boundary"),
        "workflow_permissions": _section(model, "workflow_permission_intent"),
        "environment_protection": _section(model, "environment_protection_intent"),
        "lifecycle_controls": _section(model, "lifecycle_control_intent"),
        "open_decision_boundary": _section(model, "open_decision_boundary"),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "credential_issuance": execution["credential_issuance"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "operations": copy.deepcopy(execution["operations"]),
        },
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }


def render_reference_plan(model: GithubOidcModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def recorded_claims_document() -> dict[str, object]:
    """Return a token-free decoded claim-shape fixture in an invalid namespace."""

    return {
        "schema": "RAOS_RECORDED_GITHUB_OIDC_CLAIMS_V1",
        "version": 1,
        "fixture_id": FIXTURE_ID,
        "classification": "SYNTHETIC_DECODED_CLAIM_SHAPE_ONLY",
        "authentication_status": "NOT_AUTHENTICATED",
        "signature_verification_status": "NOT_PERFORMED",
        "token_material": "ABSENT",
        "claims": copy.deepcopy(RECORDED_CLAIMS),
    }


def recorded_trust_policy_document() -> dict[str, object]:
    """Return the provider-neutral policy consumed only by the offline evaluator."""

    return {
        "schema": "RAOS_OFFLINE_GITHUB_OIDC_TRUST_POLICY_V1",
        "version": 1,
        "policy_id": POLICY_ID,
        "fixture_id": FIXTURE_ID,
        "classification": ("RECORDED_SYNTHETIC_PROVIDER_NEUTRAL_OFFLINE_FIXTURE"),
        "source_system": "GITHUB_ACTIONS_OIDC",
        "authentication_authority": "NONE",
        "credential_issuance_authority": "NONE",
        "expected_claims": copy.deepcopy(RECORDED_CLAIMS),
        "trust": {
            "exact_match_required": True,
            "wildcards_allowed": False,
            "fork_pull_request_allowed": False,
            "pull_request_allowed": False,
            "pull_request_target_allowed": False,
            "reusable_workflow_callers": [],
        },
        "session": {
            "requested_duration_seconds": 600,
            "maximum_duration_seconds": 900,
            "permission_scopes": ["deployment-fixture:evaluate"],
            "least_privilege_required": True,
            "role_chaining_allowed": False,
            "privilege_escalation_allowed": False,
            "static_credentials_allowed": False,
            "human_credentials_allowed": False,
            "cross_environment_reuse_allowed": False,
        },
        "approval": {
            "protected_environment_required": True,
            "distinct_human_approval_required": True,
            "self_approval_allowed": False,
            "bypass_allowed": False,
            "approval_record_status": "NOT_EXECUTED",
        },
        "lifecycle": {
            "signed_provenance_required": True,
            "immutable_audit_required": True,
            "revocation_required": True,
            "rollback_required": True,
            "evidence_retention_required": True,
            "evidence_status": "RECORDED_FIXTURE_ONLY_NOT_FORMAL",
        },
        "activation": {
            "enabled": False,
            "status": "DISABLED",
            "planned_actions": {action: 0 for action in ACTION_NAMES},
        },
    }


def recorded_evaluation_document() -> dict[str, object]:
    """Return a deterministic policy-match-only result with all authority denied."""

    reason_codes = [
        "RECORDED_EXACT_CLAIMS_MATCHED",
        "SIGNATURE_NOT_VERIFIED",
        "AUTHENTICATION_NOT_PERFORMED",
        "ACTIVATION_DISABLED",
        "CREDENTIAL_ISSUANCE_FORBIDDEN",
        "DEPLOYMENT_FORBIDDEN",
    ]
    payload: dict[str, object] = {
        "policy_id": POLICY_ID,
        "fixture_id": FIXTURE_ID,
        "classification": "OFFLINE_POLICY_MATCH_ONLY_NOT_AUTHENTICATION",
        "policy_match": True,
        "authentication_status": "NOT_AUTHENTICATED",
        "signature_verification_status": "NOT_PERFORMED",
        "credential_issuance_authorized": False,
        "activation_authorized": False,
        "deployment_authorized": False,
        "action_count": 0,
        "reason_codes": reason_codes,
    }
    return {
        "schema": "RAOS_OFFLINE_TRUST_EVALUATION_V1",
        "version": 1,
        **payload,
        "evidence_digest": semantic_sha256(payload),
        "formal_evidence": "NOT_EXECUTED",
    }


def inert_workflow_document() -> dict[str, object]:
    """Return valid workflow syntax stored outside GitHub's active workflow path."""

    return {
        "name": "ST-1504 repository-inert deployment identity fixture",
        "on": {"workflow_dispatch": {}},
        "permissions": {},
        "jobs": {
            "recorded_deployment_identity_fixture": {
                "if": "${{ false }}",
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 1,
                "environment": RECORDED_CLAIMS["environment"],
                "permissions": {"contents": "read", "id-token": "write"},
                "steps": [
                    {
                        "name": "Fail-closed repository-inert fixture sentinel",
                        "shell": "bash",
                        "run": "set -euo pipefail\nexit 1\n",
                    }
                ],
            }
        },
    }


def _render_json(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_inert_workflow() -> bytes:
    return yaml.dump(
        inert_workflow_document(),
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _repository_regular_file(root, relative, "source_artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: GithubOidcModel,
    generated_outputs: Mapping[Path, bytes],
    root: Path = REPO_ROOT,
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    admission = _mapping(
        model.contract["provider_neutral_deployment_identity_admission"],
        "provider_neutral_deployment_identity_admission",
    )
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-GITHUB-OIDC-MANIFEST-001",
            "version": "2.0.0",
            "story_id": "ST-1504",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "contract_sha256": sha256_file(
                _repository_regular_file(root, CONTRACT_PATH, "contract")
            ),
            "authority_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in AUTHORITY_SOURCES.items()
            ],
            "predecessor_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in PREDECESSOR_SOURCES.items()
            ],
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(GENERATED_NON_MANIFEST_PATHS),
        "generated_artifacts": [
            {
                "uri": f"repo://{relative.as_posix()}",
                "bytes": len(generated_outputs[relative]),
                "sha256": sha256_bytes(generated_outputs[relative]),
            }
            for relative in GENERATED_NON_MANIFEST_PATHS
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": evidence["deliverable_classification"],
            "activation": execution["activation_status"],
            "planned_actions": copy.deepcopy(execution["planned_actions"]),
            "admission_status": admission["admission_status"],
            "eligible": admission["eligible"],
            "selected_profile_id": admission["selected_profile_id"],
            "selected_profile_kind": admission["selected_profile_kind"],
            "selected_provider_name": admission["selected_provider_name"],
            "default_profile_id": admission["default_profile_id"],
            "fallback_profile_id": admission["fallback_profile_id"],
            "configured_mapping_count": admission["mapping_policy"][
                "configured_mapping_count"
            ],
            "required_capability_count": len(DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES),
            "aws_reference_only": True,
            "aws_reference_role": admission["aws_reference_boundary"]["role"],
            "canonical_story_deliverables": admission["aws_reference_boundary"][
                "canonical_story_deliverables"
            ],
            "portable_implementation_paths": admission["aws_reference_boundary"][
                "non_aws_owner_managed_profiles"
            ],
            "aws_reference_default": admission["aws_reference_boundary"]["default"],
            "aws_reference_implicit_fallback": admission["aws_reference_boundary"][
                "implicit_fallback"
            ],
            "aws_reference_selected_binding": admission["aws_reference_boundary"][
                "selected_binding"
            ],
            "aws_reference_eligibility_shortcut": admission["aws_reference_boundary"][
                "eligibility_shortcut"
            ],
            "aws_reference_admission_requirement": admission["aws_reference_boundary"][
                "admission_requirement"
            ],
            "aws_reference_evidence_substitute": admission["aws_reference_boundary"][
                "evidence_substitute"
            ],
            "selected_repository": selection["github_repository"],
            "selected_environment": selection["github_environment_name"],
            "selected_target_provider": selection["target_provider_name"],
            "selected_target_account_project_or_tenant": selection[
                "target_account_project_or_tenant"
            ],
            "selected_target_region": selection["target_region"],
            "selected_target_audience": selection["target_audience"],
            "selected_target_identity_role": selection[
                "target_identity_role_reference"
            ],
            "federation_trust_material": selection["federation_trust_material"],
            "workflow_file_path": selection["workflow_file_path"],
            "recorded_fixture_id": FIXTURE_ID,
            "recorded_claims_sha256": sha256_bytes(
                generated_outputs[CLAIMS_FIXTURE_PATH]
            ),
            "recorded_trust_policy_sha256": sha256_bytes(
                generated_outputs[TRUST_POLICY_FIXTURE_PATH]
            ),
            "recorded_evaluation_sha256": sha256_bytes(
                generated_outputs[EVALUATION_FIXTURE_PATH]
            ),
            "inert_workflow_sha256": sha256_bytes(
                generated_outputs[WORKFLOW_FIXTURE_PATH]
            ),
            "offline_evaluation_digest": recorded_evaluation_document()[
                "evidence_digest"
            ],
            "offline_trust_evaluator": evidence["offline_trust_evaluator"],
            "local_recorded_evaluation": evidence["local_recorded_evaluation"],
            "jwt_authentication": evidence["jwt_authentication"],
            "signature_verification": evidence["signature_verification"],
            "activation_port": evidence["activation_port"],
            "credentials": evidence["credentials"],
            "credential_issuance": evidence["credential_issuance"],
            "workflow_inspection": evidence["workflow_inspection"],
            "formal_tst_026": evidence["formal_tst_026"],
            "hosted_github_target_provider": evidence["hosted_github_target_provider"],
            "live_oidc_federation": evidence["live_oidc_federation"],
            "staging_deployment": evidence["staging_deployment"],
            "release": evidence["release"],
            "production": evidence["production"],
            "effective_canonical_status": evidence["effective_canonical_status"],
        },
    }
    return yaml.dump(
        document,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    model = load_and_validate_contract(root)
    generated_outputs = {
        REFERENCE_PLAN_PATH: render_reference_plan(model),
        CLAIMS_FIXTURE_PATH: _render_json(recorded_claims_document()),
        TRUST_POLICY_FIXTURE_PATH: _render_json(recorded_trust_policy_document()),
        EVALUATION_FIXTURE_PATH: _render_json(recorded_evaluation_document()),
        WORKFLOW_FIXTURE_PATH: render_inert_workflow(),
    }
    return {
        **generated_outputs,
        MANIFEST_PATH: render_manifest(model, generated_outputs, root),
    }


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_OUTPUT_PATH", "output")
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            try:
                current.mkdir(mode=0o755)
                metadata = current.lstat()
            except OSError:
                _fail("OUTPUT_DIRECTORY_FAILED", "output")
        except OSError:
            _fail("OUTPUT_DIRECTORY_FAILED", "output")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
    return current


def _output_file(root: Path, relative: Path) -> Path:
    parent = _safe_output_parent(root, relative, create=False)
    target = parent / relative.name
    _regular_file(target, "generated_output")
    return target


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    parent = _safe_output_parent(root, relative, create=True)
    target = parent / relative.name
    if target.exists() or target.is_symlink():
        _regular_file(target, "generated_output")
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{relative.name}.", suffix=".tmp", dir=parent
        )
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        _fail("OUTPUT_WRITE_FAILED", "output")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = _output_file(root, relative)
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
    for relative in GENERATED_PATHS:
        _atomic_write(root, relative, outputs[relative])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Build the repository-inert ST-1504 GitHub OIDC offline harness.")
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed generated bytes without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except GithubOidcContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1504 GitHub OIDC check passed")
    else:
        print("ST-1504 GitHub OIDC artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
