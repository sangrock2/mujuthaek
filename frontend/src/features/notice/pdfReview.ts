import type { NoticeJudgment } from "@/features/notice/judgment";
import type { NoticeDoc, NoticeEvidence } from "@/features/notice/mocks/notice-doc";
import { squash } from "@/features/notice/pdfQuote";

type Location = { fileId: string; page: number; quote?: string };

export type PdfReviewItem = {
  id: string;
  label: string;
  group?: { id: string; label: string };
  reason?: string;
  location?: Location;
};

export const judgedReviewId = (targetId: string, itemId: string) =>
  `judgment/${encodeURIComponent(targetId)}/${encodeURIComponent(itemId)}`;
export const conditionReviewId = (id: string) => `condition/${id}`;
export const heldReviewId = (label: string) => `held/${label}`;
export const reviewAnchorId = (id: string) => `notice-pdf-review-${id}`;

function locationOf(doc: NoticeDoc, evidence: NoticeEvidence): Location | undefined {
  const { page, quote } = evidence;
  if (page === null || !Number.isInteger(page) || page < 1) return;
  const id = evidence.fileId ?? doc.source.soleFileId;
  const file = doc.source.files?.find((candidate) => candidate.id === id);
  if (!file || (file.pageCount !== null && page > file.pageCount)) return;
  return { fileId: file.id, page, quote: quote?.trim() || undefined };
}

/** 판정 요약이 공고 조건 문구에 그대로 있고, 해당 조건의 같은 쪽 근거가 하나일 때만 원문 인용을 사용해요. */
function sourceExcerpt(doc: NoticeDoc, text: string, page: number | undefined) {
  if (text.length < 12 || page === undefined) return;
  const candidates = doc.eligibility.filter((condition) => squash(condition.text).includes(text));
  if (candidates.length !== 1) return;
  const locations = (candidates[0].evidence ?? []).flatMap((evidence) => {
    if (evidence.page !== page) return [];
    const location = locationOf(doc, evidence);
    return location?.quote ? [location] : [];
  });
  const [location] = locations;
  if (
    location &&
    locations.every((other) => other.fileId === location.fileId && other.quote === location.quote)
  )
    return location;
}

export function pdfReviewItems(doc: NoticeDoc, judgment?: NoticeJudgment | null): PdfReviewItem[] {
  const saved = doc.eligibility.flatMap((condition) => condition.evidence ?? []);
  const judged =
    judgment?.targets.flatMap((target) =>
      target.items
        .filter((item) => item.status === "unknown")
        .map((item) => {
          const quote = item.quote ?? "";
          const text = squash(quote);
          // 판정 응답엔 파일 ID가 없어요. 여러 첨부가 있으면 같은 쪽·인용이 가리키는 파일이 하나일 때만 써요.
          const matches = new Set(
            text && item.page !== undefined
              ? saved.flatMap((e) =>
                  e.page === item.page && e.fileId && squash(e.quote ?? "") === text
                    ? [e.fileId]
                    : [],
                )
              : [],
          );
          const fileId = matches.size === 1 ? [...matches][0] : null;
          return {
            id: judgedReviewId(target.id, item.id),
            label: item.label,
            group: { id: target.id, label: target.name || "내 자격" },
            reason: item.reason,
            location:
              matches.size > 1
                ? undefined
                : ((matches.size === 0 ? sourceExcerpt(doc, text, item.page) : undefined) ??
                  locationOf(doc, { page: item.page ?? null, fileId, quote })),
          };
        }),
    ) ?? [];
  return [
    ...judged,
    ...doc.eligibility.flatMap((condition) => {
      const location = condition.evidence?.map((e) => locationOf(doc, e)).find(Boolean);
      return condition.checking || location
        ? [{ id: conditionReviewId(condition.id), label: condition.text || "신청 자격", location }]
        : [];
    }),
    ...(doc.held ?? []).map(({ label }) => ({
      id: heldReviewId(label),
      label: `${label} · 공고 내용 확인 중`,
    })),
  ];
}
