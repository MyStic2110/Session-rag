const CACHE_NAME = 'ghostpolicy-v3';
const ASSETS = [
    '/static/',
    '/static/index.html',
    '/static/styles.css',
    '/static/app.js',
    '/static/icon.svg',
    '/static/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
        .then(cache => cache.addAll(ASSETS))
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(keys.map(key => {
                if (key !== CACHE_NAME) return caches.delete(key);
            }));
        })
    );
});

self.addEventListener('fetch', event => {
    // Force network-first for index.html and app.js to ensure user sees new UI
    if (event.request.url.includes('index.html') || event.request.url.includes('app.js')) {
        return event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
    }
    
    // Only intercept GET requests for other static assets
    if (event.request.method !== 'GET') return;
    
    event.respondWith(
        caches.match(event.request)
        .then(response => {
            return response || fetch(event.request);
        })
    );
});
