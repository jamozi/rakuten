from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
import yaml
import pytest

from scripts import build_raos_v2_successor as successor_builder
from scripts.validate_raos_v2_successor import (
    ValidationFailure,
    verify_phase3_external_state,
)


ROOT = Path(__file__).resolve().parents[2]
PHASE3 = ROOT / "changes/raos-v2/phase-3"


def _json(relative: str) -> dict[str, object]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _yaml(relative: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_t_v2_051_phase3_generator_owns_exact_output_inventory() -> None:
    documents = successor_builder.documents()
    assert set(documents) == set(successor_builder.OUTPUT_PATHS)
    assert set(successor_builder.PHASE3_OUTPUT_PATHS) <= set(documents)
    assert all(documents[path] == (ROOT / path).read_bytes() for path in documents)


def test_phase3_browser_bootstrap_is_closed_and_does_not_require_stale_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_json = successor_builder._read_json

    def receipt_forbidden_read(relative: Path) -> object:
        if relative == successor_builder.PHASE3_LOCAL_BROWSER_EVIDENCE_PATH:
            raise AssertionError("bootstrap must not read its prior browser receipt")
        return original_read_json(relative)

    def forbidden_evidence_verification(*args: object, **kwargs: object) -> object:
        raise AssertionError("bootstrap must not validate its prior browser receipt")

    monkeypatch.setattr(successor_builder, "_read_json", receipt_forbidden_read)
    monkeypatch.setattr(
        successor_builder,
        "validated_phase3_local_browser_evidence",
        forbidden_evidence_verification,
    )
    assert successor_builder.PHASE3_LOCAL_BROWSER_EVIDENCE_PATH not in (
        successor_builder.PHASE3_BROWSER_BOOTSTRAP_SOURCE_PATHS
    )
    documents = successor_builder.phase3_browser_bootstrap_documents()
    assert set(documents) == set(
        successor_builder.PHASE3_BROWSER_BOOTSTRAP_OUTPUT_PATHS
    )
    assert all(path in successor_builder.OUTPUT_PATHS for path in documents)
    assert all(documents[path] == (ROOT / path).read_bytes() for path in documents)
    assert all(
        "phase-3/preview" in path.as_posix()
        or "phase-3/generated/post-content.html" in path.as_posix()
        or "phase-3/wordpress/artifact" in path.as_posix()
        for path in documents
    )


def test_t_v2_035_wordpress_payload_is_one_route_and_schema_valid() -> None:
    payload = _json(
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    )
    schema = _json("contracts/raos-v2/v2/wordpress-update-payload.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["intent"] == ("UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER")
    assert payload["target"] == {
        "origin": "https://kurashinoshirube.com",
        "route": "/carry-on-suitcase-comparison/",
        "kind": "EXISTING_POST",
        "expected_match_count": 1,
        "expected_public_body_sha256": (
            "e2cace30f5e14b3f2783b3ef10885f2b7b958ac8a3a4aee45447fd95e9e72121"
        ),
    }
    assert payload["preconditions"] == {"expected_current_post_status": "publish"}
    assert payload["postconditions"] == {"required_after_post_status": "publish"}
    assert payload["preaction"] == {
        "status": "HISTORICAL_BASELINE_ONLY",
        "binding_digest": None,
        "binding": None,
    }
    structured_data = payload["structured_data_expectation"]
    assert isinstance(structured_data, dict)
    assert structured_data["emission"] == {
        "owner": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION",
        "local_json_ld_emission": False,
        "external_configuration_status": "UNVERIFIED_EXTERNAL",
    }
    assert structured_data["json_ld_types"] == [
        "Article",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    ]
    assert (
        successor_builder.semantic_json_sha256(
            {"documents": structured_data["documents"]}
        )
        == structured_data["json_ld_sha256"]
    )
    fields = payload["fields"]
    assert isinstance(fields, dict)
    assert fields["post_status"] == "publish"


def test_phase3_review_candidate_closes_claim_authority_and_update_payload() -> None:
    candidate = _json("changes/raos-v2/phase-3/generated/review-candidate.v1.json")
    phase2 = candidate["phase2_candidate"]
    bindings = candidate["claim_bindings"]
    assert isinstance(phase2, dict)
    assert isinstance(bindings, list)
    assert "draft_payload" not in candidate
    update_payload = _json(
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    )
    assert candidate["update_payload"] == update_payload
    assert candidate["preaction_status"] == "HISTORICAL_BASELINE_ONLY"
    assert candidate["preaction_binding_digest"] is None
    assert (
        candidate["structured_data_expectation_sha256"]
        == (update_payload["structured_data_expectation"]["json_ld_sha256"])
    )
    expected_binding_fields = {
        "claim_id",
        "claim_type",
        "risk_class",
        "freshness",
        "authoritative_source_status",
        "checked_at",
        "next_review_at",
        "resolved",
        "blocking",
        "intentionally_disclosed",
    }
    assert bindings and all(set(row) == expected_binding_fields for row in bindings)
    authority = {
        "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
        "version": "1.0.0",
        "claims": [
            {
                key: row[key]
                for key in (
                    "claim_id",
                    "claim_type",
                    "risk_class",
                    "freshness",
                    "authoritative_source_status",
                    "checked_at",
                    "next_review_at",
                )
            }
            for row in sorted(bindings, key=lambda item: str(item["claim_id"]))
        ],
    }
    hashes = phase2["input_hashes"]
    assert isinstance(hashes, dict)
    assert hashes["phase3_claim_authority"] == (
        successor_builder.semantic_json_sha256(authority)
    )


def test_phase3_generated_schemas_close_cutover_and_export_evidence() -> None:
    payload_schema = _json("contracts/raos-v2/v2/wordpress-update-payload.schema.json")
    dry_run_schema = _json("contracts/raos-v2/v2/wordpress-dry-run-receipt.schema.json")
    export_schema = _json("contracts/raos-v2/v2/wordpress-export-binding.schema.json")
    preaction_schema = _json("contracts/raos-v2/v2/preaction-binding.schema.json")
    public_schema = _json(
        "contracts/raos-v2/v2/public-verification-receipt.schema.json"
    )
    public_browser_schema = _json(
        "contracts/raos-v2/v2/public-browser-verification-receipt.schema.json"
    )
    assert set(payload_schema["required"]) == {
        "schema",
        "version",
        "intent",
        "target",
        "preconditions",
        "postconditions",
        "structured_data_expectation",
        "preaction",
        "fields",
    }
    dry_properties = dry_run_schema["properties"]
    export_properties = export_schema["properties"]
    assert isinstance(dry_properties, dict)
    assert isinstance(export_properties, dict)
    assert {"preconditions", "postconditions"} <= set(dry_run_schema["required"])
    field_diff = dry_properties["field_diff"]
    assert isinstance(field_diff, dict)
    assert field_diff["uniqueItems"] is True
    assert len(field_diff["allOf"]) == 9
    publish_digest = "f25fde75eb12c3cb5c9f8108e6d53c165d19d8bd2aac192e37fa68f7d6312aa7"
    preconditions = dry_properties["preconditions"]
    postconditions = dry_properties["postconditions"]
    assert isinstance(preconditions, dict)
    assert isinstance(postconditions, dict)
    assert preconditions["properties"]["before_post_status_sha256"] == {
        "const": publish_digest
    }
    assert {
        "export_role",
        "preaction_status",
        "preaction_binding_sha256",
        "observed_preaction_binding_sha256",
        "preaction_captured_at",
    } <= set(preconditions["required"])
    assert preconditions["properties"]["export_role"] == {"const": "PRE_WRITE_EXPORT"}
    assert postconditions["properties"]["after_post_status_sha256"] == {
        "const": publish_digest
    }
    assert {
        "public_body_sha256",
        "preaction_binding_sha256",
        "export_sha256",
        "export_bytes",
        "export_role",
    } <= set(export_schema["required"])
    assert export_properties["export_role"] == {
        "enum": ["PRE_WRITE_EXPORT", "POST_ACTION_OWNER_EXPORT"]
    }
    target = export_properties["target"]
    field_hashes = export_properties["field_hashes"]
    assert isinstance(target, dict)
    assert isinstance(field_hashes, dict)
    assert "kind" in target["required"]
    assert field_hashes["properties"]["post_status"] == {"const": publish_digest}
    assert set(preaction_schema["required"]) == {
        "schema",
        "version",
        "status",
        "provenance",
        "captured_at",
        "target",
        "current_public_body_sha256",
        "public_capture_sha256",
        "wordpress_export_sha256",
        "wordpress_export_bytes",
    }
    Draft202012Validator(preaction_schema, format_checker=FormatChecker()).validate(
        {
            "schema": "RAOS_V2_PHASE3_PREACTION_BINDING_V1",
            "version": "1.0.0",
            "status": "VERIFIED_PREACTION",
            "provenance": "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT",
            "captured_at": "2026-08-28T20:00:00+09:00",
            "target": {
                "origin": "https://kurashinoshirube.com",
                "route": "/carry-on-suitcase-comparison/",
                "kind": "EXISTING_POST",
                "post_id": 123,
                "exact_match_count": 1,
            },
            "current_public_body_sha256": "a" * 64,
            "public_capture_sha256": "b" * 64,
            "wordpress_export_sha256": "c" * 64,
            "wordpress_export_bytes": 1024,
        }
    )
    public_browser_properties = public_browser_schema["properties"]
    assert isinstance(public_browser_properties, dict)
    public_viewports = public_browser_properties["viewports"]
    assert isinstance(public_viewports, dict)
    assert public_viewports["minItems"] == public_viewports["maxItems"] == 3
    assert len(public_viewports["allOf"]) == 3
    assert public_browser_properties["critical_issue_count"] == {"const": 0}
    assert public_browser_properties["classification"] == {
        "const": "UNVERIFIED_EXTERNAL_TEMPLATE_NO_ACCEPTANCE_AUTHORITY"
    }
    assert public_browser_properties["verification_status"] == {
        "const": "REQUIRED_VALIDATOR_NOT_IMPLEMENTED"
    }
    assert public_browser_properties["phase_exit_eligible"] == {"const": False}
    public_properties = public_schema["properties"]
    assert isinstance(public_properties, dict)
    for name, expected in {
        "sealed_post_content_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "post_content_envelope": {"const": "RAOS_V2_A05_ENVELOPE_V1"},
        "post_content_envelope_count": {"const": 1},
        "post_content_envelope_attribute_count": {"const": 1},
        "blocked_post_content_envelope_count": {"const": 0},
        "post_content_envelope_marker_child_count": {"const": 1},
        "post_content_envelope_valid": {"const": True},
        "head_tag_count": {"const": 1},
        "metadata_location_violation_count": {"const": 0},
        "plugin_artifact_status": {
            "const": "LOCAL_SOURCE_BOUND_AND_PUBLIC_CSS_MATCHED"
        },
    }.items():
        assert name in public_schema["required"]
        assert public_properties[name] == expected


def test_phase3_plugin_artifact_rejects_post_content_hash_drift() -> None:
    sources = successor_builder.validate_phase3_browser_bootstrap_inputs()
    projection = _json(
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    )
    fields = projection["fields"]
    assert isinstance(fields, dict)
    with pytest.raises(
        successor_builder.BuildFailure,
        match="RAOS_V2_PHASE3_WORDPRESS_CONTENT_BINDING_INVALID",
    ):
        successor_builder.phase3_plugin_artifact_documents(
            sources,
            post_content=f"{fields['post_content']}<!-- drift -->",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "claim_risk",
        "claim_status",
        "claim_time",
        "payload_precondition",
        "payload_preaction",
        "payload_structured_data",
    ],
)
def test_phase3_publication_closure_rejects_authority_or_payload_drift(
    mutation: str,
) -> None:
    publication = _json(
        "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
    )
    claim_ledger = _yaml("changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml")
    migration = _yaml("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml")
    payload = _json(
        "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    )
    candidate = _json("changes/raos-v2/phase-3/generated/review-candidate.v1.json")
    bindings = candidate["claim_bindings"]
    assert isinstance(bindings, list)
    binding = bindings[0]
    assert isinstance(binding, dict)
    if mutation == "claim_risk":
        binding["risk_class"] = "LOW" if binding["risk_class"] != "LOW" else "HIGH"
    elif mutation == "claim_status":
        binding["authoritative_source_status"] = "STALE"
    elif mutation == "claim_time":
        binding["next_review_at"] = binding["checked_at"]
    elif mutation == "payload_precondition":
        preconditions = payload["preconditions"]
        assert isinstance(preconditions, dict)
        preconditions["expected_current_post_status"] = "draft"
        candidate["update_payload"] = deepcopy(payload)
    elif mutation == "payload_preaction":
        preaction = payload["preaction"]
        assert isinstance(preaction, dict)
        preaction["status"] = "VERIFIED_PREACTION"
        candidate["update_payload"] = deepcopy(payload)
    else:
        structured_data = payload["structured_data_expectation"]
        assert isinstance(structured_data, dict)
        structured_data["json_ld_sha256"] = "0" * 64
        candidate["update_payload"] = deepcopy(payload)
    with pytest.raises(
        successor_builder.BuildFailure,
        match="RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID",
    ):
        successor_builder.validate_phase3_publication_closure(
            publication=publication,
            claim_ledger=claim_ledger,
            migration=migration,
            wordpress_payload=payload,
            review_candidate=candidate,
        )


def test_t_v2_010_phase3_fragment_links_only_verified_public_routes() -> None:
    content = (PHASE3 / "generated/post-content.html").read_text(encoding="utf-8")
    assert re.search(r"<html(?:\s|>)", content, re.IGNORECASE) is None
    assert re.search(r"<head(?:\s|>)", content, re.IGNORECASE) is None
    assert re.search(r"<h1(?:\s|>)", content, re.IGNORECASE) is None
    assert "/about-ad-policy/" in content
    assert "/privacy-policy/" in content
    for forbidden in (
        "/carry-on/",
        "/tools/carry-on-size-checker/",
        "/policy/how-we-compare-carry-on-products/",
        "ローカルプレビュー",
    ):
        assert forbidden not in content


def test_t_v2_039_phase3_artifact_is_closed_and_hash_bound() -> None:
    artifact = PHASE3 / "wordpress/artifact/raos-v2-decision-support"
    manifest = json.loads(
        (artifact / "plugin-manifest.v1.json").read_text(encoding="utf-8")
    )
    assert manifest["classification"] == "DEPLOYABLE_LOCAL_ARTIFACT_NOT_DEPLOYED"
    assert manifest["deployment_status"] == "NOT_EXECUTED"
    assert manifest["runtime"]["network_request"] is False
    assert manifest["runtime"]["database_write"] is False
    assert manifest["runtime"]["publication_capability"] is False
    for row in manifest["files"]:
        payload = (artifact / row["path"]).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_t_v2_044_phase3_projection_has_no_image_or_affiliate_cta() -> None:
    content = (PHASE3 / "generated/post-content.html").read_text(encoding="utf-8")
    assert "<img" not in content.casefold()
    assert "affiliate.rakuten" not in content.casefold()
    assert "hb.afl.rakuten" not in content.casefold()
    assert content.count('data-raos-v2-cta-state="BLOCKED"') == 3


def test_t_v2_008_phase3_local_wordpress_assembly_is_fail_closed() -> None:
    preview = (PHASE3 / "preview/carry-on-suitcase-comparison/index.html").read_text(
        encoding="utf-8"
    )
    validation = _json("changes/raos-v2/phase-3/generated/phase-3-validation.v1.json")
    binding = validation["local_wordpress_assembly"]
    assert isinstance(binding, dict)
    assert (
        preview.count("<h1") == 1
        and 'data-raos-v2-classification="LOCAL_WORDPRESS_ASSEMBLY_SIMULATION"'
        in preview
        and 'name="robots" content="noindex,nofollow"' in preview
        and '<main id="raos-v2-phase3-main"' in preview
        and preview.count(
            'data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1"'
        )
        == 1
        and "<script" not in preview.casefold()
        and 'src="http' not in preview.casefold()
    )
    assert sorted(re.findall(r'href="(https?://[^"]+)"', preview)) == sorted(
        [
            "https://store.ace.jp/shop/g/g06316-01/",
            "https://store.ace.jp/shop/g/g05721-04",
            "https://store.ace.jp/shop/g/g01471-02",
        ]
    )
    payload = preview.encode("utf-8")
    assert binding["bytes"] == len(payload)
    assert binding["sha256"] == hashlib.sha256(payload).hexdigest()
    browser = binding["browser_a11y_evidence"]
    assert isinstance(browser, dict)
    assert browser == {
        "classification": "PASSED_LOCAL_ASSEMBLY_SIMULATION",
        "evidence_basis": "COMMITTED_SANITIZED_LOCAL_RECEIPT",
        "raw_verification": "RECORDED_NOT_REVERIFIED",
        "current_tree_binding": "CURRENT_PREVIEW_AND_HARNESS_BOUND",
        "manual_visual_review": "PASSED_LOCAL_MANUAL_VISUAL_REVIEW",
        "critical_findings": 0,
        "major_findings": 0,
        "formal_ci": "NOT_CLAIMED",
        "public_evidence": "NOT_CLAIMED",
    }
    assert binding["production_equivalence"] == "NOT_CLAIMED"


def test_t_v2_038_phase3_real_candidate_is_not_falsely_reviewed_or_sealed() -> None:
    request = _json("changes/raos-v2/phase-3/generated/human-review-request.v1.json")
    dry_run = _json(
        "changes/raos-v2/phase-3/generated/wordpress-dry-run-status.v1.json"
    )
    assert request["state"] == "AWAITING_VERIFIED_PREACTION_BINDING"
    assert request["preaction_status"] == "HISTORICAL_BASELINE_ONLY"
    assert request["preaction_binding_digest"] is None
    assert request["receipt"] is None
    assert request["package_seal"] == "NOT_EXECUTED"
    assert dry_run["status"] == "BLOCKED_EXTERNAL"
    assert dry_run["request_count"] == 0
    assert dry_run["external_action_count"] == 0
    assert dry_run["endpoint"] is None
    assert dry_run["blockers"] == [
        "VERIFIED_PREACTION_BINDING_MISSING",
        "CANDIDATE_REISSUE_REQUIRED",
        "NON_SYNTHETIC_HUMAN_REVIEW_RECEIPT_MISSING",
        "FRESH_WORDPRESS_EXPORT_BINDING_MISSING",
    ]


def test_t_v2_035_phase3_seo_plan_preserves_slug_and_has_no_redirect() -> None:
    plan = _yaml("changes/raos-v2/phase-3/generated/seo-url-change-plan.v1.yaml")
    assert plan["route"]["change"] == "NONE"
    assert plan["canonical"]["change"] == "NONE"
    assert plan["robots"]["change"] == "NONE"
    assert plan["sitemap"]["change"] == "NONE"
    assert plan["redirects"]["create"] == []
    assert plan["redirects"]["update"] == []
    assert plan["redirects"]["delete"] == []
    assert plan["production_change"] == "NOT_EXECUTED"
    assert plan["structured_data"]["plugin_generates_json_ld"] is False
    assert plan["structured_data"]["verification_status"] == (
        "NOT_EXECUTED_EXTERNAL_BLOCKER"
    )
    candidate = _json("changes/raos-v2/phase-3/generated/review-candidate.v1.json")
    assert (
        plan["structured_data"]["expected_graph_sha256"]
        == (candidate["structured_data_expectation_sha256"])
    )


def test_phase3_external_flow_requires_preaction_and_public_browser_receipts() -> None:
    template = _yaml(
        "changes/raos-v2/phase-3/generated/external-action-evidence-template.v1.yaml"
    )
    steps = template["steps"]
    assert isinstance(steps, list)
    assert [row["sequence"] for row in steps] == list(range(1, 11))
    by_action = {row["action"]: row for row in steps}
    assert by_action["PREACTION_PUBLIC_CAPTURE_AND_OWNER_EXPORT"] == {
        "sequence": 1,
        "action": "PREACTION_PUBLIC_CAPTURE_AND_OWNER_EXPORT",
        "status": "NOT_EXECUTED",
        "required_receipt_schema": "RAOS_V2_PHASE3_PREACTION_BINDING_V1",
        "phase0_baseline_rule": "IMMUTABLE_HISTORICAL_DO_NOT_OVERWRITE",
    }
    public_browser = by_action["PUBLIC_BROWSER_VERIFICATION"]
    assert public_browser["status"] == "REQUIRED_VALIDATOR_NOT_IMPLEMENTED"
    assert public_browser["acceptance_authority"] is False
    assert public_browser["phase_exit"] == "BLOCKED_EXTERNAL"
    assert public_browser["required_viewport_widths"] == [390, 768, 1440]
    assert public_browser["required_receipt_schema"] == (
        "RAOS_V2_PHASE3_PUBLIC_BROWSER_VERIFICATION_RECEIPT_V1"
    )
    pre_write = by_action["PRE_WRITE_EXPORT_AND_DISABLED_DRY_RUN"]
    assert pre_write["ordering"] == "AFTER_HUMAN_REVIEW_BEFORE_WORDPRESS_WRITE"
    post_action = by_action["POST_ACTION_OWNER_EXPORT"]
    assert post_action["status"] == "NOT_EXECUTED"
    assert post_action["required_binding"] == (
        "SEALED_AFTER_FIELD_HASHES_AND_FINAL_PUBLIC_BODY"
    )
    public_http = by_action["ATOMIC_POST_ACTION_HTTP_AND_EXPORT_VERIFICATION"]
    assert public_http["required_inputs"] == [
        "FRESH_PUBLIC_READ_ONLY_CAPTURE",
        "SEALED_PHASE3_PACKAGE",
        "FRESH_POST_ACTION_OWNER_EXPORT_BINDING",
    ]
    assert public_http["completion_scope"] == "HTTP_AND_OWNER_EXPORT_ONLY"
    assert public_http["pairing"] == "ATOMIC_PAIRED_CAPTURE_CONTRACT"


def test_t_v2_045_phase3_privacy_packet_keeps_sender_off() -> None:
    packet = _yaml(
        "changes/raos-v2/phase-3/generated/privacy-legal-review-packet.v1.yaml"
    )
    assert packet["safe_default"] == {
        "production_sender": "DISABLED",
        "event_transmission": "OFF",
        "metric_state": "UNAVAILABLE",
        "site_and_links_remain_usable": True,
    }
    assert packet["approval"] == "NOT_EXECUTED"
    assert packet["activation"] == "NOT_EXECUTED"


def test_t_v2_040_phase3_rollback_is_contract_only_without_export() -> None:
    receipt = _json("changes/raos-v2/phase-3/generated/rollback-rehearsal.v1.json")
    assert receipt["local_status"] == "PASSED_LOCAL_CONTRACT_ONLY"
    assert receipt["complete_export_binding"] is False
    assert receipt["production_backup"] == "NOT_EXECUTED"
    assert receipt["production_restore"] == "NOT_EXECUTED"
    assert receipt["phase_exit_evidence"] is False


def test_t_v2_051_phase3_report_never_claims_phase_exit() -> None:
    validation = _json("changes/raos-v2/phase-3/generated/phase-3-validation.v1.json")
    report = (PHASE3 / "phase-3-preparation-report.md").read_text(encoding="utf-8")
    assert validation["status"] == "PASSED_LOCAL_PREPARATION"
    assert validation["backlog_status"]["B-V2-037"] == (
        "AWAITING_VERIFIED_PREACTION_BINDING"
    )
    assert validation["backlog_status"]["B-V2-040"] == "BLOCKED_EXTERNAL"
    assert validation["phase_exit"] == "BLOCKED_EXTERNAL"
    assert "Phase 3 is **not complete**" in report
    assert "PUBLIC_VERIFIED" not in report


def test_t_v2_051_effective_traceability_extends_to_phase3_bidirectionally() -> None:
    trace = _yaml("changes/raos-v2/generated/decision-traceability.effective.v1.yaml")
    assert trace["scope"] == ["P0", "P1", "P2", "P3"]
    backlog = {row["id"]: row for row in trace["backlog"]}
    tests = {row["id"]: row for row in trace["tests"]}
    assert set(backlog) == {f"B-V2-{number:03d}" for number in range(1, 41)}
    assert backlog["B-V2-040"]["implementation_status"] == "BLOCKED_EXTERNAL"
    assert backlog["B-V2-040"]["depends_on"] == [
        "B-V2-036",
        "B-V2-037",
        "B-V2-038",
        "B-V2-039",
    ]
    assert "P3" in tests["T-V2-039"]["effective_phases"]
    assert tests["T-V2-039"]["phase3_external_execution_status"] == "NOT_EXECUTED"
    assert trace["invariants"]["B_V2_040_is_blocked_external"] is True


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("human_review", "credential"),
        ("wordpress_export", "secret"),
        ("publication", "token"),
        ("stability_window", "extra"),
    ],
)
def test_phase3_external_state_rejects_nested_extra_or_secret_like_fields(
    section: str, key: str
) -> None:
    state = deepcopy(successor_builder.phase3_external_state())
    nested = state[section]
    assert isinstance(nested, dict)
    nested[key] = "FORBIDDEN"
    with pytest.raises(ValidationFailure, match="PHASE3_EXTERNAL_STATE_INVALID"):
        verify_phase3_external_state(state)
