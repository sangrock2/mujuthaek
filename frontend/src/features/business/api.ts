"use client";

// 사업공간 실제 API: POST /api/v1/spaces/search (맞춤 목록) · POST /api/v1/spaces/{id}/evaluate (공간 하나의 판정)
// 사업 지원: POST /api/v1/supports/search · POST /api/v1/supports/{id}/evaluate (창업지원 사업, 상세 API 없이 판정 응답으로)
// 공간 상세: 공고면 공고 상세(GET /notices/{id}) + 판정, 모집 정책(K-Startup·기업마당)은 판정 응답(기간·지역·자격 조건)만으로
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ListingVerdict } from "@/components/ui/Badge";
import {
  toBusinessApplicant,
  useBizProfileInput,
  type BizProfileInput,
  type BizSession,
  type BusinessApplicant,
} from "@/features/business/profile";
import { birthDateOf, judgeRegionCode } from "@/features/conditions/applicant";
import { inputHrefOf } from "@/features/conditions/needs";
import { useConditions } from "@/features/conditions/store";
import type { DeviceConditions } from "@/features/conditions/types";
import { formatPeriod } from "@/features/notice/format";
import { providerName, tagLabel } from "@/features/notice/labels";
import { useNotice } from "@/features/notice/queries";
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import { snapshotRegions } from "@/lib/regions";
import {
  type BusinessSummary,
  type SpaceDetail,
  type SpaceItem,
  type SpaceRule,
  type SpaceType,
  type SupportItem,
  type SupportList,
  type SupportType,
} from "@/mocks/business";
import { routes } from "@/lib/routes";

type Overall = "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";
type ApiSpaceType = "STARTUP_SPACE" | "SHOP_RENTAL" | "MEETING_ROOM";

/** POST /api/v1/spaces/search 한 줄 (백엔드 SpaceSearchResponse.Item) */
type ApiSpaceItem = {
  id: string;
  /** 사업공간 모집 정책(K-Startup·기업마당)이면 true: 공고 상세 대신 판정 응답으로 상세를 보여줘요 */
  policy: boolean;
  source: PolicySource | null;
  spaceType: ApiSpaceType;
  title: string;
  provider: string | null;
  regionName: string | null;
  /** 모집 정책의 운영 기관 (출처 칸) */
  organization: string | null;
  /** 법정동코드 10자리. 전국은 빈 목록, 모르면 null */
  regionCodes: string[] | null;
  status: "UPCOMING" | "APPLYING" | "ALWAYS";
  applyStart: string | null;
  applyEnd: string | null;
  dday: number | null;
  overall: Overall;
  /** CONDITIONS_NOT_READY: 판정 틀이 아직 없어요 */
  reason: string | null;
  detailUrl: string | null;
  tags: string[];
  /** 마감일 대신 쓰는 신청 기간 안내 (「예산 소진 시까지」). 없으면 null */
  applyNote?: string | null;
};

export type ApiSpaceSearch = {
  counts: { eligible: number; needsInput: number; ineligible: number };
  typeCounts: Record<ApiSpaceType, number>;
  items: ApiSpaceItem[];
  nextCursor: string | null;
  hasNext: boolean;
};

type PolicySource = "KSTARTUP" | "BIZINFO";
type Verdict3 = "MET" | "NOT_MET" | "UNKNOWN";
type ApiCriterion = {
  id: string;
  kind: string;
  result: Verdict3;
  summary: string | null;
  /** 근거 원문 문장 */
  quote: string | null;
  /** 확인 필요일 때 넣으면 정해지는 입력 칸 (주거·혜택 판정의 needs와 같은 뜻) */
  needs?: string[];
  /** "다음 중 하나"(ANY_OF)일 때 길마다의 결과 */
  options?: { label: string; result: Verdict3; criteria: ApiCriterion[] }[];
};

/** POST /api/v1/spaces/{id}/evaluate (백엔드 SpaceEvaluationResponse) */
type ApiSpaceEvaluation = {
  id: string;
  policy: boolean;
  source: PolicySource | null;
  title: string;
  detailUrl: string | null;
  applyStart: string | null;
  applyEnd: string | null;
  dday: number | null;
  status: ApiSpaceItem["status"];
  regionCodes: string[] | null;
  /** 모집 정책 · 사업의 출처 안내. 공고 · 없으면 null */
  info: ApiPolicyInfo | null;
  /** 판정 틀이 아직 없으면 null */
  judgment: {
    result: Overall;
    common: ApiCriterion[];
    groups: { id: string; name: string; result: Overall; criteria: ApiCriterion[] }[];
  } | null;
};

type ApiSubField = "FUND" | "LOAN" | "TAX";

/** POST /api/v1/supports/search 한 줄 (백엔드 SupportSearchResponse.Item) */
/** 출처 안내 (K-Startup · 기업마당 API 칸을 옮긴 것, AI 값 아님) */
type ApiPolicyInfo = {
  supportArea: string | null;
  summary: string | null;
  organization: string | null;
  contact: string | null;
  applyMethod: string | null;
  applyUrl: string | null;
  guideUrl: string | null;
  amountText: string | null;
  /** 마감일 대신 쓰는 신청 기간 안내 (「예산 소진 시까지」). 없으면 null */
  applyNote?: string | null;
};

type ApiSupportItem = {
  id: string;
  source: PolicySource | null;
  /** 출처 지원 분야(없으면 이름)로 정한 지원 종류 */
  subField: ApiSubField;
  supportArea: string | null;
  organization: string | null;
  /** 요약 글의 「최대 · 한도 N원」 구절 */
  amountText: string | null;
  title: string;
  regionCodes: string[] | null;
  status: ApiSpaceItem["status"];
  applyStart: string | null;
  applyEnd: string | null;
  dday: number | null;
  overall: Overall;
  reason: string | null;
  groups: string[];
  missingInputs: { field: string; label: string }[];
  detailUrl: string | null;
  /** 마감일 대신 쓰는 신청 기간 안내 (「예산 소진 시까지」). 없으면 null */
  applyNote?: string | null;
};

export type ApiSupportSearch = {
  counts: { eligible: number; needsInput: number; ineligible: number };
  subFieldCounts: Record<ApiSubField, number>;
  items: ApiSupportItem[];
  nextCursor: string | null;
  hasNext: boolean;
};

/** POST /api/v1/supports/{id}/evaluate (백엔드 SupportEvaluationResponse). 판정 응답 모양은 사업공간과 같아요 */
type ApiSupportEvaluation = Omit<ApiSpaceEvaluation, "policy"> & { subField: ApiSubField };

/** 판정 입력 (판정 엔진 모양): 생년월일 · 사는 곳 + 사업 정보. 나이를 정확히 판정하도록 생년월일을 보내요 (서버는 저장하지 않아요) */
type SpaceApplicant = {
  /** 생년월일 "1997-03-15" */
  birthDate?: string;
  residenceRegionCode?: string;
  business?: BusinessApplicant;
  /** 신청 제한 사유 코드. 해당 없음이면 빈 목록, 안 골랐으면 보내지 않아요 */
  restrictions?: string[];
  /** 해당 유형 코드. 해당 없음이면 빈 목록, 안 골랐으면 보내지 않아요 */
  statuses?: string[];
};

const typeOf: Record<ApiSpaceType, SpaceType> = {
  STARTUP_SPACE: "startup",
  SHOP_RENTAL: "shop",
  MEETING_ROOM: "room",
};

const verdictOf: Record<Overall, ListingVerdict> = {
  ELIGIBLE: "ok",
  NEEDS_INPUT: "check",
  INELIGIBLE: "no",
};

const statusLabel: Record<ApiSpaceItem["status"], string> = {
  UPCOMING: "접수 예정",
  APPLYING: "접수 중",
  ALWAYS: "상시 모집",
};

const sourceLabel: Record<PolicySource, string> = { KSTARTUP: "K-Startup", BIZINFO: "기업마당" };

/** 지역 법정동코드(10자리) → "서울 종로구" · 시도 전체면 "서울". 여러 곳이면 "서울 종로구 외 1곳" */
function regionLabelOf(codes: string[] | null) {
  if (!codes?.length) return codes ? "전국" : null;
  const code = codes[0].slice(2, 5) === "000" ? codes[0].slice(0, 2) : codes[0].slice(0, 5);
  const label = snapshotRegions.label(code);
  return codes.length > 1 ? `${label} 외 ${codes.length - 1}곳` : label;
}

/** 판정 조건 종류 → 화면 이름 */
const criterionLabel: Record<string, string> = {
  AGE: "대표자 나이",
  APPLICANT_TYPE: "신청 자격 (개인 · 법인)",
  BUSINESS_AGE: "업력",
  BUSINESS_CAREER: "업력",
  BUSINESS_REGISTRATION: "사업자 등록",
  CLOSURE: "폐업 이력",
  EXCLUDED_STATUS: "신청 제한",
  INDUSTRY: "업종",
  NATIONALITY: "국적",
  REGION: "지역",
  REVENUE: "매출",
  STATUS: "대상",
  ASK: "확인할 것",
};

/** 이 날 안에 마감하면 "마감 임박" */
const CLOSING_SOON_DAYS = 7;
/** 사업공간은 많지 않아서 한 번에 받아요 */
const PAGE_SIZE = 100;

function dueOf(it: Pick<ApiSpaceItem, "dday" | "status">, applyNote?: string | null) {
  if (it.dday === 0) return "오늘 마감";
  if (it.dday !== null) return `D-${it.dday}`;
  if (applyNote) return "예산 소진 시";
  return it.status === "ALWAYS" ? "상시" : "마감일 확인";
}

/** 신청 상태 글: 마감일 대신 「예산 소진 시까지」가 있으면 「상시 모집」 대신 그 글 */
function statusText(status: ApiSpaceItem["status"], applyNote?: string | null) {
  return status === "ALWAYS" && applyNote ? applyNote : statusLabel[status];
}

/** 응답 한 줄 → 공간 카드. 모집 정책은 출처(K-Startup · 기업마당)와 지역을 보여줘요 */
export function toSpaceItem(it: ApiSpaceItem): SpaceItem {
  return {
    id: it.id,
    type: typeOf[it.spaceType],
    verdict: it.overall === "ELIGIBLE" ? "ok" : "check",
    org: it.policy
      ? [
          it.organization ?? (it.source ? sourceLabel[it.source] : "입주기업 모집"),
          regionLabelOf(it.regionCodes),
        ]
          .filter(Boolean)
          .join(" · ")
      : [providerName(it.provider), it.regionName].filter(Boolean).join(" · "),
    title: it.title,
    info:
      it.reason === "CONDITIONS_NOT_READY"
        ? `${statusText(it.status, it.applyNote)} · 자격 조건 정리 중`
        : [statusText(it.status, it.applyNote), formatPeriod(it.applyStart, it.applyEnd)]
            .filter(Boolean)
            .join(" · "),
    tags: it.tags.map((t) => tagLabel[t]).filter(Boolean),
    money: it.policy ? "입주 조건은 원문에서 확인" : "",
    due: dueOf(it, it.applyNote),
  };
}

function applicantOf(
  device: DeviceConditions | null,
  profile: BizProfileInput | null,
  session: BizSession,
): SpaceApplicant {
  return {
    birthDate: device ? birthDateOf(device.birth) : undefined,
    residenceRegionCode: judgeRegionCode(device?.regionCode),
    business: profile ? toBusinessApplicant(profile, session.revenue) : undefined,
    restrictions: session.restrictions ?? undefined,
    statuses: profile?.statuses ?? undefined,
  };
}

/**
 * 목록 지역: 사업 정보의 희망 지역(예비 창업) · 사업장 소재지(사업 중). nationwide면 전국.
 * 전국 공고 · 지역을 모르는 공고는 서버가 늘 넣어줘요
 */
export function useRegionScope() {
  const biz = useBizProfileInput();
  const [nationwide, setNationwide] = useState(false);
  const code = biz.status === "ready" ? (biz.profile?.regionCode ?? "") : "";
  return {
    label: code ? snapshotRegions.label(code) : null,
    nationwide: !code || nationwide,
    setNationwide,
    regionCodes: code && !nationwide ? [code] : undefined,
  };
}

export type RegionScope = ReturnType<typeof useRegionScope>;

export function useSpaceApplicant(): { ready: boolean; applicant: SpaceApplicant } {
  const stored = useConditions();
  const biz = useBizProfileInput();
  return useMemo(
    () =>
      stored.status === "ready" && biz.status === "ready"
        ? {
            ready: true,
            applicant: applicantOf(stored.device, biz.profile, biz.session),
          }
        : { ready: false, applicant: {} },
    [stored, biz],
  );
}

/** 사업 정보 입력 화면의 "지금 조건으로": 고치는 중인 값으로 공간 · 지원 개수를 바로 세요 */
export function useApiBusinessPreview(draft: BizProfileInput, session: BizSession) {
  const stored = useConditions();
  // 저장값을 읽은 뒤(브라우저)에만 만들어요. 판정 입력이 오늘 날짜(업력)를 써서 빌드 때 미리 그리면 안 돼요
  const applicant = useMemo(
    () => (stored.status === "ready" ? applicantOf(stored.device, draft, session) : {}),
    [stored, draft, session],
  );
  const regionCodes = draft.regionCode ? [draft.regionCode] : undefined;
  const body = { filters: { regionCodes }, applicant, size: 1 };
  const spaces = useQuery({
    queryKey: ["spaces", "preview", applicant, regionCodes] as const,
    queryFn: () => api.post<ApiSpaceSearch>(endpoints.spacesSearch, body),
    enabled: stored.status === "ready",
    staleTime: 60 * 1000,
    placeholderData: keepPreviousData,
  });
  const supports = useQuery({
    queryKey: ["supports", "preview", applicant, regionCodes] as const,
    queryFn: () => api.post<ApiSupportSearch>(endpoints.supportsSearch, body),
    enabled: stored.status === "ready",
    staleTime: 60 * 1000,
    placeholderData: keepPreviousData,
  });
  return {
    spaces: spaces.data?.counts.eligible ?? 0,
    support: supports.data?.counts.eligible ?? 0,
    check: (spaces.data?.counts.needsInput ?? 0) + (supports.data?.counts.needsInput ?? 0),
  };
}

/**
 * 사업공간 홈: 공간 맞춤 목록으로 공간 카드와 개수를, 사업 지원 맞춤 목록으로 지원 개수를 채워요.
 * 불러오는 동안은 빈 목록이에요
 */
export function useApiBusinessSummary(scope?: RegionScope) {
  const { ready, applicant } = useSpaceApplicant();
  const supports = useApiSupportSearch(scope);
  const regionCodes = scope?.regionCodes;
  const q = useQuery({
    queryKey: ["spaces", "search", applicant, regionCodes] as const,
    queryFn: () =>
      api.post<ApiSpaceSearch>(endpoints.spacesSearch, {
        filters: { regionCodes },
        applicant,
        size: PAGE_SIZE,
      }),
    enabled: ready,
    staleTime: 60 * 1000,
  });
  const data: BusinessSummary = useMemo(() => {
    const items = q.data?.items ?? [];
    return {
      spaces: {
        count: q.data?.counts.eligible ?? 0,
        closingSoon: items.filter((i) => i.dday !== null && i.dday <= CLOSING_SOON_DAYS).length,
      },
      support: supports.data
        ? {
            count: supports.data.counts.eligible,
            needCheck: supports.data.counts.needsInput,
          }
        : { count: 0, needCheck: 0 },
      list: items.map(toSpaceItem),
    };
  }, [q.data, supports.data]);
  return { data, loading: q.isPending, error: q.isError };
}

function useApiSupportSearch(scope?: RegionScope) {
  const { ready, applicant } = useSpaceApplicant();
  const regionCodes = scope?.regionCodes;
  return useQuery({
    queryKey: ["supports", "search", applicant, regionCodes] as const,
    queryFn: () =>
      api.post<ApiSupportSearch>(endpoints.supportsSearch, {
        filters: { regionCodes },
        applicant,
        size: PAGE_SIZE,
      }),
    enabled: ready,
    staleTime: 60 * 1000,
  });
}

const subFieldOf: Record<ApiSubField, SupportType> = { FUND: "fund", LOAN: "loan", TAX: "tax" };

/** 판정 이유 한 줄: 지원 가능이면 충족한 대상, 확인 필요면 넣을 입력 */
function supportReason(it: ApiSupportItem) {
  if (it.reason === "CONDITIONS_NOT_READY") return "자격 조건 정리 중";
  if (it.overall === "ELIGIBLE")
    return it.groups.length ? `${it.groups.join(" · ")} 충족` : "조건 충족";
  const inputs = it.missingInputs.map((m) => m.label).slice(0, 2);
  return inputs.length
    ? `${inputs.join(" · ")}를 넣으면 판정돼요`
    : "원문에서 조건을 확인해 주세요";
}

/** 응답 한 줄 → 사업 지원 줄. 금액은 출처 요약 글에 「최대 N원」이 있을 때만, 없으면 원문에서 */
export function toSupportItem(it: ApiSupportItem): SupportItem {
  const org = [
    it.organization ?? (it.source ? sourceLabel[it.source] : null),
    regionLabelOf(it.regionCodes),
  ]
    .filter(Boolean)
    .join(" · ");
  const period = formatPeriod(it.applyStart, it.applyEnd);
  const reason = supportReason(it);
  return {
    id: it.id,
    type: subFieldOf[it.subField],
    status: it.overall === "ELIGIBLE" ? "ok" : "check",
    title: it.title,
    org,
    mOrg: org,
    body:
      [it.supportArea, it.amountText].filter(Boolean).join(" · ") || "지원 내용은 원문에서 확인",
    note: period
      ? `${statusText(it.status, it.applyNote)} · ${period}`
      : statusText(it.status, it.applyNote),
    mBody:
      [it.supportArea, it.amountText ?? period].filter(Boolean).join(" · ") ||
      statusText(it.status, it.applyNote),
    reason,
    mReason: reason,
    summary: [org, period].filter(Boolean).join(" · "),
    due: dueOf(it, it.applyNote),
    href: `${routes.bizSupport}/${encodeURIComponent(it.id)}`,
  };
}

/** 사업 지원 목록 (불러오는 동안은 빈 목록) */
export function useApiSupportList(scope?: RegionScope) {
  const q = useApiSupportSearch(scope);
  const data: SupportList = useMemo(() => {
    const items = q.data?.items ?? [];
    return {
      count: q.data?.counts.eligible ?? 0,
      // 받은 뒤(브라우저)에만 오늘 날짜를 써요 (빌드 때 미리 그리는 화면에는 날짜를 넣지 않아요)
      baseDate: q.data
        ? new Intl.DateTimeFormat("ko-KR", {
            month: "long",
            day: "numeric",
            timeZone: "Asia/Seoul",
          }).format(new Date())
        : "",
      items: items.map(toSupportItem),
      missingSiteCount: items.filter((i) =>
        i.missingInputs.some((m) => m.field.includes("siteRegionCode")),
      ).length,
    };
  }, [q.data]);
  return { data, loading: q.isPending, error: q.isError };
}

/** 사업 지원 상세: 상세 API가 없어서 판정 응답(기간 · 지역 · 자격 조건)과 원문으로 */
export function useApiSupportDetail(id: string) {
  const { ready, applicant } = useSpaceApplicant();
  const q = useQuery({
    queryKey: ["supports", "evaluate", id, applicant] as const,
    queryFn: () => api.post<ApiSupportEvaluation>(endpoints.supportEvaluate(id), { applicant }),
    placeholderData: keepPreviousData,
    enabled: ready,
    staleTime: 60 * 1000,
    retry: false,
  });
  const data = useMemo(
    () =>
      q.data &&
      policyDetail(q.data, {
        kind: supportKindLabel[q.data.subField],
        note: "지원 금액 · 신청 방법 · 제출 서류는 원문에서 확인해 주세요",
      }),
    [q.data],
  );
  return { data, loading: !q.isError && q.isPending, error: q.isError };
}

const supportKindLabel: Record<ApiSubField, string> = {
  FUND: "창업 지원금",
  LOAN: "정책자금",
  TAX: "세금 감면",
};

/** 판정 설명 안의 법정동코드(10자리)를 지역 이름으로 ("4400000000 지역 안" → "충남 지역 안") */
const withRegionNames = (text: string) =>
  text.replace(/\b\d{10}\b/g, (code) => regionLabelOf([code]) ?? code);

/** 판정 조건 → 내 자격 줄. 근거 문장이 있으면 같이 */
function rulesOf(j: ApiSpaceEvaluation["judgment"]): SpaceDetail["rules"] {
  const criteria = j ? [...j.common, ...j.groups.flatMap((g) => g.criteria)] : [];
  const toRule = (c: ApiCriterion): SpaceRule => {
    const anyOf = c.kind === "ANY_OF" && c.options?.length;
    return {
      label: anyOf ? "다음 중 하나만 맞으면 돼요" : (criterionLabel[c.kind] ?? "조건"),
      rule: anyOf ? "" : withRegionNames(c.summary ?? c.quote ?? ""),
      mRule: anyOf ? "" : withRegionNames(c.summary ?? c.quote ?? ""),
      quote: c.summary && c.quote ? c.quote : undefined,
      met: c.result === "MET",
      notMet: c.result === "NOT_MET",
      inputHref: c.result === "UNKNOWN" ? inputHrefOf(c.needs) : undefined,
      // 길 안 조건도 같은 표시예요 (확인 필요면 넣을 입력이 있을 때만 입력 화면으로, 없으면 원문 확인)
      options: anyOf
        ? c.options!.map((o, i) => ({
            label: o.label.replace(/^\d+번째 길:\s*/, "") || `${i + 1}번째`,
            met: o.result === "MET",
            notMet: o.result === "NOT_MET",
            rules: o.criteria.filter((x) => x.kind !== "RULE").map(toRule),
          }))
        : undefined,
    };
  };
  return criteria.filter((c) => c.kind !== "RULE" && (c.summary || c.quote)).map(toRule);
}

/** 모집 정책·사업 지원 상세: 공고 상세가 없어서 판정 응답(기간 · 지역 · 자격 조건)과 원문으로 */
function policyDetail(
  e: Omit<ApiSpaceEvaluation, "policy">,
  text = {
    kind: "입주기업 모집",
    note: "입주 공간 · 기간 · 비용 · 준비 서류는 원문에서 확인해 주세요",
  },
): SpaceDetail {
  const period = formatPeriod(e.applyStart, e.applyEnd);
  const region = regionLabelOf(e.regionCodes);
  const source = e.source ? sourceLabel[e.source] : "원문";
  return {
    id: e.id,
    favoriteType: "SPACE_RECRUITMENT",
    verdict: e.judgment ? verdictOf[e.judgment.result] : "check",
    due: dueOf(e, e.info?.applyNote),
    tag: statusText(e.status, e.info?.applyNote),
    title: e.title,
    kind: text.kind,
    host: e.source ? sourceLabel[e.source] : "",
    area: region ?? "",
    facts: [
      {
        label: "접수 기간",
        value: period ?? e.info?.applyNote ?? "원문 확인",
        mValue: period ?? e.info?.applyNote ?? "원문 확인",
      },
      { label: "지역", value: region ?? "원문 확인", mValue: region ?? "원문 확인" },
      { label: "출처", value: source, mValue: source },
      ...(e.info?.supportArea
        ? [{ label: "지원 분야", value: e.info.supportArea, mValue: e.info.supportArea }]
        : []),
      ...(e.info?.amountText
        ? [{ label: "지원 금액", value: e.info.amountText, mValue: e.info.amountText }]
        : []),
    ],
    conditions: [],
    docs: [],
    currentStep: 0,
    schedule: [],
    rules: rulesOf(e.judgment),
    sourceUrl: e.detailUrl ?? undefined,
    notReady: !e.judgment,
    summaryNote: text.note,
    about: aboutOf(e.info),
  };
}

/** 출처 안내 → 상세 "공고 안내" (요약 · 기관 · 문의처 · 접수 방법 · 링크). 칸이 하나도 없으면 없음 */
function aboutOf(info: ApiPolicyInfo | null): SpaceDetail["about"] {
  if (!info) return undefined;
  const rows = [
    info.organization && { label: "운영 기관", value: info.organization },
    info.contact && { label: "문의처", value: info.contact },
    info.applyMethod && { label: "접수 방법", value: info.applyMethod },
    info.applyUrl && { label: "신청 주소", value: "신청하러 가기", href: info.applyUrl },
    info.guideUrl && { label: "사업 안내", value: "안내 페이지 열기", href: info.guideUrl },
  ].filter((r): r is { label: string; value: string; href?: string } => Boolean(r));
  return info.summary || rows.length ? { summary: info.summary ?? undefined, rows } : undefined;
}

/** 공간 상세: 판정을 먼저 받고, 공고면 공고 상세를 더 받아요 (모집 정책은 공고 상세가 없어요) */
export function useApiSpaceDetail(id: string) {
  const { ready, applicant } = useSpaceApplicant();
  const evaluation = useQuery({
    queryKey: ["spaces", "evaluate", id, applicant] as const,
    queryFn: () => api.post<ApiSpaceEvaluation>(endpoints.spaceEvaluate(id), { applicant }),
    placeholderData: keepPreviousData,
    enabled: ready,
    staleTime: 60 * 1000,
    retry: false,
  });
  const notice = useNotice(id, evaluation.data?.policy === false);
  const n = notice.data?.kind === "standard" ? notice.data : undefined;
  const data: SpaceDetail | undefined = useMemo(() => {
    const e = evaluation.data;
    if (e?.policy) return policyDetail(e);
    if (!n) return undefined;
    const j = e?.judgment ?? null;
    const schedule = n.doc.schedule.map((s, i) => ({
      step: i + 1,
      title: s.label,
      when: formatPeriod(s.start, s.end) ?? "날짜 미정",
      now: s.state === "now",
    }));
    return {
      id: n.id,
      favoriteType: "NOTICE",
      verdict: j ? verdictOf[j.result] : "check",
      due: n.dueLabel ?? "",
      tag: n.tags[0] ?? "",
      title: n.title,
      kind: n.meta,
      host: "",
      area: "",
      facts: n.facts.map((f) => ({ label: f.label, value: f.value, mValue: f.value })),
      conditions: [],
      docs: n.doc.apply.documents.flatMap((g) =>
        g.items.map((d) => ({
          name: d.name,
          note: [d.when, d.desc].filter(Boolean).join(" · "),
          mNote: d.when ?? d.desc,
          ready: false,
        })),
      ),
      currentStep: schedule.find((s) => s.now)?.step ?? 0,
      schedule,
      rules: rulesOf(j),
      sourceUrl: n.doc.source.detailUrl || undefined,
      notReady: Boolean(e) && !j,
    };
  }, [n, evaluation.data]);
  const loading =
    !evaluation.isError && (evaluation.isPending || (!evaluation.data?.policy && notice.loading));
  return { data, loading, error: evaluation.isError || notice.error };
}
