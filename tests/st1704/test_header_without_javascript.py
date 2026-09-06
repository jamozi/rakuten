"""Native header controls remain usable until both core blocks initialize."""

from __future__ import annotations

import json
from itertools import product
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
    fallback = re.search(
        r'(<details class="wp-block-details raos-header-nojs-shell">[\s\S]*?</details>)',
        header,
    )
    assert fallback is not None
    markup = fallback.group(1)
    assert 'role="search" method="get" action="/"' in markup
    assert '<label for="raos-header-nojs-query">記事を検索</label>' in markup
    assert 'id="raos-header-nojs-query" type="search" name="s"' in markup
    assert '<button type="submit">検索</button>' in markup
    assert not re.search(r"<(?:noscript|script|style)\b|onclick", markup)
    form = re.search(r"<form\b[\s\S]*?</form>", markup)
    assert form is not None and "aria-hidden" not in form.group()
    assert "メニューと検索" in markup
    links = [json.loads(match) for match in re.findall(r'<!-- wp:navigation-link (\{.*?\}) /-->', header)]
    links = list({link["url"]: link for link in links}.values())
    registry = json.loads((THEME / 'assets/editorial-navigation.v3.json').read_text())
    hub_paths = {'/' + hub['slug'] + '/' for hub in registry['reader_navigation']['hubs']}
    assert links and all(link['url'] in hub_paths for link in links)
    assert header.count("<!-- wp:search ") == 1


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
const links=[...new Map([...header.matchAll(/<!-- wp:navigation-link (\{.*?\}) \/-->/g)]
  .map(match=>JSON.parse(match[1])).map(link=>[link.url,link])).values()];
const navigationItems=links.map(link=>`<li class="wp-block-navigation-item">
  <a class="wp-block-navigation-item__content" href="${link.url}">${link.label}</a></li>`).join('');
// Retain the complete native details; model only its WP navigation block rendering.
const fallback=header.match(/<details class="wp-block-details raos-header-nojs-shell">[\s\S]*?<\/details>/)[0]
  .replace(/<!-- wp:navigation \{.*?\} -->[\s\S]*?<!-- \/wp:navigation -->/,
    `<nav class="raos-native-links wp-block-navigation" aria-label="サイト内ナビゲーション">
    <ul class="wp-block-navigation__container">${navigationItems}</ul></nav>`);
const bodyFont=JSON.parse(fs.readFileSync(theme+'/theme.json','utf8'))
  .settings.typography.fontFamilies.find(font=>font.slug==='editorial-sans').fontFamily;
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2],headless:true});
 const observations=[];
 try {
  const cases=[];
  for(const width of [320,360,390,768,1024,1440]) for(const textSize of [100,200])
   for(const javaScriptEnabled of [false,true]) for(const home of [false,true])
    cases.push({width,textSize,javaScriptEnabled,home,
      readiness:javaScriptEnabled?'both':'none',representativeFailure:false});
  // Synthetic initialized states exercise CSS behavior, not real core initialization.
  // Only three representative JS-enabled failures supplement the original 96 cases.
  for(const readiness of ['none','nav-only','search-only'])
   cases.push({width:390,textSize:100,javaScriptEnabled:true,home:false,
     readiness,representativeFailure:true});
  // Overlap actionability/frame waits with at most two independent contexts.
  // Keep real clicks, scroll stability checks, and the shared 60-second deadline.
  await Promise.all([0,1].map(async worker=>{
   for(let index=worker;index<cases.length;index+=2) {
    const {width,textSize,javaScriptEnabled,home,readiness,representativeFailure}=cases[index];
    const nativeFallback=readiness!=='both';
    const navReady=['both','nav-only'].includes(readiness)?' data-raos-nav-ready="false"':'';
    const searchReady=['both','search-only'].includes(readiness)?' data-raos-search-ready="button"':'';
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
        .is-layout-flex > :is(*,div){margin:0}
        .wp-block-navigation__responsive-container{display:none}
        .wp-block-navigation__responsive-container-open{display:flex;width:2.75rem;height:2.75rem}
        .wp-block-navigation__responsive-container-close{display:none}
        .wp-block-navigation__container{display:flex;margin:0;padding:0;list-style:none}
        .wp-block-search__searchfield-hidden input{display:none}
        .screen-reader-text{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
        @media(min-width:600px){.wp-block-navigation__responsive-container{display:block}
          .wp-block-navigation__responsive-container-open{display:none}}
        </style><style>${css}</style></head>
        <body class="${home?'raos-home-v2-page':'raos-editorial-v2-page'}"><div class="wp-site-blocks">
        <header><div class="raos-site-header"><div class="raos-masthead is-layout-flex is-nowrap">
        <p class="raos-wordmark"><a href="/">暮らしのしるべ</a></p>
        <div class="raos-masthead__actions is-layout-flex is-nowrap">
        <nav class="raos-primary-nav wp-block-navigation" aria-label="主要ナビゲーション"${navReady}>
        <button class="wp-block-navigation__responsive-container-open" aria-label="メニューを開く">☰</button>
        <div class="wp-block-navigation__responsive-container">
        <button class="wp-block-navigation__responsive-container-close" aria-label="メニューを閉じる">閉</button>
        <ul class="wp-block-navigation__container">${navigationItems}</ul></div></nav>
        <form class="raos-header-search wp-block-search wp-block-search__searchfield-hidden"${searchReady}>
        <input type="search" aria-hidden="true"><button type="button"
        class="wp-block-search__button" aria-label="検索欄を開く">⌕</button></form>
        </div>${fallback}</div></div></header>
        <main><h1>${links.find(link=>link.url===url.pathname)?.label||'記事'}</h1>
          <a href="/policy/">方針</a></main>
        </div></body></html>`});
    });
    const page=await context.newPage();await page.goto(origin+'/article/');
    const banner=page.getByRole('banner');
    const original=await page.evaluate(()=>({
      fallbackPresent:!!document.querySelector('header details.raos-header-nojs-shell > .raos-header-nojs > form'),
      fallback:document.querySelector('.raos-header-nojs-shell').getClientRects().length>0,
      initiallyOpen:document.querySelector('.raos-header-nojs-shell').open,
      overflow:document.documentElement.scrollWidth>innerWidth+.5,
      headerHeight:document.querySelector('header').getBoundingClientRect().height,
      rawMarkupVisible:document.querySelector('header').innerText.includes('<form'),
    }));
    let nativePageScrollY=0;
    if(nativeFallback){
      const details=banner.locator('details.raos-header-nojs-shell');
      const summary=details.locator('summary');
      const panel=details.locator('.raos-header-nojs');
      const openNative=async()=>{
        if(!(await details.evaluate(element=>element.open))){
          await summary.focus();await page.keyboard.press('Enter');
        }
        if(!(await details.evaluate(element=>element.open))) throw Error('Native summary did not open');
      };
      const focusedName=()=>page.evaluate(()=>{
        const active=document.activeElement;const rect=active.getBoundingClientRect();
        if(rect.width<=0||rect.height<=0||rect.left<-.5||rect.right>innerWidth+.5||
          rect.top<-.5||rect.bottom>innerHeight+.5||
          !active.contains(document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2)))
          throw Error('Native keyboard focus is clipped or covered: '+JSON.stringify({
            tag:active.tagName,rect:rect.toJSON(),scrollY}));
        return active.tagName==='INPUT'?active.id:active.textContent.trim();
      });
      const names=[];
      for(let index=0;index<2;index++){
        await page.keyboard.press('Tab');names.push(await focusedName());
      }
      if(names.join('|')!=='暮らしのしるべ|メニューと検索') throw Error('Incorrect closed header tab order: '+names);
      await openNative();
      for(let index=0;index<links.length+2;index++){
        await page.keyboard.press('Tab');names.push(await focusedName());
      }
      if(names.join('|')!=='暮らしのしるべ|メニューと検索|'+links.map(link=>link.label).join('|')+
        '|raos-header-nojs-query|検索') throw Error('Incorrect native tab order: '+names);
      const panelState=await panel.evaluate(element=>{
        const rect=element.getBoundingClientRect();
        const target=element.parentElement.querySelector('summary').getBoundingClientRect();
        return {left:rect.left,right:rect.right,
          panelPosition:getComputedStyle(element).position,summaryWidth:target.width,summaryHeight:target.height,
          headerPosition:getComputedStyle(document.querySelector('header')).position,scrollY,
          overflow:document.documentElement.scrollWidth>innerWidth+.5};
      });
      nativePageScrollY=panelState.scrollY;
      if(panelState.left<-.5||panelState.right>width+.5||
        panelState.overflow||panelState.summaryWidth<44||panelState.summaryHeight<44||
        panelState.headerPosition!=='static'||panelState.panelPosition!=='static')
        throw Error('Native panel does not reflow with the document: '+JSON.stringify({width,textSize,home,panelState}));
      if(await banner.getByRole('button',{name:'メニューを開く'}).isVisible()) throw Error('Dead menu');
      if(await banner.getByRole('button',{name:'検索欄を開く'}).isVisible()) throw Error('Dead search');
      const cdp=await context.newCDPSession(page);
      const {nodes}=await cdp.send('Accessibility.getFullAXTree');
      if(!nodes.some(n=>!n.ignored&&n.role?.value==='searchbox'&&n.name?.value==='記事を検索'))
        throw Error('Search is missing from the native accessibility tree');
      for(const link of links){
        await openNative();
        await panel.getByRole('link',{name:link.label,exact:true}).click();
        await page.waitForURL(origin+link.url);
        if(await details.evaluate(element=>element.open)) throw Error('Native menu did not reset on navigation');
        const heading=page.getByRole('heading',{name:link.label,level:1,exact:true});
        await heading.scrollIntoViewIfNeeded();
        const top=await heading.evaluate(e=>e.getBoundingClientRect().top);
        if(top < -0.5||top>=900) throw Error('Native destination heading is not visible: '+
          JSON.stringify({width,textSize,home,link,top}));
      }
      await openNative();
      await banner.getByRole('searchbox',{name:'記事を検索'}).fill('比較');
      await banner.getByRole('button',{name:'検索',exact:true}).click();
      await page.waitForURL(url=>url.searchParams.get('s')==='比較');
      await openNative();
      await banner.getByRole('searchbox',{name:'記事を検索'}).fill('選び方');
      await page.keyboard.press('Enter');
      await page.waitForURL(url=>url.searchParams.get('s')==='選び方');
    } else {
      if(await banner.getByRole('button',{name:'検索',exact:true}).isVisible()) throw Error('Fallback visible after both blocks initialize');
      if(!(await banner.getByRole('button',{name:'検索欄を開く'}).isVisible())) throw Error('Normal search missing');
      if(width<600&&!(await banner.getByRole('button',{name:'メニューを開く'}).isVisible()))
        throw Error('Normal mobile menu missing');
    }
    observations[index]={width,textSize,javaScriptEnabled,home,readiness,
      representativeFailure,nativePageScrollY,...original,blocked};
    await context.close();
   }
  }));
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
    baseline = [row for row in observations if not row["representativeFailure"]]
    assert {(row['width'], row['textSize'], row['javaScriptEnabled'], row['home']) for row in baseline} == set(product((320, 360, 390, 768, 1024, 1440), (100, 200), (False, True), (False, True)))
    failures = [row for row in observations if row["representativeFailure"]]
    initialized_heights = {
        (row["width"], row["textSize"], row["home"]): row["headerHeight"]
        for row in baseline
        if row["readiness"] == "both"
    }
    assert any(
        row["nativePageScrollY"] > 0
        for row in baseline
        if row["readiness"] != "both" and row["textSize"] == 200
    )
    assert {
        (row["width"], row["textSize"], row["javaScriptEnabled"], row["readiness"])
        for row in failures
    } == {(390, 100, True, state) for state in ("none", "nav-only", "search-only")}
    for row in observations:
        assert row["overflow"] is False, row
        assert row["blocked"] == 0, row
        assert row["rawMarkupVisible"] is False, row
        assert row["fallbackPresent"] is True, row
        assert row["initiallyOpen"] is False, row
        assert row["fallback"] is (row["readiness"] != "both"), row
        if row["readiness"] != "both":
            # Enlarged text may wrap; fallback must stay as compact as the
            # initialized header under the same width, text size and page class.
            assert row["headerHeight"] <= initialized_heights[
                (row["width"], row["textSize"], row["home"])
            ] + 0.5, row
        if row["width"] < 600 and row["textSize"] == 100:
            assert row["headerHeight"] <= 80, row
