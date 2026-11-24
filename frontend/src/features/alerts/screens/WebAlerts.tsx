"use client";

import { useRef } from "react";
import { ScrollToTop } from "@/shared/ui/ScrollToTop";
import Link from "next/link";
import { Bell, CheckCheck, Clock4, House, Sparkle, Wallet, type LucideIcon } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { alertTabs, useAlerts } from "@/features/alerts/queries";
import { usePush } from "@/features/alerts/usePush";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import type { AlertIcon } from "@/features/alerts/mocks/alerts";

const icons: Record<AlertIcon, LucideIcon> = {
  home: House,
  clock: Clock4,
  benefit: Wallet,
  notice: Sparkle,
};

export function WebAlerts() {
  const alerts = useAlerts();
  const push = usePush();
  const { data } = alerts;
  const scrollRoot = useRef<HTMLDivElement>(null);

  return (
    <WebPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0">
      <WebHeader mode="home" active="alerts" />
      <WebMain className="min-h-0 max-w-[920px] gap-0 pt-4 pb-0">
        <div
          ref={scrollRoot}
          role="region"
          aria-label="알림 센터"
          tabIndex={0}
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-0.5 pb-8"
        >
          <div className="flex flex-wrap items-end justify-between gap-4 pt-2 pb-5">
            <div className="flex flex-col gap-[6px]">
              <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">알림</h1>
              <span aria-live="polite" className="text-text-sub text-[16px]">
                {alerts.unreadText}
              </span>
            </div>
            <button
              type="button"
              onClick={alerts.readAll}
              disabled={alerts.unread === 0}
              className="bg-surface text-text inline-flex min-h-[44px] cursor-pointer items-center gap-[6px] rounded-sm border-0 px-[16px] text-[15px] font-bold"
            >
              <CheckCheck size={18} strokeWidth={2.2} aria-hidden />
              모두 읽음
            </button>
          </div>

          <section
            aria-label="알림 허용"
            className="rounded-card bg-surface mb-4 flex flex-wrap items-center gap-4 p-4"
          >
            <div className="rounded-control bg-brand-soft text-brand-strong flex size-11 shrink-0 items-center justify-center">
              <Bell size={22} aria-hidden />
            </div>
            <div className="flex min-w-[180px] flex-1 flex-col gap-1">
              <h2 className="m-0 text-base font-extrabold">이 브라우저 · 앱 알림</h2>
              <p className="text-text-sub m-0 text-sm">
                {!push.checked
                  ? "알림 설정을 확인하고 있어요"
                  : push.enabled
                    ? "이 브라우저에서 알림을 받고 있어요"
                    : "알림을 켜면 관심 공고 마감을 알려드려요"}
              </p>
            </div>
            {push.checked && alerts.loggedIn && !push.enabled && (
              <button
                type="button"
                onClick={() => void push.turnOn()}
                disabled={push.pending}
                className="rounded-control bg-brand min-h-11 cursor-pointer border-0 px-4 text-sm font-bold text-white disabled:opacity-60"
              >
                이 브라우저에서 알림 받기
              </button>
            )}
            <Link
              href={alerts.loggedIn ? `${routes.me}?tab=notifications` : routes.login}
              className="text-brand-strong inline-flex min-h-11 items-center text-sm font-bold no-underline"
            >
              알림 설정
            </Link>
            {push.error && (
              <p role="alert" className="text-danger-text m-0 w-full text-sm">
                {push.error}
              </p>
            )}
          </section>
          <div className="flex flex-col gap-4">
            <section aria-label="알림 목록" className="flex min-w-0 flex-col gap-3">
              <div
                role="group"
                aria-label="알림 분류"
                className="bg-bg sticky top-0 z-10 flex flex-wrap gap-[6px] py-2"
              >
                {alertTabs.map((t) => {
                  const on = t === alerts.tab;
                  return (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={on}
                      onClick={() => alerts.setTab(t)}
                      className={cn(
                        "rounded-pill min-h-[40px] cursor-pointer border-0 px-[16px] text-[15px] font-bold",
                        on ? "bg-brand text-white" : "bg-surface text-text-sub",
                      )}
                    >
                      {t} {alerts.countOf(t)}
                    </button>
                  );
                })}
              </div>

              {alerts.grouped.length === 0 && alerts.countOf("전체") > 0 && (
                <p className="rounded-card bg-surface text-text-sub m-0 p-6 text-center text-sm">
                  이 분류에 받은 알림이 없어요
                </p>
              )}
              {alerts.grouped.map((g) => (
                <div key={g.label} className="flex flex-col gap-1">
                  <h2 className="text-text-sub m-0 px-1 pt-2 pb-1 text-[14px] font-bold">
                    {g.label}
                  </h2>
                  {g.items.map((a) => {
                    const Icon = icons[a.icon];
                    return (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => alerts.open(a)}
                        aria-label={`${a.isRead ? "" : "읽지 않음, "}${a.kind}, ${a.title}`}
                        className={cn(
                          "rounded-card text-text hover:bg-brand-soft flex cursor-pointer items-start gap-[14px] border-0 px-5 py-4 text-left",
                          a.isRead ? "bg-surface" : "bg-row-selected",
                        )}
                      >
                        <span
                          className={cn(
                            "rounded-control flex size-[44px] flex-none items-center justify-center",
                            a.urgent
                              ? "bg-text text-white"
                              : a.isRead
                                ? "bg-fill text-text-sub"
                                : "bg-brand-soft text-brand",
                          )}
                        >
                          <Icon size={22} strokeWidth={1.8} aria-hidden />
                        </span>
                        <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                          <span className="text-text-tertiary flex justify-between gap-[10px] text-[13px]">
                            <span
                              className={cn(
                                "font-bold",
                                a.urgent ? "text-text" : "text-brand-strong",
                              )}
                            >
                              {a.kind}
                            </span>
                            <span>{a.time}</span>
                          </span>
                          <span
                            className={cn(
                              "text-[16px] leading-[1.5]",
                              a.isRead ? "font-medium" : "font-bold",
                            )}
                          >
                            {a.title}
                          </span>
                          <span className="text-text-sub text-[14px] whitespace-pre-line">
                            {a.body}
                          </span>
                        </span>
                        <span
                          aria-hidden
                          className={cn(
                            "rounded-pill mt-[8px] size-[8px] flex-none",
                            a.isRead ? "bg-transparent" : "bg-brand",
                          )}
                        />
                      </button>
                    );
                  })}
                </div>
              ))}
            </section>

            {data.settings.length > 0 && (
              <aside className="flex min-w-0 flex-col">
                <section
                  aria-label="받는 알림"
                  className="rounded-card bg-surface flex flex-col gap-[4px] px-[24px] py-[22px]"
                >
                  <div className="mb-[4px] flex items-center justify-between">
                    <h2 className="tracking-title m-0 text-[18px] font-extrabold">받는 알림</h2>
                    <Link
                      href={`${routes.me}?tab=notifications`}
                      className="text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
                    >
                      설정
                    </Link>
                  </div>
                  {data.settings.map((s) => (
                    <div key={s.label} className="flex justify-between py-[7px] text-[15px]">
                      <span>{s.label}</span>
                      {s.on ? (
                        <span className="text-brand-strong font-bold">켜짐</span>
                      ) : (
                        <span className="text-text-tertiary">꺼짐</span>
                      )}
                    </div>
                  ))}
                  <span className="border-line-soft text-text-sub mt-[6px] border-t border-solid pt-[12px] text-[14px]">
                    방해 금지 · {data.quietHours}
                  </span>
                </section>
              </aside>
            )}
          </div>
        </div>
        <ScrollToTop scrollRoot={scrollRoot} />
      </WebMain>
    </WebPage>
  );
}
