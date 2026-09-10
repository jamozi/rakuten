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
