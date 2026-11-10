"use client";

import { useState } from "react";
import Link from "next/link";
import { BellRing, CircleCheck } from "lucide-react";
import { usePush } from "@/features/alerts/usePush";
import { useSession } from "@/features/auth/session";
import { useNotificationSettings } from "@/features/me/api";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/**
 * 관심 공고 마감 D-3·D-1 알림 권유. 이미 켜져 있으면(마감 알림 설정 + 이 브라우저 푸시) 보이지 않아요.
 * 켜기는 이 브라우저 푸시 구독과 마감 알림 설정을 함께 켜고, 다 되면 「켰어요」로 알려 줘요 (닫거나 다음에 오면 안 보여요).
 * 로그인 전이면 로그인으로 보내요. 웹·모바일 홈이 같이 써요
 */
export function DeadlineAlertPrompt({ variant }: { variant: "web" | "mobile" }) {
  const box = variant === "web" ? "rounded-card px-[24px] py-[22px]" : "rounded-[22px] p-[18px]";
  const { data: session, isPending } = useSession();
  const settings = useNotificationSettings();
  const push = usePush();
  const [saving, setSaving] = useState(false);
  /** 이 화면에서 방금 켰는지 (켰다는 안내를 보여 줘요) */
  const [justOn, setJustOn] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // 상태를 다 확인하기 전에는 그리지 않아요 (켜진 회원에게 잠깐 보였다 사라지지 않게)
  if (isPending || settings.loading || !push.checked || dismissed) return null;
  const on = !!session && settings.value.deadline && push.enabled;
  if (on && !justOn) return null;

  const turnOn = async () => {
    setSaving(true);
    try {
      // 허용 창은 누른 바로 그때 띄워야 해서 푸시를 먼저 켜요
      if (!push.enabled && !(await push.turnOn())) return;
      if (!settings.value.deadline) await settings.setAsync({ deadline: true });
      setJustOn(true);
    } catch {
      // 설정 저장 실패는 settings.failed로 아래에 보여 줘요
    } finally {
      setSaving(false);
    }
  };
  const busy = saving || push.pending;
  const button =
    "bg-brand inline-flex min-h-[40px] flex-none cursor-pointer items-center rounded-[10px] border-0 px-[14px] text-[14px] font-bold text-white no-underline hover:text-white disabled:opacity-60";

  if (on) {
    return (
      <section
        role="status"
        aria-label="알림 받기"
        className={cn("bg-brand-soft flex items-center gap-[14px]", box)}
      >
        <span className="rounded-control text-brand flex size-[44px] flex-none items-center justify-center bg-white">
          <CircleCheck size={22} strokeWidth={1.8} aria-hidden />
        </span>
        <span className="flex flex-1 flex-col gap-[2px]">
          <span className="text-brand-strong text-[16px] font-bold">마감 알림을 켰어요</span>
          <span className="text-brand-strong text-[14px]">
            관심 공고 마감 3일·1일 전에 이 브라우저로 알려 드려요.{" "}
            <Link href={`${routes.me}?tab=notifications`} className="text-brand-strong font-bold">
              알림 설정
            </Link>
            에서 바꿀 수 있어요
          </span>
        </span>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-brand-strong min-h-[40px] flex-none cursor-pointer rounded-[10px] border-0 bg-white px-[14px] text-[14px] font-bold"
        >
          닫기
        </button>
      </section>
    );
  }

  return (
    <section aria-label="알림 받기" className={cn("bg-surface flex flex-col gap-[10px]", box)}>
      <div className="flex items-center gap-[14px]">
        <span className="rounded-control bg-fill text-text flex size-[44px] flex-none items-center justify-center">
          <BellRing size={22} strokeWidth={1.8} aria-hidden />
        </span>
        <span className="flex flex-1 flex-col gap-[2px]">
          <span className="text-[16px] font-bold">마감 전에 알려드릴까요?</span>
          <span className="text-text-sub text-[14px]">관심 공고 D-3, D-1에 알림</span>
        </span>
        {session ? (
          <button type="button" disabled={busy} onClick={() => void turnOn()} className={button}>
            {busy ? "켜는 중…" : "켜기"}
          </button>
        ) : (
          <Link href={routes.login} className={button}>
            로그인하고 켜기
          </Link>
        )}
      </div>
      {(push.error || settings.failed) && (
        <span role="alert" className="text-danger-text text-[14px]">
          {push.error ?? "알림 설정을 저장하지 못했어요. 잠시 뒤 다시 해 주세요"}
        </span>
      )}
      {variant === "mobile" && (
        <Link
          href={routes.install}
          className="text-brand-strong hover:text-brand-strong inline-flex min-h-[36px] items-center text-[13px] font-bold no-underline"
        >
          iPhone은 홈 화면에 추가해야 알림이 와요 · 방법 보기 ›
        </Link>
      )}
    </section>
  );
}
