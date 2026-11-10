"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { sessionKey } from "@/features/auth/session";
import { refreshAccessToken } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { routes } from "@/lib/routes";

/**
 * 간편 로그인을 마치고 돌아오는 곳. 백엔드가 refresh token 쿠키를 줬으니 access token을 받고,
 * 처음 가입했으면(?new=1) 약관 동의로, 아니면 홈으로 가요
 */
export function AuthCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const joined = params.get("new") === "1";
  const client = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    (USE_MOCKS ? Promise.resolve("mock") : refreshAccessToken()).then((token) => {
      if (cancelled) return;
      if (!token) {
        router.replace(`${routes.login}?error=social&reason=token`);
        return;
      }
      // 로그인 전 화면에서 "로그인 안 함"으로 기억한 상태를 지우고 내 정보를 다시 받아요
      void client.invalidateQueries({ queryKey: sessionKey });
      router.replace(joined ? routes.signup : routes.home);
    });
    return () => {
      cancelled = true;
    };
  }, [client, joined, router]);

  return (
    <main className="bg-bg text-text-sub flex min-h-screen items-center justify-center text-[16px] font-semibold">
      <span role="status">로그인하는 중이에요…</span>
    </main>
  );
}
