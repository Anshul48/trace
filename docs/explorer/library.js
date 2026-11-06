/* Inside the library: zoomable cluster map over the sealed-replay sample.
 * Data: window.TRACE_REPLAY (data/replay.js) only. No fetch, no CDN, no backend.
 * Membership, counts, titles, texts, fingerprints and top-10 lists are the real
 * recordings; bubble positions are a deterministic layout of that real data.
 * "Inside the library" tab of inside.html; inside.js owns the tab router. */
(function () {
"use strict";
var R = window.TRACE_REPLAY;
var $ = function (id) { return document.getElementById(id); };
function esc(s) { return String(s).replace(/[&<>"']/g, function (c) {
  return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
function fmt(n) { return Number(n).toLocaleString("en-US"); }
function params() {
  var o = {};
  try {
    var q = window.location.search.replace(/^\?/, "").split("&");
    q.forEach(function (kv) { var p = kv.split("="); if (p[0]) o[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ""); });
  } catch (e) {}
  return o;
}
var P = params();
var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
var STATIC = P.static === "1";

/* Recorded aggregate for one of the four parts (same scope line as the Query
 * trace tab): TRACE scored ~1,600 of 203,137 rows there (0.79%). Per-query
 * scored-row lists were not recorded, so the lit passages below are the
 * recorded guided top-10 for the picked question, and the counter runs to the
 * recorded aggregate. */
var SCORED = 1600, PART_ROWS = 203137, FRAC = "0.79%";

if (!R || !R.questions || !R.passages) {
  var host = $("view-library");
  if (host) host.insertAdjacentHTML("afterbegin",
    '<p class="diskwarn"><b>Data missing:</b> data/replay.js did not load.</p>');
  return;
}
var RP = R.passages, QS = R.questions;

/* ================= model: shard -> group -> passages (all real) ================= */
var groups = {};   /* "sh:pa" -> { sh, pa, ids: [pid...] } */
Object.keys(RP).forEach(function (pid) {
  var p = RP[pid];
  var k = p.sh + ":" + p.pa;
  if (!groups[k]) groups[k] = { sh: p.sh, pa: p.pa, ids: [] };
  groups[k].ids.push(pid);
});
var GARR = Object.keys(groups).map(function (k) { groups[k].key = k; return groups[k]; });
GARR.forEach(function (g) { g.ids.sort(function (a, b) { return (+a) - (+b); }); });
GARR.sort(function (a, b) {
  return (a.sh - b.sh) || (b.ids.length - a.ids.length) || (a.pa - b.pa);
});

/* Group label: most frequent word (length>=3, not a stopword) across the real
 * member passage titles. Deterministic: count desc, then alphabetical. */
var STOP = {};
("the,and,for,are,with,from,that,this,was,were,has,have,had,not,but,all,can,its,their,there,them,they,such,than,into,over,under,between,through,during,about,after,before,also,one,two,used,use,history,list,world,state,united,new,south,north,part,early,including,within,while,where,which,when,who,whom,what,made,many,most,more,other,only,own,same,may,might,must,shall,will,would,could,should,his,her,you,your,our,out,off,end,high,using,based,first,second,major,large,modern,early").split(",").forEach(function (w) { STOP[w] = 1; });
function topTerm(g) {
  var counts = {};
  g.ids.forEach(function (pid) {
    var t = (RP[pid].ti || "").toLowerCase().match(/[a-z0-9][a-z0-9']{2,}/g) || [];
    t.forEach(function (w) { if (!STOP[w]) counts[w] = (counts[w] || 0) + 1; });
  });
  var best = "", bn = 0;
  Object.keys(counts).sort().forEach(function (w) {
    if (counts[w] > bn) { bn = counts[w]; best = w; }
  });
  return best;
}
GARR.forEach(function (g) { g.term = topTerm(g); });

/* ================= deterministic layout ================= */
var SHW = 780, GAP = 30, PAD = 16;
function groupR(n) { return 9 + 8 * Math.sqrt(n); }
var shardBlocks = [];   /* { sh, x, y, w, h, n } */
var WW = 0, WH = 0;     /* world size */
(function layout() {
  var per = [[], [], [], []];
  GARR.forEach(function (g) { per[g.sh].push(g); });
  var blocks = [];
  for (var s = 0; s < 4; s++) {
    var x = PAD, y = PAD + 30, rowH = 0;
    per[s].forEach(function (g) {
      var d = groupR(g.ids.length) * 2 + 8;
      if (x + d > SHW - PAD && rowH > 0) { x = PAD; y += rowH + 6; rowH = 0; }
      g.x = x + d / 2; g.y = y + d / 2; g.r = groupR(g.ids.length);
      x += d + 6; if (d > rowH) rowH = d;
    });
    var n = 0;
    per[s].forEach(function (g) { n += g.ids.length; });
    blocks.push({ sh: s, w: SHW, h: y + rowH + PAD, n: n, groups: per[s] });
  }
  var colW = [Math.max(blocks[0].w, blocks[2].w), Math.max(blocks[1].w, blocks[3].w)];
  var rowH = [Math.max(blocks[0].h, blocks[1].h), Math.max(blocks[2].h, blocks[3].h)];
  var ox = [PAD, PAD + colW[0] + GAP], oy = [PAD, PAD + rowH[0] + GAP];
  blocks.forEach(function (b) {
    var c = b.sh % 2, r = (b.sh / 2) | 0;
    b.x = ox[c]; b.y = oy[r];
    b.groups.forEach(function (g) { g.x += b.x; g.y += b.y; });
  });
  WW = ox[1] + colW[1] + PAD; WH = oy[1] + rowH[1] + PAD;
  shardBlocks = blocks;
})();

/* Passage dots: deterministic mini-grid clipped to the group bubble. */
var DOTS = [];   /* { x, y, pid, g } */
GARR.forEach(function (g) {
  var n = g.ids.length, cols = Math.ceil(Math.sqrt(n)), rows = Math.ceil(n / cols);
  var step = n === 1 ? 0 : Math.min(11, (g.r * 1.15) / Math.max(cols, rows));
  g.ids.forEach(function (pid, i) {
    var c = i % cols, r = ((i / cols) | 0);
    DOTS.push({
      x: g.x + (n === 1 ? 0 : (c - (cols - 1) / 2) * step),
      y: g.y + (n === 1 ? 0 : (r - (rows - 1) / 2) * step),
      pid: pid, g: g
    });
  });
});
var DOT_R = 3.4;

/* ================= camera ================= */
var cam = { x: 0, y: 0, w: WW };
var canvas = null, ctx = null, CW = 0, CH = 0, DPR = 1;
function aspect() { return CH > 0 ? CW / CH : 16 / 9; }
function camH() { return cam.w / aspect(); }
function maxCamW() { return Math.max(WW, WH * aspect()) * 1.06; }
function clampCam() {
  cam.w = Math.min(maxCamW(), Math.max(60, cam.w));
  var h = camH();
  if (cam.w >= WW) cam.x = (WW - cam.w) / 2;
  else cam.x = Math.max(-60, Math.min(WW + 60 - cam.w, cam.x));
  if (h >= WH) cam.y = (WH - h) / 2;
  else cam.y = Math.max(-60, Math.min(WH + 60 - h, cam.y));
}
function fitRect(x, y, w, h, margin) {
  var m = margin || 0;
  var ww = w + m * 2, hh = h + m * 2, a = aspect();
  if (ww / hh > a) { cam.w = ww; cam.x = x - m; cam.y = y + h / 2 - (ww / a) / 2; }
  else { cam.w = hh * a; cam.x = x + w / 2 - (hh * a) / 2; cam.y = y - m; }
  clampCam();
}
/* Zoom presets. Targets follow the picked question when one is set. */
function targetShard() {
  if (curQ) {
    var p = RP[String(curQ.g[0][0])];
    if (p) return shardBlocks[p.sh];
  }
  return shardBlocks[0];
}
function targetGroup() {
  if (curQ) {
    for (var i = 0; i < curQ.g.length; i++) {
      var p = RP[String(curQ.g[i][0])];
      if (p && groups[p.sh + ":" + p.pa]) return groups[p.sh + ":" + p.pa];
    }
  }
  var best = GARR[0];
  GARR.forEach(function (g) { if (g.ids.length > best.ids.length) best = g; });
  return best;
}
function setZoom(i) {
  stop();
  if (i === 0) { fitRect(0, 0, WW, WH, 8); }
  else if (i === 1) { var b = targetShard(); fitRect(b.x, b.y, b.w, b.h, 24); }
  else { var g = targetGroup(), d = g.r * 2; fitRect(g.x - d / 2, g.y - d / 2, d, d, i === 2 ? d * 4 : d * 1.1); }
  paint();
}
function zoomAt(sx, sy, f) {
  var r = canvas.getBoundingClientRect();
  var wx = cam.x + (sx - r.left) / r.width * cam.w;
  var wy = cam.y + (sy - r.top) / r.height * camH();
  var nw = Math.min(maxCamW(), Math.max(60, cam.w * f));
  var k = nw / cam.w;
  cam.x = wx - (wx - cam.x) * k; cam.y = wy - (wy - cam.y) * k; cam.w = nw;
  clampCam(); paint();
}

/* ================= palette (follows the page theme) ================= */
function pal() {
  if (document.documentElement.getAttribute("data-theme") === "dark") {
    return { dot: "#7fa6e8", dim: "#2a3345", bubble: "#171e2c", ring: "#3b4a6b",
      shard: "#3b4a6b", ink: "#e6ebf3", mut: "#9aa5b8", lit: "#2fd6c2",
      litRing: "#2fd6c2", sel: "#6ea8ff", bg: "#10151f" };
  }
  return { dot: "#5d78b8", dim: "#d3d9e8", bubble: "#f6f8fc", ring: "#9fb2cc",
    shard: "#d3d9e8", ink: "#0e1730", mut: "#46547a", lit: "#0a8f84",
    litRing: "#0a8f84", sel: "#0b5fff", bg: "#ffffff" };
}

/* ================= routing state ================= */
var curQ = null, curQi = -1;      /* picked recorded question */
var lit = {};                     /* pid -> 1 (lit passages) */
var litG = {};                    /* gkey -> glow 0..1 */
var dimK = 0;                     /* 0 rest .. 1 all dimmed */
var litCount = 0, scored = 0;
var selected = null;              /* pid in the detail panel */
var playing = false, raf = 0, t0 = 0, DUR = 20000, follow = true;
var entered = false, initZoom = 0;
function setZoomSilent() { var a = aspect; aspect = function () { return 16 / 9; }; setZoom(initZoom); aspect = a; }

function guided() {
  if (!curQ) return [];
  return curQ.g.map(function (h) { return String(h[0]); });
}
function applyFrac(f) {
  dimK = Math.min(1, f / 0.15);
  scored = Math.round(SCORED * Math.min(1, Math.max(0, (f - 0.10) / 0.80)));
  lit = {}; litG = {}; litCount = 0;
  var ids = guided();
  ids.forEach(function (pid, i) {
    var p = RP[pid];
    if (p) {
      var gk = p.sh + ":" + p.pa, on = Math.min(1, Math.max(0, (f - (0.15 + 0.04 * i)) / 0.05));
      if (on > 0) litG[gk] = Math.max(litG[gk] || 0, on);
    }
    if (f >= 0.40 + 0.05 * i) { lit[pid] = 1; litCount++; }
  });
  paintCounter();
}
function paintCounter() {
  $("lcount").innerHTML = "<b>" + fmt(scored) + "</b> of " + fmt(PART_ROWS) +
    " rows scored <b>(" + (scored ? FRAC : "0.00%") + ")</b>";
  $("lpass").textContent = curQ ?
    (litCount + " of 10 recorded top passages lit") : "pick a recorded question, then play the routing";
}

/* ================= paint ================= */
function w2sx(x) { return (x - cam.x) / cam.w * CW; }
function w2sy(y) { return (y - cam.y) / camH() * CH; }
function paint() {
  if (!ctx) return;
  var c = pal();
  ctx.fillStyle = c.bg; ctx.fillRect(0, 0, CW, CH);
  var h = camH();
  var vx0 = cam.x - 60, vy0 = cam.y - 60, vx1 = cam.x + cam.w + 60, vy1 = cam.y + h + 60;
  var s = CW / cam.w;   /* world -> device px */
  /* shard blocks */
  ctx.textBaseline = "top";
  shardBlocks.forEach(function (b) {
    if (b.x + b.w < vx0 || b.x > vx1 || b.y + b.h < vy0 || b.y > vy1) return;
    ctx.strokeStyle = c.shard; ctx.lineWidth = Math.max(1, 1.5 * DPR);
    ctx.strokeRect(w2sx(b.x), w2sy(b.y), b.w * s, b.h * s);
    ctx.fillStyle = c.mut; ctx.font = Math.max(10, 13 * DPR) + "px " +
      "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
    var hw = b.w * s;
    ctx.fillText(hw > 430 * DPR
      ? "Part " + (b.sh + 1) + " of 4 \u00b7 " + fmt(b.n) + " sample passages (sample only)"
      : "Part " + (b.sh + 1), w2sx(b.x) + 8 * DPR, w2sy(b.y) + 6 * DPR);
  });
  /* group bubbles */
  var i, g;
  for (i = 0; i < GARR.length; i++) {
    g = GARR[i];
    if (g.x + g.r < vx0 || g.x - g.r > vx1 || g.y + g.r < vy0 || g.y - g.r > vy1) continue;
    var x = w2sx(g.x), y = w2sy(g.y), r = g.r * s;
    if (r < 1.5) continue;
    var glow = litG[g.key] || 0;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832);
    ctx.fillStyle = c.bubble; ctx.fill();
    ctx.lineWidth = Math.max(1, (glow > 0 ? 3 : 1.2) * DPR);
    ctx.strokeStyle = glow > 0 ? c.litRing : c.ring;
    ctx.globalAlpha = glow > 0 ? (0.35 + 0.65 * glow) : (dimK > 0 ? 1 - 0.45 * dimK : 1);
    ctx.stroke(); ctx.globalAlpha = 1;
    /* label: real top term, only when it fits */
    if (g.term && r * 2 > 40 * DPR && s > 0.28 * DPR) {
      ctx.fillStyle = glow > 0 ? c.lit : c.mut;
      ctx.font = (glow > 0 ? "bold " : "") + Math.max(9, 10.5 * DPR) + "px " +
        "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(g.term.length > 14 ? g.term.slice(0, 14) + "\u2026" : g.term, x, y + r + 2 * DPR);
      ctx.textAlign = "left";
    }
  }
  /* passage dots */
  var dr = DOT_R * s;
  var showDots = dr >= 0.9;
  if (showDots) {
    for (i = 0; i < DOTS.length; i++) {
      var d = DOTS[i];
      if (d.x < vx0 || d.x > vx1 || d.y < vy0 || d.y > vy1) continue;
      var isLit = lit[d.pid], glow2 = litG[d.g.key] || 0;
      ctx.beginPath(); ctx.arc(w2sx(d.x), w2sy(d.y), Math.max(1.1, dr), 0, 6.2832);
      if (isLit) { ctx.fillStyle = c.lit; }
      else if (dimK > 0) { ctx.fillStyle = glow2 > 0 ? c.dot : c.dim; }
      else { ctx.fillStyle = c.dot; }
      ctx.fill();
      if (isLit && dr > 2.4) {
        ctx.lineWidth = Math.max(1, 1.4 * DPR); ctx.strokeStyle = "#ffffff";
        ctx.stroke();
      }
      if (selected === d.pid) {
        ctx.lineWidth = Math.max(1.5, 2 * DPR); ctx.strokeStyle = c.sel;
        ctx.beginPath(); ctx.arc(w2sx(d.x), w2sy(d.y), Math.max(3, dr) + 3 * DPR, 0, 6.2832);
        ctx.stroke();
      }
    }
  }
}

/* ================= interaction ================= */
function s2w(sx, sy) {
  var r = canvas.getBoundingClientRect();
  return { x: cam.x + (sx - r.left) / r.width * cam.w,
    y: cam.y + (sy - r.top) / r.height * camH() };
}
function pickDot(wx, wy) {
  var tol = cam.w / canvas.getBoundingClientRect().width * 10, best = null, bd = tol;
  for (var i = 0; i < DOTS.length; i++) {
    var d = DOTS[i];
    if (d.x < cam.x - 40 || d.x > cam.x + cam.w + 40) continue;
    var dy = d.y - wy;
    if (dy > tol || dy < -tol) continue;
    var dd = Math.abs(d.x - wx) + Math.abs(dy);
    if (dd < bd) { bd = dd; best = d; }
  }
  return best;
}
function pickGroup(wx, wy) {
  for (var i = 0; i < GARR.length; i++) {
    var g = GARR[i], dx = wx - g.x, dy = wy - g.y;
    if (dx * dx + dy * dy <= g.r * g.r) return g;
  }
  return null;
}
function wire() {
  var drag = null;
  canvas.addEventListener("pointerdown", function (e) {
    drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y, moved: 0 };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var r = canvas.getBoundingClientRect();
    drag.moved += Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y);
    cam.x = drag.cx - (e.clientX - drag.x) / r.width * cam.w;
    cam.y = drag.cy - (e.clientY - drag.y) / r.height * camH();
    clampCam(); paint();
  });
  canvas.addEventListener("pointerup", function (e) {
    var wasDrag = drag && drag.moved > 6;
    drag = null;
    if (wasDrag) return;
    follow = false;
    var w = s2w(e.clientX, e.clientY), d = pickDot(w.x, w.y);
    if (d) { selectPassage(d.pid, true); return; }
    var g = pickGroup(w.x, w.y);
    if (g) {
      $("lstatus").textContent = "Part " + (g.sh + 1) + " \u00b7 group " + fmt(g.pa) +
        " \u00b7 " + g.ids.length + " sample passage" + (g.ids.length === 1 ? "" : "s") +
        (g.term ? " \u00b7 top word \u201c" + g.term + "\u201d" : "");
      var dd = g.r * 2;
      fitRect(g.x - dd / 2, g.y - dd / 2, dd, dd, dd * 1.6);
      paint();
    } else selectPassage(null, false);
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    follow = false;
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 0.85 : 1.18);
  }, { passive: false });
  $("lzin").addEventListener("click", function () {
    var r = canvas.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, 0.7);
  });
  $("lzout").addEventListener("click", function () {
    var r = canvas.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1.4);
  });
  $("lzreset").addEventListener("click", function () { setZoom(0); });
  $("lz1").addEventListener("click", function () { setZoom(1); });
  $("lz2").addEventListener("click", function () { setZoom(2); });
  $("lz3").addEventListener("click", function () { setZoom(3); });
}

/* ================= play / stop ================= */
function stop() {
  playing = false;
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  var b = $("lplay");
  if (b) b.textContent = "\u25b6 Play the routing (20 s)";
}
function followCam(f) {
  /* gentle scripted zoom while playing: overview -> part -> group */
  var b = targetShard(), g = targetGroup();
  function rect(i) {
    if (i === 0) return { x: 0, y: 0, w: WW, h: WH };
    if (i === 1) return { x: b.x, y: b.y, w: b.w, h: b.h };
    var d = g.r * 2;
    return { x: g.x - d * 2, y: g.y - d * 2, w: d * 4, h: d * 4 };
  }
  var keys = [rect(0), rect(1), rect(2)], segs = [0.22, 0.60, 1.01], k = 0, kf = 0;
  if (f < segs[0]) { k = 0; kf = f / segs[0]; }
  else if (f < segs[1]) { k = 1; kf = (f - segs[0]) / (segs[1] - segs[0]); }
  else { k = 1; kf = 1; }
  var A = keys[Math.min(k, 1)], B = keys[Math.min(k + 1, 2)];
  var e = kf < 0.5 ? 2 * kf * kf : 1 - Math.pow(-2 * kf + 2, 2) / 2;
  fitRect(A.x + (B.x - A.x) * e, A.y + (B.y - A.y) * e,
    A.w + (B.w - A.w) * e, A.h + (B.h - A.h) * e, 20);
}
function play() {
  if (playing) { stop(); return; }
  if (!curQ) selectQuestion(0);
  if (REDUCED || STATIC) { applyFrac(1); stop(); return; }
  playing = true; follow = $("lfollow").checked; t0 = 0;
  $("lplay").textContent = "\u23f8 Pause";
  applyFrac(0);
  function frame(ts) {
    if (!playing) return;
    if (!t0) t0 = ts;
    var f = Math.min(1, (ts - t0) / DUR);
    applyFrac(f);
    if (follow) followCam(f);
    paint();
    if (f >= 1) { stop(); return; }
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
}

/* ================= passage panel + fingerprint check ================= */
/* The fingerprint check mirrors docs/explorer/app.js sha256hex/checkHash
 * (lines 257-273): SHA-256 of the exact stored text, compared in the browser
 * to the stored fingerprint. app.js is page-bound (an IIFE wired to
 * index.html), so the same six lines run here instead of an import. */
function sha256hex(text) {
  if (!(window.crypto && crypto.subtle)) return Promise.reject(new Error("no-subtle"));
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  });
}
function selectPassage(pid, scroll) {
  selected = pid;
  var box = $("lpanel");
  if (!pid || !RP[pid]) {
    box.innerHTML = "<p class='muted'>Click a glowing passage dot to read its text and check its fingerprint.</p>";
    paint();
    return;
  }
  var p = RP[pid], gk = p.sh + ":" + p.pa, g = groups[gk];
  var close = "", exact = "";
  if (curQ) {
    curQ.g.forEach(function (h, i) { if (String(h[0]) === pid) close = "rank " + (i + 1) + ", closeness " + h[1].toFixed(4); });
    curQ.f.forEach(function (h, i) { if (String(h[0]) === pid) exact = "rank " + (i + 1); });
  }
  box.innerHTML =
    "<h3>" + esc(p.ti || ("passage " + pid)) + "</h3>" +
    "<p class='muted'>Part " + (p.sh + 1) + " of 4 \u00b7 group " + fmt(p.pa) +
    " \u00b7 passage " + fmt(pid) + " of " + fmt((R.meta && R.meta.library_passages) || 812545) +
    (g ? " \u00b7 " + g.ids.length + " sample passage" + (g.ids.length === 1 ? "" : "s") + " in this group" : "") + "</p>" +
    (close ? "<p><b>In this question's recorded top 10:</b> " + esc(close) +
      (exact ? " \u00b7 exact search: " + esc(exact) : " \u00b7 exact search did not return it") + "</p>" : "") +
    "<p class='lpass-text'>" + esc((p.tx || "").slice(0, 700)) + ((p.tx || "").length > 700 ? "\u2026" : "") + "</p>" +
    "<details><summary>Full text as stored</summary><p class='lpass-text'>" + esc(p.tx || "") + "</p></details>" +
    "<dl class='lfacts'><dt>Fingerprint stored in the library</dt><dd><code>" + esc(p.h) +
    "</code><div class='fine'>A fingerprint (SHA-256) is a short code worked out from the exact text.</div></dd></dl>" +
    "<div class='actions'><button type='button' id='lchk'>Check the fingerprint in my browser</button></div>" +
    "<div class='verdict-slot' id='lverdict' role='status' aria-live='polite'></div>";
  $("lchk").addEventListener("click", function () {
    var slot = $("lverdict");
    slot.innerHTML = '<div class="verdict">Checking&hellip;</div>';
    sha256hex(p.tx).then(function (hex) {
      slot.innerHTML = hex === p.h
        ? '<div class="verdict pass">Match. Your browser worked out <span class="mono">' + hex.slice(0, 16) + '&hellip;</span> from the text above, and it equals the fingerprint the library stored.</div>'
        : '<div class="verdict fail">No match. The text here does not give the stored fingerprint.</div>';
    }, function () {
      slot.innerHTML = '<div class="verdict fail">This browser cannot work out fingerprints on this page (it needs https or localhost). The stored fingerprint is shown above.</div>';
    });
  });
  paint();
  if (scroll && box.scrollIntoView) box.scrollIntoView({ block: "nearest" });
}

/* ================= question picker ================= */
function selectQuestion(i) {
  stop();
  curQi = Math.max(0, Math.min(QS.length - 1, i));
  curQ = QS[curQi];
  $("lq").value = String(curQi);
  $("lqmeta").textContent = "Recorded " + curQ.t + " \u00b7 " + curQ.cat +
    " \u00b7 TRACE " + (curQ.tg / 1000).toFixed(2) + " s, exact " + (curQ.tf / 1000).toFixed(2) +
    " s when recorded (no speed claim)";
  applyFrac(0); scored = 0; paintCounter(); paint();
}

/* ================= sizing / init ================= */
function sizeCanvas() {
  var r = canvas.getBoundingClientRect();
  DPR = Math.min(2, window.devicePixelRatio || 1);
  CW = Math.max(1, Math.round(r.width * DPR));
  CH = Math.max(1, Math.round(r.height * DPR));
  canvas.width = CW; canvas.height = CH;
  paint();
}
function init() {
  canvas = $("lmap");
  ctx = canvas.getContext("2d");
  var sel = $("lq");
  QS.forEach(function (q, i) {
    var o = document.createElement("option");
    o.value = String(i); o.textContent = q.q + " (" + q.cat + ")";
    sel.appendChild(o);
  });
  sel.addEventListener("change", function () { selectQuestion(+sel.value); });
  $("lplay").addEventListener("click", play);
  $("lclear").addEventListener("click", function () {
    stop(); applyFrac(0); scored = 0; paintCounter(); selectPassage(null, false);
  });
  wire();
  sizeCanvas();
  window.addEventListener("resize", sizeCanvas);
  document.fonts && document.fonts.ready && document.fonts.ready.then(paint);
  /* URL params for deterministic captures: ?view=library&q=0&lit=1&zoom=2 */
  var qi = (P.q !== undefined && QS[+P.q]) ? +P.q : -1;
  if (qi >= 0) selectQuestion(qi);
  else { curQ = null; curQi = -1; paintCounter(); }
  if (P.lit === "1" && curQ) applyFrac(1);
  initZoom = P.zoom !== undefined ? Math.max(0, Math.min(3, +P.zoom || 0)) : 0;
  if (canvas.getBoundingClientRect().width > 0) { entered = true; setZoom(initZoom); }
  else setZoomSilent();
  /* stats line: computed from the data at load */
  $("llibstats").innerHTML = "<div><b>" + fmt(DOTS.length) + "</b><span>sample passages</span></div>" +
    "<div><b>" + fmt(GARR.length) + "</b><span>groups in the sample</span></div>" +
    "<div><b>4</b><span>library parts</span></div>" +
    "<div><b>" + fmt(QS.length) + "</b><span>recorded questions</span></div>";
}

/* test hooks (read-only) */
window.__LIBRARY__ = {
  ready: function () { return !!ctx; },
  stats: function () {
    return { passages: DOTS.length, groups: GARR.length, shards: 4,
      questions: QS.length, world: { w: WW, h: WH } };
  },
  litIds: function () { return Object.keys(lit).sort(function (a, b) { return (+a) - (+b); }); },
  litGroupCount: function () { return Object.keys(litG).length; },
  counter: function () { return { scored: scored, total: PART_ROWS, frac: scored ? FRAC : "0.00%", lit: litCount }; },
  camera: function () { return { x: cam.x, y: cam.y, w: cam.w }; },
  groupLabel: function (sh, pa) { var g = groups[sh + ":" + pa]; return g ? g.term : null; },
  groupOf: function (pid) { var p = RP[pid]; return p ? { sh: p.sh, pa: p.pa } : null; },
  locate: function (pid) {
    for (var i = 0; i < DOTS.length; i++) {
      if (DOTS[i].pid !== pid) continue;
      var r = canvas.getBoundingClientRect();
      return { x: r.left + (DOTS[i].x - cam.x) / cam.w * r.width,
        y: r.top + (DOTS[i].y - cam.y) / camH() * r.height };
    }
    return null;
  },
  guidedIds: function () { return guided(); },
  setZoom: setZoom, play: play, stop: stop,
  selectQuestion: selectQuestion, selectPassage: selectPassage,
  enter: function () {
    sizeCanvas();
    if (!entered && canvas.getBoundingClientRect().width > 0) { entered = true; setZoom(initZoom); }
    paint();
  }
};

init();
})();
