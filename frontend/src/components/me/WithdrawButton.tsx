"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { providerLabel } from "@/features/auth/session";
import { goWithdrawal, startWithdrawal } from "@/features/me/api";
import { cn } from "@/lib/cn";

/**
 * 회원 탈퇴: 확인 → 본인 확인용으로 그 소셜에 다시 로그인 → 회원 삭제 → /withdrawn.
 * 함께 연결된 다른 소셜은 서버가 연결을 끊을 수 없어서 각 서비스에서 직접 해제하라고 알려요
 */
/** 백엔드가 탈퇴 재인증에 실패하고 돌려보낸 이유 (/mypage?withdraw=… → /me?tab=privacy&withdraw=…) */
const returned: Record<string, string> = {
  expired: "본인 확인 시간이 지났어요. 회원 탈퇴를 다시 눌러 주세요",
  account_mismatch: "지금 로그인한 계정과 다른 계정으로 확인했어요. 같은 계정으로 다시 해 주세요",
  cancelled: "본인 확인을 취소해서 탈퇴하지 않았어요",
  failed: "탈퇴하지 못했어요. 잠시 뒤 다시 해 주세요",
};

export function WithdrawButton({ className }: { className?: string }) {
  const reason = useSearchParams().get("withdraw");
  const [step, setStep] = useState<"idle" | "confirm" | "going">("idle");
  const [others, setOthers] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(() =>
    reason ? (returned[reason] ?? returned.failed) : null,
  );
  const [start, setStart] = useState<Awaited<ReturnType<typeof startWithdrawal>> | null>(null);

  const begin = async () => {
    setError(null);
    try {
      const s = await startWithdrawal();
      setStart(s);
      setOthers(s.otherProviders);
      setStep("confirm");
    } catch {
      setError("탈퇴를 시작하지 못했어요. 잠시 뒤 다시 해 주세요");
    }
  };

  if (step === "idle") {
    return (
      <div className={cn("flex flex-col gap-[6px]", className)}>
        <button
          type="button"
          onClick={() => void begin()}
          className="text-danger-link inline-flex min-h-[44px] cursor-pointer items-center self-start border-0 bg-transparent p-0 text-[14px] font-bold"
        >
          회원 탈퇴
        </button>
        {error && (
          <span role="alert" className="text-danger-text text-[14px]">
            {error}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      role="alertdialog"
      aria-label="회원 탈퇴 확인"
      className={cn("bg-danger-bg flex flex-col gap-[10px] rounded-[16px] p-[18px]", className)}
    >
      <span className="text-danger-text text-[16px] font-extrabold">정말 탈퇴할까요?</span>
      <span className="text-[15px] leading-[1.6]">
        관심 공고 · 관심 조건 · 알림 · 제보가 모두 지워지고 되돌릴 수 없어요. 본인 확인을 위해{" "}
        {start ? (providerLabel[start.provider] ?? start.provider) : ""}로 한 번 더 로그인해요.
      </span>
      {others.length > 0 && (
        <span className="text-[14px] leading-[1.6]">
          함께 연결된 {others.map((p) => providerLabel[p] ?? p).join(" · ")} 연결은 각 서비스에서
          직접 해제해 주세요.
        </span>
      )}
      <div className="flex flex-wrap gap-[8px]">
        <button
          type="button"
          disabled={step === "going" || !start}
          onClick={() => {
            if (!start) return;
            setStep("going");
            goWithdrawal(start);
          }}
          className="bg-danger-text min-h-[44px] cursor-pointer rounded-sm border-0 px-[16px] text-[15px] font-bold text-white disabled:opacity-60"
        >
          확인하고 탈퇴하기
        </button>
        <button
          type="button"
          onClick={() => setStep("idle")}
          className="bg-surface text-text min-h-[44px] cursor-pointer rounded-sm border-0 px-[16px] text-[15px] font-bold"
        >
          그만두기
        </button>
      </div>
    </div>
  );
}
