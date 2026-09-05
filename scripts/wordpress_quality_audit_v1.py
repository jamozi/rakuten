#!/usr/bin/env python3
"""Fail-closed two-round quality ledger for the WordPress editorial surface.

This module validates evidence; it does not execute an audit, contact WordPress,
or turn a blocked baseline into a clean review. Distinct reviewer strings are
not proof of independence. Completion additionally requires an Ed25519-signed,
canonical independent-reviewer attestation from a public key explicitly trusted
by the tracked contract. The tracked contract contains no production trust key,
so the default baseline remains blocked.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn, cast
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
SLICE_ROOT: Final = REPOSITORY_ROOT / "changes/wordpress-quality-audit-v1"
DEFAULT_CONTRACT_PATH: Final = SLICE_ROOT / "quality-audit-contract.v1.json"
DEFAULT_LEDGER_PATH: Final = SLICE_ROOT / "quality-audit-ledger.v1.json"
DEFAULT_EVIDENCE_ROOT: Final = SLICE_ROOT / "evidence"
DEFAULT_EDITORIAL_EVIDENCE_SCHEMA_PATH: Final = (
    SLICE_ROOT / "editorial-evidence.schema.json"
)
DEFAULT_EDITORIAL_EVIDENCE_REGISTER_PATH: Final = (
    SLICE_ROOT / "editorial-evidence-register.v1.json"
)
DEFAULT_ARTICLE_FIXTURE_ROOT: Final = (
    REPOSITORY_ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
)

CONTRACT_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_CONTRACT_V1"
LEDGER_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_LEDGER_V1"
POST_APPLY_RESULT_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_POST_APPLY_RESULT_V1"
EVIDENCE_MANIFEST_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_EVIDENCE_MANIFEST_V1"
GATE_RESULT_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_GATE_RESULT_V1"
COMMAND_RECORD_SCHEMA: Final = "RAOS_WORDPRESS_QUALITY_AUDIT_COMMAND_RECORD_V1"
ATTESTATION_SCHEMA: Final = (
    "RAOS_WORDPRESS_QUALITY_AUDIT_INDEPENDENT_REVIEWER_ATTESTATION_V1"
)
VERSION: Final = "1.1.0"
PRE_PUBLICATION_PHASE_ID: Final = "PRE_PUBLICATION"
PRE_PUBLICATION_COMPLETION_STATE: Final = "READY_FOR_PUBLICATION_PROPOSAL"
POST_APPLY_PHASE_ID: Final = "POST_APPLY"
POST_APPLY_COMPLETION_STATE: Final = "PRODUCTION_PARITY_VERIFIED"
POST_APPLY_PENDING_STATE: Final = "REQUIRED_NOT_EVALUATED"
FINGERPRINT_ALGORITHM: Final = "RAOS_FILE_SET_SHA256_V1"
HASH_ALGORITHM: Final = "SHA256_CANONICAL_JSON_V1"
ATTESTATION_SIGNATURE_ALGORITHM: Final = "ED25519"
ATTESTATION_CANONICALIZATION: Final = "RAOS_SORTED_UTF8_JSON_V1"
INDEPENDENCE_STATEMENT: Final = (
    "I_ATTEST_THAT_THE_BOUND_REVIEW_ROUNDS_WERE_PERFORMED_INDEPENDENTLY_"
    "OF_CONTENT_AUTHORING_AND_OF_EACH_OTHER_WITHOUT_SELF_REVIEW"
)
MAX_DOCUMENT_BYTES: Final = 2_000_000
MAX_FINGERPRINT_FILE_BYTES: Final = 32_000_000
MAX_FINGERPRINT_FILES: Final = 20_000
MAX_EVIDENCE_MANIFEST_BYTES: Final = 1_000_000
MAX_EVIDENCE_ARTIFACT_BYTES: Final = 32_000_000
MAX_EVIDENCE_ARTIFACTS: Final = 64
MAX_ATTESTATION_BYTES: Final = 16_384
MAX_ATTESTATION_SIGNATURE_BYTES: Final = 256
ED25519_PUBLIC_KEY_BYTES: Final = 32
ED25519_SIGNATURE_BYTES: Final = 64
MAX_TRUSTED_REVIEWER_KEYS: Final = 32

SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
IDENTIFIER_RE: Final = re.compile(r"[a-z0-9][a-z0-9._-]{7,95}\Z", re.ASCII)
TIMESTAMP_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)
DATE_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
ARTICLE_SLUG_RE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+\Z", re.ASCII)
EVIDENCE_PATH_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,239}\Z", re.ASCII)
TOOL_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{1,127}\Z", re.ASCII)
EVIDENCE_TYPE_RE: Final = re.compile(r"[a-z0-9][a-z0-9._:-]{2,127}\Z", re.ASCII)

EXPECTED_FINGERPRINT_INPUTS: Final = {
    "source": (
        "Makefile",
        "changes/analytics-google-live-v1/runtime-manifest.v1.json",
        "changes/editorial-measurement-v1",
        "changes/editorial-portfolio-v2/editorial-portfolio.v2.json",
        "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json",
        "changes/editorial-portfolio-v3/editorial-identities.v1.json",
        "changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        "changes/editorial-portfolio-v3/market-candidate-audit.v1.json",
        "changes/editorial-portfolio-v3/rakuten-parser-boundary.v1.json",
        "changes/editorial-portfolio-v3/README.md",
        "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json",
        "changes/st-1704/carry-on-single-url-evidence-loop-v1",
        "changes/st-1704/self-hosted-editorial-pilot-v1/BRAND_VOICE.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml",
        "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_SYSTEM.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/EDITORIAL_RESEARCH_NOTES.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/Makefile",
        "changes/st-1704/self-hosted-editorial-pilot-v1/OPERATIONS_RUNBOOK.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/PREFLIGHT.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/RAKUTEN_CAPTURE_WORKLOG.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/README.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/REVENUE_EXPERIMENT_RUNBOOK.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/REVENUE_UNBLOCK_WORKLOG.md",
        "changes/st-1704/self-hosted-editorial-pilot-v1/content",
        "changes/st-1704/self-hosted-editorial-pilot-v1/media",
        "changes/st-1704/self-hosted-editorial-pilot-v1/operations",
        "changes/st-1704/self-hosted-editorial-pilot-v1/"
        "rakuten-capture-runtime-manifest.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/sources",
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/yoast-seo-28.3.lock.json",
        "changes/wordpress-local-preview-v1/bin",
        "changes/wordpress-local-preview-v1/browser",
        "changes/wordpress-local-preview-v1/compose.yaml",
        "changes/wordpress-local-preview-v1/gateway/nginx.conf",
        "changes/wordpress-local-preview-v1/mu-plugins/raos-local-preview.php",
        "changes/wordpress-local-preview-v1/policy-profiles.v1.json",
        "changes/wordpress-local-preview-v1/production-mapping.v1.json",
        "changes/wordpress-local-preview-v1/seed.php",
        "changes/wordpress-quality-audit-v1/README.md",
        "changes/wordpress-quality-audit-v1/editorial-evidence.schema.json",
        "changes/wordpress-quality-audit-v1/editorial-evidence-register.v1.json",
        "changes/wordpress-seo-audit-v1/seo-audit-contract.v1.json",
        "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json",
        "package-lock.json",
        "package.json",
        "packages/wordpress-mcp-bridge/src/index.ts",
        "python/raos/adapters/self_hosted_editorial_pilot_https.py",
        "python/raos/adapters/self_hosted_editorial_pilot_json.py",
        "python/raos/adapters/self_hosted_editorial_rakuten_capture.py",
        "python/raos/adapters/self_hosted_editorial_source_capture.py",
        "python/raos/adapters/self_hosted_wordpress_credentials.py",
        "python/raos/adapters/self_hosted_wordpress_https.py",
        "python/raos/adapters/self_hosted_wordpress_rest.py",
        "python/raos/adapters/wordpress_rest.py",
        "python/raos/application/editorial/editorial_portfolio_v2.py",
        "python/raos/application/editorial/editorial_portfolio_v3.py",
        "python/raos/application/editorial/product_safety_manufacturer_capture.py",
        "python/raos/application/editorial/product_safety_query_capture.py",
        "python/raos/application/editorial/product_safety_receipts.py",
        "python/raos/application/editorial/rakuten_measurement_activation_v3.py",
        "python/raos/application/editorial/rakuten_standard_api_v1.py",
        "python/raos/application/editorial/self_hosted_editorial_pilot.py",
        "python/raos/application/finance/editorial_economics_v3.py",
        "python/raos/domain/editorial/content_ast.py",
        "python/raos/domain/editorial/market_learning_pilot.py",
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
        "python/raos/domain/editorial/self_hosted_wordpress.py",
        "python/raos/generated/contracts",
        "python/raos/ports/self_hosted_editorial_pilot.py",
        "scripts/build_editorial_measurement_v1.py",
        "scripts/build_editorial_portfolio_v3.py",
        "scripts/build_editorial_v3_theme_navigation.py",
        "scripts/build_st1704_portfolio_source_packets.py",
        "scripts/build_st1704_rakuten_capture_manifest.py",
        "scripts/build_st1704_reader_claim_coverage.py",
        "scripts/build_st1704_self_hosted_editorial_manifest.py",
        "scripts/build_st1704_self_hosted_theme.py",
        "scripts/build_st1704_theme_assets.py",
        "scripts/check_wordpress_public_ui_playwright.sh",
        "scripts/raos_build_core.py",
        "scripts/raos_editorial_economics_v3.py",
        "scripts/raos_editorial_portfolio_v2.py",
        "scripts/raos_rakuten_measurement_activation_v3.py",
        "scripts/raos_wordpress_deployment_operator.py",
        "scripts/raos_wordpress_publication_request.py",
        "scripts/raos_wordpress_seo_audit.py",
        "scripts/st1704_official_source_capture.py",
        "scripts/st1704_product_safety_manufacturer_capture.py",
        "scripts/st1704_product_safety_query_capture.py",
        "scripts/st1704_rakuten_product_capture.py",
        "scripts/st1704_self_hosted_editorial_pilot.py",
        "scripts/wordpress_public_ui_audit.function.js",
        "scripts/wordpress_quality_audit_v1.py",
        "tests/editorial_measurement_v1",
        "tests/editorial_portfolio_v2",
        "tests/editorial_portfolio_v3",
        "tests/editorial_product_safety_manufacturer_capture",
        "tests/editorial_product_safety_query_capture",
        "tests/editorial_product_safety_receipts",
        "tests/st1704",
        "tests/wordpress_local_preview",
        "tests/wordpress_mcp_v1/test_contract.py",
        "tests/wordpress_mcp_v1/test_release_watcher.py",
        "tests/wordpress_quality_audit_v1",
        "tests/wordpress_seo_audit_v1",
    ),
    "theme": (
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child",
    ),
    "fixture": ("changes/wordpress-local-preview-v1/fixtures",),
    "navigation": (
        "changes/editorial-portfolio-v3/generated/navigation.v3.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child/assets/editorial-navigation.v3.json",
    ),
    "inventory": (
        "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json",
    ),
}

EXPECTED_PRE_PUBLICATION_SURFACES: Final = (
    ("code", "code_static_and_tests", 86_400),
    ("editorial_sources", "editorial_source_integrity", 86_400),
    (
        "epistemic_negative_claims_and_calculation_semantics",
        "epistemic_negative_claims_and_calculation_semantics",
        86_400,
    ),
    (
        "editorial_language_story_ia",
        "editorial_language_story_information_architecture",
        86_400,
    ),
    (
        "editorial_accountability_author_credentials_corrections",
        "editorial_accountability_author_credentials_corrections",
        3_600,
    ),
    (
        "content_originality_copyright_near_duplicate_risk",
        "content_originality_copyright_near_duplicate_risk",
        86_400,
    ),
    (
        "contact_corrections_operational_deliverability",
        "contact_corrections_operational_deliverability",
        86_400,
    ),
    (
        "search_intent_cannibalization_orphaning",
        "search_intent_cannibalization_orphaning_integrity",
        3_600,
    ),
    (
        "product_selection_lifecycle_support",
        "product_selection_lifecycle_support_integrity",
        86_400,
    ),
    (
        "candidate_universe_representativeness_and_brand_blindspots",
        "candidate_universe_representativeness_and_brand_blindspots",
        86_400,
    ),
    (
        "consumer_safety_recall_compatibility",
        "consumer_safety_recall_compatibility_integrity",
        86_400,
    ),
    (
        "smart_device_app_cloud_security_update_eol_privacy",
        "smart_device_app_cloud_security_update_eol_privacy",
        86_400,
    ),
    (
        "battery_large_appliance_disposal_recycling_transport",
        "battery_large_appliance_disposal_recycling_transport",
        86_400,
    ),
    (
        "freshness_maintenance_ownership",
        "freshness_maintenance_ownership_integrity",
        86_400,
    ),
    (
        "affiliate_fairness_dark_patterns",
        "affiliate_fairness_dark_pattern_runtime",
        3_600,
    ),
    (
        "legal_disclosure_media_rights",
        "legal_disclosure_media_rights_review",
        86_400,
    ),
    (
        "provenance_reproducibility_recovery",
        "provenance_reproducibility_recovery_integrity",
        86_400,
    ),
    (
        "wordpress_backup_rollback_reproducible_restoration",
        "wordpress_backup_rollback_reproducible_restoration",
        86_400,
    ),
    (
        "dependency_supply_chain_plugin_integrity",
        "dependency_supply_chain_plugin_integrity",
        86_400,
    ),
    ("seo_schema", "seo_schema_semantics", 3_600),
    ("policy_privacy_consent", "policy_privacy_consent_runtime", 3_600),
    (
        "analytics_data_minimization_accuracy",
        "analytics_data_minimization_accuracy_runtime",
        3_600,
    ),
    ("ui_a11y_keyboard_zoom", "ui_a11y_keyboard_zoom_runtime", 3_600),
    (
        "cognitive_accessibility_japanese_readability",
        "cognitive_accessibility_japanese_readability_runtime",
        3_600,
    ),
    ("links_security_headers", "links_security_headers_runtime", 3_600),
    ("product_media_cta_evidence", "product_media_cta_activation", 900),
    ("search_archive_404", "search_archive_404_runtime", 3_600),
    (
        "browser_resilience_no_js_error_recovery",
        "browser_resilience_no_js_error_recovery_runtime",
        3_600,
    ),
    (
        "browser_compatibility_restricted_environment_resilience",
        "browser_compatibility_restricted_environment_resilience",
        3_600,
    ),
    ("performance_browser", "performance_browser_runtime", 3_600),
    (
        "task_based_decision_usability_reader_comprehension",
        "task_based_decision_usability_reader_comprehension_research",
        3_600,
    ),
    (
        "japanese_locale_measurement_semantics_inclusive_language",
        "japanese_locale_measurement_semantics_inclusive_language",
        86_400,
    ),
    (
        "touch_gesture_orientation_400_percent_reflow_target_size",
        "touch_gesture_orientation_400_percent_reflow_target_size_runtime",
        3_600,
    ),
    (
        "wordpress_public_attack_abuse_surface",
        "wordpress_public_attack_abuse_surface_runtime",
        3_600,
    ),
    (
        "operations_observability_incident_ownership",
        "operations_observability_incident_ownership_runtime",
        3_600,
    ),
    (
        "affiliate_program_compliance_destination_integrity",
        "affiliate_program_compliance_destination_integrity",
        900,
    ),
    (
        "slow_device_network_resource_budget_caching",
        "slow_device_network_resource_budget_caching_runtime",
        3_600,
    ),
)

EXPECTED_POST_APPLY_SURFACES: Final = (
    (
        "production_migration_parity_readback",
        "production_migration_parity_readback",
        900,
    ),
)

# Kept as a compatibility alias for callers that construct pre-publication
# review rounds. Production parity is intentionally not part of this tuple.
EXPECTED_SURFACES: Final = EXPECTED_PRE_PUBLICATION_SURFACES

EXPECTED_PRE_PUBLICATION_POLICY: Final = {
    "required_consecutive_clean_rounds": 2,
    "max_evaluation_age_seconds": 900,
    "max_future_skew_seconds": 300,
}
EXPECTED_POST_APPLY_POLICY: Final = {
    "required_fresh_passes": 1,
    "max_evaluation_age_seconds": 900,
    "max_future_skew_seconds": 300,
}
EXPECTED_POST_APPLY_EXTERNAL_EXECUTION: Final = (
    "deployment",
    "live_read",
    "live_write",
    "production",
    "production_migration_parity_readback",
    "publication",
    "release",
)

# A generic PASS blob is not enough.  Every executed gate must carry one
# substantive output type chosen for that surface in addition to the structured
# command record and gate-result record validated below.
EXPECTED_GATE_EVIDENCE_TYPES: Final = {
    "code_static_and_tests": ("test-report",),
    "editorial_source_integrity": ("source-trace-report",),
    "epistemic_negative_claims_and_calculation_semantics": ("claim-semantics-report",),
    "editorial_language_story_information_architecture": ("editorial-review-report",),
    "editorial_accountability_author_credentials_corrections": (
        "accountability-report",
    ),
    "content_originality_copyright_near_duplicate_risk": ("originality-report",),
    "contact_corrections_operational_deliverability": ("delivery-test-report",),
    "search_intent_cannibalization_orphaning_integrity": (
        "information-architecture-report",
    ),
    "product_selection_lifecycle_support_integrity": ("product-lifecycle-report",),
    "candidate_universe_representativeness_and_brand_blindspots": (
        "candidate-universe-report",
    ),
    "consumer_safety_recall_compatibility_integrity": ("recall-query-report",),
    "smart_device_app_cloud_security_update_eol_privacy": ("cloud-lifecycle-report",),
    "battery_large_appliance_disposal_recycling_transport": (
        "disposal-guidance-report",
    ),
    "freshness_maintenance_ownership_integrity": ("freshness-report",),
    "affiliate_fairness_dark_pattern_runtime": ("dark-pattern-review-report",),
    "legal_disclosure_media_rights_review": ("media-rights-report",),
    "provenance_reproducibility_recovery_integrity": ("roundtrip-provenance-report",),
    "wordpress_backup_rollback_reproducible_restoration": (
        "restoration-rehearsal-report",
    ),
    "dependency_supply_chain_plugin_integrity": ("dependency-integrity-report",),
    "seo_schema_semantics": ("seo-schema-browser-report",),
    "policy_privacy_consent_runtime": ("policy-profile-report",),
    "analytics_data_minimization_accuracy_runtime": ("storage-consent-report",),
    "ui_a11y_keyboard_zoom_runtime": ("a11y-runtime-report",),
    "cognitive_accessibility_japanese_readability_runtime": (
        "readability-review-report",
    ),
    "links_security_headers_runtime": ("link-security-report",),
    "product_media_cta_activation": ("product-activation-report",),
    "search_archive_404_runtime": ("template-browser-report",),
    "browser_resilience_no_js_error_recovery_runtime": (
        "browser-error-recovery-report",
    ),
    "browser_compatibility_restricted_environment_resilience": (
        "restricted-environment-report",
    ),
    "performance_browser_runtime": ("lighthouse-median-report",),
    "task_based_decision_usability_reader_comprehension_research": (
        "task-research-report",
    ),
    "japanese_locale_measurement_semantics_inclusive_language": (
        "locale-measurement-report",
    ),
    "touch_gesture_orientation_400_percent_reflow_target_size_runtime": (
        "touch-reflow-report",
    ),
    "wordpress_public_attack_abuse_surface_runtime": ("wordpress-abuse-report",),
    "operations_observability_incident_ownership_runtime": (
        "observability-rehearsal-report",
    ),
    "affiliate_program_compliance_destination_integrity": (
        "affiliate-destination-report",
    ),
    "slow_device_network_resource_budget_caching_runtime": ("resource-budget-report",),
    "production_migration_parity_readback": ("production-readback-report",),
}

BASELINE_FINDING_SUMMARIES: Final = {
    "code": (
        "Focused, full and tamper tests, publication authorization/default-off and "
        "kill-switch invariants, and secret-detection gates remain independently "
        "unexecuted."
    ),
    "editorial_sources": (
        "Reader-visible candidates/decisions lack a claim/locator trace audit; source-"
        "packet completeness, conflicts, snapshot locators, every contributor locator "
        "for multi-source claims, and required llms.txt absence remain unaudited."
    ),
    "epistemic_negative_claims_and_calculation_semantics": (
        "Negative claims lack explicit official evidence checks; UNKNOWN promotion, "
        "superlatives, and difference calculations across mismatched scope, units, "
        "dimension axes, model, sales state, or time remain unaudited."
    ),
    "editorial_language_story_ia": (
        "First-50-word hook; formal product name at first mention; single takeaway; "
        "comparison-to-judgment-to-action story flow; closing-loop quality; existing ID/"
        "slug and no-new-post invariants; local category-term identity remain unaudited."
    ),
    "editorial_accountability_author_credentials_corrections": (
        "10-article audience/scope/writer/fact-checker/date/no-hands-on and Who/How/Why "
        "fields, reader-visible AI-assistance and independent-audit explanations, no "
        "false credentials, policy/AI links, and byline/schema match are unaudited."
    ),
    "content_originality_copyright_near_duplicate_risk": (
        "All 10 articles lack originality/near-duplicate, quotation-limit, attribution, "
        "and copyright-safe paraphrase audits; third-party blogs are axis exploration "
        "only, never experience/recommendation; Review/AggregateRating are prohibited."
    ),
    "contact_corrections_operational_deliverability": (
        "Contact deliverability for contact@kurashinoshirube.com, correction/update/"
        "history ownership, correction triage and escalation, bounce monitoring, and "
        "response ownership are untested; an assumed address is not operational proof."
    ),
    "search_intent_cannibalization_orphaning": (
        "Search-intent ownership, cannibalization, orphan detection, category and "
        "internal-link intent, and purposeful primary-secondary internal routes across "
        "all existing pages remain unaudited."
    ),
    "product_selection_lifecycle_support": (
        "Final-product seven-axis due diligence is 0/33 complete; reader/audit product "
        "names and sales state, SKU use fit, Japan warranty, maintenance/consumables/"
        "repair, model end/successor, and no-buy/keep conclusions remain unverified."
    ),
    "candidate_universe_representativeness_and_brand_blindspots": (
        "Cross-brand multi-brand official sources, selected+external direct/lifecycle "
        "sets, 4-slot compression, same-axis visible exclusion tradeoffs, brand bias, "
        "dominant-peer role-only exclusion, and price/reward/Rakuten weight zero are "
        "unaudited."
    ),
    "consumer_safety_recall_compatibility": (
        "All 33 selected-product safety reviews are RECHECK_REQUIRED; SKU recall receipts (query/"
        "period/ambiguity) and safety/notice/compatibility/Japan-warranty locators. "
        "Generic pages cannot pass; NONE_FOUND is observed-only; publication blocked."
    ),
    "smart_device_app_cloud_security_update_eol_privacy": (
        "Smart-device app/cloud/account dependencies, offline degradation, data flows, "
        "security-update and vulnerability commitments, and app/cloud/device EOL behavior "
        "remain unverified product by product."
    ),
    "battery_large_appliance_disposal_recycling_transport": (
        "Battery and large-appliance products lack Japan-specific official disposal, "
        "recycling and collection duties, battery removal, damaged-cell handling, and "
        "transport restrictions; generic waste guidance cannot pass."
    ),
    "freshness_maintenance_ownership": (
        "Claim expiry and sales/specification/recall/warranty/model-end/successor "
        "triggers, named recheck owners and cadence, source-snapshot expiry, and "
        "consumables/repair continuity remain unaudited."
    ),
    "affiliate_fairness_dark_patterns": (
        "Comparison independence, commission-neutral selection, conflict disclosure, "
        "equal exposure for all selected products, proof-before-action CTA order, count, "
        "density and prominence, neutral labels, and dark-pattern absence are unaudited."
    ),
    "legal_disclosure_media_rights": (
        "Formal legal review has not been executed; per-article opening monetization-status "
        "disclosure, image/copyright licenses, rights provenance, and product-"
        "misidentification controls remain blocked without asserting legal compliance."
    ),
    "provenance_reproducibility_recovery": (
        "REST-to-DB-to-REST/HTML round-trip; KSES/Gutenberg preservation of class/"
        "data/ARIA/details/table/CTA attributes, acyclic predecessor/successor, "
        "semantic-independent runtime revisions, and reproducible snapshots/generation "
        "remain unaudited."
    ),
    "wordpress_backup_rollback_reproducible_restoration": (
        "Checksum-bound WordPress backup and restore, content/theme/plugin/options "
        "rollback, same-fixture resync idempotency, post-restore verification, cache/CDN "
        "invalidation and old-HTML absence, and RPO/RTO evidence remain unrehearsed."
    ),
    "dependency_supply_chain_plugin_integrity": (
        "Yoast checksum/version pinning, plugin/theme dependency provenance, parent-"
        "theme/PHP/WordPress compatibility, package locks, and supply-chain integrity "
        "have not been independently audited."
    ),
    "seo_schema": (
        "Author/date/tag/attachment/feed/REST exposure and indexability, XML sitemap/"
        "robots, pagination/legacy canonicals, metadata, JSON-LD, html lang, timezone/"
        "date formatting, and taxonomy semantics remain unaudited."
    ),
    "policy_privacy_consent": (
        "Local and production policy profiles, operator/contact statements, Cookie UI, "
        "retention declarations, and cross-profile isolation remain unaudited."
    ),
    "analytics_data_minimization_accuracy": (
        "Actual cookies, Web Storage, IndexedDB, Cache, service workers and analytics, "
        "consent withdrawal, default-off tracking, data minimization, and retention "
        "accuracy remain unaudited."
    ),
    "ui_a11y_keyboard_zoom": (
        "Responsive layout, keyboard and focus behavior, reduced motion, 200% text zoom, "
        "contrast, table header relations for screen readers, and image/control "
        "accessible names remain unaudited."
    ),
    "cognitive_accessibility_japanese_readability": (
        "Japanese readability, understandable labels and decision aids, heading-only "
        "scan quality, overlong headings, repeated CTA pressure, and avoidable cognitive "
        "load remain unaudited."
    ),
    "links_security_headers": (
        "Legacy-slug and trailing-slash redirects, tracking, sponsored/nofollow rel and "
        "opener isolation, final destinations, mixed content, CSP, and security headers "
        "remain unaudited."
    ),
    "product_media_cta_evidence": (
        "37 product-card placements; 33 unique products; 74 CTA; 130 runtime screenshots; "
        "product-misidentification controls; neutral/manufacturer fallback absence; "
        "exactly one hero per page; 10 article-specific header comparison visuals unaudited."
    ),
    "search_archive_404": (
        "Japanese search, zero-result, archive, pagination, category, and 404 behavior "
        "have not been independently audited."
    ),
    "browser_resilience_no_js_error_recovery": (
        "Fixture-only evidence is not runtime proof; JavaScript and no-JavaScript "
        "behavior, console/network failures, error and empty states, state reset, and "
        "user recovery paths have not been independently audited."
    ),
    "browser_compatibility_restricted_environment_resilience": (
        "Target browsers and no-storage/no-cookie/private/restricted-network modes, "
        "third-party blocking, print/no-CSS information retention, font/image/CTA "
        "failure, and recoverable degradation remain untested."
    ),
    "performance_browser": (
        "Repeated mobile performance measurements and current local-browser artifacts "
        "have not been independently executed."
    ),
    "task_based_decision_usability_reader_comprehension": (
        "Representative reader tasks have not measured correct product/no-buy outcomes, "
        "time to decision, misread paths, confidence or decision reversals; static proxy "
        "checks cannot pass this comprehension surface."
    ),
    "japanese_locale_measurement_semantics_inclusive_language": (
        "Japanese units, dimension axes, rounding, tax/sales-region scope, dates, full-/"
        "half-width notation, term consistency, and inclusive non-stereotyping language "
        "remain unaudited."
    ),
    "touch_gesture_orientation_400_percent_reflow_target_size": (
        "Touch and gesture alternatives, portrait/landscape orientation, 400% reflow, "
        "target size/spacing and accidental activation remain untested independently of "
        "keyboard and 200% zoom."
    ),
    "wordpress_public_attack_abuse_surface": (
        "Runtime absence of comment forms/feeds/X-Pingback, XML-RPC and REST users; "
        "oEmbed, admin/auth, CORS/CSRF, uploads/MIME and debug leakage lack local tests "
        "and production readback. Closed seed defaults are not production proof."
    ),
    "operations_observability_incident_ownership": (
        "Broken-link/availability, TLS/domain/email expiry, cron and core/theme/plugin "
        "updates, alert routing, incident ownership, escalation and rollback triggers "
        "remain operationally untested."
    ),
    "affiliate_program_compliance_destination_integrity": (
        "Rakuten program/image terms, redirect chains, referrer/query leakage, SKU/variant "
        "landing consistency, link expiry detection and replacement remain unverified; "
        "formal compliance is not asserted."
    ),
    "slow_device_network_resource_budget_caching": (
        "Slow-device/network request, byte, font, image, server, cache-header and third-"
        "party budgets remain unmeasured independently of median Lighthouse thresholds."
    ),
}

POST_APPLY_FINDING_SUMMARIES: Final = {
    "production_migration_parity_readback": (
        "Production ID/slug/meta/taxonomy/options/menu/media-GUID/permalink parity, dry-run "
        "diff and rollback rehearsal are NOT_EXECUTED; local mappings cannot substitute "
        "and a pre-publication review cannot satisfy this post-apply surface."
    ),
}

EXPECTED_EXTERNAL_EXECUTION: Final = {
    "contact_delivery_operational_test": "NOT_EXECUTED",
    "deployment": "NOT_EXECUTED",
    "independent_reviewer_attestation_verification": "NOT_EXECUTED",
    "legal_review": "NOT_EXECUTED",
    "live_read": "NOT_EXECUTED",
    "live_write": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "production_affiliate_destination_integrity_readback": "NOT_EXECUTED",
    "production_cache_cdn_invalidation_readback": "NOT_EXECUTED",
    "production_consent_runtime_readback": "NOT_EXECUTED",
    "production_content_roundtrip_readback": "NOT_EXECUTED",
    "production_migration_parity_readback": "NOT_EXECUTED",
    "production_observability_readback": "NOT_EXECUTED",
    "production_public_attack_surface_readback": "NOT_EXECUTED",
    "production_robots_indexability_readback": "NOT_EXECUTED",
    "production_seo_schema_readback": "NOT_EXECUTED",
    "production_taxonomy_term_identity": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
}

EXPECTED_ATTESTATION_POLICY_FIXED: Final = {
    "schema": ATTESTATION_SCHEMA,
    "signature_algorithm": ATTESTATION_SIGNATURE_ALGORITHM,
    "canonicalization": ATTESTATION_CANONICALIZATION,
    "independence_statement": INDEPENDENCE_STATEMENT,
    "max_validity_seconds": 3_600,
}

EXPECTED_EDITORIAL_EVIDENCE_POLICY: Final = {
    "third_party_blog_use": "SELECTION_AXIS_DISCOVERY_ONLY",
    "third_party_blog_recommendation_evidence": "PROHIBITED",
    "third_party_experience_as_editorial_hands_on": "PROHIBITED",
    "third_party_report_review_or_best_evidence": "PROHIBITED",
    "quotation_policy": "EXPLICIT_ATTRIBUTED_MINIMUM_NECESSARY",
    "editorial_hands_on_label_requirement": (
        "DIRECT_USE_ACQUISITION_CONFLICT_PERIOD_ENVIRONMENT_METHOD_"
        "ORIGINAL_EVIDENCE_REQUIRED"
    ),
    "third_party_report_required_fields": (
        "EXACT_MODEL_PUBLISHER_PUBLISHED_DATE_CHECKED_DATE_USE_CONDITIONS_"
        "SOURCE_URL_LOCATOR"
    ),
    "review_schema_for_non_hands_on": "PROHIBITED",
}

EDITORIAL_EVIDENCE_REGISTER_SCHEMA: Final = "RAOS_EDITORIAL_EVIDENCE_REGISTER_V1"
EDITORIAL_EVIDENCE_REVIEWED_ON: Final = "2026-09-01"
NON_HANDS_ON_MODE: Final = "OFFICIAL_SPEC_COMPARISON_NON_HANDS_ON"
EXPECTED_ARTICLE_SLUGS: Final = tuple(
    sorted(
        (
            "anker-solix-c300-c800-c1000-differences",
            "carry-on-suitcase-comparison",
            "carry-on-suitcase-under-100-seats",
            "compact-robot-vacuum-shortlist",
            "countertop-dishwasher-for-small-households",
            "front-open-carry-on-suitcase-with-stopper",
            "lightweight-carry-on-suitcase-under-3kg",
            "portable-power-station-guide",
            "roomba-mini-vs-switchbot-k11-pro",
            "solota-vs-rakua-mini-plus",
        )
    )
)


class QualityAuditFailure(RuntimeError):
    """A stable fail-closed validation error."""


def _fail(code: str) -> NoReturn:
    raise QualityAuditFailure(code)


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("QUALITY_AUDIT_CANONICAL_JSON_INVALID")


def sha256_value(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _exact_keys(value: dict[str, Any], keys: set[str], code: str) -> None:
    if set(value) != keys:
        _fail(code)


def _identifier(value: object, code: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _sha256(value: object, code: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _timestamp(value: object, code: str) -> datetime:
    if type(value) is not str or TIMESTAMP_RE.fullmatch(value) is None:
        _fail(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail(code)


def _date(value: object, code: str) -> datetime:
    if type(value) is not str or DATE_RE.fullmatch(value) is None:
        _fail(code)
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        _fail(code)


def _nonempty_text(value: object, code: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        _fail(code)
    return value


def _article_slug(value: object, code: str) -> str:
    if type(value) is not str or ARTICLE_SLUG_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _https_url(value: object, code: str) -> str:
    raw = _nonempty_text(value, code)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        _fail(code)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        _fail(code)
    return raw


def timestamp_text(value: datetime) -> str:
    if value.tzinfo is None:
        _fail("QUALITY_AUDIT_TIMESTAMP_INVALID")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_regular_bytes(
    path: Path, *, maximum: int = MAX_DOCUMENT_BYTES, allow_empty: bool = False
) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("QUALITY_AUDIT_DOCUMENT_MISSING")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > maximum
    ):
        _fail("QUALITY_AUDIT_DOCUMENT_INVALID")
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("QUALITY_AUDIT_DOCUMENT_INVALID")
    if (not raw and not allow_empty) or len(raw) > maximum:
        _fail("QUALITY_AUDIT_DOCUMENT_INVALID")
    return raw


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("QUALITY_AUDIT_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_bytes(path)
    try:
        value = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except json.JSONDecodeError, UnicodeError, RecursionError, ValueError:
        _fail("QUALITY_AUDIT_JSON_INVALID")
    return _mapping(value, "QUALITY_AUDIT_JSON_INVALID"), raw


def _decode_canonical_base64(value: object, *, expected_bytes: int, code: str) -> bytes:
    if type(value) is not str or not value:
        _fail(code)
    try:
        decoded = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        _fail(code)
    if (
        len(decoded) != expected_bytes
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        _fail(code)
    return decoded


def _read_secure_exact_path(path: Path, *, maximum: int) -> bytes:
    """Read a caller-supplied absolute file without following symlinks.

    Attestation inputs are not secrets, but treating their path as an exact
    owner-controlled boundary prevents cwd confusion, link substitution, and
    group/world-writable evidence from authorizing completion.
    """

    if not path.is_absolute() or len(os.fspath(path)) > 4_096:
        _fail("QUALITY_AUDIT_ATTESTATION_PATH_INVALID")
    try:
        metadata = path.lstat()
    except OSError:
        _fail("QUALITY_AUDIT_ATTESTATION_FILE_MISSING")
    if stat.S_ISLNK(metadata.st_mode):
        _fail("QUALITY_AUDIT_ATTESTATION_SYMLINK_REFUSED")
    try:
        if path.resolve(strict=True) != path:
            _fail("QUALITY_AUDIT_ATTESTATION_SYMLINK_REFUSED")
    except OSError:
        _fail("QUALITY_AUDIT_ATTESTATION_FILE_INVALID")
    if not stat.S_ISREG(metadata.st_mode):
        _fail("QUALITY_AUDIT_ATTESTATION_FILE_INVALID")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        _fail("QUALITY_AUDIT_ATTESTATION_MODE_INVALID")
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        _fail("QUALITY_AUDIT_ATTESTATION_SIZE_INVALID")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _fail("QUALITY_AUDIT_ATTESTATION_FILE_INVALID")
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
            or opened.st_size != metadata.st_size
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            _fail("QUALITY_AUDIT_ATTESTATION_FILE_INVALID")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != opened.st_size or len(raw) > maximum:
            _fail("QUALITY_AUDIT_ATTESTATION_SIZE_INVALID")
        return raw
    except OSError:
        _fail("QUALITY_AUDIT_ATTESTATION_FILE_INVALID")
    finally:
        os.close(descriptor)


def _read_canonical_attestation(path: Path) -> dict[str, Any]:
    raw = _read_secure_exact_path(path, maximum=MAX_ATTESTATION_BYTES)
    try:
        value = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except json.JSONDecodeError, UnicodeError, RecursionError, ValueError:
        _fail("QUALITY_AUDIT_ATTESTATION_JSON_INVALID")
    payload = _mapping(value, "QUALITY_AUDIT_ATTESTATION_JSON_INVALID")
    if raw != canonical_json(payload) + b"\n":
        _fail("QUALITY_AUDIT_ATTESTATION_CANONICAL_JSON_INVALID")
    return payload


def _read_detached_signature(path: Path) -> bytes:
    raw = _read_secure_exact_path(path, maximum=MAX_ATTESTATION_SIGNATURE_BYTES)
    try:
        text = raw.decode("ascii")
    except UnicodeError:
        _fail("QUALITY_AUDIT_ATTESTATION_SIGNATURE_ENCODING_INVALID")
    if not text.endswith("\n") or "\n" in text[:-1]:
        _fail("QUALITY_AUDIT_ATTESTATION_SIGNATURE_ENCODING_INVALID")
    return _decode_canonical_base64(
        text[:-1],
        expected_bytes=ED25519_SIGNATURE_BYTES,
        code="QUALITY_AUDIT_ATTESTATION_SIGNATURE_ENCODING_INVALID",
    )


def validate_editorial_evidence_schema(schema: dict[str, Any]) -> None:
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("$id")
        != "https://kurashinoshirube.com/contracts/editorial-evidence.schema.json"
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or schema.get("required")
        != ["schema", "version", "reviewed_on", "article_modes", "records"]
    ):
        _fail("EDITORIAL_EVIDENCE_SCHEMA_INVALID")
    definitions = _mapping(schema.get("$defs"), "EDITORIAL_EVIDENCE_SCHEMA_INVALID")
    if set(definitions) != {"common", "thirdPartyReport", "editorialHandsOn"}:
        _fail("EDITORIAL_EVIDENCE_SCHEMA_INVALID")
    expected_required = {
        "thirdPartyReport": {
            "record_id",
            "evidence_kind",
            "article_slug",
            "exact_model",
            "publisher",
            "published_date",
            "checked_date",
            "usage_conditions",
            "source_url",
            "locator",
            "attribution_label",
            "recommendation_use",
            "review_label_use",
            "best_claim_use",
        },
        "editorialHandsOn": {
            "record_id",
            "evidence_kind",
            "article_slug",
            "exact_model",
            "checked_date",
            "direct_use_confirmed",
            "acquisition_route",
            "provided_or_loaned",
            "conflict_disclosure",
            "usage_start_date",
            "usage_end_date",
            "usage_environment",
            "verification_method",
            "original_device_evidence_refs",
        },
    }
    for definition_name, required_fields in expected_required.items():
        definition = _mapping(
            definitions.get(definition_name), "EDITORIAL_EVIDENCE_SCHEMA_INVALID"
        )
        all_of = _list(definition.get("allOf"), "EDITORIAL_EVIDENCE_SCHEMA_INVALID")
        if len(all_of) != 2:
            _fail("EDITORIAL_EVIDENCE_SCHEMA_INVALID")
        strict_shape = _mapping(all_of[1], "EDITORIAL_EVIDENCE_SCHEMA_INVALID")
        required = _list(
            strict_shape.get("required"), "EDITORIAL_EVIDENCE_SCHEMA_INVALID"
        )
        properties = _mapping(
            strict_shape.get("properties"), "EDITORIAL_EVIDENCE_SCHEMA_INVALID"
        )
        if (
            strict_shape.get("additionalProperties") is not False
            or set(required) != required_fields
            or set(properties) != required_fields
        ):
            _fail("EDITORIAL_EVIDENCE_SCHEMA_INVALID")
    third_properties = cast(
        dict[str, Any],
        cast(list[object], definitions["thirdPartyReport"]["allOf"])[1]["properties"],
    )
    hands_on_properties = cast(
        dict[str, Any],
        cast(list[object], definitions["editorialHandsOn"]["allOf"])[1]["properties"],
    )
    if (
        third_properties["evidence_kind"].get("const") != "THIRD_PARTY_REPORT"
        or third_properties["attribution_label"].get("const") != "第三者による報告"
        or third_properties["recommendation_use"].get("const") is not False
        or third_properties["review_label_use"].get("const") is not False
        or third_properties["best_claim_use"].get("const") is not False
        or hands_on_properties["evidence_kind"].get("const") != "EDITORIAL_HANDS_ON"
        or hands_on_properties["direct_use_confirmed"].get("const") is not True
    ):
        _fail("EDITORIAL_EVIDENCE_SCHEMA_INVALID")


def validate_editorial_evidence_record(
    raw_record: object, *, article_slugs: set[str]
) -> str:
    record = _mapping(raw_record, "EDITORIAL_EVIDENCE_RECORD_INVALID")
    kind = record.get("evidence_kind")
    common_keys = {
        "record_id",
        "evidence_kind",
        "article_slug",
        "exact_model",
        "checked_date",
    }
    if kind == "THIRD_PARTY_REPORT":
        required_keys = common_keys | {
            "publisher",
            "published_date",
            "usage_conditions",
            "source_url",
            "locator",
            "attribution_label",
            "recommendation_use",
            "review_label_use",
            "best_claim_use",
        }
        _exact_keys(record, required_keys, "EDITORIAL_EVIDENCE_RECORD_INVALID")
        _nonempty_text(record["publisher"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        published = _date(record["published_date"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        _nonempty_text(record["usage_conditions"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        _https_url(record["source_url"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        _nonempty_text(record["locator"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        if (
            record["attribution_label"] != "第三者による報告"
            or record["recommendation_use"] is not False
            or record["review_label_use"] is not False
            or record["best_claim_use"] is not False
        ):
            _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    elif kind == "EDITORIAL_HANDS_ON":
        required_keys = common_keys | {
            "direct_use_confirmed",
            "acquisition_route",
            "provided_or_loaned",
            "conflict_disclosure",
            "usage_start_date",
            "usage_end_date",
            "usage_environment",
            "verification_method",
            "original_device_evidence_refs",
        }
        _exact_keys(record, required_keys, "EDITORIAL_EVIDENCE_RECORD_INVALID")
        if (
            record["direct_use_confirmed"] is not True
            or type(record["provided_or_loaned"]) is not bool
        ):
            _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
        for field in (
            "acquisition_route",
            "conflict_disclosure",
            "usage_environment",
            "verification_method",
        ):
            _nonempty_text(record[field], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        usage_start = _date(
            record["usage_start_date"], "EDITORIAL_EVIDENCE_RECORD_INVALID"
        )
        usage_end = _date(record["usage_end_date"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
        refs = _list(
            record["original_device_evidence_refs"],
            "EDITORIAL_EVIDENCE_RECORD_INVALID",
        )
        if not refs:
            _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
        evidence_paths: set[str] = set()
        evidence_hashes: set[str] = set()
        for raw_reference in refs:
            reference = _mapping(raw_reference, "EDITORIAL_EVIDENCE_RECORD_INVALID")
            _exact_keys(
                reference,
                {"kind", "path", "sha256"},
                "EDITORIAL_EVIDENCE_RECORD_INVALID",
            )
            if reference["kind"] not in {
                "PHOTO",
                "VIDEO",
                "AUDIO",
                "MEASUREMENT_LOG",
            }:
                _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
            evidence_path = _evidence_relative_path(
                reference["path"], prefix="evidence", suffix=None
            )
            evidence_hash = _sha256(
                reference["sha256"], "EDITORIAL_EVIDENCE_RECORD_INVALID"
            )
            if evidence_path in evidence_paths or evidence_hash in evidence_hashes:
                _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
            evidence_paths.add(evidence_path)
            evidence_hashes.add(evidence_hash)
        if usage_end < usage_start:
            _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    else:
        _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    record_id = _identifier(record["record_id"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
    article_slug = _article_slug(
        record["article_slug"], "EDITORIAL_EVIDENCE_RECORD_INVALID"
    )
    if article_slug not in article_slugs:
        _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    _nonempty_text(record["exact_model"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
    checked = _date(record["checked_date"], "EDITORIAL_EVIDENCE_RECORD_INVALID")
    if kind == "THIRD_PARTY_REPORT" and checked < published:
        _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    if kind == "EDITORIAL_HANDS_ON" and checked < usage_end:
        _fail("EDITORIAL_EVIDENCE_RECORD_INVALID")
    return record_id


def validate_editorial_evidence_register(register: dict[str, Any]) -> None:
    _exact_keys(
        register,
        {"schema", "version", "reviewed_on", "article_modes", "records"},
        "EDITORIAL_EVIDENCE_REGISTER_INVALID",
    )
    if (
        register["schema"] != EDITORIAL_EVIDENCE_REGISTER_SCHEMA
        or register["version"] != 1
        or register["reviewed_on"] != EDITORIAL_EVIDENCE_REVIEWED_ON
    ):
        _fail("EDITORIAL_EVIDENCE_REGISTER_INVALID")
    reviewed_on = _date(register["reviewed_on"], "EDITORIAL_EVIDENCE_REGISTER_INVALID")
    modes = _list(register["article_modes"], "EDITORIAL_EVIDENCE_REGISTER_INVALID")
    observed_slugs: list[str] = []
    mode_by_slug: dict[str, str] = {}
    for raw_mode in modes:
        mode = _mapping(raw_mode, "EDITORIAL_EVIDENCE_REGISTER_INVALID")
        _exact_keys(
            mode,
            {"article_slug", "evidence_mode"},
            "EDITORIAL_EVIDENCE_REGISTER_INVALID",
        )
        slug = _article_slug(
            mode["article_slug"], "EDITORIAL_EVIDENCE_REGISTER_INVALID"
        )
        if mode["evidence_mode"] != NON_HANDS_ON_MODE or slug in mode_by_slug:
            _fail("EDITORIAL_EVIDENCE_REGISTER_INVALID")
        observed_slugs.append(slug)
        mode_by_slug[slug] = cast(str, mode["evidence_mode"])
    if tuple(observed_slugs) != EXPECTED_ARTICLE_SLUGS:
        _fail("EDITORIAL_EVIDENCE_REGISTER_INVALID")
    records = _list(register["records"], "EDITORIAL_EVIDENCE_REGISTER_INVALID")
    if len(records) > 100:
        _fail("EDITORIAL_EVIDENCE_REGISTER_INVALID")
    record_ids: set[str] = set()
    for raw_record in records:
        record_id = validate_editorial_evidence_record(
            raw_record, article_slugs=set(mode_by_slug)
        )
        record = cast(dict[str, Any], raw_record)
        if (
            record_id in record_ids
            or record["evidence_kind"] == "EDITORIAL_HANDS_ON"
            or _date(record["checked_date"], "EDITORIAL_EVIDENCE_REGISTER_INVALID")
            > reviewed_on
        ):
            _fail("EDITORIAL_EVIDENCE_REGISTER_INVALID")
        record_ids.add(record_id)


def validate_editorial_article_surfaces(
    register: dict[str, Any], article_root: Path = DEFAULT_ARTICLE_FIXTURE_ROOT
) -> None:
    validate_editorial_evidence_register(register)
    try:
        paths = sorted(article_root.glob("*.html"), key=lambda path: path.name)
    except OSError:
        _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
    if tuple(path.stem for path in paths) != EXPECTED_ARTICLE_SLUGS:
        _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
    records_by_slug: dict[str, list[dict[str, Any]]] = {
        slug: [] for slug in EXPECTED_ARTICLE_SLUGS
    }
    for record in cast(list[dict[str, Any]], register["records"]):
        records_by_slug[record["article_slug"]].append(record)
    for path in paths:
        raw = _read_regular_bytes(path)
        try:
            markup = raw.decode("utf-8")
        except UnicodeDecodeError:
            _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
        first_hand_label = (
            "未実施（型番・販売表示の確認案内）"
            if path.stem == "solota-vs-rakua-mini-plus"
            else "未実施（公式仕様比較）"
        )
        if (
            markup.count("<dt>実機確認</dt>") != 1
            or markup.count(first_hand_label) != 1
            or "<blockquote" in markup
            or "AggregateRating" in markup
            or re.search(r'"@type"\s*:\s*"(?:Product|Offer|Review)"', markup)
        ):
            _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
        without_negative_labels = markup.replace("実機レビューではありません", "")
        for marker in (
            "実機レビュー",
            "使って分かった",
            "実際に使って",
            "体験レビュー",
        ):
            if marker in without_negative_labels:
                _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
        article_records = records_by_slug[path.stem]
        third_party_ids = {
            record["record_id"]
            for record in article_records
            if record["evidence_kind"] == "THIRD_PARTY_REPORT"
        }
        visible_ids = set(
            re.findall(r'data-raos-evidence-record-id="([a-z0-9._-]+)"', markup)
        )
        if visible_ids != third_party_ids:
            _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")
        if third_party_ids and "第三者による報告" not in markup:
            _fail("EDITORIAL_EVIDENCE_ARTICLE_SURFACE_INVALID")


def load_editorial_evidence_register(
    register_path: Path = DEFAULT_EDITORIAL_EVIDENCE_REGISTER_PATH,
    schema_path: Path = DEFAULT_EDITORIAL_EVIDENCE_SCHEMA_PATH,
) -> dict[str, Any]:
    schema, _schema_raw = read_json(schema_path)
    validate_editorial_evidence_schema(schema)
    register, _register_raw = read_json(register_path)
    validate_editorial_evidence_register(register)
    return register


def _evidence_relative_path(value: object, *, prefix: str, suffix: str | None) -> str:
    if (
        type(value) is not str
        or EVIDENCE_PATH_RE.fullmatch(value) is None
        or "\\" in value
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_PATH_INVALID")
    path = Path(value)
    if (
        path.is_absolute()
        or len(path.parts) < 2
        or path.parts[0] != prefix
        or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts)
        or (suffix is not None and path.suffix != suffix)
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_PATH_INVALID")
    return path.as_posix()


def _read_evidence_regular_bytes(
    evidence_root: Path,
    relative: str,
    *,
    maximum: int,
) -> bytes:
    try:
        root_metadata = evidence_root.lstat()
    except OSError:
        _fail("QUALITY_AUDIT_EVIDENCE_ROOT_MISSING")
    if evidence_root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        _fail("QUALITY_AUDIT_EVIDENCE_ROOT_INVALID")

    current = evidence_root
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError:
            _fail("QUALITY_AUDIT_EVIDENCE_FILE_MISSING")
        if current.is_symlink():
            _fail("QUALITY_AUDIT_EVIDENCE_SYMLINK_REFUSED")
        if index < len(parts) - 1:
            if not stat.S_ISDIR(metadata.st_mode):
                _fail("QUALITY_AUDIT_EVIDENCE_PATH_INVALID")
        elif not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= maximum:
            _fail("QUALITY_AUDIT_EVIDENCE_FILE_INVALID")
    try:
        raw = current.read_bytes()
    except OSError:
        _fail("QUALITY_AUDIT_EVIDENCE_FILE_INVALID")
    if not raw or len(raw) > maximum:
        _fail("QUALITY_AUDIT_EVIDENCE_FILE_INVALID")
    return raw


def _json_from_evidence(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except json.JSONDecodeError, UnicodeError, RecursionError, ValueError:
        _fail(code)
    return _mapping(value, code)


def evidence_manifest_aggregate_sha256(manifest: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in manifest.items() if key != "aggregate_sha256"
    }
    return sha256_value(payload)


def seal_evidence_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(manifest)
    sealed.pop("aggregate_sha256", None)
    sealed["aggregate_sha256"] = evidence_manifest_aggregate_sha256(sealed)
    return sealed


def _validate_relative_path(value: object) -> str:
    if type(value) is not str or not value or "\\" in value:
        _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
    if path.parts[0] in {".git", ".secrets", "output", "tmp"}:
        _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
    return path.as_posix()


def _trusted_reviewer_keys(contract: dict[str, Any]) -> dict[str, dict[str, str]]:
    policy = _mapping(
        contract["independent_reviewer_attestation"],
        "QUALITY_AUDIT_ATTESTATION_POLICY_INVALID",
    )
    _exact_keys(
        policy,
        {*EXPECTED_ATTESTATION_POLICY_FIXED, "trusted_reviewer_keys"},
        "QUALITY_AUDIT_ATTESTATION_POLICY_INVALID",
    )
    if any(
        policy[key] != expected
        for key, expected in EXPECTED_ATTESTATION_POLICY_FIXED.items()
    ):
        _fail("QUALITY_AUDIT_ATTESTATION_POLICY_INVALID")
    raw_keys = _list(
        policy["trusted_reviewer_keys"],
        "QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
    )
    if len(raw_keys) > MAX_TRUSTED_REVIEWER_KEYS:
        _fail("QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID")

    trusted: dict[str, dict[str, str]] = {}
    reviewer_ids: set[str] = set()
    public_keys: set[bytes] = set()
    for raw_key in raw_keys:
        key = _mapping(raw_key, "QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID")
        _exact_keys(
            key,
            {
                "reviewer_key_id",
                "reviewer_id",
                "signature_algorithm",
                "public_key_base64",
            },
            "QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
        )
        key_id = _identifier(
            key["reviewer_key_id"],
            "QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
        )
        reviewer_id = _identifier(
            key["reviewer_id"],
            "QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
        )
        if key["signature_algorithm"] != ATTESTATION_SIGNATURE_ALGORITHM:
            _fail("QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID")
        public_key = _decode_canonical_base64(
            key["public_key_base64"],
            expected_bytes=ED25519_PUBLIC_KEY_BYTES,
            code="QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
        )
        if (
            key_id in trusted
            or reviewer_id in reviewer_ids
            or public_key in public_keys
        ):
            _fail("QUALITY_AUDIT_ATTESTATION_TRUST_STORE_DUPLICATE")
        trusted[key_id] = cast(dict[str, str], key)
        reviewer_ids.add(reviewer_id)
        public_keys.add(public_key)
    return trusted


def _validate_contract_surfaces(
    value: object,
    expected_surfaces: tuple[tuple[str, str, int], ...],
) -> None:
    surfaces = _list(value, "QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
    if len(surfaces) != len(expected_surfaces):
        _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
    for row, expected in zip(surfaces, expected_surfaces, strict=True):
        surface = _mapping(row, "QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
        _exact_keys(
            surface,
            {
                "surface_id",
                "gate_id",
                "max_age_seconds",
                "required_evidence_types",
            },
            "QUALITY_AUDIT_CONTRACT_SURFACES_INVALID",
        )
        evidence_types = _list(
            surface["required_evidence_types"],
            "QUALITY_AUDIT_CONTRACT_SURFACES_INVALID",
        )
        if any(
            type(evidence_type) is not str
            or EVIDENCE_TYPE_RE.fullmatch(evidence_type) is None
            for evidence_type in evidence_types
        ):
            _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
        if (
            surface["surface_id"],
            surface["gate_id"],
            surface["max_age_seconds"],
        ) != expected:
            _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
        if tuple(evidence_types) != EXPECTED_GATE_EVIDENCE_TYPES[expected[1]]:
            _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")


def validate_contract(contract: dict[str, Any]) -> None:
    _exact_keys(
        contract,
        {
            "schema",
            "version",
            "fingerprint_algorithm",
            "hash_algorithm",
            "editorial_evidence_policy",
            "independent_reviewer_attestation",
            "fingerprint_groups",
            "audit_phases",
            "external_execution",
        },
        "QUALITY_AUDIT_CONTRACT_SHAPE_INVALID",
    )
    if (
        contract["schema"] != CONTRACT_SCHEMA
        or contract["version"] != VERSION
        or contract["fingerprint_algorithm"] != FINGERPRINT_ALGORITHM
        or contract["hash_algorithm"] != HASH_ALGORITHM
        or contract["editorial_evidence_policy"] != EXPECTED_EDITORIAL_EVIDENCE_POLICY
        or contract["external_execution"] != EXPECTED_EXTERNAL_EXECUTION
    ):
        _fail("QUALITY_AUDIT_CONTRACT_INVALID")

    _trusted_reviewer_keys(contract)

    groups = _list(
        contract["fingerprint_groups"], "QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID"
    )
    expected_group_ids = list(EXPECTED_FINGERPRINT_INPUTS)
    if len(groups) != len(expected_group_ids):
        _fail("QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID")
    for row, expected_id in zip(groups, expected_group_ids, strict=True):
        group = _mapping(row, "QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID")
        _exact_keys(
            group,
            {"fingerprint_id", "inputs"},
            "QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID",
        )
        inputs = _list(group["inputs"], "QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID")
        normalized = tuple(_validate_relative_path(item) for item in inputs)
        if (
            group["fingerprint_id"] != expected_id
            or normalized != EXPECTED_FINGERPRINT_INPUTS[expected_id]
            or len(set(normalized)) != len(normalized)
        ):
            _fail("QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID")

    phases = _mapping(contract["audit_phases"], "QUALITY_AUDIT_CONTRACT_PHASES_INVALID")
    _exact_keys(
        phases,
        {"pre_publication", "post_apply"},
        "QUALITY_AUDIT_CONTRACT_PHASES_INVALID",
    )
    pre_publication = _mapping(
        phases["pre_publication"], "QUALITY_AUDIT_CONTRACT_PHASES_INVALID"
    )
    _exact_keys(
        pre_publication,
        {"phase_id", "completion_state", "required_surfaces", "completion_policy"},
        "QUALITY_AUDIT_CONTRACT_PHASES_INVALID",
    )
    post_apply = _mapping(phases["post_apply"], "QUALITY_AUDIT_CONTRACT_PHASES_INVALID")
    _exact_keys(
        post_apply,
        {
            "phase_id",
            "completion_state",
            "required_surfaces",
            "completion_policy",
            "required_external_execution",
        },
        "QUALITY_AUDIT_CONTRACT_PHASES_INVALID",
    )
    if (
        pre_publication["phase_id"] != PRE_PUBLICATION_PHASE_ID
        or pre_publication["completion_state"] != PRE_PUBLICATION_COMPLETION_STATE
        or pre_publication["completion_policy"] != EXPECTED_PRE_PUBLICATION_POLICY
        or post_apply["phase_id"] != POST_APPLY_PHASE_ID
        or post_apply["completion_state"] != POST_APPLY_COMPLETION_STATE
        or post_apply["completion_policy"] != EXPECTED_POST_APPLY_POLICY
        or tuple(
            _list(
                post_apply["required_external_execution"],
                "QUALITY_AUDIT_CONTRACT_PHASES_INVALID",
            )
        )
        != EXPECTED_POST_APPLY_EXTERNAL_EXECUTION
    ):
        _fail("QUALITY_AUDIT_CONTRACT_PHASES_INVALID")
    _validate_contract_surfaces(
        pre_publication["required_surfaces"], EXPECTED_PRE_PUBLICATION_SURFACES
    )
    _validate_contract_surfaces(
        post_apply["required_surfaces"], EXPECTED_POST_APPLY_SURFACES
    )
    if set(BASELINE_FINDING_SUMMARIES) != {
        surface_id
        for surface_id, _gate_id, _max_age in EXPECTED_PRE_PUBLICATION_SURFACES
    } or set(POST_APPLY_FINDING_SUMMARIES) != {
        surface_id for surface_id, _gate_id, _max_age in EXPECTED_POST_APPLY_SURFACES
    }:
        _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")
    if set(EXPECTED_GATE_EVIDENCE_TYPES) != {
        gate_id
        for _surface_id, gate_id, _max_age in (
            *EXPECTED_PRE_PUBLICATION_SURFACES,
            *EXPECTED_POST_APPLY_SURFACES,
        )
    }:
        _fail("QUALITY_AUDIT_CONTRACT_SURFACES_INVALID")


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> tuple[dict[str, Any], str]:
    contract, raw = read_json(path)
    validate_contract(contract)
    return contract, _sha256_bytes(raw)


def _phase_contract(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    phases = _mapping(contract["audit_phases"], "QUALITY_AUDIT_CONTRACT_PHASES_INVALID")
    key = "pre_publication" if phase == PRE_PUBLICATION_PHASE_ID else "post_apply"
    return _mapping(phases[key], "QUALITY_AUDIT_CONTRACT_PHASES_INVALID")


def _fingerprint_files(
    repository_root: Path, inputs: tuple[str, ...]
) -> list[dict[str, object]]:
    try:
        root = repository_root.resolve(strict=True)
    except OSError:
        _fail("QUALITY_AUDIT_REPOSITORY_ROOT_INVALID")
    if not root.is_dir():
        _fail("QUALITY_AUDIT_REPOSITORY_ROOT_INVALID")
    files: dict[str, Path] = {}
    for raw_input in inputs:
        relative = _validate_relative_path(raw_input)
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except OSError:
            _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_MISSING")
        if candidate.is_symlink():
            _fail("QUALITY_AUDIT_FINGERPRINT_SYMLINK_REFUSED")
        if stat.S_ISREG(metadata.st_mode):
            candidates = [candidate]
        elif stat.S_ISDIR(metadata.st_mode):
            candidates = []
            for child in sorted(candidate.rglob("*"), key=lambda path: path.as_posix()):
                if child.is_symlink():
                    _fail("QUALITY_AUDIT_FINGERPRINT_SYMLINK_REFUSED")
                if "__pycache__" in child.parts or child.suffix == ".pyc":
                    continue
                try:
                    child_metadata = child.lstat()
                except OSError:
                    _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
                if stat.S_ISREG(child_metadata.st_mode):
                    candidates.append(child)
                elif not stat.S_ISDIR(child_metadata.st_mode):
                    _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
        else:
            _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
        for child in candidates:
            try:
                resolved = child.resolve(strict=True)
                relative_child = resolved.relative_to(root).as_posix()
                child_metadata = child.lstat()
            except OSError, ValueError:
                _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
            if (
                resolved != child.absolute()
                or not stat.S_ISREG(child_metadata.st_mode)
                or child_metadata.st_size > MAX_FINGERPRINT_FILE_BYTES
                or relative_child in files
            ):
                _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
            files[relative_child] = child
            if len(files) > MAX_FINGERPRINT_FILES:
                _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")
    if not files:
        _fail("QUALITY_AUDIT_FINGERPRINT_INPUT_INVALID")

    rows: list[dict[str, object]] = []
    for relative, path in sorted(files.items()):
        raw = _read_regular_bytes(
            path, maximum=MAX_FINGERPRINT_FILE_BYTES, allow_empty=True
        )
        rows.append({"path": relative, "sha256": _sha256_bytes(raw), "size": len(raw)})
    return rows


def repository_fingerprints(
    contract: dict[str, Any], repository_root: Path = REPOSITORY_ROOT
) -> dict[str, str]:
    validate_contract(contract)
    result: dict[str, str] = {}
    for group in contract["fingerprint_groups"]:
        group_id = str(group["fingerprint_id"])
        rows = _fingerprint_files(repository_root, tuple(group["inputs"]))
        result[group_id] = sha256_value(
            {
                "algorithm": FINGERPRINT_ALGORITHM,
                "files": rows,
                "fingerprint_id": group_id,
            }
        )
    return result


def fingerprint_bundle_sha256(fingerprints: dict[str, str]) -> str:
    if list(fingerprints) != list(EXPECTED_FINGERPRINT_INPUTS) or any(
        SHA256_RE.fullmatch(value) is None for value in fingerprints.values()
    ):
        _fail("QUALITY_AUDIT_FINGERPRINTS_INVALID")
    return sha256_value(
        {"algorithm": FINGERPRINT_ALGORITHM, "fingerprints": fingerprints}
    )


def receipt_sha256(receipt: dict[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return sha256_value(payload)


def round_sha256(round_row: dict[str, Any]) -> str:
    payload = {key: value for key, value in round_row.items() if key != "round_sha256"}
    return sha256_value(payload)


def ledger_sha256(ledger: dict[str, Any]) -> str:
    payload = {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    return sha256_value(payload)


def seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(receipt)
    sealed.pop("receipt_sha256", None)
    sealed["receipt_sha256"] = receipt_sha256(sealed)
    return sealed


def seal_round(round_row: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(round_row)
    sealed.pop("round_sha256", None)
    sealed["round_sha256"] = round_sha256(sealed)
    return sealed


def _open_actionable_count(findings: list[dict[str, Any]]) -> int:
    return sum(
        1
        for finding in findings
        if finding.get("actionable") is True and finding.get("status") == "OPEN"
    )


def _round_is_clean(round_row: dict[str, Any]) -> bool:
    return (
        round_row.get("status") == "PASS"
        and round_row.get("actionable_finding_count") == 0
        and all(
            surface.get("execution_status") == "EXECUTED"
            and surface.get("result") == "PASS"
            for surface in round_row.get("surfaces", [])
        )
        and all(
            receipt.get("status") == "PASS" and receipt.get("freshness") == "FRESH"
            for receipt in round_row.get("gate_receipts", [])
        )
    )


def completion_for_rounds(
    rounds: list[dict[str, Any]],
    repository_values: dict[str, str],
    *,
    reviewer_attestation_verified: bool = False,
) -> dict[str, Any]:
    current_bundle = fingerprint_bundle_sha256(repository_values)
    streak = 0
    streak_bundle: str | None = None
    drift_reset = False
    for round_row in rounds:
        if not _round_is_clean(round_row):
            streak = 0
            streak_bundle = None
            drift_reset = False
            continue
        bundle = str(round_row.get("fingerprint_bundle_sha256", ""))
        if bundle == streak_bundle:
            streak += 1
        else:
            drift_reset = streak_bundle is not None
            streak = 1
            streak_bundle = bundle

    complete = (
        streak >= 2
        and bool(rounds)
        and rounds[-1].get("fingerprints") == repository_values
        and streak_bundle == current_bundle
        and reviewer_attestation_verified
    )
    reasons: list[str] = []
    if not complete:
        if not rounds or not _round_is_clean(rounds[-1]):
            reasons.append("LATEST_ROUND_NOT_CLEAN")
        if drift_reset and streak == 1:
            reasons.append("FINGERPRINT_DRIFT_RESET")
        if streak < 2:
            reasons.append("TWO_CONSECUTIVE_CLEAN_ROUNDS_REQUIRED")
        if not reviewer_attestation_verified:
            reasons.append("INDEPENDENT_REVIEWER_ATTESTATION_NOT_VERIFIED")
    return {
        "audit_phase": PRE_PUBLICATION_PHASE_ID,
        "status": "COMPLETE" if complete else "BLOCKED",
        "completion_state": (
            PRE_PUBLICATION_COMPLETION_STATE if complete else "BLOCKED"
        ),
        "production_parity_state": POST_APPLY_PENDING_STATE,
        "required_consecutive_clean_rounds": 2,
        "consecutive_clean_rounds": streak,
        "latest_round_sha256": rounds[-1]["round_sha256"] if rounds else None,
        "fingerprint_bundle_sha256": current_bundle,
        "reason_codes": reasons,
    }


def seal_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(ledger)
    sealed.pop("ledger_sha256", None)
    sealed["ledger_sha256"] = ledger_sha256(sealed)
    return sealed


def post_apply_result_sha256(result: dict[str, Any]) -> str:
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    return sha256_value(payload)


def seal_post_apply_result(result: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(result)
    sealed.pop("result_sha256", None)
    sealed["result_sha256"] = post_apply_result_sha256(sealed)
    return sealed


@dataclass(frozen=True)
class PostApplyValidationResult:
    audit_phase: str
    status: str
    completion_state: str
    captured_at: str
    result_sha256: str


POST_APPLY_PARITY_CHECKS: Final = (
    "content_id_slug",
    "metadata",
    "taxonomy",
    "options",
    "menus",
    "media_guids",
    "permalinks",
    "dry_run_diff",
    "rollback_rehearsal",
)


def validate_post_apply_result(
    result: dict[str, Any],
    contract: dict[str, Any],
    contract_sha256: str,
    *,
    now: datetime | None = None,
) -> PostApplyValidationResult:
    """Validate production-only parity evidence after an applied release.

    This result cannot authorize a publication proposal and cannot be embedded
    in a pre-publication ledger. It exists solely to close the second audit
    phase after live apply/readback has actually occurred.
    """

    validate_contract(contract)
    _exact_keys(
        result,
        {
            "schema",
            "version",
            "audit_phase",
            "status",
            "completion_state",
            "contract_sha256",
            "pre_publication_ledger_sha256",
            "captured_at",
            "origin",
            "release_receipt_sha256",
            "external_execution",
            "surface",
            "parity_checks",
            "evidence_bindings",
            "result_sha256",
        },
        "QUALITY_AUDIT_POST_APPLY_SHAPE_INVALID",
    )
    if (
        result["schema"] != POST_APPLY_RESULT_SCHEMA
        or result["version"] != VERSION
        or result["audit_phase"] != POST_APPLY_PHASE_ID
        or result["status"] != "COMPLETE"
        or result["completion_state"] != POST_APPLY_COMPLETION_STATE
        or result["contract_sha256"]
        != _sha256(contract_sha256, "QUALITY_AUDIT_CONTRACT_HASH_INVALID")
        or result["origin"] != "https://kurashinoshirube.com"
    ):
        _fail("QUALITY_AUDIT_POST_APPLY_INVALID")

    _sha256(
        result["pre_publication_ledger_sha256"],
        "QUALITY_AUDIT_POST_APPLY_BINDING_INVALID",
    )
    _sha256(
        result["release_receipt_sha256"],
        "QUALITY_AUDIT_POST_APPLY_BINDING_INVALID",
    )
    captured_at = _timestamp(
        result["captured_at"], "QUALITY_AUDIT_POST_APPLY_TIME_INVALID"
    )
    active_now = now or datetime.now(UTC)
    if active_now.tzinfo is None:
        _fail("QUALITY_AUDIT_NOW_INVALID")
    active_now = active_now.astimezone(UTC)
    policy = _phase_contract(contract, POST_APPLY_PHASE_ID)["completion_policy"]
    age = active_now - captured_at
    if captured_at - active_now > timedelta(
        seconds=int(policy["max_future_skew_seconds"])
    ) or age > timedelta(seconds=int(policy["max_evaluation_age_seconds"])):
        _fail("QUALITY_AUDIT_POST_APPLY_TIME_INVALID")

    execution = _mapping(
        result["external_execution"],
        "QUALITY_AUDIT_POST_APPLY_EXECUTION_INVALID",
    )
    if set(execution) != set(EXPECTED_POST_APPLY_EXTERNAL_EXECUTION) or any(
        execution[name] != "EXECUTED" for name in EXPECTED_POST_APPLY_EXTERNAL_EXECUTION
    ):
        _fail("QUALITY_AUDIT_POST_APPLY_EXECUTION_INVALID")

    surface = _mapping(result["surface"], "QUALITY_AUDIT_POST_APPLY_SURFACE_INVALID")
    _exact_keys(
        surface,
        {"surface_id", "gate_id", "execution_status", "result", "freshness"},
        "QUALITY_AUDIT_POST_APPLY_SURFACE_INVALID",
    )
    expected_surface = EXPECTED_POST_APPLY_SURFACES[0]
    if surface != {
        "surface_id": expected_surface[0],
        "gate_id": expected_surface[1],
        "execution_status": "EXECUTED",
        "result": "PASS",
        "freshness": "FRESH",
    }:
        _fail("QUALITY_AUDIT_POST_APPLY_SURFACE_INVALID")

    checks = _mapping(
        result["parity_checks"], "QUALITY_AUDIT_POST_APPLY_CHECKS_INVALID"
    )
    if set(checks) != set(POST_APPLY_PARITY_CHECKS) or any(
        checks[name] != "PASS" for name in POST_APPLY_PARITY_CHECKS
    ):
        _fail("QUALITY_AUDIT_POST_APPLY_CHECKS_INVALID")

    bindings = _mapping(
        result["evidence_bindings"],
        "QUALITY_AUDIT_POST_APPLY_EVIDENCE_INVALID",
    )
    if set(bindings) != set(POST_APPLY_PARITY_CHECKS):
        _fail("QUALITY_AUDIT_POST_APPLY_EVIDENCE_INVALID")
    evidence_hashes = [
        _sha256(bindings[name], "QUALITY_AUDIT_POST_APPLY_EVIDENCE_INVALID")
        for name in POST_APPLY_PARITY_CHECKS
    ]
    if len(set(evidence_hashes)) != len(evidence_hashes) or "0" * 64 in evidence_hashes:
        _fail("QUALITY_AUDIT_POST_APPLY_EVIDENCE_INVALID")
    result_hash = _sha256(
        result["result_sha256"], "QUALITY_AUDIT_POST_APPLY_HASH_INVALID"
    )
    if result_hash != post_apply_result_sha256(result):
        _fail("QUALITY_AUDIT_POST_APPLY_HASH_INVALID")
    return PostApplyValidationResult(
        audit_phase=POST_APPLY_PHASE_ID,
        status="COMPLETE",
        completion_state=POST_APPLY_COMPLETION_STATE,
        captured_at=timestamp_text(captured_at),
        result_sha256=result_hash,
    )


def validate_post_apply_path(
    result_path: Path,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    *,
    now: datetime | None = None,
) -> PostApplyValidationResult:
    if not result_path.is_absolute():
        _fail("QUALITY_AUDIT_POST_APPLY_PATH_INVALID")
    raw = _read_secure_exact_path(result_path, maximum=MAX_DOCUMENT_BYTES)
    try:
        value = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except json.JSONDecodeError, UnicodeError, RecursionError, ValueError:
        _fail("QUALITY_AUDIT_POST_APPLY_JSON_INVALID")
    result = _mapping(value, "QUALITY_AUDIT_POST_APPLY_JSON_INVALID")
    if raw != canonical_json(result) + b"\n":
        _fail("QUALITY_AUDIT_POST_APPLY_CANONICAL_JSON_INVALID")
    contract, contract_hash = load_contract(contract_path)
    return validate_post_apply_result(result, contract, contract_hash, now=now)


@dataclass(frozen=True)
class ValidationResult:
    audit_phase: str
    status: str
    completion_state: str
    production_parity_state: str
    round_count: int
    consecutive_clean_rounds: int
    reviewer_attestation_verified: bool
    ledger_sha256: str


def _validate_fingerprints(value: object, code: str) -> dict[str, str]:
    fingerprints = _mapping(value, code)
    if list(fingerprints) != list(EXPECTED_FINGERPRINT_INPUTS):
        _fail(code)
    result: dict[str, str] = {}
    for key, raw in fingerprints.items():
        result[key] = _sha256(raw, code)
    return result


def _validate_findings(
    raw_findings: object,
    *,
    surface_ids: set[str],
    global_finding_ids: set[str],
) -> tuple[list[dict[str, Any]], int, set[str]]:
    findings = _list(raw_findings, "QUALITY_AUDIT_FINDINGS_INVALID")
    finding_ids: set[str] = set()
    open_by_surface: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw in findings:
        finding = _mapping(raw, "QUALITY_AUDIT_FINDINGS_INVALID")
        _exact_keys(
            finding,
            {"finding_id", "surface_id", "severity", "actionable", "status", "summary"},
            "QUALITY_AUDIT_FINDINGS_INVALID",
        )
        finding_id = _identifier(
            finding["finding_id"], "QUALITY_AUDIT_FINDINGS_INVALID"
        )
        surface_id = finding["surface_id"]
        summary = finding["summary"]
        if (
            finding_id in finding_ids
            or finding_id in global_finding_ids
            or surface_id not in surface_ids
            or finding["severity"] not in {"P0", "P1", "P2", "P3"}
            or type(finding["actionable"]) is not bool
            or finding["status"] not in {"OPEN", "RESOLVED"}
            or type(summary) is not str
            or not (8 <= len(summary) <= 240)
            or summary.strip() != summary
        ):
            _fail("QUALITY_AUDIT_FINDINGS_INVALID")
        finding_ids.add(finding_id)
        if finding["actionable"] is True and finding["status"] == "OPEN":
            open_by_surface.add(str(surface_id))
        validated.append(finding)
    return validated, _open_actionable_count(validated), open_by_surface


def _validate_evidence_manifest(
    receipt: dict[str, Any],
    *,
    evidence_root: Path,
    gate_id: str,
    surface_id: str,
    round_id: str,
    reviewer_id: str,
    fingerprint_bundle_sha256: str,
    global_manifest_ids: set[str],
    global_manifest_paths: set[str],
    global_manifest_hashes: set[str],
    global_artifact_paths: set[str],
    global_artifact_hashes: set[str],
    global_evidence_hashes: set[str],
) -> None:
    manifest_path = _evidence_relative_path(
        receipt["evidence_manifest_path"], prefix="manifests", suffix=".json"
    )
    if manifest_path in global_manifest_paths:
        _fail("QUALITY_AUDIT_EVIDENCE_MANIFEST_REUSED")
    manifest_raw = _read_evidence_regular_bytes(
        evidence_root,
        manifest_path,
        maximum=MAX_EVIDENCE_MANIFEST_BYTES,
    )
    manifest_file_sha256 = _sha256_bytes(manifest_raw)
    expected_manifest_sha256 = _sha256(
        receipt["evidence_manifest_sha256"],
        "QUALITY_AUDIT_EVIDENCE_MANIFEST_HASH_INVALID",
    )
    if (
        manifest_file_sha256 != expected_manifest_sha256
        or manifest_file_sha256 in global_manifest_hashes
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_MANIFEST_HASH_INVALID")
    manifest = _json_from_evidence(
        manifest_raw, "QUALITY_AUDIT_EVIDENCE_MANIFEST_INVALID"
    )
    if manifest_raw != canonical_json(manifest) + b"\n":
        _fail("QUALITY_AUDIT_EVIDENCE_MANIFEST_INVALID")
    _exact_keys(
        manifest,
        {
            "schema",
            "manifest_id",
            "receipt_id",
            "gate_id",
            "surface_id",
            "round_id",
            "reviewer_id",
            "fingerprint_bundle_sha256",
            "captured_at",
            "command",
            "artifacts",
            "aggregate_sha256",
        },
        "QUALITY_AUDIT_EVIDENCE_MANIFEST_INVALID",
    )
    manifest_id = _identifier(
        manifest["manifest_id"], "QUALITY_AUDIT_EVIDENCE_MANIFEST_INVALID"
    )
    if manifest_id in global_manifest_ids:
        _fail("QUALITY_AUDIT_EVIDENCE_MANIFEST_REUSED")
    if (
        manifest["schema"] != EVIDENCE_MANIFEST_SCHEMA
        or manifest["receipt_id"] != receipt["receipt_id"]
        or manifest["gate_id"] != gate_id
        or manifest["surface_id"] != surface_id
        or manifest["round_id"] != round_id
        or manifest["reviewer_id"] != reviewer_id
        or manifest["fingerprint_bundle_sha256"] != fingerprint_bundle_sha256
        or manifest["captured_at"] != receipt["captured_at"]
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_MANIFEST_BINDING_INVALID")

    command = _mapping(manifest["command"], "QUALITY_AUDIT_EVIDENCE_COMMAND_INVALID")
    _exact_keys(
        command,
        {"tool", "argv", "exit_code"},
        "QUALITY_AUDIT_EVIDENCE_COMMAND_INVALID",
    )
    tool = command["tool"]
    argv = _list(command["argv"], "QUALITY_AUDIT_EVIDENCE_COMMAND_INVALID")
    exit_code = command["exit_code"]
    if (
        type(tool) is not str
        or TOOL_RE.fullmatch(tool) is None
        or not 1 <= len(argv) <= 64
        or any(
            type(argument) is not str
            or not 1 <= len(argument) <= 512
            or argument != argument.strip()
            or any(character in argument for character in ("\x00", "\r", "\n"))
            for argument in argv
        )
        or type(exit_code) is not int
        or not -255 <= exit_code <= 255
        or (receipt["status"] == "PASS" and exit_code != 0)
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_COMMAND_INVALID")

    required_gate_types = set(EXPECTED_GATE_EVIDENCE_TYPES[gate_id])
    artifacts = _list(manifest["artifacts"], "QUALITY_AUDIT_EVIDENCE_ARTIFACTS_INVALID")
    if not 2 + len(required_gate_types) <= len(artifacts) <= MAX_EVIDENCE_ARTIFACTS:
        _fail("QUALITY_AUDIT_EVIDENCE_ARTIFACTS_INVALID")
    gate_result_type = f"gate-result:{gate_id}"
    evidence_types: set[str] = set()
    local_paths: set[str] = set()
    local_hashes: set[str] = set()
    for raw_artifact in artifacts:
        artifact = _mapping(raw_artifact, "QUALITY_AUDIT_EVIDENCE_ARTIFACTS_INVALID")
        _exact_keys(
            artifact,
            {"path", "sha256", "size", "evidence_type"},
            "QUALITY_AUDIT_EVIDENCE_ARTIFACTS_INVALID",
        )
        artifact_path = _evidence_relative_path(
            artifact["path"], prefix="artifacts", suffix=None
        )
        artifact_sha256 = _sha256(
            artifact["sha256"], "QUALITY_AUDIT_EVIDENCE_ARTIFACTS_INVALID"
        )
        artifact_size = artifact["size"]
        evidence_type = artifact["evidence_type"]
        if (
            type(artifact_size) is not int
            or not 1 <= artifact_size <= MAX_EVIDENCE_ARTIFACT_BYTES
            or type(evidence_type) is not str
            or EVIDENCE_TYPE_RE.fullmatch(evidence_type) is None
            or artifact_path in local_paths
            or artifact_path in global_artifact_paths
            or artifact_sha256 in local_hashes
            or artifact_sha256 in global_artifact_hashes
            or evidence_type in evidence_types
        ):
            _fail("QUALITY_AUDIT_EVIDENCE_ARTIFACTS_REUSED")
        artifact_raw = _read_evidence_regular_bytes(
            evidence_root,
            artifact_path,
            maximum=MAX_EVIDENCE_ARTIFACT_BYTES,
        )
        if len(artifact_raw) != artifact_size or _sha256_bytes(artifact_raw) != (
            artifact_sha256
        ):
            _fail("QUALITY_AUDIT_EVIDENCE_ARTIFACT_HASH_INVALID")
        if evidence_type == "command-record":
            command_record = _json_from_evidence(
                artifact_raw, "QUALITY_AUDIT_COMMAND_RECORD_INVALID"
            )
            expected_command_record = {
                "schema": COMMAND_RECORD_SCHEMA,
                "gate_id": gate_id,
                "surface_id": surface_id,
                "round_id": round_id,
                "reviewer_id": reviewer_id,
                "receipt_id": receipt["receipt_id"],
                "fingerprint_bundle_sha256": fingerprint_bundle_sha256,
                "captured_at": receipt["captured_at"],
                "command_tool": tool,
                "command_argv": argv,
                "command_exit_code": exit_code,
            }
            if (
                command_record != expected_command_record
                or artifact_raw != canonical_json(command_record) + b"\n"
            ):
                _fail("QUALITY_AUDIT_COMMAND_RECORD_INVALID")
        elif evidence_type == gate_result_type:
            result = _json_from_evidence(
                artifact_raw, "QUALITY_AUDIT_GATE_RESULT_INVALID"
            )
            expected_result = {
                "schema": GATE_RESULT_SCHEMA,
                "gate_id": gate_id,
                "surface_id": surface_id,
                "round_id": round_id,
                "reviewer_id": reviewer_id,
                "receipt_id": receipt["receipt_id"],
                "fingerprint_bundle_sha256": fingerprint_bundle_sha256,
                "status": receipt["status"],
                "captured_at": receipt["captured_at"],
                "command_tool": tool,
                "command_argv": argv,
                "command_exit_code": exit_code,
            }
            if (
                result != expected_result
                or artifact_raw != canonical_json(result) + b"\n"
            ):
                _fail("QUALITY_AUDIT_GATE_RESULT_INVALID")
        local_paths.add(artifact_path)
        local_hashes.add(artifact_sha256)
        evidence_types.add(evidence_type)
    if not {"command-record", gate_result_type, *required_gate_types} <= evidence_types:
        _fail("QUALITY_AUDIT_GATE_EVIDENCE_TYPE_MISSING")

    aggregate_sha256 = _sha256(
        manifest["aggregate_sha256"], "QUALITY_AUDIT_EVIDENCE_AGGREGATE_INVALID"
    )
    if (
        aggregate_sha256 != evidence_manifest_aggregate_sha256(manifest)
        or receipt["evidence_sha256"] != aggregate_sha256
        or aggregate_sha256 in global_evidence_hashes
    ):
        _fail("QUALITY_AUDIT_EVIDENCE_AGGREGATE_INVALID")

    global_manifest_ids.add(manifest_id)
    global_manifest_paths.add(manifest_path)
    global_manifest_hashes.add(manifest_file_sha256)
    global_artifact_paths.update(local_paths)
    global_artifact_hashes.update(local_hashes)
    global_evidence_hashes.add(aggregate_sha256)


def _validate_round(
    raw_round: object,
    *,
    contract: dict[str, Any],
    evidence_root: Path,
    evaluated_at: datetime,
    previous_round: dict[str, Any] | None,
    global_round_ids: set[str],
    global_reviewer_ids: set[str],
    global_receipt_ids: set[str],
    global_evidence_hashes: set[str],
    global_manifest_ids: set[str],
    global_manifest_paths: set[str],
    global_manifest_hashes: set[str],
    global_artifact_paths: set[str],
    global_artifact_hashes: set[str],
    global_finding_ids: set[str],
) -> dict[str, Any]:
    row = _mapping(raw_round, "QUALITY_AUDIT_ROUND_INVALID")
    _exact_keys(
        row,
        {
            "round_id",
            "reviewer_id",
            "started_at",
            "completed_at",
            "fingerprints",
            "fingerprint_bundle_sha256",
            "previous_round_sha256",
            "surfaces",
            "gate_receipts",
            "findings",
            "actionable_finding_count",
            "status",
            "round_sha256",
        },
        "QUALITY_AUDIT_ROUND_INVALID",
    )
    round_id = _identifier(row["round_id"], "QUALITY_AUDIT_ROUND_ID_INVALID")
    reviewer_id = _identifier(row["reviewer_id"], "QUALITY_AUDIT_REVIEWER_ID_INVALID")
    if round_id in global_round_ids:
        _fail("QUALITY_AUDIT_ROUND_ID_DUPLICATE")
    if reviewer_id in global_reviewer_ids:
        _fail("QUALITY_AUDIT_REVIEWER_ID_DUPLICATE")
    global_round_ids.add(round_id)
    global_reviewer_ids.add(reviewer_id)

    started_at = _timestamp(row["started_at"], "QUALITY_AUDIT_ROUND_TIME_INVALID")
    completed_at = _timestamp(row["completed_at"], "QUALITY_AUDIT_ROUND_TIME_INVALID")
    if started_at > completed_at or completed_at > evaluated_at:
        _fail("QUALITY_AUDIT_ROUND_TIME_INVALID")
    if previous_round is not None:
        previous_completed = _timestamp(
            previous_round["completed_at"], "QUALITY_AUDIT_ROUND_TIME_INVALID"
        )
        if started_at < previous_completed:
            _fail("QUALITY_AUDIT_ROUND_TIME_INVALID")

    expected_previous = (
        None if previous_round is None else previous_round["round_sha256"]
    )
    if row["previous_round_sha256"] != expected_previous:
        _fail("QUALITY_AUDIT_PREVIOUS_ROUND_HASH_INVALID")

    fingerprints = _validate_fingerprints(
        row["fingerprints"], "QUALITY_AUDIT_ROUND_FINGERPRINTS_INVALID"
    )
    bundle = fingerprint_bundle_sha256(fingerprints)
    if row["fingerprint_bundle_sha256"] != bundle:
        _fail("QUALITY_AUDIT_FINGERPRINT_BUNDLE_INVALID")

    required = _phase_contract(contract, PRE_PUBLICATION_PHASE_ID)["required_surfaces"]
    expected_surface_ids = [str(item["surface_id"]) for item in required]
    expected_gate_by_surface = {
        str(item["surface_id"]): str(item["gate_id"]) for item in required
    }
    max_age_by_gate = {
        str(item["gate_id"]): int(item["max_age_seconds"]) for item in required
    }

    surfaces = _list(row["surfaces"], "QUALITY_AUDIT_SURFACES_INVALID")
    if len(surfaces) != len(expected_surface_ids):
        _fail("QUALITY_AUDIT_SURFACES_INVALID")
    surface_by_id: dict[str, dict[str, Any]] = {}
    for raw_surface, expected_id in zip(surfaces, expected_surface_ids, strict=True):
        surface = _mapping(raw_surface, "QUALITY_AUDIT_SURFACES_INVALID")
        _exact_keys(
            surface,
            {"surface_id", "execution_status", "result"},
            "QUALITY_AUDIT_SURFACES_INVALID",
        )
        if (
            surface["surface_id"] != expected_id
            or surface["execution_status"] not in {"EXECUTED", "NOT_EXECUTED"}
            or surface["result"] not in {"PASS", "FAIL", "BLOCKED"}
        ):
            _fail("QUALITY_AUDIT_SURFACES_INVALID")
        surface_by_id[expected_id] = surface

    receipts = _list(row["gate_receipts"], "QUALITY_AUDIT_RECEIPTS_INVALID")
    if len(receipts) != len(expected_surface_ids):
        _fail("QUALITY_AUDIT_RECEIPTS_INVALID")
    receipt_by_surface: dict[str, dict[str, Any]] = {}
    for raw_receipt, expected_surface_id in zip(
        receipts, expected_surface_ids, strict=True
    ):
        receipt = _mapping(raw_receipt, "QUALITY_AUDIT_RECEIPTS_INVALID")
        _exact_keys(
            receipt,
            {
                "receipt_id",
                "gate_id",
                "surface_id",
                "round_id",
                "reviewer_id",
                "fingerprint_bundle_sha256",
                "status",
                "evidence_sha256",
                "evidence_manifest_path",
                "evidence_manifest_sha256",
                "captured_at",
                "freshness",
                "receipt_sha256",
            },
            "QUALITY_AUDIT_RECEIPTS_INVALID",
        )
        receipt_id = _identifier(
            receipt["receipt_id"], "QUALITY_AUDIT_RECEIPT_ID_INVALID"
        )
        if receipt_id in global_receipt_ids:
            _fail("QUALITY_AUDIT_RECEIPT_ID_DUPLICATE")
        global_receipt_ids.add(receipt_id)
        gate_id = expected_gate_by_surface[expected_surface_id]
        if (
            receipt["surface_id"] != expected_surface_id
            or receipt["gate_id"] != gate_id
            or receipt["round_id"] != round_id
            or receipt["reviewer_id"] != reviewer_id
            or receipt["fingerprint_bundle_sha256"] != bundle
        ):
            _fail("QUALITY_AUDIT_RECEIPT_BINDING_INVALID")
        if receipt["status"] not in {"PASS", "FAIL", "BLOCKED", "NOT_EXECUTED"}:
            _fail("QUALITY_AUDIT_RECEIPTS_INVALID")
        if receipt["status"] == "NOT_EXECUTED":
            if (
                receipt["evidence_sha256"] is not None
                or receipt["evidence_manifest_path"] is not None
                or receipt["evidence_manifest_sha256"] is not None
                or receipt["captured_at"] is not None
                or receipt["freshness"] != "NOT_EXECUTED"
            ):
                _fail("QUALITY_AUDIT_RECEIPT_NOT_EXECUTED_INVALID")
            expected_result = "BLOCKED"
            expected_execution = "NOT_EXECUTED"
        else:
            _sha256(
                receipt["evidence_sha256"], "QUALITY_AUDIT_RECEIPT_EVIDENCE_INVALID"
            )
            captured_at = _timestamp(
                receipt["captured_at"], "QUALITY_AUDIT_RECEIPT_TIME_INVALID"
            )
            if captured_at < started_at or captured_at > completed_at:
                _fail("QUALITY_AUDIT_RECEIPT_TIME_INVALID")
            age = evaluated_at - captured_at
            expected_freshness = (
                "FRESH"
                if timedelta(0) <= age <= timedelta(seconds=max_age_by_gate[gate_id])
                else "STALE"
            )
            if receipt["freshness"] != expected_freshness:
                _fail("QUALITY_AUDIT_RECEIPT_FRESHNESS_INVALID")
            expected_execution = "EXECUTED"
            if receipt["status"] == "PASS" and expected_freshness == "FRESH":
                expected_result = "PASS"
            elif receipt["status"] == "FAIL":
                expected_result = "FAIL"
            else:
                expected_result = "BLOCKED"
            _validate_evidence_manifest(
                receipt,
                evidence_root=evidence_root,
                gate_id=gate_id,
                surface_id=expected_surface_id,
                round_id=round_id,
                reviewer_id=reviewer_id,
                fingerprint_bundle_sha256=bundle,
                global_manifest_ids=global_manifest_ids,
                global_manifest_paths=global_manifest_paths,
                global_manifest_hashes=global_manifest_hashes,
                global_artifact_paths=global_artifact_paths,
                global_artifact_hashes=global_artifact_hashes,
                global_evidence_hashes=global_evidence_hashes,
            )
        surface = surface_by_id[expected_surface_id]
        if (
            surface["execution_status"] != expected_execution
            or surface["result"] != expected_result
        ):
            _fail("QUALITY_AUDIT_SURFACE_RECEIPT_STATE_INVALID")
        if receipt["receipt_sha256"] != receipt_sha256(receipt):
            _fail("QUALITY_AUDIT_RECEIPT_HASH_INVALID")
        receipt_by_surface[expected_surface_id] = receipt

    findings, actionable_count, open_by_surface = _validate_findings(
        row["findings"],
        surface_ids=set(expected_surface_ids),
        global_finding_ids=global_finding_ids,
    )
    global_finding_ids.update(str(item["finding_id"]) for item in findings)
    if type(row["actionable_finding_count"]) is not int or (
        row["actionable_finding_count"] != actionable_count
    ):
        _fail("QUALITY_AUDIT_FINDING_COUNT_INVALID")
    nonpassing_surfaces = {
        surface_id
        for surface_id, surface in surface_by_id.items()
        if surface["result"] != "PASS"
    }
    if nonpassing_surfaces - open_by_surface:
        _fail("QUALITY_AUDIT_NONPASS_WITHOUT_FINDING")

    clean = (
        not nonpassing_surfaces
        and actionable_count == 0
        and all(
            receipt["status"] == "PASS" and receipt["freshness"] == "FRESH"
            for receipt in receipt_by_surface.values()
        )
    )
    expected_status = "PASS" if clean else "BLOCKED"
    if row["status"] != expected_status:
        _fail("QUALITY_AUDIT_ROUND_STATUS_INVALID")
    if row["round_sha256"] != round_sha256(row):
        _fail("QUALITY_AUDIT_ROUND_HASH_INVALID")
    return row


def verify_independent_reviewer_attestation(
    *,
    attestation_path: Path,
    signature_path: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    rounds: list[dict[str, Any]],
    repository_values: dict[str, str],
    evaluated_at: datetime,
    now: datetime,
) -> None:
    """Verify an owner-supplied detached signature against tracked trust roots."""

    payload = _read_canonical_attestation(attestation_path)
    signature = _read_detached_signature(signature_path)
    _exact_keys(
        payload,
        {
            "schema",
            "version",
            "audit_phase",
            "signature_algorithm",
            "reviewer_key_id",
            "reviewer_id",
            "audit_contract_sha256",
            "repository_fingerprint_bundle_sha256",
            "rounds",
            "completed_at",
            "expires_at",
            "independence_statement",
        },
        "QUALITY_AUDIT_ATTESTATION_SHAPE_INVALID",
    )
    if (
        payload["schema"] != ATTESTATION_SCHEMA
        or payload["version"] != VERSION
        or payload["audit_phase"] != PRE_PUBLICATION_PHASE_ID
        or payload["signature_algorithm"] != ATTESTATION_SIGNATURE_ALGORITHM
    ):
        _fail("QUALITY_AUDIT_ATTESTATION_INVALID")
    key_id = _identifier(
        payload["reviewer_key_id"], "QUALITY_AUDIT_ATTESTATION_ID_INVALID"
    )
    reviewer_id = _identifier(
        payload["reviewer_id"], "QUALITY_AUDIT_ATTESTATION_ID_INVALID"
    )
    trusted_keys = _trusted_reviewer_keys(contract)
    trusted = trusted_keys.get(key_id)
    if trusted is None or trusted["reviewer_id"] != reviewer_id:
        _fail("QUALITY_AUDIT_ATTESTATION_REVIEWER_NOT_TRUSTED")

    public_key_bytes = _decode_canonical_base64(
        trusted["public_key_base64"],
        expected_bytes=ED25519_PUBLIC_KEY_BYTES,
        code="QUALITY_AUDIT_ATTESTATION_TRUST_STORE_INVALID",
    )
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, canonical_json(payload))
    except InvalidSignature, ValueError:
        _fail("QUALITY_AUDIT_ATTESTATION_SIGNATURE_INVALID")

    if payload["independence_statement"] != INDEPENDENCE_STATEMENT:
        _fail("QUALITY_AUDIT_ATTESTATION_INDEPENDENCE_INVALID")
    if payload["audit_contract_sha256"] != _sha256(
        contract_sha256, "QUALITY_AUDIT_CONTRACT_HASH_INVALID"
    ):
        _fail("QUALITY_AUDIT_ATTESTATION_CONTRACT_BINDING_INVALID")
    current_bundle = fingerprint_bundle_sha256(repository_values)
    if payload["repository_fingerprint_bundle_sha256"] != current_bundle:
        _fail("QUALITY_AUDIT_ATTESTATION_FINGERPRINT_BINDING_INVALID")

    required_rounds = int(
        _phase_contract(contract, PRE_PUBLICATION_PHASE_ID)["completion_policy"][
            "required_consecutive_clean_rounds"
        ]
    )
    if len(rounds) < required_rounds:
        _fail("QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID")
    expected_rounds = [
        {
            "round_id": row["round_id"],
            "reviewer_id": row["reviewer_id"],
            "round_sha256": row["round_sha256"],
        }
        for row in rounds[-required_rounds:]
    ]
    raw_attested_rounds = _list(
        payload["rounds"], "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID"
    )
    attested_rounds: list[dict[str, str]] = []
    for raw_round in raw_attested_rounds:
        attested_round = _mapping(
            raw_round, "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID"
        )
        _exact_keys(
            attested_round,
            {"round_id", "reviewer_id", "round_sha256"},
            "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID",
        )
        attested_rounds.append(
            {
                "round_id": _identifier(
                    attested_round["round_id"],
                    "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID",
                ),
                "reviewer_id": _identifier(
                    attested_round["reviewer_id"],
                    "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID",
                ),
                "round_sha256": _sha256(
                    attested_round["round_sha256"],
                    "QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID",
                ),
            }
        )
    if attested_rounds != expected_rounds:
        _fail("QUALITY_AUDIT_ATTESTATION_ROUND_BINDING_INVALID")
    if reviewer_id != expected_rounds[-1]["reviewer_id"]:
        _fail("QUALITY_AUDIT_ATTESTATION_REVIEWER_BINDING_INVALID")

    completed_at = _timestamp(
        payload["completed_at"], "QUALITY_AUDIT_ATTESTATION_TIME_INVALID"
    )
    expires_at = _timestamp(
        payload["expires_at"], "QUALITY_AUDIT_ATTESTATION_TIME_INVALID"
    )
    policy = contract["independent_reviewer_attestation"]
    if (
        completed_at != evaluated_at
        or completed_at
        < _timestamp(rounds[-1]["completed_at"], "QUALITY_AUDIT_ROUND_TIME_INVALID")
        or expires_at <= completed_at
        or expires_at - completed_at
        > timedelta(seconds=int(policy["max_validity_seconds"]))
        or completed_at - now
        > timedelta(
            seconds=int(
                _phase_contract(contract, PRE_PUBLICATION_PHASE_ID)[
                    "completion_policy"
                ]["max_future_skew_seconds"]
            )
        )
    ):
        _fail("QUALITY_AUDIT_ATTESTATION_TIME_INVALID")
    if now > expires_at:
        _fail("QUALITY_AUDIT_ATTESTATION_EXPIRED")


def validate_document(
    ledger: dict[str, Any],
    contract: dict[str, Any],
    contract_sha256: str,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    evidence_root: Path | None = None,
    attestation_path: Path | None = None,
    attestation_signature_path: Path | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    validate_contract(contract)
    _exact_keys(
        ledger,
        {
            "schema",
            "version",
            "audit_phase",
            "contract_sha256",
            "evaluated_at",
            "repository_fingerprints",
            "external_execution",
            "rounds",
            "completion",
            "ledger_sha256",
        },
        "QUALITY_AUDIT_LEDGER_SHAPE_INVALID",
    )
    if (
        ledger["schema"] != LEDGER_SCHEMA
        or ledger["version"] != VERSION
        or ledger["audit_phase"] != PRE_PUBLICATION_PHASE_ID
        or ledger["contract_sha256"]
        != _sha256(contract_sha256, "QUALITY_AUDIT_CONTRACT_HASH_INVALID")
    ):
        _fail("QUALITY_AUDIT_LEDGER_INVALID")
    external_execution = _mapping(
        ledger["external_execution"], "QUALITY_AUDIT_EXTERNAL_EXECUTION_INVALID"
    )
    _exact_keys(
        external_execution,
        set(EXPECTED_EXTERNAL_EXECUTION),
        "QUALITY_AUDIT_EXTERNAL_EXECUTION_INVALID",
    )
    for boundary, expected in EXPECTED_EXTERNAL_EXECUTION.items():
        if boundary == "independent_reviewer_attestation_verification":
            if external_execution[boundary] not in {"NOT_EXECUTED", "EXECUTED"}:
                _fail("QUALITY_AUDIT_EXTERNAL_EXECUTION_INVALID")
        elif external_execution[boundary] != expected:
            _fail("QUALITY_AUDIT_LEDGER_INVALID")
    if (attestation_path is None) != (attestation_signature_path is None):
        _fail("QUALITY_AUDIT_ATTESTATION_INPUT_PAIR_REQUIRED")

    active_now = now or datetime.now(UTC)
    if active_now.tzinfo is None:
        _fail("QUALITY_AUDIT_NOW_INVALID")
    active_now = active_now.astimezone(UTC)
    evaluated_at = _timestamp(
        ledger["evaluated_at"], "QUALITY_AUDIT_EVALUATED_AT_INVALID"
    )
    policy = _phase_contract(contract, PRE_PUBLICATION_PHASE_ID)["completion_policy"]
    if evaluated_at - active_now > timedelta(seconds=policy["max_future_skew_seconds"]):
        _fail("QUALITY_AUDIT_EVALUATED_AT_INVALID")

    expected_repository = repository_fingerprints(contract, repository_root)
    repository_values = _validate_fingerprints(
        ledger["repository_fingerprints"],
        "QUALITY_AUDIT_REPOSITORY_FINGERPRINTS_INVALID",
    )
    if repository_values != expected_repository:
        _fail("QUALITY_AUDIT_REPOSITORY_FINGERPRINTS_DRIFTED")

    raw_rounds = _list(ledger["rounds"], "QUALITY_AUDIT_ROUNDS_INVALID")
    if not raw_rounds or len(raw_rounds) > 100:
        _fail("QUALITY_AUDIT_ROUNDS_INVALID")
    rounds: list[dict[str, Any]] = []
    round_ids: set[str] = set()
    reviewer_ids: set[str] = set()
    receipt_ids: set[str] = set()
    evidence_hashes: set[str] = set()
    manifest_ids: set[str] = set()
    manifest_paths: set[str] = set()
    manifest_hashes: set[str] = set()
    artifact_paths: set[str] = set()
    artifact_hashes: set[str] = set()
    finding_ids: set[str] = set()
    active_evidence_root = (
        DEFAULT_EVIDENCE_ROOT if evidence_root is None else evidence_root
    )
    for raw_round in raw_rounds:
        validated = _validate_round(
            raw_round,
            contract=contract,
            evidence_root=active_evidence_root,
            evaluated_at=evaluated_at,
            previous_round=rounds[-1] if rounds else None,
            global_round_ids=round_ids,
            global_reviewer_ids=reviewer_ids,
            global_receipt_ids=receipt_ids,
            global_evidence_hashes=evidence_hashes,
            global_manifest_ids=manifest_ids,
            global_manifest_paths=manifest_paths,
            global_manifest_hashes=manifest_hashes,
            global_artifact_paths=artifact_paths,
            global_artifact_hashes=artifact_hashes,
            global_finding_ids=finding_ids,
        )
        rounds.append(validated)

    if rounds[-1]["fingerprints"] != repository_values:
        _fail("QUALITY_AUDIT_LATEST_FINGERPRINTS_DRIFTED")
    reviewer_attestation_verified = False
    if attestation_path is not None and attestation_signature_path is not None:
        verify_independent_reviewer_attestation(
            attestation_path=attestation_path,
            signature_path=attestation_signature_path,
            contract=contract,
            contract_sha256=contract_sha256,
            rounds=rounds,
            repository_values=repository_values,
            evaluated_at=evaluated_at,
            now=active_now,
        )
        reviewer_attestation_verified = True
    expected_attestation_execution = (
        "EXECUTED" if reviewer_attestation_verified else "NOT_EXECUTED"
    )
    if (
        external_execution["independent_reviewer_attestation_verification"]
        != expected_attestation_execution
    ):
        _fail("QUALITY_AUDIT_ATTESTATION_EXECUTION_STATE_INVALID")
    expected_completion = completion_for_rounds(
        rounds,
        repository_values,
        reviewer_attestation_verified=reviewer_attestation_verified,
    )
    if ledger["completion"] != expected_completion:
        _fail("QUALITY_AUDIT_COMPLETION_INVALID")
    if expected_completion[
        "status"
    ] == "COMPLETE" and active_now - evaluated_at > timedelta(
        seconds=policy["max_evaluation_age_seconds"]
    ):
        _fail("QUALITY_AUDIT_COMPLETE_EVALUATION_STALE")
    if ledger["ledger_sha256"] != ledger_sha256(ledger):
        _fail("QUALITY_AUDIT_LEDGER_HASH_INVALID")
    return ValidationResult(
        audit_phase=PRE_PUBLICATION_PHASE_ID,
        status=str(expected_completion["status"]),
        completion_state=str(expected_completion["completion_state"]),
        production_parity_state=str(expected_completion["production_parity_state"]),
        round_count=len(rounds),
        consecutive_clean_rounds=int(expected_completion["consecutive_clean_rounds"]),
        reviewer_attestation_verified=reviewer_attestation_verified,
        ledger_sha256=str(ledger["ledger_sha256"]),
    )


def validate_path(
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    evidence_root: Path | None = None,
    attestation_path: Path | None = None,
    attestation_signature_path: Path | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    contract, contract_hash = load_contract(contract_path)
    ledger, _raw = read_json(ledger_path)
    return validate_document(
        ledger,
        contract,
        contract_hash,
        repository_root=repository_root,
        evidence_root=evidence_root,
        attestation_path=attestation_path,
        attestation_signature_path=attestation_signature_path,
        now=now,
    )


CODEX_OWNER_REPORT_SCHEMA: Final = "RAOS_WORDPRESS_CODEX_OWNER_REVIEW_V1"
CODEX_OWNER_BINDING_SCHEMA: Final = "RAOS_WORDPRESS_CODEX_OWNER_AUDIT_BINDING_V1"
CODEX_OWNER_MODE: Final = "codex-owner"
SIGNED_INDEPENDENT_MODE: Final = "signed-independent"
CODEX_OWNER_BINDING_FIXED: Final = {
    "schema": CODEX_OWNER_BINDING_SCHEMA,
    "audit_mode": CODEX_OWNER_MODE,
    "audit_phase": PRE_PUBLICATION_PHASE_ID,
    "status": "CHECKS_PASSED",
    "completion_state": "READY_FOR_OWNER_REVIEW",
    "production_parity_state": POST_APPLY_PENDING_STATE,
    "review_kind": "CODEX_TECHNICAL_REVIEW",
    "reviewer_attestation_verified": False,
    "execution_identity_authentication": "OWNER_REVIEW_REQUIRED",
    "owner_approval_required": True,
    "publication_authority": False,
}
CODEX_OWNER_HASH_FIELDS: Final = {
    "contract_file_sha256",
    "ledger_file_sha256",
    "ledger_sha256",
    "fingerprint_bundle_sha256",
    "latest_round_sha256",
    "codex_report_sha256",
}


def validate_codex_owner_binding(value: object) -> None:
    """Validate receipt shape, not reviewer identity or publication authority."""

    row = _mapping(value, "QUALITY_AUDIT_CODEX_BINDING_INVALID")
    _exact_keys(
        row,
        set(CODEX_OWNER_BINDING_FIXED)
        | CODEX_OWNER_HASH_FIELDS
        | {"evaluated_at", "expires_at", "round_count", "consecutive_clean_rounds"},
        "QUALITY_AUDIT_CODEX_BINDING_INVALID",
    )
    if any(
        type(row[key]) is not type(expected) or row[key] != expected
        for key, expected in CODEX_OWNER_BINDING_FIXED.items()
    ):
        _fail("QUALITY_AUDIT_CODEX_BINDING_INVALID")
    for key in CODEX_OWNER_HASH_FIELDS:
        _sha256(row[key], "QUALITY_AUDIT_CODEX_BINDING_INVALID")
    for key in ("round_count", "consecutive_clean_rounds"):
        if type(row[key]) is not int or row[key] < 2:
            _fail("QUALITY_AUDIT_CODEX_BINDING_INVALID")
    if row["consecutive_clean_rounds"] > row["round_count"]:
        _fail("QUALITY_AUDIT_CODEX_BINDING_INVALID")
    evaluated = _timestamp(row["evaluated_at"], "QUALITY_AUDIT_CODEX_TIME_INVALID")
    expires = _timestamp(row["expires_at"], "QUALITY_AUDIT_CODEX_TIME_INVALID")
    if (
        not timedelta(0)
        < expires - evaluated
        <= timedelta(
            seconds=EXPECTED_PRE_PUBLICATION_POLICY["max_evaluation_age_seconds"]
        )
    ):
        _fail("QUALITY_AUDIT_CODEX_TIME_INVALID")


def validate_codex_owner_report(
    report_path: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    evidence_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Replay all evidence under the explicitly owner-approved AI review mode.

    This never promotes the unsigned V1 ledger to signed COMPLETE, creates a
    trusted key, or proves that execution identifiers belong to independent
    people. The owner must inspect the Codex run/report provenance and approve
    the exact WordPress batch separately. Recorded IDs are not authentication.
    """

    raw_before = _read_secure_exact_path(report_path, maximum=MAX_ATTESTATION_BYTES)
    report = _read_canonical_attestation(report_path)
    _exact_keys(
        report,
        {
            "schema",
            "audit_mode",
            "review_kind",
            "publication_authority",
            "owner_approval_required",
            "execution_identity_authentication",
            "reviewer_attestation_verified",
            "contract_file_sha256",
            "ledger_file_sha256",
            "ledger_sha256",
            "fingerprint_bundle_sha256",
            "evaluated_at",
            "expires_at",
            "implementation_execution_ids",
            "review_runs",
        },
        "QUALITY_AUDIT_CODEX_REPORT_INVALID",
    )
    if report["schema"] != CODEX_OWNER_REPORT_SCHEMA:
        _fail("QUALITY_AUDIT_CODEX_REPORT_INVALID")
    for key in (
        "audit_mode",
        "review_kind",
        "publication_authority",
        "owner_approval_required",
        "execution_identity_authentication",
        "reviewer_attestation_verified",
    ):
        expected = CODEX_OWNER_BINDING_FIXED[key]
        if type(report[key]) is not type(expected) or report[key] != expected:
            _fail("QUALITY_AUDIT_CODEX_REPORT_INVALID")
    contract, contract_hash = load_contract(contract_path)
    ledger, ledger_raw = read_json(ledger_path)
    active_now = now or datetime.now(UTC)
    result = validate_document(
        ledger,
        contract,
        contract_hash,
        repository_root=repository_root,
        evidence_root=evidence_root,
        now=active_now,
    )
    # Only the intentionally different signer policy may differ. Every surface,
    # artifact, source binding, finding, round and fingerprint is still checked
    # by the legacy validator; no missing evidence can pass this branch.
    if (
        result.status != "BLOCKED"
        or result.reviewer_attestation_verified
        or result.consecutive_clean_rounds < 2
        or ledger["completion"]["reason_codes"]
        != ["INDEPENDENT_REVIEWER_ATTESTATION_NOT_VERIFIED"]
    ):
        _fail("QUALITY_AUDIT_CODEX_EVIDENCE_INCOMPLETE")
    bundle = fingerprint_bundle_sha256(ledger["repository_fingerprints"])
    expected_bindings = {
        "contract_file_sha256": contract_hash,
        "ledger_file_sha256": hashlib.sha256(ledger_raw).hexdigest(),
        "ledger_sha256": result.ledger_sha256,
        "fingerprint_bundle_sha256": bundle,
        "evaluated_at": ledger["evaluated_at"],
    }
    if any(report[key] != value for key, value in expected_bindings.items()):
        _fail("QUALITY_AUDIT_CODEX_REPORT_BINDING_DRIFTED")
    authors = _list(
        report["implementation_execution_ids"], "QUALITY_AUDIT_CODEX_EXECUTION_INVALID"
    )
    if not 1 <= len(authors) <= 100:
        _fail("QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
    author_ids = {
        _identifier(item, "QUALITY_AUDIT_CODEX_EXECUTION_INVALID") for item in authors
    }
    if len(author_ids) != len(authors):
        _fail("QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
    runs = _list(report["review_runs"], "QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
    if len(runs) != 2:
        _fail("QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
    execution_ids: set[str] = set()
    for raw_run, round_row in zip(runs, ledger["rounds"][-2:], strict=True):
        run = _mapping(raw_run, "QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
        _exact_keys(
            run,
            {"round_id", "reviewer_id", "round_sha256", "execution_id"},
            "QUALITY_AUDIT_CODEX_EXECUTION_INVALID",
        )
        execution_id = _identifier(
            run["execution_id"], "QUALITY_AUDIT_CODEX_EXECUTION_INVALID"
        )
        if (
            execution_id in execution_ids
            or execution_id in author_ids
            or any(
                run[key] != round_row[key]
                for key in ("round_id", "reviewer_id", "round_sha256")
            )
        ):
            _fail("QUALITY_AUDIT_CODEX_EXECUTION_INVALID")
        execution_ids.add(execution_id)
    binding = {
        **CODEX_OWNER_BINDING_FIXED,
        **expected_bindings,
        "latest_round_sha256": ledger["rounds"][-1]["round_sha256"],
        "codex_report_sha256": hashlib.sha256(raw_before).hexdigest(),
        "expires_at": report["expires_at"],
        "round_count": result.round_count,
        "consecutive_clean_rounds": result.consecutive_clean_rounds,
    }
    validate_codex_owner_binding(binding)
    evaluated = _timestamp(binding["evaluated_at"], "QUALITY_AUDIT_CODEX_TIME_INVALID")
    expires = _timestamp(binding["expires_at"], "QUALITY_AUDIT_CODEX_TIME_INVALID")
    if active_now >= expires or active_now - evaluated > timedelta(
        seconds=EXPECTED_PRE_PUBLICATION_POLICY["max_evaluation_age_seconds"]
    ):
        _fail("QUALITY_AUDIT_CODEX_REPORT_EXPIRED")
    # Validate at current time too: V1 checks per-gate freshness at evaluation;
    # an unsigned ledger deliberately does not take its signed COMPLETE branch.
    max_ages = {
        item["gate_id"]: item["max_age_seconds"]
        for item in contract["audit_phases"]["pre_publication"]["required_surfaces"]
    }
    evidence_expiries = [expires]
    for round_row in ledger["rounds"][-2:]:
        for receipt in round_row["gate_receipts"]:
            captured = _timestamp(
                receipt["captured_at"], "QUALITY_AUDIT_CODEX_TIME_INVALID"
            )
            if active_now - captured > timedelta(seconds=max_ages[receipt["gate_id"]]):
                _fail("QUALITY_AUDIT_CODEX_REPORT_EXPIRED")
            evidence_expiries.append(
                captured + timedelta(seconds=max_ages[receipt["gate_id"]])
            )
    effective_expiry = min(evidence_expiries)
    if active_now >= effective_expiry:
        _fail("QUALITY_AUDIT_CODEX_REPORT_EXPIRED")
    binding["expires_at"] = timestamp_text(effective_expiry)
    validate_codex_owner_binding(binding)
    if (
        raw_before != canonical_json(report) + b"\n"
        or raw_before
        != _read_secure_exact_path(report_path, maximum=MAX_ATTESTATION_BYTES)
        or read_json(ledger_path)[1] != ledger_raw
        or load_contract(contract_path)[1] != contract_hash
        or repository_fingerprints(contract, repository_root)
        != ledger["repository_fingerprints"]
    ):
        _fail("QUALITY_AUDIT_CODEX_INPUT_CHANGED")
    return binding


def build_blocked_baseline(
    contract: dict[str, Any],
    contract_hash: str,
    fingerprints: dict[str, str],
    *,
    evaluated_at: datetime,
) -> dict[str, Any]:
    """Build an honest NOT_EXECUTED baseline; never a clean review."""

    validate_contract(contract)
    _sha256(contract_hash, "QUALITY_AUDIT_CONTRACT_HASH_INVALID")
    timestamp = timestamp_text(evaluated_at)
    round_id = "baseline-not-executed-round-001"
    reviewer_id = "baseline-not-executed-reviewer-001"
    bundle = fingerprint_bundle_sha256(fingerprints)
    surfaces: list[dict[str, str]] = []
    receipts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for position, (surface_id, gate_id, _max_age) in enumerate(
        EXPECTED_SURFACES, start=1
    ):
        surfaces.append(
            {
                "surface_id": surface_id,
                "execution_status": "NOT_EXECUTED",
                "result": "BLOCKED",
            }
        )
        receipts.append(
            seal_receipt(
                {
                    "receipt_id": f"baseline-gate-receipt-{position:03d}",
                    "gate_id": gate_id,
                    "surface_id": surface_id,
                    "round_id": round_id,
                    "reviewer_id": reviewer_id,
                    "fingerprint_bundle_sha256": bundle,
                    "status": "NOT_EXECUTED",
                    "evidence_sha256": None,
                    "evidence_manifest_path": None,
                    "evidence_manifest_sha256": None,
                    "captured_at": None,
                    "freshness": "NOT_EXECUTED",
                }
            )
        )
        findings.append(
            {
                "finding_id": f"baseline-surface-finding-{position:03d}",
                "surface_id": surface_id,
                "severity": "P1",
                "actionable": True,
                "status": "OPEN",
                "summary": BASELINE_FINDING_SUMMARIES[surface_id],
            }
        )
    round_row = seal_round(
        {
            "round_id": round_id,
            "reviewer_id": reviewer_id,
            "started_at": timestamp,
            "completed_at": timestamp,
            "fingerprints": copy.deepcopy(fingerprints),
            "fingerprint_bundle_sha256": bundle,
            "previous_round_sha256": None,
            "surfaces": surfaces,
            "gate_receipts": receipts,
            "findings": findings,
            "actionable_finding_count": len(findings),
            "status": "BLOCKED",
        }
    )
    ledger: dict[str, Any] = {
        "schema": LEDGER_SCHEMA,
        "version": VERSION,
        "audit_phase": PRE_PUBLICATION_PHASE_ID,
        "contract_sha256": contract_hash,
        "evaluated_at": timestamp,
        "repository_fingerprints": copy.deepcopy(fingerprints),
        "external_execution": copy.deepcopy(EXPECTED_EXTERNAL_EXECUTION),
        "rounds": [round_row],
    }
    ledger["completion"] = completion_for_rounds(
        ledger["rounds"], ledger["repository_fingerprints"]
    )
    return seal_ledger(ledger)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate_parser = subcommands.add_parser("validate")
    validate_parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    validate_parser.add_argument("--attestation", type=Path)
    validate_parser.add_argument("--signature", type=Path)
    codex_parser = subcommands.add_parser("validate-codex-owner")
    codex_parser.add_argument("--report", type=Path, required=True)
    post_apply_parser = subcommands.add_parser("validate-post-apply")
    post_apply_parser.add_argument("--result", type=Path, required=True)
    subcommands.add_parser("fingerprints")
    subcommands.add_parser("render-blocked-baseline")
    subcommands.add_parser("write-blocked-baseline")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if arguments.command == "validate-codex-owner":
            binding = validate_codex_owner_report(arguments.report)
            print(json.dumps(binding, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "validate-post-apply":
            post_apply = validate_post_apply_path(arguments.result)
            print(
                json.dumps(
                    {
                        "audit_phase": post_apply.audit_phase,
                        "status": post_apply.status,
                        "completion_state": post_apply.completion_state,
                        "captured_at": post_apply.captured_at,
                        "result_sha256": post_apply.result_sha256,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        editorial_evidence = load_editorial_evidence_register()
        validate_editorial_article_surfaces(editorial_evidence)
        contract, contract_hash = load_contract()
        if arguments.command == "fingerprints":
            values = repository_fingerprints(contract)
            print(
                json.dumps(
                    {
                        "fingerprints": values,
                        "fingerprint_bundle_sha256": fingerprint_bundle_sha256(values),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command in {
            "render-blocked-baseline",
            "write-blocked-baseline",
        }:
            values = repository_fingerprints(contract)
            evaluated_at = datetime.now(UTC).replace(microsecond=0)
            baseline = build_blocked_baseline(
                contract,
                contract_hash,
                values,
                evaluated_at=evaluated_at,
            )
            validate_document(
                baseline,
                contract,
                contract_hash,
                now=evaluated_at,
            )
            rendered = json.dumps(baseline, ensure_ascii=False, indent=2) + "\n"
            if arguments.command == "write-blocked-baseline":
                try:
                    DEFAULT_LEDGER_PATH.write_text(rendered, encoding="utf-8")
                except OSError:
                    _fail("QUALITY_AUDIT_LEDGER_WRITE_FAILED")
                print(str(DEFAULT_LEDGER_PATH))
            else:
                print(rendered, end="")
            return 0
        result = validate_path(
            arguments.ledger,
            attestation_path=arguments.attestation,
            attestation_signature_path=arguments.signature,
        )
    except QualityAuditFailure as error:
        print(str(error), file=sys.stderr)
        return 69
    print(
        json.dumps(
            {
                "audit_phase": result.audit_phase,
                "status": result.status,
                "completion_state": result.completion_state,
                "production_parity_state": result.production_parity_state,
                "round_count": result.round_count,
                "consecutive_clean_rounds": result.consecutive_clean_rounds,
                "reviewer_attestation_verified": (result.reviewer_attestation_verified),
                "ledger_sha256": result.ledger_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.status == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
