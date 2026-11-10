import { useSyncExternalStore } from "react";

/** 백엔드 서버는 자동 중지로 매일 이 시간에만 켜져 있어요 (한국 시간) */
export const SERVICE_HOURS = "10:00~19:00";

// 백엔드가 응답하지 않는지 (연결 실패, 또는 Vercel·프록시가 대신 낸 502·503·504). 화면 위 안내(ServiceHoursBanner)가 봐요
let down = false;
const listeners = new Set<() => void>();

function set(next: boolean) {
  if (down === next) return;
  down = next;
  listeners.forEach((l) => l());
}

export const backendStatus = {
  markDown: () => set(true),
  markUp: () => set(false),
};

/** 프록시가 낸 게이트웨이 오류인지: 백엔드가 직접 낸 503은 Problem JSON 본문이 있어요 (예: 검수 서버 연결 실패) */
export function isGatewayError(status: number, body: unknown) {
  return (status === 502 || status === 503 || status === 504) && body === null;
}

export function useBackendDown() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => down,
    () => false,
  );
}
