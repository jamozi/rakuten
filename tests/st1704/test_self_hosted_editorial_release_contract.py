"""Integration-bound release and manifest checks for the ST-1704 pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile
import io

from scripts import build_st1704_self_hosted_editorial_manifest as manifest_builder
from scripts import build_st1704_self_hosted_theme as theme_builder
from raos.domain.editorial.self_hosted_editorial_pilot import (
    CarryOnSingleUrlReconciliationEvidence,
    PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256,
    PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256,
    PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256,
    PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256,
    PILOT_PUBLIC_VERIFICATION_CHECKS,
    PublicVerification,
)


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
SINGLE_URL_SLICE = ROOT / "changes/st-1704/carry-on-single-url-evidence-loop-v1"


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

    assert manifest["predecessor"] == {
        "owner_id": "build_st1703_self_hosted_runtime_manifest",
        "version": "2",
    }
    records = manifest["paths"]
    assert [record["path"] for record in records] == list(
        manifest_builder.REQUIRED_RUNTIME_PATHS
    )
    assert {
        f"{manifest_builder.SINGLE_URL_SLICE}/DESIGN_HANDOFF_V1.yaml",
        f"{manifest_builder.SINGLE_URL_SLICE}/PREFLIGHT.md",
        f"{manifest_builder.SINGLE_URL_SLICE}/README.md",
        (
            f"{manifest_builder.SINGLE_URL_SLICE}/contracts/"
            "carry-on-single-url-evidence-loop.v1.json"
        ),
    } <= {record["path"] for record in records}
    for record in records:
        payload = (ROOT / record["path"]).read_bytes()
        assert record["bytes"] == len(payload)
        assert record["sha256"] == hashlib.sha256(payload).hexdigest()


def test_theme_package_is_deterministic_closed_and_has_only_measurement_javascript() -> None:
    assert theme_builder.THEME_VERSION == "1.4.0"
    assert theme_builder.OUTPUT_PATH.name == "kurashinoshirube-child-1.4.0.zip"
    assert "assets/theme.js" not in theme_builder.SOURCE_FILES
    first = theme_builder.build_package()
    second = theme_builder.build_package()
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first), "r") as archive:
        assert archive.namelist() == [
            f"kurashinoshirube-child/{relative}"
            for relative in theme_builder.SOURCE_FILES
        ]
        javascript = [name for name in archive.namelist() if name.endswith(".js")]
        assert javascript == ["kurashinoshirube-child/assets/measurement.js"]
        assert not any(
            name.endswith((".php~", ".zip")) for name in archive.namelist()
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
    assert [row["event"] for row in ledger["future_acceptance_event_spec"]] == [
        "affiliate_cta_activate",
        "product_card_reach",
        "comparison_table_view",
    ]
    assert all(
        row["status"] == "SEMANTIC_MARKUP_ONLY_NO_TRANSMISSION"
        for row in ledger["future_acceptance_event_spec"]
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
        "child-theme 1.4.0",
        "child-theme 1.1.1 package as the minimum containment floor",
        "do not roll back to 1.0.2",
        "temporary Review post Draft with no redirect",
        "restore the affected WordPress post revision",
        "Do not delete database rows",
    ):
        assert required in runbook


def test_carry_on_single_url_overlay_is_closed_and_matches_runtime_vocabulary() -> None:
    contract_path = (
        SINGLE_URL_SLICE / "contracts/carry-on-single-url-evidence-loop.v1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert set(contract) == {
        "article_id",
        "authority",
        "canonical_surface",
        "external_action_authority",
        "global_exclusions",
        "per_surface_sha256_fields",
        "production_evidence",
        "public_surface_hash_algorithm",
        "reconciliation_evidence",
        "reconciliation_command",
        "review_body_leak_guard",
        "review_route_detection",
        "review_surface",
        "review_surface_evidence_record",
        "rollback_floor",
        "schema",
        "slice_id",
        "source_request",
        "story_id",
        "verified_checks",
    }
    assert contract["schema"] == "RAOS_ST1704_CARRY_ON_SINGLE_URL_EVIDENCE_LOOP_V1"
    assert contract["story_id"] == "ST-1704"
    assert contract["article_id"] == "st1703-first-suitcase-comparison"
    assert contract["external_action_authority"] == "NONE"
    assert contract["production_evidence"] == "NOT_CLAIMED"
    assert contract["source_request"] == (
        "SOLE_TERMINAL_RECOVERY_ATTEMPTED_BOUND_IMMUTABLE_ARTIFACT"
    )
    assert contract["verified_checks"] == list(PILOT_PUBLIC_VERIFICATION_CHECKS)

    canonical = contract["canonical_surface"]
    assert canonical == {
        "page_sitemap_count": 0,
        "path": "/carry-on-suitcase-comparison/",
        "public_post_id": 19,
        "post_sitemap_count": 1,
        "url": "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
    }
    review = contract["review_surface"]
    assert review == {
        "at003_authenticated_draft_count": 1,
        "caller_selected_url_allowed": False,
        "derivation": ("PILOT_ORIGIN_PLUS_REVIEW_DRAFT_SLUG_OF_BOUND_SNAPSHOT"),
        "disposition": "DRAFT",
        "location_header": "ABSENT",
        "promoted_article_authenticated_draft_count": 0,
        "public_rest_projection_count": 0,
        "redirect_authority": "NONE",
        "retained_post_id": 26,
        "url_http_status": 404,
    }
    assert contract["reconciliation_command"] == {
        "allowed_article_id": "st1703-first-suitcase-comparison",
        "command": "verify-carry-on-single-url",
        "expected_review_draft_post_id": 26,
        "formal_gate_eligible": False,
        "journal_mutation": False,
        "journal_state": "RECOVERY_ATTEMPTED",
        "packet_sha256": PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256,
        "payload_sha256": PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256,
        "production_evidence": False,
        "publication_authority": False,
        "reconciliation_status": "PENDING_HUMAN_EXCEPTION",
        "request_artifact_sha256": PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256,
        "request_sha256": PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256,
        "target_public_post_id": 19,
        "verify_public_journal_requirement": "COMMITTED_UNCHANGED",
    }
    assert contract["reconciliation_evidence"] == {
        "adapter_return_type": "CarryOnSingleUrlReconciliationEvidence",
        "formal_gate_eligible": False,
        "production_evidence": False,
        "public_surface_verified": False,
        "publication_authority": False,
        "reconciliation_status": "PENDING_HUMAN_EXCEPTION",
        "strict_public_checks_passed": True,
    }
    assert contract["review_body_leak_guard"] == {
        "article_fragment_scope": (
            "ENTITY_DECODED_VISIBLE_TEXT_EXCLUDING_HTML_ATTRIBUTES"
        ),
        "fragment_sources": [
            "TITLE",
            "EXCERPT",
            "CONTENT",
            "SNAPSHOT_JSON_MEANINGFUL_WINDOWS_AND_TOKENS",
            "SNAPSHOT_PAYLOAD_SHA256",
            "SNAPSHOT_PACKET_SHA256",
            "SNAPSHOT_VISIBLE_CONTENT_SHA256",
        ],
        "high_signal_cta_fragments": [
            "楽天市場で写真・価格・在庫",
            "楽天市場で写真・価格を見る",
            "楽天市場で価格・在庫を見る",
            "楽天市場で価格を見る",
            "楽天市場で在庫を見る",
        ],
        "html_entity_decode_passes": 2,
        "meaningful_fragment_characters": 24,
        "meaningful_fragment_minimum_alphanumeric": 16,
        "meaningful_token_characters": 16,
        "normalization": ("HTML_UNESCAPE_THEN_NFKC_CASEFOLD_AND_WHITESPACE_COLLAPSE"),
        "snapshot_canonical_url_handling": (
            "EXCLUDE_ONLY_EXPECTED_CLEAN_CANONICAL_URL_WINDOWS_AND_TOKENS"
        ),
    }
    assert contract["review_route_detection"] == {
        "decoded_marker": "raos-review-",
        "decoded_url_components": ["AUTHORITY", "PATH", "QUERY", "FRAGMENT"],
        "double_encoded_or_remaining_percent": "FAIL_CLOSED",
        "malformed_percent_escape": "FAIL_CLOSED",
        "percent_decode": "ONE_STRICT_UTF8_PASS",
        "surfaces": ["HOME_HREF", "POST_SITEMAP_URL", "PAGE_SITEMAP_URL"],
    }
    surface_fields = contract["per_surface_sha256_fields"]
    assert surface_fields == [
        "article_html_sha256",
        "category_sha256",
        "core_sitemap_sha256",
        "homepage_html_sha256",
        "homepage_targets_sha256",
        "page_sitemap_sha256",
        "post_sitemap_sha256",
        "related_target_sha256",
        "review_draft_rest_evidence_sha256",
        "review_public_rest_evidence_sha256",
        "review_url_html_evidence_sha256",
        "robots_sha256",
        "sitemap_index_sha256",
    ]
    assert all(
        field in PublicVerification.__dataclass_fields__ for field in surface_fields
    )
    assert all(
        field in CarryOnSingleUrlReconciliationEvidence.__dataclass_fields__
        for field in surface_fields
    )
    assert contract["review_surface_evidence_record"] == {
        "digest_fields": [
            "body_sha256",
            "content_type",
            "http_status",
            "kind",
            "location_header",
            "method",
            "path",
            "schema",
            "x_wp_total",
            "x_wp_total_pages",
        ],
        "digest_operation": "SHA256_OF_CANONICAL_JSON",
        "schema": "RAOS_ST1704_REVIEW_SURFACE_EVIDENCE_V1",
    }

    handoff = (SINGLE_URL_SLICE / "DESIGN_HANDOFF_V1.yaml").read_text(encoding="utf-8")
    preflight = (SINGLE_URL_SLICE / "PREFLIGHT.md").read_text(encoding="utf-8")
    readme = (SINGLE_URL_SLICE / "README.md").read_text(encoding="utf-8")
    worklog = (SLICE / "REVENUE_UNBLOCK_WORKLOG.md").read_text(encoding="utf-8")
    for required in (
        "approved_scope: CARRY_ON_SINGLE_URL_EVIDENCE_LOOP_V1",
        "review_url_anonymous_status: 404",
        "review_url_location_header: ABSENT",
        "expected_review_draft_post_id: 26",
        "formal_gate_eligible: false",
        "reconciliation_adapter_return_type: CarryOnSingleUrlReconciliationEvidence",
        "reconciliation_public_surface_verified: false",
        "reconciliation_strict_public_checks_passed: true",
        "redirect_authority: NONE",
        "live_verify_carry_on_single_url: NOT_EXECUTED",
        "live_verify_public: NOT_EXECUTED",
    ):
        assert required in handoff
    assert "No live or public response is committed" in preflight
    assert "one exact Draft + anonymous 404 +" in readme
    assert "no redirect" in readme
    for document in (preflight, readme, worklog):
        assert "CarryOnSingleUrlReconciliationEvidence" in document
        assert "public_surface_verified=false" in document
        assert "strict_public_checks_passed=true" in document
    for fixed_value in (
        PILOT_CARRY_ON_RECONCILIATION_PACKET_SHA256,
        PILOT_CARRY_ON_RECONCILIATION_REQUEST_SHA256,
        PILOT_CARRY_ON_RECONCILIATION_PAYLOAD_SHA256,
        PILOT_CARRY_ON_RECONCILIATION_ARTIFACT_SHA256,
        "review_draft_id=26",
        "target_public_post_id=19",
    ):
        assert fixed_value in worklog


def test_revenue_unblock_schedule_and_experiments_match_the_approved_limits() -> None:
    runbook = (SLICE / "OPERATIONS_RUNBOOK.md").read_text(encoding="utf-8")
    experiment = (SLICE / "REVENUE_EXPERIMENT_RUNBOOK.md").read_text(encoding="utf-8")
    runbook_flat = " ".join(runbook.split())
    experiment_flat = " ".join(experiment.split())
    for required in (
        "Day 1 | Suitcase: Review post 26 remains Draft; existing final post 19",
        "Day 4 | Portable power: post 28 moves from Draft",
        "Day 7 | Anker model comparison: post 29 moves from Draft",
        "Day 10 | Dishwasher: prepare and create one new Review Draft",
        "including one exact THANKO variant, no more than 24 hours",
        "Day 13 | Robot vacuum: post 30 moves from Draft",
        "360/768/1440 CSS-pixel",
        "200%-zoom, keyboard-only, and JavaScript-disabled matrix",
        'rel="sponsored nofollow"',
        "The article's measurement `T0` begins only",
    ):
        assert required in runbook_flat

    for required in (
        "end of the following month",
        "28 days and 200 impressions per compared variant",
        "organic clicks or CTR improves at least 20%",
        "average position worsens by no more than 2",
        "500 impressions, and 20 clicks",
        "this runbook imposes no unapproved percentage threshold",
        "Add at most two query-led comparison/difference/model articles",
        "Rakuten confirmed outcomes have been reconciled at least twice",
    ):
        assert required in experiment_flat
    for invented in (
        "affiliate click rate improves at least 20%",
        "cluster organic clicks rise at least 25%",
        "cannibalization stays at or below 15%",
        "over 56–90 days",
        "two confirmed provider cycles",
    ):
        assert invented not in experiment_flat


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
