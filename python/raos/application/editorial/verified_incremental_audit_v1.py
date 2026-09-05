"""Evidence validation for the explicit, non-authorizing incremental audit profile.

Execution identities are owner-reviewable metadata, not authenticated identities.
This module neither runs reviews nor supplies publication or new-page approval.
The legacy full-portfolio quality ledger is deliberately not imported or changed.
These are immutable-subject review observations, not activation authority. They
may be assembled after two real rounds; a separate fresh release activation is
limited to 900 seconds and independently replays source/provider freshness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import NoReturn, cast

from raos.application.editorial.local_scratch_restore_v1 import (
    build_scratch_restoration,
    verify_scratch_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
)

PROFILE = "verified-incremental"
SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_AUDIT_V1"
EVIDENCE_SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_AUDIT_EVIDENCE_V1"
BINDING_SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_AUDIT_BINDING_V1"
CONTACT_ADDRESS = "contact@kurashinoshirube.com"
MAX_AGE_SECONDS = 24 * 60 * 60
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z", re.ASCII)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)

# Keep each review concern visible. Deferral is not a PASS for the full profile.
SURFACES = (
    "code",
    "editorial_sources",
    "epistemic_negative_claims_and_calculation_semantics",
    "editorial_language_story_ia",
    "editorial_accountability_author_credentials_corrections",
    "content_originality_copyright_near_duplicate_risk",
    "contact_corrections_operational_deliverability",
    "search_intent_cannibalization_orphaning",
    "product_selection_lifecycle_support",
    "candidate_universe_representativeness_and_brand_blindspots",
    "consumer_safety_recall_compatibility",
    "smart_device_app_cloud_security_update_eol_privacy",
    "battery_large_appliance_disposal_recycling_transport",
    "freshness_maintenance_ownership",
    "affiliate_fairness_dark_patterns",
    "legal_disclosure_media_rights",
    "provenance_reproducibility_recovery",
    "wordpress_backup_rollback_reproducible_restoration",
    "dependency_supply_chain_plugin_integrity",
    "seo_schema",
    "policy_privacy_consent",
    "analytics_data_minimization_accuracy",
    "ui_a11y_keyboard_zoom",
    "cognitive_accessibility_japanese_readability",
    "links_security_headers",
    "product_media_cta_evidence",
    "search_archive_404",
    "browser_resilience_no_js_error_recovery",
    "browser_compatibility_restricted_environment_resilience",
    "performance_browser",
    "task_based_decision_usability_reader_comprehension",
    "japanese_locale_measurement_semantics_inclusive_language",
    "touch_gesture_orientation_400_percent_reflow_target_size",
    "wordpress_public_attack_abuse_surface",
    "operations_observability_incident_ownership",
    "affiliate_program_compliance_destination_integrity",
    "slow_device_network_resource_budget_caching",
)
READER_SURFACE = "task_based_decision_usability_reader_comprehension"
CLOUD_SURFACE = "smart_device_app_cloud_security_update_eol_privacy"
DISPOSAL_SURFACE = "battery_large_appliance_disposal_recycling_transport"
CONTACT_SURFACE = "contact_corrections_operational_deliverability"
BACKUP_SURFACE = "wordpress_backup_rollback_reproducible_restoration"
OPERATIONS_SURFACE = "operations_observability_incident_ownership"
DEFERRED_CHECKS = (
    "real_reader_research",
    "longitudinal_operational_metrics",
    "external_alert_delivery_drill",
    "formal_legal_opinion",
)
REQUIRED_CHECKS = {
    "editorial_sources": (
        "every_retained_claim_traced",
        "sources_fresh_and_conflict_free",
    ),
    "epistemic_negative_claims_and_calculation_semantics": (
        "units_and_axes_correct",
        "no_unknown_promotion",
    ),
    "editorial_language_story_ia": (
        "reader_question_answered",
        "story_and_japanese_reviewed",
    ),
    "editorial_accountability_author_credentials_corrections": (
        "no_fabricated_experience",
        "attribution_and_scope_accurate",
    ),
    "content_originality_copyright_near_duplicate_risk": (
        "quotation_and_paraphrase_reviewed",
        "no_misappropriated_experience",
    ),
    "search_intent_cannibalization_orphaning": (
        "internal_routes_resolve",
        "live_and_selected_intents_coherent",
    ),
    "product_selection_lifecycle_support": (
        "retained_selection_defensible",
        "support_and_lifecycle_verified",
    ),
    "candidate_universe_representativeness_and_brand_blindspots": (
        "alternatives_considered",
        "selection_not_affiliate_driven",
    ),
    "consumer_safety_recall_compatibility": (
        "retained_products_safety_checked",
        "compatibility_and_warranty_verified",
    ),
    CLOUD_SURFACE: ("dependencies_disclosed", "security_and_eol_claims_verified"),
    DISPOSAL_SURFACE: (
        "japan_disposal_guidance_verified",
        "transport_and_damage_warnings_verified",
    ),
    "affiliate_fairness_dark_patterns": ("disclosure_visible", "no_manipulative_ctas"),
    "legal_disclosure_media_rights": (
        "media_rights_proven",
        "advertising_disclosure_accurate",
    ),
    "provenance_reproducibility_recovery": (
        "wordpress_roundtrip_preserved",
        "manifest_and_unchanged_baselines_bound",
    ),
    "dependency_supply_chain_plugin_integrity": (
        "packages_and_settings_verified",
        "runtime_compatibility_checked",
    ),
    "seo_schema": (
        "metadata_unique_and_correct",
        "structured_data_and_indexability_correct",
    ),
    "policy_privacy_consent": (
        "production_policy_matches_reality",
        "no_fictitious_consent_ui",
    ),
    "analytics_data_minimization_accuracy": (
        "measurement_off_observed",
        "storage_and_network_checked",
    ),
    "ui_a11y_keyboard_zoom": (
        "axe_and_manual_actions_pass",
        "keyboard_focus_zoom_contrast_pass",
    ),
    "cognitive_accessibility_japanese_readability": (
        "labels_and_headings_understandable",
        "decision_aids_reviewed",
    ),
    "links_security_headers": (
        "destinations_and_rel_correct",
        "security_headers_and_mixed_content_checked",
    ),
    "product_media_cta_evidence": (
        "every_retained_commercial_asset_verified",
        "no_fallback_or_unverified_assets",
    ),
    "search_archive_404": (
        "templates_and_empty_states_pass",
        "japanese_labels_and_noindex_correct",
    ),
    "browser_resilience_no_js_error_recovery": (
        "no_js_and_failure_states_checked",
        "no_broken_actions",
    ),
    "browser_compatibility_restricted_environment_resilience": (
        "restricted_modes_checked",
        "degradation_preserves_information",
    ),
    "performance_browser": (
        "repeated_mobile_medians_pass",
        "lcp_cls_tbt_within_budget",
    ),
    "japanese_locale_measurement_semantics_inclusive_language": (
        "locale_units_and_rounding_correct",
        "language_consistent_and_inclusive",
    ),
    "touch_gesture_orientation_400_percent_reflow_target_size": (
        "touch_orientation_and_reflow_pass",
        "targets_and_spacing_pass",
    ),
    "wordpress_public_attack_abuse_surface": (
        "public_exposure_bounded",
        "no_debug_or_credential_leakage",
    ),
    "affiliate_program_compliance_destination_integrity": (
        "program_and_media_terms_checked",
        "actual_variant_destination_verified",
    ),
    "slow_device_network_resource_budget_caching": (
        "slow_network_budget_checked",
        "cache_and_resource_budget_checked",
    ),
}


def _surface_max_age(surface: str) -> int:
    # The observation is when this exact subject/output was reviewed. It does
    # not refresh an underlying capture or claim that its command was rerun.
    # Operational and provider freshness is replayed again at activation.
    if surface not in SURFACES:
        _fail("SURFACE_INVALID")
    return MAX_AGE_SECONDS


FIXED = {
    "schema": SCHEMA,
    "publication_profile": PROFILE,
    "link_mode": "standard-api",
    "review_kind": "CODEX_TECHNICAL_REVIEW",
    "execution_identity_authentication": "OWNER_REVIEW_REQUIRED",
    "publication_authority": False,
    "owner_approval_required": True,
    "reviewer_attestation_verified": False,
    "new_page_approval_authority": False,
}


class IncrementalAuditFailure(ValueError):
    """A URL-free, secret-free validation failure."""


def _fail(code: str) -> NoReturn:
    raise IncrementalAuditFailure(f"RAOS_INCREMENTAL_AUDIT_{code}")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except ValueError, TypeError, UnicodeError:
        _fail("JSON_INVALID")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, keys: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail("SHAPE_INVALID")
    untrusted = cast(Mapping[object, object], value)
    if any(type(key) is not str for key in untrusted):
        _fail("SHAPE_INVALID")
    result = {cast(str, key): item for key, item in untrusted.items()}
    if keys is not None and set(result) != keys:
        _fail("FIELDS_INVALID")
    return result


def _identifier(value: object) -> str:
    if type(value) is not str or ID_RE.fullmatch(value) is None:
        _fail("IDENTIFIER_INVALID")
    return value


def _hash(value: object) -> str:
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        _fail("HASH_INVALID")
    return value


def _hashes(value: object) -> dict[str, str]:
    result = _mapping(value)
    if not result:
        _fail("HASHES_EMPTY")
    return {_identifier(key): _hash(digest) for key, digest in result.items()}


def _ids(value: object, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("IDS_INVALID")
    result = tuple(_identifier(item) for item in cast(Sequence[object], value))
    if (not empty and not result) or len(set(result)) != len(result):
        _fail("IDS_INVALID")
    return result


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail("SHAPE_INVALID")
    return cast(list[object], value)


def _time(value: object) -> datetime:
    if type(value) is not str or TIME_RE.fullmatch(value) is None:
        _fail("TIME_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail("TIME_INVALID")


@dataclass(frozen=True)
class IncrementalAuditScopeV1:
    """Construct only from the independently validated release manifest."""

    selected_article_ids: tuple[str, ...]
    existing_article_ids: tuple[str, ...]
    rendered_article_ids: tuple[str, ...]
    shared_changes: bool
    claim_ids_by_article: Mapping[str, tuple[str, ...]]
    retained_product_ids: tuple[str, ...] = ()
    smart_device_product_ids: tuple[str, ...] = ()
    disposal_product_ids: tuple[str, ...] = ()
    affiliate_cta_ids: tuple[str, ...] = ()
    product_image_ids: tuple[str, ...] = ()
    required_noncontent_rollback_targets: tuple[str, ...] = ()

    def to_document(self) -> dict[str, object]:
        selected = set(_ids(self.selected_article_ids))
        existing = set(_ids(self.existing_article_ids))
        rendered = set(_ids(self.rendered_article_ids))
        products = set(_ids(self.retained_product_ids, empty=True))
        smart = set(_ids(self.smart_device_product_ids, empty=True))
        disposal = set(_ids(self.disposal_product_ids, empty=True))
        ctas = _ids(self.affiliate_cta_ids, empty=True)
        images = _ids(self.product_image_ids, empty=True)
        noncontent = _ids(self.required_noncontent_rollback_targets, empty=True)
        claims = _mapping(self.claim_ids_by_article)
        if (
            type(self.shared_changes) is not bool
            or not selected <= existing
            or not selected <= rendered <= existing
            or (self.shared_changes and rendered != existing)
            or not smart <= products
            or not disposal <= products
            or set(claims) != selected
            or ((ctas or images) and not products)
            or not set(noncontent) <= {"theme", "seo", "plugins"}
            or (noncontent and not self.shared_changes)
        ):
            _fail("SCOPE_INVALID")
        return {
            "selected_article_ids": sorted(selected),
            "existing_article_ids": sorted(existing),
            "rendered_article_ids": sorted(rendered),
            "shared_changes": self.shared_changes,
            "claim_ids_by_article": {
                article: sorted(_ids(claims[article])) for article in sorted(selected)
            },
            "retained_product_ids": sorted(products),
            "smart_device_product_ids": sorted(smart),
            "disposal_product_ids": sorted(disposal),
            "affiliate_cta_ids": sorted(ctas),
            "product_image_ids": sorted(images),
            "required_noncontent_rollback_targets": sorted(noncontent),
        }


@dataclass(frozen=True)
class VerifiedIncrementalAuditBindingV1:
    """Integrity binding only; must never authorize WordPress or create a page."""

    report_sha256: str
    manifest_sha256: str
    scope_sha256: str
    artifact_bundle_sha256: str
    evidence_bundle_sha256: str
    evaluated_at: str
    expires_at: str
    contact_state: str

    def to_document(self) -> dict[str, object]:
        return {
            **FIXED,
            "schema": BINDING_SCHEMA,
            "completion_state": "READY_FOR_OWNER_REVIEW",
            "full_portfolio_audit_completed": False,
            "consecutive_clean_rounds": 2,
            "production_readback_state": "REQUIRED_NOT_EVALUATED",
            "report_sha256": self.report_sha256,
            "manifest_sha256": self.manifest_sha256,
            "scope_sha256": self.scope_sha256,
            "artifact_bundle_sha256": self.artifact_bundle_sha256,
            "evidence_bundle_sha256": self.evidence_bundle_sha256,
            "evaluated_at": self.evaluated_at,
            "expires_at": self.expires_at,
            "contact_state": self.contact_state,
            "deferred_checks": list(DEFERRED_CHECKS)
            + (
                ["automated_contact_delivery"]
                if self.contact_state == "OWNER_CONFIRMED"
                else []
            ),
        }


def _json_evidence(raw: bytes, *, require_canonical: bool = True) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        document = json.loads(raw, object_pairs_hook=unique)
    except ValueError, UnicodeError, RecursionError:
        _fail("EVIDENCE_JSON_INVALID")
    value = _mapping(document)
    if require_canonical and canonical_json_bytes(value) != raw:
        _fail("EVIDENCE_NOT_CANONICAL")
    return value


def validate_scratch_backup_evidence_v1(
    *,
    backup_raw: bytes,
    restoration_raw: bytes,
    readback_raw: bytes,
    expected_snapshot: Mapping[str, object],
    expected_article_slugs: frozenset[str],
    expected_backup_sha256: str,
    observed_at: datetime,
) -> dict[str, object]:
    """Replay private backup/readback bytes; certify stored fields only.

    This does not authenticate execution provenance, restore shared configuration,
    execute WordPress operations, or confer audit/publication authority.
    """
    for raw in (backup_raw, restoration_raw, readback_raw):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT_BYTES:
            _fail("RESTORATION_ARTIFACT_INVALID")
    if _digest(backup_raw) != _hash(expected_backup_sha256):
        _fail("BACKUP_INPUT_MISMATCH")
    # Captured MCP JSON and PHP readback need not have the proof-envelope format.
    # Check their actual bytes above and their duplicate-free semantic JSON below.
    backup = _json_evidence(backup_raw, require_canonical=False)
    receipt = _json_evidence(restoration_raw, require_canonical=False)
    readback = _json_evidence(readback_raw, require_canonical=False)
    if canonical_json_bytes(backup) != canonical_json_bytes(expected_snapshot):
        _fail("BACKUP_SNAPSHOT_MISMATCH")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        _fail("TIME_INVALID")
    verified_at = receipt.get("verified_at")
    if (
        type(verified_at) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
            verified_at,
        )
        is None
    ):
        _fail("RESTORATION_TIME_INVALID")
    try:
        verified = datetime.fromisoformat(verified_at)
    except ValueError:
        _fail("RESTORATION_TIME_INVALID")
    if verified > observed_at:
        _fail("RESTORATION_TIME_INVALID")
    try:
        expected = build_scratch_restoration(
            backup,
            article_slugs=expected_article_slugs,
            preparation_sha256=_hash(receipt.get("source_preparation_sha256")),
            environment_id=_identifier(receipt.get("environment_id")),
        )
        replayed = verify_scratch_restoration(expected, readback)
    except IncrementalPublicationFailure, KeyError, TypeError:
        _fail("RESTORATION_REPLAY_FAILED")
    if canonical_json_bytes(receipt) != canonical_json_bytes(
        {**replayed, "verified_at": verified_at}
    ):
        _fail("RESTORATION_RECEIPT_MISMATCH")
    snapshot_hash = _digest(canonical_json_bytes(expected_snapshot).rstrip(b"\n"))
    if receipt["source_snapshot_sha256"] != snapshot_hash:
        _fail("BACKUP_SNAPSHOT_MISMATCH")
    return {
        "schema": "RAOS_WORDPRESS_VERIFIED_SCRATCH_BACKUP_BINDING_V1",
        "status": "STORED_FIELDS_REPLAY_VERIFIED",
        "publication_authority": False,
        "production_authority": False,
        "shared_configuration_restored": False,
        "source_snapshot_sha256": snapshot_hash,
        "backup_artifact_sha256": _digest(backup_raw),
        "restoration_artifact_sha256": _digest(restoration_raw),
        "readback_artifact_sha256": _digest(readback_raw),
        "verified_document_count": 14,
        "original_id_set": receipt["original_id_set"],
        "verified_at": verified_at,
        "not_restored": receipt["not_restored"],
    }


def _backup_checks(
    value: object,
    attachments: set[str],
    *,
    artifacts: Mapping[str, bytes],
    expected_snapshot: Mapping[str, object],
    expected_article_slugs: frozenset[str],
    expected_backup_sha256: str,
    observed_at: datetime,
    required_noncontent_rollback_targets: tuple[str, ...],
) -> None:
    checks = _mapping(
        value,
        {
            "backup_available",
            "restore_rehearsal_passed",
            "restored_hashes_match",
            "rollback_owner_id",
            "backup_artifact_id",
            "restoration_artifact_id",
            "restoration_readback_artifact_id",
        },
    )
    _identifier(checks["rollback_owner_id"])
    keys = tuple(
        _identifier(checks[key])
        for key in (
            "backup_artifact_id",
            "restoration_artifact_id",
            "restoration_readback_artifact_id",
        )
    )
    if (
        len(set(keys)) != 3
        or not set(keys) <= attachments
        or any(
            checks[key] is not True
            for key in (
                "backup_available",
                "restore_rehearsal_passed",
                "restored_hashes_match",
            )
        )
    ):
        _fail("RESTORATION_UNVERIFIED")
    validate_scratch_backup_evidence_v1(
        backup_raw=artifacts[keys[0]],
        restoration_raw=artifacts[keys[1]],
        readback_raw=artifacts[keys[2]],
        expected_snapshot=expected_snapshot,
        expected_article_slugs=expected_article_slugs,
        expected_backup_sha256=expected_backup_sha256,
        observed_at=observed_at,
    )
    # A content-only scratch rehearsal does not restore theme/plugin/options.
    # There is deliberately no self-asserted shared rollback exception.
    if required_noncontent_rollback_targets:
        _fail("SHARED_ROLLBACK_NOT_VERIFIED")


def _checks(surface: str, value: object, attachments: set[str]) -> str | None:
    checks = _mapping(value)
    if surface == "code":
        _mapping(checks, {"commands"})
        commands = checks["commands"]
        if type(commands) is not list:
            _fail("COMMANDS_INVALID")
        commands = _list(checks["commands"])
        seen: set[str] = set()
        for command in commands:
            row = _mapping(command, {"command_id", "exit_code", "output_artifact_id"})
            command_id = _identifier(row["command_id"])
            if (
                command_id in seen
                or type(row["exit_code"]) is not int
                or row["exit_code"] != 0
                or _identifier(row["output_artifact_id"]) not in attachments
            ):
                _fail("TEST_FAILED_OR_UNBOUND")
            seen.add(command_id)
        if not {"generate", "check", "focused", "fast", "final"} <= seen:
            _fail("REQUIRED_COMMAND_MISSING")
    elif surface == CONTACT_SURFACE:
        _mapping(
            checks,
            {
                "state",
                "address",
                "owner_id",
                "confirmation_artifact_id",
                "delivery_artifact_id",
            },
        )
        state = _identifier(checks["state"])
        if (
            state not in {"OWNER_CONFIRMED", "TESTED"}
            or checks["address"] != CONTACT_ADDRESS
            or _identifier(checks["confirmation_artifact_id"]) not in attachments
        ):
            _fail("CONTACT_UNCONFIRMED")
        _identifier(checks["owner_id"])
        delivery = checks["delivery_artifact_id"]
        if (state == "OWNER_CONFIRMED" and delivery is not None) or (
            state == "TESTED" and _identifier(delivery) not in attachments
        ):
            _fail("CONTACT_STATE_INVALID")
        return state
    elif surface == OPERATIONS_SURFACE:
        _mapping(
            checks,
            {"immediate_readback_plan_bound", "incident_owner_id", "rollback_owner_id"},
        )
        if checks["immediate_readback_plan_bound"] is not True:
            _fail("READBACK_PLAN_MISSING")
        _identifier(checks["incident_owner_id"])
        _identifier(checks["rollback_owner_id"])
    elif surface == "freshness_maintenance_ownership":
        _mapping(checks, {"recheck_owner_id", "expiry_enforced"})
        _identifier(checks["recheck_owner_id"])
        if checks["expiry_enforced"] is not True:
            _fail("FRESHNESS_UNVERIFIED")
    else:
        _mapping(checks, {"completed_checks", "status"})
        completed = _ids(checks["completed_checks"])
        if checks["status"] != "PASS" or set(completed) != set(
            REQUIRED_CHECKS[surface]
        ):
            _fail("CHECK_FAILED")
    return None


def validate_verified_incremental_audit_v1(
    report: Mapping[str, object],
    *,
    manifest_sha256: str,
    expected_artifact_hashes: Mapping[str, str],
    evidence_artifacts: Mapping[str, bytes],
    expected_backup_snapshot: Mapping[str, object],
    expected_backup_article_slugs: frozenset[str],
    implementation_execution_ids: Sequence[str],
    scope: IncrementalAuditScopeV1,
    now: datetime,
) -> VerifiedIncrementalAuditBindingV1:
    """Rehash actual evidence bytes; caller must compute expected inputs afresh.

    This cannot authenticate who ran a command/review or whether their substantive
    findings are true. The owner must inspect provenance before wp-admin approval.
    The caller must also enforce the earlier source/product/materialization expiry.
    """
    fields = set(FIXED) | {
        "manifest_sha256",
        "scope_sha256",
        "artifact_hashes",
        "evidence_artifact_hashes",
        "implementation_execution_ids",
        "evaluated_at",
        "expires_at",
        "rounds",
        "deferred_checks",
    }
    document = _mapping(report, fields)
    if any(
        type(document[key]) is not type(value) or document[key] != value
        for key, value in FIXED.items()
    ):
        _fail("PROFILE_OR_AUTHORITY_INVALID")
    expected_manifest = _hash(manifest_sha256)
    expected_hashes = _hashes(expected_artifact_hashes)
    scope_hash = _digest(canonical_json_bytes(scope.to_document()))
    implementations = _ids(tuple(implementation_execution_ids))
    if (
        document["manifest_sha256"] != expected_manifest
        or document["scope_sha256"] != scope_hash
        or _hashes(document["artifact_hashes"]) != expected_hashes
        or _ids(document["implementation_execution_ids"]) != implementations
    ):
        _fail("INPUT_BINDING_INVALID")
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("TIME_INVALID")
    active_now = now.astimezone(UTC)
    evaluated = _time(document["evaluated_at"])
    expires = _time(document["expires_at"])
    if (
        not evaluated
        <= active_now
        < expires
        <= evaluated + timedelta(seconds=MAX_AGE_SECONDS)
    ):
        _fail("EXPIRED_OR_FUTURE")
    hashes = _hashes(document["evidence_artifact_hashes"])
    if set(evidence_artifacts) != set(hashes):
        _fail("EVIDENCE_SET_INVALID")
    for key, raw in evidence_artifacts.items():
        if (
            type(raw) is not bytes
            or not 0 < len(raw) <= MAX_ARTIFACT_BYTES
            or _digest(raw) != hashes[key]
        ):
            _fail("EVIDENCE_TAMPERED")
    rounds = _list(document["rounds"])
    if len(rounds) != 2:
        _fail("TWO_ROUNDS_REQUIRED")
    used: set[str] = set()
    reviewers: set[str] = set()
    executions: set[str] = set(implementations)
    round_ids: set[str] = set()
    prior_completed: datetime | None = None
    earliest_evidence_expiry = expires
    contact_states: set[str] = set()
    for raw_round in rounds:
        row = _mapping(
            raw_round,
            {
                "round_id",
                "reviewer_id",
                "execution_id",
                "started_at",
                "completed_at",
                "manifest_sha256",
                "scope_sha256",
                "artifact_hashes",
                "findings",
                "surfaces",
            },
        )
        rid = _identifier(row["round_id"])
        reviewer = _identifier(row["reviewer_id"])
        execution = _identifier(row["execution_id"])
        if (
            rid in round_ids
            or reviewer in reviewers
            or execution in executions
            or row["findings"] != []
        ):
            _fail("ROUND_NOT_INDEPENDENT_OR_CLEAN")
        round_ids.add(rid)
        reviewers.add(reviewer)
        executions.add(execution)
        start, end = _time(row["started_at"]), _time(row["completed_at"])
        if (
            not start < end <= evaluated
            or (prior_completed is not None and start < prior_completed)
            or active_now - start > timedelta(days=1)
        ):
            _fail("ROUND_TIME_INVALID")
        prior_completed = end
        if (
            row["manifest_sha256"] != expected_manifest
            or row["scope_sha256"] != scope_hash
            or _hashes(row["artifact_hashes"]) != expected_hashes
        ):
            _fail("ROUND_BINDING_INVALID")
        surfaces = _list(row["surfaces"])
        if len(surfaces) != len(SURFACES):
            _fail("SURFACES_MISSING")
        for expected_surface, raw_surface in zip(SURFACES, surfaces, strict=True):
            surface = _mapping(
                raw_surface,
                {
                    "surface_id",
                    "status",
                    "execution_status",
                    "reason_code",
                    "evidence_id",
                },
            )
            if surface["surface_id"] != expected_surface:
                _fail("SURFACES_MISSING")
            deferred = expected_surface == READER_SURFACE
            not_applicable = (
                expected_surface == CLOUD_SURFACE and not scope.smart_device_product_ids
            ) or (
                expected_surface == DISPOSAL_SURFACE and not scope.disposal_product_ids
            )
            if deferred or not_applicable:
                expected_status = "DEFERRED" if deferred else "NOT_APPLICABLE"
                reason = (
                    "REAL_READERS_NOT_EXECUTED"
                    if deferred
                    else "NO_APPLICABLE_PRODUCTS"
                )
                if surface != {
                    "surface_id": expected_surface,
                    "status": expected_status,
                    "execution_status": "NOT_EXECUTED",
                    "reason_code": reason,
                    "evidence_id": None,
                }:
                    _fail("EXEMPTION_INVALID")
                continue
            if (
                surface["status"] != "PASS"
                or surface["execution_status"] != "EXECUTED"
                or surface["reason_code"] is not None
            ):
                _fail("MANDATORY_SURFACE_NOT_PASSED")
            evidence_id = _identifier(surface["evidence_id"])
            if evidence_id in used or evidence_id not in evidence_artifacts:
                _fail("EVIDENCE_REUSED_OR_MISSING")
            used.add(evidence_id)
            proof = _json_evidence(evidence_artifacts[evidence_id])
            _mapping(
                proof,
                {
                    "schema",
                    "surface_id",
                    "result",
                    "manifest_sha256",
                    "scope_sha256",
                    "artifact_hashes",
                    "round_id",
                    "execution_id",
                    "captured_at",
                    "findings",
                    "observations",
                    "attachments",
                    "checks",
                },
            )
            if (
                proof["schema"] != EVIDENCE_SCHEMA
                or proof["surface_id"] != expected_surface
                or proof["result"] != "PASS"
                or proof["findings"] != []
                or proof["manifest_sha256"] != expected_manifest
                or proof["scope_sha256"] != scope_hash
                or _hashes(proof["artifact_hashes"]) != expected_hashes
                or proof["round_id"] != rid
                or proof["execution_id"] != execution
                or not start <= _time(proof["captured_at"]) <= end
            ):
                _fail("EVIDENCE_BINDING_OR_RESULT_INVALID")
            evidence_expiry = _time(proof["captured_at"]) + timedelta(
                seconds=_surface_max_age(expected_surface)
            )
            earliest_evidence_expiry = min(earliest_evidence_expiry, evidence_expiry)
            observations = _list(proof["observations"])
            if not observations or any(
                type(value) is not str or not value.strip() or len(value) > 8000
                for value in observations
            ):
                _fail("OBSERVATIONS_MISSING")
            attachments = set(_ids(proof["attachments"]))
            if evidence_id in attachments or not attachments <= set(evidence_artifacts):
                _fail("ATTACHMENT_MISSING")
            used.update(attachments)
            contact_state = None
            if expected_surface == BACKUP_SURFACE:
                _backup_checks(
                    proof["checks"],
                    attachments,
                    artifacts=evidence_artifacts,
                    expected_snapshot=expected_backup_snapshot,
                    expected_article_slugs=expected_backup_article_slugs,
                    expected_backup_sha256=_hash(expected_hashes.get("live-snapshot")),
                    observed_at=_time(proof["captured_at"]),
                    required_noncontent_rollback_targets=scope.required_noncontent_rollback_targets,
                )
            else:
                contact_state = _checks(expected_surface, proof["checks"], attachments)
            if contact_state is not None:
                contact_states.add(contact_state)
    if used != set(hashes) or len(contact_states) != 1:
        _fail("EVIDENCE_UNUSED_OR_CONTACT_DRIFT")
    if expires > earliest_evidence_expiry:
        _fail("EVIDENCE_EXPIRY_EXCEEDED")
    contact = next(iter(contact_states))
    deferred_checks = list(DEFERRED_CHECKS) + (
        ["automated_contact_delivery"] if contact == "OWNER_CONFIRMED" else []
    )
    if document["deferred_checks"] != [
        {
            "check_id": item,
            "execution_status": "NOT_EXECUTED",
            "publication_blocking": False,
        }
        for item in deferred_checks
    ]:
        _fail("DEFERRED_STATE_INVALID")
    return VerifiedIncrementalAuditBindingV1(
        _digest(canonical_json_bytes(document)),
        expected_manifest,
        scope_hash,
        _digest(canonical_json_bytes(expected_hashes)),
        _digest(canonical_json_bytes(hashes)),
        cast(str, document["evaluated_at"]),
        cast(str, document["expires_at"]),
        contact,
    )


def incomplete_audit_template_v1(
    *,
    manifest_sha256: str,
    expected_artifact_hashes: Mapping[str, str],
    implementation_execution_ids: Sequence[str],
    scope: IncrementalAuditScopeV1,
) -> dict[str, object]:
    """An intentionally unpublishable skeleton; never invent review executions."""
    return {
        **FIXED,
        "manifest_sha256": _hash(manifest_sha256),
        "scope_sha256": _digest(canonical_json_bytes(scope.to_document())),
        "artifact_hashes": _hashes(expected_artifact_hashes),
        "evidence_artifact_hashes": {},
        "implementation_execution_ids": list(_ids(tuple(implementation_execution_ids))),
        "evaluated_at": None,
        "expires_at": None,
        "rounds": [],
        "deferred_checks": [
            {
                "check_id": item,
                "execution_status": "NOT_EXECUTED",
                "publication_blocking": False,
            }
            for item in DEFERRED_CHECKS
        ],
    }


def incomplete_evidence_template_v1(
    *,
    surface_id: str,
    manifest_sha256: str,
    expected_artifact_hashes: Mapping[str, str],
    scope: IncrementalAuditScopeV1,
) -> dict[str, object]:
    """An unexecuted evidence skeleton, not an audit finding or command result."""
    if surface_id not in SURFACES or surface_id == READER_SURFACE:
        _fail("SURFACE_INVALID")
    return {
        "schema": EVIDENCE_SCHEMA,
        "surface_id": surface_id,
        "result": "NOT_EXECUTED",
        "manifest_sha256": _hash(manifest_sha256),
        "scope_sha256": _digest(canonical_json_bytes(scope.to_document())),
        "artifact_hashes": _hashes(expected_artifact_hashes),
        "round_id": None,
        "execution_id": None,
        "captured_at": None,
        "findings": [],
        "observations": [],
        "attachments": [],
        "checks": {},
    }
