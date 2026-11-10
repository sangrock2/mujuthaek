// 청약 가점 (민영주택 가점제, 84점 만점). 기준은 백엔드 POST /api/v1/eligibility/subscription-score예요.
// 이 파일의 calculateScore는 목업 모드에서 쓰는 같은 규칙(백엔드 rule/SubscriptionScore.java를 옮긴 것)이에요.
// 규칙을 바꾸면 백엔드와 같이 바꿔요

/** 가점 입력: 판정 입력(구간 값)이 아니라 정확한 값이에요. 저장하지 않아요 */
export type ScoreInput = {
  /** 생년월일 "1997-03-15" */
  birthDate?: string;
  marital?: "SINGLE" | "MARRIED" | "ENGAGED";
  /** 혼인신고 연월 "2022-05" (기혼일 때만) */
  marriedOn?: string;
  /** 집이 있으면 true (무주택 기간 0점) */
  homeOwner?: boolean;
  /** 무주택이 된 연월 "2020-01". 집을 가진 적이 없으면 태어난 달 */
  homelessSince?: string;
  /** 부양가족 수 (나를 뺀 세대원) */
  dependents?: number;
  /** 청약통장 처음 가입한 연월 "2023-05" */
  joinedOn?: string;
};

export type ScoreItemKey = "HOMELESS_PERIOD" | "DEPENDENTS" | "SUBSCRIPTION_PERIOD";

/** 항목 하나. points는 입력이 비어 계산하지 못하면 null (reason에 넣을 칸) */
export type ScoreItem = { key: ScoreItemKey; points: number | null; max: number; reason: string };

/** 백엔드 SubscriptionScore.Score */
export type Score = { total: number; max: number; items: ScoreItem[]; missingInputs: string[] };

export const MAX_HOMELESS = 32;
export const MAX_DEPENDENTS = 35;
export const MAX_SUBSCRIPTION = 17;
export const SCORE_MAX = MAX_HOMELESS + MAX_DEPENDENTS + MAX_SUBSCRIPTION;

type Ymd = { y: number; m: number; d: number };

/** "2026-11-11" · 연월 "2026-11"(그 달 1일) */
const ymd = (s: string): Ymd => {
  const [y, m, d] = s.split("-").map(Number);
  return { y, m, d: d || 1 };
};

const before = (a: Ymd, b: Ymd) => a.y * 10_000 + a.m * 100 + a.d < b.y * 10_000 + b.m * 100 + b.d;

/** n년 뒤 같은 날 (2월 29일생은 평년이면 2월 28일, java LocalDate.plusYears와 같아요) */
function plusYears(a: Ymd, n: number): Ymd {
  const y = a.y + n;
  const last = new Date(Date.UTC(y, a.m, 0)).getUTCDate();
  return { y, m: a.m, d: Math.min(a.d, last) };
}

/** 꽉 찬 년 수 (java Period.between(start, ref).getYears()) */
function fullYears(start: Ymd, ref: Ymd) {
  const months = (ref.y - start.y) * 12 + (ref.m - start.m) - (ref.d < start.d ? 1 : 0);
  return Math.floor(months / 12);
}

/** 연월(그 달 1일)부터 꽉 찬 개월 수. 기준일이 앞이면 0 (백엔드 Periods.fullMonths) */
function fullMonths(from: string, ref: Ymd) {
  const f = ymd(from);
  return Math.max(0, (ref.y - f.y) * 12 + (ref.m - f.m));
}

function homeless(a: ScoreInput, ref: Ymd, missing: string[]): ScoreItem {
  const item = (points: number | null, reason: string): ScoreItem => ({
    key: "HOMELESS_PERIOD",
    points,
    max: MAX_HOMELESS,
    reason,
  });
  if (a.homeOwner) return item(0, "집이 있으면 무주택 기간은 0점이에요");
  if (!a.birthDate) {
    missing.push("applicant.birthDate");
    return item(null, "생년월일을 넣으면 계산돼요");
  }
  if (!a.homelessSince) {
    missing.push("applicant.homelessSince");
    return item(null, "무주택 시작 연월을 넣으면 계산돼요");
  }
  const thirty = plusYears(ymd(a.birthDate), 30);
  let start = thirty;
  if (a.marital === "MARRIED") {
    if (!a.marriedOn) {
      missing.push("applicant.marriedOn");
      return item(null, "혼인신고 연월을 넣으면 계산돼요");
    }
    const married = ymd(a.marriedOn);
    if (before(married, thirty)) start = married;
  }
  const from = ymd(a.homelessSince);
  if (before(start, from)) start = from;
  if (before(ref, start)) {
    const young = start === thirty && a.marital !== "MARRIED";
    return item(
      0,
      young ? "만 30세 전 미혼이라 0점이에요" : "무주택 기간을 세기 시작하기 전이라 0점이에요",
    );
  }
  const years = fullYears(start, ref);
  return item(Math.min(MAX_HOMELESS, 2 + 2 * years), years === 0 ? "1년 미만" : `${years}년 이상`);
}

function dependents(a: ScoreInput, missing: string[]): ScoreItem {
  const item = (points: number | null, reason: string): ScoreItem => ({
    key: "DEPENDENTS",
    points,
    max: MAX_DEPENDENTS,
    reason,
  });
  if (a.dependents === undefined) {
    missing.push("applicant.dependents");
    return item(null, "부양가족 수를 넣으면 계산돼요");
  }
  return item(Math.min(MAX_DEPENDENTS, 5 + 5 * a.dependents), `${a.dependents}명`);
}

function subscription(a: ScoreInput, ref: Ymd, missing: string[]): ScoreItem {
  const item = (points: number | null, reason: string): ScoreItem => ({
    key: "SUBSCRIPTION_PERIOD",
    points,
    max: MAX_SUBSCRIPTION,
    reason,
  });
  if (!a.joinedOn) {
    missing.push("applicant.subscription.joinedOn");
    return item(null, "청약통장 가입 연월을 넣으면 계산돼요");
  }
  const months = fullMonths(a.joinedOn, ref);
  if (months < 6) return item(1, "6개월 미만");
  if (months < 12) return item(2, "1년 미만");
  const years = Math.floor(months / 12);
  return item(Math.min(MAX_SUBSCRIPTION, 2 + years), `${years}년 이상`);
}

/** 가점 계산 (백엔드와 같은 규칙). today는 "2026-11-11" (한국 날짜) */
export function calculateScore(a: ScoreInput, today: string): Score {
  const ref = ymd(today);
  const missing: string[] = [];
  const items = [homeless(a, ref, missing), dependents(a, missing), subscription(a, ref, missing)];
  const total = items.reduce((t, i) => t + (i.points ?? 0), 0);
  return { total, max: SCORE_MAX, items, missingInputs: missing };
}

/** 총점 링: 브랜드 색이 차지하는 각도 */
export function ringStyle(total: number) {
  const deg = Math.round((total / SCORE_MAX) * 360);
  return {
    background: `conic-gradient(var(--color-brand) ${deg}deg, var(--color-brand-soft) 0deg)`,
  };
}
