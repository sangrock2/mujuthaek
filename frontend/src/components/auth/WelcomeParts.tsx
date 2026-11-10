"use client";

import { Toggle } from "@/components/ui/Toggle";
import { interestOptions, type useWelcomeSetup } from "@/features/auth/useWelcomeSetup";
import { cn } from "@/lib/cn";

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
