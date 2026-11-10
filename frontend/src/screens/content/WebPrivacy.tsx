"use client";

import Link from "next/link";
import { ChevronRight, Info } from "lucide-react";
import {
  WebLegalArticle,
  WebLegalClosing,
  WebLegalSection,
  WebLegalToc,
  WebVersionSelect,
} from "@/components/content/Legal";
import {
  WebContentMain,
  WebContentShell,
  WebContentTitle,
} from "@/components/content/WebContentShell";
import { usePrivacy } from "@/features/content/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

export function WebPrivacy() {
  const { data } = usePrivacy();

  return (
    <WebContentShell current={routes.privacy}>
      <WebContentMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <WebContentTitle title="개인정보처리방침" sub={data.effective} />
          <WebVersionSelect label="다른 버전" versions={data.versions} />
        </div>

        <Link
          href={data.upcoming.href}
          className="bg-check-bg text-check-text hover:text-check-text flex flex-wrap items-center gap-x-[14px] gap-y-[8px] rounded-[18px] px-[20px] py-[16px] no-underline"
        >
          <Info size={20} aria-hidden />
          <span className="text-[15px] font-bold" style={{ flex: "1 1 300px" }}>
            {data.upcoming.web}
          </span>
          <span className="inline-flex items-center gap-[2px] text-[14px] font-bold">
            바뀌는 내용
            <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
          </span>
        </Link>

        <div className="flex flex-wrap items-start gap-[24px]">
          <WebLegalToc sections={data.sections} />
          <WebLegalArticle>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-[10px]">
              {data.highlights.map((h) => (
                <div
                  key={h.title}
                  className={cn(
                    "flex flex-col gap-[4px] rounded-[18px] px-[18px] py-[16px]",
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
                  <span className={cn("text-[14px] leading-[1.6]", h.brand && "text-text")}>
                    {h.text}
                  </span>
                </div>
              ))}
            </div>
            {data.sections.map((s) => (
              <WebLegalSection key={s.id} section={s} />
            ))}
            <WebLegalClosing>{data.closing.web}</WebLegalClosing>
          </WebLegalArticle>
        </div>
      </WebContentMain>
    </WebContentShell>
  );
}
