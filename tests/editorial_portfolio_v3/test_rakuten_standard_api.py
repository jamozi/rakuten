"""Standard links preserve full coverage without impersonating admin review."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from html import escape
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from raos.application.editorial import rakuten_standard_api_v1 as standard
from raos.application.editorial import rakuten_measurement_activation_v3 as measured
from raos.application.editorial.editorial_portfolio_v2 import (
    load_editorial_portfolio_v2,
)
from scripts import raos_wordpress_publication_request as publication
from tests.editorial_portfolio_v3.test_rakuten_measurement_activation import (
    ROOT,
    _private_root,
    _v2_pair,
    _synthetic_destination_url,
    _stub_verified_v2_evidence,  # noqa: F401 -- imported pytest fixture
)


@pytest.fixture
def api_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _private_root(tmp_path)
    pair = _v2_pair(root)
    monkeypatch.setattr(measured, "default_v2_fixture_roots", lambda _: pair)
    monkeypatch.setattr(
        standard,
        "product_evidence_views_v2",
        lambda *_a, **_k: {
            product.product_id: SimpleNamespace(
                evidence=SimpleNamespace(
                    destination_url=_synthetic_destination_url(product.product_id),
                )
            )
            for product in load_editorial_portfolio_v2(ROOT).products
        },
    )
    return root


def test_full_standard_api_roundtrip_with_repeated_urls(api_pair: Path) -> None:
    result = standard.materialize_standard_api_v1(
        repository_root=ROOT,
        private_root=api_pair,
        receipt_name="standard.json",
    )
    assert result["cta_count"] == 74
    assert result["product_count"] == 33
    overlay = standard.validate_standard_api_v1(
        repository_root=ROOT,
        receipt_path=api_pair / "standard.json",
    )
    html = "".join(
        path.read_text()
        for path in (overlay.production_fixture_root / "articles").glob("*.html")
    )
    assert html.count('rel="sponsored nofollow"') == 74
    assert html.count('data-raos-cta-id="') == 74
    assert "data-raos-rakuten-provider-slot-id" not in html
    assert "admin_receipt_sha256" not in overlay.binding
    assert overlay.binding["measurement_collection_enabled"] is False
    publication._validate_materialization_binding(dict(overlay.binding))
    urls = [
        measured._anchor_attributes(match.group(1))["href"]
        for match in measured.CTA_ANCHOR_RE.finditer(html)
    ]
    assert len(urls) == 74 and len(set(urls)) == 33
    # A standard receipt must never be silently accepted as measured-admin.
    with pytest.raises(publication.PublicationFailure):
        publication.validate_publication_link_evidence(api_pair / "standard.json")


@pytest.mark.parametrize(
    "field,value",
    [
        ("link_mode", "measured-admin"),
        ("owner_attested", True),
        ("measurement_collection_enabled", True),
        ("provenance", "ADMIN_VERIFIED"),
    ],
)
def test_standard_receipt_tampering_fails(
    api_pair: Path, field: str, value: object
) -> None:
    standard.materialize_standard_api_v1(
        repository_root=ROOT, private_root=api_pair, receipt_name="standard.json"
    )
    path = api_pair / "standard.json"
    document = json.loads(path.read_bytes())
    document[field] = value
    path.write_bytes(standard.canonical_json_bytes(document))
    with pytest.raises(measured.RakutenMeasurementActivationV3Failure):
        standard.validate_standard_api_v1(repository_root=ROOT, receipt_path=path)


def test_standard_output_tamper_and_mode_binding_rejected(api_pair: Path) -> None:
    standard.materialize_standard_api_v1(
        repository_root=ROOT, private_root=api_pair, receipt_name="standard.json"
    )
    overlay = standard.validate_standard_api_v1(
        repository_root=ROOT, receipt_path=api_pair / "standard.json"
    )
    wrong = deepcopy(dict(overlay.binding))
    wrong["measurement_collection_enabled"] = True
    with pytest.raises(publication.PublicationFailure):
        publication._validate_materialization_binding(wrong)
    path = next((overlay.production_fixture_root / "articles").glob("*.html"))
    path.write_bytes(path.read_bytes() + b"<!-- changed -->")
    with pytest.raises(measured.RakutenMeasurementActivationV3Failure):
        standard.validate_standard_api_v1(
            repository_root=ROOT, receipt_path=api_pair / "standard.json"
        )


def test_standard_mode_does_not_read_measurement_inputs_before_signature_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        publication, "validate_publication_link_evidence", lambda *_a, **_k: object()
    )

    def no_measurement(*_a: object, **_k: object) -> None:
        raise AssertionError("measurement receipt read")

    monkeypatch.setattr(
        publication, "validate_measurement_plugin_apply_receipt", no_measurement
    )
    with pytest.raises(publication.PublicationFailure):
        publication.execute(
            "all",
            link_mode="standard-api",
            standard_api_receipt=Path("/private/standard.json"),
        )
    with pytest.raises(publication.PublicationFailure, match="LINK_MODE_INVALID"):
        publication.execute("all", standard_api_receipt=Path("/private/standard.json"))
    with pytest.raises(publication.PublicationFailure, match="LINK_MODE_INVALID"):
        publication.execute(
            "all",
            link_mode="standard-api",
            standard_api_receipt=Path("/private/standard.json"),
            rakuten_activation_dry_run=Path("/private/measured.json"),
        )
    assert publication.parser().parse_args([]).link_mode == "measured-admin"


@pytest.mark.parametrize("mode", ["local", "production"])
def test_standard_rejects_materialization_older_than_fifteen_minutes(
    api_pair: Path, mode: str
) -> None:
    path = api_pair.parent / "v2" / mode / "materialization-receipt.v2.json"
    receipt = json.loads(path.read_bytes())
    receipt["generated_at"] = (datetime.now(UTC) - timedelta(minutes=16)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    path.write_bytes(standard.canonical_json_bytes(receipt))
    with pytest.raises(measured.RakutenMeasurementActivationV3Failure):
        standard.materialize_standard_api_v1(
            repository_root=ROOT, private_root=api_pair, receipt_name="standard.json"
        )


@pytest.mark.parametrize(
    "tamper", ["missing_cta", "different_product_url", "image_bytes"]
)
def test_standard_replays_inputs_even_when_article_receipt_hash_is_rewritten(
    api_pair: Path, tamper: str
) -> None:
    local = api_pair.parent / "v2" / "local"
    receipt_path = local / "materialization-receipt.v2.json"
    receipt = json.loads(receipt_path.read_bytes())
    row = receipt["articles"][0]
    path = local / "articles" / f"{row['production_slug']}.html"
    html = path.read_text()
    anchor = next(measured.CTA_ANCHOR_RE.finditer(html))
    if tamper == "missing_cta":
        html = html[: anchor.start()] + html[anchor.end() :]
    elif tamper == "different_product_url":
        attrs = measured.anchor_attributes(anchor.group(1))
        other = next(
            product.product_id
            for product in load_editorial_portfolio_v2(ROOT).products
            if product.product_id != attrs["data-raos-product-id"]
        )
        original = anchor.group(0)

        replaced = original.replace(
            escape(attrs["href"], quote=True),
            escape(_synthetic_destination_url(other), quote=True),
        )
        assert replaced != original
        html = html[: anchor.start()] + replaced + html[anchor.end() :]
    else:
        media = next((api_pair.parent / "v2" / "product-media").iterdir())
        media.write_bytes(b"different image bytes")
    path.write_text(html)
    row["content_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt_path.write_bytes(standard.canonical_json_bytes(receipt))
    with pytest.raises(measured.RakutenMeasurementActivationV3Failure):
        standard.materialize_standard_api_v1(
            repository_root=ROOT, private_root=api_pair, receipt_name="standard.json"
        )
