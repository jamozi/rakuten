(() => {
  "use strict";

  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = document.querySelectorAll(".raos-reveal");

  if (reduced || !("IntersectionObserver" in window) || targets.length === 0) {
    return;
  }

  let observer = null;
  const revealAll = () => {
    root.classList.remove("raos-reveal-ready");
    targets.forEach((target) => target.classList.add("is-visible"));
    if (observer !== null) {
      try {
        observer.disconnect();
      } catch (_error) {
        /* Content is visible; enhancement cleanup is best-effort only. */
      }
    }
  };

  try {
    observer = new IntersectionObserver(
      (entries) => {
        try {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        } catch (_error) {
          revealAll();
        }
      },
      { rootMargin: "0px 0px -10%", threshold: 0.1 },
    );

    targets.forEach((target) => observer.observe(target));
    root.classList.add("raos-reveal-ready");
  } catch (_error) {
    revealAll();
  }
})();
