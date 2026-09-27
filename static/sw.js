// ============================================================
// sw.js — Service Worker Faenas móvil
// ============================================================

const CACHE = "faenas-v66h";
const ARCHIVOS_CACHE = [
  "/static/manifest.json",
  "/static/sw.js"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => {
      return Promise.allSettled(
        ARCHIVOS_CACHE.map(url =>
          fetch(url, { cache: "no-store" }).then(res => {
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
      Promise.all(keys.map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = e.request.url;
  if (url.includes("/api/")) return;

  // /movil2 siempre de red (sin caché) para ver cambios de UI al instante
  if (e.request.mode === "navigate" || url.includes("/movil2")) {
    e.respondWith(
      fetch(e.request, { cache: "no-store" }).catch(() =>
        caches.open(CACHE).then(cache => cache.match("/movil2"))
      )
    );
    return;
  }

  if (url.includes("/static/sw.js")) {
    e.respondWith(fetch(e.request, { cache: "no-store" }));
    return;
  }

  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok && e.request.method === "GET") {
        const clone = res.clone();
        caches.open(CACHE).then(cache => cache.put(e.request, clone)).catch(() => {});
      }
      return res;
    }).catch(() => caches.open(CACHE).then(cache => cache.match(e.request)))
  );
});
