import type { GeneralReportKind } from "@/features/me/api";

/** 내 정보 탭 (웹 ?tab= · 모바일 /me/{tab}) */
export type MeTab =
  | "conditions"
  | "favorites"
  | "preparations"
  | "interests"
  | "notifications"
  | "privacy"
  | "reports";

export const meTabs: MeTab[] = [
  "conditions",
  "favorites",
  "preparations",
  "interests",
  "notifications",
  "privacy",
  "reports",
];

/**
 * 제보와 함께 보낼 수 있는 「보낸 화면」 이름. 링크(?from=)로는 이 목록의 값만 받아요.
 * 예전에는 아무 글이나 화면에 보이지 않는 칸으로 제보에 실렸어요 (2026-11-16 보안 감사 4장)
 */
export const reportScreens = [
  "자주 묻는 질문",
  "소개 화면",
  "검색",
  "검색 (모바일)",
  "오류 화면",
] as const;
export type ReportScreen = (typeof reportScreens)[number];

/** 오류 코드 모양 (예: E-503). 링크(?code=)로는 이 모양만 받아요 */
const REPORT_CODE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,39}$/;

export const reportScreenParam = (value: string | null): ReportScreen | undefined =>
  reportScreens.find((screen) => screen === value);

export const reportCodeParam = (value: string | null): string | undefined =>
  value && REPORT_CODE.test(value) ? value : undefined;

/** 제보 화면으로 보내는 주소. kind: 처음 고를 종류, from: 보낸 화면, code: 오류 코드 */
export function reportHref(
  opts: { kind?: GeneralReportKind; from?: ReportScreen; code?: string } = {},
) {
  const q = new URLSearchParams({ tab: "reports" });
  if (opts.kind) q.set("kind", opts.kind);
  if (opts.from) q.set("from", opts.from);
  if (opts.code) q.set("code", opts.code);
  return `/me?${q.toString()}`;
}

const kinds: GeneralReportKind[] = ["MISSING_NOTICE", "WRONG_INFO", "APP_ERROR", "ETC"];

export const reportKindParam = (value: string | null): GeneralReportKind =>
  kinds.includes(value as GeneralReportKind) ? (value as GeneralReportKind) : "MISSING_NOTICE";
