// Service worker de la web app installée (Brave, Chrome, Edge…).
// Réseau d'abord : la version en ligne est toujours celle utilisée ; la copie en cache ne sert que hors connexion,
// pour rouvrir l'app. Seuls les fichiers du site sont gérés : Supabase, Garmin et les CDN passent sans intermédiaire.
const CACHE = 'mon-plan-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
    event.waitUntil(caches.keys()
        .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
        .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
    event.respondWith(fetch(request)
        .then(response => {
            if (response.ok) {
                const copy = response.clone();
                caches.open(CACHE).then(cache => cache.put(request, copy));
            }
            return response;
        })
        .catch(() => caches.match(request, { ignoreSearch: request.mode === 'navigate' })));
});
