"use client";

import Link from "next/link";
import { useState } from "react";
import { useBenefitDetailQuery } from "@/features/benefits/api";
import type { NoticeBenefit } from "@/features/notice/mocks/notice";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { VerdictBadge } from "@/shared/ui/Badge";

const groups = [
  { result: "ok", title: "내 조건과 맞아요" },
  { result: "check", title: "추가로 확인할 조건" },
  { result: "no", title: "현재 조건과 달라요" },
] as const;

function BenefitConditions({ id }: { id: string }) {
  const { data, loading, error, evaluationPending, evaluationError } = useBenefitDetailQuery(
    id,
    undefined,
  );
  return (
    <div className="flex flex-col gap-3 pt-1 pb-3">
      {error || evaluationError ? (
        <p role="status">조건을 불러오지 못했어요. 혜택 상세에서 다시 확인해 주세요.</p>
      ) : loading || evaluationPending ? (
        <p role="status">내 조건과 비교하고 있어요.</p>
      ) : data ? (
        <>
          {data.reason && <p>{data.reason}</p>}
          {data.elig.length === 0 && !data.reason && (
            <p>비교할 자격 조건이 없어요. 신청 전 기관 원문을 확인해 주세요.</p>
          )}
          {groups.map(({ result, title }) => {
            const conditions = data.elig.filter((condition) => condition.result === result);
            if (!conditions.length) return null;
            return (
              <div key={result}>
                <p className="text-text font-bold">{title}</p>
                <ul className="mt-1 list-disc space-y-1 pl-4">
                  {conditions.slice(0, 2).map((condition, index) => (
                    <li key={index}>
                      {condition.label}
                      {condition.reason && <span className="block">{condition.reason}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </>
      ) : null}
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-bold">
        <Link href={routes.benefit(id)} className="text-brand underline underline-offset-2">
          혜택 상세에서 전체 조건 보기
        </Link>
        {data?.sourceUrl && (
          <a
            href={data.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="text-brand underline underline-offset-2"
          >
            기관 원문 보기
          </a>
        )}
      </div>
    </div>
  );
}

export function NoticeBenefitRow({
  benefit,
  mobile,
  divided,
}: {
  benefit: NoticeBenefit;
  mobile?: boolean;
  divided: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn("py-3", divided && "border-line-soft border-b border-solid")}>
      <Link
        href={routes.benefit(benefit.id)}
        className="text-text hover:text-text flex items-center justify-between gap-3 no-underline"
      >
        <span className="flex flex-col gap-[2px]">
          <span className={cn("font-bold", mobile ? "text-[15px]" : "text-[16px]")}>
            {benefit.title}
          </span>
          <span className="text-text-sub text-[13px]">{benefit.desc}</span>
        </span>
        <VerdictBadge
          verdict={benefit.verdict}
          size={mobile ? "xs" : undefined}
          className="flex-none"
        />
      </Link>
      {!USE_MOCKS && (
        <details
          className="text-text-sub text-[13px]"
          onToggle={(event) => setOpen(event.currentTarget.open)}
        >
          <summary className="text-brand w-fit cursor-pointer py-2 font-bold">
            맞는 조건과 확인할 조건
          </summary>
          {open && <BenefitConditions id={benefit.id} />}
        </details>
      )}
    </div>
  );
}
