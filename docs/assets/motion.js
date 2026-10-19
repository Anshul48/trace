/* TRACE docs shared motion (WS1). Vanilla JS, no dependencies.
   - IO-lazy .reveal entrances (opacity/transform only, ease-out).
   - Any [data-loop] rAF loop pauses when off-screen and when the
     page is hidden; exposes window.TRACE_MOTION.pauseAll() for pages
     that need an explicit pause control.
   - prefers-reduced-motion: reveals resolve to final state, loops
     render one static frame and never advance. */
(function () {
  'use strict';

  function reduceMotion() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /* ---------- IO-lazy reveals ---------- */
  function initReveals() {
    if (!document.querySelectorAll) return;
    var els = document.querySelectorAll('.reveal');
    if (!els.length) return;
    var i;
    if (reduceMotion() || !('IntersectionObserver' in window)) {
      for (i = 0; i < els.length; i++) els[i].classList.add('is-in');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var k = 0; k < entries.length; k++) {
        if (entries[k].isIntersecting) {
          entries[k].target.classList.add('is-in');
          io.unobserve(entries[k].target);
        }
      }
    }, { threshold: 0.15 });
    for (i = 0; i < els.length; i++) io.observe(els[i]);
  }

  /* ---------- Pausable loops ---------- */
  var loops = [];

  // Register a loop: step(dtMs) draws one frame. Loop runs only while
  // its element is visible and the page is visible; reduced-motion
  // renders exactly one frame.
  function addLoop(el, step) {
    if (!el || typeof step !== 'function') return null;
    var handle = { el: el, step: step, raf: 0, last: 0, running: false };
    loops.push(handle);
    if (reduceMotion()) {
      step(0);
      return handle;
    }
    function frame(now) {
      handle.raf = 0;
      if (document.hidden) {
        handle.running = false;
        return;
      }
      var dt = handle.last ? now - handle.last : 16;
      handle.last = now;
      step(dt > 100 ? 100 : dt);
      handle.raf = window.requestAnimationFrame(frame);
    }
    function kick() {
      if (handle.running || reduceMotion()) return;
      handle.running = true;
      handle.last = 0;
      handle.raf = window.requestAnimationFrame(frame);
    }
    function halt() {
      handle.running = false;
      if (handle.raf) {
        window.cancelAnimationFrame(handle.raf);
        handle.raf = 0;
      }
    }
    handle.kick = kick;
    handle.halt = halt;
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) kick();
        else halt();
      }, { threshold: 0.05 });
      io.observe(el);
      handle.io = io;
    } else {
      kick();
    }
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) halt();
      else kick();
    });
    return handle;
  }

  function pauseAll() {
    for (var i = 0; i < loops.length; i++) {
      if (loops[i].halt) loops[i].halt();
    }
  }

  window.TRACE_MOTION = window.TRACE_MOTION || {};
  window.TRACE_MOTION.addLoop = addLoop;
  window.TRACE_MOTION.pauseAll = pauseAll;
  window.TRACE_MOTION.reducedMotion = reduceMotion;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initReveals);
  } else {
    initReveals();
  }
})();
