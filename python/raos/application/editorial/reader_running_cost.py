"""Evidence-bound, inert cost profiles; calculation is local browser arithmetic."""

from collections.abc import Mapping
from html import escape
from math import isfinite
import re

from raos.application.editorial import reader_components as components


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LOCAL_COST_TEXT_REQUIRED")
    return value


def _identifier(value: object) -> str:
    value = _text(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("LOCAL_COST_IDENTIFIER_INVALID")
    return value


def _quantity(
    ref: object,
    *,
    model: str,
    course: str,
    kind: str,
    unit: str,
    facts: Mapping[str, Mapping[str, object]],
    refs: list[object],
) -> tuple[str, str, str] | None:
    if ref is None:
        return None
    ref = _identifier(ref)
    fact = facts.get(ref)
    if (
        ref not in refs
        or fact is None
        or fact.get("state") != "KNOWN"
        or fact.get("exact_model") != model
    ):
        raise ValueError("LOCAL_COST_EVIDENCE_UNBOUND")
    quantities = fact.get("quantities")
    if not isinstance(quantities, list) or not all(
        isinstance(q, Mapping) for q in quantities
    ):
        raise ValueError("LOCAL_COST_QUANTITY_REQUIRED")
    matches = [
        q for q in quantities if q.get("kind") == kind and q.get("course") == course
    ]
    if len(matches) != 1:
        raise ValueError("LOCAL_COST_QUANTITY_AMBIGUOUS_OR_MISSING")
    quantity = matches[0]
    value = quantity.get("value")
    if (
        quantity.get("unit") != unit
        or quantity.get("basis") != "one_cycle"
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < 0
    ):
        raise ValueError("LOCAL_COST_QUANTITY_INVALID")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("LOCAL_COST_QUANTITY_INVALID")
    return str(value), ref, _text(quantity.get("course_label"))


def render_cost_profiles(
    article: Mapping[str, object], facts: Mapping[str, Mapping[str, object]]
) -> str:
    """Called only after the guide's official sources and references are validated.

    No forms or executable HTML pass through the WordPress content sanitizer.
    An authenticated local-guide identity separately gates the enhancement asset.
    """
    config = article.get("cost_calculator")
    if config is None:
        return ""
    if article.get("article_id") != "dishwasher-running-cost" or not isinstance(
        config, Mapping
    ):
        raise ValueError("LOCAL_COST_ARTICLE_INVALID")
    profiles = config.get("profiles")
    refs = article.get("evidence_refs")
    default = _identifier(config.get("default_profile"))
    if (
        not isinstance(profiles, list)
        or not 1 <= len(profiles) <= 8
        or not isinstance(refs, list)
    ):
        raise ValueError("LOCAL_COST_PROFILES_INVALID")
    seen: set[str] = set()
    rows: list[str] = []
    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise ValueError("LOCAL_COST_PROFILE_INVALID")
        identifier = _identifier(profile.get("profile_id"))
        if identifier in seen:
            raise ValueError("LOCAL_COST_DUPLICATE_PROFILE")
        seen.add(identifier)
        model = _text(profile.get("exact_model"))
        course = _identifier(profile.get("course"))
        if "course_label" in profile:
            raise ValueError("LOCAL_COST_LABEL_MUST_BELONG_TO_EVIDENCE")
        attrs = (
            ' data-raos-cost-profile="'
            + escape(identifier, quote=True)
            + '" data-raos-cost-model="'
            + escape(model, quote=True)
            + '"'
        )
        if "product_anchor" in profile:
            anchor = _identifier(profile["product_anchor"])
            if not anchor.startswith("product-dish-"):
                raise ValueError("LOCAL_COST_PRODUCT_ANCHOR_INVALID")
            attrs += ' data-raos-cost-anchor="' + escape(anchor, quote=True) + '"'
        labels: set[str] = set()
        cells: list[str] = []
        for key, kind, unit, attribute in (
            ("energy_ref", "energy_per_cycle", "Wh", "data-raos-energy-wh"),
            ("water_ref", "water_per_cycle", "L", "data-raos-water-litres"),
        ):
            if key not in profile:
                raise ValueError("LOCAL_COST_REFERENCE_REQUIRED")
            quantity = _quantity(
                profile[key],
                model=model,
                course=course,
                kind=kind,
                unit=unit,
                facts=facts,
                refs=refs,
            )
            if quantity is None:
                cells.append("<td>未確認（計算に含めません）</td>")
            else:
                value, ref, label = quantity
                labels.add(label)
                attrs += " " + attribute + '="' + escape(value, quote=True) + '"'
                cells.append(
                    "<td>"
                    + escape(value + unit)
                    + ' <a href="#guide-evidence-'
                    + escape(ref, quote=True)
                    + '">根拠</a></td>'
                )
        if len(labels) > 1:
            raise ValueError("LOCAL_COST_CONDITION_MISMATCH")
        label = next(iter(labels)) if labels else "コース別の消費量は未確認"
        attrs += ' data-raos-cost-course="' + escape(label, quote=True) + '"'
        scope = "現行比較対象" if "product_anchor" in profile else "参考（比較対象外）"
        rows.append(
            "<tr"
            + attrs
            + '><th scope="row">'
            + escape(model)
            + "</th><td>"
            + escape(scope)
            + "</td><td>"
            + escape(label)
            + "</td>"
            + "".join(cells)
            + "</tr>"
        )
    if default not in seen:
        raise ValueError("LOCAL_COST_DEFAULT_INVALID")
    return components.section(
        "guide-cost-calculator",
        "自宅の単価で、一回分と月の従量費を計算する",
        "<p>消費電力量は公表された一運転当たりの値を使います。水量は、公表使用水量または説明書の必要給水量を一運転分の前提として試算します。「参考（比較対象外）」の行は以前の掲載機種で、現行の比較記事の候補ではありません。未確認の費目は計算に含めず、"
        "定格W・運転時間・タンク容量から補いません。表の条件を選び、自宅の単価を入力してください。機種間で対象コースが揃っていないため、使用水量だけの横比較には使えません。</p>"
        '<div class="raos-cost-calculator" data-raos-cost-calculator="v1" data-raos-default-profile="'
        + escape(default, quote=True)
        + '">'
        '<p class="raos-cost-no-script">計算フォームにはJavaScriptが必要です。利用できない場合は、'
        "下の公表値と本文の式で確認できます。入力した内容は保存・送信しません。</p>"
        '<div class="comparison-table-wrap" role="region" aria-labelledby="guide-cost-values-caption" tabindex="0">'
        '<table><caption id="guide-cost-values-caption">計算に使える公表値と対象条件（実測値ではありません）</caption>'
        '<thead><tr><th scope="col">型番</th><th scope="col">区分</th><th scope="col">コース・条件</th>'
        '<th scope="col">消費電力量／回</th><th scope="col">使用水量／回</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></div>"
        "<p>計算できるのは入力した条件での従量費の概算です。基本料金・段階料金、"
        "家庭での消費量の変化を含む請求額や、手洗いとの差額を示すものではありません。</p>",
        "raos-guide-cost-section",
    ).html()
