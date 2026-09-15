"""KS-017 / KS-030: the viewport and performance records state their conditions.

Both records come from read-only production measurements
(``scripts/ks_viewport_matrix.mjs`` and ``scripts/ks_public_performance_probe.mjs``).
These checks do not re-measure anything. They only guard that each record names
its date, widths, blocked hosts and unmeasured items, that the widths in the
record match the ones the script actually uses, and that lab values are never
written as a pass/fail verdict against thresholds the site has not adopted.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "changes/ks-integrated-20260915/evidence"
VIEWPORT_RECORD = EVIDENCE / "KS-017.md"
PERFORMANCE_RECORD = EVIDENCE / "KS-030.md"
VIEWPORT_SCRIPT = ROOT / "scripts/ks_viewport_matrix.mjs"
PERFORMANCE_SCRIPT = ROOT / "scripts/ks_public_performance_probe.mjs"

WIDTHS = (320, 375, 390, 640, 768, 1280, 1440)
BLOCKED_AD_HOSTS = ("hbb.afl.rakuten.co.jp", "hb.afl.rakuten.co.jp")
# A verdict such as "LCP 合格" is forbidden; negated disclaimers
# ("CWV 合格ではない", "合否判定しない") are allowed.
VERDICT = re.compile(
    r"(LCP|CLS|INP|TTFB|FCP)[^\n]{0,40}(?<!非)(?:合格|不合格)(?!ではない|判定しない|としない)"
)


def _token(value: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])")


def _text(path: Path) -> str:
    assert path.is_file(), f"missing record: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _script_widths(source: str) -> tuple[int, ...]:
    match = re.search(r"const WIDTHS = \[([0-9, ]+)\]", source)
    assert match, "script must declare `const WIDTHS = [...]`"
    return tuple(int(value) for value in match.group(1).split(","))


def test_viewport_script_measures_the_planned_widths_and_pseudo_content() -> None:
    source = _text(VIEWPORT_SCRIPT)
    assert _script_widths(source) == WIDTHS
    assert "::before" in source and "::after" in source
    assert "text-size-adjust" in source
    for host in BLOCKED_AD_HOSTS:
        assert host.replace(".", r"\.") in source or host in source
    assert "https://kurashinoshirube.com" in source


def test_viewport_record_states_conditions_widths_and_unmeasured_items() -> None:
    text = _text(VIEWPORT_RECORD)
    for heading in ("測定条件", "結果", "不具合一覧", "未測定"):
        assert re.search(rf"^#+ [^\n]*{heading}", text, re.MULTILINE), heading
    assert "2026-09-15" in text
    for width in WIDTHS:
        assert _token(str(width)).search(text), f"width {width} not recorded"
    assert "text-size-adjust" in text and "200%" in text
    assert (
        "640px" in text and "1280" in text
    )  # 640px as the 1280px x 200% zoom equivalent
    for host in BLOCKED_AD_HOSTS:
        assert _token(host).search(text), f"blocked host {host} not recorded"
    assert "::before" in text and "::after" in text
    assert "39" in text  # page denominator
    assert re.search(r"theme\.css:4706", text)
    assert "scripts/ks_viewport_matrix.mjs" in text
    assert "output/ks-20260915/w2-measure/" in text


def test_performance_script_declares_states_and_blocked_hosts() -> None:
    source = _text(PERFORMANCE_SCRIPT)
    assert _script_widths(source) == (390, 1280)
    for state in ("normal", "images-failed", "js-disabled", "slow-network"):
        assert f"'{state}'" in source, state
    for host in BLOCKED_AD_HOSTS:
        assert host.replace(".", r"\.") in source or host in source
    assert "largest-contentful-paint" in source and "layout-shift" in source


def test_performance_record_states_conditions_and_unmeasured_items() -> None:
    text = _text(PERFORMANCE_RECORD)
    for heading in ("測定条件", "中央値", "未測定", "参考"):
        assert re.search(rf"^#+ [^\n]*{heading}", text, re.MULTILINE), heading
    for word in (
        "JS無効",
        "画像取得失敗",
        "低速回線",
        "価格失効",
        "TTFB",
        "FCP",
        "LCP",
        "CLS",
        "INP",
    ):
        assert word in text, word
    assert "2026-09-15" in text
    assert _token("96").search(text)  # 4 pages x 2 widths x 3 runs x 4 states
    for width in (390, 1280):
        assert _token(str(width)).search(text)
    for host in BLOCKED_AD_HOSTS:
        assert _token(host).search(text)
    assert "scripts/ks_public_performance_probe.mjs" in text
    assert not VERDICT.search(text), VERDICT.search(text)


def test_verdict_guard_allows_negated_disclaimers_only() -> None:
    assert not VERDICT.search("LCP/CLS は lab 観測で CWV 合格ではない")
    assert not VERDICT.search("LCP は参考値との比較のみで合否判定しない")
    assert VERDICT.search("LCP 1.2 秒で合格")
    assert VERDICT.search("CLS は不合格")
