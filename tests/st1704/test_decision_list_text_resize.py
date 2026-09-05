"""Legacy decision lists must fit their article column at enlarged text sizes."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def test_native_legacy_decision_rows_fit_their_container_without_hiding_content() -> (
    None
):
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
        pytest.skip(
            "Native Chrome/Node unavailable; local legacy-article check required"
        )
    if not (ROOT / "node_modules/playwright/package.json").is_file():
        pytest.skip("Locked Playwright CLI runtime is not installed")
    assert node is not None and browser is not None
    result = subprocess.run(
        [
            node,
            "-e",
            r"""
const fs=require('fs');const {chromium}=require('playwright');
const theme=process.argv[1];
const css=fs.readFileSync(theme+'/assets/theme.css','utf8')+'\n'+
  fs.readFileSync(theme+'/assets/editorial-v2.css','utf8');
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2],headless:true});
 const out=[];
 try {
  for(const width of [320,360,390,768,1440]) for(const textSize of [100,200]){
   const context=await browser.newContext({viewport:{width,height:900},javaScriptEnabled:false});
   await context.route('**/*',route=>route.abort());
   const page=await context.newPage();
   // A synthetic old four-child row: no fetched article, products or live URLs.
   await page.setContent(`<!doctype html><html lang="ja"><head><meta charset="utf-8">
     <style>body{margin:0}.article-column{margin:16px;width:calc(100% - 32px)}</style><style>${css}</style>
     </head><body class="raos-editorial-v2-page"><main class="raos-editorial-v2 article-column">
     <div class="raos-editorial-v2__main">
     <ul class="decision-list"><li><span class="decision-list__number">01</span>
       <div><small>設置寸法と条件を確認</small><strong>EXAMPLE-123456</strong></div>
       <p class="summary-reason">確認できる条件から選び、購入前に型番を照合します。</p>
       <p class="summary-action"><a class="raos-cta" href="#next">購入前の確認事項を読む<span aria-hidden="true">→</span></a></p>
     </li></ul><section id="next"><h2>購入前の確認</h2></section></div></main></body></html>`);
   await page.evaluate(size=>document.documentElement.style.fontSize=size+'%',textSize);
   const row=await page.evaluate(()=>{
     const list=document.querySelector('.decision-list');const bounds=list.getBoundingClientRect();
     const visible=[...list.querySelectorAll('*')].every(e=>getComputedStyle(e).display!=='none');
     const escaped=[...list.querySelectorAll('*')].filter(e=>{
       const r=e.getBoundingClientRect();return r.width&&(r.left<bounds.left-.5||r.right>bounds.right+.5);
     }).map(e=>e.className||e.tagName);
     return {overflow:document.documentElement.scrollWidth>innerWidth+.5,visible,escaped,
       rowOverflow:getComputedStyle(list.querySelector('li')).overflowX};
   });
   await page.keyboard.press('Tab');
   const focused=await page.evaluate(()=>document.activeElement.matches('.raos-cta'));
   await page.keyboard.press('Enter');await page.waitForURL(url=>url.hash==='#next');
   out.push({width,textSize,...row,focused});await context.close();
  }
 } finally {await browser.close();}
 process.stdout.write(JSON.stringify(out));
})().catch(error=>{console.error(error);process.exit(1);});
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
    observations = json.loads(result.stdout)
    assert len(observations) == 10
    for row in observations:
        assert row["overflow"] is False and row["escaped"] == [], row
        assert row["visible"] is True and row["focused"] is True, row
        assert row["rowOverflow"] == "visible", row
