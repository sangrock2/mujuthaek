import type { NextConfig } from "next";

/**
 * 백엔드 주소 (서버 전용, Vercel 환경별로 설정. 예: http://3.37.131.73). 있으면 브라우저는 이 사이트 주소만 부르고
 * Vercel이 백엔드로 대신 넘겨요(rewrites). 백엔드는 HTTPS·도메인이 없어도 되고, refresh 토큰 쿠키(SameSite=Lax)가 같은 사이트 쿠키가 돼요.
 * 없으면(로컬 개발) 넘기지 않고, 브라우저가 NEXT_PUBLIC_API_BASE_URL로 백엔드를 바로 불러요.
 */
const API_ORIGIN = process.env.API_ORIGIN?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    useOffline: true,
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
    return [{ source: "/mypage", destination: "/me?tab=privacy", permanent: false }];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
        ],
      },
    ];
  },
};

export default nextConfig;
