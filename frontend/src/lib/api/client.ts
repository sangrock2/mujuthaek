import { backendStatus, isGatewayError } from "./availability";
import { endpoints } from "./endpoints";

/**
 * 백엔드 주소. 기본은 빈 값(이 사이트와 같은 주소): Vercel이 /api/**·/oauth2/**·/login/oauth2/**를 백엔드로 넘겨요(next.config.ts API_ORIGIN).
 * 로컬 개발은 NEXT_PUBLIC_API_BASE_URL=http://localhost:8080으로 백엔드를 바로 불러요
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

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

// access token은 메모리에만 둬요. refresh token은 백엔드가 HttpOnly 쿠키로 관리해요
let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;

export const authToken = {
  get: () => accessToken,
  set: (token: string | null) => {
    accessToken = token;
  },
};

/** 로그인 연장 한 번. 409(다른 요청이 먼저 연장함)면 그쪽이 받은 새 쿠키로 한 번 더 해요 */
async function postRefresh(retried = false): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}${endpoints.authRefresh}`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (res.status === 409 && !retried) {
    await new Promise((r) => setTimeout(r, 300));
    return postRefresh(true);
  }
  const data = res.ok ? ((await res.json()) as { accessToken: string }) : null;
  return data?.accessToken ?? null;
}

/**
 * 쿠키의 refresh token으로 access token을 다시 받아요. 이 탭에서 동시에 여러 번 불려도 한 번만 요청하고, 탭이 여러 개면 브라우저
 * 잠금으로 한 탭씩 차례로 해요(같은 쿠키로 동시에 연장하면 늦은 쪽이 로그아웃되던 문제, 2026-10-29). 잠금이 없는 브라우저는 그냥 보내요
 */
export function refreshAccessToken(): Promise<string | null> {
  const run = () => postRefresh();
  // 잠금 콜백이 돌려준 Promise를 풀어 받아요
  const locked = async (): Promise<string | null> =>
    await navigator.locks.request("mujuthaek-auth-refresh", run);
  refreshing ??= (typeof navigator !== "undefined" && navigator.locks ? locked() : run())
    .then((token) => {
      accessToken = token;
      return accessToken;
    })
    .catch(() => {
      accessToken = null;
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
    backendStatus.markDown(); // 연결 자체가 안 됨 (서버가 꺼져 있는 시간 등)
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
  // Vercel·프록시가 대신 낸 502·503·504면 백엔드가 꺼져 있는 거예요. 화면 위에 운영 시간을 알려요
  if (isGatewayError(res.status, data)) backendStatus.markDown();
  else backendStatus.markUp();
  if (!res.ok) {
    const retryAfter = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, data, retryAfter > 0 ? retryAfter : null);
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
