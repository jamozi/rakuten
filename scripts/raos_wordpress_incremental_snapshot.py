#!/usr/bin/env python3
"""Read-only MCP backup for mixed old/new local preview; no publication port."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import raos_wordpress_publication_request as publication  # noqa: E402
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    read_private_bytes,
    write_private_bytes,
)


class PublicMetadataUnavailable(ValueError):
    """A public metadata read failed without exposing response bodies or headers."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class PublicMetadataReader:
    """Unauthenticated, fixed-origin GETs for fields absent from the bounded MCP."""

    def __init__(self) -> None:
        self.opener = build_opener(_NoRedirect())

    def get(self, resource: str, resource_id: int) -> dict[str, object]:
        if resource not in {"posts", "pages", "categories", "tags"} or (
            type(resource_id) is not int or resource_id <= 0
        ):
            raise PublicMetadataUnavailable("PUBLIC_METADATA_TARGET_INVALID")
        fields = (
            "id,slug,name,parent"
            if resource in {"categories", "tags"}
            else "id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags"
        )
        url = f"{publication.ORIGIN}/wp-json/wp/v2/{resource}/{resource_id}?_fields={fields}"
        try:
            request = Request(url, headers={"Accept": "application/json"}, method="GET")
            with self.opener.open(request, timeout=20) as response:
                if (
                    response.status != 200
                    or response.url != url
                    or (response.headers.get_content_type() != "application/json")
                ):
                    raise PublicMetadataUnavailable("PUBLIC_METADATA_RESPONSE_INVALID")
                raw = response.read(65537)
            if not raw or len(raw) > 65536:
                raise PublicMetadataUnavailable("PUBLIC_METADATA_RESPONSE_INVALID")
            document = json.loads(raw)
            if type(document) is not dict or document.get("id") != resource_id:
                raise PublicMetadataUnavailable("PUBLIC_METADATA_RESPONSE_INVALID")
            return {
                "document": document,
                "url": url,
                "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                "response_utf8": raw.decode("utf-8", errors="strict"),
            }
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise PublicMetadataUnavailable("PUBLIC_METADATA_UNAVAILABLE") from error


def capture_public_metadata(
    reader: Any | None, documents: list[dict[str, object]]
) -> dict[str, object]:
    """Cross-check public fields against MCP; missing data remains unverified."""
    result: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_PUBLIC_METADATA_SNAPSHOT_V1",
        "source": "FIXED_ORIGIN_PUBLIC_REST_AFTER_MCP_CAPABILITY_CHECK",
        "status": "UNVERIFIED",
        "documents": {},
        "terms": {"category": {}, "post_tag": {}},
        "unverified": {},
        "not_observed": [
            "front_page_setting",
            "author_identity",
            "featured_media_metadata",
        ],
    }
    observed = cast(dict[str, object], result["documents"])
    unresolved = cast(dict[str, list[str]], result["unverified"])
    terms = cast(dict[str, dict[str, object]], result["terms"])
    for document in documents:
        slug = cast(str, document["slug"])
        if reader is None:
            unresolved[slug] = ["MCP_DOES_NOT_EXPOSE_PUBLISH_DATE_OR_TERM_NAMES"]
            continue
        try:
            resource = "posts" if document["post_type"] == "post" else "pages"
            evidence = reader.get(resource, document["id"])
            raw = evidence["document"]
            if any(
                raw.get(key) != document[key] for key in ("id", "slug", "status")
            ) or (
                raw.get("type") != document["post_type"]
                or str(raw.get("modified_gmt")) + "Z" != document.get("modified_gmt")
            ):
                raise PublicMetadataUnavailable("PUBLIC_METADATA_MCP_MISMATCH")
            taxonomies = document["taxonomies"] or {}
            if not isinstance(taxonomies, dict) or any(
                value
                for key, value in taxonomies.items()
                if key not in {"category", "post_tag"}
            ):
                raise PublicMetadataUnavailable("PUBLIC_METADATA_TAXONOMY_UNAVAILABLE")
            for taxonomy, rest_key, term_resource in (
                ("category", "categories", "categories"),
                ("post_tag", "tags", "tags"),
            ):
                ids = taxonomies.get(taxonomy, [])
                if sorted(raw.get(rest_key, [])) != sorted(ids):
                    raise PublicMetadataUnavailable("PUBLIC_METADATA_MCP_MISMATCH")
                pending = list(ids)
                visited = set()
                while pending:
                    term_id = pending.pop()
                    if term_id in visited:
                        continue
                    if type(term_id) is not int or term_id <= 0 or len(visited) >= 64:
                        raise PublicMetadataUnavailable("PUBLIC_METADATA_TERM_INVALID")
                    visited.add(term_id)
                    key = str(term_id)
                    if key not in terms[taxonomy]:
                        term = reader.get(term_resource, term_id)
                        again = reader.get(term_resource, term_id)
                        if term["document"] != again["document"]:
                            raise PublicMetadataUnavailable(
                                "PUBLIC_METADATA_CHANGED_DURING_READ"
                            )
                        terms[taxonomy][key] = term
                    term_row = cast(dict[str, Any], terms[taxonomy][key])["document"]
                    if term_row.get("parent", 0):
                        pending.append(term_row["parent"])
            for key in ("date", "date_gmt", "modified", "modified_gmt"):
                if not isinstance(raw.get(key), str) or not re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", raw[key]
                ):
                    raise PublicMetadataUnavailable("PUBLIC_METADATA_DATE_INVALID")
                datetime.fromisoformat(raw[key])
            repeated = reader.get(resource, document["id"])
            if repeated["document"] != raw:
                raise PublicMetadataUnavailable("PUBLIC_METADATA_CHANGED_DURING_READ")
            observed[slug] = {
                "mcp_content_sha256": document["content_sha256"],
                "mcp_revision_id": document.get("revision_id"),
                "mcp_modified_gmt": document["modified_gmt"],
                "evidence": evidence,
            }
        except (PublicMetadataUnavailable, ValueError, TypeError, KeyError) as error:
            reason = (
                str(error)
                if isinstance(error, PublicMetadataUnavailable)
                else "PUBLIC_METADATA_INVALID"
            )
            unresolved[slug] = [reason]
    if not unresolved and len(observed) == len(documents):
        result["status"] = "VERIFIED"
    return result


def capture_snapshot(
    client: Any,
    *,
    expected_slugs: frozenset[str],
    public_metadata_reader: Any | None = None,
    deployment_status_reader: Callable[[], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Authenticate with MCP, compare list/get, then make a second inventory read."""
    client.initialize()
    status = client.call("raos-codex-site-status", {})
    deployment = capture_deployment_baseline(deployment_status_reader)
    listed = publication.list_all_documents(client, post_types=("post", "page"))
    chosen = [row for row in listed if row.get("slug") in expected_slugs]
    if {row.get("slug") for row in chosen} != expected_slugs or len(chosen) != len(
        expected_slugs
    ):
        publication.fail("RAOS_INCREMENTAL_SNAPSHOT_EXISTING_TARGET_MISSING")
    captured = []
    for row in sorted(chosen, key=lambda item: str(item["slug"])):
        if row.get("status") != "publish":
            publication.fail("RAOS_INCREMENTAL_SNAPSHOT_NOT_PUBLISHED")
        document = client.call("raos-codex-content-get", {"id": row["id"]})
        if document != row:
            publication.fail("RAOS_INCREMENTAL_SNAPSHOT_CHANGED_DURING_READ")
        if publication._content_after_sha256(document, document["id"]) != document.get(
            "content_sha256"
        ):
            publication.fail("RAOS_INCREMENTAL_SNAPSHOT_HASH_INVALID")
        captured.append(document)
    public_metadata = capture_public_metadata(public_metadata_reader, captured)
    after = publication.list_all_documents(client, post_types=("post", "page"))
    before_map = {row["id"]: publication._baseline_record(row) for row in listed}
    after_map = {row["id"]: publication._baseline_record(row) for row in after}
    if before_map != after_map:
        publication.fail("RAOS_INCREMENTAL_SNAPSHOT_CHANGED_DURING_READ")
    if deployment_status_reader is not None:
        repeated_deployment = capture_deployment_baseline(deployment_status_reader)
        if deployment["theme"] != repeated_deployment["theme"]:
            publication.fail("RAOS_INCREMENTAL_SNAPSHOT_THEME_CHANGED_DURING_READ")
    return {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "publication_profile": "verified-incremental",
        "origin": publication.ORIGIN,
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "BOUNDED_WORDPRESS_EDITOR_MCP",
        "publication_authority": False,
        "site_status": status,
        "deployment_status": deployment,
        "documents": captured,
        "public_metadata": public_metadata,
        "all_document_baselines": {
            str(key): value for key, value in before_map.items()
        },
    }


def capture_deployment_baseline(
    reader: Callable[[], dict[str, object]] | None,
) -> dict[str, object]:
    if reader is None:
        return {"status": "NOT_CAPTURED", "theme": None}
    observed = reader()
    theme = observed.get("theme")
    if (
        observed.get("schema") != "RAOSWordPressDeploymentStatusV1"
        or observed.get("origin") != publication.ORIGIN
        or not isinstance(theme, dict)
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or not re.fullmatch(r"[a-f0-9]{64}", str(theme.get("tree_sha256", "")))
    ):
        publication.fail("RAOS_INCREMENTAL_SNAPSHOT_DEPLOYMENT_STATUS_INVALID")
    return {
        "schema": "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1",
        "source": "BOUNDED_WORDPRESS_DEPLOYMENT_MCP",
        "status": "CAPTURED_READ_ONLY",
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "theme": {
            "slug": theme["slug"],
            "active": True,
            "tree_sha256": theme["tree_sha256"],
        },
    }


def expected_core_slugs() -> frozenset[str]:
    mapping = publication.load_json(
        publication.MAPPING_PATH, 256 * 1024, "RAOS_INCREMENTAL_MAPPING_INVALID"
    )
    return frozenset(
        {
            "home",
            *(
                row["production_slug"]
                for row in cast(list[dict[str, str]], mapping["articles"])
            ),
            *(
                row["production_slug"]
                for row in cast(list[dict[str, str]], mapping["pages"])
            ),
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--owner-checkout", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        # Fixed-path credential validation occurs before constructing any output.
        client = publication.EditorMcpClient(owner_checkout=arguments.owner_checkout)
        document = capture_snapshot(
            client,
            expected_slugs=expected_core_slugs(),
            public_metadata_reader=PublicMetadataReader(),
            deployment_status_reader=lambda: publication._deployment_mcp_call(
                "deployment-status",
                {},
                timeout=60,
                owner_checkout=arguments.owner_checkout,
            ),
        )
        raw = publication.canonical_json_bytes(document)
        digest = hashlib.sha256(raw).hexdigest()
        directory = (
            arguments.owner_checkout / ".secrets/wordpress-mcp/incremental-snapshots"
        )
        name = f"live-{digest}.v1.json"
        write_private_bytes(directory, name, raw)
        if read_private_bytes(directory, name) != raw:
            publication.fail("RAOS_INCREMENTAL_SNAPSHOT_STORAGE_MISMATCH")
        # Never display authenticated document bodies or provider link values.
        print(f"MCP snapshot: {len(expected_core_slugs())} existing core documents")
        print(f"SHA-256: {digest}")
        print(f"Private backup: {directory / name}")
        metadata = cast(dict[str, object], document["public_metadata"])
        print(f"Public date/taxonomy metadata: {metadata['status']}")
        print("Front-page setting, author and featured-media metadata: NOT_VERIFIED")
        print("Production writes: NOT_EXECUTED; restoration test: NOT_EXECUTED")
        return 0
    except publication.PublicationFailure as error:
        sys.stderr.write(f"{error}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
