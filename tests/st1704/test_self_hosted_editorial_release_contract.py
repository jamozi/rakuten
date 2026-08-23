"""Integration-bound release and manifest checks for the ST-1704 pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile
import io

from scripts import build_st1704_self_hosted_editorial_manifest as manifest_builder
from scripts import build_st1704_self_hosted_theme as theme_builder


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"


def _load(relative: str) -> dict[str, object]:
    value = json.loads((SLICE / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_runtime_manifest_is_exact_and_keeps_st1703_as_predecessor() -> None:
    path = SLICE / "runtime-manifest.v1.json"
    assert path.read_bytes() == manifest_builder.build_manifest()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
    assert manifest["story_id"] == "ST-1704"
    assert manifest["slice_id"] == "SELF_HOSTED_EDITORIAL_PILOT_V1"
    assert manifest["external_action_authority"] == "NONE"
    assert manifest["publication_authority"] == "NONE"
    assert manifest["article_ids"] == list(manifest_builder.ARTICLE_IDS)

    predecessor = ROOT / manifest["predecessor"]["path"]
    assert (
        manifest["predecessor"]["sha256"]
        == hashlib.sha256(predecessor.read_bytes()).hexdigest()
    )
    records = manifest["paths"]
    assert [record["path"] for record in records] == list(
        manifest_builder.REQUIRED_RUNTIME_PATHS
    )
    for record in records:
        payload = (ROOT / record["path"]).read_bytes()
        assert record["bytes"] == len(payload)
        assert record["sha256"] == hashlib.sha256(payload).hexdigest()


def test_theme_package_is_deterministic_closed_and_has_no_javascript() -> None:
    first = theme_builder.build_package()
    second = theme_builder.build_package()
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first), "r") as archive:
        assert archive.namelist() == [
            f"kurashinoshirube-child/{relative}"
            for relative in theme_builder.SOURCE_FILES
        ]
        assert not any(
            name.endswith((".js", ".php~", ".zip")) for name in archive.namelist()
        )


def test_publication_plan_is_closed_and_in_the_required_order() -> None:
    plan = _load("operations/publication-plan.v1.json")
    assert plan["publication_authority"] == "NONE"
    rows = plan["articles"]
    assert isinstance(rows, list)
    assert [row["article_id"] for row in rows] == list(manifest_builder.ARTICLE_IDS)
    assert [row["day_number"] for row in rows] == [1, 4, 7, 10, 13]
    assert [row["action"] for row in rows] == [
        "UPDATE_EXISTING",
        "PUBLISH_NEW",
        "PUBLISH_NEW",
        "PUBLISH_NEW",
        "PUBLISH_NEW",
    ]
    assert all(row["immutable_snapshot_sha256"] is None for row in rows)
    assert all(row["public_verification"] == "NOT_EXECUTED" for row in rows)


def test_measurement_ledger_adds_no_tracking_and_cannot_rank_products() -> None:
    ledger = _load("operations/measurement-ledger.v1.json")
    assert ledger["analytics_transmission_added"] is False
    assert ledger["publication_authority"] == "NONE"
    assert ledger["finance_signal_policy"] == (
        "OBSERVATION_ONLY_NEVER_RECOMMENDATION_ORDER"
    )
    rows = ledger["articles"]
    assert isinstance(rows, list) and len(rows) == 5
    assert [row["article_id"] for row in rows] == list(manifest_builder.ARTICLE_IDS)
    for row in rows:
        assert row["record_at_day"] == 14
        assert row["status"] == "NOT_RECORDED"
        for field in (
            "broken_link_count",
            "confirmed_reward_jpy",
            "external_rakuten_clicks",
            "organic_sessions",
            "outcome_count",
            "public_action_at",
            "search_impressions",
        ):
            assert row[field] is None


def test_runbook_preserves_all_external_human_gates_and_reversible_rollback() -> None:
    runbook = (SLICE / "OPERATIONS_RUNBOOK.md").read_text(encoding="utf-8")
    for required in (
        "bounded Rakuten Item Search retrieval",
        "RAOS_ST1704_OFFICIAL_SOURCE_CAPTURE_V1",
        "claim_statement_sha256",
        "exact_utf8_fragments",
        "<source-ref>.body",
        "st1704_official_source_capture.py capture-article",
        "never treats a partial",
        ".affiliate-item-search-response.v1.json",
        "RAOS_ST1704_OWNER_IMMUTABLE_REVIEW_DRAFT_REQUEST_V1",
        "immutable-review-draft-requests/<article_id>.<packet_sha256>.<request_sha256>.request.v1.json",
        "Recovery loads the sole `INTENT`-bound artifact without",
        "Public verification similarly loads only the sole `COMMITTED`-bound",
        "verification deliberately does not run a fresh prepare",
        "shared C300 provider files have since been refreshed",
        "they are not journal fields",
        "A human WordPress administrator installs and activates Yoast 28.3",
        "Record the immutable snapshot hash",
        "password reauthentication",
        "暮らしの道具",
        "The repository CLI has no publish or schedule command",
        "deactivate Yoast",
        "child-theme 1.0.2",
        "restore the affected WordPress post revision",
        "Do not delete database rows",
    ):
        assert required in runbook


def test_competitor_research_is_pattern_only_and_never_product_evidence() -> None:
    research = (SLICE / "EDITORIAL_RESEARCH_NOTES.md").read_text(encoding="utf-8")
    for required in ("ROOMIE", "Rentio PRESS", "mybest", "Wirecutter"):
        assert required in research
    for boundary in (
        "They are not product evidence",
        "does not affect selection or order",
        "no competitor wording, test result, review text, product image, or evaluation",
        "no universal winner",
        "no claim that an editor used, tested, owned, or personally experienced",
    ):
        assert boundary in research
