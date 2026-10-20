// TRACE landing hero + proof counters — vanilla JS, no dependencies.
//
// Canvas: REAL membership from the recorded 20K run
// (docs/assets/hero20k.json, built by tools/build_hero20k.py from
// docs/explorer/local_20k_data.json): 144 atoms gather toward their real
// schema anchors (51 parents). Atoms in one of the 8 multi-parent leaves
// draw a second dashed pink edge to their other parent, mirroring the
// explorer's layout20kFull pattern. Layout is illustrative (deterministic
// circle + id-hash jitter); membership is real. No data, numbers, or text
// are ever drawn on the canvas.
// If the sidecar payload cannot be fetched (e.g. file:// preview), the hero
// falls back to abstract art so the page never breaks.
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

  // FNV-1a over a short hex id: deterministic jitter per atom, no RNG state.
  function hash32(str) {
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  // Real-membership sim: 51 parent anchors on a deterministic circle
  // (explorer layout20kFull pattern), 144 atoms bound to their real parent
  // anchor(s). part.a = primary anchor idx, part.b = secondary or -1.
  function buildRealSim(payload) {
    var parents = payload.parents;
    var anchors = [];
    var i;
    for (i = 0; i < parents.length; i++) {
      var angle = (i / parents.length) * Math.PI * 2;
      anchors.push({
        x: IW / 2 + Math.cos(angle) * 125,
        y: IH / 2 + Math.sin(angle) * 125
      });
    }
    var parts = [];
    for (i = 0; i < payload.atoms.length; i++) {
      var cells = String(payload.atoms[i]).split(':');
      var a = parseInt(cells[1], 10);
      var b = cells.length > 2 ? parseInt(cells[2], 10) : -1;
      if (!(a >= 0 && a < anchors.length)) return null;
      if (b !== -1 && !(b >= 0 && b < anchors.length)) return null;
      var h1 = hash32(cells[0] + 'p');
      var h2 = hash32(cells[0] + 'q');
      var ja = (h1 % 360) / 360 * Math.PI * 2;
      var jr = 10 + (h1 % 40);
      parts.push({
        x: anchors[a].x + Math.cos(ja) * jr,
        y: anchors[a].y + Math.sin(ja) * jr * 0.6,
        vx: ((h2 % 200) - 100) / 100 * 11,
        vy: (((h2 >> 8) % 200) - 100) / 100 * 11,
        r: 1.5 + (h1 % 12) / 10,
        a: a,
        b: b,
        ph: (h2 % 628) / 100
      });
    }
    return { anchors: anchors, parts: parts };
  }

  // Abstract fallback: 5 centers, round-robin parts. Page never breaks when
  // the sidecar is unreachable; the caption's real-membership claim applies
  // to the served site, which always ships the sidecar next to this file.
  function buildFallbackSim() {
    var anchors = [
      { x: 0.16 * IW, y: 0.44 * IH },
      { x: 0.36 * IW, y: 0.62 * IH },
      { x: 0.56 * IW, y: 0.36 * IH },
      { x: 0.74 * IW, y: 0.60 * IH },
      { x: 0.89 * IW, y: 0.38 * IH }
    ];
    var seed = 20261018;
    function rnd() {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    var parts = [];
    for (var i = 0; i < 140; i++) {
      var k = i % anchors.length;
      parts.push({
        x: rnd() * IW,
        y: rnd() * IH,
        vx: (rnd() - 0.5) * 22,
        vy: (rnd() - 0.5) * 22,
        r: 1.5 + rnd() * 1.2,
        a: k,
        b: -1,
        ph: rnd() * Math.PI * 2
      });
    }
    return { anchors: anchors, parts: parts };
  }

  function loadPayload() {
    if (!window.fetch) return Promise.resolve(null);
    // Landing serves this file from docs/; the recording page reuses it from
    // docs/recording/, so try both relative sidecar paths.
    var urls = ['assets/hero20k.json', '../assets/hero20k.json'];
    function attempt(i) {
      if (i >= urls.length) return Promise.resolve(null);
      return window.fetch(urls[i]).then(function (res) {
        if (!res || !res.ok) return attempt(i + 1);
        return res.json().then(function (data) {
          if (!data || !data.parents || !data.atoms) return attempt(i + 1);
          if (data.parents.length !== 51 || data.atoms.length !== 144) {
            return attempt(i + 1);
          }
          return data;
        }, function () { return attempt(i + 1); });
      }, function () { return attempt(i + 1); });
    }
    return attempt(0);
  }

  function initHero() {
    var canvas = document.getElementById('hero-canvas');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var reduced = reduceMotion();

    // Paint the field immediately so no frame is ever blank.
    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, IW, IH);

    loadPayload().then(function (data) {
      var sim = data ? buildRealSim(data) : null;
      if (!sim) sim = buildFallbackSim();
      canvas._traceAtoms = (data && data.atoms && data.atoms.length === 144) ?
        data.atoms : null;
      run(sim);
    });

    function run(sim) {
      var anchors = sim.anchors;
      var parts = sim.parts;
      // Live positions for the zoom-to-atom provenance reader below.
      canvas._traceLive = { parts: parts, anchors: anchors };

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

      // pull in [0,1]: 0 = free drift, 1 = gathered onto real anchors.
      function step(dt, pull, nowMs) {
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i];
          var c = anchors[p.a];
          var spring = pull * 0.55;
          p.vx += ((c.x - p.x) * spring + Math.cos(nowMs / 1700 + p.ph) * 5) * dt;
          p.vy += ((c.y - p.y) * spring + Math.sin(nowMs / 2100 + p.ph) * 5) * dt;
          if (p.b >= 0) {
            // Weaker pull toward the second real parent (multi-parent leaf).
            var d = anchors[p.b];
            var weak = pull * 0.14;
            p.vx += (d.x - p.x) * weak * dt;
            p.vy += (d.y - p.y) * weak * dt;
          }
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
        var i, p, c, dx, dy;
        // Solid teal spokes: every atom to its REAL primary parent anchor.
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(45,212,191,' + (0.05 + 0.20 * pull).toFixed(3) + ')';
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          c = anchors[p.a];
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(c.x, c.y);
        }
        ctx.stroke();
        // Dashed pink spokes: second edge for multi-parent atoms only.
        ctx.strokeStyle = 'rgba(236,72,153,' + (0.10 + 0.40 * pull).toFixed(3) + ')';
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          if (p.b < 0) continue;
          c = anchors[p.b];
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(c.x, c.y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        // Teal schema anchors.
        for (i = 0; i < anchors.length; i++) {
          c = anchors[i];
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
        // Amber particles, warming toward teal as they settle on anchors.
        for (i = 0; i < parts.length; i++) {
          p = parts[i];
          c = anchors[p.a];
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
  }

  initCounters();
  initHero();

  // ---------- Zoom-to-atom provenance ----------
  // Click/keyboard: nearest live particle -> real title/snippet/parent
  // from hero20k.json (prefix match) + explorer/local_20k_data.json.
  // Text-only panel update; never draws text on canvas.
  function initProvenance() {
    var canvas = document.getElementById('hero-canvas');
    var panel = document.getElementById('atom-panel');
    if (!canvas || !panel) return;
    var cache20k = null;

    function esc(s) {
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function load20k() {
      if (cache20k) return Promise.resolve(cache20k);
      if (!window.fetch) return Promise.resolve(null);
      var urls = ['explorer/local_20k_data.json', '../explorer/local_20k_data.json'];
      function attempt(i) {
        if (i >= urls.length) return Promise.resolve(null);
        return window.fetch(urls[i]).then(function (res) {
          if (!res || !res.ok) return attempt(i + 1);
          return res.json().then(function (data) {
            cache20k = data;
            return data;
          }, function () { return attempt(i + 1); });
        }, function () { return attempt(i + 1); });
      }
      return attempt(0);
    }

    function pick(clientX, clientY) {
      var live = canvas._traceLive;
      var atoms = canvas._traceAtoms;
      if (!live || !atoms) return -1;
      var rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return -1;
      var ix = (clientX - rect.left) / rect.width * 880;
      var iy = (clientY - rect.top) / rect.height * 360;
      var best = -1, bestD = 28 * 28; // 28 internal px radius
      for (var i = 0; i < live.parts.length; i++) {
        var dx = live.parts[i].x - ix, dy = live.parts[i].y - iy;
        var d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = i; }
      }
      return best;
    }

    function show(idx) {
      if (idx < 0) {
        panel.textContent = 'No atom near that point — try another dot.';
        return;
      }
      var entry = String(canvas._traceAtoms[idx]).split(':');
      var prefix = entry[0];
      load20k().then(function (data) {
        if (!data || !data.atoms) {
          panel.textContent = 'Atom ' + prefix + '… (viewer data unreachable).';
          return;
        }
        var hit = null;
        for (var i = 0; i < data.atoms.length; i++) {
          if (String(data.atoms[i].id).slice(0, 8) === prefix) {
            hit = data.atoms[i];
            break;
          }
        }
        if (!hit) {
          panel.textContent = 'Atom ' + prefix + '… (no viewer record).';
          return;
        }
        var leaf = (hit.leaf_ids || [])[0] || '?';
        var parent = '?';
        if (data.leaves) {
          for (var j = 0; j < data.leaves.length; j++) {
            if (data.leaves[j].id === leaf) {
              parent = ((data.leaves[j].parent_ids || [])[0]) || '?';
              break;
            }
          }
        }
        panel.innerHTML = '<span class="t">' + esc(hit.title || '(untitled)') +
          '</span><br>“' + esc((hit.snippet || '').slice(0, 220)) +
          '…”<br><span>atom ' + esc(String(hit.id).slice(0, 12)) +
          '… · leaf ' + esc(leaf) + ' · parent schema ' + esc(parent) +
          ' · doc ' + esc(hit.doc_id || '?') + '</span>';
      });
    }

    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('role', 'button');
    canvas.addEventListener('click', function (ev) {
      show(pick(ev.clientX, ev.clientY));
    });
    canvas.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        var rect = canvas.getBoundingClientRect();
        show(pick(rect.left + rect.width / 2, rect.top + rect.height / 2));
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProvenance);
  } else {
    initProvenance();
  }
})();
