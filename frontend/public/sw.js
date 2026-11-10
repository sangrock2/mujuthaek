// 무주택자들 서비스 워커: 오프라인 폴백 + 웹 푸시
const CACHE_NAME = "mujuthaek-v1";
const OFFLINE_URL = "/offline";
const PRECACHE_URLS = [OFFLINE_URL, "/icons/icon-192.png", "/icons/badge-96.png"];
// 백엔드 주소 (등록할 때 /sw.js?api=… 로 받아요). 알림을 봤는지·눌렀는지 알릴 때 써요
const API_BASE = (() => {
  const api = new URL(self.location.href).searchParams.get("api");
  return api && /^https?:\/\//.test(api) ? api.replace(/\/$/, "") : null;
})();

/** 알림함 줄마다 「떴어요(shown)·눌렀어요(clicked)」를 알려요 (로그인 없이, 실패해도 그냥 넘어가요) */
function report(ids, event) {
  if (!API_BASE || !Array.isArray(ids) || ids.length === 0) return Promise.resolve();
  return Promise.all(
    ids.map((id) =>
      fetch(`${API_BASE}/api/v1/notifications/${encodeURIComponent(id)}/${event}`, {
        method: "POST",
        credentials: "omit",
        keepalive: true,
      }).catch(() => undefined),
    ),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  // 페이지 이동: 네트워크 우선, 실패하면 오프라인 페이지
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL).then((res) => res ?? Response.error())),
    );
    return;
  }

  // 빌드 결과물(해시 파일명)과 아이콘: 캐시 우선
  const url = new URL(request.url);
  if (
    url.origin === self.location.origin &&
    (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/"))
  ) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ??
          fetch(request).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return res;
          }),
      ),
    );
  }
});

self.addEventListener("push", (event) => {
  if (!event.data) return;
  let data;
  try {
    data = event.data.json();
  } catch {
    data = { title: "무주택자들", body: event.data.text() };
  }

  // 알림 서버 내용: { v, type, title, body, linkPath, tag, ids } (contracts web-push 4장)
  const ids = Array.isArray(data.ids) ? data.ids : [];
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(data.title ?? "무주택자들", {
        body: data.body,
        icon: data.icon ?? "/icons/icon-192.png",
        badge: "/icons/badge-96.png",
        // 같은 화면 알림은 기기에서 최신 것 하나로 바꿔 보여요
        tag: data.tag,
        // 같은 화면 알림이 다시 오면 조용히 바꿔치기하지 않고 새로 알려요
        renotify: Boolean(data.tag),
        data: { url: data.linkPath ?? data.url ?? "/", ids },
      }),
      report(ids, "shown"),
    ]),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = new URL(event.notification.data?.url ?? "/", self.location.origin).href;

  event.waitUntil(
    Promise.all([
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
        const existing = windows.find((client) => client.url === targetUrl);
        return existing ? existing.focus() : self.clients.openWindow(targetUrl);
      }),
      report(event.notification.data?.ids, "clicked"),
    ]),
  );
});
