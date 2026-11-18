import type { NoticeDocumentItem } from "./mocks/notice-doc";

/** 원문에서 제공한 제출 시점끼리만 묶어요. 문구에서 대상·단계를 추측해 필수 서류를 숨기지 않아요. */
export function documentsBySubmission(items: NoticeDocumentItem[]) {
  const groups = new Map<string, NoticeDocumentItem[]>();
  for (const item of items) {
    const stage = item.submissionTime?.trim() || "제출 시점은 원문 확인";
    groups.set(stage, [...(groups.get(stage) ?? []), item]);
  }
  return [...groups.entries()];
}
