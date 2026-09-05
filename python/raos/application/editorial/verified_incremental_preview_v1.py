"""Pure mixed-preview projection, never a source of publication verification."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
import re
from typing import TypedDict, cast
from urllib.parse import urlsplit

from raos.application.editorial.verified_incremental_v1 import (
    canonical,
    digest,
    fail,
    omit_unverified_commerce,
    parse_markup_elements,
)


@dataclass(frozen=True)
class MixedPreview:
    posts: bytes
    articles: Mapping[str, bytes]
    binding: Mapping[str, object]
    pages: bytes | None = None
    page_bodies: Mapping[str, bytes] | None = None
    baseline_pages: Mapping[str, bytes] | None = None
    seed_metadata: bytes | None = None


@dataclass(frozen=True)
class LocalRestoration:
    """Owner-private restoration inputs; never an incremental audit result."""

    seed: bytes
    bodies: Mapping[str, bytes]
    preparation: Mapping[str, object]


class _SeedTerm(TypedDict):
    id: int
    name: str
    slug: str
    parent: int


class _SeedDocument(TypedDict):
    production_id: object
    production_slug: str
    dates: dict[str, str]
    taxonomies: dict[str, list[_SeedTerm]]
    source_content_sha256: object


class _PreviewCTA(TypedDict):
    cta_id: str | None
    product_id: str | None
    placement: str | None


class _EditorialText(HTMLParser):
    """HTML textContent equivalent, without treating a markup regex as a parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def derive_editorial_browser_expectations(markup: str) -> dict[str, object]:
    """Derive exact editorial fields from bound body bytes, never from new copy.

    A missing field in an unchanged post is recorded as absent, not silently
    replaced with the latest candidate's classification or disclosure link.
    Visibility, required advertising language and link safety remain browser
    checks; this projection cannot declare those checks successful.
    """
    elements = parse_markup_elements(markup)
    parents: list[int | None] = []
    for index, element in enumerate(elements):
        parents.append(
            next(
                (
                    candidate
                    for candidate in range(index - 1, -1, -1)
                    if elements[candidate].opening_end <= element.start
                    and elements[candidate].end >= element.end
                ),
                None,
            )
        )

    def text(index: int) -> str:
        element = elements[index]
        content = _EditorialText()
        content.feed(markup[element.opening_end : element.end])
        content.close()
        return "".join(content.parts).strip()

    facts: dict[str, list[str]] = {
        "content_role_labels": [],
        "primary_query_intents": [],
    }
    labels = {
        "記事分類": "content_role_labels",
        "この記事で答えること": "primary_query_intents",
    }
    for index, element in enumerate(elements):
        if element.tag != "dt" or text(index) not in labels:
            continue
        following = next(
            (
                candidate
                for candidate in range(index + 1, len(elements))
                if parents[candidate] == parents[index]
            ),
            None,
        )
        if following is not None and elements[following].tag == "dd":
            facts[labels[text(index)]].append(text(following))
    disclosure = next(
        (
            element
            for element in elements
            if "raos-disclosure" in (element.attrs.get("class") or "").split()
        ),
        None,
    )
    policy_links = 0
    if disclosure is not None:
        for element in elements:
            if (
                element.tag != "a"
                or not disclosure.opening_end <= element.start < disclosure.end
            ):
                continue
            target = urlsplit(element.attrs.get("href") or "")
            if (
                target.path == "/comparison-policy/"
                and not target.query
                and not target.fragment
                and (
                    not target.scheme
                    and not target.netloc
                    or target.scheme == "https"
                    and target.netloc == "kurashinoshirube.com"
                )
            ):
                policy_links += 1
    return {
        "expected_article_facts": facts,
        "expected_disclosure_policy_link_count": policy_links,
    }


def _record(value: object, reason: str) -> dict[str, object]:
    if not isinstance(value, dict):
        fail(reason)
    entries = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in entries):
        fail(reason)
    return cast(dict[str, object], entries)


def _positive_ids(value: object, reason: str) -> list[int]:
    if not isinstance(value, list):
        fail(reason)
    entries = cast(list[object], value)
    if any(type(entry) is not int or entry <= 0 for entry in entries):
        fail(reason)
    return cast(list[int], entries)


def _metadata_evidence_valid(evidence: dict[str, object]) -> bool:
    raw = evidence.get("response_utf8")
    if not isinstance(raw, str) or not 1 <= len(raw.encode()) <= 65536:
        return False
    try:
        return digest(raw.encode()) == evidence.get("snapshot_sha256") and json.loads(
            raw
        ) == evidence.get("document")
    except ValueError, TypeError:
        return False


def _public_metadata(
    snapshot: Mapping[str, object], documents: Mapping[str, dict[str, object]]
) -> tuple[dict[str, _SeedDocument], list[str]]:
    """Replay only cross-checked fields; absence is not a synthetic baseline."""
    metadata_value = snapshot.get("public_metadata")
    if not isinstance(metadata_value, dict):
        return {}, ["PUBLIC_DATE_AND_TAXONOMY_METADATA_UNVERIFIED"]
    metadata = _record(cast(object, metadata_value), "PREVIEW_METADATA_INVALID")
    if metadata.get("schema") != "RAOS_WORDPRESS_PUBLIC_METADATA_SNAPSHOT_V1":
        return {}, ["PUBLIC_DATE_AND_TAXONOMY_METADATA_UNVERIFIED"]
    if metadata.get("source") != "FIXED_ORIGIN_PUBLIC_REST_AFTER_MCP_CAPABILITY_CHECK":
        fail("PREVIEW_METADATA_INVALID")
    captured = _record(metadata.get("documents"), "PREVIEW_METADATA_INVALID")
    terms = _record(metadata.get("terms"), "PREVIEW_METADATA_INVALID")
    verified: dict[str, _SeedDocument] = {}
    for slug, live in documents.items():
        entry_value = captured.get(slug)
        if entry_value is None:
            continue
        entry = _record(entry_value, "PREVIEW_METADATA_MCP_MISMATCH")
        if any(
            entry.get(target) != live.get(source)
            for target, source in (
                ("mcp_content_sha256", "content_sha256"),
                ("mcp_revision_id", "revision_id"),
                ("mcp_modified_gmt", "modified_gmt"),
            )
        ):
            fail("PREVIEW_METADATA_MCP_MISMATCH")
        evidence = _record(entry.get("evidence"), "PREVIEW_METADATA_INVALID")
        if not isinstance(
            evidence.get("document"), dict
        ) or not _metadata_evidence_valid(evidence):
            fail("PREVIEW_METADATA_INVALID")
        raw = _record(evidence["document"], "PREVIEW_METADATA_INVALID")
        resource = "posts" if live["post_type"] == "post" else "pages"
        expected_url = f"https://kurashinoshirube.com/wp-json/wp/v2/{resource}/{live['id']}?_fields=id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags"
        if (
            evidence.get("url") != expected_url
            or not re.fullmatch(
                r"[a-f0-9]{64}", str(evidence.get("snapshot_sha256", ""))
            )
            or any(raw.get(key) != live[key] for key in ("id", "slug", "status"))
            or raw.get("type") != live["post_type"]
            or str(raw.get("modified_gmt")) + "Z" != live.get("modified_gmt")
        ):
            fail("PREVIEW_METADATA_MCP_MISMATCH")
        dates: dict[str, str] = {}
        for key in ("date", "date_gmt", "modified", "modified_gmt"):
            value = raw.get(key)
            if not isinstance(value, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", value
            ):
                fail("PREVIEW_METADATA_DATE_INVALID")
            try:
                datetime.fromisoformat(value)
            except ValueError:
                fail("PREVIEW_METADATA_DATE_INVALID")
            dates[key] = value.replace("T", " ")
        # The existing local runtime has an explicit Asia/Tokyo timezone.
        if any(
            (
                datetime.fromisoformat(dates[local])
                - datetime.fromisoformat(dates[utc])
            ).total_seconds()
            != 32400
            for local, utc in (("date", "date_gmt"), ("modified", "modified_gmt"))
        ):
            fail("PREVIEW_METADATA_TIMEZONE_NOT_REPRODUCIBLE")
        taxonomy_ids = _record(
            live.get("taxonomies") or {}, "PREVIEW_METADATA_TAXONOMY_UNAVAILABLE"
        )
        if any(
            value
            for key, value in taxonomy_ids.items()
            if key not in {"category", "post_tag"}
        ):
            fail("PREVIEW_METADATA_TAXONOMY_UNAVAILABLE")
        projected_terms: dict[str, list[_SeedTerm]] = {}
        for taxonomy, rest_key in (("category", "categories"), ("post_tag", "tags")):
            ids = _positive_ids(
                taxonomy_ids.get(taxonomy, []), "PREVIEW_METADATA_MCP_MISMATCH"
            )
            rest_ids = _positive_ids(
                raw.get(rest_key, []), "PREVIEW_METADATA_MCP_MISMATCH"
            )
            if sorted(rest_ids) != sorted(ids):
                fail("PREVIEW_METADATA_MCP_MISMATCH")
            term_evidence = _record(
                terms.get(taxonomy), "PREVIEW_METADATA_TAXONOMY_UNAVAILABLE"
            )
            rows: list[_SeedTerm] = []
            for term_id in ids:
                record = _record(
                    term_evidence.get(str(term_id)),
                    "PREVIEW_METADATA_TAXONOMY_UNAVAILABLE",
                )
                if not isinstance(
                    record.get("document"), dict
                ) or not _metadata_evidence_valid(record):
                    fail("PREVIEW_METADATA_TAXONOMY_UNAVAILABLE")
                term = _record(
                    record["document"], "PREVIEW_METADATA_TAXONOMY_UNAVAILABLE"
                )
                term_resource = "categories" if taxonomy == "category" else "tags"
                name = term.get("name")
                term_slug = term.get("slug")
                if (
                    record.get("url")
                    != f"https://kurashinoshirube.com/wp-json/wp/v2/{term_resource}/{term_id}?_fields=id,slug,name,parent"
                    or term.get("id") != term_id
                    or not re.fullmatch(
                        r"[a-f0-9]{64}", str(record.get("snapshot_sha256", ""))
                    )
                    or not isinstance(name, str)
                    or not name
                    or re.search(r"[<>\x00-\x1f]", name)
                    or not isinstance(term_slug, str)
                    or not re.fullmatch(r"(?:[a-z0-9_-]|%[0-9a-f]{2})+", term_slug)
                ):
                    fail("PREVIEW_METADATA_TERM_INVALID")
                if term.get("parent", 0) != 0:
                    fail("PREVIEW_METADATA_TERM_HIERARCHY_NOT_REPRODUCIBLE")
                rows.append(
                    {
                        "id": term_id,
                        "name": name,
                        "slug": term_slug,
                        "parent": 0,
                    }
                )
            projected_terms[taxonomy] = rows
        verified[slug] = {
            "production_id": live["id"],
            "production_slug": slug,
            "dates": dates,
            "taxonomies": projected_terms,
            "source_content_sha256": live["content_sha256"],
        }
    missing = sorted(set(documents) - set(verified))
    blockers = [f"PUBLIC_METADATA_UNVERIFIED:{slug}" for slug in missing]
    if metadata.get("status") != "VERIFIED" or metadata.get("unverified"):
        blockers.append("PUBLIC_METADATA_CAPTURE_NOT_VERIFIED")
    return verified, blockers


def _snapshot_documents(snapshot: Mapping[str, object]) -> dict[str, dict[str, object]]:
    if (
        snapshot.get("schema") != "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        or snapshot.get("publication_profile") != "verified-incremental"
        or snapshot.get("source") != "BOUNDED_WORDPRESS_EDITOR_MCP"
        or snapshot.get("origin") != "https://kurashinoshirube.com"
        or snapshot.get("publication_authority") is not False
    ):
        fail("SNAPSHOT_INVALID")
    if type(snapshot.get("documents")) is not list:
        fail("SNAPSHOT_INVALID")
    documents: dict[str, dict[str, object]] = {}
    for raw_value in cast(list[object], snapshot["documents"]):
        if type(raw_value) is not dict:
            fail("SNAPSHOT_INVALID")
        raw = _record(cast(object, raw_value), "SNAPSHOT_INVALID")
        slug = raw.get("slug")
        if type(slug) is not str:
            fail("SNAPSHOT_INVALID")
        if slug in documents or raw.get("status") != "publish":
            fail("SNAPSHOT_INVALID")
        # WordPress ContentDocumentV1 hashes its public projection, not revision
        # timestamps. Verify before any old text enters the local overlay.
        fields = {
            "schema",
            "post_type",
            "id",
            "status",
            "title",
            "slug",
            "excerpt",
            "block_markup",
            "taxonomies",
            "media_ids",
        }
        if not fields <= set(raw):
            fail("SNAPSHOT_INVALID")
        projection = {key: raw[key] for key in fields}
        wp_hash = digest(
            json.dumps(
                projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        if wp_hash != raw.get("content_sha256"):
            fail("SNAPSHOT_HASH_INVALID")
        documents[slug] = raw
    return documents


def build_local_restoration(
    snapshot: Mapping[str, object], *, article_slugs: frozenset[str]
) -> LocalRestoration:
    """Prepare exact captured stored values for fourteen existing local rows."""
    policies = {"home", "about-ad-policy", "comparison-policy", "privacy-policy"}
    if (
        len(article_slugs) != 10
        or any(
            re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) is None
            for slug in article_slugs
        )
        or article_slugs & policies
    ):
        fail("RESTORE_TARGET_INVALID")
    documents = _snapshot_documents(snapshot)
    if set(documents) != set(article_slugs) | policies:
        fail("RESTORE_TARGET_INVALID")
    metadata, blockers = _public_metadata(snapshot, documents)
    if blockers or set(metadata) != set(documents):
        fail("RESTORE_METADATA_UNVERIFIED")
    projected: dict[str, dict[str, object]] = {}
    bodies: dict[str, bytes] = {}
    seen_ids: set[int] = set()
    for slug, document in sorted(documents.items()):
        post_id = document.get("id")
        post_type = "post" if slug in article_slugs else "page"
        if (
            document.get("schema") != "ContentDocumentV1"
            or document.get("post_type") != post_type
            or type(post_id) is not int
            or post_id <= 0
            or post_id in seen_ids
            or any(
                type(document.get(key)) is not str
                for key in ("title", "excerpt", "block_markup")
            )
        ):
            fail("RESTORE_DOCUMENT_INVALID")
        seen_ids.add(post_id)
        body = cast(str, document["block_markup"]).encode("utf-8")
        if len(body) > 1024 * 1024:
            fail("RESTORE_DOCUMENT_INVALID")
        content_file = f"content/{slug}.html" if body else None
        if body:
            bodies[slug] = body
        observed = metadata[slug]
        projected[slug] = {
            "production_id": post_id,
            "production_slug": slug,
            "local_slug": f"local-preview-{slug}" if post_type == "post" else slug,
            "post_type": post_type,
            "status": "publish",
            "title": document["title"],
            "excerpt": document["excerpt"],
            "content_file": content_file,
            "content_sha256": digest(body),
            "source_content_sha256": document["content_sha256"],
            "dates": observed["dates"],
            "taxonomies": observed["taxonomies"],
        }
    snapshot_hash = digest(canonical(snapshot).rstrip(b"\n"))
    seed = canonical(
        {
            "schema": "RAOS_WORDPRESS_LOCAL_RESTORE_SEED_V1",
            "publication_profile": "local-restore-rehearsal",
            "publication_authority": False,
            "source_snapshot_sha256": snapshot_hash,
            "documents": projected,
        }
    )
    preparation: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_LOCAL_RESTORE_PREPARATION_V1",
        "publication_profile": "local-restore-rehearsal",
        "publication_authority": False,
        "status": "PREPARED_NOT_RESTORED",
        "snapshot_name": f"live-{snapshot_hash}.v1.json",
        "source_snapshot_sha256": snapshot_hash,
        "seed_sha256": digest(seed),
        "document_count": 14,
        "article_count": 10,
        "policy_count": 3,
        "home_count": 1,
        "body_sha256": {slug: row["content_sha256"] for slug, row in projected.items()},
        "source_content_sha256": {
            slug: row["source_content_sha256"] for slug, row in projected.items()
        },
        "requires_existing_local_rows": True,
        "changes_theme_plugins_or_site_options": False,
        "incremental_preview_pass": False,
        "not_restored": [
            "production_post_ids",
            "production_term_ids",
            "revision_history",
            "author_identity",
            "media_metadata",
            "post_meta",
            "theme",
            "plugins",
            "site_options",
        ],
    }
    return LocalRestoration(seed, bodies, preparation)


def verify_local_restoration(
    expected: LocalRestoration, readback: Mapping[str, object]
) -> dict[str, object]:
    """Verify stored-field readback, not visual quality or publication readiness."""
    required = {
        "schema",
        "publication_profile",
        "publication_authority",
        "preparation_sha256",
        "site_url",
        "local_only",
        "new_post_count",
        "documents",
    }
    preparation_hash = digest(canonical(expected.preparation))
    origin = readback.get("site_url")
    if (
        set(readback) != required
        or readback.get("schema") != "RAOS_WORDPRESS_LOCAL_RESTORE_READBACK_V1"
        or readback.get("publication_profile") != "local-restore-rehearsal"
        or readback.get("publication_authority") is not False
        or readback.get("preparation_sha256") != preparation_hash
        or readback.get("local_only") is not True
        or type(readback.get("new_post_count")) is not int
        or readback["new_post_count"] != 0
        or not isinstance(origin, str)
        or re.fullmatch(r"http://127\.0\.0\.1:[0-9]{4,5}", origin) is None
    ):
        fail("RESTORE_READBACK_INVALID")
    if not 1024 <= int(origin.rsplit(":", 1)[1]) <= 65535:
        fail("RESTORE_READBACK_INVALID")
    seed = _record(json.loads(expected.seed), "RESTORE_SEED_INVALID")
    documents = _record(seed.get("documents"), "RESTORE_SEED_INVALID")
    captured = _record(readback.get("documents"), "RESTORE_READBACK_INVALID")
    if set(captured) != set(documents) or len(documents) != 14:
        fail("RESTORE_READBACK_INVALID")
    identities: dict[str, int] = {}
    for slug, value in documents.items():
        document = _record(value, "RESTORE_SEED_INVALID")
        actual = _record(captured[slug], "RESTORE_READBACK_INVALID")
        expected_fields = {
            "local_id",
            "before_local_id",
            "local_slug",
            "post_type",
            "status",
            "title_sha256",
            "excerpt_sha256",
            "body_sha256",
            "dates",
            "taxonomies",
            "source_content_sha256",
        }
        local_id = actual.get("local_id")
        if (
            set(actual) != expected_fields
            or type(local_id) is not int
            or local_id <= 0
            or type(actual.get("before_local_id")) is not int
            or actual["before_local_id"] != local_id
            or local_id in identities.values()
        ):
            fail("RESTORE_IDENTITY_CHANGED")
        identities[slug] = local_id
        terms = _record(document["taxonomies"], "RESTORE_SEED_INVALID")
        semantic_terms: dict[str, list[dict[str, object]]] = {}
        for taxonomy, rows_value in terms.items():
            if not isinstance(rows_value, list):
                fail("RESTORE_SEED_INVALID")
            rows = [
                _record(row, "RESTORE_SEED_INVALID")
                for row in cast(list[object], rows_value)
            ]
            semantic_terms[taxonomy] = sorted(
                ({key: row[key] for key in ("name", "slug", "parent")} for row in rows),
                key=lambda row: str(row["slug"]),
            )
        projection = {
            "local_slug": document["local_slug"],
            "post_type": document["post_type"],
            "status": document["status"],
            "title_sha256": digest(cast(str, document["title"]).encode()),
            "excerpt_sha256": digest(cast(str, document["excerpt"]).encode()),
            "body_sha256": document["content_sha256"],
            "dates": document["dates"],
            "taxonomies": semantic_terms,
            "source_content_sha256": document["source_content_sha256"],
        }
        if any(actual.get(key) != value for key, value in projection.items()):
            fail("RESTORE_STORED_FIELDS_MISMATCH")
    return {
        "schema": "RAOS_WORDPRESS_LOCAL_RESTORE_RECEIPT_V1",
        "publication_profile": "local-restore-rehearsal",
        "publication_authority": False,
        "status": "LOCAL_STORED_FIELDS_RESTORED",
        "preparation_sha256": preparation_hash,
        "source_snapshot_sha256": expected.preparation["source_snapshot_sha256"],
        "readback_sha256": digest(canonical(readback)),
        "local_origin": origin,
        "verified_document_count": 14,
        "new_post_count": 0,
        "local_ids": identities,
        "incremental_preview_pass": False,
        "production_writes": False,
        "not_restored": expected.preparation["not_restored"],
    }


def build_mixed_preview(
    *,
    snapshot: Mapping[str, object],
    source_posts: Mapping[str, object],
    source_articles: Mapping[str, bytes],
    selected_slugs: frozenset[str],
    article_ids_by_slug: Mapping[str, str],
    source_pages: Mapping[str, object] | None = None,
    source_page_bodies: Mapping[str, bytes] | None = None,
    updated_policy_slugs: frozenset[str] = frozenset(),
    home_mode: str = "preserve-live-baseline",
) -> MixedPreview:
    """Use revised selected drafts and byte-exact unchanged MCP article bodies.

    All selected commerce is deliberately omitted in this preparation view.
    Captured old article contents remain intact so incompatible common-theme
    changes fail their real mixed-state visual audit instead of being concealed.
    The seed's existing local URL rewrite happens after this byte-level binding.
    """
    documents = _snapshot_documents(snapshot)
    metadata, metadata_blockers = _public_metadata(snapshot, documents)
    fixture = deepcopy(dict(source_posts))
    if (
        set(fixture) != {"schema", "seed_version", "posts"}
        or fixture["schema"] != "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
        or type(fixture["posts"]) is not list
    ):
        fail("PREVIEW_FIXTURE_INVALID")
    posts: list[dict[str, object]] = []
    slugs: set[str] = set()
    for row_value in cast(list[object], fixture["posts"]):
        if type(row_value) is not dict:
            fail("PREVIEW_FIXTURE_INVALID")
        row = _record(cast(object, row_value), "PREVIEW_FIXTURE_INVALID")
        local_slug = row.get("slug")
        if type(local_slug) is not str:
            fail("PREVIEW_FIXTURE_INVALID")
        slug = local_slug.removeprefix("local-preview-")
        if slug == row["slug"] or slug in slugs or slug not in documents:
            fail("PREVIEW_TARGET_INVALID")
        slugs.add(slug)
        posts.append(row)
    if (
        not selected_slugs
        or not selected_slugs <= slugs
        or set(source_articles) != slugs
        or set(article_ids_by_slug) != slugs
        or len(set(article_ids_by_slug.values())) != len(slugs)
        or slugs
        != {slug for slug, row in documents.items() if row["post_type"] == "post"}
    ):
        fail("PREVIEW_TARGET_INVALID")
    articles: dict[str, bytes] = {}
    states: dict[str, str] = {}
    baselines: dict[str, str] = {}
    for row in posts:
        slug = cast(str, row["slug"]).removeprefix("local-preview-")
        live = documents[slug]
        if (
            row.get("content_file") != f"articles/{slug}.html"
            or live["post_type"] != "post"
        ):
            fail("PREVIEW_TARGET_INVALID")
        if slug in selected_slugs:
            try:
                markup = source_articles[slug].decode("utf-8", errors="strict")
            except UnicodeError:
                fail("PREVIEW_FIXTURE_INVALID")
            articles[slug] = omit_unverified_commerce(
                markup,
                image_product_ids=frozenset(),
                cta_product_ids=frozenset(),
                article_id=article_ids_by_slug[slug],
            ).encode()
            states[slug] = "REVISED_DRAFT_NOT_VERIFIED"
        else:
            if any(
                type(live.get(key)) is not str
                for key in ("block_markup", "title", "excerpt")
            ):
                fail("SNAPSHOT_INVALID")
            articles[slug] = cast(str, live["block_markup"]).encode()
            row["title"], row["excerpt"] = live["title"], live["excerpt"]
            states[slug] = "UNCHANGED_LIVE_CONTENT"
        baselines[slug] = cast(str, live["content_sha256"])
        observed = metadata.get(slug)
        if observed is None:
            row["category"], row["date"] = "UNVERIFIED", "UNVERIFIED"
        else:
            dates = observed["dates"]
            terms = observed["taxonomies"]
            if not terms["category"]:
                fail("PREVIEW_METADATA_CATEGORY_UNAVAILABLE")
            row["category"], row["date"] = terms["category"][0]["name"], dates["date"]
    if home_mode not in {"preserve-live-baseline", "shared-theme-candidate"}:
        fail("PREVIEW_HOME_MODE_INVALID")
    page_raw: bytes | None = None
    page_bodies: dict[str, bytes] = {}
    page_states: dict[str, str] = {}
    baseline_pages = {
        slug: cast(str, live["block_markup"]).encode()
        for slug, live in documents.items()
        if live["post_type"] == "page"
    }
    if source_pages is not None:
        page_fixture = deepcopy(dict(source_pages))
        if (
            set(page_fixture) != {"schema", "seed_version", "pages"}
            or page_fixture["schema"] != "RAOS_WORDPRESS_PRODUCTION_POLICY_PAGES_V1"
            or not isinstance(page_fixture["pages"], list)
            or source_page_bodies is None
        ):
            fail("PREVIEW_POLICY_FIXTURE_INVALID")
        rows: list[dict[str, object]] = []
        policy_slugs: set[str] = set()
        for policy_value in cast(list[object], page_fixture["pages"]):
            policy_row = _record(policy_value, "PREVIEW_POLICY_FIXTURE_INVALID")
            policy_slug = policy_row.get("slug")
            if type(policy_slug) is not str:
                fail("PREVIEW_POLICY_FIXTURE_INVALID")
            policy_slugs.add(policy_slug)
            rows.append(policy_row)
        if (
            len(rows) != 3
            or policy_slugs
            != {"about-ad-policy", "comparison-policy", "privacy-policy"}
            or set(source_page_bodies) != policy_slugs
            or not updated_policy_slugs <= policy_slugs
            or set(baseline_pages) != policy_slugs | {"home"}
        ):
            fail("PREVIEW_POLICY_TARGET_INVALID")
        for row in rows:
            slug = cast(str, row["slug"])
            if row.get("content_file") != f"production-pages/{slug}.html":
                fail("PREVIEW_POLICY_FIXTURE_INVALID")
            row["content_file"] = f"pages/{slug}.html"
            if slug in updated_policy_slugs:
                if any(
                    marker in source_page_bodies[slug].decode()
                    for marker in (
                        "ローカルWordPressプレビュー",
                        "このローカルプレビュー",
                    )
                ):
                    fail("PREVIEW_POLICY_PROFILE_MIXED")
                page_bodies[slug] = source_page_bodies[slug]
                page_states[slug] = "REVISED_PRODUCTION_POLICY_NOT_VERIFIED"
            else:
                row["title"], row["excerpt"] = (
                    documents[slug]["title"],
                    documents[slug]["excerpt"],
                )
                page_bodies[slug] = baseline_pages[slug]
                page_states[slug] = "PRESERVED_LIVE_PRODUCTION_POLICY"
        page_fixture["schema"] = "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
        page_raw = (
            json.dumps(page_fixture, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    elif updated_policy_slugs or source_page_bodies is not None:
        fail("PREVIEW_POLICY_FIXTURE_INVALID")
    seed_metadata = {
        "schema": "RAOS_WORDPRESS_MIXED_PREVIEW_SEED_METADATA_V1",
        "publication_profile": "verified-incremental",
        "publication_authority": False,
        "status": "VERIFIED_FIELDS_ONLY" if not metadata_blockers else "UNVERIFIED",
        "documents": metadata,
        "article_states": states,
        "policy_states": page_states,
        "home_state": "BASELINE_CAPTURED_NOT_RENDERED"
        if home_mode == "preserve-live-baseline"
        else "SHARED_THEME_CANDIDATE_NOT_VERIFIED",
    }
    seed_metadata_raw = canonical(seed_metadata)
    # The existing PHP seed deliberately checks the fixture field order. Keep
    # its owner projection order; the separate preparation binding is canonical.
    posts_raw = (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode()
    scope_rows: list[dict[str, object]] = []
    for slug, article_raw in sorted(articles.items()):
        products: list[str | None] = []
        images: list[str | None] = []
        ctas: list[_PreviewCTA] = []
        for element in parse_markup_elements(article_raw.decode()):
            attrs = element.attrs
            classes = set((attrs.get("class") or "").split())
            if element.tag == "article" and "product-profile" in classes:
                products.append(attrs.get("data-raos-product-id"))
            if element.tag == "img" and (
                "data-raos-product-image-id" in attrs or element.product
            ):
                images.append(
                    attrs.get("data-raos-product-image-id") or element.product
                )
            if element.tag == "a" and (
                "data-raos-placement" in attrs
                or "raos-cta" in classes
                or urlsplit(attrs.get("href") or "").hostname == "hb.afl.rakuten.co.jp"
            ):
                ctas.append(
                    {
                        "cta_id": attrs.get("data-raos-cta-id"),
                        "product_id": attrs.get("data-raos-product-id")
                        or element.product,
                        "placement": attrs.get("data-raos-placement"),
                    }
                )
        if any(type(product) is not str for product in products + images):
            fail("PREVIEW_PRODUCT_ID_INVALID")
        scope_rows.append(
            {
                "article_id": article_ids_by_slug[slug],
                "editorial_product_ids": sorted(cast(list[str], products)),
                "expected_cta_ids": sorted(
                    cta["cta_id"] for cta in ctas if cta["cta_id"] is not None
                ),
                "expected_ctas": ctas,
                "expected_image_product_ids": sorted(cast(list[str], images)),
                **derive_editorial_browser_expectations(article_raw.decode()),
            }
        )
    return MixedPreview(
        posts_raw,
        articles,
        {
            "schema": "RAOS_WORDPRESS_MIXED_PREVIEW_PREPARATION_V1",
            "publication_profile": "verified-incremental",
            "link_mode": "standard-api",
            "publication_authority": False,
            "status": "NOT_VERIFIED_FOR_PUBLICATION",
            "selected_slugs": sorted(selected_slugs),
            "source_snapshot_sha256": digest(canonical(snapshot).rstrip(b"\n")),
            "baseline_document_sha256": baselines,
            "article_states": states,
            "article_body_sha256": {
                slug: digest(raw) for slug, raw in articles.items()
            },
            "posts_sha256": digest(posts_raw),
            "selected_commerce": "OMITTED_NOT_VERIFIED",
            "seed_metadata_sha256": digest(seed_metadata_raw),
            "metadata_status": seed_metadata["status"],
            "metadata_blockers": metadata_blockers,
            "unverified_public_metadata": [
                "front_page_setting",
                "author_identity",
                "featured_media_metadata",
            ],
            "home_mode": home_mode,
            "home_state": seed_metadata["home_state"],
            "policy_states": page_states,
            "pages_sha256": digest(page_raw) if page_raw is not None else None,
            "page_body_sha256": {
                slug: digest(raw) for slug, raw in page_bodies.items()
            },
            "baseline_page_sha256": {
                slug: digest(raw) for slug, raw in baseline_pages.items()
            },
            "incremental_scope": {
                "schema": "RAOS_WORDPRESS_INCREMENTAL_BROWSER_SCOPE_V1",
                "publication_profile": "verified-incremental",
                "link_mode": "standard-api",
                "selected_article_ids": sorted(
                    article_ids_by_slug[slug] for slug in selected_slugs
                ),
                "articles": scope_rows,
            },
        },
        page_raw,
        page_bodies,
        baseline_pages,
        seed_metadata_raw,
    )
