/* Optional reader measurement. No visitor identity, automatic view events or queue. */
(() => {
  'use strict';
  const settings = document.getElementById('raos-reader-consent-settings');
  const configNode = document.getElementById('raos-reader-measurement-config');
  if (!settings || !configNode || settings.dataset.readerConsentBound === 'true') return;
  const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
  const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  let config;
  try { config = JSON.parse(configNode.textContent); } catch { return; }
  if (!exact(config, ['schema', 'origin', 'endpoint', 'collection_enabled', 'contract_sha256', 'policy_sha256', 'policy_version', 'article'])
    || config.schema !== 'RAOSReaderMeasurementClientV1'
    || config.origin !== 'https://kurashinoshirube.com' || location.origin !== config.origin
    || config.endpoint !== '/wp-json/raos-reader/v1/events'
    || typeof config.collection_enabled !== 'boolean'
    || !digest(config.contract_sha256) || !digest(config.policy_sha256)
    || config.policy_version !== config.policy_sha256) return;
  const article = config.article;
  if (article !== null && (!exact(article, ['article_id', 'slug', 'navigation', 'panels', 'references'])
    || !Array.isArray(article.navigation) || !Array.isArray(article.panels) || !Array.isArray(article.references)
    || location.pathname !== '/' + article.slug + '/')) return;
  const controls = {};
  for (const name of ['allow', 'deny', 'reopen', 'revoke', 'choices', 'error']) {
    controls[name] = document.getElementById('raos-reader-consent-' + name);
    if (!controls[name]) return;
  }
  const userStatus = document.getElementById('raos-reader-user-status');
  const siteStatus = document.getElementById('raos-reader-site-status');
  if (!userStatus || !siteStatus) return;
  settings.dataset.readerConsentBound = 'true';
  const key = 'raos_reader_consent_v1';
  let choice = null;
  let failed = false;

  const readChoice = () => {
    try {
      const stored = JSON.parse(localStorage.getItem(key));
      return exact(stored, ['choice', 'policy_version'])
        && stored.policy_version === config.policy_version
        && ['granted', 'denied'].includes(stored.choice) ? stored.choice : null;
    } catch { return null; }
  };
  const render = () => {
    userStatus.textContent = 'あなたの選択：' + ({ granted: '許可', denied: '拒否' }[choice] || '未選択');
    siteStatus.textContent = config.collection_enabled && !failed
      ? 'サイトの計測は有効です。許可した場合だけ対象の操作を送ります。'
      : failed ? '計測の受付を確認できないため、このページでは送信を停止しました。'
        : 'サイトの計測は停止中です。現在、操作は送信されません。';
    controls.revoke.hidden = choice !== 'granted';
  };
  const collapse = () => {
    controls.choices.hidden = true;
    controls.reopen.setAttribute('aria-expanded', 'false');
    controls.reopen.focus();
  };
  const choose = value => {
    choice = value === 'granted' ? 'granted' : 'denied';
    controls.error.hidden = true;
    try {
      localStorage.setItem(key, JSON.stringify({ choice, policy_version: config.policy_version }));
    } catch {
      choice = 'denied';
      controls.error.textContent = '選択を保存できませんでした。計測は行いません。ブラウザーの保存設定を確認してください。';
      controls.error.hidden = false;
    }
    render();
    collapse();
  };
  controls.allow.addEventListener('click', event => { if (event.isTrusted) choose('granted'); });
  controls.deny.addEventListener('click', event => { if (event.isTrusted) choose('denied'); });
  controls.revoke.addEventListener('click', event => { if (event.isTrusted) choose('denied'); });
  const reopen = () => {
    controls.choices.hidden = false;
    controls.reopen.setAttribute('aria-expanded', 'true');
    controls.allow.focus();
  };
  controls.reopen.addEventListener('click', reopen);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) { choice = readChoice(); render(); }
  });
  window.addEventListener('pageshow', () => { choice = readChoice(); render(); });
  choice = readChoice();
  if (choice !== null) {
    controls.choices.hidden = true;
    controls.reopen.setAttribute('aria-expanded', 'false');
  }
  render();

  const send = event => {
    if (!config.collection_enabled || failed || article === null) return;
    choice = readChoice();
    if (choice !== 'granted') { render(); return; }
    // The request contains only a constructed closed event; never DOM text/URLs.
    try {
      // Default Fetch mode preserves the exact Origin with no-referrer.
      // Fixed relative endpoint + location gate + redirect:error keep it same-origin.
      const result = fetch(config.endpoint, {
        method: 'POST', redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer',
        keepalive: true, cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-RAOS-Reader-Consent': 'granted',
          'X-RAOS-Reader-Contract': config.contract_sha256, 'X-RAOS-Reader-Policy': config.policy_sha256 },
        body: JSON.stringify(event)
      });
      Promise.resolve(result).then(response => {
        if (!response.ok) { failed = true; render(); }
      }).catch(() => { failed = true; render(); });
    } catch { failed = true; render(); }
  };
  const handled = new WeakSet();
  document.addEventListener('click', event => {
    // Never cancel navigation, intercept generic input, or treat scripted clicks as readers.
    if (!event.isTrusted || event.defaultPrevented || event.button !== 0 || handled.has(event)) return;
    handled.add(event);
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest('input, select, textarea, button, [contenteditable]')) return;
    const link = target.closest('a[href]');
    if (link?.getAttribute('href') === '#raos-reader-consent-settings') { reopen(); return; }
    if (!config.collection_enabled || failed || article === null || choice !== 'granted') return;
    const articleRoot = target.closest('.raos-editorial-v2');
    if (!articleRoot || !articleRoot.querySelector('.raos-reader-view[data-raos-article-id="' + article.article_id + '"]')) return;
    const summary = target.closest('summary');
    if (summary && summary.parentElement?.tagName === 'DETAILS') {
      const details = summary.parentElement;
      const panel = article.panels.find(p => p.kind === 'details' && p.panel_id === details.id);
      if (panel && !details.open) {
        // Inspect the native activation result once; no retry or event queue.
        setTimeout(() => {
          if (details.open && !event.defaultPrevented) {
            send({ event_name: 'decision_check_open', article_id: article.article_id, panel_id: panel.panel_id });
          }
        }, 0);
      }
      return;
    }
    if (!link || link.hasAttribute('download')) return;
    let url;
    try { url = new URL(link.href, location.href); } catch { return; }
    if (url.origin === config.origin && url.pathname === location.pathname && !url.search) {
      const panel = article.panels.find(p => p.kind === 'anchor' && '#' + p.panel_id === url.hash);
      if (panel && articleRoot.querySelector('#' + panel.panel_id)) {
        send({ event_name: 'decision_check_open', article_id: article.article_id, panel_id: panel.panel_id });
        return;
      }
    }
    if (url.origin === config.origin && !url.search && !url.hash) {
      const stage = link.closest('.raos-contextual-related[data-journey-stage]')?.dataset.journeyStage;
      const nav = article.navigation.find(n => n.path === url.pathname && n.journey_stage === stage);
      if (nav) {
        send({ event_name: 'guide_navigation', article_id: article.article_id,
          target_article_id: nav.target_article_id, journey_stage: nav.journey_stage });
      }
      return;
    }
    const reference = article.references.find(ref => {
      try { return new URL(ref.url).href === url.href; } catch { return false; }
    });
    if (reference) send({ event_name: 'official_reference_open', article_id: article.article_id, source_ref: reference.source_ref });
  }, true);
})();
