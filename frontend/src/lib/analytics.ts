/**
 * 방문 통계(Google Analytics 4). 측정 ID(NEXT_PUBLIC_GA_ID)가 있고 사용자가 동의했을 때만 GA 스크립트를 불러요.
 * 보내는 것은 화면 이동과 아래 이벤트뿐이에요. 회원 ID·소득·자산·나이 같은 입력값은 보내지 않아요.
 */
export const GA_ID = process.env.NEXT_PUBLIC_GA_ID ?? "";
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
  window.dispatchEvent(new CustomEvent(CONSENT_EVENT, { detail: consent }));
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
  const w = window as GaWindow;
  if (w.gtag) {
    w.gtag("event", name, params);
    return;
  }
  if (!GA_ID || readConsent() !== "granted") return;
  const queue = (w[QUEUE_KEY] ??= []);
  if (queue.length < QUEUE_MAX) queue.push([name, params]);
}
