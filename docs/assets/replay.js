/* R3 live probe replay (trace docs/assets/replay.js). Auto-loops real probe
   paths from play/dag-skeleton.json on a canvas: probes 7, 83, 78 in turn.
   In-viewport only; reduced-motion shows one static frame; fetch failure
   hides the figure (never breaks the page, never logs). No text on canvas:
   the caption line (DOM) carries the numbers, pinned to staged rows:
   qual#queries probe 7 chunk/all 0.4/0.0; probe 83 cross/LSO 0.0/0.2
   (flat-wins); probe 78 noisy/all 0.0/0.0 (clean miss). */
(function () {
  'use strict';

  function reduced() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function cssVar(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var cv = document.querySelector('[data-replay]');
    if (!cv) return;
    var cap = document.querySelector(cv.getAttribute('data-replay'));
    var fig = cv.closest('figure');
    var ctx = cv.getContext('2d');
    var W = cv.width, H = cv.height;

    var PROBES = [
      { p: 7, note: 'probe 7 (chunk, all-sources): guided 0.4 / flat 0.0 · 3,809 rows each' },
      { p: 83, note: 'probe 83 (cross, leave-source-out): guided 0.0 / flat 0.2 — flat wins' },
      { p: 78, note: 'probe 78 (noisy, all-sources): guided 0.0 / flat 0.0 — a clean miss' }
    ];
    var SLOT = 7000;

    fetch(cv.getAttribute('data-src')).then(function (r) {
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    }).then(function (sk) {
      var leafXY = {}, atomXY = {}, i;
      sk.leaves.forEach(function (L) { leafXY[L[0]] = [L[1], L[2]]; });
      sk.atoms.forEach(function (a) { atomXY[a[0]] = [a[1], a[2]]; });
      function X(x) { return x * W; }
      function Y(y) { return y * H; }
      var field = sk.parents.map(function (p) { return [X(p[1]), Y(p[2])]; });
      var paths = PROBES.map(function (pr) {
        var pp = sk.probe_paths[String(pr.p)], pts = [];
        if (pp) {
          var rt = sk.parents[pp.root];
          if (rt) pts.push([X(rt[1]), Y(rt[2])]);
          (pp.leaves || []).forEach(function (id) {
            if (leafXY[id]) pts.push([X(leafXY[id][0]), Y(leafXY[id][1])]);
          });
          (pp.atoms || []).forEach(function (id) {
            if (atomXY[id]) pts.push([X(atomXY[id][0]), Y(atomXY[id][1])]);
          });
        }
        return pts;
      });

      var acc = cssVar('--accent', '#0b5cad');
      var mut = cssVar('--muted', '#8b949e');
      var missC = '#b3261e';

      function drawField(alpha) {
        ctx.fillStyle = mut;
        ctx.globalAlpha = alpha;
        for (i = 0; i < field.length; i += 2) {
          ctx.fillRect(field[i][0], field[i][1], 1.6, 1.6);
        }
        ctx.globalAlpha = 1;
      }

      function drawPath(pts, frac, color) {
        if (pts.length < 2) return;
        var segs = pts.length - 1, upto = frac * segs;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (var s = 0; s < segs; s++) {
          if (upto >= s + 1) ctx.lineTo(pts[s + 1][0], pts[s + 1][1]);
          else if (upto > s) {
            var f = upto - s;
            ctx.lineTo(pts[s][0] + (pts[s + 1][0] - pts[s][0]) * f,
              pts[s][1] + (pts[s + 1][1] - pts[s][1]) * f);
            break;
          } else break;
        }
        ctx.stroke();
        ctx.lineCap = 'butt';
      }

      function headAt(pts, frac) {
        var segs = pts.length - 1;
        var upto = Math.min(frac, 1) * segs;
        var s = Math.min(Math.floor(upto), segs - 1), f = upto - s;
        return [pts[s][0] + (pts[s + 1][0] - pts[s][0]) * f,
          pts[s][1] + (pts[s + 1][1] - pts[s][1]) * f];
      }

      function frame(now) {
        var slot = Math.floor(now / SLOT) % PROBES.length;
        var f = (now % SLOT) / SLOT;
        var pts = paths[slot];
        var color = (slot === 0) ? acc : (slot === 1 ? mut : missC);
        var travel = Math.min(f / 0.6, 1);
        ctx.clearRect(0, 0, W, H);
        drawField(0.45);
        drawPath(pts, travel, color);
        if (pts.length > 1) {
          var hd = headAt(pts, travel);
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(hd[0], hd[1], 4, 0, Math.PI * 2);
          ctx.fill();
        }
        if (cap && cap.dataset.slot !== String(slot)) {
          cap.dataset.slot = String(slot);
          cap.textContent = PROBES[slot].note + ' · staged explorer run';
        }
      }

      if (reduced()) {
        // One static frame: probe 7 fully lit, caption pinned.
        ctx.clearRect(0, 0, W, H);
        drawField(0.45);
        drawPath(paths[0], 1, acc);
        if (cap) cap.textContent = PROBES[0].note + ' · staged explorer run (static: reduced motion)';
        return;
      }
      var raf = null, t0 = null;
      function loop(ts) {
        if (t0 === null) t0 = ts;
        frame(ts - t0);
        raf = requestAnimationFrame(loop);
      }
      if ('IntersectionObserver' in window) {
        new IntersectionObserver(function (entries) {
          entries.forEach(function (en) {
            if (en.isIntersecting && raf === null) {
              raf = requestAnimationFrame(loop);
            } else if (!en.isIntersecting && raf !== null) {
              cancelAnimationFrame(raf);
              raf = null;
            }
          });
        }, { threshold: 0.2 }).observe(cv);
      } else {
        raf = requestAnimationFrame(loop);
      }
    }).catch(function () {
      if (fig) fig.style.display = 'none';
    });
  });
})();
