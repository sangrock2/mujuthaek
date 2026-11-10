"use client";

import Link from "next/link";
import { Check } from "lucide-react";
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

export function MWelcome() {
  const setup = useWelcomeSetup();
  const { data: session } = useSession();
  const conditions = useConditionSummary();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <main className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[48px] pb-[32px]">
        <div className="flex flex-col items-center gap-[12px] px-[8px] pb-[8px] text-center">
          <span className="rounded-pill bg-brand flex size-[68px] items-center justify-center text-white">
            <Check size={34} strokeWidth={2.4} aria-hidden />
          </span>
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">
            가입을 환영해요{session ? `, ${session.nickname}님` : ""}
          </h1>
          <span className="text-text-sub text-[16px] leading-[1.6]">
            세 가지만 정하면 딱 맞는 공고를 놓치지 않아요
          </span>
        </div>

        <SetupProgress setup={setup} className="px-[4px]" />

        <section
          aria-label="마감 알림"
          className={cn(setupCard(setup.alert), "flex items-center gap-[14px] p-[20px]")}
        >
          <span className="flex flex-1 flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">마감 알림 켜기</span>
            <span className="text-text-sub text-[14px] leading-[1.5]">
              새 공고와 관심 공고 마감 3일·1일 전에 알려드려요
            </span>
            <AlertError setup={setup} />
          </span>
          <AlertToggle setup={setup} />
        </section>

        <section
          aria-label="관심 분야"
          className={cn(setupCard(setup.interestDone), "flex flex-col gap-[12px] p-[20px]")}
        >
          <span className="flex flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">관심 분야 고르기</span>
            <span className="text-text-sub text-[14px]">여러 개 고를 수 있어요</span>
          </span>
          <InterestChips setup={setup} chipClassName="px-[16px]" />
        </section>

        <section
          aria-label="입력한 조건"
          className={cn(setupCard(setup.cond), "flex flex-col gap-[12px] p-[20px]")}
        >
          <span className="flex flex-col gap-[2px]">
            <span className="text-[17px] font-extrabold">입력한 조건이 맞나요?</span>
            <span className="text-text-sub text-[14px]">
              이 기기에 저장돼 있어요 · 소득·자산 제외
            </span>
          </span>
          {conditions.status === "ready" && !conditions.hasConditions ? (
            <span className="text-text-sub text-[14px]">아직 입력한 조건이 없어요</span>
          ) : (
            <ConditionTags
              items={conditions.status === "ready" ? conditions.shortChips : []}
              className="px-[12px] py-[6px]"
            />
          )}
          <div className="grid grid-cols-2 gap-[8px]">
            <ConfirmCondButton setup={setup} />
            <Link
              href={routes.profile}
              className="bg-fill text-text hover:text-text flex min-h-[48px] items-center justify-center rounded-sm text-[15px] font-bold no-underline"
            >
              고칠게요
            </Link>
          </div>
        </section>
      </main>
      <div className="flex flex-col gap-[4px] px-[16px] pt-[12px] pb-[28px]">
        <Link
          href={routes.home}
          className="bg-brand flex min-h-[58px] items-center justify-center rounded-[16px] text-[17px] font-extrabold text-white no-underline hover:text-white"
        >
          내 결과 보러 가기
        </Link>
        <Link
          href={routes.home}
          className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center self-center text-[15px] font-semibold no-underline"
        >
          나중에 할게요
        </Link>
      </div>
    </div>
  );
}
