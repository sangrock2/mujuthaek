"use client";

import { useEffect, useState, type RefObject } from "react";
import { ArrowUp } from "lucide-react";
import { cn } from "@/shared/lib/cn";

export function ScrollToTop({
  scrollRoot,
  returnFocus,
  className,
}: {
  scrollRoot?: RefObject<HTMLElement | null>;
  returnFocus?: RefObject<HTMLElement | null>;
  className?: string;
}) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const root = scrollRoot?.current ?? window;
    const update = () => setVisible((root instanceof Window ? root.scrollY : root.scrollTop) > 480);
    root.addEventListener("scroll", update, { passive: true });
    update();
    return () => root.removeEventListener("scroll", update);
  }, [scrollRoot]);

  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={() => {
        const root = scrollRoot?.current ?? window;
        (
          returnFocus?.current ??
          scrollRoot?.current ??
          document.getElementById("main-content")
        )?.focus({
          preventScroll: true,
        });
        root.scrollTo({
          top: 0,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
        });
      }}
      className={cn(
        "rounded-pill bg-surface border-line-soft text-text fixed right-5 bottom-5 z-10 inline-flex min-h-11 cursor-pointer items-center gap-2 border px-4 text-sm font-bold shadow-md",
        className,
      )}
    >
      <ArrowUp size={16} aria-hidden />맨 위로
    </button>
  );
}
