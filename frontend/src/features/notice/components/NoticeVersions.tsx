"use client";

import { History } from "lucide-react";
import { useNoticeVersions } from "@/features/notice/versions";
import { cn } from "@/shared/lib/cn";

/**
 * 정정 이력: 정정 공고나 바뀐 내용이 있을 때만 보여요. 지금 화면은 마지막 버전 기준이에요.
 * 바뀐 항목은 목록에 보이는 값(이름 · 기관 · 지역 · 접수일 · 요약)만 알 수 있어요
 */
export function NoticeVersions({
  noticeId,
  variant,
}: {
  noticeId: string;
  variant: "web" | "mobile";
}) {
  const versions = useNoticeVersions(noticeId);
  if (!versions.length) return null;
  const web = variant === "web";
  const last = versions.length - 1;
  return (
    <section
      aria-labelledby="versions-h"
      className={cn(
        "bg-surface flex flex-col",
        web
          ? "rounded-card-lg gap-[12px] px-[30px] py-[24px]"
          : "rounded-card mx-[16px] gap-[10px] px-[20px] py-[16px]",
      )}
    >
      <div className="flex flex-col gap-[2px]">
        <h2
          id="versions-h"
          className={cn(
            "m-0 flex items-center gap-[6px] font-extrabold",
            web ? "tracking-title text-[19px]" : "text-[17px]",
          )}
        >
          <History size={web ? 20 : 18} className="text-text-sub" aria-hidden />
          정정 이력
        </h2>
        <span className="text-text-sub text-[14px]">지금 보이는 내용은 마지막 공고 기준이에요</span>
      </div>
      <ol className="m-0 flex list-none flex-col gap-[8px] p-0">
        {versions.map((v, i) => (
          <li key={v.version} className="flex items-baseline gap-[10px]">
            <span
              aria-hidden
              className={cn(
                "rounded-pill size-[8px] flex-none translate-y-[-1px]",
                i === last ? "bg-brand" : "bg-placeholder-icon",
              )}
            />
            <span className="flex min-w-0 flex-col gap-[1px]">
              <span className={cn("font-bold", web ? "text-[15px]" : "text-[14px]")}>
                {v.label}
                <span className="text-text-sub font-medium"> · {v.day}</span>
              </span>
              {v.changed.length > 0 && (
                <span className="text-text-sub text-[13px]">바뀐 것: {v.changed.join(" · ")}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
