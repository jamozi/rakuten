"""Closed transport and owner-store tests for ST-1704 official sources."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import runpy
import ssl
import stat
import tempfile
from typing import Final, cast
import unicodedata

import pytest

import raos.adapters.self_hosted_editorial_source_capture as capture_module
from raos.adapters.self_hosted_editorial_pilot_json import (
    OWNER_DIRECTORY,
    SOURCE_DIRECTORY,
    read_official_source_capture_evidence,
    source_body_relative_path,
    source_evidence_relative_path,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    bytes_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = REPOSITORY_ROOT / "scripts/st1704_official_source_capture.py"
WORDPRESS_SCRIPT = REPOSITORY_ROOT / "scripts/st1704_self_hosted_editorial_pilot.py"
SLICE_ROOT = REPOSITORY_ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
SOURCES_ROOT = SLICE_ROOT / "sources"
FIXED_NOW = datetime(2026, 8, 23, 12, 34, 56, tzinfo=timezone.utc)
UNIQUE_FRAGMENT = "定格容量は288Whです。"
SECOND_UNIQUE_FRAGMENT = "定格出力は300Wです。"
HTML_BODY = (
    '<!doctype html><html lang="ja"><head><title>公式仕様</title></head>'
    f"<body><p>{UNIQUE_FRAGMENT}</p></body></html>"
).encode()
POLICY_REFS = frozenset(
    {
        "SRC-CAA-STEALTH-MARKETING-QA",
        "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
        "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
    }
)
REMOVED_RAKUTEN_ACE_REFS = frozenset(
    {
        "SRC-RAKUTEN-ACE-CRESTA-06316",
        "SRC-RAKUTEN-ACE-DIFFERENCE-05721",
        "SRC-RAKUTEN-ACE-MAXPASS4-01471",
    }
)

# This fixture is intentionally independent of the locator contract.  A URL,
# claim id, and exactly-once fragment are structural evidence; these tokens are
# the separately reviewed semantic minimum for every logical claim-source pair.
EXPECTED_LOCATOR_ATOMIC_FACTS: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    (
        "SRC-ACE-CRESTA-06316",
        "CLM-ST1704-SUITCASE-CRESTA-SPECS",
    ): ("H55×W35×D25/29cm", "34/39L", "3.2kg"),
    (
        "SRC-ACE-CRESTA-06316",
        "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
    ): ("34/39L", "3.2kg"),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
    ): (
        "H55×W36×D24/27cm",
        "32/38L",
        "3.5kg",
        "2通りの開閉",
        "容量拡張",
        "キャスターストッパー",
    ),
    (
        "SRC-ACE-DIFFERENCE-05721",
        "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
    ): (
        "32/38L",
        "3.5kg",
        "容量拡張",
        "2通りの開閉",
        "キャスターストッパー",
    ),
    (
        "SRC-ACE-MAXPASS4-01471",
        "CLM-ST1704-SUITCASE-MAXPASS-SPECS",
    ): (
        "H50×W40×D25cm",
        "40L",
        "3.6kg",
        "フロントポケット",
        "メイン気室へアクセス可能",
        "14.0インチ",
        "キャスターストッパー",
    ),
    (
        "SRC-ACE-MAXPASS4-01471",
        "CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES",
    ): (
        "40L",
        "3.6kg",
        "フロントポケット",
        "メイン気室へアクセス可能",
    ),
    (
        "SRC-ANA-CARRY-ON-BAGGAGE",
        "CLM-ST1704-SUITCASE-CARRYON-LIMITS",
    ): (
        "3辺合計115cm以内",
        "55cm×40cm×25cm以内",
        "3辺合計100cm以内",
        "45cm×35cm×20cm以内",
        "合計10kg以内",
        "手荷物と身の回り品の総重量",
    ),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-POWER-C300-SPECS",
    ): ("288Wh", "定格300W", "4.1kg", "16.4×16.1×24.0cm"),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("288Wh", "定格300W", "4.1kg"),
    (
        "SRC-ANKER-SOLIX-C300",
        "CLM-ST1704-ANKER-C300-SPECS",
    ): ("288Wh", "定格300W", "4.1kg", "16.4×16.1×24.0cm"),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-JACKERY-SPECS",
    ): ("512Wh", "500W", "5.7kg"),
    (
        "SRC-JACKERY-500-NEW",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("512Wh", "500W", "5.7kg"),
    (
        "SRC-BLUETTI-AC70",
        "CLM-ST1704-POWER-AC70-SPECS",
    ): ("768Wh", "1,000W", "10.2kg", "314mm×209.5mm×255.8mm"),
    (
        "SRC-BLUETTI-AC70",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("768Wh", "1,000W", "10.2kg"),
    (
        "SRC-ECOFLOW-DELTA3-CLASSIC",
        "CLM-ST1704-POWER-DELTA-SPECS",
    ): ("1024Wh", "1500W", "12.1kg", "20.0×39.8×28.3cm"),
    (
        "SRC-ECOFLOW-DELTA3-CLASSIC",
        "CLM-ST1704-POWER-CONDITIONAL-CHOICES",
    ): ("1024Wh", "1500W", "12.1kg"),
    (
        "SRC-PANASONIC-NP-TMLK1",
        "CLM-ST1704-DISH-NP-TMLK1-SPECS",
    ): (
        "6点",
        "2.5L",
        "幅310×高さ435×奥行225",
        "7.5kg",
        "着脱タンク式",
        "送風乾燥",
    ),
    (
        "SRC-PANASONIC-NP-TMLK1",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): ("6点", "2.5L", "幅310×高さ435×奥行225", "送風乾燥"),
    (
        "SRC-THANKO-RAKUA-MINI-COLOR",
        "CLM-ST1704-DISH-RAKUA-SPECS",
    ): (
        "11〜12点",
        "3.2L",
        "幅308×奥行315×高さ415",
        "開扉時奥行:594mm",
        "8kg",
        "タンク式",
        "温風乾燥",
    ),
    (
        "SRC-THANKO-RAKUA-MINI-COLOR",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): (
        "11〜12点",
        "3.2L",
        "幅308×奥行315×高さ415",
        "開扉時奥行:594mm",
    ),
    (
        "SRC-SIROCA-SS-MA251",
        "CLM-ST1704-DISH-SS-MA251-SPECS",
    ): (
        "SS-MA251",
        "16点",
        "6L",
        "幅42×奥行44×高さ47cm",
        "13.5kg",
        "送風",
        "オートオープン",
    ),
    (
        "SRC-SIROCA-SS-MA251",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): ("16点", "6L", "幅42×奥行44×高さ47cm", "送風", "オートオープン"),
    (
        "SRC-PANASONIC-NP-TSP1",
        "CLM-ST1704-DISH-NP-TSP1-SPECS",
    ): (
        "24点",
        "9L",
        "幅550",
        "高さ600",
        "奥行341",
        "19kg",
        "タンク式",
        "乾燥機能",
        "リフトアップオープンドア",
    ),
    (
        "SRC-PANASONIC-NP-TSP1",
        "CLM-ST1704-DISH-CONDITIONAL-CHOICES",
    ): (
        "24点",
        "9L",
        "幅550",
        "高さ600",
        "奥行341",
        "乾燥機能",
        "リフトアップオープンドア",
    ),
    (
        "SRC-ANKER-SOLIX-C800-PLUS",
        "CLM-ST1704-ANKER-C800-SPECS",
    ): ("768Wh", "1200W", "10.9kg", "37.1×20.5×25.0cm"),
    (
        "SRC-ANKER-SOLIX-C1000",
        "CLM-ST1704-ANKER-C1000-SPECS",
    ): ("1056Wh", "1500W", "12.9kg", "37.6×20.5×26.7cm"),
    (
        "SRC-ANKER-SOLIX-C1000",
        "CLM-ST1704-ANKER-C1000-GENERATION-DIFF",
    ): ("1056Wh", "1500W", "12.9kg"),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
    ): ("1024Wh", "1550W", "11.3kg", "38.4×20.8×24.4cm"),
    (
        "SRC-ANKER-SOLIX-C1000-GEN2",
        "CLM-ST1704-ANKER-C1000-GENERATION-DIFF",
    ): ("1024Wh", "1550W", "11.3kg"),
    (
        "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "CLM-ST1704-ROBOT-ROOMBA-MINI-SPECS",
    ): (
        "24.5×24.5×9.2",
        "17.8×21.2×28.5",
        "掃除機がけ",
        "使い捨て床拭きシート",
        "自動ゴミ収集",
        "自動給水/ローラーモップの自動洗浄/自動乾燥―",
    ),
    (
        "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "24.5×24.5×9.2",
        "17.8×21.2×28.5",
        "使い捨て床拭きシート",
        "自動ゴミ収集",
    ),
    (
        "SRC-SWITCHBOT-K11-PRO",
        "CLM-ST1704-ROBOT-K11-PRO-SPECS",
    ): (
        "248×248×92mm",
        "240×180×250mm",
        "ゴミ収集ステーション",
        "90日ごみ捨て不要",
        "市販のお掃除シート",
        "そのまま捨てる",
    ),
    (
        "SRC-SWITCHBOT-K11-PRO",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "248×248×92mm",
        "240×180×250mm",
        "90日ごみ捨て不要",
        "市販のお掃除シート",
        "そのまま捨てる",
    ),
    (
        "SRC-SWITCHBOT-K10-PRO-COMBO",
        "CLM-ST1704-ROBOT-K10-COMBO-SPECS",
    ): (
        "248×248×92mm",
        "195×297×410mm",
        "お掃除シート",
        "デュアル集塵ステーション",
        "ロボット+スティックが1つのステーション",
    ),
    (
        "SRC-SWITCHBOT-K10-PRO-COMBO",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "248×248×92mm",
        "195×297×410mm",
        "お掃除シート",
        "ロボット+スティックが1つのステーション",
    ),
    (
        "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
        "CLM-ST1704-ROBOT-ROOMBA-515-SPECS",
    ): (
        "30.3×29.8×8.4",
        "34.0×33.0×48.5",
        "DualClean™モップパッド",
        "自動ゴミ収集",
        "自動給水",
        "温水洗浄",
        "温風乾燥",
    ),
    (
        "SRC-IROBOT-ROOMBA-PLUS-515-COMBO",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    ): (
        "30.3×29.8×8.4",
        "34.0×33.0×48.5",
        "DualClean™モップパッド",
        "自動ゴミ収集",
        "自動給水",
        "温水洗浄",
        "温風乾燥",
    ),
    (
        "SRC-RAKUTEN-AFFILIATE-GUIDELINE",
        "POLICY-SOURCE-STATEMENT",
    ): ("サイズ変更", "画像の上に直接文字", "切り取って使用することは禁止"),
    (
        "SRC-CAA-STEALTH-MARKETING-QA",
        "POLICY-SOURCE-STATEMENT",
    ): ("アフィリエイト広告を利用しています", "明瞭"),
    (
        "SRC-GOOGLE-QUALIFY-OUTBOUND-LINKS",
        "POLICY-SOURCE-STATEMENT",
    ): ("advertisements or paid placements", "sponsored"),
}


_HTML_TAG = re.compile(r"<[^>]*>")


def _semantic_text(value: str) -> str:
    decoded = html.unescape(_HTML_TAG.sub(" ", value))
    normalized = unicodedata.normalize("NFKC", decoded).casefold()
    normalized = normalized.replace("〜", "~").replace("～", "~")
    normalized = normalized.replace("×", "x")
    for axis_label in ("奥行き", "奥行", "幅", "高さ"):
        normalized = normalized.replace(f"({axis_label})", "")
    return re.sub(r"\s+", "", normalized)


@pytest.fixture
def private_root() -> Iterator[Path]:
    """Use a native filesystem because mounted Windows paths ignore POSIX modes."""

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-source-capture-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


class _Response:
    def __init__(
        self,
        body: bytes = HTML_BODY,
        *,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = (
            [("Content-Type", "text/html"), ("Content-Length", str(len(body)))]
            if headers is None
            else headers
        )

    def getheader(self, name: str, default: str | None = None) -> str | None:
        matches = [
            value for key, value in self._headers if key.casefold() == name.casefold()
        ]
        return matches[0] if len(matches) == 1 else default

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            amount = len(self._body) - self._offset
        start = self._offset
        self._offset = min(len(self._body), start + amount)
        return self._body[start : self._offset]


class _Connection:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.connected = False
        self.closed = False
        self.read_timeout: int | None = None
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def connect(self) -> None:
        self.connected = True

    def set_read_timeout(self, seconds: int) -> None:
        self.read_timeout = seconds

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.requests.append((method, path, dict(headers)))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, response: _Response) -> None:
        self.connection = _Connection(response)
        self.opens: list[dict[str, object]] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> _Connection:
        self.opens.append(
            {
                "connect_timeout_seconds": connect_timeout_seconds,
                "host": host,
                "port": port,
                "tls_context": tls_context,
            }
        )
        return self.connection


class _PeerSocket:
    def __init__(self, address: tuple[str, int] | tuple[str, int, int, int]) -> None:
        self.address = address
        self.read_timeout: int | None = None

    def getpeername(self) -> tuple[str, int] | tuple[str, int, int, int]:
        return self.address

    def settimeout(self, seconds: int) -> None:
        self.read_timeout = seconds


class _SystemHttpsConnection:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout: int,
        context: ssl.SSLContext,
        response: _Response,
        failing_ips: frozenset[str],
        attempts: list[str],
    ) -> None:
        self._create_connection: object | None = None
        self._tunnel_host: str | None = None
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.response = response
        self.failing_ips = failing_ips
        self.attempts = attempts
        self.sock: _PeerSocket | None = None
        self.closed = False
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def connect(self) -> None:
        connector = cast(capture_module._PinnedConnector, self._create_connection)
        candidate = connector.candidate
        candidate_ip = str(candidate.ip)
        self.attempts.append(candidate_ip)
        if candidate_ip in self.failing_ips:
            raise ConnectionRefusedError(candidate_ip)
        self.sock = _PeerSocket(candidate.socket_address)

    def request(
        self,
        method: str,
        path: str,
        body: object,
        headers: dict[str, str],
    ) -> None:
        assert body is None
        self.requests.append((method, path, dict(headers)))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def _system_connection_doubles(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing_ips: frozenset[str],
) -> tuple[list[_SystemHttpsConnection], list[str]]:
    connections: list[_SystemHttpsConnection] = []
    attempts: list[str] = []

    def open_connection(
        *, host: str, port: int, timeout: int, context: ssl.SSLContext
    ) -> _SystemHttpsConnection:
        connection = _SystemHttpsConnection(
            host=host,
            port=port,
            timeout=timeout,
            context=context,
            response=_Response(),
            failing_ips=failing_ips,
            attempts=attempts,
        )
        connections.append(connection)
        return connection

    monkeypatch.setattr(capture_module.http.client, "HTTPSConnection", open_connection)
    return connections, attempts


def _public_resolved_address(value: str) -> capture_module._ResolvedAddress:
    ip = capture_module._public_ip(value, family=capture_module.socket.AF_INET)
    return capture_module._ResolvedAddress(
        family=capture_module.socket.AF_INET,
        socket_type=capture_module.socket.SOCK_STREAM,
        protocol=capture_module.socket.IPPROTO_TCP,
        socket_address=(str(ip), 443),
        ip=ip,
    )


def _target(
    *,
    locator_status: str = "LOCATORS_PENDING",
    fragment: str = UNIQUE_FRAGMENT,
    charset: str | None = None,
    observed_on: date = date(2026, 8, 23),
) -> capture_module.SourceCaptureTarget:
    locators: tuple[capture_module.SourceLocator, ...]
    if locator_status == "READY":
        locators = (
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (fragment,),
            ),
        )
    else:
        locators = ()
    return capture_module.SourceCaptureTarget(
        source_ref="SRC-TEST-OFFICIAL",
        url="https://official.example/specifications",
        host="official.example",
        path="/specifications",
        observed_on=observed_on,
        charset=charset,
        locator_status=locator_status,
        locators=locators,
    )


def _fetched(
    *,
    locator_status: str,
    body: bytes = HTML_BODY,
    fragment: str = UNIQUE_FRAGMENT,
) -> capture_module.FetchedSource:
    return capture_module.FetchedSource(
        target=_target(locator_status=locator_status, fragment=fragment),
        retrieved_at="2026-08-23T12:34:56Z",
        content_type="text/html",
        body=body,
    )


def _fetch(
    response: _Response,
    *,
    target: capture_module.SourceCaptureTarget | None = None,
    clock: datetime = FIXED_NOW,
) -> tuple[capture_module.FetchedSource, _Factory]:
    factory = _Factory(response)
    result = capture_module._fetch_source(
        _target() if target is None else target,
        connection_factory=factory,
        clock=lambda: clock,
        environment={},
    )
    return result, factory


def _failure_code(error: pytest.ExceptionInfo[Exception]) -> object:
    return cast(capture_module.OfficialSourceCaptureFailure, error.value).code


def test_tracked_plan_is_exactly_19_official_plus_three_policy_sources() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    capture_namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    expected_urls = {
        value["source_ref"]: value["url"]
        for collection in (registry["sources"], registry["policy_sources"])
        for value in collection
    }

    assert len(plan.targets) == 22
    assert len(expected_urls) == 22
    assert all(target.locator_status == "READY" for target in plan.targets)
    assert sum(len(target.locators) for target in plan.targets) == 40
    assert set(expected_urls) == set(capture_namespace["SOURCE_REFS"])
    assert sum(target.source_ref not in POLICY_REFS for target in plan.targets) == 19
    assert sum(target.source_ref in POLICY_REFS for target in plan.targets) == 3
    assert {target.source_ref: target.url for target in plan.targets} == expected_urls
    assert not REMOVED_RAKUTEN_ACE_REFS & set(expected_urls)
    assert all(not value.startswith("SRC-RAKUTEN-ACE-") for value in expected_urls)


def test_tracked_contract_uses_grouped_string_fragments_only() -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    locators = [
        locator for source in contract["sources"] for locator in source["locators"]
    ]

    assert len(locators) == 40
    assert all(
        set(locator) == {"claim_id", "exact_utf8_fragments"} for locator in locators
    )
    assert all(
        type(locator["exact_utf8_fragments"]) is list
        and locator["exact_utf8_fragments"]
        and all(type(fragment) is str for fragment in locator["exact_utf8_fragments"])
        for locator in locators
    )
    assert any(len(locator["exact_utf8_fragments"]) > 1 for locator in locators)
    assert sum(len(locator["exact_utf8_fragments"]) for locator in locators) > 40
    assert all(
        1 <= len(fragment.encode("utf-8")) <= 2_000
        for locator in locators
        for fragment in locator["exact_utf8_fragments"]
    )


def test_all_40_logical_locators_cover_claim_specific_atomic_facts() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    observed: dict[tuple[str, str], tuple[str, ...]] = {}
    missing: dict[tuple[str, str], tuple[str, ...]] = {}

    for target in plan.targets:
        for locator in target.locators:
            key = (target.source_ref, locator.claim_id)
            material = _semantic_text("\n".join(locator.exact_utf8_fragments))
            expected = EXPECTED_LOCATOR_ATOMIC_FACTS.get(key)
            assert expected is not None, f"unreviewed logical locator: {key!r}"
            absent = tuple(
                token for token in expected if _semantic_text(token) not in material
            )
            observed[key] = expected
            if absent:
                missing[key] = absent

    assert set(observed) == set(EXPECTED_LOCATOR_ATOMIC_FACTS)
    assert len(observed) == 40
    assert not missing, "claim-source locator semantic gaps: " + "; ".join(
        f"{source_ref}/{claim_id}: {tokens!r}"
        for (source_ref, claim_id), tokens in sorted(missing.items())
    )


def test_each_of_five_article_plans_has_four_sources_plus_fixed_policy_sources() -> (
    None
):
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)
    namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    article_ids = cast(tuple[str, ...], namespace["ARTICLE_IDS"])

    assert len(article_ids) == 5
    assert {article_id for article_id, _refs in plan.article_sources} == set(
        article_ids
    )
    for article_id in article_ids:
        selected = plan.for_article(article_id)
        selected_refs = [target.source_ref for target in selected]
        assert len(selected_refs) == 7
        assert len(selected_refs) == len(set(selected_refs))
        assert POLICY_REFS < set(selected_refs)
        assert sum(source_ref not in POLICY_REFS for source_ref in selected_refs) == 4


def test_plan_refuses_unknown_source_and_article_identifiers() -> None:
    plan = capture_module.load_source_capture_plan(REPOSITORY_ROOT)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as source_error:
        plan.target("SRC-NOT-TRACKED")
    assert _failure_code(source_error) is (
        capture_module.OfficialSourceCaptureFailureCode.SOURCE_NOT_ALLOWLISTED
    )
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as article_error:
        plan.for_article("st1704-not-allowlisted")
    assert _failure_code(article_error) is (
        capture_module.OfficialSourceCaptureFailureCode.ARTICLE_NOT_ALLOWLISTED
    )


def test_registry_change_without_locator_contract_rebind_is_rejected(
    private_root: Path,
) -> None:
    destination = private_root / capture_module.SOURCE_REGISTRY_RELATIVE_PATH.parent
    destination.mkdir(parents=True)
    registry = json.loads(
        (SOURCES_ROOT / "source-registry.v1.json").read_text(encoding="utf-8")
    )
    registry["sources"][0]["url"] = "https://official.example/changed"
    (destination / "source-registry.v1.json").write_text(
        json.dumps(registry, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (destination / "source-locator-contract.v1.json").write_bytes(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_bytes()
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module.load_source_capture_plan(private_root)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
    )


def _write_source_contract_fixture(
    private_root: Path,
    contract: dict[str, object],
) -> None:
    destination = private_root / capture_module.SOURCE_REGISTRY_RELATIVE_PATH.parent
    destination.mkdir(parents=True)
    (destination / "source-registry.v1.json").write_bytes(
        (SOURCES_ROOT / "source-registry.v1.json").read_bytes()
    )
    (destination / "source-locator-contract.v1.json").write_text(
        json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def test_contract_allows_minimal_exact_fragment_reuse_across_claims(
    private_root: Path,
) -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    source = next(value for value in contract["sources"] if len(value["locators"]) > 1)
    first, second = source["locators"][:2]
    shared = first["exact_utf8_fragments"][0]
    second["exact_utf8_fragments"] = [shared]
    _write_source_contract_fixture(private_root, contract)

    plan = capture_module.load_source_capture_plan(private_root)
    target = plan.target(source["source_ref"])

    assert target.locators[0].exact_utf8_fragments[0] == shared
    assert target.locators[1].exact_utf8_fragments == (shared,)


def test_contract_rejects_duplicate_fragment_within_one_claim(
    private_root: Path,
) -> None:
    contract = json.loads(
        (SOURCES_ROOT / "source-locator-contract.v1.json").read_text(encoding="utf-8")
    )
    locator = contract["sources"][0]["locators"][0]
    locator["exact_utf8_fragments"].append(locator["exact_utf8_fragments"][0])
    _write_source_contract_fixture(private_root, contract)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module.load_source_capture_plan(private_root)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
    )


def test_exact_get_uses_fixed_tls_timeouts_and_no_credentials() -> None:
    fetched, factory = _fetch(_Response())

    assert fetched.body == HTML_BODY
    assert fetched.content_type == "text/html"
    assert fetched.retrieved_at == "2026-08-23T12:34:56Z"
    assert fetched.target.url == "https://official.example/specifications"
    assert len(factory.opens) == 1
    opened = factory.opens[0]
    assert opened["host"] == "official.example"
    assert opened["port"] == 443
    assert opened["connect_timeout_seconds"] == (capture_module.CONNECT_TIMEOUT_SECONDS)
    context = cast(ssl.SSLContext, opened["tls_context"])
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    connection = factory.connection
    assert connection.connected
    assert connection.closed
    assert connection.read_timeout == capture_module.READ_TIMEOUT_SECONDS
    assert connection.requests == [
        (
            "GET",
            "/specifications",
            {
                "Accept": capture_module.CAPTURE_ACCEPT,
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": "official.example",
                "User-Agent": capture_module.CAPTURE_USER_AGENT,
            },
        )
    ]
    headers = connection.requests[0][2]
    assert "Authorization" not in headers
    assert "Cookie" not in headers


def test_system_transport_tries_later_verified_endpoint_before_one_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _public_resolved_address("1.1.1.1")
    second = _public_resolved_address("8.8.8.8")
    resolved_hosts: list[str] = []

    def resolve(host: str) -> tuple[capture_module._ResolvedAddress, ...]:
        resolved_hosts.append(host)
        return (first, second)

    monkeypatch.setattr(capture_module, "_resolve_public_addresses", resolve)
    connections, attempts = _system_connection_doubles(
        monkeypatch, failing_ips=frozenset({str(first.ip)})
    )

    fetched = capture_module._fetch_source(
        _target(),
        connection_factory=(
            capture_module._SystemOfficialSourceHttpsConnectionFactory()
        ),
        clock=lambda: FIXED_NOW,
        environment={},
    )

    assert fetched.body == HTML_BODY
    assert resolved_hosts == ["official.example"]
    assert attempts == [str(first.ip), str(second.ip)]
    assert len(connections) == 2
    assert all(connection.host == "official.example" for connection in connections)
    assert all(connection.port == 443 for connection in connections)
    assert all(
        connection.timeout == capture_module.CONNECT_TIMEOUT_SECONDS
        for connection in connections
    )
    assert all(connection.context.check_hostname for connection in connections)
    assert all(
        connection.context.verify_mode == ssl.CERT_REQUIRED
        for connection in connections
    )
    assert connections[0].requests == []
    assert connections[1].requests == [
        (
            "GET",
            "/specifications",
            {
                "Accept": capture_module.CAPTURE_ACCEPT,
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": "official.example",
                "User-Agent": capture_module.CAPTURE_USER_AGENT,
            },
        )
    ]
    assert sum(len(connection.requests) for connection in connections) == 1
    assert connections[0].closed and connections[1].closed
    assert connections[1].sock is not None
    assert connections[1].sock.read_timeout == capture_module.READ_TIMEOUT_SECONDS


def test_system_transport_reports_failure_only_after_all_endpoints_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _public_resolved_address("1.1.1.1")
    second = _public_resolved_address("8.8.8.8")
    monkeypatch.setattr(
        capture_module,
        "_resolve_public_addresses",
        lambda _host: (first, second),
    )
    connections, attempts = _system_connection_doubles(
        monkeypatch,
        failing_ips=frozenset({str(first.ip), str(second.ip)}),
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._fetch_source(
            _target(),
            connection_factory=(
                capture_module._SystemOfficialSourceHttpsConnectionFactory()
            ),
            clock=lambda: FIXED_NOW,
            environment={},
        )

    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.CONNECTION_FAILED
    )
    assert attempts == [str(first.ip), str(second.ip)]
    assert len(connections) == 2
    assert all(connection.closed for connection in connections)
    assert all(connection.requests == [] for connection in connections)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_dns_rejects_non_public_addresses(address: str) -> None:
    family = (
        capture_module.socket.AF_INET6
        if ":" in address
        else capture_module.socket.AF_INET
    )
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._public_ip(address, family=family)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.DNS_ADDRESS_REJECTED
    )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            _Response(status=301, headers=[("Content-Type", "text/html")]),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Location", "https://official.example/other"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Content-Encoding", "gzip"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("content-type", "text/html"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(headers=[("Content-Type", "application/json")]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(headers=[]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(headers=[("Content-Type", "text/html; charset=utf-8")]),
            capture_module.OfficialSourceCaptureFailureCode.MIME_INVALID,
        ),
        (
            _Response(
                headers=[("Content-Type", "text/html"), ("Content-Length", "01")]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Content-Length", str(len(HTML_BODY) + 1)),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(
                headers=[
                    ("Content-Type", "text/html"),
                    ("Transfer-Encoding", "gzip"),
                ]
            ),
            capture_module.OfficialSourceCaptureFailureCode.RESPONSE_INVALID,
        ),
        (
            _Response(b"", headers=[("Content-Type", "text/html")]),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
        (
            _Response(
                b"<html><body>truncated", headers=[("Content-Type", "text/html")]
            ),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
        (
            _Response(
                b"<!doctype html><html><body>\xff</body></html>",
                headers=[("Content-Type", "text/html")],
            ),
            capture_module.OfficialSourceCaptureFailureCode.HTML_INVALID,
        ),
    ],
)
def test_http_response_variants_fail_closed(
    response: _Response,
    expected: capture_module.OfficialSourceCaptureFailureCode,
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(response)
    assert _failure_code(failure) is expected


def test_declared_oversized_body_is_rejected_before_read() -> None:
    response = _Response(
        headers=[
            ("Content-Type", "text/html"),
            ("Content-Length", str(capture_module.MAX_SOURCE_BODY_BYTES + 1)),
        ]
    )

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(response)
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.BODY_TOO_LARGE
    )
    assert response._offset == 0


def test_exact_utf8_and_euc_jp_encoding_contracts() -> None:
    utf8_target = _target(charset="utf-8")
    utf8, _factory = _fetch(
        _Response(headers=[("Content-Type", "text/html; charset=UTF_8")]),
        target=utf8_target,
    )
    assert utf8.body == HTML_BODY

    euc_body = (
        "<!doctype html><html><body><p>公式仕様です。</p></body></html>"
    ).encode("euc_jp")
    euc, _factory = _fetch(
        _Response(
            euc_body,
            headers=[("Content-Type", "text/html; charset=EUC_JP")],
        ),
        target=_target(charset="euc-jp"),
    )
    assert euc.body == euc_body


@pytest.mark.parametrize(
    "environment",
    [
        {"HTTPS_PROXY": "https://proxy.invalid"},
        {"https_proxy": ""},
        {"SSL_CERT_FILE": "/tmp/ca.pem"},
        {"SSLKEYLOGFILE": "/tmp/tls.keys"},
        {"NO_PROXY": "official.example"},
    ],
)
def test_proxy_and_ca_override_environment_is_rejected(
    environment: dict[str, str],
) -> None:
    factory = _Factory(_Response())
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._fetch_source(
            _target(),
            connection_factory=factory,
            clock=lambda: FIXED_NOW,
            environment=environment,
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE
    )
    assert factory.opens == []


@pytest.mark.parametrize(
    ("clock", "expected"),
    [
        (
            datetime(2026, 8, 22, tzinfo=timezone.utc),
            capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID,
        ),
        (
            datetime(2026, 8, 23),
            capture_module.OfficialSourceCaptureFailureCode.INVALID_ARGUMENT,
        ),
        (
            datetime(2026, 8, 23, tzinfo=timezone(timedelta(hours=9))),
            capture_module.OfficialSourceCaptureFailureCode.INVALID_ARGUMENT,
        ),
    ],
)
def test_capture_clock_must_be_truthful_utc_and_not_precede_registry_baseline(
    clock: datetime, expected: capture_module.OfficialSourceCaptureFailureCode
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        _fetch(_Response(), clock=clock)
    assert _failure_code(failure) is expected


def test_registry_observed_date_is_not_an_artificial_capture_expiry() -> None:
    later = datetime(2036, 8, 23, 1, 2, 3, tzinfo=timezone.utc)
    fetched, _factory = _fetch(_Response(), clock=later)
    assert fetched.retrieved_at == "2036-08-23T01:02:03Z"


@pytest.mark.parametrize(
    "body",
    [
        b"<!doctype html><html><body>no matching fact</body></html>",
        (
            "<!doctype html><html><body>"
            f"<p>{UNIQUE_FRAGMENT}</p><p>{UNIQUE_FRAGMENT}</p>"
            "</body></html>"
        ).encode(),
    ],
)
def test_final_capture_rejects_zero_or_duplicate_locator_occurrences(
    private_root: Path, body: bytes
) -> None:
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root,
            _fetched(locator_status="READY", body=body),
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH
    )
    metadata = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    assert not metadata.exists()


def test_pending_capture_is_private_and_never_reader_accepted_as_final(
    private_root: Path,
) -> None:
    fetched = _fetched(locator_status="LOCATORS_PENDING")
    first = capture_module._persist_capture(private_root, fetched)
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    pending_body = sources / "SRC-TEST-OFFICIAL.capture.body"
    pending_metadata = sources / "SRC-TEST-OFFICIAL.capture.v1.json"

    assert first.status == "BODY_CAPTURED_LOCATORS_PENDING"
    assert first.retrieved_at == "2026-08-23T12:34:56Z"
    assert first.body_sha256 == bytes_sha256(HTML_BODY)
    assert pending_body.read_bytes() == HTML_BODY
    assert (
        json.loads(pending_metadata.read_text(encoding="utf-8"))["locator_status"]
        == "LOCATORS_PENDING"
    )
    assert not (sources / "SRC-TEST-OFFICIAL.body").exists()
    assert not (sources / "SRC-TEST-OFFICIAL.v1.json").exists()
    with pytest.raises(EditorialPilotFailure) as not_ready:
        read_official_source_capture_evidence(
            private_root, source_ref="SRC-TEST-OFFICIAL"
        )
    assert not_ready.value.code is EditorialPilotFailureCode.RESOURCE_NOT_READY

    for directory in (
        private_root / ".secrets",
        private_root / ".secrets" / OWNER_DIRECTORY,
        sources,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in (
        pending_body,
        pending_metadata,
        sources / capture_module.CAPTURE_LOCK_FILE,
    ):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_final_capture_is_idempotent_and_accepted_by_existing_reader(
    private_root: Path,
) -> None:
    fetched = _fetched(locator_status="READY")
    first = capture_module._persist_capture(private_root, fetched)
    body_path = private_root / source_body_relative_path("SRC-TEST-OFFICIAL")
    metadata_path = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    first_inodes = (body_path.stat().st_ino, metadata_path.stat().st_ino)

    second = capture_module._persist_capture(private_root, fetched)
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert first == second
    assert first.status == "CAPTURED_WITH_VERIFIED_LOCATORS"
    assert first_inodes == (body_path.stat().st_ino, metadata_path.stat().st_ino)
    assert loaded.source_ref == "SRC-TEST-OFFICIAL"
    assert loaded.final_url == "https://official.example/specifications"
    assert loaded.retrieved_at == "2026-08-23T12:34:56Z"
    assert loaded.body_sha256 == bytes_sha256(HTML_BODY)
    assert loaded.locators[0][0] == "CLM-ST1704-TEST-OFFICIAL-SPECS"
    assert loaded.locators[0][2][0][0] == UNIQUE_FRAGMENT
    assert body_path.read_bytes() == HTML_BODY
    assert stat.S_IMODE(body_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600


def test_grouped_locator_evidence_round_trips_as_fragment_records(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    grouped_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT, SECOND_UNIQUE_FRAGMENT),
            ),
        ),
    )
    body = (
        "<!doctype html><html><body>"
        f"<p>{UNIQUE_FRAGMENT}</p><p>{SECOND_UNIQUE_FRAGMENT}</p>"
        "</body></html>"
    ).encode()
    capture_module._persist_capture(
        private_root,
        capture_module.FetchedSource(
            target=grouped_target,
            retrieved_at="2026-08-23T12:34:56Z",
            content_type="text/html",
            body=body,
        ),
    )
    metadata_path = private_root / source_evidence_relative_path("SRC-TEST-OFFICIAL")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fragment_records = metadata["locators"][0]["exact_utf8_fragments"]
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert [record["exact_utf8_fragment"] for record in fragment_records] == [
        UNIQUE_FRAGMENT,
        SECOND_UNIQUE_FRAGMENT,
    ]
    assert all(
        set(record) == {"exact_utf8_fragment", "fragment_sha256"}
        for record in fragment_records
    )
    assert loaded.locators[0][2] == (
        (UNIQUE_FRAGMENT, bytes_sha256(UNIQUE_FRAGMENT.encode())),
        (SECOND_UNIQUE_FRAGMENT, bytes_sha256(SECOND_UNIQUE_FRAGMENT.encode())),
    )


def test_one_body_occurrence_can_support_two_distinct_claims(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    shared_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT,),
            ),
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-CONDITIONAL-CHOICES",
                "b" * 64,
                (UNIQUE_FRAGMENT,),
            ),
        ),
    )

    result = capture_module._persist_capture(
        private_root,
        capture_module.FetchedSource(
            target=shared_target,
            retrieved_at="2026-08-23T12:34:56Z",
            content_type="text/html",
            body=HTML_BODY,
        ),
    )
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )

    assert result.status == "CAPTURED_WITH_VERIFIED_LOCATORS"
    assert len(loaded.locators) == 2
    assert loaded.locators[0][2] == loaded.locators[1][2]
    assert loaded.locators[0][0] != loaded.locators[1][0]


def test_grouped_locator_requires_each_fragment_exactly_once(
    private_root: Path,
) -> None:
    target = _target(locator_status="LOCATORS_PENDING")
    grouped_target = capture_module.SourceCaptureTarget(
        source_ref=target.source_ref,
        url=target.url,
        host=target.host,
        path=target.path,
        observed_on=target.observed_on,
        charset=target.charset,
        locator_status="READY",
        locators=(
            capture_module.SourceLocator(
                "CLM-ST1704-TEST-OFFICIAL-SPECS",
                "a" * 64,
                (UNIQUE_FRAGMENT, SECOND_UNIQUE_FRAGMENT),
            ),
        ),
    )
    body = (
        f"<!doctype html><html><body><p>{UNIQUE_FRAGMENT}</p></body></html>"
    ).encode()

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root,
            capture_module.FetchedSource(
                target=grouped_target,
                retrieved_at="2026-08-23T12:34:56Z",
                content_type="text/html",
                body=body,
            ),
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH
    )


def test_body_is_installed_before_metadata_commit_marker(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: list[str] = []
    original = capture_module._replace_private

    def recording_install(directory: Path, name: str, payload: bytes) -> None:
        installed.append(name)
        original(directory, name, payload)

    monkeypatch.setattr(capture_module, "_replace_private", recording_install)
    capture_module._persist_capture(
        private_root, _fetched(locator_status="LOCATORS_PENDING")
    )

    assert installed == [
        "SRC-TEST-OFFICIAL.capture.body",
        "SRC-TEST-OFFICIAL.capture.v1.json",
    ]


def test_later_capture_atomically_refreshes_body_and_metadata(
    private_root: Path,
) -> None:
    first = _fetched(locator_status="LOCATORS_PENDING")
    capture_module._persist_capture(private_root, first)
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    body_path = sources / "SRC-TEST-OFFICIAL.capture.body"
    metadata_path = sources / "SRC-TEST-OFFICIAL.capture.v1.json"
    original_body = body_path.read_bytes()
    original_metadata = metadata_path.read_bytes()
    changed = _fetched(
        locator_status="LOCATORS_PENDING",
        body=HTML_BODY.replace(b"288", b"289"),
    )

    refreshed = capture_module._persist_capture(private_root, changed)

    assert refreshed.body_sha256 == bytes_sha256(changed.body)
    assert body_path.read_bytes() == changed.body
    assert body_path.read_bytes() != original_body
    assert metadata_path.read_bytes() != original_metadata


def test_interrupted_metadata_refresh_fails_closed_and_rerun_repairs(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _fetched(locator_status="READY")
    capture_module._persist_capture(private_root, original)
    refreshed = _fetched(
        locator_status="READY",
        body=HTML_BODY.replace("公式仕様".encode(), "公式諸元".encode()),
    )
    replace_private = capture_module._replace_private
    metadata_failed = False

    def fail_first_metadata(directory: Path, name: str, payload: bytes) -> None:
        nonlocal metadata_failed
        if name.endswith(".v1.json") and not metadata_failed:
            metadata_failed = True
            raise capture_module.OfficialSourceCaptureFailure(
                capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
            )
        replace_private(directory, name, payload)

    monkeypatch.setattr(capture_module, "_replace_private", fail_first_metadata)
    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as interrupted:
        capture_module._persist_capture(private_root, refreshed)
    assert _failure_code(interrupted) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    with pytest.raises(EditorialPilotFailure) as mismatch:
        read_official_source_capture_evidence(
            private_root, source_ref="SRC-TEST-OFFICIAL"
        )
    assert mismatch.value.code is EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID

    capture_module._persist_capture(private_root, refreshed)
    loaded = read_official_source_capture_evidence(
        private_root, source_ref="SRC-TEST-OFFICIAL"
    )
    assert loaded.body_sha256 == bytes_sha256(refreshed.body)


def test_private_store_rejects_symlink_at_every_owner_boundary(
    private_root: Path,
) -> None:
    outside = private_root / "outside"
    outside.mkdir(mode=0o700)
    (private_root / ".secrets").symlink_to(outside, target_is_directory=True)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root, _fetched(locator_status="LOCATORS_PENDING")
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    assert list(outside.iterdir()) == []


def test_private_store_rejects_symlink_capture_file(private_root: Path) -> None:
    sources = private_root / ".secrets" / OWNER_DIRECTORY / SOURCE_DIRECTORY
    sources.mkdir(parents=True, mode=0o700)
    (private_root / ".secrets").chmod(0o700)
    (private_root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    sources.chmod(0o700)
    outside = private_root / "outside-body"
    outside.write_bytes(b"do not overwrite")
    outside.chmod(0o600)
    (sources / "SRC-TEST-OFFICIAL.capture.body").symlink_to(outside)

    with pytest.raises(capture_module.OfficialSourceCaptureFailure) as failure:
        capture_module._persist_capture(
            private_root, _fetched(locator_status="LOCATORS_PENDING")
        )
    assert _failure_code(failure) is (
        capture_module.OfficialSourceCaptureFailureCode.STORE_UNSAFE
    )
    assert outside.read_bytes() == b"do not overwrite"


def _option_strings(parser: object) -> set[str]:
    actions = cast(list[object], getattr(parser, "_actions"))
    return {
        option
        for action in actions
        for option in cast(list[str], getattr(action, "option_strings"))
    }


def test_capture_cli_exposes_only_two_closed_commands_and_fixed_selectors() -> None:
    namespace = runpy.run_path(str(CAPTURE_SCRIPT))
    parser = namespace["_parser"]()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) is not None
    )
    choices = cast(dict[str, object], subparsers.choices)

    assert set(choices) == {"capture-source", "capture-article"}
    assert _option_strings(choices["capture-source"]) == {
        "-h",
        "--help",
        "--source-ref",
    }
    assert _option_strings(choices["capture-article"]) == {
        "-h",
        "--help",
        "--article-id",
    }
    assert len(cast(tuple[str, ...], namespace["SOURCE_REFS"])) == 22
    assert len(cast(tuple[str, ...], namespace["ARTICLE_IDS"])) == 5
    assert not REMOVED_RAKUTEN_ACE_REFS & set(namespace["SOURCE_REFS"])


def test_module_public_surface_has_no_caller_constructed_target_capture_entry() -> None:
    public = set(capture_module.__all__)
    assert {"capture_source_ref", "capture_article_sources"} <= public
    assert (
        not {
            "FetchedSource",
            "SourceCaptureTarget",
            "capture_sources",
            "fetch_source",
            "persist_capture",
            "OfficialSourceHttpsConnectionFactory",
            "SystemOfficialSourceHttpsConnectionFactory",
        }
        & public
    )


def test_public_capture_entries_rebind_only_tracked_source_and_article_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[tuple[capture_module.SourceCaptureTarget, ...]] = []

    def record_targets(
        repository_root: Path,
        targets: tuple[capture_module.SourceCaptureTarget, ...],
        **_kwargs: object,
    ) -> tuple[capture_module.SourceCaptureResult, ...]:
        assert repository_root == REPOSITORY_ROOT
        selected.append(tuple(targets))
        return ()

    monkeypatch.setattr(capture_module, "_capture_targets", record_targets)
    factory = _Factory(_Response())
    source_result = capture_module.capture_source_ref(
        REPOSITORY_ROOT,
        source_ref="SRC-ANKER-SOLIX-C300",
        connection_factory=factory,
        clock=lambda: FIXED_NOW,
        environment={},
    )
    article_result = capture_module.capture_article_sources(
        REPOSITORY_ROOT,
        article_id="st1704-portable-power-station-guide",
        connection_factory=factory,
        clock=lambda: FIXED_NOW,
        environment={},
    )

    assert source_result == article_result == ()
    assert [target.source_ref for target in selected[0]] == ["SRC-ANKER-SOLIX-C300"]
    assert len(selected[1]) == 7
    assert {target.source_ref for target in selected[1]} >= POLICY_REFS
    assert factory.opens == []


@pytest.mark.parametrize(
    "argv",
    [
        ["capture-source", "--source-ref", "SRC-NOT-TRACKED"],
        [
            "capture-source",
            "--source-ref",
            "SRC-ANKER-SOLIX-C300",
            "--url",
            "https://attacker.invalid/",
        ],
        [
            "capture-source",
            "--source-ref",
            "SRC-ANKER-SOLIX-C300",
            "--output",
            "/tmp/capture",
        ],
        ["capture-article", "--article-id", "st1704-not-allowlisted"],
    ],
)
def test_capture_cli_refuses_arbitrary_identifier_url_and_output(
    argv: list[str],
) -> None:
    parser = runpy.run_path(str(CAPTURE_SCRIPT))["_parser"]()
    with pytest.raises(SystemExit) as rejected:
        parser.parse_args(argv)
    assert rejected.value.code == 2


def test_existing_wordpress_cli_remains_exactly_five_commands() -> None:
    namespace = runpy.run_path(str(WORDPRESS_SCRIPT))
    assert namespace["COMMANDS"] == (
        "prepare",
        "create-review-draft",
        "recover-create-review-draft",
        "verify-carry-on-single-url",
        "verify-public",
    )
    parser = namespace["_parser"]()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) is not None
    )
    assert set(subparsers.choices) == set(namespace["COMMANDS"])
    for command in subparsers.choices.values():
        assert _option_strings(command) == {"-h", "--help", "--article-id"}
