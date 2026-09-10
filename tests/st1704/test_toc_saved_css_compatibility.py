"""The article TOC keeps its responsive controls beside saved site CSS."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
    / "kurashinoshirube-child"
)


def test_saved_mobile_toc_css_does_not_override_the_desktop_controls() -> None:
    node = shutil.which("node")
    browser = next(
        (
            path
            for path in (
                Path("/opt/google/chrome/chrome"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/chromium-browser"),
            )
            if path.is_file()
        ),
        None,
    )
    if node is None or browser is None:
        pytest.skip("Native Chrome/Node unavailable; local TOC check required")
    if not (ROOT / "node_modules/playwright/package.json").is_file():
        pytest.skip("Locked Playwright runtime is not installed")
    result = subprocess.run(
        [
            node,
            "-e",
            r"""
const fs=require('fs');const {chromium}=require('playwright');
const css=fs.readFileSync(process.argv[1]+'/assets/editorial-v2.css','utf8');
const saved=`
body .raos-editorial-v2 .raos-article-toc summary{display:list-item!important}
body .raos-editorial-v2 .raos-article-toc__title{display:none!important}
body .raos-editorial-v2 .raos-article-toc details:not([open])>:not(summary){display:none!important}`;
(async()=>{const browser=await chromium.launch({executablePath:process.argv[2],headless:true});const out=[];
try{for(const width of [390,1440]){const context=await browser.newContext({viewport:{width,height:900}});
 const page=await context.newPage();await page.setContent(`<!doctype html><html lang="ja"><head>
 <style>${saved}</style><style>${css}</style></head><body class="single-post raos-editorial-v2-page">
 <main class="raos-editorial-v2"><nav id="raos-article-toc" class="raos-article-toc">
 <p class="raos-article-toc__title">この記事の目次</p><details ${width>1024?'open':''}>
 <summary>この記事の目次</summary><ol><li><a href="#section">選び方</a></li></ol></details></nav>
 <section id="section"><h2>選び方</h2></section></main></body></html>`);
 await page.keyboard.press('Tab');
 const before=await page.evaluate(()=>{const visible=element=>{const style=getComputedStyle(element);
  const box=element.getBoundingClientRect();return style.display!=='none'&&style.visibility!=='hidden'&&box.width>0&&box.height>0};
  const title=document.querySelector('.raos-article-toc__title');
  const summary=document.querySelector('.raos-article-toc summary');const list=document.querySelector('.raos-article-toc ol');
  return {titleVisible:visible(title),summaryVisible:visible(summary),listVisible:visible(list),
   focus:document.activeElement.tagName.toLowerCase()};});
 if(width===390){await page.keyboard.press('Enter');}
 const detailsOpen=await page.locator('.raos-article-toc details').evaluate(node=>node.open);
 out.push({width,...before,detailsOpen});await context.close();}}
finally{await browser.close();}process.stdout.write(JSON.stringify(out));
})().catch(error=>{console.error(error);process.exit(1)});
""",
            str(THEME),
            str(browser),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    observations = {row["width"]: row for row in json.loads(result.stdout)}
    assert observations[1440] == {
        "width": 1440,
        "titleVisible": True,
        "summaryVisible": False,
        "listVisible": True,
        "focus": "a",
        "detailsOpen": True,
    }
    assert observations[390] == {
        "width": 390,
        "titleVisible": False,
        "summaryVisible": True,
        "listVisible": False,
        "focus": "summary",
        "detailsOpen": True,
    }
