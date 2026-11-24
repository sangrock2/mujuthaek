"use client";

import { useSession } from "@/features/auth/session";
import { routes } from "@/shared/lib/routes";

export function useStartLinks() {
  const { data: session } = useSession();
  return {
    start: session
      ? { href: routes.home, label: "내 홈으로" }
      : { href: routes.profile, label: "로그인 없이 시작하기" },
  };
}
