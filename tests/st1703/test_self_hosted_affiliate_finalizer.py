"""Adversarial local-only tests for the ST-1703 affiliate finalizer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import sys
from urllib.parse import urlencode

import pytest

from raos.adapters.rakuten_owner_local import (
    OwnerPrivateRakutenOwnerLocalCredentialReader,
    OwnerPrivateRakutenOwnerLocalRequestReader,
)
from raos.application.editorial.self_hosted_minimum_start import (
    AFFILIATE_CTA_LABEL,
    CONTENT_PACKET_RELATIVE_PATH,
    RAKUTEN_CREDIT_SNIPPET,
    affiliate_cta_html,
    load_first_article_candidate_with_affiliate_status,
)
from raos.domain.catalog.rakuten_owner_local import (
    RakutenOwnerLocalApi,
    RakutenOwnerLocalOutcome,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalResultEnvelope,
    normalized_record,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressFailure,
    SelfHostedWordPressOperation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "st1703_affiliate_finalizer_for_test",
    SCRIPTS_ROOT / "finalize_st1703_affiliate_links.py",
)
assert SPEC is not None and SPEC.loader is not None
finalizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = finalizer
SPEC.loader.exec_module(finalizer)

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)
SLOTS = (
    ("ace-cresta-06316", "ACE クレスタ 06316", "06316"),
    (
        "ace-difference-05721",
        "ace.TOKYO LABEL ディフェレンス 05721",
        "05721",
    ),
    (
        "proteca-maxpass4-01471",
        "PROTECA マックスパス4 01471",
        "01471",
    ),
)


def _pending_slot_html(slot_id: str) -> str:
    return (
        f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} BEGIN -->"
        f'<div class="raos-affiliate-slot" data-raos-affiliate-slot="{slot_id}">'
        "<p>公式楽天アフィリエイトリンク未設定</p></div>"
        f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} END -->"
    )


def _pending_repository(tmp_path: Path) -> Path:
    content_path = tmp_path / CONTENT_PACKET_RELATIVE_PATH
    content_path.parent.mkdir(parents=True)
    packet = json.loads(
        (REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    article = packet["article"]
    content = article["content_html"]
    for slot in article["affiliate_slots"]:
        slot_id = slot["slot_id"]
        destination = slot["destination_url"]
        content = content.replace(
            affiliate_cta_html(slot_id, destination),
            _pending_slot_html(slot_id),
        )
        product_name = slot["product_name"]
        slot.clear()
        slot.update(
            {
                "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
                "product_name": product_name,
                "required_rel": "sponsored nofollow",
                "slot_id": slot_id,
                "status": "PENDING_OFFICIAL_RAKUTEN_LINK",
            }
        )
    article["content_html"] = content.replace(f"{RAKUTEN_CREDIT_SNIPPET}\n", "")
    content_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _candidate, status = load_first_article_candidate_with_affiliate_status(
        tmp_path,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    assert status == "PENDING"
    return content_path


def _request_payload(code: str) -> dict[str, object]:
    return {
        "genre_id": None,
        "hits": 30,
        "item_code": None,
        "keyword": code,
        "page": 1,
        "schema_version": 1,
        "shop_code": None,
        "sort": "standard",
    }


def _request_files(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str]]:
    request_root = tmp_path / "owner-private-requests"
    request_root.mkdir(mode=0o700)
    paths: dict[str, Path] = {}
    fingerprints: dict[str, str] = {}
    reader = OwnerPrivateRakutenOwnerLocalRequestReader()
    for slot_id, _product_name, code in SLOTS:
        path = request_root / f"keyword-{slot_id}.json"
        path.write_text(
            json.dumps(_request_payload(code), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        paths[slot_id] = path
        fingerprints[slot_id] = reader.read(
            path, RakutenOwnerLocalApi.ITEM_SEARCH
        ).fingerprint
    return paths, fingerprints


def _affiliate_url(
    code: str,
    *,
    token: str = "synthetic-token",
    mobile_target: str | None = None,
) -> str:
    query = urlencode(
        {
            "pc": f"https://item.rakuten.co.jp/ace-store/{code}/",
            "m": (
                f"http://m.rakuten.co.jp/ace-store/i/100{code}/"
                if mobile_target is None
                else mobile_target
            ),
            "rafcid": token,
        }
    )
    return f"https://hb.afl.rakuten.co.jp/hgc/synthetic-path/?{query}"


def _result_object(
    *,
    fingerprint: str,
    code: str,
    run_index: int,
    item_mutation: tuple[str, object] | None = None,
    alternate_item_url: str | None = None,
    destination_url: str | None = None,
    finished_at: datetime = NOW,
) -> dict[str, object]:
    destination = _affiliate_url(code) if destination_url is None else destination_url
    fields: dict[str, object] = {
        "affiliateUrl": destination,
        "availability": 1,
        "genreId": 0,
        "itemCode": f"ace-store:synthetic-{run_index}",
        "itemName": f"synthetic model {code}",
        "itemPrice": 1,
        "itemUrl": destination if alternate_item_url is None else alternate_item_url,
        "mediumImageUrls": [],
        "shopCode": "ace-store",
        "shopName": "synthetic shop",
        "smallImageUrls": [],
    }
    if item_mutation is not None:
        fields[item_mutation[0]] = item_mutation[1]
    record = normalized_record(RakutenOwnerLocalApi.ITEM_SEARCH, fields)
    response_sha256 = f"{run_index + 100:064x}"[-64:]
    provider = RakutenOwnerLocalProviderResult(
        api=RakutenOwnerLocalApi.ITEM_SEARCH,
        request_fingerprint=fingerprint,
        http_status=200,
        body_byte_count=1024,
        response_sha256=response_sha256,
        count=1,
        page=1,
        first=1,
        last=1,
        hits=30,
        page_count=1,
        records=(record,),
    )
    started = finished_at - timedelta(seconds=1)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ-") + f"{run_index + 1:032x}"[-32:]
    return RakutenOwnerLocalResultEnvelope(
        run_id=run_id,
        started_at=started,
        finished_at=finished_at,
        api=RakutenOwnerLocalApi.ITEM_SEARCH,
        request_fingerprint=fingerprint,
        outcome=RakutenOwnerLocalOutcome.SUCCESS,
        provider_result=provider,
        failure=None,
    ).as_result_object()


def _result_store(tmp_path: Path) -> Path:
    store = tmp_path / "owner-result-store"
    store.mkdir(mode=0o700)
    store.chmod(0o700)
    return store


def _write_result(store: Path, value: dict[str, object]) -> Path:
    path = store / f"{value['run_id']}.json"
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _complete_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Path], dict[str, str]]:
    _pending_repository(tmp_path)
    paths, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
            ),
        )
    return tmp_path, store, paths, fingerprints


def _assert_final_content(repository_root: Path) -> dict[str, object]:
    candidate, status = load_first_article_candidate_with_affiliate_status(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    assert status == "FINAL"
    assert candidate.content_html.count(AFFILIATE_CTA_LABEL) == 3
    assert candidate.content_html.count('rel="sponsored nofollow"') == 3
    assert candidate.content_html.count(RAKUTEN_CREDIT_SNIPPET) == 1
    return json.loads(
        (repository_root / CONTENT_PACKET_RELATIVE_PATH).read_text(encoding="utf-8")
    )


def test_finalizer_is_local_all_or_nothing_and_redacts_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, store, requests, _fingerprints = _complete_inputs(tmp_path)
    monkeypatch.setattr(
        OwnerPrivateRakutenOwnerLocalCredentialReader,
        "read",
        lambda _reader: (_ for _ in ()).throw(AssertionError("credential read")),
    )
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    argv = [
        "--ace-cresta-06316-request",
        str(requests["ace-cresta-06316"]),
        "--ace-difference-05721-request",
        str(requests["ace-difference-05721"]),
        "--proteca-maxpass4-01471-request",
        str(requests["proteca-maxpass4-01471"]),
    ]
    assert (
        finalizer.main(
            argv,
            repository_root=root,
            result_store=store,
            now=NOW,
        )
        == 0
    )
    output = capsys.readouterr()
    packet = _assert_final_content(root)
    assert output.err == ""
    assert json.loads(output.out)["provider_urls_printed"] == 0
    for slot in packet["article"]["affiliate_slots"]:
        assert slot["destination_url"] not in output.out
        assert not any("result_store" in key for key in slot["evidence"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shopCode", "other-shop"),
        ("itemName", "unrelated model"),
        ("itemCode", "other-shop:synthetic"),
    ],
)
def test_finalizer_rejects_item_shop_or_name_mismatch(
    tmp_path: Path, field: str, value: str
) -> None:
    _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        mutation = (field, value) if index == 0 else None
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
                item_mutation=mutation,
            ),
        )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_RESULT_IDENTITY_MISMATCH"


def test_finalizer_rejects_provider_url_inequality(tmp_path: Path) -> None:
    _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        alternate = _affiliate_url(code, token="different") if index == 0 else None
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
                alternate_item_url=alternate,
            ),
        )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_DESTINATION_INVALID"


def test_finalizer_rejects_raos_destination_hidden_in_mobile_redirect(
    tmp_path: Path,
) -> None:
    _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        destination = None
        if index == 0:
            destination = _affiliate_url(
                code,
                mobile_target="https://kurashinoshirube.com/go/product",
            )
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
                destination_url=destination,
            ),
        )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_DESTINATION_INVALID"


@pytest.mark.parametrize("mode", ["missing", "duplicate", "fingerprint"])
def test_finalizer_rejects_partial_duplicate_or_fingerprint_mismatch(
    tmp_path: Path, mode: str
) -> None:
    _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        if mode == "missing" and index == 2:
            continue
        fingerprint = fingerprints[slot_id]
        if mode == "fingerprint" and index == 2:
            fingerprint = "f" * 64
        result = _result_object(
            fingerprint=fingerprint,
            code=code,
            run_index=index,
        )
        _write_result(store, result)
        if mode == "duplicate" and index == 0:
            duplicate = _result_object(
                fingerprint=fingerprint,
                code=code,
                run_index=9,
            )
            _write_result(store, duplicate)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_RESULT_MISSING_OR_DUPLICATE"


def test_finalizer_rejects_stale_matching_result(tmp_path: Path) -> None:
    _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        finished = NOW - timedelta(days=2) if index == 0 else NOW
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
                finished_at=finished,
            ),
        )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_RESULT_STALE"


def test_finalizer_rejects_manual_link_in_pending_packet(tmp_path: Path) -> None:
    content_path = _pending_repository(tmp_path)
    requests, fingerprints = _request_files(tmp_path)
    store = _result_store(tmp_path)
    for index, (slot_id, _product_name, code) in enumerate(SLOTS):
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints[slot_id],
                code=code,
                run_index=index,
            ),
        )
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    packet["article"]["content_html"] = packet["article"]["content_html"].replace(
        "<p>公式楽天アフィリエイトリンク未設定</p>",
        '<p><a href="https://kurashinoshirube.com/go/product">商品</a></p>',
        1,
    )
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=tmp_path,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://hb.afl.rakuten.co.jp/hgc/synthetic/",
        "https://kurashinoshirube.com/go/product",
        "https://foreign.example.invalid/product",
    ],
)
def test_content_rejects_non_https_non_rakuten_or_raos_redirect(
    tmp_path: Path, bad_url: str
) -> None:
    content_path = tmp_path / CONTENT_PACKET_RELATIVE_PATH
    content_path.parent.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH, content_path)
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    slot = packet["article"]["affiliate_slots"][0]
    old_url = slot["destination_url"]
    old_html = affiliate_cta_html(slot["slot_id"], old_url)
    bad_html = (
        f"<!-- RAOS-AFFILIATE-SLOT:{slot['slot_id']} BEGIN -->"
        f'<div class="raos-affiliate-slot" data-raos-affiliate-slot="{slot["slot_id"]}">'
        f'<p><a class="raos-affiliate-cta" href="{escape(bad_url, quote=True)}" '
        f'rel="sponsored nofollow">{AFFILIATE_CTA_LABEL}</a></p></div>'
        f"<!-- RAOS-AFFILIATE-SLOT:{slot['slot_id']} END -->"
    )
    slot["destination_url"] = bad_url
    packet["article"]["content_html"] = packet["article"]["content_html"].replace(
        old_html, bad_html
    )
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate_with_affiliate_status(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


@pytest.mark.parametrize("mutation", ["rel", "cta", "credit", "url"])
def test_content_rejects_rel_cta_credit_or_url_mutation(
    tmp_path: Path, mutation: str
) -> None:
    content_path = tmp_path / CONTENT_PACKET_RELATIVE_PATH
    content_path.parent.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH, content_path)
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    article = packet["article"]
    first = article["affiliate_slots"][0]
    if mutation == "rel":
        first["required_rel"] = "nofollow"
        article["content_html"] = article["content_html"].replace(
            'rel="sponsored nofollow"', 'rel="nofollow"', 1
        )
    elif mutation == "cta":
        article["content_html"] = article["content_html"].replace(
            AFFILIATE_CTA_LABEL, "今すぐ購入", 1
        )
    elif mutation == "credit":
        article["content_html"] = article["content_html"].replace(
            RAKUTEN_CREDIT_SNIPPET, ""
        )
    else:
        first["destination_url"] = _affiliate_url("06316", token="mutated")
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate_with_affiliate_status(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


def test_content_rejects_mixed_pending_and_final_states(tmp_path: Path) -> None:
    content_path = tmp_path / CONTENT_PACKET_RELATIVE_PATH
    content_path.parent.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH, content_path)
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    article = packet["article"]
    slot = article["affiliate_slots"][0]
    article["content_html"] = article["content_html"].replace(
        affiliate_cta_html(slot["slot_id"], slot["destination_url"]),
        _pending_slot_html(slot["slot_id"]),
    )
    product_name = slot["product_name"]
    slot.clear()
    slot.update(
        {
            "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
            "product_name": product_name,
            "required_rel": "sponsored nofollow",
            "slot_id": "ace-cresta-06316",
            "status": "PENDING_OFFICIAL_RAKUTEN_LINK",
        }
    )
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate_with_affiliate_status(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


@pytest.mark.parametrize("unsafe", ["request-mode", "result-mode", "unknown-file"])
def test_finalizer_rejects_malformed_or_non_private_files(
    tmp_path: Path, unsafe: str
) -> None:
    root, store, requests, _fingerprints = _complete_inputs(tmp_path)
    if unsafe == "request-mode":
        requests["ace-cresta-06316"].chmod(0o644)
    elif unsafe == "result-mode":
        next(store.iterdir()).chmod(0o644)
    else:
        unknown = store / "unknown-material"
        unknown.write_text("{}", encoding="utf-8")
        unknown.chmod(0o600)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.finalize(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code in {
        "AFFILIATE_REQUEST_INVALID",
        "AFFILIATE_RESULT_STORE_INVALID",
    }
