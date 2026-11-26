import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Logo } from "@/shared/brand/Logo";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

const menu = [
  { href: routes.announcements, label: "공지사항" },
  { href: routes.faq, label: "자주 묻는 질문" },
  { href: routes.howItWorks, label: "어떻게 만들었나요" },
  { href: routes.terms, label: "이용약관" },
  { href: routes.privacy, label: "개인정보처리방침" },
] as const;

export type ContentMenuHref = (typeof menu)[number]["href"];

export function CustomerCenterHeader({
  current,
  sticky = false,
}: {
  current: ContentMenuHref;
  sticky?: boolean;
}) {
  return (
    <header
      className={cn("border-line bg-surface border-b border-solid", sticky && "sticky top-0 z-20")}
    >
      <div className="mx-auto grid w-full max-w-[1200px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 px-4 pb-1 lg:min-h-[64px] lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:gap-x-5 lg:px-8 lg:pb-0">
        <div className="flex min-h-[54px] items-center gap-2 whitespace-nowrap">
          <Link
            href={routes.main}
            aria-label="무주택자들 소개"
            className="text-text hover:text-text inline-flex items-center gap-2 no-underline"
          >
            <Logo size={30} />
            <span className="tracking-logo text-base font-extrabold">무주택자들</span>
          </Link>
          <span className="border-line text-text-sub border-l pl-2 text-xs font-semibold">
            고객센터
          </span>
        </div>
        <nav
          aria-label="고객센터 메뉴"
          className="col-span-2 row-start-2 flex min-w-0 flex-wrap gap-0.5 lg:col-span-1 lg:row-auto lg:gap-1"
        >
          {menu.map((m) => {
            const active = m.href === current;
            return (
              <Link
                key={m.href}
                href={m.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-pill inline-flex min-h-11 shrink-0 items-center px-1.5 text-xs whitespace-nowrap no-underline lg:min-h-9 lg:px-3.5 lg:text-[13px]",
                  active
                    ? "bg-brand-soft text-brand-strong hover:text-brand-strong font-bold"
                    : "text-text-sub hover:bg-fill hover:text-text font-medium",
                )}
              >
                {m.label}
              </Link>
            );
          })}
        </nav>
        <Link
          href={routes.home}
          className="bg-brand rounded-pill col-start-2 row-start-1 inline-flex min-h-11 items-center gap-1 px-3 text-xs font-bold whitespace-nowrap text-white no-underline hover:text-white lg:col-start-3 lg:min-h-9"
        >
          서비스로 가기
          <ChevronRight size={14} aria-hidden />
        </Link>
      </div>
    </header>
  );
}

/** 고객센터(공지 · FAQ · 만든 방법 · 약관 · 개인정보처리방침) PC 바탕: 고객센터 헤더 + 하단 링크 */
export function WebContentShell({
  current,
  children,
  className,
}: {
  current: ContentMenuHref;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("stitch-surface bg-bg text-text flex min-h-screen w-full flex-col", className)}
    >
      <CustomerCenterHeader current={current} sticky />

      {children}

      <footer className="border-line bg-surface border-t border-solid">
        <div className="mx-auto box-border flex w-full max-w-[1200px] flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-3 lg:px-8">
          <span className="text-text-sub text-xs">
            © 무주택자들 · 공고·정책 정보는 각 기관의 원문을 기준으로 해요
          </span>
          <nav aria-label="하단 링크" className="flex flex-wrap gap-x-[20px] gap-y-[4px]">
            {menu.map((m) => (
              <Link
                key={m.href}
                href={m.href}
                className={cn(
                  "inline-flex min-h-9 items-center text-xs no-underline",
                  m.href === current
                    ? "text-text hover:text-text font-bold"
                    : "text-text-sub hover:text-text-sub",
                )}
              >
                {m.label}
              </Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}

/** 고객센터 본문 영역 (PC) */
export function WebContentMain({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className={cn(
        "mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-col gap-6 px-4 pt-6 pb-10 lg:px-8 lg:pt-8 lg:pb-14",
        className,
      )}
    >
      {children}
    </main>
  );
}

/** 고객센터 페이지 제목 + 설명 (PC) */
export function WebContentTitle({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="flex flex-col gap-[6px]">
      <h1 className="tracking-h1 m-0 text-[26px] font-extrabold lg:text-[34px]">{title}</h1>
      <span className="text-text-sub text-[16px]">{sub}</span>
    </div>
  );
}
