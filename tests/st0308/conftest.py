"""Self-contained candidate builders for the ST-0308 handoff validator."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY_ROOT / "scripts/validate_st0308_design_handoff.py"
CONTRACT_PATH = (
    REPOSITORY_ROOT / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
)

EXPECTED_HANDOFF_BYTES = 8 * 1024 * 1024
EXPECTED_VALIDATOR_CONTRACT_SHA256 = (
    "dbb63249a173e11e52504a6af03a87dc18991afba60b227867801a096f5cff7a"
)
EXPECTED_REPOSITORY_TEXT_BYTES = 16 * 1024 * 1024
EXPECTED_SQL_FRAGMENT_BYTES = 131072
EXPECTED_ARCHIVE_BYTES = 16 * 1024 * 1024
EXPECTED_YAML_DEPTH = 64
EXPECTED_YAML_NODES = 100000
EXPECTED_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT = 6291456

EXPECTED_ARCHIVE_TUPLE = (
    "changes/st-0308/pro-correction-input.v2.tar.gz",
    "209aba655caa6e29d14452ccf8ba7d74f79a9835549fe71fad9bfc7c22ef6baf",
    "approved-input/DESIGN_HANDOFF_V1.yaml",
    "33a9078095bfa7fd0f2517eba4ee941b9c9584222692e1069d35252a2b04a510",
)
EXPECTED_ARCHIVE_MEMBER_COUNT = 411
EXPECTED_ARCHIVE_REGULAR_MEMBER_COUNT = 369
EXPECTED_ARCHIVE_DIRECTORY_COUNT = 42
EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_BYTES = 5_679_757
EXPECTED_APPROVED_INPUT_SOURCE_PATH = (
    "/mnt/c/Users/naoki/Downloads/DESIGN_HANDOFF_V1.yaml"
)
EXPECTED_OWNER_APPROVAL_STATEMENT_SHA256 = (
    "7e47c77d220418b935e618c4f10ec6b54ccd20aa74cb6af897043fcf0868aeb5"
)

EXPECTED_TABLE_COUNT = 103
EXPECTED_VIEW_COUNT = 1
EXPECTED_VIEW_RELATIONS = ("catalog.v_safe_offer_current",)
EXPECTED_INVENTORY_SHA256 = (
    "0d674dd248c2d4aa3717b2e881dba2e67e506557eb473899d3df59192080a7ee"
)
EXPECTED_PHYSICAL_TABLE_RELATIONS = frozenset(
    {
        "ai.ai_attempt",
        "ai.ai_job",
        "ai.evaluation_case",
        "ai.evaluation_case_result",
        "ai.evaluation_dataset_version",
        "ai.evaluation_result",
        "ai.evaluation_run",
        "ai.evaluation_suite",
        "ai.human_evaluation",
        "ai.judge_calibration",
        "ai.model_definition",
        "ai.model_route_version",
        "ai.output_schema_version",
        "ai.prompt_version",
        "ai.release_approval",
        "ai.release_decision",
        "ai.task_definition",
        "ai.usage_cost",
        "catalog.affiliate_link_observation",
        "catalog.attribute_definition",
        "catalog.availability_observation",
        "catalog.canonical_product",
        "catalog.category_genre_mapping",
        "catalog.grouping_decision",
        "catalog.ingestion_request",
        "catalog.offer",
        "catalog.offer_current_projection",
        "catalog.price_observation",
        "catalog.product_attribute_value",
        "catalog.product_candidate",
        "catalog.product_group_membership",
        "catalog.product_relation",
        "catalog.provider_endpoint",
        "catalog.rakuten_genre",
        "catalog.review_aggregate_observation",
        "catalog.shop",
        "editorial.article",
        "editorial.article_block",
        "editorial.article_block_product",
        "editorial.article_disclosure_context",
        "editorial.article_link",
        "editorial.article_methodology_binding",
        "editorial.article_plan",
        "editorial.article_slug",
        "editorial.article_template_version",
        "editorial.article_type_version",
        "editorial.article_version",
        "editorial.comparison_axis",
        "editorial.comparison_value",
        "editorial.content_schema_version",
        "editorial.editorial_methodology_version",
        "editorial.media_asset",
        "editorial.recommendation",
        "editorial.recommendation_rationale",
        "editorial.recommendation_set",
        "editorial.review_comment",
        "editorial.seo_metadata_version",
        "editorial.structured_data_manifest",
        "evidence.claim",
        "evidence.claim_evidence_link",
        "evidence.fact",
        "evidence.fact_derivation",
        "evidence.first_hand_experience_asset",
        "evidence.first_hand_experience_record",
        "evidence.source",
        "evidence.source_packet",
        "evidence.source_packet_fact",
        "evidence.source_packet_product",
        "evidence.source_packet_version",
        "evidence.source_snapshot",
        "iam.break_glass_record",
        "iam.permission",
        "iam.principal",
        "iam.principal_role_assignment",
        "iam.role",
        "iam.role_permission",
        "iam.service_principal",
        "iam.session_revocation",
        "iam.user_account",
        "ops.audit_event",
        "ops.idempotency_record",
        "ops.inbox_receipt",
        "ops.job",
        "ops.job_attempt",
        "ops.object_artifact",
        "ops.outbox_event",
        "ops.runtime_setting_version",
        "policy.bundle_rule",
        "policy.finding",
        "policy.gate_decision",
        "policy.policy_bundle",
        "policy.quality_check_run",
        "policy.quality_score",
        "policy.rule_version",
        "policy.waiver",
        "portfolio.action_candidate",
        "portfolio.category",
        "portfolio.intent_cluster",
        "portfolio.intent_cluster_keyword",
        "portfolio.keyword",
        "portfolio.keyword_metric_observation",
        "portfolio.opportunity_assessment",
        "portfolio.site",
    }
)
EXPECTED_LOCK_VERSION_RELATIONS = frozenset(
    {
        "ai.ai_job",
        "ai.evaluation_dataset_version",
        "ai.evaluation_run",
        "ai.evaluation_suite",
        "ai.judge_calibration",
        "ai.model_route_version",
        "ai.prompt_version",
        "ai.release_decision",
        "catalog.attribute_definition",
        "catalog.canonical_product",
        "catalog.offer",
        "catalog.product_candidate",
        "catalog.rakuten_genre",
        "catalog.shop",
        "editorial.article",
        "editorial.article_link",
        "editorial.article_plan",
        "editorial.article_version",
        "evidence.source",
        "evidence.source_packet",
        "iam.principal",
        "ops.job",
        "portfolio.action_candidate",
        "portfolio.category",
        "portfolio.intent_cluster",
        "portfolio.keyword",
        "portfolio.site",
    }
)
EXPECTED_STATE_CAS_RELATIONS = frozenset(
    {
        "ai.ai_attempt",
        "ai.model_definition",
        "ai.output_schema_version",
        "ai.task_definition",
        "catalog.ingestion_request",
        "catalog.provider_endpoint",
        "editorial.article_disclosure_context",
        "editorial.article_slug",
        "editorial.article_template_version",
        "editorial.article_type_version",
        "editorial.content_schema_version",
        "editorial.editorial_methodology_version",
        "editorial.media_asset",
        "editorial.review_comment",
        "editorial.seo_metadata_version",
        "evidence.first_hand_experience_record",
        "evidence.source_packet_version",
        "iam.principal_role_assignment",
        "ops.runtime_setting_version",
        "policy.finding",
        "policy.policy_bundle",
        "policy.quality_check_run",
        "policy.rule_version",
        "policy.waiver",
    }
)

# Independent literals for the bounded approval-boundary grammar.  These are
# deliberately not derived from the live contract so contract edits cannot
# make the test suite redefine its own expected closure.
EXPECTED_BOUNDARY_GENERATED_ALIAS_COUNT = 4893
EXPECTED_BOUNDARY_EXPLICIT_ALIAS_COUNT = 4
EXPECTED_BOUNDARY_CLOSURE_COUNT = 4897
EXPECTED_BOUNDARY_PATTERN_COUNTS = {
    "direct_subject": 7,
    "direct_predicate": 10,
    "direct_status": 1,
    "direct_timestamp": 1,
    "is_subject": 17,
    "is_predicate": 1,
    "subject_status": 17,
    "is_subject_status": 17,
    "predicate_status": 0,
    "is_predicate_status": 0,
    "subject_by": 17,
    "subject_at": 17,
    "subject_timestamp": 17,
    "predicate_by": 0,
    "predicate_at": 0,
    "predicate_timestamp": 0,
    "subject_predicate": 186,
    "subject_is_predicate": 187,
    "is_subject_predicate": 186,
    "predicate_subject": 66,
    "predicate_is_subject": 66,
    "is_predicate_subject": 66,
    "is_subject_is_predicate": 187,
    "is_subject_by": 17,
    "is_subject_at": 17,
    "is_subject_timestamp": 17,
    "is_predicate_by": 0,
    "is_predicate_at": 0,
    "is_predicate_timestamp": 0,
    "subject_predicate_status": 186,
    "subject_is_predicate_status": 187,
    "is_subject_predicate_status": 186,
    "predicate_subject_status": 66,
    "predicate_is_subject_status": 66,
    "is_predicate_subject_status": 66,
    "is_subject_is_predicate_status": 187,
    "subject_predicate_by": 186,
    "subject_predicate_at": 186,
    "subject_predicate_timestamp": 186,
    "subject_is_predicate_by": 187,
    "subject_is_predicate_at": 187,
    "subject_is_predicate_timestamp": 187,
    "is_subject_predicate_by": 186,
    "is_subject_predicate_at": 186,
    "is_subject_predicate_timestamp": 186,
    "predicate_subject_by": 66,
    "predicate_subject_at": 66,
    "predicate_subject_timestamp": 66,
    "predicate_is_subject_by": 66,
    "predicate_is_subject_at": 66,
    "predicate_is_subject_timestamp": 66,
    "is_predicate_subject_by": 66,
    "is_predicate_subject_at": 66,
    "is_predicate_subject_timestamp": 66,
    "is_subject_is_predicate_by": 187,
    "is_subject_is_predicate_at": 187,
    "is_subject_is_predicate_timestamp": 187,
}
EXPECTED_BOUNDARY_REPRESENTATIVE_ALIASES = frozenset(
    {
        "implementation",
        "authorized",
        "isimplementation",
        "isauthorized",
        "implementationauthorized",
        "implementationisauthorized",
        "isimplementationauthorized",
        "authorizedimplementation",
        "authorizationisimplementation",
        "isauthorizationimplementation",
        "isimplementationisauthorized",
        "status",
        "timestamp",
        "implementationstatus",
        "isimplementationauthority",
        "isimplementationstatus",
        "isapprovalstatus",
        "authorizedstatus",
        "implementationby",
        "implementationat",
        "implementationtimestamp",
        "isimplementationby",
        "isimplementationat",
        "isimplementationtimestamp",
        "authorizedby",
        "authorizedat",
        "authorizedtimestamp",
        "implementationauthorizedstatus",
        "implementationisauthorizedstatus",
        "isimplementationauthorizedstatus",
        "authorizationgrantedstatus",
        "implementationauthorizedby",
        "implementationauthorizedat",
        "implementationauthorizedtimestamp",
        "implementationisauthorizedby",
        "implementationisauthorizedat",
        "implementationisauthorizedtimestamp",
        "isimplementationauthorizedby",
        "isimplementationauthorizedat",
        "isimplementationauthorizedtimestamp",
        "authorizedimplementationstatus",
        "authorizedimplementationby",
        "authorizedimplementationat",
        "authorizedimplementationtimestamp",
        "authorizationisimplementationstatus",
        "authorizationisimplementationby",
        "authorizationisimplementationat",
        "authorizationisimplementationtimestamp",
        "isauthorizationimplementationstatus",
        "isauthorizationimplementationby",
        "isauthorizationimplementationat",
        "isauthorizationimplementationtimestamp",
        "canonicalreconciliationisapproved",
        "ownerapprovalisauthorized",
        "iscanonicalreconciliation",
        "isstatus",
        "isapprovalstatus",
        "isownerapproved",
        "approvedgranted",
        "completedauthorized",
        "approvalisgranted",
        "isownerapprovalauthorized",
        "automatedpassauthorizesimplementation",
        "automatedpassauthorisesimplementation",
    }
)

CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES = (
    (
        "changes/st-0308/PRO-CORRECTION-REQUEST-v3.md",
        "0906d9bf46920bfd1d018590490857a6665ab9fc8eecc92411e3fcdb9d206270",
    ),
    (
        "changes/st-0308/CANONICAL-RECONCILIATION-v3.md",
        "91748530eafc018823b5a6a74cc2ca052569cb3c46f6e90dd1224d720d3fdc08",
    ),
    (
        "changes/st-0308/IMPLEMENTATION-READINESS-v3.md",
        "29e90628cc8ed4259b54486ab12abddb606ae414e3a2391c5055dbbf521577f7",
    ),
    (
        "changes/st-0308/pro-correction-bundle.v2.yaml",
        "62be122dbd16f2fbff2e2e9737eca4b0f4504574d2c6d943258e0ee7e59a33b0",
    ),
    (
        "changes/st-0308/pro-correction-bundle.v2.files",
        "84dd21a5f6f1098f7b67f403b68f7f91248d2a5d56205b1314a1f5c1bbbf37f3",
    ),
    EXPECTED_ARCHIVE_TUPLE[:2],
    (
        "changes/st-0308/pro-correction-input.v2.members.sha256",
        "dcd754d9b5d6211c52c3fa5811b65207b0d80a7fc398b14c8c58c9c93048bc7b",
    ),
    (
        "contracts/raos-v0.4/contract-repository.v0.4.json",
        "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef",
    ),
    (
        "changes/st-0105/manifest.json",
        "7f1ead0b00d7264f40b29c79a06f35cdad06610231a5c7f7a3e5e1d18054ceb7",
    ),
    (
        "docs/canonical/00_master/RAOS_MASTER_README_v1.0.md",
        "a0b27b491ee120767a59dd0c7822ab10e30cf17738960a919116623415ff8e40",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_canonical_contract_overlay_v1.0.yaml",
        "f9080e1744096b743b2ada2261d2a023cebf310a08cf3a9fc2d14a53ac56cf3e",
    ),
    (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "docs/canonical/08_codex/AGENTS.md",
        "214c1158da975465e187720d0f7ebca2691dfb2bc02a9506b7ca5adb0c812520",
    ),
    (
        "changes/st-0303/contracts/iam-ops-schema.v1.yaml",
        "af80127539a9c2c27fb0c63b7ef09c477380f90e94fedc408c5cd9a83036271b",
    ),
    (
        "changes/st-0303/manifest.yaml",
        "f795daab918844b2bd0c2fb6e8aa17031f4e849e9ccb5bcfe45d554ddf69fe8b",
    ),
    (
        "changes/st-0303/generated/iam-ops-catalog.v1.json",
        "0cab8decf1a9a874248ef16a5b1bfd01c19d1babbf45bb0f73eb42b89913720a",
    ),
    (
        "changes/st-0303/generated/iam-ops-validation.v1.sql",
        "33be33b53b9a14c7e9ad686f8dd08834a2bc8211e6fab82577f78811219fde32",
    ),
    (
        "migrations/versions/202608030003_iam_ops_tables.py",
        "a9e162915e7450e30a6c96bafd1a65485447f6163b88ef5771dedc3df14c2f4e",
    ),
    (
        "changes/st-0304/contracts/domain-schema.v1.yaml",
        "8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122",
    ),
    (
        "changes/st-0304/manifest.yaml",
        "d09aed90f37c7238f2a3dab4675e6e3b06f108b6c40d4468979541d70577ee51",
    ),
    (
        "changes/st-0304/generated/domain-catalog.v1.json",
        "41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208",
    ),
    (
        "changes/st-0304/generated/domain-validation.v1.sql",
        "7e1ce307a5751fc5d95e4c06652f0e6fb41b8bdc29c583ea9cd0a3d83d1fa3a5",
    ),
    (
        "migrations/versions/202608030004_domain_schemas.py",
        "632fc5146a57e2c7768745e3ed665aba0f91f229afc174c17fca8e9e2d88c407",
    ),
    (
        "changes/st-0306/contracts/database-roles-grants.v1.yaml",
        "6b8710a79729bde75e96e1df3698a0928d4924e4bd10afaff5631fc00f70a0d4",
    ),
    (
        "changes/st-0304/contracts/physical/01-domain-physical.sql",
        "b2f937ae00d526a886e5e875e095e247702f4bd7831a3164e2eda93423d7fdb8",
    ),
    (
        "changes/st-0304/contracts/physical/02-domain-physical.sql",
        "b685751e4e2743ea6c7202e8ce726486ac152e46987bb832e6777e61b987aafc",
    ),
    (
        "changes/st-0304/contracts/physical/03-domain-physical.sql",
        "f95ad5a2fd349177b01f97237d0d9a3fb598b2781828e9531a04c3c42b811b45",
    ),
    (
        "changes/st-0304/contracts/physical/04-domain-physical.sql",
        "4a3c029980e8c27957fac2291e7b0a8efb81eaf1faa74dee4e757b0836e7ba30",
    ),
    (
        "changes/st-0304/contracts/physical/05-domain-physical.sql",
        "c78e946f9be015d461350f347f125a2cf8f01b267647a8685158af207cefc0ec",
    ),
    (
        "changes/st-0304/contracts/physical/06-domain-physical.sql",
        "cc520254390d68fdc68d54c01ed6b95e031ea422814e5be924849ec61636904d",
    ),
    (
        "changes/st-0304/contracts/physical/07-domain-physical.sql",
        "739cc2ecae7e49702da5e36be6e37eaebaa7a535be4a623c79dee86926212870",
    ),
    (
        "changes/st-0304/contracts/physical/08-domain-physical.sql",
        "eafb7b89c6fa08bd74a8c13d89aa19aea3a946e739720a8cff9e6faa3ca2bfc4",
    ),
    (
        "changes/st-0304/contracts/physical/09-domain-physical.sql",
        "6cebf09249f027662557038f8367bdc586030197911046be242543cd43502ae5",
    ),
    (
        "changes/st-0304/contracts/physical/10-domain-physical.sql",
        "3d806436b7ed91f25e0396e15b914dda7258b743589ec4dc6c3f4272c9fcb38d",
    ),
    (
        "changes/st-0304/contracts/physical/11-domain-physical.sql",
        "947e480157a52b0d926461a4d40a7409e92e6e50482c216d394953a462d8cd09",
    ),
)

TRUSTED_V2_BUNDLE_SOURCE_REFERENCE_TUPLES = (
    (
        "changes/st-0308/PRO-CORRECTION-REQUEST-v2.md",
        "d443a7d64291022d02ae0c7d924b3905d5d2cde0b5b4f5945c2aebb13ccaa1f2",
    ),
    (
        "changes/st-0308/CANONICAL-RECONCILIATION-v2.md",
        "6c20546d907d347352c9e29e5dc68ae0c593d1f6feec4a39f8cc95919d577b60",
    ),
)

PINNED_SOURCE_REFERENCE_TUPLES = (
    *CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES,
    *TRUSTED_V2_BUNDLE_SOURCE_REFERENCE_TUPLES,
)

PINNED_SQL_FRAGMENT_PATHS = (
    "changes/st-0304/contracts/physical/01-domain-physical.sql",
    "changes/st-0304/contracts/physical/02-domain-physical.sql",
    "changes/st-0304/contracts/physical/03-domain-physical.sql",
    "changes/st-0304/contracts/physical/04-domain-physical.sql",
    "changes/st-0304/contracts/physical/05-domain-physical.sql",
    "changes/st-0304/contracts/physical/06-domain-physical.sql",
    "changes/st-0304/contracts/physical/07-domain-physical.sql",
    "changes/st-0304/contracts/physical/08-domain-physical.sql",
    "changes/st-0304/contracts/physical/09-domain-physical.sql",
    "changes/st-0304/contracts/physical/10-domain-physical.sql",
    "changes/st-0304/contracts/physical/11-domain-physical.sql",
)


def _contract() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def _live_physical_relation_sets() -> tuple[set[str], set[str]]:
    st0303 = json.loads(
        (
            REPOSITORY_ROOT / "changes/st-0303/generated/iam-ops-catalog.v1.json"
        ).read_text(encoding="utf-8")
    )
    relations = {row["fully_qualified_name"] for row in st0303["tables"]}
    lock_relations = {
        row["fully_qualified_name"]
        for row in st0303["tables"]
        if "lock_version" in {column["name"] for column in row["columns"]}
    }
    domain_catalog = json.loads(
        (
            REPOSITORY_ROOT / "changes/st-0304/generated/domain-catalog.v1.json"
        ).read_text(encoding="utf-8")
    )
    for row in domain_catalog["object_inventory"]["objects"]:
        if row["type"] == "TABLE":
            relations.add(f"{row['schema']}.{row['name']}")

    create_table_pattern = re.compile(
        r'CREATE TABLE "([^"]+)"\."([^"]+)" \(\n(.*?)\n\);',
        re.DOTALL,
    )
    for path in PINNED_SQL_FRAGMENT_PATHS:
        text = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        for match in create_table_pattern.finditer(text):
            relation = f"{match.group(1)}.{match.group(2)}"
            if re.search(r'^    "lock_version"\s+', match.group(3), re.MULTILINE):
                lock_relations.add(relation)
    return relations, lock_relations


def _live_physical_relations() -> set[str]:
    relations, _lock_relations = _live_physical_relation_sets()
    return relations


def _physical_relations() -> tuple[set[str], tuple[str, ...], set[str]]:
    assert len(EXPECTED_PHYSICAL_TABLE_RELATIONS) == EXPECTED_TABLE_COUNT
    assert len(EXPECTED_LOCK_VERSION_RELATIONS) == 27
    assert len(EXPECTED_STATE_CAS_RELATIONS) == 24
    assert EXPECTED_STATE_CAS_RELATIONS <= EXPECTED_PHYSICAL_TABLE_RELATIONS
    assert EXPECTED_STATE_CAS_RELATIONS.isdisjoint(EXPECTED_LOCK_VERSION_RELATIONS)
    return (
        set(EXPECTED_PHYSICAL_TABLE_RELATIONS),
        EXPECTED_VIEW_RELATIONS,
        set(EXPECTED_LOCK_VERSION_RELATIONS),
    )


def _source_refs() -> list[dict[str, str]]:
    refs = [
        {"path": path, "sha256": digest}
        for path, digest in CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES
    ]
    refs.append(
        {
            "archive_path": EXPECTED_ARCHIVE_TUPLE[0],
            "archive_sha256": EXPECTED_ARCHIVE_TUPLE[1],
            "member_path": EXPECTED_ARCHIVE_TUPLE[2],
            "member_sha256": EXPECTED_ARCHIVE_TUPLE[3],
        }
    )
    return refs


def _uow_surfaces() -> dict[str, dict[str, Any]]:
    join_parameter = "token"
    return {
        module: {
            "protocol_path": f"python/raos/ports/{module}/repositories.py",
            "factory_signature": "begin(self, context: PersistenceContext) -> ModuleUnitOfWork",
            "repository_properties": [
                f"repositories: {module.title()}Repositories",
            ],
            "shared_properties": [
                "audit: AuditEventAppender",
                "outbox: OutboxEventAppender",
                "idempotency: IdempotencyRepository",
            ],
            "outer_methods": [
                "__enter__(self) -> ModuleUnitOfWork",
                "__exit__(self, exc_type, exc, tb) -> None",
                "flush(self) -> None",
                "commit(self) -> None",
                "rollback(self) -> None",
            ],
            "joined_methods": [
                f"join(self, {join_parameter}: TransactionJoin) -> "
                "JoinedModuleUnitOfWork",
                "__enter__(self) -> JoinedModuleUnitOfWork",
                "__exit__(self, exc_type, exc, tb) -> None",
            ],
            "join_token_behavior": "join consumes an opaque TransactionJoin and never owns commit",
            "unavailable_or_raises": [
                "joined commit raises TransactionOwnershipError",
                "nested outer begin raises TransactionOwnershipError",
            ],
            "exit_behavior": [
                "rollback on exception, cancellation, or exit without commit",
                "close the internal Session after outer exit",
                "propagate the original exception",
            ],
        }
        for module in (
            "ops",
            "iam",
            "portfolio",
            "catalog",
            "evidence",
            "editorial",
            "ai",
            "policy",
        )
    }


def _mapper_targets() -> dict[str, dict[str, Any]]:
    return {
        module: {
            "protocol_path": f"python/raos/ports/{module}/repositories.py",
            "domain_types": [f"{module.title()} aggregate entities and typed IDs"],
            "value_types": ["PersistedVersion and module value objects"],
            "mapper_path": f"python/raos/adapters/persistence/sqlalchemy/mappers/{module}.py",
            "row_input": "adapter-owned SQLAlchemy row is consumed only inside the mapper",
            "row_output": "complete Domain entity or value object with child ownership",
            "corruption_behavior": "unknown enum or strict JSON maps to PersistenceCorruption",
            "boundary": "SQLAlchemy rows and generic dictionaries never cross inward Ports",
        }
        for module in (
            "ops",
            "iam",
            "portfolio",
            "catalog",
            "evidence",
            "editorial",
            "ai",
            "policy",
        )
    }


def build_pass_candidate() -> dict[str, Any]:
    relations, views, locks = _physical_relations()
    by_schema: dict[str, list[str]] = {}
    for relation in sorted(relations):
        schema, table = relation.split(".", 1)
        by_schema.setdefault(schema, []).append(table)
    state_relations = sorted(EXPECTED_STATE_CAS_RELATIONS)
    return {
        "DESIGN_HANDOFF_V1": {
            "authority": {
                "status": "PROPOSED_UNAPPROVED_HANDOFF",
                "proposal_effect": "NO_IMPLEMENTATION_AUTHORITY_UNTIL_ACTIVATION_CONDITIONS_ARE_MET",
                "activation_conditions": [
                    "Exact repository-owner approval of these bytes is required.",
                    "Fresh canonical reconciliation is required.",
                ],
                "blocked_until_activation": [
                    "implementation_worker handoff",
                    "production work",
                ],
            },
            "approved_story": {
                "id": "ST-0308",
                "title": "Persistence ports and repositories",
                "objective": "Implement Domain-facing persistence Ports against the database.",
                "declared_dependencies": ["ST-0304", "ST-0105"],
                "deliverables": ["repositories", "transaction boundary"],
                "canonical_acceptance_focus": "cross-module write rules",
                "required_suites": ["TST-005", "TST-008"],
            },
            "approved_scope": {
                "decision_ids_resolved_by_this_proposal": [
                    "ST0308-D1",
                    "ST0308-D2",
                    "ST0308-D3",
                    "ST0308-D4",
                    "ST0308-D5",
                    "ST0308-D6",
                ],
                "schema_cut": sorted(by_schema),
                "physical_cut": {
                    "tables": EXPECTED_TABLE_COUNT,
                    "views": EXPECTED_VIEW_COUNT,
                    "postgresql_server_version_num": 180004,
                    "inventory_sha256": EXPECTED_INVENTORY_SHA256,
                },
                "implementation_outputs": ["inward Ports", "repositories"],
                "explicit_non_goals": ["production persistence", "schema changes"],
            },
            "source_design_refs": {
                "required_v3_authority_inputs": _source_refs(),
            },
            "decision": {
                "repository_inventory": {
                    "selected_option": "current physical predecessor cut",
                    "selection_statement": "The complete current physical predecessor is the selected cut.",
                    "inventory_normalization": {
                        "format": "ST0308_PHYSICAL_INVENTORY_V1 with sorted TABLE and VIEW lines",
                        "sha256": EXPECTED_INVENTORY_SHA256,
                        "counts": {
                            "tables": EXPECTED_TABLE_COUNT,
                            "views": EXPECTED_VIEW_COUNT,
                        },
                    },
                    "included_inventory": {
                        "schemas": by_schema,
                        "views": list(views),
                        "counts_by_schema": {
                            schema: len(tables) for schema, tables in by_schema.items()
                        },
                    },
                },
                "port_contracts": {
                    "selected_option": "aggregate-specific inward Protocols",
                    "repositories": {
                        "policy": [
                            {
                                "tables_or_views": ["policy.finding", "policy.waiver"],
                                "methods": [
                                    "transition(..., expected_status: FindingStatus)",
                                ],
                            }
                        ]
                    },
                    "concurrency_models": {
                        "LOCK_VERSION_CAS": {
                            "relations": sorted(locks),
                            "rule": "WHERE primary_key = :id AND lock_version = :expected_version; successful mutation increments lock_version exactly once.",
                        },
                        "STATE_CAS_WITHOUT_LOCK_VERSION": {
                            "relations": state_relations,
                            "rule": "Exact expected status/state predicates only; no physical version column is assumed.",
                        },
                    },
                    "state_cas_predicates": {
                        "policy.finding": {
                            "resolution": {
                                "where": "WHERE id = :id AND status = :expected_status AND resolved_at IS NULL",
                                "atomic_fields": [
                                    "status",
                                    "resolution",
                                    "resolved_at",
                                ],
                            }
                        },
                        "policy.waiver": {
                            "decision": {
                                "where": "WHERE id = :id AND status = :expected_status AND decided_at IS NULL",
                                "atomic_fields": ["status", "decision", "decided_at"],
                            },
                            "revocation": {
                                "where": "WHERE id = :id AND status = :expected_status AND revoked_at IS NULL",
                                "atomic_fields": ["status", "revoked_at", "revoked_by"],
                            },
                            "expiry": {
                                "where": "WHERE id = :id AND status = :expected_status AND expires_at IS NOT NULL AND expires_at < transaction_timestamp()",
                                "atomic_fields": ["status", "expired_at"],
                            },
                        },
                    },
                    "domain_value_mapper_targets": _mapper_targets(),
                },
                "mapping_strategy": {
                    "selected_option": "adapter-owned SQLAlchemy rows with explicit Domain mappers",
                },
                "transaction_boundary": {
                    "selected_option": "one outer synchronous transaction",
                    "module_uows": _uow_surfaces(),
                },
                "cross_module_and_outbox_boundary": {
                    "selected_mechanisms": [
                        "shared persistence Ports",
                        "Outbox staging",
                    ],
                    "aggregate_version_rule": "Outbox aggregate_version is the successful persisted post-transition version.",
                    "shared_infrastructure_ownership": {
                        name: {
                            "protocol_path": "python/raos/ports/persistence/shared.py",
                            "adapter_path": "python/raos/adapters/persistence/shared.py",
                            "table": table,
                            "write_owner": "OPS_INFRASTRUCTURE_ADAPTER",
                            "uow_exposure": "exposed through the shared persistence Protocol property",
                            "cross_module_import_rule": "modules do not import another module Repository or table",
                        }
                        for name, table in (
                            ("audit", "ops.audit_event"),
                            ("outbox", "ops.outbox_event"),
                            ("idempotency", "ops.idempotency_record"),
                        )
                    },
                    "idempotency_contract": {
                        "identity": "IdempotencyIdentity(actor_fingerprint, route_key, idempotency_key)",
                        "claim": "IdempotencyClaim(record_id, expected_request_hash)",
                        "outcome": "IdempotencyOutcome with replayable response values",
                        "decision_variants": ["NewClaim", "Replay", "InProgress"],
                        "completion_success_signature": "complete_success(claim: IdempotencyClaim, expected_request_hash: RequestHash)",
                        "completion_failure_signature": "complete_failure(claim: IdempotencyClaim, expected_request_hash: RequestHash)",
                        "claim_sql": "INSERT INTO ops.idempotency_record (...) ON CONFLICT (...) DO NOTHING RETURNING id, request_hash",
                        "completion_predicate": "UPDATE ... WHERE id = :id AND status = 'IN_PROGRESS' AND request_hash = :expected_request_hash",
                        "replay_semantics": "same identity and hash replays terminal outcome; differing hash mismatches",
                    },
                    "aggregate_version_sources": {
                        "event_producing_roots": ["portfolio.site", "policy.finding"],
                        "versioned": {
                            "portfolio.site": "persisted lock_version after the successful CAS transition",
                        },
                        "excluded": {
                            "policy.finding": "no event is emitted because no persisted aggregate version is approved",
                        },
                    },
                },
                "connection_and_identity_boundary": {
                    "selected_option": "prevalidated injected provider",
                    "candidate_roles": ["raos_api_rw", "raos_worker_rw"],
                },
            },
            "rationale": [
                "The physical set is derived from pinned predecessor inputs."
            ],
            "rejected_alternatives": [
                {
                    "alternative": "91-table cut",
                    "reason": "It conflicts with current physical inputs.",
                }
            ],
            "constraints": [
                "No migrations, schema changes, or production persistence."
            ],
            "security_and_approval_gates": {
                "human_authority_boundaries": [
                    "exact-byte owner approval",
                    "canonical reconciliation",
                ],
                "implementation_activation_gate": "Approval and reconciliation remain separate gates.",
                "formal_verification_gate": "Local output is not formal TST evidence.",
                "release_gate": "Release remains outside this Story.",
            },
            "acceptance_criteria": [
                {
                    "id": "AC-01",
                    "assertion": "All required references are hash checked.",
                }
            ],
            "required_test_evidence": {
                "suite_authority_state": {
                    "TST-005": {"name": "Port contracts", "required": True},
                    "TST-008": {
                        "name": "PostgreSQL 18.4 repository behavior",
                        "required": True,
                        "exact_server_version_num": 180004,
                    },
                }
            },
            "open_decisions": [],
            "approval": {
                "status": "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL",
                "approved_by": None,
                "approved_at": None,
                "canonical_reconciliation": "PENDING_CODEX_CONFLICT_FREE_CONFIRMATION",
                "implementation_authority": "BLOCKED",
                "activation_note": "A pass is evidence only and never grants implementation authority.",
            },
        }
    }


@pytest.fixture
def pass_candidate() -> dict[str, Any]:
    return build_pass_candidate()


@pytest.fixture
def candidate_path(tmp_path: Path, pass_candidate: dict[str, Any]) -> Path:
    path = tmp_path / "DESIGN_HANDOFF_V1.yaml"
    path.write_text(
        yaml.safe_dump(pass_candidate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def run_validator(
    handoff: Path,
    *,
    expected_sha256: str | None = None,
    repository_root: Path = REPOSITORY_ROOT,
) -> subprocess.CompletedProcess[str]:
    digest = expected_sha256 or hashlib.sha256(handoff.read_bytes()).hexdigest()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--handoff",
            str(handoff),
            "--expected-sha256",
            digest,
            "--repository-root",
            str(repository_root),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def load_validator_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("st0308_validator_probe", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert process.stderr == ""
    return json.loads(process.stdout)


def clone_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(candidate)


def trusted_closure_paths() -> tuple[Path, ...]:
    """Return the exact pinned files loaded by the validator."""

    paths = {
        Path("changes/st-0308/contracts/design-handoff-validation.v1.yaml"),
        *(Path(path) for path, _digest in PINNED_SOURCE_REFERENCE_TUPLES),
    }
    st0104 = json.loads(
        (
            REPOSITORY_ROOT / "contracts/raos-v0.4/contract-repository.v0.4.json"
        ).read_text(encoding="utf-8")
    )
    for row in st0104["artifacts"]:
        paths.add(Path("contracts/raos-v0.4") / row["path"])
    return tuple(sorted(paths))


def disposable_repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "disposable-repository"
    for relative in trusted_closure_paths():
        source = REPOSITORY_ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    sentinel = root / "unrelated" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("unrelated sentinel\n", encoding="utf-8")
    return root


def _snapshot_entry(path: Path) -> tuple[str, int, int, int, str | None]:
    metadata = path.lstat()
    if stat.S_ISREG(metadata.st_mode):
        entry_type = "regular"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    elif stat.S_ISDIR(metadata.st_mode):
        entry_type = "directory"
        digest = None
    elif stat.S_ISLNK(metadata.st_mode):
        entry_type = "symlink"
        digest = hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest()
    elif stat.S_ISFIFO(metadata.st_mode):
        entry_type = "fifo"
        digest = None
    else:
        entry_type = "special"
        digest = None
    return (
        entry_type,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_size,
        metadata.st_mtime_ns,
        digest,
    )


def snapshot_repository_tree(
    root: Path,
) -> dict[str, tuple[str, int, int, int, str | None]]:
    """Snapshot every path without following symlinks or reading specials."""

    snapshot: dict[str, tuple[str, int, int, int, str | None]] = {}

    def visit(path: Path) -> None:
        relative = "." if path == root else path.relative_to(root).as_posix()
        metadata = path.lstat()
        snapshot[relative] = _snapshot_entry(path)
        if stat.S_ISDIR(metadata.st_mode):
            with os.scandir(path) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    visit(Path(entry.path))

    visit(root)
    return snapshot
