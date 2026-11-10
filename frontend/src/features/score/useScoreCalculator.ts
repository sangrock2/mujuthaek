"use client";

import { useState } from "react";
import { useScoreProfile } from "./queries";
import { pointsOf, scoreItems, totalOf, type ScoreItemKey, type ScoreSelection } from "./score";

/** 가점 계산기 상태: 내 조건으로 미리 채우고, 바꾸면 바로 다시 계산해요 */
export function useScoreCalculator() {
  const { data: profile } = useScoreProfile();
  const [sel, setSel] = useState<ScoreSelection>(profile.prefill);

  const items = scoreItems.map((i) => {
    const index = Math.min(sel[i.key], i.options.length - 1);
    const points = pointsOf(i.key, index);
    return { ...i, index, points, width: `${Math.round((points / i.max) * 100)}%` };
  });
  const total = totalOf(sel);
  const diff = total - profile.cutoff.score;

  return {
    profile,
    items,
    total,
    diff,
    set: (key: ScoreItemKey, index: number) => setSel((prev) => ({ ...prev, [key]: index })),
  };
}
