/* SPDX-License-Identifier: Apache-2.0
 * The organizing pile: 20,000 dots stand in for the 812,545 passages of the sealed library.
 * It is an ILLUSTRATION. Where each dot sits and how many groups there are is drawn.
 * What is real: the proportions (4 equal parts; a question wakes 0.79% of one part,
 * drawn as 40 of 5,000 dots) and the counts quoted in the captions.
 * Plain JavaScript, no libraries, no network requests. Reads colours from tokens.css.
 */
(function () {
  "use strict";

  var N = 20000, PARTS = 4, PER = N / PARTS, WOKEN = 40, RINGS = 10;
  var GROUPS_PER_PART = 24;

  var STAGES = {
    1: { name: "A pile",
         text: "<b>A library grows.</b> New passages just arrive, in no order. Nobody files them.",
         label: "A growing pile of 20,000 dots, one for every 41 passages, scattered with no order." },
    2: { name: "It sorts itself",
         text: "<b>The passages sort themselves into groups</b> of similar meaning. The order comes from the passages themselves, not from labels people add.",
         label: "The same dots have drifted into groups, in four equal parts." },
    3: { name: "A question wakes a part",
         text: "<b>A question wakes only a small part.</b> Here: 40 of 5,000 dots in one of four equal parts (0.8%; our measured average is 0.79%). The ringed dots are the ten best matches. A plain scan would wake every dot.",
         label: "A question has lit 40 dots in the first of the four parts, with ten ringed as best matches. All other dots are dim." }
  };

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gauss(rnd) { var u = 0, v = 0; while (u === 0) u = rnd(); while (v === 0) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
  function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }
  function smooth(x) { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); }

  function parseColor(s) {
    s = (s || "").trim();
    var m = /^#([0-9a-f]{6})$/i.exec(s);
    if (m) { var n = parseInt(m[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
    m = /^#([0-9a-f]{3})$/i.exec(s);
    if (m) { var h = m[1]; return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)]; }
    m = /rgba?\(([^)]+)\)/.exec(s);
    if (m) { var p = m[1].split(",").map(parseFloat); return [p[0], p[1], p[2]]; }
    return [120, 140, 200];
  }
  function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function css(c) { return "rgb(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + ")"; }

  function mount(root, opts) {
    opts = opts || {};
    var canvas = root.querySelector("canvas");
    if (!canvas || !canvas.getContext) return null;
    var ctx = canvas.getContext("2d");
    var captionEl = root.querySelector(".pile-caption");
    var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-stage]"));
    var playBtn = root.querySelector("[data-play]");
    var hudCount = root.querySelector("[data-hud=count]");
    var hudNote = root.querySelector("[data-hud=note]");
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---- colours from the tokens ----
    var C = {};
    function readColors() {
      var cs = getComputedStyle(document.documentElement);
      function v(n, d) { return parseColor(cs.getPropertyValue(n) || d); }
      C.dot = v("--dot", "#5d78b8"); C.group = v("--dot-group", "#7fa6e8");
      C.lit = v("--dot-lit", "#2fd6c2"); C.dim = v("--dot-dim", "#26345c");
      C.ink = v("--stage-ink", "#eef3ff"); C.muted = v("--stage-muted", "#a9b6d8");
      C.line = v("--stage-line", "#243255");
    }
    readColors();

    // ---- dots ----
    var rnd = mulberry32(20261104);
    var arrival = new Float32Array(N), delay = new Float32Array(N), part = new Uint8Array(N);
    var grp = new Uint8Array(N), pu = new Float32Array(N), pv = new Float32Array(N);
    var gx = new Float32Array(N), gy = new Float32Array(N), px = new Float32Array(N), py = new Float32Array(N);
    var lit = new Uint8Array(N); // 0 none, 1 woken, 2 woken and ringed
    var order = [], i, k;
    for (i = 0; i < N; i++) { order.push(i); part[i] = (i / PER) | 0; }
    for (i = N - 1; i > 0; i--) { k = (rnd() * (i + 1)) | 0; var tmp = order[i]; order[i] = order[k]; order[k] = tmp; }
    for (i = 0; i < N; i++) { arrival[order[i]] = i / N; delay[i] = rnd() * 0.55; pu[i] = rnd(); pv[i] = rnd(); }
    // per-dot group choice and offset normals, fixed once
    var gW = [], gcu = [], gcv = [], gNorm = new Float32Array(N * 2);
    var p, g;
    for (p = 0; p < PARTS; p++) {
      var w = [], sum = 0;
      for (g = 0; g < GROUPS_PER_PART; g++) { var x = Math.exp(gauss(rnd) * 0.55); w.push(x); sum += x; }
      gW.push(w.map(function (x) { return x / sum; }));
      var cu = [], cv = [];
      for (g = 0; g < GROUPS_PER_PART; g++) { cu.push(rnd()); cv.push(rnd()); }
      gcu.push(cu); gcv.push(cv);
    }
    for (i = 0; i < N; i++) {
      var r = rnd(), acc = 0, pp = part[i], gi = GROUPS_PER_PART - 1;
      for (g = 0; g < GROUPS_PER_PART; g++) { acc += gW[pp][g]; if (r <= acc) { gi = g; break; } }
      grp[i] = gi; gNorm[2 * i] = gauss(rnd); gNorm[2 * i + 1] = gauss(rnd);
    }

    // ---- layout (recomputed on resize; deterministic) ----
    var W = 0, H = 0, dpr = 1, rects = [], dotSize = 1.6, ready = false;
    var qx = 0, qy = 0; // question point (part 0)
    function layout() {
      var box = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = Math.max(280, Math.round(box.width * dpr)); H = Math.max(240, Math.round(box.height * dpr));
      canvas.width = W; canvas.height = H;
      var wide = box.width / box.height > 1.5, gap = 14 * dpr, pad = 8 * dpr, top = 26 * dpr;
      rects = [];
      for (p = 0; p < PARTS; p++) {
        var rw, rh, rx, ry;
        if (wide) { rw = (W - gap * 3 - pad * 2) / 4; rh = H - pad * 2 - top; rx = pad + p * (rw + gap); ry = pad + top; }
        else { rw = (W - gap - pad * 2) / 2; rh = (H - gap - pad * 2 - top * 2) / 2; rx = pad + (p % 2) * (rw + gap); ry = pad + top + ((p / 2) | 0) * (rh + gap + top); }
        rects.push({ x: rx, y: ry, w: rw, h: rh });
      }
      dotSize = Math.max(1.3 * dpr, Math.min(rects[0].w, rects[0].h) / 150);
      // group centres per part: best-candidate sampling so groups do not overlap much
      var sdBase = 0.052 * Math.min(rects[0].w, rects[0].h);
      for (p = 0; p < PARTS; p++) {
        var rc = rects[p], centres = [], radii = [];
        var idx = []; for (g = 0; g < GROUPS_PER_PART; g++) idx.push(g);
        idx.sort(function (a, b) { return gW[p][b] - gW[p][a]; });
        var rr = mulberry32(777 + p);
        var cx = new Array(GROUPS_PER_PART), cy = new Array(GROUPS_PER_PART), sd = new Array(GROUPS_PER_PART);
        for (var ii = 0; ii < idx.length; ii++) {
          g = idx[ii];
          var s = sdBase * Math.sqrt(gW[p][g] * GROUPS_PER_PART);
          var best = null, bestScore = -1e9;
          for (var c = 0; c < 28; c++) {
            var cxx = rc.x + s * 2 + rr() * (rc.w - s * 4), cyy = rc.y + s * 2 + rr() * (rc.h - s * 4), score = 1e9;
            for (var j = 0; j < centres.length; j++) {
              var dx = cxx - centres[j][0], dy = cyy - centres[j][1];
              score = Math.min(score, Math.sqrt(dx * dx + dy * dy) - (s + radii[j]) * 1.6);
            }
            if (score > bestScore) { bestScore = score; best = [cxx, cyy]; }
          }
          centres.push(best); radii.push(s); cx[g] = best[0]; cy[g] = best[1]; sd[g] = s;
        }
        gcu[p] = cx; gcv[p] = cy; gW[p].sd = sd;
      }
      for (i = 0; i < N; i++) {
        var q = part[i], rc2 = rects[q], gg = grp[i];
        px[i] = rc2.x + 4 * dpr + pu[i] * (rc2.w - 8 * dpr);
        py[i] = rc2.y + 4 * dpr + pv[i] * (rc2.h - 8 * dpr);
        var sdv = gW[q].sd[gg] * 0.9;
        gx[i] = clamp(gcu[q][gg] + gNorm[2 * i] * sdv, rc2.x + 3 * dpr, rc2.x + rc2.w - 3 * dpr);
        gy[i] = clamp(gcv[q][gg] + gNorm[2 * i + 1] * sdv, rc2.y + 3 * dpr, rc2.y + rc2.h - 3 * dpr);
      }
      // the question: a point inside part 0; wake 10 nearest dots from each of the 4 nearest groups
      var rc0 = rects[0]; qx = rc0.x + rc0.w * 0.5; qy = rc0.y + rc0.h * 0.46;
      var gd = [];
      for (g = 0; g < GROUPS_PER_PART; g++) { var ddx = gcu[0][g] - qx, ddy = gcv[0][g] - qy; gd.push([Math.sqrt(ddx * ddx + ddy * ddy), g]); }
      gd.sort(function (a, b) { return a[0] - b[0]; });
      for (i = 0; i < N; i++) lit[i] = 0;
      var wokenIdx = [];
      for (var t4 = 0; t4 < 4; t4++) {
        var gsel = gd[t4][1], cand = [];
        for (i = 0; i < PER; i++) if (grp[i] === gsel) { var ex = gx[i] - qx, ey = gy[i] - qy; cand.push([ex * ex + ey * ey, i]); }
        cand.sort(function (a, b) { return a[0] - b[0]; });
        for (var u = 0; u < Math.min(10, cand.length); u++) { lit[cand[u][1]] = 1; wokenIdx.push(cand[u]); }
      }
      // if a group had fewer than 10 dots, top up from the nearest dots overall so the total stays 40
      if (wokenIdx.length < WOKEN) {
        var more = [];
        for (i = 0; i < PER; i++) if (!lit[i]) { var fx = gx[i] - qx, fy = gy[i] - qy; more.push([fx * fx + fy * fy, i]); }
        more.sort(function (a, b) { return a[0] - b[0]; });
        for (var m = 0; wokenIdx.length < WOKEN && m < more.length; m++) { lit[more[m][1]] = 1; wokenIdx.push(more[m]); }
      }
      wokenIdx.sort(function (a, b) { return a[0] - b[0]; });
      for (var rg = 0; rg < Math.min(RINGS, wokenIdx.length); rg++) lit[wokenIdx[rg][1]] = 2;
      ready = true; dirty = true;
    }

    // ---- state ----
    var stage = 1, target = [0, 1, 0, 0], tval = [0, 0, 0, 0]; // index 1..3
    var dur = [0, 3.4, 4.8, 2.6];
    var dirty = true, raf = 0, last = 0, visible = true, playing = !reduce, userStopped = false, holdLeft = 0, loopStart = 0;
    var LEVELS = 14, ramp = [], lv = new Uint8Array(N), cnt = new Uint32Array(LEVELS), ord = new Uint32Array(N);

    function buildRamp() {
      readColors(); ramp = [];
      for (var l = 0; l < LEVELS; l++) ramp.push(css(mix(C.dot, C.group, l / (LEVELS - 1))));
    }
    buildRamp();

    function setStageUI() {
      tabs.forEach(function (b) { b.setAttribute("aria-pressed", String(+b.getAttribute("data-stage") === stage)); });
      if (captionEl) captionEl.innerHTML = STAGES[stage].text;
      canvas.setAttribute("aria-label", "Illustration. " + STAGES[stage].label);
      if (playBtn) { playBtn.textContent = playing ? "Pause" : "Play"; playBtn.setAttribute("aria-pressed", String(playing)); }
    }

    function setStage(n, instant) {
      stage = n;
      target = [0, n >= 1 ? 1 : 0, n >= 2 ? 1 : 0, n >= 3 ? 1 : 0];
      if (instant) { tval = [0, target[1], target[2], target[3]]; }
      setStageUI(); dirty = true; kick();
    }

    function drawLabels() {
      ctx.font = (12 * dpr) + "px system-ui, sans-serif"; ctx.textBaseline = "alphabetic"; ctx.textAlign = "left";
      var t3 = smooth(tval[3]);
      for (p = 0; p < PARTS; p++) {
        var rc = rects[p];
        ctx.strokeStyle = "rgba(" + (C.line[0] | 0) + "," + (C.line[1] | 0) + "," + (C.line[2] | 0) + ",0.9)"; ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(rc.x - 2 * dpr, rc.y - 2 * dpr, rc.w + 4 * dpr, rc.h + 4 * dpr);
        var label = "Part " + (p + 1) + " of 4";
        if (p === 0 && t3 > 0.3) label += " (measured)";
        else if (p > 0 && t3 > 0.3) label += " (same layout, not measured)";
        ctx.fillStyle = css(C.muted);
        ctx.fillText(label, rc.x, rc.y - 8 * dpr);
      }
    }

    function draw() {
      if (!ready) return;
      ctx.clearRect(0, 0, W, H);
      drawLabels();
      var t1 = smooth(tval[1]), t2 = tval[2], t3 = smooth(tval[3]);
      var s = dotSize, nvis = 0, l;
      for (l = 0; l < LEVELS; l++) cnt[l] = 0;
      var dimMix = t3; // 0 = normal, 1 = dimmed
      for (i = 0; i < N; i++) {
        var vis = arrival[i] <= t1; if (!vis) { lv[i] = 255; continue; }
        var pr = smooth((t2 - delay[i] * 0.9) / 0.45);
        var level = Math.round(pr * (LEVELS - 1)); lv[i] = level; cnt[level]++; nvis++;
      }
      // counting sort by level so each colour is set once
      var start = new Uint32Array(LEVELS), acc = 0;
      for (l = 0; l < LEVELS; l++) { start[l] = acc; acc += cnt[l]; }
      for (i = 0; i < N; i++) { if (lv[i] !== 255) ord[start[lv[i]]++] = i; }
      var pos = 0, a = 1 - 0.78 * dimMix;
      for (l = 0; l < LEVELS; l++) {
        ctx.fillStyle = ramp[l];
        ctx.globalAlpha = a < 1 ? Math.max(0.16, a) : 1;
        var end = pos + cnt[l];
        for (; pos < end; pos++) {
          i = ord[pos];
          if (lit[i] && part[i] === 0 && t3 > 0.02) continue; // drawn below
          var pr2 = smooth((tval[2] - delay[i] * 0.9) / 0.45);
          var x = px[i] + (gx[i] - px[i]) * pr2, y = py[i] + (gy[i] - py[i]) * pr2;
          ctx.fillRect(x, y, s, s);
        }
      }
      ctx.globalAlpha = 1;
      // woken dots and rings
      if (t3 > 0.02) {
        var glowR = 7 * dpr * t3;
        for (i = 0; i < PER; i++) {
          if (!lit[i]) continue;
          var xx = gx[i], yy = gy[i];
          ctx.globalAlpha = 0.28 * t3; ctx.fillStyle = css(C.lit);
          ctx.beginPath(); ctx.arc(xx + s / 2, yy + s / 2, glowR, 0, 6.2832); ctx.fill();
          ctx.globalAlpha = 1; ctx.fillStyle = css(C.lit);
          var big = s * (1 + 1.2 * t3);
          ctx.fillRect(xx + s / 2 - big / 2, yy + s / 2 - big / 2, big, big);
          if (lit[i] === 2) {
            ctx.globalAlpha = t3; ctx.strokeStyle = css(C.ink); ctx.lineWidth = 1.4 * dpr;
            ctx.beginPath(); ctx.arc(xx + s / 2, yy + s / 2, 5 * dpr, 0, 6.2832); ctx.stroke();
          }
        }
        ctx.globalAlpha = t3; ctx.strokeStyle = css(C.lit); ctx.lineWidth = 1.2 * dpr; ctx.setLineDash([3 * dpr, 3 * dpr]);
        ctx.beginPath(); ctx.arc(qx, qy, 15 * dpr, 0, 6.2832); ctx.stroke(); ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }
      // HUD text (outside the canvas, aria-hidden)
      if (hudCount) {
        if (t3 > 0.5) hudCount.textContent = "Woken: " + WOKEN + " of " + PER.toLocaleString("en-US") + " dots in the measured part";
        else if (t2 > 0.5) hudCount.textContent = "No labels added by anyone";
        else hudCount.textContent = "Passages so far: " + Math.round(812545 * t1).toLocaleString("en-US");
      }
      if (hudNote) hudNote.textContent = t3 > 0.5 ? "A plain scan: all " + PER.toLocaleString("en-US") + " dots" : "20,000 dots stand in for 812,545 passages";
    }

    function step(now) {
      raf = 0;
      var dt = last ? Math.min(0.1, (now - last) / 1000) : 0; last = now;
      var moving = false, n;
      for (n = 1; n <= 3; n++) {
        var d = target[n] - tval[n];
        if (Math.abs(d) > 0.0005) {
          var rate = (d > 0 ? 1 : 2.2) / dur[n]; // going back is quicker
          tval[n] += Math.sign(d) * Math.min(Math.abs(d), rate * dt); moving = true;
        } else tval[n] = target[n];
      }
      if (moving || dirty) { draw(); dirty = false; }
      // autoplay sequencing
      if (playing && visible && !moving) {
        holdLeft -= dt;
        if (holdLeft <= 0) {
          if (stage === 1) { setStage(2); holdLeft = 2.6; }
          else if (stage === 2) { setStage(3); holdLeft = 7.5; }
          else { restart(); }
        }
      }
      if (moving || playing) raf = requestAnimationFrame(step);
      else last = 0;
    }
    function restart() { tval = [0, 0, 0, 0]; setStage(1); holdLeft = 1.8; }
    function kick() { if (!raf && visible && !document.hidden) { last = 0; raf = requestAnimationFrame(step); } }

    // ---- controls ----
    tabs.forEach(function (b) {
      b.addEventListener("click", function () {
        playing = false; userStopped = true; setStage(+b.getAttribute("data-stage"), reduce);
      });
    });
    if (playBtn) playBtn.addEventListener("click", function () {
      playing = !playing; setStageUI();
      if (playing) { holdLeft = 1.2; if (stage === 3 && tval[3] >= 1) holdLeft = 3; kick(); }
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting; if (visible) { dirty = true; kick(); } else if (raf) { cancelAnimationFrame(raf); raf = 0; last = 0; }
      }, { threshold: 0.12 }).observe(canvas);
    }
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { dirty = true; kick(); } else if (raf) { cancelAnimationFrame(raf); raf = 0; last = 0; } });
    var rto = 0;
    function onResize() { clearTimeout(rto); rto = setTimeout(function () { layout(); draw(); }, 120); }
    if ("ResizeObserver" in window) new ResizeObserver(onResize).observe(canvas); else window.addEventListener("resize", onResize);
    // theme change: colours are tokens, so re-read them
    var mo = new MutationObserver(function () { buildRamp(); dirty = true; kick(); });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    if (window.matchMedia) { var mq = window.matchMedia("(prefers-color-scheme: dark)"); if (mq.addEventListener) mq.addEventListener("change", function () { buildRamp(); dirty = true; kick(); }); }

    layout();
    if (reduce || opts.stage) { setStage(opts.stage || 3, true); playing = false; }
    else { setStage(1); holdLeft = 3.6; tval[1] = 0; }
    setStageUI(); draw(); kick();

    var api = { setStage: function (n, instant) { playing = false; setStage(n, instant !== false); draw(); setStageUI(); }, state: function () { return { stage: stage, t: tval.slice(), woken: WOKEN, dots: N }; } };
    return api;
  }

  function init() {
    var roots = document.querySelectorAll("[data-pile]");
    window.TraceOrganize = window.TraceOrganize || {};
    for (var i = 0; i < roots.length; i++) {
      var api = mount(roots[i], { stage: +roots[i].getAttribute("data-initial-stage") || 0 });
      if (api) { window.TraceOrganize.last = api; if (!window.TraceOrganize.list) window.TraceOrganize.list = []; window.TraceOrganize.list.push(api); }
    }
    window.TraceOrganize.setStage = function (n, instant) { (window.TraceOrganize.list || []).forEach(function (a) { a.setStage(n, instant); }); };
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
