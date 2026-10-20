/* TRACE play/ service worker — version-pinned cache-first for same-origin
   docs/ requests. Plain CacheStorage; view source. vplay-1. */
var CACHE = "play-v1";
var CORE = [
  "./",
  "./index.html",
  "./app.js",
  "./dag-skeleton.json",
  "./provenance.json",
  "../assets/design.css",
  "../assets/motion.js",
  "../explorer/probes_summary.json",
  "../explorer/qualification_10m.json",
  "../explorer/local_20k_data.json",
  "../explorer/result.json"
];

self.addEventListener("install", function (ev) {
  ev.waitUntil(caches.open(CACHE).then(function (c) {
    return c.addAll(CORE);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (ev) {
  ev.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (ev) {
  var url = new URL(ev.request.url);
  if (url.origin !== location.origin) return; // same-origin only
  ev.respondWith(caches.match(ev.request).then(function (hit) {
    if (hit) return hit;
    return fetch(ev.request).then(function (res) {
      if (res.ok && (url.pathname.indexOf("/explorer/") !== -1 || url.pathname.indexOf("/play/") !== -1)) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(ev.request, copy); });
      }
      return res;
    }).catch(function () {
      return new Response("offline and not cached — reconnect once to fetch, then airplane mode works.",
        { status: 503, headers: { "Content-Type": "text/plain" } });
    });
  }));
});
