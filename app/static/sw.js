const CACHE_NAME = "nosocial-shell-v4";
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
    fetch(request, { cache: "no-cache" }).then(function(response) {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then(function(cache) {
          return cache.put(request, copy);
        }));
      }
      return response;
    }).catch(function(error) {
      return caches.match(request).then(function(cachedResponse) {
        if (cachedResponse) return cachedResponse;
        throw error;
      });
    })
  );
});
