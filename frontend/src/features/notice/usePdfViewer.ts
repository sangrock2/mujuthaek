"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 열 때 이동할 쪽. nonce가 바뀌면 같은 쪽이어도 다시 이동해요.
 * fileId: 첨부가 여럿일 때 어느 PDF인지 (없으면 대표 PDF) · quote: 그 쪽에서 찾아 강조할 근거 문장 (못 찾으면 쪽만)
 */
export type PdfTarget = {
  page: number;
  label?: string;
  nonce: number;
  fileId?: string;
  quote?: string;
};

export type PdfTargetExtra = { fileId?: string | null; quote?: string | null };

/**
 * 원문 PDF 열기 · 닫기.
 * 열면 주소에 ?pdf=1을 붙여서 뒤로가기로 닫을 수 있어요.
 */
export function usePdfViewer() {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<PdfTarget | null>(null);
  const nonce = useRef(0);
  /** 이 화면에서 기록을 하나 쌓았는지 (닫을 때 뒤로가기로 지워요) */
  const pushed = useRef(false);

  useEffect(() => {
    const onPop = () => {
      pushed.current = false;
      setOpen(new URLSearchParams(window.location.search).has("pdf"));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const show = useCallback((page = 1, label?: string, extra?: PdfTargetExtra) => {
    nonce.current += 1;
    setTarget({
      page,
      label,
      nonce: nonce.current,
      fileId: extra?.fileId ?? undefined,
      quote: extra?.quote ?? undefined,
    });
    if (!new URLSearchParams(window.location.search).has("pdf")) {
      const url = new URL(window.location.href);
      url.searchParams.set("pdf", "1");
      window.history.pushState(null, "", url);
      pushed.current = true;
    }
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    if (pushed.current) {
      window.history.back();
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.delete("pdf");
    window.history.replaceState(null, "", url);
    setOpen(false);
  }, []);

  return { open, target, show, close };
}
