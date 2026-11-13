"use client";

import { useEffect } from "react";

/** API가 브라우저에서만 닿는 환경에서도 실제 상세 이름을 탭에 보여줘요. */
export function useDetailTitle(title?: string) {
  useEffect(() => {
    if (title) document.title = `${title} | 무주택자들`;
  }, [title]);
}
