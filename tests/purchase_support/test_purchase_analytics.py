"""Local behavior checks; no Google property or network access."""

from dataclasses import replace
from pathlib import Path
import runpy
import shutil
import subprocess

import pytest

from raos.application.analytics.google_live_projection import ga4_purchase_document_v2
from raos.domain.analytics.google_live import (
    GA4_PURCHASE_DIMENSIONS_V2,
    GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2,
    Ga4LiveQuery,
    GoogleProviderFailure,
    canonical_json_bytes,
    sha256_hex,
)

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


@pytest.mark.parametrize(
    "harness", ["purchase_analytics_harness.mjs", "purchase_consent_gate_harness.mjs"]
)
def test_purchase_analytics_browser_fixtures(harness):
    subprocess.run(
        [
            "node",
            str(Path(__file__).with_name(harness)),
            str(THEME / "assets/analytics-consent-gate.js"),
        ],
        cwd=ROOT,
        check=True,
    )


def _purchase_batches():
    legacy = runpy.run_path(
        str(ROOT / "tests/google_live/test_google_live_projection.py")
    )["_ga4_batch"]()
    values = dict(legacy.rows[0].dimensions)
    values.update(
        {
            "customEvent:seller_id": "official",
            "customEvent:snapshot_id": "ps-" + "a" * 32,
            "eventName": "offer_click",
            "customEvent:placement": "top_summary",
        }
    )

    def make(names, event):
        dims = tuple(
            (name, event if name == "eventName" else values[name]) for name in names
        )
        row = replace(
            legacy.rows[0],
            dimensions=dims,
            grain_key_sha256=sha256_hex(
                canonical_json_bytes(
                    {
                        "date": legacy.rows[0].metric_date.isoformat(),
                        "dimensions": dict(dims),
                    }
                )
            ),
        )
        return replace(legacy, dimensions=names, rows=(row,))

    return (
        legacy,
        make(GA4_PURCHASE_DIMENSIONS_V2, "offer_click"),
        make(GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2, "page_view"),
    )


def test_purchase_analytics_v2_preserves_seller_and_separate_denominator():
    legacy, batch, views = _purchase_batches()
    with pytest.raises(GoogleProviderFailure):
        ga4_purchase_document_v2(legacy, page_views=views)
    assert (
        len(
            Ga4LiveQuery(
                batch.site_id,
                batch.property_id,
                batch.date_from,
                batch.date_to,
                dimensions=batch.dimensions,
            ).dimensions
        )
        == 9
    )
    document = ga4_purchase_document_v2(batch, page_views=views)
    assert document["schema_version"] == 2
    assert {"name": "seller_id", "value": "official"} in document["rows"][0][
        "dimensions"
    ]
    assert document["rows"][0]["metrics"] == [{"name": "eventCount", "value": "3"}]
    assert {"name": "sessions", "value": "2"} in document["page_view_rows"][0][
        "metrics"
    ]
    assert batch.configuration.snapshot_sha256 == legacy.configuration.snapshot_sha256
    assert document["purchase_and_reward"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "key,value",
    [
        (key, "")
        for key in (
            "article_id",
            "product_id",
            "seller_id",
            "offer_id",
            "cta_id",
            "placement",
            "snapshot_id",
        )
    ]
    + [("seller_id", "UNKNOWN"), ("placement", "sidebar")],
)
def test_purchase_analytics_v2_rejects_missing_identity_or_placement(key, value):
    _, batch, views = _purchase_batches()
    dims = tuple(
        (name, value if name == "customEvent:" + key else old)
        for name, old in batch.rows[0].dimensions
    )
    row = replace(
        batch.rows[0],
        dimensions=dims,
        grain_key_sha256=sha256_hex(
            canonical_json_bytes(
                {
                    "date": batch.rows[0].metric_date.isoformat(),
                    "dimensions": dict(dims),
                }
            )
        ),
    )
    with pytest.raises(GoogleProviderFailure):
        ga4_purchase_document_v2(replace(batch, rows=(row,)), page_views=views)


def test_purchase_analytics_cli_plan_and_two_query_import(monkeypatch, capsys):
    ns = runpy.run_path(str(ROOT / "scripts/raos_editorial_economics_v3.py"))
    main = ns["main"]
    monkeypatch.setitem(
        main.__globals__,
        "compose_live_google_analytics_import",
        lambda **kwargs: pytest.fail("plan accessed provider"),
    )
    argv = [
        "import-ga4",
        "--profile",
        "purchase-v2",
        "--date-from",
        "2026-08-29",
        "--date-to",
        "2026-08-29",
        "--plan",
    ]
    assert main(argv) == 0
    assert '"live_verification": "NOT_EXECUTED"' in capsys.readouterr().out
    _, batch, views = _purchase_batches()
    calls, outputs = [], []

    class Service:
        def import_ga4_with_batch(self, **kwargs):
            calls.append(kwargs)
            return (batch if len(calls) == 1 else views), None

    function = ns["_import_ga4_profile"]
    monkeypatch.setitem(
        function.__globals__,
        "write_private_json",
        lambda *args: outputs.append(args[-1]),
    )
    args = ns["_parser"]().parse_args(
        argv
        + [
            "--ga4-output",
            "ga4/purchase-v2.json",
            "--ga4-views-job-id",
            "0198f8c4-1000-7000-8000-000000000015",
        ]
    )
    function(
        Service(),
        args,
        batch.site_id,
        batch.site_id,
        batch.retrieved_at,
        Path("unused"),
    )
    assert [call["dimensions"] for call in calls] == [
        GA4_PURCHASE_DIMENSIONS_V2,
        GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2,
    ]
    assert outputs[0]["page_view_rows"][0]["metrics"][1] == {
        "name": "sessions",
        "value": "2",
    }


def test_purchase_analytics_php_owner_and_default_off():
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP CLI is unavailable; container validation required")
    harness = Path(__file__).with_name("purchase_analytics_harness.php")
    for mode in ("off", "owner", "on", "tampered"):
        subprocess.run(
            [
                php,
                "-r",
                harness.read_text().removeprefix("<?php"),
                "--",
                str(THEME / "inc/purchase-analytics.php"),
                mode,
            ],
            check=True,
        )


def _analytics_row_values(row, updates):
    dimensions = tuple(
        (name, updates.get(name, value)) for name, value in row.dimensions
    )
    return replace(
        row,
        dimensions=dimensions,
        grain_key_sha256=sha256_hex(
            canonical_json_bytes(
                {"date": row.metric_date.isoformat(), "dimensions": dict(dimensions)}
            )
        ),
    )


def test_purchase_scope_quarantines_legacy_and_reports_unknown_without_zero_metrics():
    _, clicks, views = _purchase_batches()
    legacy_click = _analytics_row_values(
        clicks.rows[0],
        {
            "customEvent:snapshot_id": "old-snapshot-1",
            "customEvent:placement": "old-slot",
        },
    )
    legacy_view = _analytics_row_values(
        views.rows[0], {"customEvent:snapshot_id": "old-snapshot-1"}
    )
    untagged_view = _analytics_row_values(
        views.rows[0],
        {"customEvent:snapshot_id": "(not set)", "customEvent:article_id": "(not set)"},
    )
    document = ga4_purchase_document_v2(
        replace(clicks, rows=(*clicks.rows, legacy_click), provider_row_count=2),
        page_views=replace(
            views, rows=(*views.rows, legacy_view, untagged_view), provider_row_count=3
        ),
    )
    assert len(document["rows"]) == len(document["page_view_rows"]) == 1
    assert document["excluded_row_counts"] == {
        "offer_click": {"NON_PURCHASE_SNAPSHOT": 1},
        "page_view": {"NON_PURCHASE_SNAPSHOT": 1, "UNATTRIBUTED_SCOPE": 1},
    }
    assert document["scope_status"] == "PARTIAL_SCOPE_UNKNOWN"
    assert document["rows"][0]["metrics"] == [{"name": "eventCount", "value": "3"}]
    only_old = ga4_purchase_document_v2(
        replace(clicks, rows=(legacy_click,)),
        page_views=replace(views, rows=(legacy_view,)),
    )
    assert only_old["scope_status"] == "NO_PURCHASE_OBSERVATIONS"
    assert only_old["rows"] == only_old["page_view_rows"] == []


@pytest.mark.parametrize(
    "snapshot", ["ps-broken", "ps-" + "g" * 32, "", "UNKNOWN", "(not set)"]
)
@pytest.mark.parametrize("report", ["click", "view"])
def test_purchase_scope_ambiguous_identified_rows_fail_closed(snapshot, report):
    _, clicks, views = _purchase_batches()
    source = clicks if report == "click" else views
    row = _analytics_row_values(source.rows[0], {"customEvent:snapshot_id": snapshot})
    changed = replace(source, rows=(row,))
    with pytest.raises(GoogleProviderFailure):
        ga4_purchase_document_v2(
            changed if report == "click" else clicks,
            page_views=changed if report == "view" else views,
        )


def test_purchase_scope_keeps_distinct_purchase_snapshots_without_mapping_old_placements():
    _, clicks, views = _purchase_batches()
    older = _analytics_row_values(
        clicks.rows[0], {"customEvent:snapshot_id": "ps-" + "b" * 32}
    )
    result = ga4_purchase_document_v2(
        replace(clicks, rows=(*clicks.rows, older), provider_row_count=2),
        page_views=views,
    )
    assert len(result["rows"]) == 2
    assert result["scope_status"] == "OBSERVED_ROWS_ONLY"
    bad = _analytics_row_values(older, {"customEvent:placement": "legacy-placement"})
    with pytest.raises(GoogleProviderFailure):
        ga4_purchase_document_v2(replace(clicks, rows=(bad,)), page_views=views)


@pytest.mark.parametrize("report", ["click", "view"])
def test_purchase_scope_only_untagged_rows_stay_unknown(report):
    _, clicks, views = _purchase_batches()
    source = clicks if report == "click" else views
    unknown = _analytics_row_values(
        source.rows[0],
        {
            name: "(not set)"
            for name, _ in source.rows[0].dimensions
            if name.startswith("customEvent:")
        },
    )
    clicks = replace(clicks, rows=(), provider_row_count=0)
    views = replace(views, rows=(), provider_row_count=0)
    if report == "click":
        clicks = replace(clicks, rows=(unknown,), provider_row_count=1)
    else:
        views = replace(views, rows=(unknown,), provider_row_count=1)
    result = ga4_purchase_document_v2(clicks, page_views=views)
    assert result["scope_status"] == "PARTIAL_SCOPE_UNKNOWN"
    assert result["rows"] == result["page_view_rows"] == []
    assert result["excluded_row_counts"][
        "offer_click" if report == "click" else "page_view"
    ] == {"UNATTRIBUTED_SCOPE": 1}


def test_purchase_scope_page_view_requires_article_when_snapshot_is_scoped():
    _, clicks, views = _purchase_batches()
    missing = _analytics_row_values(
        views.rows[0], {"customEvent:article_id": "(not set)"}
    )
    with pytest.raises(GoogleProviderFailure):
        ga4_purchase_document_v2(clicks, page_views=replace(views, rows=(missing,)))
