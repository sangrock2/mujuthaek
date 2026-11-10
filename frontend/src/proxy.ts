import type { NextFetchEvent, NextRequest } from "next/server";

/**
 * 화면 요청 기록: 화면 주소를 직접 연 요청(첫 방문·새로 고침·봇)을 api 트래픽 기록으로 넘겨요.
 * 화면만 긁어 가는 봇은 api를 부르지 않아서 GA에도 api 요청 기록에도 안 잡히거든요.
 * 응답을 기다리게 하지 않고 뒤에서 보내요. 설정(서버 전용 환경 변수)이 없으면 아무것도 하지 않아요.
 * 보내는 값: 경로(쿼리 제외), 브라우저 종류(User-Agent), 접속 IP. 회원 정보·쿠키는 보내지 않아요.
 */
const INGEST_URL = process.env.TRAFFIC_INGEST_URL; // api 주소 (예: http://api:8080)
const INGEST_TOKEN = process.env.TRAFFIC_INGEST_TOKEN; // api의 TRAFFIC_INGEST_TOKEN과 같은 값

export function proxy(request: NextRequest, event: NextFetchEvent) {
  if (!INGEST_URL || !INGEST_TOKEN || request.method !== "GET") return;
  // 사이트 안에서 이동할 때 받는 화면 데이터(RSC)는 빼요. 사람의 화면 이동은 GA가 세요
  if (request.nextUrl.searchParams.has("_rsc")) return;
  // 운영에서는 Caddy가 붙여 주는 X-Forwarded-For의 첫 값이 접속한 곳이에요
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  event.waitUntil(
    fetch(`${INGEST_URL}/api/internal/traffic/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Traffic-Token": INGEST_TOKEN },
      body: JSON.stringify({
        path: request.nextUrl.pathname,
        userAgent: request.headers.get("user-agent"),
        ip,
      }),
      signal: AbortSignal.timeout(2000),
    }).catch(() => {
      // 기록을 못 보내도 화면은 그대로 보여 줘요
    }),
  );
}

export const config = {
  matcher: [
    {
      // 정적 파일·이미지·서비스 워커·메타 파일은 빼요(점이 들어간 경로는 파일). 백엔드로 넘기는 경로(api·OAuth)도 빼요
      source: "/((?!_next/|api/|oauth2/|login/oauth2/|.*\\..*).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
