"use client";

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
import { useTerms } from "@/features/content/queries";
import { routes } from "@/lib/routes";

export function WebTerms() {
  const { data } = useTerms();

  return (
    <WebContentShell current={routes.terms}>
      <WebContentMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <WebContentTitle title="이용약관" sub={data.effective} />
          <WebVersionSelect label="지난 약관" versions={data.versions} />
        </div>
        <div className="flex flex-wrap items-start gap-[24px]">
          <WebLegalToc sections={data.sections} />
          <WebLegalArticle>
            <div className="bg-bg flex flex-col gap-[6px] rounded-[18px] px-[22px] py-[18px]">
              <span className="text-text text-[16px] font-extrabold">한눈에 보기</span>
              <span className="text-[15px] leading-[1.7]">{data.summary.web}</span>
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
