import Link from "next/link";
import { cn } from "@/lib/cn";
import type { Mode } from "@/lib/routes";
import { mobileTabs } from "./nav";

/** 모바일 하단 탭. 현재 탭은 초록 800 + 선 2.2 */
export function MTabBar({ mode = "home", current }: { mode?: Mode; current?: string }) {
  const tabs = mobileTabs[mode];
  return (
    <nav
      aria-label="하단 메뉴"
      className="border-line bg-surface sticky bottom-0 z-[2] mt-auto grid border-t border-solid px-[4px] pt-[4px] pb-[22px]"
      style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
    >
      {tabs.map(({ label, href, icon: Icon }) => {
        const active = href === current;
        return (
          <Link
            key={label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-[54px] flex-col items-center justify-center gap-[3px] text-[12px] no-underline",
              active
                ? "text-brand hover:text-brand font-extrabold"
                : "text-text-tertiary hover:text-text-tertiary font-semibold",
            )}
          >
            <Icon size={24} strokeWidth={active ? 2.2 : 1.8} aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
