/** Local-only reader layout diagnostic. This is not publication or human-test evidence. */
import { chromium } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const [origin, output] = process.argv.slice(2);
const target = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(target.hostname) || target.protocol !== 'http:' || !output) throw Error('LOCAL_READER_AUDIT_ARGUMENTS_REQUIRED');
const inventory = JSON.parse(await readFile('changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json','utf8'));
const available = [...inventory.surfaces, ...inventory.local_surfaces, ...(inventory.reader_hubs ?? [])];
const selection = process.env.READER_AUDIT_SURFACES?.split(',');
if (selection?.some(id=>!available.some(s=>s.surface_id===id))) throw Error('UNKNOWN_READER_SURFACE');
const surfaces = selection ? available.filter(s=>selection.includes(s.surface_id)) : available;
await mkdir(output,{recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true});
const axeSource = await readFile('node_modules/axe-core/axe.min.js','utf8');
const results = [];
const errors = [];
const internalLinks = new Set();
try {
  const remaining = [...surfaces];
  await Promise.all(Array.from({length:Math.min(3,surfaces.length)}, async () => {
  while (remaining.length) {
    const surface = remaining.shift();
    const page = await browser.newPage();
    await page.route('**/*', route => {
      const request = route.request();
      if (new URL(request.url()).origin !== target.origin || !['GET','HEAD'].includes(request.method())) {
        errors.push({surface:surface.surface_id,error:'NONLOCAL_OR_MUTATING_REQUEST',resourceType:request.resourceType()});
        return route.abort();
      }
      return route.continue();
    });
    page.on('pageerror', error => errors.push({surface:surface.surface_id,error:error.message}));
    const url = new URL(surface.local_path,origin).href;
    const widths = [];
    for (const width of inventory.viewports) {
      await page.setViewportSize({width,height:900});
      const response = await page.goto(url,{waitUntil:'networkidle'});
      await page.evaluate(() => document.fonts.ready);
      await page.addScriptTag({content:axeSource});
      const accessibility = await page.evaluate(async () => (await window.axe.run(document, {
        runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']},resultTypes:['violations']
      })).violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)})));
      const audit = await page.evaluate(() => {
        const main = document.querySelector('main');
        const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
        const text = main?.innerText ?? '';
        const ids = [...document.querySelectorAll('[id]')].map(e=>e.id);
        const headings = [...main.querySelectorAll('h1,h2,h3,h4,[role="heading"][aria-level]')].filter(visible).map(e=>({level:Number(e.getAttribute('aria-level')||e.tagName[1]),id:e.id,text:e.textContent.trim()}));
        const links = [...main.querySelectorAll('a')].filter(visible).map(e=>({text:(e.textContent||e.getAttribute('aria-label')||e.querySelector('img')?.alt||'').trim(),url:e.getAttribute('href')}));
        const localLinks = [...document.querySelectorAll('a[href]')].map(a=>new URL(a.href)).filter(u=>u.origin===location.origin&&!(u.hash&&u.pathname===location.pathname&&u.search===location.search)).map(u=>u.href);
        const cards = [...document.querySelectorAll('.raos-home-latest .raos-guide-card')].map(e=>{const r=e.getBoundingClientRect();return{top:r.top,bottom:r.bottom,height:r.height,date:e.querySelector('.raos-guide-card__date')?.getBoundingClientRect().bottom};});
        const allSpecifications = [...main.querySelectorAll('.comparison-table-wrap table')].filter(t=>!t.closest('details:not([open])'));
        return {h1:headings.filter(e=>e.level===1),headings,links,localLinks,cards,
          headingJumps:headings.filter((h,i)=>i>0&&h.level>headings[i-1].level+1),
          hiddenSpecifications:allSpecifications.filter(t=>!visible(t)).length,
          regions:[...main.querySelectorAll('.comparison-table-wrap')].filter(visible).map(e=>({
            scrolls:e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1,
            tabIndex:e.getAttribute('tabindex'),named:!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby'))
          })),
          overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
          placeholders: ['イメージイラスト','商品写真ではありません','商品画像未確認'].filter(p=>text.includes(p)),
          decorativeBreaks:main.querySelectorAll('.raos-editorial-v2 br').length,
          duplicateIds:ids.filter((id,i)=>ids.indexOf(id)!==i),
          nestedLinks:main.querySelectorAll('a a').length,
          unnamedLinks:links.filter(a=>!a.text),
          brokenAnchors:links.filter(a=>a.url?.startsWith('#')&&a.url.length>1&&!document.getElementById(a.url.slice(1))),
          tables:[...main.querySelectorAll('table')].filter(visible).map(t=>({caption:!!t.caption,headers:t.querySelectorAll('th[scope]').length,unscoped:t.querySelectorAll('th:not([scope])').length,scrollable:!!t.closest('[tabindex="0"]')})),
          ogImage:[...document.querySelectorAll('meta[property="og:image"]')].map(e=>e.content),
          cardLinkCounts:[...document.querySelectorAll('.raos-home-latest .raos-guide-grid > li')].map(e=>e.querySelectorAll('a').length),
          offerCount:main.querySelectorAll('[data-raos-cta-type="offer"]').length,
          approvedImageCount:main.querySelectorAll('[data-raos-product-image-state="verified"]').length
        };
      });
      audit.localLinks.forEach(href=>internalLinks.add(href));
      const screenshot = path.resolve(output,`${surface.surface_id}-${width}.png`);
      await page.screenshot({path:screenshot,fullPage:true});
      if (width === 1440) await writeFile(path.join(output,`${surface.surface_id}.html`),await page.content());
      await page.evaluate(() => {
        const sizes = [...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
        for (const [e,size] of sizes) if (e instanceof HTMLElement) e.style.fontSize=`${size*2}px`;
      });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const enlargedOverflow = await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
      await page.keyboard.press('Tab');
      const keyboardFocus = await page.evaluate(()=>{const e=document.activeElement;const s=getComputedStyle(e);return{tag:e.tagName,outline:s.outlineStyle,outlineWidth:s.outlineWidth};});
      widths.push({width,status:response.status(),expectedStatus:surface.expected_http_status??200,screenshot,...audit,accessibility,enlargedOverflow,keyboardFocus});
    }
    results.push({surface:surface.surface_id,url,widths});
    await page.close();
  }
  }));
  const context = await browser.newContext();
  const parserPage = await context.newPage();
  for (const href of internalLinks) {
    const response = await context.request.get(href,{maxRedirects:0});
    if (response.status() !== 200) errors.push({error:'INTERNAL_LINK_HTTP',url:href,status:response.status()});
    const hash = new URL(href).hash;
    if (response.status() === 200 && hash) {
      const exists = await parserPage.evaluate(({markup,id})=>!!new DOMParser().parseFromString(markup,'text/html').getElementById(id), {markup:await response.text(),id:decodeURIComponent(hash.slice(1))});
      if (!exists) errors.push({error:'INTERNAL_LINK_ANCHOR',url:href});
    }
    await response.dispose();
  }
  await context.close();
} finally { await browser.close(); }
const failures = results.flatMap(r=>r.widths.flatMap(a=>{
  const aligned = a.cards.every((card,i)=>a.cards.every((other,j)=>i===j||Math.abs(card.top-other.top)>1||(Math.abs(card.bottom-other.bottom)<=1&&Math.abs(card.date-other.date)<=1)));
  const rules = {cardAlignment:aligned,accessibility:!a.accessibility.length,headingOrder:!a.headingJumps.length,specificationsVisible:!a.hiddenSpecifications,tableHeaders:a.tables.every(t=>t.caption&&t.headers>0&&!t.unscoped),scrollRegions:a.regions.every(r=>r.named&&(!r.scrolls||r.tabIndex==='0')),focus:a.keyboardFocus.outline!=='none'&&parseFloat(a.keyboardFocus.outlineWidth)>0,cardLinks:a.cardLinkCounts.every(n=>n===1),unapprovedOg:!a.ogImage.length,status:a.status===a.expectedStatus,h1:a.h1.length===1,overflow:a.overflow<=1,enlargedOverflow:a.enlargedOverflow<=1,placeholders:!a.placeholders.length,breaks:!a.decorativeBreaks,ids:!a.duplicateIds.length,nested:!a.nestedLinks,linkNames:!a.unnamedLinks.length,anchors:!a.brokenAnchors.length};
  return Object.entries(rules).filter(([,ok])=>!ok).map(([rule])=>({surface:r.surface,width:a.width,rule}));
}));
results.sort((a,b)=>a.surface.localeCompare(b.surface));
const report = {profile:'LOCAL_READER_DIAGNOSTIC',captured_at:new Date().toISOString(),human_tests:'NOT_PERFORMED',internalLinksChecked:internalLinks.size,results,errors,failures};
await writeFile(path.join(output,'manifest.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({pages:results.length,widths:inventory.viewports,failures,errors,report:path.resolve(output,'manifest.json')}));
process.exitCode=failures.length||errors.length?1:0;
