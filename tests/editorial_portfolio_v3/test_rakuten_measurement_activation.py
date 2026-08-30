from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import re
import stat
from typing import Callable, cast
from urllib.parse import quote

import pytest

from raos.application.editorial.editorial_portfolio_v2 import (
    load_editorial_portfolio_v2,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    PORTFOLIO_RELATIVE_PATH,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.rakuten_measurement_activation_v3 import (
    ADMIN_RECEIPT_SCHEMA,
    DRY_RUN_SCHEMA,
    MONEY_LINK_MAPPING_SCHEMA,
    RakutenMeasurementActivationV3Failure,
    materialize_article_html,
    materialize_rakuten_measurement_activation_v3,
    validate_rakuten_measurement_activation_v3,
)
from raos.application.finance.editorial_economics_v3 import (
    TRUSTED_T0_EVIDENCE_REQUIRED,
    EditorialEconomicsV3Failure,
    canonical_json_bytes,
    establish_t0_receipt,
    production_readback_template,
)
from scripts.raos_rakuten_measurement_activation_v3 import main as activation_main
from tests.editorial_portfolio_v3.test_economics import _publication_evidence


ROOT = Path(__file__).resolve().parents[2]


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode()


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root.resolve()


def _write_private(root: Path, name: str, content: bytes) -> None:
    path = root / name
    path.write_bytes(content)
    os.chmod(path, 0o600)


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    portfolio = load_editorial_portfolio_v3(ROOT)
    v2 = load_editorial_portfolio_v2(ROOT)
    models = {
        product.product_id: product.representative_model for product in v2.products
    }
    portfolio_sha256 = hashlib.sha256(
        (ROOT / PORTFOLIO_RELATIVE_PATH).read_bytes()
    ).hexdigest()
    provider_measurement_ids = {
        slot.provider_slot_id: f"test-provider-{index:02d}"
        for index, slot in enumerate(portfolio.provider_slots, start=1)
    }
    mapping_provider_slots = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "rakuten_measurement_id": provider_measurement_ids[slot.provider_slot_id],
        }
        for slot in portfolio.provider_slots
    ]
    receipt_provider_slots = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "rakuten_measurement_id": provider_measurement_ids[slot.provider_slot_id],
            "csv_echoed_measurement_id": provider_measurement_ids[
                slot.provider_slot_id
            ],
            "admin_console_measurement_id_verified": True,
        }
        for slot in portfolio.provider_slots
    ]
    mapping_rows: list[dict[str, object]] = []
    receipt_money_links: list[dict[str, object]] = []
    for article in portfolio.articles:
        for binding in article.cta_bindings:
            encoded_destination = quote(
                "https://item.rakuten.co.jp/test-shop/"
                f"{binding.product_id.casefold()}/",
                safe="",
            )
            mapping_rows.append(
                {
                    "article_id": binding.article_id,
                    "product_id": binding.product_id,
                    "placement": binding.placement,
                    "provider_slot_id": binding.provider_slot_id,
                    "representative_model": models[binding.product_id],
                    "destination_url": (
                        "https://hb.afl.rakuten.co.jp/hgc/"
                        f"{provider_measurement_ids[binding.provider_slot_id]}/"
                        f"{binding.cta_id}/?pc={encoded_destination}"
                    ),
                }
            )
            receipt_money_links.append(
                {
                    "article_id": binding.article_id,
                    "product_id": binding.product_id,
                    "placement": binding.placement,
                    "provider_slot_id": binding.provider_slot_id,
                    "representative_model": models[binding.product_id],
                    "csv_echoed_representative_model": models[binding.product_id],
                    "money_link_provider_slot_selection_verified": True,
                    "money_link_product_identity_verified": True,
                }
            )
    mapping: dict[str, object] = {
        "schema": MONEY_LINK_MAPPING_SCHEMA,
        "version": "2.0.0",
        "generated_at": "2026-08-30T10:00:00Z",
        "portfolio_sha256": portfolio_sha256,
        "provider_slot_count": 20,
        "money_link_count": 74,
        "urls_copied_from_rakuten_admin": True,
        "provider_parameter_inference_used": False,
        "provider_slots": mapping_provider_slots,
        "rows": mapping_rows,
    }
    mapping_sha256 = hashlib.sha256(_json_bytes(mapping)).hexdigest()
    receipt: dict[str, object] = {
        "schema": ADMIN_RECEIPT_SCHEMA,
        "version": "2.0.0",
        "state": "OWNER_VERIFIED_RAKUTEN_ADMIN_AND_CSV",
        "verified_at": "2026-08-30T10:05:00Z",
        "owner_attested": True,
        "portfolio_sha256": portfolio_sha256,
        "money_link_mapping_sha256": mapping_sha256,
        "provider_slot_count": 20,
        "money_link_count": 74,
        "verification": {
            "all_expected_provider_slots_accepted_by_admin": True,
            "provider_slot_limit_verified": True,
            "character_set_and_length_verified": True,
            "csv_export_verified": True,
            "all_money_links_product_identity_verified": True,
            "provider_parameter_inference_used": False,
            "production_publication_authorized": False,
        },
        "provider_slots": receipt_provider_slots,
        "money_links": receipt_money_links,
    }
    return mapping, receipt


def _bind_and_write(
    root: Path,
    mapping: dict[str, object],
    receipt: dict[str, object],
) -> None:
    mapping_raw = _json_bytes(mapping)
    receipt["money_link_mapping_sha256"] = hashlib.sha256(mapping_raw).hexdigest()
    _write_private(root, "money-links.json", mapping_raw)
    _write_private(root, "admin-receipt.json", _json_bytes(receipt))


def _v2_pair(root: Path) -> tuple[Path, Path]:
    base = root.parent / "v2"
    local = base / "local"
    production = base / "production"
    portfolio = load_editorial_portfolio_v2(ROOT)
    portfolio_sha256 = hashlib.sha256(
        (
            ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
        ).read_bytes()
    ).hexdigest()
    posts = (
        ROOT / "changes/wordpress-local-preview-v1/fixtures/posts.json"
    ).read_bytes()
    products = [
        {
            "product_id": product.product_id,
            "state": "not_found",
            "provider_binding_sha256": hashlib.sha256(
                product.product_id.encode("ascii")
            ).hexdigest(),
        }
        for product in portfolio.products
    ]
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for mode, fixture_root in (("local", local), ("production", production)):
        article_root = fixture_root / "articles"
        article_root.mkdir(parents=True)
        fixture_root.chmod(0o700)
        article_root.chmod(0o700)
        article_rows = []
        for article in portfolio.articles:
            source = (
                ROOT
                / "changes/wordpress-local-preview-v1/fixtures/articles"
                / f"{article.production_slug}.html"
            ).read_bytes()
            target = article_root / f"{article.production_slug}.html"
            target.write_bytes(source)
            target.chmod(0o600)
            article_rows.append(
                {
                    "article_id": article.article_id,
                    "production_slug": article.production_slug,
                    "content_sha256": hashlib.sha256(source).hexdigest(),
                }
            )
        posts_path = fixture_root / "posts.json"
        posts_path.write_bytes(posts)
        posts_path.chmod(0o600)
        receipt = {
            "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
            "mode": mode,
            "generated_at": generated_at,
            "portfolio_sha256": portfolio_sha256,
            "evidence_status_sha256": "e" * 64,
            "articles": article_rows,
            "products": products,
        }
        receipt_path = fixture_root / "materialization-receipt.v2.json"
        receipt_path.write_bytes(_json_bytes(receipt))
        receipt_path.chmod(0o600)
    return local.resolve(), production.resolve()


def _run(root: Path) -> dict[str, object]:
    local, production = _v2_pair(root)
    report = materialize_rakuten_measurement_activation_v3(
        repository_root=ROOT,
        private_root=root,
        portfolio=load_editorial_portfolio_v3(ROOT),
        admin_receipt_name="admin-receipt.json",
        money_link_mapping_name="money-links.json",
        dry_run_output_name="activation-dry-run.json",
        local_v2_fixture_root=local,
        production_v2_fixture_root=production,
    )
    return dict(report)


def _reseal_production_overlay_after_html_change(
    private: Path,
    report: dict[str, object],
    mutate: Callable[[str], str],
) -> None:
    overlays = cast(dict[str, dict[str, object]], report["overlays"])
    production = overlays["production"]
    old_root = private / cast(str, production["directory_name"])
    rows = cast(list[dict[str, object]], production["articles"])
    row = rows[0]
    slug = cast(str, row["production_slug"])
    article_path = old_root / "articles" / f"{slug}.html"
    changed = mutate(article_path.read_text(encoding="utf-8"))
    article_path.write_text(changed, encoding="utf-8")
    article_path.chmod(0o600)
    row["materialized_sha256"] = hashlib.sha256(changed.encode()).hexdigest()
    article_set_sha256 = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "article_id": article_row["article_id"],
                    "production_slug": article_row["production_slug"],
                    "sha256": article_row["materialized_sha256"],
                }
                for article_row in rows
            ]
        )
    ).hexdigest()
    production["article_set_sha256"] = article_set_sha256

    receipt_path = old_root / "materialization-receipt.v3.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["article_set_sha256"] = article_set_sha256
    receipt["articles"] = rows
    receipt_raw = canonical_json_bytes(receipt)
    overlay_receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    receipt_path.write_bytes(receipt_raw)
    receipt_path.chmod(0o600)
    new_name = f"production-materialized-fixtures-v3-{overlay_receipt_sha256[:16]}"
    production["directory_name"] = new_name
    production["overlay_receipt_sha256"] = overlay_receipt_sha256
    old_root.rename(private / new_name)

    report["materialized_set_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {
                mode: {
                    "posts_sha256": overlays[mode]["posts_sha256"],
                    "article_set_sha256": overlays[mode]["article_set_sha256"],
                    "overlay_receipt_sha256": overlays[mode]["overlay_receipt_sha256"],
                }
                for mode in ("local", "production")
            }
        )
    ).hexdigest()
    _write_private(private, "activation-dry-run.json", canonical_json_bytes(report))


def _replace_first_cta_href_with_host_decoy(markup: str) -> str:
    match = re.search(
        r'href="(https://hb\.afl\.rakuten\.co\.jp/[^"]+)"',
        markup,
    )
    assert match is not None
    return (
        markup[: match.start(1)]
        + "https://example.invalid/not-a-money-link"
        + markup[match.end(1) :]
        + f"\n<!-- {match.group(1)} -->"
    )


def test_exact_20_provider_slots_and_74_money_links_materialize_without_live_write(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    tracked_before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
        ).glob("*.html")
    }

    report = _run(private)

    assert report["schema"] == DRY_RUN_SCHEMA
    assert report["state"] == "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
    assert report["article_count"] == 10
    assert report["provider_slot_count"] == 20
    assert report["provider_measurement_id_count"] == 20
    assert report["internal_cta_identity_count"] == 74
    assert report["live_link_count"] == 74
    assert report["cta_count"] == 74
    portfolio = load_editorial_portfolio_v3(ROOT)
    expected_provider_slot_set_sha256 = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "provider_slot_id": slot.provider_slot_id,
                    "article_id": slot.article_id,
                    "placement": slot.placement,
                }
                for slot in sorted(
                    portfolio.provider_slots,
                    key=lambda value: value.provider_slot_id,
                )
            ]
        )
    ).hexdigest()
    assert report["provider_slot_set_sha256"] == expected_provider_slot_set_sha256
    assert re.fullmatch(
        r"[0-9a-f]{64}", cast(str, report["provider_measurement_binding_sha256"])
    )
    assert report["tracked_source_modified"] is False
    assert report["live_write_performed"] is False
    assert report["publication_authorized"] is False
    assert report["provider_parameter_inference_used"] is False
    assert "hb.afl.rakuten.co.jp" not in json.dumps(report)
    assert "test-provider-" not in json.dumps(report)

    overlay_names = cast(dict[str, dict[str, object]], report["overlays"])
    for mode in ("local", "production"):
        overlay_receipt = json.loads(
            (
                private
                / str(overlay_names[mode]["directory_name"])
                / "materialization-receipt.v3.json"
            ).read_text(encoding="utf-8")
        )
        assert overlay_receipt["provider_slot_count"] == 20
        assert overlay_receipt["provider_measurement_id_count"] == 20
        assert overlay_receipt["internal_cta_identity_count"] == 74
        assert overlay_receipt["live_link_count"] == 74
        assert overlay_receipt["cta_count"] == 74
    materialized = list(
        (
            private / str(overlay_names["production"]["directory_name"]) / "articles"
        ).glob("*.html")
    )
    assert len(materialized) == 10
    combined = b"".join(path.read_bytes() for path in materialized)
    assert combined.count(b"https://hb.afl.rakuten.co.jp/") == 74
    assert combined.count(b'data-raos-cta-id="') == 74
    assert combined.count(b'data-raos-snapshot-id="') == 74
    assert combined.count(b'data-raos-offer-id="') == 74
    assert combined.count(b'data-raos-product-id="') >= 74
    assert combined.count(b'data-raos-placement="') >= 74
    assert combined.count(b'data-raos-rakuten-provider-slot-id="') == 74
    assert b'data-raos-rakuten-measurement-id="' not in combined
    assert combined.count(b'rel="sponsored nofollow"') == 74
    assert combined.count("型番と最新価格を楽天市場で確認する".encode()) == 37
    assert combined.count("在庫・カラーを楽天市場で確認する".encode()) == 37
    assert "一致する楽天商品を確認できなかったため".encode() not in combined
    anchors = re.findall(
        rb'<a class="rakuten-cta raos-cta"[^>]+>',
        combined,
    )
    required_attributes = {
        b"data-raos-article-id",
        b"data-raos-cta-id",
        b"data-raos-snapshot-id",
        b"data-raos-offer-id",
        b"data-raos-product-id",
        b"data-raos-placement",
        b"data-raos-rakuten-provider-slot-id",
    }
    assert len(anchors) == 74
    assert all(
        set(re.findall(rb"\b(data-raos-[a-z-]+)=", anchor)) == required_attributes
        for anchor in anchors
    )
    assert {
        value.decode()
        for value in re.findall(
            rb'data-raos-rakuten-provider-slot-id="([^"]+)"', combined
        )
    } == set(portfolio.provider_slot_by_id)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in materialized)
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    assert tracked_before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked_before
    }
    local = (private.parent / "v2/local").resolve()
    production = (private.parent / "v2/production").resolve()
    validated = validate_rakuten_measurement_activation_v3(
        repository_root=ROOT,
        dry_run_path=private / "activation-dry-run.json",
        portfolio=load_editorial_portfolio_v3(ROOT),
        local_v2_fixture_root=local,
        production_v2_fixture_root=production,
    )
    assert validated.article_count == 10
    assert validated.provider_slot_count == 20
    assert validated.provider_measurement_id_count == 20
    assert validated.internal_cta_identity_count == 74
    assert validated.live_link_count == 74
    assert validated.cta_count == 74
    assert validated.provider_slot_set_sha256 == report["provider_slot_set_sha256"]
    assert (
        validated.provider_measurement_binding_sha256
        == report["provider_measurement_binding_sha256"]
    )
    assert validated.production_article_sha256 == {
        path.stem: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in materialized
    }


def test_cli_emits_only_safe_hash_and_count_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    monkeypatch.setattr(
        "raos.application.editorial.rakuten_measurement_activation_v3._default_v2_fixture_roots",
        lambda _root: (local, production),
    )

    assert (
        activation_main(
            [
                "--private-root",
                str(private),
                "--admin-receipt",
                "admin-receipt.json",
                "--money-link-mapping",
                "money-links.json",
                "--dry-run-output",
                "activation-dry-run.json",
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert '"provider_slot_count":20' in output.out
    assert '"provider_measurement_id_count":20' in output.out
    assert '"internal_cta_identity_count":74' in output.out
    assert '"live_link_count":74' in output.out
    assert '"cta_count":74' in output.out
    assert "hb.afl.rakuten.co.jp" not in output.out
    assert "item.rakuten.co.jp" not in output.out
    assert "test-provider-" not in output.out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda mapping, _receipt: mapping["rows"].pop(),
        lambda mapping, _receipt: mapping["provider_slots"].pop(),
        lambda mapping, _receipt: mapping.update({"provider_slot_count": 74}),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"provider_slot_id": "rps-a99-card"}
        ),
        lambda mapping, _receipt: mapping["provider_slots"][1].update(
            {
                "rakuten_measurement_id": mapping["provider_slots"][0][
                    "rakuten_measurement_id"
                ]
            }
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"representative_model": "=FORMULA()"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": "http://hb.afl.rakuten.co.jp/hgc/bad/"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": "https://evil.example/hgc/bad/"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {
                "destination_url": (
                    "https://hb.afl.rakuten.co.jp/hgc/bad/?keyword=private-query"
                )
            }
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": ("https://user:password@hb.afl.rakuten.co.jp/hgc/bad/")}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": ("https://hb.afl.rakuten.co.jp/hgc/%2e%2e/bad/")}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {
                "destination_url": (
                    "https://hb.afl.rakuten.co.jp/hgc/bad/?pc="
                    "https%3A%2F%2Fitem.rakuten.co.jp%2Fsearch%2Fprivate-query%2F"
                )
            }
        ),
        lambda mapping, _receipt: mapping["rows"][1].update(
            {"destination_url": mapping["rows"][0]["destination_url"]}
        ),
        lambda _mapping, receipt: receipt["provider_slots"][0].update(
            {"csv_echoed_measurement_id": "wrong-provider-id"}
        ),
        lambda _mapping, receipt: receipt["provider_slots"][0].update(
            {
                "rakuten_measurement_id": "wrong-provider-id",
                "csv_echoed_measurement_id": "wrong-provider-id",
            }
        ),
        lambda _mapping, receipt: receipt["money_links"][0].update(
            {"csv_echoed_representative_model": "WRONG-MODEL"}
        ),
        lambda _mapping, receipt: receipt["verification"].update(
            {"csv_export_verified": False}
        ),
    ],
)
def test_missing_extra_mismatched_formula_sensitive_or_unverified_input_fails_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, object], dict[str, object]], object],
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    mutate(mapping, receipt)
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(RakutenMeasurementActivationV3Failure):
        _run(private)

    assert not list(private.glob("*-materialized-fixtures-v3-*"))
    assert not (private / "activation-dry-run.json").exists()


def test_admin_receipt_rejects_wrong_valid_slot_for_article_placement(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    money_links = cast(list[dict[str, object]], receipt["money_links"])
    provider_slots = cast(list[dict[str, object]], receipt["provider_slots"])
    assert money_links[0]["provider_slot_id"] != provider_slots[1]["provider_slot_id"]
    money_links[0]["provider_slot_id"] = provider_slots[1]["provider_slot_id"]
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_admin_receipt_requires_separate_provider_slot_selection_verification(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    money_links = cast(list[dict[str, object]], receipt["money_links"])
    money_links[0]["money_link_provider_slot_selection_verified"] = False
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_mapping_raw_hash_must_equal_owner_receipt_binding(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    mapping_raw = _json_bytes(mapping)
    receipt["money_link_mapping_sha256"] = "0" * 64
    _write_private(private, "money-links.json", mapping_raw)
    _write_private(private, "admin-receipt.json", _json_bytes(receipt))

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_private_inputs_require_exact_modes(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    os.chmod(private / "money-links.json", 0o644)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_PRIVATE_INPUT_INVALID",
    ):
        _run(private)


def test_validated_overlay_fails_closed_on_mode_or_v2_receipt_drift(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    local = (private.parent / "v2/local").resolve()
    production = (private.parent / "v2/production").resolve()
    portfolio = load_editorial_portfolio_v3(ROOT)
    production_overlay = private / str(
        cast(dict[str, dict[str, object]], report["overlays"])["production"][
            "directory_name"
        ]
    )
    target = next((production_overlay / "articles").glob("*.html"))
    target.chmod(0o644)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=portfolio,
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )
    target.chmod(0o600)
    source_receipt = production / "materialization-receipt.v2.json"
    source_receipt.write_bytes(source_receipt.read_bytes() + b"\n")
    source_receipt.chmod(0o600)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_SOURCE_DRIFT",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=portfolio,
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        _replace_first_cta_href_with_host_decoy,
        lambda markup: markup.replace(
            'rel="sponsored nofollow"',
            'rel="noopener"',
            1,
        ),
        lambda markup: re.sub(
            r'data-raos-rakuten-provider-slot-id="[^"]+"',
            'data-raos-rakuten-provider-slot-id="rps-a99-card"',
            markup,
            count=1,
        ),
    ],
    ids=("cta-href-with-host-decoy", "cta-rel", "logical-provider-slot"),
)
def test_resealed_overlay_revalidates_each_cta_href_and_exact_rel(
    tmp_path: Path,
    mutate: Callable[[str], str],
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    _reseal_production_overlay_after_html_change(private, report, mutate)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_(?:URL|OVERLAY)_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_legacy_v2_dry_run_identity_is_rejected(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2"
    dry_run["version"] = "2.0.0"
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


@pytest.mark.parametrize(
    ("field", "invalid_count"),
    (
        ("provider_measurement_id_count", 19),
        ("internal_cta_identity_count", 73),
        ("live_link_count", 73),
    ),
)
def test_dry_run_validator_rejects_explicit_provider_or_live_link_count_drift(
    tmp_path: Path,
    field: str,
    invalid_count: int,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run[field] = invalid_count
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_v3_dry_run_requires_explicit_internal_cta_identity_count(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    assert dry_run["schema"] == DRY_RUN_SCHEMA
    dry_run.pop("internal_cta_identity_count")
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_real_v3_activation_dry_run_cannot_establish_unsigned_t0(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, admin = _documents()
    _bind_and_write(private, mapping, admin)
    activation = _run(private)
    portfolio = load_editorial_portfolio_v3(ROOT)
    activation_raw = (private / "activation-dry-run.json").read_bytes()
    activation_sha256 = hashlib.sha256(activation_raw).hexdigest()
    readback = production_readback_template(portfolio)
    readback["owner_attested"] = True
    publication_binding, publication_contents = _publication_evidence(
        portfolio,
        activation,
        activation_sha256,
        portfolio.source_sha256,
    )
    readback["publication_binding"] = publication_binding
    readback["analytics_site_binding"] = {
        "state": "OWNER_PRIVATE_READ_ONLY_BINDING_VERIFIED",
        "binding_sha256": "a" * 64,
        "ga4_property_id_sha256": "b" * 64,
        "ga4_configuration_response_sha256": "c" * 64,
    }
    timestamps = (
        "2026-08-30T10:01:00Z",
        "2026-08-30T10:02:00Z",
        "2026-08-30T10:03:00Z",
    )
    observations = cast(list[dict[str, object]], readback["observations"])
    for row, timestamp in zip(observations, timestamps, strict=True):
        row["state"] = "SUCCESS"
        row["observed_at"] = timestamp
        row["request_sha256"] = "d" * 64
        row["response_sha256"] = "e" * 64
    production = cast(dict[str, dict[str, object]], activation["overlays"])[
        "production"
    ]
    rakuten = cast(dict[str, object], observations[0]["details"])
    rakuten.update(
        {
            "provider_slot_count": 20,
            "provider_measurement_id_count": 20,
            "internal_cta_identity_count": 74,
            "live_link_count": 74,
            "all_provider_measurement_ids_echo_verified": True,
            "provider_slot_set_sha256": activation["provider_slot_set_sha256"],
            "provider_measurement_binding_sha256": activation[
                "provider_measurement_binding_sha256"
            ],
            "activation_dry_run_sha256": activation_sha256,
            "materialized_set_sha256": activation["materialized_set_sha256"],
            "production_posts_sha256": production["posts_sha256"],
            "production_article_set_sha256": production["article_set_sha256"],
            "production_overlay_receipt_sha256": production["overlay_receipt_sha256"],
        }
    )
    cast(dict[str, object], observations[1]["details"]).update(
        {
            "http_status": 202,
            "aggregate_readback_observed": True,
            "event_id_sha256": "f" * 64,
        }
    )
    cast(dict[str, object], observations[2]["details"]).update(
        {
            "property_id_sha256": "b" * 64,
            "configuration_response_sha256": "c" * 64,
            "analytics_site_binding_sha256": "a" * 64,
            "article_id": portfolio.articles[0].article_id,
            "event_observed": True,
        }
    )
    readback_sha256 = hashlib.sha256(canonical_json_bytes(readback)).hexdigest()
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match=f"^{TRUSTED_T0_EVIDENCE_REQUIRED}$",
    ):
        establish_t0_receipt(
            document=readback,
            observation_sha256=readback_sha256,
            rakuten_activation=activation,
            rakuten_activation_sha256=activation_sha256,
            expected_portfolio_sha256=portfolio.source_sha256,
            portfolio=portfolio,
            **publication_contents,
            evaluated_at=datetime(2026, 8, 30, 11, 0, tzinfo=UTC),
        )


def test_output_name_cannot_overwrite_an_input(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    portfolio = load_editorial_portfolio_v3(ROOT)

    for output_name in ("admin-receipt.json", "money-links.json"):
        with pytest.raises(
            RakutenMeasurementActivationV3Failure,
            match="RAOS_RAKUTEN_ACTIVATION_PRIVATE_NAME_INVALID",
        ):
            materialize_rakuten_measurement_activation_v3(
                repository_root=ROOT,
                private_root=private,
                portfolio=portfolio,
                admin_receipt_name="admin-receipt.json",
                money_link_mapping_name="money-links.json",
                dry_run_output_name=output_name,
            )


def test_article_materialization_rejects_missing_or_duplicate_cta() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    article = portfolio.articles[0]
    source = (
        ROOT
        / "changes/wordpress-local-preview-v1/fixtures/articles"
        / f"{article.production_slug}.html"
    ).read_bytes()
    mapping, _receipt = _documents()
    mapping_rows = cast(list[dict[str, object]], mapping["rows"])
    urls = cast(
        dict[tuple[str, str, str], str],
        {
            (row["article_id"], row["product_id"], row["placement"]): row[
                "destination_url"
            ]
            for row in mapping_rows
            if row["article_id"] == article.article_id
        },
    )
    text = source.decode()
    first = re.search(
        r"<a\b(?=[^>]*data-raos-product-id)[^>]*data-raos-placement="
        r"[\"'](?:product_card|final_summary)[\"'][^>]*>.*?</a>",
        text,
        flags=re.DOTALL,
    )
    assert first is not None

    with pytest.raises(RakutenMeasurementActivationV3Failure):
        materialize_article_html(
            article,
            text.replace(first.group(0), "", 1).encode(),
            urls,
        )
    with pytest.raises(RakutenMeasurementActivationV3Failure):
        materialize_article_html(
            article,
            (text + first.group(0)).encode(),
            urls,
        )
