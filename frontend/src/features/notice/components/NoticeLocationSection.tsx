"use client";

import type { NoticeSite } from "@/features/notice/mocks/notice";
import { cn } from "@/shared/lib/cn";
import { SitesMap } from "./SitesMap";

/** 호별 주택 목록이 없어도 확인된 단지 위치는 따로 보여줘요. */
export function NoticeLocationSection({
  sites,
  mobile = false,
}: {
  sites: NoticeSite[];
  mobile?: boolean;
}) {
  if (!sites.some((site) => site.lat !== null && site.lng !== null)) return null;
  return (
    <section
      aria-label="공고 위치"
      className={cn(
        "bg-surface flex flex-col gap-[12px]",
        mobile ? "rounded-card mx-[16px] p-[20px]" : "rounded-card-lg p-[24px]",
      )}
    >
      <h3 className="tracking-title m-0 text-[18px] font-extrabold">단지 위치</h3>
      <p className="text-text-sub m-0 text-[14px] leading-[1.6]">
        호별 주택 목록과 별도로 확인한 위치예요. 신청 전 공고 원문의 주소를 확인해 주세요.
      </p>
      <SitesMap sites={sites} className={mobile ? "h-[240px] w-full" : "h-[400px] w-full"} />
    </section>
  );
}
