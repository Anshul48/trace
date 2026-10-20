/* TRACE play/ — client-only queries over recorded exports. Vanilla, zero deps. */
(function () {
  "use strict";
  var sliceURL = "../explorer/local_20k_data.json";
  var q = document.getElementById("q");
  var qStatus = document.getElementById("q-status");
  var hits = document.getElementById("hits");
  var probeStatus = document.getElementById("probe-status");
  var probeBody = document.querySelector("#probes tbody");
  var atoms = [];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderHits(list, total) {
    hits.innerHTML = "";
    if (!list.length) {
      qStatus.textContent = total + " recorded atoms searched, no matches. Slice only — not the 10M index.";
      return;
    }
    qStatus.textContent = list.length + " of " + total + " recorded atoms match (top 20 shown). Recorded slice, not the 10M index.";
    list.slice(0, 20).forEach(function (a) {
      var li = document.createElement("li");
      var title = a.title || "(untitled atom " + String(a.id).slice(0, 8) + ")";
      var snip = (a.snippet || "").slice(0, 220);
      li.innerHTML = '<div class="t">' + esc(title) + '</div>' +
        '<div class="s">' + esc(snip) + (a.snippet && a.snippet.length > 220 ? "…" : "") + "</div>" +
        '<div class="s">doc ' + esc(a.doc_id || "?") + " · parents: " + esc((a.leaf_ids || []).join(", ")) + "</div>";
      hits.appendChild(li);
    });
  }

  fetch(sliceURL).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (data) {
    atoms = data.atoms || [];
    qStatus.textContent = atoms.length + " recorded atoms loaded (20K slice). Type to search titles + snippets.";
    // Per-probe recorded outcomes: group evaluation_queries by probe.
    var byProbe = {};
    (data.evaluation_queries || []).forEach(function (row) {
      var p = byProbe[row.probe] || (byProbe[row.probe] = { family: row.family, all: null, lso: null });
      var cell = "guided " + row.guided_recall10 + " / flat " + row.flat_recall10;
      if (row.leave_source_out) p.lso = cell; else p.all = cell;
    });
    var ids = Object.keys(byProbe).map(Number).sort(function (a, b) { return a - b; });
    probeBody.innerHTML = "";
    ids.forEach(function (id) {
      var p = byProbe[id];
      var tr = document.createElement("tr");
      tr.innerHTML = "<td>" + id + "</td><td>" + esc(p.family || "?") + "</td><td>" +
        esc(p.all || "—") + "</td><td>" + esc(p.lso || "—") + "</td>";
      probeBody.appendChild(tr);
    });
    probeStatus.textContent = ids.length + " probes, recorded numbers (guided vs flat, matched work).";
  }).catch(function (e) {
    qStatus.textContent = "Could not load the recorded slice (" + e.message + "). Open explorer/local_20k_data.json directly.";
    probeStatus.textContent = "Probe rows unavailable offline of the slice file; see explorer/probes_summary.json.";
  });

  var t = null;
  q.addEventListener("input", function () {
    clearTimeout(t);
    t = setTimeout(function () {
      var needle = q.value.trim().toLowerCase();
      if (!needle) { hits.innerHTML = ""; qStatus.textContent = atoms.length + " recorded atoms loaded. Type to search."; return; }
      var out = atoms.filter(function (a) {
        return ((a.title || "") + " " + (a.snippet || "")).toLowerCase().indexOf(needle) !== -1;
      });
      renderHits(out, atoms.length);
    }, 120);
  });

  // 10M opt-in with progress + cancel.
  var btn = document.getElementById("load10m");
  var cancel = document.getElementById("cancel10m");
  var bar = document.getElementById("dl10m");
  var st = document.getElementById("m10m-status");
  var ctrl = null;
  btn.addEventListener("click", function () {
    if (!("DecompressionStream" in window)) {
      st.textContent = "This browser cannot gunzip in-page (no DecompressionStream). Grab graph_10m.json directly from the explorer folder.";
      return;
    }
    ctrl = new AbortController();
    btn.disabled = true; cancel.disabled = false; bar.hidden = false; bar.value = 0;
    st.textContent = "Downloading graph_10m.json.gz (7.25 MB)…";
    fetch("../explorer/graph_10m.json.gz", { signal: ctrl.signal }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      var total = +(r.headers.get("content-length") || 7254185);
      var reader = r.body.getReader();
      var chunks = [];
      var seen = 0;
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
      st.textContent = "Decompressing 21.7 MB locally…";
      var ds = new DecompressionStream("gzip");
      return new Response(blob.stream().pipeThrough(ds)).json();
    }).then(function (g) {
      var np = (g.parents && g.parents.length) || 0;
      var nl = (g.leaves && g.leaves.length) || 0;
      var na = (g.atoms && g.atoms.length) || 0;
      st.textContent = "Loaded locally: " + np + " parents / " + nl + " leaves / " + na + " atoms. Recorded freeze — explore topology in the explorer tour.";
      bar.value = 100;
    }).catch(function (e) {
      st.textContent = (e && e.name === "AbortError") ? "Cancelled — nothing kept." : "Load failed (" + (e && e.message) + "). The raw file is still at explorer/graph_10m.json.";
    }).finally(function () {
      btn.disabled = false; cancel.disabled = true; ctrl = null;
    });
  });
  cancel.addEventListener("click", function () { if (ctrl) ctrl.abort(); });
})();
