"""Detached owner-approval tests for the inert ST-1903 candidate."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

import pytest

from scripts import build_st1903_autonomous_publication_policy as generator


def _approval_inputs() -> tuple[dict[str, Any], bytes, bytes]:
    approval, approval_raw = generator._load_yaml(
        generator.APPROVAL_PATH, "APPROVAL_YAML_INVALID"
    )
    handoff_raw = (generator.REPO_ROOT / generator.HANDOFF_PATH).read_bytes()
    return approval, approval_raw, handoff_raw


def test_detached_approval_binds_exact_handoff_and_owner_statement() -> None:
    """Only the exact owner statement approves the exact inert handoff bytes."""

    approval, approval_raw, handoff_raw = _approval_inputs()
    generator._validate_approval(approval, approval_raw, handoff_raw)
    record = approval["DESIGN_HANDOFF_APPROVAL_V1"]
    statement = record["owner_approval_statement"].encode("utf-8")

    assert len(approval_raw) == generator.EXPECTED_APPROVAL_BYTES
    assert (
        hashlib.sha256(approval_raw).hexdigest() == generator.EXPECTED_APPROVAL_SHA256
    )
    assert len(statement) == 114
    assert (
        hashlib.sha256(statement).hexdigest()
        == generator.EXPECTED_OWNER_APPROVAL_STATEMENT_SHA256
    )
    assert len(handoff_raw) == record["handoff_bytes"]
    assert hashlib.sha256(handoff_raw).hexdigest() == record["handoff_sha256"]
    assert record["status"] == "OWNER_APPROVED_INERT_POLICY_CANDIDATE_ONLY"
    assert record["boundaries"]["canonical_mutation_authority"] == "NONE"
    assert record["boundaries"]["activation"] == "DISABLED"
    assert record["boundaries"]["publication"] == "NOT_EXECUTED"
    assert record["boundaries"]["publication_authority"] == "NOT_AUTHORIZED"


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("status", "APPROVED_FOR_PUBLICATION"),
        ("canonical_reconciliation", "EXECUTED"),
        ("actions", [{"kind": "PUBLISH"}]),
    ),
)
def test_approval_authority_drift_is_rejected(field: str, replacement: object) -> None:
    """The detached record cannot acquire release, canonical, or action authority."""

    approval, approval_raw, handoff_raw = _approval_inputs()
    mutated = deepcopy(approval)
    mutated["DESIGN_HANDOFF_APPROVAL_V1"][field] = replacement

    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_approval(mutated, approval_raw, handoff_raw)
    assert captured.value.code == "APPROVAL_RECORD_INVALID"


def test_approval_byte_drift_is_rejected() -> None:
    """A detached approval revision requires a new reviewed record digest."""

    approval, approval_raw, handoff_raw = _approval_inputs()
    with pytest.raises(generator.BuildRefusal) as captured:
        generator._validate_approval(approval, approval_raw + b"\n", handoff_raw)
    assert captured.value.code == "APPROVAL_BYTES_INVALID"
