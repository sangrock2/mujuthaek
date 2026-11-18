"use client";

import { useHasHousingInput } from "../personalization";

/** 아직 입력하지 않은 조건을 「지원 가능 0곳」으로 오해하지 않게 해요. */
export function PersonalizationSummary({
  kind,
  loading,
  error,
  eligible,
  needsInput,
}: {
  kind: "homes" | "benefits";
  loading: boolean;
  error: boolean;
  eligible: number;
  needsInput?: number | null;
}) {
  const hasInput = useHasHousingInput();
  if (error) return <>결과를 불러오지 못했어요. 다시 시도해 주세요</>;
  if (loading) return <>공고와 조건을 확인하고 있어요</>;
  if (!hasInput) return <>조건을 입력하면 지원 자격을 확인할 수 있어요</>;
  return (
    <>
      {kind === "homes" ? "입력한 조건으로 지원 가능 " : "조건에 맞춰 살펴볼 혜택 "}
      <strong className="text-brand-strong">
        {eligible}
        {kind === "homes" ? "곳" : "개"}
      </strong>
      {!!needsInput && ` · 확인 필요 ${needsInput}곳`}
    </>
  );
}
