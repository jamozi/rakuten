"""Keep the shared masthead readable and reachable with 200% text size."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
    / "kurashinoshirube-child/assets/theme.css"
)


def test_mobile_header_reflows_enlarged_text_without_clipping() -> None:
    css = CSS.read_text(encoding="utf-8")
    shared_mobile = css.split("/* Share the compact header", 1)[1].split(
        "@media (max-width: 20rem)", 1
    )[0]
    assert "display: flex;" in shared_mobile
    assert "flex-wrap: wrap;" in shared_mobile
    assert "text-wrap: balance;" in shared_mobile
    assert "white-space: normal;" in shared_mobile
    assert "margin-inline-start: auto;" in shared_mobile
    assert "grid-template-columns:" not in shared_mobile
    assert "overflow:" not in shared_mobile
    assert "text-overflow:" not in shared_mobile
    assert "font-size: 1rem;" in shared_mobile


def test_native_header_layout_hit_targets_and_tab_order_at_text_200_percent() -> None:
    """Synthetic shared block structure; real WP menu/search behavior is separate."""
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
        pytest.skip("Native Chrome/Node unavailable; local WP check remains required")
    if not (ROOT / "node_modules/playwright/package.json").is_file():
        pytest.skip("Locked Playwright CLI runtime is not installed")
    assert node is not None and browser is not None
    result = subprocess.run(
        [
            node,
            "-e",
            r"""
const fs=require('fs');
const { chromium }=require('playwright');
const css=fs.readFileSync(process.argv[1],'utf8');
const theme=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const bodyFont=theme.settings.typography.fontFamilies.find(
  family=>family.slug==='editorial-sans').fontFamily;
const pageClasses=['raos-home-v2-page','raos-editorial-v2-page',
  'raos-policy-v3-page','raos-listing-page','raos-not-found-page'];
(async()=>{
  const browser=await chromium.launch({executablePath:process.argv[2],headless:true});
  const observations=[];
  try {
    for(const width of [360,390,768,1440]) for(const textSize of [100,200]) {
      const context=await browser.newContext({viewport:{width,height:900},serviceWorkers:'block'});
      let blocked=0;
      await context.route('**/*',route=>{blocked++;return route.abort();});
      const page=await context.newPage();
      for(const pageClass of pageClasses){
        // These rules model the shared WP block layout, not its interactive runtime.
        await page.setContent(`<!doctype html><html lang="ja"><head><style>
          body{margin:0;font-family:${bodyFont}}*{box-sizing:border-box}
          a{color:inherit}button{font:inherit;border:0;background:transparent;cursor:pointer}
          p{margin:0}.is-layout-flex{display:flex;align-items:center}.is-nowrap{flex-wrap:nowrap}
          .wp-block-navigation{display:flex;position:relative;align-items:center}
          .wp-block-navigation__container{display:flex;list-style:none;margin:0;padding:0;gap:1rem}
          .wp-block-navigation__responsive-container-open{display:flex;width:2.75rem;height:2.75rem}
          .wp-block-navigation__responsive-container{display:none}
          .wp-block-search__inside-wrapper{display:flex}.wp-block-search{margin:0}
          .screen-reader-text{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
          @media(min-width:600px){.wp-block-navigation__responsive-container-open{display:none}
            .wp-block-navigation__responsive-container{display:block}}
          </style><style>${css}</style></head><body class="${pageClass}">
          <div class="wp-site-blocks"><header><div class="raos-site-header">
            <div class="raos-masthead is-layout-flex is-nowrap">
              <p class="raos-wordmark"><a href="#main">暮らしのしるべ</a></p>
              <div class="raos-masthead__actions is-layout-flex is-nowrap">
                <nav class="raos-primary-nav wp-block-navigation">
                  <button class="wp-block-navigation__responsive-container-open" aria-label="メニューを開く">☰</button>
                  <div class="wp-block-navigation__responsive-container"><ul class="wp-block-navigation__container">
                    <li><a href="#main">目的から探す</a></li>
                    <li><a href="#main">選び方・比較記事</a></li>
                    <li><a href="#main">最近更新したガイド</a></li>
                    <li><a href="#main">このサイトについて</a></li>
                  </ul></div>
                </nav>
                <form class="raos-header-search wp-block-search wp-block-search__searchfield-hidden">
                  <label class="screen-reader-text">記事を検索</label>
                  <div class="wp-block-search__inside-wrapper"><button type="button"
                    class="wp-block-search__button" aria-label="検索欄を開く">⌕</button></div>
                </form>
              </div>
            </div></div></header><main id="main">本文</main></div></body></html>`);
        await page.evaluate(size=>{document.documentElement.style.fontSize=size+'%';},textSize);
        await page.evaluate(()=>document.fonts.ready);
        const observed=await page.evaluate(()=>{
          const brand=document.querySelector('.raos-wordmark a');
          const b=brand.getBoundingClientRect();
          const a=document.querySelector('.raos-masthead__actions').getBoundingClientRect();
          const h=document.querySelector('.raos-masthead').getBoundingClientRect();
          const text=brand.firstChild;
          const lineTops=[];
          for(let index=0;index<text.length;index++){
            const range=document.createRange();range.setStart(text,index);range.setEnd(text,index+1);
            lineTops.push(range.getBoundingClientRect().top);
          }
          return {brand:b.toJSON(),actions:a.toJSON(),header:h.toJSON(),
            overlap:Math.min(b.right,a.right)>Math.max(b.left,a.left)&&
              Math.min(b.bottom,a.bottom)>Math.max(b.top,a.top),
            lineCounts:[...new Set(lineTops)].map(top=>lineTops.filter(y=>y===top).length),
            fontSize:parseFloat(getComputedStyle(brand).fontSize),fonts:document.fonts.status};
        });
        const focus=[];
        await page.keyboard.press('Tab');
        focus.push(await page.evaluate(()=>document.activeElement.closest('.raos-wordmark')!==null));
        await page.keyboard.press('Tab');
        focus.push(await page.evaluate(()=>document.activeElement.closest('.raos-primary-nav')!==null));
        // The browser must dispatch real clicks to these visible native controls.
        await page.evaluate(()=>{window.headerClicks=[];document.addEventListener('click',event=>{
          if(event.target instanceof Element) window.headerClicks.push(event.target.getAttribute('aria-label'));
        });});
        if(width<600) await page.getByRole('button',{name:'メニューを開く'}).click();
        await page.getByRole('button',{name:'検索欄を開く'}).click();
        const clicks=await page.evaluate(()=>window.headerClicks);
        await page.keyboard.press('Shift+Tab');
        const previousInNav=await page.evaluate(()=>document.activeElement.closest('.raos-primary-nav')!==null);
        observations.push({width,textSize,pageClass,...observed,focus,clicks,previousInNav,blocked});
      }
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
        timeout=60,
    )
    observations = json.loads(result.stdout)
    assert len(observations) == 40
    for row in observations:
        assert row["overlap"] is False, row
        assert row["brand"]["right"] <= row["width"] + 0.5, row
        assert row["actions"]["right"] <= row["width"] + 0.5, row
        assert row["brand"]["left"] >= 0, row
        assert len(row["lineCounts"]) <= 2, row
        assert row["focus"] == [True, True] and row["previousInNav"] is True, row
        assert row["clicks"][-1] == "検索欄を開く", row
        assert row["fonts"] == "loaded" and row["blocked"] == 0, row
        if row["width"] < 600:
            assert min(row["lineCounts"]) >= 3, row
            assert row["clicks"] == ["メニューを開く", "検索欄を開く"], row
            assert row["fontSize"] == 16 * row["textSize"] / 100, row
            if row["textSize"] == 200:
                assert row["actions"]["top"] >= row["brand"]["bottom"], row
            else:
                assert len(row["lineCounts"]) == 1, row
                assert row["header"]["height"] <= 80, row
