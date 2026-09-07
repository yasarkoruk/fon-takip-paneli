const VERSION = "fon-takip-pwa-v6";
self.addEventListener("install", event => event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(["/fon-takip-paneli/", "/fon-takip-paneli/index.html", "/fon-takip-paneli/app.js", "/fon-takip-paneli/manifest.json?v=6", "/fon-takip-paneli/apple-touch-icon-180.png", "/fon-takip-paneli/icon-192-v6.png", "/fon-takip-paneli/icon-512-v6.png"]))));
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(Promise.all([caches.keys().then(keys => Promise.all(keys.filter(key => key !== VERSION).map(key => caches.delete(key)))), self.clients.claim()])));
self.addEventListener("fetch", event => { const url = new URL(event.request.url); if (url.pathname.includes("/data/")) return; event.respondWith(fetch(event.request).catch(() => caches.match(event.request))); });
