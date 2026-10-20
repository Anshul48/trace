/* R3 always-on visuals. Identical file in trace + anima (docs/assets/always.js).
   Widgets activate by data-attribute; absent widget = inert. No deps,
   no console output on success, reduced-motion safe throughout. */
(function () {
  'use strict';

  function reduced() {
    return !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function onVisible(el, fn) {
    if (!('IntersectionObserver' in window)) { fn(); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { io.unobserve(el); fn(); }
      });
    }, { threshold: 0.25 });
    io.observe(el);
  }

  /* Ticker: duplicate track for a seamless -50% loop (RM: static). */
  function tickers() {
    if (reduced()) return;
    document.querySelectorAll('[data-ticker]').forEach(function (t) {
      if (t.dataset.done) return;
      t.dataset.done = '1';
      t.innerHTML += t.innerHTML;
      t.classList.add('live');
    });
  }

  /* Typed: full text already in DOM; retype on scroll-in (RM: keep text). */
  function typed() {
    document.querySelectorAll('[data-typed]').forEach(function (pre) {
      if (pre.dataset.done) return;
      pre.dataset.done = '1';
      if (reduced()) return;
      var full = pre.textContent;
      onVisible(pre, function () {
        var i = 0;
        pre.textContent = '';
        var caret = document.createElement('span');
        caret.className = 'caret';
        pre.appendChild(caret);
        var timer = setInterval(function () {
          i += 3;
          pre.textContent = full.slice(0, i);
          pre.appendChild(caret);
          if (i >= full.length) { clearInterval(timer); pre.textContent = full; }
        }, 24);
      });
    });
  }

  /* Constellation: click/hover a node -> detail line (markup carries status). */
  function constel() {
    document.querySelectorAll('[data-constel]').forEach(function (svg) {
      var out = document.querySelector(svg.getAttribute('data-constel'));
      if (!out) return;
      svg.querySelectorAll('.node').forEach(function (n) {
        function show() {
          out.innerHTML = '';
          var b = document.createElement('strong');
          b.textContent = n.getAttribute('data-name') + ' — ' +
            n.getAttribute('data-status');
          out.appendChild(b);
          out.appendChild(document.createTextNode(
            ' · ' + n.getAttribute('data-detail')));
        }
        n.addEventListener('click', show);
        n.addEventListener('mouseenter', show);
      });
    });
  }

  /* Step sequence: auto-advance .on while visible (RM: all on, no timer). */
  function stepseq() {
    document.querySelectorAll('[data-stepseq]').forEach(function (seq) {
      var steps = seq.querySelectorAll('[data-step]');
      if (!steps.length) return;
      if (reduced()) {
        steps.forEach(function (s) { s.classList.add('on'); });
        return;
      }
      var i = 0, timer = null;
      function show(n) {
        steps.forEach(function (s, k) { s.classList.toggle('on', k <= n); });
      }
      show(0);
      onVisible(seq, function () {
        timer = setInterval(function () {
          i = (i + 1) % steps.length;
          show(i);
        }, 2400);
      });
      if ('IntersectionObserver' in window) {
        new IntersectionObserver(function (entries) {
          entries.forEach(function (en) {
            if (!en.isIntersecting && timer) {
              clearInterval(timer);
              timer = null;
              i = 0;
              show(steps.length - 1);
            }
          });
        }).observe(seq);
      }
    });
  }

  /* Parallax: gentle backdrop drift (RM: off). */
  function parallax() {
    if (reduced()) return;
    var els = document.querySelectorAll('[data-parallax]');
    if (!els.length) return;
    var ticking = false;
    function update() {
      ticking = false;
      els.forEach(function (el) {
        var r = el.getBoundingClientRect();
        var off = Math.max(-1, Math.min(1,
          (r.top + r.height / 2 - window.innerHeight / 2) / window.innerHeight));
        el.style.transform = 'translateY(' + (off * 22).toFixed(1) + 'px)';
      });
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* sha-verify: hash a staged file, compare to provenance manifest. Real. */
  function verifies() {
    document.querySelectorAll('[data-verify]').forEach(function (btn) {
      if (btn.dataset.done) return;
      btn.dataset.done = '1';
      btn.addEventListener('click', function () {
        var out = document.querySelector(btn.getAttribute('data-verify'));
        var manUrl = btn.getAttribute('data-manifest');
        var fileKey = btn.getAttribute('data-key');
        var fileUrl = btn.getAttribute('data-file');
        if (!out) return;
        out.className = 'verify-out';
        out.textContent = 'hashing…';
        function fail(msg) {
          out.className = 'verify-out bad';
          out.textContent = 'NOT VERIFIED: ' + msg;
        }
        if (!window.crypto || !window.crypto.subtle) {
          fail('SubtleCrypto unavailable (needs https or localhost)');
          return;
        }
        Promise.all([
          fetch(manUrl).then(function (r) {
            if (!r.ok) throw new Error('manifest HTTP ' + r.status);
            return r.json();
          }),
          fetch(fileUrl).then(function (r) {
            if (!r.ok) throw new Error('file HTTP ' + r.status);
            return r.arrayBuffer();
          })
        ]).then(function (pair) {
          var want = pair[0] && pair[0].files && pair[0].files[fileKey] &&
            pair[0].files[fileKey].sha256;
          if (!want) { fail('no pin for ' + fileKey); return; }
          window.crypto.subtle.digest('SHA-256', pair[1]).then(function (h) {
            var got = Array.prototype.map.call(new Uint8Array(h), function (b) {
              return ('0' + b.toString(16)).slice(-2);
            }).join('');
            if (got === want) {
              out.className = 'verify-out ok';
              out.textContent = 'MATCHES ' + want.slice(0, 12) + '… (' +
                pair[1].byteLength + ' bytes hashed in your browser)';
            } else {
              fail('digest mismatch for ' + fileKey);
            }
          }, function () { fail('digest error'); });
        }).catch(function (e) { fail(e.message); });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    tickers();
    typed();
    constel();
    stepseq();
    parallax();
    verifies();
  });
})();
