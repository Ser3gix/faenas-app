// ============================================================
// sw.js — Service Worker para funcionamiento offline
// Gestión de Faenas — App móvil
// Versión 2 — cachea la app completa en la instalación
// ============================================================

const CACHE = "faenas-v28";
const ARCHIVOS_CACHE = [
  "/movil2",
  "/static/manifest.json",
  "/static/sw.js"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => {
      return Promise.allSettled(
        ARCHIVOS_CACHE.map(url =>
          fetch(url).then(res => {
            if (res.ok) cache.put(url, res);
          }).catch(() => {})
        )
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = e.request.url;
  if (url.includes("/api/")) return;

  const esPagina = e.request.mode === "navigate" || url.includes("/movil2") || url.includes("/static/sw.js");
  if (esPagina) {
    e.respondWith(
      caches.open(CACHE).then(cache =>
        cache.match(e.request).then(cached => {
          const networkFetch = fetch(e.request).then(res => {
            if (res.ok && e.request.method === "GET") cache.put(e.request, res.clone());
            return res;
          }).catch(() => cached || null);
          return cached || networkFetch;
        })
      )
    );
    return;
  }

  e.respondWith(
    caches.open(CACHE).then(cache =>
      cache.match(e.request).then(cached => {
        const networkFetch = fetch(e.request).then(res => {
          if (res.ok && e.request.method === "GET") {
            cache.put(e.request, res.clone());
          }
          return res;
        }).catch(() => null);
        return cached || networkFetch;
      })
    )
  );
});
