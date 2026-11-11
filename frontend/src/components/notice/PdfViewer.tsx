"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, ExternalLink, Minus, Plus, X } from "lucide-react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { type QuoteBox, quoteBoxes } from "@/features/notice/pdfQuote";
import type { PdfTarget } from "@/features/notice/usePdfViewer";
import { cn } from "@/lib/cn";

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
  /** 불러오지 못하면 보내는 기관 공고 페이지 (없으면 안내만) */
  detailUrl?: string;
  /** 로그인이 필요한 주소(관리자)처럼 직접 받아야 하면: PDF 바이트를 돌려줘요. 이때는 내려받기·새 창 단추를 숨겨요 */
  fetchData?: (src: string) => Promise<ArrayBuffer>;
  target: PdfTarget | null;
  /** 뷰어 위 섹션 목차 (쪽 순서) */
  sections?: { label: string; page: number }[];
  /** 섹션을 누르면 그 쪽으로 이동해요 */
  onJump?: (page: number, label: string) => void;
  /** web: 왼쪽 패널 · mobile: 아래 시트 · dialog: 가운데 창(관리자) */
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
  detailUrl,
  fetchData,
  target,
  variant,
  sections = [],
  onJump,
}: PdfViewerProps) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState(false);
  /** 첫 쪽의 세로/가로 비율 (그리기 전 자리 잡기용) */
  const [ratio, setRatio] = useState(1.414);
  const [zoom, setZoom] = useState(1);
  const [current, setCurrent] = useState(1);
  const [width, setWidth] = useState(0);
  /** 섹션 표시를 숨긴 이동(nonce) */
  const [chipHidden, setChipHidden] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const pageEls = useRef(new Map<number, HTMLDivElement>());
  const [quote, setQuote] = useState<QuoteResult | null>(null);
  const fetcher = useRef(fetchData);

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
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pageWidth = Math.max(0, Math.floor(width * zoom));

  const goTo = useCallback((page: number, smooth = true) => {
    const el = pageEls.current.get(page);
    const box = scroller.current;
    if (!el || !box) return;
    box.scrollTo({ top: el.offsetTop - PAGE_GAP, behavior: smooth ? "smooth" : "auto" });
    setCurrent(page);
  }, []);

  // 목차에서 누른 쪽으로 이동하고, 어느 섹션인지 잠깐 보여줘요
  useEffect(() => {
    if (!doc || !target || width === 0) return;
    goTo(Math.min(Math.max(1, target.page), doc.numPages), false);
    const t = window.setTimeout(() => setChipHidden(target.nonce), 2500);
    return () => window.clearTimeout(t);
  }, [doc, target, width, goTo]);
  const missed = quote?.missed === true && quote.nonce === target?.nonce;
  const chip =
    doc && target && (target.label || missed) && chipHidden !== target.nonce
      ? [
          target.label && `${target.label} (p.${Math.min(target.page, doc.numPages)})`,
          missed && "근거 문장 위치는 표시하지 못했어요",
        ]
          .filter(Boolean)
          .join(" · ")
      : null;

  // 근거 문장을 찾으면 그 줄이 보이게 내려요
  const onQuote = useCallback(
    (result: QuoteResult) => {
      setQuote(result);
      if (result.top === undefined) return;
      const box = scroller.current;
      const el = target
        ? pageEls.current.get(Math.min(target.page, doc?.numPages ?? target.page))
        : undefined;
      if (box && el) box.scrollTo({ top: Math.max(0, el.offsetTop + result.top - QUOTE_MARGIN) });
    },
    [target, doc],
  );
  const highlight =
    doc && target?.quote
      ? { page: Math.min(target.page, doc.numPages), quote: target.quote, nonce: target.nonce }
      : null;

  // 스크롤 위치로 지금 쪽 계산
  const onScroll = () => {
    const box = scroller.current;
    if (!box || !doc) return;
    const mid = box.scrollTop + box.clientHeight / 3;
    let page = 1;
    for (const [n, el] of pageEls.current) if (el.offsetTop <= mid && n > page) page = n;
    setCurrent(page);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const numPages = doc?.numPages ?? 0;
  /** 지금 쪽이 속한 섹션 쪽 (그 쪽 이전에서 가장 가까운 섹션) */
  const activePage = sections.reduce((acc, sec) => (sec.page <= current ? sec.page : acc), 0);

  const sectionBar = sections.length > 0 && onJump && (
    <nav
      aria-label="원문 섹션"
      className="border-line-soft flex gap-[6px] overflow-x-auto border-b border-solid px-[12px] py-[8px]"
    >
      {sections.map((sec) => {
        // 같은 쪽에 섹션이 여럿이면 누른 섹션만 표시해요
        const picked =
          target?.page === activePage && sections.some((x) => x.label === target.label);
        const on = sec.page === activePage && (!picked || sec.label === target?.label);
        return (
          <button
            key={sec.label}
            type="button"
            aria-current={on ? "true" : undefined}
            ref={(el) => {
              if (on) el?.scrollIntoView({ block: "nearest", inline: "nearest" });
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
    "text-text-sub inline-flex size-[40px] flex-none cursor-pointer items-center justify-center rounded-[10px] border-0 bg-transparent disabled:cursor-default disabled:opacity-40";

  const toolbar = (
    <div className="border-line-soft flex items-center gap-[2px] border-b border-solid px-[8px] py-[6px]">
      <button
        type="button"
        aria-label="이전 쪽"
        disabled={current <= 1}
        onClick={() => goTo(current - 1)}
        className={iconBtn}
      >
        <ChevronLeft size={20} aria-hidden />
      </button>
      <span aria-live="polite" className="min-w-[56px] text-center text-[14px] font-bold">
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
      <button
        type="button"
        aria-label="축소"
        disabled={zoom <= ZOOM_MIN}
        onClick={() => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(1)))}
        className={iconBtn}
      >
        <Minus size={18} aria-hidden />
      </button>
      <span className="text-text-sub min-w-[44px] text-center text-[13px] font-semibold">
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
          rel="noreferrer"
          aria-label="새 창에서 열기"
          className={iconBtn}
        >
          <ExternalLink size={18} aria-hidden />
        </a>
      )}
    </div>
  );

  const body = (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {toolbar}
      {sectionBar}
      {chip && (
        <span
          role="status"
          className="rounded-pill bg-brand shadow-float absolute top-[108px] left-1/2 z-[1] -translate-x-1/2 px-[14px] py-[7px] text-[13px] font-bold whitespace-nowrap text-white"
        >
          {chip}
        </span>
      )}
      <div
        ref={scroller}
        onScroll={onScroll}
        className="bg-fill relative min-h-0 flex-1 overflow-auto overscroll-contain px-[12px]"
      >
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-[12px] px-[24px] text-center">
            <span className="text-[16px] font-bold">원문을 불러오지 못했어요</span>
            {detailUrl ? (
              <>
                <span className="text-text-sub text-[14px]">
                  기관 사이트에서 원문을 확인해 주세요
                </span>
                <a
                  href={detailUrl}
                  target="_blank"
                  rel="noreferrer"
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
          <div className="flex items-start justify-between gap-[12px] px-[20px] pt-[10px] pb-[8px]">
            <div className="flex min-w-0 flex-col gap-[2px]">
              <span className="truncate text-[18px] font-extrabold">
                {dialog ? fileName : "PDF 원문"}
              </span>
              <span className="text-text-sub text-[13px]">
                {dialog ? "근거 위치의 원문이에요" : "닫으면 보던 공고로 돌아가요"}
              </span>
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

  return (
    <section
      aria-label="공고 원문"
      className="bg-surface border-line shadow-float fixed top-0 bottom-0 left-0 z-[30] flex w-[min(46vw,680px)] flex-col border-r border-solid"
    >
      <div className="flex items-start justify-between gap-[12px] px-[20px] pt-[16px] pb-[10px]">
        <div className="flex min-w-0 flex-col gap-[2px]">
          <span className="text-text-tertiary text-[12px] font-semibold">원문 근거</span>
          <span className="truncate text-[17px] font-extrabold">{fileName}</span>
        </div>
        <button type="button" aria-label="원문 닫기" onClick={onClose} className={iconBtn}>
          <X size={22} aria-hidden />
        </button>
      </div>
      {body}
    </section>
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
