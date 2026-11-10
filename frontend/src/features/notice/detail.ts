// GET /api/v1/notices/{id} 응답 (백엔드 NoticeDetailResponse) → 공고 상세 화면 값
import { dueText } from "@/features/notice/format";
import {
  noticeTypeLabel,
  providerName,
  tagLabel,
  targetGroupLabel,
} from "@/features/notice/labels";
import type { NoticeFact, StandardNotice } from "@/mocks/notice";
import type {
  EligibilityCategory,
  NoticeDoc,
  NoticeHousingType,
  NoticeDocumentGroup,
  NoticeFollowUp,
  NoticeHeldPart,
  NoticeScheduleItem,
  NoticeSelectionKind,
  NoticeTextItem,
} from "@/mocks/notice-doc";

type Evidence = { quote: string; page: number | null };
type TimeRange = { start: string; end: string };

type ApiSchedule = {
  id: string;
  label: string;
  kinds: string[];
  startsAt: string | null;
  endsAt: string | null;
  description: string | null;
  applicationUrl: string | null;
  channels: string[];
  places: { name: string | null; address: string | null; detail: string | null }[];
  dailyHours: TimeRange[];
  excludedDays: string[];
  timeNote: string | null;
  current: boolean;
  evidence: Evidence[];
};

export type ApiNoticeDetail = {
  header: {
    id: string;
    title: string;
    provider: string | null;
    noticeType: string | null;
    supplyTypeText: string | null;
    status: "UPCOMING" | "APPLYING" | "CLOSED" | "ALWAYS" | "UNKNOWN";
    applyStart: string | null;
    applyEnd: string | null;
    dday: number | null;
    regionName: string | null;
    detailUrl: string | null;
  };
  summary: {
    summaryText: string | null;
    targetGroups: string[];
    supplyTotal: number | null;
    exclusiveM2Min: number | null;
    exclusiveM2Max: number | null;
    applicationChannels: string[];
  };
  schedules: ApiSchedule[];
  sites: {
    id: string;
    name: string | null;
    address: string | null;
    lat: number | null;
    lng: number | null;
    /** area 위치 ID (GET /areas/sites/{siteId}). area가 아직 모르는 위치면 null */
    siteId: string | null;
    tags: string[];
  }[];
  unitTypes: {
    houseType: string;
    /** 이 가격을 내는 대상 (예: 「수급자 등」·「그 외」) */
    targetGroups: string[];
    supplyGroupId: string | null;
    /** 단지·건물 이름 */
    siteName: string | null;
    exclusiveM2: number | null;
    depositWon: number | null;
    rentWon: number | null;
    supplyCount: number | null;
    evidence: Evidence[];
  }[];
  conditions: {
    id: string;
    category: string | null;
    description: string | null;
    originalText: string | null;
    inReview: boolean;
    evidence: Evidence[];
  }[];
  requiredDocuments: {
    id: string;
    name: string;
    group: string | null;
    appliesTo: string | null;
    submissionTime: string | null;
    description: string | null;
    evidence: Evidence[];
  }[];
  /** 선정 방식 (백엔드 #103부터, 그 전 응답엔 없어요) */
  selectionRules?: {
    id: string;
    kind: string | null;
    description: string | null;
    originalText: string | null;
    priorityRank: number | null;
    points: number | null;
  }[];
  /** 안내: 신청 방법 · 주의 · 입주 · 거주 · 문의처 (백엔드 #103부터) */
  guidance?: {
    id: string;
    kind: string | null;
    title: string | null;
    description: string | null;
    phone: string | null;
    url: string | null;
  }[];
  files: { name: string; url: string }[];
  /** 원문 확인 전까지 화면에서 뺀 항목. section은 추출 결과의 섹션 이름(schedules·supplyGroups 등), description은 내부 검사 문구라 화면에 쓰지 않아요 */
  heldItems?: { section: string | null; target: string | null; description: string | null }[];
  areaSummaries: { siteId: string; kind: "LIVING" | "COMMERCIAL"; score: number }[];
  /** 원래 공고에 붙은 후속 안내 (당첨자 발표·서류 제출, 일정만 바꾼 짧은 정정 등). 공고 버전과 따로 붙어요 */
  followUps?: {
    title: string;
    detailUrl: string | null;
    postedOn: string | null;
    schedules: ApiSchedule[];
  }[];
  hasUnits: boolean;
};

const categoryOf: Record<string, EligibilityCategory> = {
  AGE: "AGE",
  HOME_OWNERSHIP: "HOME_OWNERSHIP",
  HOMELESS: "HOME_OWNERSHIP",
  INCOME: "INCOME",
  ASSET: "ASSETS",
  ASSETS: "ASSETS",
  CAR: "CAR_ASSETS",
  CAR_ASSETS: "CAR_ASSETS",
  CAR_VALUE: "CAR_ASSETS",
  RESIDENCE: "RESIDENCE",
  HOUSEHOLD: "HOUSEHOLD",
  NATIONALITY: "NATIONALITY",
};

const channelOf: Record<string, NonNullable<NoticeDoc["apply"]["channel"]>> = {
  ONLINE: "ONLINE",
  ONSITE: "ONSITE",
  EMAIL: "EMAIL",
  MAIL: "MAIL",
  FAX: "FAX",
};

const channelText: Record<string, string> = {
  ONLINE: "온라인",
  ONSITE: "방문",
  EMAIL: "이메일",
  MAIL: "우편",
  FAX: "팩스",
};

const groupOf: Record<string, NoticeDocumentGroup> = {
  COMMON: "COMMON",
  CONDITIONAL: "CONDITIONAL",
  DIRECT: "DIRECT",
  PROXY_SPOUSE: "PROXY_SPOUSE",
  PROXY_OTHER: "PROXY_OTHER",
};

const selectionKindOf: Record<string, NoticeSelectionKind> = {
  PRIORITY: "PRIORITY",
  SCORING: "SCORE",
  TIE_BREAK: "TIE_BREAK",
  LOTTERY: "LOTTERY",
  FIRST_COME: "FIRST_COME",
};

const dayText: Record<string, string> = {
  MON: "월",
  TUE: "화",
  WED: "수",
  THU: "목",
  FRI: "금",
  SAT: "토",
  SUN: "일",
  HOLIDAY: "공휴일",
};

/** "2026-10-01T10:00" · "2026-10-01" → "2026-10-01" */
const dayOf = (v: string | null) => (v ? v.slice(0, 10) : null);

/** 근거 원문 중 가장 앞 쪽 */
const firstPage = (items: { evidence: Evidence[] }[]) => {
  const pages = items.flatMap((i) => i.evidence.map((e) => e.page)).filter((p) => p !== null);
  return pages.length ? Math.min(...pages) : undefined;
};

const hoursText = (s: ApiSchedule) => {
  const hours = s.dailyHours.map((h) => `${h.start}~${h.end}`).join(", ");
  const off = s.excludedDays.map((d) => dayText[d] ?? d).join("·");
  return [hours, off && `${off} 제외`].filter(Boolean).join(" · ") || undefined;
};

function scheduleItem(s: ApiSchedule, today: string): NoticeScheduleItem {
  const end = dayOf(s.endsAt) ?? dayOf(s.startsAt);
  return {
    id: s.id,
    label: s.label,
    start: dayOf(s.startsAt),
    end: dayOf(s.endsAt),
    time: hoursText(s),
    note: s.timeNote ?? s.description ?? undefined,
    state: s.current ? "now" : end && end < today ? "done" : "todo",
  };
}

const statusOf: Record<ApiNoticeDetail["header"]["status"], NoticeDoc["status"]> = {
  UPCOMING: "UPCOMING",
  APPLYING: "OPEN",
  ALWAYS: "OPEN",
  CLOSED: "CLOSED",
  UNKNOWN: "UPCOMING",
};

function dueLabelOf(h: ApiNoticeDetail["header"]) {
  if (h.status === "ALWAYS") return "상시 모집";
  if (h.status === "UPCOMING") return "접수 예정";
  if (h.status === "CLOSED") return "마감";
  if (h.dday === null) return "마감일 확인";
  return h.dday <= 0 ? "오늘 마감" : undefined;
}

function factsOf(d: ApiNoticeDetail): NoticeFact[] {
  const { summary: s } = d;
  const groups = s.targetGroups.map((g) => targetGroupLabel[g]).filter(Boolean);
  const min = s.exclusiveM2Min;
  const max = s.exclusiveM2Max;
  const area =
    min === null && max === null
      ? null
      : min === max || max === null
        ? `${min}㎡`
        : min === null
          ? `${max}㎡`
          : `${min} ~ ${max}㎡`;
  const channels = s.applicationChannels.map((c) => channelText[c]).filter(Boolean);
  return [
    groups.length ? { label: "모집 대상", value: groups.join(" · ") } : null,
    s.supplyTotal !== null ? { label: "공급 호수", value: `${s.supplyTotal}호` } : null,
    area ? { label: "전용면적", value: area } : null,
    channels.length ? { label: "신청 방법", value: channels.join(" · ") } : null,
  ].filter((f): f is NoticeFact => f !== null);
}

type ApiUnitType = ApiNoticeDetail["unitTypes"][number];

const range = (values: (number | null)[]) => {
  const known = values.filter((v): v is number => v !== null);
  if (known.length < values.length || !known.length) return { min: null, max: undefined };
  const min = Math.min(...known);
  const max = Math.max(...known);
  return { min, max: max === min ? undefined : max };
};

/**
 * 주택 표 한 단지의 줄. 주택목록(호별) 공고는 같은 주택형·면적·가격 대상의 호를 한 줄로 모아 호수를 세고 가격은 범위로 보여줘요
 * (68호 × 가격 대상 2 = 136줄이 되던 문제)
 */
function housingTypes(rows: ApiUnitType[], byUnit: boolean): NoticeHousingType[] {
  const target = (u: ApiUnitType) => u.targetGroups.join("·") || undefined;
  if (!byUnit) {
    return rows.map((u) => ({
      code: u.houseType,
      areaSqm: u.exclusiveM2,
      offered: u.supplyCount,
      depositWon: u.depositWon,
      monthlyRentWon: u.rentWon,
      target: target(u),
    }));
  }
  // 호 하나의 수는 첫 가격 대상 줄에만 있어요
  const countOf = new Map<string, number>();
  for (const u of rows) {
    if (u.supplyGroupId && u.supplyCount !== null) countOf.set(u.supplyGroupId, u.supplyCount);
  }
  const groups = new Map<string, ApiUnitType[]>();
  for (const u of rows) {
    const key = [u.houseType, u.exclusiveM2, target(u)].join("|");
    groups.set(key, [...(groups.get(key) ?? []), u]);
  }
  return [...groups.values()].map((same) => {
    const ids = [...new Set(same.map((u) => u.supplyGroupId).filter((id): id is string => !!id))];
    const deposit = range(same.map((u) => u.depositWon));
    const rent = range(same.map((u) => u.rentWon));
    return {
      code: same[0].houseType,
      areaSqm: same[0].exclusiveM2,
      offered: ids.length ? ids.reduce((sum, id) => sum + (countOf.get(id) ?? 0), 0) : null,
      depositWon: deposit.min,
      depositMaxWon: deposit.max,
      monthlyRentWon: rent.min,
      monthlyRentMaxWon: rent.max,
      target: target(same[0]),
    };
  });
}

/** 주택 표: 단지 이름이 있으면 단지별로 나눠요 */
function housingOf(d: ApiNoticeDetail, sites: ApiNoticeDetail["sites"]): NoticeDoc["housing"] {
  if (!d.unitTypes.length) return [];
  const h = d.header;
  const bySite = new Map<string | null, ApiUnitType[]>();
  for (const u of d.unitTypes) bySite.set(u.siteName, [...(bySite.get(u.siteName) ?? []), u]);
  if (bySite.size === 1 && bySite.has(null)) {
    return [
      {
        id: "unit-types",
        complexName: sites.map((s) => s.name ?? s.address).join(" · ") || h.title,
        address: sites[0]?.address ?? h.regionName ?? "",
        types: housingTypes(d.unitTypes, d.hasUnits),
      },
    ];
  }
  return [...bySite.entries()].map(([name, rows], i) => ({
    id: `unit-types-${i}`,
    complexName: name ?? "그 밖의 주택",
    address: sites.find((s) => s.name === name)?.address ?? h.regionName ?? "",
    types: housingTypes(rows, d.hasUnits),
  }));
}

/**
 * 일정 목록 → 화면 값, 날짜순. 시작일이 없으면 끝 날짜로 견주고(공고일·마감처럼 하루만 적힌 일정이 맨 뒤로 가던 것), 날짜가 아예 없으면 뒤로.
 * id가 비어 오면 순서로 채워요(목록 key가 겹치지 않게)
 */
function schedulesOf(list: ApiSchedule[], today: string, idPrefix: string): NoticeScheduleItem[] {
  const when = (s: NoticeScheduleItem) => s.start ?? s.end ?? "9999";
  return list
    .map((s, i) => ({ ...scheduleItem(s, today), id: s.id || `${idPrefix}-${i}` }))
    .sort((a, b) => when(a).localeCompare(when(b)));
}

/**
 * 보류 섹션(추출 결과 이름) → 화면 섹션과 알림에 쓸 이름. 안내(guidance)는 꼭 확인하세요·입주·문의처·신청 방법으로 나뉘는데
 * 보류한 항목은 응답에서 빠져 어느 쪽인지 알 수 없어 섹션 표시 없이 이름만 알려요
 */
const heldPartOf = new Map<string, NoticeHeldPart>([
  ["notice", { key: null, label: "공고 정보" }],
  ["schedules", { key: "schedule", label: "일정" }],
  ["supplyGroups", { key: "housing", label: "주택·임대조건" }],
  ["locations", { key: "housing", label: "주택 위치" }],
  ["eligibility", { key: "eligibility", label: "신청 자격" }],
  ["selectionRules", { key: "selection", label: "선정 방식" }],
  ["requiredDocuments", { key: "apply", label: "서류" }],
  ["guidance", { key: null, label: "안내·문의처" }],
  ["documents", { key: null, label: "첨부 파일" }],
]);

/**
 * 원문과 다시 확인하는 내용이 있는 곳 (같은 이름은 한 번, 모르는 섹션은 「그 밖의 내용」). 보류(heldItems) 말고도 확인 중으로 온
 * 자격 조건(inReview)이 있으면 신청 자격을 넣어요
 */
function heldParts(d: ApiNoticeDetail): NoticeHeldPart[] {
  const parts = new Map<string, NoticeHeldPart>();
  for (const h of d.heldItems ?? []) {
    const part = heldPartOf.get(h.section ?? "") ?? { key: null, label: "그 밖의 내용" };
    parts.set(part.label, part);
  }
  if (d.conditions.some((c) => c.inReview)) {
    const part = heldPartOf.get("eligibility")!;
    parts.set(part.label, part);
  }
  return [...parts.values()];
}

function followUpsOf(d: ApiNoticeDetail, today: string): NoticeFollowUp[] {
  return (d.followUps ?? []).map((f, i) => ({
    id: `follow-up-${i}`,
    title: f.title,
    postedOn: dayOf(f.postedOn),
    url: f.detailUrl,
    schedule: schedulesOf(f.schedules, today, `follow-up-${i}-schedule`),
  }));
}

function docOf(d: ApiNoticeDetail, today: string): NoticeDoc {
  const { header: h } = d;
  const guidance = d.guidance ?? [];
  const textItems = (kinds: string[]): NoticeTextItem[] =>
    guidance
      .filter((g) => kinds.includes(g.kind ?? "OTHER"))
      .map((g) => ({ id: g.id, title: g.title ?? "", text: g.description ?? "" }));
  const method = guidance
    .filter((g) => g.kind === "APPLICATION_METHOD")
    .map((g) => g.description)
    .filter(Boolean)
    .join(" ");
  const applyUrl = guidance.find((g) => g.kind === "APPLICATION_METHOD" && g.url)?.url;
  const application = d.schedules.find((s) => s.kinds.includes("APPLICATION"));
  const place = application?.places[0];
  const documents = new Map<NoticeDocumentGroup, NoticeDoc["apply"]["documents"][number]>();
  for (const r of d.requiredDocuments) {
    const group = groupOf[r.group ?? ""] ?? "COMMON";
    const g = documents.get(group) ?? { group, items: [] };
    g.items.push({
      id: r.id,
      name: r.name,
      when: [r.appliesTo, r.submissionTime].filter(Boolean).join(" · ") || undefined,
      desc: r.description ?? "",
    });
    documents.set(group, g);
  }
  const start = h.applyStart ?? h.applyEnd;
  const end = h.applyEnd ?? h.applyStart;
  const sites = d.sites.filter((s) => s.name || s.address);

  return {
    status: statusOf[h.status],
    applyPeriod: start && end ? { start, end, note: application && hoursText(application) } : null,
    summary: d.summary.summaryText ?? "",
    source: {
      fileName: d.files[0]?.name ?? "",
      // 원문 PDF는 아직 우리 저장소에 없어서 기관 사이트로 보내요
      pdfUrl: null,
      pageCount: null,
      detailUrl: h.detailUrl ?? d.files[0]?.url ?? "",
    },
    pages: {
      eligibility: firstPage(d.conditions),
      housing: firstPage(d.unitTypes),
      schedule: firstPage(d.schedules),
      apply: firstPage(d.requiredDocuments),
    },
    eligibility: d.conditions.map((c) => ({
      id: c.id,
      category: categoryOf[c.category ?? ""] ?? "OTHER",
      text: c.description ?? c.originalText ?? "",
      // 예외 조건(detail)과 따로: 예전엔 detail에 넣어 「예외 · 원문과 다시 확인하는 중이에요」로 보였어요
      checking: c.inReview || undefined,
    })),
    housing: housingOf(d, sites),
    schedule: schedulesOf(d.schedules, today, "schedule"),
    followUps: followUpsOf(d, today),
    held: heldParts(d),
    apply: {
      // 안내의 신청 방법 문장 (일정 설명은 일정 칸에 있어서 다시 쓰지 않아요)
      method,
      channel: channelOf[application?.channels[0] ?? ""] ?? null,
      url: application?.applicationUrl ?? applyUrl ?? undefined,
      place:
        place && (place.name || place.address)
          ? { name: place.name ?? "", address: place.address ?? "" }
          : undefined,
      hours: application && hoursText(application),
      documents: [...documents.values()],
    },
    selection: (d.selectionRules ?? []).map((r) => {
      const text = r.description ?? r.originalText ?? "";
      // 배점은 문장에 점수가 없을 때만 붙여요
      const points = r.points !== null && !text.includes("점") ? ` (${r.points}점)` : "";
      return { id: r.id, kind: selectionKindOf[r.kind ?? ""] ?? "OTHER", text: text + points };
    }),
    cautions: textItems(["CAUTION"]),
    living: textItems(["MOVE_IN", "LIVING_NOTICE", "OTHER"]),
    contacts: guidance
      .filter((g) => g.kind === "CONTACT")
      .map((g) => ({
        id: g.id,
        name: g.title ?? "문의처",
        phone: g.phone ?? "",
        desc: g.description ?? "",
      })),
  };
}

/** "2026-10-26" (한국 날짜) */
const todayYmd = (now: Date) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(now);

/** 상세 응답 → 화면 값. 판정(배지 · 내 자격 · 준비할 돈)은 판정 응답에서 따로 채워요 */
export function toNotice(d: ApiNoticeDetail, now = new Date()): StandardNotice {
  const { header: h } = d;
  const scoreOf = new Map(
    d.areaSummaries
      .filter((a) => a.kind === "LIVING")
      .map((a) => [a.siteId, Math.round(a.score)] as const),
  );
  const siteName = (s: ApiNoticeDetail["sites"][number]) => s.name ?? s.address ?? "단지";
  const lifeSites = d.sites
    .filter((s) => scoreOf.has(s.id))
    .map((s) => ({
      id: s.id,
      areaId: s.siteId,
      name: siteName(s),
      score: scoreOf.get(s.id)!,
      tags: s.tags.map((t) => tagLabel[t]).filter(Boolean),
    }))
    .sort((a, b) => b.score - a.score);
  const tags = [...new Set(d.sites.flatMap((s) => s.tags))].map((t) => tagLabel[t]).filter(Boolean);
  const agency = providerName(h.provider);
  const notice: StandardNotice = {
    kind: "standard",
    id: h.id,
    verdict: "check",
    dday: Math.max(0, h.dday ?? 0),
    tags,
    title: h.title,
    meta: [
      agency,
      h.supplyTypeText ?? (h.noticeType ? noticeTypeLabel[h.noticeType] : null),
      h.regionName,
    ]
      .filter(Boolean)
      .join(" · "),
    agency: agency ?? "기관",
    facts: factsOf(d),
    eligibility: [],
    doc: docOf(d, todayYmd(now)),
    life: lifeSites.length
      ? { score: lifeSites[0].score, min: lifeSites.at(-1)!.score, sites: lifeSites }
      : undefined,
    sites: d.sites.map((s) => ({
      id: s.id,
      name: siteName(s),
      lat: s.lat,
      lng: s.lng,
      lifeScore: scoreOf.get(s.id),
    })),
    hasUnits: d.hasUnits,
  };
  notice.dueLabel = dueLabelOf(h) ?? dueText(notice);
  return notice;
}
