import { privacyPolicy, serviceTerms } from "./versions/v1";

export const legalVersions = [
  { kind: "privacy", publishedDate: "2026-11-14", reason: "최초 공개", document: privacyPolicy },
  { kind: "terms", publishedDate: "2026-11-14", reason: "최초 공개", document: serviceTerms },
] as const;

export function legalVersionPath(kind: string, version: string) {
  return `/legal/${encodeURIComponent(kind)}/${encodeURIComponent(version)}`;
}
