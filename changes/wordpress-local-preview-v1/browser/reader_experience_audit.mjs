/** Local-only reader layout diagnostic. This is not publication or human-test evidence. */
import { chromium } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const [origin, output] = process.argv.slice(2);
const target = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(target.hostname) || target.protocol !== 'http:' || !output) throw Error('LOCAL_READER_AUDIT_ARGUMENTS_REQUIRED');
const inventory = JSON.parse(await readFile('changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json','utf8'));
const surfaces = inventory.surfaces.filter(s => ['home','article'].includes(s.kind));
await mkdir(output,{recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true});
const results = [];
const errors = [];
try {
  for (const surface of surfaces) {
    const page = await browser.newPage();
    await page.route('**/*', route => new URL(route.request().url()).origin === target.origin ? route.continue() : route.abort());
    page.on('pageerror', error => errors.push({surface:surface.surface_id,error:error.message}));
    const url = new URL(surface.local_path,origin).href;
    const widths = [];
    for (const width of inventory.viewports) {
      await page.setViewportSize({width,height:900});
      const response = await page.goto(url,{waitUntil:'networkidle'});
      await page.evaluate(() => document.fonts.ready);
      const audit = await page.evaluate(() => {
        const main = document.querySelector('main');
        const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
        const text = main?.innerText ?? '';
        const ids = [...document.querySelectorAll('[id]')].map(e=>e.id);
        const headings = [...main.querySelectorAll('h1,h2,h3,h4')].filter(visible).map(e=>({level:Number(e.tagName[1]),id:e.id,text:e.textContent.trim()}));
        const links = [...main.querySelectorAll('a')].filter(visible).map(e=>({text:(e.textContent||e.getAttribute('aria-label')||e.querySelector('img')?.alt||'').trim(),url:e.getAttribute('href')}));
        const cards = [...document.querySelectorAll('.raos-home-latest .raos-guide-card')].map(e=>{const r=e.getBoundingClientRect();return{top:r.top,bottom:r.bottom,height:r.height,date:e.querySelector('.raos-guide-card__date')?.getBoundingClientRect().bottom};});
        return {h1:headings.filter(e=>e.level===1),headings,links,cards,
          overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
          placeholders: ['イメージイラスト','商品写真ではありません','商品画像未確認'].filter(p=>text.includes(p)),
          decorativeBreaks:main.querySelectorAll('.raos-editorial-v2 br').length,
          duplicateIds:ids.filter((id,i)=>ids.indexOf(id)!==i),
          nestedLinks:main.querySelectorAll('a a').length,
          unnamedLinks:links.filter(a=>!a.text),
          brokenAnchors:links.filter(a=>a.url?.startsWith('#')&&a.url.length>1&&!document.getElementById(a.url.slice(1))),
          tables:[...main.querySelectorAll('table')].filter(visible).map(t=>({caption:!!t.caption,headers:t.querySelectorAll('th[scope]').length,scrollable:!!t.closest('[tabindex="0"]')})),
          ogImage:[...document.querySelectorAll('meta[property="og:image"]')].map(e=>e.content),
          cardLinkCounts:[...document.querySelectorAll('.raos-home-latest .raos-guide-grid > li')].map(e=>e.querySelectorAll('a').length),
          offerCount:main.querySelectorAll('[data-raos-cta-type="offer"]').length,
          approvedImageCount:main.querySelectorAll('[data-raos-product-image-state="verified"]').length
        };
      });
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
      widths.push({width,status:response.status(),screenshot,...audit,enlargedOverflow,keyboardFocus});
    }
    results.push({surface:surface.surface_id,url,widths});
    await page.close();
  }
} finally { await browser.close(); }
const failures = results.flatMap(r=>r.widths.flatMap(a=>{
  const rules = {cardLinks:a.cardLinkCounts.every(n=>n===1),unapprovedOg:!a.ogImage.length,status:a.status===200,h1:a.h1.length===1,overflow:a.overflow<=1,enlargedOverflow:a.enlargedOverflow<=1,placeholders:!a.placeholders.length,breaks:!a.decorativeBreaks,ids:!a.duplicateIds.length,nested:!a.nestedLinks,linkNames:!a.unnamedLinks.length,anchors:!a.brokenAnchors.length};
  return Object.entries(rules).filter(([,ok])=>!ok).map(([rule])=>({surface:r.surface,width:a.width,rule}));
}));
const report = {profile:'LOCAL_READER_DIAGNOSTIC',captured_at:new Date().toISOString(),human_tests:'NOT_PERFORMED',results,errors,failures};
await writeFile(path.join(output,'manifest.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({pages:results.length,widths:inventory.viewports,failures,errors,report:path.resolve(output,'manifest.json')}));
process.exitCode=failures.length||errors.length?1:0;
