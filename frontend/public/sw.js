// 무주택자들 서비스 워커: 오프라인 폴백 + 웹 푸시
const CACHE_NAME = "mujuthaek-v1";
const OFFLINE_URL = "/offline";
const PRECACHE_URLS = [OFFLINE_URL, "/icons/icon-192.png", "/icons/badge-96.png"];
const LOOPBACK = ["localhost", "127.0.0.1", "[::1]"];

/**
 * 알림을 봤는지·눌렀는지 알릴 API 주소. 기본은 이 사이트(운영은 같은 주소로 API를 넘겨요).
 * 등록할 때 /sw.js?api=… 로 다른 주소를 받을 수 있지만, 이 사이트와 워커가 모두 로컬(loopback)일 때만 써요.
 * 예전에는 아무 출처나 받아서, 스크립트가 끼어들면 알림 ID를 다른 호스트로 계속 보내게 할 수 있었어요 (2026-11-16 보안 감사 4장)
 */
function apiBaseFrom(workerHref) {
  const worker = new URL(workerHref);
  const value = worker.searchParams.get("api");
  if (!value) return worker.origin;
  let api;
  try {
    api = new URL(value);
  } catch {
    return worker.origin;
  }
  if (api.origin === worker.origin) return worker.origin;
  const local =
    LOOPBACK.includes(worker.hostname) &&
    LOOPBACK.includes(api.hostname) &&
    (api.protocol === "http:" || api.protocol === "https:") &&
    !api.username &&
    !api.password;
  return local ? api.origin : worker.origin;
}
const API_BASE = apiBaseFrom(self.location.href);

/** 알림함 줄마다 「떴어요(shown)·눌렀어요(clicked)」를 알려요 (로그인 없이, 실패해도 그냥 넘어가요) */
function report(ids, event) {
  if (!API_BASE || !Array.isArray(ids) || ids.length === 0) return Promise.resolve();
  // 「.」「..」은 인코딩해도 경로를 한 칸 위로 줄여서 다른 API를 부르게 돼요
  const valid = ids.filter(
    (id) => typeof id === "string" && id !== "" && id !== "." && id !== "..",
  );
  return Promise.all(
    valid.map((id) =>
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

/** 알림을 누르면 이 사이트 안의 화면만 열어요. 「//다른곳」·「/\다른곳」 같은 주소가 와도 홈으로 (2026-11-16 보안 감사 M-8) */
function sameSiteUrl(value) {
  try {
    const url = new URL(typeof value === "string" ? value : "/", self.location.origin);
    return url.origin === self.location.origin ? url.href : new URL("/", self.location.origin).href;
  } catch {
    return new URL("/", self.location.origin).href;
  }
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = sameSiteUrl(event.notification.data?.url);

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
