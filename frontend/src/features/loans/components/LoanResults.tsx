"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge, type BadgeTone } from "@/shared/ui/Badge";
import { FilterChip } from "@/shared/ui/Chip";
import {
  loanStatusLabel,
  loanTypeLabel,
  type LoanItem,
  type LoanStatus,
  type LoanType,
} from "@/features/loans/loan";
import type { LoanCheck } from "@/features/loans/useLoanCheck";
import { cn } from "@/shared/lib/cn";

type Props = { calc: LoanCheck; variant: "web" | "mobile" };

const statusTone: Record<LoanStatus, BadgeTone> = {
  ELIGIBLE: "ok",
  NEEDS_INPUT: "check",
  INELIGIBLE: "neutral",
};

type TypeFilter = "ALL" | LoanType;
const typeFilters: TypeFilter[] = ["ALL", "JEONSE", "MONTHLY_RENT", "PURCHASE"];

function Reasons({ item }: { item: LoanItem }) {
  if (item.status === "ELIGIBLE") {
    return (
      <p className="text-ok-text m-0 text-[14px] font-semibold">넣은 조건으로는 모두 맞아요</p>
    );
  }
  if (item.status === "INELIGIBLE") {
    return (
      <div className="flex flex-col gap-[4px]">
        <span className="text-text-sub text-[13px] font-bold">맞지 않는 조건</span>
        <ul className="m-0 flex list-disc flex-col gap-[2px] pl-[20px] text-[14px] leading-[1.55]">
          {item.failedConditions.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-[6px]">
      {item.checkReasons.length > 0 && (
        <div className="flex flex-col gap-[4px]">
          <span className="text-check-text text-[13px] font-bold">확인이 필요한 이유</span>
          <ul className="m-0 flex list-disc flex-col gap-[2px] pl-[20px] text-[14px] leading-[1.55]">
            {item.checkReasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {item.missingInputs.length > 0 && (
        <p className="text-text-sub m-0 text-[14px] leading-[1.55]">
          <strong className="text-text">넣으면 정해져요</strong> ·{" "}
          {item.missingInputs.map((m) => m.label).join(", ")}
        </p>
      )}
    </div>
  );
}

function ItemCard({ item, web }: { item: LoanItem; web: boolean }) {
  return (
    <li
      className={cn(
        "rounded-card bg-surface flex flex-col gap-[12px]",
        web ? "px-[24px] py-[20px]" : "px-[18px] py-[16px]",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-[8px]">
        <span className="flex min-w-0 flex-col gap-[4px]">
          <span className="text-text-sub text-[13px] font-bold">
            {loanTypeLabel[item.loanType]} 대출
          </span>
          <span
            className={cn("tracking-title font-extrabold", web ? "text-[18px]" : "text-[17px]")}
          >
            {item.productName}
          </span>
        </span>
        <Badge tone={statusTone[item.status]} size="md" className="flex-none">
          {loanStatusLabel[item.status]}
        </Badge>
      </div>
      <Reasons item={item} />
      <dl className="m-0 grid gap-[6px] text-[14px] leading-[1.5]">
        <div className="flex gap-[10px]">
          <dt className="text-text-sub w-[34px] flex-none font-semibold">한도</dt>
          <dd className="m-0 min-w-0">{item.limitSummary}</dd>
        </div>
        <div className="flex gap-[10px]">
          <dt className="text-text-sub w-[34px] flex-none font-semibold">금리</dt>
          <dd className="m-0 min-w-0">{item.rateSummary}</dd>
        </div>
      </dl>
      {item.sourceUrl && (
        <a
          href={item.sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-[40px] items-center gap-[4px] self-start text-[14px] font-bold no-underline"
        >
          상품 안내 원문
          <ExternalLink size={14} aria-hidden />
        </a>
      )}
    </li>
  );
}

/** 상품별 결과: 받을 수 있음 → 확인 필요 → 받을 수 없음 (서버가 정렬해서 줘요) */
export function LoanResults({ calc, variant }: Props) {
  const web = variant === "web";
  const [type, setType] = useState<TypeFilter>("ALL");
  const { result } = calc;

  if (!result) {
    return (
      <div
        className={cn(
          "rounded-card bg-surface text-text-sub flex flex-col gap-[6px] text-center",
          web ? "px-[28px] py-[48px]" : "px-[20px] py-[32px]",
        )}
      >
        <span className="text-text text-[17px] font-bold">
          {calc.pending ? "상품마다 확인하는 중이에요" : "아직 확인하지 않았어요"}
        </span>
        {!calc.pending && (
          <span className="text-[14px] leading-[1.6]">
            조건을 넣고 「확인하기」를 누르면 전세 · 월세 · 구입 대출 상품마다 받을 수 있는지 알려
            드려요. 모르는 칸은 비워 둬도 돼요
          </span>
        )}
      </div>
    );
  }

  const shown = type === "ALL" ? result.items : result.items.filter((i) => i.loanType === type);
  const { counts } = result;

  return (
    <div className="flex flex-col gap-[12px]" aria-busy={calc.pending}>
      <div
        className={cn(
          "rounded-card bg-surface flex flex-col gap-[10px]",
          web ? "px-[24px] py-[20px]" : "px-[18px] py-[16px]",
        )}
      >
        <span className="text-text-sub text-[13px]">{result.asOf} 기준</span>
        <div className="flex flex-wrap gap-[6px]">
          <Badge tone="ok">받을 수 있어요 {counts.eligible}</Badge>
          <Badge tone="check">확인 필요 {counts.needsInput}</Badge>
          <Badge tone="neutral">받을 수 없어요 {counts.ineligible}</Badge>
        </div>
        {calc.stale && (
          <p
            role="status"
            className="rounded-control bg-check-bg text-check-text m-0 px-[14px] py-[10px] text-[14px] font-semibold"
          >
            입력이 바뀌었어요. 「확인하기」를 다시 누르면 새 조건으로 확인해요
          </p>
        )}
      </div>
      <div role="group" aria-label="대출 종류" className="flex flex-wrap gap-[6px]">
        {typeFilters.map((t) => (
          <FilterChip key={t} selected={t === type} onClick={() => setType(t)}>
            {t === "ALL" ? "전체" : loanTypeLabel[t]}
          </FilterChip>
        ))}
      </div>
      <ul className="m-0 flex list-none flex-col gap-[10px] p-0">
        {shown.map((item) => (
          <ItemCard key={item.productCode} item={item} web={web} />
        ))}
      </ul>
      {shown.length === 0 && (
        <p className="rounded-card bg-surface text-text-sub m-0 px-[20px] py-[28px] text-center text-[15px]">
          이 종류의 상품이 없어요
        </p>
      )}
    </div>
  );
}

/** 결과 아래 안내 */
export function LoanNote({ className }: { className?: string }) {
  return (
    <span className={cn("text-text-sub px-[4px] text-[13px] leading-[1.6]", className)}>
      주택도시기금 상품 안내의 사람 조건(나이 · 세대 · 혼인 · 출산 · 소득 · 순자산 · 무주택)만
      봤어요. 보증금 · 면적 · 담보 가치처럼 집이 정해져야 보는 조건과 은행 심사는 포함하지 않아요.
      한도 · 금리는 상품 안내 요약이라 참고만 해 주세요.{" "}
      <strong className="text-text">넣은 값은 저장하지 않아요</strong> (이 기기 · 서버 모두).
    </span>
  );
}
