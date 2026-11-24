"use client";

import { useEffect, useRef, type RefObject } from "react";

export type InfiniteScrollState = {
  hasMore: boolean;
  loadingMore: boolean;
  loadMoreError: boolean;
  loadMore: () => void;
};

export function InfiniteScroll({
  data: { hasMore, loadingMore, loadMoreError, loadMore },
  label,
  scrollRoot,
}: {
  data: InfiniteScrollState;
  label: string;
  scrollRoot?: RefObject<HTMLElement | null>;
}) {
  const end = useRef<HTMLDivElement>(null);
  const supportsObserver = typeof IntersectionObserver !== "undefined";

  useEffect(() => {
    if (!supportsObserver || !hasMore || loadingMore || loadMoreError || !end.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMore();
      },
      { root: scrollRoot?.current ?? null, rootMargin: "0px 0px 200px" },
    );
    observer.observe(end.current);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loadMoreError, loadMore, scrollRoot, supportsObserver]);

  if (!hasMore) return null;
  return (
    <div ref={end} className="min-h-px shrink-0">
      {loadingMore && (
        <p role="status" className="text-text-sub m-0 py-3 text-center text-[14px]">
          {label} 목록을 더 불러오는 중이에요
        </p>
      )}
      {loadMoreError && !loadingMore && (
        <p role="alert" className="text-text-sub m-0 py-2 text-center text-[14px]">
          다음 {label} 목록을 불러오지 못했어요
        </p>
      )}
      {(!supportsObserver || loadMoreError) && !loadingMore && (
        <button
          type="button"
          onClick={loadMore}
          className="rounded-control bg-surface text-text min-h-[44px] w-full cursor-pointer px-4 text-[14px] font-bold"
        >
          {loadMoreError ? "다시 시도" : "더 보기"}
        </button>
      )}
    </div>
  );
}
