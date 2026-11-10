"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { ApiError, api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { ALL_PERMISSIONS, type AdminPermission } from "@/features/admin/permissions";
import { routes } from "@/lib/routes";

/** 관리자 화면의 내 권한 (GET /api/admin/me). 메뉴·버튼을 고르는 데만 써요. 실제 확인은 서버가 요청마다 해요 */
export type AdminMe = {
  id: string;
  nickname: string | null;
  /** 일반 관리자 · 최상위 관리자 */
  role: "ADMIN" | "SUPER_ADMIN";
  /** 쓸 수 있는 권한 (최상위는 전부) */
  permissions: AdminPermission[];
  /** 지금 관리자 화면을 쓸 수 있는지 (긴급 정지·이용 정지면 false) */
  active: boolean;
  /** 관리자 긴급 정지 중이면 그 내용 */
  freeze: { reason: string | null; at: string } | null;
};

/** 목업에서는 모든 권한을 가진 최상위 관리자로 봐요 */
const MOCK_ME: AdminMe = {
  id: "01a17000-0000-7000-8000-00000000ad01",
  nickname: null,
  role: "SUPER_ADMIN",
  permissions: ALL_PERMISSIONS,
  active: true,
  freeze: null,
};

/** 내 관리자 권한. 로그인 안 했으면 401, 관리자가 아니면 403으로 끝나요(다시 시도하지 않음) */
export function useAdminMe() {
  return useQuery({
    queryKey: ["admin", "me"],
    queryFn: () => (USE_MOCKS ? Promise.resolve(MOCK_ME) : api.get<AdminMe>("/api/admin/me")),
    retry: false,
    staleTime: 60_000,
  });
}

/**
 * 관리자만 관리자 화면을 보게 해요. 데이터는 서버가 막지만, 화면이 오류만 보이지 않게 먼저 확인해요.
 * 로그인 안 했으면 로그인 안내, 관리자가 아니면 「관리자만 볼 수 있어요」, 긴급 정지·이용 정지 중이면 그 안내를 보여 줘요.
 * 화면마다 필요한 권한은 AdminShell이 봐요.
 */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const me = useAdminMe();
  if (me.isPending) return <Notice title="권한을 확인하고 있어요" />;
  if (me.isError) {
    const status = me.error instanceof ApiError ? me.error.status : 0;
    if (status === 401) {
      return (
        <Notice
          title="로그인이 필요해요"
          text="관리자 계정으로 로그인한 뒤 다시 들어와 주세요."
          action={{ href: routes.login, label: "로그인하기" }}
        />
      );
    }
    if (status === 403) {
      return (
        <Notice
          title="관리자만 볼 수 있어요"
          text="관리자 권한이 필요한 화면이에요. 권한이 필요하면 관리자에게 요청해 주세요."
          action={{ href: routes.main, label: "처음 화면으로" }}
        />
      );
    }
    return (
      <Notice
        title="권한을 확인하지 못했어요"
        text="잠시 뒤 다시 시도해 주세요."
        action={{ href: routes.main, label: "처음 화면으로" }}
      />
    );
  }
  if (!me.data.active) {
    return (
      <Notice
        title={me.data.freeze ? "관리자 화면이 긴급 정지됐어요" : "관리자 화면을 쓸 수 없어요"}
        text={
          me.data.freeze
            ? `최상위 관리자가 모든 관리자의 작업을 잠시 멈췄어요${me.data.freeze.reason ? ` · ${me.data.freeze.reason}` : ""}. 풀리면 다시 쓸 수 있어요.`
            : "이용이 정지된 계정이에요. 관리자에게 문의해 주세요."
        }
        action={{ href: routes.main, label: "처음 화면으로" }}
      />
    );
  }
  return <>{children}</>;
}

function Notice({
  title,
  text,
  action,
}: {
  title: string;
  text?: string;
  action?: { href: string; label: string };
}) {
  return (
    <main className="bg-bg text-text flex min-h-screen items-center justify-center px-[16px]">
      <section
        role={action ? "alert" : "status"}
        className="rounded-card bg-surface flex w-full max-w-[420px] flex-col items-center gap-[12px] px-[28px] py-[32px] text-center"
      >
        {action && <ShieldAlert size={36} className="text-text-sub" aria-hidden />}
        <h1 className="m-0 text-[20px] font-extrabold">{title}</h1>
        {text && <p className="text-text-sub m-0 text-[15px] leading-[1.6]">{text}</p>}
        {action && (
          <Link
            href={action.href}
            className="rounded-control bg-brand mt-[8px] flex min-h-[48px] items-center px-[20px] text-[15px] font-bold text-white no-underline hover:text-white"
          >
            {action.label}
          </Link>
        )}
      </section>
    </main>
  );
}
