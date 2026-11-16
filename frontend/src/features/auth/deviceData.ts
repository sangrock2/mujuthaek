"use client";

// 이 기기(브라우저 저장소)에 남는 개인 데이터 정리 (2026-11-16 보안 감사 L-3)
// 로그아웃·탈퇴하면 지우고, 다른 계정으로 로그인하면 앞 계정이 남긴 값을 지워요. 공용 PC에서 다음 사람의 판정에 쓰이지 않게요.
// 로그인하지 않은 사람은 지금처럼 이 기기에 저장해요
import { clearConditions } from "@/features/conditions/store";
import { clearRecentSearches } from "@/features/search/recent";

/** 이 기기의 조건·사업 정보·최근 검색어가 어느 계정 것인지. 계정 ID를 줄인 값이라 ID 그대로는 남지 않아요 */
const OWNER_KEY = "mujuthaek:owner";
/** 이 탭에서 회원 탈퇴를 시작한 시각 (탈퇴 완료 화면은 이 표시가 있을 때만 기기 데이터를 지워요) */
const WITHDRAWAL_KEY = "mujuthaek:withdrawal-started";
/** 탈퇴 표시를 믿는 시간: 본인 확인(다시 로그인)을 마치는 동안만 */
const WITHDRAWAL_TTL_MS = 60 * 60 * 1000;

/**
 * 지우지 않고 두는 값. 사람의 정보가 아니라 이 브라우저의 설정이에요
 * - analytics-consent: 방문 통계 허용 여부 (GA 쿠키처럼 브라우저 단위로 정해요)
 * - save-on-device: 「이 기기에 조건 저장」을 켰는지 (값이 아니라 저장 방식이에요)
 * - demo-notice-hidden: 시연 안내를 이번 탭에서 닫았는지
 */
export const KEPT_DEVICE_KEYS: readonly string[] = [
  "mujuthaek:analytics-consent",
  "mujuthaek:save-on-device",
  "mujuthaek:demo-notice-hidden",
];

const ours = (key: string) => key.startsWith("mujuthaek:") || key.startsWith("mujuthaek.");

/** 우리 키 가운데 설정이 아닌 것을 모두 지워요 (조건·사업 정보·최근 검색어·채팅 안내 기록, 앞으로 생길 키도) */
function sweep(storage: () => Storage) {
  try {
    const s = storage();
    const keys: string[] = [];
    for (let i = 0; i < s.length; i++) {
      const key = s.key(i);
      if (key !== null && ours(key) && !KEPT_DEVICE_KEYS.includes(key)) keys.push(key);
    }
    for (const key of keys) s.removeItem(key);
  } catch {
    // 저장소를 못 쓰는 브라우저면 남은 것도 없어요
  }
}

function clearPersonalData() {
  sweep(() => window.localStorage);
  sweep(() => window.sessionStorage);
  // 화면이 기억해 둔 값(메모리)도 비우고 보고 있는 화면에 알려요
  clearConditions();
  clearRecentSearches();
}

/**
 * 계정 ID → 짧은 표시 (cyrb53). 같은 계정인지만 견주려는 값이라 암호 해시가 아니어도 돼요
 * (동기라서 로그인 직후 바로 견줄 수 있어요)
 */
export function ownerMark(id: string) {
  let h1 = 0xdeadbeef ^ id.length;
  let h2 = 0x41c6ce57 ^ id.length;
  for (let i = 0; i < id.length; i++) {
    const c = id.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

function readLocal(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** 로그아웃·탈퇴: 이 기기의 조건·사업 정보·최근 검색어와 이번 탭의 값(소득·자산·매출 등)을 지워요 */
export function forgetDeviceData() {
  clearPersonalData();
}

/**
 * 로그인한 계정을 확인했을 때 불러요. 이 기기의 값이 다른 계정 것이면 지우고 이 계정 것으로 적어요.
 * 주인이 적혀 있지 않은 값(로그인 전에 입력했거나 이 기능 전에 저장한 값)은 지금 계정 것으로 보고 그대로 둬요
 */
export function claimDeviceData(userId: string) {
  const mark = ownerMark(userId);
  const owner = readLocal(OWNER_KEY);
  if (owner === mark) return;
  if (owner !== null) clearPersonalData();
  try {
    window.localStorage.setItem(OWNER_KEY, mark);
  } catch {
    // 저장소를 못 쓰면 주인도 적지 않아요 (값도 이번 화면에만 있어요)
  }
}

/** 회원 탈퇴로 본인 확인 화면에 가기 직전에 불러요 */
export function markWithdrawalStarted(now = Date.now()) {
  try {
    window.sessionStorage.setItem(WITHDRAWAL_KEY, String(now));
  } catch {
    // 표시를 못 남기면 탈퇴 완료 화면이 기기 데이터를 지우지 않아요 (내 정보에서 직접 지울 수 있어요)
  }
}

/**
 * 탈퇴 완료 화면: 이 탭에서 방금 탈퇴를 시작했는지 확인하고 표시를 지워요.
 * 로그인 없이 열 수 있는 화면이라, 링크만으로 남의 기기 데이터를 지우지 못하게 이 표시를 봐요
 */
export function consumeWithdrawalMark(now = Date.now()) {
  try {
    const started = Number(window.sessionStorage.getItem(WITHDRAWAL_KEY));
    window.sessionStorage.removeItem(WITHDRAWAL_KEY);
    return started > 0 && now - started >= 0 && now - started < WITHDRAWAL_TTL_MS;
  } catch {
    return false;
  }
}
