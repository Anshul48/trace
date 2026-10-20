/* TRACE play/ — probe-first replay theater over staged exports. Vanilla, zero deps.
   Small files paint first; 10M graph is opt-in. Every number carries data-src. */
(function () {
  "use strict";

  var EXP = "../explorer/";
  var SMALL = ["probes_summary.json", "qualification_10m.json", "local_20k_data.json", "result.json"];
  var D = { prov: null, summary: null, qual: null, slice20k: null, result: null, skel: null, graph: null, manifest: {} };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function reducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) {
      return ("0" + b.toString(16)).slice(-2);
    }).join("");
  }

  /* ---------- fetch + manifest verify ---------- */
  function cachePut(url, buf) {
    if (!("caches" in window)) return;
    try {
      caches.open("play-v1").then(function (c) {
        c.put(url, new Response(buf.slice(0), { headers: { "Content-Type": "application/json" } }));
      });
    } catch (e) { /* offline cache best-effort */ }
  }

  function fetchVerified(dir, name, key) {
    var url = dir + name;
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " " + name);
      return r.arrayBuffer();
    }).then(function (buf) {
      cachePut(url, buf);
      return crypto.subtle.digest("SHA-256", buf).then(function (digest) {
        var sha = hex(digest);
        var want = D.prov && D.prov.files[key || ("explorer/" + name)];
        var ok = want ? (want.sha256 === sha) : null;
        D.manifest[name] = { bytes: buf.byteLength, sha: sha, ok: ok };
        renderManifest();
        var text = new TextDecoder().decode(buf);
        return JSON.parse(text);
      });
    });
  }

  function renderManifest() {
    var tb = document.querySelector("#manifest tbody");
    if (!tb) return;
    var rows = Object.keys(D.manifest).sort().map(function (name) {
      var m = D.manifest[name];
      var st = m.ok === null ? "unpinned" : (m.ok ? "✓ verified" : "✗ MISMATCH");
      return "<tr><td>" + esc(name) + "</td><td data-src=\"provenance.json#files\">" + m.bytes +
        "</td><td><code>" + esc(m.sha.slice(0, 16)) + "…</code></td><td>" + st + "</td></tr>";
    });
    tb.innerHTML = rows.length ? rows.join("") : "<tr><td colspan=\"4\">verifying…</td></tr>";
  }

  /* ---------- hash router (accepts #p=… and #/play?p=…) ---------- */
  function parseHash() {
    var h = location.hash.replace(/^#/, "");
    h = h.replace(/^\/play\?/, "");
    var q = {};
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) q[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
    });
    var st = { p: 0, m: "10m", v: "race", lso: 0, t: 7, reset: false };
    function bad() { st.reset = true; }
    if (q.p !== undefined) {
      var p = parseInt(q.p, 10);
      if (isNaN(p) || p < 0 || p > 119) bad(); else st.p = p;
    }
    if (q.m !== undefined) {
      if (q.m === "10m" || q.m === "20k") st.m = q.m; else bad();
    }
    if (q.v !== undefined) {
      if (q.v === "guided" || q.v === "flat" || q.v === "race") st.v = q.v; else bad();
    }
    if (q.lso !== undefined) {
      if (q.lso === "0" || q.lso === "1") st.lso = +q.lso; else bad();
    }
    if (q.t !== undefined) {
      var t = parseInt(q.t, 10);
      if (isNaN(t) || t < 0 || t > 7) bad(); else st.t = t;
    }
    return st;
  }

  function writeHash(st) {
    location.hash = "p=" + st.p + "&m=" + st.m + "&v=" + st.v + "&lso=" + st.lso + "&t=" + st.t;
  }

  /* ---------- rows ---------- */
  function rowFor(probe, m, lso) {
    var rows = m === "10m" ? D.qual.queries : D.slice20k.evaluation_queries;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.probe === probe && (r.leave_source_out ? 1 : 0) === lso) return { row: r, ix: i };
    }
    return null;
  }

  function srcFor(m, ix, field) {
    var file = m === "10m" ? "qualification_10m.json#queries[" + ix + "]." :
      "local_20k_data.json#evaluation_queries[" + ix + "].";
    return file + field;
  }

  /* ---------- replay render ---------- */
  var anim = { raf: 0, t0: 0, lit: 1 };

  function renderReplay(st) {
    var found = rowFor(st.p, st.m, st.lso);
    if (!found) return;
    var r = found.row, ix = found.ix;
    var fam = r.family || "?";

    // Picker.
    var sel = $("probe");
    if (!sel.options.length) {
      for (var i = 0; i < 120; i++) {
        var o = document.createElement("option");
        var rr = rowFor(i, "10m", 0);
        o.value = i;
        o.textContent = "#" + i + " (" + (rr ? rr.row.family : "?") + ")";
        sel.appendChild(o);
      }
    }
    sel.value = st.p;
    $("corpus").value = st.m;
    $("view").value = st.v;
    $("lso").value = st.lso;

    // Race bars.
    var g = r.guided_recall10, f = r.flat_recall10;
    var cls = st.lso ? " lso" : "";
    var html = "";
    function bar(label, val, flat, src) {
      return "<div class=\"bar-row\"><span>" + label + "</span><span class=\"track\">" +
        "<span class=\"bar-fill" + (flat ? " flat" : cls) + "\" style=\"width:" + (val * 100).toFixed(1) +
        "%\"></span></span><span data-src=\"" + src + "\">" + val.toFixed(4).replace(/0+$/, "").replace(/\.$/, ".0") + "</span></div>";
    }
    if (st.v === "guided" || st.v === "race") html += bar("guided", g, false, srcFor(st.m, ix, "guided_recall10"));
    if (st.v === "flat" || st.v === "race") html += bar("flat", f, true, srcFor(st.m, ix, "flat_recall10"));
    if (st.v === "race") {
      html += "<p class=\"src\">" + (g === f ? "tie" : (g > f ? "guided wins" : "flat wins — losses stay visible")) +
        " · matched work: " + (r.matched_work ? "yes" : "no") + "</p>";
    }
    $("race").innerHTML = html;

    // Work line with provenance.
    var w = r.work || {};
    $("workline").innerHTML =
      "probe <b data-src=\"" + srcFor(st.m, ix, "probe") + "\">#" + st.p + "</b> (" + esc(fam) + ", " +
      (st.lso ? "leave-source-out" : "all-sources") + ", " + (st.m === "10m" ? "10M structure" : "20K readable") +
      ") — parents scored <b data-src=\"" + srcFor(st.m, ix, "work.parents_scored") + "\">" + w.parents_scored +
      "</b> · children <b data-src=\"" + srcFor(st.m, ix, "work.children_scored") + "\">" + w.children_scored +
      "</b> · atoms <b data-src=\"" + srcFor(st.m, ix, "work.atoms_scored") + "\">" + w.atoms_scored +
      "</b> · scoring rows <b data-src=\"" + srcFor(st.m, ix, "guided_scoring_rows") + "\">" + r.guided_scoring_rows + "</b>";

    // Scrub slider follows hash.
    $("scrub").value = st.t;

    // Canvas cascade.
    anim.lit = 0;
    anim.t0 = performance.now();
    cancelAnimationFrame(anim.raf);
    if (reducedMotion()) { anim.lit = 1; drawDAG(st, r); }
    else {
      (function step(ts) {
        anim.lit = Math.min(1, (ts - anim.t0) / 700);
        drawDAG(st, r);
        if (anim.lit < 1) anim.raf = requestAnimationFrame(step);
      })(anim.t0);
    }
  }

  function drawDAG(st, r) {
    var cvs = $("dag");
    var ctx = cvs.getContext("2d");
    var W = cvs.width, H = cvs.height;
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    var bg = dark ? "#0e1116" : "#f4f6f8";
    var dot = dark ? "#484f58" : "#8b98a8";
    var lit = st.lso ? (dark ? "#3fb950" : "#0a6e4e") : (dark ? "#4493f8" : "#0b5cad");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // Scrub density: fraction of phases complete dims the field honestly.
    var dens = 0.25 + 0.75 * ((st.t + 1) / 8);

    if (st.m === "10m" && D.skel) {
      var P = D.skel.parents;
      var path = D.skel.probe_paths[String(st.p)] || { root: 0, leaves: [], atoms: [] };
      var leafSet = {}, atomSet = {};
      path.leaves.forEach(function (id) { leafSet[id] = 1; });
      path.atoms.forEach(function (id) { atomSet[id] = 1; });
      // Parent field.
      for (var i = 0; i < P.length; i++) {
        var isRoot = (i === path.root);
        ctx.globalAlpha = isRoot ? 1 : 0.75 * dens; // field always on
        ctx.fillStyle = isRoot ? lit : dot;
        var s = isRoot ? 8 : 2.6;
        ctx.fillRect(P[i][1] * W - s / 2, P[i][2] * H - s / 2, s, s);
      }
      // Path edges: root -> leaves -> atoms.
      var R0e = P[path.root];
      ctx.globalAlpha = Math.min(1, anim.lit * 1.4);
      ctx.strokeStyle = lit; ctx.lineWidth = 1.5;
      D.skel.leaves.forEach(function (L) {
        if (!leafSet[L[0]]) return;
        ctx.beginPath(); ctx.moveTo(R0e[1] * W, R0e[2] * H);
        ctx.lineTo(L[1] * W, L[2] * H); ctx.stroke();
      });
      // Neighborhood: leaves then atoms cascade.
      var lp = Math.min(1, anim.lit * 1.6), ap = Math.max(0, anim.lit * 1.6 - 0.6);
      ctx.globalAlpha = 1;
      D.skel.leaves.forEach(function (L) {
        if (!leafSet[L[0]]) return;
        ctx.globalAlpha = lp;
        ctx.strokeStyle = lit; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(L[1] * W, L[2] * H, 12, 0, 7); ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.fillStyle = lit;
        ctx.font = "10px sans-serif";
        ctx.fillText(String(L[0]).slice(0, 18), L[1] * W + 14, L[2] * H + 4);
      });
      D.skel.atoms.forEach(function (A) {
        if (!atomSet[A[0]]) return;
        ctx.globalAlpha = ap;
        ctx.fillStyle = lit;
        ctx.fillRect(A[1] * W - 3, A[2] * H - 3, 6, 6);
      });
      ctx.globalAlpha = 1;
      // Root id tag.
      ctx.fillStyle = lit;
      ctx.font = "11px sans-serif";
      var R0 = P[path.root];
      ctx.fillText("root " + String(R0[0]).slice(0, 30), R0[1] * W + 10, R0[2] * H - 8);
      ctx.fillStyle = dark ? "#8b949e" : "#3d4c5c";
      ctx.fillText("3,711 parents · neighborhood of probe #" + st.p + " · phase " + st.t + "/7", 10, H - 10);
    } else if (D.slice20k) {
      // 20k mode: real 51 parents + 81 leaves on an index grid.
      var ps = D.slice20k.parents || [], ls = D.slice20k.leaves || [];
      var nk = Math.min(ps.length, (r.work && r.work.parents_scored) || 0);
      var lk = Math.min(ls.length, (r.work && r.work.children_scored) || 0);
      for (var pi = 0; pi < ps.length; pi++) {
        ctx.fillStyle = pi < nk * anim.lit ? lit : dot;
        var gx = 20 + (pi % 17) * ((W - 40) / 16), gy = 30 + Math.floor(pi / 17) * 26;
        ctx.beginPath(); ctx.arc(gx, gy, pi < nk * anim.lit ? 6 : 4, 0, 7); ctx.fill();
      }
      for (var li = 0; li < ls.length; li++) {
        ctx.fillStyle = li < lk * anim.lit ? lit : dot;
        var hx = 20 + (li % 27) * ((W - 40) / 26), hy = 140 + Math.floor(li / 27) * 26;
        ctx.beginPath(); ctx.arc(hx, hy, li < lk * anim.lit ? 6 : 4, 0, 7); ctx.fill();
      }
      ctx.fillStyle = dark ? "#8b949e" : "#3d4c5c";
      ctx.font = "11px sans-serif";
      ctx.fillText("20K readable slice: 51 parents / 81 leaves · lit = recorded work counts (selection in index order, labeled)", 10, H - 10);
    }
    ctx.globalAlpha = 1;
  }

  /* ---------- re-run: re-aggregate + CI + verify ---------- */
  function lcg(seed) {
    var a = seed >>> 0;
    return function () {
      a = (Math.imul(a, 1664525) + 1013904223) >>> 0;
      return a / 4294967296;
    };
  }

  function runRerun() {
    var out = $("rerun-out");
    function agg(rows, lso) {
      var g = rows.filter(function (r) { return (r.leave_source_out ? 1 : 0) === lso; })
        .map(function (r) { return r.guided_recall10; });
      var f = rows.filter(function (r) { return (r.leave_source_out ? 1 : 0) === lso; })
        .map(function (r) { return r.flat_recall10; });
      function mean(a) { return a.reduce(function (x, y) { return x + y; }, 0) / a.length; }
      function sd(a, m) {
        return Math.sqrt(a.reduce(function (x, y) { return x + (y - m) * (y - m); }, 0) / (a.length - 1));
      }
      var mg = mean(g), sg = sd(g, mg);
      var n = g.length;
      var ci = 1.96 * sg / Math.sqrt(n);
      // Bootstrap (seeded, deterministic).
      var rnd = lcg(1207), boots = [];
      for (var k = 0; k < 1000; k++) {
        var s = 0;
        for (var j = 0; j < n; j++) s += g[Math.floor(rnd() * n)];
        boots.push(s / n);
      }
      boots.sort(function (a, b) { return a - b; });
      return { n: n, mg: mg, mf: mean(f), ci: ci, lo: boots[25], hi: boots[974] };
    }
    var q = D.qual, s = D.slice20k;
    var a10 = agg(q.queries, 0), l10 = agg(q.queries, 1);
    var a20 = agg(s.evaluation_queries, 0), l20 = agg(s.evaluation_queries, 1);
    var ev = q.evaluation_summary || q.eval_summary || {};
    function close(a, b) { return Math.abs(a - b) < 1e-9; }
    var checks = [];
    if (ev.all_sources) {
      checks.push(["10M guided(all) vs eval_summary", close(a10.mg, ev.all_sources.guided_recall10)]);
      checks.push(["10M flat(all) vs eval_summary", close(a10.mf, ev.all_sources.flat_recall10)]);
    }
    if (ev.leave_source_out) {
      checks.push(["10M guided(lso) vs eval_summary", close(l10.mg, ev.leave_source_out.guided_recall10)]);
    }
    var manOK = Object.keys(D.manifest).every(function (k) { return D.manifest[k].ok !== false; });
    checks.push(["manifest sha256 (all fetched files)", manOK]);
    function cell(v, src) { return "<b data-src=\"" + src + "\">" + v.toFixed(4) + "</b>"; }
    out.innerHTML =
      "<div style=\"overflow-x:auto\"><table class=\"data\"><thead><tr><th scope=\"col\">Corpus / mode</th><th scope=\"col\">guided mean</th>" +
      "<th scope=\"col\">flat mean</th><th scope=\"col\">95% CI (guided)</th><th scope=\"col\">bootstrap 95%</th></tr></thead><tbody>" +
      "<tr><td>10M all (n=120)</td><td>" + cell(a10.mg, "recomputed#10m.all.guided") + "</td><td>" + cell(a10.mf, "recomputed#10m.all.flat") +
      "</td><td>±" + a10.ci.toFixed(4) + "</td><td>[" + a10.lo.toFixed(4) + ", " + a10.hi.toFixed(4) + "]</td></tr>" +
      "<tr><td>10M lso (n=120)</td><td>" + cell(l10.mg, "recomputed#10m.lso.guided") + "</td><td>" + cell(l10.mf, "recomputed#10m.lso.flat") +
      "</td><td>±" + l10.ci.toFixed(4) + "</td><td>[" + l10.lo.toFixed(4) + ", " + l10.hi.toFixed(4) + "]</td></tr>" +
      "<tr><td>20K all (n=120)</td><td>" + cell(a20.mg, "recomputed#20k.all.guided") + "</td><td>" + cell(a20.mf, "recomputed#20k.all.flat") +
      "</td><td>±" + a20.ci.toFixed(4) + "</td><td>[" + a20.lo.toFixed(4) + ", " + a20.hi.toFixed(4) + "]</td></tr>" +
      "<tr><td>20K lso (n=120)</td><td>" + cell(l20.mg, "recomputed#20k.lso.guided") + "</td><td>" + cell(l20.mf, "recomputed#20k.lso.flat") +
      "</td><td>±" + l20.ci.toFixed(4) + "</td><td>[" + l20.lo.toFixed(4) + ", " + l20.hi.toFixed(4) + "]</td></tr>" +
      "</tbody></table></div>" +
      "<ul>" + checks.map(function (c) {
        return "<li>" + esc(c[0]) + ": <b>" + (c[1] ? "✓ match" : "✗ MISMATCH") + "</b></li>";
      }).join("") + "</ul>" +
      "<p class=\"src\">Recomputed live from staged rows in this page — not pasted. CI: normal approx; bootstrap: 1000 seeded resamples.</p>";
  }

  /* ---------- misses ---------- */
  function renderMisses() {
    var m = $("misscorpus").value, lso = +$("misslso").value;
    var rows = (m === "10m" ? D.qual.queries : D.slice20k.evaluation_queries)
      .map(function (r, ix) { return { r: r, ix: ix }; })
      .filter(function (e) { return (e.r.leave_source_out ? 1 : 0) === lso; })
      .sort(function (a, b) { return a.r.guided_recall10 - b.r.guided_recall10; })
      .slice(0, 10);
    var tb = document.querySelector("#misses tbody");
    tb.innerHTML = rows.map(function (e) {
      var r = e.r;
      var flag = r.flat_recall10 > r.guided_recall10 ? " ★ flat wins" : "";
      var href = "#p=" + r.probe + "&m=" + m + "&v=race&lso=" + lso + "&t=7";
      return "<tr><td>" + r.probe + "</td><td>" + esc(r.family || "?") + "</td>" +
        "<td data-src=\"" + srcFor(m, e.ix, "guided_recall10") + "\">" + r.guided_recall10.toFixed(2) + "</td>" +
        "<td data-src=\"" + srcFor(m, e.ix, "flat_recall10") + "\">" + r.flat_recall10.toFixed(2) + flag + "</td>" +
        "<td><a href=\"" + href + "\">replay</a></td></tr>";
    }).join("");
  }

  /* ---------- scrub ---------- */
  function renderScrub(st) {
    var walls = (D.result && D.result.walls_s) || (D.qual && D.qual.walls_s) || {};
    var names = Object.keys(walls);
    var cum = 0;
    var tb = document.querySelector("#phases tbody");
    tb.innerHTML = names.map(function (nm, i) {
      var w = walls[nm];
      cum += w;
      var mark = i === st.t ? " ←" : "";
      return "<tr><td>" + esc(nm) + mark + "</td>" +
        "<td data-src=\"result.json#walls_s." + esc(nm) + "\">" + w.toFixed(1) + " s</td>" +
        "<td>" + cum.toFixed(0) + " s</td></tr>";
    }).join("");
    $("scrub").max = names.length - 1;
  }

  /* ---------- 20k search ---------- */
  function initSearch() {
    var atoms = D.slice20k.atoms || [];
    var q = $("q"), qs = $("q-status"), hits = $("hits");
    qs.textContent = atoms.length + " recorded atoms loaded (20K slice). Type to search titles + snippets.";
    var t = null;
    q.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () {
        var needle = q.value.trim().toLowerCase();
        hits.innerHTML = "";
        if (!needle) { qs.textContent = atoms.length + " recorded atoms loaded. Type to search."; return; }
        var out = atoms.filter(function (a) {
          return ((a.title || "") + " " + (a.snippet || "")).toLowerCase().indexOf(needle) !== -1;
        });
        if (!out.length) {
          qs.textContent = atoms.length + " recorded atoms searched, no matches. Slice only — not the 10M index.";
          return;
        }
        qs.textContent = out.length + " of " + atoms.length + " recorded atoms match (top 20 shown). Recorded slice, not the 10M index.";
        out.slice(0, 20).forEach(function (a, i) {
          var li = document.createElement("li");
          var title = a.title || "(untitled atom " + String(a.id).slice(0, 8) + ")";
          var snip = (a.snippet || "").slice(0, 220);
          li.innerHTML = "<div class=\"t\">" + esc(title) + "</div>" +
            "<div class=\"s\" data-src=\"local_20k_data.json#atoms\">" + esc(snip) +
            ((a.snippet && a.snippet.length > 220) ? "…" : "") + "</div>" +
            "<div class=\"s\">doc " + esc(a.doc_id || "?") + "</div>";
          hits.appendChild(li);
        });
      }, 120);
    });
  }

  /* ---------- 10m opt-in verify ---------- */
  function initOptin() {
    var btn = $("load10m"), cancel = $("cancel10m"), bar = $("dl10m"), st = $("m10m-status");
    var ctrl = null;
    btn.addEventListener("click", function () {
      if (!("DecompressionStream" in window)) {
        st.textContent = "This browser cannot gunzip in-page (no DecompressionStream). Grab graph_10m.json directly from the explorer folder.";
        return;
      }
      ctrl = new AbortController();
      btn.disabled = true; cancel.disabled = false; bar.hidden = false; bar.value = 0;
      st.textContent = "Downloading graph_10m.json.gz (7.25 MB)…";
      fetch(EXP + "graph_10m.json.gz", { signal: ctrl.signal }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        var total = +(r.headers.get("content-length") || 7254185);
        var reader = r.body.getReader();
        var chunks = [], seen = 0;
        function pump() {
          return reader.read().then(function (step) {
            if (step.done) return new Blob(chunks);
            chunks.push(step.value); seen += step.value.length;
            bar.value = Math.min(100, (seen / total) * 100);
            st.textContent = "Downloading… " + (seen / 1048576).toFixed(1) + " / 7.25 MB";
            return pump();
          });
        }
        return pump();
      }).then(function (blob) {
        st.textContent = "Verifying sha256, then decompressing 21.7 MB locally…";
        return blob.arrayBuffer().then(function (buf) {
          cachePut(EXP + "graph_10m.json.gz", buf);
          return crypto.subtle.digest("SHA-256", buf).then(function (digest) {
            var sha = hex(digest);
            var want = D.prov.files["explorer/graph_10m.json.gz"];
            D.manifest["graph_10m.json.gz"] = { bytes: buf.byteLength, sha: sha, ok: want.sha256 === sha };
            renderManifest();
            if (want.sha256 !== sha) throw new Error("sha256 MISMATCH on graph_10m.json.gz");
            var ds = new DecompressionStream("gzip");
            return new Response(new Blob([buf]).stream().pipeThrough(ds)).json();
          });
        });
      }).then(function (g) {
        D.graph = g;
        var np = (g.parents && g.parents.length) || 0;
        var nl = (g.leaves && g.leaves.length) || 0;
        var na = (g.atoms && g.atoms.length) || 0;
        // Skeleton ⊆ graph check (all skeleton parent ids present).
        var ids = {};
        g.parents.forEach(function (p) { ids[p.id] = 1; });
        var missing = D.skel.parents.filter(function (P) { return !ids[P[0]]; }).length;
        st.innerHTML = "Loaded locally: <b data-src=\"graph_10m.json#manifest\">" + np +
          " parents / " + nl + " leaves / " + na + " atoms</b>. Skeleton check: " +
          (missing === 0 ? "✓ all 3,711 skeleton parents resolve in the full export." :
            "✗ " + missing + " skeleton parents MISSING from export.");
        bar.value = 100;
      }).catch(function (e) {
        st.textContent = (e && e.name === "AbortError") ? "Cancelled — nothing kept." :
          "Load failed (" + (e && e.message) + "). The raw file is still at explorer/graph_10m.json.";
      }).finally(function () {
        btn.disabled = false; cancel.disabled = true; ctrl = null;
      });
    });
    cancel.addEventListener("click", function () { if (ctrl) ctrl.abort(); });
  }

  /* ---------- boot ---------- */
  function currentState() { return parseHash(); }

  function applyStateToControls(st) {
    renderReplay(st);
    renderScrub(st);
    if (st.reset) {
      $("hashnote").textContent = "unreadable URL state — reset to probe 0.";
      writeHash(st);
    } else {
      $("hashnote").textContent = "";
    }
  }

  function boot() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(function () { /* offline SW best-effort */ });
    }
    fetch(EXP + "../play/provenance.json").then(function (r) { return r.json(); })
      .then(function (prov) {
        D.prov = prov;
        return Promise.all([
          fetchVerified(EXP, "probes_summary.json"),
          fetchVerified(EXP, "qualification_10m.json"),
          fetchVerified(EXP, "local_20k_data.json"),
          fetchVerified(EXP, "result.json"),
          fetchVerified("../play/", "dag-skeleton.json", "play/dag-skeleton.json")
        ]);
      }).then(function (all) {
        D.summary = all[0]; D.qual = all[1]; D.slice20k = all[2]; D.result = all[3]; D.skel = all[4];
        var st = currentState();
        applyStateToControls(st);
        renderMisses();
        initSearch();
        // Wire controls.
        $("probe").addEventListener("change", function () {
          st.p = +$("probe").value; writeHash(st);
        });
        $("prev").addEventListener("click", function () {
          st.p = (st.p + 119) % 120; writeHash(st);
        });
        $("next").addEventListener("click", function () {
          st.p = (st.p + 1) % 120; writeHash(st);
        });
        $("corpus").addEventListener("change", function () { st.m = $("corpus").value; writeHash(st); });
        $("view").addEventListener("change", function () { st.v = $("view").value; writeHash(st); });
        $("lso").addEventListener("change", function () { st.lso = +$("lso").value; writeHash(st); });
        $("scrub").addEventListener("change", function () { st.t = +$("scrub").value; writeHash(st); });
        window.addEventListener("hashchange", function () {
          st = currentState();
          applyStateToControls(st);
        });
        $("copylink").addEventListener("click", function () {
          var url = location.href;
          function done() { $("hashnote").textContent = "link copied."; }
          if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done);
          else done();
        });
        $("rerun").addEventListener("click", runRerun);
        $("misscorpus").addEventListener("change", renderMisses);
        $("misslso").addEventListener("change", renderMisses);
        initOptin();
        window.__playReady = true;
      }).catch(function (e) {
        $("workline").textContent = "Could not load staged files (" + e.message +
          "). If offline: reconnect once to fetch them — then airplane mode works.";
        window.__playReady = false;
      });
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
