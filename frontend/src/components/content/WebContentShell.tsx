import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const menu = [
  { href: routes.announcements, label: "공지사항" },
  { href: routes.faq, label: "자주 묻는 질문" },
  { href: routes.terms, label: "이용약관" },
  { href: routes.privacy, label: "개인정보처리방침" },
] as const;

export type ContentMenuHref = (typeof menu)[number]["href"];

/** 고객센터(공지 · FAQ · 약관 · 개인정보처리방침) PC 바탕: 고객센터 헤더 + 하단 링크 */
export function WebContentShell({
  current,
  children,
}: {
  current: ContentMenuHref;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <header className="border-line bg-surface sticky top-0 z-20 border-b border-solid">
        <div className="mx-auto box-border flex min-h-[68px] w-full max-w-[1200px] flex-wrap items-center justify-between gap-x-[24px] gap-y-[12px] px-[32px]">
          <div className="flex items-center gap-[14px]">
            <Link
              href={routes.main}
              aria-label="무주택자들 소개"
              className="text-text hover:text-text inline-flex items-center gap-[9px] no-underline"
            >
              <Logo size={30} />
              <span className="tracking-logo text-[19px] font-extrabold">무주택자들</span>
            </Link>
            <span className="border-line text-text-sub border-l border-solid pl-[14px] text-[16px] font-bold">
              고객센터
            </span>
          </div>
          <Link
            href={routes.home}
            className="bg-brand-soft text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center gap-[4px] rounded-sm px-[16px] text-[15px] font-bold no-underline"
          >
            서비스로 가기
            <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
          </Link>
        </div>
        <div className="mx-auto box-border w-full max-w-[1200px] px-[32px]">
          <nav aria-label="고객센터 메뉴" className="flex flex-wrap gap-x-[24px] gap-y-[4px]">
            {menu.map((m) => {
              const active = m.href === current;
              return (
                <Link
                  key={m.href}
                  href={m.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-[52px] items-center text-[16px] no-underline",
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

      {children}

      <footer className="border-line bg-surface border-t border-solid">
        <div className="mx-auto box-border flex w-full max-w-[1200px] flex-wrap justify-between gap-x-[24px] gap-y-[16px] px-[32px] pt-[32px] pb-[44px]">
          <span className="text-text-sub text-[14px]">
            © [회사명] · 공고·정책 정보는 각 기관의 원문을 기준으로 해요
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
