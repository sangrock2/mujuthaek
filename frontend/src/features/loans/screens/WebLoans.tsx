"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { LoanFields } from "@/features/loans/components/LoanFields";
import { LoanNote, LoanResults } from "@/features/loans/components/LoanResults";
import { Button } from "@/shared/ui/Button";
import { useLoanCheck } from "@/features/loans/useLoanCheck";
import { routes } from "@/shared/lib/routes";

export function WebLoans() {
  const calc = useLoanCheck();

  return (
    <WebPage>
      <WebHeader mode="home" current={routes.benefits} />
      <WebMain className="gap-[20px] pt-[24px]">
        <nav
          aria-label="위치"
          className="text-text-tertiary flex items-center gap-[4px] text-[14px]"
        >
          <Link
            href={routes.benefits}
            className="text-text-sub hover:text-text-sub inline-flex min-h-[36px] items-center font-semibold no-underline"
          >
            내 혜택
          </Link>
          <ChevronRight size={16} aria-hidden />
          <span aria-current="page">대출 자격 확인</span>
        </nav>
        <div className="flex flex-col gap-[6px]">
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">대출 자격 확인</h1>
          <span className="text-text-sub text-[16px]">
            버팀목 · 디딤돌 같은 주택도시기금 대출을 정확한 소득 · 순자산으로 확인해요. 내 조건으로
            채울 수 있는 칸은 미리 채웠어요
          </span>
        </div>

        <div className="flex flex-wrap items-start gap-[20px]">
          <form
            aria-label="대출 조건"
            autoComplete="off"
            onSubmit={(e) => {
              e.preventDefault();
              calc.check();
            }}
            className="flex min-w-0 flex-col gap-[12px]"
            style={{ flex: "1 1 480px" }}
          >
            <LoanFields calc={calc} variant="web" />
            <div className="rounded-card bg-surface sticky bottom-[16px] flex flex-wrap items-center gap-[10px] px-[20px] py-[16px] shadow-[0_6px_20px_rgba(25,31,40,0.08)]">
              <Button
                type="submit"
                variant={calc.canCheck ? "primary" : "disabled"}
                disabled={!calc.canCheck}
                className="min-w-[160px] flex-1"
              >
                {calc.pending ? "확인하는 중이에요" : "확인하기"}
              </Button>
              <Button variant="secondary" onClick={calc.clear}>
                입력 지우기
              </Button>
              {calc.error && (
                <span role="alert" className="text-check-text basis-full text-[14px] font-semibold">
                  {calc.error}
                </span>
              )}
            </div>
          </form>

          <section
            aria-label="대출 상품별 결과"
            aria-live="polite"
            className="flex min-w-0 flex-col gap-[12px]"
            style={{ flex: "1 1 440px" }}
          >
            <LoanResults calc={calc} variant="web" />
            <LoanNote />
          </section>
        </div>
      </WebMain>
    </WebPage>
  );
}
