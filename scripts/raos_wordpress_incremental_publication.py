#!/usr/bin/env python3
"""Explicit incremental publication port; owner approval is never synthesized.

The first route omits all commerce and reconstructs its private candidate from
current authoring and revalidated sources. Extra audit bytes are content-addressed
under audit/inputs and audit/evidence. The old full-portfolio route is untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "python", ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import raos_wordpress_incremental_candidate as candidate_owner  # noqa: E402
import raos_wordpress_publication_request as publication  # noqa: E402
import raos_wordpress_deployment_operator as wordpress_deployment  # noqa: E402
from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    load_editorial_portfolio_v3,
)
from raos.application.editorial.verified_incremental_audit_v1 import (  # noqa: E402
    IncrementalAuditScopeV1,
    validate_verified_incremental_audit_v1,
)
from raos.application.editorial.verified_incremental_release_v1 import (  # noqa: E402
    VerifiedIncrementalReleaseV1,
    build_verified_incremental_release_v1,
    validate_release_inputs_v1,
    validate_release_envelope,
    verify_release_readback,
)
from raos.application.editorial.verified_incremental_sources_v1 import (  # noqa: E402
    validate_selected_official_sources,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    ExistingDocument,
    PROFILE,
    canonical,
    digest,
    validate_manifest,
    DNS_TRANSITION_STATE,
    DNS_TRANSITION_MODE,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    read_private_bytes,
    write_private_bytes,
)

OWNER = Path("/home/minami/rakuten")
PRIVATE = OWNER / ".secrets/wordpress-mcp"
RECEIPT_SCHEMA = "RAOS_WORDPRESS_INCREMENTAL_PUBLICATION_REQUEST_V1"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")


def fail(code: str) -> NoReturn:
    publication.fail(f"RAOS_INCREMENTAL_PORT_{code}")


def instant(value: object) -> datetime:
    if (
        type(value) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is None
    ):
        fail("TIME_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        fail("TIME_INVALID")
    raise AssertionError("unreachable")


def private_directory(path: Path) -> None:
    """Reject parent symlinks as well as leaf symlinks; never create on read."""
    try:
        parts = path.relative_to(OWNER / ".secrets").parts
    except ValueError:
        fail("PRIVATE_PATH_INVALID")
    if not path.is_absolute() or any(part in {".", ".."} for part in parts):
        fail("PRIVATE_PATH_INVALID")
    cursor = OWNER / ".secrets"
    for part in (None, *parts):
        if part is not None:
            cursor /= part
        try:
            metadata = cursor.lstat()
        except OSError:
            fail("PRIVATE_DIRECTORY_MISSING")
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            fail("PRIVATE_DIRECTORY_INVALID")


def read_bytes(directory: Path, name: str) -> bytes:
    private_directory(directory)
    if SAFE_NAME.fullmatch(name) is None:
        fail("PRIVATE_NAME_INVALID")
    return read_private_bytes(directory, name)


def read_json(directory: Path, name: str) -> tuple[dict[str, Any], bytes]:
    raw = read_bytes(directory, name)

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                fail("JSON_DUPLICATE_KEY")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except ValueError, UnicodeError:
        fail("JSON_INVALID")
    if type(value) is not dict:
        fail("JSON_INVALID")
    return value, raw


def _candidate_directory(path: Path) -> None:
    if (
        path.parent != PRIVATE / "incremental-candidates"
        or re.fullmatch(r"[0-9a-f]{64}", path.name) is None
    ):
        fail("CANDIDATE_PATH_INVALID")
    private_directory(path)


@dataclass(frozen=True)
class ReplayedCandidate:
    context: VerifiedIncrementalReleaseV1
    manifest: Mapping[str, Any]
    preparation: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    preview_binding: Mapping[str, object]


def validate_candidate_browser(
    *,
    candidate_path: Path,
    manifest: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
    snapshot: Mapping[str, Any],
    now: datetime,
    fixture_root: Path,
) -> Mapping[str, object]:
    """Replay the authoritative measured report, then bind its mixed scope."""
    private_directory(fixture_root)
    browser = ROOT / "changes/wordpress-local-preview-v1/browser"
    if str(browser) not in sys.path:
        sys.path.insert(0, str(browser))
    mixed_audit_report = importlib.import_module("mixed_audit_report")

    recorded = json.loads(mixed_audit_report.read_regular(mixed_audit_report.REPORT))
    modern = recorded.get("schema") == mixed_audit_report.SCHEMA_V2
    from raos_wordpress_release_workflow import preview_origin

    report = mixed_audit_report.validate_report(
        mixed_audit_report.REPORT,
        fixture_root=fixture_root,
        origin=preview_origin(dict(os.environ)) if modern else "http://127.0.0.1:39330",
        now=now,
        **({"candidate_path": candidate_path} if modern else {}),
    )
    raw = mixed_audit_report.read_regular(mixed_audit_report.REPORT)
    if json.loads(raw) != report:
        fail("BROWSER_REPORT_CHANGED")
    inputs = cast(dict[str, Any], report["inputs"])
    validate_browser_inputs(
        inputs, manifest=manifest, artifact_bytes=artifact_bytes, snapshot=snapshot
    )
    if set(report["core_document_slugs"]) != {
        row["slug"] for row in snapshot["documents"]
    }:
        fail("BROWSER_SCOPE_MISMATCH")
    return {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_BROWSER_BINDING_V1",
        "status": "LOCAL_MIXED_BROWSER_AUDIT_PASSED",
        "report_sha256": digest(raw),
        "manifest_sha256": digest(canonical(manifest)),
        "preparation_binding_sha256": inputs["preparation_binding_sha256"],
        "publication_authority": False,
    }


def validate_browser_inputs(
    inputs: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
    snapshot: Mapping[str, Any],
) -> None:
    """Bind fixture bytes before expensive checks and again before publication."""
    selected = {row["article_id"] for row in manifest["articles"]}
    if (
        inputs["source_snapshot_sha256"]
        != digest(publication.canonical_json_bytes(snapshot))
        or set(inputs["scope"]["selected_article_ids"]) != selected
    ):
        fail("BROWSER_SCOPE_MISMATCH")
    for row in manifest["articles"]:
        local = row["local_artifact"]
        if inputs["article_body_sha256"].get(row["slug"]) != digest(
            artifact_bytes[local["key"]]
        ):
            fail("BROWSER_ARTICLE_MISMATCH")
    shared = manifest["shared_artifacts"]
    for identifier, row in shared.items():
        if (
            identifier not in {"theme", "seo"}
            and inputs["page_body_sha256"].get(identifier) != row["sha256"]
        ):
            fail("BROWSER_POLICY_MISMATCH")
    baseline_theme = (
        snapshot.get("deployment_status", {}).get("theme", {}).get("tree_sha256")
    )
    expected_theme = shared.get("theme", {}).get("sha256", baseline_theme)
    if inputs["theme_tree_sha256"] != expected_theme:
        fail("BROWSER_THEME_MISMATCH")
    for row in snapshot["documents"]:
        if (
            row["post_type"] == "post"
            and inputs["baseline_document_sha256"].get(row["slug"])
            != row["content_sha256"]
        ):
            fail("BROWSER_BASELINE_MISMATCH")


@dataclass(frozen=True)
class PreparedCandidate:
    """Read-only reconstruction; no audit receipt or activation is manufactured."""

    manifest: Mapping[str, Any]
    manifest_raw: bytes
    preparation: Mapping[str, Any]
    preparation_raw: bytes
    snapshot: Mapping[str, Any]
    snapshot_raw: bytes
    artifacts: Mapping[str, bytes]
    scope: IncrementalAuditScopeV1
    validated: Any
    release_arguments: Mapping[str, Any]


def prepare_candidate(path: Path, *, now: datetime) -> PreparedCandidate:
    """Reject invalid inputs before tests, browser work, reviews or credentials."""
    _candidate_directory(path)
    manifest, manifest_raw = read_json(path, "manifest.v1.json")
    preparation, preparation_raw = read_json(path, "candidate-preparation.v1.json")
    if digest(canonical(manifest)) != path.name or manifest_raw != canonical(manifest):
        fail("CANDIDATE_HASH_INVALID")
    if preparation.get("manifest_sha256") != path.name:
        fail("CANDIDATE_HASH_INVALID")
    snapshot, _snapshot_raw = read_json(
        PRIVATE / "incremental-snapshots", preparation.get("snapshot_name", "")
    )
    snapshot_raw = publication.canonical_json_bytes(snapshot)
    if digest(snapshot_raw) != preparation.get("snapshot_sha256"):
        fail("SNAPSHOT_HASH_INVALID")
    portfolio = load_editorial_portfolio_v3(ROOT)
    selected_slugs = sorted(row["slug"] for row in manifest.get("articles", []))
    articles = publication.load_articles(",".join(selected_slugs)) if selected_slugs else []
    selected_ids = tuple(
        sorted(portfolio.article_by_slug[slug].article_id for slug in selected_slugs)
    )
    reader_bindings = manifest.get("reader_pages", {})
    page_articles = candidate_owner.reader_pages.select_hub_pages(ROOT, sorted(slug for slug, row in reader_bindings.items() if row["kind"] == "hub")) if any(row["kind"] == "hub" for row in reader_bindings.values()) else []
    if "privacy-policy" in reader_bindings:
        page_articles.append(candidate_owner.reader_pages.load_reader_privacy_page(ROOT))
    page_targets = candidate_owner.reader_pages.reader_page_targets(ROOT, page_articles, snapshot)
    sources = (validate_selected_official_sources(ROOT, OWNER, selected_ids, now, allow_empty=True)
               if page_targets and not selected_ids else validate_selected_official_sources(ROOT, OWNER, selected_ids, now))
    sources.require_complete()
    shared = manifest.get("shared_artifacts", {})
    policies = [
        article
        for article in (
            publication.load_policy_pages(profile="production")
            if set(shared) - {"theme", "seo"}
            else ()
        )
        if article.production_slug in shared and article.production_slug not in reader_bindings
    ]
    transition_mode = "strict"
    if "runtime_transition" in manifest:
        transition = manifest["runtime_transition"]
        if (
            type(transition) is not dict
            or transition.get("mode") != DNS_TRANSITION_MODE
        ):
            fail("DNS_TRANSITION_INVALID")
        transition_mode = DNS_TRANSITION_MODE
    measurement_profile, measurement_manifest = candidate_owner.reader_pages.reader_measurement_projection(ROOT) if "reader_measurement" in manifest else (None, None)
    reconstructed, artifacts, current_preparation = (
        candidate_owner.prepare_noncommercial_candidate(
            portfolio=portfolio,
            snapshot=snapshot,
            sources=sources,
            articles=articles,
            now=instant(manifest["evaluated_at"]),
            theme_projection=candidate_owner.current_theme_projection()
            if "theme" in shared
            else None,
            policy_articles=policies,
            home_article=candidate_owner.reader_pages.load_home_page(ROOT) if "home" in shared else None,
            reader_page_articles=page_articles,
            reader_page_targets=page_targets,
            reader_measurement=measurement_profile,
            reader_measurement_manifest=measurement_manifest,
            runtime_transition_mode=transition_mode,
        )
    )
    if canonical(reconstructed) != manifest_raw:
        fail("CANDIDATE_CHANGED")
    # Replaying an unchanged capture does not create a new publication window.
    cast(dict[str, Any], current_preparation["source_evidence"])["evaluated_at"] = (
        preparation["source_evidence"]["evaluated_at"]
    )
    if canonical(current_preparation) != canonical(preparation):
        fail("CANDIDATE_PREPARATION_CHANGED")
    for key, raw in artifacts.items():
        if read_bytes(path / "artifacts", preparation["artifact_files"][key]) != raw:
            fail("ARTIFACT_CHANGED")
    inventory = {
        row["slug"]: ExistingDocument(
            row["id"],
            row["slug"],
            row["post_type"],
            row["content_sha256"],
            row["status"],
        )
        for row in snapshot["documents"]
    }
    targets = {
        binding.article_id: (
            binding.production_slug,
            inventory[binding.production_slug].post_id,
        )
        for binding in portfolio.articles
    }
    bindings = [portfolio.article_by_slug[slug] for slug in selected_slugs]
    products = {product for binding in bindings for product in binding.product_ids}
    from raos.application.editorial.reader_release_applicability_v1 import classify_product_audit_scope

    applicability = classify_product_audit_scope(ROOT, tuple(sorted(products)))
    images = {
        f"image:{binding.article_id}:{product}": (binding.article_id, product)
        for binding in bindings
        for product in binding.product_ids
    }
    ctas = {
        cta.cta_id: (cta.article_id, cta.product_id)
        for binding in bindings
        for cta in binding.cta_bindings
    }
    validated = validate_manifest(
        manifest,
        inventory=inventory,
        article_targets=targets,
        reader_page_targets=page_targets,
        reader_measurement=measurement_profile,
        shared_baseline_sha256={
            key: row["baseline_sha256"]
            for key, row in shared.items()
            if key in {"theme", "seo"}
        },
        article_products={
            binding.article_id: binding.product_ids for binding in bindings
        },
        article_claims={
            article: tuple(claims)
            for article, claims in sources.article_claim_sources.items()
        },
        claim_sources={
            claim: refs
            for claims in sources.article_claim_sources.values()
            for claim, refs in claims.items()
        },
        source_receipt_sha256=sources.source_receipt_sha256,
        verified_image_sha256={},
        verified_cta_sha256={},
        image_article_products=images,
        cta_article_products=ctas,
        artifact_bytes=artifacts,
        now=now,
    )
    rendered = set(manifest["rendered_document_slugs"])
    scope = IncrementalAuditScopeV1(
        selected_ids,
        tuple(sorted(targets)),
        tuple(
            sorted(
                article for article, (slug, _id) in targets.items() if slug in rendered
            )
        ),
        bool(shared),
        {
            article: tuple(sorted(sources.article_claim_sources[article]))
            for article in selected_ids
        },
        selected_page_slugs=tuple(sorted(page_targets)),
        retained_product_ids=applicability.retained_product_ids,
        smart_device_product_ids=applicability.smart_device_product_ids,
        disposal_product_ids=applicability.disposal_product_ids,
        required_noncontent_rollback_targets=tuple(
            sorted(set(shared) & {"theme", "seo", "plugins"})
        ),
    )
    release_arguments = dict(
        validated_manifest=validated,
        audit_scope=scope,
        official_sources=sources,
        artifact_bytes=artifacts,
        inventory=inventory,
        article_targets=targets,
        reader_page_targets=page_targets,
        reader_measurement=measurement_profile,
        commerce_views={},
        image_article_products=images,
        cta_bindings={},
        expected_production_content_sha256={
            slug: row["after_sha256"]
            for slug, row in preparation["production_documents"].items()
        },
        expected_shared_readback_sha256=preparation["expected_shared_readback_sha256"],
        source_article_id_by_article_id={article: article for article in selected_ids},
        now=now,
    )
    validate_release_inputs_v1(manifest, **release_arguments)
    return PreparedCandidate(
        manifest=manifest,
        manifest_raw=manifest_raw,
        preparation=preparation,
        preparation_raw=preparation_raw,
        snapshot=snapshot,
        snapshot_raw=snapshot_raw,
        artifacts=artifacts,
        scope=scope,
        validated=validated,
        release_arguments=release_arguments,
    )


def load_candidate(
    path: Path,
    *,
    implementation_execution_ids: tuple[str, ...],
    now: datetime,
    browser_validator: Callable[..., Mapping[str, object]],
    activation_evaluated_at: datetime | None = None,
    verification_base: str = "origin/main",
) -> ReplayedCandidate:
    """No WordPress credential read or mutation until this function succeeds."""
    prepared = prepare_candidate(path, now=now)
    manifest = prepared.manifest
    manifest_raw = prepared.manifest_raw
    preparation = prepared.preparation
    preparation_raw = prepared.preparation_raw
    snapshot = prepared.snapshot
    snapshot_raw = prepared.snapshot_raw
    artifacts = prepared.artifacts
    scope = prepared.scope
    validated = prepared.validated

    report_name = (
        "report.v2.json"
        if (path / "audit/report.v2.json").exists()
        else "report.v1.json"
    )
    report, _raw = read_json(path / "audit", report_name)
    inputs = {
        **artifacts,
        "manifest": manifest_raw,
        "live-snapshot": snapshot_raw,
        "candidate-preparation": preparation_raw,
    }
    from raos.application.editorial.reader_release_applicability_v1 import classify_product_audit_scope

    if scope.retained_product_ids:
        inputs["product-audit-applicability"] = canonical(classify_product_audit_scope(ROOT, scope.retained_product_ids).to_document())
    hashes = report.get("artifact_hashes")
    if type(hashes) is not dict or not set(inputs) <= set(hashes):
        fail("AUDIT_INPUT_BINDING_INVALID")
    for key, expected in hashes.items():
        if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            fail("AUDIT_INPUT_BINDING_INVALID")
        if key not in inputs:
            inputs[key] = read_bytes(path / "audit/inputs", f"{expected}.bin")
        if digest(inputs[key]) != expected:
            fail("AUDIT_INPUT_BINDING_INVALID")
    evidence_hashes = report.get("evidence_artifact_hashes")
    if type(evidence_hashes) is not dict:
        fail("AUDIT_EVIDENCE_INVALID")
    evidence = {}
    for key, expected in evidence_hashes.items():
        if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            fail("AUDIT_EVIDENCE_INVALID")
        evidence[key] = read_bytes(path / "audit/evidence", f"{expected}.bin")
    modern_audit = (
        report.get("schema") == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_AUDIT_V2"
    )
    verification_context = {}
    if modern_audit:
        from raos_wordpress_release_workflow import verification_inputs
        from raos_wordpress_verification import required_ci

        required_ci(ROOT)
        verification_context["verification_inputs"] = verification_inputs(
            verification_base
        )
    audit = validate_verified_incremental_audit_v1(
        report,
        manifest_sha256=validated.manifest_sha256,
        expected_artifact_hashes={key: digest(raw) for key, raw in inputs.items()},
        evidence_artifacts=evidence,
        expected_backup_snapshot=snapshot,
        expected_backup_article_slugs=frozenset(
            slug
            for slug, _post_id in prepared.release_arguments["article_targets"].values()
        ),
        implementation_execution_ids=implementation_execution_ids,
        scope=scope,
        now=now,
        **verification_context,
    )
    preview_binding = browser_validator(
        candidate_path=path,
        manifest=manifest,
        artifact_bytes=artifacts,
        snapshot=snapshot,
        now=now,
    )
    if (
        "mixed-browser-report" not in inputs
        or digest(inputs["mixed-browser-report"])
        != preview_binding.get("report_sha256")
        or preview_binding.get("manifest_sha256") != validated.manifest_sha256
    ):
        fail("AUDITED_BROWSER_REPORT_MISMATCH")
    context = build_verified_incremental_release_v1(
        manifest,
        audit_binding=audit,
        audit_artifact_bytes=inputs,
        activation_evaluated_at=activation_evaluated_at,
        **prepared.release_arguments,
    )
    return ReplayedCandidate(context, manifest, preparation, snapshot, preview_binding)


def deployment_call(command: str, value: Mapping[str, object]) -> dict[str, object]:
    return publication._deployment_mcp_call(
        command,
        value,
        timeout=publication.RELEASE_FOREGROUND_TIMEOUT_SECONDS
        if command == "release-wait-and-apply"
        else 120,
        owner_checkout=OWNER,
    )


def _save(path: Path, receipt: dict[str, Any], state: str) -> None:
    receipt["state"] = state
    receipt["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_private_bytes(path, "publication-request.v1.json", canonical(receipt))


def _ids(receipt: Mapping[str, Any]) -> list[str]:
    return publication._registered_proposal_ids(receipt)


def _validate_request(
    receipt: Mapping[str, Any], path: Path
) -> VerifiedIncrementalReleaseV1:
    envelope = receipt.get("release_envelope")
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("publication_profile") != PROFILE
        or receipt.get("link_mode") != "standard-api"
        or type(envelope) is not dict
        or receipt.get("candidate_sha256") != path.name
    ):
        fail("REQUEST_INVALID")
    context = VerifiedIncrementalReleaseV1(canonical(envelope))
    if (
        context.sha256 != receipt.get("release_sha256")
        or envelope.get("manifest_sha256") != path.name
    ):
        fail("REQUEST_BINDING_INVALID")
    validate_release_envelope(
        envelope,
        current_context=context,
        publication_profile=PROFILE,
        link_mode="standard-api",
        stage="readback",
        now=instant(envelope.get("evaluated_at")),
    )
    expected = envelope["expected_production_content_sha256"]
    if receipt.get("selected_slugs") != sorted(expected) or receipt.get(
        "selected_documents"
    ) != {slug: envelope["inventory"][slug]["post_type"] for slug in expected}:
        fail("REQUEST_TARGET_SET_INVALID")
    proposals = receipt.get("proposals")
    if type(proposals) is not list:
        fail("REQUEST_PROPOSAL_BINDING_INVALID")
    expected_theme = envelope["expected_shared_readback_sha256"].get("theme")
    if (
        expected_theme is not None
        and receipt.get("desired_theme_tree_sha256") != expected_theme
    ):
        fail("REQUEST_THEME_BINDING_INVALID")
    for proposal in proposals:
        if type(proposal) is not dict or proposal.get("kind") not in {
            "THEME_RELEASE",
            "CONTENT_RELEASE",
        }:
            fail("REQUEST_PROPOSAL_BINDING_INVALID")
        wanted = (
            receipt["desired_theme_tree_sha256"]
            if proposal["kind"] == "THEME_RELEASE"
            else expected.get(proposal["slug"])
        )
        if proposal.get("after_sha256") != wanted:
            fail("REQUEST_PROPOSAL_BINDING_INVALID")
        target = (
            "theme" if proposal["kind"] == "THEME_RELEASE" else proposal.get("slug")
        )
        if proposal.get("idempotency_key") != publication.sha256_json(
            {"release_sha256": context.sha256, "target": target}
        ):
            fail("REQUEST_PROPOSAL_BINDING_INVALID")
        if (
            proposal["kind"] == "THEME_RELEASE"
            and "theme" not in envelope["shared_artifact_sha256"]
        ):
            fail("REQUEST_PROPOSAL_BINDING_INVALID")
    if receipt.get("batch_registration") is not None:
        _ids(receipt)
        if sum(row["kind"] == "THEME_RELEASE" for row in proposals) != int(
            expected_theme is not None
        ):
            fail("REQUEST_THEME_BINDING_INVALID")
    return context


def _batch_status(
    receipt: Mapping[str, Any], deploy: Callable[..., dict[str, object]]
) -> dict[str, object]:
    ids = _ids(receipt)
    registered = receipt["batch_registration"]
    args = {key: registered[key] for key in ("batch_token", "batch_manifest_sha256")}
    response = deploy("publication-batch-status", {**args, "proposal_ids": ids})
    if (
        response.get("schema") != "RAOSWordPressPublicationBatchStatusV1"
        or any(response.get(key) != value for key, value in args.items())
        or response.get("proposal_ids") != ids
        or response.get("proposal_count") != len(ids)
        or response.get("state")
        not in {"REGISTERED", "APPROVED", "APPLIED", "EXPIRED", "FAILED"}
        or type(response.get("preconditions_ready")) is not bool
    ):
        fail("BATCH_STATUS_INVALID")
    instant(response.get("expires_at_gmt"))
    bindings = response.get("proposal_bindings")
    if type(bindings) is not dict or set(bindings) != set(ids):
        fail("SERVER_PROPOSAL_BINDING_REQUIRED")
    envelope = receipt["release_envelope"]
    for proposal in receipt["proposals"]:
        target = "theme" if proposal["kind"] == "THEME_RELEASE" else proposal["slug"]
        binding = bindings[proposal["proposal_id"]]
        if type(binding) is not dict or set(binding) != {
            "kind",
            "idempotency_key",
            "before_sha256",
            "after_sha256",
            "post_id",
            "post_type",
        }:
            fail("SERVER_PROPOSAL_BINDING_INVALID")
        if (
            binding["kind"] != proposal["kind"]
            or binding["idempotency_key"]
            != publication.sha256_json(
                {"release_sha256": receipt["release_sha256"], "target": target}
            )
            or binding["after_sha256"] != proposal["after_sha256"]
        ):
            fail("SERVER_PROPOSAL_BINDING_INVALID")
        if target == "theme":
            if binding["post_id"] is not None or binding["post_type"] is not None:
                fail("SERVER_PROPOSAL_BINDING_INVALID")
        else:
            expected = envelope["inventory"][target]
            if (
                binding["post_id"] != expected["post_id"]
                or binding["post_type"] != expected["post_type"]
                or binding["before_sha256"] != expected["content_sha256"]
            ):
                fail("SERVER_PROPOSAL_BINDING_INVALID")
    return response


def _stored_document_sha256(document: Mapping[str, Any]) -> str:
    """Hash the observed state, not the intended status of a release proposal."""
    if document.get("status") not in {"draft", "publish"}:
        fail("LIVE_DOCUMENT_STATUS_INVALID")
    return publication.sha256_json(
        {
            "schema": "ContentDocumentV1",
            "id": document["id"],
            "status": document["status"],
            **publication.document_projection(document),
        }
    )


def _live_documents(client: Any) -> dict[str, dict[str, Any]]:
    listed = publication.list_all_documents(client, post_types=("post", "page"))
    result = {}
    for row in listed:
        document = client.call("raos-codex-content-get", {"id": row["id"]})
        if document != row or _stored_document_sha256(document) != document.get(
            "content_sha256"
        ):
            fail("LIVE_DOCUMENT_CHANGED_DURING_READ")
        if document["slug"] in result:
            fail("LIVE_DUPLICATE_SLUG")
        result[document["slug"]] = document
    return result


def _require_before(
    replayed: ReplayedCandidate,
    current: Mapping[str, Any],
    deployment: Mapping[str, Any],
) -> None:
    expected_all = replayed.snapshot["all_document_baselines"]
    if {
        str(row["id"]): publication._baseline_record(row) for row in current.values()
    } != expected_all:
        fail("LIVE_BASELINE_CHANGED")
    theme = deployment.get("theme")
    baseline = (
        replayed.snapshot.get("deployment_status", {})
        .get("theme", {})
        .get("tree_sha256")
    )
    if type(theme) is not dict or theme.get("tree_sha256") != baseline:
        fail("LIVE_THEME_BASELINE_CHANGED")


def _require_before_or_bound_progress(
    replayed: ReplayedCandidate,
    current: Mapping[str, Any],
    deployment: Mapping[str, Any],
    receipt: Mapping[str, Any],
    batch: Mapping[str, Any],
    client: Any,
    deploy: Callable[..., dict[str, Any]],
) -> None:
    """Permit selected partial progress only through immutable server evidence.

    This is a read-only gate into the existing lease-bound recovery adapter,
    not an inference that an after hash authorizes applying or resending a member.
    Unselected documents retain their complete original baseline, including
    revision and modification time; a selected before state does too.
    """
    expected_all = replayed.snapshot["all_document_baselines"]
    current_all = {
        str(row["id"]): publication._baseline_record(row) for row in current.values()
    }
    selected_ids = {
        str(row["post_id"])
        for row in replayed.preparation["production_documents"].values()
    }
    if (
        len(current) != len(expected_all)
        or set(current_all) != set(expected_all)
        or any(
            current_all[key] != baseline
            for key, baseline in expected_all.items()
            if key not in selected_ids
        )
    ):
        fail("LIVE_BASELINE_CHANGED")
    baseline_theme = replayed.snapshot["deployment_status"]["theme"]["tree_sha256"]
    selected_theme = "theme" in replayed.manifest["shared_artifacts"]
    if not selected_theme and deployment["theme"]["tree_sha256"] != baseline_theme:
        fail("LIVE_THEME_BASELINE_CHANGED")

    operations = publication.read_content_operations(client, receipt)
    for proposal in receipt["proposals"]:
        identifier = proposal["proposal_id"]
        if proposal["kind"] == "THEME_RELEASE":
            response = deploy("operation-status", {"operation_id": identifier})
            if (
                set(response) != {"kind", "operation"}
                or response["kind"] != "THEME_RELEASE"
            ):
                fail("APPLY_OPERATION_READBACK_INVALID")
            operations[identifier] = response["operation"]
        try:
            operation = wordpress_deployment._validated_release_operation(
                operations.get(identifier), identifier
            )
        except wordpress_deployment.OperatorFailure:
            fail("APPLY_OPERATION_READBACK_INVALID")
        binding = batch["proposal_bindings"][identifier]
        if any(
            operation[key] != binding[key] for key in ("before_sha256", "after_sha256")
        ):
            fail("APPLY_OPERATION_BINDING_INVALID")

        if proposal["kind"] == "THEME_RELEASE":
            if not selected_theme or binding["before_sha256"] != baseline_theme:
                fail("SERVER_PROPOSAL_BINDING_INVALID")
            live_hash = deployment["theme"]["tree_sha256"]
            at_before = live_hash == binding["before_sha256"]
            at_after = live_hash == binding["after_sha256"]
        else:
            slug = proposal["slug"]
            post_id = str(binding["post_id"])
            live = current.get(slug)
            if (
                post_id not in selected_ids
                or live is None
                or live["id"] != binding["post_id"]
                or live["post_type"] != binding["post_type"]
                or (live["status"] != expected_all[post_id]["status"] and not (
                    replayed.manifest.get("reader_pages", {}).get(slug, {}).get("kind") == "hub"
                    and expected_all[post_id]["status"] == "draft" and live["status"] == "publish"
                ))
            ):
                fail("LIVE_SELECTED_IDENTITY_CHANGED")
            at_before = current_all[post_id] == expected_all[post_id]
            at_after = live["status"] == "publish" and live["content_sha256"] == binding["after_sha256"]
        state, code = operation["state"], operation["result_code"]
        before_allowed = (state, code) in {
            ("APPROVED", "PROPOSAL_APPROVED"),
            ("APPLYING", "BATCH_CLAIMED"),
            ("APPLYING", "OPERATION_APPLYING"),
        }
        after_allowed = state == "APPLIED" or (state, code) == (
            "APPLYING",
            "OPERATION_APPLYING",
        )
        if not ((at_before and before_allowed) or (at_after and after_allowed)):
            fail("LIVE_SELECTED_OPERATION_STATE_MISMATCH")
    if set(operations) != set(_ids(receipt)):
        fail("APPLY_OPERATION_READBACK_INVALID")


def _validate_deployment_status(
    response: Mapping[str, Any], *, require_apply_ready: bool, allow_legacy_runtime: bool = False
) -> None:
    """Preserve the legacy closed gates without requiring the new theme yet."""
    theme, gates = response.get("theme"), response.get("gates")
    if (
        response.get("schema") != "RAOSWordPressDeploymentStatusV1"
        or response.get("origin") != publication.ORIGIN
        or (response.get("plugin_runtime_revision") != publication.EXPECTED_PLUGIN_RUNTIME_REVISION
            and not (allow_legacy_runtime is True and response.get("plugin_runtime_revision") == "c0dfb252e3920e87128fed6952f6a5f9ce099b57f2aed96d380ce3b02556f472"))
        or response.get("private_directory_ready") is not True
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or type(theme.get("tree_sha256")) is not str
        or publication.SHA256_RE.fullmatch(theme["tree_sha256"]) is None
        or type(gates) is not dict
        or any(
            type(gates.get(key)) is not bool
            for key in ("global", "content_apply", "theme_apply")
        )
        or (
            require_apply_ready
            and any(
                gates.get(key) is not True
                for key in ("global", "content_apply", "theme_apply")
            )
        )
        or response.get("apply_authorization")
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
        }
    ):
        fail("DEPLOYMENT_STATUS_INVALID")


def _validate_apply_receipt(
    receipt: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    ids = _ids(receipt)
    registration = receipt["batch_registration"]
    operations = response.get("receipts")
    if (
        response.get("schema") != "ReleaseWaitApplyReceiptV1"
        or response.get("state") != "APPLIED"
        or response.get("proposal_ids") != ids
        or response.get("proposal_count") != len(ids)
        or any(
            response.get(key) != registration[key]
            for key in ("batch_token", "batch_manifest_sha256")
        )
        or type(operations) is not list
        or len(operations) != len(ids)
    ):
        fail("APPLY_RECEIPT_INVALID")
    proposals = {row["proposal_id"]: row for row in receipt["proposals"]}
    observed = set()
    for operation in operations:
        if type(operation) is not dict:
            fail("APPLY_RECEIPT_INVALID")
        identifier = operation.get("proposal_id")
        if (
            identifier not in proposals
            or identifier in observed
            or operation.get("schema") != "OperationReceiptV1"
            or operation.get("state") != "APPLIED"
            or operation.get("operation_id") != identifier
            or operation.get("after_sha256") != proposals[identifier]["after_sha256"]
            or type(operation.get("audit_id")) is not str
            or publication.SHA256_RE.fullmatch(operation["audit_id"]) is None
            or type(operation.get("result_code")) is not str
            or re.fullmatch(r"[A-Z0-9_]{3,96}", operation["result_code"]) is None
        ):
            fail("APPLY_RECEIPT_INVALID")
        observed.add(identifier)


def _operation_readback(
    receipt: Mapping[str, Any],
    client: Any,
    deploy: Callable[..., dict[str, Any]],
) -> dict[str, dict[str, object]]:
    """Recover real operation evidence by GET only, including a shared theme."""
    observed = publication.read_content_operations(client, receipt)
    publication._require_applied_receipt_content_operations(receipt, observed)
    for proposal in receipt["proposals"]:
        if proposal["kind"] != "THEME_RELEASE":
            continue
        response = deploy("operation-status", {"operation_id": proposal["proposal_id"]})
        if (
            set(response) != {"kind", "operation"}
            or response["kind"] != "THEME_RELEASE"
            or type(response["operation"]) is not dict
        ):
            fail("THEME_OPERATION_READBACK_INVALID")
        observed[proposal["proposal_id"]] = response["operation"]
    # Reuse aggregate member validation without pretending the GET observations
    # were a new apply response or synthesizing an owner approval.
    validation_projection = {
        "schema": "ReleaseWaitApplyReceiptV1",
        "state": "APPLIED",
        "proposal_ids": _ids(receipt),
        "proposal_count": len(observed),
        "batch_token": receipt["batch_registration"]["batch_token"],
        "batch_manifest_sha256": receipt["batch_registration"]["batch_manifest_sha256"],
        "receipts": list(observed.values()),
    }
    _validate_apply_receipt(receipt, validation_projection)
    return observed


def _validate_public_binding(
    visible: Mapping[str, object],
    context: VerifiedIncrementalReleaseV1,
    snapshot: Mapping[str, Any],
    preparation_raw: bytes,
    expected_theme: str,
    site_status: Mapping[str, object],
    *, post_activation: bool = False,
) -> None:
    envelope = context.to_document()
    binding = envelope.get("reader_measurement")
    schema = visible.get("schema")
    if type(post_activation) is not bool:
        fail("PUBLIC_READBACK_BINDING_INVALID")
    if schema == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V2":
        # Reconstruct metadata from the fixed, hash-checked theme independently
        # of the report. A self-consistent V2 report is not its own authority.
        seo_owner = importlib.import_module("raos_wordpress_incremental_seo_audit")
        expected_metadata = seo_owner.build_reader_seo_metadata(expected_theme)
        if visible.get("reader_metadata_sha256") != digest(
            publication.canonical_json_bytes(expected_metadata.to_document())
        ):
            fail("PUBLIC_READER_METADATA_BINDING_INVALID")
        if binding is None and visible.get("reader_measurement") != {
            "state": "NOT_INCLUDED"
        }:
            fail("PUBLIC_READER_READBACK_BINDING_INVALID")
    elif (
        schema != "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V1"
        or envelope.get("schema") == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V2"
        or binding is not None
        or "reader_metadata_sha256" in visible
        or "reader_measurement" in visible
    ):
        fail("PUBLIC_READBACK_BINDING_INVALID")
    if binding is not None:
        expected_reader = {
            **{key: value for key, value in binding.items() if key != "schema"},
            "expected_collection_enabled": post_activation,
            "mode": "post-activation-readback" if post_activation else "release",
            "state": "DECLARED_RUNTIME_AND_MCP_STATUS_VERIFIED",
        }
        observed_reader = visible.get("reader_measurement")
        if (
            type(observed_reader) is not dict
            or type(observed_reader.get("expected_collection_enabled")) is not bool
            or observed_reader != expected_reader
        ):
            fail("PUBLIC_READER_READBACK_BINDING_INVALID")
    elif post_activation:
        fail("READER_RUNTIME_BINDING_INVALID")
    unsigned = {key: value for key, value in visible.items() if key != "binding_sha256"}
    if (
        visible.get("status") != "PUBLIC_READBACK_PASSED"
        or visible.get("publication_profile") != PROFILE
        or visible.get("link_mode") != "standard-api"
        or visible.get("publication_authority") is not False
        or visible.get("measurement_collection_enabled") is not False
        or visible.get("release_sha256") != context.sha256
        or visible.get("manifest_sha256") != envelope["manifest_sha256"]
        or visible.get("snapshot_sha256")
        != digest(publication.canonical_json_bytes(snapshot))
        or visible.get("candidate_preparation_sha256") != digest(preparation_raw)
        or visible.get("theme_tree_sha256") != expected_theme
        or visible.get("site_status_sha256")
        != digest(publication.canonical_json_bytes(site_status))
        or visible.get("monetization_state") != envelope["monetization_state"]
        or visible.get("binding_sha256")
        != digest(publication.canonical_json_bytes(unsigned))
    ):
        fail("PUBLIC_READBACK_BINDING_INVALID")


def runtime_precondition_matches(
    observed: Mapping[str, Any], manifest: Mapping[str, Any], current_tree: str
) -> bool:
    """Never promote a transitional observation into the strict OFF state."""
    if observed.get("theme_tree_sha256") != current_tree:
        return False
    binding = manifest.get("reader_measurement")
    reader = observed.get("reader_measurement")
    if binding is None:
        if reader is not None:
            return False
    elif (type(reader) is not dict or any(reader.get(key) != binding[key] for key in ("profile", "manifest_sha256", "policy_sha256", "contract_sha256", "revision", "expected_collection_enabled"))
        or reader.get("collection_state") != "OFF"):
        return False
    policy = manifest.get("runtime_transition")
    if policy is None or current_tree != policy["baseline_theme_sha256"]:
        return (
            observed.get("state") == "CLOSED_DECLARED_RUNTIME_VERIFIED"
            and "runtime_transition_sha256" not in observed
        )
    pages = observed.get("pages")
    return (
        observed.get("state") == DNS_TRANSITION_STATE
        and observed.get("runtime_transition_sha256") == digest(canonical(policy))
        and type(pages) is dict
        and set(pages) == set(policy["expected_baseline_hints"])
        and all(
            type(page) is dict
            and type(page.get("dns_hints")) is int
            and page["dns_hints"] == 1
            for page in pages.values()
        )
    )


def reader_runtime_for(document: Mapping[str, Any], *, post_activation: bool = False) -> Any:
    binding = document.get("reader_measurement")
    if type(post_activation) is not bool or (post_activation and binding is None):
        fail("READER_RUNTIME_BINDING_INVALID")
    if binding is None:
        return None
    import raos_wordpress_runtime_audit as runtime
    result = runtime.build_reader_measurement_runtime(
        expected_manifest_sha256=binding["manifest_sha256"],
        expected_policy_sha256=binding["policy_sha256"],
        expected_collection_enabled=post_activation,
    )
    if (binding.get("expected_collection_enabled") is not False
        or result.contract_sha256 != binding["contract_sha256"]
        or result.revision != binding["revision"]):
        fail("READER_RUNTIME_BINDING_INVALID")
    return result



def _resume_completed_proposal_registration(
    candidate_path: Path,
    receipt: dict[str, Any],
    replayed: ReplayedCandidate,
    *,
    client: Any,
    deploy: Callable[..., dict[str, Any]],
    clock: Callable[[], datetime],
) -> Path:
    """Reconcile every saved member; never resend a proposal or approve it."""
    if (
        receipt.get("state") != "PROPOSALS_IN_PROGRESS"
        or receipt.get("inflight_proposal") is not None
        or receipt.get("batch_registration") is not None
    ):
        fail("PROPOSAL_OUTCOME_REQUIRES_RECONCILIATION")
    ids = publication._proposal_ids(receipt)
    selected_theme = "theme" in replayed.manifest["shared_artifacts"]
    if sum(row["kind"] == "THEME_RELEASE" for row in receipt["proposals"]) != int(selected_theme):
        fail("REQUEST_THEME_BINDING_INVALID")
    receipt["operation_ids"] = {identifier: identifier for identifier in ids}
    operations = publication.read_content_operations(client, receipt)
    for proposal in receipt["proposals"]:
        identifier = proposal["proposal_id"]
        theme = proposal["kind"] == "THEME_RELEASE"
        if theme:
            response = deploy("operation-status", {"operation_id": identifier})
            if set(response) != {"kind", "operation"} or response["kind"] != "THEME_RELEASE":
                fail("PROPOSAL_OPERATION_READBACK_INVALID")
            operations[identifier] = response["operation"]
        try:
            operation = wordpress_deployment._validated_release_operation(
                operations.get(identifier), identifier
            )
        except wordpress_deployment.OperatorFailure:
            fail("PROPOSAL_OPERATION_READBACK_INVALID")
        before = (
            replayed.snapshot["deployment_status"]["theme"]["tree_sha256"]
            if theme
            else receipt["release_envelope"]["inventory"][proposal["slug"]]["content_sha256"]
        )
        if (
            operation["state"] != "PENDING"
            or operation["result_code"] != "PROPOSAL_CREATED"
            or operation["before_sha256"] != before
            or operation["after_sha256"] != proposal["after_sha256"]
            or clock() >= instant(proposal["expires_at_gmt"])
        ):
            fail("PROPOSAL_OPERATION_NOT_PENDING_OR_CHANGED")
    validate_release_envelope(
        receipt["release_envelope"], current_context=replayed.context,
        publication_profile=PROFILE, link_mode="standard-api",
        stage="proposal", now=clock(),
    )
    _save(candidate_path, receipt, "REGISTRATION_IN_FLIGHT")
    registration = client.call(
        "raos-codex-publication-batch-register",
        {
            "proposal_ids": sorted(ids),
            "expected_theme_tree_sha256": receipt["desired_theme_tree_sha256"],
        },
    )
    receipt["batch_registration"] = registration
    _ids(receipt)
    status = _batch_status(receipt, deploy)
    if (
        status["state"] not in {"REGISTERED", "APPROVED"}
        or status["preconditions_ready"] is not True
        or clock() >= instant(status["expires_at_gmt"])
    ):
        _save(candidate_path, receipt, "REGISTRATION_REQUIRES_RECONCILIATION")
        fail("EXISTING_BATCH_NOT_READY_OR_EXPIRED")
    _save(candidate_path, receipt, "AWAITING_OWNER_APPROVAL")
    print("保存済み提案の状態を照合し、承認対象を登録しました。まだ公開していません。")
    print(publication.REVIEW_URL)
    print(f"承認対象の識別末尾: {registration['batch_token'][-12:]} / {registration['batch_manifest_sha256'][-8:]}")
    return candidate_path / "publication-request.v1.json"

def execute_incremental(
    candidate_path: Path,
    *,
    stage: str,
    implementation_execution_ids: tuple[str, ...],
    browser_validator: Callable[..., Mapping[str, object]],
    public_readback_validator: Callable[..., Mapping[str, object]],
    client_factory: Callable[[], Any] = lambda: publication.EditorMcpClient(
        owner_checkout=OWNER
    ),
    deploy: Callable[..., dict[str, Any]] = deployment_call,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    runtime_precondition: Callable[..., Mapping[str, Any]] | None = None,
    verification_base: str = "origin/main",
    reader_measurement_readback: bool = False,
) -> Path:
    """Explicit stages. Proposal only registers; apply uses the server's lease."""
    if type(reader_measurement_readback) is not bool or (reader_measurement_readback and stage != "readback"):
        fail("READER_READBACK_STAGE_INVALID")
    if stage not in {"propose", "apply", "readback"}:
        fail("STAGE_INVALID")
    _candidate_directory(candidate_path)
    lock_path = candidate_path / "publication.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            fail("LOCK_INVALID")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_file = candidate_path / "publication-request.v1.json"
        receipt = (
            read_json(candidate_path, receipt_file.name)[0]
            if receipt_file.exists()
            else None
        )
        original_context = (
            _validate_request(receipt, candidate_path) if receipt else None
        )
        if stage in {"apply", "readback"} and receipt is None:
            fail("REGISTERED_REQUEST_REQUIRED")
        client = None
        if stage == "apply":
            # Query the durable server state before freshness replay. An
            # already-applied batch must never be resent after evidence expiry.
            assert receipt is not None
            client = client_factory()
            client.initialize()
            observed_batch = _batch_status(receipt, deploy)
            if observed_batch["state"] == "APPLIED":
                stage = "readback"
        # Readback is permitted after expiry without rebuilding/extending proof.
        replayed = (
            None
            if stage == "readback"
            else load_candidate(
                candidate_path,
                implementation_execution_ids=implementation_execution_ids,
                now=clock(),
                browser_validator=browser_validator,
                verification_base=verification_base,
                activation_evaluated_at=(
                    instant(original_context.to_document()["evaluated_at"])
                    if original_context is not None
                    else None
                ),
            )
        )
        if replayed is not None and original_context is not None:
            validate_release_envelope(
                original_context.to_document(),
                current_context=replayed.context,
                publication_profile=PROFILE,
                link_mode="standard-api",
                stage="resume",
                now=clock(),
            )
            expected_theme = cast(dict[str, Any], replayed.context.to_document())[
                "expected_shared_readback_sha256"
            ].get(
                "theme", replayed.snapshot["deployment_status"]["theme"]["tree_sha256"]
            )
            if (
                receipt is None
                or receipt.get("desired_theme_tree_sha256") != expected_theme
            ):
                fail("REQUEST_THEME_BINDING_INVALID")
        if client is None:
            client = client_factory()
            client.initialize()
        status = client.call("raos-codex-site-status", {})
        bound_document = replayed.manifest if replayed is not None else original_context.to_document()
        legacy_runtime = "reader_measurement" not in bound_document and "privacy-policy" not in bound_document.get("reader_pages", bound_document.get("selected_pages", {}))
        if reader_measurement_readback:
            reader_runtime_for(bound_document, post_activation=True)
            if status.get("measurement", {}).get("collection_enabled") is not False:
                fail("LEGACY_MEASUREMENT_NOT_OFF")
        publication.validate_site_status(status, require_measurement_off=not reader_measurement_readback, allow_legacy_runtime=legacy_runtime)
        deployment = deploy("deployment-status", {})
        _validate_deployment_status(deployment, require_apply_ready=stage != "readback", allow_legacy_runtime=legacy_runtime)
        current = _live_documents(client)
        if stage != "readback":
            # MCP's measurement field only covers the RAOS plugin. Independently
            # inspect the currently installed (baseline or bound candidate) public
            # runtime before creating proposals or attempting any new writes.
            import raos_wordpress_runtime_audit as runtime

            assert replayed is not None
            runtime_before = (runtime_precondition or runtime.verify_before_write)(
                current_tree=deployment["theme"]["tree_sha256"],
                baseline_tree=replayed.snapshot["deployment_status"]["theme"][
                    "tree_sha256"
                ],
                candidate_tree=replayed.context.to_document()[
                    "expected_shared_readback_sha256"
                ].get(
                    "theme",
                    replayed.snapshot["deployment_status"]["theme"]["tree_sha256"],
                ),
                now=clock(),
                snapshot=replayed.snapshot,
                runtime_transition=replayed.manifest.get("runtime_transition"),
                **({"reader_measurement": reader_runtime_for(replayed.manifest)} if "reader_measurement" in replayed.manifest else {}),
            )
            if not runtime_precondition_matches(
                runtime_before, replayed.manifest, deployment["theme"]["tree_sha256"]
            ):
                fail("PUBLIC_RUNTIME_PRECONDITION_FAILED")
        if stage == "propose":
            assert replayed is not None
            _require_before(replayed, current, deployment)
            if receipt is not None:
                if receipt.get("batch_registration"):
                    batch = _batch_status(receipt, deploy)
                    if batch["state"] not in {"REGISTERED", "APPROVED"}:
                        fail("EXISTING_BATCH_TERMINAL_REQUIRES_RECONCILIATION")
                    if batch["preconditions_ready"] is not True or clock() >= instant(
                        batch["expires_at_gmt"]
                    ):
                        fail("EXISTING_BATCH_NOT_READY_OR_EXPIRED")
                    return receipt_file
                return _resume_completed_proposal_registration(
                    candidate_path, receipt, replayed,
                    client=client, deploy=deploy, clock=clock,
                )
            context = replayed.context
            envelope = cast(dict[str, Any], context.to_document())
            desired_theme = envelope["expected_shared_readback_sha256"].get(
                "theme", deployment["theme"]["tree_sha256"]
            )
            documents = replayed.preparation["production_documents"]
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "publication_profile": PROFILE,
                "link_mode": "standard-api",
                "candidate_sha256": candidate_path.name,
                "release_sha256": context.sha256,
                "release_envelope": envelope,
                "preview_binding": dict(replayed.preview_binding),
                "selected_slugs": sorted(documents),
                "selected_documents": {
                    slug: row["document"]["post_type"]
                    for slug, row in documents.items()
                },
                "desired_theme_tree_sha256": desired_theme,
                "proposals": [],
                "operation_ids": {},
                "batch_registration": None,
                "apply_receipt": None,
                "runtime_before_proposal": runtime_before,
            }
            _save(candidate_path, receipt, "PROPOSALS_IN_PROGRESS")
            if "theme" in replayed.manifest["shared_artifacts"]:
                validate_release_envelope(
                    envelope,
                    current_context=context,
                    publication_profile=PROFILE,
                    link_mode="standard-api",
                    stage="proposal",
                    now=clock(),
                )
                key = publication.sha256_json(
                    {"release_sha256": context.sha256, "target": "theme"}
                )
                receipt["inflight_proposal"] = {
                    "target": "theme",
                    "idempotency_key": key,
                }
                _save(candidate_path, receipt, "PROPOSAL_CALL_IN_FLIGHT")
                response = deploy("theme-propose-release", {"idempotency_key": key})
                receipt["proposals"].append(
                    publication._proposal_record(
                        kind="THEME_RELEASE",
                        slug=None,
                        key=key,
                        response=response,
                        expected_after=desired_theme,
                    )
                )
                receipt.pop("inflight_proposal", None)
                _save(candidate_path, receipt, "PROPOSALS_IN_PROGRESS")
            for slug, row in sorted(documents.items()):
                validate_release_envelope(
                    envelope,
                    current_context=context,
                    publication_profile=PROFILE,
                    link_mode="standard-api",
                    stage="proposal",
                    now=clock(),
                )
                key = publication.sha256_json(
                    {"release_sha256": context.sha256, "target": slug}
                )
                receipt["inflight_proposal"] = {"target": slug, "idempotency_key": key}
                _save(candidate_path, receipt, "PROPOSAL_CALL_IN_FLIGHT")
                response = client.call(
                    "raos-codex-content-propose-release",
                    {
                        "id": row["post_id"],
                        "precondition": row["baseline_precondition"],
                        "document": row["document"],
                        "idempotency_key": key,
                    },
                )
                receipt["proposals"].append(
                    publication._proposal_record(
                        kind="CONTENT_RELEASE",
                        slug=slug,
                        key=key,
                        response=response,
                        expected_after=row["after_sha256"],
                        post_type=row["document"]["post_type"],
                    )
                )
                receipt.pop("inflight_proposal", None)
                _save(candidate_path, receipt, "PROPOSALS_IN_PROGRESS")
            receipt["operation_ids"] = {
                row["proposal_id"]: row["proposal_id"] for row in receipt["proposals"]
            }
            ids = sorted(publication._proposal_ids(receipt))
            validate_release_envelope(
                envelope,
                current_context=context,
                publication_profile=PROFILE,
                link_mode="standard-api",
                stage="proposal",
                now=clock(),
            )
            _save(candidate_path, receipt, "REGISTRATION_IN_FLIGHT")
            registration = client.call(
                "raos-codex-publication-batch-register",
                {"proposal_ids": ids, "expected_theme_tree_sha256": desired_theme},
            )
            receipt["batch_registration"] = registration
            _ids(receipt)
            registered_status = _batch_status(receipt, deploy)
            if registered_status["state"] not in {
                "REGISTERED",
                "APPROVED",
            } or clock() >= instant(registered_status["expires_at_gmt"]):
                _save(candidate_path, receipt, "REGISTRATION_REQUIRES_RECONCILIATION")
                fail("EXISTING_BATCH_TERMINAL_REQUIRES_RECONCILIATION")
            _save(candidate_path, receipt, "AWAITING_OWNER_APPROVAL")
            print(
                "公開提案を登録しました。まだ公開していません。WordPress管理画面で対象の差分とハッシュを確認して承認してください。"
            )
            print(publication.REVIEW_URL)
            if "runtime_transition" in replayed.manifest:
                print(
                    "移行条件: 公開前は拘束済み旧テーマのGoogle DNS事前参照1件/対象URLを許容。"
                    "新テーマ適用後は0件必須。Site Kitは保持、計測はOFF。他のruntime検査は維持。"
                )
            print(
                f"承認対象の識別末尾: {registration['batch_token'][-12:]} / {registration['batch_manifest_sha256'][-8:]}"
            )
            return receipt_file
        assert receipt is not None and original_context is not None
        batch = _batch_status(receipt, deploy)
        if stage == "apply" and batch["state"] != "APPLIED":
            assert replayed is not None
            if batch["state"] != "APPROVED" or batch["preconditions_ready"] is not True:
                fail("OWNER_APPROVAL_REQUIRED_OR_BATCH_TERMINAL")
            if clock() >= instant(batch["expires_at_gmt"]):
                fail("BATCH_APPROVAL_EXPIRED")
            _require_before_or_bound_progress(
                replayed, current, deployment, receipt, batch, client, deploy
            )
            if clock() >= instant(batch["expires_at_gmt"]):
                fail("BATCH_APPROVAL_EXPIRED")
            validate_release_envelope(
                original_context.to_document(),
                current_context=replayed.context,
                publication_profile=PROFILE,
                link_mode="standard-api",
                stage="apply",
                now=clock(),
            )
            registration = receipt["batch_registration"]
            receipt["runtime_before_apply"] = runtime_before
            _save(candidate_path, receipt, "APPLY_IN_FLIGHT")
            applied = deploy(
                "release-wait-and-apply",
                {
                    "batch_token": registration["batch_token"],
                    "batch_manifest_sha256": registration["batch_manifest_sha256"],
                    "proposal_ids": _ids(receipt),
                    "evidence_expires_at_gmt": original_context.to_document()[
                        "expires_at"
                    ],
                },
            )
            _validate_apply_receipt(receipt, applied)
            receipt["apply_receipt"] = applied
            _save(candidate_path, receipt, "APPLIED_READBACK_PENDING")
            batch = _batch_status(receipt, deploy)
        if batch["state"] != "APPLIED":
            fail("APPLIED_BATCH_REQUIRED")
        current = _live_documents(client)
        envelope = cast(dict[str, Any], original_context.to_document())
        preparation, preparation_raw = read_json(
            candidate_path, "candidate-preparation.v1.json"
        )
        if digest(preparation_raw) != envelope["audit_artifact_hashes"].get(
            "candidate-preparation"
        ):
            fail("READBACK_PREPARATION_BINDING_INVALID")
        snapshot, _raw = read_json(
            PRIVATE / "incremental-snapshots", preparation.get("snapshot_name", "")
        )
        if digest(publication.canonical_json_bytes(snapshot)) != envelope[
            "audit_artifact_hashes"
        ].get("live-snapshot"):
            fail("READBACK_SNAPSHOT_BINDING_INVALID")
        original_all = snapshot["all_document_baselines"]
        current_all = {
            str(row["id"]): publication._baseline_record(row)
            for row in current.values()
        }
        selected_ids = {
            str(row["post_id"]) for row in preparation["production_documents"].values()
        }
        if set(current_all) != set(original_all) or any(
            current_all[key] != value
            for key, value in original_all.items()
            if key not in selected_ids
        ):
            fail("READBACK_UNCHANGED_COMPLEMENT_CHANGED")
        operations = _operation_readback(receipt, client, deploy)
        receipt["operation_readback"] = {
            "schema": "RAOS_WORDPRESS_INCREMENTAL_OPERATION_READBACK_V1",
            "source": "BOUNDED_WORDPRESS_READ_ONLY_OPERATIONS",
            "release_sha256": original_context.sha256,
            "batch_status": batch,
            "operations": operations,
            "apply_response_received": receipt.get("apply_receipt") is not None,
            "publication_authority": False,
        }
        core = {
            slug: ExistingDocument(
                row["id"], slug, row["post_type"], row["content_sha256"], row["status"]
            )
            for slug, row in current.items()
            if slug in envelope["inventory"]
        }
        deployment = deploy("deployment-status", {})
        _validate_deployment_status(deployment, require_apply_ready=False, allow_legacy_runtime=legacy_runtime)
        expected_theme = envelope["expected_shared_readback_sha256"].get(
            "theme", snapshot["deployment_status"]["theme"]["tree_sha256"]
        )
        if (
            receipt["desired_theme_tree_sha256"] != expected_theme
            or deployment["theme"]["tree_sha256"] != expected_theme
        ):
            fail("READBACK_THEME_CHANGED")
        shared_hashes = (
            {"theme": deployment["theme"]["tree_sha256"]}
            if "theme" in envelope["expected_shared_readback_sha256"]
            else {}
        )
        parity = verify_release_readback(
            original_context,
            current_inventory=core,
            shared_readback_sha256=shared_hashes,
            now=clock(),
        )
        site_status = client.call("raos-codex-site-status", {})
        if reader_measurement_readback and site_status.get("measurement", {}).get("collection_enabled") is not False:
            fail("LEGACY_MEASUREMENT_NOT_OFF")
        publication.validate_site_status(site_status, require_measurement_off=not reader_measurement_readback, allow_legacy_runtime=legacy_runtime)
        visible = public_readback_validator(
            context=original_context,
            candidate_path=candidate_path,
            original_snapshot=snapshot,
            current_documents=current,
            now=clock(),
            deployment_readback=deployment,
            site_status_readback=site_status,
        )
        _validate_public_binding(
            visible,
            original_context,
            snapshot,
            preparation_raw,
            expected_theme,
            site_status,
            post_activation=reader_measurement_readback,
        )
        if reader_measurement_readback:
            receipt["reader_measurement_readback"] = {"content": parity, "public": dict(visible)}
            _save(candidate_path, receipt, "READER_MEASUREMENT_READBACK_VERIFIED")
        else:
            receipt["readback"] = {"content": parity, "public": dict(visible)}
            _save(candidate_path, receipt, "PUBLISHED_AND_READBACK_VERIFIED")
        return receipt_file
    except BlockingIOError:
        fail("REQUEST_ALREADY_RUNNING")
    finally:
        os.close(descriptor)


def execute_cli(arguments: Any) -> Path:
    """Closed explicit dispatch; no legacy proof is accepted for this profile."""
    if (
        arguments.publication_profile != PROFILE
        or arguments.link_mode != "standard-api"
        or arguments.incremental_candidate is None
        or arguments.incremental_stage not in {"propose", "apply", "readback"}
        or arguments.articles != "all"
        or any(
            (
                arguments.standard_api_receipt,
                arguments.rakuten_activation_dry_run,
                arguments.measurement_plugin_apply_receipt,
                arguments.quality_audit_attestation,
                arguments.quality_audit_signature,
            )
        )
        or (
            arguments.incremental_stage != "readback"
            and arguments.quality_audit_mode != "codex-owner"
        )
        or (
            arguments.codex_audit_report is not None
            and arguments.codex_audit_report
            != arguments.incremental_candidate / "audit/report.v1.json"
        )
    ):
        fail("EXPLICIT_PROFILE_INPUTS_REQUIRED")

    post_activation = getattr(arguments, "incremental_reader_measurement_readback", False)
    if type(post_activation) is not bool or (post_activation and arguments.incremental_stage != "readback"):
        fail("READER_READBACK_STAGE_INVALID")

    def browser(**kwargs: Any) -> Mapping[str, object]:
        fixture = arguments.incremental_preview_fixture
        if fixture is None:
            fail("PREVIEW_FIXTURE_REQUIRED")
        return validate_candidate_browser(**kwargs, fixture_root=fixture)

    def public(**kwargs: Any) -> Mapping[str, object]:
        module = importlib.import_module("raos_wordpress_incremental_seo_audit")
        try:
            envelope = kwargs["context"].to_document()
            kwargs["reader_metadata"] = module.build_reader_seo_metadata(kwargs["deployment_readback"]["theme"]["tree_sha256"])
            if "reader_measurement" in envelope:
                kwargs["reader_measurement"] = reader_runtime_for(envelope, post_activation=post_activation)
                if post_activation:
                    kwargs["reader_measurement_mode"] = "post-activation-readback"
            return cast(
                Mapping[str, object],
                module.run_verified_incremental_public_audit(**kwargs),
            )
        except module.seo.AuditError as error:
            code = str(error)
            if re.fullmatch(r"INCREMENTAL_[A-Z0-9_]{3,100}", code):
                publication.fail(code)
            fail("PUBLIC_READBACK_FAILED")

    try:
        return execute_incremental(
            arguments.incremental_candidate,
            stage=arguments.incremental_stage,
            implementation_execution_ids=tuple(
                arguments.incremental_implementation_execution_id
            ),
            browser_validator=browser,
            public_readback_validator=public,
            verification_base=getattr(arguments, "incremental_base", "origin/main"),
            **({"reader_measurement_readback": True} if post_activation else {}),
        )
    except publication.PublicationFailure:
        raise
    except ValueError, KeyError, TypeError, OSError, ImportError:
        # Provider bodies, private paths and exception repr are not diagnostics.
        fail("EVIDENCE_OR_ADAPTER_NOT_READY")
