"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { alertTabs, useAlerts } from "@/features/alerts/queries";
import { usePush } from "@/features/alerts/usePush";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

export function MAlerts() {
  const alerts = useAlerts();
  const push = usePush();

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <MBackHeader title="알림" backHref={routes.home} />
      <main className="flex flex-1 flex-col gap-[10px] pt-[12px] pb-[24px]">
        <div className="flex items-center justify-between px-[20px]">
          <span aria-live="polite" className="text-text-sub text-[14px]">
            {alerts.unreadText}
          </span>
          <button
            type="button"
            onClick={alerts.readAll}
            className="text-brand-strong min-h-[44px] cursor-pointer border-0 bg-transparent px-[6px] py-[1px] text-[14px] font-bold"
          >
            모두 읽음
          </button>
        </div>

        <div role="group" aria-label="알림 종류" className="flex gap-[6px] px-[20px]">
          {alertTabs.map((t) => {
            const on = t === alerts.tab;
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => alerts.setTab(t)}
                className={cn(
                  "rounded-pill min-h-[38px] cursor-pointer border-0 px-[14px] text-[14px] font-bold",
                  on ? "bg-text text-white" : "bg-fill text-text-sub",
                )}
              >
                {t} {alerts.countOf(t)}
              </button>
            );
          })}
        </div>

        {push.enabled && (
          <div className="bg-brand-soft text-brand-strong mx-[16px] my-[4px] flex flex-col gap-[4px] rounded-[20px] p-[16px]">
            <span className="text-[15px] font-extrabold">이 기기에서 알림을 받고 있어요</span>
            <span className="text-[13px] leading-[1.5]">
              앱이나 이메일로도 받으려면 받는 알림 설정에서 바꿀 수 있어요
            </span>
          </div>
        )}
        {!push.enabled && (
          <div className="bg-brand-soft mx-[16px] my-[4px] flex flex-col gap-[10px] rounded-[20px] p-[16px]">
            <span className="text-brand-strong text-[15px] font-extrabold">
              마감 전에 놓치지 않게
            </span>
            <span className="text-brand-strong text-[14px] leading-[1.5]">
              알림을 켜면 관심 공고 마감 3일 전과 1일 전에 알려드려요
            </span>
            <button
              type="button"
              onClick={() => void push.turnOn()}
              aria-disabled={push.pending || undefined}
              className="bg-brand min-h-[44px] cursor-pointer self-start rounded-sm border-0 px-[16px] text-[15px] font-extrabold text-white"
            >
              푸시 알림 켜기
            </button>
            {push.error && (
              <span role="alert" className="text-danger-text text-[13px] font-bold">
                {push.error}
              </span>
            )}
            <Link
              href={routes.install}
              className="border-brand/18 text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center border-t border-solid text-[14px] font-bold no-underline"
            >
              iPhone은 홈 화면에 추가해야 알림이 와요 · 방법 보기 ›
            </Link>
          </div>
        )}

        {alerts.grouped.map((g) => (
          <section key={g.label} className="flex flex-col">
            <h2 className="text-text-sub m-0 px-[20px] pt-[14px] pb-[6px] text-[14px] font-extrabold">
              {g.label}
            </h2>
            {g.items.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => alerts.open(a)}
                aria-label={`${a.isRead ? "" : "읽지 않음, "}${a.kind}, ${a.short?.title ?? a.title}`}
                className={cn(
                  "text-text flex w-full cursor-pointer gap-[12px] border-0 px-[20px] py-[14px] text-left",
                  a.isRead ? "bg-surface" : "bg-row-selected",
                )}
              >
                <span
                  className={cn(
                    "relative flex size-[40px] flex-none items-center justify-center rounded-sm",
                    a.urgent
                      ? "bg-text text-white"
                      : a.isRead
                        ? "bg-fill text-text-sub"
                        : "bg-brand-soft text-brand",
                  )}
                >
                  <Bell size={20} aria-hidden />
                  <span
                    aria-hidden
                    className={cn(
                      "rounded-pill absolute top-[-2px] right-[-2px] size-[13px] border-2 border-solid border-white",
                      a.isRead ? "bg-transparent" : "bg-brand",
                    )}
                  />
                </span>
                <span className="flex flex-1 flex-col gap-[3px]">
                  <span className="flex justify-between">
                    <span
                      className={cn(
                        "text-[13px] font-bold",
                        a.urgent ? "text-text" : "text-brand-strong",
                      )}
                    >
                      {a.kind}
                    </span>
                    <span className="text-text-sub text-[12px]">{a.short?.time ?? a.time}</span>
                  </span>
                  <span
                    className={cn(
                      "text-[15px] leading-[1.45]",
                      a.isRead ? "font-medium" : "font-bold",
                    )}
                  >
                    {a.short?.title ?? a.title}
                  </span>
                  <span className="text-text-sub text-[13px] whitespace-pre-line">
                    {a.short?.body ?? a.body}
                  </span>
                </span>
              </button>
            ))}
          </section>
        ))}

        <section
          aria-label="받는 알림"
          className="bg-surface mx-[16px] mt-[8px] flex flex-col rounded-[20px] px-[18px] py-[14px]"
        >
          <div className="flex items-center justify-between">
            <h2 className="m-0 text-[16px] font-extrabold">받는 알림</h2>
            <Link
              href={`${routes.me}?tab=notifications`}
              className="text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
            >
              설정
            </Link>
          </div>
          {alerts.data.settings.map((s) => (
            <div key={s.label} className="flex justify-between py-[6px] text-[14px]">
              <span>{s.label}</span>
              {s.on ? (
                <span className="text-brand-strong font-bold">켜짐</span>
              ) : (
                <span className="text-text-tertiary">꺼짐</span>
              )}
            </div>
          ))}
          <span className="border-line-soft text-text-sub mt-[6px] border-t border-solid pt-[10px] text-[13px]">
            방해 금지 · {alerts.data.quietHours}
          </span>
        </section>
      </main>
    </div>
  );
}
