"use client";

import Link from "next/link";
import { ArrowRight, BellRing } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { AuthWebHeader } from "@/components/auth/parts";
import {
  AlertError,
  AlertToggle,
  ConditionTags,
  ConfirmCondButton,
  InterestChips,
  SetupProgress,
  setupCard,
} from "@/components/auth/WelcomeParts";
import { useSession } from "@/features/auth/session";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { useWelcomeSetup } from "@/features/auth/useWelcomeSetup";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

export function WebWelcome() {
  const setup = useWelcomeSetup();
  const { data: session } = useSession();
  const conditions = useConditionSummary();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <AuthWebHeader />
      <main className="mx-auto box-border flex w-full max-w-[640px] flex-1 flex-col gap-[20px] px-[24px] pt-[56px] pb-[72px]">
        <div className="flex flex-col items-center gap-[14px] pb-[8px] text-center">
          <Logo size={72} />
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">
            가입을 환영해요{session ? `, ${session.nickname}님` : ""}
          </h1>
          <span className="text-text-sub text-[17px]">시작하기 전에 세 가지만 정해 주세요</span>
        </div>

        <SetupProgress setup={setup} />

        <section
          aria-label="마감 알림"
          className={cn(setupCard(setup.alert), "flex items-center gap-[16px] px-[24px] py-[22px]")}
        >
          <span className="bg-brand-soft text-brand flex size-[48px] flex-none items-center justify-center rounded-[15px]">
            <BellRing size={24} strokeWidth={1.8} aria-hidden />
          </span>
          <span className="flex flex-1 flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">마감 알림 켜기</span>
            <span className="text-text-sub text-[14px]">
              새 공고와 관심 공고 마감 3일·1일 전에 알려드려요
            </span>
            <AlertError setup={setup} />
          </span>
          <AlertToggle setup={setup} />
        </section>

        <section
          aria-label="관심 분야"
          className={cn(
            setupCard(setup.interestDone),
            "flex flex-col gap-[14px] px-[24px] py-[22px]",
          )}
        >
          <span className="flex flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">관심 분야 고르기</span>
            <span className="text-text-sub text-[14px]">
              고른 분야의 공고와 혜택을 홈에 먼저 보여드려요 · 여러 개 가능
            </span>
          </span>
          <InterestChips setup={setup} chipClassName="px-[18px]" />
        </section>

        <section
          aria-label="입력한 조건"
          className={cn(setupCard(setup.cond), "flex flex-col gap-[14px] px-[24px] py-[22px]")}
        >
          <span className="flex flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">입력한 조건이 맞나요?</span>
            <span className="text-text-sub text-[14px]">
              입력한 조건은 이 기기에 저장돼 있어요 (소득·자산 제외)
            </span>
          </span>
          {conditions.status === "ready" && !conditions.hasConditions ? (
            <span className="text-text-sub text-[14px]">아직 입력한 조건이 없어요</span>
          ) : (
            <ConditionTags
              items={conditions.status === "ready" ? conditions.shortChips : []}
              className="px-[13px] py-[7px]"
            />
          )}
          <div className="flex gap-[8px]">
            <ConfirmCondButton setup={setup} className="px-[18px]" />
            <Link
              href={routes.profile}
              className="bg-fill text-text hover:text-text inline-flex min-h-[48px] items-center rounded-sm px-[18px] text-[15px] font-bold no-underline"
            >
              고칠게요
            </Link>
          </div>
        </section>

        <Link
          href={routes.home}
          className="bg-brand mt-[8px] flex min-h-[60px] items-center justify-center gap-[8px] rounded-[16px] text-[18px] font-extrabold text-white no-underline hover:text-white"
        >
          내 결과 보러 가기
          <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
        </Link>
        <Link
          href={routes.home}
          className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center self-center text-[15px] font-semibold no-underline"
        >
          나중에 할게요
        </Link>
      </main>
    </div>
  );
}
