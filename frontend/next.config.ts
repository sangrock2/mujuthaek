import type { NextConfig } from "next";
import { browserApiOrigin, secureApiOrigin } from "./src/shared/lib/api/origin";
import { safeGaId, securityHeaders, serviceWorkerPolicy } from "./src/shared/lib/securityHeaders";

/**
 * 백엔드 주소 (서버 전용, Vercel 환경별 HTTPS origin). 있으면 브라우저는 이 사이트 주소만 부르고
 * Vercel이 TLS로 백엔드에 넘겨요(rewrites). refresh token 쿠키는 같은 사이트 쿠키로 사용해요.
 * 없으면(로컬 개발) 넘기지 않고, 브라우저가 NEXT_PUBLIC_API_BASE_URL로 백엔드를 바로 불러요.
 */
const hosted = process.env.VERCEL === "1";
const API_ORIGIN = secureApiOrigin(process.env.API_ORIGIN, hosted);
const CANONICAL_WEB_ORIGIN = secureApiOrigin(process.env.CANONICAL_WEB_ORIGIN, hosted);
const BROWSER_API_ORIGIN = browserApiOrigin(
  process.env.NEXT_PUBLIC_API_BASE_URL,
  API_ORIGIN,
  hosted,
);
secureApiOrigin(process.env.TRAFFIC_INGEST_URL, hosted);

// 화면이 실제로 부르는 곳만 CSP에 넣어요: 이 사이트, 로컬 개발 API, 켠 경우에만 GA·카카오맵 (2026-11-16 보안 감사 4장)
const CSP_OPTIONS = {
  dev: process.env.NODE_ENV === "development",
  apiOrigin: BROWSER_API_ORIGIN,
  analytics: Boolean(safeGaId(process.env.NEXT_PUBLIC_GA_ID)),
  kakaoMap: Boolean(process.env.NEXT_PUBLIC_KAKAO_MAP_KEY),
};

const nextConfig: NextConfig = {
  output: process.env.DEPLOY_TARGET === "standalone" ? "standalone" : undefined,
  // next/image를 쓰지 않아요. 켜 두면 /_next/image가 이 사이트의 아무 파일이나 변환해 주는 공개 기능이 돼요 (404로 막아요)
  images: { unoptimized: true },
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    useOffline: true,
    // 빌드한 Next 자산의 무결성을 브라우저도 확인해요. 동적으로 배포되는 외부 SDK까지 고정하는 기능은 아니에요.
    sri: { algorithm: "sha384" },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    if (!API_ORIGIN) return [];
    return {
      // 화면보다 먼저: /login 화면은 그대로 두고 백엔드 OAuth 콜백(/login/oauth2/**)만 넘겨요
      beforeFiles: [
        { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
        { source: "/oauth2/:path*", destination: `${API_ORIGIN}/oauth2/:path*` },
        { source: "/login/oauth2/:path*", destination: `${API_ORIGIN}/login/oauth2/:path*` },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
  // 백엔드가 탈퇴 재인증에 실패하면 /mypage?withdraw=<이유>로 보내요. 내 정보 개인정보(탈퇴 버튼 자리)로 넘기고 쿼리는 그대로 붙어요
  async redirects() {
    return [
      ...(CANONICAL_WEB_ORIGIN
        ? [
            {
              source: "/:path*",
              has: [{ type: "host" as const, value: "mujuthaek.vercel.app" }],
              destination: `${CANONICAL_WEB_ORIGIN}/:path*`,
              permanent: false,
            },
          ]
        : []),
      { source: "/mypage", destination: "/me?tab=privacy", permanent: false },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders(CSP_OPTIONS),
      },
      // 관리자 화면은 검색에 나오지 않게 해요 (메타 태그와 함께, 화면을 그리기 전 응답에도)
      {
        source: "/admin/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Security-Policy", value: serviceWorkerPolicy(BROWSER_API_ORIGIN) },
        ],
      },
    ];
  },
};

export default nextConfig;
