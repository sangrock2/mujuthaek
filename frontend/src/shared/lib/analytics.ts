/**
 * 방문 통계(Google Analytics 4). 측정 ID(NEXT_PUBLIC_GA_ID)가 있고 사용자가 동의했을 때만 GA 스크립트를 불러요.
 * 보내는 것은 화면 이동과 아래 이벤트뿐이에요. 회원 ID·소득·자산·나이 같은 입력값은 보내지 않아요.
 */
import { safeGaId } from "./securityHeaders";

/** GA4 모양(G-…)이 아니면 GA를 쓰지 않아요. 이 값은 인라인 초기화 스크립트에 들어가요 (2026-11-16 보안 감사 4장) */
export const GA_ID = safeGaId(process.env.NEXT_PUBLIC_GA_ID);
/** 개발 중 확인용: 1이면 이벤트가 GA 「DebugView」에만 보이고 보고서 숫자에는 섞이지 않아요 */
export const GA_DEBUG = process.env.NEXT_PUBLIC_GA_DEBUG === "1";

const CONSENT_KEY = "mujuthaek:analytics-consent";
const CONSENT_EVENT = "mujuthaek:analytics-consent";

export type Consent = "granted" | "denied" | null;

export function readConsent(): Consent {
  try {
    const value = localStorage.getItem(CONSENT_KEY);
    return value === "granted" || value === "denied" ? value : null;
  } catch {
    return null;
  }
}

export function writeConsent(consent: "granted" | "denied") {
  try {
    localStorage.setItem(CONSENT_KEY, consent);
  } catch {
    // 저장이 막힌 브라우저면 이번 방문 동안만 적용돼요
  }
  if (consent === "denied") stopAnalytics();
  window.dispatchEvent(new CustomEvent(CONSENT_EVENT, { detail: consent }));
}

/**
 * 동의를 철회하면(또는 거부하면) 이미 불러온 GA도 바로 멈추고 GA 쿠키(_ga, _ga_…)를 지워요 (2026-11-16 보안 감사 4장).
 * 불러온 gtag.js는 페이지를 새로 열 때까지 남지만 ga-disable 표시가 있으면 아무것도 보내지 않아요
 */
function stopAnalytics() {
  if (typeof window === "undefined") return;
  if (GA_ID) (window as unknown as Record<string, unknown>)[`ga-disable-${GA_ID}`] = true;
  try {
    const names = document.cookie
      .split(";")
      .map((part) => part.split("=")[0].trim())
      .filter((name) => name === "_ga" || name.startsWith("_ga_"));
    // GA는 쿠키를 가장 상위 도메인(예: .mujuthaek.store)에 둬요. 호스트의 상위 도메인마다 지워 봐요
    const labels = location.hostname.split(".");
    const domains = [""];
    for (let i = 0; i < labels.length - 1; i++)
      domains.push(`; domain=.${labels.slice(i).join(".")}`);
    for (const name of names)
      for (const domain of domains)
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain}`;
  } catch {
    // 쿠키를 못 읽는 환경이면 지울 것도 없어요
  }
}

export function onConsentChange(listener: (consent: Consent) => void) {
  const handler = (e: Event) => listener((e as CustomEvent<Consent>).detail ?? readConsent());
  window.addEventListener(CONSENT_EVENT, handler);
  return () => window.removeEventListener(CONSENT_EVENT, handler);
}

/** 관리자 화면 「트래픽 → 이용 흐름」에 쓰는 이벤트 (백엔드 TrafficService.FUNNEL과 같은 이름) */
export type AnalyticsEvent =
  | "conditions_complete" // 조건 입력을 마치고 저장함
  | "judgment_run" // 조건이 있는 상태에서 공고 판정 결과를 봄
  | "notice_source_open" // 공고 원문(PDF·기관 사이트)을 엶
  | "notice_bookmark"; // 관심 등록

/** GA 스크립트가 준비되기 전에 나온 이벤트를 잠깐 모아 두는 곳. GA 초기화 스크립트가 config 뒤에 보내요 */
export const QUEUE_KEY = "__mujuthaekGaQueue";
const QUEUE_MAX = 20;

type GaWindow = Window & {
  gtag?: (...args: unknown[]) => void;
  [QUEUE_KEY]?: [AnalyticsEvent, Record<string, string | number>][];
};

/**
 * 이벤트를 보내요. GA를 불러오지 않았으면(측정 ID 없음·동의 안 함) 아무 일도 하지 않아요.
 * 공고 주소로 바로 들어오면 화면이 GA 스크립트보다 먼저 그려져요. 그때 나온 이벤트는 모아 뒀다가 GA가 준비되면 보내요
 */
export function track(name: AnalyticsEvent, params: Record<string, string | number> = {}) {
  if (typeof window === "undefined") return;
  // 철회한 뒤에는 이미 불러온 gtag가 있어도 보내지 않아요
  if (!GA_ID || readConsent() !== "granted") return;
  const w = window as GaWindow;
  if (w.gtag) {
    w.gtag("event", name, params);
    return;
  }
  const queue = (w[QUEUE_KEY] ??= []);
  if (queue.length < QUEUE_MAX) queue.push([name, params]);
}
