const VERSION = "fon-takip-pwa-v7";
const OFFLINE_SHELL = ["/fon-takip-paneli/index.html?v=7", "/fon-takip-paneli/app.js?v=13", "/fon-takip-paneli/manifest.json?v=6", "/fon-takip-paneli/apple-touch-icon-180.png", "/fon-takip-paneli/icon-192-v6.png", "/fon-takip-paneli/icon-512-v6.png"];
self.addEventListener("install", event => event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(OFFLINE_SHELL))));
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(Promise.all([caches.keys().then(keys => Promise.all(keys.filter(key => key !== VERSION).map(key => caches.delete(key)))), self.clients.claim()])));
self.addEventListener("fetch", event => { const url = new URL(event.request.url); if (url.pathname.includes("/data/")) return; event.respondWith(fetch(event.request, {cache: "no-store"}).catch(() => event.request.mode === "navigate" ? caches.match("/fon-takip-paneli/index.html?v=7") : caches.match(event.request))); });
