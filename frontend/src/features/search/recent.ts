"use client";

// 최근 검색어: 이 기기에만 30일, 최대 8개까지 둬요. 로그아웃·탈퇴하면 지워요 (2026-11-16 보안 감사 L-3)

const RECENT_KEY = "mujuthaek.search.recent";
/** 같은 탭에서 지웠다고 검색 화면에 알리는 이벤트 (다른 탭은 storage 이벤트로 알아요) */
const RECENT_EVENT = "mujuthaek:search-recent";

export const RECENT_MAX = 8;
/** 조건 저장과 같은 30일 */
export const RECENT_TTL_MS = 30 * 24 * 60 * 60 * 1000;
/** 이보다 긴 검색어는 기억하지 않아요 */
export const RECENT_TEXT_MAX = 100;

export type RecentEntry = { q: string; at: number };

// 저장소를 못 쓰는 브라우저면 이번 화면 동안만 메모리에 둬요
let memory: string | null = null;

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(RECENT_KEY);
  } catch {
    return memory;
  }
}

function writeRaw(value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(RECENT_KEY);
    else window.localStorage.setItem(RECENT_KEY, value);
  } catch {
    memory = value;
  }
}

/**
 * 저장된 값 → 30일이 지나지 않은 검색어 (최근 것부터, 최대 8개).
 * 예전 모양(글자 목록)은 언제 저장했는지 몰라서 버려요
 */
export function parseRecent(raw: string | null, now: number): RecentEntry[] {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (e): e is RecentEntry =>
          typeof e === "object" &&
          e !== null &&
          typeof e.q === "string" &&
          e.q.length > 0 &&
          e.q.length <= RECENT_TEXT_MAX &&
          typeof e.at === "number" &&
          Number.isFinite(e.at) &&
          now - e.at < RECENT_TTL_MS,
      )
      .slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

/** 고른 검색어를 맨 앞에 둬요 (같은 검색어는 하나만, 최대 8개). 비었거나 너무 길면 그대로 */
export function addRecent(entries: RecentEntry[], query: string, now: number): RecentEntry[] {
  const q = query.trim();
  if (!q || q.length > RECENT_TEXT_MAX) return entries;
  return [{ q, at: now }, ...entries.filter((e) => e.q !== q)].slice(0, RECENT_MAX);
}

function readEntries(now: number): RecentEntry[] {
  const raw = readRaw();
  const entries = parseRecent(raw, now);
  // 지난 것·예전 모양은 읽을 때 정리해요 (방문하지 않으면 30일이 지나도 남아 있을 수 있어요)
  const tidy = entries.length ? JSON.stringify(entries) : null;
  if (raw !== null && raw !== tidy) writeRaw(tidy);
  return entries;
}

/** 이 기기의 최근 검색어 (최근 것부터) */
export function readRecent(now = Date.now()): string[] {
  return readEntries(now).map((e) => e.q);
}

/** 검색어를 기억하고 바뀐 목록을 돌려줘요 */
export function rememberRecent(query: string, now = Date.now()): string[] {
  const next = addRecent(readEntries(now), query, now);
  writeRaw(next.length ? JSON.stringify(next) : null);
  return next.map((e) => e.q);
}

/** 최근 검색어 모두 지우기 (로그아웃·탈퇴) */
export function clearRecentSearches() {
  writeRaw(null);
  memory = null;
  window.dispatchEvent(new Event(RECENT_EVENT));
}

/** 이 탭이나 다른 탭에서 최근 검색어가 지워지거나 바뀌면 알려 줘요 */
export function subscribeRecent(listener: () => void) {
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === RECENT_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(RECENT_EVENT, listener);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(RECENT_EVENT, listener);
  };
}
