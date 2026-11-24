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
      <div className="mx-auto box-border flex min-h-[60px] w-full max-w-[1200px] flex-wrap items-center justify-between gap-2 px-4 md:min-h-[68px] md:gap-x-6 md:px-8">
        <div className="flex items-center gap-2 md:gap-[14px]">
          <Link
            href={routes.main}
            aria-label="무주택자들 소개"
            className="text-text hover:text-text inline-flex items-center gap-[9px] no-underline"
          >
            <Logo size={30} />
            <span className="tracking-logo text-[16px] font-extrabold md:text-[19px]">
              무주택자들
            </span>
          </Link>
          <span className="border-line text-text-sub border-l border-solid pl-2 text-[13px] font-bold md:pl-[14px] md:text-[16px]">
            고객센터
          </span>
        </div>
        <Link
          href={routes.home}
          className="bg-brand-soft text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center gap-1 rounded-sm px-2 text-[12px] font-bold no-underline md:px-4 md:text-[15px]"
        >
          서비스로 가기
          <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
        </Link>
      </div>
      <div className="mx-auto box-border w-full max-w-[1200px] px-4 md:px-8">
        <nav aria-label="고객센터 메뉴" className="flex flex-wrap gap-x-3 md:gap-x-6">
          {menu.map((m) => {
            const active = m.href === current;
            return (
              <Link
                key={m.href}
                href={m.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-[36px] items-center text-[13px] no-underline sm:min-h-[44px] md:min-h-[52px] md:text-[16px]",
                  active
                    ? "text-text hover:text-text font-bold shadow-[inset_0_-3px_0_var(--color-brand)]"
                    : "text-text-sub hover:text-text-sub font-medium",
                )}
              >
                {m.label}
              </Link>
            );
          })}
        </nav>
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
        <div className="mx-auto box-border flex w-full max-w-[1200px] flex-wrap justify-between gap-x-[24px] gap-y-[16px] px-[32px] pt-[32px] pb-[44px]">
          <span className="text-text-sub text-[14px]">
            © 무주택자들 · 공고·정책 정보는 각 기관의 원문을 기준으로 해요
          </span>
          <nav aria-label="하단 링크" className="flex flex-wrap gap-x-[20px] gap-y-[4px]">
            {menu.map((m) => (
              <Link
                key={m.href}
                href={m.href}
                className={cn(
                  "inline-flex min-h-[44px] items-center text-[14px] no-underline",
                  m.href === routes.privacy
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
        "mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-col gap-[24px] px-[32px] pt-[40px] pb-[72px]",
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
      <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">{title}</h1>
      <span className="text-text-sub text-[16px]">{sub}</span>
    </div>
  );
}
