import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const base = 'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/';
const source = fs.readFileSync(base + 'assets/purchase-analytics.js', 'utf8');
const binding = {article_id:'article-1', product_id:'product-1', seller_id:'official', offer_id:'offer-1', cta_id:'cta-1', placement:'top_summary', snapshot_id:'snapshot-1', href:'https://seller.example/item?private=never-send'};
function fixture() {
  const listeners = {}, calls = []; let granted=true, optout=null;
  const root={getAttribute: key => ({'data-raos-article-id':'article-1','data-raos-snapshot-id':'snapshot-1'})[key]};
  const anchor={href:binding.href, getAttribute:key=>binding[key.replace('data-raos-', '').replaceAll('-', '_')], closest:()=>root};
  const config = {profile:'purchase-support-v1',enabled:true,debug_mode:false,bindings:[{...binding}]};
  const nodes={'raos-purchase-ga4-config':{type:'application/json',get textContent(){return JSON.stringify(config);}}, 'google_gtagjs-js':{getAttribute:()=> 'G-ABC12345'}};
  const window={getCkyConsent:()=>({isUserActionCompleted:granted,categories:{analytics:granted}}),wp_has_consent:()=>granted,_googlesitekitConsents:{analytics_storage:'granted'},localStorage:{getItem:()=>optout},gtag:(...args)=>calls.push(args)};
  window.gtag.raosConsentGate=true;
  const document={getElementById:id=>nodes[id],addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
  const context=vm.createContext({window,document}); vm.runInContext(source,context);
  const click=(type='click',button=0)=>{const e={type,button,isTrusted:true,target:{closest:()=>anchor}};for(const fn of listeners[type])fn(e);};
  return {window,context,config,nodes,calls,click,listeners,anchor,deny:()=>granted=false,optout:()=>optout='1'};
}
let f=fixture(); f.click(); assert.equal(f.calls.length,1);assert.deepEqual(Object.keys(f.calls[0][2]).sort(),[...Object.keys(binding).filter(k=>k!=='href'),'send_to','debug_mode'].sort());assert.ok(!JSON.stringify(f.calls).includes('private'));
vm.runInContext(source,f.context); f.click();f.click(); assert.equal(f.calls.length,3);assert.equal(f.listeners.click.length,1);
f.click('click',1);f.click('auxclick',1);f.click('auxclick',0);assert.equal(f.calls.length,4);
for (const alter of [f=>f.deny(),f=>f.optout(),f=>delete f.window.gtag,f=>delete f.nodes['raos-purchase-ga4-config'],f=>f.config.enabled=false,f=>f.config.bindings[0].seller_id='unknown',f=>f.anchor.href+='&drift=1',f=>f.window.gtag.raosConsentGate=false,f=>f.window['ga-disable-G-ABC12345']=true]) {f=fixture();alter(f);f.click();assert.equal(f.calls.length,0);}
f=fixture();f.config.debug_mode=true;f.click();assert.equal(f.calls[0][2].debug_mode,true);f.deny();f.click();assert.equal(f.calls.length,1);
f=fixture();f.window.gtag=()=>{throw Error('network');};f.window.gtag.raosConsentGate=true;assert.doesNotThrow(()=>f.click());
console.log('purchase analytics: payload, consent, no config/tag, allowlist/href drift, opt-out, revocation, debug, duplicate install, repeat/aux click, network failure PASS');
