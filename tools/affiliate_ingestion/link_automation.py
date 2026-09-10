"""Owner-local acquisition, exact matching, and article draft updates.

This module never publishes, registers a partnership, or persists raw API data.
The plan is owner-controlled input, not provider content or a publication grant.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from difflib import unified_diff
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from raos.application.editorial.reader_experience_v1 import (
    ARTICLE_TYPES,
    CtaEvidence,
    cta_visible,
)

from .client import EndpointValidator, FetchError, fetch_resource
from .config import ConfigError, provider_diagnostics, resolve_indirections
from .link_markup import LinkError, creative, https_url, insert_slot
from .providers import PROVIDERS

REGISTRY = "changes/wordpress-direct-publish-v1/articles.v1.json"
ARTICLE_ROOT = "changes/wordpress-direct-publish-v1/articles/"
MAX_INPUT_BYTES = 2 * 1024 * 1024
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\Z")
FIELDS = {
    "offer_id",
    "advertiser_id",
    "model",
    "variant",
    "jan",
    "status",
    "landing_url",
    "affiliate_url",
    "html",
}


def fail(code: str):
    raise LinkError(code)


def require_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        fail("PLAN_ID_INVALID")
    return value


def no_symlinks(path: Path):
    if any(part.is_symlink() for part in (path, *path.parents)):
        fail("SYMLINK_NOT_ALLOWED")


def read_json(path: Path, *, private=False):
    no_symlinks(path)
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        fail("INPUT_MISSING_OR_TOO_LARGE")
    if private and os.name != "nt" and path.stat().st_mode & 0o077:
        fail("PLAN_REQUIRES_OWNER_ONLY_PERMISSIONS")
    return json.loads(path.read_text(encoding="utf-8"))


def instant(value):
    if not isinstance(value, str):
        fail("GRANT_TIME_INVALID")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("GRANT_TIME_INVALID")
    if result.tzinfo is None:
        fail("GRANT_TIMEZONE_REQUIRED")
    return result.astimezone(UTC)


def validate_plan(plan: dict, config: dict, now: datetime):
    if (
        not isinstance(plan, dict)
        or plan.get("schema") != "RAOSAffiliateAutomationPlanV1"
        or plan.get("enabled") is not True
    ):
        fail("AUTOMATION_DISABLED_OR_INVALID")
    site = https_url(plan.get("site_url"))
    placements, grants = plan.get("placements"), plan.get("grants")
    if not isinstance(placements, list) or not 1 <= len(placements) <= 100:
        fail("PLACEMENTS_REQUIRED")
    if not isinstance(grants, list) or not 1 <= len(grants) <= 100:
        fail("PARTNERSHIP_GRANTS_REQUIRED")
    checked_grants = {}
    for grant in grants:
        if (
            not isinstance(grant, dict)
            or grant.get("provider") not in PROVIDERS
            or grant.get("approved") is not True
            or grant.get("site_url") != site
            or not isinstance(grant.get("evidence_ref"), str)
            or not grant["evidence_ref"].strip()
            or grant.get("format") not in {"url", "html"}
        ):
            fail("PARTNERSHIP_NOT_VERIFIED")
        key = grant["provider"], require_id(grant.get("advertiser_id"))
        checked, expires = (
            instant(grant.get("checked_at")),
            instant(grant.get("expires_at")),
        )
        if not checked <= now < expires or now - checked > timedelta(days=1):
            fail("PARTNERSHIP_STALE_OR_FUTURE")
        hosts = grant.get("allowed_hosts")
        if not isinstance(hosts, list) or not 1 <= len(hosts) <= 10:
            fail("CREATIVE_HOSTS_REQUIRED")
        for host in hosts:
            if not isinstance(host, str) or not re.fullmatch(
                r"[a-z0-9]+(?:[.-][a-z0-9]+)*", host
            ):
                fail("CREATIVE_HOST_INVALID")
        if key in checked_grants:
            fail("PARTNERSHIP_AMBIGUOUS")
        checked_grants[key] = grant
    slots, articles, sources = set(), set(), {}
    for placement in placements:
        if not isinstance(placement, dict):
            fail("PLACEMENT_INVALID")
        for field in (
            "slot_id",
            "article_key",
            "product_ref",
            "anchor_id",
            "offer_id",
            "resource",
        ):
            require_id(placement.get(field))
        slot = placement["slot_id"]
        if slot in slots:
            fail("SLOT_DUPLICATED")
        slots.add(slot)
        articles.add(placement["article_key"])
        if (
            placement.get("editorial_eligible") is not True
            or placement.get("article_type") not in ARTICLE_TYPES
            or placement["article_type"] == "status_check"
        ):
            fail("ARTICLE_NOT_ELIGIBLE_FOR_OFFERS")
        identity = placement.get("identity")
        if (
            not isinstance(identity, dict)
            or set(identity) - {"model", "variant", "jan"}
            or not {"model", "variant"} <= set(identity)
            or any(
                not isinstance(v, str) or not v.strip() or len(v) > 256
                for v in identity.values()
            )
        ):
            fail("EXACT_PRODUCT_IDENTITY_REQUIRED")
        https_url(placement.get("landing_url"))
        key = placement.get("provider"), placement["resource"]
        if key[0] not in PROVIDERS or key[1] not in {"products", "links", "creatives"}:
            fail("SOURCE_NOT_AN_AD_RESOURCE")
        if provider_diagnostics(config, key[0]):
            fail("PROVIDER_NOT_READY")
        provider = config["providers"][key[0]]
        resource = provider.get("resources", {}).get(key[1])
        if not isinstance(resource, dict) or resource.get("enabled") is not True:
            fail("AD_RESOURCE_DISABLED")
        mode = resource.get("mode", provider.get("mode", "api"))
        fields = resource.get("link_fields", {})
        if (
            not isinstance(fields, dict)
            or set(fields) - FIELDS
            or any(
                not isinstance(v, str)
                or not re.fullmatch(
                    r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", v
                )
                for v in fields.values()
            )
        ):
            fail("LINK_FIELD_MAPPING_INVALID")
        if mode in {"api", "feed"}:
            EndpointValidator.validate_syntax(str(resource.get("endpoint", "")))
            # Resolve auth existence in a dry run without making any requests.
            resolve_indirections(provider.get("auth", {}))
        elif mode == "file":
            export = Path(resource.get("path", "")).expanduser().absolute()
            no_symlinks(export)
            if not export.is_file():
                fail("OFFICIAL_EXPORT_MISSING")
        else:
            fail("SOURCE_MODE_INVALID")
        sources[key] = (mode, fields)
    return checked_grants, articles, sources


def article_sources(root: Path, keys: set[str]):
    registry = read_json(root / REGISTRY)
    if (
        not isinstance(registry, dict)
        or registry.get("schema") != "RAOSOwnerDirectArticlesV1"
        or registry.get("profile") != "owner-direct-v1"
    ):
        fail("OWNER_DIRECT_REGISTRY_REQUIRED")
    selected, paths = {}, set()
    for row in registry["articles"]:
        if row["article_key"] not in keys:
            continue
        name = row.get("body_source", "")
        if (
            not isinstance(name, str)
            or not name.startswith(ARTICLE_ROOT)
            or ".." in Path(name).parts
            or not name.endswith(".html")
        ):
            fail("ARTICLE_SOURCE_OUTSIDE_EDITABLE_ROOT")
        path = root / name
        no_symlinks(path)
        if row["article_key"] in selected or path in paths:
            fail("ARTICLE_SOURCE_AMBIGUOUS")
        if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            fail("ARTICLE_SOURCE_MISSING_OR_TOO_LARGE")
        body = path.read_text(encoding="utf-8")
        if any(
            text in body
            for text in ("この記事の販売リンクは掲載していません", "販売リンクなし")
        ):
            fail("ARTICLE_DISCLOSURE_REQUIRES_EDITORIAL_UPDATE")
        selected[row["article_key"]] = (name, body)
        paths.add(path)
    if set(selected) != keys:
        fail("ARTICLE_NOT_REGISTERED")
    return selected


def mapped(record: dict, fields: dict):
    result = {}
    for name in FIELDS:
        value: Any = record
        for part in fields.get(name, name).split("."):
            value = value.get(part) if isinstance(value, dict) else None
        result[name] = value
    return result


def select_creative(placement, records, grants):
    matches = [r for r in records if r["offer_id"] == placement["offer_id"]]
    if len(matches) != 1:
        fail("OFFER_MISSING_OR_AMBIGUOUS")
    offer = matches[0]
    if (
        offer["status"] != "active"
        or offer["landing_url"] != placement["landing_url"]
        or any(offer[k] != v for k, v in placement["identity"].items())
    ):
        fail("OFFER_INACTIVE_OR_IDENTITY_MISMATCH")
    grant = grants.get((placement["provider"], offer["advertiser_id"]))
    if grant is None:
        fail("OFFER_PARTNERSHIP_UNVERIFIED")
    hosts = set(grant["allowed_hosts"])
    url = https_url(offer["affiliate_url"], hosts)
    evidence = CtaEvidence(
        verified_offers=frozenset({(placement["product_ref"], url)}),
        eligible_products=frozenset({placement["product_ref"]}),
    )
    if not cta_visible(
        "offer",
        url,
        placement["product_ref"],
        evidence,
        article_type=placement["article_type"],
    ):
        fail("ARTICLE_NOT_ELIGIBLE_FOR_OFFERS")
    if grant["format"] == "html":
        return creative(offer["html"], hosts, url)
    if offer["html"]:
        fail("HTML_CREATIVE_CANNOT_BE_REWRITTEN_AS_URL")
    return (
        '<a href="'
        + escape(url, quote=True)
        + '" rel="sponsored nofollow noopener noreferrer">'
        "販売条件を確認する</a>"
    )


def private_directory(path: Path):
    no_symlinks(path)
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name != "nt" and path.stat().st_mode & 0o077:
        fail("OUTPUT_REQUIRES_OWNER_ONLY_PERMISSIONS")


def write_private(path: Path, payload: str):
    no_symlinks(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".affiliate-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_drafts(root: Path, before: dict, after: dict):
    for key, (name, text) in before.items():
        no_symlinks(root / name)
        if (root / name).read_text(encoding="utf-8") != text:
            fail("ARTICLE_CHANGED_DURING_RUN")
    written = []
    try:
        for key, (name, text) in before.items():
            if text == after[key]:
                continue
            path = root / name
            no_symlinks(path)
            if path.read_text(encoding="utf-8") != text:
                fail("ARTICLE_CHANGED_DURING_RUN")
            write_private(path, after[key])
            written.append(key)
    except Exception:
        for key in reversed(written):
            name, original = before[key]
            path = root / name
            no_symlinks(path)
            if path.read_text(encoding="utf-8") == after[key]:
                write_private(path, original)
        raise


def automate(
    config: dict,
    plan_path: Path,
    root: Path,
    output: Path,
    *,
    fetch=False,
    dry_run=False,
    apply=False,
    now=None,
):
    now = now or datetime.now(UTC)
    plan = read_json(plan_path.expanduser().absolute(), private=True)
    grants, keys, sources = validate_plan(plan, config, now)
    root, output = root.absolute(), output.expanduser().absolute()
    no_symlinks(root)
    before = article_sources(root, keys)
    if dry_run:
        return {
            "status": "DRY_RUN_READY",
            "article_count": len(keys),
            "source_count": len(sources),
            "provider_requests": 0,
            "published": False,
        }
    if not fetch and any(mode != "file" for mode, _ in sources.values()):
        fail("LIVE_FETCH_REQUIRES_EXPLICIT_FLAG")
    batches = {}
    for key, (_, fields) in sources.items():
        batch = fetch_resource(config, *key)
        if batch.warnings:
            fail("FETCH_INCOMPLETE")
        if not batch.records or len(batch.records) > 10000:
            fail("FETCH_EMPTY_OR_TOO_LARGE")
        batches[key] = [mapped(record, fields) for record in batch.records]
    # Revalidate time after slow provider calls. Expired grants cannot be used.
    if now < datetime.now(UTC):
        validate_plan(plan, config, datetime.now(UTC))
    after = {key: text for key, (_, text) in before.items()}
    for placement in plan["placements"]:
        ad = select_creative(
            placement, batches[placement["provider"], placement["resource"]], grants
        )
        key = placement["article_key"]
        after[key] = insert_slot(after[key], placement, ad)
    material = {
        "schema": "RAOSAffiliateDraftCandidateV1",
        "site_url": plan["site_url"],
        "articles": [
            {
                "article_key": key,
                "body_source": before[key][0],
                "before_sha256": sha256(before[key][1].encode()).hexdigest(),
                "after_sha256": sha256(after[key].encode()).hexdigest(),
                "file": key + ".html",
            }
            for key in sorted(keys)
        ],
    }
    payload = json.dumps(material, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    candidate_id = sha256(payload.encode()).hexdigest()
    private_directory(output)
    directory = output / candidate_id
    private_directory(directory)
    artifacts = {key + ".html": after[key] for key in keys}
    artifacts.update(
        {
            key + ".diff": "".join(
                unified_diff(
                    before[key][1].splitlines(keepends=True),
                    after[key].splitlines(keepends=True),
                    fromfile=before[key][0],
                    tofile=before[key][0],
                )
            )
            for key in keys
        }
    )
    artifacts["candidate.json"] = payload
    # Reusing an ID requires byte-identical contents. Never overwrite evidence.
    for name, content in artifacts.items():
        path = directory / name
        no_symlinks(path)
        if path.exists() and path.read_text(encoding="utf-8") != content:
            fail("CANDIDATE_DRIFT")
        if not path.exists():
            write_private(path, content)
    if apply:
        write_drafts(root, before, after)
    result = {
        "status": "DRAFTS_UPDATED" if apply else "CANDIDATE_CREATED",
        "candidate_id": candidate_id,
        "article_keys": sorted(keys),
        "article_count": len(keys),
        "slot_count": len(plan["placements"]),
        "changed_articles": sum(after[key] != before[key][1] for key in keys),
        "published": False,
    }
    write_private(
        output / "latest.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return result


def run_cli(args, config):
    try:
        result = automate(
            config,
            args.plan,
            args.repo,
            args.output,
            fetch=args.fetch,
            dry_run=args.dry_run,
            apply=args.write_drafts,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except LinkError as error:
        print(
            json.dumps({"status": "BLOCKED", "reason": str(error), "published": False})
        )
        return 2
    except FetchError:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": "PROVIDER_FETCH_FAILED",
                    "published": False,
                }
            )
        )
        return 2
    except ConfigError, OSError, ValueError, KeyError, TypeError:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": "INPUT_OR_IO_INVALID",
                    "published": False,
                }
            )
        )
        return 2
