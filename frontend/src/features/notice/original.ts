import { pdfSections, sectionTitles } from "@/features/notice/format";
import type { usePdfViewer } from "@/features/notice/usePdfViewer";
import type { NoticeDoc, NoticeSectionKey, PdfAnchor } from "@/mocks/notice-doc";

/** 근거를 앱 안에서 열 곳: PDF 주소·이름, 쪽, 강조할 문장 */
export type OriginalPlace = {
  src: string;
  fileName: string;
  fileId?: string;
  page: number;
  quote?: string;
};

/**
 * 근거를 어디서 열지 정해요. null이면 앱 안에서 열 PDF가 없어 기관 사이트로 보내요.
 *
 * - 목업·예전 모양(source.files 없음): PDF 하나(pdfUrl)를 그 쪽으로
 * - anchor(섹션 근거): 그 근거의 PDF(fileId)가 앱 안에 있을 때만 그 쪽·문장으로. 어느 PDF인지 모르면(fileId null) 기관 사이트로
 *   (다른 PDF의 같은 쪽을 가리키지 않게)
 * - 쪽 없이: 대표 PDF 첫 쪽 · 쪽만(판정 화면): 글자를 읽은 PDF가 하나뿐일 때만 그 PDF
 */
export function resolveOriginal(
  doc: NoticeDoc,
  page?: number,
  anchor?: PdfAnchor,
): OriginalPlace | null {
  const { source } = doc;
  const files = source.files;
  if (!files) {
    return source.pdfUrl
      ? { src: source.pdfUrl, fileName: source.fileName, page: page ?? 1 }
      : null;
  }
  const byId = (id: string | null | undefined) => (id ? files.find((f) => f.id === id) : undefined);
  const place = (fileId: string | null | undefined, at: number, quote?: string | null) => {
    const f = byId(fileId);
    return f
      ? { src: f.pdfUrl, fileName: f.name, fileId: f.id, page: at, quote: quote ?? undefined }
      : null;
  };
  if (anchor) return place(anchor.fileId, page ?? 1, anchor.quote);
  if (page === undefined) return place(files[0]?.id, 1);
  return place(source.soleFileId, page);
}

/**
 * 공고 상세의 원문 열기: 섹션 「원문 p.N」·내 자격 「근거 원문」·「공고 원문 보기」를 앱 안 PDF(근거의 PDF·쪽·문장)나 기관 사이트로 보내요.
 * pdf는 화면이 맨 위에서 부른 usePdfViewer()예요(공고를 불러오기 전에도 훅 순서가 같게). viewer는 PdfViewer에 넘길 값이에요(앱 안 PDF가
 * 없으면 null).
 */
export function noticeOriginal(
  doc: NoticeDoc,
  pdf: ReturnType<typeof usePdfViewer>,
  onOpen?: (via: "pdf" | "site") => void,
) {
  const openOriginal = (page?: number, label?: string, anchor?: PdfAnchor) => {
    const place = resolveOriginal(doc, page, anchor);
    onOpen?.(place ? "pdf" : "site");
    if (place) pdf.show(place.page, label, { fileId: place.fileId, quote: place.quote });
    else window.open(doc.source.detailUrl, "_blank", "noreferrer");
  };

  /** 내 자격 「근거 원문」: 판정의 쪽이 섹션 근거 쪽과 같으면 그 근거(PDF·문장)로, 다르면 쪽만 */
  const openEligibility = (page?: number) => {
    const sectionPage = doc.pages.eligibility;
    if (page === undefined || page === sectionPage) {
      openOriginal(sectionPage, sectionTitles.eligibility.toc, doc.anchors?.eligibility);
    } else {
      openOriginal(page, sectionTitles.eligibility.toc);
    }
  };

  const files = doc.source.files;
  const current = files ? (files.find((f) => f.id === pdf.target?.fileId) ?? files[0]) : undefined;
  const src = current?.pdfUrl ?? doc.source.pdfUrl;
  // 뷰어 위 섹션 목차: 지금 연 PDF의 근거가 있는 섹션만 (다른 PDF의 쪽으로 옮기지 않게)
  const keyOf = new Map(
    (Object.keys(sectionTitles) as NoticeSectionKey[]).map((k) => [sectionTitles[k].toc, k]),
  );
  const sections = pdfSections(doc).filter((s) => {
    if (!doc.anchors || !current) return true;
    const key = keyOf.get(s.label);
    return key !== undefined && doc.anchors[key]?.fileId === current.id;
  });
  const viewer = src
    ? {
        open: pdf.open,
        onClose: pdf.close,
        src,
        fileName: current?.name ?? doc.source.fileName,
        detailUrl: doc.source.detailUrl,
        target: pdf.target,
        sections,
        onJump: (page: number, label: string) => {
          const key = keyOf.get(label);
          const anchor = key ? doc.anchors?.[key] : undefined;
          pdf.show(page, label, { fileId: current?.id, quote: anchor?.quote });
        },
      }
    : null;

  return { hasPdf: Boolean(doc.source.pdfUrl), openOriginal, openEligibility, viewer };
}
