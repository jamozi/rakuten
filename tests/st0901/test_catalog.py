"""Exact installed human-review checklist catalog tests."""

from __future__ import annotations

import hashlib

import yaml

from .support import REPOSITORY_ROOT
from raos.domain.publishing.review_workflow import (
    CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON,
    CHECKLIST_RESPONSE_TOKENS,
    HUMAN_REVIEW_CHECKLIST,
    HUMAN_REVIEW_CHECKLIST_IDS,
    HUMAN_REVIEW_CHECKLIST_SHA256,
    HUMAN_REVIEW_CHECKLIST_VERSION,
    ChecklistItemStatus,
)


CHECKLIST_PATH = (
    REPOSITORY_ROOT
    / "contracts/raos-v0.4/contracts/content/RAOS_06_review_checklist_v0.1.yaml"
)


def test_catalog_bytes_version_hash_count_and_exact_ids_match_installed_source() -> (
    None
):
    source_bytes = CHECKLIST_PATH.read_bytes()
    source = yaml.safe_load(source_bytes)

    assert hashlib.sha256(source_bytes).hexdigest() == HUMAN_REVIEW_CHECKLIST_SHA256
    assert HUMAN_REVIEW_CHECKLIST_SHA256 == (
        "8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63"
    )
    assert source["checklist_version"] == HUMAN_REVIEW_CHECKLIST_VERSION == "1.0.0"
    assert len(source["items"]) == len(HUMAN_REVIEW_CHECKLIST) == 75
    assert HUMAN_REVIEW_CHECKLIST_IDS == tuple(
        f"REV-{number:03d}" for number in range(1, 76)
    )


def test_every_catalog_record_is_exact_without_invented_metadata() -> None:
    source = yaml.safe_load(CHECKLIST_PATH.read_bytes())
    expected = tuple(
        (item["id"], item["section"], item["check"]) for item in source["items"]
    )
    actual = tuple(
        (item.item_id, item.section, item.check) for item in HUMAN_REVIEW_CHECKLIST
    )

    assert actual == expected
    assert all(
        set(item)
        == {
            "id",
            "section",
            "check",
            "response",
            "evidence_or_comment_required_on",
        }
        for item in source["items"]
    )
    assert all(
        "severity" not in item
        and "blocker" not in item
        and "applicability" not in item
        and "review_type" not in item
        for item in source["items"]
    )


def test_response_and_justification_vocabularies_are_exact_for_all_items() -> None:
    source = yaml.safe_load(CHECKLIST_PATH.read_bytes())
    expected_response = ["PASS", "FAIL", "NOT_APPLICABLE_WITH_REASON"]
    expected_justification = ["FAIL", "NOT_APPLICABLE_WITH_REASON"]

    assert tuple(value.value for value in CHECKLIST_RESPONSE_TOKENS) == tuple(
        expected_response
    )
    assert tuple(
        value.value for value in CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON
    ) == tuple(expected_justification)
    assert all(item["response"] == expected_response for item in source["items"])
    assert all(
        item["evidence_or_comment_required_on"] == expected_justification
        for item in source["items"]
    )
    assert all(
        item.response_tokens == tuple(ChecklistItemStatus)
        and item.evidence_or_comment_required_on
        == (
            ChecklistItemStatus.FAIL,
            ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
        )
        for item in HUMAN_REVIEW_CHECKLIST
    )


def test_source_mutations_change_the_pinned_hash() -> None:
    source_bytes = CHECKLIST_PATH.read_bytes()
    mutations = (
        source_bytes.replace(b"checklist_version: 1.0.0", b"checklist_version: 1.0.1"),
        source_bytes.replace(b"REV-001", b"REV-999", 1),
        source_bytes + b"\n",
    )

    assert all(
        hashlib.sha256(candidate).hexdigest() != HUMAN_REVIEW_CHECKLIST_SHA256
        for candidate in mutations
    )
