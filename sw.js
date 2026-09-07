// Basit servis calisani: PWA yuklenebilirligi icin gerekli.
// Ag isteklerini olabildigince ag uzerinden gecirir (veri her zaman guncel gelsin diye),
// sadece kabuk dosyalarini (index.html) kisa sureli onbellekler.
const CACHE_NAME = "thf-panel-v1";
const SHELL_FILES = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // data/*.json her zaman ag uzerinden (guncel veri icin); digerlerinde
  // ag basarisiz olursa onbellege dus.
  const url = new URL(event.request.url);
  if (url.pathname.includes("/data/")) return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
