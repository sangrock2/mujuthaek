import { estimateRank, marryOptions } from "@/features/profile/useProfileForm";
import type { Regions } from "@/lib/regions";
import type { RankCriteria } from "@/mocks/profile";
import type { DeviceConditions, SessionConditions } from "./types";

/** 생년월일(1997.03.15 · 19970315 · 1997-03-15)로 만 나이 */
export function ageOf(birth: string, today = new Date()) {
  const digits = birth.replace(/\D/g, "");
  if (digits.length !== 8) return null;
  const y = Number(digits.slice(0, 4));
  const m = Number(digits.slice(4, 6));
  const d = Number(digits.slice(6, 8));
  if (!y || m < 1 || m > 12 || d < 1 || d > 31) return null;
  let age = today.getFullYear() - y;
  if (today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) age -= 1;
  return age >= 0 && age < 130 ? age : null;
}

const won = (v: string) => {
  const n = Number(v.replace(/\D/g, ""));
  return n ? `${n.toLocaleString("ko-KR")}만 원` : null;
};

const marryLabel = (c: DeviceConditions) =>
  marryOptions.find((o) => o.key === c.marry)?.label ?? "";

/** "3명" → "3인". 모르면 "" */
const householdLabel = (size: string) => size.replace("명", "인");

const homelessChip = (period: string) => (period === "집이 있어요" ? "유주택" : `무주택 ${period}`);

/** 사는 곳 "서울 마포구". 안 골랐으면 "" */
const place = (c: DeviceConditions, regions: Regions) =>
  c.regionCode ? regions.label(c.regionCode) : "";

/** "부산 해운대구 외 1곳" */
const searchChip = (c: DeviceConditions, regions: Regions) => {
  const [first] = c.searchRegionCodes;
  return first && `찾아볼 지역 ${regions.label(first)}`;
};

/** 홈·가입 완료의 조건 칩. 소득·순위는 이번 탭에서 입력했을 때만 */
export function conditionChips(
  c: DeviceConditions,
  session: SessionConditions | null,
  criteria: RankCriteria[],
  regions: Regions,
) {
  const age = ageOf(c.birth);
  const rank = session ? estimateRank(criteria, session.rankChecks) : null;
  return [
    age !== null && `만 ${age}세`,
    searchChip(c, regions),
    place(c, regions),
    session && won(session.income) && `연소득 ${won(session.income)}`,
    marryLabel(c),
    ...c.statuses,
    rank && `${rank}순위`,
    homelessChip(c.homelessPeriod),
  ].filter((x): x is string => Boolean(x));
}

/** 내 정보(모바일) 칩 */
export function shortConditionChips(c: DeviceConditions, regions: Regions) {
  const age = ageOf(c.birth);
  return [
    age !== null && `만 ${age}세`,
    searchChip(c, regions),
    place(c, regions),
    [marryLabel(c), householdLabel(c.householdSize)].filter(Boolean).join(" · "),
    ...c.statuses,
    homelessChip(c.homelessPeriod),
  ].filter((x): x is string => Boolean(x));
}

export type ConditionRow = { k: string; v: string; muted?: boolean };

const MISSING = "미입력";
const NOT_STORED = "저장 안 함";

/** 내 정보 › 내 조건 표. 소득·자산·순위 세부 조건은 저장하지 않아요 */
export function conditionRows(c: DeviceConditions, regions: Regions): ConditionRow[] {
  const age = ageOf(c.birth);
  return [
    { k: "나이", v: age !== null ? `만 ${age}세` : MISSING, muted: age === null },
    {
      k: "찾아볼 지역",
      v: c.searchRegionCodes.length
        ? c.searchRegionCodes.map(regions.label).join(" · ")
        : "전체 지역",
      muted: !c.searchRegionCodes.length,
    },
    { k: "사는 곳", v: place(c, regions) || MISSING, muted: !c.regionCode },
    {
      k: "세대",
      v: `${c.head === "head" ? "세대주" : "세대원"} · ${c.householdSize ? `${householdLabel(c.householdSize)} 가구` : `가구원 수 ${MISSING}`}`,
    },
    { k: "결혼 · 자녀", v: `${marryLabel(c)} · ${c.kids ? `자녀 ${c.kids}명` : "자녀 없음"}` },
    {
      k: "지금 상황",
      v: c.statuses.length ? c.statuses.join(" · ") : MISSING,
      muted: !c.statuses.length,
    },
    { k: "연소득", v: NOT_STORED, muted: true },
    { k: "자산", v: NOT_STORED, muted: true },
    { k: "순위 세부 조건", v: NOT_STORED, muted: true },
    { k: "무주택 기간", v: c.homelessPeriod },
    {
      k: "청약통장",
      v: c.paymentCount ? `${c.bankbookPeriod} · ${c.paymentCount}회` : c.bankbookPeriod,
    },
    {
      k: "중요한 것",
      v: c.priorities.length ? c.priorities.join(" · ") : MISSING,
      muted: !c.priorities.length,
    },
  ];
}

/** 이 기기에 저장한 조건이 지워지기까지 남은 날 */
export function daysLeft(savedAt: number, ttlMs: number, now = Date.now()) {
  return Math.max(0, Math.ceil((savedAt + ttlMs - now) / (24 * 60 * 60 * 1000)));
}
