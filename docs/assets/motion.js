/* Shared motion helper — identical in trace and anima (docs/assets/motion.js).
   Durations mirror design.css tokens: 150/250/400/600ms.
   Respects prefers-reduced-motion; no dependencies. */
(function () {
  'use strict';

  var DUR = { fast: 150, base: 250, slow: 400, slower: 600 };

  function reducedMotion() {
    return window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // Progressive reveal: elements with [data-reveal] fade in on entry.
  function initReveal() {
    if (reducedMotion() || !('IntersectionObserver' in window)) return;
    var els = document.querySelectorAll('[data-reveal]');
    if (!els.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.style.transitionDuration = DUR.slow + 'ms';
        entry.target.setAttribute('data-revealed', 'true');
        io.unobserve(entry.target);
      });
    }, { threshold: 0.15 });
    els.forEach(function (el) { io.observe(el); });
  }

  // Smooth in-page anchor scroll (skipped under reduced motion).
  function initAnchors() {
    if (reducedMotion()) return;
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest('a[href^="#"]');
      if (!a) return;
      var target = document.querySelector(a.getAttribute('href'));
      if (!target) return;
      ev.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initReveal();
    initAnchors();
  });

  window.siteMotion = { durations: DUR, reducedMotion: reducedMotion };
})();
