/* Open only the provider's existing preferences UI; never alter consent state. */
(() => {
  'use strict';
  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const trigger = target.closest('a.cky-banner-element');
    if (!trigger) return;
    const revisit = document.querySelector('.cky-btn-revisit');
    if (!(revisit instanceof HTMLElement)) return;
    // CookieYes owns all switches, persistence, consent events and focus trapping.
    // If it is unavailable the ordinary privacy-policy href remains useful.
    event.preventDefault();
    event.stopImmediatePropagation();
    revisit.click();
  }, true);
})();
