import { routes } from "@/lib/routes";

/**
 * 조건 입력(/profile)에서 받는 판정 입력. 주거·혜택은 판정 입력 경로(applicant.*)로, 사업공간·사업 지원은 판정 엔진 입력 칸 이름으로 와요.
 * 화면에 입력 칸을 새로 만들면 여기에도 넣어 주세요.
 */
const PROFILE_INPUTS = new Set([
  "birthDate",
  "birthMonth", // 예전 서버: 출생 연월로 판정할 때 와요
  "regionCode",
  "residenceRegionCode",
  "householdHead",
  "householdSize",
  "targetGroups",
  "marital",
  "children",
  "homeOwner",
  "homelessYears",
  "subscription.months",
  "subscription.payments",
  "welfareStatuses",
  "income",
  "householdIncome", // 가구 소득 칸은 없지만 본인 소득을 넣으면 판정이 달라져요
  "assets",
  "car",
]);

/** 사업 정보 입력(/business/onboarding)에서 받는 판정 입력 */
const BUSINESS_INPUTS = new Set([
  "business.applicantType",
  "business.siteRegionCode",
  "business.history",
  "business.industryCode",
  "business.revenueByYear",
  "statuses",
  "restrictions",
]);

/**
 * 확인 필요 조건의 needs(넣으면 정해지는 입력) → 그 입력을 받는 화면. 우리 화면에 칸이 없는 입력뿐이면 undefined라 「원문 확인」이에요
 * (주거·혜택·사업공간·사업 지원 공통, 2026-10-29 QA: 넣을 칸이 없는데 「입력」으로 보내던 것)
 */
export function inputHrefOf(needs: readonly string[] | null | undefined): string | undefined {
  const names = (needs ?? []).map((n) => n.replace(/^applicant\./, ""));
  if (names.some((n) => BUSINESS_INPUTS.has(n))) return routes.bizOnboarding;
  if (names.some((n) => PROFILE_INPUTS.has(n))) return routes.profile;
  return undefined;
}
