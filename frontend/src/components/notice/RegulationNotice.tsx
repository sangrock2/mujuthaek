"use client";

import { Badge } from "@/components/ui/Badge";
import { useNoticeRegulation } from "@/features/notice/regulation";
import { cn } from "@/lib/cn";

/**
 * 공고 지역이 규제지역(투기과열지구 · 조정대상지역 · 투기지역)이면 요약 아래에 안내를 붙여요. 아니면 아무것도 그리지 않아요.
 * 판정 결과는 바꾸지 않는 참고 안내예요
 */
export function RegulationNotice({
  noticeId,
  variant,
}: {
  noticeId: string;
  variant: "web" | "mobile";
}) {
  const r = useNoticeRegulation(noticeId);
  if (!r) return null;
  const web = variant === "web";
  return (
    <div
      role="note"
      aria-label="규제지역 안내"
      className={cn(
        "bg-bg flex flex-col gap-[8px]",
        web ? "rounded-tile px-[18px] py-[16px]" : "rounded-control px-[14px] py-[12px]",
      )}
    >
      <span className="flex flex-wrap items-center gap-[6px]">
        {r.kinds.map((k) => (
          <Badge key={k} tone="check" size={web ? "md" : "sm"}>
            {k}
          </Badge>
        ))}
        <span className={cn("font-bold", web ? "text-[15px]" : "text-[14px]")}>
          {r.partial ? "공고 지역 일부가 규제지역이에요" : "규제지역 공고예요"}
        </span>
      </span>
      {r.partial && (
        <span className="text-text-sub text-[13px] leading-[1.5]">{r.areas.join(" / ")}</span>
      )}
      <ul
        className={cn(
          "text-text-sub m-0 flex list-none flex-col gap-[4px] p-0 leading-[1.6]",
          web ? "text-[14px]" : "text-[13px]",
        )}
      >
        {r.guidance.map((g) => (
          <li key={g}>{g}</li>
        ))}
      </ul>
    </div>
  );
}
