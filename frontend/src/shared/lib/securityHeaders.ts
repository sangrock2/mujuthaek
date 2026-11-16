// 보안 헤더와 CSP (2026-11-16 보안 감사 4장 프론트). next.config.ts가 빌드할 때 한 번 만들어요.
// 목표: 스크립트가 끼어들어도 토큰·화면 값을 다른 호스트로 보내지 못하게(connect-src·img-src), 외부 스크립트는 쓰는 곳만(script-src)

/** GA4 측정 ID 모양 (G-XXXX). 이 값은 GA 초기화 인라인 스크립트에 그대로 들어가서 모양을 확인해요 */
const GA_ID_PATTERN = /^G-[A-Z0-9]{4,20}$/;

/** 측정 ID가 GA4 모양일 때만 돌려줘요. 아니면 GA를 쓰지 않아요("") */
export function safeGaId(value: string | undefined): string {
  return value && GA_ID_PATTERN.test(value) ? value : "";
}

export type CspOptions = {
  /** next dev (React·Turbopack 개발 도구가 eval을 써요) */
  dev: boolean;
  /** 브라우저가 바로 부르는 API origin. 비어 있으면 같은 주소(Vercel 프록시)예요 */
  apiOrigin: string;
  /** GA를 켰는지 (측정 ID가 있을 때) */
  analytics: boolean;
  /** 카카오맵을 켰는지 (JavaScript 키가 있을 때) */
  kakaoMap: boolean;
};

// Google이 안내하는 GA4 호스트 (gtag.js 받기·수집 요청·픽셀)
const GA_SCRIPT = ["https://*.googletagmanager.com"];
const GA_CONNECT = [
  "https://*.google-analytics.com",
  "https://*.analytics.google.com",
  "https://*.googletagmanager.com",
];
const GA_IMG = ["https://*.google-analytics.com", "https://*.googletagmanager.com"];
// 카카오맵: sdk.js(dapi) → 본체 스크립트(t1.daumcdn.net) → 지도 타일·표시 이미지(*.daumcdn.net).
// SDK가 「//t1.daumcdn.net」처럼 스킴 없이 불러서 스킴 없이 적어요 (https 화면에서는 https만 맞아요)
const KAKAO_SCRIPT = ["dapi.kakao.com", "t1.daumcdn.net"];
const KAKAO_CONNECT = ["dapi.kakao.com"];
const KAKAO_IMG = ["*.daumcdn.net"];

const join = (name: string, sources: string[]) => `${name} ${[...new Set(sources)].join(" ")}`;

/**
 * 화면 CSP. Next.js는 화면 데이터를 인라인 스크립트로 넣어서 'unsafe-inline'이 필요해요.
 * nonce를 쓰려면 모든 화면을 요청마다 그려야 해서(정적·부분 사전 렌더 포기) 쓰지 않고, 대신 호스트를 좁혀요.
 */
export function contentSecurityPolicy({ dev, apiOrigin, analytics, kakaoMap }: CspOptions) {
  const script = ["'self'", "'unsafe-inline'"];
  const connect = ["'self'"];
  const img = ["'self'", "data:", "blob:"];
  if (dev) script.push("'unsafe-eval'");
  if (apiOrigin) connect.push(apiOrigin);
  if (analytics) {
    script.push(...GA_SCRIPT);
    connect.push(...GA_CONNECT);
    img.push(...GA_IMG);
  }
  if (kakaoMap) {
    script.push(...KAKAO_SCRIPT);
    connect.push(...KAKAO_CONNECT);
    img.push(...KAKAO_IMG);
  }
  return [
    "default-src 'self'",
    join("script-src", script),
    join("connect-src", connect),
    join("img-src", img),
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    "worker-src 'self'",
    "manifest-src 'self'",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** 서비스 워커 CSP: 알림을 봤는지·눌렀는지 API에 알리는 것 말고는 이 사이트만 불러요 */
export function serviceWorkerPolicy(apiOrigin: string) {
  return [
    "default-src 'self'",
    "script-src 'self'",
    join("connect-src", apiOrigin ? ["'self'", apiOrigin] : ["'self'"]),
  ].join("; ");
}

/** 쓰지 않는 브라우저 기능은 막아요 (위치·카메라·마이크 등). 알림은 이 정책과 무관한 별도 권한이에요 */
export const PERMISSIONS_POLICY = [
  "camera=()",
  "microphone=()",
  "geolocation=()",
  "payment=()",
  "usb=()",
  "serial=()",
  "hid=()",
  "midi=()",
  "display-capture=()",
  "browsing-topics=()",
].join(", ");

/** 모든 응답에 붙는 헤더 */
export function securityHeaders(options: CspOptions) {
  return [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Content-Security-Policy", value: contentSecurityPolicy(options) },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: PERMISSIONS_POLICY },
    // 다른 사이트 창과 창 참조를 나누고(window.opener), 우리 파일을 다른 사이트가 끌어가지 못하게 해요
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  ];
}
