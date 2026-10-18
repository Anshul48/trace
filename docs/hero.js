// TRACE landing hero + proof counters — vanilla JS, no dependencies.
//
// Canvas: abstract "memory self-organizing" — amber particles drift in a dark
// slate field, then gather into teal schema constellations with thin threads.
// Abstract art only: no data, numbers, or text are ever drawn on the canvas.
// Counters: elements with [data-countup] animate to their exact final value
// when scrolled into view. Final values live in the DOM as text first, so
// no-JS and prefers-reduced-motion readers see correct numbers.
(function () {
  'use strict';

  function reduceMotion() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  // ---------- Count-up ----------

  // Deterministic grouping: 10003381 -> "10,003,381", independent of locale.
  function formatGrouped(value, decimals) {
    var neg = value < 0;
    var fixed = Math.abs(value).toFixed(decimals);
    var parts = fixed.split('.');
    var head = parts[0];
    var grouped = '';
    while (head.length > 3) {
      grouped = ',' + head.slice(-3) + grouped;
      head = head.slice(0, -3);
    }
    grouped = head + grouped;
    return (neg ? '-' : '') + grouped + (decimals > 0 ? '.' + parts[1] : '');
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function counterParts(el) {
    return {
      target: parseFloat(el.getAttribute('data-countup')),
      decimals: parseInt(el.getAttribute('data-decimals') || '0', 10),
      prefix: el.getAttribute('data-prefix') || '',
      suffix: el.getAttribute('data-suffix') || ''
    };
  }

  function renderCounter(el, value) {
    var p = counterParts(el);
    el.textContent = p.prefix + formatGrouped(value, p.decimals) + p.suffix;
  }

  function animateCounter(el) {
    var p = counterParts(el);
    if (!isFinite(p.target) || !isFinite(p.decimals)) return;
    var durMs = 1400;
    var raf = window.requestAnimationFrame || function (cb) {
      return setTimeout(function () { cb(Date.now()); }, 16);
    };
    var start = null;
    function frame(now) {
      if (start === null) start = now;
      var t = (now - start) / durMs;
      if (t >= 1) {
        renderCounter(el, p.target);
        return;
      }
      renderCounter(el, p.target * easeOutCubic(t < 0 ? 0 : t));
      raf(frame);
    }
    raf(frame);
  }

  function initCounters() {
    if (!document.querySelectorAll) return;
    var els = document.querySelectorAll('[data-countup]');
    if (!els.length) return;
    // Reduced motion / no IntersectionObserver: DOM already holds the exact
    // final values, so there is nothing to do.
    if (reduceMotion() || !('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          animateCounter(entries[i].target);
          io.unobserve(entries[i].target);
        }
      }
    }, { threshold: 0.4 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  // ---------- Canvas hero ----------

  var IW = 880;
  var IH = 360;

  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function initHero() {
    var canvas = document.getElementById('hero-canvas');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var reduced = reduceMotion();

    var clusters = [
      { x: 0.16 * IW, y: 0.44 * IH },
      { x: 0.36 * IW, y: 0.62 * IH },
      { x: 0.56 * IW, y: 0.36 * IH },
      { x: 0.74 * IW, y: 0.60 * IH },
      { x: 0.89 * IW, y: 0.38 * IH }
    ];

    var narrow = (canvas.clientWidth || IW) < 640;
    var count = narrow ? 70 : 140;
    var rnd = mulberry32(20261018);
    var parts = [];
    for (var i = 0; i < count; i++) {
      parts.push({
        x: rnd() * IW,
        y: rnd() * IH,
        vx: (rnd() - 0.5) * 22,
        vy: (rnd() - 0.5) * 22,
        r: 1.5 + rnd() * 1.2,
        k: i % clusters.length,
        ph: rnd() * Math.PI * 2
      });
    }

    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var cssW = canvas.clientWidth || IW;
      var cssH = Math.round(cssW * IH / IW);
      canvas.width = Math.max(1, Math.round(cssW * dpr));
      canvas.height = Math.max(1, Math.round(cssH * dpr));
      ctx.setTransform(canvas.width / IW, 0, 0, canvas.height / IH, 0, 0);
    }
    window.addEventListener('resize', resize);
    resize();

    // pull in [0,1]: 0 = free drift, 1 = gathered into constellations.
    function step(dt, pull, nowMs) {
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        var c = clusters[p.k];
        var spring = pull * 0.55;
        p.vx += ((c.x - p.x) * spring + Math.cos(nowMs / 1700 + p.ph) * 5) * dt;
        p.vy += ((c.y - p.y) * spring + Math.sin(nowMs / 2100 + p.ph) * 5) * dt;
        var damp = Math.max(0, 1 - 1.6 * dt);
        p.vx *= damp;
        p.vy *= damp;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        if (p.x < 0) p.x += IW; else if (p.x > IW) p.x -= IW;
        if (p.y < 0) p.y += IH; else if (p.y > IH) p.y -= IH;
      }
    }

    function draw(pull, nowMs) {
      ctx.fillStyle = '#0b1220';
      ctx.fillRect(0, 0, IW, IH);
      var i, p, c, dx, dy, d2;
      // Threads between same-cluster neighbours.
      ctx.lineWidth = 1;
      for (i = 0; i < parts.length; i++) {
        p = parts[i];
        for (var j = i + 1; j < parts.length; j++) {
          var q = parts[j];
          if (q.k !== p.k) continue;
          dx = q.x - p.x; dy = q.y - p.y;
          d2 = dx * dx + dy * dy;
          if (d2 < 8100) {
            var a = (0.04 + 0.22 * pull) * (1 - Math.sqrt(d2) / 90);
            if (a > 0.01) {
              ctx.strokeStyle = 'rgba(45,212,191,' + a.toFixed(3) + ')';
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(q.x, q.y);
              ctx.stroke();
            }
          }
        }
      }
      // Teal constellation nodes.
      for (i = 0; i < clusters.length; i++) {
        c = clusters[i];
        var pulse = 4.5 + Math.sin(nowMs / 2400 + i * 1.3) * 0.8;
        ctx.fillStyle = '#2dd4bf';
        ctx.beginPath();
        ctx.arc(c.x, c.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(45,212,191,' + (0.35 + 0.3 * pull).toFixed(3) + ')';
        ctx.beginPath();
        ctx.arc(c.x, c.y, 4 + pulse * (0.5 + pull), 0, Math.PI * 2);
        ctx.stroke();
      }
      // Amber particles, warming toward the clusters as pull rises.
      for (i = 0; i < parts.length; i++) {
        p = parts[i];
        c = clusters[p.k];
        dx = c.x - p.x; dy = c.y - p.y;
        var near = Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / 320);
        var warm = Math.round(245 - 35 * near * pull);
        ctx.fillStyle = 'rgb(' + warm + ',' +
          Math.round(165 + 20 * near * pull) + ',' +
          Math.round(36 + 140 * near * pull) + ')';
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    if (reduced) {
      // Single static composed frame: settle the simulation, draw once.
      for (var s = 0; s < 1500; s++) step(1 / 60, 1, s * 16.7);
      draw(1, 0);
      return;
    }

    var startMs = 0;
    var visible = true;
    var rafId = null;
    var last = 0;

    function frame(nowMs) {
      rafId = null;
      if (!visible || (document.hidden)) return;
      var dt = (nowMs - last) / 1000;
      last = nowMs;
      if (!(dt > 0)) dt = 0.016;
      if (dt > 0.1) dt = 0.1;
      if (startMs === 0) startMs = nowMs;
      var phase = (nowMs - startMs) / 24000;
      if (phase > 1) phase = 1;
      var pull = phase * phase * (3 - 2 * phase);
      step(dt, pull, nowMs);
      draw(pull, nowMs);
      rafId = window.requestAnimationFrame(frame);
    }

    function kick() {
      if (rafId === null && visible && !document.hidden) {
        last = window.performance ? window.performance.now() : Date.now();
        rafId = window.requestAnimationFrame(frame);
      }
    }

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        visible = entries.length ? entries[0].isIntersecting : true;
        if (visible) kick();
      }, { threshold: 0.05 }).observe(canvas);
    }
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) kick();
    });
    kick();
  }

  initCounters();
  initHero();
})();
