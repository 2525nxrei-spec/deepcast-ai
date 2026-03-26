const CACHE_NAME = "deepcast-v1";

const STATIC_ASSETS = ["/", "/episodes", "/library", "/auth/login"];

// Install: 静的アセットをプリキャッシュ
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: 古いキャッシュを削除
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch: Network First（API） + Cache First（静的アセット）
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API リクエスト → Network First
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // 静的アセット → Cache First
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        // バックグラウンドでキャッシュ更新
        fetch(request)
          .then((response) => {
            caches.open(CACHE_NAME).then((cache) => cache.put(request, response));
          })
          .catch(() => {});
        return cached;
      }
      return fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      });
    })
  );
});
