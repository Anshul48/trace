/* Inside TRACE: static views over data/replay.js + data/corpus.js. No fetch. */
(function () {
"use strict";
var R = window.TRACE_REPLAY, C = window.TRACE_CORPUS;
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

/* ---------- data guards ---------- */
function fatal(msg) {
  $("main").insertAdjacentHTML("afterbegin",
    '<p class="diskwarn"><b>Data missing:</b> ' + esc(msg) + "</p>");
}
if (!R || !R.questions || !R.passages) fatal("data/replay.js did not load.");
if (!C || !C.atoms || !C.evaluation_queries) fatal("data/corpus.js did not load.");
if ((!R || !R.questions) && (!C || !C.atoms)) return;
var RP = (R && R.passages) || {};

/* ---------- theme ---------- */
(function () {
  var b = $("themebtn");
  function paint() { b.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "Light" : "Dark"; }
  b.addEventListener("click", function () {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    if (dark) document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", "dark");
    try { localStorage.setItem("trace-inside-theme", dark ? "light" : "dark"); } catch (e) {}
    paint();
  });
  paint();
})();

/* ---------- router ---------- */
var VIEWS = ["corpus", "trace", "memory", "compare"];
var curView = "corpus";
function show(name) {
  if (VIEWS.indexOf(name) < 0) name = "corpus";
  curView = name;
  VIEWS.forEach(function (v) {
    $("view-" + v).hidden = (v !== name);
  });
  var tabs = document.querySelectorAll("[data-tab]");
  for (var i = 0; i < tabs.length; i++)
    tabs[i].setAttribute("aria-current", tabs[i].getAttribute("data-tab") === name ? "page" : "false");
  if (name === "trace") Trace.enter();
  if (name === "corpus") Corpus.mapPaint();
}
window.addEventListener("hashchange", function () {
  show(window.location.hash.replace(/^#\/?/, "").split("?")[0]);
});

/* ================= CORPUS ================= */
var Corpus = (function () {
  var parentById = {}, leafById = {}, leafAtoms = {}, docAtoms = {};
  var multiLeaf = {};
  function build() {
    if (!C || !C.atoms) return;
    C.parents.forEach(function (p) { parentById[p.id] = p; });
    C.leaves.forEach(function (l) {
      leafById[l.id] = l;
      leafAtoms[l.id] = 0;
      if (l.parent_ids.length > 1) multiLeaf[l.id] = 1;
    });
    C.atoms.forEach(function (a) {
      (a.leaf_ids || []).forEach(function (lid) { leafAtoms[lid] = (leafAtoms[lid] || 0) + 1; });
      docAtoms[a.doc_id] = (docAtoms[a.doc_id] || 0) + 1;
    });
  }
  function stats() {
    var el = $("corpus-stats");
    if (!C) { el.innerHTML = "<div><b>—</b><span>no corpus data</span></div>"; return; }
    var m = C.manifest, mp = Object.keys(multiLeaf).length;
    var cells = [
      [fmt(m.actual_tokens), "tokens"],
      [fmt(C.atoms.length), "atoms = passages"],
      [fmt(C.leaves.length), "leaves = units"],
      [fmt(C.parents.length), "parents = groups"],
      [fmt(m.complete_documents), "documents"],
      [fmt(m.parent_child_edges), "parent→leaf edges"],
      [fmt(mp), "multi-parent leaves"]
    ];
    el.innerHTML = cells.map(function (c) {
      return "<div><b>" + c[0] + "</b><span>" + c[1] + "</span></div>";
    }).join("");
  }
  function coverage() {
    if (!R) return;
    var ids = Object.keys(RP), sh = { 0: 0, 1: 0, 2: 0, 3: 0 }, pa = {};
    ids.forEach(function (id) {
      var p = RP[id];
      if (p && p.sh !== undefined && sh[p.sh] !== undefined) sh[p.sh]++;
      if (p && p.pa !== undefined) pa[p.sh + ":" + p.pa] = 1;
    });
    $("cov-pass").textContent = fmt(ids.length);
    $("cov-grp").textContent = fmt(Object.keys(pa).length);
    $("parts-strip").innerHTML = [0, 1, 2, 3].map(function (s) {
      return "<div><b>" + fmt(sh[s]) + "</b><br>sample passages in part " + (s + 1) + "</div>";
    }).join("");
  }
  function shortId(id) {
    var m = /^(xpar|xseg)-(\d+)-s(\d+)$/.exec(id || "");
    return m ? ((m[1] === "xpar" ? "P" : "U") + m[2]) : String(id);
  }
  function passText(a) {
    return ((a.title || "") + " " + (a.snippet || "") + " " + a.id + " " + a.doc_id).toLowerCase();
  }
  var cache = [];
  function currentList() {
    var q = ($("cq").value || "").toLowerCase().trim();
    var pf = $("cpar").value, mp = $("cmp").checked;
    return cache.filter(function (a) {
      if (pf && (a._parents.indexOf(pf) < 0)) return false;
      if (mp && !a._multi) return false;
      if (q && a._text.indexOf(q) < 0) return false;
      return true;
    });
  }
  function renderList() {
    var list = currentList(), ul = $("plist");
    $("ccount").textContent = "Showing " + list.length + " of " + cache.length + " passages.";
    ul.innerHTML = "";
    var frag = document.createDocumentFragment();
    list.forEach(function (a) {
      var li = document.createElement("li");
      li.tabIndex = 0;
      li.setAttribute("role", "button");
      li.dataset.atom = a.id;
      var chips = a.leaf_ids.map(function (l) { return "<span class='chip'>" + esc(shortId(l)) + "</span>"; }).join("") +
        a._parents.map(function (p) { return "<span class='chip'>" + esc(shortId(p)) + "</span>"; }).join("");
      li.innerHTML = "<div class='t'>" + esc(a.title || a.id) + "</div>" +
        "<div class='s'>" + esc((a.snippet || "").slice(0, 110)) + "…</div>" +
        "<div class='chips'>" + chips + "</div>";
      function pick() { detail(a.id); }
      li.addEventListener("click", pick);
      li.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      frag.appendChild(li);
    });
    ul.appendChild(frag);
  }
  function detail(atomId) {
    var a = null;
    cache.forEach(function (x) { if (x.id === atomId) a = x; });
    var box = $("cdetail");
    var items = document.querySelectorAll("#plist li");
    for (var i = 0; i < items.length; i++)
      items[i].setAttribute("aria-current", items[i].dataset.atom === atomId ? "true" : "false");
    if (!a) { box.innerHTML = "<p class='muted'>Pick a passage to see its tier and membership chain.</p>"; return; }
    var chain = ["<span class='node'>shard 0 · 144 atoms</span>"]
      .concat(a._parents.map(function (pid) {
        var p = parentById[pid];
        return "<span aria-hidden='true'>→</span><span class='node' title='parent group'>" +
          esc(shortId(pid)) + " · " + (p ? p.atom_count : "?") + " atoms</span>";
      }))
      .concat(a.leaf_ids.map(function (lid) {
        return "<span aria-hidden='true'>→</span><span class='node' title='leaf unit'>" +
          esc(shortId(lid)) + " · " + (leafAtoms[lid] || 0) + " atoms</span>";
      }))
      .concat(["<span aria-hidden='true'>→</span><span class='node' title='atom passage'>atom · doc " + esc(a.doc_id) + "</span>"])
      .join("");
    box.innerHTML =
      "<h3 style='margin:.2em 0'>" + esc(a.title || a.id) + "</h3>" +
      "<p class='muted' style='margin:.2em 0'>" + esc(a.snippet || "") + "</p>" +
      "<div class='chain'>" + chain + "</div>" +
      "<dl style='font-size:.85rem'>" +
      "<dt>Tier</dt><dd>atom (passage) → leaf (unit) → parent (group) → shard</dd>" +
      "<dt>Character span</dt><dd>" + esc(JSON.stringify(a.span)) + " in doc " + esc(a.doc_id) + "</dd>" +
      "<dt>Atom id</dt><dd><code style='word-break:break-all'>" + esc(a.id) + "</code></dd>" +
      "</dl>";
  }
  /* ----- map ----- */
  var NS = "http://www.w3.org/2000/svg";
  var view = { x: 0, y: 0, w: 760 };
  var H = 1180, W = 760, sel = null;
  function mk(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function layout() {
    var leaves = C.leaves.slice().sort(function (a, b) { return a.id < b.id ? -1 : 1; });
    var ly = {};
    leaves.forEach(function (l, j) { ly[l.id] = 50 + j * 13.6; });
    var py = {};
    C.parents.forEach(function (p) {
      var ys = p.children.map(function (c) { return ly[c]; }).filter(function (y) { return y !== undefined; });
      py[p.id] = ys.length ? ys.reduce(function (a, b) { return a + b; }, 0) / ys.length : H / 2;
    });
    return { leaves: leaves, ly: ly, py: py };
  }
  function mapBuild() {
    var svg = $("cmap");
    if (!C || !svg) return;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    var L = layout();
    var g = mk("g", {}, svg);
    svg._root = g;
    L.leaves.forEach(function (l) {
      l.parent_ids.forEach(function (pid) {
        if (L.py[pid] === undefined) return;
        mk("line", { x1: 250, y1: L.py[pid], x2: 520, y2: L.ly[l.id],
          stroke: "#9fb2cc", "stroke-width": 1, "data-p": pid, "data-l": l.id, class: "edge" }, g);
      });
    });
    C.parents.forEach(function (p) {
      var y = L.py[p.id];
      mk("line", { x1: 90, y1: H / 2, x2: 250, y2: y, stroke: "#c6d2e4",
        "stroke-width": 1, "data-p": p.id, class: "sedge" }, g);
    });
    mk("circle", { cx: 60, cy: H / 2, r: 16, fill: "#0a1124", "data-n": "shard" }, g);
    mk("text", { x: 60, y: H / 2 + 34, "text-anchor": "middle", "font-size": 11, fill: "currentColor" }, g)
      .textContent = "shard 0 · 144";
    C.parents.forEach(function (p) {
      var y = L.py[p.id], r = 4 + Math.sqrt(p.atom_count || 1) * 1.6;
      mk("circle", { cx: 250, cy: y, r: r, fill: "#0b5fff", opacity: 0.8,
        "data-n": "p:" + p.id, class: "node" }, g);
      var t = mk("text", { x: 250 + r + 4, y: y + 3.5, "font-size": 9.5, fill: "currentColor" }, g);
      t.textContent = shortId(p.id) + "·" + p.atom_count;
    });
    L.leaves.forEach(function (l) {
      mk("circle", { cx: 520, cy: L.ly[l.id], r: 4, fill: multiLeaf[l.id] ? "#8a5a00" : "#2fd6c2",
        stroke: "#0a1124", "stroke-width": 0.6, "data-n": "l:" + l.id, class: "node" }, g);
      var t = mk("text", { x: 530, y: L.ly[l.id] + 3.5, "font-size": 9.5, fill: "currentColor" }, g);
      t.textContent = shortId(l.id) + "·" + (leafAtoms[l.id] || 0);
    });
    var h1 = mk("text", { x: 60, y: 24, "text-anchor": "middle", "font-size": 12, "font-weight": "bold", fill: "currentColor" }, g);
    h1.textContent = "shard";
    var h2 = mk("text", { x: 250, y: 24, "text-anchor": "middle", "font-size": 12, "font-weight": "bold", fill: "currentColor" }, g);
    h2.textContent = "51 parents";
    var h3 = mk("text", { x: 520, y: 24, "text-anchor": "middle", "font-size": 12, "font-weight": "bold", fill: "currentColor" }, g);
    h3.textContent = "81 units (amber = multi-parent)";
    mapPaint();
    /* pan / zoom */
    var drag = null;
    svg.addEventListener("pointerdown", function (e) { drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: 0, n: e.target && e.target.getAttribute ? e.target.getAttribute("data-n") : null }; svg.setPointerCapture(e.pointerId); });
    svg.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var sc = view.w / svg.clientWidth;
      drag.moved += Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y);
      view.x = drag.vx - (e.clientX - drag.x) * sc;
      view.y = drag.vy - (e.clientY - drag.y) * sc;
      mapPaint();
    });
    svg.addEventListener("pointerup", function (e) {
      var wasDrag = drag && drag.moved > 6;
      /* setPointerCapture above retargets pointerup to the svg, so use the
         node recorded at pointerdown; fall back to the event target only when
         no pointerdown was seen (no capture active, target is trustworthy). */
      var n = (drag && drag.n) || (e.target && e.target.getAttribute && e.target.getAttribute("data-n"));
      drag = null;
      if (wasDrag) return;
      select(n || null);
    });
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      zoom(e.deltaY < 0 ? 0.85 : 1.18);
    }, { passive: false });
    $("zin").addEventListener("click", function () { zoom(0.7); });
    $("zout").addEventListener("click", function () { zoom(1.4); });
    $("zreset").addEventListener("click", function () {
      view = { x: 0, y: 0, w: W }; sel = null; paintSel(); mapPaint();
      $("mapnote").textContent = "";
    });
  }
  function zoom(f) {
    var nw = Math.min(W * 1.2, Math.max(120, view.w * f));
    var cx = view.x + view.w / 2, cy = view.y + (view.w * 420 / svgW()) / 2;
    view.w = nw;
    view.x = cx - nw / 2; view.y = cy - (nw * 420 / svgW()) / 2;
    mapPaint();
  }
  function svgW() { var s = $("cmap"); return (s && s.clientWidth) || 700; }
  function mapPaint() {
    var svg = $("cmap");
    if (!svg || !svg._root) return;
    var h = view.w * 420 / svgW();
    svg.setAttribute("viewBox", view.x + " " + view.y + " " + view.w + " " + h);
  }
  function select(n) {
    sel = n; paintSel();
    var note = $("mapnote");
    if (!n) { note.textContent = ""; return; }
    if (n === "shard") { note.textContent = "shard 0: all 51 parents, 81 units, 144 atoms."; return; }
    var kind = n.slice(0, 2), id = n.slice(2);
    if (kind === "p:") {
      var p = parentById[id];
      note.textContent = "parent " + id + ": " + (p ? p.children.length : "?") +
        " child units, " + (p ? p.atom_count : "?") + " atoms.";
    } else {
      var l = leafById[id];
      note.textContent = "unit " + id + ": " + (leafAtoms[id] || 0) + " atoms; parents " +
        (l ? l.parent_ids.map(shortId).join(", ") : "?") + ".";
    }
  }
  function paintSel() {
    var svg = $("cmap");
    if (!svg || !svg._root) return;
    var edges = svg.querySelectorAll(".edge,.sedge"), nodes = svg.querySelectorAll(".node");
    var i;
    if (!sel) {
      for (i = 0; i < edges.length; i++) { edges[i].setAttribute("stroke", edges[i].getAttribute("class") === "edge" ? "#9fb2cc" : "#c6d2e4"); edges[i].setAttribute("stroke-width", 1); }
      for (i = 0; i < nodes.length; i++) nodes[i].setAttribute("opacity", 1);
      return;
    }
    var kind = sel.slice(0, 2), id = sel.slice(2);
    var keepL = {}, keepP = {};
    if (kind === "p:") {
      keepP[id] = 1;
      var p = parentById[id];
      (p ? p.children : []).forEach(function (c) { keepL[c] = 1; });
    } else if (kind === "l:") {
      keepL[id] = 1;
      var l = leafById[id];
      (l ? l.parent_ids : []).forEach(function (x) { keepP[x] = 1; });
    }
    for (i = 0; i < edges.length; i++) {
      var e = edges[i], on = keepP[e.getAttribute("data-p")] && (!e.getAttribute("data-l") || keepL[e.getAttribute("data-l")]);
      e.setAttribute("stroke", on ? "#0b5fff" : "#e2e8f2");
      e.setAttribute("stroke-width", on ? 2 : 1);
    }
    for (i = 0; i < nodes.length; i++) {
      var nd = nodes[i].getAttribute("data-n"), on2 = false;
      if (nd === sel) on2 = true;
      else if (nd && nd.slice(0, 2) === "p:") on2 = !!keepP[nd.slice(2)];
      else if (nd && nd.slice(0, 2) === "l:") on2 = !!keepL[nd.slice(2)];
      nodes[i].setAttribute("opacity", on2 ? 1 : 0.25);
    }
  }
  function init() {
    if (!C || !C.atoms) return;
    build(); stats(); coverage();
    cache = C.atoms.map(function (a) {
      var pls = {};
      (a.leaf_ids || []).forEach(function (lid) {
        var l = null;
        C.leaves.forEach(function (x) { if (x.id === lid) l = x; });
        (l ? l.parent_ids : []).forEach(function (p) { pls[p] = 1; });
      });
      var c = { _parents: Object.keys(pls), _text: "" };
      for (var k in a) c[k] = a[k];
      c._multi = (a.leaf_ids || []).some(function (lid) { return multiLeaf[lid]; });
      c._text = passText(a);
      return c;
    });
    var psel = $("cpar");
    C.parents.slice().sort(function (a, b) { return a.id < b.id ? -1 : 1; }).forEach(function (p) {
      var o = document.createElement("option");
      o.value = p.id; o.textContent = shortId(p.id) + " (" + p.atom_count + " atoms)";
      psel.appendChild(o);
    });
    $("cq").addEventListener("input", renderList);
    psel.addEventListener("change", renderList);
    $("cmp").addEventListener("change", renderList);
    renderList();
    mapBuild();
  }
  return { init: init, mapPaint: mapPaint, shortId: shortId,
    counts: function () { return C ? { atoms: C.atoms.length, leaves: C.leaves.length, parents: C.parents.length } : null; } };
})();

/* ================= QUERY TRACE ================= */
var Trace = (function () {
  var NS = "http://www.w3.org/2000/svg";
  var probes = [], qi = 0, pi = 0, step = 0, tick = 0, playing = false, raf = 0;
  var STEPS = ["Query", "Route", "Open groups", "Candidate set C", "Rerank", "Answer"];
  function evalRows() { return (C && C.evaluation_queries) || []; }
  function pickProbes() {
    var rows = evalRows(), seen = {}, out = [];
    rows.forEach(function (e, i) {
      var k = e.family + "|" + (e.leave_source_out ? "t" : "f");
      if (!seen[k]) { seen[k] = 1; out.push(i); }
    });
    probes = out.slice(0, 6);
  }
  function probeLabel(i) {
    var e = evalRows()[i];
    return "probe #" + e.probe + " · " + e.family + " · leave-source-out " +
      (e.leave_source_out ? "on" : "off") + " · recall " + e.guided_recall10.toFixed(2);
  }
  function counts() {
    var e = evalRows()[probes[pi]], q = R.questions[qi];
    return [
      { n: "1 query", d: (q ? "“" + q.q + "”" : "") },
      { n: e.work.parents_scored + " rows", d: "score query vs parent centres" },
      { n: e.work.children_scored + " units", d: "open best-matching units" },
      { n: e.work.atoms_scored + " atoms", d: e.work.member_visits + " member visits" },
      { n: e.guided_scoring_rows + " rows", d: "score C, keep top 10" },
      { n: "10 passages", d: "recall@10 " + e.guided_recall10.toFixed(2) + " (recorded)" }
    ];
  }
  function renderStages() {
    var cs = counts(), ol = $("stages");
    ol.innerHTML = "";
    cs.forEach(function (c, i) {
      var li = document.createElement("li");
      li.setAttribute("aria-current", i === step ? "true" : "false");
      if (i < step) li.className = "done";
      li.innerHTML = "<div class='k'>step " + (i + 1) + "</div><div class='n'>" + STEPS[i] +
        "</div><div class='c'>" + esc(c.n) + "</div><div class='d'>" + esc(c.d) + "</div>" +
        "<span class='arrow' aria-hidden='true'>▶</span>";
      li.tabIndex = 0;
      function go() { setStep(i, 0); }
      li.addEventListener("click", go);
      li.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      ol.appendChild(li);
    });
    var e = evalRows()[probes[pi]], q = R.questions[qi];
    $("tprov").textContent = "Counts from eval row " + probes[pi] + " of " + evalRows().length +
      " (" + e.family + ", leave-source-out " + (e.leave_source_out ? "on" : "off") +
      "); question “" + (q ? q.q : "?") + "” recorded " + (q ? q.t : "?") + ". " +
      "Sealed-library context: 0.79% ≈ 1,600 of 203,137 rows on one part.";
    renderAnswer();
    renderReceipts();
    flowPaint();
  }
  function renderAnswer() {
    var q = R.questions[qi], box = $("tanswer");
    if (!q) { box.innerHTML = ""; return; }
    var fi = q.f.map(function (x) { return x[0]; });
    var items = q.g.map(function (hit, i) {
      var p = RP[hit[0]] || {}, fr = fi.indexOf(hit[0]) + 1;
      return "<li><b>" + (i + 1) + ".</b> " + esc(p.ti || ("passage " + hit[0])) +
        " <span class='muted'>closeness " + hit[1].toFixed(3) + "</span>" +
        (fr ? "<span class='tag same'>exact rank " + fr + "</span>" : "<span class='tag only'>only TRACE</span>") + "</li>";
    }).join("");
    box.innerHTML = "<h3 style='margin:.2em 0'>Answer: top 10 for “" + esc(q.q) + "” " +
      "<span class='pill recorded'>RECORDED</span></h3><ol>" + items + "</ol>" +
      "<p class='muted'>Recorded " + esc(q.t) + " · server timings when recorded: TRACE " +
      (q.tg / 1000).toFixed(2) + " s, exact " + (q.tf / 1000).toFixed(2) +
      " s (no speed claim). Stage shapes and flow are " +
      "<span class='pill designed'>DESIGNED</span>.</p>";
  }
  function renderReceipts() {
    var e = evalRows()[probes[pi]], q = R.questions[qi];
    $("treceipt").textContent = JSON.stringify(e, null, 1);
    $("treceipt2").textContent = JSON.stringify({ question: q.q, guided_top10: q.g, flat_top10: q.f }, null, 1);
  }
  /* flow strip: 6 nodes, dots positioned by (step, tick); deterministic for film frames */
  var FX = [60, 210, 360, 510, 660, 810], FW = 870, FH = 96;
  function flowBuild() {
    var svg = $("flow");
    svg.setAttribute("viewBox", "0 0 " + FW + " " + FH);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var g = document.createElementNS(NS, "g");
    svg.appendChild(g);
    svg._g = g;
    for (var i = 0; i < 6; i++) {
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", FX[i]); c.setAttribute("cy", 40); c.setAttribute("r", 14);
      c.setAttribute("fill", "#0a1124"); c.setAttribute("data-fx", i);
      g.appendChild(c);
      var t = document.createElementNS(NS, "text");
      t.setAttribute("x", FX[i]); t.setAttribute("y", 44.5); t.setAttribute("text-anchor", "middle");
      t.setAttribute("font-size", 12); t.setAttribute("fill", "#fff");
      t.textContent = String(i + 1);
      g.appendChild(t);
      var lab = document.createElementNS(NS, "text");
      lab.setAttribute("x", FX[i]); lab.setAttribute("y", 72); lab.setAttribute("text-anchor", "middle");
      lab.setAttribute("font-size", 10.5); lab.setAttribute("fill", "currentColor");
      lab.textContent = STEPS[i];
      g.appendChild(lab);
      if (i < 5) {
        var ln = document.createElementNS(NS, "line");
        ln.setAttribute("x1", FX[i] + 16); ln.setAttribute("y1", 40);
        ln.setAttribute("x2", FX[i + 1] - 16); ln.setAttribute("y2", 40);
        ln.setAttribute("stroke", "#9fb2cc"); ln.setAttribute("stroke-width", 2);
        g.appendChild(ln);
      }
    }
    for (var d = 0; d < 3; d++) {
      var dot = document.createElementNS(NS, "circle");
      dot.setAttribute("r", 4.5); dot.setAttribute("fill", "#0b5fff");
      dot.setAttribute("data-dot", d);
      g.appendChild(dot);
    }
    flowPaint();
  }
  function flowPaint() {
    var svg = $("flow");
    if (!svg || !svg._g) return;
    var nodes = svg._g.querySelectorAll("[data-fx]");
    for (var i = 0; i < nodes.length; i++)
      nodes[i].setAttribute("fill", i < step ? "#1c7a3d" : (i === step ? "#0b5fff" : "#0a1124"));
    var dots = svg._g.querySelectorAll("[data-dot]");
    for (var d = 0; d < dots.length; d++) {
      var off = (d / 3 + tick) % 1;
      var from = FX[Math.min(step, 5)], to = FX[Math.min(step + 1, 5)];
      var x = step >= 5 ? FX[5] : from + (to - from) * off;
      dots[d].setAttribute("cx", x);
      dots[d].setAttribute("cy", 40);
      dots[d].setAttribute("opacity", step >= 5 && d > 0 ? 0 : 1);
    }
  }
  function setStep(s, t) {
    step = Math.max(0, Math.min(5, s));
    tick = t || 0;
    renderStages();
  }
  function stop() {
    playing = false;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    $("tplay").textContent = "▶ Play (20 s)";
  }
  function play() {
    if (playing) { stop(); return; }
    if (STATIC) return;
    playing = true;
    $("tplay").textContent = "⏸ Pause";
    if (REDUCED) { /* jump steps without smooth motion */
      setStep(0, 0);
      var jumps = [0, 1, 2, 3, 4, 5], j = 0;
      var iv = setInterval(function () {
        j++;
        if (j >= jumps.length || !playing) { clearInterval(iv); stop(); setStep(5, 0); return; }
        setStep(j, 0);
      }, 3000);
      return;
    }
    var t0 = null, DUR = 20000;
    setStep(0, 0);
    function frame(ts) {
      if (!playing) return;
      if (t0 === null) t0 = ts;
      var el = Math.min(DUR, ts - t0), frac = el / DUR;
      var s = Math.min(5, Math.floor(frac * 6));
      var tk = frac * 6 - s;
      if (s !== step) { step = s; renderStages(); }
      tick = tk; flowPaint();
      if (el >= DUR) { stop(); setStep(5, 0); return; }
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
  }
  function enter() { flowPaint(); }
  function init() {
    if (!R || !R.questions || !C || !C.evaluation_queries) return;
    pickProbes();
    var tq = $("tq");
    R.questions.forEach(function (q, i) {
      var o = document.createElement("option");
      o.value = i; o.textContent = q.q + " (" + q.cat + ")";
      tq.appendChild(o);
    });
    var tp = $("tp");
    probes.forEach(function (idx, k) {
      var o = document.createElement("option");
      o.value = k; o.textContent = probeLabel(idx);
      tp.appendChild(o);
    });
    if (P.q !== undefined && R.questions[+P.q]) qi = +P.q;
    if (P.probe !== undefined && probes[+P.probe] !== undefined) pi = +P.probe;
    if (P.step !== undefined) step = Math.max(0, Math.min(5, +P.step || 0));
    if (P.tick !== undefined) tick = Math.max(0, Math.min(0.99, +P.tick || 0));
    tq.value = qi; tp.value = pi;
    tq.addEventListener("change", function () { stop(); qi = +tq.value; renderStages(); });
    tp.addEventListener("change", function () { stop(); pi = +tp.value; renderStages(); });
    $("tprev").addEventListener("click", function () { stop(); setStep(step - 1, 0); });
    $("tnext").addEventListener("click", function () { stop(); setStep(step + 1, 0); });
    $("tplay").addEventListener("click", play);
    flowBuild();
    renderStages();
  }
  return { init: init, enter: enter,
    state: function () { return { step: step, qi: qi, pi: pi, stages: STEPS.length }; } };
})();

/* ---------- init ---------- */
Corpus.init();
Trace.init();
(function () {
  var start = P.view || window.location.hash.replace(/^#\/?/, "").split("?")[0] || "corpus";
  if (VIEWS.indexOf(start) < 0) start = "corpus";
  try { history.replaceState(null, "", "#/" + start); } catch (e) { window.location.hash = "#/" + start; }
  show(start);
})();

/* test hooks */
window.__INSIDE__ = {
  view: function () { return curView; },
  corpus: function () { return Corpus.counts(); },
  trace: function () { return Trace.state(); }
};
})();
