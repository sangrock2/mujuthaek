"use client";

import Link from "next/link";
import { MLegalMain, MLegalSection, MLegalTabs } from "@/components/content/Legal";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { usePrivacy } from "@/features/content/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

export function MPrivacy() {
  const { data } = usePrivacy();

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <MBackHeader title="개인정보처리방침" backHref={routes.me} />
      <MLegalMain>
        <MLegalTabs current="privacy" />
        <label className="text-text-sub flex items-center justify-between gap-[8px] text-[14px]">
          {data.effective}
          <select className="bg-fill text-text min-h-[40px] rounded-[10px] border-0 px-[10px] text-[14px] font-semibold">
            {data.versions.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <Link
          href={data.upcoming.href}
          className="rounded-control bg-check-bg text-check-text hover:text-check-text px-[14px] py-[12px] text-[14px] leading-[1.5] font-bold no-underline"
        >
          {data.upcoming.mobile}
        </Link>
        <div className="flex flex-col gap-[8px]">
          {data.highlights.map((h) => (
            <div
              key={h.title}
              className={cn(
                "rounded-control flex flex-col gap-[2px] px-[14px] py-[12px]",
                h.brand ? "bg-brand-soft" : "bg-bg",
              )}
            >
              <span
                className={cn(
                  "text-[15px] font-extrabold",
                  h.brand ? "text-brand-strong" : "text-text",
                )}
              >
                {h.title}
              </span>
              <span className={cn("text-[13px] leading-[1.6]", h.brand && "text-text")}>
                {h.text}
              </span>
            </div>
          ))}
        </div>
        {data.sections.map((s, i) => (
          <MLegalSection key={s.id} section={s} open={i === 0} />
        ))}
        <span className="text-text-sub text-[13px]">{data.closing.web}</span>
      </MLegalMain>
    </div>
  );
}
