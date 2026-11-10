"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import {
  AgentLoop,
  FlowSteps,
  Numbers,
  Principles,
  ReviewCases,
  Roles,
  SectionTitle,
  Verdicts,
} from "@/components/content/HowItWorksParts";
import { WebContentMain, WebContentShell } from "@/components/content/WebContentShell";
import { routes } from "@/lib/routes";

/** 「무주택자들은 어떻게 만들었나요」 (PC) */
export function WebHowItWorks() {
  const web = true;
  return (
    <WebContentShell current={routes.howItWorks}>
      <WebContentMain className="max-w-[960px] gap-[40px] pt-[48px]">
        <div className="flex flex-col gap-[10px]">
          <span className="text-brand-strong text-[15px] font-bold">서비스 소개</span>
          <h1 className="tracking-h1 m-0 text-[34px] leading-[1.3] font-extrabold">
            무주택자들은 어떻게 만들었나요
          </h1>
          <p className="text-text-sub m-0 text-[17px] leading-[1.7]">
            여러 기관에 흩어진 공고를 모으고, 첨부 원문에서 자격 · 일정 · 서류를 뽑아, 내 조건으로
            지원할 수 있는지 알려 드리기까지의 과정을 보여 드려요.
          </p>
        </div>

        <Principles web={web} />

        <section aria-labelledby="hw-flow" className="flex flex-col gap-[16px]">
          <div id="hw-flow">
            <SectionTitle
              web={web}
              title="공고 하나가 화면에 오기까지"
              sub="모으기부터 알림까지 여섯 단계를 거쳐요"
            />
          </div>
          <FlowSteps web={web} />
        </section>

        <section aria-labelledby="hw-loop" className="flex flex-col gap-[16px]">
          <div id="hw-loop">
            <SectionTitle
              web={web}
              title="AI는 어떻게 일하나요"
              sub="AI를 한 번 불러 결과를 받는 데서 끝나지 않아요. 섹션을 나눠 맡은 AI 담당이 값을 넣고, 코드의 검증 결과를 받아 스스로 고쳐요"
            />
          </div>
          <AgentLoop web={web} />
          <Roles web={web} />
        </section>

        <section aria-labelledby="hw-review" className="flex flex-col gap-[16px]">
          <div id="hw-review">
            <SectionTitle
              web={web}
              title="이럴 때는 「확인 필요」로 둬요"
              sub="값을 추측해서 채우지 않고, 사람이 원문을 확인할 때까지 게시하지 않아요"
            />
          </div>
          <ReviewCases web={web} />
        </section>

        <section aria-labelledby="hw-numbers" className="flex flex-col gap-[16px]">
          <div id="hw-numbers">
            <SectionTitle
              web={web}
              title="바꾸고 나서 얼마나 나아졌나요"
              sub="처음 방식과 지금 방식(섹션 담당 에이전트)을 같은 정답표로 대조했어요"
            />
          </div>
          <Numbers web={web} />
        </section>

        <section aria-labelledby="hw-judge" className="flex flex-col gap-[16px]">
          <div id="hw-judge">
            <SectionTitle
              web={web}
              title="지원할 수 있는지는 이렇게 알려 드려요"
              sub="뽑아 둔 자격 조건과 내 조건을 하나씩 비교해요"
            />
          </div>
          <Verdicts web={web} />
        </section>

        <section
          aria-label="시작하기"
          className="rounded-card-lg bg-surface flex flex-wrap items-center justify-between gap-[16px] px-[32px] py-[28px]"
        >
          <span className="flex flex-col gap-[6px]">
            <span className="text-[20px] font-extrabold">내 조건으로 확인해 보세요</span>
            <span className="text-text-sub text-[15px]">
              가입 없이 조건만 넣으면 지원할 수 있는 집과 혜택을 보여 드려요
            </span>
          </span>
          <span className="flex flex-wrap gap-[8px]">
            <Link
              href={routes.faq}
              className="rounded-control bg-fill text-text hover:text-text inline-flex min-h-[52px] items-center px-[18px] text-[15px] font-bold no-underline"
            >
              자주 묻는 질문
            </Link>
            <Link
              href={routes.home}
              className="rounded-control bg-brand inline-flex min-h-[52px] items-center gap-[4px] px-[20px] text-[16px] font-extrabold text-white no-underline hover:text-white"
            >
              서비스로 가기
              <ChevronRight size={18} strokeWidth={2.2} aria-hidden />
            </Link>
          </span>
        </section>
      </WebContentMain>
    </WebContentShell>
  );
}
