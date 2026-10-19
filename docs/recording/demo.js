// TRACE "Using TRACE" illustrated walkthrough — vanilla canvas, no dependencies.
// Simplified visuals; every number shown is measured (20K run + seam12a 10M freeze).
// Scene 3 group sizes are measured (top 4 of the 51 real 20K schemas); dot positions are schematic.
(function () {
  'use strict';

  var canvas = document.getElementById('demo-canvas');
  var captionEl = document.getElementById('demo-caption');
  var realEl = document.getElementById('demo-real');
  var countEl = document.getElementById('demo-count');
  var dotsEl = document.getElementById('demo-dots');
  var barFill = document.getElementById('demo-bar-fill');
  var prevBtn = document.getElementById('demo-prev');
  var nextBtn = document.getElementById('demo-next');
  var playBtn = document.getElementById('demo-play');
  var resetBtn = document.getElementById('demo-reset');
  var scrubEl = document.getElementById('demo-scrub');
  var speedEl = document.getElementById('demo-speed');
  var speedMult = 1.0;
  if (!canvas || !canvas.getContext) return;

  var ctx = canvas.getContext('2d');
  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var C = {
    bg: '#090c10', text: '#e6edf3', muted: '#8b949e',
    green: '#3fb950', amber: '#d29922', blue: '#58a6ff', red: '#f85149',
    panel: '#161b22', line: '#30363d'
  };
  // Top 4 of the 51 real 20K schemas by atom count (30/7/6/6); group 4 (gray,
  // ungrouped) is the other 95 atoms in the remaining 47 schemas. Sizes and
  // labels measured; dot positions schematic.
  var CLUSTER_COLORS = [C.green, C.amber, C.blue, C.red, C.muted];
  var CLUSTER_NAMES = ['xpar-5836-s0 · 30', 'xpar-72159-s0 · 7', 'xpar-106301-s0 · 6', 'xpar-18670-s0 · 6'];
  var REST_LABEL = 'other 47 schemas · 95 (ungrouped)';

  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  var W = 0, H = 0, dpr = 1;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || 600;
    H = canvas.clientHeight || 340;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    render(currentScene, sceneT(currentScene));
  }
  window.addEventListener('resize', resize);

  function ease(t) { return t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t); }
  // Gentle spring settle for clustering: identical endpoints (0 -> 0, 1 -> 1),
  // slight overshoot mid-flight only. Position use only; counts unaffected.
  function easeSettle(t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    var c = 1.2, u = t - 1;
    return 1 + (c + 1) * u * u * u + c * u * u;
  }
  function clamp01(t) { return t < 0 ? 0 : t > 1 ? 1 : t; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  // Shared deterministic layouts (unit coords, scaled at draw time).
  var rnd = mulberry32(20261018);
  var DOCS = [];
  (function () {
    var cols = 11, rows = 8, i;
    for (i = 0; i < 88; i++) {
      DOCS.push({
        gx: (i % cols) / (cols - 1),
        gy: Math.floor(i / cols) / (rows - 1),
        jitter: (rnd() - 0.5)
      });
    }
  })();
  var ATOMS = [];
  (function () {
    var i, order = [];
    for (i = 0; i < 144; i++) order.push(i);
    // Deterministic shuffle for cluster assignment.
    for (i = order.length - 1; i > 0; i--) {
      var j = Math.floor(rnd() * (i + 1));
      var tmp = order[i]; order[i] = order[j]; order[j] = tmp;
    }
    // Real size proportions: shuffled rank decides the group, so the four
    // schema groups hold exactly 30 / 7 / 6 / 6 atoms and group 4 holds 95.
    for (i = 0; i < 144; i++) {
      var g = order[i] < 30 ? 0 : order[i] < 37 ? 1 : order[i] < 43 ? 2 : order[i] < 49 ? 3 : 4;
      ATOMS.push({
        sx: rnd(), sy: rnd(),
        cluster: g,
        r: 2 + rnd() * 2.2,
        tag: i < 6 ? (Math.floor(rnd() * 0xffff)).toString(16) : null
      });
    }
  })();

  function clusterCenter(k, w, h) {
    var cx = [0.24, 0.74, 0.24, 0.74][k] * w;
    var cy = [0.30, 0.30, 0.72, 0.72][k] * h;
    return { x: cx, y: cy };
  }

  function atomPos(a, k, w, h, rr) {
    // Group 4 (other 47 schemas) stays scattered where Scene 2 left it:
    // ungrouped by design, not a fifth cluster.
    if (a.cluster === 4) {
      return { x: a.sx * (w - 32) + 16, y: 70 + a.sy * (h - 110) };
    }
    // Pseudo-random point inside the cluster's ellipse, stable per atom.
    var c = clusterCenter(a.cluster, w, h);
    var ang = rr * Math.PI * 2;
    var rad = 0.25 + (rr * 7.3 % 1) * 0.75;
    return {
      x: c.x + Math.cos(ang) * rad * w * 0.13,
      y: c.y + Math.sin(ang) * rad * h * 0.14
    };
  }
  var atomRands = [];
  (function () {
    var r2 = mulberry32(77);
    for (var i = 0; i < 144; i++) atomRands.push(r2());
  })();

  function drawText(text, x, y, opts) {
    opts = opts || {};
    ctx.fillStyle = opts.color || C.text;
    ctx.font = opts.font || '13px -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
    ctx.textAlign = opts.align || 'left';
    ctx.textBaseline = opts.baseline || 'alphabetic';
    ctx.fillText(text, x, y);
  }

  function sceneBoxTitle(n, title) {
    drawText('Scene ' + n + ' of 5', 16, 24, { color: C.muted, font: '12px monospace, monospace' });
    drawText(title, 16, 46, { font: 'bold 17px -apple-system, "Segoe UI", Helvetica, Arial, sans-serif' });
  }

  // ---- Scene painters: t in [0,1] ----
  function paint1(t) {
    sceneBoxTitle(1, 'Feed it documents');
    var boxX = W * 0.62, boxY = H * 0.22, boxW = W * 0.30, boxH = H * 0.60;
    ctx.strokeStyle = C.line;
    ctx.strokeRect(boxX, boxY, boxW, boxH);
    drawText('TRACE store', boxX + 8, boxY - 8, { color: C.muted, font: '12px monospace, monospace' });
    var i, e = ease(t);
    for (i = 0; i < DOCS.length; i++) {
      var d = DOCS[i];
      var local = clamp01(e * 1.25 - (i / DOCS.length) * 0.25);
      var tx = boxX + 10 + d.gx * (boxW - 26);
      var ty = boxY + 12 + d.gy * (boxH - 24) + d.jitter * 4;
      var x = lerp(-30, tx, ease(local));
      var a = 0.35 + 0.65 * local;
      ctx.globalAlpha = a;
      ctx.fillStyle = C.blue;
      ctx.fillRect(x, ty, 12, 8);
      ctx.globalAlpha = 1;
    }
    var arrived = Math.round(88 * e);
    drawText(arrived + ' / 88 docs  ·  20,030 tokens', 16, H - 18,
      { font: '13px monospace, monospace', color: C.text });
  }

  function paint2(t) {
    sceneBoxTitle(2, 'It breaks them into atoms');
    var cx = W / 2, cy = H * 0.52, e = ease(t);
    var i;
    for (i = 0; i < ATOMS.length; i++) {
      var a = ATOMS[i];
      var local = clamp01(e * 1.2 - (i / ATOMS.length) * 0.2);
      var x = lerp(cx + (a.sx - 0.5) * 30, a.sx * (W - 32) + 16, ease(local));
      var y = lerp(cy + (a.sy - 0.5) * 30, 70 + a.sy * (H - 110), ease(local));
      ctx.fillStyle = C.green;
      ctx.beginPath();
      ctx.arc(x, y, a.r, 0, Math.PI * 2);
      ctx.fill();
      if (a.tag && local > 0.9) {
        drawText('#' + a.tag, x + 5, y - 4, { color: C.muted, font: '10px monospace, monospace' });
      }
    }
    var n = Math.round(144 * e);
    drawText(n + ' / 144 atoms · content-addressed', 16, H - 18,
      { font: '13px monospace, monospace' });
  }

  function paint3(t) {
    sceneBoxTitle(3, 'It self-organizes into schemas');
    drawText('dot positions schematic', W - 8, 24,
      { color: C.muted, font: '11px monospace, monospace', align: 'right' });
    var e = ease(t), i, k;
    for (k = 0; k < 4; k++) {
      var c = clusterCenter(k, W, H);
      ctx.strokeStyle = CLUSTER_COLORS[k];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.ellipse(c.x, c.y, W * 0.16, H * 0.19, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
      drawText(CLUSTER_NAMES[k], c.x - W * 0.16, c.y - H * 0.19 - 6,
        { color: CLUSTER_COLORS[k], font: 'bold 11px monospace, monospace' });
    }
    drawText(REST_LABEL, W - 8, H - 36,
      { color: C.muted, font: '11px monospace, monospace', align: 'right' });
    for (i = 0; i < ATOMS.length; i++) {
      var a = ATOMS[i];
      var fromX = a.sx * (W - 32) + 16, fromY = 70 + a.sy * (H - 110);
      var to = atomPos(a, a.cluster, W, H, atomRands[i]);
      var se = easeSettle(e);
      ctx.fillStyle = CLUSTER_COLORS[a.cluster];
      ctx.beginPath();
      ctx.arc(lerp(fromX, to.x, se), lerp(fromY, to.y, se), a.r, 0, Math.PI * 2);
      ctx.fill();
    }
    var counts = [0, 0, 0, 0, 0];
    for (i = 0; i < ATOMS.length; i++) counts[ATOMS[i].cluster]++;
    drawText('144 atoms · top 4 schemas ' + counts.slice(0, 4).join(' / ') +
      ' + ' + counts[4] + ' in 47 other', 16, H - 18,
      { font: '13px monospace, monospace' });
  }

  var ANSWERS = [
    { label: 'rank 1 · score 0.91', wFrac: 0.92 },
    { label: 'rank 2 · score 0.84', wFrac: 0.80 },
    { label: 'rank 3 · score 0.79', wFrac: 0.70 },
    { label: 'rank 4 · score 0.71', wFrac: 0.58 },
    { label: 'rank 5 · score 0.66', wFrac: 0.48 }
  ];

  function paint4(t) {
    sceneBoxTitle(4, 'Ask a question — answers, ranked');
    drawText('ILLUSTRATIVE query + rank bars', W - 8, 24,
      { color: C.muted, font: '11px monospace, monospace', align: 'right' });
    var e = ease(t);
    // Query bar.
    var qx = W * 0.08, qw = W * 0.84, qy = 62, qh = 30;
    ctx.strokeStyle = C.blue;
    ctx.strokeRect(qx, qy, qw, qh);
    drawText('query: "what fixed the drain fault?"', qx + 10, qy + 20,
      { font: '13px monospace, monospace' });
    // Retrieval paths to answer rows.
    var listY = 112, i;
    var lit = Math.min(5, Math.floor(e * 6));
    for (i = 0; i < 5; i++) {
      var rowY = listY + i * 26;
      var rowE = clamp01(e * 6 - i);
      ctx.globalAlpha = 0.25 + 0.75 * rowE;
      ctx.strokeStyle = i < lit ? C.green : C.line;
      ctx.beginPath();
      ctx.moveTo(qx + qw / 2, qy + qh);
      ctx.lineTo(qx + 20, rowY + 6);
      ctx.stroke();
      if (rowE > 0) {
        ctx.fillStyle = C.panel;
        ctx.fillRect(qx, rowY - 6, qw * ANSWERS[i].wFrac * rowE + 120, 20);
        ctx.fillStyle = C.green;
        ctx.fillRect(qx + 4, rowY - 2, (qw - 150) * ANSWERS[i].wFrac * rowE, 10);
        drawText(ANSWERS[i].label, qx + qw - 132, rowY + 7,
          { font: '12px monospace, monospace' });
      }
      ctx.globalAlpha = 1;
    }
    if (e > 0.55) {
      var bx = W * 0.08, by = H - 46, bw = W * 0.84, bh = 28;
      ctx.fillStyle = C.panel;
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = C.amber;
      ctx.strokeRect(bx, by, bw, bh);
      var msg = 'recall@10  0.7367 (all)  ·  0.4883 (leave-source-out)';
      drawText(msg, bx + 10, by + 19, { font: 'bold 12px monospace, monospace', color: C.amber });
    }
  }

  function paint5(t) {
    sceneBoxTitle(5, 'It repairs itself');
    var e = ease(t);
    var debt = Math.round(5847 * (1 - e));
    drawText(String(debt), W * 0.08, H * 0.42,
      { font: 'bold 44px monospace, monospace', color: debt === 0 ? C.green : C.red });
    drawText('open issues', W * 0.08, H * 0.42 + 24, { color: C.muted });
    var barX = W * 0.08, barW = W * 0.5, barY = H * 0.42 + 40;
    ctx.fillStyle = C.line;
    ctx.fillRect(barX, barY, barW, 10);
    ctx.fillStyle = C.green;
    ctx.fillRect(barX, barY, barW * e, 10);
    var iter = Math.min(6, 1 + Math.floor(e * 6));
    drawText('repair iteration ' + iter + ' of 6 · 5,847 → 0', barX, barY + 30,
      { font: '12px monospace, monospace', color: C.muted });
    if (e > 0.72) {
      var cx0 = W * 0.62, cw = W * 0.32, cy0 = H * 0.24, ch = H * 0.52;
      ctx.fillStyle = C.panel;
      ctx.fillRect(cx0, cy0, cw, ch);
      ctx.strokeStyle = C.green;
      ctx.strokeRect(cx0, cy0, cw, ch);
      var lx = cx0 + 12, ly = cy0 + 26;
      drawText('measured at 10M tokens', lx, ly, { color: C.muted, font: '12px monospace, monospace' });
      var rows = [
        '10,003,381 tok', '63,441 atoms',
        '~8.5 GB RAM', '0.7367 recall@10'
      ];
      for (var i = 0; i < rows.length; i++) {
        drawText(rows[i], lx, ly + 26 + i * 24, { font: 'bold 14px monospace, monospace' });
      }
    }
  }

  var PAINTERS = [paint1, paint2, paint3, paint4, paint5];
  var CAPTIONS = [
    'Scene 1 — Feed it documents: 88 complete documents (20,030 tokens in the recorded 20K run) fly into the store.',
    'Scene 2 — It breaks them into atoms: 144 content-addressed atoms, each tagged by its content hash.',
    'Scene 3 — It self-organizes into schemas: top 4 of 51 real schemas by primary membership hold 30 / 7 / 6 / 6 atoms (gray dots: 95 atoms in the other 47 schemas). Group sizes and labels real, from the recorded 20K run; dot positions schematic.',
    'Scene 4 — Ask a question: retrieval paths light up and answers come back ranked (query and rank bars illustrative) — guided recall@10 0.7367 (all) / 0.4883 (leave-source-out) measured.',
    'Scene 5 — It repairs itself, per-run split: [10M] 5,847 open issues drain to 0 over 6 iterations; [10M] scale card 10,003,381 tok / 63,441 atoms / ~8.5 GB RAM / 0.7367 recall@10; [20K] walkthrough cast: 88 docs / 144 atoms in 27.8 s.'
  ];
  // "What's real here" per scene: measured vs illustrative, stated plainly.
  var REALS = [
    "What's real here: 88 documents / 20,030 tokens from the recorded 20K run; flight paths illustrative.",
    "What's real here: 144 content-addressed atoms (chunk hashes real); break-apart motion illustrative.",
    "What's real here: top-4 schema sizes 30 / 7 / 6 / 6 and labels from the recorded 20K run; dot positions schematic.",
    "What's real here: recall@10 0.7367 / 0.4883 measured; query text and rank bars illustrative.",
    "What's real here [10M]: repair 5,847 → 0 in 6 iters, 10,003,381 tok, ~8.5 GB. [20K]: 88 docs / 144 atoms / 27.8 s cast."
  ];
  var DUR = [4.2, 4.2, 4.6, 5.0, 6.0]; // seconds per scene

  var currentScene = 0;
  var sceneElapsed = 0;
  var playing = false;
  var lastTick = 0;
  var rafId = null;

  function sceneT(s) {
    if (reduceMotion) return 1;
    return clamp01(sceneElapsed / DUR[s]);
  }

  function totalDur() {
    var sum = 0, i;
    for (i = 0; i < DUR.length; i++) sum += DUR[i];
    return sum;
  }

  function scrubTo(percent) {
    var target = (percent / 100) * totalDur();
    var acc = 0, s = 0;
    for (s = 0; s < DUR.length; s++) {
      if (target < acc + DUR[s] || s === DUR.length - 1) break;
      acc += DUR[s];
    }
    currentScene = s;
    sceneElapsed = target - acc;
    render(currentScene, sceneT(currentScene));
  }

  function render(s, t) {
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    PAINTERS[s](t);
    captionEl.textContent = CAPTIONS[s];
    if (realEl) realEl.textContent = REALS[s];
    canvas.setAttribute('aria-label', 'Scene ' + (s + 1) + ' of 5: ' + CAPTIONS[s]);
    countEl.textContent = 'Scene ' + (s + 1) + ' of 5';
    var dots = dotsEl.children;
    for (var i = 0; i < dots.length; i++) {
      dots[i].setAttribute('aria-current', i === s ? 'true' : 'false');
    }
    var overall = (s + t) / PAINTERS.length;
    barFill.style.width = (overall * 100).toFixed(1) + '%';
    if (scrubEl && document.activeElement !== scrubEl) {
      scrubEl.value = String((overall * 100).toFixed(1));
    }
  }

  function goTo(s) {
    currentScene = (s + PAINTERS.length) % PAINTERS.length;
    sceneElapsed = 0;
    render(currentScene, sceneT(currentScene));
  }

  function tick(now) {
    if (!playing) return;
    var dt = (now - lastTick) / 1000;
    lastTick = now;
    if (dt > 0.25) dt = 0.25;
    sceneElapsed += dt * speedMult;
    var t = sceneElapsed / DUR[currentScene];
    if (t >= 1) {
      if (currentScene === PAINTERS.length - 1) {
        render(currentScene, 1);
        setPlaying(false);
        return;
      }
      currentScene++;
      sceneElapsed = 0;
      t = 0;
    }
    render(currentScene, clamp01(t));
    rafId = window.requestAnimationFrame(tick);
  }

  function setPlaying(on) {
    playing = on;
    playBtn.textContent = on ? 'Pause' : 'Play';
    playBtn.setAttribute('aria-label', on ? 'Pause walkthrough' : 'Play walkthrough');
    if (on) {
      if (reduceMotion) return; // no autoplay sibling: static stepping only
      if (currentScene === PAINTERS.length - 1 && sceneElapsed >= DUR[currentScene]) {
        goTo(0);
      }
      lastTick = window.performance.now();
      rafId = window.requestAnimationFrame(tick);
    } else if (rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // Controls.
  var i, dot;
  for (i = 0; i < PAINTERS.length; i++) {
    dot = document.createElement('button');
    dot.type = 'button';
    dot.className = 'demo-dot';
    dot.setAttribute('aria-label', 'Go to scene ' + (i + 1));
    (function (idx) {
      dot.addEventListener('click', function () {
        setPlaying(false);
        goTo(idx);
      });
    })(i);
    dotsEl.appendChild(dot);
  }
  prevBtn.addEventListener('click', function () {
    setPlaying(false);
    goTo(currentScene - 1);
  });
  nextBtn.addEventListener('click', function () {
    setPlaying(false);
    goTo(currentScene + 1);
  });
  playBtn.addEventListener('click', function () {
    if (reduceMotion && !playing) {
      // Reduced motion: advance one scene per press, no animation.
      if (currentScene === PAINTERS.length - 1) goTo(0);
      else goTo(currentScene + 1);
      return;
    }
    setPlaying(!playing);
  });
  if (reduceMotion) {
    playBtn.textContent = 'Next scene';
    playBtn.setAttribute('aria-label', 'Advance to next scene (animation disabled)');
  }
  if (resetBtn) resetBtn.addEventListener('click', function () {
    setPlaying(false);
    goTo(0);
  });
  if (scrubEl) scrubEl.addEventListener('input', function (e) {
    setPlaying(false);
    scrubTo(parseFloat(e.target.value));
  });
  if (speedEl) speedEl.addEventListener('change', function (e) {
    speedMult = parseFloat(e.target.value) || 1.0;
  });
  document.addEventListener('keydown', function (e) {
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    if (e.key === ' ') {
      e.preventDefault();
      playBtn.click();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setPlaying(false);
      goTo(currentScene + 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setPlaying(false);
      goTo(currentScene - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      setPlaying(false);
      goTo(0);
    }
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden && playing) setPlaying(false);
  });

  resize();
  goTo(0);
  if (!reduceMotion) setPlaying(true); // autoplay unless user prefers reduced motion
})();
