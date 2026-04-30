const CACHE_NAME = "nosocial-shell-v1";
const SHELL_ASSETS = [
  "/static/css/styles.css",
  "/static/js/main.js",
  "/static/js/tree.js",
  "/static/js/admin.js",
  "/static/img/app-icon.svg",
  "/static/manifest.json"
];

self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(SHELL_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames
          .filter(function(cacheName) {
            return cacheName !== CACHE_NAME;
          })
          .map(function(cacheName) {
            return caches.delete(cacheName);
          })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function(event) {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (!url.pathname.startsWith("/static/")) {
    return;
  }

  event.respondWith(
    caches.match(request).then(function(cachedResponse) {
      return cachedResponse || fetch(request);
    })
  );
});
