"""The native header fallback must work without executing page scripts."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def test_nojs_header_uses_existing_navigation_and_a_native_search_form() -> None:
    header = (THEME / "parts/header.html").read_text(encoding="utf-8")
    fallback = re.search(r"<noscript\b[\s\S]*?</noscript>", header)
    assert fallback is not None
    markup = fallback.group()
    assert 'role="search" method="get" action="/"' in markup
    assert '<label for="raos-header-nojs-query">記事を検索</label>' in markup
    assert 'id="raos-header-nojs-query" type="search" name="s"' in markup
    assert '<button type="submit">検索</button>' in markup
    assert not re.search(r"<(?:script|style|nav)\b|aria-hidden|onclick", markup)
    assert header.count("<!-- wp:navigation-link ") == 4
    assert header.count("<!-- wp:search ") == 1
    css = (THEME / "assets/theme.css").read_text(encoding="utf-8")
    assert ".raos-header-nojs-shell {\n  display: none;\n}" in css
    assert ".raos-header-nojs-shell:has(.raos-header-nojs)" in css
    assert ".wp-site-blocks > header:has(.raos-site-header .raos-header-nojs)" in css


def test_native_nojs_navigation_search_accessibility_and_scripted_isolation() -> None:
    """Real Chrome, synthetic WP block chrome, no provider or live WP needed."""
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
        pytest.skip("Native Chrome/Node unavailable; local no-JS WP check is required")
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
const theme=process.argv[1];
const css=fs.readFileSync(theme+'/assets/theme.css','utf8');
const header=fs.readFileSync(theme+'/parts/header.html','utf8');
const fallback=header.match(/<noscript\b[\s\S]*?<\/noscript>/)[0];
const links=[...header.matchAll(/<!-- wp:navigation-link (\{.*?\}) \/-->/g)]
  .map(match=>JSON.parse(match[1]));
const bodyFont=JSON.parse(fs.readFileSync(theme+'/theme.json','utf8'))
  .settings.typography.fontFamilies.find(font=>font.slug==='editorial-sans').fontFamily;
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2],headless:true});
 const observations=[];
 try {
  for(const width of [320,360,390,768,1440]) for(const textSize of [100,200])
   for(const javaScriptEnabled of [false,true]) for(const home of [false,true]) {
    const context=await browser.newContext({viewport:{width,height:900},javaScriptEnabled,
      serviceWorkers:'block',reducedMotion:'reduce'});
    const origin='http://127.0.0.1:48998';let blocked=0;
    await context.route('**/*',route=>{
      const request=route.request();const url=new URL(request.url());
      if(url.origin!==origin||request.method()!=='GET'){blocked++;return route.abort();}
      if(url.pathname.endsWith('.svg')) return route.fulfill({contentType:'image/svg+xml',
        body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"/>'});
      return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ja"
        style="font-size:${textSize}%"><head><meta charset="utf-8"><style>
        body{margin:0;font-family:${bodyFont}}*{box-sizing:border-box}p{margin:0}
        .is-layout-flex{display:flex;align-items:center}.is-nowrap{flex-wrap:nowrap}
        .wp-block-navigation__responsive-container{display:none}
        .wp-block-navigation__responsive-container-open{display:flex;width:2.75rem;height:2.75rem}
        .wp-block-navigation__responsive-container-close{display:none}
        .wp-block-navigation__container{display:flex;margin:0;padding:0;list-style:none}
        .wp-block-search__searchfield-hidden input{display:none}
        @media(min-width:600px){.wp-block-navigation__responsive-container{display:block}
          .wp-block-navigation__responsive-container-open{display:none}}
        </style><style>${css}</style></head>
        <body class="${home?'raos-home-v2-page':'raos-editorial-v2-page'}"><div class="wp-site-blocks">
        <header><div class="raos-site-header"><div class="raos-masthead is-layout-flex is-nowrap">
        <p class="raos-wordmark"><a href="/">暮らしのしるべ</a></p>
        <div class="raos-masthead__actions is-layout-flex is-nowrap">
        <nav class="raos-primary-nav wp-block-navigation" aria-label="主要ナビゲーション">
        <button class="wp-block-navigation__responsive-container-open" aria-label="メニューを開く">☰</button>
        <div class="wp-block-navigation__responsive-container">
        <button class="wp-block-navigation__responsive-container-close" aria-label="メニューを閉じる">閉</button>
        <ul class="wp-block-navigation__container">${links.map(link=>
          `<li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content"
           href="${link.url}">${link.label}</a></li>`).join('')}</ul></div></nav>
        <form class="raos-header-search wp-block-search wp-block-search__searchfield-hidden">
        <input type="search" aria-hidden="true"><button type="button"
        class="wp-block-search__button" aria-label="検索欄を開く">⌕</button></form>
        </div>${fallback}</div></div></header>
        <main>${links.map(link=>`<section id="${link.url.slice(2)}" style="min-height:1100px">
          <h2>${link.label}</h2><a href="/policy/">方針</a></section>`).join('')}</main>
        </div></body></html>`});
    });
    const page=await context.newPage();await page.goto(origin+'/article/');
    const banner=page.getByRole('banner');
    const original=await page.evaluate(()=>({
      fallback:!!document.querySelector('.raos-header-nojs'),
      overflow:document.documentElement.scrollWidth>innerWidth+.5,
      headerHeight:document.querySelector('header').getBoundingClientRect().height,
      headerPosition:getComputedStyle(document.querySelector('header')).position,
      rawMarkupVisible:document.querySelector('header').innerText.includes('<form'),
    }));
    if(!javaScriptEnabled){
      const names=[];
      for(let index=0;index<7;index++){
        await page.keyboard.press('Tab');names.push(await page.evaluate(()=>{
          const active=document.activeElement;return active.tagName==='INPUT'?active.id:active.textContent.trim();
        }));
      }
      if(names.join('|')!=='暮らしのしるべ|'+links.map(link=>link.label).join('|')+
        '|raos-header-nojs-query|検索') throw Error('Incorrect native tab order: '+names);
      if(await banner.getByRole('button',{name:'メニューを開く'}).isVisible()) throw Error('Dead menu');
      if(await banner.getByRole('button',{name:'検索欄を開く'}).isVisible()) throw Error('Dead search');
      const cdp=await context.newCDPSession(page);
      const {nodes}=await cdp.send('Accessibility.getFullAXTree');
      if(!nodes.some(n=>!n.ignored&&n.role?.value==='searchbox'&&n.name?.value==='記事を検索'))
        throw Error('Search is missing from the native accessibility tree');
      for(const link of links){
        await banner.getByRole('link',{name:link.label,exact:true}).click();
        await page.waitForURL(origin+link.url);
        const top=await page.locator(link.url.slice(1)+' h2').evaluate(e=>e.getBoundingClientRect().top);
        if(top < -0.5||top>=900) throw Error('Native fragment heading is not visible: '+
          JSON.stringify({width,textSize,home,link,top}));
      }
      await banner.getByRole('searchbox',{name:'記事を検索'}).fill('比較');
      await banner.getByRole('button',{name:'検索',exact:true}).click();
      await page.waitForURL(url=>url.searchParams.get('s')==='比較');
      await banner.getByRole('searchbox',{name:'記事を検索'}).fill('選び方');
      await page.keyboard.press('Enter');
      await page.waitForURL(url=>url.searchParams.get('s')==='選び方');
    } else {
      if(await banner.getByRole('button',{name:'検索',exact:true}).count()) throw Error('Fallback visible with JS');
      if(!(await banner.getByRole('button',{name:'検索欄を開く'}).isVisible())) throw Error('Normal search missing');
    }
    observations.push({width,textSize,javaScriptEnabled,home,...original,blocked});
    await context.close();
   }
 } finally {await browser.close();}
 process.stdout.write(JSON.stringify(observations));
})().catch(error=>{console.error(error);process.exit(1);});
""",
            str(THEME),
            str(browser),
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
        assert row["overflow"] is False, row
        assert row["blocked"] == 0, row
        assert row["rawMarkupVisible"] is False, row
        assert row["fallback"] is not row["javaScriptEnabled"], row
        if not row["javaScriptEnabled"]:
            assert row["headerPosition"] == "static", row
        elif row["width"] < 600 and row["textSize"] == 100:
            assert row["headerHeight"] <= 80, row
