/* SPDX-License-Identifier: Apache-2.0
 * Small shared behaviour for the TRACE and ANIMA sites. No libraries, no tracking.
 *  - menu button (narrow screens)
 *  - theme button: Dark <-> Light, remembered in localStorage (inside try/catch)
 *  - status badges: elements with data-status-id take their word and colour from status.json
 *  - films: elements with data-films render cards from demos/films.json (the single swap list)
 */
(function () {
  "use strict";
  var root = (function () {
    var s = document.querySelector('script[src$="assets/site.js"]');
    return s ? s.getAttribute("src").replace(/assets\/site\.js$/, "") : "";
  })();
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }

  /* ---- menu ---- */
  var menu = $(".menu-btn"), nav = $("#site-nav");
  if (menu && nav) {
    menu.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      menu.setAttribute("aria-expanded", String(open));
      menu.textContent = open ? "Close" : "Menu";
    });
    nav.addEventListener("click", function (e) { if (e.target.tagName === "A" && nav.classList.contains("open")) { nav.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); menu.textContent = "Menu"; } });
  }

  /* ---- theme: light is the default; the button flips Dark <-> Light ---- */
  var tbtn = $("[data-theme-toggle]");
  function currentPref() { return store("trace-theme") === "dark" ? "dark" : "light"; }
  function applyPref(p) {
    document.documentElement.setAttribute("data-theme", p);
    if (tbtn) {
      var other = p === "dark" ? "Light" : "Dark";
      tbtn.textContent = other;
      tbtn.setAttribute("aria-label", "Switch to " + other + " mode. Current mode: " + p + ".");
    }
  }
  if (tbtn) {
    applyPref(currentPref());
    tbtn.addEventListener("click", function () {
      var next = currentPref() === "dark" ? "light" : "dark";
      store("trace-theme", next); applyPref(next);
    });
  }

  /* ---- status badges from status.json ---- */
  var badgeEls = $$("[data-status-id]");
  var cls = { built: "badge-built", prototype: "badge-proto", next: "badge-next" };
  var statusP = null;
  function loadStatus() {
    if (!statusP) statusP = fetch(root + "status.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    return statusP;
  }
  if (badgeEls.length && window.fetch) {
    loadStatus().then(function (st) {
      badgeEls.forEach(function (el) {
        var cap = (st.capabilities || []).filter(function (c) { return c.id === el.getAttribute("data-status-id"); })[0];
        if (!cap || !cls[cap.status]) return;
        el.className = "badge " + cls[cap.status];
        el.textContent = cap.badge_text || st.labels[cap.status];
      });
    }).catch(function () { /* the build already wrote the same words into the page */ });
  }

  /* ---- films ---- */
  function fmtMeta(f) {
    var bits = [];
    if (f.project) bits.push(f.project.toUpperCase());
    if (f.length) bits.push(f.length);
    if (f.role === "working-version") bits.push("working version");
    return bits;
  }
  function cueText(vtt) {
    var out = [], blocks = vtt.replace(/\r/g, "").split(/\n\n+/);
    blocks.forEach(function (b) {
      var lines = b.split("\n").filter(function (l) { return l && l.indexOf("-->") < 0 && !/^\d+$/.test(l) && l.indexOf("WEBVTT") !== 0; });
      if (lines.length) out.push(lines.join(" "));
    });
    return out.join(" ");
  }
  function frame(f) {
    var base = root + "demos/";
    if (f.file) {
      return '<div class="film-frame"><video controls preload="none" playsinline' + (f.poster ? ' poster="' + esc(base + f.poster) + '"' : "") + ' aria-label="' + esc(f.title) + '">' +
        '<source src="' + esc(base + f.file) + '" type="video/mp4">' +
        (f.captions ? '<track kind="captions" srclang="en" label="English" src="' + esc(base + f.captions) + '" default>' : "") +
        '<p>Your browser cannot play this video. <a href="' + esc(base + f.file) + '">Download the file</a>.</p></video></div>';
    }
    if (f.youtube) {
      return '<div class="film-frame">' + (f.poster ? '<img src="' + esc(base + f.poster) + '" alt="">' : "") + '</div>';
    }
    if (f.fallback_href) {
      return '<div class="film-frame"><div class="placeholder"><strong>' + esc(f.title) + '</strong><span>' + esc(f.fallback_label || "Open the working demo") + '</span></div></div>';
    }
    return '<div class="film-frame"><div class="placeholder"><strong>The 3-minute film is being published</strong><span>It will appear here as soon as it is on YouTube. Until then, watch the working versions of the films on the Demos page.</span></div></div>';
  }
  function card(f, compact) {
    var yt = f.youtube ? '<p><a class="text-link" href="https://www.youtube.com/watch?v=' + encodeURIComponent(f.youtube) + '" target="_blank" rel="noopener">Watch on YouTube (opens a new tab)</a></p>' : "";
    var meta = fmtMeta(f).map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("");
    var copy = f.captions && !compact ? '<details class="copy" data-vtt="' + esc(root + "demos/" + f.captions) + '"><summary>Read the words of the film</summary><p class="note">Loading the written copy.</p></details>' : "";
    var action = "";
    if (!f.file && !f.youtube) {
      if (f.fallback_href) {
        var href = /^https?:\/\//.test(f.fallback_href) ? f.fallback_href : root + f.fallback_href;
        action = '<p><a class="text-link" href="' + esc(href) + '">' + esc(f.fallback_label || "Open the working demo") + '</a></p>';
      } else {
        action = '<p><a class="text-link" href="' + root + 'demos/#films">Watch the working films</a></p>';
      }
    }
    var h = compact ? "h2" : "h3";
    return '<article class="card film-card' + (compact ? ' film-compact' : '') + '" id="' + esc(f.id) + '">' + frame(f) + '<div><' + h + '>' + esc(f.title) + '</' + h + '><div class="film-meta">' + meta + '</div><p>' + esc(f.blurb || "") + "</p>" + (f.file ? '<p class="slot-keys">Keyboard: Tab to the player, Space plays or pauses, arrow keys seek, M mutes, F opens full screen. Nothing plays until you press play.</p>' : "") + yt + action + copy + "</div></article>";
  }
  var slots = $$("[data-films]");
  if (slots.length && window.fetch) {
    fetch(root + "demos/films.json", { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (data) {
      var films = data.films || [];
      slots.forEach(function (slot) {
        var which = slot.getAttribute("data-films"), list;
        if (which === "main") list = films.filter(function (f) { return f.role === "main"; }).slice(0, 1);
        else if (which.indexOf("id:") === 0) list = films.filter(function (f) { return f.id === which.slice(3); }).slice(0, 1);
        else if (which.indexOf("not:") === 0) { var skip = which.slice(4).split(","); list = films.filter(function (f) { return skip.indexOf(f.id) < 0; }); }
        else list = films.filter(function (f) { return f.role !== "main" || !f.hideOnDemos; });
        slot.innerHTML = list.map(function (f) { return card(f, which === "main" || which.indexOf("id:") === 0); }).join("");
        $$("details.copy", slot).forEach(function (d) {
          d.addEventListener("toggle", function () {
            if (!d.open || d.getAttribute("data-loaded")) return;
            d.setAttribute("data-loaded", "1");
            fetch(d.getAttribute("data-vtt")).then(function (r) { return r.text(); }).then(function (t) { d.querySelector("p").textContent = cueText(t); }).catch(function () { d.querySelector("p").textContent = "The written copy could not be loaded. The captions in the player carry the same words."; });
          });
        });
        if (location.hash) { var t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
      });
      var tbl = $("[data-films-table]");
      if (tbl) tbl.innerHTML = films.map(function (f) {
        return "<tr><td><code>" + esc(f.file || (f.fallback_href ? "(links to working demo)" : "(none yet: set youtube id)")) + "</code></td><td>" + esc(f.title) + "</td><td>" + esc(f.source || "") + "</td><td>" + esc(f.size || "") + "</td><td>" + esc(f.where || "") + "</td></tr>";
      }).join("");
    }).catch(function () {
      slots.forEach(function (s) { s.innerHTML = '<p class="note">The film list could not be loaded. The files are in <code>docs/demos/</code>.</p>'; });
    });
  }
})();
