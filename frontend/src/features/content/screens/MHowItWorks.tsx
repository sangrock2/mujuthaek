"use client";

import Link from "next/link";
import {
  AgentLoop,
  FlowSteps,
  Numbers,
  Principles,
  ReviewCases,
  Roles,
  SectionTitle,
  Verdicts,
} from "@/features/content/components/HowItWorksParts";
import { CustomerCenterHeader } from "@/features/content/components/WebContentShell";
import { MPage } from "@/shared/layout/Responsive";
import { routes } from "@/shared/lib/routes";
import { ScrollToTop } from "@/shared/ui/ScrollToTop";

/** 「무주택자들은 어떻게 만들었나요」 (모바일) */
export function MHowItWorks() {
  const web = false;
  return (
    <MPage className="stitch-surface">
      <CustomerCenterHeader current={routes.howItWorks} sticky />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[28px] px-[16px] pt-[20px] pb-[36px]"
      >
        <div className="flex flex-col gap-[8px] px-[4px]">
          <span className="text-brand-strong text-[14px] font-bold">서비스 소개</span>
          <h1 className="tracking-h1 m-0 text-[26px] leading-[1.35] font-extrabold">
            무주택자들은 어떻게 만들었나요
          </h1>
          <p className="text-text-sub m-0 text-[15px] leading-[1.7]">
            여러 기관에 흩어진 공고를 모으고, 첨부 원문에서 자격 · 일정 · 서류를 뽑아, 내 조건으로
            지원할 수 있는지 알려 드리기까지의 과정을 보여 드려요.
          </p>
        </div>

        <Principles web={web} />

        <section aria-labelledby="mhw-flow" className="flex flex-col gap-[14px]">
          <div id="mhw-flow">
            <SectionTitle web={web} title="공고 하나가 화면에 오기까지" />
          </div>
          <FlowSteps web={web} />
        </section>

        <section aria-labelledby="mhw-loop" className="flex flex-col gap-[14px]">
          <div id="mhw-loop">
            <SectionTitle
              web={web}
              title="AI는 어떻게 일하나요"
              sub="섹션을 나눠 맡은 AI 담당이 값을 넣고, 코드의 검증 결과를 받아 스스로 고쳐요"
            />
          </div>
          <AgentLoop />
          <Roles web={web} />
        </section>

        <section aria-labelledby="mhw-review" className="flex flex-col gap-[14px]">
          <div id="mhw-review">
            <SectionTitle
              web={web}
              title="이럴 때는 「확인 필요」로 둬요"
              sub="값을 추측해서 채우지 않고, 사람이 원문을 확인할 때까지 게시하지 않아요"
            />
          </div>
          <ReviewCases web={web} />
        </section>

        <section aria-labelledby="mhw-numbers" className="flex flex-col gap-[14px]">
          <div id="mhw-numbers">
            <SectionTitle
              web={web}
              title="바꾸고 나서 얼마나 나아졌나요"
              sub="처음 방식과 지금 방식을 같은 정답표로 대조했어요"
            />
          </div>
          <Numbers web={web} />
        </section>

        <section aria-labelledby="mhw-judge" className="flex flex-col gap-[14px]">
          <div id="mhw-judge">
            <SectionTitle web={web} title="지원할 수 있는지는 이렇게 알려 드려요" />
          </div>
          <Verdicts web={web} />
        </section>

        <section aria-label="시작하기" className="rounded-card bg-surface flex flex-col gap-2 p-5">
          <span className="text-[17px] font-extrabold">내 조건으로 확인해 보세요</span>
          <span className="text-text-sub text-sm">
            가입 없이 조건만 넣으면 지원할 수 있는 집과 혜택을 보여 드려요
          </span>
          <div className="flex flex-wrap gap-2">
            <Link
              href={routes.home}
              className="rounded-pill bg-brand flex min-h-11 items-center justify-center px-4 text-sm font-bold text-white no-underline hover:text-white"
            >
              서비스로 가기
            </Link>
            <Link
              href={routes.faq}
              className="rounded-pill bg-brand-soft text-brand-strong hover:text-brand-strong inline-flex min-h-11 items-center justify-center px-4 text-sm font-bold no-underline"
            >
              자주 묻는 질문
            </Link>
          </div>
        </section>
      </main>
      <ScrollToTop />
    </MPage>
  );
}
