"""Exercise real file ingestion and draft changes without provider traffic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.affiliate_ingestion.cli import main
from tools.affiliate_ingestion.config import atomic_write_config, initial_config


SITE = "https://reader.example"
ARTICLE = "changes/wordpress-direct-publish-v1/articles/guide.html"
ORIGINAL = (
    '<!-- wp:html --><section id="model-a" data-raos-product-id="product-a">'
    '<h2>製品A</h2><p><a href="https://maker.example/manual">出典</a></p>'
    "</section><p>既存本文</p><!-- /wp:html -->"
)


def setup_case(tmp_path, provider="linkshare", html=None):
    now = datetime.now(UTC)
    root = tmp_path / "repo"
    body = root / ARTICLE
    body.parent.mkdir(parents=True)
    body.write_text(ORIGINAL)
    registry = {
        "schema": "RAOSOwnerDirectArticlesV1",
        "profile": "owner-direct-v1",
        "articles": [{"article_key": "guide", "body_source": ARTICLE}],
    }
    (body.parent.parent / "articles.v1.json").write_text(json.dumps(registry))
    offer = {
        "offer_id": "offer-a",
        "advertiser_id": "merchant-a",
        "site_url": SITE,
        "model": "MODEL-A",
        "variant": "standard",
        "jan": "1234567890128",
        "status": "active",
        "landing_url": "https://maker.example/product/a",
        "affiliate_url": "https://tracking.example/click?id=offer-a",
        "html": html or "",
        "raw_private": "NEVER_EXPORT_PRIVATE_DATA",
    }
    export = tmp_path / "official.json"
    export.write_text(json.dumps([offer]))
    config = initial_config()
    config["providers"][provider].update(
        enabled=True, mode="file", account_id="synthetic-owner"
    )
    config["providers"][provider]["resources"]["products"].update(
        enabled=True, mode="file", path=str(export), format="json"
    )
    config_path = atomic_write_config(tmp_path / "networks.json", config)
    plan = {
        "schema": "RAOSAffiliateAutomationPlanV1",
        "enabled": True,
        "site_url": SITE,
        "grants": [
            {
                "provider": provider,
                "advertiser_id": "merchant-a",
                "site_url": SITE,
                "approved": True,
                "checked_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=12)).isoformat(),
                "evidence_ref": "owner-confirmed-partnership",
                "format": "html" if html else "url",
                "allowed_hosts": ["tracking.example", "pixel.example"],
            }
        ],
        "placements": [
            {
                "slot_id": "guide-product-a",
                "article_key": "guide",
                "editorial_eligible": True,
                "article_type": "shortlist",
                "product_ref": "product-a",
                "anchor_id": "model-a",
                "provider": provider,
                "resource": "products",
                "offer_id": "offer-a",
                "identity": {
                    "model": "MODEL-A",
                    "variant": "standard",
                    "jan": "1234567890128",
                },
                "landing_url": "https://maker.example/product/a",
            }
        ],
    }
    plan_path = atomic_write_config(tmp_path / "plan.json", plan)
    return root, config_path, plan_path, export, tmp_path / "result"


def run_case(case, *flags):
    root, config, plan, _, output = case
    args = [
        "--config",
        str(config),
        "automate",
        "--plan",
        str(plan),
        "--repo",
        str(root),
        "--output",
        str(output),
        *flags,
    ]
    try:
        return main(args)
    except SystemExit as error:
        return error.code


def test_documented_module_command_works_without_pythonpath(tmp_path):
    case = setup_case(tmp_path)
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.affiliate_ingestion",
            "--config",
            str(case[1]),
            "automate",
            "--plan",
            str(case[2]),
            "--repo",
            str(case[0]),
            "--output",
            str(case[4]),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "DRY_RUN_READY"


def rewrite(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))
    path.chmod(0o600)


@pytest.mark.parametrize(
    "provider", ["a8net", "valuecommerce", "moshimo", "linkshare", "accesstrade", "afb"]
)
def test_official_file_creates_private_candidate_preserving_source(tmp_path, provider):
    case = setup_case(tmp_path, provider)
    assert run_case(case) == 0
    root, _, _, _, output = case
    assert (root / ARTICLE).read_text() == ORIGINAL
    report = json.loads((output / "latest.json").read_text())
    candidate = output / report["candidate_id"]
    rendered = (candidate / "guide.html").read_text()
    assert 'rel="sponsored nofollow noopener noreferrer"' in rendered
    assert "https://tracking.example/click?id=offer-a" in rendered
    assert 'href="https://maker.example/manual">出典</a>' in rendered
    assert rendered.index("広告・PR") < rendered.index("tracking.example")
    assert "既存本文" in rendered
    assert not any(
        "NEVER_EXPORT_PRIVATE_DATA" in p.read_text() for p in candidate.iterdir()
    )
    assert (candidate.stat().st_mode & 0o077) == 0
    assert all((p.stat().st_mode & 0o077) == 0 for p in candidate.iterdir())


def test_apply_is_local_and_idempotent(tmp_path):
    case = setup_case(tmp_path)
    assert run_case(case, "--write-drafts") == 0
    text = (case[0] / ARTICLE).read_text()
    assert "tracking.example" in text
    assert run_case(case, "--write-drafts") == 0
    assert (case[0] / ARTICLE).read_text() == text
    assert text.count('data-raos-affiliate-slot="guide-product-a"') == 1


def test_official_html_is_inserted_without_rewriting(tmp_path):
    html = '<a href="https://tracking.example/click?id=offer-a">広告主の指定文言</a><img src="https://pixel.example/p.gif" width="1" height="1" alt="" />'
    case = setup_case(tmp_path, "afb", html)
    assert run_case(case, "--write-drafts") == 0
    assert html in (case[0] / ARTICLE).read_text()


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "MODEL-B"),
        ("variant", "accessory-only"),
        ("jan", "different"),
        ("status", "ended"),
        ("advertiser_id", "unapproved-merchant"),
        ("landing_url", "https://maker.example/product/b"),
        ("affiliate_url", "javascript:alert(1)"),
        ("affiliate_url", "https://tracking.example.attacker.example/click"),
    ],
)
def test_wrong_or_unapproved_offer_cannot_change_article(tmp_path, field, value):
    case = setup_case(tmp_path)
    rewrite(case[3], lambda rows: rows[0].update({field: value}))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL
    assert not (case[4] / "latest.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", False),
        ("approved", "true"),
        ("site_url", "https://other.example"),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
        ("checked_at", "2099-01-01T00:00:00+00:00"),
        ("evidence_ref", ""),
    ],
)
def test_missing_stale_or_other_site_grant_cannot_change_article(
    tmp_path, field, value
):
    case = setup_case(tmp_path)
    rewrite(case[2], lambda plan: plan["grants"][0].update({field: value}))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


@pytest.mark.parametrize(
    "html",
    [
        '<script src="https://tracking.example/script.js"></script>',
        '<a href="https://tracking.example/click" onclick="alert(1)">buy</a>',
        '<a href="https://tracking.example/click">buy</a><img src="https://evil.example/p">',
        '<iframe src="https://tracking.example"></iframe>',
        '<a href="https://tracking.example/click?id=offer-a">buy</a><![CDATA[hidden]]>',
        '<a href="https://tracking.example/click?id=offer-a">buy</a><img src="https://pixel.example/p',
        '<a href="https://tracking.example/click?id=offer-a"/>',
    ],
)
def test_unsafe_creative_is_rejected_not_sanitized(tmp_path, html):
    case = setup_case(tmp_path, "afb", html)
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_ambiguous_offer_and_missing_anchor_do_not_write(tmp_path):
    case = setup_case(tmp_path)
    rewrite(case[3], lambda rows: rows.append(dict(rows[0])))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL
    rewrite(case[3], lambda rows: rows.pop())
    (case[0] / ARTICLE).write_text(ORIGINAL.replace('id="model-a"', 'id="another"'))
    assert run_case(case, "--write-drafts") != 0


def test_disabled_and_empty_plan_never_fetch(tmp_path, monkeypatch):
    case = setup_case(tmp_path)
    import tools.affiliate_ingestion.link_automation as automation

    monkeypatch.setattr(
        automation, "fetch_resource", lambda *a, **kw: pytest.fail("unexpected fetch")
    )
    rewrite(case[2], lambda plan: plan.update(enabled=False))
    assert run_case(case) != 0
    rewrite(case[2], lambda plan: plan.update(enabled=True, placements=[]))
    assert run_case(case) != 0


def test_remote_requires_explicit_fetch_and_dry_run_has_no_network(
    tmp_path, monkeypatch
):
    case = setup_case(tmp_path)
    rewrite(
        case[1],
        lambda cfg: cfg["providers"]["linkshare"].update(
            mode="api", account_id="owner-id"
        ),
    )
    rewrite(
        case[1],
        lambda cfg: cfg["providers"]["linkshare"]["resources"]["products"].update(
            mode="api", endpoint="https://api.example/products"
        ),
    )
    import tools.affiliate_ingestion.link_automation as automation

    monkeypatch.setattr(
        automation, "fetch_resource", lambda *a, **kw: pytest.fail("unexpected fetch")
    )
    assert run_case(case) != 0
    assert run_case(case, "--dry-run") == 0
    assert not case[4].exists()


def test_path_escape_and_symlink_are_rejected(tmp_path):
    case = setup_case(tmp_path)
    registry = case[0] / "changes/wordpress-direct-publish-v1/articles.v1.json"
    rewrite(
        registry,
        lambda data: data["articles"][0].update(body_source="../../outside.html"),
    )
    assert run_case(case, "--write-drafts") != 0
    rewrite(registry, lambda data: data["articles"][0].update(body_source=ARTICLE))
    outside = tmp_path / "outside.html"
    outside.write_text(ORIGINAL)
    (case[0] / ARTICLE).unlink()
    (case[0] / ARTICLE).symlink_to(outside)
    assert run_case(case, "--write-drafts") != 0
    assert outside.read_text() == ORIGINAL


@pytest.mark.parametrize(
    "field,value",
    [
        ("editorial_eligible", False),
        ("editorial_eligible", "true"),
        ("article_type", "status_check"),
        ("article_type", "invented"),
    ],
)
def test_editorially_ineligible_articles_cannot_receive_ads(tmp_path, field, value):
    case = setup_case(tmp_path)
    rewrite(case[2], lambda plan: plan["placements"][0].update({field: value}))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_different_destination_inside_official_code_is_rejected(tmp_path):
    case = setup_case(
        tmp_path, "afb", '<a href="https://tracking.example/wrong-product">購入</a>'
    )
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_api_field_mapping_and_fetch_failure_keep_raw_private(
    tmp_path, monkeypatch, capsys
):
    case = setup_case(tmp_path)
    rewrite(
        case[1],
        lambda cfg: cfg["providers"]["linkshare"]["resources"]["products"].update(
            mode="api",
            endpoint="https://api.example/products",
            link_fields={"offer_id": "advertisement.id"},
        ),
    )
    raw = json.loads(case[3].read_text())[0]
    raw["advertisement"] = {"id": raw.pop("offer_id")}
    import tools.affiliate_ingestion.link_automation as automation
    from tools.affiliate_ingestion.client import FetchBatch, FetchError

    monkeypatch.setattr(
        automation,
        "fetch_resource",
        lambda *a: FetchBatch(
            "linkshare", "products", datetime.now(UTC).isoformat(), [raw], []
        ),
    )
    assert run_case(case, "--fetch") == 0
    latest = (case[4] / "latest.json").read_bytes()

    def broken(*args):
        raise FetchError("https://api.example/?token=NEVER_PRINT_TOKEN")

    monkeypatch.setattr(automation, "fetch_resource", broken)
    assert run_case(case, "--fetch", "--write-drafts") != 0
    assert "NEVER_PRINT_TOKEN" not in capsys.readouterr().out
    assert (case[4] / "latest.json").read_bytes() == latest
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_truncated_or_empty_feed_never_removes_existing_link(tmp_path, monkeypatch):
    case = setup_case(tmp_path)
    assert run_case(case, "--write-drafts") == 0
    original = (case[0] / ARTICLE).read_bytes()
    import tools.affiliate_ingestion.link_automation as automation
    from tools.affiliate_ingestion.client import FetchBatch

    for records, warnings in [
        ([], []),
        (json.loads(case[3].read_text()), ["max_pages reached"]),
    ]:
        monkeypatch.setattr(
            automation,
            "fetch_resource",
            lambda *a: FetchBatch(
                "linkshare",
                "products",
                datetime.now(UTC).isoformat(),
                records,
                [],
                warnings,
            ),
        )
        assert run_case(case, "--write-drafts") != 0
        assert (case[0] / ARTICLE).read_bytes() == original


def test_all_placements_are_validated_before_any_article_write(tmp_path):
    case = setup_case(tmp_path)
    rewrite(
        case[2],
        lambda plan: plan["placements"].append(
            dict(plan["placements"][0], slot_id="second", offer_id="missing")
        ),
    )
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_no_sale_disclosure_requires_editorial_update(tmp_path):
    case = setup_case(tmp_path)
    body = ORIGINAL.replace("既存本文", "この記事の販売リンクは掲載していません")
    (case[0] / ARTICLE).write_text(body)
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == body


def test_live_patch_articles_require_a_fresh_baseline(tmp_path, capsys):
    case = setup_case(tmp_path)
    rewrite(
        case[0] / "changes/wordpress-direct-publish-v1/articles.v1.json",
        lambda registry: registry["articles"][0].update(
            patch_source="guide.patch.json"
        ),
    )
    assert run_case(case, "--write-drafts") != 0
    assert "PATCH_ARTICLE_REQUIRES_LIVE_BASELINE" in capsys.readouterr().out
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


@pytest.mark.parametrize("site", ["https://other.example", None])
def test_offer_must_explicitly_belong_to_plan_site(tmp_path, site):
    case = setup_case(tmp_path)
    rewrite(case[3], lambda rows: rows[0].update(site_url=site))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


def test_supplied_offer_jan_requires_verified_expected_jan(tmp_path):
    case = setup_case(tmp_path)
    rewrite(case[2], lambda plan: plan["placements"][0]["identity"].pop("jan"))
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL


@pytest.mark.parametrize(
    "prefix", ["<p>Intro\u2028</p>\n", "<p>Intro\r</p>\n", "<p>Intro\r\n</p>\r\n"]
)
def test_article_newlines_and_offsets_are_preserved(tmp_path, prefix):
    case = setup_case(tmp_path)
    source = prefix + ORIGINAL.replace("既存本文", "既存\u2029本文")
    (case[0] / ARTICLE).write_bytes(source.encode())
    assert run_case(case, "--write-drafts") == 0
    updated = (case[0] / ARTICLE).read_bytes().decode()
    start = updated.index("<!-- raos-affiliate:guide-product-a:start -->")
    end = updated.index("<!-- raos-affiliate:guide-product-a:end -->") + len(
        "<!-- raos-affiliate:guide-product-a:end -->"
    )
    assert updated[:start] + updated[end:] == source
    assert updated[end:].startswith("</section>")
    from hashlib import sha256

    report = json.loads((case[4] / "latest.json").read_text())
    candidate = json.loads(
        (case[4] / report["candidate_id"] / "candidate.json").read_text()
    )
    assert (
        candidate["articles"][0]["before_sha256"] == sha256(source.encode()).hexdigest()
    )
    assert run_case(case, "--write-drafts") == 0
    assert (case[0] / ARTICLE).read_bytes().decode() == updated


def test_report_write_failure_restores_updated_drafts(tmp_path, monkeypatch):
    case = setup_case(tmp_path)
    import tools.affiliate_ingestion.link_automation as automation

    original_write = automation.write_private

    def failed_report(path, content):
        if path == case[4] / "latest.json":
            raise OSError("synthetic report write failure")
        original_write(path, content)

    monkeypatch.setattr(automation, "write_private", failed_report)
    assert run_case(case, "--write-drafts") != 0
    assert (case[0] / ARTICLE).read_text() == ORIGINAL
    assert not (case[4] / "latest.json").exists()


def test_second_article_write_failure_restores_first_draft(tmp_path, monkeypatch):
    case = setup_case(tmp_path)
    root = case[0]
    second = root / ARTICLE.replace("guide.html", "second.html")
    second.write_text(ORIGINAL)
    rewrite(
        root / "changes/wordpress-direct-publish-v1/articles.v1.json",
        lambda registry: registry["articles"].append(
            {"article_key": "second", "body_source": str(second.relative_to(root))}
        ),
    )
    rewrite(
        case[2],
        lambda plan: plan["placements"].append(
            dict(plan["placements"][0], article_key="second", slot_id="second-a")
        ),
    )
    import tools.affiliate_ingestion.link_automation as automation

    original_write = automation.write_private
    written = []

    def failed_second_write(path, content):
        if path == second:
            assert (root / ARTICLE).read_text() != ORIGINAL
            raise OSError("synthetic disk failure")
        if path == root / ARTICLE:
            written.append(content)
        original_write(path, content)

    monkeypatch.setattr(automation, "write_private", failed_second_write)
    assert run_case(case, "--write-drafts") != 0
    assert len(written) == 2
    assert (root / ARTICLE).read_text() == ORIGINAL
    assert second.read_text() == ORIGINAL
    assert not (case[4] / "latest.json").exists()


def test_plan_and_candidate_symlinks_do_not_write_outside_output(tmp_path):
    case = setup_case(tmp_path)
    case[2].chmod(0o644)
    assert run_case(case) != 0
    case[2].chmod(0o600)
    assert run_case(case) == 0
    report = json.loads((case[4] / "latest.json").read_text())
    path = case[4] / report["candidate_id"] / "guide.html"
    path.unlink()
    victim = tmp_path / "outside"
    victim.write_text("KEEP")
    path.symlink_to(victim)
    assert run_case(case) != 0
    assert victim.read_text() == "KEEP"
