"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ClipboardCheck,
  Database,
  ExternalLink,
  Flag,
  History,
  Users,
  LayoutDashboard,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { useAdminMe } from "@/components/admin/AdminGuard";
import { canOpen, PERMISSION_INFO, ROUTE_PERMISSIONS } from "@/features/admin/permissions";
import { useAdminCounts } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { AdminCounts } from "@/mocks/admin";

type MenuItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** 여러 개면 받은 숫자만 더해요 (권한이 없어 못 받은 숫자는 빼요) */
  count?: { keys: (keyof AdminCounts)[]; tone: "wait" | "fail" };
};

const menu: MenuItem[] = [
  { href: routes.admin, label: "개요", icon: LayoutDashboard },
  { href: routes.adminUsers, label: "회원", icon: Users },
  {
    href: routes.adminSources,
    label: "수집 현황",
    icon: Database,
    count: { keys: ["sourceIssues"], tone: "fail" },
  },
  {
    href: routes.adminReview,
    label: "검수",
    icon: ClipboardCheck,
    count: { keys: ["reviewPending"], tone: "wait" },
  },
  {
    href: routes.adminReports,
    label: "제보·신고",
    icon: Flag,
    count: { keys: ["newReports", "chatReports", "policyDuplicates"], tone: "wait" },
  },
  { href: routes.adminTraffic, label: "트래픽", icon: Activity },
  { href: routes.adminCriteria, label: "기준값", icon: SlidersHorizontal },
  { href: routes.adminActivity, label: "처리 기록", icon: History },
];

/** 메뉴 숫자: 받은 숫자만 더하고, 하나도 못 받았으면 null (0으로 보이지 않게) */
function menuCount(counts: AdminCounts, keys: (keyof AdminCounts)[]) {
  const got = keys.map((k) => counts[k]).filter((n): n is number => n != null);
  return got.length ? got.reduce((a, b) => a + b, 0) : null;
}

/** 관리자 화면 틀: 왼쪽 232px 어두운 사이드바 + 본문 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: counts } = useAdminCounts();
  const me = useAdminMe(); // AdminGuard가 먼저 받아 둬요
  const permissions = me.data?.permissions ?? [];
  const allowed = menu.filter((m) => canOpen(permissions, m.href));
  const pageAllowed = canOpen(permissions, pathname);

  return (
    <div className="bg-bg text-text box-border flex min-h-screen w-full flex-wrap">
      <aside
        aria-label="관리자 메뉴"
        className="bg-brand-deep box-border flex flex-col gap-[28px] px-[16px] py-[24px] text-white"
        style={{ flex: "1 1 232px" }}
      >
        <Link
          href={routes.admin}
          className="inline-flex items-center gap-[9px] px-[8px] text-white no-underline hover:text-white"
        >
          <Logo size={30} inverted />
          <span className="tracking-logo text-[18px] font-extrabold">무주택자들</span>
          <span className="rounded-tag text-brand-deep-text-3 bg-white/12 px-[7px] py-[3px] text-[12px] font-bold">
            관리자
          </span>
        </Link>
        <nav aria-label="관리자 메뉴" className="flex flex-col gap-[4px]">
          {allowed.map(({ href, label, icon: Icon, count }) => {
            const current = pathname === href;
            const n = count ? menuCount(counts, count.keys) : null;
            return (
              <Link
                key={href}
                href={href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "flex min-h-[46px] items-center gap-[10px] rounded-sm px-[12px] text-[15px] no-underline",
                  current
                    ? "bg-white/10 font-bold text-white hover:text-white"
                    : "text-brand-deep-text hover:text-brand-deep-text font-medium",
                )}
              >
                <Icon size={20} aria-hidden />
                <span className="flex-1">{label}</span>
                {count && n != null && (
                  <span
                    className={cn(
                      "rounded-pill px-[8px] py-[2px] text-[12px] font-extrabold",
                      count.tone === "fail"
                        ? "bg-danger-bg text-danger-text"
                        : "bg-check-bg text-check-text",
                    )}
                  >
                    {n}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        <span className="flex-1" />
        <div className="flex flex-col gap-[6px] border-t border-solid border-white/12 pt-[16px]">
          <Link
            href={routes.home}
            className="text-brand-deep-text hover:text-brand-deep-text flex min-h-[44px] items-center gap-[8px] px-[12px] text-[14px] font-semibold no-underline"
          >
            <ExternalLink size={18} aria-hidden />
            서비스 화면 보기
          </Link>
          <span className="text-brand-deep-text px-[12px] text-[13px]">
            {me.data?.role === "SUPER_ADMIN" ? "최상위 관리자" : "운영자"}{" "}
            {me.data?.nickname ?? "이름 없음"}
          </span>
        </div>
      </aside>

      {/* 디자인의 버튼·입력칸은 브라우저 기본 자간(normal)을 써요 */}
      <main
        className="box-border flex min-w-0 flex-col gap-[20px] px-[40px] pt-[36px] pb-[56px] [&_button,&_input,&_select,&_textarea]:tracking-normal"
        style={{ flex: "999 1 640px" }}
      >
        {pageAllowed ? (
          children
        ) : (
          <section
            role="alert"
            className="rounded-card bg-surface flex flex-col gap-[8px] px-[24px] py-[28px]"
          >
            <h1 className="m-0 text-[20px] font-extrabold">이 화면의 권한이 없어요</h1>
            <p className="text-text-sub m-0 text-[15px]">
              필요한 권한:{" "}
              {(ROUTE_PERMISSIONS[pathname] ?? [])
                .map((p) => PERMISSION_INFO[p].label)
                .join(" 또는 ")}{" "}
              · 「권한 부여」를 가진 관리자에게 요청해 주세요.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}

/** 페이지 제목 + 설명 */
export function AdminTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex flex-col gap-[6px]">
      <h1 className="tracking-h1 m-0 text-[30px] font-extrabold">{title}</h1>
      <span className="text-text-sub text-[15px]">{desc}</span>
    </div>
  );
}

/** 제목 줄: 왼쪽 제목, 오른쪽 탭·필터 */
export function AdminTitleRow({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-end justify-between gap-[12px]">{children}</div>;
}
