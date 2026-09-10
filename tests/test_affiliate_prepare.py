"""Real owner-direct preparation against synthetic live reads and official files."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import raos_wordpress_direct_publish as direct
from tests import test_affiliate_link_automation as ads
from tests.wordpress_reader_complete import test_prepare_patch as patch_tests
from tests.wordpress_mcp_v1 import test_owner_direct_client as client_tests


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


@pytest.mark.parametrize(
    "expire_after", ["status", "content-propose", "authorize", None]
)
def test_deadline_is_rechecked_and_passed_to_bounded_apply(
    tmp_path, monkeypatch, expire_after
):
    directory, candidate, baseline = client_tests.frozen(tmp_path)
    start_time = datetime.now(UTC).replace(microsecond=0)
    deadline = start_time + timedelta(seconds=60)

    class Clock(datetime):
        current = start_time

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(direct, "datetime", Clock)
    candidate["affiliate"] = {
        "schema": "RAOSAffiliatePreparedArticlesV1",
        "valid_until": deadline.isoformat(),
    }
    monkeypatch.setattr(direct, "load_candidate", lambda *a: candidate)
    monkeypatch.setattr(direct, "verify_preview", lambda *a: None)
    monkeypatch.setattr(direct, "finish_publication", lambda *a: a[3])
    writes = []

    def call(command, body):
        if command == expire_after:
            Clock.current = deadline + timedelta(seconds=5)
        if command == "status":
            return {
                "profile": direct.PROFILE,
                "enabled": True,
                "profile_sha256": "e" * 64,
                "theme": {"tree_sha256": "d" * 64},
            }
        if command == "document":
            return baseline
        if command == "operation-status":
            return {"operation": {"state": "PENDING"}}
        writes.append(command)
        if command == "content-propose":
            return {
                "proposal_id": "b" * 64,
                "after_sha256": direct.content_after_sha256(
                    body["document"], body["id"]
                ),
            }
        if command == "authorize":
            return {"batch_token": "c" * 64, "batch_manifest_sha256": "d" * 64}
        if command == "apply":
            assert body["evidence_expires_at_gmt"] == deadline.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            return {"state": "APPLIED"}
        pytest.fail(command)

    if expire_after:
        with pytest.raises(direct.DirectFailure, match="AFFILIATE_EXPIRED_REPREPARE"):
            direct._publish(tmp_path, directory, candidate["candidate_id"], call)
        assert "apply" not in writes
        if expire_after == "status":
            assert writes == []
    else:
        assert (
            direct._publish(tmp_path, directory, candidate["candidate_id"], call)[
                "publication_status"
            ]
            == "APPLIED"
        )
