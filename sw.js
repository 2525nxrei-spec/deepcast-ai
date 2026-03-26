const CACHE_NAME = 'deepcast-v19';
const ASSETS = [
  '/',
  '/css/style.css',
  '/js/audio-player.js',
  '/js/page-init.js',
  '/js/spa-router.js',
  '/js/main.js',
  '/episodes/episodes.json',
  '/manifest.json',
  '/all-episodes.html',
  '/feed.xml',
  '/about.html',
  '/contact.html',
  '/privacy.html',
  '/terms.html',
  '/tokushoho.html',
  '/copyright.html',
  '/assets/icon.svg',
  '/assets/cover-podcast.svg',
  '/assets/og-image.png'
];

// Install: cache shell assets
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first, but skip audio and ad requests entirely
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Skip non-GET requests
  if (e.request.method !== 'GET') return;

  // Skip cross-origin ad requests
  if (url.hostname.includes('googlesyndication') || url.hostname.includes('doubleclick')) return;

  // Skip audio files — let browser handle Range Requests natively
  if (url.pathname.endsWith('.mp3') || url.pathname.endsWith('.wav')) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        // Only cache 200 OK responses from same origin (not 206 Partial Content)
        if (url.origin === location.origin && res.status === 200) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
