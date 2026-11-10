"use client";

// 사업 정보 (사업공간 · 사업 지원 판정 입력). 조건 입력과 같이 이 기기에 저장하고, 매출은 이번 탭에서만 써요
import { useSyncExternalStore } from "react";
import { snapshotRegions } from "@/lib/regions";
import type { BizStage } from "@/mocks/business";

/** 이 기기에 저장하는 사업 정보. 매출은 넣지 않아요 */
export type BizProfileInput = {
  stage: BizStage;
  /** 사업 중일 때 개인 · 법인 (모르면 "") */
  applicantType: "" | "INDIVIDUAL" | "CORPORATION";
  /** industries의 key (모르면 "") */
  industry: string;
  /** 업력 개월 (사업 중일 때) */
  months: string;
  /** 직원 수 (나 포함). 판정에는 아직 쓰지 않아요 */
  employees: string;
  /** 예비 창업은 희망 지역, 사업 중은 사업장 소재지 (시·도 2자리 또는 시·군·구 5자리, 모르면 "") */
  regionCode: string;
  /** 필요한 공간 (STARTUP_SPACE · SHOP_RENTAL · MEETING_ROOM) */
  needs: string[];
  /** 업종 코드 직접 입력 (한국표준산업분류 11차 5자리). 있으면 업종 선택지의 대표 코드 대신 써요 */
  industryCode?: string;
  /** 해당 유형 코드 (소상공인 · 사회적기업 …). 해당 없음이면 빈 목록, 아직 안 골랐으면 null */
  statuses?: string[] | null;
};

/** 이번 탭에서만 쓰는 사업 정보: 매출, 신청 제한 사유 (민감해서 기기에 저장하지 않아요) */
export type BizSession = {
  /** 연 매출 (만 원) */
  revenue: string;
  /** 고른 신청 제한 사유 코드. 해당 없음이면 빈 목록, 아직 안 골랐으면 null */
  restrictions: string[] | null;
};

export const emptyBizSession: BizSession = { revenue: "", restrictions: null };

export type BizProfileSnapshot =
  { status: "loading" } | { status: "ready"; profile: BizProfileInput | null; session: BizSession };

/**
 * 신청 제한 사유 (판정 엔진 Codes의 사업공간 · 창업지원 신청 제한 사유). 공고의 "해당하면 신청할 수 없어요" 조건에 써요
 */
export const restrictionOptions = [
  { code: "TAX_ARREARS", label: "국세·지방세 체납 중" },
  { code: "CREDIT_DELINQUENT", label: "금융기관 채무불이행·불량거래자" },
  { code: "BUSINESS_SUSPENDED", label: "휴업 중인 사업자" },
  { code: "PROGRAM_SANCTION", label: "창업지원사업 참여 제한 제재 중" },
  { code: "CLAWBACK_UNPAID", label: "환수금 반환이 끝나지 않음" },
  { code: "SUBSIDY_EXCLUDED", label: "보조사업 수행 배제 대상" },
  { code: "WAGE_ARREARS", label: "체불사업주 명단 공개 대상" },
  { code: "ADULT_WARD", label: "피성년후견인·피한정후견인" },
  { code: "LH_EMPLOYEE_FAMILY", label: "LH 직원과 그 배우자·부모·자녀" },
] as const;

/**
 * 업종 선택지 → 한국표준산업분류(11차) 세세분류 대표 코드. 판정 엔진은 공고의 업종 코드(2~5자리)가 이 코드의 앞부분이면 해당한다고 봐요.
 * 묶음(group)으로 나눠 보여주고, 코드 하나로 정할 수 없는 "그 밖의 제조" · "기타"만 코드를 보내지 않아 업종 조건을 확인 필요로 둬요.
 * key는 저장값이라 바꾸지 않아요 (예전 선택지 SOFTWARE · CONTENT 등도 그대로 읽혀요)
 */
export const industries = [
  { group: "IT · 소프트웨어", key: "SOFTWARE", label: "소프트웨어 개발", code: "58222" },
  { group: "IT · 소프트웨어", key: "GAME", label: "게임 개발", code: "58211" },
  { group: "IT · 소프트웨어", key: "IT_SERVICE", label: "IT 서비스 · 외주 개발", code: "62010" },
  { group: "IT · 소프트웨어", key: "PLATFORM", label: "플랫폼 · 앱 서비스", code: "63120" },
  { group: "IT · 소프트웨어", key: "DATA_AI", label: "데이터 · AI", code: "62090" },
  { group: "음식점 · 카페", key: "FOOD", label: "음식점", code: "56111" },
  { group: "음식점 · 카페", key: "CAFE", label: "카페", code: "56221" },
  { group: "음식점 · 카페", key: "BAKERY", label: "제과점 · 베이커리", code: "56191" },
  {
    group: "판매 · 유통",
    key: "ONLINE_SALES",
    label: "온라인 판매 (쇼핑몰 · 스마트스토어)",
    code: "47912",
  },
  { group: "판매 · 유통", key: "RETAIL", label: "종합 소매 (매장)", code: "47190" },
  { group: "판매 · 유통", key: "RETAIL_FOOD", label: "식품 소매", code: "47219" },
  { group: "판매 · 유통", key: "RETAIL_CLOTH", label: "의류 소매", code: "47419" },
  { group: "판매 · 유통", key: "RETAIL_COSMETIC", label: "화장품 소매", code: "47813" },
  { group: "콘텐츠 · 디자인", key: "DESIGN", label: "디자인", code: "73203" },
  { group: "콘텐츠 · 디자인", key: "CONTENT", label: "영상 · 콘텐츠 제작", code: "59111" },
  { group: "콘텐츠 · 디자인", key: "PUBLISH", label: "출판 · 웹툰", code: "58119" },
  { group: "콘텐츠 · 디자인", key: "MUSIC", label: "음악 · 오디오", code: "59201" },
  { group: "콘텐츠 · 디자인", key: "AD", label: "광고 · 마케팅 대행", code: "71310" },
  { group: "제조", key: "MFG_FOOD", label: "식품 제조", code: "10799" },
  { group: "제조", key: "MFG_COSMETIC", label: "화장품 제조", code: "20423" },
  { group: "제조", key: "MFG_CLOTH", label: "의류 제조", code: "14199" },
  { group: "제조", key: "MFG_ELECTRONIC", label: "전자부품 제조", code: "26299" },
  { group: "제조", key: "MFG_MACHINE", label: "기계 제조", code: "29199" },
  { group: "제조", key: "MANUFACTURING", label: "그 밖의 제조", code: null },
  { group: "서비스", key: "EDU", label: "교육 · 학원", code: "85669" },
  { group: "서비스", key: "BEAUTY", label: "미용", code: "96112" },
  { group: "서비스", key: "CONSULT", label: "경영 컨설팅", code: "71531" },
  { group: "서비스", key: "LAUNDRY", label: "세탁", code: "96911" },
  { group: "농림 · 기타", key: "AGRI", label: "농업", code: "01110" },
  { group: "농림 · 기타", key: "OTHER", label: "기타", code: null },
] as const;

/** 업종 선택지를 묶음별로 (select의 optgroup) */
export const industryGroups = Array.from(new Set(industries.map((i) => i.group))).map((group) => ({
  group,
  items: industries.filter((i) => i.group === group),
}));

export const needOptions = [
  { key: "STARTUP_SPACE", label: "사무실 · 창업 공간" },
  { key: "SHOP_RENTAL", label: "상가" },
  { key: "MEETING_ROOM", label: "회의실" },
] as const;

export const emptyBizProfile: BizProfileInput = {
  stage: "pre",
  applicantType: "",
  industry: "",
  months: "",
  employees: "",
  regionCode: "",
  needs: [],
  industryCode: "",
  statuses: null,
};

/** 해당 유형 (판정 엔진 Codes의 사업공간 · 창업지원 유형). 공고의 「소상공인」「사회적기업」 같은 대상 조건에 써요 */
export const statusOptions = [
  { code: "SMALL_BUSINESS", label: "소상공인" },
  { code: "SME", label: "중소기업" },
  { code: "VENTURE_COMPANY", label: "벤처기업" },
  { code: "ONE_PERSON_CREATIVE", label: "1인 창조기업" },
  { code: "WOMAN", label: "여성 (대표자)" },
  { code: "CAREER_BREAK_WOMAN", label: "경력단절여성" },
  { code: "DISABLED", label: "장애인" },
  { code: "STUDENT", label: "대학생 · 대학원생" },
  { code: "NATIONAL_MERIT", label: "국가유공자 등 보훈대상자" },
  { code: "SOCIAL_ENTERPRISE", label: "사회적기업" },
  { code: "PRE_SOCIAL_ENTERPRISE", label: "예비사회적기업" },
  { code: "SOCIAL_COOPERATIVE", label: "사회적협동조합" },
  { code: "VILLAGE_ENTERPRISE", label: "마을기업" },
  { code: "SELF_SUFFICIENCY_ENTERPRISE", label: "자활기업" },
  { code: "SOCIAL_VENTURE", label: "소셜벤처" },
] as const;

/** 업종 코드 직접 입력이 올바른지 (5자리 숫자) */
export const validIndustryCode = (v: string | undefined) => /^\d{5}$/.test(v ?? "");

const DEVICE_KEY = "mujuthaek:business:v1";
const REVENUE_KEY = "mujuthaek:business:revenue";
const RESTRICTIONS_KEY = "mujuthaek:business:restrictions";
/** 조건 입력의 "이 기기에 저장" 설정을 같이 따라요 */
const SAVE_PREF_KEY = "mujuthaek:save-on-device";
const SESSION_DEVICE_KEY = "mujuthaek:business:device-session";

const LOADING: BizProfileSnapshot = { status: "loading" };

function read(storage: () => Storage, key: string): string | null {
  try {
    return storage().getItem(key);
  } catch {
    return null;
  }
}

function write(storage: () => Storage, key: string, value: string | null) {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, value);
  } catch {
    // 저장소를 못 쓰면(사파리 프라이빗 등) 이번 화면에서만 써요
  }
}

const local = () => window.localStorage;
const session = () => window.sessionStorage;

function readSnapshot(): BizProfileSnapshot {
  const onDevice = read(local, SAVE_PREF_KEY) !== "false";
  const raw = read(onDevice ? local : session, onDevice ? DEVICE_KEY : SESSION_DEVICE_KEY);
  let profile: BizProfileInput | null = null;
  try {
    profile = raw ? { ...emptyBizProfile, ...(JSON.parse(raw) as Partial<BizProfileInput>) } : null;
  } catch {
    profile = null;
  }
  let restrictions: string[] | null = null;
  try {
    const raw = read(session, RESTRICTIONS_KEY);
    restrictions = raw ? (JSON.parse(raw) as string[]) : null;
  } catch {
    restrictions = null;
  }
  return {
    status: "ready",
    profile,
    session: { revenue: read(session, REVENUE_KEY) ?? "", restrictions },
  };
}

let snapshot: BizProfileSnapshot | null = null;
const listeners = new Set<() => void>();

function emit() {
  snapshot = readSnapshot();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key.startsWith("mujuthaek:")) emit();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot() {
  if (!snapshot) snapshot = readSnapshot();
  return snapshot;
}

export function useBizProfileInput(): BizProfileSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, () => LOADING);
}

export function saveBizProfile(profile: BizProfileInput, { revenue, restrictions }: BizSession) {
  const onDevice = read(local, SAVE_PREF_KEY) !== "false";
  write(
    onDevice ? local : session,
    onDevice ? DEVICE_KEY : SESSION_DEVICE_KEY,
    JSON.stringify(profile),
  );
  write(session, REVENUE_KEY, revenue || null);
  write(session, RESTRICTIONS_KEY, restrictions === null ? null : JSON.stringify(restrictions));
  emit();
}

/** "3,200" → 3200. 비었거나 숫자가 없으면 null */
export function digits(v: string): number | null {
  const d = v.replace(/\D/g, "");
  return d ? Number(d) : null;
}

/** 판정 엔진의 사업 입력 (JudgmentApplicantRequest.business). 모르는 칸은 보내지 않아 확인 필요로 둬요 */
export type BusinessApplicant = {
  applicantType?: "INDIVIDUAL" | "CORPORATION";
  hasSite?: boolean;
  siteRegionCode?: string;
  /** 사업 이력. 예비 창업이면 빈 목록 (사업한 적 없음) */
  history?: { openedOn: string; closedOn?: string }[];
  industryCode?: string;
  /** 연도 → 매출 (원). 판정할 때만 보내고 저장하지 않아요 */
  revenueByYear?: Record<string, number>;
};

const ymd = (d: Date) => d.toISOString().slice(0, 10);

/** 사업 정보 → 판정 입력. 업력은 오늘에서 개월 수만큼 앞을 개업일로, 매출은 작년 매출로 봐요 */
export function toBusinessApplicant(
  p: BizProfileInput,
  revenueManWon: string,
  today = new Date(),
): BusinessApplicant {
  const code = validIndustryCode(p.industryCode)
    ? p.industryCode
    : (industries.find((i) => i.key === p.industry)?.code ?? undefined);
  if (p.stage === "pre") {
    return { applicantType: "INDIVIDUAL", hasSite: false, history: [], industryCode: code };
  }
  const months = digits(p.months);
  const opened = new Date(today);
  if (months !== null) opened.setMonth(opened.getMonth() - months);
  const revenue = digits(revenueManWon);
  return {
    applicantType: p.applicantType || undefined,
    hasSite: p.regionCode ? true : undefined,
    siteRegionCode: p.regionCode || undefined,
    history: months !== null ? [{ openedOn: ymd(opened) }] : undefined,
    industryCode: code,
    revenueByYear:
      revenue !== null ? { [String(today.getFullYear() - 1)]: revenue * 10_000 } : undefined,
  };
}

/** 사업공간 홈 "내 사업 정보" 칩 */
export function profileChips(p: BizProfileInput | null): string[] {
  if (!p) return [];
  const industry = industries.find((i) => i.key === p.industry)?.label;
  const employees = digits(p.employees);
  const region = p.regionCode ? snapshotRegions.label(p.regionCode) : null;
  return [
    p.stage === "pre" ? "예비 창업" : "사업 중",
    industry,
    p.stage === "run" && digits(p.months) !== null ? `업력 ${digits(p.months)}개월` : null,
    employees !== null ? `${employees}인` : null,
    region && (p.stage === "pre" ? `희망 지역 ${region}` : `사업장 ${region}`),
    ...(p.statuses ?? []).map((c) => statusOptions.find((o) => o.code === c)?.label),
  ].filter((c): c is string => Boolean(c));
}
