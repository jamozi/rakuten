"""Local editorial guides and exact-model comparison eligibility.

This projection has no provider or WordPress writer. Its documents have only
local routes and never participate in the ten-article publication portfolio.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from hashlib import sha256
from html import escape
import re
from typing import Any
from urllib.parse import urlsplit

from raos.application.editorial import reader_components as components
from raos.application.editorial.reader_experience_v1 import (
    COMPARISON_REQUIREMENTS,
    CheckedFact,
    comparison_issues,
    validate_experience,
)

SCHEMA = "RAOS_LOCAL_READER_GUIDES_V1"


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LOCAL_GUIDE_TEXT_REQUIRED")
    return value


def _identifier(value: object) -> str:
    value = _text(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("LOCAL_GUIDE_IDENTIFIER_INVALID")
    return value


def _dated(value: object, today: date) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value) <= today
    except ValueError:
        return False


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("LOCAL_GUIDE_SCHEMA_INVALID")
    return value


def _records(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError("LOCAL_GUIDE_SCHEMA_INVALID")
    return value


def _validate_schema(registry: Mapping[str, Any]) -> None:
    _strings(registry.get("official_hosts"))
    for source in _records(registry.get("sources")):
        _identifier(source.get("source_ref"))
        for field in ("url", "title", "authority"):
            _text(source.get(field))
        models = _strings(source.get("models"))
        if not models or len(set(models)) != len(models):
            raise ValueError("LOCAL_GUIDE_SOURCE_MODELS_INVALID")
    for fact in _records(registry.get("facts")):
        for field in ("evidence_ref", "source_ref"):
            _identifier(fact.get(field))
        for field in ("exact_model", "requirement", "text", "state"):
            _text(fact.get(field))
        if not isinstance(fact.get("locator"), str):
            raise ValueError("LOCAL_GUIDE_LOCATOR_INVALID")
    for article in _records(registry.get("articles")):
        for field in (
            "article_id",
            "local_slug",
            "article_type",
            "title",
            "dek",
            "summary",
            "category",
        ):
            _text(article.get(field))
        for field in ("evidence_refs", "purposes", "purchase_checks"):
            _strings(article.get(field, []))
        for axis in _records(article.get("decision_axes", [])):
            for field in ("label", "why_it_matters", "how_to_check"):
                _text(axis.get(field))
        for section in _records(article.get("sections")):
            _identifier(section.get("id"))
            _text(section.get("heading"))
            for paragraph in _records(section.get("paragraphs")):
                _text(paragraph.get("text"))
                _strings(paragraph.get("evidence_refs", []))
        for unknown in _records(article.get("unknowns", [])):
            for field in ("topic", "why_unknown", "how_to_verify", "decision_effect"):
                _text(unknown.get(field))
        for link in _records(article.get("contextual_links", [])):
            for field in ("question", "target_ref", "journey_stage"):
                _text(link.get(field))
        if article["article_type"] == "comparison":
            _strings(article.get("comparison_products"))


def _bound(
    fact: Mapping[str, Any], sources: Mapping[str, Any], hosts: set[str], today: date
) -> bool:
    source = sources.get(str(fact.get("source_ref", "")), {})
    parsed = urlsplit(str(source.get("url", "")))
    return bool(
        fact.get("state") == "KNOWN"
        and fact.get("text")
        and fact.get("locator")
        and source.get("authority") == "MANUFACTURER_OFFICIAL"
        and parsed.scheme == "https"
        and parsed.hostname in hosts
        and not parsed.username
        and not parsed.password
        and _dated(source.get("checked_at"), today)
        and fact.get("exact_model") in source.get("models", [])
    )


def build_local_guides(
    registry: Mapping[str, Any],
    *,
    today: date,
    existing_targets: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve evidence before rendering; incomplete comparisons emit only blockers."""
    if (
        registry.get("schema") != SCHEMA
        or registry.get("publication_authority") is not False
    ):
        raise ValueError("LOCAL_GUIDE_BOUNDARY_INVALID")
    _validate_schema(registry)
    hosts = set(registry["official_hosts"])
    sources = {s["source_ref"]: s for s in registry["sources"]}
    facts = {f["evidence_ref"]: f for f in registry["facts"]}
    if len(sources) != len(registry["sources"]) or len(facts) != len(registry["facts"]):
        raise ValueError("LOCAL_GUIDE_DUPLICATE_REFERENCE")
    ready, blocked = [], []
    ids, slugs = set(), set()
    for article in registry["articles"]:
        identifier = _identifier(article["article_id"])
        slug = _text(article["local_slug"])
        if not re.fullmatch(r"local-preview-[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("LOCAL_GUIDE_ROUTE_INVALID")
        if (
            identifier in ids
            or slug in slugs
            or article["article_type"] not in {"guide", "comparison"}
        ):
            raise ValueError("LOCAL_GUIDE_IDENTITY_INVALID")
        ids.add(identifier)
        slugs.add(slug)
        for field in ("title", "dek", "summary", "category"):
            _text(article[field])
        section_ids = [_identifier(s["id"]) for s in article["sections"]]
        if len(section_ids) != len(set(section_ids)) or any(
            s.startswith("guide-") or s.startswith("reader-") for s in section_ids
        ):
            raise ValueError("LOCAL_GUIDE_SECTION_ID_INVALID")
        refs = article["evidence_refs"]
        issues = []
        if not refs:
            issues.append("evidence.required")
        valid = {}
        for ref in refs:
            _identifier(ref)
            fact = facts.get(ref)
            if fact is None or not _bound(fact, sources, hosts, today):
                issues.append("evidence." + ref)
            else:
                valid[ref] = fact
        for section in article["sections"]:
            for paragraph in section["paragraphs"]:
                _text(paragraph["text"])
                if any(ref not in refs for ref in paragraph.get("evidence_refs", [])):
                    issues.append("paragraph.unresolved_evidence")
        if article["article_type"] == "comparison":
            models = article.get("comparison_products", [])
            grouped: dict[str, dict[str, CheckedFact]] = {}
            for model in models:
                grouped[model] = {}
                for ref, fact in valid.items():
                    if fact["exact_model"] != model:
                        continue
                    requirement = fact["requirement"]
                    if requirement in grouped[model]:
                        issues.append(
                            model + "." + requirement + ".conflicting_evidence"
                        )
                    grouped[model][requirement] = CheckedFact(
                        ref,
                        fact["source_ref"],
                        sources[fact["source_ref"]]["checked_at"],
                        "KNOWN",
                    )
            issues.extend(comparison_issues(grouped))
        # Apply the shared untested-experience rule to authored guide copy as well.
        issues.extend(
            validate_experience(
                {
                    "article_type": "shortlist",
                    "research_status": {
                        "real_world_tested": False,
                        "ranking_uses_commission": False,
                    },
                    "dek": article["dek"],
                    "local_guide": article,
                },
                product_refs=frozenset(),
                evidence_refs=frozenset(),
            )
        )
        if issues:
            blocked.append(
                {"article_id": identifier, "issues": list(dict.fromkeys(issues))}
            )
        else:
            ready.append(article)
    # Candidate requests carry evidence only. They never create article prose.
    for candidate in _records(registry.get("comparison_candidates", [])):
        identifier = _identifier(candidate.get("candidate_id"))
        models = _strings(candidate.get("exact_models"))
        refs = _strings(candidate.get("evidence_refs"))
        grouped = {model: {} for model in models}
        candidate_issues = []
        for ref in refs:
            fact = facts.get(ref)
            if fact is None or fact["exact_model"] not in grouped:
                candidate_issues.append("evidence." + ref)
                continue
            requirement = fact["requirement"]
            if requirement not in COMPARISON_REQUIREMENTS:
                candidate_issues.append("requirement." + requirement)
                continue
            group = grouped[fact["exact_model"]]
            if requirement in group:
                candidate_issues.append("evidence.conflicting." + requirement)
                continue
            source = sources.get(fact["source_ref"], {})
            group[requirement] = CheckedFact(
                ref, fact["source_ref"], source.get("checked_at"),
                "KNOWN" if _bound(fact, sources, hosts, today) else "UNKNOWN",
            )
        candidate_issues.extend(comparison_issues(grouped))
        if candidate_issues:
            blocked.append({"article_id": identifier, "issues": list(dict.fromkeys(candidate_issues))})
    targets = dict(existing_targets or {})
    if any(
        not isinstance(url, str)
        or not re.fullmatch(
            r"/local-preview-[a-z0-9]+(?:-[a-z0-9]+)*/(?:#[A-Za-z0-9_-]+)?", url
        )
        for url in targets.values()
    ):
        raise ValueError("LOCAL_GUIDE_TARGET_INVALID")
    targets.update({a["article_id"]: "/" + a["local_slug"] + "/" for a in ready})
    documents = []
    for article in ready:
        html = _render(article, facts, sources, targets)
        documents.append(
            {
                k: article[k]
                for k in (
                    "article_id",
                    "local_slug",
                    "article_type",
                    "title",
                    "dek",
                    "category",
                    "purposes",
                )
            }
            | {
                "html": html,
                "content_sha256": sha256(html.encode()).hexdigest(),
                "checked_at": max(
                    sources[facts[ref]["source_ref"]]["checked_at"]
                    for ref in article["evidence_refs"]
                ),
            }
        )
    return {
        "schema": SCHEMA,
        "publication_authority": False,
        "articles": documents,
        "blocked": blocked,
    }


def _render(
    article: Mapping[str, Any],
    facts: Mapping[str, Any],
    sources: Mapping[str, Any],
    targets: Mapping[str, str],
) -> str:
    body = [
        '<div class="raos-editorial-v2"><span class="raos-reader-view" data-raos-article-id="'
        + escape(article["article_id"], quote=True)
        + '" hidden></span>'
    ]
    body.append(
        '<p class="raos-article-category">選び方ガイド</p><p>'
        + escape(article["dek"])
        + "</p>"
    )
    dates = sorted(
        {
            sources[facts[ref]["source_ref"]]["checked_at"]
            for ref in article["evidence_refs"]
        }
    )
    body.append(
        '<p class="raos-research-status">公式情報確認：'
        + escape(" / ".join(dates))
        + ' ／ 実機確認：未実施 ／ 販売リンクなし。<a href="#guide-evidence">出典・調査範囲</a></p>'
    )
    body.append(
        components.section(
            "guide-summary",
            "30秒で分かる、先にすること",
            "<p>" + escape(article["summary"]) + "</p>",
            "raos-guide-summary",
        ).html()
    )
    axes = components.decision_axes(article.get("decision_axes", []))
    if axes is not None:
        body.append(axes.html())
    for section in article["sections"]:
        paragraphs = []
        for paragraph in section["paragraphs"]:
            refs = paragraph.get("evidence_refs", [])
            links = "".join(
                ' <a href="#guide-evidence-'
                + escape(ref, quote=True)
                + '">根拠'
                + str(i)
                + "</a>"
                for i, ref in enumerate(refs, 1)
            )
            paragraphs.append("<p>" + escape(paragraph["text"]) + links + "</p>")
        body.append(
            components.section(
                section["id"],
                section["heading"],
                "".join(paragraphs),
                "raos-guide-section",
            ).html()
        )
    for component in (
        components.unknowns_panel(article.get("unknowns", [])),
        components.purchase_checklist(article.get("purchase_checks", [])),
    ):
        if component is not None:
            body.append(component.html())
    for link in article.get("contextual_links", []):
        target = targets.get(link["target_ref"])
        if target:
            component = components.contextual_link(
                link["question"],
                target,
                link["journey_stage"],
                existing_targets=frozenset(targets.values()),
            )
            if component is not None:
                body.append(component.html())
    body.append(
        '<section class="raos-evidence-panel" id="guide-evidence" aria-labelledby="guide-evidence-title"><h2 id="guide-evidence-title">型番・公式出典・確認日を確認する</h2>'
    )
    for ref in article["evidence_refs"]:
        fact = facts[ref]
        source = sources[fact["source_ref"]]
        body.append(
            '<div id="guide-evidence-'
            + escape(ref, quote=True)
            + '"><h3>'
            + escape(fact["exact_model"])
            + "</h3><p>"
            + escape(fact["text"])
            + '</p><p><a data-raos-cta-type="verify" href="'
            + escape(source["url"], quote=True)
            + '">'
            + escape(source["title"])
            + "</a>："
            + escape(fact["locator"])
            + " ／ 確認日："
            + escape(source["checked_at"])
            + "</p></div>"
        )
    body.append("</section></div>")
    return "".join(body)
