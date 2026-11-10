"use client";

import { useEffect, useRef } from "react";
import { MBackHeader, MBottomActions } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
import { LoanFields } from "@/components/loans/LoanFields";
import { LoanNote, LoanResults } from "@/components/loans/LoanResults";
import { Button } from "@/components/ui/Button";
import { useLoanCheck } from "@/features/loans/useLoanCheck";
import { routes } from "@/lib/routes";

export function MLoans() {
  const calc = useLoanCheck();
  const resultsRef = useRef<HTMLElement>(null);

  // 결과를 받으면 결과로 내려가요 (모바일은 입력 아래에 결과가 있어요). PC 폭에서는 이 화면이 숨어 있어서 움직이지 않아요
  useEffect(() => {
    if (!calc.result || window.matchMedia("(min-width: 1024px)").matches) return;
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [calc.result]);

  return (
    <MPage>
      <MBackHeader title="대출 자격 확인" backHref={routes.benefits} />
      <form
        aria-label="대출 조건"
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          calc.check();
        }}
        className="flex flex-1 flex-col"
      >
        <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[16px] pb-[28px]">
          <span className="text-text-sub px-[4px] text-[14px] leading-[1.6]">
            버팀목 · 디딤돌 같은 주택도시기금 대출을 정확한 소득 · 순자산으로 확인해요. 내 조건으로
            채울 수 있는 칸은 미리 채웠어요
          </span>
          <LoanFields calc={calc} variant="mobile" />
          <section
            ref={resultsRef}
            aria-label="대출 상품별 결과"
            aria-live="polite"
            className="flex scroll-mt-[calc(var(--m-header-h)+12px)] flex-col gap-[12px] pt-[8px]"
          >
            <h2 className="tracking-title m-0 px-[4px] text-[19px] font-extrabold">결과</h2>
            <LoanResults calc={calc} variant="mobile" />
          </section>
          <LoanNote />
        </main>
        <MBottomActions>
          <div className="flex w-full flex-col gap-[6px]">
            {calc.error && (
              <span role="alert" className="text-check-text text-[14px] font-semibold">
                {calc.error}
              </span>
            )}
            <div className="flex gap-[8px]">
              <Button variant="secondary" onClick={calc.clear} className="flex-[1_1_0] px-[12px]">
                지우기
              </Button>
              <Button
                type="submit"
                variant={calc.canCheck ? "primary" : "disabled"}
                disabled={!calc.canCheck}
                className="flex-[2_1_0]"
              >
                {calc.pending ? "확인하는 중이에요" : "확인하기"}
              </Button>
            </div>
          </div>
        </MBottomActions>
      </form>
    </MPage>
  );
}
