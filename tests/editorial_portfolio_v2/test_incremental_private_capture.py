"""Recorded selected captures; source contracts and private provider stores stay separate."""

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from raos.application.editorial import editorial_portfolio_v2 as owner
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
)
from scripts import raos_editorial_portfolio_v2 as cli


@pytest.fixture
def scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "current-source"
    private = tmp_path / "saved-checkout"
    source.mkdir()
    private.mkdir()
    first = owner.ProductBindingV2(
        product_id="PRD-TEST-ONE",
        official_name="Test MODEL-1",
        official_models=("MODEL-1",),
        representative_model="MODEL-1",
        official_jan=None,
        official_url="https://example.com/model-1",
        rakuten_shop_code="shop",
        rakuten_item_code="shop:10000001",
        required_title_tokens=("MODEL-1",),
        product_kind_tokens=("test",),
        forbidden_title_tokens=("accessory",),
    )
    second = replace(first, product_id="PRD-TEST-TWO", official_jan="4901234567894")
    portfolio = owner.EditorialPortfolioV2(
        version="test",
        target_origin="https://example.com",
        theme_version="1.5.1",
        editorial_reviewed_on="2026-09-05",
        articles=(),
        products=(first, second),
    )

    def source_portfolio(root):
        assert root == source
        return portfolio

    def source_hash(root):
        assert root == source
        return "a" * 64

    for module in (owner, cli):
        monkeypatch.setattr(module, "load_editorial_portfolio_v2", source_portfolio)
        monkeypatch.setattr(module, "portfolio_sha256", source_hash)
    monkeypatch.setattr(cli, "ROOT", source)
    return source, private, portfolio


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)


def receipt_for(source: Path, product_ids: tuple[str, ...]) -> dict:
    return {
        "schema": owner.INCREMENTAL_STATUS_SCHEMA,
        "portfolio_sha256": "a" * 64,
        "scope_sha256": owner.incremental_product_evidence_scope_sha256(
            source, product_ids
        ),
        "product_ids": sorted(product_ids),
        "owner_attested": False,
        "publication_authority": False,
        "captured_at": "2026-09-05T00:00:00Z",
        "products": [
            {
                "product_id": product_id,
                "state": "not_found",
                "reason": None,
                "retrieved_at": "2026-09-05T00:00:00Z",
                "item_code": None,
                "response_sha256": "b" * 64,
                "affiliate_response_sha256": None,
                "image_sha256": None,
            }
            for product_id in product_ids
        ],
    }


def test_selected_receipt_replays_private_store_without_legacy_receipt(scope) -> None:
    source, private, portfolio = scope
    selected = (portfolio.products[0].product_id,)
    relative = owner.incremental_product_evidence_status_relative_path(source, selected)
    save(private / relative, receipt_for(source, selected))
    # A conflicting legacy receipt is never substituted for the exact subset.
    save(private / owner.STATUS_RELATIVE_PATH, {"schema": "WRONG"})
    views = owner.product_evidence_views_v2(
        source,
        private_root=private,
        product_ids=selected,
        now=datetime(2026, 9, 5, 1, tzinfo=UTC),
        require_fresh_set=True,
    )
    assert set(views) == set(selected)
    assert views[selected[0]].state == "not_found"
    assert not (source / ".secrets").exists()
    with pytest.raises(owner.EditorialPortfolioV2Failure, match="EVIDENCE_INCOMPLETE"):
        owner.product_evidence_views_v2(
            source,
            private_root=private,
            product_ids=selected,
            now=datetime(2026, 9, 5, 1, tzinfo=UTC),
            require_verified_set=True,
        )


@pytest.mark.parametrize(
    "mutation", ["schema", "scope", "owner", "product", "missing", "expired"]
)
def test_incremental_receipt_rejects_tampering_or_expiry(scope, mutation: str) -> None:
    source, private, portfolio = scope
    selected = (portfolio.products[0].product_id,)
    document = receipt_for(source, selected)
    if mutation == "schema":
        document["schema"] = owner.STATUS_SCHEMA
    elif mutation == "scope":
        document["scope_sha256"] = "0" * 64
    elif mutation == "owner":
        document["owner_attested"] = True
    elif mutation == "product":
        document["products"][0]["product_id"] = portfolio.products[1].product_id
    elif mutation == "missing":
        document["products"] = []
    else:
        document["captured_at"] = "2026-09-01T00:00:00Z"
    save(
        private
        / owner.incremental_product_evidence_status_relative_path(source, selected),
        document,
    )
    with pytest.raises(owner.EditorialPortfolioV2Failure):
        owner.product_evidence_views_v2(
            source,
            private_root=private,
            product_ids=selected,
            now=datetime(2026, 9, 5, 1, tzinfo=UTC),
            require_fresh_set=True,
        )


def test_incremental_path_is_bound_to_product_set_and_source_revision(
    scope, monkeypatch
) -> None:
    source, _, portfolio = scope
    first = (portfolio.products[0].product_id,)
    second = (portfolio.products[1].product_id,)
    path = owner.incremental_product_evidence_status_relative_path(source, first)
    assert path != owner.incremental_product_evidence_status_relative_path(
        source, second
    )
    monkeypatch.setattr(owner, "portfolio_sha256", lambda root: "b" * 64)
    assert path != owner.incremental_product_evidence_status_relative_path(
        source, first
    )


def test_empty_scope_does_not_read_jan_credentials_or_receipts(
    scope, monkeypatch
) -> None:
    source, private, _ = scope

    def forbidden(*args, **kwargs):
        pytest.fail("An informational scope must not access commerce evidence")

    monkeypatch.setattr(owner, "product_jan_evidence_bindings_v1", forbidden)
    monkeypatch.setattr(owner, "_load_status_receipt", forbidden)
    monkeypatch.setattr(cli, "product_jan_evidence_bindings_v1", forbidden)
    monkeypatch.setattr(cli.rakuten_capture, "read_owner_credentials", forbidden)
    assert (
        owner.product_evidence_views_v2(source, private_root=private, product_ids=())
        == {}
    )
    assert cli.capture(product_ids=()) == {
        "verified": 0,
        "not_found": 0,
        "ambiguous": 0,
        "unresolved": 0,
    }
    assert not (source / ".secrets").exists()


@pytest.mark.parametrize(
    "selected", [("PRD-UNKNOWN",), ("PRD-TEST-ONE", "PRD-TEST-ONE")]
)
def test_unknown_or_duplicate_scope_is_rejected_before_credentials(
    scope, selected, monkeypatch
) -> None:
    monkeypatch.setattr(
        cli.rakuten_capture,
        "read_owner_credentials",
        lambda root: pytest.fail("credential read"),
    )
    with pytest.raises(
        owner.EditorialPortfolioV2Failure, match="PRODUCT_SELECTION_INVALID"
    ):
        cli.capture(product_ids=selected)


def test_missing_official_jan_does_not_capture_or_claim_verification(
    scope, monkeypatch
) -> None:
    source, private, portfolio = scope
    selected = (portfolio.products[1].product_id,)
    monkeypatch.setattr(cli, "_capture_private_root", lambda root: private)
    monkeypatch.setattr(
        cli.rakuten_capture, "require_clean_capture_environment", lambda: None
    )
    monkeypatch.setattr(
        cli.rakuten_capture,
        "read_owner_credentials",
        lambda root: pytest.fail("credential read"),
    )
    assert cli.capture(owner_checkout=private, product_ids=selected) == {
        "verified": 0,
        "not_found": 0,
        "ambiguous": 0,
        "unresolved": 1,
    }
    relative = owner.incremental_product_evidence_status_relative_path(source, selected)
    document = json.loads((private / relative).read_text())
    assert document["products"][0]["reason"] == "OFFICIAL_JAN_EVIDENCE_MISSING"
    assert document["owner_attested"] is False
    assert document["publication_authority"] is False
    assert not (private / owner.STATUS_RELATIVE_PATH).exists()
    assert not (source / ".secrets").exists()
    with pytest.raises(owner.EditorialPortfolioV2Failure, match="EVIDENCE_INCOMPLETE"):
        owner.product_evidence_views_v2(
            source,
            private_root=private,
            product_ids=selected,
            require_verified_set=True,
        )


def test_capture_uses_private_root_but_current_source_contract(
    scope, monkeypatch
) -> None:
    source, private, portfolio = scope
    selected = (portfolio.products[0].product_id,)
    calls = []
    stored = {}
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(cli, "_capture_private_root", lambda root: private)
    monkeypatch.setattr(
        cli.rakuten_capture, "require_clean_capture_environment", lambda: None
    )
    monkeypatch.setattr(
        cli.rakuten_capture,
        "read_owner_credentials",
        lambda root: calls.append(("credentials", root)),
    )
    monkeypatch.setattr(
        cli.rakuten_capture,
        "SystemRakutenHttpsConnectionFactory",
        lambda root: calls.append(("factory", root)),
    )

    def read(root, *, product_id):
        calls.append(("evidence", root))
        if not stored:
            raise EditorialPilotFailure(EditorialPilotFailureCode.RESOURCE_NOT_READY)
        return stored[product_id]

    def capture(root, target, credentials, **kwargs):
        calls.append(("capture", root))
        assert target.variants == (portfolio.products[0].representative_model,)
        evidence = SimpleNamespace(
            product_id=target.product_id,
            item_code=target.fixed_item_code,
            retrieved_at=timestamp,
            response_sha256="b" * 64,
            affiliate_response_sha256="c" * 64,
            image_sha256="d" * 64,
        )
        stored[target.product_id] = evidence
        return evidence

    monkeypatch.setattr(cli, "read_rakuten_product_evidence", read)
    monkeypatch.setattr(owner, "read_rakuten_product_evidence", read)
    monkeypatch.setattr(cli.rakuten_capture, "_capture_product", capture)
    monkeypatch.setattr(
        owner, "_validate_rakuten_identity", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        owner,
        "_verified_product_image_extension",
        lambda root, **kwargs: calls.append(("image", root)) or "jpg",
    )
    assert cli.capture(owner_checkout=private, product_ids=selected)["verified"] == 1
    assert all(root == private for _, root in calls)
    assert {kind for kind, _ in calls} == {
        "credentials",
        "factory",
        "evidence",
        "capture",
        "image",
    }
    assert not (source / ".secrets").exists()
    assert not (private / owner.STATUS_RELATIVE_PATH).exists()
    receipt_path = private / owner.incremental_product_evidence_status_relative_path(
        source, selected
    )
    original_receipt = receipt_path.read_text()
    for field in ("response_sha256", "affiliate_response_sha256", "image_sha256"):
        document = json.loads(original_receipt)
        document["products"][0][field] = "e" * 64
        save(receipt_path, document)
        with pytest.raises(owner.EditorialPortfolioV2Failure, match="EVIDENCE_INVALID"):
            owner.product_evidence_views_v2(
                source,
                private_root=private,
                product_ids=selected,
                require_verified_set=True,
            )


def test_capture_parser_preserves_full_default_and_requires_explicit_selection() -> (
    None
):
    legacy = cli.parser().parse_args(["capture"])
    assert legacy.owner_checkout is None and legacy.product_ids is None
    selected = cli.parser().parse_args(
        [
            "capture",
            "--owner-checkout",
            "/home/minami/rakuten",
            "--product-ids",
            "PRD-TEST-ONE",
        ]
    )
    assert selected.product_ids == ["PRD-TEST-ONE"]
    assert selected.owner_checkout == Path("/home/minami/rakuten")
    with pytest.raises(
        owner.EditorialPortfolioV2Failure, match="OWNER_CHECKOUT_INVALID"
    ):
        cli._capture_private_root(Path("/tmp/not-the-owner-checkout"))


def test_selected_replay_rejects_symlinked_private_tree(scope, tmp_path: Path) -> None:
    source, private, portfolio = scope
    redirected = tmp_path / "redirected-private"
    redirected.mkdir()
    (private / ".secrets").symlink_to(redirected, target_is_directory=True)
    with pytest.raises(owner.EditorialPortfolioV2Failure, match="PRIVATE_ROOT_INVALID"):
        owner.product_evidence_views_v2(
            source,
            private_root=private,
            product_ids=(portfolio.products[0].product_id,),
        )


def test_selected_official_jan_replays_private_snapshot_and_retains_strict_owner_binding(
    scope,
) -> None:
    source, private, portfolio = scope
    product = portfolio.products[1]
    selected = (product.product_id,)
    snapshot = b"MODEL-1 official JAN 4901234567894\n"
    snapshot_path = (
        private
        / owner.JAN_EVIDENCE_SNAPSHOT_RELATIVE_ROOT
        / f"{product.product_id}.snapshot.txt"
    )
    snapshot_path.parent.mkdir(parents=True, mode=0o700)
    snapshot_path.write_bytes(snapshot)
    snapshot_path.chmod(0o600)
    verified_at = "2026-09-05T00:00:00Z"
    receipt = {
        "schema": owner.JAN_EVIDENCE_SCHEMA,
        "portfolio_sha256": "a" * 64,
        "owner_attested": True,
        "verified_at": verified_at,
        "products": [
            {
                "product_id": product.product_id,
                "representative_model": product.representative_model,
                "official_jan": product.official_jan,
                "official_url": product.official_url,
                "source_locator": "Official JAN row",
                "source_snapshot_file": snapshot_path.name,
                "source_snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
                "verified_at": verified_at,
            }
        ],
    }
    receipt_path = private / owner.JAN_EVIDENCE_RELATIVE_PATH
    save(receipt_path, receipt)
    arguments = {
        "portfolio": portfolio,
        "private_root": private,
        "product_ids": selected,
        "now": datetime(2026, 9, 5, 1, tzinfo=UTC),
    }
    assert set(owner.product_jan_evidence_bindings_v1(source, **arguments)) == set(
        selected
    )
    assert not (source / ".secrets").exists()
    receipt["owner_attested"] = False
    save(receipt_path, receipt)
    with pytest.raises(owner.EditorialPortfolioV2Failure, match="JAN_EVIDENCE_INVALID"):
        owner.product_jan_evidence_bindings_v1(source, **arguments)
    receipt["owner_attested"] = True
    receipt["products"] = []
    save(receipt_path, receipt)
    assert owner.product_jan_evidence_bindings_v1(source, **arguments) == {}
    with pytest.raises(
        owner.EditorialPortfolioV2Failure, match="JAN_EVIDENCE_INCOMPLETE"
    ):
        owner.product_jan_evidence_bindings_v1(
            source,
            portfolio=portfolio,
            private_root=private,
            now=arguments["now"],
        )
