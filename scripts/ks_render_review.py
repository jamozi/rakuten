#!/usr/bin/env python3
"""Render a Before/After review page from scripts/ks_before_after.py output.

Usage: ks_render_review.py <out-dir> [label] [before-origin] [after-origin]
Images are referenced by relative path (open review.html next to the PNG files).
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

PYTHON = Path(__file__).resolve().parents[1] / "python"


def refuse_while_price_overlay_live(*checkouts: str | Path | None) -> None:
    """Contract §8: do not republish a Before/After directory while values are published.

    The input directory is what ``scripts/ks_before_after.py`` wrote: full-page renderings of
    the injected pages and the candidate id. This script embeds every one of those PNGs in a
    single reviewer-facing ``review.html`` inside the repository, which the §5 purge sweep does
    not reach, so it is refused for the same reason the capture is.
    """
    if str(PYTHON) not in sys.path:
        sys.path.insert(0, str(PYTHON))
    from raos.adapters.price_overlay_live_guard import price_overlay_refusal

    code = price_overlay_refusal(*checkouts)
    if code is not None:
        print(code, file=sys.stderr)
        raise SystemExit(69)


def read_index(out: Path) -> list[tuple[str, ...]]:
    rows = []
    for line in (out / "index.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| `([^`]+)` \| `([^`]+)` \| (-\d+ / \+\d+) \| (\S+) \|", line)
        if m:
            rows.append(m.groups())
    return rows


def main() -> int:
    # Before reading index.md and before writing review.html.
    refuse_while_price_overlay_live()
    out = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else out.name
    before_origin = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:41398"
    after_origin = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:42429"
    rows = read_index(out)

    def img(name: str) -> str:
        if not (out / name).is_file():
            return "<div class='missing'>（画像なし）</div>"
        return f"<a href='{html.escape(name)}'><img loading='lazy' src='{html.escape(name)}' alt='{html.escape(name)}'></a>"

    parts = [
        "<!doctype html><meta charset='utf-8'><title>Before / After " + html.escape(label) + "</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:16px;color:#17243f}h2{margin-top:40px;border-top:2px solid #ddd;padding-top:12px}"
        ".pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pair>div{border:1px solid #ccc;padding:6px;background:#fafafa}"
        ".pair h4{margin:0 0 6px;font-size:14px}.pair img{max-width:100%;border:1px solid #eee}"
        "pre{background:#f4f4f4;padding:10px;overflow:auto;font-size:12px;max-height:420px}.del{color:#a11}.add{color:#161}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px}.missing{color:#999}"
        "details summary{cursor:pointer;font-weight:600}</style>",
        f"<h1>Before / After — {html.escape(label)}</h1>",
        f"<p>Before = 本番相当のローカル preview (<code>{html.escape(before_origin)}</code>) / After = 公開候補の preview (<code>{html.escape(after_origin)}</code>)。"
        "画像は全ページ縦長のスクリーンショット (390px / 1440px)。差分は可視テキストの unified diff (- が Before、+ が After)。</p>",
        "<table><tr><th>記事</th><th>URL</th><th>可視テキスト -/+</th><th>内部語 before→after</th></tr>",
    ]
    for key, path, delta, tokens in rows:
        parts.append(
            f"<tr><td><a href='#{html.escape(key)}'>{html.escape(key)}</a></td><td><a href='{html.escape(after_origin + path)}'>{html.escape(path)}</a></td>"
            f"<td>{html.escape(delta)}</td><td>{html.escape(tokens)}</td></tr>"
        )
    parts.append("</table>")
    for key, path, delta, tokens in rows:
        parts.append(f"<h2 id='{html.escape(key)}'>{html.escape(key)} <small>{html.escape(path)}</small></h2>")
        parts.append(
            f"<p>After をローカルで開く: <a href='{html.escape(after_origin + path)}'>{html.escape(after_origin + path)}</a> ／ "
            f"Before: <a href='{html.escape(before_origin + path)}'>{html.escape(before_origin + path)}</a></p>"
        )
        diff_file = out / f"{key}.text.diff"
        diff = diff_file.read_text(encoding="utf-8") if diff_file.is_file() else ""
        body = "".join(
            f"<span class='del'>{html.escape(line)}</span>\n"
            if line.startswith("-") and not line.startswith("---")
            else f"<span class='add'>{html.escape(line)}</span>\n"
            if line.startswith("+") and not line.startswith("+++")
            else html.escape(line) + "\n"
            for line in diff.splitlines()
        )
        parts.append(
            f"<details open><summary>可視テキスト差分 ({html.escape(delta)})</summary><pre>"
            f"{body or '(差分なし: アンカー・見出しタグなど非表示の変更のみ)'}</pre></details>"
        )
        parts.append("<h3>390px</h3><div class='pair'><div><h4>Before</h4>" + img(f"{key}-390-before.png") + "</div><div><h4>After</h4>" + img(f"{key}-390-after.png") + "</div></div>")
        parts.append("<h3>1440px</h3><div class='pair'><div><h4>Before</h4>" + img(f"{key}-1440-before.png") + "</div><div><h4>After</h4>" + img(f"{key}-1440-after.png") + "</div></div>")
    (out / "review.html").write_text("\n".join(parts), encoding="utf-8")
    print("wrote", out / "review.html", (out / "review.html").stat().st_size // 1024, "KB", "rows", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
