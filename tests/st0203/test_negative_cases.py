"""Fail-closed semantic drift cases for ST-0203."""

from __future__ import annotations

from typing import Any


def test_duplicate_identity_drift_is_rejected(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["fake"]["duplicate_injection"]["preserves_message_id"] = False
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_stale_receipt_acceptance_drift_is_rejected(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["port"]["receipt_handle"]["stale_or_unknown"] = "IGNORE"
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_attempt_budget_expansion_is_rejected(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["message"]["max_attempts"]["maximum"] = 500
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_external_runtime_scope_creep_is_rejected(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["fake"]["network"] = "ALLOWED"
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_formal_status_promotion_is_rejected(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["document"]["formal_verification"] = "PASS"
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_future_security_obligation_cannot_be_claimed(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["security"]["controls"][0]["relationship"] = "IMPLEMENTED"
    reject_contract(mutable_contract, "differs from the reviewed value")


def test_boolean_cannot_alias_integer_contract_value(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["message"]["max_attempts"]["minimum"] = True
    reject_contract(mutable_contract, "type differs")


def test_integer_cannot_alias_boolean_contract_value(
    mutable_contract: dict[str, Any], reject_contract
) -> None:
    mutable_contract["fake"]["duplicate_injection"]["preserves_message_id"] = 1
    reject_contract(mutable_contract, "type differs")
