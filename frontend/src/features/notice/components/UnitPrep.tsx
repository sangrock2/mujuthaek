"use client";

import { Fragment } from "react";
import { useUnitPrep } from "@/features/notice/prepareCost";
import type { NoticeUnit } from "@/features/notice/mocks/notice";

/** 고른 집의 준비할 돈 (굵은 글씨). 가격 대상마다 다르면 「대상 금액 · 대상 금액」 */
export function UnitPrepValue({ unit }: { unit: NoticeUnit }) {
  const preps = useUnitPrep(unit);
  const same = preps.every((p) => p.text === preps[0]?.text);
  if (same) return <strong className="text-brand-strong">{preps[0]?.text ?? unit.prep}</strong>;
  return (
    <>
      {preps.map((p, i) => (
        <Fragment key={p.target ?? i}>
          {i > 0 && " · "}
          <span className="text-text-sub text-[0.9em]">{p.target}</span>{" "}
          <strong className="text-brand-strong">{p.text}</strong>
        </Fragment>
      ))}
    </>
  );
}
