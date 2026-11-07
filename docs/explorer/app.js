/* TRACE Explorer: static replay. No network calls; all data comes from data/replay.js. */
(function () {
  "use strict";
  var R = window.TRACE_REPLAY;
  var $ = function (id) { return document.getElementById(id); };
  if (!R || !R.questions) {
    $("results").innerHTML = '<p class="wrap">The recorded data did not load (data/replay.js).</p>';
    return;
  }
  var Q = R.questions, P = R.passages, TOTAL = (R.meta && R.meta.library_passages) || 812545;
  var CATS = ["Science", "History", "How things work", "World and culture", "Weaker matches"];
  var cur = null;          // current question object
  var curCat = CATS[0];

  /* ---------- small helpers ---------- */
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(n) { return Number(n).toLocaleString("en-US"); }
  function sec(ms) { return (ms / 1000).toFixed(2) + " s"; }
  function byId(id) { for (var i = 0; i < Q.length; i++) if (Q[i].id === id) return Q[i]; return null; }

  var ENT = { quot: '"', amp: "&", lt: "<", gt: ">", nbsp: " ", apos: "'", "#39": "'" };
  function decode(s) { return s.replace(/&(quot|amp|lt|gt|nbsp|apos|#39);/g, function (m, k) { return ENT[k]; }).replace(/&#(\d+);/g, function (m, n) { return String.fromCharCode(+n); }); }
  /* Tidy wiki markup for reading. The record view can still show the text exactly as stored. */
  function dropStray(s, close, open) {
    for (var guard = 0; guard < 20; guard++) {
      var i = s.indexOf(close);
      if (i < 0 || (open && s.lastIndexOf(open, i) >= 0)) break;
      s = s.slice(i + close.length);
    }
    return s;
  }
  function clean(raw) {
    var s = decode(decode(raw));
    s = s.replace(/<math[^>]*>[\s\S]*?(<\/math>|$)/gi, " ");
    s = s.replace(/<ref[^>]*\/>/gi, "").replace(/<ref[^>]*>[\s\S]*?(<\/ref>|$)/gi, "");
    s = s.replace(/<!--[\s\S]*?(-->|$)/g, "");
    s = dropStray(s, "-->", "<!--");
    s = s.replace(/<[^>]+>/g, "").replace(/^[^<>\n]{0,120}(?:"|\/)\s*>/, "");
    for (var i = 0; i < 4; i++) s = s.replace(/\{\{[^{}]*\}\}/g, "");
    s = dropStray(s, "}}", "{{");
    s = s.replace(/\{\{[\s\S]*$/, "").replace(/\{\|[\s\S]*?(\|\}|$)/g, " ");
    s = s.replace(/\[\[(?:File|Image|Category):[^\]\[]*\]\]/gi, "");
    s = s.replace(/\[\[([^\]|\[]*)\|([^\]\[]*)\]\]/g, "$2");
    s = s.replace(/\[\[(?:File|Image|Category):[^\]\[]*\]\]/gi, "");
    s = s.replace(/\[\[([^\]\[]*)\]\]/g, "$1");
    s = dropStray(s, "]]", "[[");
    s = s.replace(/\[\[([^\]|\[]*)\|([^\]\[]*)$/, "$2").replace(/\[\[([^\]\[]*)$/, "$1");
    s = s.replace(/\[https?:\/\/\S+ ([^\]]*)\]/g, "$1").replace(/\[https?:\/\/\S+\]/g, "");
    s = s.replace(/'{2,}/g, "");
    s = s.replace(/^[ \t]*\|[^\n]*=[^\n]*$/gm, "").replace(/^.*\|\|.*$/gm, "").replace(/^:.*\\.*$/gm, "");
    s = s.replace(/^\s*((thumb|thumbnail|frameless|framed|right|left|center|none|upright(=[\d.]+)?|\d+x?\d*px|alt=[^|\n]*|link=[^|\n]*)\|)+/gim, "");
    s = s.replace(/\b(?:upright|link|thumbtime|class|style|width|height|colspan|rowspan|align|valign|scope|border)\s*=\s*(?:"[^"]*"|[^\s|]*)\s*\|?/gi, "").replace(/\balt=/gi, "");
    s = s.replace(/^\s*=+\s*(.*?)\s*=+\s*$/gm, "\n$1\n");
    s = s.replace(/^\s*[|!]-?\s*/gm, "").replace(/\s\|\s*/g, " ");
    s = s.replace(/^\s*[}\]]+\s*/, "").replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    return s.length < 25 ? "(Mostly markup or a table. Open the record to see it exactly as stored.)" : s;
  }
  function snippet(raw, n) {
    var s = clean(raw).replace(/\s+/g, " ");
    if (s.length <= n) return s;
    var cut = s.slice(0, n), sp = cut.lastIndexOf(" ");
    return (sp > n * 0.6 ? cut.slice(0, sp) : cut) + "…";
  }
  function wikiUrl(p) {
    var m = /^wikipedia:(\d+)$/.exec(p.d);
    if (m) return "https://en.wikipedia.org/?curid=" + m[1];
    return "https://en.wikipedia.org/wiki/" + encodeURIComponent((p.ti || "").replace(/ /g, "_"));
  }
  function partOf(p) { return (p.u === null || p.u === undefined) ? "" : " &middot; part " + (p.u + 1) + " of the article"; }
  function ordinalSuffix(n) { var v = n % 100; if (v >= 11 && v <= 13) return n + "th"; return n + ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"); }

  /* ---------- v5 guide: live caption + strip highlight. Every number comes from the replay data. ---------- */
  var capTimer = 0, capSeq = 0;
  var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function setCaption(t) { var c = $("captiontext"); if (c) c.textContent = t; }
  function setStep(n) {
    var items = document.querySelectorAll(".guide-steps li");
    for (var i = 0; i < items.length; i++) items[i].classList.toggle("active", items[i].getAttribute("data-step") === String(n));
  }
  function groupStats(q) {
    var gs = {}, ss = {};
    q.g.forEach(function (hit) { var p = P[hit[0]]; gs[p.pa] = 1; ss[p.sh] = 1; });
    return { g: Object.keys(gs).length, s: Object.keys(ss).length };
  }
  function sharedCount(q) {
    var fi = q.f.map(function (x) { return x[0]; });
    return q.g.map(function (x) { return x[0]; }).filter(function (o) { return fi.indexOf(o) >= 0; }).length;
  }
  function resultsCaption(q) {
    var st = groupStats(q);
    return "Only the groups that fit opened; the rest stayed closed. These 10 answers came from " + st.g + " groups across " + st.s + " of the 4 parts, and " + sharedCount(q) + " of 10 match exact search.";
  }
  function recordCaption(q, hit, rank) {
    var o = hit[0], p = P[o];
    return "Checking the record for result " + rank + ": the article \u201c" + (p.ti || p.d) + "\u201d, passage " + fmt(o) + " of " + fmt(TOTAL) + ". The fingerprint check runs in your own browser.";
  }
  /* Glossary tap-toggle (hover and keyboard focus are pure CSS). One delegated listener covers static and dynamic tips. */
  document.addEventListener("click", function (ev) {
    var g = ev.target && ev.target.closest ? ev.target.closest("dfn.g") : null;
    var pins = document.querySelectorAll("dfn.g.pin");
    for (var i = 0; i < pins.length; i++) if (pins[i] !== g) pins[i].classList.remove("pin");
    if (g) { g.classList.toggle("pin"); ev.stopPropagation(); }
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") { var pins = document.querySelectorAll("dfn.g.pin"); for (var i = 0; i < pins.length; i++) pins[i].classList.remove("pin"); }
  });

  /* ---------- question picker ---------- */
  function renderTabs() {
    var t = $("cattabs"); t.innerHTML = "";
    CATS.forEach(function (c) {
      var n = Q.filter(function (q) { return q.cat === c; }).length;
      if (!n) return;
      var b = document.createElement("button");
      b.type = "button"; b.setAttribute("aria-pressed", c === curCat ? "true" : "false");
      b.textContent = c + " (" + n + ")";
      b.addEventListener("click", function () { curCat = c; renderTabs(); renderChips(); });
      t.appendChild(b);
    });
  }
  function renderChips() {
    var ul = $("chips"); ul.innerHTML = "";
    Q.filter(function (q) { return q.cat === curCat; }).forEach(function (q) {
      var li = document.createElement("li"), b = document.createElement("button");
      b.type = "button"; b.textContent = q.q; b.dataset.id = q.id;
      if (cur && cur.id === q.id) b.setAttribute("aria-current", "true");
      b.addEventListener("click", function () { $("q").value = q.q; $("matchnote").hidden = true; show(q, { scroll: true }); });
      li.appendChild(b); ul.appendChild(li);
    });
  }

  /* ---------- typed question -> closest recorded question ---------- */
  var STOP = "a an the is are was were be been do does did how what why who when where which of to in on for and or by with from as at it its this that into than then there their they them can could would should will about have has had i you we me my your".split(" ");
  var STOPSET = {}; STOP.forEach(function (w) { STOPSET[w] = 1; });
  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.replace(/ies$/, "y");
    if (w.length > 4 && /(oes|ses|xes|ches|shes)$/.test(w)) return w.replace(/es$/, "");
    if (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) return w.slice(0, -1);
    if (w.length > 5 && /ing$/.test(w)) return w.slice(0, -3);
    if (w.length > 4 && /ed$/.test(w)) return w.slice(0, -2);
    return w;
  }
  function words(s) {
    var out = {}, n = 0;
    s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).forEach(function (w) {
      if (!w || STOPSET[w]) return;
      out[stem(w)] = 1; n++;
    });
    return out;
  }
  function score(a, b) {
    var ka = Object.keys(a), kb = Object.keys(b); if (!ka.length || !kb.length) return 0;
    var hit = 0; ka.forEach(function (k) { if (b[k]) hit++; });
    return hit / Math.sqrt(ka.length * kb.length);
  }
  Q.forEach(function (q) { q._w = words(q.q); });
  function closest(text) {
    var tw = words(text);
    return Q.map(function (q) { return { q: q, s: score(tw, q._w) }; }).sort(function (a, b) { return b.s - a.s; });
  }
  function onSubmit(ev) {
    ev.preventDefault();
    var text = $("q").value.trim(), note = $("matchnote");
    if (!text) { note.hidden = false; note.textContent = "Type a question, or pick one below."; return; }
    var r = closest(text), best = r[0];
    note.hidden = false; note.innerHTML = "";
    if (best.s >= 0.5) {
      note.innerHTML = "<b>No live search here.</b> Your words are closest to the recorded question <b>&ldquo;" + esc(best.q.q) + "&rdquo;</b>, so that is the replay shown.";
      show(best.q, { scroll: true, keepNote: true });
    } else {
      var html = "<b>No recorded question is a close match for &ldquo;" + esc(text) + "&rdquo;.</b> There is no live search behind this page, so we can only replay questions that were recorded. The nearest ones:<br>";
      note.innerHTML = html;
      r.slice(0, 4).forEach(function (x) {
        var b = document.createElement("button"); b.type = "button"; b.className = "linkish"; b.textContent = x.q.q;
        b.addEventListener("click", function () { $("q").value = x.q.q; note.hidden = true; show(x.q, { scroll: true }); });
        note.appendChild(b);
      });
    }
  }

  /* ---------- results ---------- */
  function inList(list, o) { for (var i = 0; i < list.length; i++) if (list[i][0] === o) return i + 1; return 0; }

  function renderCard(q, hit, idx) {
    var o = hit[0], p = P[o], rank = idx + 1, flatRank = inList(q.f, o);
    var li = document.createElement("li"); li.className = "card"; li.id = "r" + rank;
    var recId = "rec" + rank;
    li.innerHTML =
      '<div class="chead"><div class="rank"><span class="sr">Rank </span>' + rank + '</div><div>' +
      '<div class="ctitle">' + esc(p.ti || p.d) + '</div>' +
      '<div class="csub">English Wikipedia' + partOf(p) + ' &middot; <dfn class="g" tabindex="0">closeness<span class="tip" role="tooltip">How close this passage is in meaning to the question. Higher is closer.</span></dfn> ' + hit[1].toFixed(3) + '</div></div></div>' +
      '<p class="snippet">' + esc(snippet(p.tx, 300)) + '</p>' +
      '<div class="tags">' + (flatRank
        ? '<span class="tag same">Exact search also found it (its rank ' + flatRank + ')</span>'
        : '<span class="tag only">Only TRACE returned this one</span>') + '</div>' +
      '<button type="button" class="recbtn" aria-expanded="false" aria-controls="' + recId + '">See its checkable record</button>' +
      '<div class="record" id="' + recId + '" hidden></div>';
    var btn = li.querySelector(".recbtn");
    btn.addEventListener("click", function () { toggleRecord(li, q, hit, rank); });
    li.addEventListener("mouseenter", function () { markCompare(o, true); });
    li.addEventListener("mouseleave", function () { markCompare(o, false); });
    return li;
  }
  function markCompare(o, on) {
    var els = document.querySelectorAll('.cols li[data-o="' + o + '"]');
    for (var i = 0; i < els.length; i++) els[i].classList.toggle("hot", on);
  }

  function toggleRecord(li, q, hit, rank, forceOpen) {
    var box = li.querySelector(".record"), btn = li.querySelector(".recbtn");
    var open = forceOpen !== undefined ? forceOpen : box.hidden;
    if (open && !box.dataset.built) { buildRecord(box, q, hit, rank); box.dataset.built = "1"; }
    box.hidden = !open; btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.textContent = open ? "Hide the checkable record" : "See its checkable record";
    li.classList.toggle("open", open);
    capSeq++; clearTimeout(capTimer);
    if (open) { setStep(4); setCaption(recordCaption(q, hit, rank)); }
    else { setStep(3); setCaption(resultsCaption(q)); }
  }

  function buildRecord(box, q, hit, rank) {
    var o = hit[0], p = P[o], flatRank = inList(q.f, o);
    var url = wikiUrl(p);
    var span = p.c ? fmt(p.c[0]) + " to " + fmt(p.c[1]) : "unknown";
    var sent = p.s ? p.s[0] + " to " + p.s[1] : "unknown";
    var nth = (p.u === null || p.u === undefined) ? "" : " (the " + ordinalSuffix(p.u + 1) + " passage of this article)";
    box.innerHTML =
      '<h4>Checkable record for result ' + rank + '</h4>' +
      '<div class="where"><b>Where it came from:</b> the article &ldquo;' + esc(p.ti || p.d) + '&rdquo; on English Wikipedia, characters ' + span + nth + '.</div>' +
      '<dl class="facts">' +
      '<dt>Article ID</dt><dd><code>' + esc(p.d) + '</code></dd>' +
      '<dt>Passage number</dt><dd><code>' + fmt(o) + '</code> of ' + fmt(TOTAL) + ' in the library</dd>' +
      '<dt>Position in the article</dt><dd>Characters ' + span + '; sentences ' + sent + '</dd>' +
      '<dt>Licence</dt><dd>' + esc(p.lic || "unknown") + ' (Wikipedia text: reuse needs credit and the same licence)</dd>' +
      '<dt>Library part</dt><dd>Part ' + (p.sh + 1) + ' of 4, <dfn class="g" tabindex="0">group<span class="tip" role="tooltip">One pile of similar passages. The computer sorted them by itself.</span></dfn> ' + fmt(p.pa) + ' (TRACE scores only the passages inside the few best groups)</dd>' +
      '<dt>Closeness to the question</dt><dd>' + hit[1].toFixed(4) + ' (higher is closer in meaning)</dd>' +
      '<dt>Exact search also returned it</dt><dd>' + (flatRank ? 'Yes, at its rank ' + flatRank : 'No') + '</dd>' +
      '<dt>Fingerprint stored in the library</dt><dd><span class="hash mono">' + esc(p.h) + '</span><div class="fine">A fingerprint (SHA-256) is a short code worked out from the exact text. Change one letter and the code changes completely.</div></dd>' +
      '</dl>' +
      '<div class="actions"><button type="button" class="chk">Check the fingerprint in my browser</button>' +
      '<a href="' + esc(url) + '" target="_blank" rel="noopener">Open the Wikipedia article</a>' +
      '<button type="button" class="dl">Download this record</button></div>' +
      '<div class="verdict-slot" role="status" aria-live="polite"></div>' +
      '<p class="fine">A match shows that the raw text agrees with the fingerprint published alongside it. It does not prove Wikipedia says the same today: pages change, so the link may show newer wording.</p>' +
      '<h4>The full passage</h4><div class="fulltext" tabindex="0" role="region" aria-label="Full passage text"></div>' +
      '<div class="actions"><button type="button" class="rawbtn">Show the text exactly as stored</button></div>';
    var ft = box.querySelector(".fulltext"); ft.textContent = clean(p.tx);
    var raw = false;
    box.querySelector(".rawbtn").addEventListener("click", function (e) {
      raw = !raw; ft.textContent = raw ? p.tx : clean(p.tx); ft.classList.toggle("raw", raw);
      e.target.textContent = raw ? "Show the tidied text" : "Show the text exactly as stored";
    });
    box.querySelector(".chk").addEventListener("click", function () { checkHash(p, box.querySelector(".verdict-slot")); });
    box.querySelector(".dl").addEventListener("click", function () { download(q, hit, rank); });
  }

  function sha256hex(text) {
    if (!(window.crypto && crypto.subtle)) return Promise.reject(new Error("no-subtle"));
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (buf) {
      return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
    });
  }
  function checkHash(p, slot) {
    slot.innerHTML = '<div class="verdict">Checking&hellip;</div>';
    setCaption("Checking the fingerprint in your browser\u2026");
    sha256hex(p.tx).then(function (hex) {
      if (hex === p.h) { slot.innerHTML = '<div class="verdict pass">Match. Your browser worked out <span class="mono">' + hex.slice(0, 16) + '&hellip;</span> from the text on this page, and it equals the fingerprint the library stored.</div>'; setCaption("Match: the text on this page gives the same fingerprint the library stored."); }
      else { slot.innerHTML = '<div class="verdict fail">No match. The text here does not give the stored fingerprint.</div>'; setCaption("No match: the text here does not give the stored fingerprint."); }
    }, function () {
      slot.innerHTML = '<div class="verdict fail">This browser cannot work out fingerprints on this page (it needs https or localhost). The stored fingerprint is shown above.</div>';
      setCaption("This browser cannot work out fingerprints here. The stored fingerprint is shown above.");
    });
  }
  function download(q, hit, rank) {
    var o = hit[0], p = P[o];
    var rec = {
      note: "Checkable record exported from the TRACE Explorer replay. Recorded on the sealed corpus.",
      question: q.q, recorded_utc: q.t, rank: rank, closeness: hit[1],
      passage_number: o, article_id: p.d, article_title: p.ti, character_span: p.c, sentence_ids: p.s,
      passage_index_in_article: p.u, licence: p.lic, library_section: p.sh + 1, group: p.pa,
      exact_search_rank: inList(q.f, o) || null, fingerprint_sha256: p.h, text_as_stored: p.tx
    };
    var blob = new Blob([JSON.stringify(rec, null, 2)], { type: "application/json" });
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "trace-record-" + o + ".json"; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }

  /* ---------- comparison panel ---------- */
  function renderCompare(q) {
    var gi = q.g.map(function (x) { return x[0]; }), fi = q.f.map(function (x) { return x[0]; });
    var shared = gi.filter(function (o) { return fi.indexOf(o) >= 0; }).length;
    var same = shared === gi.length && gi.length === fi.length;
    var sameOrder = same && gi.every(function (o, i) { return o === fi[i]; });
    var n = gi.length;
    function col(title, list, other) {
      var h = '<div><h4>' + title + '</h4><ol>';
      list.forEach(function (o, i) {
        var p = P[o], miss = other.indexOf(o) < 0;
        h += '<li class="' + (miss ? "miss" : "") + '" data-o="' + o + '"><b>' + (i + 1) + '</b><span>' + esc(p.ti || p.d) + ((p.u === null || p.u === undefined) ? '' : ' <i>part ' + (p.u + 1) + '</i>') + (miss ? ' (only here)' : '') + '</span></li>';
      });
      return h + '</ol></div>';
    }
    var orderLine = sameOrder ? "Same order too."
      : (same ? "Same passages, in a slightly different order." : "Passages that appear in only one list are marked in amber.");
    var all = Q.reduce(function (a, x) {
      var g = x.g.map(function (y) { return y[0]; }), f = x.f.map(function (y) { return y[0]; });
      var sh = g.filter(function (o) { return f.indexOf(o) >= 0; }).length;
      a.n++; a.sum += sh; if (sh === g.length && g.length === f.length) a.all++;
      if (g.length === f.length && g.every(function (o, i) { return o === f[i]; })) a.ord++; return a;
    }, { n: 0, sum: 0, all: 0, ord: 0 });
    $("compare").innerHTML =
      '<h3><span class="n" aria-hidden="true">4</span> Same answer as exact search?</h3>' +
      '<div class="big ' + (same ? "" : "partial") + '">' + shared + ' of ' + n + ' <small>passages are the same</small></div>' +
      '<p>' + orderLine + ' We asked this question twice on the same library of ' + fmt(TOTAL) + ' passages: once with TRACE, which looks inside a small part of the library, and once with exact search, which checks every passage. Both lists are real recordings.</p>' +
      '<div class="cols">' + col("TRACE", gi, fi) + col("Exact search", fi, gi) + '</div>' +
      '<p class="legend">Green edge: also in the other list. Amber edge: only in this list.</p>' +
      '<p class="fine">Time the server took when we recorded: TRACE ' + sec(q.tg) + ', the server&rsquo;s scan-everything mode ' + sec(q.tf) + '. We make no speed claim: what TRACE aims to save is scoring work, not time in this demo.</p>' +
      '<div class="measured"><div class="bars" role="img" aria-label="Passages scored per search: exact search 100 percent, TRACE 0.79 percent"><div class="bar-row"><span>Exact search</span><i style="width:100%"></i><em>scores 100% of passages</em></div><div class="bar-row"><span>TRACE</span><i class="thin" style="width:max(0.79%,4px)"></i><em>scores 0.79% of passages on the measured library part</em></div></div><p><b>Our 50 test searches:</b> TRACE kept <b>0.9985</b> of exact search&rsquo;s results (1.0 would be identical) while scoring <b>0.79%</b> of passages on the measured library part, about <b>127 times</b> less scoring work; choosing and building groups are separate costs.</p>' +
      '<p class="fine">Across the ' + all.n + ' questions recorded on this page: ' + all.all + ' gave identical top-10 sets (' + all.ord + ' in exactly the same order), and on average ' + (all.sum / all.n).toFixed(2) + ' of 10 passages were shared. These are only the questions we chose to record, so treat this as an illustration. The 50-search test above is the measurement.</p></div>';
  }

  function renderWeakNote(q) {
    var el = $("weaknote"); if (!el) return;
    if (q.cat !== "Weaker matches") { el.hidden = true; return; }
    var gi = q.g.map(function (x) { return x[0]; }), fi = q.f.map(function (x) { return x[0]; });
    var same = gi.length === fi.length && gi.every(function (o, i) { return o === fi[i]; });
    el.hidden = false;
    el.innerHTML = "<b>This is one of the weaker matches.</b> The top passages here read less well as an answer. " +
      (same ? "Exact search returned exactly the same list, so the weakness comes from how meaning is scored, not from TRACE&rsquo;s shortcut. "
            : "Compare the lists in step 4. ") +
      "We kept it in on purpose.";
  }

  /* ---------- show a question ---------- */
  function show(q, opt) {
    opt = opt || {};
    cur = q;
    if (!opt.keepNote) { /* leave note as set by caller */ }
    $("qtitle").textContent = "“" + q.q + "”";
    var list = $("list"); list.innerHTML = "";
    q.g.forEach(function (hit, i) { list.appendChild(renderCard(q, hit, i)); });
    renderCompare(q);
    renderWeakNote(q);
    renderChips();
    try { history.replaceState(null, "", "#q=" + q.id); } catch (e) { /* file:// may refuse */ }
    (function () {
      var my = ++capSeq; clearTimeout(capTimer);
      setStep(1); setCaption("You asked: \u201c" + q.q + "\u201d");
      if (REDUCED) { setStep(3); setCaption(resultsCaption(q)); }
      else capTimer = setTimeout(function () { if (my !== capSeq) return; setStep(3); setCaption(resultsCaption(q)); }, 1100);
    })();
    if (opt.scroll) $("results").scrollIntoView({ behavior: "smooth", block: "start" });
    if (opt.open) {
      var idx = Math.max(1, Math.min(q.g.length, +opt.open || 1));
      var li = $("r" + idx); toggleRecord(li, q, q.g[idx - 1], idx, true);
      if (opt.scroll !== false && opt.focusOpen) li.scrollIntoView({ block: "start" });
    }
  }

  /* ---------- start ---------- */
  function hashParams() {
    var h = (location.hash || "").replace(/^#/, ""), out = {};
    h.split("&").forEach(function (kv) { var a = kv.split("="); if (a[0]) out[a[0]] = decodeURIComponent(a[1] || ""); });
    return out;
  }
  function start() {
    var hp = hashParams();
    var q = (hp.q && byId(hp.q)) || byId("why-is-the-sky-blue") || Q[0];
    curCat = q.cat || CATS[0];
    renderTabs();
    $("askform").addEventListener("submit", onSubmit);
    $("jumpcmp").addEventListener("click", function () {
      capSeq++; clearTimeout(capTimer);
      setCaption(sharedCount(cur) + " of 10 passages are the same as exact search. Both lists are real recordings of this question.");
    });
    show(q, { open: hp.open ? +hp.open : 0, focusOpen: !!hp.open });
    if (hp.view === "compare") setTimeout(function () { $("compare").scrollIntoView({ block: "start" }); }, 50);
    var n = Q.length, m = R.meta || {};
    $("recmeta").innerHTML = "<b>" + n + " questions</b> were asked one at a time on " + esc(m.recorded_date || "2026-11-04") + ", each twice (TRACE, then exact search), returning the top 10 passages each time. Each answer is stored as it came back, with its timings.";
    window.addEventListener("hashchange", function () {
      var p = hashParams(); var nq = p.q && byId(p.q);
      if (nq && nq !== cur) { $("q").value = nq.q; show(nq, { open: p.open ? +p.open : 0 }); }
      else if (nq && p.open) { var ix = Math.max(1, Math.min(nq.g.length, +p.open || 1)); toggleRecord($("r" + ix), nq, nq.g[ix - 1], ix, true); $("r" + ix).scrollIntoView({ block: "start" }); }
    });
  }
  start();
})();
