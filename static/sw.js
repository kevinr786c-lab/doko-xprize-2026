const CACHE_NAME = 'doko-pwa-v33-implementacion';
const ASSETS_TO_CACHE = [
    '/static/css/main.css',
    '/static/css/responsive.css',
    '/static/js/chatbot_faq.js',
    '/static/js/pwa_experience.js',
    '/static/offline.html',
    '/static/img/logo-pwa.svg'
];

// Cache only public static assets. Medical and operational data always stays online.
self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE)));
    self.skipWaiting();
});

// The page explicitly activates a new worker after the user accepts the update.
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => Promise.all(
            cacheNames.map((cacheName) => cacheName !== CACHE_NAME && caches.delete(cacheName))
        ))
    );
    self.clients.claim();
});

// Static assets work offline. Dynamic medical data and API responses are never cached.
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    if (ASSETS_TO_CACHE.includes(url.pathname)) {
        event.respondWith(
            caches.match(event.request).then((response) => response || fetch(event.request).then((networkResponse) => {
                const copy = networkResponse.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                return networkResponse;
            }))
        );
        return;
    }

    if (event.request.mode === 'navigate') {
        event.respondWith(fetch(event.request).catch(() => caches.match('/static/offline.html')));
    }
});
