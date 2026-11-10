import Link from "next/link";
import { Search, User } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Segment } from "@/components/ui/Segment";
import { cn } from "@/lib/cn";
import { routes, type Mode } from "@/lib/routes";
import { AlertsBell } from "./AlertsBell";
import { modeSegment, webMenu } from "./nav";

type WebHeaderProps = {
  mode?: Mode;
  /** 현재 메뉴 href. 없으면 강조 없음 */
  current?: string;
  /** 검색 · 알림 · 내 정보 화면이면 오른쪽 아이콘을 현재 화면으로 강조 */
  active?: HeaderIcon;
};

export type HeaderIcon = "search" | "alerts" | "me";

const iconLink = "inline-flex size-[44px] items-center justify-center rounded-sm";
const iconTone = (on: boolean) =>
  on ? "bg-brand-soft text-brand hover:text-brand" : "text-text-sub hover:text-text-sub";

export function WebHeader({ mode = "home", current, active }: WebHeaderProps) {
  return (
    <header className="border-line bg-surface sticky top-0 z-20 border-b border-solid">
      <div className="mx-auto box-border flex min-h-[68px] w-full max-w-[1200px] flex-wrap items-center justify-between gap-x-[28px] gap-y-[12px] px-[32px]">
        <div className="flex flex-wrap items-center gap-x-[28px] gap-y-[12px]">
          <Link
            href={routes.main}
            aria-label="무주택자들 소개"
            className="text-text hover:text-text inline-flex items-center gap-[9px] no-underline"
          >
            <Logo size={30} />
            <span className="tracking-logo text-[19px] font-extrabold">무주택자들</span>
          </Link>
          <Segment items={modeSegment(mode)} />
          <nav aria-label="주 메뉴" className="flex flex-wrap gap-[2px]">
            {webMenu[mode].map((item) => {
              const isCurrent = item.href === current;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isCurrent ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-[44px] items-center px-[12px] text-[16px] no-underline",
                    isCurrent
                      ? "text-text hover:text-text font-bold"
                      : "text-text-sub hover:text-text-sub font-medium",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-[4px]">
          <Link
            href={routes.search}
            aria-label="검색"
            aria-current={active === "search" ? "page" : undefined}
            className={cn(iconLink, iconTone(active === "search"))}
          >
            <Search size={22} aria-hidden />
          </Link>
          <AlertsBell
            className={cn(iconLink, iconTone(active === "alerts"))}
            current={active === "alerts"}
          />
          <Link
            href={routes.me}
            aria-label="내 정보"
            className="rounded-pill bg-brand-soft text-brand ml-[4px] inline-flex size-[36px] items-center justify-center"
          >
            <User size={20} aria-hidden />
          </Link>
        </div>
      </div>
    </header>
  );
}
