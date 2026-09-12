(() => {
  'use strict';

  const selector = '.raos-article-toc a[href^="#"],.raos-back-to-toc[href^="#"],.ps-article a[href^="#"]';
  const editorialRoot = document.querySelector('.raos-editorial-v2');
  const toc = document.querySelector('.raos-article-toc');
  const tocDetails = document.querySelector('.raos-article-toc details');
  const desktopQuery = window.matchMedia('(min-width: 64.0625rem)');
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
    const verticallyScrollable = visible && region.scrollHeight > region.clientHeight + 1 && ['auto', 'scroll'].includes(style.overflowY);
    if (horizontallyScrollable || verticallyScrollable) {
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
    const offset = Math.ceil((Number.isFinite(stickyTop) ? stickyTop : 0) + 16);
    editorialRoot.style.setProperty('--raos-toc-scroll-offset', `${offset}px`);
  };

  const revealHashTarget = (target) => {
    let ancestor = target.parentElement;
    while (ancestor) {
      if (ancestor instanceof HTMLDetailsElement) ancestor.open = true;
      ancestor = ancestor.parentElement;
    }
    // Hidden or inert state belongs to another owner and is never cleared here.
    if (target.closest('[hidden],[inert]')) return;
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
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
    // Modified, non-primary, download and new-window clicks keep the browser default.
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
        event.shiftKey || event.altKey) return;
    const anchor = event.target instanceof Element ? event.target.closest(selector) : null;
    if (!(anchor instanceof HTMLAnchorElement)) return;
    if (anchor.hasAttribute('download') || (anchor.target && anchor.target !== '_self')) return;
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

// Keep the existing editorial copy and links as the no-JavaScript fallback.
(() => {
  'use strict';
  const root = document.querySelector('#ks-magazine');
  const hero = root?.querySelector('.km-hero');
  const first = hero?.querySelector('a');
  const promos = root ? [...root.querySelectorAll('.km-promos .km-promo')] : [];
  if (!hero || !first || promos.length !== 3 || hero.dataset.carousel) return;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const track = document.createElement('div');
  track.className = 'km-carousel-track';
  track.id = 'km-editor-pick-slides';
  const slides = [first, ...promos.map((promo) => {
    const slide = document.createElement('a');
    slide.href = promo.href;
    const tag = document.createElement('span');
    tag.className = 'km-tag';
    tag.textContent = promo.querySelector('.km-eyebrow')?.textContent || 'FEATURE';
    const title = document.createElement('h2');
    title.className = 'km-carousel-title';
    title.textContent = promo.querySelector('h3').textContent;
    const description = promo.querySelector('p').cloneNode(true);
    const arrow = document.createElement('span');
    arrow.className = 'km-arrow';
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '⟶';
    slide.append(tag, title, description, arrow);
    return slide;
  })];
  slides.forEach((slide, i) => {
    slide.classList.add('km-carousel-slide');
    track.append(slide);
  });
  const controls = document.createElement('div');
  controls.className = 'km-carousel-controls';
  controls.setAttribute('role', 'group');
  controls.setAttribute('aria-label', '特集スライドの操作');
  const button = (label, text) => {
    const el = document.createElement('button');
    el.type = 'button';
    el.setAttribute('aria-label', label);
    el.setAttribute('aria-controls', track.id);
    el.textContent = text;
    return el;
  };
  const previous = button('前の特集', '←');
  const next = button('次の特集', '→');
  controls.append(previous, next);
  hero.append(track, controls);
  hero.classList.add('km-carousel');
  hero.dataset.carousel = 'ready';
  let index = 0;
  let timer;
  let hovered = false;
  let focused = false;
  let visible = true;
  const schedule = () => {
    window.clearTimeout(timer);
    if (!motion.matches && !hovered && !focused && visible && !document.hidden) {
      timer = window.setTimeout(() => show(index + 1), 5000);
    }
  };
  const show = (value) => {
    index = (value + slides.length) % slides.length;
    hero.dataset.slide = String(index);
    slides.forEach((slide, i) => {
      slide.style.transform = `translateX(${(i - index) * 100}%)`;
      slide.inert = i !== index;
      slide.setAttribute('aria-hidden', String(i !== index));
    });
    schedule();
  };
  previous.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  hero.addEventListener('pointerenter', (event) => { if (event.pointerType === 'mouse') { hovered = true; schedule(); } });
  hero.addEventListener('pointerleave', () => { hovered = false; schedule(); });
  hero.addEventListener('focusin', () => { focused = true; schedule(); });
  hero.addEventListener('focusout', (event) => { focused = hero.contains(event.relatedTarget); schedule(); });
  document.addEventListener('visibilitychange', schedule);
  motion.addEventListener('change', schedule);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; schedule(); }).observe(hero);
  show(0);
})();
