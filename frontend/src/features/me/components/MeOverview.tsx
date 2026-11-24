"use client";

import Link from "next/link";
import {
  Bell,
  ChevronRight,
  ClipboardList,
  Heart,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { isMember, providerLabel, useSession } from "@/features/auth/session";
import { usePush } from "@/features/alerts/usePush";
import { useFavorites } from "@/features/favorites/queries";
import { useInterest, useNotificationSettings } from "@/features/me/api";
import { usePreparations } from "@/features/preparations/api";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { meTabHref } from "./MeNavigation";
import { useEmailNotificationStatus } from "./EmailNotifications";

function MeAccountCard({
  children,
  className,
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  const { data: session, isPending } = useSession();
  return (
    <section
      aria-label="계정"
      className={cn(
        "rounded-card bg-surface flex flex-wrap items-center justify-between gap-3 p-5",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-[11px]">
        <span className="rounded-pill bg-brand-soft text-brand-strong flex size-[48px] shrink-0 items-center justify-center sm:size-[54px]">
          <UserRound size={23} aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[18px] font-extrabold sm:text-[22px]">
            {isPending ? "계정 확인 중" : session ? `${session.nickname}님` : "로그인하지 않았어요"}
          </p>
          {session && (
            <p className="text-text-sub truncate text-[13px]">
              {session.providers.map((provider) => providerLabel[provider] ?? provider).join(" · ")}
            </p>
          )}
        </div>
      </div>
      {!isPending && !session && (
        <Link
          href={routes.login}
          className="text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold"
        >
          로그인하기
        </Link>
      )}
      {session && children}
    </section>
  );
}

const surface = "rounded-card bg-surface min-w-0 p-[15px] sm:p-[19px]";
const more =
  "text-brand-strong inline-flex min-h-[44px] shrink-0 items-center gap-[3px] text-[13px] font-bold no-underline";

export function MeOverview({ mobile = false }: { mobile?: boolean }) {
  const { data: session } = useSession();
  const conditions = useConditionSummary();
  const favorites = useFavorites();
  const housing = useInterest("housing");
  const support = useInterest("support");
  const business = useInterest("business");
  const preparations = usePreparations();
  const member = isMember(session);
  const interests = [housing, support, business];
  const interestCount = interests.filter((interest) => interest.value.saved).length;
  const preparing = preparations.items.filter((item) => item.status === "PREPARING").length;
  const rows = conditions.status === "ready" ? conditions.rows : [];
  const highlights = rows.filter(({ k }) =>
    ["나이", "찾아볼 지역", "세대", "무주택 기간"].includes(k),
  );
  const notificationHref = meTabHref("notifications", mobile);
  const stats = [
    {
      label: "관심 공고",
      href: meTabHref("favorites", mobile),
      icon: Heart,
      value: favorites.loading || favorites.error ? undefined : `${favorites.items.length}건`,
    },
    {
      label: "관심 조건",
      href: meTabHref("interests", mobile),
      icon: SlidersHorizontal,
      value: interests.some((interest) => interest.loading || interest.error)
        ? undefined
        : `${interestCount}개`,
    },
    {
      label: "신청 준비함",
      href: meTabHref("preparations", mobile),
      icon: ClipboardList,
      value: preparations.data ? `${preparations.items.length}건` : undefined,
      detail: preparing ? `준비 중 ${preparing}건` : undefined,
    },
  ];

  return (
    <div className="grid gap-[12px] sm:gap-[15px]">
      <MeAccountCard>
        <Link
          href={notificationHref}
          className="rounded-control border-line text-brand-strong inline-flex min-h-[44px] items-center gap-[5px] border px-[10px] text-[13px] font-bold no-underline"
        >
          <Bell size={16} aria-hidden /> 알림 설정 관리
        </Link>
      </MeAccountCard>

      <section
        aria-label="내 청약과 공고 요약"
        className="grid min-w-0 grid-cols-3 gap-[6px] sm:gap-[11px]"
      >
        {stats.map(({ label, href, icon: Icon, value, detail }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              surface,
              "text-text hover:text-brand-strong flex flex-col gap-[5px] px-[9px] no-underline sm:gap-[9px] sm:px-[14px]",
            )}
          >
            <div className="flex flex-wrap items-center gap-x-[6px] gap-y-[5px] sm:justify-between">
              <Icon size={17} className="text-brand-strong shrink-0 sm:order-2" aria-hidden />
              <span className="text-text-sub text-[12px] font-bold break-keep sm:text-[14px]">
                {label}
              </span>
            </div>
            {member && (
              <div className="flex flex-wrap items-baseline gap-x-[7px]">
                <strong className="text-[20px] leading-snug font-extrabold tabular-nums sm:text-[27px]">
                  {value ?? "—"}
                </strong>
                {detail && <span className="text-text-sub text-[12px]">{detail}</span>}
              </div>
            )}
          </Link>
        ))}
      </section>

      <section aria-label="내 조건 요약" className={cn(surface, "flex flex-col gap-[7px]")}>
        <div className="flex flex-wrap items-center justify-between gap-x-[8px]">
          <h2 className="text-[17px] font-extrabold">내 조건</h2>
          <Link href={meTabHref("conditions", mobile)} className={more}>
            자세히 보기 <ChevronRight size={16} aria-hidden />
          </Link>
        </div>
        {highlights.length > 0 ? (
          <dl className="m-0 grid grid-cols-2 gap-3">
            {highlights.map(({ k, v }) => (
              <div key={k} className="rounded-control bg-fill px-4 py-3">
                <dt className="text-text-sub text-[12px]">{k}</dt>
                <dd className="m-0 mt-[4px] text-[14px] font-bold break-words">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          conditions.status === "ready" && (
            <p className="text-text-sub text-[14px]">아직 입력한 조건이 없어요.</p>
          )
        )}
      </section>

      {member && <ChannelOverview href={notificationHref} />}
    </div>
  );
}

function ChannelOverview({ href }: { href: string }) {
  const push = usePush();
  const settings = useNotificationSettings();
  const { query: email } = useEmailNotificationStatus();
  const channels = [
    {
      label: "이 브라우저 · 앱 알림",
      status: !push.checked ? "확인 중" : push.error ? "확인 필요" : push.enabled ? "켜짐" : "꺼짐",
      on: push.enabled,
    },
    {
      label: "이메일 알림",
      status: email.isPending
        ? "확인 중"
        : email.isError
          ? "확인 필요"
          : email.data?.enabled && email.data?.verified
            ? "수신 중"
            : email.data?.email
              ? "설정 필요"
              : "미등록",
      on: email.data?.enabled && email.data?.verified,
    },
    {
      label: "방해 금지",
      status: settings.loading
        ? "확인 중"
        : settings.readError
          ? "확인 필요"
          : settings.value.quietEnabled
            ? "22:00–08:00"
            : "꺼짐",
      on: !settings.loading && !settings.readError && settings.value.quietEnabled,
    },
  ];
  return (
    <section aria-label="알림 수신 현황" className={cn(surface, "flex flex-col gap-[5px]")}>
      <div className="flex flex-wrap items-center justify-between gap-x-[8px]">
        <h2 className="text-[17px] font-extrabold">알림 수신 현황</h2>
        <Link href={href} className={more}>
          알림 설정 이동 <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      <ul className="m-0 flex list-none flex-wrap gap-[6px] p-0">
        {channels.map(({ label, status, on }) => (
          <li
            key={label}
            className={cn(
              "rounded-pill px-[9px] py-[6px] text-[12px]",
              on ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
            )}
          >
            {label} <strong className="font-extrabold">· {status}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
