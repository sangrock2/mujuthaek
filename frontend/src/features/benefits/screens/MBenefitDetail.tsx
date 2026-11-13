"use client";

import { useDetailTitle } from "@/shared/lib/useDetailTitle";

import { QueryFeedback } from "@/shared/states/QueryFeedback";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { ReportButton } from "@/features/report/components/ReportButton";
import { MBackHeader, MBottomActions } from "@/shared/layout/MBackHeader";
import { MPage } from "@/shared/layout/Responsive";
import { Badge, VerdictBadge } from "@/shared/ui/Badge";
import { CheckAction } from "@/shared/ui/CheckAction";
import { useBenefit, applyHref } from "@/features/benefits/queries";
import { track } from "@/shared/lib/analytics";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

const eligLabel = { ok: "충족", check: "확인 필요", no: "해당 안 돼요" } as const;
const eligTone = { ok: "ok", check: "check", no: "neutral" } as const;

export function MBenefitDetail({ id }: { id: string }) {
  const { data: b, loading, error } = useBenefit(id);
  useDetailTitle(b?.title);
  if (!b) {
    return (
      <MPage>
        <MBackHeader title="혜택" backHref={routes.benefits} />
        {(loading || error) && <QueryFeedback error={error} label="혜택" queryKey={["benefits"]} />}
      </MPage>
    );
  }

  return (
    <MPage>
      <MBackHeader title={b.title} backHref={routes.benefits} />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[16px] pb-[24px]"
      >
        <section className="rounded-card bg-surface flex flex-col gap-[12px] px-[20px] py-[22px]">
          <div className="flex flex-wrap gap-[6px]">
            <VerdictBadge verdict={b.verdict} size="md" />
            <Badge tone="neutral" size="md">
              {b.cat}
            </Badge>
            {b.budget && (
              <Badge tone="neutral" size="md" className="font-semibold">
                내 집 &apos;준비할 돈&apos;에 반영
              </Badge>
            )}
          </div>
          <h2 className="tracking-h1 m-0 text-[24px] font-extrabold">{b.title}</h2>
          <span className="text-text-sub text-[14px]">{b.org}</span>
          <dl className="m-0 grid grid-cols-2 gap-[8px]">
            <div className="rounded-tile bg-bg p-[14px]">
              <dt className="text-text-sub text-[12px]">지원 내용</dt>
              <dd className="m-0 mt-[4px] text-[15px] leading-[1.4] font-extrabold">{b.amount}</dd>
            </div>
            <div className="rounded-tile bg-bg p-[14px]">
              <dt className="text-text-sub text-[12px]">신청 기한</dt>
              <dd className="m-0 mt-[4px] text-[15px] leading-[1.4] font-extrabold">
                {b.deadline}
              </dd>
            </div>
          </dl>
          {b.overlap && (
            <div className="rounded-control bg-check-bg text-check-text px-[14px] py-[12px] text-[14px] leading-[1.5] font-semibold">
              <span className="font-extrabold">함께 못 받는 혜택</span> · {b.overlap}
            </div>
          )}
          {b.budget && (
            <Link
              href={routes.loans}
              className="rounded-control bg-brand-soft text-text hover:text-text flex min-h-[56px] items-center justify-between gap-[10px] px-[14px] py-[12px] no-underline"
            >
              <span className="flex flex-col gap-[2px]">
                <span className="text-brand-strong text-[15px] font-extrabold">
                  대출 자격 확인하기
                </span>
                <span className="text-text-sub text-[13px]">
                  정확한 소득 · 순자산으로 상품마다 받을 수 있는지 봐요
                </span>
              </span>
              <ChevronRight size={18} className="text-brand-strong flex-none" aria-hidden />
            </Link>
          )}
        </section>

        <section
          aria-labelledby="el-h"
          className="rounded-card bg-surface flex flex-col px-[20px] pt-[18px] pb-[8px]"
        >
          <div className="flex items-center justify-between">
            <h3 id="el-h" className="m-0 text-[17px] font-extrabold">
              내 자격
            </h3>
            {b.sourceUrl && (
              <a
                href={b.sourceUrl}
                target="_blank"
                onClick={() => track("notice_source_open", { notice_kind: "benefit", via: "site" })}
                rel="noreferrer"
                className="inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
              >
                근거 원문
              </a>
            )}
          </div>
          {b.reason && <p className="text-text-sub m-0 pb-[4px] text-[13px]">{b.reason}</p>}
          {b.elig.length === 0 && (
            <p className="text-text-sub m-0 py-[12px] text-[15px]">
              원문에 적힌 자격 조건이 없어요
            </p>
          )}
          {b.elig.map((e, i) => (
            <div
              key={`${i}-${e.label}`}
              className={cn(
                "flex items-center justify-between gap-[10px] py-[12px] text-[15px]",
                i < b.elig.length - 1 && "border-line-soft border-b border-solid",
              )}
            >
              <span className="flex min-w-0 flex-col gap-[2px]">
                <span>{e.label}</span>
                {e.reason && <span className="text-text-sub text-[13px]">{e.reason}</span>}
              </span>
              {e.result === "check" ? (
                <CheckAction inputHref={e.inputHref} web={false} />
              ) : (
                <Badge tone={eligTone[e.result]} size="md" className="flex-none py-[3px]">
                  {eligLabel[e.result]}
                </Badge>
              )}
            </div>
          ))}
        </section>

        <section
          aria-labelledby="how-h"
          className="rounded-card bg-surface flex flex-col gap-[12px] px-[20px] py-[18px]"
        >
          <h3 id="how-h" className="m-0 text-[17px] font-extrabold">
            신청 방법
          </h3>
          {b.how.length === 0 && (
            <p className="text-text-sub m-0 text-[15px]">정책 원문의 신청 방법을 확인해 주세요</p>
          )}
          <ol className="m-0 flex list-none flex-col gap-[10px] p-0">
            {b.how.map((text, i) => (
              <li key={text} className="flex items-center gap-[10px] text-[15px]">
                <span className="rounded-badge bg-brand-soft text-brand-strong flex size-[26px] flex-none items-center justify-center text-[13px] font-extrabold">
                  {i + 1}
                </span>
                {text}
              </li>
            ))}
          </ol>
          <span className="text-text-sub text-[14px]">필요 서류 · {b.docs}</span>
        </section>
        <ReportButton target={{ kind: "benefit", id: b.id }} screen="혜택 상세 (모바일)" />
      </main>
      {(b.policyUrl || applyHref(b)) && (
        <MBottomActions>
          {/* 주소가 없으면 누를 수 없는 버튼이 되어서 숨겨요 (웹과 같아요) */}
          {b.policyUrl && (
            <a
              href={b.policyUrl}
              target="_blank"
              onClick={() => track("notice_source_open", { notice_kind: "benefit", via: "site" })}
              rel="noreferrer"
              className="rounded-control bg-fill text-text hover:text-text flex min-h-[54px] min-w-0 flex-[1_1_0] items-center justify-center text-[15px] font-bold no-underline"
            >
              정책 원문
            </a>
          )}
          {applyHref(b) && (
            <a
              href={applyHref(b)}
              target="_blank"
              rel="noreferrer"
              className="rounded-control bg-brand flex min-h-[54px] min-w-0 flex-[2_1_0] items-center justify-center text-[16px] font-extrabold text-white no-underline hover:text-white"
            >
              신청하러 가기
            </a>
          )}
        </MBottomActions>
      )}
    </MPage>
  );
}
