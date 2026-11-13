"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

/** 데이터를 기다리는 자리와 같은 크기로 오류·다시 시도를 보여줘요. */
export function QueryFeedback({
  error,
  label = "내용",
  queryKey,
}: {
  error?: boolean;
  label?: string;
  queryKey?: readonly unknown[];
}) {
  const client = useQueryClient();
  const [retrying, setRetrying] = useState(false);
  const retry = async () => {
    setRetrying(true);
    try {
      await client.refetchQueries({ queryKey, type: "active" });
    } finally {
      setRetrying(false);
    }
  };
  return (
    <div
      role={error ? "alert" : "status"}
      aria-busy={!error || retrying}
      className="rounded-card bg-surface flex min-h-[280px] w-full flex-col justify-center gap-[16px] p-[24px]"
    >
      {error ? (
        <>
          <p className="text-text-sub m-0 text-[15px]">{label}을 불러오지 못했어요.</p>
          <button
            type="button"
            disabled={retrying}
            onClick={() => void retry()}
            className="rounded-control bg-brand min-h-[48px] cursor-pointer border-0 px-[20px] text-[15px] font-bold text-white disabled:opacity-60"
          >
            {retrying ? "다시 불러오는 중" : "다시 시도"}
          </button>
        </>
      ) : (
        <>
          <span className="text-text-sub text-[15px]">{label}을 불러오는 중이에요</span>
          {["w-2/3", "w-full", "w-4/5"].map((width) => (
            <span key={width} aria-hidden className={`bg-fill h-[32px] rounded-sm ${width}`} />
          ))}
        </>
      )}
    </div>
  );
}
