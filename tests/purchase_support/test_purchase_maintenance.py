"""Read-only maintenance queue for the purchase-support catalog (no fetch, no write)."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
SCRIPT = ROOT / "scripts/report_reader_purchase_support_maintenance.py"
AS_OF = date(2026, 9, 15)


def synthetic():
    conflict_sources = [
        {
            "value": "資料Aの値",
            "source_url": "https://maker.example/a",
            "locator": "A",
            "checked_at": "2026-08-20",
        },
        {
            "value": "資料Bの値",
            "source_url": "https://maker.example/b",
            "locator": "B",
            "checked_at": "2026-08-20",
        },
    ]
    return {
        "products": [
            {
                "product_id": "P-B",
                "facts": [
                    {
                        "label": "重量",
                        "text": "3kg",
                        "state": "PRESERVED",
                        "checked_at": "not-a-date",
                    },
                ],
                "guide_facts": [],
            },
            {
                "product_id": "P-A",
                "facts": [
                    {
                        "label": "容量",
                        "text": "3L",
                        "state": "KNOWN",
                        "checked_at": "2026-09-01",
                    },
                    {
                        "label": "開扉時の寸法",
                        "text": "未確認",
                        "state": "UNKNOWN",
                        "checked_at": "2026-09-10",
                    },
                ],
                "guide_facts": [
                    {
                        "field": "door",
                        "text": "資料で異なる",
                        "state": "CONFLICT",
                        "checked_at": "2026-08-20",
                        "conflict_sources": conflict_sources,
                    },
                    {
                        "field": "water_supply",
                        "text": "給水",
                        "state": "KNOWN",
                        "checked_at": "2026-09-14",
                    },
                ],
            },
        ],
        "offers": [
            {
                # 23:59:59 JST on 2026-09-14: past at as_of 2026-09-15.
                "offer_id": "O-expired",
                "product_id": "P-A",
                "valid_until": "2026-09-14T14:59:59Z",
                "source_url": "https://shop.example/a",
                "source_urls": ["https://shop.example/a", "https://shop.example/terms"],
                "url": "https://hb.afl.rakuten.co.jp/offer-a",
                "affiliate_url": "https://hb.afl.rakuten.co.jp/offer-a",
                "merchant_url": "https://item.rakuten.co.jp/shop/a/",
            },
            {
                # 00:00 JST on 2026-09-15: the same UTC date, but not past in JST.
                "offer_id": "O-current",
                "product_id": "P-A",
                "valid_until": "2026-09-14T15:00:00Z",
                "source_url": "https://shop.example/b",
                "url": "https://hb.afl.rakuten.co.jp/offer-b",
                "affiliate_url": "https://hb.afl.rakuten.co.jp/offer-b",
                "merchant_url": "https://item.rakuten.co.jp/shop/b/",
            },
        ],
        "research_issues": [
            {
                "issue_id": "I-overdue",
                "product_id": "P-A",
                "status": "OPEN",
                "next_check_on": "2026-09-14",
                "target_url": "https://maker.example/spec",
                "unknown_reason": {"owner": "暮らしのしるべ編集部"},
            },
            {
                "issue_id": "I-due-today",
                "product_id": "P-A",
                "status": "RESEARCHING",
                "next_check_on": "2026-09-15",
                "target_url": "https://maker.example/manual",
                "unknown_reason": {"owner": "暮らしのしるべ編集部"},
            },
            {
                "issue_id": "I-resolved",
                "product_id": "P-B",
                "status": "RESOLVED",
                "next_check_on": "2026-09-01",
                "target_url": "https://maker.example/old",
                "unknown_reason": {"owner": "暮らしのしるべ編集部"},
            },
            {
                "issue_id": "I-no-owner",
                "product_id": "P-B",
                "status": "OPEN",
                "next_check_on": "2026-09-11",
                "target_url": "https://maker.example/spec",
                "unknown_reason": None,
            },
        ],
    }


def test_report_lists_overdue_unsettled_stale_and_expired_items():
    from raos.application.editorial.purchase_maintenance import maintenance_report

    report = maintenance_report(synthetic(), as_of=AS_OF, spec_max_age_days=10)
    assert report["as_of"] == "2026-09-15"
    assert [
        (r["issue_id"], r["next_check_on"], r["owner"])
        for r in report["overdue_research_issues"]
    ] == [
        ("I-no-owner", "2026-09-11", None),
        ("I-overdue", "2026-09-14", "暮らしのしるべ編集部"),
    ]
    assert (
        report["overdue_research_issues"][1]["target_url"]
        == "https://maker.example/spec"
    )
    assert [
        (r["product_id"], r["source"], r["name"], r["state"])
        for r in report["unsettled_facts"]
    ] == [
        ("P-A", "facts", "開扉時の寸法", "UNKNOWN"),
        ("P-A", "guide_facts", "door", "CONFLICT"),
    ]
    stale = report["stale_spec_facts"]
    assert stale["interval_undecided"] is False
    assert stale["checked_before"] == "2026-09-05"
    assert [(r["product_id"], r["name"]) for r in stale["items"]] == [
        ("P-A", "容量"),
        ("P-A", "door"),
    ]
    expired = report["expired_offers"]
    assert expired["offer_ids"] == ["O-expired"]
    assert expired["refetch_mechanism"] == "OWNER_DECISION_PENDING"
    assert expired["fetched"] is False
    assert report["unreadable_dates"] == [
        {
            "kind": "facts",
            "id": "P-B",
            "name": "重量",
            "field": "checked_at",
            "value": "not-a-date",
        }
    ]
    assert report["dimension_mismatches"] == []
    assert report["counts"] == {
        "overdue_research_issues": 2,
        "unsettled_facts": 2,
        "stale_spec_facts": 2,
        "expired_offers": 1,
        "target_urls": 6,
        "dimension_mismatches": 0,
        "unreadable_dates": 1,
    }


def test_stale_specs_stay_undecided_without_an_interval():
    from raos.application.editorial.purchase_maintenance import maintenance_report

    stale = maintenance_report(synthetic(), as_of=AS_OF, spec_max_age_days=None)[
        "stale_spec_facts"
    ]
    assert stale == {
        "spec_max_age_days": None,
        "interval_undecided": True,
        "checked_before": None,
        "items": [],
    }
    with pytest.raises(ValueError, match="MAINTENANCE_SPEC_MAX_AGE_INVALID"):
        maintenance_report(synthetic(), as_of=AS_OF, spec_max_age_days=-1)


def test_target_urls_are_sources_only_and_never_checked():
    from raos.application.editorial.purchase_maintenance import maintenance_report

    rows = maintenance_report(synthetic(), as_of=AS_OF, spec_max_age_days=None)[
        "target_urls"
    ]
    assert [r["url"] for r in rows] == [
        "https://maker.example/manual",
        "https://maker.example/old",
        "https://maker.example/spec",
        "https://shop.example/a",
        "https://shop.example/b",
        "https://shop.example/terms",
    ]
    assert {r["reachability"] for r in rows} == {"NOT_CHECKED"}
    spec = next(r for r in rows if r["url"] == "https://maker.example/spec")
    assert spec["referenced_by"] == ["research:I-no-owner", "research:I-overdue"]
    terms = next(r for r in rows if r["url"] == "https://shop.example/terms")
    assert terms["referenced_by"] == ["offer:O-expired"]
    assert not any("rakuten" in r["url"] for r in rows)


def test_tracked_catalog_report_is_deterministic_read_only_and_uses_dimension_checker(
    monkeypatch, tmp_path
):
    from raos.application.editorial.purchase_maintenance import maintenance_report

    catalog = json.loads(CATALOG_PATH.read_text())
    before = deepcopy(catalog)

    class NoNetwork(socket.socket):
        def __init__(self, *args, **kwargs):
            raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", NoNetwork)
    monkeypatch.chdir(tmp_path)
    report = maintenance_report(catalog, as_of=AS_OF, spec_max_age_days=90)
    assert list(tmp_path.iterdir()) == []
    assert catalog == before
    shuffled = deepcopy(catalog)
    for key in ("products", "offers", "research_issues"):
        shuffled[key].reverse()
    assert maintenance_report(shuffled, as_of=AS_OF, spec_max_age_days=90) == report
    assert json.dumps(report, ensure_ascii=False, sort_keys=True) == json.dumps(
        maintenance_report(catalog, as_of=AS_OF, spec_max_age_days=90),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert report["dimension_mismatches"] == []
    sizes = {
        key: len(report[key])
        for key in report["counts"]
        if isinstance(report[key], list)
    }
    sizes["stale_spec_facts"] = len(report["stale_spec_facts"]["items"])
    sizes["expired_offers"] = len(report["expired_offers"]["offer_ids"])
    assert report["counts"] == sizes
    assert all(r["url"].startswith("https://") for r in report["target_urls"])
    affiliate = {o.get("affiliate_url") for o in catalog["offers"]} - {None}
    assert not affiliate & {r["url"] for r in report["target_urls"]}
    assert all(
        r["status"] != "RESOLVED" and r["next_check_on"] < "2026-09-15"
        for r in report["overdue_research_issues"]
    )
    product = next(
        p for p in catalog["products"] if p["product_id"] == "PRD-PANASONIC-NP-TMLK1"
    )
    product["installation"]["width_mm"] = 311
    rows = maintenance_report(catalog, as_of=AS_OF, spec_max_age_days=None)[
        "dimension_mismatches"
    ]
    assert {(r["product_id"], r["group"], r["code"]) for r in rows} == {
        ("PRD-PANASONIC-NP-TMLK1", "dimensions", "PURCHASE_DIMENSION_SOURCE_MISMATCH")
    }


def test_cli_prints_the_report_without_writing_and_is_not_a_build_owner(tmp_path):
    before = CATALOG_PATH.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--as-of",
            "2026-09-15",
            "--spec-max-age-days",
            "90",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["as_of"] == "2026-09-15"
    assert report["stale_spec_facts"]["spec_max_age_days"] == 90
    assert list(tmp_path.iterdir()) == []
    assert CATALOG_PATH.read_bytes() == before
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "--as-of", "15/09/2026"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert bad.returncode != 0
    for manifest in (ROOT / "changes/build").glob("*.json"):
        text = manifest.read_text()
        assert "purchase_maintenance" not in text, manifest
        assert "report_reader_purchase_support_maintenance" not in text, manifest
