"use client";

import { Toggle } from "@/shared/ui/Toggle";
import { interestOptions, type useWelcomeSetup } from "@/features/auth/useWelcomeSetup";
import { cn } from "@/shared/lib/cn";

type Setup = ReturnType<typeof useWelcomeSetup>;

/** 첫 설정 진행 막대 */
export function SetupProgress({ setup, className }: { setup: Setup; className?: string }) {
  return (
    <div aria-live="polite" className={cn("flex flex-col gap-[8px]", className)}>
      <span className="flex justify-between text-[15px] font-bold">
        <span>첫 설정</span>
        <span className="text-brand-strong">{setup.done} / 3 완료</span>
      </span>
      <span className="bg-line block h-[8px] overflow-hidden rounded-[4px]">
        <span className="bg-brand block h-full rounded-[4px]" style={{ width: setup.progress }} />
      </span>
    </div>
  );
}

/** 완료한 칸은 초록 2px 테두리 */
export const setupCard = (done: boolean) =>
  cn("rounded-card bg-surface border-2 border-solid", done ? "border-brand" : "border-surface");

export function AlertToggle({ setup }: { setup: Setup }) {
  return (
    <Toggle
      checked={setup.alert}
      onChange={(on) => !setup.alertPending && setup.setAlert(on)}
      label="마감 알림"
    />
  );
}

/** 마감 알림을 켜지 못한 이유 (알림 차단·지원 안 함 등) */
export function AlertError({ setup }: { setup: Setup }) {
  if (!setup.alertError) return null;
  return (
    <span role="alert" className="text-danger-text text-[13px] font-bold">
      {setup.alertError}
    </span>
  );
}

export function InterestChips({ setup, chipClassName }: { setup: Setup; chipClassName?: string }) {
  return (
    <div role="group" aria-label="관심 분야" className="flex flex-wrap gap-[8px]">
      {interestOptions.map((l) => {
        const on = setup.interests.includes(l);
        return (
          <button
            key={l}
            type="button"
            aria-pressed={on}
            onClick={() => setup.toggleInterest(l)}
            className={cn(
              "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid text-[15px] font-bold",
              on
                ? "border-brand bg-brand-soft text-brand-strong"
                : "border-line bg-surface text-text",
              chipClassName,
            )}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 사는 지역(이 기기에만 저장한 값)을 관심 지역으로 계정에 저장할지 묻는 칸. 기본은 꺼져 있어요.
 * 켜야만 서버에 올라가고, 끄면 지역 없이(전국) 저장해요 (2026-11-16 보안 감사 4장)
 */
export function RegionShareOption({ setup, className }: { setup: Setup; className?: string }) {
  if (!setup.deviceRegion) return null;
  return (
    <label className={cn("flex items-start gap-[8px] text-[14px] leading-[1.6]", className)}>
      <input
        type="checkbox"
        checked={setup.shareRegion}
        onChange={(e) => setup.setShareRegion(e.target.checked)}
        className="mt-[4px]"
      />
      <span className="flex flex-col">
        <span className="font-bold">
          사는 지역({setup.deviceRegionLabel || "이 기기에 저장한 지역"})도 관심 지역으로 저장할게요
        </span>
        <span className="text-text-sub text-[13px]">
          사는 지역은 지금 이 기기에만 있어요. 켜면 내 계정의 관심 조건에 저장돼 새 공고 알림에
          쓰이고, 내 정보 → 관심 조건에서 언제든 바꾸거나 지울 수 있어요. 끄면 지역 없이 전국 공고로
          받아요.
        </span>
      </span>
    </label>
  );
}

export function ConditionTags({ items, className }: { items: string[]; className?: string }) {
  return (
    <div className="flex flex-wrap gap-[6px]">
      {items.map((c) => (
        <span
          key={c}
          className={cn("rounded-pill bg-fill text-text-sub text-[14px] font-semibold", className)}
        >
          {c}
        </span>
      ))}
    </div>
  );
}

export function ConfirmCondButton({ setup, className }: { setup: Setup; className?: string }) {
  return (
    <button
      type="button"
      onClick={setup.confirmCond}
      aria-pressed={setup.cond}
      className={cn(
        "min-h-[48px] cursor-pointer rounded-sm border-0 text-[15px] font-extrabold",
        setup.cond ? "bg-brand-soft text-brand-strong" : "bg-brand text-white",
        className,
      )}
    >
      {setup.cond ? "확인했어요" : "맞아요"}
    </button>
  );
}
