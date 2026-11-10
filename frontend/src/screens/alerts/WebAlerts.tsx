"use client";

import Link from "next/link";
import { CheckCheck, Clock4, House, Sparkle, Wallet, type LucideIcon } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { alertTabs, useAlerts } from "@/features/alerts/queries";
import { usePush } from "@/features/alerts/usePush";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { AlertIcon } from "@/mocks/alerts";

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

  return (
    <WebPage>
      <WebHeader mode="home" active="alerts" />
      <WebMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <div className="flex flex-col gap-[6px]">
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">알림</h1>
            <span aria-live="polite" className="text-text-sub text-[16px]">
              {alerts.unreadText}
            </span>
          </div>
          <button
            type="button"
            onClick={alerts.readAll}
            className="bg-surface text-text inline-flex min-h-[44px] cursor-pointer items-center gap-[6px] rounded-sm border-0 px-[16px] text-[15px] font-bold"
          >
            <CheckCheck size={18} strokeWidth={2.2} aria-hidden />
            모두 읽음
          </button>
        </div>

        <div className="flex flex-wrap items-start gap-[20px]">
          <section
            aria-label="알림 목록"
            className="rounded-card-lg bg-surface flex min-w-0 flex-[999_1_600px] flex-col pt-[20px] pb-[12px]"
          >
            <div
              role="group"
              aria-label="알림 분류"
              className="flex flex-wrap gap-[6px] px-[24px] pb-[8px]"
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
                      on ? "bg-text text-white" : "bg-fill text-text-sub",
                    )}
                  >
                    {t} {alerts.countOf(t)}
                  </button>
                );
              })}
            </div>

            {alerts.grouped.map((g) => (
              <div key={g.label} className="flex flex-col">
                <h2 className="text-text-sub m-0 px-[24px] pt-[18px] pb-[6px] text-[14px] font-bold">
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
                        "text-text flex cursor-pointer items-start gap-[14px] border-0 px-[24px] py-[16px] text-left",
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

          <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-[16px]">
            <section
              aria-label="알림 허용"
              className="rounded-card bg-brand-deep flex flex-col gap-[12px] p-[24px] text-white"
            >
              <span className="tracking-title text-[18px] font-extrabold">
                {push.enabled ? "이 브라우저에서 알림을 받고 있어요" : "마감 전에 놓치지 않게"}
              </span>
              <span className="text-brand-deep-text-2 text-[14px] leading-[1.6]">
                {push.enabled
                  ? "앱이나 이메일로도 받으려면 내 정보의 알림 설정에서 바꿀 수 있어요"
                  : "알림을 켜면 관심 공고 마감 3일 전과 1일 전에 알려드려요"}
              </span>
              {!push.enabled && (
                <button
                  type="button"
                  onClick={() => void push.turnOn()}
                  aria-disabled={push.pending || undefined}
                  className="text-brand-strong min-h-[48px] cursor-pointer rounded-sm border-0 bg-white text-[15px] font-extrabold"
                >
                  이 브라우저에서 알림 받기
                </button>
              )}
              {push.error && (
                <span role="alert" className="text-[13px] font-bold text-white">
                  {push.error}
                </span>
              )}
            </section>

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
        </div>
      </WebMain>
    </WebPage>
  );
}
