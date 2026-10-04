const CACHE_NAME = 'nextplan-shell-v12-phase-c';
const APP_SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg', './apple-web-v1.css'];
const APPLE_STYLE_TAG = '<link rel="stylesheet" href="./apple-web-v1.css?v=apple-web-v1">';

async function injectAppleWebTheme(response) {
  if (!response) return response;
  const type = response.headers.get('content-type') || '';
  if (!type.includes('text/html')) return response;
  const html = await response.text();
  const styled = html.includes('apple-web-v1.css') ? html : html.replace('</head>', `${APPLE_STYLE_TAG}\n</head>`);
  const headers = new Headers(response.headers);
  headers.delete('content-length');
  return new Response(styled, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(request, { cache: 'no-store' });
        const styled = await injectAppleWebTheme(response);
        const copy = styled.clone();
        caches.open(CACHE_NAME).then(cache => cache.put('./index.html', copy));
        return styled;
      } catch (_) {
        const cached = await caches.match('./index.html');
        return injectAppleWebTheme(cached);
      }
    })());
    return;
  }

  const url = new URL(request.url);
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(request, { cache: 'no-store' })
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
