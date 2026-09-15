#!/usr/bin/env python3
"""Before/After evidence for a KS batch: visible-text diffs and two-width screenshots.

Ad-hoc review helper (not a generator owner). For each article key it writes

* ``<key>.text.diff``   unified diff of the reader-visible text, base ref vs working tree
* ``<key>-<width>-before.png`` captured from a running local WordPress (the current
  production-equivalent preview) with the tracked ``preview-browser.mjs``
* ``<key>-<width>-after.png`` copied from an owner-direct candidate's screenshot set
* ``index.md`` linking everything for the reviewer

Nothing here touches production or Git history.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = "changes/wordpress-direct-publish-v1/articles"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
BROWSER = "changes/wordpress-direct-publish-v1/preview-browser.mjs"
TOKENS = re.compile(r"\b(?:UNKNOWN|UNAVAILABLE|SOLD_OUT|PREORDER)\b|本文候補|レビュー中")


def visible_text(html: str) -> list[str]:
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(script|style|template)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"</(p|li|h[1-6]|tr|div|section|article|dt|dd|caption|figcaption)>", "\n", html)
    html = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'")
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return [line for line in lines if line]


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def ledger_rows() -> dict[str, dict]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    return {row["article_key"]: row for row in ledger["articles"]}


def surface_path(row: dict) -> str:
    return "/" if row["post_type"] == "page" and row["slug"] == "home" else "/" + row["slug"] + "/"


def capture_before(keys: list[str], rows: dict[str, dict], origin: str, out: Path, owner_root: Path) -> dict:
    """Run the tracked preview browser against the running local WordPress."""
    shots = out / "_before-raw"
    shots.mkdir(parents=True, exist_ok=True)
    surfaces = [{"kind": "home" if surface_path(rows[k]) == "/" else "article", "path": surface_path(rows[k])} for k in keys]
    plan = {"origin": origin, "widths": [390, 1440], "surfaces": surfaces, "screenshots": str(shots), "images": {}}
    plan_file = out / "_before-input.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    script = owner_root / BROWSER
    result = subprocess.run(["node", str(script), str(plan_file)], cwd=owner_root, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise SystemExit(f"BEFORE_CAPTURE_FAILED\n{result.stdout}\n{result.stderr}")
    report = json.loads(result.stdout.strip().splitlines()[-1])
    for index, key in enumerate(keys):
        kind = surfaces[index]["kind"]
        for width in (390, 1440):
            source = shots / f"{index}-{kind}-{width}.png"
            if source.is_file():
                shutil.copy(source, out / f"{key}-{width}-before.png")
    return report


def copy_after(keys: list[str], rows: dict[str, dict], candidate_dir: Path, out: Path) -> dict[str, list[str]]:
    browser_input = json.loads((candidate_dir / "browser-input.json").read_text(encoding="utf-8"))
    surfaces = browser_input["surfaces"]
    copied: dict[str, list[str]] = {}
    for key in keys:
        path = surface_path(rows[key])
        for index, surface in enumerate(surfaces):
            if surface["path"] != path:
                continue
            for width in (390, 1440):
                source = candidate_dir / "screenshots" / f"{index}-{surface['kind']}-{width}.png"
                if source.is_file():
                    target = out / f"{key}-{width}-after.png"
                    shutil.copy(source, target)
                    copied.setdefault(key, []).append(target.name)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keys", required=True, help="comma separated article keys")
    parser.add_argument("--base-ref", default="codex/all-pages-improvements-20260913")
    parser.add_argument("--before-origin", default=None, help="running local WordPress, e.g. http://127.0.0.1:41398")
    parser.add_argument("--candidate", default=None, help="owner-direct candidate id whose screenshots are the After")
    parser.add_argument("--owner-checkout", default="/home/minami/rakuten")
    parser.add_argument("--out", default="output/ks-20260915")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    rows = ledger_rows()
    unknown = [k for k in keys if k not in rows]
    if unknown:
        raise SystemExit(f"UNKNOWN_KEYS {unknown}")
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    owner_root = Path(args.owner_checkout)

    summary = []
    for key in keys:
        path = rows[key].get("body_source") or ""
        before = visible_text(git_show(args.base_ref, path)) if path else []
        after = visible_text((ROOT / path).read_text(encoding="utf-8")) if path else []
        diff = list(difflib.unified_diff(before, after, f"{args.base_ref}:{path}", f"worktree:{path}", lineterm="", n=1))
        (out / f"{key}.text.diff").write_text("\n".join(diff) + "\n", encoding="utf-8")
        summary.append(
            {
                "key": key,
                "path": surface_path(rows[key]),
                "removed": sum(1 for line in diff if line.startswith("-") and not line.startswith("---")),
                "added": sum(1 for line in diff if line.startswith("+") and not line.startswith("+++")),
                "tokens_before": sum(len(TOKENS.findall(line)) for line in before),
                "tokens_after": sum(len(TOKENS.findall(line)) for line in after),
            }
        )

    before_report = None
    if args.before_origin:
        before_report = capture_before(keys, rows, args.before_origin, out, owner_root)
    after_copied: dict[str, list[str]] = {}
    if args.candidate:
        candidate_dir = owner_root / ".secrets/wordpress-mcp/owner-direct-v1" / args.candidate
        if not candidate_dir.is_dir():
            raise SystemExit(f"CANDIDATE_DIR_MISSING {candidate_dir}")
        after_copied = copy_after(keys, rows, candidate_dir, out)

    lines = [f"# Before / After {args.label}".rstrip(), ""]
    lines.append(f"- base: `{args.base_ref}` / worktree: `{ROOT}`")
    if args.before_origin:
        lines.append(f"- Before 画面: `{args.before_origin}` (稼働中のローカル WordPress) / 判定: {before_report and before_report.get('status')} {before_report and before_report.get('failures')}")
    if args.candidate:
        lines.append(f"- After 画面: candidate `{args.candidate}` の preview screenshots")
    lines += ["", "| key | path | 可視テキスト -/+ | 内部語 before→after | 390px | 1440px | diff |", "| --- | --- | ---: | ---: | --- | --- | --- |"]
    for item in summary:
        key = item["key"]
        cells = []
        for width in (390, 1440):
            b = f"{key}-{width}-before.png"
            a = f"{key}-{width}-after.png"
            parts = []
            if (out / b).is_file():
                parts.append(f"[before]({b})")
            if (out / a).is_file():
                parts.append(f"[after]({a})")
            cells.append(" / ".join(parts) or "-")
        lines.append(
            f"| `{key}` | `{item['path']}` | -{item['removed']} / +{item['added']} | {item['tokens_before']}→{item['tokens_after']} | {cells[0]} | {cells[1]} | [diff]({key}.text.diff) |"
        )
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "articles": len(summary), "before": bool(before_report), "after": sorted(after_copied)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
