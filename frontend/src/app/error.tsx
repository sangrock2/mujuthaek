"use client";

import { useEffect, useState } from "react";
import { MLoadErrorState, WebLoadErrorState } from "@/components/states/LoadErrorState";
import { StateFrame } from "@/components/states/StateFrame";

const formatAt = (d: Date) =>
  `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  // 오류가 난 시각을 한 번만 정해요
  const [at] = useState(() => formatAt(new Date()));
  const code =
    error instanceof Error && "digest" in error && typeof error.digest === "string"
      ? error.digest
      : undefined;

  useEffect(() => {
    console.error(error);
  }, [error]);

  const props = { onRetry: retry, code, at };
  return (
    <StateFrame web={<WebLoadErrorState {...props} />} mobile={<MLoadErrorState {...props} />} />
  );
}
