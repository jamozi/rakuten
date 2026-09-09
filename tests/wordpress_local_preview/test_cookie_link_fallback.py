"""A saved footer remains navigable when the CookieYes UI is unavailable."""
from pathlib import Path
import re
import subprocess


def test_saved_cookie_link_has_a_real_fallback_without_changing_consent():
    root = Path(__file__).resolve().parents[2]
    source = (root / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php").read_text()
    match = re.search(r"function kurashinoshirube_cookie_link_fallback\(.*?\n\}", source, re.S)
    assert match is not None
    code = match.group() + '''
$original = '<p><a href="#cookie-settings" class="cky-banner-element">Cookie設定を変更</a></p>';
$result = kurashinoshirube_cookie_link_fallback($original);
if ($result !== '<p><a href="/privacy-policy/" class="cky-banner-element">Cookie・個人情報の取り扱い</a></p>') { exit(1); }
if (kurashinoshirube_cookie_link_fallback($result) !== $result) { exit(2); }
$other = '<a href="#different">別のリンク</a>';
if (kurashinoshirube_cookie_link_fallback($other) !== $other) { exit(3); }
echo 'PASS';
'''
    result = subprocess.run([str(root / "scripts/test-runtime-bin/php"), "-r", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "PASS"
