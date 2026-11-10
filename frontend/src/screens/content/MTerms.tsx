"use client";

import { MLegalMain, MLegalSection, MLegalTabs } from "@/components/content/Legal";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { useTerms } from "@/features/content/queries";
import { routes } from "@/lib/routes";

export function MTerms() {
  const { data } = useTerms();

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <MBackHeader title="이용약관" backHref={routes.me} />
      <MLegalMain>
        <MLegalTabs current="terms" />
        <label className="text-text-sub flex items-center justify-between gap-[8px] text-[14px]">
          {data.effective}
          <select className="bg-fill text-text min-h-[40px] rounded-[10px] border-0 px-[10px] text-[14px] font-semibold">
            {data.versions.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <div className="bg-bg rounded-tile flex flex-col gap-[4px] p-[16px]">
          <span className="text-text text-[15px] font-extrabold">한눈에 보기</span>
          <span className="text-[14px] leading-[1.7]">{data.summary.mobile}</span>
        </div>
        {data.sections.map((s, i) => (
          <MLegalSection key={s.id} section={s} open={i === 0} />
        ))}
        <span className="text-text-sub text-[13px]">{data.closing.web}</span>
      </MLegalMain>
    </div>
  );
}
