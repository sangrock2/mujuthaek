"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EllipsisVertical, Share, SquarePlus } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

type Os = "ios" | "android";
type Visual = "share" | "menu" | "add" | "confirm" | "bell";
type Step = { text: string; visual: Visual; menuLabel?: string };

const steps: Record<Os, Step[]> = {
  ios: [
    { text: "Safari 아래쪽 가운데 공유 버튼을 눌러요", visual: "share" },
    { text: "메뉴를 올려서 ‘홈 화면에 추가’를 골라요", visual: "add", menuLabel: "홈 화면에 추가" },
    { text: "오른쪽 위 ‘추가’를 눌러요", visual: "confirm", menuLabel: "추가" },
    { text: "홈 화면의 무주택자들을 열고 알림을 허용해요", visual: "bell" },
  ],
  android: [
    { text: "Chrome 오른쪽 위 점 세 개 메뉴를 눌러요", visual: "menu" },
    { text: "‘홈 화면에 추가’ 또는 ‘앱 설치’를 골라요", visual: "add", menuLabel: "앱 설치" },
    { text: "‘설치’를 눌러요", visual: "confirm", menuLabel: "설치" },
    { text: "무주택자들을 열고 알림을 허용해요", visual: "bell" },
  ],
};

const tabs: { key: Os; label: string }[] = [
  { key: "ios", label: "iPhone" },
  { key: "android", label: "Android" },
];

const highlight =
  "bg-brand flex size-[40px] items-center justify-center rounded-sm text-white shadow-[0_0_0_4px_var(--color-brand-soft)]";

/** 단계마다 화면 모습을 흉내 낸 그림 (장식) */
function StepVisual({ step }: { step: Step }) {
  switch (step.visual) {
    case "share":
      return (
        <>
          <span className="bg-check-off h-[4px] w-[24px] rounded-[2px]" />
          <span className={highlight}>
            <Share size={22} />
          </span>
          <span className="bg-check-off h-[4px] w-[24px] rounded-[2px]" />
        </>
      );
    case "menu":
      return (
        <>
          <span className="rounded-pill bg-line h-[28px] flex-1" />
          <span className={highlight}>
            <EllipsisVertical size={22} strokeWidth={2.4} />
          </span>
        </>
      );
    case "add":
      return (
        <span className="bg-surface text-text flex flex-1 items-center justify-between rounded-[10px] px-[12px] py-[10px] text-[15px] font-bold shadow-[0_0_0_2px_var(--color-brand)]">
          {step.menuLabel}
          <SquarePlus size={20} className="text-brand" />
        </span>
      );
    case "confirm":
      return (
        <>
          <span className="text-text-sub flex-1 text-[14px]">무주택자들</span>
          <span className="bg-brand rounded-[10px] px-[14px] py-[8px] text-[14px] font-extrabold text-white">
            {step.menuLabel}
          </span>
        </>
      );
    case "bell":
      return (
        <>
          <span className="flex flex-1 flex-col gap-[2px] py-[8px]">
            <span className="text-text text-[13px] font-bold">
              &apos;무주택자들&apos;에서 알림을 보내려고 해요
            </span>
            <span className="text-text-sub text-[12px]">알림에는 마감·새 공고 소식이 와요</span>
          </span>
          <span className="bg-brand rounded-[10px] px-[12px] py-[8px] text-[13px] font-extrabold text-white">
            허용
          </span>
        </>
      );
  }
}

export function MInstall() {
  const [os, setOs] = useState<Os>("ios");

  useEffect(() => {
    // 브라우저에서만 알 수 있는 값: Android 기기면 Android 안내를 먼저 보여줘요
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (/Android/i.test(navigator.userAgent)) setOs("android");
  }, []);

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <MBackHeader title="홈 화면에 추가" backHref={routes.alerts} />
      <main className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[20px] pb-[28px]">
        <section className="rounded-card bg-brand-deep flex items-center gap-[16px] px-[20px] py-[22px] text-white">
          <Logo size={56} className="flex-none" />
          <span className="flex flex-col gap-[6px]">
            <span className="tracking-title text-[20px] leading-[1.35] font-extrabold">
              홈 화면에 추가하면
              <br />
              마감 알림을 받을 수 있어요
            </span>
            <span className="text-brand-deep-text text-[14px]">
              앱처럼 바로 열리고, 설치는 무료예요
            </span>
          </span>
        </section>

        <div
          role="tablist"
          aria-label="휴대폰 종류"
          className="rounded-control bg-surface grid grid-cols-2 p-[4px]"
        >
          {tabs.map((t) => {
            const on = t.key === os;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`install-tab-${t.key}`}
                aria-selected={on}
                aria-controls="install-steps"
                onClick={() => setOs(t.key)}
                className={cn(
                  "min-h-[44px] cursor-pointer rounded-[10px] border-0 text-[15px] font-bold",
                  on ? "bg-text text-white" : "text-text-sub bg-transparent",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        <div
          id="install-steps"
          role="tabpanel"
          aria-labelledby={`install-tab-${os}`}
          className="flex flex-col gap-[14px]"
        >
          {os === "ios" ? (
            <div className="rounded-tile bg-check-bg text-check-text px-[14px] py-[12px] text-[14px] leading-[1.55] font-semibold">
              iPhone은 Safari에서 홈 화면에 추가해야만 알림이 와요 · iOS 16.4 이상
            </div>
          ) : (
            <div className="rounded-tile bg-brand-soft text-brand-strong px-[14px] py-[12px] text-[14px] leading-[1.55] font-semibold">
              Android는 추가하지 않아도 Chrome에서 알림을 받을 수 있어요 · 추가하면 더 빨리 열려요
            </div>
          )}

          <ol className="m-0 flex list-none flex-col gap-[10px] p-0">
            {steps[os].map((s, i) => (
              <li
                key={s.text}
                className="bg-surface flex flex-col gap-[12px] rounded-[22px] p-[18px]"
              >
                <span className="flex items-center gap-[12px]">
                  <span className="bg-brand flex size-[30px] flex-none items-center justify-center rounded-[10px] text-[15px] font-extrabold text-white">
                    {i + 1}
                  </span>
                  <span className="text-[16px] leading-[1.45] font-bold">{s.text}</span>
                </span>
                <span
                  aria-hidden
                  className="rounded-control bg-bg text-placeholder-icon flex min-h-[52px] items-center justify-center gap-[18px] self-stretch px-[16px]"
                >
                  <StepVisual step={s} />
                </span>
              </li>
            ))}
          </ol>
        </div>

        <Link
          href={routes.alerts}
          className="rounded-tile bg-brand flex min-h-[56px] items-center justify-center text-[17px] font-extrabold text-white no-underline hover:text-white"
        >
          다 했어요 · 알림 켜기
        </Link>
        <Link
          href={routes.home}
          className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center self-center text-[15px] font-semibold no-underline"
        >
          나중에 할게요
        </Link>
      </main>
    </div>
  );
}
