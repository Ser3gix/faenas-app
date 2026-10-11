// ============================================================
// sw.js — Service Worker Faenas móvil
// ============================================================

const CACHE = "faenas-v66o";
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
    })    .catch(() => caches.open(CACHE).then(cache => cache.match(e.request)))
  );
});

const AVISO_TIEMPO = "faenas-crono";
let _avisoTiempo = null;
let _avisoTick = null;

function _fmtCronoSw(inicioIso) {
  const ini = new Date(inicioIso).getTime();
  if (!Number.isFinite(ini)) return "0:00";
  const s = Math.max(0, Math.floor((Date.now() - ini) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return h + ":" + String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
  return m + ":" + String(sec).padStart(2, "0");
}

function _pintarAvisoTiempo() {
  if (!_avisoTiempo || !self.registration || !self.registration.showNotification) return;
  const t = _avisoTiempo;
  const crono = _fmtCronoSw(t.inicio);
  const titulo = "⏱ " + crono + "  " + (t.tipo || "Tiempo");
  const cuerpo = (t.faena || "Faenas") + " · pulsa para abrir o Parar";
  self.registration.showNotification(titulo, {
    body: cuerpo,
    tag: AVISO_TIEMPO,
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    renotify: false,
    silent: true,
    requireInteraction: true,
    data: t,
    actions: [
      { action: "parar", title: "Parar" },
      { action: "abrir", title: "Abrir" }
    ]
  }).catch(() => {});
}

function _arrancarAvisoTiempo(datos) {
  _avisoTiempo = datos || null;
  if (!_avisoTiempo) return;
  if (!_avisoTick) {
    _pintarAvisoTiempo();
    _avisoTick = setInterval(_pintarAvisoTiempo, 1000);
  }
}

function _pararAvisoTiempo() {
  _avisoTiempo = null;
  if (_avisoTick) { clearInterval(_avisoTick); _avisoTick = null; }
  self.registration.getNotifications({ tag: AVISO_TIEMPO }).then(list => {
    list.forEach(n => n.close());
  }).catch(() => {});
}

self.addEventListener("message", e => {
  const msg = e.data || {};
  if (msg.type === "TIMER_START" || msg.type === "TIMER_UPDATE") {
    _arrancarAvisoTiempo(msg.datos || msg);
  }
  if (msg.type === "TIMER_STOP") _pararAvisoTiempo();
});

self.addEventListener("notificationclick", e => {
  const accion = e.action;
  e.notification.close();
  e.waitUntil((async () => {
    const clientsList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (accion === "parar") {
      _pararAvisoTiempo();
      for (const c of clientsList) {
        try { c.postMessage({ type: "TIMER_PARAR" }); } catch (err) {}
      }
    }
    if (clientsList.length) {
      await clientsList[0].focus();
      return;
    }
    await self.clients.openWindow("/movil2");
  })());
});
