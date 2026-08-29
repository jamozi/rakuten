"""Adversarial local-only tests for the ST-1703 affiliate verifier."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlencode

import pytest

import raos.application.editorial.self_hosted_minimum_start as minimum_start
from raos.adapters.rakuten_owner_local import (
    OwnerPrivateRakutenOwnerLocalCredentialReader,
    OwnerPrivateRakutenOwnerLocalRequestReader,
)
from raos.application.editorial.self_hosted_minimum_start import (
    AFFILIATE_CTA_LABEL,
    AFFILIATE_FINAL_DISCLOSURE_HTML,
    AFFILIATE_PENDING_DISCLOSURE_HTML,
    CONTENT_PACKET_RELATIVE_PATH,
    RAKUTEN_CREDIT_SNIPPET,
    affiliate_destination_attestation_sha256,
    affiliate_cta_html,
    load_first_article_candidate_with_affiliate_status,
)
from raos.domain.catalog.rakuten_owner_local import (
    RakutenOwnerLocalApi,
    RakutenOwnerLocalOutcome,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
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
MOBILE_ITEM_IDS = {
    "06316": "10007275",
    "05721": "10009372",
    "01471": "10009099",
}


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
    shutil.copyfile(
        REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH,
        content_path,
    )
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    assert all(
        slot["status"] == "PENDING_OFFICIAL_RAKUTEN_LINK"
        and "destination_url" not in slot
        and "evidence" not in slot
        for slot in packet["article"]["affiliate_slots"]
    )
    assert "hb.afl.rakuten.co.jp" not in content_path.read_text(encoding="utf-8")
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
                f"http://m.rakuten.co.jp/ace-store/i/{MOBILE_ITEM_IDS[code]}/"
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
        "itemCode": f"ace-store:{MOBILE_ITEM_IDS[code]}",
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


def _result_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _write_result(store: Path, value: dict[str, object]) -> Path:
    path = store / f"{value['run_id']}.json"
    path.write_bytes(_result_bytes(value))
    path.chmod(0o600)
    return path


def _validated_fixture_result(
    *,
    fingerprint: str,
    code: str,
    run_index: int = 0,
    item_mutation: tuple[str, object] | None = None,
    alternate_item_url: str | None = None,
    destination_url: str | None = None,
    finished_at: datetime = NOW,
) -> finalizer._ValidatedResult:
    value = _result_object(
        fingerprint=fingerprint,
        code=code,
        run_index=run_index,
        item_mutation=item_mutation,
        alternate_item_url=alternate_item_url,
        destination_url=destination_url,
        finished_at=finished_at,
    )
    return finalizer._validated_result(
        _result_bytes(value),
        file_name=f"{value['run_id']}.json",
    )


def _result_path_for_fingerprint(store: Path, fingerprint: str) -> Path:
    matches = []
    for path in sorted(store.iterdir()):
        result = finalizer._validated_result(path.read_bytes(), file_name=path.name)
        if result.request_fingerprint == fingerprint:
            matches.append(path)
    assert len(matches) == 1
    return matches[0]


def _complete_inputs(
    tmp_path: Path,
    *,
    finished_at: datetime = NOW,
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
                finished_at=finished_at,
            ),
        )
    return tmp_path, store, paths, fingerprints


def _complete_final_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    review_attestations: bool = True,
    finished_at: datetime = NOW,
) -> tuple[Path, Path, dict[str, Path], dict[str, str]]:
    root, store, requests, fingerprints = _complete_inputs(
        tmp_path,
        finished_at=finished_at,
    )
    results_by_fingerprint: dict[str, finalizer._ValidatedResult] = {}
    for result_path in sorted(store.iterdir()):
        result = finalizer._validated_result(
            result_path.read_bytes(),
            file_name=result_path.name,
        )
        results_by_fingerprint[result.request_fingerprint] = result
    finalized = tuple(
        finalizer._verified_slot_from_result(
            definition,
            results_by_fingerprint[fingerprints[definition.slot_id]],
        )
        for definition in finalizer._SLOTS
    )
    if review_attestations:
        monkeypatch.setattr(
            minimum_start,
            "_EXPECTED_AFFILIATE_ATTESTATIONS",
            {
                slot.definition.slot_id: slot.evidence["destination_attestation_sha256"]
                for slot in finalized
            },
        )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    article = packet["article"]
    content = article["content_html"]
    for index, slot in enumerate(finalized):
        content = content.replace(
            _pending_slot_html(slot.definition.slot_id),
            affiliate_cta_html(slot.definition.slot_id, slot.destination_url),
        )
        article["affiliate_slots"][index] = {
            "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
            "destination_url": slot.destination_url,
            "evidence": slot.evidence,
            "product_name": slot.definition.product_name,
            "required_rel": "sponsored nofollow",
            "slot_id": slot.definition.slot_id,
            "status": "FINAL_OFFICIAL_RAKUTEN_LINK",
        }
    article["content_html"] = content.replace(
        '<p class="raos-freshness">',
        f'{RAKUTEN_CREDIT_SNIPPET}\n<p class="raos-freshness">',
        1,
    )
    article["content_html"] = article["content_html"].replace(
        AFFILIATE_PENDING_DISCLOSURE_HTML,
        AFFILIATE_FINAL_DISCLOSURE_HTML,
    )
    content_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root, store, requests, fingerprints


def _assert_final_content(repository_root: Path) -> dict[str, object]:
    candidate, status = load_first_article_candidate_with_affiliate_status(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    assert status == "FINAL"
    assert candidate.content_html.count(AFFILIATE_CTA_LABEL) == 3
    packet = json.loads(
        (repository_root / CONTENT_PACKET_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    article = packet["article"]
    assert article["content_html"].count(AFFILIATE_CTA_LABEL) == 3
    assert article["content_html"].count('rel="sponsored nofollow"') == 3
    assert article["content_html"].count(RAKUTEN_CREDIT_SNIPPET) == 1
    for slot in article["affiliate_slots"]:
        evidence = slot["evidence"]
        provider_evidence = {
            key: value
            for key, value in evidence.items()
            if key != "destination_attestation_sha256"
        }
        assert evidence["destination_attestation_sha256"] == (
            affiliate_destination_attestation_sha256(
                slot["slot_id"],
                slot["destination_url"],
                provider_evidence,
            )
        )
    return packet


def test_direct_execution_is_disabled_before_private_read(tmp_path: Path) -> None:
    script = SCRIPTS_ROOT / "finalize_st1703_affiliate_links.py"
    source = script.read_text(encoding="utf-8")
    assert source.index('if __name__ == "__main__":') < source.index(
        "REPOSITORY_ROOT ="
    )
    assert source.index('if __name__ == "__main__":') < source.index(
        "from dataclasses import dataclass"
    )
    assert "def _parser(" not in source
    assert "def main(" not in source

    trace = tmp_path / "direct-execution.trace"
    arguments = [str(script)]
    for slot_id, flag in (
        ("ace-cresta-06316", "--ace-cresta-06316-request"),
        ("ace-difference-05721", "--ace-difference-05721-request"),
        ("proteca-maxpass4-01471", "--proteca-maxpass4-01471-request"),
    ):
        arguments.extend((flag, str(finalizer.OWNER_REQUEST_PATHS[slot_id])))
    result = subprocess.run(
        [
            "/usr/bin/strace",
            "-f",
            "-e",
            "trace=openat",
            "-o",
            str(trace),
            sys.executable,
            "-B",
            "-I",
            "-S",
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "external_writes": 0,
        "reason_code": "AFFILIATE_DIRECT_EXECUTION_DISABLED",
        "status": "BLOCKED",
    }
    assert b"AFFILIATE_LINKS_VERIFIED" not in result.stdout
    trace_text = trace.read_text(encoding="utf-8")
    assert ".secrets/rakuten-owner-local" not in trace_text
    assert not any(
        slot_id in trace_text
        for slot_id, _flag in (
            ("ace-cresta-06316", "--ace-cresta-06316-request"),
            ("ace-difference-05721", "--ace-difference-05721-request"),
            ("proteca-maxpass4-01471", "--proteca-maxpass4-01471-request"),
        )
    )


def test_normal_direct_execution_cannot_load_shadow_module_or_private_files(
    tmp_path: Path,
) -> None:
    disposable_scripts = tmp_path / "scripts"
    disposable_scripts.mkdir()
    script = disposable_scripts / "finalize_st1703_affiliate_links.py"
    shutil.copyfile(SCRIPTS_ROOT / script.name, script)
    marker = tmp_path / "shadow-module-executed"
    (disposable_scripts / "dataclasses.py").write_text(
        f"open({str(marker)!r}, 'wb').write(b'shadowed')\n",
        encoding="utf-8",
    )
    trace = tmp_path / "normal-direct-execution.trace"
    arguments = [str(script)]
    for slot_id, flag in (
        ("ace-cresta-06316", "--ace-cresta-06316-request"),
        ("ace-difference-05721", "--ace-difference-05721-request"),
        ("proteca-maxpass4-01471", "--proteca-maxpass4-01471-request"),
    ):
        arguments.extend((flag, str(finalizer.OWNER_REQUEST_PATHS[slot_id])))
    result = subprocess.run(
        [
            "/usr/bin/strace",
            "-f",
            "-e",
            "trace=openat",
            "-o",
            str(trace),
            sys.executable,
            *arguments,
        ],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "external_writes": 0,
        "reason_code": "AFFILIATE_DIRECT_EXECUTION_DISABLED",
        "status": "BLOCKED",
    }
    assert not marker.exists()
    trace_text = trace.read_text(encoding="utf-8")
    assert str(disposable_scripts / "dataclasses.py") not in trace_text
    assert ".secrets/rakuten-owner-local" not in trace_text


def test_finalizer_is_local_all_or_nothing_and_redacts_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(tmp_path, monkeypatch)
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    content_before = content_path.read_bytes()
    identity_before = content_path.stat()
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
    for mutation_name in ("fchmod", "mkdir", "replace", "unlink", "write"):
        monkeypatch.setattr(
            finalizer.os,
            mutation_name,
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("external write")
            ),
        )
    receipt = finalizer.verify(
        repository_root=root,
        result_store=store,
        request_paths=requests,
        now=NOW,
    )
    output = capsys.readouterr()
    packet = _assert_final_content(root)
    assert output.err == ""
    assert receipt["status"] == "AFFILIATE_LINKS_VERIFIED"
    assert receipt["external_writes"] == 0
    assert receipt["provider_urls_printed"] == 0
    assert content_path.read_bytes() == content_before
    identity_after = content_path.stat()
    assert (identity_after.st_dev, identity_after.st_ino) == (
        identity_before.st_dev,
        identity_before.st_ino,
    )
    for slot in packet["article"]["affiliate_slots"]:
        assert slot["destination_url"] not in output.out
        assert not any("result_store" in key for key in slot["evidence"])


def test_verifier_decodes_descriptor_snapshot_without_reopening_request_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
    )
    target = requests["ace-cresta-06316"]
    original_target = target.read_bytes()
    original_decode = finalizer._decode_closed_request_snapshot
    decoded_fingerprints: list[str] = []

    def swap_restore_while_decoding(
        raw: bytes,
        slot: finalizer._SlotDefinition,
    ) -> RakutenOwnerLocalRequest:
        if not decoded_fingerprints:
            target.write_text(
                json.dumps(_request_payload("99999"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            target.chmod(0o600)
            try:
                request = original_decode(raw, slot)
            finally:
                target.write_bytes(original_target)
                target.chmod(0o600)
        else:
            request = original_decode(raw, slot)
        decoded_fingerprints.append(request.fingerprint)
        return request

    monkeypatch.setattr(
        finalizer,
        "_decode_closed_request_snapshot",
        swap_restore_while_decoding,
    )
    monkeypatch.setattr(
        OwnerPrivateRakutenOwnerLocalRequestReader,
        "read",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("request pathname reopened")
        ),
    )

    receipt = finalizer.verify(
        repository_root=root,
        result_store=store,
        request_paths=requests,
        now=NOW,
    )
    assert receipt["status"] == "AFFILIATE_LINKS_VERIFIED"
    assert decoded_fingerprints == [
        fingerprints[slot_id] for slot_id, _product_name, _code in SLOTS
    ]


@pytest.mark.parametrize(("slot_id", "_product_name", "model_code"), SLOTS)
def test_closed_request_snapshot_decoder_matches_owner_local_reader(
    tmp_path: Path,
    slot_id: str,
    _product_name: str,
    model_code: str,
) -> None:
    slot = next(
        definition for definition in finalizer._SLOTS if definition.slot_id == slot_id
    )
    raw = (json.dumps(_request_payload(model_code), sort_keys=True) + "\n").encode()
    path = tmp_path / f"keyword-{slot_id}.json"
    path.write_bytes(raw)
    path.chmod(0o600)

    expected = OwnerPrivateRakutenOwnerLocalRequestReader().read(
        path,
        RakutenOwnerLocalApi.ITEM_SEARCH,
    )
    actual = finalizer._decode_closed_request_snapshot(raw, slot)

    assert actual.fingerprint == expected.fingerprint
    assert actual.canonical_parameters == expected.canonical_parameters


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", True),
        ("keyword", "unreviewed-model"),
        ("shop_code", "ace-store"),
        ("item_code", "ace-store:unreviewed"),
        ("genre_id", 0),
        ("hits", 29),
        ("hits", True),
        ("page", 2),
        ("sort", "+itemPrice"),
    ],
)
def test_closed_request_snapshot_decoder_rejects_nonexact_fields(
    field: str,
    replacement: object,
) -> None:
    slot = finalizer._SLOTS[0]
    payload = _request_payload(slot.model_code)
    payload[field] = replacement
    raw = json.dumps(payload, sort_keys=True).encode()

    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._decode_closed_request_snapshot(raw, slot)
    assert failure.value.code == "AFFILIATE_REQUEST_INVALID"


@pytest.mark.parametrize(
    "case",
    ["duplicate", "missing", "extra", "non_object", "invalid_utf8", "empty"],
)
def test_closed_request_snapshot_decoder_rejects_malformed_shape(case: str) -> None:
    slot = finalizer._SLOTS[0]
    payload = _request_payload(slot.model_code)
    if case == "duplicate":
        raw = b'{"keyword":"06316","keyword":"06316"}'
    elif case == "missing":
        payload.pop("sort")
        raw = json.dumps(payload, sort_keys=True).encode()
    elif case == "extra":
        payload["unexpected"] = None
        raw = json.dumps(payload, sort_keys=True).encode()
    elif case == "non_object":
        raw = b"[]"
    elif case == "invalid_utf8":
        raw = b"\xff"
    else:
        raw = b""

    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._decode_closed_request_snapshot(raw, slot)
    assert failure.value.code == "AFFILIATE_REQUEST_INVALID"


def test_finalizer_rejects_unreviewed_attestation_before_write_or_success_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
        review_attestations=False,
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    pending = content_path.read_bytes()
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    output = capsys.readouterr()
    assert output.err == ""
    assert output.out == ""
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"
    assert content_path.read_bytes() == pending
    assert not content_path.with_name(
        f".{content_path.name}.affiliate-finalizing"
    ).exists()


def test_verifier_rejects_pending_packet_without_write_or_success_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, store, requests, _fingerprints = _complete_inputs(tmp_path)
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    pending = content_path.read_bytes()
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    output = capsys.readouterr()
    assert output.err == ""
    assert output.out == ""
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"
    assert content_path.read_bytes() == pending


def test_verifier_rejects_runtime_bound_packet_drift_before_private_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_inputs(tmp_path)
    monkeypatch.setattr(
        finalizer,
        "_request_fingerprints",
        lambda paths: (_ for _ in ()).throw(
            AssertionError(f"private request read reached: {len(paths)}")
        ),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
            expected_content_packet_bytes=b"different-runtime-bound-packet",
        )
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"


def test_verifier_rejects_tampered_packet_evidence_before_private_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    packet["article"]["affiliate_slots"][0]["evidence"]["result_sha256"] = "d" * 64
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        finalizer,
        "_request_fingerprints",
        lambda paths: (_ for _ in ()).throw(
            AssertionError(f"private request read reached: {len(paths)}")
        ),
    )

    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"


@pytest.mark.parametrize(
    ("evidence_key", "replacement"),
    [
        ("api", "product-search"),
        ("api_version", "2026-07-02"),
        ("endpoint_id", "OTHER_ENDPOINT"),
        ("evidence_authority", "OTHER_AUTHORITY"),
        ("request_fingerprint", "f" * 64),
        ("response_sha256", "e" * 64),
        ("result_sha256", "d" * 64),
        ("retrieved_at", "2026-08-23T12:00:01.000000Z"),
    ],
)
def test_result_selection_rejects_any_packet_provider_evidence_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_key: str,
    replacement: str,
) -> None:
    root, store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
    )
    content_snapshot = finalizer._read_content_packet(
        root / CONTENT_PACKET_RELATIVE_PATH
    )
    committed = list(
        finalizer._load_committed_final_slots(root, snapshot=content_snapshot)
    )
    evidence = dict(committed[0].evidence)
    evidence[evidence_key] = replacement
    committed[0] = replace(committed[0], evidence=evidence)

    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._scan_results(
            store,
            committed_slots=tuple(committed),
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_RESULT_MISSING_OR_DUPLICATE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shopCode", "other-shop"),
        ("itemName", "unrelated model"),
        ("itemCode", "other-shop:synthetic"),
    ],
)
def test_finalizer_rejects_item_shop_or_name_mismatch(field: str, value: str) -> None:
    result = _validated_fixture_result(
        fingerprint="a" * 64,
        code="06316",
        item_mutation=(field, value),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._verified_slot_from_result(finalizer._SLOTS[0], result)
    assert failure.value.code == "AFFILIATE_RESULT_IDENTITY_MISMATCH"


def test_finalizer_rejects_provider_url_inequality() -> None:
    result = _validated_fixture_result(
        fingerprint="a" * 64,
        code="06316",
        alternate_item_url=_affiliate_url("06316", token="different"),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._verified_slot_from_result(finalizer._SLOTS[0], result)
    assert failure.value.code == "AFFILIATE_DESTINATION_INVALID"


def test_finalizer_rejects_raos_destination_hidden_in_mobile_redirect() -> None:
    result = _validated_fixture_result(
        fingerprint="a" * 64,
        code="06316",
        destination_url=_affiliate_url(
            "06316",
            mobile_target="https://kurashinoshirube.com/go/product",
        ),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._verified_slot_from_result(finalizer._SLOTS[0], result)
    assert failure.value.code == "AFFILIATE_DESTINATION_INVALID"


def test_finalizer_rejects_wrong_reviewed_mobile_item_target() -> None:
    result = _validated_fixture_result(
        fingerprint="a" * 64,
        code="06316",
        destination_url=_affiliate_url(
            "06316",
            mobile_target="http://m.rakuten.co.jp/ace-store/i/10009372/",
        ),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._verified_slot_from_result(finalizer._SLOTS[0], result)
    assert failure.value.code == "AFFILIATE_DESTINATION_INVALID"


def test_finalizer_rejects_synchronized_wrong_item_code_and_mobile_target() -> None:
    result = _validated_fixture_result(
        fingerprint="a" * 64,
        code="06316",
        item_mutation=("itemCode", "ace-store:10009999"),
        destination_url=_affiliate_url(
            "06316",
            mobile_target="http://m.rakuten.co.jp/ace-store/i/10009999/",
        ),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer._verified_slot_from_result(finalizer._SLOTS[0], result)
    assert failure.value.code == "AFFILIATE_RESULT_IDENTITY_MISMATCH"


@pytest.mark.parametrize("action", ["remove", "replace"])
def test_verifier_rejects_removed_or_replaced_exact_committed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
        finished_at=NOW - timedelta(days=2),
    )
    exact = _result_path_for_fingerprint(
        store,
        fingerprints["proteca-maxpass4-01471"],
    )
    exact.unlink()
    if action == "replace":
        _write_result(
            store,
            _result_object(
                fingerprint=fingerprints["proteca-maxpass4-01471"],
                code="01471",
                run_index=9,
                finished_at=NOW + timedelta(minutes=1),
            ),
        )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code == "AFFILIATE_RESULT_MISSING_OR_DUPLICATE"


def test_verifier_accepts_exact_committed_result_older_than_24_hours(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
        finished_at=NOW - timedelta(days=2),
    )
    receipt = finalizer.verify(
        repository_root=root,
        result_store=store,
        request_paths=requests,
        now=NOW,
    )
    assert receipt["status"] == "AFFILIATE_LINKS_VERIFIED"


def test_verifier_ignores_preexisting_newer_same_fingerprint_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
        finished_at=NOW - timedelta(days=2),
    )
    packet = json.loads((root / CONTENT_PACKET_RELATIVE_PATH).read_text())
    committed_sha256 = packet["article"]["affiliate_slots"][0]["evidence"][
        "result_sha256"
    ]
    newer = _write_result(
        store,
        _result_object(
            fingerprint=fingerprints["ace-cresta-06316"],
            code="06316",
            run_index=9,
            finished_at=NOW + timedelta(minutes=6),
        ),
    )
    assert hashlib.sha256(newer.read_bytes()).hexdigest() != committed_sha256

    receipt = finalizer.verify(
        repository_root=root,
        result_store=store,
        request_paths=requests,
        now=NOW,
    )
    assert receipt["status"] == "AFFILIATE_LINKS_VERIFIED"
    assert receipt["affiliate_slots_verified"] == 3


def test_verifier_rejects_exact_committed_result_beyond_future_skew(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
        finished_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
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
        finalizer.verify(
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_url: str,
) -> None:
    root, _store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path, monkeypatch
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root, _store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path, monkeypatch
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
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


def test_content_rejects_mixed_pending_and_final_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path, monkeypatch
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
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


@pytest.mark.parametrize(
    "unsafe", ["request-mode", "request-parent-mode", "result-mode", "unknown-file"]
)
def test_finalizer_rejects_malformed_or_non_private_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe: str,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
    )
    if unsafe == "request-mode":
        requests["ace-cresta-06316"].chmod(0o644)
    elif unsafe == "request-parent-mode":
        requests["ace-cresta-06316"].parent.chmod(0o755)
    elif unsafe == "result-mode":
        next(store.iterdir()).chmod(0o644)
    else:
        unknown = store / "unknown-material"
        unknown.write_text("{}", encoding="utf-8")
        unknown.chmod(0o600)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )
    assert failure.value.code in {
        "AFFILIATE_REQUEST_INVALID",
        "AFFILIATE_RESULT_STORE_INVALID",
    }


def test_finalizer_rejects_result_inserted_after_initial_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(tmp_path, monkeypatch)
    pending = (root / CONTENT_PACKET_RELATIVE_PATH).read_bytes()
    original_scan = finalizer._scan_results
    scans = 0

    def insert_late_duplicate(*args: object, **kwargs: object):
        nonlocal scans
        result = original_scan(*args, **kwargs)
        scans += 1
        if scans == 1:
            _write_result(
                store,
                _result_object(
                    fingerprint=fingerprints["ace-cresta-06316"],
                    code="06316",
                    run_index=9,
                ),
            )
        return result

    monkeypatch.setattr(finalizer, "_scan_results", insert_late_duplicate)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    assert scans == 2
    assert failure.value.code == "AFFILIATE_RESULT_STORE_INVALID"
    assert (root / CONTENT_PACKET_RELATIVE_PATH).read_bytes() == pending


@pytest.mark.parametrize("action", ["remove", "replace"])
def test_finalizer_rejects_exact_result_removal_or_replacement_between_scans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(tmp_path, monkeypatch)
    fingerprint = fingerprints["ace-cresta-06316"]
    exact = _result_path_for_fingerprint(store, fingerprint)
    original_scan = finalizer._scan_results
    scans = 0

    def mutate_before_terminal_scan(*args: object, **kwargs: object):
        nonlocal scans
        scans += 1
        if scans == 2:
            exact.unlink()
            if action == "replace":
                _write_result(
                    store,
                    _result_object(
                        fingerprint=fingerprint,
                        code="06316",
                        run_index=10,
                        finished_at=NOW,
                    ),
                )
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(finalizer, "_scan_results", mutate_before_terminal_scan)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    assert scans == 2
    assert failure.value.code == "AFFILIATE_RESULT_MISSING_OR_DUPLICATE"


def test_finalizer_rejects_byte_identical_result_inode_replacement_between_scans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, fingerprints = _complete_final_inputs(tmp_path, monkeypatch)
    exact = _result_path_for_fingerprint(
        store,
        fingerprints["ace-cresta-06316"],
    )
    original_scan = finalizer._scan_results
    scans = 0

    def replace_exact_after_initial_scan(*args: object, **kwargs: object):
        nonlocal scans
        result = original_scan(*args, **kwargs)
        scans += 1
        if scans == 1:
            replacement = tmp_path / "byte-identical-result.json"
            replacement.write_bytes(exact.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, exact)
        return result

    monkeypatch.setattr(finalizer, "_scan_results", replace_exact_after_initial_scan)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    assert scans == 2
    assert failure.value.code == "AFFILIATE_RESULT_STORE_INVALID"


def test_finalizer_rejects_terminal_packet_inode_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(
        tmp_path,
        monkeypatch,
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    original_scan = finalizer._scan_results
    scans = 0

    def replace_packet_after_terminal_scan(*args: object, **kwargs: object):
        nonlocal scans
        result = original_scan(*args, **kwargs)
        scans += 1
        if scans == 2:
            replacement = tmp_path / "byte-identical-content-packet.json"
            replacement.write_bytes(content_path.read_bytes())
            replacement.chmod(content_path.stat().st_mode & 0o777)
            os.replace(replacement, content_path)
        return result

    monkeypatch.setattr(finalizer, "_scan_results", replace_packet_after_terminal_scan)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    assert scans == 2
    assert failure.value.code == "AFFILIATE_CONTENT_STATE_INVALID"


def test_finalizer_rejects_result_store_inode_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store, requests, _fingerprints = _complete_final_inputs(tmp_path, monkeypatch)
    pending = (root / CONTENT_PACKET_RELATIVE_PATH).read_bytes()
    moved_store = store.with_name("moved-result-store")
    original_scan = finalizer._scan_results
    scans = 0

    def replace_store_after_initial_scan(*args: object, **kwargs: object):
        nonlocal scans
        result = original_scan(*args, **kwargs)
        scans += 1
        if scans == 1:
            store.rename(moved_store)
            store.mkdir(mode=0o700)
            store.chmod(0o700)
            for source in moved_store.iterdir():
                shutil.copy2(source, store / source.name)
        return result

    monkeypatch.setattr(finalizer, "_scan_results", replace_store_after_initial_scan)
    with pytest.raises(finalizer.AffiliateFinalizationFailure) as failure:
        finalizer.verify(
            repository_root=root,
            result_store=store,
            request_paths=requests,
            now=NOW,
        )

    assert scans == 2
    assert failure.value.code == "AFFILIATE_RESULT_STORE_INVALID"
    assert (root / CONTENT_PACKET_RELATIVE_PATH).read_bytes() == pending


def test_content_rejects_synchronized_destination_and_cta_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path, monkeypatch
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    article = packet["article"]
    slot = article["affiliate_slots"][0]
    old_url = slot["destination_url"]
    new_url = _affiliate_url("06316", token="mutated")
    article["content_html"] = article["content_html"].replace(
        affiliate_cta_html(slot["slot_id"], old_url),
        affiliate_cta_html(slot["slot_id"], new_url),
    )
    slot["destination_url"] = new_url
    provider_evidence = {
        key: value
        for key, value in slot["evidence"].items()
        if key != "destination_attestation_sha256"
    }
    slot["evidence"]["destination_attestation_sha256"] = (
        affiliate_destination_attestation_sha256(
            slot["slot_id"],
            new_url,
            provider_evidence,
        )
    )
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate_with_affiliate_status(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


def test_runtime_cta_rejects_cross_slot_mobile_item_target() -> None:
    wrong_mobile = _affiliate_url(
        "06316",
        mobile_target="http://m.rakuten.co.jp/ace-store/i/10009372/",
    )
    with pytest.raises(SelfHostedWordPressFailure):
        affiliate_cta_html("ace-cresta-06316", wrong_mobile)


@pytest.mark.parametrize(
    ("evidence_key", "replacement"),
    [
        ("request_fingerprint", "f" * 64),
        ("response_sha256", "e" * 64),
        ("result_sha256", "d" * 64),
    ],
)
def test_content_rejects_arbitrary_provider_evidence_even_with_new_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_key: str,
    replacement: str,
) -> None:
    root, _store, _requests, _fingerprints = _complete_final_inputs(
        tmp_path, monkeypatch
    )
    content_path = root / CONTENT_PACKET_RELATIVE_PATH
    packet = json.loads(content_path.read_text(encoding="utf-8"))
    slot = packet["article"]["affiliate_slots"][0]
    slot["evidence"][evidence_key] = replacement
    provider_evidence = {
        key: value
        for key, value in slot["evidence"].items()
        if key != "destination_attestation_sha256"
    }
    slot["evidence"]["destination_attestation_sha256"] = (
        affiliate_destination_attestation_sha256(
            slot["slot_id"],
            slot["destination_url"],
            provider_evidence,
        )
    )
    content_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate_with_affiliate_status(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
