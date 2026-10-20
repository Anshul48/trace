/* Shared motion rig v2 — trace docs/assets/motion.js.
   R1: extends the v1 reveal/anchor helper (API kept) with the R5
   motion-graphics-spec rig: exact easing tokens, f(t) timeline, 2D camera,
   stagger, linear counters, kinetic captions. Zero deps. Deterministic:
   no wall-clock inside frame(); seeded RNG for layouts.
   NOTE: anima's copy syncs in R2 (anima untouched in R1). */
(function () {
  'use strict';

  var DUR = { fast: 150, base: 250, slow: 400, slower: 600 };

  function reducedMotion() {
    return window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ---------- v1: progressive reveal + smooth anchors (unchanged) ---------- */

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

  /* ---------- v2 rig: easings (spec §2, exact) ---------- */

  var EASE_CSS = {
    enter: 'cubic-bezier(0.05, 0.7, 0.1, 1)',
    exit: 'cubic-bezier(0.3, 0, 0.8, 0.15)',
    move: 'cubic-bezier(0.2, 0, 0, 1)',
    snap: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    linear: 'linear'
  };

  // Cubic-bezier solver (y for x), Newton + bisection fallback.
  function cubicBezier(x1, y1, x2, y2) {
    function bx(t) {
      var u = 1 - t;
      return 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t;
    }
    function by(t) {
      var u = 1 - t;
      return 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t;
    }
    function dx(t) {
      var u = 1 - t;
      return 3 * u * u * x1 + 6 * u * t * (x2 - x1) + 3 * t * t * (1 - x2);
    }
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      var t = x;
      for (var i = 0; i < 5; i++) {
        var d = dx(t);
        if (Math.abs(d) < 1e-4) break;
        var n = t - (bx(t) - x) / d;
        if (n < 0 || n > 1) break;
        t = n;
      }
      var lo = 0, hi = 1;
      while (hi - lo > 1e-4) {
        var v = bx(t);
        if (Math.abs(v - x) < 1e-4) break;
        if (v < x) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return by(t);
    };
  }

  var EASE = {
    enter: cubicBezier(0.05, 0.7, 0.1, 1),
    exit: cubicBezier(0.3, 0, 0.8, 0.15),
    move: cubicBezier(0.2, 0, 0, 1),
    snap: cubicBezier(0.34, 1.56, 0.64, 1),
    linear: function (t) { return t; }
  };

  /* ---------- v2 rig: f(t) primitives ---------- */

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  // Progress of t within [t0,t1], eased. Before: 0. After: 1.
  function seg(t, t0, t1, ease) {
    if (t1 <= t0) return t < t0 ? 0 : 1;
    var p = clamp01((t - t0) / (t1 - t0));
    return (ease || EASE.linear)(p);
  }

  // Envelope: 0 → 1 over [t0,t1], hold, 1 → 0 over [t2,t3].
  function env(t, t0, t1, t2, t3, easeIn, easeOut) {
    if (t < t0) return 0;
    if (t < t1) return (easeIn || EASE.enter)(clamp01((t - t0) / (t1 - t0)));
    if (t < t2) return 1;
    if (t < t3) return 1 - (easeOut || EASE.exit)(clamp01((t - t2) / (t3 - t2)));
    return 0;
  }

  // Stagger delay for item i: 60–90ms steps, max 12 staggered (spec §2).
  function staggerDelay(i, stepMs, maxItems) {
    var step = (stepMs == null ? 75 : stepMs) / 1000;
    var cap = maxItems == null ? 12 : maxItems;
    return Math.min(i, cap - 1) * step;
  }

  // Linear counter: data moves linearly (§2). Returns display value.
  function counter(t, t0, dur, from, to) {
    return lerp(from, to, seg(t, t0, t0 + dur, EASE.linear));
  }

  // Anticipation pullback before a kill/death/merge snap (§2): scale dip.
  function anticipate(t, tHit, pullMs, depth) {
    var pull = (pullMs == null ? 250 : pullMs) / 1000;
    var d = depth == null ? 0.03 : depth;
    if (t < tHit - pull || t >= tHit) return 1;
    return 1 - d * EASE.move((t - (tHit - pull)) / pull);
  }

  // Deterministic RNG (mulberry32) for layouts.
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ---------- v2 rig: 2D camera (§4) ---------- */

  // keys: [{t, cx, cy, scale}] in world units. view: {w, h} output px.
  // Returns {x, y, k} mapping world→screen each frame; eased with move.
  function createCamera(keys, view) {
    var ks = keys.slice().sort(function (a, b) { return a.t - b.t; });
    function at(t) {
      var i = 0;
      while (i < ks.length - 1 && t >= ks[i + 1].t) i++;
      var a = ks[i], b = ks[Math.min(i + 1, ks.length - 1)];
      var p = (b.t > a.t) ? EASE.move(clamp01((t - a.t) / (b.t - a.t))) : 1;
      var cx = lerp(a.cx, b.cx, p), cy = lerp(a.cy, b.cy, p);
      var s = lerp(a.scale, b.scale, p);
      return { cx: cx, cy: cy, scale: s };
    }
    function apply(ctx, t) {
      var c = at(t);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.translate(view.w / 2, view.h / 2);
      ctx.scale(c.scale, c.scale);
      ctx.translate(-c.cx, -c.cy);
      return c;
    }
    // SVG variant: set viewBox on el each frame.
    function applySVG(el, t) {
      var c = at(t);
      var w = view.w / c.scale, h = view.h / c.scale;
      el.setAttribute('viewBox',
        (c.cx - w / 2) + ' ' + (c.cy - h / 2) + ' ' + w + ' ' + h);
      return c;
    }
    return { at: at, apply: apply, applySVG: applySVG };
  }

  /* ---------- v2 rig: beat timeline (§8/§12) ---------- */

  // beats: [{id, start, end}] from timings.json. Returns index + local p.
  function createTimeline(beats, duration) {
    function at(t) {
      var idx = 0;
      for (var i = 0; i < beats.length; i++) {
        if (t >= beats[i].start) idx = i;
      }
      var b = beats[idx];
      var p = (b.end > b.start) ? clamp01((t - b.start) / (b.end - b.start)) : 1;
      return { index: idx, beat: b, p: p, t: t, duration: duration };
    }
    return { beats: beats, duration: duration, at: at };
  }

  /* ---------- v2 rig: kinetic captions (§3) ---------- */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // One idea per caption; KEY TERM emphasized exactly when spoken.
  // emphAt: [[startSec, endSec]] windows where the key term pops.
  function renderCaption(el, text, keyTerm, t, emphWindows) {
    var emph = false;
    (emphWindows || []).forEach(function (w) {
      if (t >= w[0] && t < w[1]) emph = true;
    });
    if (!keyTerm || text.indexOf(keyTerm) === -1) {
      el.innerHTML = esc(text);
      return;
    }
    var parts = text.split(keyTerm);
    el.innerHTML = esc(parts[0]) +
      '<span class="key' + (emph ? ' on' : '') + '">' + esc(keyTerm) + '</span>' +
      esc(parts.slice(1).join(keyTerm));
  }

  /* ---------- v2 rig: honesty chips (§5/§9) ---------- */

  function chipHTML(kind, text) {
    return '<span class="mrig-chip mrig-' + kind.toLowerCase() + '">' +
      esc(kind) + ' · ' + esc(text) + '</span>';
  }

  /* ---------- exports ---------- */

  document.addEventListener('DOMContentLoaded', function () {
    initReveal();
    initAnchors();
  });

  window.siteMotion = { durations: DUR, reducedMotion: reducedMotion };
  window.MotionRig = {
    durations: DUR, reducedMotion: reducedMotion,
    EASE_CSS: EASE_CSS, EASE: EASE,
    clamp01: clamp01, lerp: lerp, seg: seg, env: env,
    staggerDelay: staggerDelay, counter: counter,
    anticipate: anticipate, rng: rng,
    createCamera: createCamera, createTimeline: createTimeline,
    renderCaption: renderCaption, chipHTML: chipHTML, esc: esc
  };
})();
