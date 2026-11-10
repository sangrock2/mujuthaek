"use client";

// 로그인 상태: 쿠키의 refresh token으로 access token을 받고 내 정보(GET /api/users/me)를 불러와요.
// 로그인하지 않았으면(401) null. 화면은 이걸로 로그인/내 홈을 나눠 보여줘요
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import { api, ApiError, authToken } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";

/** GET /api/users/me (백엔드 MeResponse) */
export type Session = {
  id: string;
  nickname: string;
  role: string;
  /** 연결된 간편 로그인 (KAKAO · NAVER · GOOGLE) */
  providers: string[];
  joinedAt: string;
  /** 계정 연락용 이메일 (선택). 등록하지 않았으면 null */
  email: string | null;
};

export const sessionKey = ["auth", "me"] as const;

const MOCK_SESSION: Session = {
  id: "mock",
  nickname: "준",
  role: "USER",
  providers: ["KAKAO"],
  joinedAt: "2026-10-01T00:00:00Z",
  email: null,
};

async function fetchSession(): Promise<Session | null> {
  if (USE_MOCKS) return MOCK_SESSION;
  try {
    // access token이 없거나 만료됐으면 api가 쿠키로 한 번 다시 받아요
    return await api.get<Session>(endpoints.usersMe);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return null;
    throw error;
  }
}

/** 지금 로그인한 사람. 불러오는 동안 data는 undefined, 로그인 안 했으면 null */
export function useSession() {
  return useQuery({
    queryKey: sessionKey,
    queryFn: fetchSession,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** 로그아웃: 백엔드가 refresh token 쿠키를 지우고, 메모리의 access token과 로그인 상태도 비워요 */
export function useLogout() {
  const client = useQueryClient();
  return useCallback(async () => {
    if (!USE_MOCKS) {
      await api.post(endpoints.authLogout).catch(() => undefined);
    }
    authToken.set(null);
    client.setQueryData(sessionKey, null);
  }, [client]);
}

/** 간편 로그인 표시 이름 */
export const providerLabel: Record<string, string> = {
  KAKAO: "카카오",
  NAVER: "네이버",
  GOOGLE: "구글",
};

/** 로그인 화면: 이미 로그인했으면 로그인 버튼 대신 내 홈으로 보내요 */
export function useLeaveIfLoggedIn() {
  const { data } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (data) router.replace(routes.home);
  }, [data, router]);
}
