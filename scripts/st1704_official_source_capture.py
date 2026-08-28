#!/usr/bin/env python3
"""Manifest-bound official-source capture CLI for the ST-1704 pilot."""

from __future__ import annotations

import argparse
from collections.abc import Container
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import types
from typing import Callable, Final, NoReturn, Protocol, TextIO, cast


SOURCE_CLI_PATH: Final = Path(os.path.abspath(__file__))
REPOSITORY_ROOT: Final = SOURCE_CLI_PATH.parent.parent
OWNER_PYTHON: Final = (REPOSITORY_ROOT / ".venv/bin/python").as_posix()
MANIFEST_RELATIVE: Final = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
)
PREDECESSOR_RELATIVE: Final = (
    "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
)
BOOTSTRAP_RELATIVE: Final = "scripts/st1704_official_source_capture.py"
MAX_MANIFEST_BYTES: Final = 256 * 1024
MAX_RUNTIME_BYTES: Final = 4 * 1024 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
SOURCE_REFS: Final = (
    "SRC-ACE-CRESTA-06316",
    "SRC-ACE-DIFFERENCE-05721",
    "SRC-ACE-MAXPASS4-01471",
    "SRC-ANA-CARRY-ON-BAGGAGE",
    "SRC-ANKER-SOLIX-C300",
    "SRC-JACKERY-500-NEW",
    "SRC-BLUETTI-AC70",
    "SRC-ECOFLOW-DELTA3-CLASSIC",
    "SRC-PANASONIC-NP-TMLK1",
    "SRC-THANKO-RAKUA-MINI-COLOR",
    "SRC-SIROCA-SS-MA251",
    "SRC-PANASONIC-NP-TSP1",
    "SRC-ANKER-SOLIX-C800-PLUS",
    "SRC-ANKER-SOLIX-C1000",
    "SRC-ANKER-SOLIX-C1000-GEN2",
    "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
    "SRC-SWITCHBOT-K11-PRO",
    "SRC-SWITCHBOT-K10-PRO-COMBO",
    "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
    "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
    "SRC-CAA-STEALTH-MARKETING-QA",
    "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
)

_BASE_RUNTIME_PATHS: Final[tuple[str, ...]] = (
    "changes/st-1704/carry-on-single-url-evidence-loop-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/carry-on-single-url-evidence-loop-v1/PREFLIGHT.md",
    "changes/st-1704/carry-on-single-url-evidence-loop-v1/README.md",
    "changes/st-1704/carry-on-single-url-evidence-loop-v1/contracts/carry-on-single-url-evidence-loop.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/self-hosted-editorial-pilot-v1/EDITORIAL_RESEARCH_NOTES.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/Makefile",
    "changes/st-1704/self-hosted-editorial-pilot-v1/OPERATIONS_RUNBOOK.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/PREFLIGHT.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/README.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/REVENUE_EXPERIMENT_RUNBOOK.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/REVENUE_UNBLOCK_WORKLOG.md",
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/media/product-media-registry.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-locator-contract.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/article-portable-power-guide.png",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/article-suitcase-guide.webp",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/brand-mark.svg",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-hero.webp",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/parts/footer.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/parts/header.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/raos-assets.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/style.css",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/front-page.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/single.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme-contract.v1.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/theme.json",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/yoast-seo-28.3.lock.json",
    "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json",
    "python/raos/adapters/self_hosted_editorial_pilot_https.py",
    "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    "python/raos/adapters/self_hosted_editorial_source_capture.py",
    "python/raos/adapters/self_hosted_wordpress_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_https.py",
    "python/raos/adapters/self_hosted_wordpress_rest.py",
    "python/raos/adapters/wordpress_rest.py",
    "python/raos/application/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/editorial/content_ast.py",
    "python/raos/domain/editorial/market_learning_pilot.py",
    "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/editorial/self_hosted_wordpress.py",
    "python/raos/ports/self_hosted_editorial_pilot.py",
    "scripts/build_st1704_self_hosted_editorial_manifest.py",
    "scripts/build_st1704_self_hosted_theme.py",
    BOOTSTRAP_RELATIVE,
    "scripts/st1704_self_hosted_editorial_pilot.py",
)
GENERATED_RUNTIME_PATHS: Final[tuple[str, ...]] = (
    "python/raos/generated/contracts/__init__.py",
    "python/raos/generated/contracts/_internal.py",
    "python/raos/generated/contracts/actor_ref.py",
    "python/raos/generated/contracts/affiliate_click_input.py",
    "python/raos/generated/contracts/ai/__init__.py",
    "python/raos/generated/contracts/ai/article_draft/__init__.py",
    "python/raos/generated/contracts/ai/article_draft/v1/__init__.py",
    "python/raos/generated/contracts/ai/article_draft/v1/output.py",
    "python/raos/generated/contracts/ai/article_outline/__init__.py",
    "python/raos/generated/contracts/ai/article_outline/v1/__init__.py",
    "python/raos/generated/contracts/ai/article_outline/v1/output.py",
    "python/raos/generated/contracts/ai/claim_extraction/__init__.py",
    "python/raos/generated/contracts/ai/claim_extraction/v1/__init__.py",
    "python/raos/generated/contracts/ai/claim_extraction/v1/output.py",
    "python/raos/generated/contracts/ai/comparison_axis_suggestion/__init__.py",
    "python/raos/generated/contracts/ai/comparison_axis_suggestion/v1/__init__.py",
    "python/raos/generated/contracts/ai/comparison_axis_suggestion/v1/output.py",
    "python/raos/generated/contracts/ai/internal_link_suggestion/__init__.py",
    "python/raos/generated/contracts/ai/internal_link_suggestion/v1/__init__.py",
    "python/raos/generated/contracts/ai/internal_link_suggestion/v1/output.py",
    "python/raos/generated/contracts/ai/opportunity_assessment/__init__.py",
    "python/raos/generated/contracts/ai/opportunity_assessment/v1/__init__.py",
    "python/raos/generated/contracts/ai/opportunity_assessment/v1/output.py",
    "python/raos/generated/contracts/ai/policy_assist/__init__.py",
    "python/raos/generated/contracts/ai/policy_assist/v1/__init__.py",
    "python/raos/generated/contracts/ai/policy_assist/v1/output.py",
    "python/raos/generated/contracts/ai/quality_remediation/__init__.py",
    "python/raos/generated/contracts/ai/quality_remediation/v1/__init__.py",
    "python/raos/generated/contracts/ai/quality_remediation/v1/output.py",
    "python/raos/generated/contracts/ai/refresh_diff_summary/__init__.py",
    "python/raos/generated/contracts/ai/refresh_diff_summary/v1/__init__.py",
    "python/raos/generated/contracts/ai/refresh_diff_summary/v1/output.py",
    "python/raos/generated/contracts/ai/search_intent_classification/__init__.py",
    "python/raos/generated/contracts/ai/search_intent_classification/v1/__init__.py",
    "python/raos/generated/contracts/ai/search_intent_classification/v1/output.py",
    "python/raos/generated/contracts/ai/source_packet_gap_analysis/__init__.py",
    "python/raos/generated/contracts/ai/source_packet_gap_analysis/v1/__init__.py",
    "python/raos/generated/contracts/ai/source_packet_gap_analysis/v1/output.py",
    "python/raos/generated/contracts/ai/update_priority_explanation/__init__.py",
    "python/raos/generated/contracts/ai/update_priority_explanation/v1/__init__.py",
    "python/raos/generated/contracts/ai/update_priority_explanation/v1/output.py",
    "python/raos/generated/contracts/ai_assess_opportunity_v1.py",
    "python/raos/generated/contracts/ai_classify_search_intent_v1.py",
    "python/raos/generated/contracts/ai_evaluate_output_v1.py",
    "python/raos/generated/contracts/ai_extract_claims_v1.py",
    "python/raos/generated/contracts/ai_generate_article_draft_v1.py",
    "python/raos/generated/contracts/ai_generic_task_v1.py",
    "python/raos/generated/contracts/ai_job/__init__.py",
    "python/raos/generated/contracts/ai_job/v1.py",
    "python/raos/generated/contracts/ai_policy_assist_v1.py",
    "python/raos/generated/contracts/ai_task_contract/__init__.py",
    "python/raos/generated/contracts/ai_task_contract/v1.py",
    "python/raos/generated/contracts/ai_task_definition/__init__.py",
    "python/raos/generated/contracts/ai_task_definition/v1.py",
    "python/raos/generated/contracts/analytics_import_ga4_v1.py",
    "python/raos/generated/contracts/analytics_import_keyword_rank_csv_v1.py",
    "python/raos/generated/contracts/analytics_import_provider_data_v1.py",
    "python/raos/generated/contracts/analytics_import_search_console_v1.py",
    "python/raos/generated/contracts/analytics_rollup_daily_metrics_v1.py",
    "python/raos/generated/contracts/article_ast.py",
    "python/raos/generated/contracts/article_disclosure_context/__init__.py",
    "python/raos/generated/contracts/article_disclosure_context/v1.py",
    "python/raos/generated/contracts/article_draft_output.py",
    "python/raos/generated/contracts/article_methodology_binding/__init__.py",
    "python/raos/generated/contracts/article_methodology_binding/v1.py",
    "python/raos/generated/contracts/article_template_version/__init__.py",
    "python/raos/generated/contracts/article_template_version/v1.py",
    "python/raos/generated/contracts/article_type_version/__init__.py",
    "python/raos/generated/contracts/article_type_version/v1.py",
    "python/raos/generated/contracts/artifact_ref.py",
    "python/raos/generated/contracts/bullet_list.py",
    "python/raos/generated/contracts/callout.py",
    "python/raos/generated/contracts/catalog_group_product_candidates_v1.py",
    "python/raos/generated/contracts/catalog_normalize_ingestion_v1.py",
    "python/raos/generated/contracts/catalog_rakuten_genre_sync_v1.py",
    "python/raos/generated/contracts/catalog_rakuten_item_search_v1.py",
    "python/raos/generated/contracts/catalog_refresh_offer_v1.py",
    "python/raos/generated/contracts/caution.py",
    "python/raos/generated/contracts/claim.py",
    "python/raos/generated/contracts/claim_extraction_output.py",
    "python/raos/generated/contracts/comparison_table.py",
    "python/raos/generated/contracts/content_ast.py",
    "python/raos/generated/contracts/content_review_request/__init__.py",
    "python/raos/generated/contracts/content_review_request/v1.py",
    "python/raos/generated/contracts/content_schema_version/__init__.py",
    "python/raos/generated/contracts/content_schema_version/v1.py",
    "python/raos/generated/contracts/content_validation_request/__init__.py",
    "python/raos/generated/contracts/content_validation_request/v1.py",
    "python/raos/generated/contracts/content_validation_result/__init__.py",
    "python/raos/generated/contracts/content_validation_result/v1.py",
    "python/raos/generated/contracts/decision_summary.py",
    "python/raos/generated/contracts/difference_matrix.py",
    "python/raos/generated/contracts/disclosure_slot.py",
    "python/raos/generated/contracts/editorial_methodology_version/__init__.py",
    "python/raos/generated/contracts/editorial_methodology_version/v1.py",
    "python/raos/generated/contracts/editorial_review_decision.py",
    "python/raos/generated/contracts/evaluation_case/__init__.py",
    "python/raos/generated/contracts/evaluation_case/v1.py",
    "python/raos/generated/contracts/evaluation_case_result/__init__.py",
    "python/raos/generated/contracts/evaluation_case_result/v1.py",
    "python/raos/generated/contracts/evaluation_dataset_create_request/__init__.py",
    "python/raos/generated/contracts/evaluation_dataset_create_request/v1.py",
    "python/raos/generated/contracts/evaluation_dataset_version/__init__.py",
    "python/raos/generated/contracts/evaluation_dataset_version/v1.py",
    "python/raos/generated/contracts/evaluation_run/__init__.py",
    "python/raos/generated/contracts/evaluation_run/v1.py",
    "python/raos/generated/contracts/evaluation_run_create_request/__init__.py",
    "python/raos/generated/contracts/evaluation_run_create_request/v1.py",
    "python/raos/generated/contracts/evaluation_run_detail/__init__.py",
    "python/raos/generated/contracts/evaluation_run_detail/v1.py",
    "python/raos/generated/contracts/evaluation_suite/__init__.py",
    "python/raos/generated/contracts/evaluation_suite/v1.py",
    "python/raos/generated/contracts/event_envelope.py",
    "python/raos/generated/contracts/evidence_build_source_packet_v1.py",
    "python/raos/generated/contracts/evidence_capture_source_snapshot_v1.py",
    "python/raos/generated/contracts/evidence_extract_facts_v1.py",
    "python/raos/generated/contracts/evidence_note.py",
    "python/raos/generated/contracts/faq.py",
    "python/raos/generated/contracts/finance_calculate_unit_economics_v1.py",
    "python/raos/generated/contracts/finance_commit_revenue_import_v1.py",
    "python/raos/generated/contracts/finance_parse_revenue_csv_v1.py",
    "python/raos/generated/contracts/first_hand_experience_asset/__init__.py",
    "python/raos/generated/contracts/first_hand_experience_asset/v1.py",
    "python/raos/generated/contracts/first_hand_experience_create_request/__init__.py",
    "python/raos/generated/contracts/first_hand_experience_create_request/v1.py",
    "python/raos/generated/contracts/first_hand_experience_record/__init__.py",
    "python/raos/generated/contracts/first_hand_experience_record/v1.py",
    "python/raos/generated/contracts/freshness_assess_change_impact_v1.py",
    "python/raos/generated/contracts/freshness_check_affiliate_link_v1.py",
    "python/raos/generated/contracts/freshness_run_refresh_batch_v1.py",
    "python/raos/generated/contracts/ga4_metric_row.py",
    "python/raos/generated/contracts/ga4_run_report_request.py",
    "python/raos/generated/contracts/gsc_search_analytics_request.py",
    "python/raos/generated/contracts/gsc_search_analytics_row.py",
    "python/raos/generated/contracts/heading.py",
    "python/raos/generated/contracts/human_evaluation/__init__.py",
    "python/raos/generated/contracts/human_evaluation/v1.py",
    "python/raos/generated/contracts/human_evaluation_create_request/__init__.py",
    "python/raos/generated/contracts/human_evaluation_create_request/v1.py",
    "python/raos/generated/contracts/intended_reader.py",
    "python/raos/generated/contracts/internal_links.py",
    "python/raos/generated/contracts/job_message.py",
    "python/raos/generated/contracts/jp_raos_ai_evaluation_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_evaluation_completed_v2.py",
    "python/raos/generated/contracts/jp_raos_ai_job_failed_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_job_requested_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_job_succeeded_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_policy_assist_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_release_decision_approved_v1.py",
    "python/raos/generated/contracts/jp_raos_ai_release_decision_revoked_v1.py",
    "python/raos/generated/contracts/jp_raos_analytics_daily_metrics_updated_v1.py",
    "python/raos/generated/contracts/jp_raos_analytics_import_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_affiliate_link_invalid_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_candidates_normalized_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_genre_sync_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_grouping_decision_recorded_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_grouping_proposals_created_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_ingestion_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_offer_observed_v1.py",
    "python/raos/generated/contracts/jp_raos_catalog_offer_unavailable_v1.py",
    "python/raos/generated/contracts/jp_raos_editorial_article_created_v1.py",
    "python/raos/generated/contracts/jp_raos_editorial_article_plan_approved_v1.py",
    "python/raos/generated/contracts/jp_raos_editorial_article_version_submitted_v1.py",
    "python/raos/generated/contracts/jp_raos_editorial_draft_generated_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_claim_unsupported_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_claims_extracted_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_facts_extracted_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_source_packet_approved_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_source_packet_ready_v1.py",
    "python/raos/generated/contracts/jp_raos_evidence_source_snapshot_captured_v1.py",
    "python/raos/generated/contracts/jp_raos_finance_commission_status_changed_v1.py",
    "python/raos/generated/contracts/jp_raos_finance_revenue_import_committed_v1.py",
    "python/raos/generated/contracts/jp_raos_finance_revenue_import_dry_run_ready_v1.py",
    "python/raos/generated/contracts/jp_raos_finance_unit_economics_calculated_v1.py",
    "python/raos/generated/contracts/jp_raos_freshness_impact_detected_v1.py",
    "python/raos/generated/contracts/jp_raos_freshness_link_check_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_freshness_refresh_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_freshness_staleness_assessed_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_audit_export_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_child_jobs_created_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_incident_closed_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_incident_declared_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_job_failed_terminal_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_job_quarantined_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_job_requested_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_job_succeeded_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_kill_switch_changed_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_notification_dispatched_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_readmodel_rebuilt_v1.py",
    "python/raos/generated/contracts/jp_raos_ops_retention_sweep_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_blocking_finding_raised_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_finding_resolved_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_gate_decision_recorded_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_policy_bundle_activated_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_policy_recheck_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_policy_quality_check_completed_v1.py",
    "python/raos/generated/contracts/jp_raos_portfolio_action_candidate_decided_v1.py",
    "python/raos/generated/contracts/jp_raos_portfolio_action_candidates_generated_v1.py",
    "python/raos/generated/contracts/jp_raos_portfolio_opportunity_assessed_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_approval_granted_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_approval_revoked_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_article_published_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_article_rolled_back_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_article_unpublished_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_public_projection_rebuilt_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_review_assigned_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_review_decision_recorded_v1.py",
    "python/raos/generated/contracts/jp_raos_publishing_snapshot_built_v1.py",
    "python/raos/generated/contracts/judge_calibration/__init__.py",
    "python/raos/generated/contracts/judge_calibration/v1.py",
    "python/raos/generated/contracts/judge_calibration_create_request/__init__.py",
    "python/raos/generated/contracts/judge_calibration_create_request/v1.py",
    "python/raos/generated/contracts/judge_output/__init__.py",
    "python/raos/generated/contracts/judge_output/v1.py",
    "python/raos/generated/contracts/keyword_rank_row.py",
    "python/raos/generated/contracts/lead.py",
    "python/raos/generated/contracts/llm_structured_task_request.py",
    "python/raos/generated/contracts/llm_structured_task_result.py",
    "python/raos/generated/contracts/media.py",
    "python/raos/generated/contracts/media_asset.py",
    "python/raos/generated/contracts/media_asset_create_request/__init__.py",
    "python/raos/generated/contracts/media_asset_create_request/v1.py",
    "python/raos/generated/contracts/media_asset_resource/__init__.py",
    "python/raos/generated/contracts/media_asset_resource/v1.py",
    "python/raos/generated/contracts/media_asset_update_request/__init__.py",
    "python/raos/generated/contracts/media_asset_update_request/v1.py",
    "python/raos/generated/contracts/methodology.py",
    "python/raos/generated/contracts/methodology_validation_request/__init__.py",
    "python/raos/generated/contracts/methodology_validation_request/v1.py",
    "python/raos/generated/contracts/model_definition/__init__.py",
    "python/raos/generated/contracts/model_definition/v1.py",
    "python/raos/generated/contracts/model_route_version/__init__.py",
    "python/raos/generated/contracts/model_route_version/v1.py",
    "python/raos/generated/contracts/model_route_version_create_request/__init__.py",
    "python/raos/generated/contracts/model_route_version_create_request/v1.py",
    "python/raos/generated/contracts/money.py",
    "python/raos/generated/contracts/numbered_list.py",
    "python/raos/generated/contracts/opportunity_assessment_output.py",
    "python/raos/generated/contracts/ops_export_audit_v1.py",
    "python/raos/generated/contracts/ops_rebuild_readmodel_v1.py",
    "python/raos/generated/contracts/ops_retention_sweep_v1.py",
    "python/raos/generated/contracts/ops_send_notification_v1.py",
    "python/raos/generated/contracts/paragraph.py",
    "python/raos/generated/contracts/policy_assist_output.py",
    "python/raos/generated/contracts/portfolio_assess_opportunity_v1.py",
    "python/raos/generated/contracts/portfolio_generate_action_candidates_v1.py",
    "python/raos/generated/contracts/problem_details.py",
    "python/raos/generated/contracts/product_card.py",
    "python/raos/generated/contracts/prompt_version/__init__.py",
    "python/raos/generated/contracts/prompt_version/v1.py",
    "python/raos/generated/contracts/prompt_version_create_request/__init__.py",
    "python/raos/generated/contracts/prompt_version_create_request/v1.py",
    "python/raos/generated/contracts/pros_cons.py",
    "python/raos/generated/contracts/publication_content_manifest.py",
    "python/raos/generated/contracts/publication_manifest_create_request/__init__.py",
    "python/raos/generated/contracts/publication_manifest_create_request/v1.py",
    "python/raos/generated/contracts/publication_snapshot.py",
    "python/raos/generated/contracts/publishing_build_snapshot_v1.py",
    "python/raos/generated/contracts/publishing_publish_snapshot_v1.py",
    "python/raos/generated/contracts/publishing_rebuild_public_projection_v1.py",
    "python/raos/generated/contracts/publishing_rollback_v1.py",
    "python/raos/generated/contracts/publishing_unpublish_v1.py",
    "python/raos/generated/contracts/quality_evaluate_article_v1.py",
    "python/raos/generated/contracts/quality_recheck_policy_bundle_v1.py",
    "python/raos/generated/contracts/rakuten_item_search_canonical_page.py",
    "python/raos/generated/contracts/rakuten_item_search_request.py",
    "python/raos/generated/contracts/recommendation_group.py",
    "python/raos/generated/contracts/recommendation_methodology.py",
    "python/raos/generated/contracts/release_active_approval_request/__init__.py",
    "python/raos/generated/contracts/release_active_approval_request/v1.py",
    "python/raos/generated/contracts/release_approval/__init__.py",
    "python/raos/generated/contracts/release_approval/v1.py",
    "python/raos/generated/contracts/release_canary_approval_request/__init__.py",
    "python/raos/generated/contracts/release_canary_approval_request/v1.py",
    "python/raos/generated/contracts/release_decision/__init__.py",
    "python/raos/generated/contracts/release_decision/v1.py",
    "python/raos/generated/contracts/release_decision_approval_result/__init__.py",
    "python/raos/generated/contracts/release_decision_approval_result/v1.py",
    "python/raos/generated/contracts/release_decision_create_request/__init__.py",
    "python/raos/generated/contracts/release_decision_create_request/v1.py",
    "python/raos/generated/contracts/release_decision_revoke_request/__init__.py",
    "python/raos/generated/contracts/release_decision_revoke_request/v1.py",
    "python/raos/generated/contracts/resource_ref.py",
    "python/raos/generated/contracts/revenue_canonical_row.py",
    "python/raos/generated/contracts/rich_text.py",
    "python/raos/generated/contracts/selection_criteria.py",
    "python/raos/generated/contracts/seo_metadata.py",
    "python/raos/generated/contracts/seo_metadata_update_request/__init__.py",
    "python/raos/generated/contracts/seo_metadata_update_request/v1.py",
    "python/raos/generated/contracts/seo_metadata_version/__init__.py",
    "python/raos/generated/contracts/seo_metadata_version/v1.py",
    "python/raos/generated/contracts/source_summary.py",
    "python/raos/generated/contracts/structured_data_command_request/__init__.py",
    "python/raos/generated/contracts/structured_data_command_request/v1.py",
    "python/raos/generated/contracts/structured_data_manifest.py",
    "python/raos/generated/contracts/structured_data_manifest_resource/__init__.py",
    "python/raos/generated/contracts/structured_data_manifest_resource/v1.py",
    "python/raos/generated/contracts/tradeoff.py",
    "python/raos/generated/contracts/update_notice.py",
)
EXPECTED_RUNTIME_PATHS: Final[tuple[str, ...]] = tuple(
    sorted((*_BASE_RUNTIME_PATHS, *GENERATED_RUNTIME_PATHS))
)
_MODULE_PATHS: Final = (
    (
        "raos.domain.editorial.self_hosted_editorial_pilot",
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.ports.self_hosted_editorial_pilot",
        "python/raos/ports/self_hosted_editorial_pilot.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_pilot_json",
        "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    ),
    (
        "raos.adapters.self_hosted_editorial_source_capture",
        "python/raos/adapters/self_hosted_editorial_source_capture.py",
    ),
)
_PACKAGE_NAMES: Final = (
    "raos",
    "raos.domain",
    "raos.domain.editorial",
    "raos.ports",
    "raos.adapters",
)
_TRACKED_SOURCE_PATHS: Final = frozenset(
    {
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-locator-contract.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json",
    }
)
_CAPTURE_FAILURE_CODES: Final = frozenset(
    {
        "ARTICLE_NOT_ALLOWLISTED",
        "BODY_TOO_LARGE",
        "CONNECTION_FAILED",
        "CONTRACT_INVALID",
        "DNS_ADDRESS_REJECTED",
        "DNS_FAILED",
        "HTML_INVALID",
        "INVALID_ARGUMENT",
        "LOCATOR_MISMATCH",
        "LOCATORS_PENDING",
        "MIME_INVALID",
        "NETWORK_ENVIRONMENT_UNSAFE",
        "REQUEST_AMBIGUOUS",
        "RESPONSE_INVALID",
        "SOURCE_NOT_ALLOWLISTED",
        "STORE_CONFLICT",
        "STORE_UNSAFE",
        "TLS_CONTEXT_INVALID",
    }
)
RootIdentity = tuple[int, int]


class _CaptureResult(Protocol):
    body_sha256: str
    credentials_used: bool
    production_evidence: bool
    publication_authority: bool
    request_count: int
    response_sha256: str
    retrieved_at: str
    source_ref: str
    status: str


class _RuntimeFailure(RuntimeError):
    """Sanitized stage-zero integrity refusal."""


class _CommandFailure(RuntimeError):
    """Sanitized verified-runtime refusal."""


def _fail_runtime() -> NoReturn:
    raise _RuntimeFailure("OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID") from None


def _canonical_manifest(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail_runtime()


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail_runtime()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail_runtime()


def _parse_integer(value: str) -> int:
    if not 1 <= len(value) <= 20:
        _fail_runtime()
    try:
        return int(value)
    except ValueError:
        _fail_runtime()


def _decode_json(raw: bytes) -> dict[str, object]:
    if not raw or raw.startswith(b"\xef\xbb\xbf"):
        _fail_runtime()
    try:
        decoded = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_int=_parse_integer,
            parse_constant=_reject_number,
        )
    except _RuntimeFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail_runtime()
    if type(decoded) is not dict:
        _fail_runtime()
    return cast(dict[str, object], decoded)


def _relative_parts(relative: str) -> tuple[str, ...]:
    if type(relative) is not str or not relative or relative != relative.strip():
        _fail_runtime()
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail_runtime()
    return path.parts


def _safe_directory(fd: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        _fail_runtime()
    return observed


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail_runtime()
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        _safe_directory(current)
        return current
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    current = -1
    try:
        current = os.dup(root_fd)
        for part in parts[:-1]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            _safe_directory(following)
            os.close(current)
            current = following
        return current, parts[-1]
    except _RuntimeFailure:
        if current >= 0:
            os.close(current)
        raise
    except OSError:
        if current >= 0:
            os.close(current)
        _fail_runtime()


def _safe_file(fd: int, *, maximum: int) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) & 0o022
        or not 0 < observed.st_size <= maximum
    ):
        _fail_runtime()
    return observed


def _read_relative(root_fd: int, relative: str, *, maximum: int) -> bytes:
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail_runtime()
        try:
            before = _safe_file(descriptor, maximum=maximum)
            remaining = before.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    _fail_runtime()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail_runtime()
            after = _safe_file(descriptor, maximum=maximum)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                _fail_runtime()
            try:
                rebound_fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
            except OSError:
                _fail_runtime()
            try:
                rebound = _safe_file(rebound_fd, maximum=maximum)
                if (before.st_dev, before.st_ino) != (
                    rebound.st_dev,
                    rebound.st_ino,
                ):
                    _fail_runtime()
            finally:
                os.close(rebound_fd)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _rebind_root(root: Path, identity: RootIdentity) -> None:
    descriptor = _open_absolute_directory(root)
    try:
        observed = _safe_directory(descriptor)
        if (observed.st_dev, observed.st_ino) != identity:
            _fail_runtime()
    finally:
        os.close(descriptor)


def _verify_stage_zero() -> None:
    flags = sys.flags
    try:
        current_directory = os.getcwd()
    except OSError:
        _fail_runtime()
    if (
        SOURCE_CLI_PATH != REPOSITORY_ROOT / BOOTSTRAP_RELATIVE
        or sys.executable != OWNER_PYTHON
        or sys.version_info[:3] != (3, 14, 6)
        or flags.dont_write_bytecode != 1
        or flags.ignore_environment != 1
        or flags.isolated != 1
        or flags.no_site != 1
        or flags.no_user_site != 1
        or not flags.safe_path
        or current_directory != REPOSITORY_ROOT.as_posix()
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(REPOSITORY_ROOT)
    try:
        root = _safe_directory(root_fd)
        try:
            cwd_fd = os.open(".", _DIRECTORY_FLAGS)
        except OSError:
            _fail_runtime()
        try:
            cwd = _safe_directory(cwd_fd)
            if (root.st_dev, root.st_ino) != (cwd.st_dev, cwd.st_ino):
                _fail_runtime()
        finally:
            os.close(cwd_fd)
    finally:
        os.close(root_fd)


def _validate_predecessor(raw: bytes) -> None:
    predecessor = _decode_json(raw)
    if raw != _canonical_manifest(predecessor) or set(predecessor) != {
        "external_action_authority",
        "generated_by",
        "generator_owner",
        "generator_version",
        "paths",
        "schema",
        "slice_id",
        "story_id",
    }:
        _fail_runtime()
    if (
        predecessor["external_action_authority"] != "NONE"
        or predecessor["generated_by"]
        != "scripts/build_st1703_self_hosted_runtime_manifest.py"
        or predecessor["generator_owner"] != "build_st1703_self_hosted_runtime_manifest"
        or predecessor["generator_version"] != "2"
        or predecessor["schema"] != "SELF_HOSTED_WORDPRESS_RUNTIME_MANIFEST_V1"
        or predecessor["slice_id"] != "SELF_HOSTED_MINIMUM_START_V1"
        or predecessor["story_id"] != "ST-1703"
        or type(predecessor["paths"]) is not list
        or not predecessor["paths"]
    ):
        _fail_runtime()


def _contains_exact(values: Container[str], expected: str) -> bool:
    return expected in values


def _verify_runtime_integrity(
    root: object,
) -> tuple[dict[str, bytes], RootIdentity]:
    """Verify the closed tree before importing any RAOS runtime module."""

    runtime_paths = set(EXPECTED_RUNTIME_PATHS)
    if (
        not isinstance(root, Path)
        or not root.is_absolute()
        or tuple(sorted(EXPECTED_RUNTIME_PATHS)) != EXPECTED_RUNTIME_PATHS
        or len(runtime_paths) != len(EXPECTED_RUNTIME_PATHS)
        or _contains_exact(runtime_paths, MANIFEST_RELATIVE)
        or not _contains_exact(runtime_paths, BOOTSTRAP_RELATIVE)
        or not _TRACKED_SOURCE_PATHS < runtime_paths
    ):
        _fail_runtime()
    root_fd = _open_absolute_directory(root)
    try:
        verified_root = _safe_directory(root_fd)
        manifest_raw = _read_relative(
            root_fd, MANIFEST_RELATIVE, maximum=MAX_MANIFEST_BYTES
        )
        manifest = _decode_json(manifest_raw)
        if manifest_raw != _canonical_manifest(manifest) or set(manifest) != {
            "article_ids",
            "external_action_authority",
            "generated_by",
            "generator_owner",
            "generator_version",
            "paths",
            "predecessor",
            "publication_authority",
            "schema",
            "slice_id",
            "story_id",
        }:
            _fail_runtime()
        if (
            manifest["article_ids"] != list(ARTICLE_IDS)
            or manifest["external_action_authority"] != "NONE"
            or manifest["generated_by"]
            != "scripts/build_st1704_self_hosted_editorial_manifest.py"
            or manifest["generator_owner"]
            != "build_st1704_self_hosted_editorial_manifest"
            or manifest["generator_version"] != "2"
            or manifest["publication_authority"] != "NONE"
            or manifest["schema"] != "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
            or manifest["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
            or manifest["story_id"] != "ST-1704"
        ):
            _fail_runtime()
        predecessor_value = manifest["predecessor"]
        if type(predecessor_value) is not dict:
            _fail_runtime()
        predecessor = cast(dict[str, object], predecessor_value)
        if predecessor != {
            "owner_id": "build_st1703_self_hosted_runtime_manifest",
            "version": "2",
        }:
            _fail_runtime()
        entries_value = manifest["paths"]
        if type(entries_value) is not list:
            _fail_runtime()
        entries = cast(list[object], entries_value)
        if len(entries) != len(EXPECTED_RUNTIME_PATHS):
            _fail_runtime()
        sources: dict[str, bytes] = {}
        for expected_path, entry_value in zip(
            EXPECTED_RUNTIME_PATHS, entries, strict=True
        ):
            if type(entry_value) is not dict:
                _fail_runtime()
            entry = cast(dict[str, object], entry_value)
            if set(entry) != {"bytes", "path", "sha256"}:
                _fail_runtime()
            byte_count = entry["bytes"]
            sha256 = entry["sha256"]
            if (
                entry["path"] != expected_path
                or type(byte_count) is not int
                or not 0 < byte_count <= MAX_RUNTIME_BYTES
                or type(sha256) is not str
                or _SHA256.fullmatch(sha256) is None
            ):
                _fail_runtime()
            raw = _read_relative(root_fd, expected_path, maximum=MAX_RUNTIME_BYTES)
            if len(raw) != byte_count or hashlib.sha256(raw).hexdigest() != sha256:
                _fail_runtime()
            sources[expected_path] = raw
        rebound = _open_absolute_directory(root)
        try:
            final_root = _safe_directory(rebound)
            if (verified_root.st_dev, verified_root.st_ino) != (
                final_root.st_dev,
                final_root.st_ino,
            ):
                _fail_runtime()
        finally:
            os.close(rebound)
        return sources, (final_root.st_dev, final_root.st_ino)
    except _RuntimeFailure:
        raise
    except Exception:
        _fail_runtime()
    finally:
        os.close(root_fd)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    setattr(module, "__path__", [])
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
    return module


def _load_verified_modules(sources: dict[str, bytes]) -> dict[str, types.ModuleType]:
    runtime_names = {*_PACKAGE_NAMES, *(name for name, _path in _MODULE_PATHS)}
    if runtime_names & set(sys.modules):
        _fail_runtime()
    for name in _PACKAGE_NAMES:
        _package(name)
    loaded: dict[str, types.ModuleType] = {}
    for module_name, relative in _MODULE_PATHS:
        raw = sources.get(relative)
        if type(raw) is not bytes:
            _fail_runtime()
        module = types.ModuleType(module_name)
        module.__file__ = (REPOSITORY_ROOT / relative).as_posix()
        module.__package__ = module_name.rsplit(".", 1)[0]
        sys.modules[module_name] = module
        parent_name, child_name = module_name.rsplit(".", 1)
        setattr(sys.modules[parent_name], child_name, module)
        try:
            code = compile(raw, module.__file__, "exec", dont_inherit=True)
            exec(code, module.__dict__)
        except BaseException:
            _fail_runtime()
        loaded[module_name] = module
    return loaded


def _bind_verified_source_documents(
    module: types.ModuleType,
    sources: dict[str, bytes],
    root_identity: RootIdentity,
) -> None:
    verified = {relative: sources[relative] for relative in _TRACKED_SOURCE_PATHS}
    source_directory_value = getattr(module, "_source_directory", None)
    if not callable(source_directory_value):
        _fail_runtime()
    source_directory = cast(Callable[[Path], object], source_directory_value)

    def read_tracked_file(
        repository_root: object, relative: object, maximum: object
    ) -> bytes:
        if (
            not isinstance(repository_root, Path)
            or repository_root != REPOSITORY_ROOT
            or not isinstance(relative, Path)
            or type(maximum) is not int
            or maximum <= 0
        ):
            _fail_runtime()
        key = relative.as_posix()
        raw = verified.get(key)
        if raw is None or len(raw) > maximum:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, root_identity)
        return raw

    def checked_source_directory(repository_root: object) -> Path:
        if not isinstance(repository_root, Path) or repository_root != REPOSITORY_ROOT:
            _fail_runtime()
        _rebind_root(REPOSITORY_ROOT, root_identity)
        result = source_directory(repository_root)
        if not isinstance(result, Path):
            _fail_runtime()
        return result

    setattr(module, "_read_tracked_file", read_tracked_file)
    setattr(module, "_source_directory", checked_source_directory)


def _write_json(value: object, *, target: TextIO | None = None) -> None:
    destination = sys.stdout if target is None else target
    if destination is None:
        _fail_runtime()
    destination.write(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="st1704_official_source_capture.py",
        description=(
            "Capture exact allowlisted official HTML sources with read-only HTTPS. "
            "There is no caller URL, credential, WordPress, Rakuten API, product "
            "retrieval, publication, plugin, theme, or generic HTTP capability."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("capture-source", allow_abbrev=False)
    source.add_argument("--source-ref", choices=SOURCE_REFS, required=True)
    article = commands.add_parser("capture-article", allow_abbrev=False)
    article.add_argument("--article-id", choices=ARTICLE_IDS, required=True)
    return parser


def _execute(
    command: str,
    *,
    source_ref: str | None,
    article_id: str | None,
    sources: dict[str, bytes],
    root_identity: RootIdentity,
) -> dict[str, object]:
    if (
        type(root_identity) is not tuple
        or len(root_identity) != 2
        or any(type(value) is not int or value < 0 for value in root_identity)
    ):
        _fail_runtime()
    _rebind_root(REPOSITORY_ROOT, root_identity)
    modules = _load_verified_modules(sources)
    capture = modules["raos.adapters.self_hosted_editorial_source_capture"]
    _bind_verified_source_documents(capture, sources, root_identity)
    capture_source_ref = getattr(capture, "capture_source_ref", None)
    capture_article_sources = getattr(capture, "capture_article_sources", None)
    failure_type = getattr(capture, "OfficialSourceCaptureFailure", None)
    result_type = getattr(capture, "SourceCaptureResult", None)
    if (
        not callable(capture_source_ref)
        or not callable(capture_article_sources)
        or not isinstance(failure_type, type)
        or not isinstance(result_type, type)
    ):
        _fail_runtime()
    results_value: object
    try:
        if (
            command == "capture-source"
            and source_ref in SOURCE_REFS
            and article_id is None
        ):
            results_value = capture_source_ref(
                REPOSITORY_ROOT,
                source_ref=source_ref,
                clock=lambda: datetime.now(timezone.utc),
            )
        elif (
            command == "capture-article"
            and article_id in ARTICLE_IDS
            and source_ref is None
        ):
            results_value = capture_article_sources(
                REPOSITORY_ROOT,
                article_id=article_id,
                clock=lambda: datetime.now(timezone.utc),
            )
        else:
            _fail_runtime()
    except _RuntimeFailure:
        raise
    except Exception as error:
        if type(error) is failure_type:
            code = getattr(getattr(error, "code", None), "value", None)
            if type(code) is str and code in _CAPTURE_FAILURE_CODES:
                raise _CommandFailure(code) from None
        raise
    if type(results_value) is not tuple:
        _fail_runtime()
    results = cast(tuple[object, ...], results_value)
    documents: list[dict[str, object]] = []
    for value in results:
        if type(value) is not result_type:
            _fail_runtime()
        result = cast(_CaptureResult, value)
        if (
            type(result.body_sha256) is not str
            or _SHA256.fullmatch(result.body_sha256) is None
            or result.credentials_used is not False
            or result.production_evidence is not False
            or result.publication_authority is not False
            or type(result.request_count) is not int
            or result.request_count != 1
            or type(result.response_sha256) is not str
            or _SHA256.fullmatch(result.response_sha256) is None
            or type(result.retrieved_at) is not str
            or not result.retrieved_at
            or type(result.source_ref) is not str
            or result.source_ref not in SOURCE_REFS
            or type(result.status) is not str
            or result.status
            not in {
                "BODY_CAPTURED_LOCATORS_PENDING",
                "CAPTURED_WITH_VERIFIED_LOCATORS",
            }
        ):
            _fail_runtime()
        documents.append(
            {
                "body_sha256": result.body_sha256,
                "request_count": result.request_count,
                "response_sha256": result.response_sha256,
                "retrieved_at": result.retrieved_at,
                "source_ref": result.source_ref,
                "status": result.status,
            }
        )
    return {
        "article_id": article_id,
        "command": command,
        "credentials_used": False,
        "network_requests": len(results),
        "production_evidence": False,
        "publication_authority": False,
        "results": documents,
        "source_ref": source_ref,
        "status": "CAPTURE_COMPLETED",
    }


def _refusal(
    arguments: argparse.Namespace, code: str, *, target: TextIO | None = None
) -> None:
    if target is None:
        target = sys.stderr
    _write_json(
        {
            "article_id": getattr(arguments, "article_id", None),
            "command": arguments.command,
            "credentials_used": False,
            "error": code,
            "production_evidence": False,
            "publication_authority": False,
            "source_ref": getattr(arguments, "source_ref", None),
            "status": "REFUSED",
        },
        target=target,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _verify_stage_zero()
        sources, root_identity = _verify_runtime_integrity(REPOSITORY_ROOT)
        result = _execute(
            arguments.command,
            source_ref=getattr(arguments, "source_ref", None),
            article_id=getattr(arguments, "article_id", None),
            sources=sources,
            root_identity=root_identity,
        )
    except _RuntimeFailure:
        _refusal(arguments, "OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID")
        return 1
    except _CommandFailure as error:
        _refusal(arguments, str(error))
        return 1
    except Exception:
        _refusal(arguments, "OFFICIAL_SOURCE_CAPTURE_INTERNAL_FAILURE")
        return 1
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
