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
from typing import TypeAlias, TypeGuard
from urllib.parse import urlsplit

from raos.application.editorial import reader_components as components
from raos.application.editorial.reader_running_cost import render_cost_profiles
from raos.application.editorial.reader_experience_v1 import (
    COMPARISON_REQUIREMENTS,
    CheckedFact,
    comparison_issues,
    validate_experience,
)

SCHEMA = "RAOS_LOCAL_READER_GUIDES_V1"
Record: TypeAlias = Mapping[str, object]


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LOCAL_GUIDE_TEXT_REQUIRED")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


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


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_record(value: object) -> TypeGuard[Record]:
    return isinstance(value, Mapping)


def _strings(value: object) -> list[str]:
    if not _is_object_list(value) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("LOCAL_GUIDE_SCHEMA_INVALID")
    return [item for item in value if isinstance(item, str)]


def _records(value: object) -> list[Record]:
    if not _is_object_list(value) or any(not _is_record(item) for item in value):
        raise ValueError("LOCAL_GUIDE_SCHEMA_INVALID")
    return [item for item in value if _is_record(item)]


def _validate_schema(registry: Mapping[str, object]) -> None:
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
        if "heading_topic" in fact:
            _text(fact["heading_topic"])
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
        if _text(article.get("article_type")) == "comparison":
            _strings(article.get("comparison_products"))


def _bound(
    fact: Record, sources: Mapping[str, Record], hosts: set[str], today: date
) -> bool:
    source = sources.get(str(fact.get("source_ref", "")))
    if source is None:
        return False
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
        and fact.get("exact_model") in _strings(source.get("models", []))
    )


def build_local_guides(
    registry: Mapping[str, object],
    *,
    today: date,
    existing_targets: Mapping[object, object] | None = None,
) -> dict[str, object]:
    """Resolve evidence before rendering; incomplete comparisons emit only blockers."""
    if (
        registry.get("schema") != SCHEMA
        or registry.get("publication_authority") is not False
    ):
        raise ValueError("LOCAL_GUIDE_BOUNDARY_INVALID")
    _validate_schema(registry)
    hosts = set(_strings(registry["official_hosts"]))
    source_rows = _records(registry["sources"])
    fact_rows = _records(registry["facts"])
    articles = _records(registry["articles"])
    sources = {_identifier(source.get("source_ref")): source for source in source_rows}
    facts = {_identifier(fact.get("evidence_ref")): fact for fact in fact_rows}
    if len(sources) != len(source_rows) or len(facts) != len(fact_rows):
        raise ValueError("LOCAL_GUIDE_DUPLICATE_REFERENCE")
    ready: list[Record] = []
    blocked: list[dict[str, object]] = []
    ids: set[str] = set()
    slugs: set[str] = set()
    for article in articles:
        identifier = _identifier(article.get("article_id"))
        slug = _text(article.get("local_slug"))
        article_type = _text(article.get("article_type"))
        if not re.fullmatch(r"local-preview-[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("LOCAL_GUIDE_ROUTE_INVALID")
        if (
            identifier in ids
            or slug in slugs
            or article_type not in {"guide", "comparison"}
        ):
            raise ValueError("LOCAL_GUIDE_IDENTITY_INVALID")
        ids.add(identifier)
        slugs.add(slug)
        for field in ("title", "dek", "summary", "category"):
            _text(article.get(field))
        sections = _records(article.get("sections"))
        section_ids = [_identifier(section.get("id")) for section in sections]
        if len(section_ids) != len(set(section_ids)) or any(
            s.startswith("guide-") or s.startswith("reader-") for s in section_ids
        ):
            raise ValueError("LOCAL_GUIDE_SECTION_ID_INVALID")
        refs = _strings(article.get("evidence_refs", []))
        issues: list[str] = []
        if not refs:
            issues.append("evidence.required")
        valid: dict[str, Record] = {}
        for ref in refs:
            _identifier(ref)
            fact = facts.get(ref)
            if fact is None or not _bound(fact, sources, hosts, today):
                issues.append("evidence." + ref)
            else:
                valid[ref] = fact
        for section in sections:
            for paragraph in _records(section.get("paragraphs")):
                _text(paragraph.get("text"))
                if any(
                    ref not in refs
                    for ref in _strings(paragraph.get("evidence_refs", []))
                ):
                    issues.append("paragraph.unresolved_evidence")
        if article_type == "comparison":
            models = _strings(article.get("comparison_products", []))
            grouped: dict[str, dict[str, CheckedFact]] = {}
            for model in models:
                grouped[model] = {}
                for ref, fact in valid.items():
                    if _text(fact.get("exact_model")) != model:
                        continue
                    requirement = _text(fact.get("requirement"))
                    if requirement in grouped[model]:
                        issues.append(
                            model + "." + requirement + ".conflicting_evidence"
                        )
                    grouped[model][requirement] = CheckedFact(
                        ref,
                        _identifier(fact.get("source_ref")),
                        _optional_text(
                            sources[_identifier(fact.get("source_ref"))].get(
                                "checked_at"
                            )
                        ),
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
                    "dek": _text(article.get("dek")),
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
        candidate_issues: list[str] = []
        for ref in refs:
            fact = facts.get(ref)
            if fact is None or _text(fact.get("exact_model")) not in grouped:
                candidate_issues.append("evidence." + ref)
                continue
            requirement = _text(fact.get("requirement"))
            if requirement not in COMPARISON_REQUIREMENTS:
                candidate_issues.append("requirement." + requirement)
                continue
            group = grouped[_text(fact.get("exact_model"))]
            if requirement in group:
                candidate_issues.append("evidence.conflicting." + requirement)
                continue
            source = sources.get(_identifier(fact.get("source_ref")))
            group[requirement] = CheckedFact(
                ref,
                _identifier(fact.get("source_ref")),
                _optional_text(source.get("checked_at"))
                if source is not None
                else None,
                "KNOWN" if _bound(fact, sources, hosts, today) else "UNKNOWN",
            )
        candidate_issues.extend(comparison_issues(grouped))
        if candidate_issues:
            blocked.append(
                {
                    "article_id": identifier,
                    "issues": list(dict.fromkeys(candidate_issues)),
                }
            )
    targets: dict[str, str] = {}
    for target_ref, url in (existing_targets or {}).items():
        if not isinstance(url, str) or not re.fullmatch(
            r"/local-preview-[a-z0-9]+(?:-[a-z0-9]+)*/(?:#[A-Za-z0-9_-]+)?", url
        ):
            raise ValueError("LOCAL_GUIDE_TARGET_INVALID")
        if isinstance(target_ref, str):
            targets[target_ref] = url
    targets.update(
        {
            _identifier(article.get("article_id")): "/"
            + _text(article.get("local_slug"))
            + "/"
            for article in ready
        }
    )
    documents: list[dict[str, object]] = []
    for article in ready:
        html = _render(article, facts, sources, targets)
        document: dict[str, object] = {
            "article_id": _identifier(article.get("article_id")),
            "local_slug": _text(article.get("local_slug")),
            "article_type": _text(article.get("article_type")),
            "title": _text(article.get("title")),
            "dek": _text(article.get("dek")),
            "category": _text(article.get("category")),
            "purposes": _strings(article.get("purposes", [])),
        }
        document.update(
            {
                "html": html,
                "content_sha256": sha256(html.encode()).hexdigest(),
                "checked_at": max(
                    _text(
                        sources[_identifier(facts[ref].get("source_ref"))].get(
                            "checked_at"
                        )
                    )
                    for ref in _strings(article.get("evidence_refs", []))
                ),
            }
        )
        documents.append(document)
    return {
        "schema": SCHEMA,
        "publication_authority": False,
        "articles": documents,
        "blocked": blocked,
    }


def _render(
    article: Record,
    facts: Mapping[str, Record],
    sources: Mapping[str, Record],
    targets: Mapping[str, str],
) -> str:
    body: list[str] = [
        '<div class="raos-editorial-v2"><span class="raos-reader-view" data-raos-article-id="'
        + escape(_identifier(article.get("article_id")), quote=True)
        + '" hidden></span>'
    ]
    body.append(
        '<p class="raos-article-category">選び方ガイド</p><p>'
        + escape(_text(article.get("dek")))
        + "</p>"
    )
    dates = sorted(
        {
            _text(sources[_identifier(facts[ref].get("source_ref"))].get("checked_at"))
            for ref in _strings(article.get("evidence_refs", []))
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
            "<p>" + escape(_text(article.get("summary"))) + "</p>",
            "raos-guide-summary",
        ).html()
    )
    axes = components.decision_axes(
        [
            {
                "label": _text(axis.get("label")),
                "why_it_matters": _text(axis.get("why_it_matters")),
                "how_to_check": _text(axis.get("how_to_check")),
            }
            for axis in _records(article.get("decision_axes", []))
        ]
    )
    if axes is not None:
        body.append(axes.html())
    body.append(render_cost_profiles(article, facts))
    for section in _records(article.get("sections")):
        paragraphs: list[str] = []
        for paragraph in _records(section.get("paragraphs")):
            refs = _strings(paragraph.get("evidence_refs", []))
            links = "".join(
                ' <a href="#guide-evidence-'
                + escape(ref, quote=True)
                + '">根拠'
                + str(i)
                + "</a>"
                for i, ref in enumerate(refs, 1)
            )
            paragraphs.append(
                "<p>" + escape(_text(paragraph.get("text"))) + links + "</p>"
            )
        body.append(
            components.section(
                _identifier(section.get("id")),
                _text(section.get("heading")),
                "".join(paragraphs),
                "raos-guide-section",
            ).html()
        )
    for component in (
        components.unknowns_panel(
            [
                {
                    "topic": _text(unknown.get("topic")),
                    "why_unknown": _text(unknown.get("why_unknown")),
                    "how_to_verify": _text(unknown.get("how_to_verify")),
                    "decision_effect": _text(unknown.get("decision_effect")),
                }
                for unknown in _records(article.get("unknowns", []))
            ]
        ),
        components.purchase_checklist(_strings(article.get("purchase_checks", []))),
    ):
        if component is not None:
            body.append(component.html())
    for link in _records(article.get("contextual_links", [])):
        target = targets.get(_text(link.get("target_ref")))
        if target:
            component = components.contextual_link(
                _text(link.get("question")),
                target,
                _text(link.get("journey_stage")),
                existing_targets=frozenset(targets.values()),
            )
            if component is not None:
                body.append(component.html())
    body.append(
        '<section class="raos-evidence-panel" id="guide-evidence" aria-labelledby="guide-evidence-title"><h2 id="guide-evidence-title">型番・公式出典・確認日を確認する</h2>'
    )
    for ref in _strings(article.get("evidence_refs", [])):
        fact = facts[ref]
        source = sources[_identifier(fact.get("source_ref"))]
        body.append(
            '<div id="guide-evidence-'
            + escape(ref, quote=True)
            + '"><h3>'
            + escape(_text(fact.get("exact_model")))
            + (
                "：" + escape(_text(fact["heading_topic"]))
                if "heading_topic" in fact
                else ""
            )
            + "</h3><p>"
            + escape(_text(fact.get("text")))
            + '</p><p><a data-raos-cta-type="verify" href="'
            + escape(_text(source.get("url")), quote=True)
            + '">'
            + escape(_text(source.get("title")))
            + "</a>："
            + escape(_text(fact.get("locator")))
            + " ／ 確認日："
            + escape(_text(source.get("checked_at")))
            + "</p></div>"
        )
    body.append("</section></div>")
    return "".join(body)
