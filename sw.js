const VERSION = "fon-takip-pwa-v5";
self.addEventListener("install", event => event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(["/fon-takip-paneli/", "/fon-takip-paneli/index.html", "/fon-takip-paneli/app.js", "/fon-takip-paneli/manifest.json?v=5", "/fon-takip-paneli/fon-takip-icon.svg?v=5", "/fon-takip-paneli/icon-192.png?v=5", "/fon-takip-paneli/icon-512.png?v=5"]))));
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(Promise.all([caches.keys().then(keys => Promise.all(keys.filter(key => key !== VERSION).map(key => caches.delete(key)))), self.clients.claim()])));
self.addEventListener("fetch", event => { const url = new URL(event.request.url); if (url.pathname.includes("/data/")) return; event.respondWith(fetch(event.request).catch(() => caches.match(event.request))); });
