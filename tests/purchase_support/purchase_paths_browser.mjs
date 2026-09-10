/** Opt-in checks against an already frozen local WordPress preview; no live writes. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {chromium} from 'playwright';
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const runtime = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
if (!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(input.origin)) throw Error('LOCAL_ORIGIN_REQUIRED');
const output = path.resolve('output/playwright/purchase-p0');
fs.mkdirSync(output, {recursive:true});
const browser = await chromium.launch({headless:true});
const results = [];
try {
  for (const width of [390,1440]) {
    const context = await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
    await context.route('**/*', route => {
      const url = new URL(route.request().url()), mirrored = input.images?.[url.href];
      if (mirrored && route.request().resourceType() === 'image') {
        const body = fs.readFileSync(mirrored.path);
        if (crypto.createHash('sha256').update(body).digest('hex') !== mirrored.sha256) throw Error('PINNED_IMAGE_CHANGED');
        return route.fulfill({status:200,contentType:mirrored.mime,body});
      }
      return url.origin === input.origin || url.protocol === 'data:' ? route.continue() : route.abort();
    });
    for (const article of input.articles) {
      const slug = article.document.slug;
      const expected = runtime.articles.find(a => a.slug === slug);
      if (!expected) throw Error('EXPECTED_ARTICLE_MISSING');
      const page = await context.newPage();
      const errors=[];page.on('pageerror', e => errors.push(e.name));
      const response=await page.goto(input.origin+'/'+slug+'/',{waitUntil:'networkidle'});
      if (response.status() !== 200) throw Error('LOCAL_HTTP_FAILURE');
      const checks=await page.evaluate(expected => {
        const failures=[];
        for (const b of expected.bindings) {
          const nodes=[...document.querySelectorAll('[data-raos-cta-id]')].filter(n=>n.dataset.raosCtaId===b.cta_id);
          if(nodes.length!==1){failures.push('binding-count');continue;}
          const node=nodes[0],a=node.matches('a')?node:node.querySelector('a');
          if(!a || a.getAttribute('href')!==b.href) failures.push('href');
          for(const [k,v] of Object.entries(b)) if(k!=='href' && node.getAttribute('data-raos-'+k.replaceAll('_','-'))!==v) failures.push('binding');
          if(b.affiliate==='true' && (!a.relList.contains('sponsored') || !a.relList.contains('nofollow'))) failures.push('rel');
        }
        for(const seller of document.querySelectorAll('[data-ps-price-state]')) {
          if(!['CURRENT','EXPIRED','UNKNOWN'].includes(seller.dataset.psPriceState))failures.push('runtime-price-state');
          if(seller.dataset.psPriceState==='EXPIRED' && !seller.querySelector('a.ps-offer-link'))failures.push('expired-link-removed');
        }
        return {failures,bindings:expected.bindings.length};
      },expected);
      const anchors=page.locator('a[data-raos-link-purpose="internal_navigation"]');
      let clicked=0;
      for(let i=0;i<await anchors.count();i++) {
        const anchor=anchors.nth(i);
        // Preserved long-form details may be folded; open only their containing details.
        await anchor.evaluate(a=>{for(let p=a.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;});
        const href=await anchor.getAttribute('href'),product=await anchor.getAttribute('data-raos-product-id');
        await anchor.click();
        const valid=await page.evaluate(({href,product})=>{
          const target=document.getElementById(href.slice(1));
          return location.hash===href && target?.matches('section.ps-product-offers') && target.dataset.psProduct===product && target.innerText.trim().length>0;
        },{href,product});
        if(!valid)checks.failures.push('clicked-anchor-target');
        clicked++;
      }
      await page.locator('#ps-offers').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output,`${slug}-${width}.png`)});
      results.push({slug,width,clicked_anchors:clicked,binding_count:checks.bindings,failures:[...checks.failures,...errors]});
      await page.close();
    }
    await context.close();
  }
} finally {await browser.close();}
const report={status:results.every(r=>r.failures.length===0)?'PASS':'FAIL',environment:'LOCAL_WORDPRESS',results};
fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
if(report.status!=='PASS')process.exitCode=1;
