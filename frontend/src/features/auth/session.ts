"use client";

// 로그인 상태: 쿠키의 refresh token으로 access token을 받고 내 정보(GET /api/users/me)를 불러와요.
// 로그인하지 않았으면(401) null. 화면은 이걸로 로그인/내 홈을 나눠 보여줘요
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { claimDeviceData, forgetDeviceData } from "@/features/auth/deviceData";
import {
  api,
  ApiError,
  authToken,
  endSession,
  subscribeSessionEnded,
  subscribeTermsRequired,
} from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { routes } from "@/shared/lib/routes";

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
  /**
   * 가입 필수 동의(만 14세 이상 · 이용약관 · 개인정보 수집·이용)를 서버에 기록했는지. false면 동의 화면으로 보내요
   * (2026-11-16 보안 감사 L-2). 이 칸이 없는 예전 응답은 동의한 것으로 봐요
   */
  termsAgreed: boolean;
};

export const sessionKey = ["auth", "me"] as const;

const MOCK_SESSION: Session = {
  id: "mock",
  nickname: "준",
  role: "USER",
  providers: ["KAKAO"],
  joinedAt: "2026-10-01T00:00:00Z",
  email: null,
  termsAgreed: true,
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

const sessionQuery = {
  queryKey: sessionKey,
  queryFn: fetchSession,
  staleTime: 5 * 60 * 1000,
  retry: false,
} as const;

/** 지금 로그인한 사람. 불러오는 동안 data는 undefined, 로그인 안 했으면 null */
export function useSession() {
  return useQuery(sessionQuery);
}

/** 내 정보를 서버에서 새로 받아요 (간편 로그인 직후처럼 캐시를 믿을 수 없을 때) */
export function loadSession(client: QueryClient) {
  return client.fetchQuery({ queryKey: sessionKey, queryFn: fetchSession, staleTime: 0 });
}

/**
 * 가입을 마친 회원인지 (로그인 + 필수 약관 동의). 동의 전에는 서버가 /api/users/me/** 를 403으로 막으니
 * 관심 공고·알림·준비함처럼 그 API를 부르는 쿼리는 이걸로 켜요 (동의 화면에서 헛요청·되돌리기가 반복되지 않게)
 */
export const isMember = (session: Session | null | undefined): session is Session =>
  !!session && session.termsAgreed !== false;

/**
 * 필수 약관에 동의하기 전에도 머무를 수 있는 화면: 동의 화면, 동의할 문서(약관·처리방침·이력), 간편 로그인 처리, 탈퇴 완료,
 * 메일 수신 거부(로그인 없이 써요), 오프라인 안내
 */
const TERMS_FREE_PATHS = [
  routes.signup,
  routes.authCallback,
  routes.terms,
  routes.privacy,
  routes.legal,
  routes.withdrawn,
  "/email/unsubscribe",
  "/offline",
];

export const isTermsFreePath = (path: string) =>
  TERMS_FREE_PATHS.some((p) => path === p || path.startsWith(`${p}/`));

/** 로그아웃: 백엔드가 refresh token 쿠키를 지우고, 메모리의 access token과 로그인 상태도 비워요 */
export function useLogout() {
  const client = useQueryClient();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const logout = useCallback(async () => {
    setLogoutError(null);
    if (!USE_MOCKS) {
      try {
        await endSession();
      } catch {
        setLogoutError("로그아웃을 완료하지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.");
        return false;
      }
    }
    authToken.set(null);
    // 이 기기에 남긴 조건·사업 정보·최근 검색어도 지워요 (공용 PC의 다음 사람에게 보이지 않게, 2026-11-16 보안 감사 L-3)
    forgetDeviceData();
    await client.cancelQueries();
    // clear()로 query를 제거하기 전에 기존 화면의 observer에도 로그아웃을 알려요.
    client.setQueryData(sessionKey, null);
    client.clear();
    client.setQueryData(sessionKey, null);
    return true;
  }, [client]);
  return { logout, logoutError };
}

/**
 * 모든 화면에 하나 있는 로그인 상태 지킴이 (providers.tsx)
 * - 다른 탭에서 로그아웃하면 이 탭의 캐시와 이번 탭에만 둔 값(소득·자산 등)도 비워요
 * - 다른 계정으로 로그인했으면 앞 계정이 이 기기에 남긴 값을 지워요
 * - 필수 약관에 동의하지 않은 계정이면(내 정보의 termsAgreed=false 또는 어느 요청이든 403 TERMS_NOT_AGREED) 동의 화면으로 보내요
 */
export function SessionSync() {
  const client = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const free = isTermsFreePath(pathname);
  // 동의 전에도 머무는 화면(약관·처리방침·로그인 처리 등)에서는 내 정보를 따로 묻지 않고 다른 곳에서 받은 값만 봐요
  const { data: session } = useQuery({ ...sessionQuery, enabled: !free });
  const userId = session?.id;
  const needsTerms = session?.termsAgreed === false;

  useEffect(
    () =>
      subscribeSessionEnded(() => {
        forgetDeviceData();
        void client.cancelQueries().then(() => {
          client.setQueryData(sessionKey, null);
          client.clear();
          client.setQueryData(sessionKey, null);
        });
      }),
    [client],
  );

  useEffect(
    () =>
      subscribeTermsRequired(() => {
        const current = client.getQueryData<Session | null>(sessionKey);
        if (current) {
          if (current.termsAgreed !== false) {
            client.setQueryData<Session>(sessionKey, { ...current, termsAgreed: false });
          }
        } else {
          void client.invalidateQueries({ queryKey: sessionKey });
        }
      }),
    [client],
  );

  useEffect(() => {
    if (userId) claimDeviceData(userId);
  }, [userId]);

  useEffect(() => {
    if (needsTerms && !free) router.replace(routes.signup);
  }, [needsTerms, free, router]);

  return null;
}

/** 간편 로그인 표시 이름 */
export const providerLabel: Record<string, string> = {
  KAKAO: "카카오",
  NAVER: "네이버",
  GOOGLE: "구글",
};

/** 로그인 화면: 이미 로그인했으면 로그인 버튼 대신 내 홈으로 (필수 약관 동의 전이면 동의 화면으로) 보내요 */
export function useLeaveIfLoggedIn() {
  const { data } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (data) router.replace(data.termsAgreed === false ? routes.signup : routes.home);
  }, [data, router]);
}
