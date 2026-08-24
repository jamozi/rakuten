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
    assert set(document["capabilities"].values()) == {
        "NONE",
        "NONE_OD014_UNRESOLVED",
    }
    assert document["formal_evidence"] == {
        "tst_011_postgresql": "NOT_EXECUTED",
        "tst_012_http": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production": "NOT_AUTHORIZED",
    }
