"""Pure, immutable incremental release binding; never publication authority.

The orchestrator must replay the manifest, audit, official captures and V2
provider adapters before building this context, and verify wp-admin approval
separately. Typed validator outputs are not signatures or owner attestations.
Production content hashes are ContentDocumentV1 projection hashes, NOT HTML
hashes; the orchestrator must derive them from the artifact-backed documents.

The manifest and two reviews identify a stable audit subject (at most 24 hours).
This separate activation is valid for at most 900 seconds. Replaying an existing
activation must supply its original activation_evaluated_at; adapter replay time
does not renew it. Expired activations permit only inspection/readback.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import NoReturn, cast

from raos.application.editorial import verified_incremental_v1 as manifest_contract
from raos.application.editorial.editorial_portfolio_v2 import ProductEvidenceViewV2
from raos.application.editorial.verified_incremental_audit_v1 import (
    IncrementalAuditScopeV1,
    VerifiedIncrementalAuditBindingV1,
    canonical_json_bytes,
)
from raos.application.editorial.verified_incremental_sources_v1 import (
    SelectedOfficialSourcesV1,
)

SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V1"
READBACK_SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_READBACK_V1"
PROFILE = manifest_contract.PROFILE
LINK_MODE = "standard-api"
STAGES = frozenset({"proposal", "resume", "apply", "readback"})


def _fail(code: str) -> NoReturn:
    manifest_contract.fail(f"RELEASE_{code}")


def _hash(value: object) -> str:
    return manifest_contract.validate_hash(value)


def _hashes(value: Mapping[str, str]) -> dict[str, str]:
    return {
        manifest_contract.validate_text(key): _hash(raw) for key, raw in value.items()
    }


def _time(value: object) -> datetime:
    return manifest_contract.parse_instant(value)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(value: object) -> str:
    return manifest_contract.digest(canonical_json_bytes(value))


@dataclass(frozen=True)
class VerifiedIncrementalReleaseV1:
    """Canonical bytes avoid mutable nested maps in an otherwise frozen object."""

    _canonical_document: bytes

    @property
    def sha256(self) -> str:
        return manifest_contract.digest(self._canonical_document)

    @property
    def expires_at(self) -> datetime:
        return _time(self.to_document()["expires_at"])

    def to_document(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self._canonical_document))

    def to_bytes(self) -> bytes:
        return self._canonical_document


def commerce_receipt_sha256(view: ProductEvidenceViewV2) -> str:
    """Canonical binding of a replayed existing V2 domain object, not a new proof.

    CTA manifest receipts use this digest; image manifest receipts use the
    evidence's image_sha256. URLs occur only inside the hashed material.
    """
    if view.state != "verified" or view.evidence is None:
        _fail("COMMERCE_UNVERIFIED")
    return _digest(asdict(view))


def build_verified_incremental_release_v1(
    manifest_document: Mapping[str, object],
    *,
    validated_manifest: manifest_contract.VerifiedIncrementalManifest,
    audit_binding: VerifiedIncrementalAuditBindingV1,
    audit_scope: IncrementalAuditScopeV1,
    official_sources: SelectedOfficialSourcesV1,
    artifact_bytes: Mapping[str, bytes],
    audit_artifact_bytes: Mapping[str, bytes],
    inventory: Mapping[str, manifest_contract.ExistingDocument],
    article_targets: Mapping[str, tuple[str, int]],
    commerce_views: Mapping[str, ProductEvidenceViewV2],
    image_article_products: Mapping[str, tuple[str, str]],
    cta_bindings: Mapping[str, tuple[str, str, str]],
    expected_production_content_sha256: Mapping[str, str],
    expected_shared_readback_sha256: Mapping[str, str],
    source_article_id_by_article_id: Mapping[str, str],
    now: datetime,
    activation_evaluated_at: datetime | None = None,
) -> VerifiedIncrementalReleaseV1:
    """Bind already-replayed contracts and actual local/production HTML bytes.

    article_targets is the complete authoritative existing-article identity map.
    source_article_id_by_article_id is its explicit selected source-contract
    projection; no prefix guessing occurs. CTA values are article/product/slot.
    audit_artifact_bytes contains actual audited inputs (including all release
    artifacts); extra audit inputs are also rehashed, not accepted as hash maps.
    No commerce means no provider receipt is required or accepted.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("TIME_INVALID")
    doc = dict(manifest_document)
    manifest = validated_manifest
    if (
        doc.get("schema") != manifest_contract.SCHEMA
        or doc.get("publication_profile") != PROFILE
        or doc.get("link_mode") != LINK_MODE
        or doc.get("measurement_collection_enabled") is not False
        or doc.get("publication_authority") is not False
        or _digest(doc) != manifest.manifest_sha256
    ):
        _fail("MANIFEST_BINDING_INVALID")
    if (
        not manifest.evaluated_at
        <= now
        < manifest.expires_at
        <= (manifest.evaluated_at + timedelta(hours=24))
    ):
        _fail("EXPIRED")
    rows = cast(list[dict[str, object]], doc["articles"])
    selected = {article.article_id: article for article in manifest.articles}
    if not selected or len(selected) != len(rows):
        _fail("SCOPE_INVALID")
    if (
        len(set(article_targets.values())) != len(article_targets)
        or {slug for slug, _post_id in article_targets.values()}
        != {slug for slug, entry in inventory.items() if entry.post_type == "post"}
        or any(
            inventory[slug].post_id != post_id
            for slug, post_id in article_targets.values()
        )
    ):
        _fail("IDENTITY_MAP_INVALID")
    if set(source_article_id_by_article_id) != set(selected) or (
        len(set(source_article_id_by_article_id.values())) != len(selected)
    ):
        _fail("SOURCE_IDENTITY_MAP_INVALID")
    sources = official_sources.require_complete()
    if (
        set(sources.article_ids) != set(source_article_id_by_article_id.values())
        or set(sources.article_claim_sources) != set(sources.article_ids)
        or set(sources.article_source_refs) != set(sources.article_ids)
        or _time(sources.evaluated_at) > now
        or set(sources.contract_file_sha256) != {"source_registry", "locator_contract"}
    ):
        _fail("SOURCE_SCOPE_INVALID")
    source_refs: set[str] = set()
    source_expiries: list[datetime] = []
    for ref, receipt in sources.sources.items():
        for value in (
            receipt.evidence_file_sha256,
            receipt.body_file_sha256,
            receipt.response_sha256,
            receipt.locator_binding_sha256,
            *receipt.claim_statement_sha256.values(),
        ):
            _hash(value)
        captured, expires = _time(receipt.retrieved_at), _time(receipt.expires_at)
        if (
            ref != receipt.source_ref
            or not captured <= _time(sources.evaluated_at) <= now < expires
            or expires != captured + timedelta(hours=24)
            or receipt.contract_file_sha256 != sources.contract_file_sha256
        ):
            _fail("SOURCE_EXPIRED_OR_INCONSISTENT")
        source_expiries.append(expires)
    used_artifacts: set[str] = set()
    selected_ctas: set[str] = set()
    selected_images: set[str] = set()
    commercial_products: set[str] = set()
    claims_by_article: dict[str, tuple[str, ...]] = {}
    article_documents: dict[str, object] = {}
    for row in rows:
        article_id = cast(str, row["article_id"])
        article = selected.get(article_id)
        if article is None:
            _fail("SCOPE_INVALID")
        assert article is not None
        if (
            article_targets.get(article_id) != (article.slug, article.post_id)
            or (row["slug"], row["post_id"], row["baseline_sha256"])
            != (article.slug, article.post_id, article.baseline_sha256)
            or inventory[article.slug].content_sha256 != article.baseline_sha256
            or tuple(cast(list[str], row["editorial_product_ids"]))
            != article.editorial_product_ids
            or tuple(sorted(cast(dict[str, str], row["images"]))) != article.image_ids
            or tuple(sorted(cast(dict[str, str], row["ctas"]))) != article.cta_ids
        ):
            _fail("MANIFEST_PROJECTION_INVALID")
        source_article = source_article_id_by_article_id[article_id]
        claim_sources = sources.article_claim_sources[source_article]
        claims = tuple(cast(list[str], row["claim_ids"]))
        if not claims or set(claims) != set(claim_sources):
            _fail("CLAIM_SCOPE_INVALID")
        claims_by_article[article_id] = claims
        refs = {ref for values in claim_sources.values() for ref in values}
        if (
            not refs
            or any(not values for values in claim_sources.values())
            or refs != set(sources.article_source_refs[source_article])
            or row["source_receipts"]
            != {ref: sources.source_receipt_sha256.get(ref) for ref in refs}
            or not refs <= set(sources.sources)
            or any(
                claim not in sources.sources[ref].claim_statement_sha256
                for claim, values in claim_sources.items()
                for ref in values
            )
        ):
            _fail("SOURCE_RECEIPT_BINDING_INVALID")
        source_refs.update(refs)
        expected_images: dict[str, str] = {}
        expected_ctas: dict[str, tuple[str, str, str]] = {}
        for image_id in article.image_ids:
            pair = image_article_products.get(image_id)
            if pair is None or pair[0] != article_id or image_id in selected_images:
                _fail("IMAGE_IDENTITY_INVALID")
            assert pair is not None
            product = pair[1]
            view = commerce_views.get(product)
            if (
                view is None
                or view.evidence is None
                or view.image_extension not in {"jpg", "png", "gif"}
                or product in expected_images
                or cast(dict[str, str], row["images"])[image_id]
                != view.evidence.image_sha256
            ):
                _fail("IMAGE_RECEIPT_INVALID")
            assert view is not None and view.evidence is not None
            expected_images[product] = view.evidence.image_url
            selected_images.add(image_id)
            commercial_products.add(product)
        for cta_id in article.cta_ids:
            identity = cta_bindings.get(cta_id)
            if identity is None or identity[0] != article_id or cta_id in selected_ctas:
                _fail("CTA_IDENTITY_INVALID")
            assert identity is not None
            _, product, placement = identity
            view = commerce_views.get(product)
            if (
                view is None
                or view.evidence is None
                or cast(dict[str, str], row["ctas"])[cta_id]
                != commerce_receipt_sha256(view)
            ):
                _fail("CTA_RECEIPT_INVALID")
            assert view is not None and view.evidence is not None
            expected_ctas[cta_id] = (product, placement, view.evidence.destination_url)
            selected_ctas.add(cta_id)
            commercial_products.add(product)
        for artifact, expected in (
            (cast(dict[str, str], row["local_artifact"]), article.local_sha256),
            (
                cast(dict[str, str], row["production_artifact"]),
                article.production_sha256,
            ),
        ):
            key = artifact["key"]
            raw = artifact_bytes.get(key)
            if (
                type(raw) is not bytes
                or key in used_artifacts
                or artifact["sha256"] != expected
                or manifest_contract.digest(raw) != expected
            ):
                _fail("ARTIFACT_BINDING_INVALID")
            assert raw is not None
            used_artifacts.add(key)
            try:
                markup = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                _fail("MARKUP_ENCODING_INVALID")
                raise AssertionError("unreachable")
            manifest_contract.verify_commerce_markup(
                markup,
                article_id=article_id,
                editorial_product_ids=frozenset(article.editorial_product_ids),
                expected_ctas=expected_ctas,
                expected_images=expected_images,
            )
        article_documents[article.slug] = {
            "article_id": article_id,
            "post_id": article.post_id,
            "baseline_sha256": article.baseline_sha256,
            "local_artifact_sha256": article.local_sha256,
            "production_artifact_sha256": article.production_sha256,
        }
    if source_refs != set(sources.sources) or not source_expiries:
        _fail("SOURCE_SET_INVALID")
    if set(commerce_views) != commercial_products:
        _fail("COMMERCE_SET_INVALID")
    product_expiries: list[datetime] = []
    for product, view in commerce_views.items():
        evidence = view.evidence
        if (
            view.state != "verified"
            or view.product_id != product
            or evidence is None
            or evidence.product_id != product
            or evidence.retrieved_at != view.retrieved_at
        ):
            _fail("COMMERCE_UNVERIFIED")
        captured = _time(view.retrieved_at)
        expires = captured + timedelta(hours=24)
        if not captured <= now < expires:
            _fail("PRODUCT_EXPIRED")
        product_expiries.append(expires)
    shared = cast(dict[str, dict[str, object]], doc["shared_artifacts"])
    if {key: row["sha256"] for key, row in shared.items()} != dict(
        manifest.shared_artifact_sha256
    ) or doc["unchanged_documents"] != dict(manifest.unchanged_sha256):
        _fail("SHARED_OR_UNCHANGED_BINDING_INVALID")
    for row in shared.values():
        key = cast(str, row["key"])
        raw = artifact_bytes.get(key)
        if (
            type(raw) is not bytes
            or key in used_artifacts
            or manifest_contract.digest(raw) != row["sha256"]
        ):
            _fail("ARTIFACT_BINDING_INVALID")
        used_artifacts.add(key)
    if used_artifacts != set(artifact_bytes):
        _fail("ARTIFACT_SET_INVALID")
    expected_content = _hashes(expected_production_content_sha256)
    expected_shared = _hashes(expected_shared_readback_sha256)
    if set(expected_content) != set(article_documents) | (
        set(shared) - {"theme", "seo"}
    ):
        _fail("PRODUCTION_CONTENT_SET_INVALID")
    if set(expected_shared) != set(shared) & {"theme", "seo"}:
        _fail("SHARED_READBACK_SET_INVALID")
    if set(manifest.unchanged_sha256) != set(inventory) - set(expected_content):
        _fail("UNCHANGED_SET_INVALID")
    for slug, expected in manifest.unchanged_sha256.items():
        if inventory[slug].content_sha256 != expected:
            _fail("UNCHANGED_BASELINE_INVALID")
    by_slug = {slug: article for article, (slug, _) in article_targets.items()}
    scope = audit_scope.to_document()
    if (
        set(audit_scope.selected_article_ids) != set(selected)
        or set(audit_scope.existing_article_ids) != set(article_targets)
        or set(audit_scope.rendered_article_ids)
        != {
            by_slug[slug]
            for slug in cast(list[str], doc["rendered_document_slugs"])
            if slug in by_slug
        }
        or audit_scope.shared_changes != bool(shared)
        or set(audit_scope.required_noncontent_rollback_targets)
        != set(shared) & {"theme", "seo", "plugins"}
        or {
            key: set(values) for key, values in audit_scope.claim_ids_by_article.items()
        }
        != {key: set(values) for key, values in claims_by_article.items()}
        or set(audit_scope.retained_product_ids)
        != {
            product
            for article in selected.values()
            for product in article.editorial_product_ids
        }
        or set(audit_scope.affiliate_cta_ids) != selected_ctas
        or set(audit_scope.product_image_ids) != selected_images
    ):
        _fail("AUDIT_SCOPE_INVALID")
    if any(type(raw) is not bytes for raw in audit_artifact_bytes.values()):
        _fail("AUDIT_ARTIFACT_INVALID")
    for value in (
        audit_binding.report_sha256,
        audit_binding.scope_sha256,
        audit_binding.artifact_bundle_sha256,
        audit_binding.evidence_bundle_sha256,
    ):
        _hash(value)
    if audit_binding.contact_state not in {"OWNER_CONFIRMED", "TESTED"}:
        _fail("AUDIT_CONTACT_INVALID")
    audit_hashes = {
        key: manifest_contract.digest(raw) for key, raw in audit_artifact_bytes.items()
    }
    if (
        any(audit_artifact_bytes.get(key) != raw for key, raw in artifact_bytes.items())
        or audit_binding.manifest_sha256 != manifest.manifest_sha256
        or audit_binding.scope_sha256 != _digest(scope)
        or audit_binding.artifact_bundle_sha256 != _digest(audit_hashes)
        or not _time(audit_binding.evaluated_at)
        <= now
        < _time(audit_binding.expires_at)
        <= _time(audit_binding.evaluated_at) + timedelta(hours=24)
    ):
        _fail("AUDIT_BINDING_INVALID_OR_EXPIRED")
    activation = activation_evaluated_at or now.replace(microsecond=0)
    if (
        activation.tzinfo is None
        or activation.utcoffset() is None
        or activation.microsecond != 0
        or not max(manifest.evaluated_at, _time(audit_binding.evaluated_at))
        <= activation
        <= now
    ):
        _fail("ACTIVATION_TIME_INVALID")
    expires = min(
        activation + timedelta(seconds=900),
        manifest.expires_at,
        _time(audit_binding.expires_at),
        *source_expiries,
        *product_expiries,
    )
    if now >= expires:
        _fail("ACTIVATION_EXPIRED")
    envelope = {
        "schema": SCHEMA,
        "publication_profile": PROFILE,
        "link_mode": LINK_MODE,
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "owner_approval_required": True,
        "manifest_sha256": manifest.manifest_sha256,
        "scope_sha256": _digest(scope),
        "artifact_hashes": {
            key: manifest_contract.digest(raw) for key, raw in artifact_bytes.items()
        },
        "audit_binding_sha256": _digest(audit_binding.to_document()),
        "audit_artifact_hashes": audit_hashes,
        "source_receipts": sources.source_receipt_sha256,
        "source_contract_sha256": _hashes(sources.contract_file_sha256),
        "source_article_id_by_article_id": dict(source_article_id_by_article_id),
        "commerce_state": "VERIFIED_PRESENT" if commercial_products else "NOT_INCLUDED",
        "monetization_state": "VERIFIED_PRESENT" if selected_ctas else "NOT_INCLUDED",
        "product_receipts": {
            product: commerce_receipt_sha256(view)
            for product, view in commerce_views.items()
        },
        "selected_articles": article_documents,
        "unchanged_documents": dict(manifest.unchanged_sha256),
        "inventory": {slug: asdict(entry) for slug, entry in inventory.items()},
        "shared_artifact_sha256": dict(manifest.shared_artifact_sha256),
        "expected_production_content_sha256": expected_content,
        "expected_shared_readback_sha256": expected_shared,
        "evaluated_at": _stamp(activation),
        "expires_at": _stamp(expires),
    }
    return VerifiedIncrementalReleaseV1(canonical_json_bytes(envelope))


def validate_release_envelope(
    document: Mapping[str, object],
    *,
    current_context: VerifiedIncrementalReleaseV1,
    publication_profile: str,
    link_mode: str,
    stage: str,
    now: datetime,
) -> str:
    """One byte-equivalent binding across stages; readback remains read-only."""
    if publication_profile != PROFILE or link_mode != LINK_MODE or stage not in STAGES:
        _fail("PROFILE_MODE_OR_STAGE_INVALID")
    if (
        document.get("schema") != SCHEMA
        or document.get("publication_profile") != PROFILE
        or document.get("link_mode") != LINK_MODE
        or document.get("measurement_collection_enabled") is not False
        or document.get("publication_authority") is not False
        or document.get("owner_approval_required") is not True
    ):
        _fail("PROFILE_MODE_OR_STAGE_INVALID")
    if canonical_json_bytes(dict(document)) != current_context.to_bytes():
        _fail("ENVELOPE_CHANGED")
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("TIME_INVALID")
    evaluated, expires = _time(document["evaluated_at"]), current_context.expires_at
    if not evaluated < expires <= evaluated + timedelta(seconds=900):
        _fail("ACTIVATION_WINDOW_INVALID")
    if now < evaluated or (stage != "readback" and now >= expires):
        _fail("EXPIRED_OR_FUTURE")
    return "EXPIRED_READ_ONLY" if now >= expires else "FRESH"


def verify_release_readback(
    context: VerifiedIncrementalReleaseV1,
    *,
    current_inventory: Mapping[str, manifest_contract.ExistingDocument],
    shared_readback_sha256: Mapping[str, str],
    now: datetime,
) -> dict[str, object]:
    """Only hash/identity parity, not proof that the live UI or SEO audit passed."""
    doc = context.to_document()
    freshness = validate_release_envelope(
        doc,
        current_context=context,
        publication_profile=PROFILE,
        link_mode=LINK_MODE,
        stage="readback",
        now=now,
    )
    before = cast(dict[str, dict[str, object]], doc["inventory"])
    if set(before) != set(current_inventory):
        _fail("UNEXPECTED_DOCUMENT_CREATED_OR_REMOVED")
    expected = {
        **cast(dict[str, str], doc["unchanged_documents"]),
        **cast(dict[str, str], doc["expected_production_content_sha256"]),
    }
    for slug, previous in before.items():
        current = asdict(current_inventory[slug])
        if any(
            current[key] != previous[key]
            for key in ("post_id", "slug", "post_type", "status")
        ):
            _fail("READBACK_IDENTITY_CHANGED")
        if current["content_sha256"] != expected[slug]:
            _fail("READBACK_CONTENT_MISMATCH")
    if _hashes(shared_readback_sha256) != doc["expected_shared_readback_sha256"]:
        _fail("READBACK_SHARED_MISMATCH")
    return {
        "schema": READBACK_SCHEMA,
        "publication_profile": PROFILE,
        "link_mode": LINK_MODE,
        "release_sha256": context.sha256,
        "status": "CONTENT_AND_IDENTITY_HASHES_MATCH",
        "evidence_freshness": freshness,
        "observed_at": _stamp(now),
        "publication_authority": False,
        "publication_completed": False,
        "rendered_ui_and_seo_readback_required": True,
    }
