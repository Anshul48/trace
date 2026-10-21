/* R4 /play galaxy: 120 real probe comets over the real 3,711-parent field.
   Data: play/dag-skeleton.json (real parents + representative neighborhoods)
   + explorer/qualification_10m.json (240 REAL per-probe rows; aggregates are
   computed in-browser from those rows, never hardcoded as the source).
   Two controls only: Replay + Guided/Flat toggle. Reduced-motion renders one
   static final frame. #p=N deep link spotlights one probe (film OG promise).
   No text is drawn on canvas; all numbers live in the DOM caption. */
(function () {
  'use strict';

  function reduced() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var cv = document.getElementById('galaxy');
    if (!cv) return;
    var cap = document.getElementById('galaxy-cap');
    var agg = document.getElementById('galaxy-agg');
    var replayBtn = document.getElementById('galaxy-replay');
    var modeBtns = document.querySelectorAll('[data-mode]');
    var ctx = cv.getContext('2d');
    var W = cv.width, H = cv.height;
    var mode = 'guided'; // or 'flat'

    function X(x) { return x * W; }
    function Y(y) { return y * H; }

    function hashP() {
      var m = /[?#&]p=(\d{1,3})/.exec(window.location.hash || '');
      if (!m) return -1;
      var n = parseInt(m[1], 10);
      return (n >= 0 && n < 120) ? n : -1;
    }

    function getJSON(url) {
      return fetch(url).then(function (r) {
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      });
    }

    function finish(ids) {
      // ids: [{pts:[[x,y]..], hit:bool}] in probe order
      var D = 9000; // full flight, ms
      var PER = 1400; // per-comet travel, ms
      var STAG = (D - PER) / 119;
      var FIELD = 'rgba(157,184,221,0.55)';
      var HIT = { guided: '#4da3ff', flat: '#c8d4e6' };
      var MISS = '#e5484d';
      var field = ids.field;

      function drawField() {
        ctx.fillStyle = FIELD;
        for (var i = 0; i < field.length; i++) {
          ctx.fillRect(field[i][0], field[i][1], 1.7, 1.7);
        }
      }

      function cometPos(pts, f) {
        var segs = pts.length - 1;
        var upto = Math.min(Math.max(f, 0), 1) * segs;
        var s = Math.min(Math.floor(upto), segs - 1), fr = upto - s;
        return [pts[s][0] + (pts[s + 1][0] - pts[s][0]) * fr,
                pts[s][1] + (pts[s + 1][1] - pts[s][1]) * fr];
      }

      function drawTrail(pts, f, color) {
        if (pts.length < 2 || f <= 0) return;
        var head = cometPos(pts, f);
        var tail = cometPos(pts, f - 0.28);
        var g = ctx.createLinearGradient(tail[0], tail[1], head[0], head[1]);
        g.addColorStop(0, 'rgba(0,0,0,0)');
        g.addColorStop(1, color);
        ctx.strokeStyle = g;
        ctx.lineWidth = 2.2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tail[0], tail[1]);
        // walk the travelled sub-path for curved trails
        var segs = pts.length - 1;
        var upto = Math.min(f, 1) * segs;
        var from = Math.max(upto - 0.28 * segs, 0);
        var steps = 8;
        for (var k = 1; k <= steps; k++) {
          var u = from + (upto - from) * k / steps;
          var s = Math.min(Math.floor(u), segs - 1), fr = u - s;
          ctx.lineTo(pts[s][0] + (pts[s + 1][0] - pts[s][0]) * fr,
                     pts[s][1] + (pts[s + 1][1] - pts[s][1]) * fr);
        }
        ctx.stroke();
        if (f >= 1 && pts.length > 2) {
          // settled: faint full-path glow so the final frame stays luminous
          ctx.globalAlpha = 0.3;
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (var q = 1; q < pts.length; q++) ctx.lineTo(pts[q][0], pts[q][1]);
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(head[0], head[1], 3.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineCap = 'butt';
      }

      function drawSettled(colorOf) {
        drawField();
        ids.comets.forEach(function (c) {
          drawTrail(c.pts, 1, colorOf(c));
        });
      }

      function colorOf(c) { return c.hit[mode] ? HIT[mode] : MISS; }

      function setAgg(frac) {
        // Counting aggregate climbs with the flight; exact at rest.
        var t = ids.totals[mode];
        var v = t * Math.min(frac, 1);
        agg.textContent = (mode === 'guided' ? 'guided ' : 'flat ') + v.toFixed(2);
      }

      function setCaption() {
        var t = ids.totals;
        var sp = hashP();
        var base = mode === 'guided'
          ? 'probe-vector guided recall@10 ' + t.guided.toFixed(4) + ' vs flat ' + t.flat.toFixed(4) +
            ' (120 probes; staged explorer run, harness 9f516288; matched work)'
          : 'flat baseline recall@10 ' + t.flat.toFixed(4) + ' vs guided ' + t.guided.toFixed(4) +
            ' (120 probes; staged explorer run, harness 9f516288; matched work)';
        if (sp >= 0 && ids.rows[sp]) {
          var r = ids.rows[sp];
          base += ' · probe ' + sp + ' (' + r.family + '): guided ' +
            Number(r.guided_recall10).toFixed(1) + ' / flat ' +
            Number(r.flat_recall10).toFixed(1);
        }
        cap.textContent = base;
      }

      function spotlight() {
        var sp = hashP();
        if (sp < 0 || !ids.comets[sp]) return;
        var c = ids.comets[sp];
        var head = cometPos(c.pts, 1);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(head[0], head[1], 9, 0, Math.PI * 2);
        ctx.stroke();
      }

      var raf = null, t0 = null;
      function frame(ts) {
        if (t0 === null) t0 = ts;
        var el = ts - t0;
        ctx.fillStyle = '#0b1020';
        ctx.fillRect(0, 0, W, H);
        drawField();
        for (var i = 0; i < 120; i++) {
          var c = ids.comets[i];
          var f = (el - i * STAG) / PER;
          if (f > 0) drawTrail(c.pts, Math.min(f, 1), colorOf(c));
        }
        setAgg(el / D);
        if (el < D + 600) {
          raf = requestAnimationFrame(frame);
        } else {
          setAgg(1);
          setCaption();
          spotlight();
          raf = null;
        }
      }

      function play() {
        if (raf !== null) cancelAnimationFrame(raf);
        raf = null; t0 = null;
        // live region: announce the final numbers once they land
        raf = requestAnimationFrame(frame);
      }

      if (reduced()) {
        ctx.fillStyle = '#0b1020';
        ctx.fillRect(0, 0, W, H);
        drawSettled(colorOf);
        spotlight();
        setAgg(1);
        setCaption();
        if (replayBtn) replayBtn.disabled = true;
      } else {
        play();
      }

      if (replayBtn) replayBtn.addEventListener('click', function () {
        if (!reduced()) play();
      });
      modeBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          var m = b.getAttribute('data-mode');
          if (m !== 'guided' && m !== 'flat') return;
          mode = m;
          modeBtns.forEach(function (o) {
            o.setAttribute('aria-pressed', o === b ? 'true' : 'false');
          });
          if (reduced()) {
            ctx.fillStyle = '#0b1020';
            ctx.fillRect(0, 0, W, H);
            drawSettled(colorOf);
            spotlight();
            setAgg(1);
            setCaption();
          } else {
            play();
          }
        });
      });
      window.addEventListener('hashchange', function () {
        if (raf === null) {
          ctx.fillStyle = '#0b1020';
          ctx.fillRect(0, 0, W, H);
          drawSettled(colorOf);
          spotlight();
        }
        setCaption();
      });
    }

    function fail() {
      // Data failed: say so in-DOM with the staged numbers (same bytes,
      // labeled), never a blank canvas, never a console error.
      ctx.fillStyle = '#0b1020';
      ctx.fillRect(0, 0, W, H);
      agg.textContent = 'guided 0.73';
      cap.textContent = 'Galaxy data could not load — staged aggregates: ' +
        'probe-vector guided recall@10 0.73 vs flat 0.0558 ' +
        '(120 probes; staged explorer run, harness 9f516288). ' +
        'Open the explorer for the full data.';
      if (replayBtn) replayBtn.disabled = true;
    }

    Promise.all([getJSON('dag-skeleton.json'),
                 getJSON('../explorer/qualification_10m.json')]).then(function (pair) {
      var sk = pair[0], qual = pair[1];
      var field = sk.parents.map(function (p) { return [X(p[1]), Y(p[2])]; });
      var leafXY = {}, atomXY = {};
      sk.leaves.forEach(function (L) { leafXY[L[0]] = [X(L[1]), Y(L[2])]; });
      sk.atoms.forEach(function (a) { atomXY[a[0]] = [X(a[1]), Y(a[2])]; });
      var rows = {};
      (qual.queries || []).forEach(function (q) {
        if (!q.leave_source_out) rows[q.probe] = q;
      });
      var comets = [], gs = 0, fs = 0, n = 0;
      for (var p = 0; p < 120; p++) {
        var pp = sk.probe_paths[String(p)], pts = [];
        if (pp) {
          var rt = sk.parents[pp.root];
          if (rt) pts.push([X(rt[1]), Y(rt[2])]);
          (pp.leaves || []).forEach(function (id) {
            if (leafXY[id]) pts.push(leafXY[id]);
          });
          (pp.atoms || []).forEach(function (id) {
            if (atomXY[id]) pts.push(atomXY[id]);
          });
        }
        if (pts.length < 2 && rt) pts.push([X(rt[1]) + 8, Y(rt[2]) + 8]);
        var r = rows[p] || { guided_recall10: 0, flat_recall10: 0, family: '?' };
        comets.push({ pts: pts, hit: {
          guided: Number(r.guided_recall10) > 0,
          flat: Number(r.flat_recall10) > 0
        }});
        gs += Number(r.guided_recall10) || 0;
        fs += Number(r.flat_recall10) || 0;
        n++;
      }
      finish({ field: field, comets: comets, rows: rows,
               totals: { guided: gs / n, flat: fs / n } });
    }).catch(fail);
  });
})();
