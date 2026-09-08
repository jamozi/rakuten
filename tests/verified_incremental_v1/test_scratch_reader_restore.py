"""Synthetic V2 scratch producer inputs; no Docker, live records or authority."""

from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest

from raos.application.editorial import local_scratch_restore_v1 as content
from raos.application.editorial import local_scratch_theme_restore_v1 as theme
from raos.application.editorial import verified_incremental_audit_v1 as audit
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
    READER_HUB_SLUGS,
    canonical,
    digest,
)
from tests.verified_incremental_v1.test_restore import snapshot

NOW = datetime(2026, 9, 7, tzinfo=UTC)
FIELDS = {
    "schema",
    "id",
    "post_type",
    "status",
    "title",
    "slug",
    "excerpt",
    "block_markup",
    "taxonomies",
    "media_ids",
}


def fixture(hubs=("categories",), selected=None):
    value, articles = snapshot()
    if hubs:
        value["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
        value["reader_page_slugs"] = sorted(hubs)
    for index, slug in enumerate(hubs, 101):
        row = {
            "schema": "ContentDocumentV1",
            "id": index,
            "post_type": "page",
            "status": "draft",
            "title": "Synthetic hub " + slug,
            "slug": slug,
            "excerpt": "Synthetic scratch input",
            "block_markup": '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="'
            + slug
            + '"]<!-- /wp:shortcode -->',
            "taxonomies": {},
            "media_ids": [],
        }
        row["content_sha256"] = digest(canonical(row).rstrip(b"\n"))
        value["documents"].append(row)
    pages = frozenset(
        selected if selected is not None else (hubs or ("privacy-policy",))
    )
    return value, articles, pages


def prepare(value, articles, pages):
    preparation = content.reader_page_preparation(
        value, article_slugs=articles, selected_page_slugs=pages
    )
    preparation_hash = digest(canonical(preparation))
    expected = content.build_scratch_restoration(
        value,
        article_slugs=articles,
        selected_page_slugs=pages,
        preparation_sha256=preparation_hash,
        environment_id=preparation_hash[:8] + "-abcdef123456",
    )
    return preparation, expected


def observed(value, expected):
    seed = json.loads(expected.seed)
    return {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_READBACK_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": seed["environment_id"],
        "site_url": "http://scratch.wordpress.invalid",
        "source_snapshot_sha256": digest(canonical(value).rstrip(b"\n")),
        "original_id_set": sorted(row["id"] for row in value["documents"]),
        "documents": {
            row["slug"]: {
                key: deepcopy(row[key]) for key in FIELDS | {"content_sha256"}
            }
            for row in value["documents"]
        },
    }


@pytest.mark.parametrize("hubs", [(), ("categories",), tuple(sorted(READER_HUB_SLUGS))])
def test_v2_producer_replays_every_original_field_and_passes_release_validator(hubs):
    value, articles, pages = fixture(hubs)
    before = deepcopy(value)
    preparation, expected = prepare(value, articles, pages)
    assert value == before
    assert preparation["status"] == "PREPARED_NOT_RESTORED"
    seed = json.loads(expected.seed)
    assert set(seed["documents"]) == {row["slug"] for row in value["documents"]}
    assert seed["selected_page_slugs"] == sorted(pages)
    for row in value["documents"]:
        stored = seed["documents"][row["slug"]]
        assert stored["production_id"] == row["id"]
        assert stored["status"] == row["status"]
    receipt = {
        **content.verify_scratch_restoration(expected, observed(value, expected)),
        "verified_at": NOW.isoformat(),
    }
    result = audit.validate_scratch_backup_evidence_v1(
        backup_raw=canonical(value),
        restoration_raw=canonical(receipt),
        readback_raw=canonical(observed(value, expected)),
        expected_snapshot=value,
        expected_article_slugs=articles,
        expected_backup_sha256=digest(canonical(value)),
        observed_at=NOW,
        expected_page_slugs=pages,
    )
    assert result["verified_document_count"] == 14 + len(hubs)
    assert result["selected_page_slugs"] == sorted(pages)
    assert "dates" in result["not_restored"]


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "local-guide",
        "missing-article",
        "missing-core",
        "duplicate-id",
        "boolean-id",
        "wrong-type",
        "undeclared-hub",
        "missing-declared",
        "empty-scope",
        "article-draft",
        "core-draft",
        "unselected-draft",
        "media",
        "hash-drift",
        "taxonomy",
        "wrong-schema",
        "authority",
    ],
)
def test_v2_producer_rejects_unbound_or_nonrestorable_snapshot(change):
    value, articles, pages = fixture()
    row = value["documents"][-1]
    if change in {"unknown", "local-guide"}:
        row["slug"] = (
            "unknown-hub" if change == "unknown" else "dishwasher-running-cost"
        )
    elif change == "missing-article":
        value["documents"].pop(0)
    elif change == "missing-core":
        value["documents"] = [r for r in value["documents"] if r["slug"] != "home"]
    elif change == "duplicate-id":
        row["id"] = value["documents"][0]["id"]
    elif change == "boolean-id":
        row["id"] = True
    elif change == "wrong-type":
        row["post_type"] = "post"
    elif change == "undeclared-hub":
        value["reader_page_slugs"] = []
    elif change == "missing-declared":
        value["reader_page_slugs"].append("purposes")
    elif change == "empty-scope":
        pages = frozenset()
    elif change in {"article-draft", "core-draft"}:
        target = next(
            r
            for r in value["documents"]
            if r["slug"]
            == ("article-0" if change == "article-draft" else "privacy-policy")
        )
        target["status"] = "draft"
        target["content_sha256"] = digest(
            canonical({k: target[k] for k in FIELDS}).rstrip(b"\n")
        )
    elif change == "unselected-draft":
        pages = frozenset({"privacy-policy"})
    elif change == "media":
        row["media_ids"] = [400]
    elif change == "hash-drift":
        row["block_markup"] = "Changed"
    elif change == "taxonomy":
        row["taxonomies"] = {"arbitrary": [1]}
    elif change == "wrong-schema":
        value["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
    else:
        value["publication_authority"] = True
    if change != "hash-drift":
        row["content_sha256"] = digest(
            canonical({k: row[k] for k in FIELDS}).rstrip(b"\n")
        )
    with pytest.raises(IncrementalPublicationFailure):
        prepare(value, articles, pages)


@pytest.mark.parametrize("field", sorted(FIELDS | {"content_sha256"}))
def test_v2_readback_checks_fields_even_when_hashes_are_resealed(field):
    value, articles, pages = fixture()
    _, expected = prepare(value, articles, pages)
    proof = observed(value, expected)
    proof["documents"]["categories"][field] = "tampered"
    with pytest.raises(IncrementalPublicationFailure):
        content.verify_scratch_restoration(expected, proof)


@pytest.mark.parametrize(
    "field",
    [
        "source_snapshot_sha256",
        "environment_id",
        "original_id_set",
        "documents",
        "schema",
        "publication_authority",
        "site_url",
    ],
)
def test_v2_readback_rejects_scope_identity_and_snapshot_drift(field):
    value, articles, pages = fixture()
    _, expected = prepare(value, articles, pages)
    proof = observed(value, expected)
    proof[field] = "tampered"
    with pytest.raises(IncrementalPublicationFailure):
        content.verify_scratch_restoration(expected, proof)


def theme_fixture(hubs=("categories",)):
    value, articles, pages = fixture(hubs)
    baseline = theme.build_theme_package({"style.css": b"Synthetic old theme"})
    candidate = theme.build_theme_package(
        {"style.css": b"Synthetic new theme", "a.css": b"body{}"}
    )
    value["deployment_status"] = {
        "schema": "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1",
        "source": "BOUNDED_WORDPRESS_DEPLOYMENT_MCP",
        "status": "CAPTURED_READ_ONLY",
        "theme": {
            "slug": theme.THEME_SLUG,
            "active": True,
            "tree_sha256": json.loads(baseline)["tree_sha256"],
        },
    }
    _, expected_content = prepare(value, articles, pages)
    readback = observed(value, expected_content)
    receipt = {
        **content.verify_scratch_restoration(expected_content, readback),
        "verified_at": NOW.isoformat(),
    }
    args = dict(
        article_slugs=articles,
        selected_page_slugs=pages,
        content_receipt_raw=canonical(receipt),
        content_readback_raw=canonical(readback),
        baseline_package_raw=baseline,
        candidate_package_raw=candidate,
    )
    expected = theme.build_scratch_theme_restoration(value, **args)
    p = json.loads(expected.preparation)
    proof = {
        "schema": "RAOS_WORDPRESS_READER_PAGE_THEME_RESTORE_READBACK_V2",
        "publication_profile": theme.PROFILE,
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": receipt["environment_id"],
        "theme_slug": theme.THEME_SLUG,
        "site_url": "http://scratch.wordpress.invalid",
        "operation": "SAME_BASENAME_FILES_ONLY_NO_ACTIVATION",
        "source_snapshot_sha256": receipt["source_snapshot_sha256"],
        "content_restore_receipt_sha256": digest(canonical(receipt)),
        "baseline_package_sha256": digest(baseline),
        "candidate_package_sha256": digest(candidate),
        "stages": [
            {
                "stage": stage,
                "theme_tree_sha256": p[kind + "_tree_sha256"],
                "file_manifest": p[kind + "_file_manifest"],
                "content_readback": deepcopy(readback),
                "wordpress_options_sha256": "a" * 64,
            }
            for stage, kind in (
                ("baseline_before", "baseline"),
                ("candidate_installed", "candidate"),
                ("baseline_restored", "baseline"),
            )
        ],
    }
    return value, args, expected, proof


@pytest.mark.parametrize("hubs", [(), ("categories",), tuple(sorted(READER_HUB_SLUGS))])
def test_v2_theme_producer_receipt_passes_actual_release_consumer(hubs):
    value, args, expected, proof = theme_fixture(hubs)
    receipt = {
        **theme.verify_scratch_theme_restoration(expected, proof),
        "verified_at": NOW.isoformat(),
    }
    arguments = dict(args)
    pages = arguments.pop("selected_page_slugs")
    result = audit.validate_scratch_theme_backup_evidence_v1(
        snapshot=value,
        **arguments,
        expected_page_slugs=pages,
        theme_readback_raw=canonical(proof),
        theme_receipt_raw=canonical(receipt),
        expected_candidate_tree_sha256=json.loads(expected.preparation)[
            "candidate_tree_sha256"
        ],
        observed_at=NOW,
    )
    assert result["verified_document_count"] == 14 + len(hubs)
    assert result["selected_page_slugs"] == sorted(pages)


@pytest.mark.parametrize("stage", range(3))
@pytest.mark.parametrize(
    "change", ["draft-promoted", "body", "omitted", "extra", "options", "tree"]
)
def test_v2_theme_rejects_any_stage_mutation(stage, change):
    _, _, expected, proof = theme_fixture()
    row = proof["stages"][stage]
    if change == "draft-promoted":
        row["content_readback"]["documents"]["categories"]["status"] = "publish"
    elif change == "body":
        row["content_readback"]["documents"]["article-0"]["block_markup"] = "Changed"
    elif change == "omitted":
        row["content_readback"]["documents"].pop("categories")
    elif change == "extra":
        row["content_readback"]["documents"]["unknown"] = {}
    elif change == "options":
        row["wordpress_options_sha256"] = "b" * 64
    else:
        row["theme_tree_sha256"] = "b" * 64
    with pytest.raises(IncrementalPublicationFailure):
        theme.verify_scratch_theme_restoration(expected, proof)


def php_simulation(value, expected, *, mutation="", theme_expected=None):
    import base64
    import os
    from pathlib import Path
    import shutil
    import subprocess

    root = Path(__file__).resolve().parents[2]
    payload = {
        "seed": expected.seed.decode(),
        "snapshot": canonical(value).decode(),
        "bodies": {slug: body.decode() for slug, body in expected.bodies.items()},
        "mutation": mutation,
    }
    if theme_expected is not None:
        payload["theme"] = {
            "preparation": theme_expected.preparation.decode(),
            "baseline-package": theme_expected.baseline_package.decode(),
            "candidate-package": theme_expected.candidate_package.decode(),
            "content-receipt": theme_expected.content_receipt.decode(),
        }
    php = os.environ.get("RAOS_PHP_BIN") or shutil.which("php")
    assert php, "The explicit local, offline PHP runtime is required"
    result = subprocess.run(
        [
            php,
            str(root / "tests/verified_incremental_v1/scratch_reader_harness.php"),
            base64.b64encode(canonical(payload)).decode(),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def bound_home_markup() -> str:
    return (
        '<div id="ks-magazine" style="'
        + ";".join(
            f"--km-image-{index}:url(data:image/webp;base64,UklGRg==)"
            for index in range(5)
        )
        + '">'
        '<form action="/" class="km-search" method="get" role="search">'
        '<label for="km-search">検索</label><input id="km-search" name="s" '
        'placeholder="検索" required type="search"><button type="submit">検索</button>'
        "</form></div>"
    )


def set_bound_home(value, markup):
    home = next(row for row in value["documents"] if row["slug"] == "home")
    home["block_markup"] = markup
    home["content_sha256"] = digest(
        canonical({key: home[key] for key in FIELDS}).rstrip(b"\n")
    )
    return home


def test_v2_php_import_preserves_exact_bound_home_with_inline_webp_and_form():
    value, articles, pages = fixture()
    home = set_bound_home(value, bound_home_markup())
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert "synthetic_error" not in proof, proof
    assert (
        proof["synthetic_content"]["documents"]["home"]["block_markup"]
        == home["block_markup"]
    )


def test_v2_php_import_does_not_extend_bound_home_exception_to_active_content():
    value, articles, pages = fixture()
    set_bound_home(value, bound_home_markup() + "<script>alert(1)</script>")
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert proof == {
        "synthetic_error": "RAOS_SCRATCH_BODY_INVALID",
        "synthetic_inserted_count": 0,
    }


def test_v2_php_import_rejects_malformed_active_attribute_on_bound_home():
    value, articles, pages = fixture()
    set_bound_home(
        value,
        bound_home_markup().replace(
            '<form action="/"', '<img/onerror=alert(1) src=x><form action="/"'
        ),
    )
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert proof == {
        "synthetic_error": "RAOS_SCRATCH_BODY_INVALID",
        "synthetic_inserted_count": 0,
    }


@pytest.mark.parametrize(
    "old,new",
    (
        ('method="get"', 'method="post"'),
        ('action="/"', 'action="https://other.example/search"'),
    ),
)
def test_v2_php_import_rejects_non_get_or_external_bound_home_form(old, new):
    value, articles, pages = fixture()
    set_bound_home(value, bound_home_markup().replace(old, new))
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert proof == {
        "synthetic_error": "RAOS_SCRATCH_BODY_INVALID",
        "synthetic_inserted_count": 0,
    }


def test_v2_php_import_rejects_entity_encoded_javascript_url_on_bound_home():
    value, articles, pages = fixture()
    set_bound_home(
        value,
        bound_home_markup().replace(
            "</form>", '<a href="java&#9;script:alert(1)">unsafe</a></form>'
        ),
    )
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert proof == {
        "synthetic_error": "RAOS_SCRATCH_BODY_INVALID",
        "synthetic_inserted_count": 0,
    }


def test_v2_php_import_does_not_extend_bound_home_exception_to_other_documents():
    value, articles, pages = fixture()
    article = next(row for row in value["documents"] if row["post_type"] == "post")
    article["block_markup"] = bound_home_markup()
    article["content_sha256"] = digest(
        canonical({key: article[key] for key in FIELDS}).rstrip(b"\n")
    )
    _, expected = prepare(value, articles, pages)

    proof = php_simulation(value, expected)

    assert proof == {
        "synthetic_error": "RAOS_SCRATCH_BODY_INVALID",
        "synthetic_inserted_count": 0,
    }


@pytest.mark.parametrize("hubs", [(), ("categories",), tuple(sorted(READER_HUB_SLUGS))])
def test_php_import_and_three_theme_states_use_actual_double_stored_fields(hubs):
    value, _, expected, _ = theme_fixture(hubs)
    proof = php_simulation(value, expected.content, theme_expected=expected)
    assert "synthetic_error" not in proof, proof
    result = content.verify_scratch_restoration(
        expected.content, proof["synthetic_content"]
    )
    assert result["verified_document_count"] == 14 + len(hubs)
    theme_result = theme.verify_scratch_theme_restoration(
        expected, proof["synthetic_theme"]
    )
    assert theme_result["verified_document_count"] == 14 + len(hubs)


@pytest.mark.parametrize("mutation", ["promote", "body"])
def test_php_refuses_stored_draft_promotion_and_body_change(mutation):
    value, articles, pages = fixture()
    _, expected = prepare(value, articles, pages)
    result = php_simulation(value, expected, mutation=mutation)
    assert result["synthetic_error"] == "RAOS_SCRATCH_READER_STORED_FIELDS_MISMATCH"


def test_php_rehashes_snapshot_before_any_scratch_insert():
    value, articles, pages = fixture()
    _, expected = prepare(value, articles, pages)
    value["documents"][-1]["title"] = "Different captured document"
    result = php_simulation(value, expected)
    assert result == {
        "synthetic_error": "RAOS_SCRATCH_READER_SNAPSHOT_INVALID",
        "synthetic_inserted_count": 0,
    }


def test_legacy_php_import_and_theme_receipts_still_replay_without_v2_scope():
    from tests.verified_incremental_v1.test_theme_restore import sample

    value, _, expected = sample()
    proof = php_simulation(value, expected.content, theme_expected=expected)
    assert "synthetic_error" not in proof, proof
    result = content.verify_scratch_restoration(
        expected.content, proof["synthetic_content"]
    )
    theme_result = theme.verify_scratch_theme_restoration(
        expected, proof["synthetic_theme"]
    )
    assert result["schema"] == "RAOS_WORDPRESS_SCRATCH_RESTORE_RECEIPT_V1"
    assert theme_result["schema"] == "RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_RECEIPT_V1"


def test_cli_prepare_and_check_do_not_invoke_docker_or_emit_success_receipts(
    tmp_path, monkeypatch, capsys
):
    from scripts import raos_wordpress_scratch_restore as cli
    from raos.application.finance.editorial_economics_v3 import write_private_bytes

    value, articles, pages = fixture()
    private = tmp_path / "private"
    monkeypatch.setattr(cli.local_restore, "owner_root", lambda: private)
    monkeypatch.setattr(cli.local_restore, "production_article_slugs", lambda: articles)
    monkeypatch.setattr(
        cli,
        "run_command",
        lambda *a, **kw: pytest.fail("Preparation must not execute Docker"),
    )
    name = f"live-{digest(canonical(value).rstrip(b'\n'))}.v1.json"
    write_private_bytes(private / "incremental-snapshots", name, canonical(value))
    assert (
        cli.main(
            ["--prepare-only", "--snapshot-name", name, "--reader-pages", "categories"]
        )
        == 0
    )
    preparation = content.reader_page_preparation(
        value, article_slugs=articles, selected_page_slugs=pages
    )
    identity = digest(canonical(preparation))
    assert (
        cli.main(
            [
                "--check-inputs",
                "--preparation-sha256",
                identity,
                "--reader-pages",
                "categories",
            ]
        )
        == 0
    )
    assert not list(private.rglob("*receipt*"))
    assert not list(private.rglob("credentials.env"))
    assert "NOT_EXECUTED" in capsys.readouterr().out
    # A different selected scope cannot reuse a prepared candidate or reach Docker.
    assert (
        cli.main(
            [
                "--check-inputs",
                "--preparation-sha256",
                identity,
                "--reader-pages",
                "privacy-policy",
            ]
        )
        == 69
    )
    # Even a semantically unchanged source rewritten after preparation is not the
    # same retained input bytes.
    write_private_bytes(
        private / "incremental-snapshots", name, canonical(value) + b"\n"
    )
    assert (
        cli.main(
            [
                "--check-inputs",
                "--preparation-sha256",
                identity,
                "--reader-pages",
                "categories",
            ]
        )
        == 69
    )


@pytest.mark.parametrize(
    "slugs",
    [
        "",
        "all",
        "categories,categories",
        "dishwasher-running-cost",
        "categories,unknown",
        "home",
    ],
)
def test_cli_reader_scope_is_explicit_and_closed(slugs):
    from scripts import raos_wordpress_scratch_restore as cli

    with pytest.raises(IncrementalPublicationFailure):
        cli.parse_reader_pages(slugs)


def test_theme_prepare_v2_requires_actual_baseline_bytes_and_matching_page_scope(
    tmp_path, monkeypatch
):
    from scripts import raos_wordpress_scratch_theme_restore as cli
    from raos.application.finance.editorial_economics_v3 import write_private_bytes

    value, args, expected, proof = theme_fixture()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(cli, "private_root", lambda env: private)
    monkeypatch.setattr(
        cli.local_restore, "production_article_slugs", lambda: args["article_slugs"]
    )
    monkeypatch.setattr(
        cli,
        "baseline_package",
        lambda: pytest.fail("V2 must not reuse the pinned V1 Git theme"),
    )
    monkeypatch.setattr(
        cli, "candidate_package", lambda tree: expected.candidate_package
    )
    monkeypatch.setattr(
        cli,
        "run_command",
        lambda *a, **kw: pytest.fail("Theme preparation must not execute Docker"),
    )
    write_private_bytes(private, "source-snapshot.v1.json", canonical(value))
    write_private_bytes(
        private, "scratch-restoration-receipt.v1.json", expected.content_receipt
    )
    write_private_bytes(
        private,
        "scratch-readback.v1.json",
        canonical(proof["stages"][0]["content_readback"]),
    )
    p = json.loads(expected.preparation)
    with pytest.raises(IncrementalPublicationFailure):
        cli.prepare(
            p["environment_id"],
            p["candidate_tree_sha256"],
            selected_page_slugs=frozenset({"categories"}),
        )
    name = f"reader-theme-baseline-{digest(expected.baseline_package)}.v1.json"
    write_private_bytes(private, name, expected.baseline_package)
    target = cli.prepare(
        p["environment_id"],
        p["candidate_tree_sha256"],
        selected_page_slugs=frozenset({"categories"}),
        baseline_package_name=name,
    )
    assert (target / "preparation.v1.json").read_bytes() == expected.preparation
    assert not (target / "receipt.v1.json").exists()
    with pytest.raises(IncrementalPublicationFailure):
        cli.execute(
            p["environment_id"],
            digest(expected.preparation),
            selected_page_slugs=frozenset({"privacy-policy"}),
        )


def test_v2_requires_no_unverified_dates_or_taxonomy_labels_and_preserves_empty_encoding():
    value, articles, pages = fixture()
    value.pop("public_metadata")
    for row in value["documents"]:
        row.pop("modified_gmt", None)
        row.pop("revision_id", None)
        if row["post_type"] == "page":
            row["taxonomies"] = []
            row["content_sha256"] = digest(
                canonical({key: row[key] for key in FIELDS}).rstrip(b"\n")
            )
    _, expected = prepare(value, articles, pages)
    proof = php_simulation(value, expected)
    assert "synthetic_error" not in proof, proof
    result = content.verify_scratch_restoration(expected, proof["synthetic_content"])
    assert "dates" in result["not_restored"]
    assert proof["synthetic_content"]["documents"]["categories"]["taxonomies"] == []


def test_v2_preserves_shared_term_id_across_two_taxonomies_in_scratch():
    value, articles, pages = fixture()
    row = value["documents"][0]
    row["taxonomies"]["post_tag"] = [5]
    row["content_sha256"] = digest(
        canonical({key: row[key] for key in FIELDS}).rstrip(b"\n")
    )
    _, expected = prepare(value, articles, pages)
    proof = php_simulation(value, expected)
    assert "synthetic_error" not in proof, proof
    content.verify_scratch_restoration(expected, proof["synthetic_content"])

def test_reader_snapshot_keeps_wordpress_post_format_taxonomy():
    value, articles, pages = fixture(())
    for row in value["documents"]:
        if row["post_type"] == "post":
            row["taxonomies"]["post_format"] = []
            projection = {key: row[key] for key in content.CONTENT_FIELDS}
            row["content_sha256"] = digest(canonical(projection).rstrip(b"\n"))
    _, expected = prepare(value, articles, pages)
    assert all(
        row["taxonomies"].get("post_format") == []
        for row in json.loads(expected.seed)["content_documents"].values() if row["post_type"] == "post"
    )
