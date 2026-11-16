import { backendStatus, isGatewayError } from "./availability";
import { endpoints } from "./endpoints";
import { secureApiOrigin } from "./origin";

/**
 * 백엔드 주소. 기본은 빈 값(이 사이트와 같은 주소): Vercel이 /api/**·/oauth2/**·/login/oauth2/**를 백엔드로 넘겨요(next.config.ts API_ORIGIN).
 * 로컬 개발은 NEXT_PUBLIC_API_BASE_URL=http://localhost:8080으로 백엔드를 바로 불러요
 */
export const API_BASE_URL = secureApiOrigin(process.env.NEXT_PUBLIC_API_BASE_URL);

/** 백엔드 오류 응답 (Problem Details + 화면이 문구를 고를 code) */
export type Problem = {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  instance?: string;
  errors?: { field: string; reason: string }[];
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    /** 429 등에서 다시 해도 되는 때까지 남은 초 (Retry-After). 없거나 다른 주소라 못 읽으면 null */
    readonly retryAfter: number | null = null,
  ) {
    super(`API 요청 실패 (${status})`);
    this.name = "ApiError";
  }

  /** 백엔드 오류 코드 (예: VALIDATION_FAILED, NOT_FOUND). 형식이 다르면 undefined */
  get code() {
    return (this.body as Problem | null)?.code;
  }
}

/** 로그인했지만 필수 약관에 아직 동의하지 않은 계정의 요청을 서버가 막을 때(403) 오는 코드 */
export const TERMS_NOT_AGREED = "TERMS_NOT_AGREED";

/** 필수 약관 동의 전이라 막힌 요청인지 (화면 문구를 고를 때 써요) */
export const isTermsNotAgreed = (error: unknown) =>
  error instanceof ApiError && error.status === 403 && error.code === TERMS_NOT_AGREED;

// access token은 메모리에만 둬요. refresh token은 백엔드가 HttpOnly 쿠키로 관리해요
let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;
let sessionEpoch = 0;
let sessionChannel: BroadcastChannel | null = null;
const sessionListeners = new Set<() => void>();
const termsListeners = new Set<() => void>();

export const authToken = {
  get: () => accessToken,
  set: (token: string | null) => {
    sessionEpoch++;
    accessToken = token;
  },
};

function channel() {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return null;
  sessionChannel ??= new BroadcastChannel("mujuthaek-session");
  return sessionChannel;
}

export function subscribeSessionEnded(listener: () => void) {
  sessionListeners.add(listener);
  const bus = channel();
  if (bus)
    bus.onmessage = (event) => {
      if (event.data?.type !== "logout") return;
      authToken.set(null);
      for (const notify of sessionListeners) notify();
    };
  return () => {
    sessionListeners.delete(listener);
    if (!sessionListeners.size) {
      sessionChannel?.close();
      sessionChannel = null;
    }
  };
}

/** 로그아웃 요청 없이 로그인이 끝났을 때(회원 탈퇴 완료) 다른 탭에도 알려요. 받은 탭은 토큰·캐시·기기 데이터를 비워요 */
export function announceSessionEnded() {
  channel()?.postMessage({ type: "logout" });
}

/**
 * 어느 요청이든 403 TERMS_NOT_AGREED가 오면 알려요. 화면은 이걸 받아 필수 약관 동의 화면으로 보내요
 * (2026-11-16 보안 감사 L-2: 동의 전에는 서버가 내 정보·채팅 쓰기·제보를 막아요)
 */
export function subscribeTermsRequired(listener: () => void) {
  termsListeners.add(listener);
  return () => {
    termsListeners.delete(listener);
  };
}

async function withSessionLock<T>(run: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.locks) {
    return navigator.locks.request(
      "mujuthaek-auth-refresh",
      { signal: AbortSignal.timeout(20000) },
      run,
    );
  }
  return run();
}

export async function endSession() {
  await withSessionLock(async () => {
    await apiFetch(endpoints.authLogout, { method: "POST", signal: AbortSignal.timeout(10000) });
    authToken.set(null);
    channel()?.postMessage({ type: "logout" });
  });
}

/** 로그인 연장 한 번. 사용한 토큰을 다시 보내는 자동 재시도는 하지 않아요. */
async function postRefresh(): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}${endpoints.authRefresh}`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
    signal: AbortSignal.timeout(10000),
  });
  const data = res.ok ? ((await res.json()) as { accessToken: string }) : null;
  return data?.accessToken ?? null;
}

/**
 * 쿠키의 refresh token으로 access token을 다시 받아요. 이 탭에서 동시에 여러 번 불려도 한 번만 요청하고, 탭이 여러 개면 브라우저
 * 잠금으로 한 탭씩 차례로 해요(같은 쿠키로 동시에 연장하면 늦은 쪽이 로그아웃되던 문제, 2026-10-29). 잠금이 없는 브라우저는 그냥 보내요
 */
export function refreshAccessToken(): Promise<string | null> {
  const epoch = sessionEpoch;
  refreshing ??= withSessionLock(() => postRefresh())
    .then((token) => {
      if (epoch !== sessionEpoch) return null;
      accessToken = token;
      return accessToken;
    })
    .catch(() => {
      if (epoch === sessionEpoch) accessToken = null;
      return null;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function send(path: string, { body, headers, ...init }: RequestOptions) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(body !== undefined && { "Content-Type": "application/json" }),
      ...(accessToken && { Authorization: `Bearer ${accessToken}` }),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
  }).catch((error: unknown) => {
    // 화면 이동·요청 취소는 서버 장애가 아니에요.
    const cancelled =
      init.signal?.aborted ||
      (error !== null &&
        typeof error === "object" &&
        "name" in error &&
        error.name === "AbortError");
    if (!cancelled) backendStatus.markDown();
    throw error;
  });
  return res;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}) {
  let res = await send(path, options);

  // 토큰이 없거나 만료됐으면 한 번만 다시 받아서 재시도해요 (재발급·로그아웃 요청은 제외)
  if (res.status === 401 && !path.startsWith("/api/auth/") && (await refreshAccessToken())) {
    res = await send(path, options);
  }

  const data = res.status === 204 || res.status === 304 ? null : await res.json().catch(() => null);
  // 프록시 오류를 연결 장애로 표시하고, 복구되면 안내를 해제해요.
  if (isGatewayError(res.status, data)) backendStatus.markDown();
  else backendStatus.markUp();
  if (!res.ok) {
    const retryAfter = Number(res.headers.get("Retry-After"));
    const error = new ApiError(res.status, data, retryAfter > 0 ? retryAfter : null);
    if (isTermsNotAgreed(error)) for (const notify of termsListeners) notify();
    throw error;
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, init?: RequestOptions) => apiFetch<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: RequestOptions) =>
    apiFetch<T>(path, { ...init, method: "POST", body }),
  put: <T>(path: string, body?: unknown, init?: RequestOptions) =>
    apiFetch<T>(path, { ...init, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, init?: RequestOptions) =>
    apiFetch<T>(path, { ...init, method: "PATCH", body }),
  delete: <T>(path: string, init?: RequestOptions) =>
    apiFetch<T>(path, { ...init, method: "DELETE" }),
};
