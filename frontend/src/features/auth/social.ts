import { API_BASE_URL } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { routes } from "@/lib/routes";

export type SocialProvider = "kakao" | "naver" | "google";

export const socialProviders: { key: SocialProvider; name: string }[] = [
  { key: "kakao", name: "카카오" },
  { key: "naver", name: "네이버" },
  { key: "google", name: "Google" },
];

/**
 * 간편 로그인 시작 주소. 백엔드가 제공자 화면으로 보내고, 끝나면 /auth/callback으로 돌아와요.
 * 목업 모드에선 처음 가입한 것처럼 콜백으로 바로 가요
 */
export function socialLoginUrl(provider: SocialProvider) {
  return USE_MOCKS
    ? `${routes.authCallback}?new=1`
    : `${API_BASE_URL}/oauth2/authorization/${provider}`;
}

/** 로그인 실패 이유(백엔드 /login?error=social&reason=…) → 안내 문구 */
export function loginErrorMessage(reason: string | null) {
  if (reason === "access_denied") return "로그인을 취소했어요. 다시 시도해 주세요";
  return "로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요";
}
