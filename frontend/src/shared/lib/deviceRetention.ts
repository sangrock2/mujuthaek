/** 주거·사업 조건 모두 이 기기에 저장한 시각부터 30일만 사용해요. */
export const DEVICE_DATA_TTL_MS = 30 * 24 * 60 * 60 * 1000;

/** 손상됐거나 미래/만료된 저장 시각은 사용하지 않아요. */
export function retainedDeviceValue(savedAt: unknown, now = Date.now()): savedAt is number {
  return (
    typeof savedAt === "number" &&
    Number.isFinite(savedAt) &&
    now >= savedAt &&
    now - savedAt < DEVICE_DATA_TTL_MS
  );
}
