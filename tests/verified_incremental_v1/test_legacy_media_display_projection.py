"""Synthetic byte-bound display transformations; no captured article fixtures."""

from copy import deepcopy

import pytest

from raos.application.editorial import legacy_media_display_projection_v1 as owner
from scripts import raos_wordpress_incremental_seo_audit as seo


def synthetic() -> tuple[dict, dict[str, str]]:
    contract = {
        "schema": owner.SCHEMA,
        "version": "1.0.0",
        "broken_image_path": owner.BROKEN_PATH,
        "articles": {},
    }
    bodies = {}
    for aid, (slug, post_id, decorations, neutrals) in owner.TARGETS.items():
        body = "<div><h2>Comparison question</h2><p>Keep every reader claim.</p>"
        removals = []
        for index in range(decorations + neutrals):
            if index < decorations:
                kind = "decorative-image"
                fragment = (
                    '<img class="raos-comparison__product-image" src="'
                    + owner.BROKEN_PATH
                    + '" alt="" width="64" height="64" loading="lazy">'
                )
            else:
                kind = "neutral-media"
                fragment = (
                    '<div class="raos-product-card__media"><img src="'
                    + owner.BROKEN_PATH
                    + '" alt="Syntheticを比較検討するための中立イメージ。商品写真ではありません"'
                    ' width="128" height="128" loading="lazy" data-raos-product-image-id="PRD-TEST"'
                    ' data-raos-product-image-state="neutral"></div>'
                )
            removals.append(
                {
                    "offset": len(body.encode()),
                    "length": len(fragment.encode()),
                    "sha256": owner.digest(fragment.encode()),
                    "kind": kind,
                }
            )
            body += fragment + "<span>Keep product name.</span>"
        body += '<a href="https://example.invalid/recorded" rel="nofollow sponsored">Keep purchase link.</a>'
        body += '<img src="/verified-test.jpg" alt="Recorded verified image" data-raos-product-image-state="verified">'
        body += "</div>"
        output = body.encode()
        for row in reversed(removals):
            output = output[: row["offset"]] + output[row["offset"] + row["length"] :]
        profile = {
            "input_sha256": owner.digest(body.encode()),
            "output_sha256": owner.digest(output),
            "removals": removals,
        }
        contract["articles"][aid] = {
            "slug": slug,
            "post_id": post_id,
            "baseline_document_sha256": "a" * 64,
            "profiles": {name: deepcopy(profile) for name in sorted(owner.PROFILES)},
        }
        bodies[aid] = body
    return contract, bodies


def project(body: str, aid: str, contract: dict):
    return owner.project_legacy_media(
        body, aid, profile="production", contract=contract, contract_sha256="c" * 64
    )


def test_exact_projection_removes_only_decorations_and_empty_neutral_wrappers() -> None:
    contract, bodies = synthetic()
    for aid, body in bodies.items():
        before = body
        result = project(body, aid, contract)
        assert body == before
        assert result.proof["state"] == "APPLIED"
        assert result.proof["removed_decoration_count"] == 8
        assert result.proof["removed_neutral_media_count"] == owner.TARGETS[aid][3]
        assert owner.BROKEN_PATH not in result.markup
        assert "raos-product-card__media" not in result.markup
        assert 'data-raos-product-image-state="verified"' in result.markup
        assert "Keep every reader claim." in result.markup
        assert "Keep purchase link." in result.markup
        assert result.markup.count("Keep product name.") == 8 + owner.TARGETS[aid][3]


@pytest.mark.parametrize(
    "mutation",
    [
        "body",
        "cta",
        "path",
        "offset",
        "length",
        "fragment_hash",
        "output",
        "count",
        "kind",
        "profile",
    ],
)
def test_projection_refuses_modified_baseline_or_self_described_bad_removals(
    mutation: str,
) -> None:
    contract, bodies = synthetic()
    aid = next(iter(bodies))
    body = bodies[aid]
    rule = contract["articles"][aid]["profiles"]["production"]
    if mutation == "body":
        body += " "
    elif mutation == "cta":
        body = body.replace("recorded", "changed")
    elif mutation == "path":
        body = body.replace(owner.BROKEN_PATH, "/other.png", 1)
    elif mutation == "offset":
        rule["removals"][0]["offset"] += 1
    elif mutation == "length":
        rule["removals"][0]["length"] -= 1
    elif mutation == "fragment_hash":
        rule["removals"][0]["sha256"] = "d" * 64
    elif mutation == "output":
        rule["output_sha256"] = "d" * 64
    elif mutation == "count":
        rule["removals"].pop()
    elif mutation == "kind":
        rule["removals"][0]["kind"] = "arbitrary-container"
    else:
        contract["articles"][aid]["profiles"].pop("local-stored")
    with pytest.raises(owner.LegacyMediaProjectionFailure):
        project(body, aid, contract)


def test_even_rehashed_text_or_verified_image_is_not_a_removable_fragment() -> None:
    for raw, kind in (
        (b"<p>Do not hide an inconvenient claim.</p>", "decorative-image"),
        (b'<img src="/verified.jpg" alt="Verified photograph">', "decorative-image"),
        (
            b'<div class="raos-product-card__media"><p>Keep safety warning.</p></div>',
            "neutral-media",
        ),
    ):
        with pytest.raises(owner.LegacyMediaProjectionFailure):
            owner.validate_fragment(raw, kind)


def test_updated_clean_article_is_not_applicable_and_never_promoted_to_verified() -> (
    None
):
    contract, bodies = synthetic()
    aid = next(iter(bodies))
    result = project(
        "<p>Updated article without the obsolete media.</p>", aid, contract
    )
    assert result.proof["state"] == "NOT_APPLICABLE"
    assert result.proof["input_sha256"] == result.proof["output_sha256"]
    assert result.proof["removed_neutral_media_count"] == 0
    unchanged = project(bodies[aid], "unrelated-article", contract)
    assert unchanged.markup == bodies[aid]


def test_public_body_check_uses_expected_projection_without_ignoring_actual_nodes(
    monkeypatch,
) -> None:
    contract, bodies = synthetic()
    aid = next(iter(bodies))
    monkeypatch.setattr(owner, "load_contract", lambda: (contract, "c" * 64))
    rendered = project(bodies[aid], aid, contract).markup
    page = (
        '<html><head></head><body><div class="entry-content">'
        + rendered
        + "</div></body></html>"
    )
    assert len(seo.verify_rendered_body(bodies[aid], page, article_id=aid)) == 64
    with pytest.raises(seo.seo.AuditError, match="PUBLIC_BODY_OR_COMMERCE_MISMATCH"):
        seo.verify_rendered_body(
            bodies[aid],
            page.replace("Keep purchase link.", "Altered purchase."),
            article_id=aid,
        )
    with pytest.raises(seo.seo.AuditError, match="PUBLIC_BODY_OR_COMMERCE_MISMATCH"):
        seo.verify_rendered_body(
            bodies[aid],
            page.replace("/verified-test.jpg", "/wrong.jpg"),
            article_id=aid,
        )


def test_checked_contract_contains_hashes_ranges_and_counts_not_captured_copy() -> None:
    contract, checksum = owner.load_contract()
    assert len(checksum) == 64
    owner.validate_contract(contract)
    for row in contract["articles"].values():
        assert set(row) == {"slug", "post_id", "baseline_document_sha256", "profiles"}
        for profile in row["profiles"].values():
            for removal in profile["removals"]:
                assert set(removal) == {"offset", "length", "sha256", "kind"}
    source = (
        owner.ROOT / owner.CONTRACT_PATH.parent.parent / "functions.php"
    ).read_text()
    assert (
        "add_filter('the_content', 'kurashinoshirube_filter_legacy_media_display', 1)"
        in source
    )
    section = source[
        source.index(
            "function kurashinoshirube_filter_legacy_media_display"
        ) : source.index("/** Load the generated public-safe")
    ]
    assert "get_post_field('post_content'" in section
    assert "wp_update_post(" not in section
