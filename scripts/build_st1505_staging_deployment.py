#!/usr/bin/env python3
"""Build the disabled, non-executable ST-1505 staging reference artifacts."""

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
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CONTRACT_PATH: Final = Path("changes/st-1505/contracts/staging-deployment.v1.yaml")
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1505/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1505_staging_deployment.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py"
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
    "docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml": (
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0"
    ),
    "docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml": (
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2"
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
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
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
    DESIGN_HANDOFF_PATH.as_posix(): (
        "5438a2971ab60472e5145a0af7f5c9be03b30463484a483d188b77e014d1c9b5"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "488281f5178250ce90d0f01548ffbc390fc023eae3e27ea04291a44f263399f9"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "a933f47a6c06c6b1d8d57dae84a815018bd00b3bc0d576a8e68fc11621c7ac70"
    ),
    "scripts/build_st1501_terraform_foundation.py": (
        "8c24545a0b992db2116e956b8ff0948066ca86b78026aa546417a6be025a9ec8"
    ),
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml": (
        "ee41e5d240322e084b0a9a945ac8a06347267e55dd6552a5669772925c9497e5"
    ),
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "bb5eefc8bc5cfa62905bf87436b457cfaf3d40ac16e1d285ffabb13c8c3e1041"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "84868985990b42dfb6824887582be127962af480d9f48cf50fa103ad92e01699"
    ),
    "scripts/build_st1502_data_services.py": (
        "ba974d9d44c2184f6809ba68e14c8cd9df422573cd517dd957015e070932a6cf"
    ),
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml": (
        "2a6da0fa771153cafe2aa79f01b09843832e032ec13a29dd34884a31ae0c519d"
    ),
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml": (
        "07e78229b21b181c951fa6c7f7fa9cf601b9118149f8162691189b3739d8dd60"
    ),
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json": (
        "62d0d2975ebc28951340488eed2da3138b29729b56d7638290deda886651d4d8"
    ),
    "scripts/build_st1503_compute_edge.py": (
        "9c322273a8c9a1106ee777bc7747d519d059e719fb40a91d4333209e06e8361d"
    ),
    "changes/st-0107/contracts/pr-governance.v1.yaml": (
        "b387255fa65577051203b0fb1f935d5340c0d00f1285fd25557a38776fb07d92"
    ),
    "changes/st-0107/ruleset-policy.v1.json": (
        "e999838c2f592e3795aa79222bcfbc8cedf4b59bad06024f0328ebd65b3e11f5"
    ),
    "changes/st-1504/"
    "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml": (
        "36ac3095033f8ad7c91deac77f6a6689d354dc63dd46f03350e0bf68b3ccca04"
    ),
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml": (
        "c9b01688f58be30dd561b9845aef2d8725c35af3ea9ce50e187c1a0866da011b"
    ),
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json": (
        "1a929da93ef2610db8a0d8a147fe52e32b01ddb6f8989b06dc6cb8abd41003d4"
    ),
    "scripts/build_st1504_github_oidc.py": (
        "996176c1f977d39dd1dbb36fa7b1159c35f5fa1e5adacf7c21f1dc93919e248f"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    Path("changes/st-1505/README.md"),
    Path("scripts/build_st1505_staging_deployment.py"),
    Path("tests/st1505/conftest.py"),
    Path("tests/st1505/test_contract.py"),
    Path("tests/st1505/test_generation.py"),
    Path("tests/st1505/test_negative_cases.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1505",
    "epic_id": "EPIC-15",
    "title": "Staging deployment pipeline",
    "objective": "artifact promotion、migration、smoke、rollback",
    "depends_on": ["ST-1502", "ST-1503", "ST-1504"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["staging pipeline"],
    "acceptance_criteria": ["repeatable deployment"],
    "test_suites": ["TST-009", "TST-022"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
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
    "OD-002": {
        "id": "OD-002",
        "topic": "site_name_and_domain",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Staging public UI",
        "owner": "Product Owner",
        "decision_needed": "ブランド名、ドメイン、運営者表記を決定",
        "default_behavior": "example.invalidと仮ブランドを使用し外部公開禁止",
        "blocking": True,
    },
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
    "OD-010": {
        "id": "OD-010",
        "topic": "oidc_provider",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Admin authentication",
        "owner": "Security Owner",
        "decision_needed": "Cognitoまたは承認済みOIDC Providerを選定",
        "default_behavior": "Local fake authはdevelopmentのみ。外部公開不可",
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
    "OD-014": {
        "id": "OD-014",
        "topic": "retention_periods",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Deletion jobs",
        "owner": "Privacy/Finance/Legal",
        "decision_needed": (
            "Analytics個票、Security Log、AI Artifact、成果データの保持期間を承認"
        ),
        "default_behavior": "自動削除Jobは無効、最小収集",
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
EXPECTED_TESTS: Final = {
    "TST-009": {
        "id": "TST-009",
        "name": "Migration zero-to-latest",
        "layer": "database",
        "purpose": "空DBから最新版へ到達",
        "candidate_tools": ["migration runner", "PostgreSQL 18"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    "TST-022": {
        "id": "TST-022",
        "name": "Browser functional E2E",
        "layer": "ui",
        "purpose": "主要WorkflowとPublic view",
        "candidate_tools": ["Playwright"],
        "release_blocking": True,
        "environments": ["CI", "staging"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-IAM-010": "長期AWS keyをActions secretに置かない",
    "SEC-INFRA-001": "RDS/worker/object admin endpointをPublicにしない",
    "SEC-INFRA-002": "Public ingressを管理Pointへ限定",
    "SEC-SDLC-002": "Security、migration、contractsへowner review",
    "SEC-SDLC-004": "Dependency/container vulnerability scan",
    "SEC-SDLC-006": "History/PR/artifactをscan",
    "SEC-SDLC-007": "Release artifactのSBOM生成",
    "SEC-SDLC-008": "Build provenance/attestationを生成",
    "SEC-SDLC-010": "DDL/role/data migrationを独立review",
    "SEC-SDLC-011": "Critical/High未解決でRelease禁止",
}
EXPECTED_THREATS: Final = {
    "THR-007": "pin、SCA、SBOM、provenance",
    "THR-008": "OIDC trust condition、environment approval",
    "THR-019": "separate OpenAPI/role/readmodel、schema scan",
    "THR-020": "structured redacted logs、log tests",
}

MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _phase(name: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "DISABLED",
        "execution_status": "NOT_EXECUTED",
        "external_action": "FORBIDDEN",
        "action_count": 0,
    }


STAGING_TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_bindings",
    "reference_architecture",
    "provider_neutral_staging_admission",
    "open_decision_boundary",
    "environment_boundary",
    "selected_bindings",
    "artifact_admission_intent",
    "protected_environment_intent",
    "migration_intent",
    "health_security_runtime_intent",
    "transport_security_intent",
    "observability_alerting_intent",
    "isolation_residency_budget_intent",
    "target_adapter_intent",
    "rollback_restore_intent",
    "logical_phases",
    "execution_boundary",
    "evidence_boundary",
)
HANDOFF_TOP_LEVEL_KEYS: Final = (
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
)
EXPECTED_HANDOFF_LIST_SECTIONS: Final = {
    "approved_scope": (
        "Define an additional provider-neutral staging admission boundary for "
        "Full RAOS without making AWS or any provider a selected, default, "
        "fallback, or staging-admission binding.",
        "Bind the provider-neutral ST-1501 foundation, ST-1502 "
        "data-services, ST-1503 compute-edge, and ST-1504 "
        "deployment-identity handoffs, contracts, and reference plans as "
        "mandatory future dependency evidence.",
        "Preserve AWS Tokyo and the AWS service mappings as the current "
        "Canonical Reference Architecture inherited from INT-DEC-007 and "
        "RAOS-ARCH-001.",
        "Preserve the Canonical AWS-specific ST-1505 objective and staging "
        "pipeline deliverable as authoritative, not erased, replaced, or "
        "completed by this portability overlay.",
        "Admit non-AWS and owner-managed staging profiles only as additional "
        "portable implementation paths with identical complete capabilities "
        "and evidence.",
        "Keep every current target, deployment, migration, runtime, "
        "rollback, release, and Production binding unset and every "
        "external action disabled.",
    ),
    "source_design_refs": (
        "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "repo://docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml#INT-DEC-007",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-002",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-009",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-010",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-011",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-014",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-015",
        "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-1505",
        "repo://changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "repo://changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
        "repo://changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
        "repo://changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
        "repo://docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md#RAOS-ARCH-001",
        "repo://docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml#RAOS-ARCH-001",
        "repo://docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md#RAOS-SEC-001",
        "repo://docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md#RAOS-OPS-001",
        "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-009",
        "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-022",
    ),
    "rationale": (
        "Staging is a release-evidence environment, so eligibility must depend "
        "on complete capabilities and evidence rather than a cloud or service "
        "name.",
        "The four provider-neutral predecessor profiles define complementary "
        "foundation, data, compute-edge, and deployment-identity boundaries and "
        "none currently selects a live profile.",
        "Exact dependency admission prevents an AWS label, predecessor "
        "completion claim, or local reference artifact from substituting for "
        "explicit mappings and identical evidence.",
        "Keeping target bindings null and all actions disabled preserves "
        "Canonical human gates and unresolved decisions while allowing a "
        "reversible local contract implementation.",
    ),
    "rejected_alternatives": (
        "Require AWS, AWS Tokyo, an AWS account, or AWS service "
        "names merely because they remain in the current Canonical "
        "Reference Architecture.",
        "Treat Terraform, RDS, S3, SQS, ECS, Fargate, CloudFront, "
        "WAF, Route53, ACM, IAM, or GitHub OIDC labels as staging "
        "eligibility or evidence.",
        "Select another cloud or owner-managed target without "
        "complete dependency mappings, target-adapter evidence, "
        "residency, budget, identity, security, operations, and "
        "release evidence.",
        "Allow missing, unknown, duplicate, partial, implicit, "
        "defaulted, fallback, name-only, or "
        "canonical-reference-designation-only dependency or capability "
        "mappings.",
        "Execute a deployment, migration, smoke request, provider "
        "call, rollback, release, or Production action from a local "
        "reference plan.",
    ),
    "constraints": (
        "Every ST-1501 through ST-1504 handoff, contract, and generated plan "
        "remains raw-hash, semantic-hash, and deterministic-byte bound.",
        "A future staging profile must explicitly satisfy every predecessor "
        "provider-neutral admission and exactly one mapping for every staging "
        "capability.",
        "Build admission requires an immutable digest, SBOM, vulnerability "
        "result, signed provenance, and promotion without rebuild.",
        "Migration admission requires Expand-Migrate-Contract compatibility, "
        "a dry run, lock evidence, forward-fix readiness, an assigned "
        "migration owner, independent migration review, and no destructive "
        "current-release Contract step.",
        "Protected environment admission requires exact repository, ref, "
        "workflow, environment, audience, subject, and independent human "
        "approval evidence.",
        "Runtime admission requires liveness, readiness, dependency, "
        "migration-compatibility, Public/Admin/Internal isolation, smoke, "
        "security, and browser workflow evidence.",
        "Every artifact, promotion, identity federation, deployment, "
        "migration, smoke/runtime, telemetry/alerting, rollback/restore, and "
        "target-adapter network flow requires authenticated encrypted "
        "transport, exact peer/hostname verification, and downgrade-resistant "
        "evidence.",
        "Telemetry, alerts, release markers, rollback, restore, integrity, "
        "residency, isolation, budget, and automatic-stop evidence are "
        "mandatory and provider-neutral.",
        "The target adapter must expose provider-neutral deployment "
        "operations and evidence without provider SDK types entering the "
        "domain contract.",
        "Site/domain, identity provider, notification, region/residency, "
        "retention/deletion, budget, credentials, provider, profile, "
        "account/project/tenant, backend, identity, adapter, and resource "
        "choices remain unset while Open Decisions are unresolved.",
        "No credential, provider call, network access, external write, "
        "deployment, migration, release, staging, or Production action is "
        "authorized by this record.",
    ),
    "security_and_approval_gates": (
        "Preserve security, operations, release, "
        "migration-owner, protected-environment, and "
        "independent human approval gates.",
        "Preserve exact repository/ref/workflow subject "
        "binding, short-lived identity, no static cloud "
        "secret, least privilege, provenance, audit, "
        "revocation, and rollback requirements.",
        "Preserve Critical/High release blocking, SBOM, "
        "vulnerability scan, signed provenance, data "
        "isolation, transport, retention, restore, and "
        "residency evidence.",
        "Preserve OD-002, OD-009, OD-010, OD-011, OD-013, "
        "OD-014, and OD-015 blocking states until their "
        "owners provide valid evidence.",
        "Require identical security, operations, release, "
        "supply-chain, migration, runtime, observability, "
        "rollback/restore, isolation, residency, budget, and "
        "adapter evidence for every eligible provider kind.",
        "Never infer eligibility from AWS or another provider "
        "label, GitHub source status, Canonical Reference Architecture "
        "status, "
        "predecessor completion, or local generator/test "
        "success.",
    ),
    "acceptance_criteria": (
        "The ST-1505 source and generated reference expose a closed "
        "provider-neutral dependency and capability admission "
        "inventory with no selected, default, or fallback target.",
        "All four provider-neutral predecessors remain exact inputs "
        "and each future profile must satisfy its complete mapping "
        "and identical-evidence contract.",
        "Unknown, missing, duplicate, partial, implicit, label-only, "
        "default, fallback, predecessor-only, or reference-only "
        "admission attempts fail closed.",
        "AWS staging remains the current Canonical Reference Architecture, "
        "while that status alone cannot satisfy dependency, capability, "
        "admission, or evidence requirements.",
        "The Canonical AWS-specific ST-1505 objective and staging pipeline "
        "deliverable remain authoritative and NOT_STARTED/NOT_EXECUTED; "
        "this overlay neither erases, replaces, nor completes them.",
        "Non-AWS and owner-managed staging profiles remain additional portable "
        "implementation paths admitted only by identical complete "
        "capabilities and evidence.",
        "Build/SBOM/provenance, independent migration review, "
        "protected approval, smoke/security/runtime, cross-capability "
        "transport security, observability/alerts, rollback/restore, "
        "isolation/residency/budget, and target-adapter evidence "
        "remain required and unconfigured.",
        "Existing disabled activation, zero action counts, unresolved "
        "decisions, human gates, and NOT_EXECUTED evidence remain "
        "unchanged.",
    ),
    "required_test_evidence": (
        "Isolated tests/st1505 positive contract and generated-plan assertions.",
        "Hostile tests for every predecessor semantic and byte "
        "drift, missing/unknown/duplicate/partial mappings, "
        "provider shortcuts, defaults, fallbacks, and gate "
        "downgrades.",
        "Owner generator regeneration and read-only --check.",
        "Ruff for changed Python, git diff --check, and affected "
        "ST-1505 developer checks when available.",
        "Formal TST-009 and TST-022, hosted CI, live provider, "
        "staging, rollback, release, and Production evidence "
        "remain separately unexecuted.",
    ),
}
EXPECTED_HANDOFF_DECISION: Final = {
    "staging_provider_policy": "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION",
    "selected_profile": None,
    "default_profile": None,
    "fallback_profile": None,
    "concrete_alternate_provider_selected": False,
    "eligible_profile_kinds": ["AWS", "OTHER_CLOUD", "OWNER_MANAGED_INFRASTRUCTURE"],
    "eligibility_condition": "COMPLETE_EXACT_DEPENDENCY_AND_CAPABILITY_MAPPING_WITH_EQUIVALENT_EVIDENCE",
    "aws_reference_boundary": {
        "canonical_decision_id": "INT-DEC-007",
        "reference_profile": "AWS_TOKYO_STAGING",
        "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "canonical_story_deliverables": (
            "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
        ),
        "non_aws_owner_managed_profiles": ("ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"),
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    },
    "required_dependency_stories": ["ST-1501", "ST-1502", "ST-1503", "ST-1504"],
    "required_capability_ids": [
        "provider_neutral_foundation_profile",
        "provider_neutral_data_services_profile",
        "provider_neutral_compute_edge_profile",
        "provider_neutral_deployment_identity_profile",
        "immutable_build_sbom_scan_and_provenance",
        "migration_compatibility_and_dry_run",
        "protected_environment_human_approval",
        "smoke_security_and_runtime_verification",
        "cross_capability_transport_security",
        "observability_alerting_and_release_markers",
        "rollback_restore_and_recovery_readiness",
        "isolation_region_residency_and_budget_controls",
        "provider_neutral_target_adapter",
    ],
}
STAGING_ADMISSION_KEYS: Final = (
    "classification",
    "admission_status",
    "eligible",
    "selected_profile_id",
    "selected_profile_kind",
    "selected_provider_name",
    "default_profile_id",
    "fallback_profile_id",
    "concrete_alternate_provider_selected",
    "eligible_profile_kinds",
    "eligibility_condition",
    "dependency_admission_policy",
    "mapping_policy",
    "binding_policy",
    "aws_reference_boundary",
    "evidence_equivalence_policy",
    "dependency_admission_requirements",
    "capability_mapping_requirements",
)
DEPENDENCY_STORIES: Final = ("ST-1501", "ST-1502", "ST-1503", "ST-1504")
DEPENDENCY_POLICIES: Final = {
    "ST-1501": "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
    "ST-1502": "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION",
    "ST-1503": "STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION",
    "ST-1504": "STRICT_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY_CAPABILITY_ADMISSION",
}
STAGING_CAPABILITY_OUTCOMES: Final = {
    "provider_neutral_foundation_profile": (
        "COMPLETE_FOUNDATION_MAPPING_AND_EQUIVALENT_SECURITY_OPERATIONS_RELEASE_"
        "RECOVERY_RESIDENCY_EVIDENCE"
    ),
    "provider_neutral_data_services_profile": (
        "COMPLETE_POSTGRES_OBJECT_QUEUE_SECRET_RECOVERY_OBSERVABILITY_ISOLATION_"
        "RESIDENCY_MAPPING"
    ),
    "provider_neutral_compute_edge_profile": (
        "COMPLETE_RUNTIME_EDGE_DNS_TLS_WAF_ISOLATION_IDENTITY_HEALTH_RESIDENCY_MAPPING"
    ),
    "provider_neutral_deployment_identity_profile": (
        "COMPLETE_EXACT_SUBJECT_SHORT_LIVED_IDENTITY_APPROVAL_AUDIT_REVOCATION_MAPPING"
    ),
    "immutable_build_sbom_scan_and_provenance": (
        "BUILD_ONCE_IMMUTABLE_DIGEST_SBOM_SCAN_SIGNED_PROVENANCE_AND_PROMOTION_"
        "WITHOUT_REBUILD"
    ),
    "migration_compatibility_and_dry_run": (
        "EXPAND_MIGRATE_CONTRACT_DRY_RUN_LOCK_COMPATIBILITY_AND_FORWARD_FIX_EVIDENCE"
    ),
    "protected_environment_human_approval": (
        "EXACT_REPOSITORY_REF_WORKFLOW_ENVIRONMENT_AUDIENCE_SUBJECT_AND_"
        "INDEPENDENT_HUMAN_APPROVAL"
    ),
    "smoke_security_and_runtime_verification": (
        "LIVENESS_READINESS_DEPENDENCY_MIGRATION_ISOLATION_SMOKE_SECURITY_RUNTIME_"
        "AND_BROWSER_EVIDENCE"
    ),
    "cross_capability_transport_security": (
        "AUTHENTICATED_ENCRYPTED_DOWNGRADE_RESISTANT_TRANSPORT_FOR_ALL_STAGING_"
        "NETWORK_FLOWS"
    ),
    "observability_alerting_and_release_markers": (
        "TRACES_METRICS_LOGS_RELEASE_MARKERS_SLO_ALERT_ROUTES_AND_NOTIFICATION_EVIDENCE"
    ),
    "rollback_restore_and_recovery_readiness": (
        "PRIOR_ARTIFACT_CONFIGURATION_SNAPSHOT_MIGRATION_COMPATIBILITY_RESTORE_"
        "INTEGRITY_AND_ROLLBACK_EVIDENCE"
    ),
    "isolation_region_residency_and_budget_controls": (
        "ENVIRONMENT_TENANT_DATA_PLANE_SURFACE_ISOLATION_REGION_RESIDENCY_BUDGET_"
        "ALERT_AND_STOP_EVIDENCE"
    ),
    "provider_neutral_target_adapter": (
        "EXPLICIT_PROVIDER_NEUTRAL_TARGET_ADAPTER_MAPPING_WITH_IDENTICAL_SECURITY_"
        "OPERATIONS_AND_RELEASE_EVIDENCE"
    ),
}
STAGING_CAPABILITY_IDS: Final = tuple(STAGING_CAPABILITY_OUTCOMES)
STAGING_PHASE_NAMES: Final = (
    "PREDECESSOR_CAPABILITY_ADMISSION",
    "TARGET_ADAPTER_ADMISSION",
    "ARTIFACT_ADMISSION",
    "PROTECTED_ENVIRONMENT_APPROVAL_GATE",
    "MIGRATION_COMPATIBILITY_GATE",
    "INDEPENDENT_MIGRATION_REVIEW_GATE",
    "TRANSPORT_SECURITY_GATE",
    "ROLLBACK_RESTORE_READINESS_GATE",
    "ARTIFACT_PROMOTION",
    "STAGING_DEPLOYMENT",
    "MIGRATION_DRY_RUN_GATE",
    "MIGRATE",
    "OBSERVABILITY_ALERT_GATE",
    "STAGING_SMOKE_SECURITY_RUNTIME_GATE",
    "ROLLBACK_RESTORE_GATE",
    "RELEASE_EVIDENCE_GATE",
)
STAGING_ACTION_COUNT_NAMES: Final = (
    "create",
    "update",
    "delete",
    "build",
    "promote",
    "approve",
    "deploy",
    "migrate",
    "migration_review",
    "smoke",
    "security",
    "runtime",
    "browser",
    "transport_security",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "release",
    "production",
)
STAGING_OPERATION_NAMES: Final = (
    "dependency_admission",
    "target_adapter_call",
    "artifact_build",
    "artifact_promote",
    "environment_approval",
    "deploy",
    "migration_dry_run",
    "migration_review",
    "migrate",
    "smoke",
    "security_check",
    "runtime_check",
    "browser",
    "transport_security_check",
    "telemetry_write",
    "alert_route_write",
    "rollback",
    "restore",
    "release",
    "production",
)
EVIDENCE_BOUNDARY_KEYS: Final = (
    "deliverable_classification",
    "executable_pipeline",
    "workflow",
    "target_adapter_runtime",
    "terraform_or_provider_runtime",
    "migration_runtime",
    "browser_runtime",
    "credentials",
    "predecessor_dependency_admission",
    "target_profile_admission",
    "build_sbom_scan_provenance",
    "protected_environment_approval",
    "formal_tst_009",
    "formal_tst_022",
    "migration_database",
    "independent_migration_review",
    "smoke_security_runtime",
    "transport_security",
    "observability_alerting",
    "rollback_restore",
    "hosted_ci",
    "live_provider",
    "staging",
    "release",
    "production",
    "effective_canonical_status",
)
EXPECTED_HANDOFF_SEMANTIC_SHA256: Final = (
    "d4f680a468ab1246734595394d7e2b1edefa6a590e33c418f7c0c9b487e30448"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256: Final = (
    "9c5e6c5a8c52e40cb43e7405f95492d75bf0096430566425e0b47b550ade1215"
)
PREDECESSOR_SEMANTIC_SHA256: Final = {
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "e20e03d89693bc8ad7adfffcc515eb656ec11375c2a304aa58ab0e30b8fe4722"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "dcf15e5dd721b504a6bac04b71a0c6d26c7ba72bf86e074459babc59f2e3f080"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "8679ac98b14f1bd33572679d7fa1fcd1d64e65d3f94b0a973d35637c176567d7"
    ),
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml": (
        "fda0d363d17ca4d8197179b74ad0fac23d252fc3a4e7ef0dc66c2c10a7fc3500"
    ),
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "733d4b6f8c057f3b6d73b413c9ca63b642087005e6f159ae0104a95bf1ff374c"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "8af68f20679a97fc45c20ed9db15edb704edfa7ce63b03b389437cb3eee91329"
    ),
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml": (
        "ad5e207a8f201d0ccdff72670a0f1cd7d90ba76f3e52ad7e51db2eb96d0dd707"
    ),
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml": (
        "3d802aa46e08af8241e0feca42ffa7a3d3397a49d4f839cbfef28321cdd52852"
    ),
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json": (
        "8e483d3448213f8fd328241c39029e4ed443a3ffc0df7a358ed0de6870eb074a"
    ),
    "changes/st-1504/"
    "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml": (
        "e26a0bbedb909530587462881a96e8b85b7bfdb93aedc57e281eda9d4d043282"
    ),
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml": (
        "86c418b07701b4cf47f478b13f7665911ece7c4a46d39edd07f7b6944019a4b7"
    ),
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json": (
        "9fac1776d4b7cd2a89999559036e4c465979d5de0f80ccaff26004e56ade5951"
    ),
}
PREDECESSOR_SPECIFICATIONS: Final = (
    (
        "foundation",
        "ST-1501",
        "scripts/build_st1501_terraform_foundation.py",
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
        "provider_neutral_foundation_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
    (
        "data_services",
        "ST-1502",
        "scripts/build_st1502_data_services.py",
        "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
        "changes/st-1502/contracts/data-services-foundation.v1.yaml",
        "infra/terraform/data-services/data-services.reference-plan.v1.json",
        "provider_neutral_data_services_admission",
        {
            "create": 0,
            "update": 0,
            "delete": 0,
            "migrate": 0,
            "backup": 0,
            "restore": 0,
            "redrive": 0,
            "rotate": 0,
        },
    ),
    (
        "compute_edge",
        "ST-1503",
        "scripts/build_st1503_compute_edge.py",
        "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
        "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
        "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        "provider_neutral_compute_edge_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
    (
        "deployment_identity",
        "ST-1504",
        "scripts/build_st1504_github_oidc.py",
        (
            "changes/st-1504/"
            "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml"
        ),
        "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
        "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
        "provider_neutral_deployment_identity_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
)
EXPECTED_OPEN_DECISION_BOUNDARY: Final = {
    "OD-002": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": (
            "EXAMPLE_INVALID_PROVISIONAL_BRAND_EXTERNAL_PUBLICATION_FORBIDDEN"
        ),
    },
    "OD-009": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": "LOW_DEVELOPMENT_CAP_STAGING_AND_PRODUCTION_DISABLED",
    },
    "OD-010": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": (
            "LOCAL_FAKE_AUTH_DEVELOPMENT_ONLY_EXTERNAL_PUBLICATION_FORBIDDEN"
        ),
    },
    "OD-011": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": "LOCAL_LOG_ONLY_STAGING_AND_PRODUCTION_UNAVAILABLE",
    },
    "OD-013": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": (
            "REFERENCE_REGION_METADATA_ONLY_STAGING_TARGET_UNSET_"
            "PRODUCTION_APPLY_FORBIDDEN"
        ),
    },
    "OD-014": {
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": "NO_RETENTION_OR_AUTOMATIC_DELETION_POLICY_SELECTED",
    },
    "OD-015": {
        "status": "EXTERNAL_EVIDENCE_REQUIRED",
        "resolved": False,
        "blocking": True,
        "safe_default": (
            "RECORDED_FIXTURES_ONLY_CREDENTIALS_ABSENT_PROVIDER_CALLS_FORBIDDEN"
        ),
    },
}


class StagingDeploymentContractError(RuntimeError):
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
class StagingDeploymentModel:
    """A fully validated, closed ST-1505 contract."""

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
    raise StagingDeploymentContractError(code, field)


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


def _assert_unset_tree(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, Mapping):
        mapping = _mapping(value, field)
        for nested in mapping.values():
            _assert_unset_tree(nested, f"{field}.item")
        return
    if type(value) is list:
        if value:
            _fail("PREDECESSOR_SELECTION_SET", field)
        return
    _fail("PREDECESSOR_SELECTION_SET", field)


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
    except StagingDeploymentContractError:
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
    except StagingDeploymentContractError:
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


def _load_repo_json(root: Path, relative: str, field: str) -> Mapping[str, Any]:
    return _mapping(
        load_json(_repository_regular_file(root, Path(relative), field)), field
    )


def _require_text(root: Path, relative: str, snippets: tuple[str, ...]) -> None:
    path = _repository_regular_file(root, Path(relative), "authority_text")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        _fail("AUTHORITY_TEXT_UNAVAILABLE", "authority_text")
    if any(snippet not in text for snippet in snippets):
        _fail("AUTHORITY_SEMANTIC_DRIFT", "authority_text")


def _validate_authority_semantics(root: Path) -> None:
    backlog = _load_repo_yaml(
        root,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    story = _find_exact_record(backlog, "stories", "ST-1505", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1505")

    canonical_decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "canonical_decisions",
    )
    _strict_match(
        _find_exact_record(
            canonical_decisions,
            "decisions",
            "INT-DEC-007",
            "canonical_decisions.decisions",
        ),
        EXPECTED_INT_DEC_007,
        "canonical_decisions.INT-DEC-007",
    )

    decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        decision = _find_exact_record(
            decisions, "items", decision_id, "open_decisions.items"
        )
        _strict_match(decision, expected, f"open_decisions.{decision_id}")

    test_catalog = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    for suite_id, expected in EXPECTED_TESTS.items():
        suite = _find_exact_record(
            test_catalog, "suites", suite_id, "test_catalog.suites"
        )
        _strict_match(suite, expected, f"test_catalog.{suite_id}")

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
    for threat_id, required_controls in EXPECTED_THREATS.items():
        threat = _find_exact_record(
            threats, "threats", threat_id, "threat_register.threats"
        )
        if (
            threat.get("controls") != required_controls
            or threat.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or threat.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_THREAT_DRIFT", threat_id)

    slices = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_implementation_slices_v1.0.yaml",
        "security_slices",
    )
    _strict_match(
        _find_exact_record(slices, "slices", "SEC-SLICE-009", "security_slices"),
        {
            "id": "SEC-SLICE-009",
            "name": "Supply chain and deployment",
            "depends_on": ["SEC-SLICE-001", "SEC-SLICE-007"],
            "deliverables": [
                "SBOM",
                "provenance",
                "OIDC deploy",
                "environment approval",
            ],
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
        },
        "security_slices.SEC-SLICE-009",
    )

    architecture = _load_repo_yaml(
        root,
        "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml",
        "architecture_catalog",
    )
    deployment = _mapping(architecture.get("deployment"), "deployment")
    _strict_match(
        deployment.get("environments"),
        {
            "local": {"data": "synthetic", "external": "mock_or_sandbox"},
            "ci": {"data": "ephemeral", "external": "fixture"},
            "dev": {"data": "synthetic", "external": "limited"},
            "staging": {
                "data": "sanitized_fixtures",
                "external": "sandbox_or_limited_read",
            },
            "production": {"data": "production", "external": "production"},
        },
        "deployment.environments",
    )
    _strict_match(
        deployment.get("migration"),
        "expand_migrate_contract",
        "deployment.migration",
    )
    _strict_match(
        deployment.get("infrastructure_as_code"), "Terraform", "deployment.iac"
    )
    _strict_match(
        deployment.get("production_data_in_nonprod"),
        False,
        "deployment.production_data",
    )
    aws = _mapping(deployment.get("aws_mapping"), "deployment.aws")
    _strict_match(aws.get("ci_cd"), "GitHub_Actions_OIDC", "deployment.ci_cd")

    _require_text(
        root,
        "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md",
        (
            "| staging | 本番相当検証 | Sanitized Fixture | Sandbox/限定本番Read |",
            "7. Deploy Staging",
            "8. Migration Dry Run",
            "Immutable Image Build",
            "Expand-Migrate-Contract",
            "破壊的変更は複数Release",
            "PITRは重大災害時に使用し、通常の内容誤りには使わない。",
        ),
    )
    _require_text(
        root,
        "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md",
        (
            "B --> S[Deploy Staging]",
            "S --> T[Runtime / Security / Migration / Smoke]",
            "Database changeはBackward-compatibleなExpandを先に出し",
            "Releaseごと: Contract/migration/security/evidence/rollback review",
        ),
    )
    _require_text(
        root,
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        (
            "Worker、CI、Migration、Projection、Public Webは異なるWorkload Identityを使う。",
            "ReleaseにSBOM、Build provenance、Commit SHA、Contract hash、Migration versionを含める。",
            "Raw Secret、Prompt本文、Source本文、個人情報をLogに出さない。",
        ),
    )
    _require_text(
        root,
        "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md",
        (
            "Production dataをCIへ持ち込まない。",
            "Migration zero-to-latest/upgrade失敗",
            "Browser/Accessibility/Security/Load Test",
        ),
    )
    _require_text(
        root,
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        (
            "Status: `ACTIVE_UNDER_STANDING_DEVELOPMENT_AUTHORIZATION`",
            "`ST-1504`, `ST-1505`, `ST-1506`",
            "Open-Decision and infrastructure Stories remain disabled/synthetic",
        ),
    )

    agents_path = _repository_regular_file(root, Path("AGENTS.md"), "agents_policy")
    try:
        agents_text = agents_path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        _fail("FILE_UNAVAILABLE", "agents_policy")
    if "初期 external review connector には GitHub のみを使用する。" not in agents_text:
        _fail("AUTHORITY_CONNECTOR_POLICY_DRIFT", "agents_policy")

    handoff = _load_repo_yaml(
        root, DESIGN_HANDOFF_PATH.as_posix(), "provider_neutral_design_handoff"
    )
    if tuple(handoff) != HANDOFF_TOP_LEVEL_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "provider_neutral_design_handoff")
    _strict_match(handoff.get("schema"), "DESIGN_HANDOFF_V1", "handoff.schema")
    _strict_match(handoff.get("version"), 1, "handoff.version")
    _strict_match(
        handoff.get("record_status"),
        "RECORDED_DURABLE_OWNER_DECISION",
        "handoff.record_status",
    )
    _strict_match(handoff.get("approved_story"), "ST-1505", "handoff.story")
    for field, expected_rows in EXPECTED_HANDOFF_LIST_SECTIONS.items():
        _strict_match(handoff.get(field), list(expected_rows), f"handoff.{field}")
    _strict_match(
        handoff.get("decision"), EXPECTED_HANDOFF_DECISION, "handoff.decision"
    )
    _strict_match(
        handoff.get("open_decision_state"),
        EXPECTED_OPEN_DECISION_BOUNDARY,
        "handoff.open_decision_state",
    )
    if semantic_sha256(handoff) != EXPECTED_HANDOFF_SEMANTIC_SHA256:
        _fail("HANDOFF_SEMANTIC_DRIFT", "provider_neutral_design_handoff")


def _expected_predecessor_binding(
    story_id: str,
    owner_generator_path: str,
    handoff_path: str,
    contract_path: str,
    plan_path: str,
    action_counts: Mapping[str, int],
) -> dict[str, object]:
    expected: dict[str, object] = {
        "story_id": story_id,
        "owner_generator_uri": f"repo://{owner_generator_path}",
        "owner_generator_sha256": PREDECESSOR_SOURCES[owner_generator_path],
        "design_handoff_uri": f"repo://{handoff_path}",
        "design_handoff_sha256": PREDECESSOR_SOURCES[handoff_path],
        "design_handoff_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[handoff_path],
        "contract_uri": f"repo://{contract_path}",
        "contract_sha256": PREDECESSOR_SOURCES[contract_path],
        "contract_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[contract_path],
        "reference_plan_uri": f"repo://{plan_path}",
        "reference_plan_sha256": PREDECESSOR_SOURCES[plan_path],
        "reference_plan_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[plan_path],
        "required_provider_policy": DEPENDENCY_POLICIES[story_id],
        "required_admission_status": "NOT_EVALUATED",
        "required_eligible": False,
        "required_complete_mapping": False,
        "required_selected_values": "UNSET",
        "required_activation_status": "DISABLED",
        "required_network_access": "FORBIDDEN",
        "required_credential_access": "FORBIDDEN",
        "required_live_provider_calls": "FORBIDDEN",
        "required_external_writes": "FORBIDDEN",
    }
    if story_id == "ST-1504":
        expected["required_credential_issuance"] = "FORBIDDEN"
    expected["required_reference_plan_executable"] = False
    expected["required_action_counts"] = copy.deepcopy(dict(action_counts))
    return expected


def _validate_predecessor_bindings(contract: Mapping[str, Any]) -> None:
    bindings = _mapping(contract.get("predecessor_bindings"), "predecessor_bindings")
    expected_keys = tuple(
        specification[0] for specification in PREDECESSOR_SPECIFICATIONS
    )
    if tuple(bindings) != expected_keys:
        _fail("CLOSED_SCHEMA_VIOLATION", "predecessor_bindings")
    for (
        binding_name,
        story_id,
        owner_generator_path,
        handoff_path,
        contract_path,
        plan_path,
        _admission_name,
        action_counts,
    ) in PREDECESSOR_SPECIFICATIONS:
        _strict_match(
            bindings.get(binding_name),
            _expected_predecessor_binding(
                story_id,
                owner_generator_path,
                handoff_path,
                contract_path,
                plan_path,
                action_counts,
            ),
            f"predecessor_bindings.{binding_name}",
        )


def _load_predecessor_document(
    root: Path, relative: str, *, is_json: bool = False
) -> Mapping[str, Any]:
    path = _repository_regular_file(root, Path(relative), "predecessor")
    document = _mapping(load_json(path) if is_json else load_yaml(path), "predecessor")
    if semantic_sha256(document) != PREDECESSOR_SEMANTIC_SHA256[relative]:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    return document


def _render_predecessor_plan(
    story_id: str, contract: Mapping[str, Any], root: Path
) -> bytes:
    try:
        if story_id == "ST-1501":
            from scripts import build_st1501_terraform_foundation as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1502":
            from scripts import build_st1502_data_services as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1503":
            from scripts import build_st1503_compute_edge as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1504":
            from scripts import build_st1504_github_oidc as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
    except Exception:  # noqa: BLE001
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    _fail("PREDECESSOR_STORY_UNKNOWN", "predecessor")


def _validate_predecessor_contract_boundary(
    story_id: str,
    contract: Mapping[str, Any],
    admission_name: str,
    expected_policy: str,
) -> None:
    document = _mapping(contract.get("document"), "predecessor.document")
    _strict_match(document.get("story_id"), story_id, "predecessor.story")
    _strict_match(document.get("version"), "1.1.0", "predecessor.version")
    _strict_match(
        document.get("status"),
        "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "predecessor.status",
    )
    _strict_match(
        document.get("formal_verification"),
        "NOT_EXECUTED",
        "predecessor.formal_verification",
    )
    admission = _mapping(contract.get(admission_name), "predecessor.admission")
    _strict_match(
        admission.get("classification"), expected_policy, "predecessor.policy"
    )
    _strict_match(
        admission.get("admission_status"),
        "NOT_EVALUATED",
        "predecessor.admission_status",
    )
    _strict_match(admission.get("eligible"), False, "predecessor.eligible")
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(admission.get(field), None, f"predecessor.admission.{field}")
    mapping_policy = _mapping(
        admission.get("mapping_policy"), "predecessor.mapping_policy"
    )
    _strict_match(
        mapping_policy.get("configured_mapping_count"),
        0,
        "predecessor.configured_mapping_count",
    )
    _strict_match(
        mapping_policy.get("complete_mapping"),
        False,
        "predecessor.complete_mapping",
    )
    mappings = _list(
        admission.get("capability_mapping_requirements"),
        "predecessor.capability_mappings",
    )
    _strict_match(
        mapping_policy.get("required_capability_count"),
        len(mappings),
        "predecessor.required_capability_count",
    )
    observed: list[str] = []
    for raw_mapping in mappings:
        mapping = _mapping(raw_mapping, "predecessor.capability_mapping")
        capability_id = mapping.get("capability_id")
        if type(capability_id) is not str or capability_id in observed:
            _fail("PREDECESSOR_CAPABILITY_INVENTORY_DRIFT", "predecessor")
        observed.append(capability_id)
        _strict_match(
            mapping.get("selected_mapping"),
            None,
            "predecessor.capability_mapping.selected",
        )
        evidence_key = (
            "evidence_refs" if "evidence_refs" in mapping else "evidence_references"
        )
        _strict_match(
            mapping.get(evidence_key), [], "predecessor.capability_mapping.evidence"
        )
        _strict_match(
            mapping.get("mapping_status"),
            "REQUIRED_NOT_CONFIGURED",
            "predecessor.capability_mapping.status",
        )
    reference = _mapping(
        contract.get("reference_architecture"), "predecessor.reference_architecture"
    )
    _strict_match(
        reference.get("classification"),
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "predecessor.reference.classification",
    )
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        _strict_match(reference.get(field), False, f"predecessor.reference.{field}")
    aws_reference_boundary = _mapping(
        admission.get("aws_reference_boundary"),
        "predecessor.admission.aws_reference_boundary",
    )
    _strict_match(
        aws_reference_boundary.get("role"),
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "predecessor.admission.aws_reference_boundary.role",
    )
    _strict_match(
        aws_reference_boundary.get("canonical_story_deliverables"),
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED",
        "predecessor.admission.aws_reference_boundary.canonical_story_deliverables",
    )
    _strict_match(
        aws_reference_boundary.get("non_aws_owner_managed_profiles"),
        "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS",
        "predecessor.admission.aws_reference_boundary.portable_paths",
    )
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        _strict_match(
            aws_reference_boundary.get(field),
            False,
            f"predecessor.admission.aws_reference_boundary.{field}",
        )
    selection_name = (
        "selected_bindings" if story_id == "ST-1504" else "selected_configuration"
    )
    _assert_unset_tree(contract.get(selection_name), "predecessor.selection")
    execution = _mapping(contract.get("execution_boundary"), "predecessor.execution")
    _strict_match(execution.get("activation_enabled"), False, "predecessor.enabled")
    _strict_match(execution.get("activation_status"), "DISABLED", "predecessor.status")
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
    ):
        _strict_match(execution.get(field), "FORBIDDEN", f"predecessor.{field}")
    actions = _mapping(execution.get("planned_actions"), "predecessor.planned_actions")
    if not actions or any(
        type(value) is not int or value != 0 for value in actions.values()
    ):
        _fail("PREDECESSOR_ACTION_DRIFT", "predecessor.planned_actions")
    if story_id == "ST-1504":
        _strict_match(
            execution.get("credential_issuance"),
            "FORBIDDEN",
            "predecessor.credential_issuance",
        )


def _validate_predecessor_semantics(root: Path) -> None:
    for (
        _binding_name,
        story_id,
        _owner_generator_path,
        handoff_path,
        contract_path,
        plan_path,
        admission_name,
        _action_counts,
    ) in PREDECESSOR_SPECIFICATIONS:
        handoff = _load_predecessor_document(root, handoff_path)
        _strict_match(
            handoff.get("approved_story"), story_id, "predecessor.handoff.story"
        )
        contract = _load_predecessor_document(root, contract_path)
        _validate_predecessor_contract_boundary(
            story_id, contract, admission_name, DEPENDENCY_POLICIES[story_id]
        )
        plan_file = _repository_regular_file(root, Path(plan_path), "predecessor_plan")
        plan = _load_predecessor_document(root, plan_path, is_json=True)
        plan_document = _mapping(plan.get("document"), "predecessor.plan.document")
        _strict_match(plan_document.get("story_id"), story_id, "predecessor.plan.story")
        _strict_match(
            plan_document.get("executable"), False, "predecessor.plan.executable"
        )
        expected_bytes = _render_predecessor_plan(story_id, contract, root)
        try:
            actual_bytes = plan_file.read_bytes()
        except OSError:
            _fail("FILE_UNAVAILABLE", "predecessor_plan")
        if actual_bytes != expected_bytes:
            _fail("PREDECESSOR_GENERATED_DRIFT", "predecessor_plan")


def _validate_staging_admission(contract: Mapping[str, Any]) -> None:
    admission = _mapping(
        contract.get("provider_neutral_staging_admission"), "staging_admission"
    )
    if tuple(admission) != STAGING_ADMISSION_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "staging_admission")
    _strict_match(
        admission.get("classification"),
        "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION",
        "staging_admission.classification",
    )
    _strict_match(
        admission.get("admission_status"),
        "NOT_EVALUATED",
        "staging_admission.status",
    )
    _strict_match(admission.get("eligible"), False, "staging_admission.eligible")
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(admission.get(field), None, f"staging_admission.{field}")
    _strict_match(
        admission.get("concrete_alternate_provider_selected"),
        False,
        "staging_admission.alternate",
    )
    _strict_match(
        admission.get("eligible_profile_kinds"),
        ["AWS", "OTHER_CLOUD", "OWNER_MANAGED_INFRASTRUCTURE"],
        "staging_admission.profile_kinds",
    )
    _strict_match(
        admission.get("dependency_admission_policy"),
        {
            "required_dependency_count": 4,
            "satisfied_dependency_count": 0,
            "all_dependencies_satisfied": False,
            "exact_provider_neutral_admission_required": True,
            "complete_predecessor_mapping_required": True,
            "equivalent_predecessor_evidence_required": True,
            "missing_dependency": "REJECT",
            "unknown_dependency": "REJECT",
            "duplicate_dependency": "REJECT",
            "partial_dependencies": "REJECT",
            "provider_label_only_dependency": "REJECT",
            "predecessor_completion_only": "REJECT",
            "canonical_reference_architecture_status_only": "REJECT",
        },
        "staging_admission.dependency_policy",
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
        "staging_admission.aws_reference_boundary",
    )
    dependency_rows = _list(
        admission.get("dependency_admission_requirements"),
        "staging_admission.dependencies",
    )
    observed_dependencies: list[str] = []
    for raw_row in dependency_rows:
        row = _mapping(raw_row, "staging_admission.dependency")
        if tuple(row) != (
            "story_id",
            "required_policy",
            "current_admission_status",
            "current_eligible",
            "selected_profile_id",
            "selected_provider_name",
            "evidence_references",
            "dependency_status",
        ):
            _fail("CLOSED_SCHEMA_VIOLATION", "staging_admission.dependency")
        story_id = row.get("story_id")
        if type(story_id) is not str or story_id not in DEPENDENCY_POLICIES:
            _fail("UNKNOWN_DEPENDENCY_MAPPING", "staging_admission.dependency")
        if story_id in observed_dependencies:
            _fail("DUPLICATE_DEPENDENCY_MAPPING", "staging_admission.dependency")
        observed_dependencies.append(story_id)
        _strict_match(
            row.get("required_policy"),
            DEPENDENCY_POLICIES[story_id],
            "staging_admission.dependency.policy",
        )
        _strict_match(
            row.get("current_admission_status"),
            "NOT_EVALUATED",
            "staging_admission.dependency.status",
        )
        _strict_match(
            row.get("current_eligible"),
            False,
            "staging_admission.dependency.eligible",
        )
        _strict_match(
            row.get("selected_profile_id"),
            None,
            "staging_admission.dependency.profile",
        )
        _strict_match(
            row.get("selected_provider_name"),
            None,
            "staging_admission.dependency.provider",
        )
        _strict_match(
            row.get("evidence_references"),
            [],
            "staging_admission.dependency.evidence",
        )
        _strict_match(
            row.get("dependency_status"),
            "REQUIRED_NOT_SATISFIED",
            "staging_admission.dependency.result",
        )
    if set(observed_dependencies) != set(DEPENDENCY_STORIES):
        _fail("MISSING_DEPENDENCY_MAPPING", "staging_admission.dependencies")
    if tuple(observed_dependencies) != DEPENDENCY_STORIES:
        _fail("DEPENDENCY_MAPPING_ORDER_DRIFT", "staging_admission.dependencies")

    mappings = _list(
        admission.get("capability_mapping_requirements"),
        "staging_admission.capabilities",
    )
    observed_capabilities: list[str] = []
    for raw_mapping in mappings:
        mapping = _mapping(raw_mapping, "staging_admission.capability")
        if tuple(mapping) != (
            "capability_id",
            "required_outcome",
            "selected_mapping",
            "evidence_references",
            "mapping_status",
        ):
            _fail("CLOSED_SCHEMA_VIOLATION", "staging_admission.capability")
        capability_id = mapping.get("capability_id")
        if type(capability_id) is not str or capability_id not in (
            STAGING_CAPABILITY_OUTCOMES
        ):
            _fail("UNKNOWN_CAPABILITY_MAPPING", "staging_admission.capability")
        if capability_id in observed_capabilities:
            _fail("DUPLICATE_CAPABILITY_MAPPING", "staging_admission.capability")
        observed_capabilities.append(capability_id)
        _strict_match(
            mapping.get("required_outcome"),
            STAGING_CAPABILITY_OUTCOMES[capability_id],
            "staging_admission.capability.outcome",
        )
        _strict_match(
            mapping.get("selected_mapping"),
            None,
            "staging_admission.capability.selected",
        )
        _strict_match(
            mapping.get("evidence_references"),
            [],
            "staging_admission.capability.evidence",
        )
        _strict_match(
            mapping.get("mapping_status"),
            "REQUIRED_NOT_CONFIGURED",
            "staging_admission.capability.status",
        )
    if set(observed_capabilities) != set(STAGING_CAPABILITY_IDS):
        _fail("MISSING_CAPABILITY_MAPPING", "staging_admission.capabilities")
    if tuple(observed_capabilities) != STAGING_CAPABILITY_IDS:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "staging_admission.capabilities")


def _validate_local_safety_invariants(contract: Mapping[str, Any]) -> None:
    if tuple(contract) != STAGING_TOP_LEVEL_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "contract")
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-STAGING-DEPLOYMENT-001",
            "version": "1.1.0",
            "story_id": "ST-1505",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "document",
    )
    _validate_predecessor_bindings(contract)
    _validate_staging_admission(contract)
    reference = _mapping(contract.get("reference_architecture"), "reference")
    _strict_match(
        reference.get("classification"),
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "reference.classification",
    )
    _strict_match(reference.get("inherited_from"), "INT-DEC-007", "reference.source")
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        _strict_match(reference.get(field), False, f"reference.{field}")
    _assert_unset_tree(contract.get("selected_bindings"), "selected_bindings")
    _strict_match(
        contract.get("open_decision_boundary"),
        EXPECTED_OPEN_DECISION_BOUNDARY,
        "open_decision_boundary",
    )
    environment = _mapping(contract.get("environment_boundary"), "environment")
    _strict_match(environment.get("label"), "STAGING", "environment.label")
    _strict_match(
        environment.get("activation_status"), "DISABLED", "environment.activation"
    )
    _strict_match(environment.get("apply_target"), None, "environment.apply_target")
    _strict_match(
        environment.get("reference_region_use"),
        "METADATA_ONLY",
        "environment.reference_region_use",
    )
    for field in (
        "external_access",
        "staging_action",
        "release_action",
        "production_action",
    ):
        _strict_match(environment.get(field), "FORBIDDEN", f"environment.{field}")
    phases = _list(contract.get("logical_phases"), "logical_phases")
    _strict_match(
        phases, [_phase(name) for name in STAGING_PHASE_NAMES], "logical_phases"
    )
    execution = _mapping(contract.get("execution_boundary"), "execution")
    _strict_match(execution.get("activation_enabled"), False, "execution.enabled")
    _strict_match(execution.get("activation_status"), "DISABLED", "execution.status")
    _strict_match(execution.get("runtime_status"), "NOT_EXECUTED", "execution.runtime")
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "staging_action",
        "deploy_action",
        "migration_action",
        "migration_review_action",
        "transport_security_action",
        "rollback_action",
        "release_action",
        "production_action",
    ):
        _strict_match(execution.get(field), "FORBIDDEN", f"execution.{field}")
    _strict_match(
        execution.get("operations"),
        {name: "FORBIDDEN" for name in STAGING_OPERATION_NAMES},
        "execution.operations",
    )
    _strict_match(
        execution.get("action_counts"),
        {name: 0 for name in STAGING_ACTION_COUNT_NAMES},
        "execution.action_counts",
    )
    evidence = _mapping(contract.get("evidence_boundary"), "evidence")
    if tuple(evidence) != EVIDENCE_BOUNDARY_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "evidence")
    _strict_match(
        evidence.get("deliverable_classification"),
        (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
            "REFERENCE_PLAN"
        ),
        "evidence.classification",
    )
    for field in (
        "executable_pipeline",
        "workflow",
        "target_adapter_runtime",
        "terraform_or_provider_runtime",
        "migration_runtime",
        "browser_runtime",
        "credentials",
    ):
        _strict_match(evidence.get(field), "ABSENT", f"evidence.{field}")
    _strict_match(
        evidence.get("effective_canonical_status"),
        "UNCHANGED",
        "evidence.effective_canonical_status",
    )
    for field in EVIDENCE_BOUNDARY_KEYS:
        if field in {
            "deliverable_classification",
            "executable_pipeline",
            "workflow",
            "target_adapter_runtime",
            "terraform_or_provider_runtime",
            "migration_runtime",
            "browser_runtime",
            "credentials",
            "effective_canonical_status",
        }:
            continue
        _strict_match(evidence[field], "NOT_EXECUTED", f"evidence.{field}")
    if semantic_sha256(contract) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
        _fail("CONTRACT_SEMANTIC_DRIFT", "contract")


def validate_contract(
    contract: object, root: Path = REPO_ROOT
) -> StagingDeploymentModel:
    value = _mapping(contract, "contract")
    _validate_local_safety_invariants(value)
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    return StagingDeploymentModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> StagingDeploymentModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: StagingDeploymentModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: StagingDeploymentModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-STAGING-DEPLOYMENT-REFERENCE-PLAN-001",
            "version": "1.1.0",
            "story_id": "ST-1505",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_bindings": _section(model, "predecessor_bindings"),
        "reference_architecture": _section(model, "reference_architecture"),
        "provider_neutral_staging_admission": _section(
            model, "provider_neutral_staging_admission"
        ),
        "open_decision_boundary": _section(model, "open_decision_boundary"),
        "environment": _section(model, "environment_boundary"),
        "selected_bindings": _section(model, "selected_bindings"),
        "artifact_admission": _section(model, "artifact_admission_intent"),
        "protected_environment": _section(model, "protected_environment_intent"),
        "migration": _section(model, "migration_intent"),
        "health_security_runtime": _section(model, "health_security_runtime_intent"),
        "transport_security": _section(model, "transport_security_intent"),
        "observability_alerting": _section(model, "observability_alerting_intent"),
        "isolation_residency_budget": _section(
            model, "isolation_residency_budget_intent"
        ),
        "target_adapter": _section(model, "target_adapter_intent"),
        "rollback_restore": _section(model, "rollback_restore_intent"),
        "logical_phases": _section(model, "logical_phases"),
        "action_counts": copy.deepcopy(execution["action_counts"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "runtime_status": execution["runtime_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "staging_action": execution["staging_action"],
            "deploy_action": execution["deploy_action"],
            "migration_action": execution["migration_action"],
            "migration_review_action": execution["migration_review_action"],
            "transport_security_action": execution["transport_security_action"],
            "rollback_action": execution["rollback_action"],
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


def render_reference_plan(model: StagingDeploymentModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
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
    model: StagingDeploymentModel, reference_plan: bytes, root: Path = REPO_ROOT
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    environment = _mapping(model.contract["environment_boundary"], "environment")
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    admission = _mapping(
        model.contract["provider_neutral_staging_admission"], "admission"
    )
    reference = _mapping(model.contract["reference_architecture"], "reference")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-STAGING-DEPLOYMENT-MANIFEST-001",
            "version": "1.1.0",
            "story_id": "ST-1505",
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
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_plan),
                "sha256": sha256_bytes(reference_plan),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": evidence["deliverable_classification"],
            "environment_label": environment["label"],
            "configuration_status": environment["configuration_status"],
            "activation": execution["activation_status"],
            "action_counts": copy.deepcopy(execution["action_counts"]),
            "provider_policy": admission["classification"],
            "admission_status": admission["admission_status"],
            "eligible": admission["eligible"],
            "selected_profile_id": admission["selected_profile_id"],
            "selected_profile_kind": admission["selected_profile_kind"],
            "selected_provider": selection["target_provider_name"],
            "default_profile_id": admission["default_profile_id"],
            "fallback_profile_id": admission["fallback_profile_id"],
            "configured_mapping_count": admission["mapping_policy"][
                "configured_mapping_count"
            ],
            "required_capability_count": len(STAGING_CAPABILITY_IDS),
            "required_dependency_count": len(DEPENDENCY_STORIES),
            "satisfied_dependency_count": admission["dependency_admission_policy"][
                "satisfied_dependency_count"
            ],
            "aws_reference_only": True,
            "aws_reference_role": admission["aws_reference_boundary"]["role"],
            "canonical_story_deliverables": admission["aws_reference_boundary"][
                "canonical_story_deliverables"
            ],
            "portable_implementation_paths": admission["aws_reference_boundary"][
                "non_aws_owner_managed_profiles"
            ],
            "aws_reference_default": reference["default"],
            "aws_reference_implicit_fallback": reference["implicit_fallback"],
            "aws_reference_selected_binding": reference["selected_binding"],
            "aws_reference_eligibility_shortcut": reference["eligibility_shortcut"],
            "aws_reference_admission_requirement": reference["admission_requirement"],
            "aws_reference_evidence_substitute": reference["evidence_substitute"],
            "selected_account_project_or_tenant": selection[
                "target_account_project_or_tenant"
            ],
            "selected_region": selection["target_region"],
            "selected_backend": selection["target_state_backend"],
            "selected_identity": selection["target_deployment_identity"],
            "selected_adapter": selection["target_adapter"],
            "selected_repository": selection["github_repository"],
            "selected_environment": selection["github_environment"],
            "selected_artifact": selection["artifact_digest"],
            "credentials": evidence["credentials"],
            "predecessor_dependency_admission": evidence[
                "predecessor_dependency_admission"
            ],
            "target_profile_admission": evidence["target_profile_admission"],
            "build_sbom_scan_provenance": evidence["build_sbom_scan_provenance"],
            "protected_environment_approval": evidence[
                "protected_environment_approval"
            ],
            "formal_tst_009": evidence["formal_tst_009"],
            "formal_tst_022": evidence["formal_tst_022"],
            "migration_database": evidence["migration_database"],
            "independent_migration_review": evidence["independent_migration_review"],
            "smoke_security_runtime": evidence["smoke_security_runtime"],
            "transport_security": evidence["transport_security"],
            "observability_alerting": evidence["observability_alerting"],
            "rollback_restore": evidence["rollback_restore"],
            "hosted_ci": evidence["hosted_ci"],
            "live_provider": evidence["live_provider"],
            "staging": evidence["staging"],
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
    reference_plan = render_reference_plan(model)
    return {
        REFERENCE_PLAN_PATH: reference_plan,
        MANIFEST_PATH: render_manifest(model, reference_plan, root),
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
        description="Build the disabled ST-1505 staging reference artifacts."
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
    except StagingDeploymentContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1505 staging deployment check passed")
    else:
        print("ST-1505 staging deployment artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
