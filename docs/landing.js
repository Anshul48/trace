/* TRACE landing extras (WS1). Vanilla JS, no dependencies.
   - data.json check: fetches assets/data.json, compares key numbers to
     DOM text, console.warn on mismatch. DOM stays authoritative.
   - IO-triggered race bars + RSS gauge (width from data-w).
   - IO-triggered repair countdown 5,847 -> 0 (data-countdown). */
(function () {
  'use strict';

  function reduceMotion() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function digits(s) {
    return String(s).replace(/[^0-9]/g, '');
  }

  /* ---------- data.json cross-check ---------- */
  function checkData() {
    if (!window.fetch) return;
    var urls = ['assets/data.json'];
    window.fetch(urls[0]).then(function (res) {
      if (!res || !res.ok) return null;
      return res.json();
    }).then(function (d) {
      if (!d || !d.seam12a) return;
      var expect = {
        '10003381': d.seam12a.tokens,
        '63441': d.seam12a.atoms,
        '253': d.seam12a.freeze_files
      };
      var ups = document.querySelectorAll('[data-countup]');
      for (var i = 0; i < ups.length; i++) {
        var key = ups[i].getAttribute('data-countup');
        if (key && expect[key] !== undefined &&
            parseFloat(key) !== Number(expect[key])) {
          if (window.console && console.warn) {
            console.warn('data.json mismatch for ' + key);
          }
        }
      }
      var sha = d.seam12a.freeze_sha256 || '';
      if (sha && sha.slice(0, 8) !== '8d3bbb6b' &&
          window.console && console.warn) {
        console.warn('data.json freeze sha mismatch');
      }
    }).catch(function () {});
  }

  /* ---------- IO-triggered bars ---------- */
  function initBars() {
    var bars = document.querySelectorAll('.bar-fill[data-w]');
    if (!bars.length) return;
    function fire(el) {
      el.style.width = el.getAttribute('data-w') + '%';
    }
    if (reduceMotion() || !('IntersectionObserver' in window)) {
      for (var i = 0; i < bars.length; i++) fire(bars[i]);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var k = 0; k < entries.length; k++) {
        if (entries[k].isIntersecting) {
          fire(entries[k].target);
          io.unobserve(entries[k].target);
        }
      }
    }, { threshold: 0.4 });
    for (var j = 0; j < bars.length; j++) io.observe(bars[j]);
  }

  /* ---------- IO-triggered repair countdown ---------- */
  function initCountdown() {
    var els = document.querySelectorAll('[data-countdown]');
    if (!els.length) return;
    function format(n) {
      n = Math.round(n);
      var s = String(n);
      var out = '';
      while (s.length > 3) {
        out = ',' + s.slice(-3) + out;
        s = s.slice(0, -3);
      }
      return s + out;
    }
    function fire(el) {
      var from = parseFloat(el.getAttribute('data-countdown'));
      if (!isFinite(from)) return;
      if (reduceMotion()) {
        el.textContent = '0';
        return;
      }
      var dur = 1600;
      var raf = window.requestAnimationFrame || function (cb) {
        return setTimeout(function () { cb(Date.now()); }, 16);
      };
      var start = null;
      function frame(now) {
        if (start === null) start = now;
        var t = (now - start) / dur;
        if (t >= 1) {
          el.textContent = '0';
          return;
        }
        var eased = 1 - Math.pow(1 - (t < 0 ? 0 : t), 3);
        el.textContent = format(from * (1 - eased));
        raf(frame);
      }
      raf(frame);
    }
    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) fire(els[i]);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var k = 0; k < entries.length; k++) {
        if (entries[k].isIntersecting) {
          fire(entries[k].target);
          io.unobserve(entries[k].target);
        }
      }
    }, { threshold: 0.4 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  function init() {
    checkData();
    initBars();
    initCountdown();
    void digits;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
