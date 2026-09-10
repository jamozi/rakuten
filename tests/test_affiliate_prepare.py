"""Real owner-direct preparation against synthetic live reads and official files."""

import json

import pytest

from scripts import raos_wordpress_direct_publish as direct
from tests import test_affiliate_link_automation as ads
from tests.wordpress_reader_complete import test_prepare_patch as patch_tests


@pytest.fixture
def prepared(tmp_path):
    fixture = patch_tests.PreparePatchTests()
    fixture.setUp()
    try:
        case = ads.setup_case(tmp_path)
        ads.rewrite(
            case[2],
            lambda plan: plan["placements"][0].update(
                article_key="demo", anchor_id="table"
            ),
        )
        fixture.operator.ORIGIN = ads.SITE
        fixture.baseline["block_markup"] = patch_tests.BODY.replace(
            '<section id="table">',
            '<section id="table" data-raos-product-id="product-a">',
        ).replace(
            "比較表</section>",
            '比較表<a href="https://maker.example/manual">出典</a></section>',
        )
        recipe = json.loads((fixture.root / fixture.source).read_text())
        recipe["required_product_ids"] = ["product-a"]
        fixture.write(fixture.source, json.dumps(recipe))
        fixture.git("add", ".")
        fixture.git("commit", "-qm", "synthetic product binding")
        fixture.commit = fixture.git("rev-parse", "HEAD").strip()
        yield fixture, case
    finally:
        fixture.doCleanups()


def prepare(fixture, case):
    return fixture.namespace["prepare"](
        fixture.root,
        ["demo"],
        call=fixture.call,
        affiliate_plan=case[2],
        affiliate_config=case[1],
    )


def test_live_patch_and_verified_ad_share_private_preview_candidate(prepared):
    fixture, case = prepared
    before = (fixture.root / fixture.source).read_bytes()
    candidate, directory = prepare(fixture, case)
    row = candidate["articles"][0]
    body = row["document"]["block_markup"]
    assert 'id="ks-article-nav"' in body
    assert 'href="https://maker.example/manual"' in body
    assert 'href="https://tracking.example/click?id=offer-a"' in body
    assert "広告・PR" in body
    assert row["baseline"] == fixture.baseline
    assert (fixture.root / fixture.source).read_bytes() == before
    assert candidate["affiliate"]["schema"] == "RAOSAffiliatePreparedArticlesV1"
    assert "NEVER_EXPORT_PRIVATE_DATA" not in json.dumps(candidate)
    assert (
        fixture.namespace["load_candidate"](directory, candidate["candidate_id"])
        == candidate
    )
    assert fixture.calls == ["status", "document"]
    from scripts.raos_wordpress_direct_preview import preview_plan

    assert preview_plan(candidate, directory)["surfaces"][0]["path"] == "/demo/"


@pytest.mark.parametrize(
    "problem", ["wrong_site", "stale", "empty", "different_article"]
)
def test_unverified_input_cannot_create_a_wordpress_candidate(prepared, problem):
    fixture, case = prepared
    if problem == "wrong_site":
        fixture.operator.ORIGIN = "https://other.example"
    elif problem == "stale":
        ads.rewrite(
            case[2],
            lambda plan: plan["grants"][0].update(expires_at="2000-01-01T00:00:00Z"),
        )
    elif problem == "empty":
        case[3].write_text("[]")
    else:
        ads.rewrite(
            case[2], lambda plan: plan["placements"][0].update(article_key="another")
        )
    with pytest.raises(fixture.namespace["DirectFailure"], match="AFFILIATE_"):
        prepare(fixture, case)
    assert not (fixture.root / fixture.namespace["PRIVATE"]).exists()
    assert fixture.calls == ["status", "document"]


def test_expired_affiliate_candidate_cannot_start_publication(tmp_path, monkeypatch):
    candidate = {
        "candidate_id": "a" * 64,
        "checkpoint": {},
        "articles": [],
        "theme": None,
        "affiliate": {
            "schema": "RAOSAffiliatePreparedArticlesV1",
            "valid_until": "2000-01-01T00:00:00+00:00",
        },
    }
    monkeypatch.setattr(direct, "load_candidate", lambda *args: candidate)
    with pytest.raises(direct.DirectFailure, match="AFFILIATE_EXPIRED_REPREPARE"):
        direct._publish(
            tmp_path,
            tmp_path,
            candidate["candidate_id"],
            lambda *a: pytest.fail("unexpected external call"),
        )
    assert not (tmp_path / "journal.json").exists()


def test_expiry_does_not_repeat_an_already_applied_publication(tmp_path, monkeypatch):
    candidate = {
        "candidate_id": "a" * 64,
        "checkpoint": {},
        "articles": [],
        "theme": None,
        "affiliate": {
            "schema": "RAOSAffiliatePreparedArticlesV1",
            "valid_until": "2000-01-01T00:00:00+00:00",
        },
    }
    (tmp_path / "journal.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate["candidate_id"],
                "publication_status": "APPLIED",
                "proposals": {},
            }
        )
    )
    monkeypatch.setattr(direct, "load_candidate", lambda *args: candidate)
    monkeypatch.setattr(
        direct, "finish_publication", lambda *args: {"status": "readback_only"}
    )
    assert direct._publish(
        tmp_path,
        tmp_path,
        candidate["candidate_id"],
        lambda *a: pytest.fail("unexpected publish"),
    ) == {"status": "readback_only"}
