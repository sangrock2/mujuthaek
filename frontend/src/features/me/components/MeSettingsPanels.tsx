"use client";

import Link from "next/link";
import { ChevronRight, Database, Pencil, Shield, SlidersHorizontal, UserRound } from "lucide-react";
import { AnalyticsConsentSetting } from "@/shared/analytics/Analytics";
import { isMember, providerLabel, useSession } from "@/features/auth/session";
import {
  clearConditions,
  setSaveOnDevice,
  useHasStoredConditions,
} from "@/features/conditions/store";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { Toggle } from "@/shared/ui/Toggle";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { EmailNotifications } from "./EmailNotifications";
import { NicknameSetting } from "./NicknameSetting";
import { RecentSearchSetting } from "./RecentSearchSetting";
import { meTabHref } from "./MeNavigation";
import { StoredInfoList, saveOnDeviceNote } from "./StoredInfo";
import { WithdrawButton } from "./WithdrawButton";

const card = "rounded-card border-line-soft bg-surface border p-[17px] sm:p-[22px]";
export const editConditionClass =
  "bg-brand text-white hover:text-white inline-flex min-h-[44px] shrink-0 items-center justify-center gap-[6px] rounded-sm px-[13px] text-[14px] font-bold no-underline";

export function ConditionEditLink() {
  return (
    <Link href={routes.profile} className={editConditionClass}>
      <Pencil size={15} aria-hidden /> 조건 수정
    </Link>
  );
}

export function ConditionsPanel() {
  const conditions = useConditionSummary();
  if (conditions.status === "loading")
    return (
      <p role="status" className="text-text-sub text-[14px]">
        조건을 불러오는 중이에요.
      </p>
    );
  if (!conditions.hasConditions)
    return (
      <div className={cn(card, "flex flex-col items-start gap-[10px]")}>
        <SlidersHorizontal size={23} className="text-brand-strong" aria-hidden />
        <p className="text-[16px] font-extrabold">아직 입력한 조건이 없어요</p>
        <p className="text-text-sub text-[14px]">
          나이, 사는 곳, 가구 조건을 입력해 맞춤 공고를 찾아보세요.
        </p>
      </div>
    );
  return (
    <dl className={cn(card, "m-0 grid grid-cols-2 gap-[7px] sm:gap-[10px] lg:grid-cols-3")}>
      {conditions.rows.map(({ k, v, muted }) => (
        <div
          key={k}
          className={cn(
            "rounded-control bg-fill min-w-0 px-[10px] py-[11px] sm:px-[13px]",
            ["세대", "결혼 · 자녀"].includes(k) && "col-span-2 lg:col-span-1",
          )}
        >
          <dt className="text-text-sub mb-[5px] text-[13px]">{k}</dt>
          <dd
            className={cn(
              "m-0 text-[15px] font-extrabold break-words sm:text-[16px]",
              muted && "text-text-sub",
            )}
          >
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function PrivacyPanel() {
  const { data: session } = useSession();
  const conditions = useConditionSummary();
  const hasStoredConditions = useHasStoredConditions();
  const saveOnDevice = conditions.status === "ready" ? conditions.saveOnDevice : true;

  return (
    <div className="flex flex-col gap-[12px] sm:gap-[16px]">
      <section className={cn(card, "flex flex-col gap-[12px]")} aria-label="계정 및 연동 정보">
        <h2 className="flex items-center gap-[8px] text-[17px] font-extrabold">
          <UserRound size={19} className="text-brand-strong" aria-hidden /> 계정 및 연동 정보
        </h2>
        {isMember(session) && <NicknameSetting key={session.id} member={session} />}
        {session && (
          <dl className="bg-fill rounded-control m-0 grid gap-[8px] px-[12px] py-[10px] text-[14px]">
            <div className="flex items-start justify-between gap-[10px]">
              <dt className="text-text-sub shrink-0">로그인 연동</dt>
              <dd className="m-0 text-right font-bold">
                {session.providers
                  .map((provider) => providerLabel[provider] ?? provider)
                  .join(" · ") || "없음"}
              </dd>
            </div>
          </dl>
        )}
        {!session && (
          <Link href={routes.login} className="text-brand-strong self-start text-[14px] font-bold">
            로그인하기
          </Link>
        )}
      </section>

      <EmailNotifications />

      <section
        className={cn(card, "flex flex-col gap-[13px]")}
        aria-label="개인정보 및 방문 통계 설정"
      >
        <h2 className="flex items-center gap-[8px] text-[17px] font-extrabold">
          <Shield size={19} className="text-brand-strong" aria-hidden /> 개인정보 및 방문 통계 설정
        </h2>
        <div className="flex items-center justify-between gap-[12px]">
          <div className="flex flex-col gap-[3px]">
            <span className="text-[15px] font-bold">이 기기에 조건 저장</span>
            <p className="text-text-sub text-[13px]">{saveOnDeviceNote(saveOnDevice)}</p>
          </div>
          <Toggle checked={saveOnDevice} onChange={setSaveOnDevice} label="이 기기에 조건 저장" />
        </div>
        <RecentSearchSetting />
        <AnalyticsConsentSetting className="border-line-soft border-t pt-[13px]" />
      </section>

      <section className={cn(card, "flex flex-col gap-[12px]")} aria-label="데이터 및 계정 관리">
        <h2 className="flex items-center gap-[8px] text-[17px] font-extrabold">
          <Database size={19} className="text-brand-strong" aria-hidden /> 데이터 및 계정 관리
        </h2>
        <StoredInfoList compact />
        <div className="border-line-soft flex flex-col border-t pt-[6px]">
          {session && (
            <>
              <PrivacyLink href={meTabHref("favorites", true)}>관심 공고 관리</PrivacyLink>
              <PrivacyLink href={meTabHref("interests", true)}>관심 조건 관리</PrivacyLink>
              <PrivacyLink href={routes.preparations}>신청 준비 기록 관리</PrivacyLink>
            </>
          )}
          <PrivacyLink href={`${routes.privacy}#privacy-rights`}>
            개인정보 열람·정정·삭제 요청 안내
          </PrivacyLink>
        </div>
        <div className="border-line-soft flex flex-wrap items-center gap-x-[16px] gap-y-[6px] border-t pt-[12px]">
          <button
            type="button"
            onClick={clearConditions}
            disabled={!hasStoredConditions}
            className="border-line min-h-[44px] rounded-sm border px-[12px] text-[14px] font-bold disabled:opacity-60"
          >
            저장한 조건 모두 지우기
          </button>
          {session && <WithdrawButton />}
        </div>
      </section>
    </div>
  );
}

function PrivacyLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="text-text hover:text-brand-strong flex min-h-[44px] items-center justify-between gap-[8px] text-[14px] font-bold no-underline"
    >
      {children} <ChevronRight size={16} className="text-text-tertiary shrink-0" aria-hidden />
    </Link>
  );
}
