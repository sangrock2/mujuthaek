"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Maximize,
  Minus,
  Plus,
  X,
} from "lucide-react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { PdfReviewList } from "@/features/notice/components/PdfReviewList";
import { type QuoteBox, quoteBoxes } from "@/features/notice/pdfQuote";
import type { PdfReviewItem } from "@/features/notice/pdfReview";
import type { PdfTarget } from "@/features/notice/usePdfViewer";
import { cn } from "@/shared/lib/cn";
import { safeExternalUrl } from "@/shared/lib/safeUrl";

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.2;
/** 쪽 사이 간격 */
const PAGE_GAP = 12;
/** 강조한 문장 위로 남길 여백 */
const QUOTE_MARGIN = 96;

/** 강조 결과: 찾았으면 그 쪽 안 위치(px), 못 찾았으면 missed */
type QuoteResult = { nonce: number; top?: number; missed?: boolean };

type PdfViewerProps = {
  open: boolean;
  onClose: () => void;
  src: string;
  fileName: string;
  notice?: { title: string; summary?: string | null };
  /** 불러오지 못하면 보내는 기관 공고 페이지 (없으면 안내만) */
  detailUrl?: string;
  /** 로그인이 필요한 주소(관리자)처럼 직접 받아야 하면: PDF 바이트를 돌려줘요. 이때는 내려받기·새 창 단추를 숨겨요 */
  fetchData?: (src: string) => Promise<ArrayBuffer>;
  target: PdfTarget | null;
  /** 뷰어 위 섹션 목차 (쪽 순서) */
  sections?: { label: string; page: number; summary?: string }[];
  /** 섹션을 누르면 그 쪽으로 이동해요 */
  onJump?: (page: number, label: string) => void;
  reviewItems?: PdfReviewItem[];
  onReviewPick?: (id: string) => void;
  /** web: 요약과 PDF 비교 화면 · mobile: 아래 시트 · dialog: 가운데 창(관리자) */
  variant: "web" | "mobile" | "dialog";
};

/** 공고 원문 PDF 보기. 근거 문장(target.quote)을 그 쪽 글자 층에서 찾으면 강조하고, 못 찾으면 쪽만 열어요 */
export function PdfViewer(props: PdfViewerProps) {
  if (!props.open) return null;
  // 다른 PDF로 바꾸면 처음부터 다시 그려요 (쪽 위치·크기를 섞지 않게)
  return <PdfViewerPanel key={props.src} {...props} />;
}

function PdfViewerPanel({
  onClose,
  src,
  fileName,
  notice,
  detailUrl,
  fetchData,
  target,
  variant,
  sections = [],
  onJump,
  reviewItems = [],
  onReviewPick,
}: PdfViewerProps) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState(false);
  /** 첫 쪽의 세로/가로 비율 (그리기 전 자리 잡기용) */
  const [ratio, setRatio] = useState(1.414);
  const [zoom, setZoom] = useState(1);
  const [current, setCurrent] = useState(1);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [fitPage, setFitPage] = useState(variant === "web");
  const comparison = useRef<HTMLDialogElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const jumpedTo = useRef<number>(undefined);
  const pageEls = useRef(new Map<number, HTMLDivElement>());
  const [quote, setQuote] = useState<QuoteResult | null>(null);
  const fetcher = useRef(fetchData);
  // 기관 공고 페이지는 http·https 주소일 때만 링크로 보여요 (2026-11-16 보안 감사 L-4)
  const siteUrl = safeExternalUrl(detailUrl);

  useEffect(() => {
    const dialog = comparison.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  // PDF 불러오기 (pdf.js는 브라우저에서만 불러와요)
  useEffect(() => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | null = null;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        // 범위 요청(Range) 없이 한 번에 받아요: api가 Range를 받지 않고, 다른 주소(로컬 백엔드)면 CORS 사전 요청이 생겨요
        task = fetcher.current
          ? pdfjs.getDocument({ data: await fetcher.current(src) })
          : pdfjs.getDocument({ url: src, disableRange: true, disableStream: true });
        const loaded = await task.promise;
        const vp = (await loaded.getPage(1)).getViewport({ scale: 1 });
        if (cancelled) return;
        setRatio(vp.height / vp.width);
        setDoc(loaded);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [src]);

  // 보이는 너비에 맞춰 그려요
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setViewport({ width: Math.floor(width), height: Math.floor(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const usableHeight = Math.max(0, viewport.height - 2 * PAGE_GAP);
  const fittedWidth = fitPage ? Math.min(viewport.width, usableHeight / ratio) : viewport.width;
  const pageWidth = Math.floor(fittedWidth * zoom);

  const goTo = useCallback((page: number, smooth = true) => {
    const el = pageEls.current.get(page);
    const box = scroller.current;
    if (!el || !box) return;
    box.scrollTo({
      top: el.offsetTop - PAGE_GAP,
      behavior:
        smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "smooth"
          : "auto",
    });
    setCurrent(page);
  }, []);

  // 목차에서 누른 쪽으로 이동해요.
  useEffect(() => {
    if (!doc || !target || pageWidth === 0 || jumpedTo.current === target.nonce) return;
    jumpedTo.current = target.nonce;
    goTo(Math.min(Math.max(1, target.page), doc.numPages), false);
  }, [doc, target, pageWidth, goTo]);
  const invalidReviewPage = Boolean(doc && target?.reviewId && target.page > doc.numPages);
  const missed = invalidReviewPage || (quote?.missed === true && quote.nonce === target?.nonce);
  const highlighted = quote?.nonce === target?.nonce && quote?.top !== undefined;

  // 근거 문장을 찾으면 그 줄이 보이게 내려요
  const onQuote = useCallback(
    (result: QuoteResult) => {
      setQuote(result);
      if (result.top === undefined) return;
      const box = scroller.current;
      const el = target
        ? pageEls.current.get(Math.min(target.page, doc?.numPages ?? target.page))
        : undefined;
      if (box && el)
        box.scrollTo({ top: el.offsetTop + Math.max(-PAGE_GAP, result.top - QUOTE_MARGIN) });
    },
    [target, doc],
  );
  const highlight =
    doc && target?.quote && !invalidReviewPage
      ? { page: Math.min(target.page, doc.numPages), quote: target.quote, nonce: target.nonce }
      : null;

  // 다음 쪽이 화면 아래에 보여도 지금 읽는 쪽은 화면 위쪽을 기준으로 골라요.
  const onScroll = () => {
    const box = scroller.current;
    if (!box || !doc) return;
    if (box.scrollTop > 0 && box.scrollHeight - box.clientHeight - box.scrollTop <= 1) {
      setCurrent(doc.numPages);
      return;
    }
    const top = box.scrollTop + PAGE_GAP + 1;
    let page = 1;
    for (const [n, el] of pageEls.current) if (el.offsetTop <= top && n > page) page = n;
    setCurrent(page);
  };

  useEffect(() => {
    if (variant === "web") return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, variant]);

  const numPages = doc?.numPages ?? 0;
  /** 지금 쪽이 속한 섹션 쪽 (그 쪽 이전에서 가장 가까운 섹션) */
  const activePage = sections.reduce(
    (page, section) => (section.page <= current ? Math.max(page, section.page) : page),
    0,
  );
  const sectionsAtPage = sections.filter((section) => section.page === activePage);
  const selectedSection =
    sectionsAtPage.find(
      (section) => target?.page === section.page && target.label === section.label,
    ) ?? (sectionsAtPage.length === 1 ? sectionsAtPage[0] : undefined);

  const sectionBar = sections.length > 0 && onJump && (
    <nav
      aria-label="원문 섹션"
      className={cn(
        "border-line-soft flex gap-[6px] overflow-x-auto border-b border-solid px-[12px] py-[8px]",
        variant === "web" && "bg-bg px-4",
      )}
    >
      {sections.map((sec) => {
        const on = sec === selectedSection;
        return (
          <button
            key={sec.label}
            type="button"
            aria-current={on ? "true" : undefined}
            ref={(el) => {
              if (on && el?.parentElement) {
                // 목차 가로 스크롤만 옮겨요. scrollIntoView는 바깥 공고 본문까지 맨 위로 옮겨요.
                const bar = el.parentElement;
                const delta = el.getBoundingClientRect().left - bar.getBoundingClientRect().left;
                if (delta < 0 || delta + el.clientWidth > bar.clientWidth)
                  bar.scrollLeft += delta - (bar.clientWidth - el.clientWidth) / 2;
              }
            }}
            onClick={() => onJump(sec.page, sec.label)}
            className={cn(
              "rounded-pill inline-flex min-h-[36px] flex-none cursor-pointer items-center gap-[4px] border-0 px-[12px] text-[13px] font-bold whitespace-nowrap",
              on ? "bg-brand text-white" : "bg-fill text-text-sub",
            )}
          >
            {sec.label}
            <span className={cn("font-semibold", on ? "text-white" : "text-text-tertiary")}>
              p.{sec.page}
            </span>
          </button>
        );
      })}
    </nav>
  );
  const iconBtn =
    "text-text-sub hover:bg-fill focus-visible:outline-brand inline-flex size-[44px] flex-none cursor-pointer items-center justify-center rounded-[10px] border-0 bg-transparent disabled:cursor-default disabled:opacity-40";

  const toolbar = (
    <div
      role="group"
      aria-label="PDF 보기 도구"
      className="border-line-soft bg-surface flex items-center border-b border-solid px-[5px] py-[3px] sm:gap-[2px] sm:px-[8px]"
    >
      <button
        type="button"
        aria-label="이전 쪽"
        disabled={current <= 1}
        onClick={() => goTo(current - 1)}
        className={iconBtn}
      >
        <ChevronLeft size={20} aria-hidden />
      </button>
      <span
        aria-live="polite"
        className="min-w-[40px] text-center text-[14px] font-bold sm:min-w-[56px]"
      >
        {numPages ? `${current} / ${numPages}` : "–"}
      </span>
      <button
        type="button"
        aria-label="다음 쪽"
        disabled={!numPages || current >= numPages}
        onClick={() => goTo(current + 1)}
        className={iconBtn}
      >
        <ChevronRight size={20} aria-hidden />
      </button>
      <span className="flex-1" />
      {variant === "web" && (
        <button
          type="button"
          className={cn(
            iconBtn,
            "w-auto gap-[5px] px-[8px] text-[13px] font-bold",
            fitPage && "bg-fill",
          )}
          aria-pressed={fitPage}
          onClick={() => {
            setFitPage((value) => !value);
            setZoom(1);
            requestAnimationFrame(() => goTo(current, false));
          }}
        >
          <Maximize size={16} aria-hidden /> 쪽 맞춤
        </button>
      )}
      <button
        type="button"
        aria-label="축소"
        disabled={zoom <= ZOOM_MIN}
        onClick={() => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(1)))}
        className={iconBtn}
      >
        <Minus size={18} aria-hidden />
      </button>
      <span className="text-text-sub min-w-[36px] text-center text-[13px] font-semibold sm:min-w-[44px]">
        {Math.round(zoom * 100)}%
      </span>
      <button
        type="button"
        aria-label="확대"
        disabled={zoom >= ZOOM_MAX}
        onClick={() => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(1)))}
        className={iconBtn}
      >
        <Plus size={18} aria-hidden />
      </button>
      {!fetchData && (
        <a href={src} download={fileName} aria-label="PDF 내려받기" className={iconBtn}>
          <Download size={18} aria-hidden />
        </a>
      )}
      {variant === "web" && !fetchData && (
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="새 창에서 열기"
          className={iconBtn}
        >
          <ExternalLink size={18} aria-hidden />
        </a>
      )}
    </div>
  );

  const evidenceControls = (
    <>
      {reviewItems.length > 0 && onReviewPick && (
        <PdfReviewList
          items={reviewItems}
          selected={target?.reviewId}
          highlighted={highlighted}
          missed={missed}
          comparison={variant === "web"}
          onPick={onReviewPick}
        />
      )}
      {variant !== "web" &&
        (target?.reviewId && sectionBar ? (
          <details key={target.reviewId} className="border-line-soft border-b">
            <summary className="text-text-sub cursor-pointer px-3 py-1.5 text-[12px] font-bold">
              원문 목차
            </summary>
            {sectionBar}
          </details>
        ) : (
          sectionBar
        ))}
    </>
  );

  const body = (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {toolbar}
      {variant === "web" ? sectionBar : evidenceControls}
      <div
        ref={scroller}
        onScroll={onScroll}
        aria-label="PDF 페이지 영역"
        tabIndex={0}
        className={cn(
          "bg-fill relative min-h-0 flex-1 overflow-auto overscroll-contain px-[12px]",
          variant === "web" && "bg-line-soft",
        )}
      >
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-[12px] px-[24px] text-center">
            <span className="text-[16px] font-bold">원문을 불러오지 못했어요</span>
            {siteUrl ? (
              <>
                <span className="text-text-sub text-[14px]">
                  기관 사이트에서 원문을 확인해 주세요
                </span>
                <a
                  href={siteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-surface text-text hover:text-text inline-flex min-h-[44px] items-center gap-[6px] rounded-sm px-[16px] text-[14px] font-bold no-underline"
                >
                  <ExternalLink size={16} aria-hidden />
                  기관 사이트에서 보기
                </a>
              </>
            ) : (
              <span className="text-text-sub text-[14px]">
                우리 저장소에 원본이 없거나 잠시 불러올 수 없어요
              </span>
            )}
          </div>
        ) : !doc ? (
          <div className="text-text-sub flex h-full items-center justify-center text-[14px]">
            원문을 불러오고 있어요
          </div>
        ) : (
          <div
            className="mx-auto flex flex-col py-[12px]"
            style={{ width: pageWidth, gap: PAGE_GAP }}
          >
            {Array.from({ length: numPages }, (_, i) => i + 1).map((n) => (
              <PdfPage
                key={n}
                doc={doc}
                n={n}
                width={pageWidth}
                ratio={ratio}
                root={scroller}
                highlight={highlight?.page === n ? highlight : null}
                onQuote={onQuote}
                register={(el) => {
                  if (el) pageEls.current.set(n, el);
                  else pageEls.current.delete(n);
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );

  if (variant === "mobile" || variant === "dialog") {
    const dialog = variant === "dialog";
    return (
      <div
        className={cn(
          "fixed inset-0 z-[40] flex flex-col",
          dialog ? "items-center justify-center" : "justify-end",
        )}
      >
        <button
          type="button"
          aria-label="원문 닫기"
          onClick={onClose}
          className="absolute inset-0 cursor-default border-0 bg-[rgba(25,31,40,0.45)]"
        />
        <section
          role="dialog"
          aria-modal="true"
          aria-label="공고 원문"
          className={cn(
            "bg-surface relative flex flex-col overflow-hidden",
            dialog ? "h-[92dvh] w-[min(92vw,900px)] rounded-[20px]" : "h-[92dvh] rounded-t-[20px]",
          )}
        >
          {!dialog && (
            <span aria-hidden className="bg-line mx-auto mt-[8px] h-[4px] w-[40px] rounded-[2px]" />
          )}
          <div className="border-line-soft flex items-center justify-between gap-2 border-b px-4 pt-2 pb-1">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="bg-brand-soft text-brand-strong flex size-9 shrink-0 items-center justify-center rounded-sm">
                <FileText size={18} aria-hidden />
              </span>
              <div className="flex min-w-0 flex-col">
                <span className="text-text-sub text-[11px] font-bold">공고 원문 PDF</span>
                <h2 className="m-0 truncate text-[15px] font-extrabold" title={fileName}>
                  {fileName}
                </h2>
              </div>
            </div>
            <button type="button" aria-label="원문 닫기" onClick={onClose} className={iconBtn}>
              <X size={22} aria-hidden />
            </button>
          </div>
          {body}
        </section>
      </div>
    );
  }

  const currentReview = reviewItems.find((item) => item.id === target?.reviewId);
  return (
    <dialog
      ref={comparison}
      aria-label="공고 원문 비교"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      className="bg-bg text-text fixed inset-0 m-0 h-[100dvh] max-h-none w-screen max-w-none overflow-hidden border-0 p-0 open:flex open:flex-col"
    >
      <header className="border-line bg-surface flex min-w-0 shrink-0 items-center gap-4 border-b px-5 py-2.5 xl:px-6">
        <button
          type="button"
          aria-label="원문 닫기"
          onClick={onClose}
          className="rounded-control border-line text-text hover:bg-fill flex min-h-[44px] shrink-0 cursor-pointer items-center gap-1.5 border px-3 text-[13px] font-bold"
        >
          <X size={17} aria-hidden /> 비교 닫기
        </button>
        <div className="border-line-soft flex min-w-0 flex-col gap-0.5 border-l pl-4">
          <h2 className="m-0 text-[13px] font-bold">공고 원문 비교</h2>
          {notice && <p className="text-text-sub truncate text-[14px]">{notice.title}</p>}
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section
          aria-label="공고 요약과 근거"
          className="border-line bg-surface flex min-h-0 flex-col gap-4 overflow-y-auto overscroll-contain border-r p-5 xl:p-6"
        >
          <div className="flex flex-col gap-2">
            <h3 className="tracking-title m-0 text-[21px] font-extrabold">요약 및 자격 근거</h3>
            {notice?.summary && (
              <p className="text-text-sub text-[14px] leading-relaxed">{notice.summary}</p>
            )}
          </div>
          {sections.length > 0 && onJump && (
            <ul
              role="list"
              aria-label="공고 요약 근거"
              className="m-0 flex list-none flex-col gap-2 p-0"
            >
              {sections.map((section) => {
                const selected = section === selectedSection && !target?.reviewId;
                return (
                  <li key={section.label}>
                    <button
                      type="button"
                      aria-current={selected || undefined}
                      onClick={() => onJump(section.page, section.label)}
                      className={cn(
                        "rounded-control flex min-h-[52px] w-full cursor-pointer flex-col gap-1.5 border px-3.5 py-3 text-left",
                        selected
                          ? "border-brand bg-brand-soft"
                          : "border-line-soft bg-surface hover:bg-bg",
                      )}
                    >
                      <span className="flex w-full items-center justify-between gap-3">
                        <span className="text-[14px] font-extrabold">{section.label}</span>
                        <span className="text-brand-strong flex shrink-0 items-center gap-1 text-[12px] font-bold">
                          p.{section.page} <ChevronRight size={15} aria-hidden />
                        </span>
                      </span>
                      {section.summary && (
                        <span className="text-text-sub line-clamp-2 text-[13px] leading-relaxed">
                          {section.summary}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {currentReview && (
            <div className="rounded-card bg-brand-soft flex flex-col gap-[5px] p-[15px]">
              <p className="text-brand-strong text-[13px] font-bold">선택한 근거</p>
              <p className="text-[15px] font-extrabold">{currentReview.label}</p>
              {currentReview.reason && (
                <p className="text-text-sub text-[13px] leading-relaxed">{currentReview.reason}</p>
              )}
              <p role="status" className="text-text-sub text-[12px]">
                {currentReview.location
                  ? [
                      `${currentReview.location.page}쪽`,
                      highlighted
                        ? "근거 문장 강조됨"
                        : missed
                          ? "원문 문장을 찾지 못했어요"
                          : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : "정확한 위치 미확인"}
              </p>
              {highlighted && currentReview.location?.quote && (
                <blockquote className="text-text-sub border-brand mt-[3px] border-l-2 pl-[10px] text-[13px] leading-relaxed">
                  {currentReview.location.quote}
                </blockquote>
              )}
            </div>
          )}
          {reviewItems.length > 0 && onReviewPick && (
            <div className="rounded-control border-line-soft bg-bg overflow-hidden border [&_section:last-child]:border-b-0">
              {evidenceControls}
            </div>
          )}
        </section>
        <section aria-label="공고 원문" className="bg-surface flex min-h-0 min-w-0 flex-col">
          <div className="border-line-soft bg-bg flex shrink-0 items-center gap-2.5 border-b px-4 py-2.5">
            <span className="bg-brand-soft text-brand-strong flex size-9 shrink-0 items-center justify-center rounded-sm">
              <FileText size={18} aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-text-sub text-[11px] font-bold">공고 원문 PDF</p>
              <h3 className="m-0 truncate text-[14px] font-extrabold" title={fileName}>
                {fileName}
              </h3>
            </div>
          </div>
          {body}
        </section>
      </div>
    </dialog>
  );
}

/** 한 쪽: 화면 근처에 오면 그려요 */
function PdfPage({
  doc,
  n,
  width,
  ratio,
  root,
  register,
  highlight,
  onQuote,
}: {
  doc: PDFDocumentProxy;
  n: number;
  width: number;
  ratio: number;
  root: React.RefObject<HTMLDivElement | null>;
  register: (el: HTMLDivElement | null) => void;
  /** 이 쪽에서 찾아 강조할 근거 문장 */
  highlight: { quote: string; nonce: number } | null;
  onQuote: (result: QuoteResult) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [near, setNear] = useState(false);
  const [height, setHeight] = useState<number | null>(null);
  const [marks, setMarks] = useState<{ nonce: number; boxes: QuoteBox[] } | null>(null);
  const quote = highlight?.quote;
  const nonce = highlight?.nonce;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), {
      root: root.current,
      rootMargin: "800px 0px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, [root]);

  useEffect(() => {
    if (!near || width === 0 || !canvas.current) return;
    let task: RenderTask | null = null;
    let cancelled = false;
    (async () => {
      const page = await doc.getPage(n);
      if (cancelled || !canvas.current) return;
      const base = page.getViewport({ scale: 1 });
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: (width / base.width) * dpr });
      const c = canvas.current;
      c.width = Math.floor(viewport.width);
      c.height = Math.floor(viewport.height);
      setHeight(Math.round((width * base.height) / base.width));
      task = page.render({ canvas: c, viewport });
      await task.promise.catch(() => {});
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [near, width, doc, n]);

  // 근거 문장: 이 쪽 글자 층(getTextContent)에서 꼭 한 번 나오면 강조하고, 아니면 쪽만 열었다고 알려요
  useEffect(() => {
    if (!near || width === 0 || !quote || nonce === undefined) return;
    let cancelled = false;
    (async () => {
      try {
        const [pdfjs, page] = await Promise.all([import("pdfjs-dist"), doc.getPage(n)]);
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: width / base.width });
        const content = await page.getTextContent();
        const pieces = content.items.flatMap((item) =>
          "str" in item ? [{ str: item.str, transform: item.transform, width: item.width }] : [],
        );
        const boxes = quoteBoxes(
          pieces,
          quote,
          (t) => pdfjs.Util.transform(viewport.transform, t),
          viewport.scale,
        );
        if (cancelled) return;
        setMarks(boxes ? { nonce, boxes } : null);
        onQuote(
          boxes ? { nonce, top: Math.min(...boxes.map((b) => b.top)) } : { nonce, missed: true },
        );
      } catch {
        if (!cancelled) onQuote({ nonce, missed: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [near, width, doc, n, quote, nonce, onQuote]);
  const shown = marks && marks.nonce === nonce ? marks.boxes : [];

  return (
    <div
      ref={(el) => {
        box.current = el;
        register(el);
      }}
      aria-label={`${n}쪽`}
      className="bg-surface relative shadow-[0_1px_4px_rgba(25,31,40,0.12)]"
      style={{ width, height: height ?? Math.round(width * ratio) }}
    >
      <canvas ref={canvas} className="block h-full w-full" />
      {shown.map((b, i) => (
        <span
          key={i}
          aria-hidden
          className="pointer-events-none absolute rounded-[2px] bg-[rgba(255,196,0,0.38)] mix-blend-multiply"
          style={{ left: b.left, top: b.top, width: b.width, height: b.height }}
        />
      ))}
      {shown.length > 0 && <span className="sr-only">근거 문장을 노란색으로 표시했어요</span>}
    </div>
  );
}
