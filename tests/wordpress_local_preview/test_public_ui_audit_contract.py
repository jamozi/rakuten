from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts/wordpress_public_ui_audit.function.js"
SHELL = ROOT / "scripts/check_wordpress_public_ui_playwright.sh"


def test_public_audit_covers_home_ten_articles_and_three_pages_at_four_widths() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert source.count("article: true") == 10
    for path in (
        "/carry-on-suitcase-comparison/",
        "/portable-power-station-guide/",
        "/anker-solix-c300-c800-c1000-differences/",
        "/countertop-dishwasher-for-small-households/",
        "/compact-robot-vacuum-shortlist/",
        "/carry-on-suitcase-under-100-seats/",
        "/lightweight-carry-on-suitcase-under-3kg/",
        "/front-open-carry-on-suitcase-with-stopper/",
        "/roomba-mini-vs-switchbot-k11-pro/",
        "/solota-vs-rakua-mini-plus/",
        "/about-ad-policy/",
        "/comparison-policy/",
        "/privacy-policy/",
    ):
        assert f"path: '{path}'" in source
    assert "const widths = [360, 390, 768, 1440];" in source
    assert "response.status() !== 200" in source
    assert "response.url() !== expectedUrl" in source
    assert "audit.contextualLinks < 1" in source
    assert "audit.contextualLinks > 2" in source
    assert "audit.relatedLinks < 2" in source
    assert "results.length !== 56" in source


def test_public_audit_shell_requires_all_56_artifacts_and_is_portable() -> None:
    source = SHELL.read_text(encoding="utf-8")
    assert 'readonly repository_root="$(CDPATH= cd -- "$script_directory/.."' in source
    assert "for name in home carryclassic powerguide" in source
    assert '[ "$#" -eq 56 ]' in source
    assert "/home/minami/rakuten" not in source
    subprocess.run(
        ["/usr/bin/bash", "-n", str(SHELL)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
