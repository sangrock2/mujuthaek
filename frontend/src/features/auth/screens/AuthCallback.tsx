"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { loadSession } from "@/features/auth/session";
import { refreshAccessToken } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { routes } from "@/shared/lib/routes";

/**
 * 간편 로그인을 마치고 돌아오는 곳. 백엔드가 refresh token 쿠키를 줬으니 access token을 받고,
 * 필수 약관에 아직 동의하지 않은 계정이면 약관 동의로, 아니면 홈으로 가요.
 * 처음 가입(?new=1)이 아니어도 동의 기록이 없으면 동의 화면으로 가요 (2026-11-16 보안 감사 L-2)
 */
export function AuthCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const joined = params.get("new") === "1";
  const client = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    (USE_MOCKS ? Promise.resolve("mock") : refreshAccessToken()).then(async (token) => {
      if (cancelled) return;
      if (!token) {
        router.replace(`${routes.login}?error=social&reason=token`);
        return;
      }
      // 로그인 전 화면에서 "로그인 안 함"으로 기억한 상태를 버리고 내 정보를 다시 받아요.
      // 받지 못했거나 동의 여부가 없는 예전 응답이면 처음 가입했는지(?new=1)로 정해요
      const me = USE_MOCKS ? undefined : await loadSession(client).catch(() => undefined);
      if (cancelled) return;
      const agreed = me?.termsAgreed;
      const needsTerms = agreed === false || (agreed === undefined && joined);
      router.replace(needsTerms ? routes.signup : routes.home);
    });
    return () => {
      cancelled = true;
    };
  }, [client, joined, router]);

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="bg-bg text-text-sub flex min-h-screen items-center justify-center text-[16px] font-semibold"
    >
      <span role="status">로그인하는 중이에요…</span>
    </main>
  );
}
