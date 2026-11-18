"use client";

import { History } from "lucide-react";
import { useNoticeVersions } from "@/features/notice/versions";
import { cn } from "@/shared/lib/cn";

/**
 * 서비스 반영 이력: 첫 반영·정정·최근 반영을 보여줘요.
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
          정보 반영·정정 이력
        </h2>
        <span className="text-text-sub text-[14px] leading-[1.6]">
          서비스가 정보를 받은 날짜예요. 기관의 원문 발표일·갱신일과 다를 수 있어요. 접수 전에는
          원문을 다시 확인해 주세요.
        </span>
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
