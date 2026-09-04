from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SALES_STATE_PATH = (
    ROOT / "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
)
PORTFOLIO_PATH = ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
SNAPSHOT_KIND = "STRUCTURED_OFFICIAL_SALES_STATE_SNAPSHOT_V1"
HASH_FIELDS = (
    "checked_at_utc",
    "product_id",
    "state",
    "availability_scope",
    "official_url",
    "status_evidence_urls",
    "locator",
    "basis",
    "variant_caveat",
    "alternative",
)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_structured_snapshot(row: dict[str, object]) -> None:
    payload = {field: row[field] for field in HASH_FIELDS}
    expected = _canonical_sha256(payload)
    actual = row["structured_snapshot_sha256"]
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise ValueError("structured_snapshot_sha256 mismatch")


def test_sales_state_contract_covers_the_portfolio_exactly() -> None:
    contract = _read_json(SALES_STATE_PATH)
    portfolio = _read_json(PORTFOLIO_PATH)

    assert contract["schema"] == "RAOS_MANUFACTURER_SALES_STATE_AUDIT_V1"
    assert contract["snapshot_kind"] == SNAPSHOT_KIND
    assert contract["hash_contract"] == {
        "algorithm": "SHA-256",
        "canonicalization": (
            "UTF-8 JSON with recursively sorted object keys, no insignificant "
            "whitespace, and unescaped Unicode"
        ),
        "fields": list(HASH_FIELDS),
    }
    assert contract["evidence_resolution_policy"] == {
        "exact_variant_reader_visible_purchase_ui_required": True,
        "reader_visible_sold_out_discontinued_or_preorder_precedes_hidden_structured_availability": True,
        "structured_data_alone_cannot_establish_available": True,
        "conflict_resolution": "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK",
        "preorder_resolution": "FAIL_CLOSED_TO_UNKNOWN",
    }

    sales_rows = contract["products"]
    portfolio_rows = portfolio["products"]
    assert isinstance(sales_rows, list)
    assert isinstance(portfolio_rows, list)
    assert len(sales_rows) == len(portfolio_rows) == 33

    sales_by_id = {row["product_id"]: row for row in sales_rows}
    portfolio_by_id = {row["product_id"]: row for row in portfolio_rows}
    assert len(sales_by_id) == len(portfolio_by_id) == 33
    assert set(sales_by_id) == set(portfolio_by_id)
    assert {
        product_id: row["official_url"] for product_id, row in sales_by_id.items()
    } == {
        product_id: row["official_url"] for product_id, row in portfolio_by_id.items()
    }

    checked_at = contract["checked_at_utc"]
    required_fields = set(HASH_FIELDS) | {
        "snapshot_kind",
        "structured_snapshot_sha256",
    }
    for row in sales_rows:
        assert required_fields <= set(row)
        assert row["checked_at_utc"] >= checked_at
        assert row["availability_scope"] in {"MODEL", "VARIANT"}
        assert row["snapshot_kind"] == SNAPSHOT_KIND
        assert row["state"] in {
            "AVAILABLE",
            "OUT_OF_STOCK",
            "DISCONTINUED",
            "UNKNOWN",
        }
        evidence_urls = row["status_evidence_urls"]
        assert isinstance(evidence_urls, list)
        assert evidence_urls
        assert all(url.startswith("https://") for url in evidence_urls)
        assert row["alternative"] is None
    assert min(row["checked_at_utc"] for row in sales_rows) == checked_at


def test_sales_state_counts_match_the_official_source_audit() -> None:
    contract = _read_json(SALES_STATE_PATH)
    rows = contract["products"]
    assert isinstance(rows, list)

    counts = Counter(row["state"] for row in rows)
    assert counts == {"AVAILABLE": 33}


def test_structured_snapshot_hashes_reject_semantic_tampering() -> None:
    contract = _read_json(SALES_STATE_PATH)
    rows = contract["products"]
    assert isinstance(rows, list)

    for row in rows:
        _verify_structured_snapshot(row)
        assert "raw_body_sha256" not in row

    tampered_basis = deepcopy(rows[0])
    tampered_basis["basis"] = f"{tampered_basis['basis']} 改変"
    with pytest.raises(ValueError, match="structured_snapshot_sha256 mismatch"):
        _verify_structured_snapshot(tampered_basis)

    tampered_locator = deepcopy(rows[0])
    tampered_locator["locator"] = "hidden JSON only"
    with pytest.raises(ValueError, match="structured_snapshot_sha256 mismatch"):
        _verify_structured_snapshot(tampered_locator)


def test_publication_policy_is_fail_closed_and_manufacturer_scope_is_not_cta_proof() -> (
    None
):
    contract = _read_json(SALES_STATE_PATH)
    policy = contract["publication_policy"]
    assert policy["UNKNOWN"] == {
        "state_gate": "INELIGIBLE",
        "known_state": False,
        "recheck_required": True,
    }
    assert policy["DISCONTINUED"] == {
        "state_gate": "INELIGIBLE",
        "known_state": True,
        "recheck_required": True,
    }
    assert policy["OUT_OF_STOCK"] == {
        "state_gate": "INELIGIBLE",
        "known_state": True,
        "recheck_required": True,
    }
    assert policy["AVAILABLE"] == {
        "state_gate": "CONDITIONAL",
        "known_state": True,
        "recheck_required": True,
    }

    assert contract["availability_scope_policy"] == {
        scope: {
            "establishes_exact_rakuten_variant": False,
            "cta_requires_separate_exact_variant_evidence": True,
        }
        for scope in ("MODEL", "VARIANT")
    }

    rows = contract["products"]
    assert isinstance(rows, list)
    caveats = [row["variant_caveat"] for row in rows if row["variant_caveat"]]
    assert all(
        caveat["establishes_exact_rakuten_variant"] is False for caveat in caveats
    )
    assert {
        row["product_id"] for row in rows if row["availability_scope"] == "VARIANT"
    } == {
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-BLUETTI-AORA100-V2",
    }
    assert all(
        row["availability_scope"] == "MODEL"
        for row in rows
        if row["product_id"]
        not in {
            "PRD-ACE-DIFFERENCE-05721",
            "PRD-BLUETTI-AORA30-V2",
            "PRD-BLUETTI-AORA100-V2",
        }
    )


def test_removed_panasonic_products_are_absent_from_both_owner_contracts() -> None:
    contract = _read_json(SALES_STATE_PATH)
    portfolio = _read_json(PORTFOLIO_PATH)
    rows = contract["products"]
    assert isinstance(rows, list)
    removed = {
        "PRD-PANASONIC-NP-TMLK1",
        "PRD-PANASONIC-SOLOTA-NP-TML1-W",
    }
    portfolio_rows = portfolio["products"]
    assert isinstance(portfolio_rows, list)
    assert removed.isdisjoint({row["product_id"] for row in rows})
    assert removed.isdisjoint({row["product_id"] for row in portfolio_rows})


def test_visible_purchase_ui_precedes_conflicting_hidden_structured_state() -> None:
    contract = _read_json(SALES_STATE_PATH)
    policy = contract["evidence_resolution_policy"]
    assert policy["exact_variant_reader_visible_purchase_ui_required"] is True
    assert policy["structured_data_alone_cannot_establish_available"] is True
    assert (
        policy[
            "reader_visible_sold_out_discontinued_or_preorder_precedes_hidden_structured_availability"
        ]
        is True
    )
    assert policy["conflict_resolution"] == "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK"
    assert policy["preorder_resolution"] == "FAIL_CLOSED_TO_UNKNOWN"
