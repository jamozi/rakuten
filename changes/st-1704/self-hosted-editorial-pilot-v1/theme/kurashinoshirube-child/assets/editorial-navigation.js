(() => {
  'use strict';

  const selector = '.raos-article-toc a[href^="#"],.raos-back-to-toc[href^="#"]';
  const editorialRoot = document.querySelector('.raos-editorial-v2');
  const toc = document.querySelector('.raos-article-toc');
  const tocDetails = document.querySelector('.raos-article-toc details');
  const desktopQuery = window.matchMedia('(min-width: 48.0625rem)');
  const comparisonRegions = [
    ...document.querySelectorAll('.comparison-table-wrap[role="region"]'),
  ];

  const synchronizeComparisonFocusability = (region) => {
    if (!(region instanceof HTMLElement)) return;
    const style = window.getComputedStyle(region);
    const visible = style.display !== 'none' && style.visibility !== 'hidden' &&
      region.getClientRects().length > 0;
    const horizontallyScrollable = visible &&
      region.scrollWidth > region.clientWidth + 1 &&
      ['auto', 'scroll'].includes(style.overflowX);
    if (horizontallyScrollable) {
      region.tabIndex = 0;
      region.dataset.raosHorizontalScroll = 'available';
      return;
    }
    region.removeAttribute('tabindex');
    delete region.dataset.raosHorizontalScroll;
  };

  const synchronizeComparisonRegions = () => {
    comparisonRegions.forEach(synchronizeComparisonFocusability);
  };

  const synchronizeScrollOffset = () => {
    if (!(editorialRoot instanceof HTMLElement) || !(toc instanceof HTMLElement)) return;
    if (!desktopQuery.matches) {
      editorialRoot.style.removeProperty('--raos-toc-scroll-offset');
      return;
    }
    const stickyTop = Number.parseFloat(window.getComputedStyle(toc).top);
    const offset = Math.ceil(toc.getBoundingClientRect().height +
      (Number.isFinite(stickyTop) ? stickyTop : 0) + 16);
    editorialRoot.style.setProperty('--raos-toc-scroll-offset', `${offset}px`);
  };

  const revealHashTarget = (target) => {
    window.requestAnimationFrame(() => {
      synchronizeScrollOffset();
      target.scrollIntoView({ behavior: 'auto', block: 'start' });
      target.focus({ preventScroll: true });
    });
  };

  const currentHashTarget = () => {
    if (!window.location.hash) return null;
    try {
      const target = document.getElementById(
        decodeURIComponent(window.location.hash.slice(1)),
      );
      return target instanceof HTMLElement ? target : null;
    } catch (_error) {
      return null;
    }
  };

  if (tocDetails instanceof HTMLDetailsElement) {
    let mobileOpen = false;
    const synchronizeToc = () => {
      tocDetails.open = desktopQuery.matches || mobileOpen;
      window.requestAnimationFrame(synchronizeScrollOffset);
    };
    tocDetails.addEventListener('toggle', () => {
      if (!desktopQuery.matches) mobileOpen = tocDetails.open;
    });
    desktopQuery.addEventListener('change', synchronizeToc);
    synchronizeToc();
  }

  if (toc instanceof HTMLElement) {
    window.addEventListener('resize', synchronizeScrollOffset, { passive: true });
    if (typeof ResizeObserver === 'function') {
      new ResizeObserver(synchronizeScrollOffset).observe(toc);
    }
    synchronizeScrollOffset();
  }

  if (comparisonRegions.length > 0) {
    window.addEventListener('resize', synchronizeComparisonRegions, { passive: true });
    if (typeof ResizeObserver === 'function') {
      const comparisonObserver = new ResizeObserver(synchronizeComparisonRegions);
      comparisonRegions.forEach((region) => comparisonObserver.observe(region));
    }
    synchronizeComparisonRegions();
    window.addEventListener('load', synchronizeComparisonRegions, { once: true });
  }

  window.addEventListener('hashchange', () => {
    const target = currentHashTarget();
    if (target) revealHashTarget(target);
  });

  const initialTarget = currentHashTarget();
  if (initialTarget) revealHashTarget(initialTarget);

  document.addEventListener('click', (event) => {
    const anchor = event.target instanceof Element ? event.target.closest(selector) : null;
    if (!(anchor instanceof HTMLAnchorElement)) return;
    let target;
    try {
      const destination = new URL(anchor.href, window.location.href);
      if (
        destination.origin !== window.location.origin ||
        destination.pathname !== window.location.pathname ||
        destination.search !== window.location.search ||
        !destination.hash
      ) return;
      target = document.getElementById(decodeURIComponent(destination.hash.slice(1)));
    } catch (_error) {
      return;
    }
    if (!(target instanceof HTMLElement)) return;
    synchronizeScrollOffset();
    revealHashTarget(target);
  });
})();
