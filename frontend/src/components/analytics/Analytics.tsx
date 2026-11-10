"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Script from "next/script";
import { useSyncExternalStore } from "react";
import {
  GA_DEBUG,
  GA_ID,
  onConsentChange,
  QUEUE_KEY,
  readConsent,
  writeConsent,
  type Consent,
} from "@/lib/analytics";
import { routes } from "@/lib/routes";

/**
 * GA 스크립트와 동의 배너. 측정 ID가 없으면(로컬·목업) 아무것도 그리지 않아요.
 * 동의하기 전에는 GA를 불러오지 않고, 관리자 화면에서는 배너도 GA도 띄우지 않아요(운영자 방문이 통계에 섞이지 않게).
 */
export function Analytics() {
  const pathname = usePathname();
  // 서버와 첫 렌더는 「모름」이라 아무것도 그리지 않아요(동의 여부는 이 브라우저에만 있어요)
  const consent = useSyncExternalStore<Consent | "unknown">(
    (listener) => onConsentChange(() => listener()),
    readConsent,
    () => "unknown",
  );

  if (!GA_ID || consent === "unknown" || pathname?.startsWith("/admin")) return null;
  if (consent === null) return <ConsentBanner />;
  if (consent !== "granted") return null;
  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
        strategy="afterInteractive"
      />
      <Script id="ga-init" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());gtag('config','${GA_ID}'${GA_DEBUG ? ",{debug_mode:true}" : ""});(window.${QUEUE_KEY}||[]).splice(0).forEach(function(e){gtag('event',e[0],e[1]);});`}
      </Script>
    </>
  );
}

function ConsentBanner() {
  return (
    <div
      role="dialog"
      aria-label="방문 통계 수집 동의"
      className="fixed inset-x-0 bottom-0 z-50 flex justify-center px-[16px] pb-[calc(16px+env(safe-area-inset-bottom))]"
    >
      <div className="rounded-card bg-surface text-text flex w-full max-w-[560px] flex-col gap-[12px] p-[18px] shadow-[0_8px_32px_rgba(0,0,0,0.16)]">
        <p className="m-0 text-[14px] leading-[1.6]">
          서비스를 고치는 데 쓰려고 방문 통계(Google Analytics)를 모아도 될까요? 본 화면, 들어온
          경로, 기기 종류, 원문 보기 같은 이용 행동을 모으고, 입력한 소득·자산 같은 조건 값은 보내지
          않아요.{" "}
          <Link href={routes.privacy} className="text-text-sub underline">
            개인정보 처리방침
          </Link>
        </p>
        <div className="flex justify-end gap-[8px]">
          <button
            type="button"
            onClick={() => writeConsent("denied")}
            className="rounded-control bg-fill text-text min-h-[44px] cursor-pointer border-0 px-[16px] text-[14px] font-bold"
          >
            거부
          </button>
          <button
            type="button"
            onClick={() => writeConsent("granted")}
            className="rounded-control bg-brand min-h-[44px] cursor-pointer border-0 px-[16px] text-[14px] font-bold text-white"
          >
            동의
          </button>
        </div>
      </div>
    </div>
  );
}
