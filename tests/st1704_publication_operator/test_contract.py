"""Closed contract and additive Canonical decision checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/publication-operator-v2"

ARTICLE_BINDINGS = {
    "st1704-portable-power-station-guide": "portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences": (
        "anker-solix-c300-c800-c1000-differences"
    ),
    "st1704-countertop-dishwasher-for-small-households": (
        "countertop-dishwasher-for-small-households"
    ),
    "st1704-compact-robot-vacuum-shortlist": "compact-robot-vacuum-shortlist",
}


def test_addendum_preserves_human_decision_and_forbids_self_approval(
    canonical_addendum: dict[str, Any],
) -> None:
    decision = canonical_addendum["decision"]
    assert decision["id"] == "INT-DEC-016"
    assert decision["status"] == "ADOPTED_ADDITIVE_CLARIFICATION"
    assert decision["relationship_to_existing_decisions"] == {
        "INT-DEC-009": "PRESERVED_HUMAN_FINAL_PUBLICATION_DECISION",
        "INT-DEC-013": (
            "PRESERVED_CODEX_HAS_NO_SELF_APPROVAL_OR_FINAL_APPROVAL_AUTHORITY"
        ),
    }
    assert "CODEX_CANNOT_APPROVE_OR_MODIFY_APPROVAL" in decision["mandatory_boundaries"]
    assert decision["excluded_article"] == "st1703-first-suitcase-comparison"
    assert canonical_addendum["document"]["base_canonical_bytes_modified"] is False


def test_routes_operation_gates_and_receipts_are_closed(
    publication_contract: dict[str, Any],
) -> None:
    assert publication_contract["site"]["wordpress_core_release_line"] == "7.1.x"
    assert publication_contract["operation"]["exact"] == "PUBLISH_ST1704_ARTICLE"
    assert publication_contract["operation"]["allowed_article_bindings"] == (
        ARTICLE_BINDINGS
    )
    assert (
        publication_contract["operation"][
            "maximum_global_nonterminal_unexpired_publication_proposals"
        ]
        == 1
    )
    assert [(row["method"], row["path"]) for row in publication_contract["routes"]] == [
        ("GET", "/wp-json/raos-operator/v2/status"),
        ("POST", "/wp-json/raos-operator/v2/proposals"),
        ("GET", "/wp-json/raos-operator/v2/proposals/{64_lowercase_hex}"),
        (
            "POST",
            "/wp-json/raos-operator/v2/proposals/{64_lowercase_hex}/apply",
        ),
    ]
    assert publication_contract["activation"] == {
        "master_constant": "RAOS_OPERATOR_WRITES_ENABLED",
        "publication_constant": "RAOS_ST1704_PUBLICATION_WRITES_ENABLED",
        "enabled_iff_both_defined_and_strictly_true": True,
        "default": "DISABLED",
        "rest_or_option_toggle": "ABSENT",
        "plugin_install_and_activation": "HUMAN_BOOTSTRAP_ONLY",
    }
    assert publication_contract["approval"]["rest_route"] == "ABSENT"
    assert publication_contract["approval"]["executor_can_self_approve"] is False
    assert publication_contract["proposal_receipt"]["exact_get_recovery"] == {
        "replayed": True,
        "state": "ANY_CLOSED_PROPOSAL_STATE",
        "sensitive_approval_or_audit_material": "ABSENT",
    }
    assert publication_contract["proposal_receipt"]["list_or_search_receipt"] == (
        "ABSENT"
    )


def test_proposal_request_and_golden_bytes_are_exact(
    publication_contract: dict[str, Any],
) -> None:
    golden = json.loads(
        (SLICE / "contracts/canonical-publication-proposal-golden.v2.json").read_bytes()
    )
    canonical = golden["canonical_ascii_json"].encode("ascii")
    parsed = json.loads(canonical)
    assert list(sorted(parsed)) == sorted(
        publication_contract["proposal_request"]["exact_keys"]
    )
    assert (
        json.dumps(
            parsed,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        == canonical
    )
    assert len(canonical) == golden["canonical_byte_length"] == 748
    assert hashlib.sha256(canonical).hexdigest() == golden["proposal_id"]
    assert parsed["request_token"] == golden["request_token"]
    assert parsed["operation"] == "PUBLISH_ST1704_ARTICLE"
    assert parsed["operator_contract_version"] == 2
    assert parsed["profile_version"] == 2
    assert parsed["category_contract"] == "KURASHINO_DOGU_SINGLE_V1"


def test_mutation_boundary_preserves_content_media_and_taxonomy_creation(
    publication_contract: dict[str, Any],
) -> None:
    operation = publication_contract["operation"]
    assert operation["exact_target_changes"] == [
        "POST_STATUS_DRAFT_TO_PUBLISH",
        "POST_NAME_REVIEW_SLUG_TO_FIXED_PUBLIC_SLUG",
        "CATEGORY_ASSIGNMENT_TO_EXACT_EXISTING_SINGLE_TERM",
    ]
    assert operation["category"]["term_creation"] == "FORBIDDEN"
    assert {
        "POST_TITLE",
        "POST_EXCERPT",
        "POST_CONTENT",
        "_raos_publication_snapshot_v1",
        "FEATURED_MEDIA_AND__thumbnail_id",
        "TAGS",
    }.issubset(operation["must_preserve_exact"])
    assert publication_contract["authentication"]["executor_can_edit_posts"] is False
    assert publication_contract["authentication"]["executor_can_publish_posts"] is False
    assert publication_contract["release_boundary"] == {
        "local_implementation": "ALLOWED",
        "plugin_install_activation_and_gate_change": "HUMAN_EXTERNAL_OPERATION",
        "live_publication": "REQUIRES_EXACT_DISTINCT_HUMAN_APPROVAL",
        "formal_validation": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production_readiness": "NOT_READY",
    }


def test_additive_revision_contract_keeps_literal_ids_and_draft_invariants() -> None:
    revision = json.loads(
        (
            SLICE
            / "contracts/self-hosted-wordpress-draft-revision.v2.json"
        ).read_bytes()
    )
    assert revision["operation"] == "REVISE_ST1704_DRAFT"
    assert revision["article_post_bindings"] == {
        "st1704-portable-power-station-guide": 28,
        "st1704-anker-solix-c300-c800-c1000-differences": 29,
        "st1704-countertop-dishwasher-for-small-households": 41,
        "st1704-compact-robot-vacuum-shortlist": 30,
    }
    assert "post_status_draft" in revision["immutable"]
    assert "proposal_applied_receipt" in revision["atomic_write_set"]
    assert revision["recovery"]["proposal_id"] == "SAME_PROPOSAL_ID_ONLY"
    assert revision["recovery"]["applying"] == (
        "EXACT_IDEMPOTENT_APPLY_RETRY_ONLY"
    )
    assert revision["recovery"]["classification"] == [
        "EXACT_SUCCESSOR",
        "EXACT_PREDECESSOR",
    ]
    assert revision["recovery"]["mutex"] == "PUBLICATION_V2_SHARED_MUTEX"
    assert revision["recovery_route"].endswith("/{proposal_id}/revision-state")
