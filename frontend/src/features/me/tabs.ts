import type { GeneralReportKind } from "@/features/me/api";

/** 내 정보 탭 (웹 ?tab= · 모바일 /me/{tab}) */
export type MeTab =
  "conditions" | "favorites" | "interests" | "notifications" | "privacy" | "reports";

export const meTabs: MeTab[] = [
  "conditions",
  "favorites",
  "interests",
  "notifications",
  "privacy",
  "reports",
];

/** 제보 화면으로 보내는 주소. kind: 처음 고를 종류, from: 보낸 화면, code: 오류 코드 */
export function reportHref(opts: { kind?: GeneralReportKind; from?: string; code?: string } = {}) {
  const q = new URLSearchParams({ tab: "reports" });
  if (opts.kind) q.set("kind", opts.kind);
  if (opts.from) q.set("from", opts.from);
  if (opts.code) q.set("code", opts.code);
  return `/me?${q.toString()}`;
}

const kinds: GeneralReportKind[] = ["MISSING_NOTICE", "WRONG_INFO", "APP_ERROR", "ETC"];

export const reportKindParam = (value: string | null): GeneralReportKind =>
  kinds.includes(value as GeneralReportKind) ? (value as GeneralReportKind) : "MISSING_NOTICE";
