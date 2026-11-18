"use client";

import Link from "next/link";
import { useHasHousingInput } from "@/features/conditions/personalization";
import { profileThen, routes } from "@/shared/lib/routes";

export function BenefitEmptyState({
  filtered,
  onReset,
}: {
  filtered: boolean;
  onReset: () => void;
}) {
  const hasInput = useHasHousingInput();
  return (
    <div className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <p className="text-text m-0 text-[16px] font-bold">
        {filtered ? "이 분야에 표시할 혜택이 없어요" : "현재 조건으로 표시할 혜택을 찾지 못했어요"}
      </p>
      <p className="text-text-sub m-0 max-w-[420px] text-[14px] leading-[1.6]">
        {hasInput
          ? "선택한 지역·조건이나 현재 제공 중인 정보에 따라 결과가 달라져요. 모든 혜택의 신청 자격이 없다는 뜻은 아니에요."
          : "아직 조건을 입력하지 않았어요. 조건을 넣어 확인하거나 주거 공고부터 살펴보세요. 현재 제공 중인 정보에 따라 결과가 달라질 수 있어요."}
      </p>
      <div className="flex flex-wrap justify-center gap-[12px]">
        {filtered && (
          <button
            type="button"
            onClick={onReset}
            className="text-brand-strong min-h-[44px] cursor-pointer border-0 bg-transparent text-[14px] font-bold"
          >
            전체 분야 보기
          </button>
        )}
        <Link
          href={profileThen(routes.benefits)}
          className="text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold"
        >
          {hasInput ? "지역·조건 수정" : "조건 입력하고 확인"}
        </Link>
        <Link
          href={routes.homes}
          className="text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold"
        >
          주거 공고 둘러보기
        </Link>
      </div>
    </div>
  );
}
