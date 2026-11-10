"use client";

// 메인의 시작 버튼이 갈 곳: 로그인했으면 내 홈, 조건을 저장했으면 바로 공고 목록
import { useSession } from "@/features/auth/session";
import { useConditions } from "@/features/conditions/store";
import { profileThen, routes } from "@/lib/routes";

export function useStartLinks() {
  const session = useSession().data;
  const conditions = useConditions();
  const hasConditions = conditions.status === "ready" && conditions.device !== null;
  return {
    /** 「로그인 없이 시작하기」: 로그인했으면 「내 홈으로」 (확인 중에는 그대로) */
    start: session
      ? { href: routes.home, label: "내 홈으로" }
      : { href: routes.profile, label: "로그인 없이 시작하기" },
    /** 「살 곳을 찾아요」: 조건이 있으면 공고 목록, 없으면 조건 입력 뒤 공고 목록 */
    homes: hasConditions ? routes.homes : profileThen(routes.homes),
  };
}
