// 청약 가점 계산 규칙 (민영주택 가점제, 84점 만점)

export type ScoreOption = { label: string; points: number };
export type ScoreItemKey = "homeless" | "dependents" | "account";

export const SCORE_MAX = 84;

function homelessOptions(): ScoreOption[] {
  const list: ScoreOption[] = [
    { label: "해당 없음 · 만 30세 전 미혼 (0점)", points: 0 },
    { label: "1년 미만 (2점)", points: 2 },
  ];
  for (let y = 1; y <= 14; y++) {
    const p = 2 + y * 2;
    list.push({ label: `${y}년 이상 ~ ${y + 1}년 미만 (${p}점)`, points: p });
  }
  list.push({ label: "15년 이상 (32점)", points: 32 });
  return list;
}

function dependentOptions(): ScoreOption[] {
  const list: ScoreOption[] = [];
  for (let n = 0; n <= 5; n++) list.push({ label: `${n}명 (${5 + n * 5}점)`, points: 5 + n * 5 });
  list.push({ label: "6명 이상 (35점)", points: 35 });
  return list;
}

function accountOptions(): ScoreOption[] {
  const list: ScoreOption[] = [
    { label: "6개월 미만 (1점)", points: 1 },
    { label: "6개월 이상 ~ 1년 미만 (2점)", points: 2 },
  ];
  for (let y = 1; y <= 14; y++) {
    list.push({ label: `${y}년 이상 ~ ${y + 1}년 미만 (${2 + y}점)`, points: 2 + y });
  }
  list.push({ label: "15년 이상 (17점)", points: 17 });
  return list;
}

export const scoreItems: { key: ScoreItemKey; max: number; options: ScoreOption[] }[] = [
  { key: "homeless", max: 32, options: homelessOptions() },
  { key: "dependents", max: 35, options: dependentOptions() },
  { key: "account", max: 17, options: accountOptions() },
];

export type ScoreSelection = Record<ScoreItemKey, number>;

export function pointsOf(key: ScoreItemKey, index: number) {
  const item = scoreItems.find((i) => i.key === key)!;
  return item.options[Math.min(index, item.options.length - 1)].points;
}

export function totalOf(sel: ScoreSelection) {
  return scoreItems.reduce((t, i) => t + pointsOf(i.key, sel[i.key]), 0);
}

/** 총점 링: 브랜드 색이 차지하는 각도 */
export function ringStyle(total: number) {
  const deg = Math.round((total / SCORE_MAX) * 360);
  return {
    background: `conic-gradient(var(--color-brand) ${deg}deg, var(--color-brand-soft) 0deg)`,
  };
}
