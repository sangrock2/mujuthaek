// 공고 원문 정리(NoticeDoc) 값을 화면 문구로 바꿔요
import type {
  EligibilityCategory,
  NoticeDoc,
  NoticeDocumentGroup,
  NoticeSectionKey,
  NoticeSelectionKind,
} from "@/features/notice/mocks/notice-doc";

import { formatWon } from "@/shared/lib/money";
export { formatWon } from "@/shared/lib/money";

/** 원문에 금액이 없으면 "원문 확인" */
export const formatWonOr = (won: number | null) => (won === null ? "원문 확인" : formatWon(won));

/** 호마다 다르면 범위: "15만 4,990원 ~ 16만 7,670원" */
export const formatWonRange = (won: number | null, max?: number) =>
  won === null || max === undefined ? formatWonOr(won) : `${formatWon(won)} ~ ${formatWon(max)}`;

/** 공고 상세 맨 위 마감 표시 */
export const dueText = (n: { dday: number; dueLabel?: string }) => n.dueLabel ?? `마감 D-${n.dday}`;

const weekdays = ["일", "월", "화", "수", "목", "금", "토"];

/**
 * "2026-10-12" → "10월 12일 (월)" · 해가 다르면 연도도 붙여요.
 * 공고에 월이나 해만 적힌 날짜도 와요: "2027-03" → "3월", "2027" → "2027년" (일·요일은 지어내지 않아요)
 */
export function formatDay(ymd: string, withYear = false): string {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!m) return `${y}년`;
  const year = withYear ? `${y}년 ` : "";
  if (!d) return `${year}${m}월`;
  const wd = weekdays[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${year}${m}월 ${d}일 (${wd})`;
}

/** 올해 (한국 날짜) */
const thisYear = (now: Date) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(now).slice(0, 4);

/**
 * 시작 ~ 끝. 하루면 하나만. 올해가 아닌 날짜는 연도를 붙이고(예전엔 다음 해 「2월 24일」에 연도가 없어 올해로 읽혔어요), 해가 바뀌면
 * 끝에도 붙여요: "12월 14일 (월) ~ 2027년 1월 14일 (목)" · "2027년 2월 24일 (수)" · "2027년 1월 4일 (월) ~ 1월 8일 (금)"
 */
export function formatPeriod(
  start: string | null,
  end: string | null,
  now = new Date(),
): string | null {
  if (!start && !end) return null;
  const year = thisYear(now);
  if (!start || !end || start === end) {
    const day = (start ?? end)!;
    return formatDay(day, day.slice(0, 4) !== year);
  }
  const startYear = start.slice(0, 4);
  const endYear = end.slice(0, 4);
  const startWithYear = startYear !== year;
  return `${formatDay(start, startWithYear)} ~ ${formatDay(end, endYear !== startYear)}`;
}

export const sectionTitles: Record<NoticeSectionKey, { toc: string; heading: string }> = {
  eligibility: { toc: "신청 자격", heading: "누가 신청할 수 있나요" },
  housing: { toc: "주택·임대조건", heading: "주택과 임대조건" },
  schedule: { toc: "일정", heading: "일정" },
  followUps: { toc: "후속 안내", heading: "후속 안내" },
  apply: { toc: "신청 방법·서류", heading: "신청 방법과 서류" },
  selection: { toc: "선정 방식", heading: "어떻게 뽑나요" },
  cautions: { toc: "꼭 확인하세요", heading: "꼭 확인하세요" },
  living: { toc: "입주·거주", heading: "입주와 거주" },
  contacts: { toc: "문의처", heading: "문의처" },
};

/** 내용이 있는 섹션만 목차 순서대로 */
export function visibleSections(doc: NoticeDoc): NoticeSectionKey[] {
  const has: Record<NoticeSectionKey, boolean> = {
    eligibility: doc.eligibility.length > 0,
    housing: doc.housing.length > 0,
    schedule: doc.schedule.length > 0,
    followUps: (doc.followUps?.length ?? 0) > 0,
    apply: Boolean(doc.apply.method) || doc.apply.documents.length > 0,
    selection: doc.selection.length > 0,
    cautions: doc.cautions.length > 0,
    living: doc.living.length > 0,
    contacts: doc.contacts.length > 0,
  };
  return (
    [
      "eligibility",
      "cautions",
      ...Object.keys(sectionTitles).filter((k) => k !== "eligibility" && k !== "cautions"),
    ] as NoticeSectionKey[]
  ).filter((k) => has[k]);
}

export const categoryLabel: Record<EligibilityCategory, string> = {
  AGE: "나이",
  HOME_OWNERSHIP: "무주택",
  INCOME: "소득",
  ASSETS: "자산",
  CAR_ASSETS: "자동차",
  RESIDENCE: "사는 곳",
  HOUSEHOLD: "세대",
  NATIONALITY: "국적",
  OTHER: "기타",
};

export const selectionLabel: Record<NoticeSelectionKind, string> = {
  FIRST_COME: "선착순",
  LOTTERY: "추첨",
  PRIORITY: "순위",
  SCORE: "배점",
  TIE_BREAK: "순번 놓치면",
  OTHER: "안내",
};

export const documentGroupLabel: Record<NoticeDocumentGroup, string> = {
  COMMON: "모두 내요",
  CONDITIONAL: "해당하면 더 내요",
  DIRECT: "본인이 방문해서 신청할 때",
  PROXY_SPOUSE: "배우자가 대신 신청할 때",
  PROXY_OTHER: "다른 사람이 대신 신청할 때",
};

export const channelLabel: Record<NonNullable<NoticeDoc["apply"]["channel"]>, string> = {
  ONLINE: "온라인 신청",
  ONSITE: "현장 방문",
  EMAIL: "이메일 접수",
  MAIL: "우편 접수",
  FAX: "팩스 접수",
};

export const statusLabel: Record<NoticeDoc["status"], string> = {
  UPCOMING: "접수 예정",
  OPEN: "접수 중",
  CLOSED: "마감",
};

/** 원문 뷰어 위 섹션 목차: 원문 쪽이 있는 섹션만 쪽 순서로 */
export function pdfSections(doc: NoticeDoc): { label: string; page: number }[] {
  return visibleSections(doc)
    .filter((k) => doc.pages[k])
    .map((k) => ({ label: sectionTitles[k].toc, page: doc.pages[k]! }))
    .sort((a, b) => a.page - b.page);
}
