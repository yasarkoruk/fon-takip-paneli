const VERSION = "thf-static-v2";
self.addEventListener("install", event => event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(["./", "./index.html"]))));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== VERSION).map(key => caches.delete(key))))));
self.addEventListener("fetch", event => { const url = new URL(event.request.url); if (url.pathname.includes("/data/")) return; event.respondWith(fetch(event.request).catch(() => caches.match(event.request))); });
