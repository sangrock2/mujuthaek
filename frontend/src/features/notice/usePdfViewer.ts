"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

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
 * 모바일에서 열면 주소에 ?pdf=1을 붙여 뒤로가기로 닫아요. PC는 본문 위치를 유지해 옆에 열어요.
 */
export function usePdfViewer() {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<PdfTarget | null>(null);
  const nonce = useRef(0);
  /** 이 화면에서 기록을 하나 쌓았는지 (닫을 때 뒤로가기로 지워요) */
  const pushed = useRef(false);
  const position = useRef<{ element: Element | null; top: number; y: number } | null>(null);
  const rememberPosition = useCallback(() => {
    if (!window.matchMedia("(min-width: 1024px)").matches) return;
    const focused = document.activeElement?.closest("main section");
    // 오른쪽 칸은 PDF를 열면 아래로 흐를 수 있어요. 그 칸 대신 읽고 있던 본문을 기준으로 삼아요.
    const element =
      focused && !focused.closest("aside")
        ? focused
        : [...document.querySelectorAll("main section")].find((section) => {
            const rect = section.getBoundingClientRect();
            return (
              !section.closest("aside") &&
              rect.width > 0 &&
              rect.bottom > 140 &&
              rect.top < window.innerHeight
            );
          });
    position.current = {
      element: element ?? null,
      top: element?.getBoundingClientRect().top ?? 0,
      y: window.scrollY,
    };
  }, []);
  useLayoutEffect(() => {
    const saved = position.current;
    if (!saved) return;
    position.current = null;
    const restore = () =>
      window.scrollTo({
        top: saved.element
          ? window.scrollY + saved.element.getBoundingClientRect().top - saved.top
          : saved.y,
        behavior: "instant",
      });
    restore();
    // 레이아웃 변경 뒤 브라우저의 스크롤 앵커 보정까지 끝난 위치를 다시 맞춰요.
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(restore);
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    const onPop = () => {
      pushed.current = false;
      setOpen(new URLSearchParams(window.location.search).has("pdf"));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const show = useCallback(
    (page = 1, label?: string, extra?: PdfTargetExtra) => {
      rememberPosition();
      nonce.current += 1;
      setTarget({
        page,
        label,
        nonce: nonce.current,
        fileId: extra?.fileId ?? undefined,
        quote: extra?.quote ?? undefined,
      });
      if (
        !window.matchMedia("(min-width: 1024px)").matches &&
        !new URLSearchParams(window.location.search).has("pdf")
      ) {
        const url = new URL(window.location.href);
        url.searchParams.set("pdf", "1");
        window.history.pushState(null, "", url);
        pushed.current = true;
      }
      setOpen(true);
    },
    [rememberPosition],
  );

  const close = useCallback(() => {
    rememberPosition();
    if (pushed.current) {
      window.history.back();
      return;
    }
    if (new URLSearchParams(window.location.search).has("pdf")) {
      const url = new URL(window.location.href);
      url.searchParams.delete("pdf");
      window.history.replaceState(null, "", url);
    }
    setOpen(false);
  }, [rememberPosition]);

  return { open, target, show, close };
}
