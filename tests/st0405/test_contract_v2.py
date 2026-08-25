"""Source-contract drift and authority boundary checks for ST-0405 V2."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from conftest import REPOSITORY_ROOT
from raos.domain.ops.audit_runtime_v2 import AUDIT_RUNTIME_CONTRACT_SHA256_V2


CONTRACT = Path("changes/st-0405/contracts/local-audit-runtime.v2.yaml")


def test_contract_bytes_are_bound_to_the_runtime() -> None:
    content = (REPOSITORY_ROOT / CONTRACT).read_bytes()
    assert hashlib.sha256(content).hexdigest() == AUDIT_RUNTIME_CONTRACT_SHA256_V2


def test_contract_keeps_query_and_external_authority_disabled() -> None:
    document = yaml.safe_load((REPOSITORY_ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert document["schema"] == "RAOS_LOCAL_AUDIT_RUNTIME_V2"
    assert document["story_id"] == "ST-0405"
    assert document["authorization"] == {
        "source_story": "ST-0403",
        "service": "DurableAuthorizationService.recover_admin",
        "required_action": "edit_article_draft",
        "required_resource_kind": "ARTICLE_VERSION",
        "required_resource_state": "DRAFT",
        "direct_grant_provenance": "FORBIDDEN",
        "audit_store_open_before_authorization": "FORBIDDEN",
    }
    assert document["query"] == {
        "internal_integrity_query": "BOUNDED_CORRELATION_ONLY",
        "outward_query": "DISABLED",
        "reason": "ST0403_OPS012_SITE_SCOPE_CONFLICT",
    }
    assert document["writer"] == {
        "backend": "SQLITE_OWNER_PRIVATE",
        "initialization": "CREATED_ONLY",
        "create_primitive": "OWNER_ROOT_DIRFD_O_EXCL",
        "preexisting_empty_partial_foreign": "REJECT_UNCHANGED",
        "preexisting_legacy_schema": "REJECT_UNCHANGED_NO_MIGRATION",
        "database_mode": "0600",
        "owner_root_mode": "0700",
        "schema_validation": (
            "EXACT_APPLICATION_USER_STRICT_TABLE_XINFO_INDEX_TRIGGER_FK"
        ),
        "connection_profile": (
            "EXACT_FOREIGN_KEYS_TRUSTED_SCHEMA_TEMP_STORE_SYNC_SECURE_DELETE_"
            "JOURNAL_BUSY_TIMEOUT"
        ),
        "append_only": True,
        "append_guards": "EXACT_EVENT_MARKER_METADATA_TRIGGERS",
        "metadata_cas": "COUNT_HEAD_RECORD_SHA256",
        "idempotency_binding": "authorization_command_id_fingerprint",
        "canonical_validation": "FULL_EVENT_REDUNDANT_ROW_MARKER_METADATA",
        "hash_chain": "FULL_PREFIX_SHA256",
        "readback_required": True,
        "ambiguous_commit_recovery": "EXACT_ONLY",
        "commit_exception_open_transaction": "STORAGE_ROLLED_BACK",
        "commit_exception_closed_transaction": "STORAGE_COMMIT_UNKNOWN",
        "blind_retry": "FORBIDDEN",
        "synthetic_atomicity_marker": True,
        "business_mutation_claim": "NONE",
    }
    assert document["identity"] == {
        "owner_root_anchor": "PATH_DEVICE_INODE",
        "database_anchor": "DEVICE_INODE_SINGLE_LINK",
        "process_prefix_anchor": "COUNT_HEAD_AND_PRIOR_PREFIX",
        "named_file_replacement": "TAMPER_DETECTED",
        "same_process_valid_snapshot_rollback": "TAMPER_DETECTED",
        "fresh_process_external_rollback_anchor": "NONE",
    }
    assert document["collaborators"] == {
        "context_result": "RECONSTRUCT_AND_REVALIDATE",
        "store_input_output": "RECONSTRUCT_AND_REVALIDATE",
        "external_action_count": "EXACT_INTEGER_ZERO_BEFORE_AND_AFTER",
    }
    assert set(document["capabilities"].values()) == {
        "NONE",
        "NONE_OD014_UNRESOLVED",
    }
    assert document["authority"] == {
        "external_action_count": 0,
        "external_write": "NONE",
        "provider_write": "NONE",
        "staging_write": "NONE",
        "release": "NONE",
        "publication": "NONE",
        "production": "NONE",
    }
    assert document["formal_evidence"] == {
        "tst_011_postgresql": "NOT_EXECUTED",
        "tst_012_http": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production": "NOT_AUTHORIZED",
    }
