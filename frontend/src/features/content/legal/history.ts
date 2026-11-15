import { privacyPolicy, serviceTerms } from "./versions/v1";
import { privacyPolicy as updatedPrivacy } from "./versions/v1_1";

export const legalVersions = [
  {
    kind: "privacy",
    publishedDate: "2026-11-15",
    reason: "선택 이메일 인증·알림 수신 동의·해제 및 도메인 변경 안내",
    document: updatedPrivacy,
  },
  { kind: "privacy", publishedDate: "2026-11-14", reason: "최초 공개", document: privacyPolicy },
  { kind: "terms", publishedDate: "2026-11-14", reason: "최초 공개", document: serviceTerms },
] as const;

export function legalVersionPath(kind: string, version: string) {
  return `/legal/${encodeURIComponent(kind)}/${encodeURIComponent(version)}`;
}
