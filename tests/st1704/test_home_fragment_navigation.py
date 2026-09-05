"""Native cross-document fragments must not use placeholder section heights."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
    / "kurashinoshirube-child/assets/theme.css"
)


def test_home_fragment_layout_never_uses_placeholder_heights() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "content-visibility:" not in css
    assert "contain-intrinsic-size:" not in css
    assert "scroll-margin-top: 6rem;" in css
    assert re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*"
        r"scroll-behavior:\s*auto",
        css,
    )


def test_native_cross_page_hash_and_tab_after_fonts_ready_and_delayed_image() -> None:
    """No live WordPress, network provider, timers that re-scroll, or JS fix."""
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
            "Native Chrome/Node unavailable; local browser check is still required"
        )
    if not (ROOT / "node_modules/playwright/package.json").is_file():
        pytest.skip("Locked Playwright CLI runtime is not installed")
    assert node is not None and browser is not None
    result = subprocess.run(
        [
            node,
            "-e",
            r"""
const fs = require('fs');
const { chromium } = require('playwright');
const css = fs.readFileSync(process.argv[1], 'utf8');
const theme = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const bodyFont = theme.settings.typography.fontFamilies.find(
  family => family.slug === 'editorial-sans').fontFamily;
(async () => {
  const browser = await chromium.launch({executablePath:process.argv[2], headless:true});
  const observations=[];
  try {
    for (const width of [360,1440]) for (const reducedMotion of ['reduce','no-preference']) {
      const context=await browser.newContext({viewport:{width,height:900},reducedMotion});
      const page=await context.newPage();
      let blocked=0;
      const origin='http://127.0.0.1:48999';
      await context.route('**/*',async route=>{
        const url=new URL(route.request().url());
        if (url.origin!==origin) {blocked++;return route.abort();}
        if (url.pathname==='/style.css') return route.fulfill({contentType:'text/css',body:css});
        if (url.pathname==='/late.svg') {
          await new Promise(resolve=>setTimeout(resolve,350));
          return route.fulfill({contentType:'image/svg+xml',body:
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"><rect width="800" height="450" fill="#24365f"/></svg>'});
        }
        const paragraphs=Array.from({length:12},()=>'<p>条件を確認して比較する。 Compare the dimensions and requirements before choosing.</p>').join('');
        const sections=Array.from({length:8},(_,index)=>
          `<section class="raos-home-section" style="padding:32px"><h2>比較 ${index}</h2>${paragraphs}
          <img src="/late.svg" loading="lazy" width="800" height="450" alt="比較図"></section>`).join('');
        const home=`<main class="raos-home-v2"><section class="raos-home-hero" style="height:500px">案内</section>${sections}
          <section id="about" class="raos-home-about raos-home-section" style="min-height:1100px;padding:32px">
          <h2>このサイトについて</h2><a href="/policy/">運営方針</a></section></main>`;
        return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ja"><head>
          <link rel="stylesheet" href="/style.css"><style>body{margin:0}header{position:fixed;inset:0 0 auto;height:73px;z-index:2;background:white}
          p{line-height:1.8}.raos-home-v2{font-family:${bodyFont}}</style></head><body><header>暮らしのしるべ</header>
          ${url.pathname==='/category/'?'<main style="padding-top:100px"><a id="jump" href="/#about">このサイトについて</a></main>':home}</body></html>`});
      });
      await page.goto(`${origin}/category/`);
      await page.locator('#jump').click();
      await page.waitForURL(`${origin}/#about`);
      await page.evaluate(()=>document.fonts.ready);
      await page.waitForTimeout(1800);
      const before=await page.locator('#about').evaluate(node=>node.getBoundingClientRect().top);
      await page.keyboard.press('Tab');
      const observed=await page.evaluate(()=>({
        top:document.getElementById('about').getBoundingClientRect().top,
        within:document.getElementById('about').contains(document.activeElement),
        focus:document.activeElement.getAttribute('href'),fonts:document.fonts.status,
        scrollBehavior:getComputedStyle(document.documentElement).scrollBehavior,
        loadedImages:[...document.images].filter(image=>image.complete&&image.naturalWidth>0).length,
      }));
      observations.push({width,reducedMotion,before,blocked,...observed});
      await context.close();
    }
  } finally {await browser.close();}
  process.stdout.write(JSON.stringify(observations));
})().catch(error=>{console.error(error);process.exit(1);});
""",
            str(CSS),
            str(browser),
            str(CSS.parent.parent / "theme.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )
    observations = json.loads(result.stdout)
    assert len(observations) == 4
    for row in observations:
        assert 73 <= row["before"] <= 110, row
        assert 73 <= row["top"] <= 110, row
        assert row["within"] is True and row["focus"] == "/policy/", row
        assert row["fonts"] == "loaded" and row["loadedImages"] > 0, row
        assert row["blocked"] == 0, row
        if row["reducedMotion"] == "reduce":
            assert row["scrollBehavior"] == "auto", row
